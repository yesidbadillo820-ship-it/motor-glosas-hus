"""Tests de regresión ronda 21 (30-jun-2026) — auditoría del dictamen
MEDIMÁS da Vinci $273M en producción.

Caso real: la glosa cita textualmente el contrato CTR-2024-MEDIMAS-HUS
con tarifa SOAT × 0.85, pero el dictamen producido decía DOS veces "al no
existir contrato pactado" — auto-contradicción legal-killer: el campo
"Contrato:" quedó corregido pero el cuerpo negaba el contrato citado por
la EPS.

Bug #1 — _reescribir_negacion_contrato no cubría la forma verbal
"(al) no existir contrato pactado" (solo "SIN/NO EXISTE CONTRATO
PACTADO"). El infinitivo/conjugado se escapaba.
"""

from __future__ import annotations

from app.services.glosa_service import _reescribir_negacion_contrato

_GLOSA_MEDIMAS = (
    "(III) TARIFA: el contrato vigente CTR-2024-MEDIMAS-HUS define para "
    "prostatectomía CUPS 60.1.2.01 una tarifa de SOAT × 0.85."
)


class TestBug1NegacionContratoInfinitivo:
    def test_al_no_existir_contrato_pactado_se_reescribe(self):
        """La frase real del dictamen MEDIMÁS (1ª ocurrencia)."""
        d = (
            "facturado bajo tarifa SOAT pleno conforme al manual tarifario "
            "SOAT 2026 vigente, al no existir contrato pactado con la entidad."
        )
        out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
        assert "al no existir contrato pactado" not in out.lower()
        assert "CTR-2024-MEDIMAS-HUS" in out

    def test_al_no_existir_contrato_pactado_segunda_ocurrencia(self):
        """2ª ocurrencia: la que funda toda la defensa tarifaria."""
        d = (
            "En tercer lugar, al no existir contrato pactado rige el manual "
            "tarifario SOAT 2026 en su integridad conforme al art. 177."
        )
        out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
        assert "al no existir contrato pactado" not in out.lower()
        assert "CTR-2024-MEDIMAS-HUS" in out

    def test_variantes_verbales(self):
        """Cubre existe/existen/existir/existía/existiendo + prefijo."""
        for frase in (
            "no existe contrato pactado",
            "al no existir contrato pactado",
            "de no existir contrato pactado",
            "no existía contrato pactado",
            "no existen contrato",
        ):
            d = f"El servicio se facturó porque {frase} con la entidad."
            out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
            assert "CTR-2024-MEDIMAS-HUS" in out, f"no reescribió: {frase!r}"

    def test_no_sobrecaptura_afirmaciones(self):
        """Frases AFIRMATIVAS sobre el contrato NO deben tocarse."""
        afirm = (
            "El contrato pactado define la tarifa; existe contrato pactado "
            "vigente entre las partes, según el contrato CTR-2024-MEDIMAS-HUS."
        )
        out = _reescribir_negacion_contrato(afirm, texto_glosa=_GLOSA_MEDIMAS)
        assert out == afirm

    def test_glosa_sin_contrato_no_toca_nada(self):
        """Si la glosa NO cita contrato (aseguradora SOAT pura), el cuerpo
        queda intacto aunque diga 'no existir contrato pactado'."""
        d = "Se facturó SOAT pleno al no existir contrato pactado con la aseguradora."
        out = _reescribir_negacion_contrato(d, texto_glosa="SOAT puro, sin contrato citado")
        assert out == d

    def test_sin_contrato_pactado_clasico_sigue_funcionando(self):
        """Regresión: la variante original 'SIN CONTRATO PACTADO' no se rompe."""
        d = "Contrato: SIN CONTRATO PACTADO. El servicio fue prestado."
        out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
        assert "SIN CONTRATO PACTADO" not in out
        assert "CTR-2024-MEDIMAS-HUS" in out
