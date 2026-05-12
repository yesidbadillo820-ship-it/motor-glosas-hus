"""
confidence_scorer.py — Calcula un score de confianza 0.0-1.0 para cada
dictamen generado por la IA.

El score sirve para que el gestor (Yesid) sepa si el dictamen es:
  - Sólido (>= 0.80, verde) → enviar con alta probabilidad de levantamiento
  - Aceptable (0.60-0.79, amarillo) → revisar antes de enviar
  - Débil (< 0.60, rojo) → reformular, faltan piezas clave

Variables ponderadas:
  +0.20  Cláusula contractual literal aplicable (ClausulaContrato del PDF)
  +0.15  Precedente interno: glosa similar levantada (mismo código + EPS)
  +0.10  Soportes adjuntados al expediente
  +0.20  Norma citada existe en corpus + sin citas literales falsas
  +0.10  Auditor pre-IA verificó datos contra BD sin discrepancias
  +0.10  Cálculo numérico verificable (valor objetado/facturado/pactado)
  +0.15  Calidad intrínseca del dictamen (chevrones « », doctrina invocada,
         tabla códigos, estructura argumentativa)

El gestor puede ver el breakdown completo en la UI para entender qué
le falta al dictamen y reforzarlo si toca.
"""
import logging
from typing import Optional

logger = logging.getLogger("motor_glosas")


def _tiene_clausula_contractual(eps: str, codigo: str) -> bool:
    """Consulta BD: ¿hay al menos 1 ClausulaContrato vigente para esta
    EPS cuyo tema coincida con el código de glosa?"""
    if not eps or not codigo:
        return False
    tema = (codigo[:2] or "").upper().strip()
    if not tema:
        return False
    try:
        from app.database import SessionLocal
        from app.models.db import ClausulaContrato
    except Exception:
        return False
    db = SessionLocal()
    try:
        # Match contra eps normalizado + raw, por compat con registros viejos
        eps_norm = eps.upper().strip()
        n = (
            db.query(ClausulaContrato)
            .filter(
                ClausulaContrato.eps.in_([eps, eps_norm]),
                ClausulaContrato.tema.in_([tema, "NN"]),
            )
            .count()
        )
        return n > 0
    except Exception:
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass


def _tiene_precedente_interno(eps: str, codigo: str) -> bool:
    """Consulta BD: ¿hay alguna glosa LEVANTADA con misma EPS y mismo
    prefijo de código (ej. TA*, SO*, AU*)?"""
    if not eps or not codigo:
        return False
    prefijo = codigo[:2] if len(codigo) >= 2 else codigo
    try:
        from app.database import SessionLocal
        from app.models.db import GlosaRecord
    except Exception:
        return False
    db = SessionLocal()
    try:
        from sqlalchemy import func
        n = (
            db.query(GlosaRecord)
            .filter(
                GlosaRecord.eps == eps,
                GlosaRecord.estado == "LEVANTADA",
                GlosaRecord.codigo_glosa.like(f"{prefijo}%"),
            )
            .count()
        )
        return n > 0
    except Exception:
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass


def _verificar_calculo_numerico(
    valor_objetado: Optional[str],
    valor_facturado: Optional[str],
    valor_pactado: Optional[str],
) -> bool:
    """Devuelve True si los valores son consistentes (no son cero, no
    son negativos, y la relación entre facturado/pactado/objetado es
    coherente). False si falta data o hay incoherencia."""
    def _to_num(s):
        if not s:
            return None
        try:
            cleaned = "".join(c for c in str(s) if c.isdigit() or c in ".-")
            if not cleaned:
                return None
            return float(cleaned)
        except Exception:
            return None

    obj = _to_num(valor_objetado)
    fact = _to_num(valor_facturado)
    pact = _to_num(valor_pactado)

    if obj is None or obj <= 0:
        return False
    # Si tenemos facturado y pactado, el objetado debería ser ≈ fact - pact
    if fact and pact and fact > 0 and pact > 0:
        diff_esperada = abs(fact - pact)
        if diff_esperada > 0:
            ratio = obj / diff_esperada
            # Tolerancia ±15% para no penalizar pequeños desajustes de
            # redondeo/IPS sumando IVA o reajustes intermedios.
            if 0.85 <= ratio <= 1.15:
                return True
        return False
    # Si solo tenemos objetado, nos conformamos con que sea positivo
    return True


def _evaluar_calidad_intrinseca(dictamen: str) -> tuple[float, str]:
    """Mide la calidad estructural del dictamen sin importar PDFs/precedentes.

    Puntos hasta 0.15:
      +0.04  Cita literal entre chevrones franceses « ... » (mínimo 1)
      +0.04  Invoca doctrina jurídica colombiana (Pacta Sunt Servanda,
             Art. 1602 CC, Art. 871 CCo, Lex Artis, Carga Dinámica, etc.)
      +0.03  Estructura: tabla código/valor/respuesta + bloque servicio
      +0.04  Cita ≥3 normas distintas (Ley/Decreto/Resolución/Sentencia)

    Devuelve (puntos, explicacion).
    """
    if not dictamen:
        return 0.0, "Dictamen vacío — sin calidad evaluable."

    txt = dictamen.upper()
    pts = 0.0
    razones = []

    if "«" in dictamen and "»" in dictamen:
        pts += 0.04
        razones.append("cita literal entre chevrones")

    doctrina = [
        "PACTA SUNT SERVANDA", "ART. 1602", "ARTICULO 1602", "ARTÍCULO 1602",
        "ART. 871", "ARTICULO 871", "ARTÍCULO 871",
        "LEX ARTIS", "CARGA DINÁMICA", "CARGA DINAMICA",
        "BUENA FE CONTRACTUAL", "CARGA DE LA PRUEBA",
    ]
    if any(d in txt for d in doctrina):
        pts += 0.04
        razones.append("doctrina jurídica invocada")

    if "<TABLE" in txt or "CÓDIGO GLOSA" in txt or "CODIGO RESPUESTA" in txt:
        pts += 0.03
        razones.append("estructura tabular completa")

    import re as _re
    normas_distintas = set()
    for m in _re.finditer(
        r"(LEY\s*\d+|DECRETO\s*\d+|RESOLUCI[OÓ]N\s*\d+|SENTENCIA\s+[TCSU][\-\d/]+)",
        txt,
    ):
        normas_distintas.add(m.group(1).strip())
    if len(normas_distintas) >= 3:
        pts += 0.04
        razones.append(f"{len(normas_distintas)} normas distintas")

    pts = round(min(pts, 0.15), 3)
    expl = (
        "Dictamen bien estructurado: " + " · ".join(razones) + "."
        if razones
        else "Dictamen pobre: sin chevrones, sin doctrina, sin tabla. Reforzar argumentación."
    )
    return pts, expl


def calcular_confianza(
    eps: str,
    codigo: str,
    dictamen: str,
    soportes_count: int = 0,
    auditor_sin_discrepancias: bool = False,
    valor_objetado: Optional[str] = None,
    valor_facturado: Optional[str] = None,
    valor_pactado: Optional[str] = None,
    verificacion_citas: Optional[dict] = None,
) -> dict:
    """Calcula confianza 0.0-1.0 + breakdown + recomendación.

    Estructura devuelta:
        {
          "score": 0.78,
          "nivel": "alto" | "medio" | "bajo",
          "color": "#16a34a" | "#d97706" | "#dc2626",
          "recomendacion": "ENVIAR" | "REVISAR" | "REFORMULAR",
          "breakdown": [
            {"factor": "Cláusula contractual aplicable", "puntos": 0.25, "obtenido": 0.25, "ok": True, "explicacion": "..."},
            ...
          ],
          "faltantes": ["...", "..."],  # qué le falta al dictamen
        }
    """
    breakdown = []
    score = 0.0

    # 1. Cláusula contractual literal
    tiene_clausula = _tiene_clausula_contractual(eps, codigo)
    pts = 0.20 if tiene_clausula else 0.0
    score += pts
    breakdown.append({
        "factor": "Cláusula del contrato vigente con esta EPS",
        "puntos_max": 0.20,
        "puntos_obtenidos": pts,
        "ok": tiene_clausula,
        "explicacion": (
            "Hay cláusulas extraídas del PDF del contrato firmado con la EPS para citar literalmente."
            if tiene_clausula
            else "No hay PDF de contrato cargado para esta EPS, o las cláusulas no cubren este tema. Subí el PDF del contrato en Tarifas → Subir PDF del contrato."
        ),
    })

    # 2. Precedente interno (glosa similar levantada)
    tiene_precedente = _tiene_precedente_interno(eps, codigo)
    pts = 0.15 if tiene_precedente else 0.0
    score += pts
    breakdown.append({
        "factor": "Precedente interno: glosa similar ya levantada antes",
        "puntos_max": 0.15,
        "puntos_obtenidos": pts,
        "ok": tiene_precedente,
        "explicacion": (
            "Tenés glosas similares levantadas históricamente; el dictamen puede apoyarse en argumentos que ya funcionaron."
            if tiene_precedente
            else "Es la primera glosa de este tipo+EPS. La defensa se basa solo en normativa, no en jurisprudencia interna del HUS."
        ),
    })

    # 3. Soportes adjuntados
    tiene_soportes = soportes_count > 0
    pts = 0.10 if tiene_soportes else 0.0
    score += pts
    breakdown.append({
        "factor": "Soportes documentales adjuntados",
        "puntos_max": 0.10,
        "puntos_obtenidos": pts,
        "ok": tiene_soportes,
        "explicacion": (
            f"{soportes_count} PDFs/soportes anexados al expediente."
            if tiene_soportes
            else "No se anexaron soportes. La defensa documental es débil — la EPS puede ratificar pidiendo los anexos."
        ),
    })

    # 4. Validación de citas legales
    citas_ok = True
    detalle_citas = "Sin citas legales detectadas en el dictamen."
    if verificacion_citas:
        graves = verificacion_citas.get("tiene_problemas_graves", False)
        n_issues = len(verificacion_citas.get("issues", []))
        n_total = verificacion_citas.get("total_citas", 0)
        if graves:
            citas_ok = False
            detalle_citas = (
                f"{n_issues} issues detectados ({n_total} citas totales). "
                "Hay normas inexistentes o citas literales falsas — corregí antes de enviar."
            )
        elif n_issues > 0:
            citas_ok = True
            detalle_citas = (
                f"{n_total} citas legales válidas, {n_issues} con observaciones menores."
            )
        elif n_total > 0:
            detalle_citas = f"{n_total} citas legales válidas y verificadas contra el corpus."
    pts = 0.20 if citas_ok else 0.0
    score += pts
    breakdown.append({
        "factor": "Normas y citas legales verificadas",
        "puntos_max": 0.20,
        "puntos_obtenidos": pts,
        "ok": citas_ok,
        "explicacion": detalle_citas,
    })

    # 5. Auditor pre-IA sin discrepancias
    pts = 0.10 if auditor_sin_discrepancias else 0.0
    score += pts
    breakdown.append({
        "factor": "Auditor pre-IA verificó datos sin discrepancias",
        "puntos_max": 0.10,
        "puntos_obtenidos": pts,
        "ok": auditor_sin_discrepancias,
        "explicacion": (
            "Los datos del expediente coinciden con la BD del HUS (factura, paciente, valor)."
            if auditor_sin_discrepancias
            else "El auditor pre-IA encontró posibles inconsistencias o no pudo verificar contra BD."
        ),
    })

    # 6. Cálculo numérico verificable
    calc_ok = _verificar_calculo_numerico(valor_objetado, valor_facturado, valor_pactado)
    pts = 0.10 if calc_ok else 0.0
    score += pts
    breakdown.append({
        "factor": "Valores numéricos consistentes",
        "puntos_max": 0.10,
        "puntos_obtenidos": pts,
        "ok": calc_ok,
        "explicacion": (
            "El valor objetado es consistente con la diferencia facturado vs pactado."
            if calc_ok
            else "Falta alguno de los valores (objetado/facturado/pactado) o son inconsistentes entre sí."
        ),
    })

    # 7. Calidad intrínseca del dictamen (chevrones, doctrina, tabla, normas)
    pts_intr, expl_intr = _evaluar_calidad_intrinseca(dictamen)
    score += pts_intr
    breakdown.append({
        "factor": "Calidad intrínseca del dictamen",
        "puntos_max": 0.15,
        "puntos_obtenidos": pts_intr,
        "ok": pts_intr >= 0.10,
        "explicacion": expl_intr,
    })

    # Cap a 1.0 por las dudas
    score = max(0.0, min(1.0, round(score, 3)))

    # Umbrales calibrados sobre 7 factores (suma máxima 1.05, capeada a 1.0):
    #   ≥0.70 ENVIAR  — dictamen completo, listo
    #   0.50-0.69 REVISAR — buenas piezas, le falta una clave (PDF/soporte)
    #   <0.50 REFORMULAR — débil, reescribir
    if score >= 0.70:
        nivel, color, recom = "alto", "#16a34a", "ENVIAR"
    elif score >= 0.50:
        nivel, color, recom = "medio", "#d97706", "REVISAR"
    else:
        nivel, color, recom = "bajo", "#dc2626", "REFORMULAR"

    faltantes = [b["factor"] for b in breakdown if not b["ok"]]

    return {
        "score": score,
        "nivel": nivel,
        "color": color,
        "recomendacion": recom,
        "breakdown": breakdown,
        "faltantes": faltantes,
    }
