"""El Excel de Glosas ADRES dice quién trabaja cada factura, no «(sin gestor)».

02-09-2026. Yesid: «la celda GESTOR no me dice qué gestor la está trabajando
para esas que están EN PROCESO o CERRADA; este dato se puede sacar por el
correo de las celdas Cerrada por».

En el paquete 31078 las 84 facturas salían «(sin gestor asignado)», aunque 16
estaban cerradas por auditorhus01/02/03 y glosashus03, y 41 en proceso con
glosas ya decididas. Se prueba la regla pura, sin base de datos.
"""

from __future__ import annotations

from app.services.gestor_adres import (
    ORIGEN_CIERRE,
    ORIGEN_DECISIONES,
    ORIGEN_MACRO,
    ORIGEN_REAPERTURA,
    SIN_GESTOR,
    VENIA_EN_LA_MACRO,
    nombre_de,
    quien_la_trabaja,
)

NOMBRES = {
    "auditorhus02@sinacsc.com": "Carolina Rueda",
    "auditorhus01@sinacsc.com": "Claudia Prada",
    "glosashus09@sinacsc.com": "Jhon Alex",
}


class TestElNombre:
    def test_el_correo_se_cambia_por_el_nombre_de_la_tabla(self):
        assert nombre_de("auditorhus02@sinacsc.com", NOMBRES) == "Carolina Rueda"

    def test_mayusculas_y_espacios_no_estorban(self):
        assert nombre_de("  AuditorHUS02@sinacsc.com ", NOMBRES) == "Carolina Rueda"

    def test_correo_sin_nombre_se_deja_tal_cual(self):
        """No se inventa un nombre: se muestra el correo, que es el dato real."""
        assert nombre_de("glosashus03@sinacsc.com", NOMBRES) == "glosashus03@sinacsc.com"

    def test_vacio_da_vacio(self):
        assert nombre_de(None, NOMBRES) == ""
        assert nombre_de("   ", NOMBRES) == ""


class TestQuienLaTrabaja:
    def test_la_macro_manda_si_trae_gestor(self):
        g, o = quien_la_trabaja(
            "MARIA",
            "CERRADA",
            "auditorhus02@sinacsc.com",
            None,
            ["glosashus09@sinacsc.com"],
            NOMBRES,
        )
        assert (g, o) == ("MARIA", ORIGEN_MACRO)

    def test_sin_gestor_asignado_no_cuenta_como_gestor_de_la_macro(self):
        g, o = quien_la_trabaja(
            SIN_GESTOR, "CERRADA", "auditorhus02@sinacsc.com", None, [], NOMBRES
        )
        assert (g, o) == ("Carolina Rueda", ORIGEN_CIERRE)

    def test_cerrada_es_quien_la_cerro(self):
        """El caso de las 6 facturas cerradas por auditorhus02 en el 31078."""
        g, o = quien_la_trabaja("", "CERRADA", "auditorhus02@sinacsc.com", None, [], NOMBRES)
        assert (g, o) == ("Carolina Rueda", ORIGEN_CIERRE)

    def test_cerrada_por_un_correo_sin_nombre_muestra_el_correo(self):
        g, o = quien_la_trabaja("", "CERRADA", "glosashus03@sinacsc.com", None, [], NOMBRES)
        assert (g, o) == ("glosashus03@sinacsc.com", ORIGEN_CIERRE)

    def test_cerrada_manda_sobre_quien_decidio(self):
        """Si otra persona decidió glosas pero Carolina la cerró, la cerró Carolina."""
        g, o = quien_la_trabaja(
            "",
            "CERRADA",
            "auditorhus02@sinacsc.com",
            None,
            ["glosashus09@sinacsc.com"] * 5,
            NOMBRES,
        )
        assert (g, o) == ("Carolina Rueda", ORIGEN_CIERRE)

    def test_en_proceso_es_quien_decidio_sus_glosas(self):
        """El caso de HUS405315 en el 31073: una glosa marcada por glosashus09."""
        g, o = quien_la_trabaja("", "EN PROCESO", None, None, ["glosashus09@sinacsc.com"], NOMBRES)
        assert (g, o) == ("Jhon Alex", ORIGEN_DECISIONES)

    def test_lo_que_venia_en_la_macro_no_es_una_persona(self):
        g, o = quien_la_trabaja(
            "", "EN PROCESO", None, None, [VENIA_EN_LA_MACRO, "", None], NOMBRES
        )
        assert (g, o) == (SIN_GESTOR, "")

    def test_varias_personas_la_que_mas_decidio_va_primero(self):
        decididos = ["glosashus09@sinacsc.com"] * 2 + ["auditorhus01@sinacsc.com"] * 5
        g, o = quien_la_trabaja("", "EN PROCESO", None, None, decididos, NOMBRES)
        assert (g, o) == ("Claudia Prada / Jhon Alex", ORIGEN_DECISIONES)

    def test_mas_de_tres_personas_se_resume(self):
        decididos = ["a@x.co", "b@x.co", "c@x.co", "d@x.co", "e@x.co"]
        g, o = quien_la_trabaja("", "EN PROCESO", None, None, decididos, {})
        assert g.endswith(" y 2 más")
        assert g.count(" / ") == 2
        assert o == ORIGEN_DECISIONES

    def test_reabierta_sin_decisiones_nuevas_es_quien_la_reabrio(self):
        g, o = quien_la_trabaja(
            "", "EN PROCESO", "auditorhus02@sinacsc.com", "glosashus09@sinacsc.com", [], NOMBRES
        )
        assert (g, o) == ("Jhon Alex", ORIGEN_REAPERTURA)

    def test_reabierta_con_decisiones_nuevas_es_quien_decidio(self):
        g, o = quien_la_trabaja(
            "",
            "EN PROCESO",
            "auditorhus02@sinacsc.com",
            "glosashus09@sinacsc.com",
            ["auditorhus01@sinacsc.com"],
            NOMBRES,
        )
        assert (g, o) == ("Claudia Prada", ORIGEN_DECISIONES)

    def test_pendiente_sin_huella_sigue_sin_gestor(self):
        g, o = quien_la_trabaja("", "PENDIENTE", None, None, [], NOMBRES)
        assert (g, o) == (SIN_GESTOR, "")

    def test_estado_raro_con_cierre_viejo_usa_el_cierre(self):
        """Estado en blanco pero con cerrada_por: mejor ese dato que nada."""
        g, o = quien_la_trabaja("", "", "auditorhus01@sinacsc.com", None, [], NOMBRES)
        assert (g, o) == ("Claudia Prada", ORIGEN_CIERRE)
