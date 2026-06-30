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
    # Solo dígitos
    solo_dig = re.sub(r"\D", "", c)
    _add(solo_dig)
    if solo_dig and len(solo_dig) <= 6:
        _add(solo_dig.zfill(6))
    # base solo dígitos con zfill
    base_dig = re.sub(r"\D", "", base)
    if base_dig and len(base_dig) <= 6:
        _add(base_dig.zfill(6))
    return candidatos


def homologar_cups_a_soat(cups: str | None) -> list[dict]:
    """Devuelve la lista de mapeos SOAT para un CUPS, o [] si no existe.

    Cada mapeo: {"soat": "1101", "desc_soat": "...", "desc_cups": "..."}.
    Un CUPS puede tener varios SOAT (multi-mapeo). Prueba variantes
    normalizadas del CUPS (sin sufijos, con zfill).
    """
    tabla = _cargar().get("cups_a_soat", {})
    if not tabla:
        return []
    for cand in _normalizar_cups(cups):
        if cand in tabla:
            return list(tabla[cand])
    return []


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
    """Devuelve la descripción del procedimiento CUPS (la del primer mapeo)."""
    mapeos = homologar_cups_a_soat(cups)
    return mapeos[0]["desc_cups"] if mapeos else ""


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
    mapeos = homologar_cups_a_soat(cups)
    if not mapeos:
        return ""
    cups_norm = str(cups).strip()
    desc_cups = mapeos[0].get("desc_cups", "")
    lineas = [
        "\n\n═══ HOMOLOGACIÓN OFICIAL CUPS → SOAT (Manual Único Res. 2775) ═══",
        f"El CUPS {cups_norm} ({desc_cups}) corresponde oficialmente a los "
        "siguientes código(s) SOAT del Manual Tarifario:",
    ]
    for m in mapeos[:max_soat]:
        lineas.append(f"  • SOAT {m['soat']} — {m['desc_soat']}")
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
