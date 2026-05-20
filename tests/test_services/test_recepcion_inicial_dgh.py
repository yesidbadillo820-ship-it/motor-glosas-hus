"""Regresión del bug real: la hoja INICIAL del export DGH tenía el
encabezado más allá de la fila 5 (fila título "ENTREGA GLOSA INICIAL"
+ filas de formato), y el detector la descartaba entera → las glosas
INICIAL (las nuevas) NO se importaban. Solo entraban las RATIFICADA.
Estructura y valores tomados del archivo real del usuario."""

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
    "RESPONSABLE",
    "FECHA DE ENTREGA",
    "FECHA RADICACION",
    "FECHA DOCUMENTO DGH",
    "FECHA RECEPCION",
    "ENTIDAD",
    "FACTURA",
    "CONSECUTIVO DGH",
    "VALOR GLOSA",
    "VENCE",
    "DEVOLUCION \nS/N",
    "DIAS \nRADICACION VS RECEPCION",
    "RADICADO",
    "REFERENCIA",
    "OBSERVACION TECNICO",
    "TECNICO QUE RECEPCIONO",
    "TIPO GLOSA",
    "PROFESIONAL(MEDICO)",
]
_FILA = [
    "YESID PEREZ",
    "28/04/2026",
    "14/04/2026",
    "24/04/2026",
    "24/04/2026",
    "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG",
    "HUS0000494973",
    "171863",
    " 1.211.302 ",
    "14/05/2026",
    "N",
    "8",
    "",
    "",
    "",
    "ELIAS ALFONSO CARVAJAL NAVARRO",
    "",
    "Administrativo",
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


def _excel_dgh_real() -> bytes:
    """Reproduce la hoja INICIAL real: título + filas de formato ANTES
    del encabezado (lo empuja más allá de la antigua ventana de 5)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "INICIAL"
    ws.append(["ENTREGA GLOSA INICIAL"])  # fila 1: título
    for _ in range(6):  # filas 2-7: formato/blank
        ws.append([])
    ws.append(_HEADER_INICIAL)  # fila 8: encabezado real
    ws.append(_FILA)  # fila 9: datos
    ws.append(
        _FILA[:6]
        + [
            "HUS0000495362",
            "171865",
            " 5.892.038 ",
            "14/05/2026",
            "N",
            "8",
            "",
            "",
            "",
            "ELIAS ALFONSO CARVAJAL NAVARRO",
            "",
            "Administrativo",
        ]
    )
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_inicial_con_encabezado_mas_alla_de_fila_5_se_importa(db_session):
    r = RecepcionService(db_session).procesar_excel(_excel_dgh_real())

    # Antes: total=0 (hoja descartada). Ahora: las 2 glosas INICIAL entran.
    assert r.total == 2, f"errores={r.errores} omitidas={r.filas_omitidas}"
    assert r.creadas == 2
    assert len(r.glosas_ids_todas) == 2

    # Valores en formato colombiano parseados correctamente (no ×100).
    valores = sorted(float(g.valor_objetado) for g in db_session.query(GlosaRecord).all())
    assert abs(valores[0] - 1211302.0) < 0.01
    assert abs(valores[1] - 5892038.0) < 0.01

    # Factura y entidad mapeadas bien desde el encabezado real.
    g = db_session.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000494973").first()
    assert g is not None
    assert "EJERCITO" in (g.eps or "").upper()
