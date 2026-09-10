"""Al analizar una glosa de tarifas, el auditor tiene que VER la evidencia.

09-09-2026, pedido de Yesid: «que cuando analicen una glosa vean qué van a
auditar, y si es por tarifas que aparezca el Excel de la tarifa pactada y el
valor para que ellos lo analicen».

Y el dato ya existía. El motor cruzaba la factura contra las 19.051 filas del
catálogo de tarifas que cargó el hospital… y el resultado se pegaba como HTML
DENTRO del texto del dictamen. Dos problemas de una vez:

  · la pantalla no podía pintarlo como una tabla de verdad, y
  · ese cuadro de trabajo interno terminaba metido en el escrito que se
    radica ante la entidad, donde no pinta nada.

Ahora sale como dato: el renglón exacto del contrato —con el archivo del que
salió, para que el auditor pueda ir a comprobarlo— junto a las cifras del
caso.

QUÉ CUIDA ESTA PRUEBA. Que la evidencia se arme con lo que hay y NUNCA con lo
que no: en este motor un valor en cero no es «cero pesos», es «no se pudo
leer», y restar contra ese cero daría una diferencia inventada del tamaño de
la factura.
"""

from __future__ import annotations

import pytest

from app.api.routers.analizar import _evidencia_de_la_tarifa

FILA = {
    "id": 7,
    "eps": "FAMISANAR EPS",
    "codigo_cups": "890201",
    "codigo_ips": "CS-0201",
    "descripcion": "CONSULTA DE PRIMERA VEZ POR MEDICINA ESPECIALIZADA",
    "contrato_numero": "CW-2026-FAMISANAR-0142",
    "valor_pactado": 157250.0,
    "tipo_tarifa": "SOAT_PORCENTAJE",
    "factor_ajuste": -15.0,
    "modalidad": "EVENTO",
    "fuente_archivo": "TARIFAS_FAMISANAR_2026_v3.xlsx",
    "vigencia_desde": "2026-01-01",
    "vigencia_hasta": "2026-12-31",
}


def _info(**cambios):
    base = {
        "encontrada": True,
        "tarifa": dict(FILA),
        "valor_facturado": 185000.0,
        "valor_objetado": 27750.0,
        "valor_reconocido": 157250.0,
        "valor_pactado_calc": 157250.0,
        "recomendacion": {"accion": "ACEPTAR_PARCIAL"},
        "homologacion_2641": None,
    }
    base.update(cambios)
    return base


class TestElRenglonDelContratoLlegaCompleto:
    def test_sale_el_codigo_y_el_servicio(self):
        f = _evidencia_de_la_tarifa(_info())["fila_del_catalogo"]
        assert f["codigo_cups"] == "890201"
        assert "CONSULTA DE PRIMERA VEZ" in f["descripcion"]

    def test_sale_de_que_archivo_salio(self):
        """Es lo que le permite al auditor ir a buscarlo y comprobarlo por su
        cuenta, en vez de creerle al motor."""
        f = _evidencia_de_la_tarifa(_info())["fila_del_catalogo"]
        assert f["fuente_archivo"] == "TARIFAS_FAMISANAR_2026_v3.xlsx"

    def test_sale_como_se_pacto_no_solo_cuanto(self):
        """«SOAT -15%» y «$157.250» dicen cosas distintas: la primera se puede
        discutir con el contrato en la mano."""
        f = _evidencia_de_la_tarifa(_info())["fila_del_catalogo"]
        assert f["tipo_tarifa"] == "SOAT_PORCENTAJE"
        assert f["factor_ajuste"] == -15.0

    def test_sale_el_contrato_y_su_vigencia(self):
        f = _evidencia_de_la_tarifa(_info())["fila_del_catalogo"]
        assert f["contrato_numero"] == "CW-2026-FAMISANAR-0142"
        assert f["vigencia_desde"] and f["vigencia_hasta"]


class TestLaDiferenciaSoloSeCalculaSiSePuede:
    """En este motor el 0 no es «cero pesos»: es «no se pudo leer la cifra»."""

    def test_con_las_dos_cifras_se_calcula(self):
        c = _evidencia_de_la_tarifa(_info())["las_cifras_del_caso"]
        assert c["diferencia"] == 27750.0

    def test_sin_el_facturado_NO_se_inventa_una_diferencia(self):
        c = _evidencia_de_la_tarifa(_info(valor_facturado=0))["las_cifras_del_caso"]
        assert c["diferencia"] is None, (
            "Restó contra un cero: la 'diferencia' saldría del tamaño de toda "
            "la tarifa pactada y el auditor la leería como un sobrecosto real."
        )

    def test_sin_la_tarifa_pactada_tampoco(self):
        c = _evidencia_de_la_tarifa(_info(valor_pactado_calc=0))["las_cifras_del_caso"]
        assert c["diferencia"] is None

    def test_se_dice_QUE_falta_por_su_nombre(self):
        c = _evidencia_de_la_tarifa(_info(valor_facturado=0))["las_cifras_del_caso"]
        assert c["no_se_pudo_leer"] == ["el valor facturado"]

    def test_pueden_faltar_varias(self):
        c = _evidencia_de_la_tarifa(_info(valor_facturado=0, valor_objetado=0))[
            "las_cifras_del_caso"
        ]
        assert "el valor facturado" in c["no_se_pudo_leer"]
        assert "el valor objetado" in c["no_se_pudo_leer"]

    def test_con_todo_completo_no_falta_nada(self):
        c = _evidencia_de_la_tarifa(_info())["las_cifras_del_caso"]
        assert c["no_se_pudo_leer"] == []

    def test_un_cero_no_se_entrega_como_cero(self):
        """Se entrega como None para que la pantalla diga «no se pudo leer»
        en vez de pintar «$0», que se lee como un dato real."""
        c = _evidencia_de_la_tarifa(_info(valor_facturado=0))["las_cifras_del_caso"]
        assert c["facturado"] is None

    def test_facturado_igual_a_pactado_da_diferencia_cero(self):
        """Cero SÍ es un resultado válido acá: significa que la objeción no
        tiene sustento tarifario. No confundirlo con «no se pudo calcular»."""
        c = _evidencia_de_la_tarifa(_info(valor_facturado=157250.0))["las_cifras_del_caso"]
        assert c["diferencia"] == 0.0


class TestCuandoNoHayNadaQueMostrar:
    """Que el motor no tenga con qué comparar es información, no un hueco que
    haya que disimular."""

    @pytest.mark.parametrize("info", [None, {}, {"encontrada": False}])
    def test_no_se_inventa_una_evidencia(self, info):
        assert _evidencia_de_la_tarifa(info) is None

    def test_sin_fila_en_el_catalogo_no_hay_panel(self):
        assert _evidencia_de_la_tarifa({"encontrada": False, "tarifa": {}}) is None


class TestLaHomologacionSeAvisa:
    """Si el código facturado no es el mismo del contrato, el auditor tiene
    que saber que el cruce pasó por una traducción."""

    def test_se_entrega_cuando_se_aplico(self):
        ev = _evidencia_de_la_tarifa(
            _info(
                homologacion_2641={
                    "aplicada": True,
                    "codigo_entrada": "39147B-18",
                    "cups_oficial": "39147",
                    "norma": "Res. 2641/2025 MinSalud — CUPS 2025",
                }
            )
        )
        assert ev["homologacion"]["codigo_entrada"] == "39147B-18"

    def test_no_se_entrega_cuando_el_codigo_cruzo_directo(self):
        ev = _evidencia_de_la_tarifa(_info(homologacion_2641={"aplicada": False}))
        assert ev["homologacion"] is None


class TestElContratoDeLaRespuesta:
    def test_el_campo_existe_en_el_resultado(self):
        from app.models.schemas import GlosaResult

        assert "evidencia_tarifa" in GlosaResult.model_fields

    def test_nace_vacio(self):
        """Las glosas que no son de tarifas no lo llevan, y eso es correcto."""
        from app.models.schemas import GlosaResult

        assert GlosaResult.model_fields["evidencia_tarifa"].default is None

    def test_el_analisis_lo_llena(self):
        import inspect

        from app.api.routers import analizar

        fuente = inspect.getsource(analizar)
        assert "resultado.evidencia_tarifa = _evidencia_de_la_tarifa(info_tarifa_pre)" in fuente, (
            "La evidencia se arma pero nadie la pone en el resultado: la "
            "pantalla nunca la recibiría."
        )
