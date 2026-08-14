"""Dos hechos que el dictamen afirmaba sin tener de dónde sacarlos.

Pruebas reales del 05-08-2026 en el motor del hospital, sin soportes:

  OT-015 · COMPENSAR AU0401 — la glosa no traía ninguna fecha y el dictamen
  salió con "...EN EL PERIODO CORRESPONDIENTE AL AÑO 2023". Ese año no
  existe en el caso. La entidad abre la factura, ve otra fecha y desacredita
  el dictamen entero sin discutir el fondo.

  OT-016 · AURORA FA0101 — la glosa hablaba solo de tarifa y contrato, no
  había CUPS ni PDF, y el dictamen salió con "Servicio objetado: ESTANCIA U
  OBSERVACIÓN DE URGENCIAS". El modelo lo puso porque el campo lo pedía.

Un servicio legítimo puede venir de tres sitios: la descripción del CUPS del
catálogo, el texto de la glosa, o el PDF de soportes. Sin ninguno de los
tres, el dictamen usa el texto neutro que ya trae el sistema — que no afirma
nada — en vez de nombrar un servicio que nadie prestó.
"""

from __future__ import annotations

from app.services.glosa_service import (
    _neutralizar_periodo_inventado,
    _servicio_con_respaldo,
)

GLOSA_COMPENSAR = (
    "AU0401 - Se glosa por cuanto el procedimiento 895201 no corresponde con la "
    "descripción clínica registrada."
)
GLOSA_AURORA = (
    "FA0101 - Se glosa el procedimiento por cuanto el valor facturado supera la "
    "tarifa pactada en el Contrato S-13-1-03-1-04958, cláusula 7.4."
)


class TestElPeriodoInventado:
    def test_el_caso_real_compensar(self):
        d = (
            "ESE HUS NO ACEPTA LA GLOSA AU0401, RESPECTO DEL PROCEDIMIENTO FACTURADO, "
            "EN EL PERIODO CORRESPONDIENTE AL AÑO 2023. SE SOLICITA EL LEVANTAMIENTO."
        )
        out = _neutralizar_periodo_inventado(d, GLOSA_COMPENSAR)
        assert "2023" not in out
        assert "PERIODO" not in out.upper()
        assert "SE SOLICITA EL LEVANTAMIENTO." in out

    def test_si_el_año_esta_en_la_glosa_se_conserva(self):
        """Si el gestor pegó la fecha, el año es dato del expediente."""
        glosa = "AU0401 - Atención del 12/03/2023. El procedimiento no corresponde."
        d = "ESE HUS NO ACEPTA LA GLOSA, EN EL PERIODO CORRESPONDIENTE AL AÑO 2023."
        assert _neutralizar_periodo_inventado(d, glosa) == d

    def test_otras_formas_de_afirmar_el_periodo(self):
        for d in (
            "EL SERVICIO SE PRESTÓ DURANTE LA VIGENCIA 2021 SEGÚN LO PACTADO.",
            "FACTURADO EN EL AÑO 2022 CONFORME AL CONTRATO.",
            "LA ATENCIÓN CORRESPONDE AL PERIODO 2019.",
        ):
            out = _neutralizar_periodo_inventado(d, GLOSA_COMPENSAR)
            assert out != d, d

    def test_no_toca_las_fechas_del_contrato(self):
        """La vigencia del contrato viene del catálogo, no es una invención."""
        d = (
            "SEGÚN EL CONTRATO S-13-1-03-1-04958 VIGENTE DESDE EL 15 DE ABRIL DE 2026 "
            "HASTA EL 14 DE ABRIL DE 2027."
        )
        assert _neutralizar_periodo_inventado(d, GLOSA_AURORA) == d

    def test_no_toca_las_normas(self):
        d = "EN VIRTUD DEL ARTÍCULO 57 DE LA LEY 1438 DE 2011 Y LA RESOLUCIÓN 2284 DE 2023."
        assert _neutralizar_periodo_inventado(d, GLOSA_AURORA) == d

    def test_dictamen_sin_periodo_sale_identico(self):
        d = "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO."
        assert _neutralizar_periodo_inventado(d, GLOSA_AURORA) == d

    def test_texto_vacio(self):
        assert _neutralizar_periodo_inventado("", GLOSA_AURORA) == ""

    def test_no_deja_puntuacion_suelta(self):
        d = "ESE HUS NO ACEPTA LA GLOSA, EN EL AÑO 2023, Y SOLICITA EL LEVANTAMIENTO."
        out = _neutralizar_periodo_inventado(d, GLOSA_COMPENSAR)
        assert ", ," not in out
        assert "  " not in out


class TestElServicioInventado:
    def test_el_caso_real_aurora(self):
        assert _servicio_con_respaldo("ESTANCIA U OBSERVACIÓN DE URGENCIAS", GLOSA_AURORA) == ""

    def test_con_cups_se_conserva(self):
        """Con CUPS, el nombre pudo salir del catálogo de tarifas."""
        s = "ESTANCIA U OBSERVACIÓN DE URGENCIAS"
        assert _servicio_con_respaldo(s, GLOSA_AURORA, cups="890201") == s

    def test_con_pdf_se_conserva(self):
        s = "ESTANCIA U OBSERVACIÓN DE URGENCIAS"
        assert _servicio_con_respaldo(s, GLOSA_AURORA, contexto_pdf="epicrisis del ingreso") == s

    def test_nombrado_en_la_glosa_se_conserva(self):
        s = "TAC DE ABDOMEN"
        assert _servicio_con_respaldo(s, "TA0601 - TAC de abdomen no pertinente") == s

    def test_sin_tildes_tambien_se_reconoce(self):
        s = "EXPLORACIÓN ESPECIALIZADA"
        g = "AU0401 - se facturó una exploracion especializada"
        assert _servicio_con_respaldo(s, g) == s

    def test_el_texto_neutro_no_se_toca(self):
        """No nombra ningún servicio: no hay nada que verificar."""
        s = "EL PROCEDIMIENTO FACTURADO"
        assert _servicio_con_respaldo(s, GLOSA_AURORA) == s

    def test_vacio_sigue_vacio(self):
        assert _servicio_con_respaldo("", GLOSA_AURORA) == ""

    def test_sin_texto_de_glosa_no_borra(self):
        """Sin nada contra qué comparar, no se asume invención."""
        s = "ESTANCIA U OBSERVACIÓN DE URGENCIAS"
        assert _servicio_con_respaldo(s, "") == s


class TestLasGuardasEstanEnchufadas:
    def test_el_periodo_pasa_por_la_cadena_de_redes_finales(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_neutralizar_periodo_inventado(" in src
        i = src.index("_neutralizar_periodo_inventado(")
        assert "PERIODO-INVENTADO" in src[i : i + 1200]

    def test_el_servicio_se_verifica_antes_de_armar_el_dictamen(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_servicio_con_respaldo(" in src
        i = src.index("_servicio_con_respaldo(")
        bloque = src[i : i + 500]
        assert "texto_glosa=texto_base" in bloque
        assert "contexto_pdf=contexto_pdf" in bloque
        assert "SERVICIO-INVENTADO" in bloque


class TestElAñoPuedeVenirDeOtraParteDelExpediente:
    """El primer arreglo solo miraba el texto pegado. Si el año está en los
    soportes o en las fechas del formulario, el periodo es un hecho del caso
    y borrarlo sería quitarle al dictamen algo cierto."""

    DICTAMEN = "ESE HUS NO ACEPTA LA GLOSA, EN EL PERIODO CORRESPONDIENTE AL AÑO 2023."

    def test_el_año_esta_en_los_soportes(self):
        out = _neutralizar_periodo_inventado(
            self.DICTAMEN,
            GLOSA_COMPENSAR,
            contexto_pdf="EPICRISIS — FECHA DE EGRESO 14/07/2023",
        )
        assert out == self.DICTAMEN

    def test_el_año_esta_en_la_fecha_de_radicacion(self):
        out = _neutralizar_periodo_inventado(
            self.DICTAMEN, GLOSA_COMPENSAR, fechas_expediente="2023-11-30"
        )
        assert out == self.DICTAMEN

    def test_sin_ninguna_fuente_se_sigue_quitando(self):
        out = _neutralizar_periodo_inventado(
            self.DICTAMEN,
            GLOSA_COMPENSAR,
            contexto_pdf="EPICRISIS SIN FECHAS",
            fechas_expediente="",
        )
        assert "2023" not in out

    def test_un_año_distinto_en_los_soportes_no_sirve_de_coartada(self):
        out = _neutralizar_periodo_inventado(
            self.DICTAMEN, GLOSA_COMPENSAR, contexto_pdf="EPICRISIS — EGRESO 14/07/2025"
        )
        assert "2023" not in out

    def test_el_dictamen_recibe_las_tres_fuentes(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("_neutralizar_periodo_inventado(")
        bloque = src[i : i + 700]
        assert "contexto_pdf=contexto_pdf" in bloque
        assert "fecha_radicacion" in bloque and "fecha_recepcion" in bloque
