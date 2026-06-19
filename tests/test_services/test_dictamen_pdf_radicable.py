"""Tests del PDF radicable (app/services/dictamen_pdf).

El PDF es el documento formal que se sube a los portales de las EPS
para radicar la objeción: debe ser un PDF válido, con el contenido del
dictamen en texto limpio (sin HTML crudo) y los datos de la glosa.
"""

import io
from types import SimpleNamespace

import pdfplumber
import pytest

from app.services.dictamen_pdf import (
    formatear_cop,
    generar_pdf_dictamen,
    nombre_archivo_pdf,
)

DICTAMEN_HTML = (
    '<table border="1" style="width:100%;border-collapse:collapse;">'
    "<tr style='background-color:#1e40af;color:white;'>"
    "<th>CÓDIGO GLOSA</th><th>VALOR OBJETADO</th><th>CÓDIGO RESPUESTA</th></tr>"
    "<tr><td>TA0801</td><td>$36.402</td><td><b>RE9901</b><br>"
    "<span style='font-size:10px'>Glosa no aceptada</span></td></tr>"
    "<tr><td colspan='3'>N&deg; Factura: <b>HUS123456</b></td></tr></table>"
    "<div style='background:#f8fafc;'><h4>ARGUMENTACIÓN JURÍDICA</h4>"
    "<div>El valor facturado corresponde a la tarifa pactada en el contrato vigente."
    "<br/>Se solicita el levantamiento total de la glosa.</div></div>"
    "<div><b>Nota:</b> Generado con asistencia de IA.</div>"
)


def _glosa(**kw):
    base = dict(
        id=42,
        factura="HUS123456",
        eps="SANITAS",
        tercero_nombre=None,
        eps_codigo=None,
        codigo_glosa="TA0801",
        valor_objetado=36402.0,
        codigo_respuesta="RE9901",
        paciente="JUAN PEREZ",
        numero_radicado=None,
        dictamen=DICTAMEN_HTML,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _texto_pdf(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
        return "\n".join(p.extract_text() or "" for p in doc.pages)


class TestGenerarPdfDictamen:
    def test_bytes_validos_empiezan_con_magic_pdf(self):
        pdf = generar_pdf_dictamen(_glosa())
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000

    def test_contiene_datos_de_la_glosa(self):
        txt = _texto_pdf(generar_pdf_dictamen(_glosa()))
        assert "ESE HOSPITAL UNIVERSITARIO DE SANTANDER" in txt
        assert "RESPUESTA A GLOSA / OBJECIÓN" in txt
        assert "TA0801" in txt
        assert "RE9901" in txt
        assert "HUS123456" in txt
        assert "SANITAS" in txt
        assert "JUAN PEREZ" in txt
        assert "$ 36.402" in txt

    def test_dictamen_sin_html_crudo(self):
        txt = _texto_pdf(generar_pdf_dictamen(_glosa()))
        assert "<table" not in txt
        assert "<div" not in txt
        assert "style=" not in txt
        assert "tarifa pactada en el contrato vigente" in txt

    def test_pie_y_firma(self):
        txt = _texto_pdf(generar_pdf_dictamen(_glosa()))
        assert "IA GLOSAS SINAC SC" in txt
        assert "verificar antes de radicar" in txt
        assert "Firma y sello" in txt

    def test_sin_dictamen_lanza_value_error(self):
        with pytest.raises(ValueError, match="no tiene dictamen"):
            generar_pdf_dictamen(_glosa(dictamen=""))
        with pytest.raises(ValueError):
            generar_pdf_dictamen(_glosa(dictamen=None))

    def test_dictamen_texto_plano_tambien_funciona(self):
        # Dictámenes legacy/texto-fijo sin HTML deben renderizar igual
        pdf = generar_pdf_dictamen(_glosa(dictamen="Respuesta en texto plano.\n\nSegundo párrafo."))
        txt = _texto_pdf(pdf)
        assert "Respuesta en texto plano." in txt
        assert "Segundo párrafo." in txt

    def test_caracteres_xml_peligrosos_no_rompen(self):
        pdf = generar_pdf_dictamen(
            _glosa(
                dictamen='Valor < 100 & > 50 con "comillas"',
                paciente="PEREZ & GOMEZ",
            )
        )
        assert pdf.startswith(b"%PDF")


class TestNombreArchivoPdf:
    def test_formato(self):
        assert nombre_archivo_pdf(_glosa()) == "respuesta_glosa_HUS123456_42.pdf"

    def test_sanea_caracteres_raros(self):
        n = nombre_archivo_pdf(_glosa(factura='FAC/2026 "X"', id=7))
        assert n == "respuesta_glosa_FAC-2026--X_7.pdf"

    def test_sin_factura(self):
        assert nombre_archivo_pdf(_glosa(factura=None, id=9)) == "respuesta_glosa_SIN-FACTURA_9.pdf"


class TestFormatearCop:
    def test_miles_colombianos(self):
        assert formatear_cop(36402) == "$ 36.402"
        assert formatear_cop(1500000) == "$ 1.500.000"

    def test_none_y_basura(self):
        assert formatear_cop(None) == "$ 0"
        assert formatear_cop("no-numero") == "$ 0"
