"""Directiva Yesid 2026-05-19: solo las glosas INICIAL pendientes van
al cerebro IA. Las RATIFICADA ya traen TEXTO FIJO → NO deben gastar
tokens/tiempo en la IA, pero SÍ deben salir en el Excel-respuesta.
Headers tomados del archivo real del DGH del usuario.
"""

from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaRecord
from app.services.recepcion_service import RecepcionService

_HDR_INI = [
    "GESTOR",
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
_ROW_INI = [
    "YESID PEREZ",
    "04/05/2026",
    "24/04/2026",
    "28/04/2026",
    "28/04/2026",
    "U220311 - DIRECCION DE SANIDAD EJERCITO",
    "HUS0000499027",
    "174667",
    " 2.359.398 ",
    "19/05/2026",
    "N",
    "2",
    "",
    "",
    "",
    "ELIAS CARVAJAL",
    "",
    "Administrativo",
]
_HDR_RAT = [
    "RESPONSABLE",
    "FECHA ENTREGA",
    "FECHA DE DOCUMENTO (DGH)",
    "FECHA NOTIFICACION OBJECIÓN",
    "EMPRESA",
    "NUMERO DE FACTURA",
    "CONSECUTIVO DGH",
    "VALOR GLOSA",
    "FECHA VENCIMIENTO",
    "OBSERVACION RECEPCION",
    "TECNICO QUE RECEPCIONO",
]
_ROW_RAT = [
    "EQUIPO ASEGURADORAS",
    "04/05/2026",
    "29/04/2026",
    "29/04/2026",
    "U220154 - COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT",
    "HUS0000469342",
    "174697",
    " 4.081.405 ",
    "11/05/2026",
    "",
    "JOHAN FONCE",
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


def _excel() -> bytes:
    wb = Workbook()
    wi = wb.active
    wi.title = "INICIAL"
    wi.append(["ENTREGA GLOSA INICIAL"])
    wi.append(_HDR_INI)
    wi.append(_ROW_INI)
    wr = wb.create_sheet("RATIFICADA")
    wr.append(["ENTREGA GLOSA RATIFICADA"])
    wr.append(_HDR_RAT)
    wr.append(_ROW_RAT)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_ratificada_no_va_a_ia_pero_si_al_excel(db_session):
    r = RecepcionService(db_session).procesar_excel(_excel())

    assert r.total == 2
    assert r.ratificadas == 1

    # Ambas glosas van al Excel-respuesta...
    assert len(r.glosas_ids_todas) == 2
    # ...pero SOLO la INICIAL/RADICADA va al cerebro IA.
    assert len(r.glosas_ids_para_auto_responder) == 1

    rad = db_session.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000499027").first()
    rat = db_session.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000469342").first()
    assert rad is not None and rat is not None
    assert rat.estado == "RATIFICADA"
    # La ratificada trae el TEXTO FIJO, no un placeholder de IA pendiente.
    assert "RATIFICADA" in (rat.dictamen or "").upper()

    # El único id para IA es el de la INICIAL, NO el de la ratificada.
    assert r.glosas_ids_para_auto_responder == [rad.id]
    assert rat.id in r.glosas_ids_todas
    assert rat.id not in r.glosas_ids_para_auto_responder
