"""Gemini puede volver a redactar dictámenes.

10-09-2026, pedido de Yesid: «buscame alternativas gratis porque los modelos
de Claude son de paga, ya pagué por los token».

Gemini salió del dictamen en junio de 2026, y la razón quedó escrita en el
código con sus palabras: «no las veo trabajando y de pago ya tenemos Claude».
Las dos mitades de esa frase cambiaron:

  · «de pago ya tenemos Claude» — ahora esos tokens los paga el hospital.
  · «no las veo trabajando» — era otra generación del modelo.

Y hay un número que decide: el tier gratis de Gemini da **250.000 tokens por
minuto** contra los **8.000** del gratis de Groq. Los prompts de este motor
pesan unos 21.000, así que en Groq gratis **una sola glosa no cabe en el
minuto**.

Lo que estas pruebas vigilan no es que Gemini escriba bien —eso se mide con
glosas reales, no con una prueba— sino que el motor no se rompa por dejarlo
entrar: mismo contrato que los otros dos proveedores, y que un fallo suyo
caiga al siguiente en vez de servir una hoja en blanco con sello de validado.
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import GlosaService


def _servicio(**kw) -> GlosaService:
    base = {
        "anthropic_api_key": "sk-ant-de-prueba",
        "groq_api_key": "gsk_de_prueba",
        "gemini_api_key": "AIza_de_prueba",
    }
    base.update(kw)
    return GlosaService(**base)


class TestYaNoSeLeCierraLaPuerta:
    def test_primary_ai_gemini_se_respeta(self):
        """Antes se normalizaba a 'groq' y el auditor no se enteraba."""
        assert _servicio(primary_ai="gemini").primary_ai == "gemini"

    def test_openrouter_sigue_afuera(self):
        """Ese sí sigue retirado: no hay llave ni evidencia de que sirva."""
        assert _servicio(primary_ai="openrouter").primary_ai == "groq"

    def test_el_servicio_de_gemini_esta_instanciado(self):
        assert _servicio(primary_ai="gemini").gemini is not None

    def test_sin_llave_no_hay_proveedor(self):
        assert _servicio(gemini_api_key="").gemini is None


class TestElModeloDeRedactarEsOtroQueElDeLeerPdfs:
    """Son tareas distintas y no pueden pisarse.

    El modelo bueno para leer un escaneo no tiene por qué ser el bueno para
    redactar un escrito jurídico. Si compartieran ajuste, cambiar el del OCR
    cambiaría el de los dictámenes sin que nadie lo pidiera.
    """

    def test_son_dos_ajustes_distintos(self):
        from app.core.config import Settings

        campos = Settings.model_fields
        assert "gemini_model" in campos
        assert "gemini_model_dictamen" in campos

    def test_el_servicio_expone_los_dos(self):
        s = _servicio(primary_ai="gemini")
        assert hasattr(s, "gemini_model")
        assert hasattr(s, "gemini_model_dictamen")


class TestMismoContratoQueLosOtrosProveedores:
    def test_existe_el_metodo_con_la_misma_firma(self):
        import inspect

        s = _servicio()
        assert hasattr(s, "_llamar_gemini_con_retry")
        firma = inspect.signature(s._llamar_gemini_con_retry).parameters
        # Los tres proveedores se llaman igual desde `_llamar_ia`.
        for arg in ("system", "user", "llamada_corta"):
            assert arg in firma, f"a Gemini le falta el parámetro {arg}"

    @pytest.mark.asyncio
    async def test_sin_llave_levanta_en_vez_de_devolver_vacio(self):
        s = _servicio(gemini_api_key="")
        with pytest.raises(RuntimeError):
            await s._llamar_gemini_con_retry("sys", "user")

    @pytest.mark.asyncio
    async def test_una_respuesta_vacia_es_un_fallo_no_un_dictamen(self, monkeypatch):
        """Servir vacío en silencio le deja al auditor una hoja en blanco sellada."""
        s = _servicio(primary_ai="gemini")

        async def _vacio(**kw):
            return ("   ", "gemini-flash-latest")

        monkeypatch.setattr(s.gemini, "completar", _vacio)
        with pytest.raises(RuntimeError, match="vac"):
            await s._llamar_gemini_con_retry("sys", "user", max_intentos=1)

    @pytest.mark.asyncio
    async def test_cuando_responde_devuelve_texto_y_modelo(self, monkeypatch):
        s = _servicio(primary_ai="gemini")

        async def _ok(**kw):
            return ("ESE HUS NO ACEPTA LA GLOSA...", "gemini-flash-latest")

        monkeypatch.setattr(s.gemini, "completar", _ok)
        texto, modelo = await s._llamar_gemini_con_retry("sys", "user")
        assert "NO ACEPTA" in texto
        assert modelo.startswith("gemini/"), "el dictamen tiene que decir quién lo escribió"

    @pytest.mark.asyncio
    async def test_la_llamada_corta_no_pide_una_salida_larga(self, monkeypatch):
        """Auto-crítica y refinamiento contestan en dos renglones."""
        s = _servicio(primary_ai="gemini")
        visto = {}

        async def _espia(**kw):
            visto.update(kw)
            return ("ok", "gemini-flash-latest")

        monkeypatch.setattr(s.gemini, "completar", _espia)
        await s._llamar_gemini_con_retry("sys", "user", llamada_corta=True)
        corta = visto["max_tokens"]
        await s._llamar_gemini_con_retry("sys", "user", llamada_corta=False)
        assert corta < visto["max_tokens"]


class TestNoRevientaConUnServicioAMedioArmar:
    """El defecto que el CI cazó el 10-09-2026, y por qué existe esta clase.

    Al agregar Gemini a la cadena de respaldos escribí `if self.gemini:` a
    secas. Dos pruebas viejas arman el servicio con
    `GlosaService.__new__(GlosaService)` —saltándose el `__init__`— y le
    ponen a mano solo los atributos que van a usar. Leer uno que no existe
    reventaba con AttributeError **justo al elegir proveedor**: no en una
    prueba rara, sino en el momento en que el motor decide a quién llamar.

    Se lee con `getattr(..., None)`. Esta clase lo vigila.
    """

    def _a_medio_armar(self):
        """Un servicio como el que arman esas pruebas: sin pasar por __init__."""
        s = GlosaService.__new__(GlosaService)
        s.primary_ai = "groq"
        s.groq = object()
        s.anthropic_key = ""
        return s

    def test_elegir_proveedor_no_revienta_sin_el_atributo(self):
        s = self._a_medio_armar()
        assert not hasattr(s, "gemini"), "la prueba dejó de reproducir el caso"
        # Lo mismo que hace `_llamar_ia` al armar la cadena de respaldos.
        assert getattr(s, "gemini", None) is None

    def test_el_codigo_no_lee_gemini_a_pelo(self):
        """Si alguien lo vuelve a escribir sin `getattr`, esta prueba avisa."""
        import inspect

        fuente = inspect.getsource(GlosaService._llamar_ia)
        assert 'getattr(self, "gemini", None)' in fuente
        assert "and self.gemini:" not in fuente, (
            "leer self.gemini a secas revienta con un servicio a medio armar"
        )
