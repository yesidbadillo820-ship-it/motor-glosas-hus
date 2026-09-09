"""«…ENTRE LAS PARTES ENTRE LAS PARTES».

09-09-2026, visto por el auditor en un dictamen real del Dispensario
(factura HUS0000541440).

Cuando el contrato de una entidad ya venció, el motor no borra su mención
—nombrarlo es correcto y muchas veces necesario— sino que quita la
afirmación de que «sigue vigente». Para eso reemplaza frases como «EL
CONTRATO VIGENTE» por «EL CONTRATO QUE RIGIÓ LA RELACIÓN ENTRE LAS PARTES».

El problema es que el reemplazo **termina** en «entre las partes», y la
frase original muchas veces ya la traía:

    «EL CONTRATO VIGENTE ENTRE LAS PARTES ESTABLECE…»
          ↓
    «EL CONTRATO QUE RIGIÓ LA RELACIÓN ENTRE LAS PARTES ENTRE LAS PARTES…»

Sale en el documento que se radica. No cambia el fondo del argumento, pero
es de las cosas que le dicen al auditor de la entidad que nadie leyó el
escrito antes de mandarlo — y a partir de ahí lo lee con otra disposición.

QUÉ CUIDA ESTA PRUEBA. Que la coletilla salga una sola vez, en las cuatro
formas que el motor reemplaza, **y que el número del contrato siga
intacto**: borrarlo sería el error contrario, y ya se cometió una vez.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def contrato_vencido(monkeypatch):
    """El neutralizador solo actúa si la ficha dice que la vigencia terminó."""
    import app.services.glosa_ia_prompts as prompts

    monkeypatch.setattr(
        prompts, "get_contrato", lambda *a, **k: {"_vigencia_vencida": True}, raising=False
    )


def _limpiar(texto: str) -> str:
    from app.services.glosa_service import _no_afirmar_contrato_vencido

    return _no_afirmar_contrato_vencido(texto, eps="DMBUG")


class TestLaColetillaSaleUnaSolaVez:
    @pytest.mark.parametrize(
        "original",
        [
            "EL CONTRATO VIGENTE ENTRE LAS PARTES ESTABLECE LA TARIFA.",
            "EL CONTRATO SE ENCUENTRA VIGENTE ENTRE LAS PARTES.",
            "EL CONTRATO VIGENTE SUSCRITO ENTRE LAS PARTES DISPONE.",
            "EL CONTRATO 440-DIGSA/DMBUG-2025 PERMANECE VIGENTE ENTRE LAS PARTES.",
            "EL ACUERDO SE ENCUENTRA EN EJECUCIÓN ENTRE LAS PARTES.",
            "EL CONTRATO VIGENTE HASTA EL 30 DE JULIO ENTRE LAS PARTES.",
        ],
    )
    def test_no_se_duplica(self, original):
        resultado = _limpiar(original)
        veces = resultado.upper().count("ENTRE LAS PARTES")
        assert veces == 1, f"«entre las partes» sale {veces} veces:\n  {resultado}"

    def test_cuando_no_la_traia_igual_se_agrega_una(self):
        """El reemplazo tiene que seguir sirviendo cuando la frase original
        no traía la coletilla."""
        r = _limpiar("EN EL CONTRATO VIGENTE SE PACTÓ SOAT MENOS 15%.")
        assert r.upper().count("ENTRE LAS PARTES") == 1
        assert "RIGIÓ LA RELACIÓN" in r


class TestElNumeroDelContratoNoSeToca:
    """Ya se cometió el error contrario una vez: la primera versión de estos
    patrones se comía «440-DIGSA/DMBUG-2025» al pasar por delante. Nombrar el
    contrato es correcto; lo que sobra es el «sigue vigente»."""

    @pytest.mark.parametrize(
        "original,numero",
        [
            (
                "EL CONTRATO 440-DIGSA/DMBUG-2025 PERMANECE VIGENTE ENTRE LAS PARTES.",
                "440-DIGSA/DMBUG-2025",
            ),
            ("EL CONTRATO VIGENTE ENTRE LAS PARTES ES EL S-13-1-03-1-04958.", "S-13-1-03-1-04958"),
        ],
    )
    def test_sigue_ahi(self, original, numero):
        assert numero in _limpiar(original)


class TestConElContratoVigenteNoSeToca:
    """El neutralizador solo entra cuando la vigencia terminó. Con un contrato
    vivo, decir que está vigente es la verdad."""

    def test_no_cambia_nada(self, monkeypatch):
        import app.services.glosa_ia_prompts as prompts

        monkeypatch.setattr(
            prompts, "get_contrato", lambda *a, **k: {"_vigencia_vencida": False}, raising=False
        )
        original = "EL CONTRATO VIGENTE ENTRE LAS PARTES ESTABLECE LA TARIFA."
        assert _limpiar(original) == original
