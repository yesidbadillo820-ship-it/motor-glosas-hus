"""El dictamen cita el FOLIO REAL donde está el soporte (V2, Pilar 3, 03-09-2026).

Hasta ahora el escrito podía decir «la epicrisis está adjunta». Para el auditor
de la EPS eso no prueba nada: le toca buscarla, y si no la encuentra rápido,
ratifica. Ahora Python abre el PDF, halla el documento que la glosa echa de
menos y el dictamen dice dónde está:

    «EL SOPORTE REQUERIDO SE ENCUENTRA ÍNTEGRAMENTE VISIBLE EN EL EXPEDIENTE
     REMITIDO: LA EPICRISIS EN EL FOLIO 3 DEL ARCHIVO ADJUNTO «soportes.pdf»»

La regla de siempre: si el término NO aparece en ningún folio, no se cita
ubicación. El folio no se inventa.
"""

from __future__ import annotations

import pytest

from app.services.ubicacion_soportes import (
    documentos_que_pide_la_glosa,
    parrafo_ubicacion_soportes,
    ubicar_documentos,
)


def _pdf(paginas: list[str]) -> bytes:
    """Un PDF de verdad, con una frase por página."""
    import pymupdf

    doc = pymupdf.open()
    for texto in paginas:
        pagina = doc.new_page()
        pagina.insert_text((72, 100), texto)
    datos = doc.tobytes()
    doc.close()
    return datos


@pytest.fixture(scope="module")
def expediente() -> bytes:
    return _pdf(["PORTADA", "ORDEN MEDICA", "EPICRISIS DEL PACIENTE", "ANEXOS"])


class TestQueDocumentoPideLaGlosa:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("SO0101 NO SE ADJUNTA LA EPICRISIS", "la epicrisis"),
            ("FA0102 NO SE ADJUNTA FORMATO MIPRES", "el formato MIPRES"),
            ("NO APORTA LA NOTA OPERATORIA", "la nota operatoria"),
            ("FALTA EL RECORD DE ANESTESIA", "el récord de anestesia"),
        ],
    )
    def test_reconoce_el_documento_reclamado(self, texto, esperado):
        assert esperado in documentos_que_pide_la_glosa(texto)

    def test_una_glosa_de_tarifa_no_pide_documentos(self):
        assert documentos_que_pide_la_glosa("TA0201 MAYOR VALOR COBRADO SEGUN CONTRATO") == []


class TestUbicarElFolioReal:
    def test_encuentra_la_epicrisis_en_su_folio(self, expediente):
        h = ubicar_documentos([("soportes.pdf", expediente)], ["la epicrisis"])
        assert len(h) == 1
        assert h[0]["folio"] == 3  # tercera página
        assert h[0]["archivo"] == "soportes.pdf"

    def test_lo_que_no_esta_no_se_ubica(self, expediente):
        assert ubicar_documentos([("soportes.pdf", expediente)], ["el formato MIPRES"]) == []

    def test_un_pdf_corrupto_no_revienta(self):
        assert ubicar_documentos([("malo.pdf", b"esto no es un pdf")], ["la epicrisis"]) == []

    def test_sin_adjuntos_no_hay_ubicacion(self):
        assert ubicar_documentos([], None) == []

    def test_varios_archivos_reportan_cada_uno_su_folio(self, expediente):
        otro = _pdf(["MIPRES No 123", "FIN"])
        h = ubicar_documentos(
            [("soportes.pdf", expediente), ("mipres.pdf", otro)],
            ["la epicrisis", "el formato MIPRES"],
        )
        ubicaciones = {(x["documento"], x["archivo"], x["folio"]) for x in h}
        assert ("la epicrisis", "soportes.pdf", 3) in ubicaciones
        assert ("el formato MIPRES", "mipres.pdf", 1) in ubicaciones


class TestElParrafoQueSeEscribe:
    def test_cita_folio_y_archivo(self, expediente):
        h = ubicar_documentos([("soportes.pdf", expediente)], ["la epicrisis"])
        p = parrafo_ubicacion_soportes(h)
        assert "ÍNTEGRAMENTE VISIBLE" in p
        assert "FOLIO 3" in p
        assert "soportes.pdf" in p

    def test_sin_hallazgos_no_escribe_nada(self):
        assert parrafo_ubicacion_soportes([]) == ""

    def test_con_varios_los_enumera(self, expediente):
        otro = _pdf(["MIPRES No 123"])
        h = ubicar_documentos(
            [("soportes.pdf", expediente), ("mipres.pdf", otro)],
            ["la epicrisis", "el formato MIPRES"],
        )
        p = parrafo_ubicacion_soportes(h)
        assert "FOLIO 3" in p and "FOLIO 1" in p and " Y " in p


class TestElMotorLoInyecta:
    """Integración: el motor cita el folio real en el dictamen."""

    @pytest.mark.asyncio
    async def test_el_dictamen_cita_el_folio_del_soporte(self, monkeypatch, expediente):
        import app.services.dictamen_directo as dd
        import app.services.validador_dictamen as vd
        from app.models.schemas import GlosaInput
        from app.services.glosa_service import GlosaService

        for v in ("QUALITY_GATE_ENABLED", "TOOL_USE_HABILITADO", "MULTI_AGENT_HABILITADO"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setattr(vd, "detectar_defectos_criticos", lambda *a, **k: [])
        monkeypatch.setattr(dd, "puede_emitir_directo", lambda *a, **k: False)

        async def fake(self, system, user, eps="", codigo="", **k):
            cuerpo = "ESE HUS NO ACEPTA LA GLOSA POR SOPORTES. " * 6
            return (f"<paciente>N/A</paciente><argumento>{cuerpo}</argumento>", "stub")

        monkeypatch.setattr(GlosaService, "_llamar_ia", fake)

        data = GlosaInput(
            eps="NUEVA EPS",
            etapa="RESPUESTA A GLOSA",
            tabla_excel="SO0101 | HUS0000601111 | NUEVA EPS. NO SE ADJUNTA LA EPICRISIS. VALOR OBJETADO $500.000.",
            valor_aceptado="0",
        )
        r = await GlosaService(groq_api_key=None).analizar(
            data,
            contexto_pdf="═══ DOCUMENTO: soportes.pdf ═══\nEPICRISIS DEL PACIENTE",
            contratos_db={},
            pdfs_raw_para_multimodal=[("soportes.pdf", expediente)],
        )
        d = r.dictamen.upper()
        assert "FOLIO 3" in d
        assert "ÍNTEGRAMENTE VISIBLE" in d

    @pytest.mark.asyncio
    async def test_sin_el_documento_no_inventa_folio(self, monkeypatch):
        import app.services.dictamen_directo as dd
        import app.services.validador_dictamen as vd
        from app.models.schemas import GlosaInput
        from app.services.glosa_service import GlosaService

        for v in ("QUALITY_GATE_ENABLED", "TOOL_USE_HABILITADO", "MULTI_AGENT_HABILITADO"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setattr(vd, "detectar_defectos_criticos", lambda *a, **k: [])
        monkeypatch.setattr(dd, "puede_emitir_directo", lambda *a, **k: False)

        async def fake(self, system, user, eps="", codigo="", **k):
            cuerpo = "ESE HUS NO ACEPTA LA GLOSA POR SOPORTES. " * 6
            return (f"<paciente>N/A</paciente><argumento>{cuerpo}</argumento>", "stub")

        monkeypatch.setattr(GlosaService, "_llamar_ia", fake)

        vacio = _pdf(["PORTADA", "OTRA COSA"])  # la epicrisis NO está
        data = GlosaInput(
            eps="NUEVA EPS",
            etapa="RESPUESTA A GLOSA",
            tabla_excel="SO0101 | HUS0000601111 | NUEVA EPS. NO SE ADJUNTA LA EPICRISIS. VALOR OBJETADO $500.000.",
            valor_aceptado="0",
        )
        r = await GlosaService(groq_api_key=None).analizar(
            data,
            contexto_pdf="═══ DOCUMENTO: soportes.pdf ═══\nPORTADA",
            contratos_db={},
            pdfs_raw_para_multimodal=[("soportes.pdf", vacio)],
        )
        assert "ÍNTEGRAMENTE VISIBLE" not in r.dictamen.upper()
