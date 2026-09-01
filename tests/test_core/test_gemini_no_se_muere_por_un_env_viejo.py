"""Un .env viejo en un PC no puede dejar una herramienta muerta — 19-08-2026.

El Auditor Forense tiene cadena de respaldo: Anthropic → Gemini PDF → Gemini
Vision. En el PC de cartera los tres estaban caídos a la vez:

  · **Anthropic**, porque la red del hospital corta la salida hacia
    api.anthropic.com («WinError 10054» en el Diagnóstico);
  · **Gemini**, porque el `.env` de esa máquina traía
    `GEMINI_MODEL=gemini-2.0-flash`, que Google retiró («404 — is no longer
    available»).

O sea que la herramienta no tenía por dónde. Y lo peor: **falla en silencio**.
El OCR de los PDF escaneados simplemente deja de leer, sin error visible.

Corregir el `.env` a mano en cada máquina no es una solución. Esta sí: el
motor ignora los modelos retirados aunque la configuración los mande, usa el
alias que el proveedor mantiene vivo, y lo deja anotado en el registro para
que se vea por qué no obedeció.
"""

from __future__ import annotations

import pytest

from app.core.config import (
    GEMINI_VIVO,
    MODELOS_GEMINI_RETIRADOS,
    modelo_gemini_vigente,
)


class TestIgnoraLosModelosMuertos:
    @pytest.mark.parametrize("muerto", sorted(MODELOS_GEMINI_RETIRADOS))
    def test_ninguno_se_le_pasa(self, muerto):
        assert modelo_gemini_vigente(muerto) == GEMINI_VIVO

    def test_el_del_pc_de_cartera(self):
        """El caso exacto: `GEMINI_MODEL=gemini-2.0-flash` en el .env."""
        assert modelo_gemini_vigente("gemini-2.0-flash") == GEMINI_VIVO

    def test_lo_deja_anotado_para_que_se_sepa(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="motor_glosas"):
            modelo_gemini_vigente("gemini-2.0-flash")
        texto = caplog.text
        assert "retiró" in texto
        assert "GEMINI_MODEL" in texto, "no dice qué línea corregir"


class TestRespetaLoQueSiSirve:
    def test_un_modelo_vivo_se_usa_tal_cual(self):
        """No es una lista blanca: solo se descartan los que se sabe muertos."""
        assert modelo_gemini_vigente("gemini-3.5-flash") == "gemini-3.5-flash"

    def test_sin_configuracion_usa_el_alias_vivo(self):
        assert modelo_gemini_vigente("") == GEMINI_VIVO

    def test_el_alias_no_puede_estar_en_la_lista_de_muertos(self):
        """Si alguien lo agrega por error, el decisor se muerde la cola."""
        assert GEMINI_VIVO not in MODELOS_GEMINI_RETIRADOS


class TestNadieSeSaltaAlDecisor:
    """Cinco archivos tenían el nombre del modelo escrito a mano. Cada copia es
    otro sitio donde el sistema puede quedarse con un modelo muerto."""

    ARCHIVOS = (
        "app/services/auditor_forense.py",
        "app/services/gemini_service.py",
        "app/services/pdf_service.py",
        "app/services/pdf_fallback_patch.py",
    )

    @pytest.mark.parametrize("ruta", ARCHIVOS)
    def test_no_escriben_un_modelo_muerto_como_valor(self, ruta):
        import ast
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        arbol = ast.parse((raiz / ruta).read_text(encoding="utf-8"))
        textos = {
            n.value
            for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        malos = textos & MODELOS_GEMINI_RETIRADOS
        assert not malos, f"{ruta} usa como valor un modelo retirado: {malos}"

    def test_el_forense_pasa_por_el_decisor(self):
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        fuente = (raiz / "app" / "services" / "auditor_forense.py").read_text(encoding="utf-8")
        assert "modelo_gemini_vigente" in fuente
