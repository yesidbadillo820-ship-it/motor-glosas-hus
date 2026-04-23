"""Tests del catálogo oficial de tarifas HUS + SOAT 2026."""
from app.services.tarifas_oficiales import (
    TARIFAS_PROPIAS_HUS,
    TARIFAS_SOAT_2026,
    buscar_tarifa_propia_hus,
    buscar_tarifa_soat_2026,
    contexto_tarifa_oficial,
    tarifa_a_banner_dict,
)


class TestBuscarTarifaPropiaHUS:
    def test_electrofisiologico_caso_user(self):
        """CUPS 372301H — caso específico que el user pidió."""
        r = buscar_tarifa_propia_hus("372301H")
        assert r is not None
        assert r["valor_pesos_2026"] == 2_601_000
        assert r["factor_smdlv"] == 44.56
        assert r["norma"] == "RES_124_2026"

    def test_cardioversion(self):
        r = buscar_tarifa_propia_hus("996101H")
        assert r["valor_pesos_2026"] == 836_200

    def test_consulta_primera_vez_electrofisiologia(self):
        r = buscar_tarifa_propia_hus("890202H1")
        assert r["valor_pesos_2026"] == 109_000
        assert r["factor_smdlv"] == 1.86

    def test_no_encontrado_devuelve_none(self):
        assert buscar_tarifa_propia_hus("ZZZ999") is None
        assert buscar_tarifa_propia_hus("") is None
        assert buscar_tarifa_propia_hus(None) is None

    def test_case_insensitive(self):
        r = buscar_tarifa_propia_hus("372301h")
        assert r is not None
        assert r["valor_pesos_2026"] == 2_601_000


class TestBuscarTarifaSOAT:
    def test_acetaminofen(self):
        r = buscar_tarifa_soat_2026("19001")
        assert r["factor_uvb"] == 5.93
        assert r["valor_pesos_2026"] == 71_800

    def test_no_encontrado(self):
        assert buscar_tarifa_soat_2026("999999") is None


class TestContextoTarifaOficial:
    def test_contiene_valor_y_factor(self):
        txt = contexto_tarifa_oficial("372301H")
        assert "$2,601,000" in txt
        assert "44.56" in txt
        assert "Res. 124" in txt or "124/2026" in txt

    def test_soat_incluye_formula(self):
        txt = contexto_tarifa_oficial("19001")
        assert "5.93" in txt
        assert "$12,110" in txt or "12.110" in txt

    def test_vacio_si_no_encontrado(self):
        assert contexto_tarifa_oficial("ZZZ") == ""
        assert contexto_tarifa_oficial("") == ""


class TestTarifaABannerDict:
    def test_hus_devuelve_banner_compatible(self):
        d = tarifa_a_banner_dict("372301H")
        assert d is not None
        assert d["codigo_cups"] == "372301H"
        assert d["valor_pactado"] == 2_601_000
        assert d["tipo_tarifa"] == "VALOR_FIJO"
        assert "TARIFA PROPIA HUS" in d["modalidad"]
        assert "054" in d["contrato_numero"]

    def test_soat_devuelve_banner(self):
        d = tarifa_a_banner_dict("19001")
        assert d is not None
        assert d["valor_pactado"] == 71_800
        assert "SOAT PLENO" in d["modalidad"]

    def test_no_encontrado(self):
        assert tarifa_a_banner_dict("ZZZ") is None


class TestIntegridad:
    def test_todos_los_valores_son_positivos(self):
        for k, (factor, valor, desc, norma) in TARIFAS_PROPIAS_HUS.items():
            assert factor > 0, f"{k}: factor {factor}"
            assert valor > 0, f"{k}: valor {valor}"
            assert desc, f"{k}: sin descripcion"

    def test_todas_las_soat_son_positivas(self):
        for k, (factor, valor, desc, norma) in TARIFAS_SOAT_2026.items():
            assert factor > 0
            assert valor > 0

    def test_cobertura_minima(self):
        """Sanity: debe haber al menos 50 CUPS propios y 3 SOAT."""
        assert len(TARIFAS_PROPIAS_HUS) >= 50
        assert len(TARIFAS_SOAT_2026) >= 3
