"""Tests for GlosaIA Prompts module."""
import pytest
from app.services.glosa_ia_prompts import (
    get_system_prompt,
    build_user_prompt,
    SYSTEM_BASE,
    SYSTEM_TA,
    SYSTEM_SO,
)


class TestSystemPrompts:
    """Tests for system prompt generation."""

    def test_get_system_prompt_tarifa(self):
        """Should return tariff-specific prompt."""
        prompt = get_system_prompt(prefijo="TA", eps="EPS TEST")
        assert "EPS TEST" in prompt
        assert "DEFENSA TARIFARIA" in prompt

    def test_get_system_prompt_soportes(self):
        """Should return supports-specific prompt."""
        prompt = get_system_prompt(prefijo="SO", eps="EPS TEST")
        assert "DEFENSA POR SOPORTES" in prompt

    def test_get_system_prompt_desconocido(self):
        """Unknown prefix should fall back to FA (facturación) prompt."""
        prompt = get_system_prompt(prefijo="XX", eps="EPS TEST")
        assert "EPS TEST" in prompt
        assert "DATOS CONTRACTUALES" in prompt

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
        assert "CONTRATO" in SYSTEM_TA.upper()

    def test_soportes_contiene_historia_clinica(self):
        """Supports prompt should mention clinical history."""
        assert "HISTORIA CLÍNICA" in SYSTEM_SO.upper()


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
        assert "TA0201" in prompt

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
        """Should include PDF context data."""
        pdf_context = (
            "Historia clínica del paciente. Servicio: Consulta externa. "
            "Código CUPS 890201. Diagnóstico J18.9 Neumonía. "
            "Médico: Dr. Juan Pérez, especialista en medicina interna."
        )
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf=pdf_context,
            codigo="CO0001",
            eps="EPS TEST"
        )
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

    def test_build_user_prompt_instrucciones(self):
        """Should include structured instructions and norms."""
        prompt = build_user_prompt(
            texto_glosa="GLOSA",
            contexto_pdf="",
            codigo="FA0001",
            eps="EPS TEST"
        )
        assert "INSTRUCCIONES" in prompt.upper()
        assert "NORMAS" in prompt.upper()
