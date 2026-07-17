"""Tests del servicio de lotes (Fase 1 app unificada)."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import (
    FacturaLoteRecord,
    LoteRecord,
    TareaLoteRecord,
)
from app.services import lotes_service

HEADERS = [
    "ID_GLOSA",
    "NUMERO_FACTURA",
    "TIPO_GLOSA",
    "COD RESPUESTA GLOSA",
    "OBSERVACION RTA GLOSA",
]

FILAS_BASE = [
    ["G1", "HUS100", "TARIFAS", "RE9901 - NO ACEPTA", "Respuesta tarifas"],
    ["G2", "HUS100", "SOPORTES", "RE9901 - NO ACEPTA", "Respuesta soportes"],
    ["G3", "HUS200", "SOPORTES", "RE9502 - EXTEMPORANEA", "Glosa extemporanea"],
    ["G4", "HUS200", "CALIDAD", "", ""],
    ["G5", "HUS200", "TARIFAS", "RE9901 - NO ACEPTA", "Respuesta tarifas"],
]


def excel_bytes(hoja: str = "BASE", filas: list | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(HEADERS)
    for fila in FILAS_BASE if filas is None else filas:
        ws.append(fila)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def crear_lote(db, **kwargs):
    params = {
        "contenido": excel_bytes(),
        "nombre_archivo": "lote.xlsx",
        "pagador": "COOSALUD",
        "hoja": "BASE",
        "incluir_calidad": False,
        "creado_por": "auditor@hus.com",
    }
    params.update(kwargs)
    return lotes_service.crear_lote(db, **params)


class TestParsearExcel:
    def test_agrupa_por_factura_con_reglas_del_bot(self):
        facturas = lotes_service.parsear_excel_coosalud(excel_bytes(), "BASE", False)
        assert set(facturas) == {"HUS100", "HUS200"}
        hus100 = facturas["HUS100"]
        assert len(hus100["grupos"]) == 2
        assert any(g["es_soporte"] for g in hus100["grupos"])
        # RE9502 (extemporánea) NO exige soporte aunque el tipo sea SOPORTES,
        # y la glosa CALIDAD queda excluida del conteo de grupos.
        hus200 = facturas["HUS200"]
        assert len(hus200["grupos"]) == 2
        assert not any(g["es_soporte"] for g in hus200["grupos"])
        assert hus200["calidad"] == 1

    def test_hoja_tolerante_a_espacios(self):
        facturas = lotes_service.parsear_excel_coosalud(excel_bytes(hoja="BASE "), "base", False)
        assert set(facturas) == {"HUS100", "HUS200"}

    def test_hoja_inexistente_lanza_valueerror(self):
        with pytest.raises(ValueError, match="no tiene la hoja"):
            lotes_service.parsear_excel_coosalud(excel_bytes(), "OTRA", False)


class TestCrearLote:
    def test_crea_lote_facturas_y_tarea(self, db):
        lote = crear_lote(db)
        assert lote.estado == "EN_COLA"
        assert lote.total_facturas == 2
        assert lote.total_glosas == 4
        assert lote.total_calidad == 1
        assert lote.excel_archivo

        facturas = {
            f.factura: f for f in db.query(FacturaLoteRecord).filter_by(lote_id=lote.id).all()
        }
        assert facturas["HUS100"].requiere_soporte == 1
        assert facturas["HUS200"].requiere_soporte == 0
        assert facturas["HUS200"].calidad == 1
        assert all(f.estado == "PENDIENTE" for f in facturas.values())

        tarea = db.query(TareaLoteRecord).filter_by(lote_id=lote.id).one()
        assert tarea.tipo == "RESPONDER_COOSALUD"
        assert tarea.estado == "PENDIENTE"

    def test_pagador_no_soportado(self, db):
        with pytest.raises(ValueError, match="no soportado"):
            crear_lote(db, pagador="SIMED")

    def test_excel_sin_facturas(self, db):
        with pytest.raises(ValueError, match="no tiene facturas"):
            crear_lote(db, contenido=excel_bytes(filas=[]))


class TestColaDeTareas:
    def test_reclamar_marca_tarea_y_lote(self, db):
        lote = crear_lote(db)
        tarea = lotes_service.reclamar_tarea(db, "pc-cartera-01")
        assert tarea is not None
        assert tarea.estado == "RECLAMADA"
        assert tarea.agente == "pc-cartera-01"
        assert tarea.reclamada_en is not None
        assert db.query(LoteRecord).get(lote.id).estado == "EN_PROCESO"

    def test_sin_pendientes_devuelve_none(self, db):
        crear_lote(db)
        assert lotes_service.reclamar_tarea(db, "a") is not None
        assert lotes_service.reclamar_tarea(db, "b") is None

    def test_completar_todo_exitoso(self, db):
        lote = crear_lote(db)
        tarea = lotes_service.reclamar_tarea(db, "pc")
        resultados = [
            {"factura": "HUS100", "estado": "OK", "detalle": ""},
            {"factura": "HUS200", "estado": "OK_CALIDAD_ABIERTA", "detalle": "1 CALIDAD abierta"},
        ]
        lote = lotes_service.completar_tarea(db, tarea, exito=True, resultados=resultados)
        assert lote.estado == "COMPLETADO"
        assert tarea.estado == "COMPLETADA"
        resumen = json.loads(lote.resumen)
        assert resumen["pendientes"] == 0
        assert resumen["estados"] == {"OK": 1, "OK_CALIDAD_ABIERTA": 1}

    def test_completar_con_pendientes(self, db):
        crear_lote(db)
        tarea = lotes_service.reclamar_tarea(db, "pc")
        resultados = [
            {"factura": "HUS100", "estado": "OK", "detalle": ""},
            {"factura": "HUS200", "estado": "PENDIENTE_PDX", "detalle": "falta PDX"},
        ]
        lote = lotes_service.completar_tarea(db, tarea, exito=True, resultados=resultados)
        assert lote.estado == "COMPLETADO_CON_PENDIENTES"
        fila = db.query(FacturaLoteRecord).filter_by(lote_id=lote.id, factura="HUS200").one()
        assert fila.estado == "PENDIENTE_PDX"
        assert fila.detalle == "falta PDX"

    def test_completar_con_error_del_bot(self, db):
        crear_lote(db)
        tarea = lotes_service.reclamar_tarea(db, "pc")
        lote = lotes_service.completar_tarea(
            db, tarea, exito=False, resultados=[], error="bot murió"
        )
        assert lote.estado == "ERROR"
        assert tarea.estado == "ERROR"
        assert tarea.error == "bot murió"

    def test_factura_residual_se_agrega_al_lote(self, db):
        # El bot puede encontrar en el portal facturas que no estaban en el
        # Excel (residuales); deben aparecer en el semáforo, no perderse.
        lote = crear_lote(db)
        tarea = lotes_service.reclamar_tarea(db, "pc")
        resultados = [
            {"factura": "HUS100", "estado": "OK", "detalle": ""},
            {"factura": "HUS200", "estado": "OK", "detalle": ""},
            {"factura": "HUS999", "estado": "RECHAZADA", "detalle": "no en bolsa"},
        ]
        lotes_service.completar_tarea(db, tarea, exito=True, resultados=resultados)
        assert db.query(FacturaLoteRecord).filter_by(lote_id=lote.id, factura="HUS999").count() == 1
