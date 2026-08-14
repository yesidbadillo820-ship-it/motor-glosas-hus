"""La tarifa pactada era el único dato del dictamen sin verificar.

OT-026 · 06-08-2026. El dictamen imprime tres datos duros bajo la
argumentación: servicio objetado, contrato y **tarifa pactada**. Los dos
primeros ya tenían guarda —el servicio desde OT-016, el contrato desde la
red de contratos ajenos—. La tarifa salía del modelo y nadie la cruzaba
contra nada.

Es el dato que la entidad verifica primero: le basta abrir el contrato para
desmentirlo, y de paso desacredita todo lo demás sin discutir el fondo.

Una tarifa legítima puede venir de tres sitios: el catálogo de contratos
—que es lo que el prompt le entrega al modelo—, las cláusulas cargadas de
esa entidad, o el texto de la glosa. Sin ninguno de los tres, el campo queda
con el texto neutro que ya trae el sistema.

Solo se exige respaldo cuando la tarifa afirma un PORCENTAJE, que es lo
verificable. "SOAT PLENO" o "la pactada en el contrato" no afirman un número
y pasan.
"""

from __future__ import annotations

from app.services.glosa_service import _tarifa_con_respaldo

GLOSA_AURORA = (
    "FA0101 - Se glosa el procedimiento por cuanto la tarifa pactada en el "
    "Contrato S-13-1-03-1-04958 establece SOAT menos el 12%."
)


class TestLaTarifaDelContratoSeConserva:
    def test_aurora_soat_menos_3(self):
        assert _tarifa_con_respaldo("SOAT -3% EN SMLMV", eps="AURORA")

    def test_coosalud_soat_menos_15(self):
        assert _tarifa_con_respaldo("SOAT -15 %", eps="COOSALUD")

    def test_famisanar_uvb_menos_5(self):
        assert _tarifa_con_respaldo("SOAT UVB VIGENTE -5 %", eps="FAMISANAR EPS")

    def test_ppl_soat_menos_15(self):
        assert _tarifa_con_respaldo("SOAT -15%", eps="PPL")


class TestLaTarifaInventadaSeCae:
    def test_aurora_con_un_porcentaje_que_no_es_el_suyo(self):
        assert _tarifa_con_respaldo("SOAT -20% EN SMLMV", eps="AURORA") == ""

    def test_coosalud_con_un_porcentaje_que_no_es_el_suyo(self):
        assert _tarifa_con_respaldo("SOAT -40%", eps="COOSALUD") == ""

    def test_el_numero_del_contrato_no_sirve_de_respaldo(self):
        """El catálogo de AURORA trae "GID-ARL-0090 — ARL + VIDA AP (2024)".
        La primera versión comparaba contra CUALQUIER número del texto, así
        que de ahí salían 00, 90, 20 y 24 y un "-20%" inventado pasaba como
        respaldado."""
        assert _tarifa_con_respaldo("SOAT -20%", eps="AURORA") == ""
        assert _tarifa_con_respaldo("SOAT -24%", eps="AURORA") == ""
        assert _tarifa_con_respaldo("SOAT -90%", eps="AURORA") == ""


class TestLoQueNoAfirmaUnPorcentajeNoSeVerifica:
    def test_soat_pleno(self):
        assert _tarifa_con_respaldo("SOAT PLENO", eps="SANITAS") == "SOAT PLENO"

    def test_texto_neutro(self):
        t = "TARIFA PACTADA EN EL CONTRATO"
        assert _tarifa_con_respaldo(t, eps="AURORA") == t

    def test_tarifas_propias(self):
        t = "TARIFAS PROPIAS HUS (ACTOS ADMINISTRATIVOS)"
        assert _tarifa_con_respaldo(t, eps="AURORA") == t

    def test_vacio(self):
        assert _tarifa_con_respaldo("", eps="AURORA") == ""
        assert _tarifa_con_respaldo(None, eps="AURORA") == ""


class TestElPorcentajeQueTraeLaGlosa:
    def test_si_lo_dijo_la_entidad_se_conserva(self):
        """Si el porcentaje viene del texto de la entidad, no es invención
        del motor: es el dato con el que hay que discutir."""
        assert _tarifa_con_respaldo("SOAT -12%", eps="AURORA", texto_glosa=GLOSA_AURORA)

    def test_sin_ese_texto_el_mismo_porcentaje_se_cae(self):
        assert _tarifa_con_respaldo("SOAT -12%", eps="AURORA") == ""

    def test_el_contrato_pasado_a_mano_tambien_respalda(self):
        d = "CONTRATO X — TARIFA: SOAT -7% PARA TODOS LOS SERVICIOS."
        assert _tarifa_con_respaldo("SOAT -7%", eps="OTRA / SIN DEFINIR", detalles_contrato=d)


class TestLaGuardaEstaEnchufada:
    def test_el_dictamen_la_llama(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_tarifa_con_respaldo(" in src
        i = src.index("_tarifa_con_respaldo(")
        bloque = src[i : i + 600]
        assert "texto_glosa=texto_base" in bloque
        assert "TARIFA-INVENTADA" in bloque, "un fallo no puede tumbar el dictamen"

    def test_los_tres_datos_duros_tienen_guarda(self):
        """Servicio, contrato y tarifa: los tres que la entidad verifica."""
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        for guarda in (
            "_servicio_con_respaldo(",
            "_neutralizar_contratos_ajenos(",
            "_tarifa_con_respaldo(",
        ):
            assert guarda in src, guarda
