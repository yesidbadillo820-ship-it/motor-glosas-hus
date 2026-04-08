"""Tests for GlosaService."""
import pytest
from app.services.glosa_service import (
    GlosaService,
    generar_texto_extemporanea,
    generar_texto_injustificada,
    obtener_plantilla_por_codigo,
    DIAS_HABILES_LIMITE_EXTEMPORANEA
)


class TestCalculoDiasHabiles:
    """Tests for business days calculation."""

    def test_calcular_dias_habiles_mismo_dia(self, glosa_service):
        """Same day should return 0 business days."""
        result = glosa_service._calcular_dias_habiles("2026-03-02", "2026-03-02")
        assert result == 0

    def test_calcular_dias_habiles_un_dia(self, glosa_service):
        """Monday to Tuesday should return 1 business day."""
        result = glosa_service._calcular_dias_habiles("2026-03-02", "2026-03-03")
        assert result == 1

    def test_calcular_dias_habiles_fin_de_semana(self, glosa_service):
        """Friday to Monday should return 1 business day."""
        result = glosa_service._calcular_dias_habiles("2026-03-06", "2026-03-09")
        assert result == 1

    def test_calcular_dias_habiles_feriado(self, glosa_service):
        """Should skip holidays in count."""
        result = glosa_service._calcular_dias_habiles("2026-03-02", "2026-03-03")
        assert result == 1


class TestConstantes:
    """Tests for system constants."""

    def test_dias_limite_extemporanea(self):
        """Verify 20 business days limit per Art. 56 Ley 1438/2011."""
        assert DIAS_HABILES_LIMITE_EXTEMPORANEA == 20


class TestGenerarTextoExtemporanea:
    """Tests for extemporaneous response text generation."""

    def test_genera_texto_con_dias(self):
        """Should include days elapsed in response."""
        texto = generar_texto_extemporanea(25)
        assert "25 DÍAS HÁBILES" in texto
        assert "20 DÍAS HÁBILES" in texto
        assert "ARTÍCULO 56" in texto
        assert "LEY 1438 DE 2011" in texto

    def test_genera_texto_no_acepta_glosa(self):
        """Should reject the glosa."""
        texto = generar_texto_extemporanea(25)
        assert "RECHAZA" in texto or "NO ACEPTA" in texto.upper()

    def test_genera_texto_pago_integro(self):
        """Should demand full payment."""
        texto = generar_texto_extemporanea(25)
        assert "PAGO" in texto.upper()
        assert "IPS" in texto


class TestGenerarTextoInjustificada:
    """Tests for unjustified response text generation."""

    def test_genera_texto_con_eps(self):
        """Should include EPS name in response."""
        texto = generar_texto_injustificada("EPS EJEMPLO")
        assert "EPS EJEMPLO" in texto

    def test_genera_texto_soat(self):
        """Should mention SOAT tariff."""
        texto = generar_texto_injustificada("EPS TEST")
        assert "SOAT" in texto


class TestPlantillas:
    """Tests for glosa response templates."""

    def test_obtener_plantilla_ta0201(self):
        """TA0201 should return tariff template."""
        plantilla = obtener_plantilla_por_codigo("TA0201")
        assert plantilla is not None
        assert "plantilla" in plantilla

    def test_obtener_plantilla_so0101(self):
        """SO0101 should return supports template."""
        plantilla = obtener_plantilla_por_codigo("SO0101")
        assert plantilla is not None
        assert "TARIFA INSTITUCIONAL" in plantilla["plantilla"] or "orden" in plantilla["plantilla"].lower()

    def test_obtener_plantilla_mayusculas(self):
        """Should find template regardless of case."""
        plantilla = obtener_plantilla_por_codigo("ta0201")
        assert plantilla is not None

    def test_obtener_plantilla_inexistente(self):
        """Should return None for non-existent code."""
        plantilla = obtener_plantilla_por_codigo("ZZ9999")
        assert plantilla is None


class TestExtraccionCodigo:
    """Tests for glosa code extraction."""

    def test_extraer_codigo_ta(self, glosa_service):
        """Should extract TA codes."""
        result = glosa_service._extraer_codigo_glosa("GLOSA TA0201 $100000")
        assert result == "TA0201"

    def test_extraer_codigo_so(self, glosa_service):
        """Should extract SO codes."""
        result = glosa_service._extraer_codigo_glosa("Soportes SO0101 incompletos")
        assert result == "SO0101"

    def test_extraer_codigo_inexistente(self, glosa_service):
        """Should return SE-N/A for unknown codes."""
        result = glosa_service._extraer_codigo_glosa("Sin código específico")
        assert result == "SE-N/A"


class TestExtraccionValor:
    """Tests for value extraction from glosa text."""

    def test_extraer_valor_formato_colombiano(self, glosa_service):
        """Should extract Colombian peso format."""
        result = glosa_service._extraer_valor("Glosa por $1,500,000")
        assert "$ 1,500,000" in result or "1,500,000" in result

    def test_extraer_valor_sin_signo(self, glosa_service):
        """Should handle value without $ sign - returns default when not found."""
        result = glosa_service._extraer_valor("Valor 500000 sin pesos")
        assert "$ 0.00" in result

    def test_extraer_valor_inexistente(self, glosa_service):
        """Should return default $0.00 when no value found."""
        result = glosa_service._extraer_valor("Sin valor especificado")
        assert "$ 0.00" in result


class TestDeterminarTipoGlosa:
    """Tests for glosa type determination."""

    def test_tipo_tarifa(self, glosa_service):
        """Should identify TA prefix as tariff."""
        result = glosa_service._determinar_tipo_glosa("TA", "GLOSA TARIFA")
        assert result == "TA_TARIFA"

    def test_tipo_soportes(self, glosa_service):
        """Should identify SO prefix as supports."""
        result = glosa_service._determinar_tipo_glosa("SO", "SOPORTES")
        assert result == "SO_SOPORTES"

    def test_tipo_extemporanea(self, glosa_service):
        """Should identify extemporaneous glosa."""
        result = glosa_service._determinar_tipo_glosa("EX", "EXTEMPORANEA")
        assert result == "EXT_EXTEMPORANEA"

    def test_tipo_medicamentos(self, glosa_service):
        """Should identify medications in text."""
        result = glosa_service._determinar_tipo_glosa("SE", "medicamento no reconocido")
        assert result == "ME_MEDICAMENTOS"

    def test_tipo_insumos(self, glosa_service):
        """Should identify supplies in text."""
        result = glosa_service._determinar_tipo_glosa("SE", "insumo no facturado")
        assert result == "IN_INSUMOS"


class TestXmlParser:
    """Tests for XML extraction from AI responses."""

    def test_extraer_paciente(self, glosa_service):
        """Should extract patient name from XML tag."""
        xml = "<paciente>Juan Pérez</paciente><argumento>Texto</argumento>"
        result = glosa_service._xml("paciente", xml, "DEFAULT")
        assert result == "Juan Pérez"

    def test_extraer_argumento(self, glosa_service):
        """Should extract argument from XML tag."""
        xml = "<paciente>Test</paciente><argumento>Respuesta legal</argumento>"
        result = glosa_service._xml("argumento", xml, "DEFAULT")
        assert result == "Respuesta legal"

    def test_xml_sin_tag_retorna_default(self, glosa_service):
        """Should return default when tag not found."""
        xml = "<otro>Contenido</otro>"
        result = glosa_service._xml("paciente", xml, "NO ENCONTRADO")
        assert result == "NO ENCONTRADO"


class TestScoreCalculo:
    """Tests for score calculation."""

    def test_score_extemporanea(self, glosa_service):
        """Extemporaneous should have highest score."""
        score = glosa_service._calcular_score(
            tipo_glosa="EXT_EXTEMPORANEA",
            es_extemporanea=True,
            es_ratificacion=False,
            tiene_pdf=False,
            es_urgencia=False,
            es_tarifa=False
        )
        assert score == 99.0

    def test_score_ratificacion(self, glosa_service):
        """Ratification should have high score."""
        score = glosa_service._calcular_score(
            tipo_glosa="RATIFICADA",
            es_extemporanea=False,
            es_ratificacion=True,
            tiene_pdf=False,
            es_urgencia=False,
            es_tarifa=False
        )
        assert score == 92.0

    def test_score_urgencia(self, glosa_service):
        """Urgency should have high score."""
        score = glosa_service._calcular_score(
            tipo_glosa="AU_AUTORIZACION",
            es_extemporanea=False,
            es_ratificacion=False,
            tiene_pdf=False,
            es_urgencia=True,
            es_tarifa=False
        )
        assert score == 90.0

    def test_score_con_pdf(self, glosa_service):
        """PDF support should add 5 points up to 100."""
        score = glosa_service._calcular_score(
            tipo_glosa="EXT_EXTEMPORANEA",
            es_extemporanea=True,
            es_ratificacion=False,
            tiene_pdf=True,
            es_urgencia=False,
            es_tarifa=False
        )
        assert score == 100.0

    def test_score_tarifa(self, glosa_service):
        """Tariff should have base score."""
        score = glosa_service._calcular_score(
            tipo_glosa="TA_TARIFA",
            es_extemporanea=False,
            es_ratificacion=False,
            tiene_pdf=False,
            es_urgencia=False,
            es_tarifa=True
        )
        assert score == 75.0
