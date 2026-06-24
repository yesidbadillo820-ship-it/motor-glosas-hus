"""Few-shot dinámico de dictámenes ganadores (R-cerebro mejora #2).

Inyecta 1-2 ejemplos de dictámenes que YA GANARON (estado = LEVANTADA o
plantilla curada en `plantillas_gold`) para el mismo par (eps,
codigo_glosa). El LLM aprende del estilo y argumentación que funcionó
con esa misma EPS y código.

Estrategia de búsqueda (en orden):
  1. PlantillaGoldRecord activa para (eps, codigo) — curado por equipo
  2. GlosaRecord con estado=LEVANTADA, mismo (eps, codigo), dictamen
     >= 200 chars, ordenado por fecha_decision_eps DESC
  3. Vacío si no hay ninguno

Filosofía:
  • Solo se inyectan si existen — no perturba el caso base sin histórico
  • Truncamos cada ejemplo a 1500 chars para no inflar el prompt
  • Marcamos claramente "EJEMPLO" para que el LLM no copie textual
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Límite de chars por ejemplo para no inflar el contexto
_MAX_CHARS_EJEMPLO = 1500
# Límite de ejemplos a inyectar
_MAX_EJEMPLOS = 2


def _contiene_contrato_ajeno(argumento: str, eps: str) -> bool:
    """True si el ejemplo cita un contrato cuya EPS dueña NO es `eps`.

    Ronda 2 (12-jun-2026, CONTRATO CRUZADO): los ejemplos del banco HUS
    (eps=GENERICO) y los históricos venían con números de contrato reales de
    OTRAS EPS, y la instrucción "copia el cuerpo VERBATIM" hacía que la IA
    los arrastrara al dictamen (glosa DMBUG citando el S-13-1-03-1-04958 de
    FAMISANAR). Un ejemplo así NO se inyecta: contamina más de lo que aporta.
    """
    try:
        from app.services.glosa_ia_prompts import contratos_ajenos_citados

        return bool(contratos_ajenos_citados(argumento or "", eps))
    except Exception:
        return False


def obtener_ejemplos_gold(
    db,
    eps: str,
    codigo: str,
    max_ejemplos: int = _MAX_EJEMPLOS,
) -> list[dict]:
    """Devuelve hasta N dictámenes ganadores del par (eps, codigo).

    Prioridad (revisión 21 mayo 2026 — Yesid):
      1. **BANCO HUS** (eps=GENERICO, codigo='XX-G*' por familia del CUPS)
         — citas verificadas por el equipo jurídico, prelación absoluta.
      2. PlantillaGoldRecord específica del par (eps, codigo) — battle-tested
         (sólo si usos >= 3 evita inyectar plantillas curadas con citas
         inventadas que la IA todavía no ha refinado).
      3. GlosaRecord LEVANTADA histórica del par.

    Antes el banco HUS era último recurso; cuando había aunque sea UNA
    plantilla curada vieja para la EPS+código, esa ganaba y el banco
    HUS nunca se activaba — por eso los dictámenes seguían con citas
    inventadas como "Art. 10 Ley 1438" o "Art. 2 Ley 1122".

    Cada ejemplo: {"argumento": str, "fuente": "BANCO_HUS"|"GOLD"|"HISTORICO", "id": int}
    """
    if not db or not eps or not codigo:
        return []
    eps_norm = (eps or "").strip()
    cod_norm = (codigo or "").strip().upper()
    if not eps_norm or not cod_norm:
        return []

    ejemplos: list[dict] = []

    # 1) BANCO HUS — citas jurídicas verificadas, prelación absoluta
    try:
        from app.models.db import PlantillaGoldRecord

        prefijo = cod_norm[:2]  # "TA" de "TA0201", "SO" de "SO0501", etc.
        hus = (
            db.query(PlantillaGoldRecord)
            .filter(PlantillaGoldRecord.eps == "GENERICO")
            .filter(PlantillaGoldRecord.codigo_glosa.like(f"{prefijo}-G%"))
            .filter(PlantillaGoldRecord.activa == 1)
            .order_by(PlantillaGoldRecord.usos.desc())
            .limit(int(max_ejemplos))
            .all()
        )
        for h in hus:
            arg = (h.argumento or "").strip()
            if len(arg) < 200:
                continue
            # Ronda 2 12-jun-2026: plantilla genérica con contrato de OTRA
            # EPS (la IA lo copia verbatim) — no inyectar.
            if _contiene_contrato_ajeno(arg, eps_norm):
                logger.warning(
                    f"[FEW-SHOT-GOLD] plantilla BANCO_HUS #{h.id} omitida: "
                    f"cita contrato de otra EPS (glosa de {eps_norm})"
                )
                continue
            ejemplos.append(
                {
                    "argumento": arg[:_MAX_CHARS_EJEMPLO],
                    "fuente": "BANCO_HUS",
                    "id": h.id,
                }
            )
            if len(ejemplos) >= max_ejemplos:
                return ejemplos
    except Exception as e:
        logger.debug(f"few_shot_gold: error consultando banco HUS: {e}")

    # 2) PlantillaGoldRecord específica del par — solo battle-tested (usos >= 3)
    # para evitar inyectar plantillas curadas con citas inventadas.
    try:
        from app.models.db import PlantillaGoldRecord

        gold = (
            db.query(PlantillaGoldRecord)
            .filter(PlantillaGoldRecord.eps.ilike(eps_norm))
            .filter(PlantillaGoldRecord.codigo_glosa == cod_norm)
            .filter(PlantillaGoldRecord.activa == 1)
            .filter(PlantillaGoldRecord.usos >= 3)
            .order_by(PlantillaGoldRecord.usos.desc())
            .limit(int(max_ejemplos))
            .all()
        )
        for g in gold:
            arg = (g.argumento or "").strip()
            if len(arg) < 200:
                continue
            # Evitar duplicados con banco HUS
            if any(arg[:200] == e["argumento"][:200] for e in ejemplos):
                continue
            # Ronda 2 12-jun-2026: plantilla curada con contrato ajeno — fuera.
            if _contiene_contrato_ajeno(arg, eps_norm):
                logger.warning(
                    f"[FEW-SHOT-GOLD] plantilla GOLD #{g.id} omitida: "
                    f"cita contrato de otra EPS (glosa de {eps_norm})"
                )
                continue
            ejemplos.append(
                {
                    "argumento": arg[:_MAX_CHARS_EJEMPLO],
                    "fuente": "GOLD",
                    "id": g.id,
                }
            )
            if len(ejemplos) >= max_ejemplos:
                return ejemplos
    except Exception as e:
        logger.debug(f"few_shot_gold: error consultando PlantillaGold: {e}")

    # 2) Fallback: GlosaRecord LEVANTADA con dictamen útil
    try:
        from app.models.db import GlosaRecord

        rows = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.eps.ilike(eps_norm))
            .filter(GlosaRecord.codigo_glosa == cod_norm)
            .filter(GlosaRecord.estado == "LEVANTADA")
            .filter(GlosaRecord.dictamen.isnot(None))
            .order_by(GlosaRecord.fecha_decision_eps.desc())
            .limit(20)
            .all()
        )
        for r in rows:
            arg = (r.dictamen or "").strip()
            if len(arg) < 200:
                continue
            # Evitar duplicados: ya tenemos uno con este texto
            if any(arg[:200] == e["argumento"][:200] for e in ejemplos):
                continue
            # Ronda 2 12-jun-2026: histórico contaminado con contrato ajeno.
            if _contiene_contrato_ajeno(arg, eps_norm):
                logger.warning(
                    f"[FEW-SHOT-GOLD] histórico #{r.id} omitido: "
                    f"cita contrato de otra EPS (glosa de {eps_norm})"
                )
                continue
            ejemplos.append(
                {
                    "argumento": arg[:_MAX_CHARS_EJEMPLO],
                    "fuente": "HISTORICO",
                    "id": r.id,
                }
            )
            if len(ejemplos) >= max_ejemplos:
                break
    except Exception as e:
        logger.debug(f"few_shot_gold: error consultando GlosaRecord: {e}")

    return ejemplos


def bloque_few_shot_para_prompt(ejemplos: list[dict]) -> str:
    """Construye el bloque de texto a anexar al user_prompt.

    Si TODOS los ejemplos vienen del banco HUS (fuente=BANCO_HUS), usa
    instrucciones de "PLANTILLA BASE" — el LLM debe usar el texto verbatim
    como esqueleto y SÓLO personalizar: nombre del servicio, valores, nombre
    del paciente, fechas (estos últimos sólo si vienen en los soportes PDF).

    Si hay ejemplos de GOLD/HISTORICO, usa instrucciones tradicionales de
    "inspírate, no copies".
    """
    if not ejemplos:
        return ""

    solo_hus = all(e.get("fuente") == "BANCO_HUS" for e in ejemplos)

    if solo_hus:
        partes = [
            "",
            "═══════════════════════════════════════════════════════════════════",
            "★★★ PLANTILLA(S) JURÍDICA(S) BASE — BANCO HUS — MÁXIMA PRIORIDAD ★★★",
            "═══════════════════════════════════════════════════════════════════",
            (
                "ESTAS PLANTILLAS SON LA FUENTE OFICIAL DE LA RESPUESTA. "
                "ANULAN cualquier 'REGLA DURA' del system prompt sobre formato "
                "estándar de P1/P2/P3. El equipo jurídico del HUS aprobó cada "
                "palabra: citas, normas, sentencias, decretos, encabezado y cierre."
            ),
            "",
            "CÓMO USAR LA PLANTILLA (regla EXACTA):",
            (
                "  ① COPIA EL ENCABEZADO VERBATIM. La plantilla empieza con "
                "'ESE HUS NO ACEPTA GLOSA POR CONCEPTO DE [X]...'. NO lo cambies "
                "por el formato 'ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO "
                "DE [Y] SOBRE EL CÓDIGO...' del template estándar."
            ),
            (
                "  ② COPIA TODO EL CUERPO LEGAL VERBATIM — las citas a artículos, "
                "decretos y sentencias son JURÍDICAMENTE VERIFICADAS. No las "
                "reformules ni cambies los números."
            ),
            (
                "  ③ COPIA EL CIERRE VERBATIM: termina en 'SE SOLICITA EL "
                "LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO DE LO FACTURADO.' — "
                "NO agregues 'mesa de conciliación', '10 días hábiles', "
                "emails @hus.gov.co ni nada después del cierre."
            ),
            "",
            "ÚNICA PERSONALIZACIÓN PERMITIDA (los placeholders):",
            "  • Reemplazar 'LA ENTIDAD PAGADORA' o '{PAGADOR}' por el nombre real del pagador (del BLOQUE 1)",
            "  • Inyectar VALORES MONETARIOS del caso (objetado/facturado) si la plantilla deja huecos",
            "  • Inyectar NOMBRE DEL SERVICIO / CUPS del caso si la plantilla deja huecos",
            "  • NOMBRE DEL PACIENTE Y DOCUMENTO: solo si vienen en soportes PDF — si no hay PDF, OMITIR",
            "  • FECHAS DE ATENCIÓN: solo si vienen en soportes PDF — si no hay PDF, OMITIR",
            "",
        ]
        for i, ej in enumerate(ejemplos, 1):
            partes.append(f"--- PLANTILLA BASE #{i} (fuente: BANCO_HUS) ---")
            partes.append(ej["argumento"])
            partes.append("--- FIN PLANTILLA ---")
            partes.append("")
        partes.append(
            "⚠ PROHIBIDO ABSOLUTO: inventar nombres de pacientes, números de "
            "documento o fechas que NO estén en los soportes PDF o en el texto "
            "de la glosa. Si el dato no existe, omitir la mención."
        )
        partes.append(
            "⚠ PROHIBIDO ABSOLUTO: re-redactar las citas legales con palabras "
            "propias. La plantilla DICE 'Artículo 87 del Decreto 2423 de 1996' "
            "— NO digas 'Art. 10 Ley 1438 de 2011' ni otras citas inventadas."
        )
        partes.append(
            "⚠ ⚠ ⚠ PROHIBIDO ABSOLUTO (mayo 2026, regla nueva): NO AGREGUES "
            "NORMAS QUE NO ESTÉN LITERALMENTE EN LA PLANTILLA. El validador "
            "del HUS marca como ERROR cualquier 'Art. X Ley Y' que no esté en "
            "el corpus normativo cargado. La plantilla YA tiene las 2-3 normas "
            "verificadas que necesitas — NO agregues 'Art. 10 Ley 1438', "
            "'Art. 15 Ley 1122', 'Art. 2 Ley 1751' ni similares. Si tu instinto "
            "es 'reforzar el argumento con más normas', RESÍSTELO: el equipo "
            "jurídico ya seleccionó las normas óptimas."
        )
        partes.append(
            "⚠ TERMINA EXACTAMENTE DONDE TERMINA LA PLANTILLA. Si la plantilla "
            "termina en 'SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO "
            "ÍNTEGRO DE LO FACTURADO.', tu respuesta termina ahí. NO agregues "
            "párrafos 'DE ACUERDO CON EL ARTÍCULO X DE LA LEY Y' después del "
            "cierre. NO agregues 'EN ESTE SENTIDO, SE DEBE TENER EN CUENTA QUE...' "
            "con citas adicionales. La plantilla está completa por diseño."
        )
        partes.append("═══════════════════════════════════════════════════════════════════")
        partes.append("")
        return "\n".join(partes)

    # Comportamiento original: ejemplos GOLD o HISTORICO
    partes = [
        "",
        "═══ EJEMPLOS DE DICTÁMENES GANADORES PREVIOS (mismo eps + código) ═══",
        (
            "Estos casos ANTERIORES ganaron la glosa (LEVANTADA). "
            "Úsalos como referencia de ESTILO Y ARGUMENTACIÓN, "
            "adaptándolos al caso ACTUAL con los datos del BLOQUE 1. "
            "NO copies textualmente."
        ),
        "",
    ]
    for i, ej in enumerate(ejemplos, 1):
        fuente = ej.get("fuente", "?")
        partes.append(f"--- EJEMPLO {i} (fuente: {fuente}) ---")
        partes.append(ej["argumento"])
        partes.append("--- FIN EJEMPLO ---")
        partes.append("")
    partes.append(
        "⚠ El dictamen final debe usar los DATOS DEL BLOQUE 1 (CUPS, valor, "
        "EPS exactos del caso actual), no los del ejemplo."
    )
    partes.append("═══════════════════════════════════════════════════════════════════")
    partes.append("")
    return "\n".join(partes)


def construir_bloque_gold(
    db,
    eps: str,
    codigo: str,
    max_ejemplos: int = _MAX_EJEMPLOS,
) -> str:
    """Helper de un solo paso: busca y formatea."""
    try:
        ejemplos = obtener_ejemplos_gold(db, eps, codigo, max_ejemplos)
        if ejemplos:
            logger.info(
                f"[FEW-SHOT-GOLD] {len(ejemplos)} ejemplo(s) inyectado(s) "
                f"para par ({eps}, {codigo})"
            )
        return bloque_few_shot_para_prompt(ejemplos)
    except Exception as e:
        logger.warning(f"few_shot_gold: error construyendo bloque: {e}")
        return ""
