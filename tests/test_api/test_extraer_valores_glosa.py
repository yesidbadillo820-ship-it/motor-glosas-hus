"""Tests del extractor de valores desde texto de glosa (_extraer_valores_glosa)."""
from app.main import _extraer_valores_glosa


class TestExtraerValoresGlosa:
    def test_caso_real_famisanar(self):
        """Texto real del motor: facturado + reconocido + diferencia."""
        txt = (
            "TA0201 - CONSULTA DE URGENCIAS - CUPS 890750 - facturada por "
            "$114.900 y reconocida solo por $90.000, objetándose una "
            "diferencia de $24.900"
        )
        v = _extraer_valores_glosa(txt)
        assert v["facturado"] == 114_900.0
        assert v["reconocido"] == 90_000.0
        assert v["objetado"] == 24_900.0

    def test_mayusculas_y_minusculas(self):
        txt = "FACTURADA POR $50.000 Y ACEPTADA POR $30.000"
        v = _extraer_valores_glosa(txt)
        assert v["facturado"] == 50_000.0
        assert v["reconocido"] == 30_000.0

    def test_solo_facturado(self):
        txt = "valor facturado: $100.000 sin más info"
        v = _extraer_valores_glosa(txt)
        assert v["facturado"] == 100_000.0
        assert v["reconocido"] == 0.0

    def test_texto_vacio(self):
        v = _extraer_valores_glosa("")
        assert v == {"facturado": 0.0, "reconocido": 0.0, "objetado": 0.0}

    def test_none(self):
        v = _extraer_valores_glosa(None)
        assert v == {"facturado": 0.0, "reconocido": 0.0, "objetado": 0.0}

    def test_glosa_con_diferencia(self):
        txt = "GLOSADO POR $5.000 DIFERENCIA DE $5.000"
        v = _extraer_valores_glosa(txt)
        # "diferencia" y "glosado" son alias de objetado; alguno debe pegar
        assert v["objetado"] == 5_000.0

    def test_formato_pesos_sin_puntos(self):
        txt = "FACTURADO POR 20000 Y RECONOCIDO POR 15000"
        v = _extraer_valores_glosa(txt)
        assert v["facturado"] == 20_000.0
        assert v["reconocido"] == 15_000.0

    def test_formato_con_decimales(self):
        txt = "FACTURADO POR $20.000,50"
        v = _extraer_valores_glosa(txt)
        assert v["facturado"] == 20_000.5
