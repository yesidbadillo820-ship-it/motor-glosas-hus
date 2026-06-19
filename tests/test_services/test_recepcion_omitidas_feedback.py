"""Regresión: las filas/hojas que antes se descartaban en SILENCIO
ahora se reportan (resumen.filas_omitidas, hojas_descartadas, errores)
para que el usuario entienda por qué total=0."""

from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.recepcion_service import RecepcionService


@pytest.fixture
def db_session():
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


def _excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "RECEPCION"
    ws.append(
        [
            "GESTOR",
            "ENTIDAD",
            "FACTURA",
            "CONSECUTIVO DGH",
            "VALOR GLOSA",
            "FECHA RECEPCION",
            "VENCE",
        ]
    )
    ws.append(["JUAN", "SURA", "FAC-1", "C1", "1.000,00", "01/03/2026", "31/12/2026"])  # OK
    ws.append(["PEDRO", "", "FAC-2", "C2", "2.000,00", "01/03/2026", "31/12/2026"])  # sin ENTIDAD
    basura = wb.create_sheet("BASURA")
    basura.append(["col_a", "col_b"])
    basura.append([1, 2])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_filas_y_hojas_omitidas_se_reportan(db_session):
    r = RecepcionService(db_session).procesar_excel(_excel())

    assert r.total == 1
    assert r.filas_omitidas == 1
    assert r.filas_omitidas_detalle[0]["fila"] == 3
    assert "ENTIDAD" in r.filas_omitidas_detalle[0]["motivo"]

    assert len(r.hojas_descartadas) == 1
    assert r.hojas_descartadas[0]["hoja"] == "BASURA"
    assert "factura" in r.hojas_descartadas[0]["columnas_faltantes"]

    # to_dict (lo que ve el frontend) expone los nuevos campos.
    d = r.to_dict()
    assert d["filas_omitidas"] == 1
    assert d["hojas_descartadas"]
    assert any("BASURA" in e for e in d["errores"])
