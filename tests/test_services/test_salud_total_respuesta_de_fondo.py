"""La respuesta de fondo de Salud Total reproduce lo que el HUS radica.

18-08-2026. Yesid mandó el archivo real (RTAGLOSA OK del 10-08). De ahí salió:

  • El texto de TARIFAS decía «CONFORME AL CONTRATO VIGENTE» — falso: con
    Salud Total NO hay contrato. Afirmarlo en un documento radicable le regala
    a la entidad el argumento de que sí lo había. Ahora dice la verdad.
  • Facturación (FA) salía con RE9901; el HUS radica RE9602 (injustificada).
  • Soportes (SO) salía con RE9602; el HUS radica RE9901 (subsanada).

Cada familia de motivo (Res. 2284/2023) tiene su código y su texto, tal como
en el archivo real.
"""

from __future__ import annotations

from app.services.salud_total_service import GlosaSaludTotal


def _glosa(cod_general: str, cod_espc: str = "", servicio: str = "SERVICIO X"):
    """Arma una fila de notificación (24 columnas) con el motivo dado."""
    campos = [""] * 24
    campos[0] = "07/16/2026 11:47:00 AM"
    campos[1] = "350000284269130"
    campos[8] = servicio
    campos[13] = "93340"  # ValorGlosaTotalxServ
    campos[16] = cod_general
    campos[18] = cod_espc
    return GlosaSaludTotal(campos, tipo_respuesta="extemporanea", fecha_recepcion=None)


class TestReproduceElArchivoOK:
    def test_tarifa_es_injustificada_sin_contrato(self):
        r = _glosa("TA", "TA02").generar_respuesta()
        assert r["Codigo_Respuesta_a_glosas"] == "RE9602"
        obs = r["Observacion_IPS"].upper()
        assert "SIN CONTRATO VIGENTE" in obs
        assert "SOAT VIGENTE" in obs

    def test_tarifa_ya_no_afirma_un_contrato_que_no_existe(self):
        """El bug de fondo: NO puede decir 'conforme al contrato vigente'."""
        obs = _glosa("TA", "TA02").generar_respuesta()["Observacion_IPS"].upper()
        assert "CONFORME AL CONTRATO VIGENTE" not in obs
        assert "CONTRATO VIGENTE Y AL MANUAL" not in obs

    def test_soporte_es_subsanada(self):
        r = _glosa("SO", "SO08").generar_respuesta()
        assert r["Codigo_Respuesta_a_glosas"] == "RE9901"
        assert "SOPORTES ADJUNTOS" in r["Observacion_IPS"].upper()

    def test_facturacion_es_injustificada(self):
        """FA salía RE9901; el HUS radica RE9602."""
        r = _glosa("FA", "FA06").generar_respuesta()
        assert r["Codigo_Respuesta_a_glosas"] == "RE9602"

    def test_pertinencia_es_subsanada(self):
        assert _glosa("CL", "CL06").generar_respuesta()["Codigo_Respuesta_a_glosas"] == "RE9901"

    def test_valor_aceptado_siempre_cero(self):
        for fam in ("TA", "FA", "SO", "CL"):
            assert _glosa(fam).generar_respuesta()["ValorAceptadoIPS"] == 0

    def test_ninguna_observacion_pasa_de_500(self):
        for fam in ("TA", "FA", "SO", "CL", "AU", "CO"):
            obs = _glosa(fam).generar_respuesta()["Observacion_IPS"]
            assert len(obs) <= 500

    def test_no_le_pega_el_nombre_del_servicio(self):
        """El archivo real no lleva 'SERVICIO: ...' pegado a la observación."""
        obs = _glosa("TA", "TA02", servicio="RADIOGRAFIA DE TORAX").generar_respuesta()[
            "Observacion_IPS"
        ]
        assert "SERVICIO: RADIOGRAFIA" not in obs.upper()


class TestExtemporaneidadSigueBien:
    def test_con_fecha_vencida_alega_extemporanea(self):
        from datetime import datetime

        campos = [""] * 24
        campos[0] = "07/16/2026 11:47:00 AM"  # radicó la glosa
        campos[13] = "1000"
        campos[16] = "TA"
        # Recibió la factura 3 meses antes → muy por fuera de los 20 días.
        g = GlosaSaludTotal(
            campos, tipo_respuesta="extemporanea", fecha_recepcion=datetime(2026, 4, 1)
        )
        assert g.generar_respuesta()["Codigo_Respuesta_a_glosas"] == "RE9502"

    def test_sin_fecha_no_alega_extemporanea_sino_de_fondo(self):
        r = _glosa("TA", "TA02").generar_respuesta()
        assert r["Codigo_Respuesta_a_glosas"] == "RE9602"  # de fondo, no RE9502
