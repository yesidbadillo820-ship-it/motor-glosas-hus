"""Regresión: al importar un Excel de recepción con hojas INICIAL y
RATIFICADA, el cerebro IA solo debe procesar las glosas INICIAL pendientes
(estado RADICADA). Las RATIFICADA ya traen su dictamen de texto fijo
(_dictamen_ratificada), así que NO deben ir a la IA (no gastan tokens ni
tiempo) — pero SÍ deben entrar al Excel-respuesta (glosas_ids_todas).

Estructura y valores tomados del archivo real del usuario (entrega del
4/05/2026: 19 glosas INICIAL de DIRECCION DE SANIDAD EJERCITO + 5 glosas
RATIFICADA de aseguradoras)."""
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaRecord
from app.services.recepcion_service import RecepcionService

_HEADER_INICIAL = [
    "GESTOR", "FECHA DE ENTREGA", "FECHA RADICACION",
    "FECHA DOCUMENTO DGH", "FECHA RECEPCION", "ENTIDAD", "FACTURA",
    "CONSECUTIVO DGH", "VALOR GLOSA", "VENCE", "DEVOLUCION \nS/N",
    "DIAS \nRADICACION VS RECEPCION", "RADICADO", "REFERENCIA",
    "OBSERVACION TECNICO", "TECNICO QUE RECEPCIONO", "TIPO GLOSA",
    "PROFESIONAL(MEDICO)",
]
_EPS_EJERCITO = (
    "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG"
)
_FILAS_INICIAL = [
    ["YESID PEREZ", "4/05/2026", "24/04/2026", "28/04/2026", "28/04/2026",
     _EPS_EJERCITO, "HUS0000499027", "174667", " 2.359.398 ", "19/05/2026",
     "N", "2", "", "", "", "ELIAS ALFONSO CARVAJAL NAVARRO",
     "Administrativo", ""],
    ["YESID PEREZ", "4/05/2026", "24/04/2026", "28/04/2026", "28/04/2026",
     _EPS_EJERCITO, "HUS0000500478", "174668", " 31.016 ", "19/05/2026",
     "N", "2", "", "", "", "ELIAS ALFONSO CARVAJAL NAVARRO",
     "Administrativo", ""],
]

_HEADER_RATIFICADA = [
    "RESPONSABLE", "FECHA ENTREGA", "FECHA DE DOCUMENTO (DGH)",
    "FECHA NOTIFICACION OBJECION", "EMPRESA", "NUMERO DE FACTURA",
    "CONSECUTIVO DGH", "VALOR GLOSA", "FECHA VENCIMIENTO",
    "OBSERVACION RECEPCION", "TECNICO QUE RECEPCIONO",
]
_FILAS_RATIFICADA = [
    ["EQUIPO ASEGURADORAS", "4/05/2026", "29/04/2026", "29/04/2026",
     "U220154 - COMPANIA MUNDIAL DE SEGUROS S.A.  SOAT UVB",
     "HUS0000469342", "174697", " 4.081.405 ", "11/05/2026", "",
     "JOHAN DANIEL FONCE PINZON"],
    ["EQUIPO ASEGURADORAS", "4/05/2026", "29/04/2026", "29/04/2026",
     "U220073 - AXA COLPATRIA SEGUROS S.A. SOAT UVB",
     "HUS0000466385", "174611", " 2.363.547 ", "11/05/2026", "",
     "CAMILO ALEJANDRO CASTILLO MENDEZ"],
]


@pytest.fixture
def db_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


def _excel_inicial_y_ratificada() -> bytes:
    """Replica el export real: hoja INICIAL + hoja RATIFICADA, cada una con
    su fila título antes del encabezado (como el DGH la entrega)."""
    wb = Workbook()
    ws_i = wb.active
    ws_i.title = "INICIAL"
    ws_i.append(["ENTREGA GLOSA INICIAL"])
    ws_i.append(_HEADER_INICIAL)
    for fila in _FILAS_INICIAL:
        ws_i.append(fila)

    ws_r = wb.create_sheet("RATIFICADA")
    ws_r.append(["ENTREGA GLOSA RATIFICADA"])
    ws_r.append(_HEADER_RATIFICADA)
    for fila in _FILAS_RATIFICADA:
        ws_r.append(fila)

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_solo_inicial_va_a_la_ia_ratificada_no(db_session):
    r = RecepcionService(db_session).procesar_excel(
        _excel_inicial_y_ratificada()
    )

    # Las 4 glosas entran (2 INICIAL + 2 RATIFICADA).
    assert r.total == 4, f"errores={r.errores} omitidas={r.filas_omitidas}"
    assert r.creadas == 4
    assert r.ratificadas == 2

    inicial_ids = {
        g.id
        for g in db_session.query(GlosaRecord)
        .filter(GlosaRecord.estado == "RADICADA")
        .all()
    }
    ratificada_ids = {
        g.id
        for g in db_session.query(GlosaRecord)
        .filter(GlosaRecord.estado == "RATIFICADA")
        .all()
    }
    assert len(inicial_ids) == 2
    assert len(ratificada_ids) == 2

    # Solo las INICIAL (RADICADA) van al cerebro IA.
    para_ia = set(r.glosas_ids_para_auto_responder)
    assert inicial_ids.issubset(para_ia)
    assert ratificada_ids.isdisjoint(para_ia), (
        "Las RATIFICADA NO deben ir a la IA (ya tienen texto fijo)"
    )
    assert len(para_ia) == 2

    # Pero TODAS (incl. RATIFICADA) entran al Excel-respuesta.
    todas = set(r.glosas_ids_todas)
    assert inicial_ids.issubset(todas)
    assert ratificada_ids.issubset(todas)
    assert len(todas) == 4

    # La RATIFICADA trae su dictamen de texto fijo; la INICIAL queda pendiente.
    g_rat = (
        db_session.query(GlosaRecord)
        .filter(GlosaRecord.factura == "HUS0000469342")
        .first()
    )
    assert "RESPUESTA A GLOSA RATIFICADA" in (g_rat.dictamen or "")
    g_ini = (
        db_session.query(GlosaRecord)
        .filter(GlosaRecord.factura == "HUS0000499027")
        .first()
    )
    assert "Pendiente de análisis" in (g_ini.dictamen or "")
