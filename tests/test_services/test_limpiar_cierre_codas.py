"""Tests para limpiar_cierre_extemporanea_indebido.

Cubre las variantes que la IA real ha emitido — incluyendo el typo 'carttera'
y la variante 'LA ENTIDAD CUENTA CON 10 DÍAS' (sin 'PAGADORA').
"""

from __future__ import annotations

from app.services.glosa_service import limpiar_cierre_extemporanea_indebido


TEXTO_REAL_DICTAMEN = (
    "En este orden de ideas, se solicita respetuosamente el levantamiento de "
    "la glosa TA0201 y el reconocimiento íntegro del valor facturado. La entidad "
    "cuenta con 10 días hábiles, conforme al artículo 57 de la Ley 1438 de 2011, "
    "para dar respuesta a la presente solicitud. Se extiende una invitación a la "
    "mesa de conciliación para discutir y resolver cualquier diferencia o "
    "inquietud relacionada con la glosa aplicada. Las comunicaciones pueden ser "
    "dirigidas a los correos electrónicos carttera@hus.gov.co, "
    "glosasydevoluciones@hus.gov.co."
)


class TestLimpiezaRE9901:
    """RE9901 = defensa normal → debe limpiar TODA la coda procesal."""

    def test_quita_la_entidad_cuenta_con_10(self):
        out = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9901")
        assert "10 días" not in out.lower()
        assert "10 dias" not in out.lower()

    def test_quita_mesa_de_conciliacion(self):
        out = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9901")
        assert "conciliación" not in out.lower()
        assert "conciliacion" not in out.lower()

    def test_quita_typo_carttera(self):
        """El typo 'carttera' (2 t) lo invento Groq llama-3.3 — debe quitarse."""
        out = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9901")
        assert "carttera" not in out.lower()
        assert "@hus.gov.co" not in out.lower()

    def test_preserva_cierre_canonico(self):
        out = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9901")
        # El "SE SOLICITA EL LEVANTAMIENTO" debe quedar intacto
        assert "se solicita" in out.lower()
        assert "levantamiento" in out.lower()


class TestPreservaEnRatificadas:
    """RE9601/RE9602 (ratificada) y RE9501/RE9502 (extemporánea) DEBEN llevar la coda."""

    def test_re9601_conserva_coda(self):
        out = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9601")
        assert "10 días" in out.lower()

    def test_re9602_conserva_coda(self):
        out = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9602")
        assert "10 días" in out.lower()

    def test_re9501_extemporanea_conserva_coda(self):
        out = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9501")
        assert "10 días" in out.lower()

    def test_flag_es_ratificacion_conserva(self):
        out = limpiar_cierre_extemporanea_indebido(
            TEXTO_REAL_DICTAMEN, es_ratificacion=True, codigo_respuesta=""
        )
        assert "10 días" in out.lower()


class TestIdempotente:
    def test_aplicar_dos_veces_no_rompe(self):
        once = limpiar_cierre_extemporanea_indebido(TEXTO_REAL_DICTAMEN, codigo_respuesta="RE9901")
        twice = limpiar_cierre_extemporanea_indebido(once, codigo_respuesta="RE9901")
        assert once == twice
