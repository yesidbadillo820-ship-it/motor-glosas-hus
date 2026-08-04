"""El .env también tiene que llegar al ENTORNO del proceso.

Incidente 04-08-2026: pydantic-settings lee el archivo .env hacia la
configuración, pero NO lo exporta a os.environ. El motor de dictámenes
recibe las claves por inyección y funcionaba, pero el asistente maestro,
el auditor forense, el extractor de cláusulas, los multi-agentes y el
diagnóstico de arranque leen os.getenv — y con un .env perfectamente
válido veían todo AUSENTE. El log llegó a reportar «groq=AUSENTE»
teniendo la clave cargada, y eso mandó la búsqueda por el camino errado.
"""

from __future__ import annotations

import os

from app.core.config import _CLAVES_AL_ENTORNO, Settings, _exportar_claves_al_entorno


class TestPuenteAlEntorno:
    def test_exporta_lo_que_vino_del_archivo(self, monkeypatch):
        for nombre, _ in _CLAVES_AL_ENTORNO:
            monkeypatch.delenv(nombre, raising=False)

        s = Settings(groq_api_key="clave_del_archivo", anthropic_api_key="ant_del_archivo")
        _exportar_claves_al_entorno(s)

        assert os.getenv("GROQ_API_KEY") == "clave_del_archivo"
        assert os.getenv("ANTHROPIC_API_KEY") == "ant_del_archivo"

    def test_no_pisa_lo_que_ya_venia_del_entorno_real(self, monkeypatch):
        """Docker/systemd mandan sobre el archivo: si la variable ya existe
        en el entorno, el .env no la sobreescribe."""
        monkeypatch.setenv("GROQ_API_KEY", "la_del_contenedor")

        s = Settings(groq_api_key="la_del_archivo")
        _exportar_claves_al_entorno(s)

        assert os.getenv("GROQ_API_KEY") == "la_del_contenedor"

    def test_sin_valor_no_inventa_variable(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        _exportar_claves_al_entorno(Settings(gemini_api_key=""))

        assert os.getenv("GEMINI_API_KEY") is None

    def test_cubre_las_claves_que_el_sistema_lee_del_entorno(self):
        """Si mañana alguien agrega otro os.getenv de clave, esta lista
        es donde se registra."""
        nombres = {n for n, _ in _CLAVES_AL_ENTORNO}
        assert {"GROQ_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"} <= nombres
