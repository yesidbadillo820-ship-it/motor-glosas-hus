"""Tests del modelo de datos unico de conciliacion
(tools/expediente_conciliacion.py).

Cubre: ensamblado del expediente por factura (id_expediente = factura, con
paciente, contrato por fecha, base tarifaria, cartera, glosas y soportes del
indice), lectura de la cartera desde xlsx, y el roundtrip guardar/cargar.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import asistente_conciliacion_dispensario as asis  # noqa: E402
import expediente_conciliacion as exp  # noqa: E402


def _glosa(factura, cod, fatt, valor, servicio="890201", ident="1029407046"):
    return asis.Glosa(
        factura=asis.norm_factura(factura),
        radicado="644561",
        fecha_atencion=fatt,
        paciente="VALERY MOSQUERA",
        identificacion=ident,
        valor_factura=231461,
        num_glosa="1",
        codigo=cod,
        familia=asis.familia_de(cod),
        motivo="Mayor valor cobrado",
        valor_objetado=valor,
        servicio=servicio,
    )


def _indice(factura_corta):
    return {
        "documentos": [
            {"factura": factura_corta, "tipo": "RIPS", "nombre": "RIPS_x.json", "ruta": "Y:\\x"},
            {
                "factura": factura_corta,
                "tipo": "Historia clinica / Evolucion",
                "nombre": "HEV_x.pdf",
                "ruta": "Y:\\y",
            },
        ]
    }


def test_construir_expediente_amarra_todo():
    glosas = [
        _glosa("436483", "TA02 01 TARIFAS", datetime(2025, 10, 28), 156061),
        _glosa("436483", "SO36 01 SOPORTES", datetime(2025, 10, 28), 44000),
    ]
    cartera = {
        "436483": {
            "contrato": "U22031",
            "saldo": 200061,
            "edad": 223,
            "edad_rango": "X181 A 360",
            "deterioro": 0,
        }
    }
    exps = exp.construir_expedientes(glosas, _indice("436483"), cartera)
    assert len(exps) == 1
    e = exps[0]
    # id unico = factura normalizada
    assert e.id_expediente == "HUS0000436483" == e.factura
    assert e.factura_corta == "436483"
    # paciente
    assert e.paciente.identificacion == "1029407046"
    # contrato por fecha (oct-2025 -> 287) + base tarifaria + codigo de cartera
    assert e.contrato.codigo == "287"
    assert "SOAT 2025 -15%" in e.contrato.base_tarifaria
    assert e.contrato.codigo_cartera == "U22031"
    assert e.contrato.pendiente_confirmar is True
    # cartera
    assert e.cartera.en_cartera is True
    assert e.cartera.saldo == 200061
    assert e.cartera.edad_rango == "X181 A 360"
    # glosas (2) + total objetado
    assert len(e.glosas) == 2
    assert e.valor_objetado_total == 200061
    assert e.glosas[0].codigo_corto == "TA0201"
    # soportes del indice
    assert {s.tipo for s in e.soportes} == {"RIPS", "Historia clinica / Evolucion"}
    assert e.estado == "PENDIENTE"


def test_dedup_glosas_exactamente_duplicadas():
    """Una fila de glosa repetida en el Excel origen no se cuenta dos veces."""
    g1 = _glosa("468966", "CL08 01", datetime(2026, 2, 15), 250811, servicio="HEMOCULTIVO")
    g2 = _glosa("468966", "CL08 01", datetime(2026, 2, 15), 250811, servicio="HEMOCULTIVO")
    exps = exp.construir_expedientes([g1, g2], {"documentos": []}, {})
    assert len(exps) == 1
    assert len(exps[0].glosas) == 1  # el duplicado exacto se elimina
    assert exps[0].valor_objetado_total == 250811  # no se suma dos veces


def test_no_dedup_servicios_distintos():
    """Servicios distintos (aunque compartan codigo) se conservan ambos."""
    g1 = _glosa("468966", "CL08 01", datetime(2026, 2, 15), 250811, servicio="HEMOCULTIVO")
    g2 = _glosa("468966", "CL08 01", datetime(2026, 2, 15), 172623, servicio="UROCULTIVO")
    exps = exp.construir_expedientes([g1, g2], {"documentos": []}, {})
    assert len(exps[0].glosas) == 2
    assert exps[0].valor_objetado_total == 250811 + 172623


def test_contrato_440_por_fecha():
    glosas = [_glosa("500000", "TA02 01", datetime(2026, 2, 15), 1000)]
    exps = exp.construir_expedientes(glosas, {"documentos": []}, {})
    assert exps[0].contrato.codigo == "440"
    assert exps[0].contrato.pendiente_confirmar is False
    assert exps[0].cartera.en_cartera is False  # no estaba en cartera


def test_cartera_desde_xlsx(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ESTADO DE CARTERA A JUNIO 30 DE 2026"])  # fila titulo
    hdr = [""] * 34
    hdr[6] = "FACTURA"
    ws.append(hdr)  # fila encabezados
    fila = [None] * 34
    fila[4] = "U22031"
    fila[6] = "HUS0000436483"
    fila[7] = 156061
    fila[28] = 223
    fila[30] = "X181 A 360"
    fila[33] = 0
    ws.append(fila)
    ruta = tmp_path / "cartera.xlsx"
    wb.save(str(ruta))

    cart = exp.cartera_desde_xlsx(ruta, {"436483"})
    assert cart["436483"]["saldo"] == 156061
    assert cart["436483"]["edad_rango"] == "X181 A 360"
    assert cart["436483"]["contrato"] == "U22031"


def test_guardar_cargar_roundtrip(tmp_path):
    glosas = [_glosa("436483", "TA02 01", datetime(2025, 10, 28), 156061)]
    exps = exp.construir_expedientes(glosas, {"documentos": []}, {})
    salida = tmp_path / "expedientes.json"
    exp.guardar_expedientes(exps, salida)

    data = json.loads(salida.read_text(encoding="utf-8"))
    assert data["total"] == 1
    assert data["expedientes"][0]["id_expediente"] == "HUS0000436483"
    assert data["expedientes"][0]["contrato"]["codigo"] == "287"
    # cargar via helper
    assert exp.cargar_expedientes(salida)["total"] == 1
