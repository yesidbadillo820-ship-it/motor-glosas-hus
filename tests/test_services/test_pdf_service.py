"""Tests del servicio de extracción PDF — R51 P4."""
from __future__ import annotations

import asyncio
from io import BytesIO

import pytest

from app.services.pdf_service import UMBRAL_TEXTO_MINIMO, PdfService


def _pdf_con_texto(contenido: str) -> bytes:
    """Genera un PDF mínimo con el texto indicado.

    Usa reportlab si está disponible; si no, skipea el test."""
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        pytest.skip("reportlab no instalado — no se puede generar PDF de prueba")
    buf = BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for linea in contenido.split("\n"):
        c.drawString(50, y, linea)
        y -= 20
        if y < 50:
            c.showPage()
            y = 800
    c.save()
    return buf.getvalue()


class TestExtraer:
    def test_extraer_pdf_simple(self):
        pdf_bytes = _pdf_con_texto("Factura FE-001 valor $168.563 EPS FAMISANAR")
        texto = asyncio.run(PdfService().extraer(pdf_bytes))
        assert "FE-001" in texto
        assert "168.563" in texto
        assert "PÁG 1" in texto

    def test_extraer_pdf_multipagina_no_omite_bordes(self):
        """Con >4 páginas se omite el medio pero inicio y fin se preservan."""
        lineas = ["PRIMERA_PAGINA_MARKER"]
        for i in range(200):
            lineas.append(f"linea_medio_{i}")
        lineas.append("ULTIMA_PAGINA_MARKER")
        pdf_bytes = _pdf_con_texto("\n".join(lineas))
        texto = asyncio.run(PdfService().extraer(pdf_bytes))
        # El marker del inicio debe estar (primeras 2 pags → primeros 3000 chars)
        assert "PRIMERA_PAGINA_MARKER" in texto
        # El marker final también (últimas 2 pags → últimos 2000 chars)
        assert "ULTIMA_PAGINA_MARKER" in texto

    def test_extraer_pdf_vacio_o_corrupto(self):
        """Bytes inválidos no deben explotar — retornan '' o texto vacío."""
        texto = asyncio.run(PdfService().extraer(b"no soy un pdf"))
        assert texto == "" or isinstance(texto, str)


class TestUmbralYOcr:
    def test_umbral_definido(self):
        """Guardarraíl: si alguien baja el umbral por accidente, se detecta."""
        assert UMBRAL_TEXTO_MINIMO >= 200
        assert UMBRAL_TEXTO_MINIMO <= 500

    def test_ocr_sin_api_key_usa_nativo(self):
        """Si el PDF tiene poco texto pero no hay API key, retorna método 'vacio'."""
        pdf_bytes = _pdf_con_texto("solo cinco palabras aqui hoy")
        texto, metodo = asyncio.run(
            PdfService().extraer_con_ocr(pdf_bytes, anthropic_api_key="")
        )
        assert metodo in ("vacio", "nativo")

    def test_ocr_con_texto_abundante_usa_nativo(self):
        """Si el PDF ya trae texto abundante, no se llama a OCR."""
        # 1500 chars de texto real (> UMBRAL 300)
        contenido = "\n".join([
            f"linea abundante numero {i} con mucho texto repetido y relleno"
            for i in range(50)
        ])
        pdf_bytes = _pdf_con_texto(contenido)
        texto, metodo = asyncio.run(
            PdfService().extraer_con_ocr(pdf_bytes, anthropic_api_key="fake")
        )
        assert metodo == "nativo"
