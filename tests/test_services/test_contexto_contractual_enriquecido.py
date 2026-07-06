"""Tests del inyector de contexto contractual enriquecido.

Objetivo: replicar la calidad de la "otra IA" que produjo dictámenes
9/10 en la evaluación del 10-jun-2026 — CUPS específico + tarifa
pactada + NIT + SECOP + parágrafos + anexos + corrección de
denominación + soportes específicos.
"""

from __future__ import annotations

import pytest

from app.services.contexto_contractual_enriquecido import (
    ContextoContractual,
    _detectar_correcciones_denominacion,
    _extraer_cups_del_texto,
    _regimen_especial_texto,
    _soportes_por_familia,
    construir_contexto,
)


class TestExtraccionCUPS:
    @pytest.mark.parametrize(
        "texto,esperados",
        [
            (
                "Se objeta el CUPS 882298 ecografía doppler obstétrica",
                ["882298"],
            ),
            (
                "EQUIPO EN Y PARA IRRIGACION TUR (FMQ0016) - $64.400",
                ["FMQ0016"],
            ),
            (
                "Se incluye sistema de suspensión FMO01763 en cirugía y compresa FMQ1506",
                ["FMO01763", "FMQ1506"],
            ),
            (
                "Consulta cirugía vascular código institucional 39143A-4",
                ["39143A-4"],
            ),
            ("Glosa sin código alguno", []),
        ],
    )
    def test_cups(self, texto, esperados):
        assert _extraer_cups_del_texto(texto) == esperados


class TestCorreccionDenominacion:
    def test_beta_2_macroglobulina_se_corrige(self):
        # Caso real Excel: la auditoría escribió "MACROGLOBULINA" cuando
        # el examen es "GLICOPROTEINA" — exámenes diferentes.
        out = _detectar_correcciones_denominacion(
            "GLOSA MVC BETA 2 MACROGLOBULINA IPS SIN CONTRATO"
        )
        assert out and out[0]["equivocado"] == "BETA 2 MACROGLOBULINA"
        assert out[0]["correcto"] == "BETA 2 GLICOPROTEINA"

    def test_critulina_se_corrige(self):
        out = _detectar_correcciones_denominacion("GLOSA CRITULINA NO EVIDENCIA ACUERDO DE TARIFAS")
        assert out and "PEPTIDO" in out[0]["correcto"]

    def test_sin_error_no_dispara(self):
        out = _detectar_correcciones_denominacion("Glosa de tarifa normal")
        assert out == []

    def test_ya_corrige_internamente_no_dispara(self):
        # Si el propio texto ya menciona el correcto, no hay que volver a
        # corregir (evita ruido cuando el motivo trae paréntesis aclarando).
        out = _detectar_correcciones_denominacion(
            "BETA 2 MACROGLOBULINA (REALMENTE ES BETA 2 GLICOPROTEINA)"
        )
        assert out == []


class TestRegimenEspecial:
    @pytest.mark.parametrize(
        "eps,esperado_keyword",
        [
            ("DISPENSARIO MEDICO BUCARAMANGA", "1795"),
            ("DIGSA", "1795"),
            ("SANIDAD MILITAR", "1795"),
            ("POLICÍA NACIONAL", "Acuerdo 002"),
            ("FOMAG", "3752"),
            ("PPL CARCEL MODELO", "5159"),
            ("POSITIVA ARL", "1295"),
        ],
    )
    def test_regimen_se_construye(self, eps, esperado_keyword):
        out = _regimen_especial_texto(eps, {})
        assert esperado_keyword in out

    def test_eps_regular_no_dispara_regimen(self):
        out = _regimen_especial_texto("FAMISANAR", {})
        assert out == ""


class TestSoportesPorFamilia:
    def test_so_pide_hc_rips_anexo_5(self):
        s = _soportes_por_familia("SO", [])
        full = " ".join(s).lower()
        assert "historia clínica" in full
        assert "rips" in full
        assert "anexo técnico" in full or "3047" in full

    def test_in_pide_descripcion_quirurgica(self):
        s = _soportes_por_familia("IN", ["FMQ0016"])
        full = " ".join(s).lower()
        assert "descripción quirúrgica" in full or "descripcion quirurgica" in full
        assert "fmq0016" in full or "fmq" in full.upper()

    def test_ta_pide_anexo_tarifario(self):
        s = _soportes_por_familia("TA", [])
        full = " ".join(s).lower()
        assert "anexo tarifario" in full or "anexo" in full
        assert "soat" in full or "uvb" in full

    def test_familia_desconocida_devuelve_lista_vacia_o_solo_cups(self):
        s = _soportes_por_familia("XX", ["123456"])
        # Solo el CUPS — sin lista por familia
        assert len(s) <= 1


class TestBloquePrompt:
    def test_contexto_vacio_no_imprime_nada(self):
        ctx = ContextoContractual()
        assert ctx.es_vacio()
        assert ctx.a_bloque_prompt() == ""

    def test_bloque_incluye_secciones_principales(self):
        ctx = ContextoContractual(
            contrato_metadata={
                "numero_contrato": "440-DIGSA/DMBUG-2025",
                "nit_eps": "901.541.137-1",
                "nit_ips": "900.006.037-4",
                "razon_social_eps": "DISPENSARIO MEDICO DE BUCARAMANGA",
                "razon_social_ips": "ESE HOSPITAL UNIVERSITARIO DE SANTANDER",
                "fecha_suscripcion": "29/12/2025",
                "fecha_inicio": "29/12/2025",
                "fecha_fin": "30/07/2026",
                "numero_proceso_secop": "CD477-DIGSA/DMBUG-2025",
                "modalidades_tarifarias": ["TARIFA PROPIA ESE", "SOAT UVB"],
                "anexos_descripcion": [
                    {"nombre": "Anexo 1", "descripcion": "Tarifas (7.141 ítems)"},
                    {"nombre": "Anexo 05", "descripcion": "Dispositivos médicos"},
                ],
                "__hint_motivo": "IPS SIN CONTRATO",
            },
            clausulas=[
                {
                    "numero_clausula": "SEGUNDA - PARÁGRAFO 4",
                    "tema": "TA",
                    "titulo": "Modalidades tarifarias",
                    "texto_literal": "Las tarifas propias ESE se aplicarán a los servicios pactados como tales en el Anexo 1.",
                    "pagina": 4,
                }
            ],
            cups_detectados=["882298"],
            tarifas_pactadas=[
                {
                    "codigo_cups": "882298",
                    "descripcion": "ECOGRAFIA DOPPLER OBSTETRICA",
                    "modalidad": "TARIFA PROPIA ESE",
                    "valor_pactado": 36402.0,
                }
            ],
            correcciones_denominacion=[
                {"equivocado": "BETA 2 MACROGLOBULINA", "correcto": "BETA 2 GLICOPROTEINA"}
            ],
            regimen_especial="Régimen especial Subsistema FF.MM. y Policía...",
            soportes_recomendados=["Historia clínica", "Anexo tarifario"],
        )
        out = ctx.a_bloque_prompt()
        # Datos del contrato presentes
        assert "440-DIGSA/DMBUG-2025" in out
        assert "901.541.137-1" in out
        assert "CD477-DIGSA/DMBUG-2025" in out
        assert "30/07/2026" in out
        assert "Anexo 1" in out
        # CUPS + tarifa pactada
        assert "CUPS 882298" in out
        assert "TARIFA PROPIA ESE" in out
        # Cláusula con número y tema
        assert "PARÁGRAFO 4" in out
        # Régimen especial
        assert "FF.MM." in out or "Régimen especial" in out
        # Corrección al auditor
        assert "BETA 2 MACROGLOBULINA" in out
        # Doctrina agotamiento (porque __hint_motivo trae "IPS SIN CONTRATO")
        assert "AGOTAMIENTO" in out.upper()
        assert "ENRIQUECIMIENTO SIN JUSTA CAUSA" in out.upper()


class TestConstruirContextoSinBD:
    """Verifica que el inyector degrada elegantemente sin BD."""

    def test_glosa_dmbug_sin_bd_aun_trae_regimen_y_soportes(self):
        # Sin BD activa, debe traer al menos régimen especial y soportes
        # por familia + CUPS detectados + corrección de denominación.
        ctx = construir_contexto(
            eps="DISPENSARIO MEDICO BUCARAMANGA",
            codigo_glosa="",
            texto_glosa="GLOSA MVC BETA 2 MACROGLOBULINA CUPS 906481 IPS SIN CONTRATO",
            familia="TA",
        )
        assert "1795" in ctx.regimen_especial  # Dec. 1795/2000
        assert "906481" in ctx.cups_detectados
        assert ctx.correcciones_denominacion
        assert ctx.correcciones_denominacion[0]["correcto"] == "BETA 2 GLICOPROTEINA"
        bloque = ctx.a_bloque_prompt()
        assert "BETA 2 GLICOPROTEINA" in bloque
        assert "906481" in bloque
