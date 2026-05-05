"""
citation_verifier.py — Valida que las normas y citas legales en el dictamen
correspondan al texto real del corpus normativa_completa.

Detecta 3 problemas comunes que la EPS usa para ratificar glosas:
  1. NORMA_INEXISTENTE — dictamen cita "Res. 9999/2099" que no existe
  2. ARTICULO_FUERA_DE_NORMA — cita Art. 47 de norma que no tiene Art. 47
  3. CITA_LITERAL_FALSA — texto entrecomillado «...» que no aparece literal

Salida: lista de issues con severidad. La UI los muestra como warnings
debajo del dictamen y sugiere reformulación.

NO bloquea el envío — el gestor decide si corrige o ignora. Pero al menos
no manda el dictamen a ciegas con citas inventadas.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger("motor_glosas")


# Patrones de citación legal típicos en dictámenes ESE HUS
PAT_RESOLUCION = re.compile(
    r"Resolución\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})|Res(?:olución)?\.?\s*(\d{1,5})[/\-](\d{2,4})",
    re.IGNORECASE,
)
PAT_DECRETO = re.compile(
    r"Decreto\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})",
    re.IGNORECASE,
)
PAT_LEY = re.compile(
    r"Ley\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})",
    re.IGNORECASE,
)
PAT_SENTENCIA = re.compile(
    r"(?:Sentencia\s+)?(T|C|SU)[\.\-]?\s*(\d{1,4})[/\-](\d{2,4})",
    re.IGNORECASE,
)
PAT_ARTICULO = re.compile(
    r"(?:art(?:ículo|iculo|\.)\s*)(\d{1,4})(?:\s*(?:de\s+(?:la\s+)?(Resolución|Ley|Decreto)\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})))?",
    re.IGNORECASE,
)
# Texto entrecomillado — chevrones franceses « » preferidos en el motor
PAT_CITA_LITERAL = re.compile(r"«([^«»]{15,800})»")
# Limpia HTML para comparar texto plano
PAT_HTML = re.compile(r"<[^>]+>")


def _quitar_html(s: str) -> str:
    return re.sub(r"\s+", " ", PAT_HTML.sub(" ", s or "")).strip()


def _normalizar(s: str) -> str:
    """Lower + sin acentos + sin puntuación + sin espacios extras para
    comparar fragmentos sin sufrir por mayúsculas/tildes/comillas."""
    if not s:
        return ""
    repl = str.maketrans("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN")
    s = s.translate(repl).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _buscar_clave_norma(tipo: str, numero: str, anio: str, normas: dict) -> Optional[str]:
    """Mapea (tipo, número, año) a la clave en _TODAS_LAS_NORMAS.

    El corpus usa claves tipo "res_2284_2023", "decreto_4747_2007",
    "ley_1438_2011", "sentencia_t_1025_2002". Probamos varios formatos.
    """
    n = numero.lstrip("0") or numero
    candidatos = [
        f"{tipo.lower()}_{n}_{anio}",
        f"{tipo.lower()}_{numero}_{anio}",
        f"res_{n}_{anio}" if tipo.lower().startswith("res") else None,
        f"decreto_{n}_{anio}" if tipo.lower().startswith("dec") else None,
        f"ley_{n}_{anio}" if tipo.lower().startswith("ley") else None,
        f"sentencia_{n.lower()}_{anio}" if tipo.lower() in ("t", "c", "su") else None,
    ]
    for c in candidatos:
        if c and c in normas:
            return c
    # Fallback: buscar cualquier clave que contenga el número y el año
    for k in normas.keys():
        if n in k and anio in k:
            return k
    return None


def verificar_citas(dictamen_html: str) -> dict:
    """Escanea el dictamen y devuelve un reporte de validación.

    Estructura:
        {
          "total_citas": int,
          "ok": int,
          "issues": [
            {
              "tipo": "NORMA_INEXISTENTE" | "ARTICULO_FUERA_DE_NORMA" | "CITA_LITERAL_FALSA",
              "severidad": "ALTA" | "MEDIA" | "BAJA",
              "cita": str,      # lo que aparece en el dictamen
              "detalle": str,   # explicación
              "sugerencia": str | None,
            }
          ],
          "tiene_problemas_graves": bool,  # alguna severidad ALTA
        }

    Si el corpus no se puede importar, devuelve reporte vacío (no rompe nada).
    """
    issues: list[dict] = []
    total_citas = 0

    try:
        from app.services.normativa_completa import _TODAS_LAS_NORMAS as normas
    except Exception:
        return {"total_citas": 0, "ok": 0, "issues": [], "tiene_problemas_graves": False}

    if not dictamen_html:
        return {"total_citas": 0, "ok": 0, "issues": [], "tiene_problemas_graves": False}

    texto = _quitar_html(dictamen_html)

    # 1. Verificar Resoluciones / Decretos / Leyes
    for pat, tipo_label in (
        (PAT_RESOLUCION, "Resolución"),
        (PAT_DECRETO, "Decreto"),
        (PAT_LEY, "Ley"),
    ):
        for m in pat.finditer(texto):
            total_citas += 1
            grupos = [g for g in m.groups() if g]
            if len(grupos) >= 2:
                numero, anio = grupos[0], grupos[1]
                if len(anio) == 2:
                    anio = "20" + anio if int(anio) < 50 else "19" + anio
                tipo_short = tipo_label[:3].lower()
                clave = _buscar_clave_norma(tipo_short, numero, anio, normas)
                if not clave:
                    issues.append({
                        "tipo": "NORMA_INEXISTENTE",
                        "severidad": "ALTA",
                        "cita": f"{tipo_label} {numero} de {anio}",
                        "detalle": f"No existe en el corpus normativo cargado ({tipo_label} {numero}/{anio}).",
                        "sugerencia": "Verifica la cita o reemplaza por una norma vigente del corpus.",
                    })

    # 2. Verificar Sentencias
    for m in PAT_SENTENCIA.finditer(texto):
        total_citas += 1
        sala, num, anio = m.groups()
        if len(anio) == 2:
            anio = "20" + anio if int(anio) < 50 else "19" + anio
        clave = _buscar_clave_norma(sala.lower(), num, anio, normas)
        if not clave:
            issues.append({
                "tipo": "NORMA_INEXISTENTE",
                "severidad": "MEDIA",
                "cita": f"Sentencia {sala.upper()}-{num}/{anio}",
                "detalle": "Sentencia no incluida en el corpus jurisprudencial.",
                "sugerencia": "Verifica que la sentencia exista o reemplaza por una conocida (ej: T-760/2008, T-1025/2002).",
            })

    # 3. Verificar artículos cuando se citan junto a su norma
    for m in PAT_ARTICULO.finditer(texto):
        art_num = m.group(1)
        norma_tipo = m.group(2)
        norma_num = m.group(3)
        norma_anio = m.group(4)
        if not (norma_tipo and norma_num and norma_anio):
            continue
        total_citas += 1
        clave = _buscar_clave_norma(norma_tipo[:3].lower(), norma_num, norma_anio, normas)
        if clave:
            n = normas[clave]
            arts = n.get("articulos", {}) or {}
            # Las claves de articulos pueden ser strings o ints
            keys_art = {str(k) for k in arts.keys()}
            if str(art_num) not in keys_art:
                issues.append({
                    "tipo": "ARTICULO_FUERA_DE_NORMA",
                    "severidad": "MEDIA",
                    "cita": f"Art. {art_num} {norma_tipo} {norma_num}/{norma_anio}",
                    "detalle": f"La {norma_tipo} {norma_num}/{norma_anio} no contiene el Art. {art_num} en el corpus cargado.",
                    "sugerencia": f"Verifica el número de artículo o consulta los artículos disponibles de esta norma.",
                })

    # 4. Verificar citas literales entre chevrones
    citas_literales = PAT_CITA_LITERAL.findall(texto)
    if citas_literales:
        # Construir corpus completo de TODOS los textos normativos para búsqueda
        corpus_normalizado = " ".join(
            _normalizar(n.get("texto", ""))
            + " "
            + _normalizar(n.get("ratio_literal", ""))
            + " "
            + _normalizar(n.get("extracto_judicial", ""))
            + " "
            + " ".join(
                _normalizar(a.get("texto", "")) for a in (n.get("articulos") or {}).values()
            )
            for n in normas.values()
        )
        for cita in citas_literales:
            total_citas += 1
            cita_norm = _normalizar(cita)
            # Tomamos un fragmento mid de 30 chars como "huella" para buscar
            if len(cita_norm) < 30:
                continue
            mid = cita_norm[10 : min(len(cita_norm) - 10, 80)]
            if mid and mid not in corpus_normalizado:
                # Probamos también con los primeros 60 chars
                inicio = cita_norm[:60]
                if inicio not in corpus_normalizado:
                    issues.append({
                        "tipo": "CITA_LITERAL_FALSA",
                        "severidad": "ALTA",
                        "cita": "«" + (cita[:140] + "..." if len(cita) > 140 else cita) + "»",
                        "detalle": "Este texto entrecomillado no se encuentra literalmente en el corpus normativo cargado. Puede ser una cita inventada por la IA.",
                        "sugerencia": "Reemplaza el texto entre comillas por una cita literal de una norma real, o quita las comillas si solo querías parafrasear.",
                    })

    ok = max(0, total_citas - len(issues))
    tiene_graves = any(i["severidad"] == "ALTA" for i in issues)

    if issues:
        logger.info(
            f"[CITATION-VERIFIER] {len(issues)} issues "
            f"({sum(1 for i in issues if i['severidad'] == 'ALTA')} ALTA) en {total_citas} citas"
        )

    return {
        "total_citas": total_citas,
        "ok": ok,
        "issues": issues,
        "tiene_problemas_graves": tiene_graves,
    }
