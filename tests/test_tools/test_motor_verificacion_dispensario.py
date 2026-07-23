"""Tests del Motor de Verificacion de Evidencia (Modulo 3.5)
(tools/motor_verificacion_dispensario.py).

Cubre: verificacion determinista de hechos por familia de glosa (probado /
no probado, confianza, faltantes), el motor de contradicciones (factura no en
cartera, paciente que no coincide con el RIPS, CUPS ausente en RIPS), y la
orquestacion con el flag 'defendible'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import motor_verificacion_dispensario as ver  # noqa: E402


def test_hechos_soportes_probados_con_evidencia_fuerte():
    glosa = {
        "familia": "SOPORTES",
        "servicio": "PROCEDIMIENTO 470700",
        "evidencias": [
            {"tipo": "Historia clinica / Evolucion", "pagina": 18, "fuerza": "fuerte"},
            {"tipo": "Epicrisis", "pagina": 3, "fuerza": "fuerte"},
        ],
    }
    soportes = [
        {"tipo": "Historia clinica / Evolucion"},
        {"tipo": "Epicrisis"},
    ]
    hechos = ver.verificar_hechos(glosa, soportes, {"codigo": "440"})
    assert len(hechos) == 2
    assert all(h["probado"] for h in hechos)
    # con evidencia por codigo fuerte -> confianza alta
    assert all(h["nivel_confianza"] >= 0.9 for h in hechos)
    ordenado = next(h for h in hechos if "ORDENADA" in h["hecho"])
    assert any("pag.18" in e for e in ordenado["evidencia"])


def test_hechos_soportes_sin_documentos_no_probado():
    glosa = {"familia": "SOPORTES", "servicio": "PROCEDIMIENTO 470700", "evidencias": []}
    hechos = ver.verificar_hechos(glosa, soportes=[{"tipo": "RIPS"}], contrato={})
    # ninguno de los soportes clinicos requeridos esta presente
    assert all(not h["probado"] for h in hechos)
    assert all(h["nivel_confianza"] == 0.0 for h in hechos)
    assert hechos[0]["faltantes"]  # dice qué falta


def test_hechos_tarifas_contrato_probado():
    glosa = {"familia": "TARIFAS", "servicio": "CONSULTA 890201", "evidencias": []}
    soportes = [{"tipo": "RIPS"}, {"tipo": "Factura electronica (XML/CUFE)"}]
    contrato = {"codigo": "287", "base_tarifaria": "SOAT -15%"}
    hechos = ver.verificar_hechos(glosa, soportes, contrato)
    facturado = next(h for h in hechos if "facturado" in h["hecho"].lower())
    contrato_h = next(h for h in hechos if "contrato" in h["hecho"].lower())
    assert facturado["probado"] is True
    assert contrato_h["probado"] is True
    assert "287" in contrato_h["evidencia"][0]


def test_calidad_existencia_no_prueba_pertinencia():
    """Historia clinica presente, pero el servicio glosado NO aparece citado:
    no se prueba por mera existencia (defendibilidad baja)."""
    glosa = {"familia": "CALIDAD", "servicio": "TOMOGRAFIA DE CUELLO", "evidencias": []}
    soportes = [{"tipo": "Historia clinica / Evolucion"}]
    hechos = ver.verificar_hechos(glosa, soportes, {})
    assert len(hechos) == 1
    assert hechos[0]["probado"] is False
    assert hechos[0]["nivel_confianza"] == 0.40
    assert hechos[0]["faltantes"]  # dice qué falta (referencia del servicio)


def test_calidad_referencia_por_nombre_confianza_media():
    glosa = {
        "familia": "CALIDAD",
        "servicio": "TOMOGRAFIA DE CUELLO",
        "evidencias": [{"tipo": "Historia clinica / Evolucion", "pagina": 12, "fuerza": "debil"}],
    }
    hechos = ver.verificar_hechos(glosa, [{"tipo": "Historia clinica / Evolucion"}], {})
    assert hechos[0]["probado"] is True
    assert hechos[0]["nivel_confianza"] == 0.75  # por nombre, no por codigo
    assert any("pag.12" in e for e in hechos[0]["evidencia"])


def test_calidad_referencia_por_codigo_confianza_alta():
    glosa = {
        "familia": "CALIDAD",
        "servicio": "TOMOGRAFIA DE CUELLO 879101",
        "evidencias": [{"tipo": "Historia clinica / Evolucion", "pagina": 12, "fuerza": "fuerte"}],
    }
    hechos = ver.verificar_hechos(glosa, [{"tipo": "Historia clinica / Evolucion"}], {})
    assert hechos[0]["probado"] is True
    assert hechos[0]["nivel_confianza"] == 0.90  # codigo CUPS localizado


def test_contradiccion_factura_no_en_cartera():
    exp = {
        "factura_corta": "436483",
        "cartera": {"en_cartera": False},
        "contrato": {},
        "soportes": [],
        "glosas": [],
    }
    alertas = ver.detectar_contradicciones(exp)
    assert any("cartera" in a.lower() for a in alertas)


def test_contradiccion_paciente_no_coincide_con_rips(tmp_path):
    rips = tmp_path / "RIPS.json"
    rips.write_text(
        json.dumps(
            {
                "numFactura": "HUS0000436483",
                "usuarios": [{"numDocumentoIdentificacion": "99999999"}],
            }
        ),
        encoding="utf-8",
    )
    exp = {
        "factura_corta": "436483",
        "cartera": {"en_cartera": True},
        "contrato": {},
        "paciente": {"identificacion": "1029407046"},  # distinto al del RIPS
        "soportes": [{"tipo": "RIPS", "ruta": str(rips)}],
        "glosas": [{"codigo_corto": "TA0201", "servicio": "CONSULTA 890201"}],
    }
    alertas = ver.detectar_contradicciones(exp)
    assert any("paciente" in a.lower() for a in alertas)
    # el CUPS 890201 no esta en el RIPS -> alerta de CUPS
    assert any("890201" in a for a in alertas)


def test_verificar_expedientes_resumen_y_defendible():
    payload = {
        "expedientes": [
            {
                "factura": "HUS0000436483",
                "factura_corta": "436483",
                "cartera": {"en_cartera": True},
                "contrato": {"codigo": "440", "base_tarifaria": "SOAT -20%"},
                "soportes": [{"tipo": "RIPS"}, {"tipo": "Factura electronica (XML/CUFE)"}],
                "glosas": [
                    {
                        "familia": "TARIFAS",
                        "codigo_corto": "TA0201",
                        "servicio": "CONSULTA 890201",
                        "evidencias": [],
                    }
                ],
            }
        ]
    }
    out = ver.verificar_expedientes(payload)
    e = out["expedientes"][0]
    assert "hechos_probados" in e["glosas"][0]
    assert e["defendible"] is True  # facturado + contrato probados, sin alertas
    assert out["resumen_verificacion"]["expedientes_defendibles"] == 1
