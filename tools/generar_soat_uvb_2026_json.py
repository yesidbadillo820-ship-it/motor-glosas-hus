"""Convierte la Circular Externa 047 de 2025 (PDF oficial) a JSON comprimido.

Genera ``app/data/soat_uvb_2026.json.gz`` con la tabla completa de tarifas
del Manual de Régimen Tarifario indexadas en UVB para la vigencia 2026.

Uso:
    python tools/generar_soat_uvb_2026_json.py /ruta/Circular_Externa_047_2025.pdf

Fuente: MINISTERIO DE SALUD Y PROTECCIÓN SOCIAL, Circular Externa 047 del
30 de diciembre de 2025 — «Indexación de tarifas del Manual de Régimen
Tarifario expresadas en UVB que regirán a partir de la vigencia 2026».

Por qué se lee por coordenadas y no por texto plano: el PDF es un escaneo
con capa de texto (OCR). La descripción de cada servicio se parte en varias
líneas y el código queda impreso en la mitad del bloque, así:

    Sesión de hemodiálisis por insuficiencia renal crónica,
    39161   incluidos los controles médicos que el paciente        6,88
    requiera_____________________________________

Leyendo el texto seguido se pierde la descripción. Leyendo por columnas
—código a la izquierda (x≈131), descripción al centro (x≈182) y tarifa a la
derecha (x≈460)— cada renglón queda completo.

Salida JSON:
    {
      "_meta": {...},
      "tarifas": {
        "19001": {"uvb": 5.93, "descripcion": "Acetaminofén"},
        ...
      }
    }
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_AQUI, "app", "data", "soat_uvb_2026.json.gz")

# Fronteras de columna medidas sobre el PDF oficial (ancho de página 614 pt).
_X_FIN_CODIGO = 175.0
_X_INI_TARIFA = 440.0
# El membrete de la Circular ("000047 / Salud / 3 0 DIC 2025") ocupa los
# primeros 90 puntos de cada página. Más abajo no se puede recortar por
# altura: en la última página la tabla arranca en el punto 121.
_Y_FIN_ENCABEZADO = 95.0
# Palabras del mismo renglón que quedan corridas en vertical por el escaneo.
_TOLERANCIA_RENGLON = 6.0
# Un renglón suelto de descripción se pega al código más cercano, pero solo
# si está a menos de dos renglones de distancia.
_MAX_DISTANCIA_RENGLON = 20.0
# Cuánto puede correrse la tarifa respecto del código en el mismo renglón.
_MAX_DESFASE_TARIFA = 8.0

_RX_CODIGO = re.compile(r"^\d{4,6}$")
# 5,93 · 1.080,29 · 0,602 · y el caso OCR donde la coma salió como punto: 22.52
_RX_TARIFA = re.compile(r"^\d{1,3}(?:\.\d{3})*[,.]\d{1,3}$")

_RUIDO_ENCABEZADO = (
    "INDEXACION",
    "INDEXACIÓN",
    "ÍNDEXACIÓN",
    "EXPRESADAS",
    "CÓDIGO",
    "DESCRIPCIÓN",
    "TARIFA",
    "EN UVB",
    "Ministerio de Salud",
    "Conmutador",
    "Resto del país",
    "Dirección: Carrera",
    "Página |",
    "PUBLÍQUESE",
)


# Basura que el OCR pega a los lados de un número: comillas, apóstrofes,
# guiones bajos de relleno y los trazos del borde de la tabla.
_BASURA_OCR = " \t'\"`´■|_.,;:—-"


def _a_float(txt: str) -> float | None:
    """'1.080,29' → 1080.29 · '0,602' → 0.602 · '22.52' → 22.52 (OCR).

    Limpia primero la basura que el escaneo deja pegada al número: la tarifa
    del código 31113 quedó leída como '"5,11'."""
    t = (txt or "").strip().strip(_BASURA_OCR)
    if not _RX_TARIFA.match(t):
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _limpiar(texto: str) -> str:
    """Quita el relleno de guiones bajos y la basura de OCR de los bordes."""
    t = re.sub(r"[_]{2,}", " ", texto or "")
    t = re.sub(r"\s+", " ", t)
    return t.strip(" _.,;:'\"—-")


def _es_ruido(texto: str) -> bool:
    """True si el renglón es encabezado o pie repetido de la Circular."""
    return any(r in texto for r in _RUIDO_ENCABEZADO)


def _centro(w: dict) -> float:
    return (w["top"] + w["bottom"]) / 2.0


def _lineas_de_texto(palabras: list[dict]) -> list[tuple[float, str]]:
    """Junta las palabras de la columna del medio en renglones legibles."""
    if not palabras:
        return []
    palabras = sorted(palabras, key=_centro)
    lineas: list[list[dict]] = [[palabras[0]]]
    for w in palabras[1:]:
        if abs(_centro(w) - _centro(lineas[-1][-1])) <= _TOLERANCIA_RENGLON:
            lineas[-1].append(w)
        else:
            lineas.append([w])
    salida = []
    for ln in lineas:
        ln.sort(key=lambda w: w["x0"])
        texto = _limpiar(" ".join(w["text"] for w in ln))
        if texto and not _es_ruido(texto):
            salida.append((sum(_centro(w) for w in ln) / len(ln), texto))
    return salida


def _leer_pagina(pagina) -> list[tuple[str, float, str]]:
    """Lee una página como tabla de tres columnas.

    No se agrupa por renglones completos: cuando la descripción ocupa dos
    líneas, el código y la tarifa quedan centrados entre ellas y ningún
    agrupamiento por altura los deja juntos. Se ancla en el código y se le
    busca la tarifa que esté a su misma altura.
    """
    palabras = [w for w in pagina.extract_words() if w["top"] >= _Y_FIN_ENCABEZADO]

    codigos = sorted(
        (w for w in palabras if w["x0"] < _X_FIN_CODIGO and _RX_CODIGO.match(w["text"])),
        key=_centro,
    )
    tarifas = [w for w in palabras if w["x0"] >= _X_INI_TARIFA and _a_float(w["text"]) is not None]
    medio = [w for w in palabras if _X_FIN_CODIGO <= w["x0"] < _X_INI_TARIFA]

    registros: list[dict] = []
    usadas: set[int] = set()
    for cod in codigos:
        elegida, distancia, indice = None, None, -1
        for i, tar in enumerate(tarifas):
            if i in usadas:
                continue
            d = abs(_centro(tar) - _centro(cod))
            if distancia is None or d < distancia:
                elegida, distancia, indice = tar, d, i
        if elegida is None or distancia > _MAX_DESFASE_TARIFA:
            continue
        usadas.add(indice)
        registros.append(
            {
                "codigo": cod["text"],
                "uvb": _a_float(elegida["text"]),
                "y": _centro(cod),
                "desc": [],
            }
        )

    for y, texto in _lineas_de_texto(medio):
        if not registros:
            continue
        cerca = min(registros, key=lambda r: abs(r["y"] - y))
        if abs(cerca["y"] - y) <= _MAX_DISTANCIA_RENGLON:
            cerca["desc"].append((y, texto))

    salida = []
    for r in registros:
        partes = [t for _y, t in sorted(r["desc"], key=lambda x: x[0])]
        salida.append((r["codigo"], r["uvb"], _limpiar(" ".join(partes))))
    return salida


def generar(src_pdf: str, out_path: str = _OUT, version: str = "") -> dict:
    import pdfplumber  # dependencia ya declarada en requirements.txt

    tarifas: dict[str, dict] = {}
    repetidos_en_conflicto: list[str] = []
    paginas = 0

    with pdfplumber.open(src_pdf) as pdf:
        paginas = len(pdf.pages)
        for pagina in pdf.pages:
            for codigo, uvb, desc in _leer_pagina(pagina):
                previo = tarifas.get(codigo)
                if previo is None:
                    tarifas[codigo] = {"uvb": uvb, "descripcion": desc}
                elif abs(previo["uvb"] - uvb) >= 0.0005:
                    # El mismo código con dos tarifas distintas: no se elige
                    # una a dedo, se deja la primera y se reporta.
                    repetidos_en_conflicto.append(codigo)
                elif len(desc) > len(previo["descripcion"]):
                    previo["descripcion"] = desc

    data = {
        "_meta": {
            "fuente": (
                "MinSalud — Circular Externa 047 del 30 de diciembre de 2025. "
                "Indexación de tarifas del Manual de Régimen Tarifario "
                "expresadas en UVB, vigencia 2026."
            ),
            "descripcion": (
                "Tarifa oficial en UVB por código del Manual Tarifario SOAT. "
                "Para pesos: tarifa_UVB × valor UVB del año, ajustado a la "
                "centena más próxima (Decreto 780/2016, Anexo técnico 1, num. 87)."
            ),
            "norma": "CIRCULAR_047_2025",
            "paginas_leidas": paginas,
            "codigos": len(tarifas),
            "codigos_en_conflicto": sorted(set(repetidos_en_conflicto)),
            "version": version or "2026-CIRCULAR-047-2025",
        },
        "tarifas": dict(sorted(tarifas.items())),
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return data["_meta"]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python tools/generar_soat_uvb_2026_json.py /ruta/Circular_047_2025.pdf")
        sys.exit(1)
    meta = generar(sys.argv[1], version=sys.argv[2] if len(sys.argv) > 2 else "")
    print(f"JSON.gz generado en {_OUT}")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
