"""El modelo primario de Groq tiene que existir en el catálogo del proveedor.

05-08-2026, panel de Diagnóstico del hospital:

    Groq → Error code: 404 - {'error': {'message': 'The model
    `meta-llama/llama-4-scout-17b-16e-instruct` does not exist or you do not
    have access to it.', 'code': 'model_not_found'}}

Groq retiró el modelo primario. El motor SEGUÍA funcionando —todos los
dictámenes de ese día salieron por gpt-oss-120b, el primer respaldo— pero
cada análisis gastaba un intento muerto antes de llegar ahí, y el panel
avisaba «✕ Ningún proveedor responde», que es lo que ve el auditor cuando
en realidad el sistema trabaja.

Se promovió el modelo que ya estaba haciendo el trabajo.
"""

from __future__ import annotations

from app.core.config import Settings

# Modelos retirados por Groq. Si alguno vuelve a aparecer como primario o
# respaldo, la suite lo dice antes de que el auditor lo descubra en un panel
# rojo.
MODELOS_RETIRADOS = (
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma-7b-it",
)


class TestLaCadenaDeGroq:
    def _cadena(self) -> list[str]:
        s = Settings(secret_key="x" * 40)
        return [
            s.groq_model,
            s.groq_model_fallback_1,
            s.groq_model_fallback_2,
            s.groq_model_fallback_3,
        ]

    def test_ningun_modelo_retirado_en_la_cadena(self):
        cadena = self._cadena()
        muertos = [m for m in cadena if m in MODELOS_RETIRADOS]
        assert not muertos, (
            f"Modelos retirados por Groq todavía en la cadena: {muertos}. "
            "El motor los intenta, pierde el turno y cae al respaldo."
        )

    def test_el_primario_es_el_que_venia_respondiendo(self):
        s = Settings(secret_key="x" * 40)
        assert s.groq_model == "openai/gpt-oss-120b"

    def test_la_cadena_no_repite_modelos(self):
        cadena = self._cadena()
        assert len(set(cadena)) == len(cadena), f"modelo repetido en la cadena: {cadena}"

    def test_hay_al_menos_tres_escalones(self):
        """Si el proveedor retira uno, tiene que quedar a quién llamar."""
        assert len([m for m in self._cadena() if m]) >= 3


class TestElPanelNoAsustaDeMas:
    """«✕ Ningún proveedor responde» cuando el motor sí trabaja es una
    falsa alarma que manda al auditor a buscar donde no es."""

    def _html(self) -> str:
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent.parent
        return (raiz / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")

    def test_distingue_el_modelo_retirado_de_la_caida_real(self):
        html = self._html()
        assert "esModeloRetirado" in html
        assert "salió del catálogo del proveedor" in html
        assert "sigue trabajando por el respaldo" in html

    def test_sigue_avisando_cuando_de_verdad_no_responde_nadie(self):
        html = self._html()
        assert "✕ Ningún proveedor responde" in html
