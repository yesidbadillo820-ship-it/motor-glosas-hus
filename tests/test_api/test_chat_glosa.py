"""Tests del chat conversacional de glosa (Ronda 8)."""
from types import SimpleNamespace

from app.api.routers.chat_glosa import (
    _es_modificacion,
    _respuesta_rapida,
)


class TestEsModificacion:
    def test_hazlo_mas_corto(self):
        assert _es_modificacion("Hazlo más corto")

    def test_agrega_cita(self):
        assert _es_modificacion("Agrega cita a la Sentencia T-760")

    def test_cambia_tono(self):
        assert _es_modificacion("Cambia el tono a firme")

    def test_reescribe(self):
        assert _es_modificacion("reescribe el segundo párrafo")

    def test_pregunta_no_es_modificacion(self):
        assert not _es_modificacion("¿Por qué citas el Art. 871?")

    def test_que_significa(self):
        assert not _es_modificacion("Qué significa silencio administrativo")


class TestRespuestaRapida:
    def _glosa_fake(self):
        return SimpleNamespace(
            id=1, codigo_glosa="TA0201", eps="FAMISANAR EPS",
            dictamen="<p>...</p>"
        )

    def test_por_que_871(self):
        r = _respuesta_rapida("¿Por qué citas el Art. 871?", self._glosa_fake())
        assert "buena fe" in r.lower()

    def test_por_que_1602(self):
        r = _respuesta_rapida("¿Por qué el 1602 del civil?", self._glosa_fake())
        assert "contrato legalmente celebrado" in r.lower() or "1602" in r

    def test_plazo(self):
        r = _respuesta_rapida("¿Cuál es el plazo?", self._glosa_fake())
        assert "30 días" in r or "15 días" in r or "plazo" in r.lower()

    def test_uvb(self):
        r = _respuesta_rapida("Qué es la UVB", self._glosa_fake())
        assert "12.110" in r or "12110" in r

    def test_pregunta_no_conocida_devuelve_vacio(self):
        r = _respuesta_rapida("¿Cómo cocinar pasta?", self._glosa_fake())
        assert r == ""

    def test_silencio_administrativo(self):
        r = _respuesta_rapida("qué es el silencio favorable", self._glosa_fake())
        assert "silencio" in r.lower() or "57" in r


class TestRagNormativaIntegration:
    """El chat debería poder conectar con rag_normativa en respuestas futuras."""

    def test_rag_normativa_modulo_existe(self):
        """Sanity: garantizar que el módulo está disponible para el chat."""
        from app.services import rag_normativa
        assert callable(getattr(rag_normativa, "buscar_normas", None))
