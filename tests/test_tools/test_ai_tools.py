"""
Pruebas de nucleo.ai_tools (funciones de IA de la caja PDF — fase 3).

No hacen llamadas reales a Gemini: se mockea el transporte (urllib) o la
función _llamar. Así corren en CI sin API key ni internet. Las que arman
insumos PDF necesitan PyMuPDF; traducir necesita python-docx (importorskip).
"""

import json
import os
import sys
import urllib.error
import urllib.request

import pytest

SUITE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "tools", "suite_cartera_hus")
)
if SUITE not in sys.path:
    sys.path.insert(0, SUITE)

fitz = pytest.importorskip("fitz")

from nucleo import ai_tools  # noqa: E402


def _silencio(_):
    pass


@pytest.fixture
def pdf_mixto(tmp_path):
    """PDF con una página de texto y una página casi vacía (irá como imagen)."""
    ruta = str(tmp_path / "doc.pdf")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Factura HUS con texto suficiente para pasar el umbral")
    doc.new_page()  # vacía → imagen (OCR)
    doc.save(ruta)
    doc.close()
    return ruta


# ------------------------------------------------------------- disponibilidad


def test_disponible_segun_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert ai_tools.disponible() is False
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert ai_tools.disponible() is True


def test_sin_key_mensaje_claro(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        ai_tools._llamar("s", [ai_tools._parte_texto("hola")])


# ------------------------------------------------------------- transporte


def test_llamar_arma_peticion_correcta(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "CLAVE_TEST")
    capturado = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"candidates": [{"content": {"parts": [{"text": "OK_IA"}]}}]}
            ).encode()

    def fake_urlopen(req, timeout=0):
        capturado["url"] = req.full_url
        capturado["headers"] = {k.lower(): v for k, v in req.header_items()}
        capturado["body"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    out = ai_tools._llamar(
        "Eres auditor", [ai_tools._parte_pdf(b"%PDF fake"), ai_tools._parte_texto("resume")]
    )
    assert out == "OK_IA"
    # la key NUNCA en la URL, SIEMPRE en el header
    assert "CLAVE_TEST" not in capturado["url"]
    assert capturado["headers"].get("x-goog-api-key") == "CLAVE_TEST"
    cuerpo = capturado["body"]
    assert "systemInstruction" in cuerpo
    assert cuerpo["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0
    assert any("inline_data" in p for p in cuerpo["contents"][0]["parts"])


def test_llamar_http_error_claro(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        ai_tools._llamar("s", [ai_tools._parte_texto("x")])


# ------------------------------------------------------------- páginas


def test_paginas_texto_vs_imagen(pdf_mixto):
    tipos = [t for _, _, t in ai_tools._paginas_como_partes(pdf_mixto, _silencio)]
    assert tipos == ["texto", "imagen (OCR)"]


# ------------------------------------------------------------- operaciones (mock _llamar)


def test_resumir_escribe_md(pdf_mixto, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_tools, "_llamar", lambda system, parts, **k: "RESUMEN IA")
    out = ai_tools.resumir(pdf_mixto, str(tmp_path / "r.md"), log=_silencio)
    assert out.endswith(".md")
    assert open(out, encoding="utf-8").read() == "RESUMEN IA"


def test_markdown_une_paginas(pdf_mixto, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_tools, "_llamar", lambda system, parts, **k: "# Página")
    out = ai_tools.a_markdown(pdf_mixto, str(tmp_path / "m.md"), log=_silencio)
    # dos páginas → dos bloques unidos
    assert open(out, encoding="utf-8").read().count("# Página") == 2


def test_ocr_escribe_txt(pdf_mixto, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_tools, "_llamar", lambda system, parts, **k: "texto pagina")
    out = ai_tools.ocr(pdf_mixto, str(tmp_path / "o.txt"), log=_silencio)
    assert out.endswith(".txt") and "texto pagina" in open(out, encoding="utf-8").read()


def test_traducir_genera_docx(pdf_mixto, tmp_path, monkeypatch):
    pytest.importorskip("docx")
    monkeypatch.setattr(ai_tools, "_llamar", lambda system, parts, **k: "translated text")
    out = ai_tools.traducir(pdf_mixto, "inglés", str(tmp_path / "t.docx"), log=_silencio)
    from docx import Document

    doc = Document(out)
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "translated text" in texto
