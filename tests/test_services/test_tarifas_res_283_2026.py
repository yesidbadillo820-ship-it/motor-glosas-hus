"""Las tarifas institucionales de la Resolución 283 de 2026 del ESE HUS.

Yesid mandó el 20-08-2026 el archivo «TARIFAS_INSTITUCIONALES_RES_283.xlsx»,
con 695 tarifas. Comparado con lo que el motor ya tenía cargado (Res. 054/2026
+ 124/2026, 1.932 códigos):

  · 662 códigos NUEVOS que no existían — sin ellos el dictamen no podía dar el
    valor propio de esos procedimientos;
  · 22 códigos que YA estaban y cambiaron de valor. El hospital venía
    defendiendo tarifas viejas: HIERRO TOTAL a $50.000 cuando la resolución
    dice $66.500, TROPONINA T a $90.900 cuando dice $109.100;
  · 4 códigos publicados por NIVELES (el mismo CUPS con dos o tres valores),
    que quedaron FUERA a propósito.

Decisión del auditor: la 283 SE SUMA a las anteriores, no las reemplaza.
"""

from __future__ import annotations

from app.services.tarifas_oficiales import (
    buscar_tarifa_propia_hus,
    contexto_tarifa_oficial,
    tarifa_por_niveles,
    tarifas_propias_hus_completas,
)

CITA_283 = "Resolución 283 de 2026 ESE HUS"


class TestLasTarifasNuevasEstan:
    def test_baciloscopia(self):
        """El examen por el que empezó todo este módulo."""
        t = buscar_tarifa_propia_hus("901111")
        assert t is not None
        assert t["valor_pesos_2026"] == 96_800

    def test_troponina_i_cuantitativa(self):
        t = buscar_tarifa_propia_hus("903437")
        assert t is not None and t["valor_pesos_2026"] == 172_700

    def test_dengue_anticuerpos(self):
        t = buscar_tarifa_propia_hus("906208")
        assert t is not None and t["valor_pesos_2026"] == 104_000

    def test_se_encuentra_tambien_por_el_codigo_ips(self):
        """El HUS factura con el sufijo institucional: «901111H»."""
        por_cups = buscar_tarifa_propia_hus("901111")
        por_ips = buscar_tarifa_propia_hus("901111H")
        assert por_ips is not None
        assert por_ips["valor_pesos_2026"] == por_cups["valor_pesos_2026"]


class TestLasQueCambiaronDeValor:
    """El hospital defendía cifras viejas."""

    def test_hierro_total(self):
        assert buscar_tarifa_propia_hus("903846")["valor_pesos_2026"] == 66_500

    def test_troponina_t(self):
        assert buscar_tarifa_propia_hus("903439")["valor_pesos_2026"] == 109_100

    def test_renina(self):
        assert buscar_tarifa_propia_hus("904005")["valor_pesos_2026"] == 131_300


class TestNoSePerdioNadaDeLoAnterior:
    """La 283 SE SUMA. Dar de baja 1.910 tarifas que se usan todos los días
    sería el peor resultado posible de «actualizar»."""

    def test_el_catalogo_crecio(self):
        assert len(tarifas_propias_hus_completas()) > 1_932

    def test_la_colecistectomia_sigue_ahi(self):
        t = buscar_tarifa_propia_hus("512101")
        assert t is not None and t["valor_pesos_2026"] == 6_296_900

    def test_y_sigue_citando_su_propia_resolucion(self):
        """Cada tarifa cita la resolución de la que sale, no la más nueva.
        La EPS verifica la norma citada: citar una que no la contiene es
        regalarle el argumento."""
        vieja = buscar_tarifa_propia_hus("512101")
        assert "283" not in vieja["resolucion"]
        assert "124" in vieja["resolucion"]

    def test_las_nuevas_citan_la_283(self):
        assert buscar_tarifa_propia_hus("901111")["resolucion"] == CITA_283

    def test_las_actualizadas_tambien_citan_la_283(self):
        assert buscar_tarifa_propia_hus("903846")["resolucion"] == CITA_283


class TestLasTarifasPorNivelesNoSeInventan:
    """Cuatro CUPS salen repetidos con valores distintos y la resolución no
    dice cuál aplica. Elegir uno sería inventarle una cifra al dictamen."""

    def test_la_hemofiltracion_tiene_tres_niveles(self):
        assert tarifa_por_niveles("399802") == [5_450_000, 7_260_000, 9_075_000]

    def test_no_entraron_al_catalogo_con_un_valor_cualquiera(self):
        catalogo = tarifas_propias_hus_completas()
        for cups in ("399802", "399502", "399601", "908338"):
            assert cups not in catalogo, (
                f"{cups} entró al catálogo con un solo valor; la resolución "
                "publica varios y no dice cuál aplica"
            )

    def test_el_motor_avisa_en_vez_de_afirmar(self):
        texto = contexto_tarifa_oficial("399802")
        assert "NIVELES" in texto.upper()
        assert "NO afirmes" in texto
        # Y muestra los valores para que el auditor sepa entre cuáles elegir.
        assert "5.450.000" in texto and "9.075.000" in texto

    def test_un_cups_repetido_con_el_MISMO_valor_no_es_por_niveles(self):
        """325401 sale dos veces con $2.194.400 las dos: es una fila
        duplicada, no una tarifa por niveles. Sí debe estar en el catálogo."""
        assert tarifa_por_niveles("325401") is None
        assert buscar_tarifa_propia_hus("325401") is not None


class TestElDictamenCitaLaResolucionCorrecta:
    def test_el_bloque_del_prompt_trae_la_283(self):
        texto = contexto_tarifa_oficial("901111")
        assert "283" in texto

    def test_y_para_una_tarifa_vieja_no_la_trae(self):
        texto = contexto_tarifa_oficial("512101")
        assert "283" not in texto
        assert "124" in texto
