"""Regresión del leak de API keys en logs (visto en producción 10-jun-2026).

El logger INFO de httpx escribe la URL completa de cada request. La key de
Gemini viajaba como query param (?key=AIza...) tanto en gemini_service como
en el ping de /admin/diagnostico → la key quedaba en texto plano en los
logs de Fly.

Dos defensas:
  1. Los call sites usan el header x-goog-api-key (la URL no lleva key).
  2. El StructuredFormatter redacta cualquier patrón key=/token=/password=
     que se cuele en un mensaje de log (defensa en profundidad).
"""

from __future__ import annotations

import json
import logging

from app.core.logging_utils import StructuredFormatter, _redactar_secretos


def _formatear(msg: str) -> dict:
    rec = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    return json.loads(StructuredFormatter().format(rec))


class TestRedaccionSecretos:
    def test_key_de_gemini_en_url_se_redacta(self):
        # El caso real visto en los logs de Fly
        msg = (
            "HTTP Request: POST https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-2.0-flash:generateContent"
            '?key=AIzaSyAZm7Hiq9TlDFAKEFAKEFAKE "HTTP/1.1 429"'
        )
        out = _formatear(msg)["message"]
        assert "AIzaSyAZm7Hiq9TlDFAKEFAKEFAKE" not in out
        assert "***REDACTADO***" in out
        # Los primeros 4 chars se conservan para correlacionar
        assert "key=AIza***REDACTADO***" in out

    def test_token_y_password_tambien_se_redactan(self):
        out = _formatear("login con password=SuperSecreta123 y token=eyJhbGciOiJIUzI1")
        assert "SuperSecreta123" not in out["message"]
        assert "eyJhbGciOiJIUzI1" not in out["message"]

    def test_mensajes_normales_intactos(self):
        msg = "Análisis solicitado por: auditor@hus.gov.co | eps=FAMISANAR | tono=conciliador"
        assert _formatear(msg)["message"] == msg

    def test_prefijos_cortos_no_se_tocan(self):
        # key=ok (3 chars) no parece un secreto — el patrón exige >=6
        msg = "estado key=ok listo"
        assert _redactar_secretos(msg) == msg


class TestGeminiKeyPorHeader:
    def test_url_de_gemini_service_sin_key(self):
        """La URL que construye GeminiService no debe contener la key."""
        import inspect

        from app.services import gemini_service

        src = inspect.getsource(gemini_service)
        # Ninguna interpolación de la key dentro de una URL
        assert "?key={" not in src and "?key=%s" not in src
        # El header correcto está presente
        assert "x-goog-api-key" in src

    def test_url_de_diagnostico_sin_key(self):
        import inspect

        from app.api.routers import diagnostico

        src = inspect.getsource(diagnostico)
        assert "?key={" not in src
        assert "x-goog-api-key" in src
