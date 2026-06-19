"""Aprendizaje por DIFF entre versiones de dictamen.

Complementa `memoria_gestor.py`:
  - memoria_gestor: aprende de lo que el gestor PIDIÓ explícitamente
    en `mensaje_refinar` ("agrega T-760", "más conciliador", etc.)
  - aprendizaje_diff: aprende de lo que el gestor AGREGÓ MANUALMENTE
    al editar el HTML del dictamen sin instrucción explícita.

Detecta normas (Leyes, Arts., Sentencias, Resoluciones, Decretos, Circulares)
que aparecen en la versión EDITADA pero no en la ORIGINAL. Cuando un gestor
agrega 3+ veces la misma norma en glosas similares, se infiere como patrón
y se inyecta al prompt junto con los patrones explícitos de memoria_gestor.

Diseñado para ser barato (regex, sin LLM) y ejecutable en cada análisis.
"""

from __future__ import annotations

import re
from collections import Counter

# Patrones para extraer normas/sentencias de un dictamen.
# Cada uno se compila una sola vez al import.
_REGEX_NORMAS = (
    # Sentencias constitucionales: T-760/2008, C-313-2014, T-1025/2002, SU-480
    re.compile(r"\b(T|C|SU|A)-?\d{2,4}(?:[/-]\d{2,4})?\b", re.IGNORECASE),
    # Artículos: "Art. 177", "Artículo 57", "art 871"
    re.compile(r"\bart[íi]?(?:culo)?\.?\s*(\d{1,4})\b", re.IGNORECASE),
    # Leyes: "Ley 1438/2011", "Ley 100 de 1993"
    re.compile(r"\bley\s+(\d{2,4})(?:\s*[/de\s]+\s*\d{4})?\b", re.IGNORECASE),
    # Resoluciones: "Res. 2284/2023", "Resolución 2284", "Res 1995"
    re.compile(r"\bres(?:oluci[óo]n)?\.?\s*(\d{3,5})(?:\s*[/de\s]+\s*\d{4})?\b", re.IGNORECASE),
    # Decretos: "Decreto 4747/2007"
    re.compile(r"\bdecreto\s+(\d{2,5})(?:\s*[/de\s]+\s*\d{4})?\b", re.IGNORECASE),
    # Circulares: "Circular 047/2025", "Circ. Externa 047"
    re.compile(
        r"\bcirc(?:ular)?\.?\s*(?:externa\s+)?(\d{2,4})(?:\s*[/de\s]+\s*\d{4})?\b",
        re.IGNORECASE,
    ),
)

# Tags HTML que limpiamos para comparar solo texto
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")


def _normalizar_texto(html_o_texto: str) -> str:
    """Quita tags HTML y normaliza espacios para comparación textual."""
    if not html_o_texto:
        return ""
    sin_tags = _RE_HTML_TAG.sub(" ", html_o_texto)
    return _RE_WS.sub(" ", sin_tags).strip()


def extraer_normas(texto: str) -> set[str]:
    """Devuelve el conjunto de normas mencionadas en el texto, normalizadas.

    Cada norma se devuelve como string canónico con prefijo (ej. "art:177",
    "ley:1438", "sent:T-760", "res:2284", "dec:4747", "circ:047") para
    evitar colisiones entre distintos tipos.
    """
    if not texto:
        return set()
    txt = _normalizar_texto(texto).upper()
    encontradas: set[str] = set()
    # Sentencias
    for m in _REGEX_NORMAS[0].finditer(txt):
        encontradas.add(f"sent:{m.group(0).upper().replace(' ', '')}")
    # Artículos (solo el número — el contexto determina cuál ley)
    for m in _REGEX_NORMAS[1].finditer(txt):
        encontradas.add(f"art:{m.group(1)}")
    # Leyes
    for m in _REGEX_NORMAS[2].finditer(txt):
        encontradas.add(f"ley:{m.group(1)}")
    # Resoluciones
    for m in _REGEX_NORMAS[3].finditer(txt):
        encontradas.add(f"res:{m.group(1)}")
    # Decretos
    for m in _REGEX_NORMAS[4].finditer(txt):
        encontradas.add(f"dec:{m.group(1)}")
    # Circulares
    for m in _REGEX_NORMAS[5].finditer(txt):
        encontradas.add(f"circ:{m.group(1)}")
    return encontradas


def diff_normas_agregadas(original: str, editado: str) -> set[str]:
    """Devuelve normas presentes en `editado` pero ausentes en `original`.

    Útil para detectar qué adiciones manuales hace un gestor al revisar
    un dictamen. Casos:
      - Original sin T-760, editado con T-760 → {"sent:T-760"}
      - Ambos con T-760 → {} (no es adición)
      - Editado sin nada nuevo → {}
    """
    return extraer_normas(editado) - extraer_normas(original)


def _etiqueta_legible(norma_canonica: str) -> str:
    """Convierte 'sent:T-760' → 'Sentencia T-760', 'art:177' → 'Art. 177', etc."""
    if ":" not in norma_canonica:
        return norma_canonica
    tipo, valor = norma_canonica.split(":", 1)
    mapa = {
        "sent": f"Sentencia {valor}",
        "art": f"Art. {valor}",
        "ley": f"Ley {valor}",
        "res": f"Res. {valor}",
        "dec": f"Decreto {valor}",
        "circ": f"Circular {valor}",
    }
    return mapa.get(tipo, norma_canonica)


def patron_diff_gestor(
    db,
    autor_email: str,
    codigo_glosa: str = "",
    eps: str = "",
    limite_meses: int = 6,
    min_repeticiones: int = 3,
) -> dict:
    """Analiza diffs entre versiones consecutivas del MISMO gestor.

    Para cada glosa donde el gestor creó múltiples versiones, calcula el diff
    entre versiones consecutivas (cronológicas) y cuenta qué normas agrega
    sistemáticamente. min_repeticiones=3 evita falsos positivos por
    coincidencias casuales.

    Filtra por codigo_glosa / eps si se proveen, igual que `patron_gestor`.

    Returns:
      {
        "autor": str,
        "n_glosas_analizadas": int,
        "n_diffs": int,
        "normas_recurrentes": [{"norma": "Sentencia T-760", "veces": 5}, ...],
        "hint_para_prompt": str,   # texto listo para inyectar al system
      }
    """
    vacio = {
        "autor": autor_email or "",
        "n_glosas_analizadas": 0,
        "n_diffs": 0,
        "normas_recurrentes": [],
        "hint_para_prompt": "",
    }
    if not autor_email:
        return vacio

    from datetime import datetime, timedelta, timezone

    from app.models.db import DictamenVersionRecord, GlosaRecord

    desde = datetime.now(timezone.utc) - timedelta(days=30 * limite_meses)

    # Cargar versiones del gestor, ordenadas por glosa y tiempo
    q = (
        db.query(DictamenVersionRecord, GlosaRecord)
        .join(GlosaRecord, DictamenVersionRecord.glosa_id == GlosaRecord.id)
        .filter(DictamenVersionRecord.autor_email == autor_email)
        .filter(DictamenVersionRecord.creado_en >= desde)
        .order_by(
            DictamenVersionRecord.glosa_id,
            DictamenVersionRecord.creado_en.asc(),
        )
        .limit(2000)
    )
    rows = q.all()
    if not rows:
        return vacio

    # Filtros de contexto (mismo formato que patron_gestor)
    cod_norm = (codigo_glosa or "").upper().strip()
    eps_norm = (eps or "").upper().strip()

    def _match_contexto(g: object) -> bool:
        if not (cod_norm or eps_norm):
            return True  # sin filtros → todo cuenta
        g_cod = (getattr(g, "codigo_glosa", "") or "").upper().strip()
        g_eps = (getattr(g, "eps", "") or "").upper().strip()
        if cod_norm and g_cod:
            if cod_norm == g_cod or g_cod.startswith(cod_norm[:4]):
                return True
        if eps_norm and g_eps:
            if eps_norm in g_eps or g_eps in eps_norm:
                return True
        return False

    # Agrupar versiones por glosa_id (las rows ya vienen ordenadas)
    por_glosa: dict[int, list] = {}
    glosa_meta: dict[int, object] = {}
    for ver, g in rows:
        por_glosa.setdefault(ver.glosa_id, []).append(ver)
        glosa_meta[ver.glosa_id] = g

    contador: Counter = Counter()
    n_diffs = 0
    n_glosas_validas = 0
    for gid, versiones in por_glosa.items():
        if len(versiones) < 2:
            continue
        g = glosa_meta.get(gid)
        if g is not None and not _match_contexto(g):
            continue
        n_glosas_validas += 1
        # Diff entre versiones consecutivas
        for i in range(1, len(versiones)):
            prev = versiones[i - 1].dictamen_html or ""
            curr = versiones[i].dictamen_html or ""
            agregadas = diff_normas_agregadas(prev, curr)
            for norma in agregadas:
                contador[norma] += 1
            n_diffs += 1

    # Filtrar por min_repeticiones y construir lista
    normas_top = [
        {"norma": _etiqueta_legible(n), "veces": v}
        for n, v in contador.most_common(10)
        if v >= min_repeticiones
    ]

    # Hint para prompt
    hint = ""
    if normas_top:
        items = "\n".join(f"• {n['norma']} (agregada {n['veces']} veces)" for n in normas_top[:4])
        hint = (
            "\n[ESTILO DEL GESTOR — adiciones manuales recurrentes]\n"
            "Este auditor suele AGREGAR estas normas al editar dictámenes en casos similares. "
            "Inclúyelas desde el inicio si encajan con el caso:\n" + items + "\n"
        )

    return {
        "autor": autor_email,
        "n_glosas_analizadas": n_glosas_validas,
        "n_diffs": n_diffs,
        "normas_recurrentes": normas_top,
        "hint_para_prompt": hint,
    }
