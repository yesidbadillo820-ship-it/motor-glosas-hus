"""Tests del servicio UVB (Manual SOAT 2026) y tarifas propias HUS (SMDLV)."""
from app.services.uvb import (
    SMDLV_2026,
    UVB_2026,
    calcular_propia_hus,
    calcular_soat_con_factor,
    calcular_valor_pesos,
    inferir_uvb_desde_pesos,
    marco_normativo_segun_modalidad,
    valor_smdlv_vigente,
    valor_uvb_vigente,
)


class TestUVBConstantes:
    def test_uvb_2026_es_12110(self):
        assert UVB_2026 == 12_110

    def test_valor_uvb_vigente_2026(self):
        assert valor_uvb_vigente(2026) == 12_110

    def test_valor_uvb_fallback(self):
        # Año futuro no definido → usa el último conocido (2026)
        assert valor_uvb_vigente(2030) == 12_110


class TestCalcularValorPesos:
    def test_acetaminofen_ejemplo_oficial(self):
        # Ejemplo de la Circular: 5.93 UVB × 12_110 = 71_812.3 → 71_800
        assert calcular_valor_pesos(5.93) == 71_800

    def test_hematocrito_ejemplo_oficial(self):
        # 0.567 UVB × 12_110 = 6_866.37 → 6_900
        assert calcular_valor_pesos(0.567) == 6_900

    def test_histocompatibilidad(self):
        # 305.70 UVB × 12_110 = 3_702_027 → 3_702_000
        assert calcular_valor_pesos(305.70) == 3_702_000

    def test_cero_retorna_cero(self):
        assert calcular_valor_pesos(0) == 0

    def test_negativo_retorna_cero(self):
        assert calcular_valor_pesos(-5) == 0

    def test_none_retorna_cero(self):
        assert calcular_valor_pesos(None) == 0


class TestCalcularSOATConFactor:
    def test_descuento_5pct(self):
        # 5.93 UVB × 12_110 × 0.95 = 68_221.685 → 68_200
        assert calcular_soat_con_factor(5.93, factor_pct=-5.0) == 68_200

    def test_factor_cero_igual_a_soat_pleno(self):
        assert calcular_soat_con_factor(5.93, factor_pct=0) == calcular_valor_pesos(5.93)

    def test_recargo_10pct(self):
        # 5.93 × 12_110 × 1.10 = 78_993.53 → 79_000
        assert calcular_soat_con_factor(5.93, factor_pct=10.0) == 79_000

    def test_cero_retorna_cero(self):
        assert calcular_soat_con_factor(0, -5.0) == 0


class TestInferirUVB:
    def test_inferir_acetaminofen(self):
        # 71_800 / 12_110 ≈ 5.929... → redondeado a 3 decimales
        uvb = inferir_uvb_desde_pesos(71_800)
        assert abs(uvb - 5.929) < 0.01

    def test_cero(self):
        assert inferir_uvb_desde_pesos(0) == 0.0


class TestSMDLV:
    def test_smdlv_2026_aprox_58375(self):
        assert SMDLV_2026 == 58_375
        assert valor_smdlv_vigente(2026) == 58_375

    def test_factor_zero_retorna_zero(self):
        assert calcular_propia_hus(0) == 0
        assert calcular_propia_hus(None) == 0

    def test_ejemplo_potenciales_evocados(self):
        # Res. 124/2026: 3.94 SMDLV ≈ $230_000
        assert abs(calcular_propia_hus(3.94) - 230_000) < 500

    def test_ejemplo_cardioversion(self):
        # Res. 124/2026: 14.32 SMDLV ≈ $836_200
        v = calcular_propia_hus(14.32)
        assert abs(v - 836_200) < 500

    def test_ejemplo_electrofisiologico(self):
        # Res. 124/2026: 44.56 SMDLV ≈ $2_601_000
        v = calcular_propia_hus(44.56)
        assert abs(v - 2_601_000) < 500


class TestMarcoNormativoSegunModalidad:
    def test_soat_uvb_devuelve_manual_soat(self):
        marco = marco_normativo_segun_modalidad("SOAT UVB VIGENTE")
        assert "Circular 047" in marco or "047 de 2025" in marco

    def test_propias_devuelve_res_hus(self):
        marco = marco_normativo_segun_modalidad("PROPIAS")
        assert "054" in marco
        assert "124" in marco
        assert "SMDLV" in marco

    def test_manual_hus_devuelve_res_hus(self):
        marco = marco_normativo_segun_modalidad("MANUAL HUS")
        assert "054" in marco

    def test_vacio_default_soat(self):
        marco = marco_normativo_segun_modalidad("")
        assert "SOAT" in marco
