"""Una devolución no es una glosa, y el trámite es otro.

Prueba real del 05-08-2026, glosa de trampa Nº 8:

    "DE1601 FACTURA DEVUELTA POR NO CORRESPONDER A USUARIO DE LA ENTIDAD.
     VALOR TOTAL $3.900.000."

El motor la clasificó como «FA FACTURACIÓN», dejó el código en «N/A» y la
respondió con el formato de una glosa —incluso hablando del «servicio
facturado con CUPS DE1601»—.

La causa: el único lugar del sistema que nombraba los códigos DE los
mapeaba a FA para reutilizar ejemplos, y el lector de códigos de glosa ni
siquiera los reconocía.

Son trámites distintos: en una devolución la factura vuelve COMPLETA y hay
que corregir la causa y radicarla de nuevo dentro del término (art. 57 de
la Ley 1438 de 2011; anexo de devoluciones de la Resolución 2284 de 2023).
No se «controvierte» un valor.
"""

from __future__ import annotations

from app.services.glosa_service import GlosaService

GLOSA_DEVOLUCION = "DE1601 FACTURA DEVUELTA POR NO CORRESPONDER A USUARIO DE LA ENTIDAD."


def _svc() -> GlosaService:
    return GlosaService(groq_api_key="gsk_x")


class TestElCodigoSeReconoce:
    def test_ya_no_queda_en_na(self):
        assert _svc()._extraer_codigo_glosa(GLOSA_DEVOLUCION) == "DE1601"

    def test_tambien_en_la_lista_completa(self):
        assert "DE1601" in _svc()._extraer_codigos_glosa(GLOSA_DEVOLUCION)

    def test_las_demas_familias_no_cambian(self):
        s = _svc()
        assert s._extraer_codigo_glosa("TA0801 GLOSA POR TARIFA") == "TA0801"
        assert s._extraer_codigo_glosa("SO0201 FALTA EPICRISIS") == "SO0201"


class TestSeClasificaComoDevolucion:
    def test_ya_no_es_facturacion(self):
        tipo = _svc()._determinar_tipo_glosa("DE", GLOSA_DEVOLUCION)
        assert tipo == "DE_DEVOLUCION"
        assert tipo != "FA_FACTURACION"

    def test_una_glosa_de_facturacion_sigue_siendo_facturacion(self):
        assert _svc()._determinar_tipo_glosa("FA", "FA0301 CÓDIGO ERRADO") == "FA_FACTURACION"

    def test_la_extemporaneidad_sigue_mandando(self):
        """Si además está fuera de término, eso pesa más."""
        tipo = _svc()._determinar_tipo_glosa("DE", "DE1601 GLOSA EXTEMPORANEA")
        assert tipo == "EXT_EXTEMPORANEA"


class TestElAvisoDeTramite:
    def test_el_dictamen_advierte_que_el_tramite_es_otro(self):
        import inspect

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("ESTO ES UNA")
        bloque = src[i - 400 : i + 2000]
        assert "DEVOLUCIÓN, NO UNA GLOSA" in bloque
        assert "1438 de 2011" in bloque
        assert "2284 de 2023" in bloque
        assert "radicarla de nuevo" in bloque

    def test_solo_se_agrega_a_las_devoluciones(self):
        import inspect

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("ESTO ES UNA")
        assert 'startswith("DE")' in src[i - 600 : i]
