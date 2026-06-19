"""Regresión de performance: el procesamiento de hojas CONCEPTOS (I/R)
del DGH re-resolvía la glosa padre con 3 queries POR FILA y re-logueaba
el mismo fallback cientos de veces (importación tardaba MINUTOS / parecía
colgada). Con cache por (factura, consecutivo): se resuelve una vez y se
loguea una sola vez por factura.
"""

import logging
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import ConceptoGlosaRecord, GlosaRecord
from app.services.recepcion_service import RecepcionService

_HDR_INI = [
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
    "DEVOLUCION S/N",
    "DIAS RADICACION VS RECEPCION",
    "RADICADO",
    "REFERENCIA",
    "OBSERVACION TECNICO",
    "TECNICO QUE RECEPCIONO",
    "TIPO GLOSA",
    "PROFESIONAL(MEDICO)",
]
# Glosa INICIAL SIN consecutivo → fuerza el Fallback 1 en CONCEPTOS.
_ROW_INI = [
    "YESID PEREZ",
    "28/04/2026",
    "14/04/2026",
    "24/04/2026",
    "24/04/2026",
    "U240061 - FOMAG",
    "HUS0000496016",
    "",
    " 1.234,50 ",
    "14/05/2026",
    "N",
    "4",
    "",
    "",
    "",
    "ELIAS CARVAJAL",
    "",
    "Administrativo",
]
_HDR_CON = [
    "FacturaCartera.Factura",
    "Consecutivo",
    "ListadoConceptos.ConceptoObjecion.Codigo",
    "ListadoConceptos.Oid",
    "ListadoConceptos.ConceptoObjecion.Nombre",
    "ListadoConceptos.ValorObjecion",
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


def _excel(n_conceptos: int) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "INICIAL"
    ws.append(["ENTREGA GLOSA INICIAL"])
    ws.append(_HDR_INI)
    ws.append(_ROW_INI)
    ci = wb.create_sheet("I")
    ci.append(_HDR_CON)
    for k in range(n_conceptos):
        ci.append(
            [
                "HUS0000496016",
                "174999",
                "TA0201",
                f"OID-{k}",
                "Diferencia de valores pactados",
                "100",
            ]
        )
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_conceptos_cache_resuelve_padre_una_vez(db_session, caplog):
    with caplog.at_level(logging.INFO, logger="motor_glosas"):
        r = RecepcionService(db_session).procesar_excel(_excel(6))

    # La glosa INICIAL entró y los 6 conceptos quedaron vinculados.
    assert r.total == 1
    assert r.conceptos_creados == 6
    assert r.conceptos_huerfanos == []

    g = db_session.query(GlosaRecord).first()
    assert g is not None
    # El consecutivo se completó vía Fallback 1.
    assert g.consecutivo_dgh == "174999"
    assert (
        db_session.query(ConceptoGlosaRecord).filter(ConceptoGlosaRecord.glosa_id == g.id).count()
        == 6
    )

    # CLAVE: el "Fallback match" se loguea UNA sola vez (no una por fila).
    fallback_logs = [m for m in caplog.messages if "[I/R] Fallback match" in m]
    assert len(fallback_logs) == 1, f"esperaba 1 log de fallback, hubo {len(fallback_logs)}"
