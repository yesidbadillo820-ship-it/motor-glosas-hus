"""Tests del orquestador multi-agente (Ronda 6)."""
from app.services.multi_agente import (
    agente_clinico,
    agente_conciliador,
    agente_juridico,
    agente_tarifario,
    orquestar_dictamen,
)


class TestAgenteJuridico:
    def test_ta_famisanar_incluye_871_1602(self):
        r = agente_juridico("TA0201", "FAMISANAR EPS", "Inicial")
        joined = " ".join(r["normas_primarias"])
        assert "871" in joined
        assert "1602" in joined

    def test_ta_evita_t1025_y_t478(self):
        r = agente_juridico("TA0201", "NUEVA EPS", "Inicial")
        joined = " ".join(r["evitar"])
        assert "T-1025" in joined or "1025" in joined
        assert "T-478" in joined or "478" in joined

    def test_so_incluye_1995(self):
        r = agente_juridico("SO0101", "COOSALUD", "Inicial")
        joined = " ".join(r["normas_primarias"])
        assert "1995" in joined

    def test_au_cita_t1025(self):
        r = agente_juridico("AU0101", "COMPENSAR", "Inicial")
        joined = " ".join(r["jurisprudencia"])
        assert "T-1025" in joined or "1025" in joined

    def test_fomag_evita_t760(self):
        r = agente_juridico("TA0201", "FOMAG", "Inicial")
        joined = " ".join(r["evitar"])
        assert "T-760" in joined or "760" in joined
        joined_pri = " ".join(r["normas_primarias"])
        assert "1795" in joined_pri

    def test_ratificacion_agrega_dec_4747(self):
        r = agente_juridico("TA0201", "NUEVA EPS", "RATIFICADA")
        joined = " ".join(r["normas_primarias"])
        assert "4747" in joined


class TestAgenteClinico:
    def test_urgencia_es_categoria_y_inherente(self):
        r = agente_clinico("890701", "CONSULTA URGENCIAS MEDICINA GENERAL")
        assert r["categoria"] == "URGENCIA"
        assert r["justificacion_inherente"]

    def test_cups_con_sufijo_h_refiere_res_hus(self):
        r = agente_clinico("372301H", "ESTUDIO ELECTROFISIOLOGICO")
        joined = " ".join(r["soportes_esperados"])
        assert "054" in joined or "124" in joined

    def test_cirugia_categoria(self):
        r = agente_clinico("849501H", "CIRUGIA RECONSTRUCTIVA")
        assert r["categoria"] == "CIRUGIA"


class TestAgenteTarifario:
    def test_soat_porcentaje_calcula_interp(self):
        r = agente_tarifario(
            modalidad="SOAT UVB VIGENTE", factor_ajuste=-5.0,
            tipo_tarifa="SOAT_PORCENTAJE",
            valor_facturado=114_900, valor_reconocido=90_000,
        )
        assert r["interpretacion_hus"] > r["interpretacion_eps"]
        assert r["diferencia_pesos"] == 24_900.0
        assert r["recomendacion"] in ("DEFENDER", "REVISAR")

    def test_propias_valor_fijo_match_perfecto_defender(self):
        r = agente_tarifario(
            modalidad="PROPIAS", tipo_tarifa="VALOR_FIJO",
            valor_pactado=83_800, valor_facturado=83_800,
        )
        assert r["recomendacion"] == "DEFENDER"


class TestAgenteConciliador:
    def test_ratificacion_tono_firme(self):
        r = agente_conciliador("conciliador", "RATIFICADA")
        joined = " ".join(r["lineamientos"])
        assert "firme" in joined.lower() or "autoridades" in joined.lower()

    def test_conciliador_incluye_respetuosamente(self):
        r = agente_conciliador("conciliador", "INICIAL")
        joined = " ".join(r["lineamientos"])
        assert "RESPETUOSAMENTE" in joined.upper() or "respetuosamente" in joined


class TestOrquestador:
    def test_orquestar_incluye_4_agentes(self):
        bloque = orquestar_dictamen(
            codigo_glosa="TA0201", eps="FAMISANAR EPS",
            cups="890750", servicio="CONSULTA URGENCIAS", etapa="INICIAL",
            modalidad="SOAT UVB", factor_ajuste=-5.0,
            tipo_tarifa="SOAT_PORCENTAJE",
            valor_facturado=114_900, valor_reconocido=90_000,
        )
        assert "AGENTE JURÍDICO" in bloque
        assert "AGENTE CLÍNICO" in bloque
        assert "AGENTE TARIFARIO" in bloque
        assert "AGENTE CONCILIADOR" in bloque
        assert "890750" not in bloque  # el CUPS en sí no debería duplicarse en cada agente
        # Debería estar el factor y las citas jurídicas
        assert "871" in bloque
        assert "1602" in bloque

    def test_orquestar_fomag_aparece_t760_en_evitar(self):
        """T-760 debe aparecer solo en la sección NO CITES (evitar), no
        en normas primarias ni jurisprudencia sugerida."""
        bloque = orquestar_dictamen(
            codigo_glosa="TA0201", eps="FOMAG",
            cups="890202", etapa="Inicial",
        )
        # Debe estar presente en evitar (prefijo ✗)
        assert "T-760" in bloque
        # pero la línea debe ser de evitar, identificable por ✗
        lineas_t760 = [l for l in bloque.split("\n") if "T-760" in l]
        assert all("✗" in l for l in lineas_t760), f"T-760 debe estar en evitar: {lineas_t760}"
        # Y las primarias deben tener 1795 (Dec. FF.MM.)
        assert "1795" in bloque
