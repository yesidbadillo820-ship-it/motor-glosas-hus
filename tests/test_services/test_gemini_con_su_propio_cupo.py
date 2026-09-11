"""Gemini: dos cupos en vez de uno, y no insistir contra un 429.

10-09-2026. El primer día que Gemini entró a redactar dictámenes se quedó sin
cuota a media tarde — y no por los dictámenes. La MISMA llave la gasta el
motor para leer PDFs escaneados, que consume mucho más. Las dos tareas se
comían el mismo cupo gratis del día, y la que perdía era la que el auditor
estaba mirando.

Dos arreglos, los dos sin obligar al hospital a decidir nada hoy:

1. `GEMINI_API_KEY_DICTAMEN` — si se pone una segunda llave gratis, los
   dictámenes van por ella y el OCR se queda con la primera. Si se deja
   vacía, todo sigue exactamente igual que antes.

2. Un 429 del tier gratis no es un tropiezo del que se salga esperando dos
   segundos: es el cupo agotado. Antes se reintentaba igual, gastando siete
   segundos del auditor y otras dos peticiones contra un cupo que ya no
   existe. Ahora se sale de una y la cadena prueba el siguiente proveedor.
"""

import asyncio

import pytest

from app.services.glosa_service import GlosaService, _es_falta_de_cuota


class _ClienteFalso:
    def __init__(self, excepcion=None, texto="DICTAMEN"):
        self.excepcion = excepcion
        self.texto = texto
        self.llamadas = 0

    async def completar(self, **_kw):
        self.llamadas += 1
        if self.excepcion:
            raise self.excepcion
        return self.texto, "gemini-flash-latest"


def _servicio(cliente, dictamen=None) -> GlosaService:
    s = GlosaService.__new__(GlosaService)
    s.gemini = cliente
    s.gemini_dictamen = dictamen if dictamen is not None else cliente
    s.gemini_model = "gemini-flash-latest"
    s.gemini_model_dictamen = "gemini-flash-latest"
    return s


class TestReconocerLaFaltaDeCupo:
    @pytest.mark.parametrize(
        "mensaje",
        [
            "429 Too Many Requests",
            "RESOURCE_EXHAUSTED: quota exceeded",
            "You exceeded your current quota",
            "rate limit reached for model",
            "Rate_Limit_Exceeded",
        ],
    )
    def test_los_mensajes_del_proveedor(self, mensaje):
        assert _es_falta_de_cuota(RuntimeError(mensaje))

    def test_el_codigo_http_de_la_respuesta(self):
        class _Resp:
            status_code = 429

        e = RuntimeError("algo")
        e.response = _Resp()
        assert _es_falta_de_cuota(e)

    @pytest.mark.parametrize(
        "mensaje",
        [
            "Connection reset by peer",
            "500 Internal Server Error",
            "model not found",
            "timeout",
        ],
    )
    def test_lo_que_no_es_falta_de_cupo(self, mensaje):
        assert not _es_falta_de_cuota(RuntimeError(mensaje))


class TestNoInsistirContraUn429:
    def test_una_sola_llamada_y_se_pasa_al_siguiente(self):
        cliente = _ClienteFalso(RuntimeError("429 quota exceeded"))
        s = _servicio(cliente)
        with pytest.raises(RuntimeError):
            asyncio.run(s._llamar_gemini_con_retry("sys", "user"))
        assert cliente.llamadas == 1, "insistir contra un cupo agotado no recupera nada"

    def test_un_fallo_normal_si_se_reintenta(self, monkeypatch):
        """Un timeout o una conexión caída sí se recuperan esperando."""
        dormir_de_verdad = asyncio.sleep

        async def _sin_esperar(_segundos):
            await dormir_de_verdad(0)

        monkeypatch.setattr(asyncio, "sleep", _sin_esperar)
        cliente = _ClienteFalso(RuntimeError("Connection reset by peer"))
        s = _servicio(cliente)
        with pytest.raises(RuntimeError):
            asyncio.run(s._llamar_gemini_con_retry("sys", "user", max_intentos=3))
        assert cliente.llamadas == 3


class TestLaLlaveApartePuedeSerLaMisma:
    def test_sin_segunda_llave_usa_el_de_siempre(self):
        cliente = _ClienteFalso()
        s = _servicio(cliente)
        texto, modelo = asyncio.run(s._llamar_gemini_con_retry("sys", "user"))
        assert texto == "DICTAMEN"
        assert modelo.startswith("gemini/")
        assert cliente.llamadas == 1

    def test_con_segunda_llave_el_dictamen_va_por_ella(self):
        ocr = _ClienteFalso(texto="NO DEBERÍA USARSE")
        dictamenes = _ClienteFalso(texto="DICTAMEN BUENO")
        s = _servicio(ocr, dictamen=dictamenes)
        texto, _ = asyncio.run(s._llamar_gemini_con_retry("sys", "user"))
        assert texto == "DICTAMEN BUENO"
        assert ocr.llamadas == 0, "el cupo del OCR no se toca para redactar"
        assert dictamenes.llamadas == 1

    def test_sin_ningun_cliente_avisa_claro(self):
        s = _servicio(None, dictamen=None)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            asyncio.run(s._llamar_gemini_con_retry("sys", "user"))

    def test_un_servicio_viejo_sin_el_atributo_no_se_cae(self):
        """Construido con __new__ y sin `gemini_dictamen`, como en pruebas viejas."""
        s = GlosaService.__new__(GlosaService)
        s.gemini = _ClienteFalso()
        s.gemini_model = "gemini-flash-latest"
        s.gemini_model_dictamen = ""
        texto, _ = asyncio.run(s._llamar_gemini_con_retry("sys", "user"))
        assert texto == "DICTAMEN"


class TestLaConfiguracion:
    def test_la_llave_aparte_esta_declarada_y_vacia_por_defecto(self):
        from app.core.config import Settings

        assert "gemini_api_key_dictamen" in Settings.model_fields
        assert Settings.model_fields["gemini_api_key_dictamen"].default == ""

    def test_se_lee_del_env(self):
        from pathlib import Path

        fuente = Path("app/core/config.py").read_text(encoding="utf-8")
        assert '("GEMINI_API_KEY_DICTAMEN", "gemini_api_key_dictamen")' in fuente

    def test_el_modelo_de_ocr_y_el_de_dictamen_siguen_separados(self):
        from app.core.config import Settings

        assert "gemini_model" in Settings.model_fields
        assert "gemini_model_dictamen" in Settings.model_fields
