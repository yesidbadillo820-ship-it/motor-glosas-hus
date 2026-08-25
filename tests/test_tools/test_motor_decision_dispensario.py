"""Tests del Motor de Decision (tools/motor_decision_dispensario.py).

Cubre: matriz de precedencia (documentos requeridos por familia), calificacion
de una glosa bien probada (defendibilidad alta -> solicitar levantamiento), de
una glosa sin soporte (defendibilidad baja + riesgo probatorio ALTO), el
escalamiento ante contradiccion grave, y la orquestacion con el resumen.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import motor_decision_dispensario as dec  # noqa: E402


def test_documentos_requeridos_matriz_precedencia():
    req_sop = dec.documentos_requeridos("SOPORTES")
    assert "Historia clinica / Evolucion" in req_sop
    assert "Epicrisis" in req_sop
    req_au = dec.documentos_requeridos("AUTORIZACION")
    assert req_au == ["Autorizacion", "MIPRES"]


def _glosa_probada(valor=200000):
    return {
        "familia": "SOPORTES",
        "valor_objetado": valor,
        "hechos_probados": [
            {
                "hecho": "La prestacion fue ORDENADA",
                "probado": True,
                "nivel_confianza": 0.95,
                "faltantes": [],
            },
            {
                "hecho": "La prestacion fue EJECUTADA / registrada",
                "probado": True,
                "nivel_confianza": 0.95,
                "faltantes": [],
            },
        ],
    }


def test_glosa_bien_probada_solicita_levantamiento():
    exp = {"contrato": {"codigo": "440"}, "cartera": {"en_cartera": True}, "alertas": []}
    d = dec.calificar_glosa(_glosa_probada(), exp)
    assert d["defendibilidad"] >= 90
    assert d["decision"] == "SOLICITAR_LEVANTAMIENTO"
    assert d["riesgos"]["probatorio"] == "BAJO"


def test_glosa_sin_soporte_riesgo_probatorio_alto():
    glosa = {
        "familia": "SOPORTES",
        "valor_objetado": 6_000_000,
        "hechos_probados": [
            {
                "hecho": "La prestacion fue ORDENADA",
                "probado": False,
                "nivel_confianza": 0.0,
                "faltantes": ["Orden medica / Formula", "Historia clinica / Evolucion"],
            },
            {
                "hecho": "La prestacion fue EJECUTADA / registrada",
                "probado": False,
                "nivel_confianza": 0.0,
                "faltantes": ["Epicrisis", "Descripcion quirurgica"],
            },
        ],
    }
    exp = {"contrato": {"codigo": "440"}, "cartera": {"en_cartera": True}, "alertas": []}
    d = dec.calificar_glosa(glosa, exp)
    assert d["defendibilidad"] == 0
    assert d["riesgos"]["probatorio"] == "ALTO"
    assert d["riesgos"]["documental"] == "ALTO"
    assert d["riesgos"]["financiero"] == "ALTO"  # 6M
    assert d["decision"] in ("SOLICITAR_SOPORTE", "CONCILIAR")
    assert d["documentos_faltantes"]
    assert d["prioridad"] == "ALTA"


def test_contradiccion_grave_escala():
    exp = {
        "contrato": {"codigo": "440"},
        "cartera": {"en_cartera": True},
        "alertas": ["El documento del paciente (X) no coincide con el RIPS."],
    }
    d = dec.calificar_glosa(_glosa_probada(), exp)
    assert d["decision"] == "ESCALAR"
    assert "paciente" in d["motivo_decision"].lower()


def test_decidir_expedientes_resumen():
    payload = {
        "expedientes": [
            {
                "factura": "HUS0000436483",
                "contrato": {"codigo": "440"},
                "cartera": {"en_cartera": True},
                "alertas": [],
                "glosas": [{**_glosa_probada(), "codigo_corto": "SO3601"}],
            }
        ]
    }
    out = dec.decidir_expedientes(payload)
    g = out["expedientes"][0]["glosas"][0]
    assert "decision" in g
    assert out["expedientes"][0]["defendibilidad_promedio"] >= 90
    assert out["expedientes"][0]["decision_dominante"] == "SOLICITAR_LEVANTAMIENTO"
    assert out["resumen_decision"].get("SOLICITAR_LEVANTAMIENTO") == 1
