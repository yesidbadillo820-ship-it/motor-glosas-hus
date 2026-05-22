"""Tests del IA Router."""

from __future__ import annotations

import pytest

from app.services.ia_router import clasificar_complejidad, elegir_modelo, enrutar


class TestClasificarComplejidad:
    def test_glosa_simple(self):
        assert (
            clasificar_complejidad(
                valor=100_000, texto_glosa="TA0201 corto", tiene_soportes_pdf=True
            )
            == "SIMPLE"
        )

    def test_glosa_media(self):
        assert clasificar_complejidad(valor=500_000, texto_glosa="TA0201 mayor valor") == "MEDIA"

    def test_alto_valor_es_compleja(self):
        assert clasificar_complejidad(valor=1_500_000, texto_glosa="TA0201") == "COMPLEJA"

    def test_ratificacion_es_compleja(self):
        assert clasificar_complejidad(valor=100_000, es_ratificacion=True) == "COMPLEJA"

    def test_extemporanea_es_compleja(self):
        assert clasificar_complejidad(valor=100_000, es_extemporanea=True) == "COMPLEJA"

    def test_multi_codigo_es_compleja(self):
        texto = "TA0201 y también SO0501 en la misma factura"
        assert clasificar_complejidad(valor=500_000, texto_glosa=texto) == "COMPLEJA"

    def test_texto_largo_es_complejo(self):
        texto = "X" * 900
        assert clasificar_complejidad(valor=500_000, texto_glosa=texto) == "COMPLEJA"

    def test_eps_critica_es_compleja(self):
        assert clasificar_complejidad(valor=500_000, eps_familia_critica=True) == "COMPLEJA"


class TestElegirModelo:
    def test_compleja_prefiere_anthropic(self):
        r = elegir_modelo("COMPLEJA")
        assert r.modelo_recomendado == "anthropic"
        assert "razonamiento" in r.razon.lower()

    def test_simple_prefiere_groq(self):
        r = elegir_modelo("SIMPLE")
        assert r.modelo_recomendado == "groq"
        assert "speed" in r.razon.lower()

    def test_media_prefiere_groq(self):
        r = elegir_modelo("MEDIA")
        assert r.modelo_recomendado == "groq"

    def test_compleja_sin_anthropic_fallback_groq(self):
        r = elegir_modelo("COMPLEJA", proveedores_disponibles={"groq", "gemini"})
        assert r.modelo_recomendado == "groq"
        assert "anthropic" not in r.modelos_fallback

    def test_simple_sin_groq_fallback_anthropic(self):
        r = elegir_modelo("SIMPLE", proveedores_disponibles={"anthropic", "gemini"})
        assert r.modelo_recomendado == "anthropic"

    def test_fallback_excluye_preferido(self):
        r = elegir_modelo("COMPLEJA")
        assert r.modelo_recomendado not in r.modelos_fallback


class TestEnrutar:
    def test_glosa_complete_compleja_a_claude(self):
        r = enrutar(
            eps="FAMISANAR EPS",
            valor=2_000_000,
            texto_glosa="TA0201 mayor valor cobrado",
            es_ratificacion=False,
        )
        assert r.complejidad == "COMPLEJA"
        assert r.modelo_recomendado == "anthropic"

    def test_glosa_simple_a_groq(self):
        r = enrutar(
            eps="NUEVA EPS",
            valor=50_000,
            texto_glosa="TA0201",
            tiene_soportes_pdf=True,
        )
        assert r.complejidad == "SIMPLE"
        assert r.modelo_recomendado == "groq"

    def test_eps_critica_dispara_compleja(self):
        # POLICIA NACIONAL es crítica → upgrade a COMPLEJA aunque valor sea bajo
        r = enrutar(
            eps="POLICIA NACIONAL",
            valor=300_000,
            texto_glosa="TA0201 mayor valor",
        )
        assert r.complejidad == "COMPLEJA"


@pytest.mark.parametrize(
    "eps,esperada",
    [
        ("FAMISANAR EPS", "COMPLEJA"),
        ("POLICIA NACIONAL", "COMPLEJA"),
        ("FOMAG", "COMPLEJA"),
        ("PPL", "COMPLEJA"),
        ("NUEVA EPS", "MEDIA"),  # no crítica
        ("COMPENSAR", "MEDIA"),  # no crítica
    ],
)
def test_eps_criticas(eps, esperada):
    r = enrutar(eps=eps, valor=300_000, texto_glosa="TA0201 mayor valor cobrado")
    assert r.complejidad == esperada
