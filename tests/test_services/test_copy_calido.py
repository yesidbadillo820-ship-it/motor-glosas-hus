"""Capa de Vida (ronda 32): copys cálidos — funciones puras y deterministas."""

from __future__ import annotations

from app.services import copy_calido


class TestSaludoPorHora:
    def test_manana(self):
        assert copy_calido.saludo_por_hora(8) == "Buenos días"

    def test_tarde(self):
        assert copy_calido.saludo_por_hora(15) == "Buenas tardes"

    def test_noche(self):
        assert copy_calido.saludo_por_hora(21) == "Buenas noches"

    def test_madrugada(self):
        assert copy_calido.saludo_por_hora(3) == "Trabajando temprano"


class TestFraseAnimo:
    def test_deterministic_por_indice(self):
        assert copy_calido.frase_animo(0) == copy_calido.frase_animo(0)

    def test_rota_y_no_desborda(self):
        # cualquier índice grande sigue devolviendo una frase válida
        assert copy_calido.frase_animo(999) in copy_calido._FRASES_ANIMO


class TestCelebraciones:
    def test_levantada_gran_valor_muestra_monto(self):
        msg = copy_calido.celebrar_levantada("COMPENSAR", 6_400_000)
        assert "COMPENSAR" in msg and "6,400,000" in msg

    def test_levantada_valor_bajo_sin_monto(self):
        msg = copy_calido.celebrar_levantada("FAMISANAR", 50_000)
        assert "FAMISANAR" in msg

    def test_racha_umbral(self):
        assert copy_calido.celebrar_racha(2) is None
        assert "3" in (copy_calido.celebrar_racha(3) or "")
        assert copy_calido.celebrar_racha(20) is not None

    def test_hito_recuperado(self):
        assert copy_calido.celebrar_hito_recuperado(5_000_000) is None
        assert copy_calido.celebrar_hito_recuperado(120_000_000) is not None
