"""No se puede glosar plata que nunca se cobró.

OT-002 · 05-08-2026. Glosa de prueba SO0202 de SUMIMEDICAL:

    "VALOR FACTURADO $1.500.000 ... VALOR GLOSADO $1.850.000"

El motor armó toda la defensa jurídica —soportes, normativa, petición de
levantamiento— y no dijo lo único que cerraba el caso solo: la EPS está
objetando $350.000 MÁS de lo que el hospital cobró. Los dos montos venían
escritos en el texto y nadie los restaba.

El aviso es una SEÑAL para el auditor, igual que el de aceptación parcial y
el de extemporaneidad: el dictamen no cambia, se le pone el dato al lado.
"""

from __future__ import annotations

from app.services.glosa_service import _facturado_y_objetado, _monto_por_etiqueta


class TestLeeLosDosMontos:
    def test_el_caso_real_so0202(self):
        t = "SO0202 FALTA DE SOPORTE. VALOR FACTURADO $1.500.000. VALOR GLOSADO $1.850.000."
        assert _facturado_y_objetado(t) == (1500000.0, 1850000.0)

    def test_con_la_palabra_total_en_medio(self):
        """«VALOR TOTAL FACTURADO» es la forma más común en los detallados
        y el lector compartido no la reconocía."""
        t = "VALOR TOTAL FACTURADO: $1.500.000 — VALOR OBJETADO: $1.850.000"
        assert _facturado_y_objetado(t) == (1500000.0, 1850000.0)

    def test_forma_verbal(self):
        t = "GLOSA SO0202: FACTURADO POR $1.500.000 Y SE GLOSAN $1.850.000"
        assert _facturado_y_objetado(t) == (1500000.0, 1850000.0)

    def test_total_de_la_factura_y_valor_de_la_glosa(self):
        t = "TOTAL DE LA FACTURA $1.500.000. VALOR DE LA GLOSA $1.850.000"
        assert _facturado_y_objetado(t) == (1500000.0, 1850000.0)

    def test_sin_montos_no_inventa(self):
        assert _facturado_y_objetado("GLOSA SIN MONTOS DECLARADOS") == (0.0, 0.0)
        assert _facturado_y_objetado("") == (0.0, 0.0)

    def test_lo_que_no_esta_etiquetado_queda_en_cero(self):
        """Sin etiqueta explícita de facturado, el aviso no puede dispararse:
        vale más callar que señalar un error que no existe."""
        fact, _ = _facturado_y_objetado("VALOR GLOSADO $300.000 SOBRE LA ATENCIÓN PRESTADA")
        assert fact == 0.0

    def test_etiqueta_suelta_sin_monto(self):
        assert _monto_por_etiqueta("VALOR FACTURADO: PENDIENTE", (r"VALOR\s+FACTURAD[OA]",)) == 0.0


class TestLaResta:
    """La condición del aviso, tal como quedó en el dictamen."""

    def _dispara(self, fact: float, obj: float) -> bool:
        # 06-08-2026: se llama a LA REGLA del motor, no a una copia del
        # umbral. Repetirlo acá dejaba estas pruebas en verde aunque
        # alguien cambiara el margen en el dictamen.
        from app.services.glosa_service import _excede_lo_facturado

        return _excede_lo_facturado(fact, obj)

    def test_el_caso_real_dispara(self):
        assert self._dispara(1500000.0, 1850000.0)

    def test_lo_normal_no_dispara(self):
        """Una glosa pide una parte de la factura: es lo esperado."""
        assert not self._dispara(2000000.0, 300000.0)

    def test_glosa_por_el_total_no_dispara(self):
        assert not self._dispara(1500000.0, 1500000.0)

    def test_diferencia_de_redondeo_no_dispara(self):
        """$1.500.000 vs $1.505.000 es ruido de IVA partido, no un error."""
        assert not self._dispara(1500000.0, 1505000.0)

    def test_sin_facturado_no_dispara(self):
        assert not self._dispara(0.0, 1850000.0)


class TestElAvisoEstaEnchufado:
    def test_el_dictamen_lo_agrega(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_facturado_y_objetado(" in src
        i = src.index("_facturado_y_objetado(")
        bloque = src[max(0, i - 1000) : i + 2000]
        assert "LA GLOSA SUPERA EL " in bloque
        assert "GLOSA-MAYOR-QUE-FACTURA" in bloque, "un fallo no puede tumbar el dictamen"

    def test_manda_el_valor_que_escribio_el_auditor(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("_facturado_y_objetado(")
        bloque = src[i : i + 900]
        assert "valor_raw" in bloque

    def test_no_toca_el_lector_compartido(self):
        """_extraer_valores_glosa también llena los campos de valor que ve el
        auditor en pantalla: ampliarle los patrones le cambiaría los montos
        precargados a todo el mundo. Por eso el lector del aviso es local."""
        import inspect

        from app.utils import parsers_glosa

        src = inspect.getsource(parsers_glosa._extraer_valores_glosa)
        assert "TOTAL\\s+FACTURAD" not in src


class TestLaReglaViveEnElMotor:
    """OT-024. El umbral estaba escrito en línea dentro del dictamen, así
    que el golden set tenía que repetirlo y se quedaba en verde aunque
    alguien cambiara el margen o invirtiera la comparación."""

    def test_la_regla_es_una_funcion_del_motor(self):
        from app.services.glosa_service import _excede_lo_facturado

        assert _excede_lo_facturado(1500000, 1850000) is True
        assert _excede_lo_facturado(2000000, 300000) is False

    def test_el_borde_del_margen(self):
        from app.services.glosa_service import _excede_lo_facturado

        assert _excede_lo_facturado(1500000, 1505000) is False  # ruido de IVA
        assert _excede_lo_facturado(1500000, 1516000) is True  # ya es error

    def test_aguanta_basura(self):
        from app.services.glosa_service import _excede_lo_facturado

        for f, o in ((None, None), ("x", "y"), (0, 100), (-1, 5)):
            assert _excede_lo_facturado(f, o) is False, (f, o)

    def test_el_dictamen_llama_a_la_regla_y_no_repite_el_umbral(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_excede_lo_facturado(" in src
        assert "* 0.01)" not in src, "el umbral volvió a quedar escrito en línea"
