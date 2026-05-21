"""Regresión: la auto-crítica del dictamen debe re-aplicar TODOS los sanitizers.

Bug reportado por Yesid (21 mayo 2026): dictámenes con score < 70 activan
auto-crítica → la IA regenera el texto y vuelve a meter la coda procesal
('La entidad cuenta con 10 días hábiles', 'mesa de conciliación', emails).
Sin re-aplicar los sanitizers post-refinamiento, el guard-rail queda anulado.

Estos tests no ejecutan auto-crítica end-to-end (eso requiere IA real);
verifican que el comportamiento de los sanitizers es IDEMPOTENTE cuando
se aplican múltiples veces sobre texto con coda.
"""

from __future__ import annotations

from app.services.dictamen_postprocesor import truncar_despues_de_levantamiento
from app.services.glosa_service import (
    _suavizar_tono,
    limpiar_cierre_extemporanea_indebido,
    limpiar_palabra_injustificado,
)


TEXTO_REFINADO_TIPICO = (
    "EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO DE LA "
    "GLOSA TA0201 Y EL RECONOCIMIENTO INTEGRO DEL PROCEDIMIENTO FACTURADO. "
    "SE INVITA A FAMISANAR EPS A PARTICIPAR EN UNA MESA DE CONCILIACIÓN PARA "
    "RESOLVER LAS DIFERENCIAS Y LLEGAR A UN ACUERDO MUTUAMENTE BENEFICIOSO. "
    "LA ENTIDAD CUENTA CON 10 DÍAS HÁBILES (ART. 57 LEY 1438/2011) PARA "
    "RESPONDER A ESTA SOLICITUD. LAS COMUNICACIONES DEBERÁN DIRIGIRSE A "
    "CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
)


def _pipeline_completo(texto: str, codigo_respuesta: str = "RE9901") -> str:
    """Replica el pipeline post-IA del flujo principal en glosa_service:2360-2372
    y el bloque nuevo de auto-crítica en 2432-2451."""
    texto = _suavizar_tono(texto)
    texto = limpiar_palabra_injustificado(texto, codigo_respuesta=codigo_respuesta)
    texto = limpiar_cierre_extemporanea_indebido(texto, codigo_respuesta=codigo_respuesta)
    texto = truncar_despues_de_levantamiento(texto)
    return texto


class TestPipelineCompleto:
    def test_quita_se_invita_a_mesa(self):
        out = _pipeline_completo(TEXTO_REFINADO_TIPICO)
        assert "se invita" not in out.lower()
        assert "mesa de conciliaci" not in out.lower()

    def test_quita_la_entidad_cuenta_con_10(self):
        out = _pipeline_completo(TEXTO_REFINADO_TIPICO)
        assert "10 días" not in out.lower()
        assert "10 dias" not in out.lower()

    def test_quita_emails(self):
        out = _pipeline_completo(TEXTO_REFINADO_TIPICO)
        assert "@hus.gov.co" not in out.lower()

    def test_preserva_cierre_canonico(self):
        out = _pipeline_completo(TEXTO_REFINADO_TIPICO)
        assert "levantamiento" in out.lower()
        assert "se solicita" in out.lower()

    def test_idempotente_doble_pasada(self):
        """Aplicar el pipeline 2 veces produce el mismo resultado.
        Esto valida que la auto-crítica puede re-correrlo sin daño."""
        primera = _pipeline_completo(TEXTO_REFINADO_TIPICO)
        segunda = _pipeline_completo(primera)
        assert primera == segunda
