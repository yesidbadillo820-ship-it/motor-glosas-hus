"""Tests del Motor de Evidencia (tools/motor_evidencia_dispensario.py).

Cubre: extraccion de terminos de busqueda de la glosa, lectura pagina por
pagina, localizacion de la evidencia EN LA PAGINA correcta con su fragmento, y
el enriquecimiento del expediente (cada glosa recibe su lista 'evidencias').
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import motor_evidencia_dispensario as mev  # noqa: E402


def _hc_dos_paginas(ruta: Path):
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(ruta))
    c.drawString(70, 800, "HISTORIA CLINICA ADMISION DATOS DEL PACIENTE")
    c.showPage()
    c.drawString(70, 800, "EVOLUCION 14/03/2026 SE ORDENA PROCEDIMIENTO 890201 CONSULTA CONTROL")
    c.showPage()
    c.save()


def test_terminos_de_glosa():
    t = mev.terminos_de_glosa("CONSULTA DE CONTROL 890201", "SE GLOSA CODIGO 890201 mayor valor")
    assert "890201" in t
    assert "CONSULTA" in t and "CONTROL" in t
    # stopwords y palabras cortas no entran
    assert "DE" not in t and "SE" not in t


def test_snippet_recorta():
    s = mev._snippet("abcdefghij TERM klmnopqrst" * 3, 11, ancho=8)
    assert "TERM" in s


def test_texto_por_pagina(tmp_path):
    pdf = tmp_path / "hc.pdf"
    _hc_dos_paginas(pdf)
    pags = mev.texto_por_pagina(pdf)
    assert len(pags) == 2
    assert "890201" in pags[1]
    assert "890201" not in pags[0]


def test_evidencia_en_pagina_correcta(tmp_path):
    pdf = tmp_path / "hc.pdf"
    _hc_dos_paginas(pdf)
    clinicos = [{"tipo": "Historia clinica / Evolucion", "nombre": "hc.pdf", "ruta": str(pdf)}]
    ev = mev.evidencias_para_glosa("CONSULTA DE CONTROL 890201", "SE GLOSA CODIGO 890201", clinicos)
    assert ev, "debe encontrar evidencia"
    e0 = ev[0]
    assert e0["pagina"] == 2
    assert e0["termino"] == "890201"
    assert e0["fuerza"] == "fuerte"  # match por codigo CUPS, no palabra generica
    assert "890201" in e0["fragmento"]


def test_sin_evidencia_no_inventa(tmp_path):
    pdf = tmp_path / "hc.pdf"
    _hc_dos_paginas(pdf)
    clinicos = [{"tipo": "Historia clinica / Evolucion", "nombre": "hc.pdf", "ruta": str(pdf)}]
    # Un CUPS que NO aparece en el documento -> sin evidencia
    ev = mev.evidencias_para_glosa("PROCEDIMIENTO 999999", "SE GLOSA CODIGO 999999", clinicos)
    assert ev == []


def test_enriquecer_expedientes(tmp_path):
    pdf = tmp_path / "hc.pdf"
    _hc_dos_paginas(pdf)
    payload = {
        "expedientes": [
            {
                "factura": "HUS0000436483",
                "soportes": [
                    {"tipo": "Historia clinica / Evolucion", "nombre": "hc.pdf", "ruta": str(pdf)},
                    {"tipo": "RIPS", "nombre": "r.json", "ruta": str(tmp_path / "no.json")},
                ],
                "glosas": [
                    {
                        "codigo_corto": "TA0201",
                        "familia": "TARIFAS",
                        "servicio": "CONSULTA CONTROL 890201",
                        "motivo": "SE GLOSA CODIGO 890201",
                    },
                ],
            }
        ]
    }
    out = mev.enriquecer_expedientes(payload)
    ev = out["expedientes"][0]["glosas"][0]["evidencias"]
    assert len(ev) == 1
    assert ev[0]["pagina"] == 2
    assert out["evidencias_localizadas"] == 1


def test_cache_texto_da_mismo_resultado(tmp_path):
    """Leer el PDF una vez (cache) y reusarlo da la misma evidencia que releerlo."""
    pdf = tmp_path / "hc.pdf"
    _hc_dos_paginas(pdf)
    clinicos = [{"tipo": "Historia clinica / Evolucion", "nombre": "hc.pdf", "ruta": str(pdf)}]
    cache = mev.cachear_texto(clinicos)
    assert str(pdf) in cache and len(cache[str(pdf)]) == 2  # leido una vez, 2 paginas
    sin_cache = mev.evidencias_para_glosa("CONSULTA CONTROL 890201", "890201", clinicos)
    con_cache = mev.evidencias_para_glosa(
        "CONSULTA CONTROL 890201", "890201", clinicos, cache=cache
    )
    assert [e["pagina"] for e in sin_cache] == [e["pagina"] for e in con_cache]
    assert con_cache and con_cache[0]["termino"] == "890201"


def _hc_muchas_paginas(ruta: Path, n: int = 10):
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(ruta))
    for i in range(1, n + 1):
        # Todas las paginas mencionan el servicio por nombre (evidencia debil);
        # solo la pagina 7 trae ademas el codigo CUPS (evidencia fuerte).
        linea = f"EVOLUCION DIA {i} TOMOGRAFIA DE CUELLO CONTROL"
        if i == 7:
            linea += " CODIGO 879101"
        c.drawString(70, 800, linea)
        c.showPage()
    c.save()


def test_evidencia_acota_a_las_mas_relevantes(tmp_path):
    """No cita 300 paginas: tope MAX y la pagina con el codigo (fuerte) primero."""
    pdf = tmp_path / "hc.pdf"
    _hc_muchas_paginas(pdf, n=10)
    clinicos = [{"tipo": "Historia clinica / Evolucion", "nombre": "hc.pdf", "ruta": str(pdf)}]
    ev = mev.evidencias_para_glosa("TOMOGRAFIA DE CUELLO 879101", "SE GLOSA 879101", clinicos)
    # Las 10 paginas coinciden por nombre, pero solo se citan las MAS relevantes.
    assert len(ev) == mev.MAX_EVIDENCIAS_POR_GLOSA
    # La pagina con el codigo va primero y es evidencia fuerte.
    assert ev[0]["pagina"] == 7
    assert ev[0]["fuerza"] == "fuerte"
    # No arrastra todas las paginas (p. ej. la 10 queda fuera del tope).
    assert 10 not in [e["pagina"] for e in ev]
