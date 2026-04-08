"""Tests for GlosaIA Prompts module."""
import pytest
from app.services.glosa_ia_prompts import (
    get_system_prompt,
    build_user_prompt,
    SYSTEM_BASE,
    SYSTEM_TARIFA,
    SYSTEM_SOPORTES
)


class TestSystemPrompts:
    """Tests for system prompt generation."""

    def test_get_system_prompt_tarifa(self):
        """Should return tariff-specific prompt."""
        prompt = get_system_prompt(
            tipo_glosa="TA_TARIFA",
            eps="EPS TEST",
            contrato="CONTRATO 2026",
            cod_res="RE9602",
            desc_res="Glosa tarifaria"
        )
        assert "EPS TEST" in prompt
        assert "CONTRATO 2026" in prompt
        assert "DEFENSA TARIFARIA" in prompt

    def test_get_system_prompt_soportes(self):
        """Should return supports-specific prompt."""
        prompt = get_system_prompt(
            tipo_glosa="SO_SOPORTES",
            eps="EPS TEST",
            contrato="CONTRATO 2026",
            cod_res="RE9601",
            desc_res="Soportes incompletos"
        )
        assert "DEFENSA POR SOPORTES" in prompt

    def test_get_system_prompt_desconocido(self):
        """Should return base prompt for unknown types."""
        prompt = get_system_prompt(
            tipo_glosa="XX_UNKNOWN",
            eps="EPS TEST",
            contrato="CONTRATO 2026",
            cod_res="RE9999",
            desc_res="Desconocido"
        )
        assert "DATOS DEL CASO ACTUAL" in prompt

    def test_base_contiene_normativa(self):
        """Base prompt should include Colombian legal framework."""
        assert "Ley 100" in SYSTEM_BASE
        assert "Ley 1438" in SYSTEM_BASE
        assert "Ley 1751" in SYSTEM_BASE

    def test_base_art_56(self):
        """Base should reference Art. 56 (20 business days)."""
        assert "Art. 56" in SYSTEM_BASE or "20 días hábiles" in SYSTEM_BASE

    def test_tarifa_contiene_contrato(self):
        """Tariff prompt should mention contract importance."""
        assert "CONTRATO" in SYSTEM_TARIFA.upper() or "CONTRATO ES LEY" in SYSTEM_TARIFA.upper()

    def test_soportes_contiene_historia_clinica(self):
        """Supports prompt should mention clinical history."""
        assert "HISTORIA CLÍNICA" in SYSTEM_SOPORTES.upper()


class TestUserPrompt:
    """Tests for user prompt building."""

    def test_build_user_prompt_basic(self):
        """Should build basic user prompt."""
        prompt = build_user_prompt(
            texto_glosa="GLOSA TA0201",
            contexto_pdf="",
            codigo="TA0201",
            eps="EPS TEST"
        )
        assert "GLOSA TA0201" in prompt
        assert "CÓDIGO DETECTADO: TA0201" in prompt

    def test_build_user_prompt_con_factura(self):
        """Should include invoice number."""
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf="",
            codigo="TA0001",
            eps="EPS TEST",
            numero_factura="FAC-12345"
        )
        assert "FAC-12345" in prompt

    def test_build_user_prompt_con_radicado(self):
        """Should include radicado number."""
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf="",
            codigo="SO0001",
            eps="EPS TEST",
            numero_radicado="RAD-67890"
        )
        assert "RAD-67890" in prompt

    def test_build_user_prompt_con_pdf(self):
        """Should include PDF context."""
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf="Datos del paciente: Juan Pérez. Diagnóstico: J18.9",
            codigo="CO0001",
            eps="EPS TEST"
        )
        assert "SOPORTES ADJUNTOS" in prompt
        assert "Juan Pérez" in prompt
        assert "J18.9" in prompt

    def test_build_user_prompt_trunca_pdf(self):
        """Should truncate long PDF context."""
        long_pdf = "X" * 10000
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf=long_pdf,
            codigo="TA0001",
            eps="EPS TEST"
        )
        assert len(prompt) < 15000

    def test_build_user_prompt_formato_xml(self):
        """Should include XML format tags."""
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf="",
            codigo="SE0001",
            eps="EPS TEST"
        )
        assert "<razonamiento>" in prompt
        assert "<paciente>" in prompt
        assert "<argumento>" in prompt

    def test_build_user_prompt_instrucciones(self):
        """Should include step-by-step instructions."""
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf="",
            codigo="FA0001",
            eps="EPS TEST"
        )
        assert "PASO 1" in prompt or "RAZONAMIENTO" in prompt
        assert "MAYÚSCULAS SOSTENIDAS" in prompt
        assert "ARTÍCULO" in prompt.upper()
