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

    def test_famisanar_facturado_por_ips(self):
        """Caso real: 'VALOR UNITARIO FACTURADO POR IPS $ 206,400'."""
        txt = (
            "SE REALIZA OBJECIÓN POR MAYOR VALOR COBRADO DE ACUERDO A TARIFA "
            "CONTRATADA CON EPS FAMISANAR. SE OBJETA DIFERENCIA DE $ 38400 DE "
            "1 UNIDAD(ES), VALOR UNITARIO CONTRATADO PARA LA FECHA DE "
            "PRESTACIÓN DEL SERVICIO CON EPS FAMISANAR 168,000 EQUIVALENTE "
            "A TARIFA VALOR UNITARIO FACTURADO POR IPS $ 206,400"
        )
        v = _extraer_valores_glosa(txt)
        assert v["facturado"] == 206_400.0
        assert v["reconocido"] == 168_000.0
        assert v["objetado"] == 38_400.0

    def test_contratado_sin_palabra_por(self):
        """'VALOR UNITARIO CONTRATADO ... CON EPS FAMISANAR 168,000'."""
        txt = "VALOR UNITARIO CONTRATADO PARA LA FECHA CON EPS FAMISANAR 168,000"
        v = _extraer_valores_glosa(txt)
        assert v["reconocido"] == 168_000.0
