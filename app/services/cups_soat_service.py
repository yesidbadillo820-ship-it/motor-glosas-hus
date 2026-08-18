"""Homologador CUPS → SOAT (tarifación) — Manual Único Res. 2775 → Manual SOAT.

DISTINTO del homologador_cups.py (que homologa CUPS_viejo → CUPS_nuevo de
la Res. 2641/2025). Este módulo mapea un código CUPS a su(s) código(s)
SOAT oficial(es), con la descripción de cada uno, para fundamentar la
tarifa en glosas de TARIFA (TA).

Fuente: app/data/cups_soat_homologacion.json.gz (10.024 CUPS únicos,
2.919 SOAT únicos, 1.168 CUPS con multi-mapeo ~11.7%). Generado por
tools/generar_cups_soat_json.py a partir del Excel oficial del HUS.

Uso:

    from app.services.cups_soat_service import homologar_cups_a_soat

    mapeos = homologar_cups_a_soat("012403")
    # → [{"soat": "1101", "desc_soat": "CRANEOTOMIA...", "desc_cups": "..."},
    #    {"soat": "1102", ...}, ...]   (multi-mapeo)

    mapeos = homologar_cups_a_soat("999999")
    # → []  (CUPS no encontrado en la tabla oficial)

Por qué importa: cuando la EPS glosa una tarifa SOAT, el HUS necesita
demostrar con la tabla OFICIAL que el CUPS facturado corresponde a tal
código SOAT — no a uno inventado por el auditor de la EPS. Inyectar este
dato en el dictamen lo blinda contra modificaciones tarifarias unilaterales.
"""

from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
import unicodedata
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "cups_soat_homologacion.json.gz"


@lru_cache(maxsize=1)
def _cargar() -> dict:
    """Carga el JSON.gz una sola vez (cacheado). Si el archivo no existe o
    está corrupto, devuelve un dict vacío para no romper el motor —
    la homologación es un realce, no un bloqueante.
    """
    try:
        with gzip.open(_DATA_PATH, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"_meta": {}, "cups_a_soat": {}}


def _normalizar_cups(cups: str | None) -> list[str]:
    """Devuelve las variantes candidatas de un CUPS para buscar en la tabla.

    Los CUPS de la tabla son de 6 dígitos con ceros a la izquierda
    ("012403"). Las glosas pueden traer:
      - sin ceros: "12403"
      - con sufijo institucional: "012403H", "012403-18"
      - con espacios.
    Generamos variantes razonables (sin inventar): el código tal cual, sin
    sufijos no numéricos, y con zfill(6).
    """
    if not cups:
        return []
    c = str(cups).strip().upper()
    candidatos: list[str] = []

    def _add(x: str) -> None:
        if x and x not in candidatos:
            candidatos.append(x)

    _add(c)
    # Quitar sufijos institucionales: letra(s) al final ("012403H"),
    # o guion + dígitos de versión ("012403-18").
    base = re.sub(r"[A-Z]+\d*$", "", c)  # quita "H", "H1", "H2"...
    base = re.sub(r"-\d{1,3}$", "", base)  # quita "-18", "-16"
    base = base.strip()
    _add(base)
    # Ronda 30: solo homologar por dígitos si el código EMPIEZA por dígito.
    # Los CUPS oficiales son numéricos; una letra inicial marca código
    # institucional HUS (S estancias, M materiales, FMQ/FMO quirúrgicos) que
    # NO debe homologarse por colisión de dígitos con el manual SOAT.
    if c and c[0].isdigit():
        solo_dig = re.sub(r"\D", "", c)
        _add(solo_dig)
        if solo_dig and len(solo_dig) <= 6:
            _add(solo_dig.zfill(6))
        base_dig = re.sub(r"\D", "", base)
        if base_dig and len(base_dig) <= 6:
            _add(base_dig.zfill(6))
    return candidatos


# 13-08-2026. En la tabla hay CUPS que NO tienen equivalente en el Manual
# SOAT, y la tabla lo dice escribiendo esta frase en la casilla del código.
# No es un código: es la ausencia de código. Devolverla como si lo fuera
# hacía que el motor le dijera a la IA, textualmente, que «el CUPS 013205
# corresponde oficialmente al código SOAT NO TIENE HOMOLOGACION DIRECTA», y
# encima le ordenaba usar ese dato para fundamentar la tarifa. Son 2.966
# códigos, y entre ellos hay tarifas del propio contrato de FAMISANAR.
_SIN_HOMOLOGACION = "NO TIENE HOMOLOGACION DIRECTA"


def _es_marca_sin_homologacion(mapeo: dict) -> bool:
    if mapeo.get("sin_homologacion"):
        return True
    soat = str(mapeo.get("soat") or "").strip().upper()
    return not soat or soat.replace("Ó", "O") == _SIN_HOMOLOGACION


def _crudos(cups: str | None) -> list[dict]:
    """Lo que la tabla tiene para ese CUPS, marcas incluidas."""
    tabla = _cargar().get("cups_a_soat", {})
    if not tabla:
        return []
    for cand in _normalizar_cups(cups):
        if cand in tabla:
            return list(tabla[cand])
    return []


def homologar_cups_a_soat(cups: str | None) -> list[dict]:
    """Devuelve la lista de mapeos SOAT para un CUPS, o [] si no existe.

    Cada mapeo: {"soat": "1101", "desc_soat": "...", "desc_cups": "..."}.
    Un CUPS puede tener varios SOAT (multi-mapeo). Prueba variantes
    normalizadas del CUPS (sin sufijos, con zfill).

    Solo devuelve códigos SOAT de verdad. Un CUPS registrado como sin
    homologación directa devuelve [] — ver `sin_homologacion_directa`.
    """
    return [m for m in _crudos(cups) if not _es_marca_sin_homologacion(m)]


def sin_homologacion_directa(cups: str | None) -> bool:
    """True si la tabla dice expresamente que ese CUPS no tiene código SOAT.

    No es lo mismo que no estar en la tabla. Que el manual oficial no le
    asigne código es un hecho a favor del hospital: la entidad no puede
    objetar la tarifa citando un SOAT que no existe para ese procedimiento.
    """
    crudos = _crudos(cups)
    return bool(crudos) and all(_es_marca_sin_homologacion(m) for m in crudos)


def validar_soat_para_cups(cups: str | None, soat: str | None) -> bool:
    """True si `soat` es un código SOAT oficial válido para `cups`.

    Útil para detectar cuando la EPS asigna a un CUPS un código SOAT que
    NO le corresponde (modificación tarifaria unilateral).
    """
    if not cups or not soat:
        return False
    soat_norm = str(soat).strip().lstrip("0") or "0"
    for m in homologar_cups_a_soat(cups):
        if str(m.get("soat", "")).strip().lstrip("0") == soat_norm:
            return True
    return False


def descripcion_cups(cups: str | None) -> str:
    """Devuelve la descripción del procedimiento CUPS (la del primer mapeo).

    Sirve también para los CUPS sin homologación: la tabla trae su
    descripción aunque no le asigne código SOAT.
    """
    crudos = _crudos(cups)
    return crudos[0].get("desc_cups", "") if crudos else ""


# ─── Búsqueda por descripción ───────────────────────────────────────────────
#
# 18-08-2026. El liquidador de tarifas solo sabía buscar por CÓDIGO SOAT
# (21102, 19001…). El auditor no tiene ese código: tiene el CUPS que sale en
# la factura (873420) o el nombre del procedimiento («radiografía de
# rodilla»). Escribiendo cualquiera de los dos, la pantalla devolvía cero.
#
# El puente ya estaba cargado —10.024 CUPS homologados— pero nadie lo usaba
# para buscar. Esto lo expone.

_INDICE_DESC: list[tuple[str, str, str]] | None = None


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def _indice() -> list[tuple[str, str, str]]:
    """[(cups, descripcion, descripcion_normalizada)] — se arma una sola vez."""
    global _INDICE_DESC
    if _INDICE_DESC is not None:
        return _INDICE_DESC
    salida: list[tuple[str, str, str]] = []
    for cups, mapeos in (_cargar().get("cups_a_soat", {}) or {}).items():
        desc = ""
        for m in mapeos or []:
            desc = str(m.get("desc_cups") or "").strip()
            if desc:
                break
        salida.append((cups, desc, _sin_tildes(desc)))
    _INDICE_DESC = salida
    return salida


def buscar_cups(texto: str, limite: int = 25) -> list[dict]:
    """Busca en los 10.024 CUPS por código o por descripción.

    Devuelve, por cada CUPS encontrado, su descripción y los códigos SOAT a
    los que homologa. Si el manual no le asigna ninguno, lo dice —no se
    inventa un código.

    El orden pone primero el código exacto, luego los que empiezan por lo
    escrito, y de último las coincidencias por descripción.
    """
    q = _sin_tildes(texto).strip()
    if len(q) < 3:
        return []

    tokens = [t for t in q.split() if len(t) >= 3]
    encontrados: list[tuple[int, str, str]] = []
    for cups, desc, desc_norm in _indice():
        if cups == q:
            prioridad = 0
        elif q.isdigit() and cups.startswith(q):
            prioridad = 1
        elif q in desc_norm:
            prioridad = 2
        elif tokens and all(t in desc_norm for t in tokens):
            prioridad = 3
        else:
            continue
        encontrados.append((prioridad, cups, desc))

    encontrados.sort(key=lambda x: (x[0], len(x[2]), x[1]))
    salida = []
    for _prio, cups, desc in encontrados[:limite]:
        salida.append(
            {
                "cups": cups,
                "descripcion": desc,
                "homologaciones": homologar_cups_a_soat(cups),
                "sin_homologacion": sin_homologacion_directa(cups),
            }
        )
    return salida


def resumen_homologacion() -> dict:
    """Metadatos de la tabla cargada (para el panel de Diagnóstico)."""
    data = _cargar()
    meta = dict(data.get("_meta", {}))
    meta["cargado"] = bool(data.get("cups_a_soat"))
    return meta


def bloque_homologacion_para_prompt(cups: str | None, max_soat: int = 4) -> str:
    """Construye un bloque de texto con la homologación oficial CUPS→SOAT
    para inyectar en el user prompt de glosas de TARIFA.

    Devuelve "" si el CUPS no está en la tabla (no inventa nada).
    """
    cups_norm = str(cups or "").strip()
    mapeos = homologar_cups_a_soat(cups)

    if not mapeos:
        if not sin_homologacion_directa(cups):
            return ""
        # Que el manual no le asigne código es un HECHO, y juega a favor: la
        # entidad no puede objetar la tarifa citando un SOAT que para ese
        # procedimiento no existe. Callarlo dejaba el dictamen sin ese
        # argumento; escribir la frase en la casilla del código, que es lo
        # que pasaba antes, era peor: afirmaba un código falso.
        desc = descripcion_cups(cups)
        return "\n".join(
            [
                "\n\n═══ HOMOLOGACIÓN OFICIAL CUPS → SOAT ═══",
                f"El CUPS {cups_norm} ({desc}) NO tiene homologación directa en el "
                "Manual Tarifario SOAT, según la tabla oficial de homologación.",
                "USA ESTE DATO ASÍ: no existe código SOAT equivalente, luego la "
                "entidad NO puede objetar la tarifa citando un código SOAT para "
                "este procedimiento. PROHIBIDO afirmar que corresponde a algún "
                "código SOAT: la tabla oficial dice que no lo hay.",
            ]
        )

    desc_cups = mapeos[0].get("desc_cups", "")
    lineas = [
        "\n\n═══ HOMOLOGACIÓN OFICIAL CUPS → SOAT (Manual Único Res. 2775) ═══",
        f"El CUPS {cups_norm} ({desc_cups}) corresponde oficialmente a los "
        "siguientes código(s) SOAT del Manual Tarifario:",
    ]
    for m in mapeos[:max_soat]:
        linea = f"  • SOAT {m['soat']} — {m['desc_soat']}"
        # El homologador 2026 trae el artículo del manual donde está el
        # código. Poder citarlo es la diferencia entre «corresponde al SOAT
        # 1101» y «corresponde al SOAT 1101, Artículo 03: Neurocirugía».
        if m.get("articulo"):
            linea += f" ({m['articulo']})"
        lineas.append(linea)
    if len(mapeos) > max_soat:
        lineas.append(f"  • (… y {len(mapeos) - max_soat} código(s) SOAT más)")
    lineas.append(
        "USA ESTE DATO OFICIAL para fundamentar la tarifa: si la EPS asignó "
        "un código SOAT distinto a los listados, es una modificación "
        "tarifaria unilateral (viola Pacta Sunt Servanda). Si la EPS objeta "
        "la homologación, esta tabla oficial es la prueba. NO inventes otros "
        "códigos SOAT fuera de esta lista."
    )
    return "\n".join(lineas)
