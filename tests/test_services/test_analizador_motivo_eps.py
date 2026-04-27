"""Tests del analizador del motivo EPS (R-cerebro #6)."""
from __future__ import annotations

from app.services.analizador_motivo_eps import (
    bloque_puntos_a_refutar,
    construir_bloque_motivo_eps,
    extraer_puntos_eps,
)


class TestExtraerPuntos:
    def test_texto_vacio(self):
        d = extraer_puntos_eps("")
        assert d["motivo_principal"] is None
        assert d["soportes_faltantes"] == []
        assert d["exige_devolucion"] is False

    def test_valor_reconocido(self):
        t = "SE RECONOCE LA TARIFA POR VALOR DE $45.411."
        d = extraer_puntos_eps(t)
        assert d["valor_reconocido"] == "$45.411"

    def test_descuento_soat(self):
        t = "APLICA DESCUENTO SOAT -20%"
        d = extraer_puntos_eps(t)
        assert "20%" in d["descuento_aplicado"]

    def test_cups_alternativo(self):
        t = "SE RECONOCE TARIFA SOAT UVB CODIGO 39143"
        d = extraer_puntos_eps(t)
        assert d["cups_alternativo"] == "39143"

    def test_soportes_faltantes(self):
        t = "FALTA HISTORIA CLINICA Y NO SE ANEXÓ AUTORIZACION"
        d = extraer_puntos_eps(t)
        assert any(
            "HISTORIA" in s for s in d["soportes_faltantes"]
        )
        assert any(
            "AUTORIZ" in s for s in d["soportes_faltantes"]
        )

    def test_devolucion(self):
        t = "SE EXIGE LA DEVOLUCION DEL VALOR PAGADO"
        d = extraer_puntos_eps(t)
        assert d["exige_devolucion"] is True

    def test_normas_eps(self):
        t = "DE CONFORMIDAD CON LA RESOLUCION 2284 DE 2023 Y LEY 1438"
        d = extraer_puntos_eps(t)
        assert any("2284" in n for n in d["normas_citadas_eps"])
        assert any("1438" in n for n in d["normas_citadas_eps"])

    def test_pertinencia(self):
        t = "NO ES PERTINENTE EL SERVICIO FACTURADO"
        d = extraer_puntos_eps(t)
        assert d["cuestiona_pertinencia"] is True


class TestBloque:
    def test_sin_puntos_devuelve_vacio(self):
        d = extraer_puntos_eps("")
        assert bloque_puntos_a_refutar(d) == ""

    def test_con_valor_genera_bloque(self):
        d = extraer_puntos_eps(
            "SE RECONOCE $50.000 POR EL SERVICIO FACTURADO"
        )
        b = bloque_puntos_a_refutar(d)
        assert "PUNTOS DE LA EPS A REFUTAR" in b
        assert "$50.000" in b

    def test_descuento_invoca_normas(self):
        d = extraer_puntos_eps(
            "APLICA DESCUENTO SOAT -20% SOBRE LA TARIFA"
        )
        b = bloque_puntos_a_refutar(d)
        assert "Art. 871" in b or "871" in b
        assert "1602" in b


class TestIntegrado:
    def test_un_paso(self):
        b = construir_bloque_motivo_eps(
            "FALTA HISTORIA CLINICA. SE RECONOCE $30.000."
        )
        assert "PUNTOS DE LA EPS" in b
        assert "$30.000" in b
