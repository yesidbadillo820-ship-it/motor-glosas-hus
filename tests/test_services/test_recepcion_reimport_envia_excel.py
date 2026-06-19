"""Regresión del bug: reimportar un Excel ya cargado (solo duplicados)
NO enviaba ningún correo a los gestores.

Cubre:
  1. recepcion_service: los IDs de glosas duplicadas se acumulan en
     `resumen.glosas_ids_todas` (aunque `total`/`para_auto` queden en 0).
  2. auto_responder: con `ids_ia=[]` NO se corre el lote IA pero el
     Excel-respuesta SÍ se envía; el background se programa igual.
"""

from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.recepcion_service import RecepcionService


@pytest.fixture
def anyio_backend():
    return "asyncio"


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


def _excel_recepcion() -> bytes:
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
    ws.append(
        ["JUAN PEREZ", "SURA EPS", "FAC-001", "C-001", "1.234.567,89", "01/03/2026", "31/12/2026"]
    )
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_reimport_acumula_ids_en_glosas_ids_todas(db_session):
    contenido = _excel_recepcion()

    r1 = RecepcionService(db_session).procesar_excel(contenido)
    assert r1.total == 1
    assert len(r1.glosas_ids_todas) == 1
    assert len(r1.glosas_ids_para_auto_responder) == 1

    # Segunda importación idéntica → 100% duplicada.
    r2 = RecepcionService(db_session).procesar_excel(contenido)
    assert r2.duplicadas == 1
    assert r2.total == 0
    assert r2.glosas_ids_para_auto_responder == []  # nada para IA
    # PERO la glosa duplicada SÍ queda en glosas_ids_todas → el Excel
    # se puede regenerar/enviar igual.
    assert len(r2.glosas_ids_todas) == 1
    assert r2.glosas_ids_todas[0] == r1.glosas_ids_todas[0]

    # Y el valor monetario se guardó correctamente (no ×100).
    from app.models.db import GlosaRecord

    g = db_session.query(GlosaRecord).first()
    assert abs(float(g.valor_objetado) - 1234567.89) < 0.01


@pytest.mark.anyio
async def test_procesar_lote_y_enviar_excel_sin_ia_no_corre_lote(monkeypatch):
    """ids_ia=[] → NO se invoca procesar_lote, pero SÍ se envía el Excel."""
    import app.services.auto_responder_service as ar

    lote_llamado = {"n": 0}

    async def _fake_procesar_lote(ids):
        lote_llamado["n"] += 1
        return {"respondidas": 0}

    envio_llamado = {"n": 0}

    async def _fake_enviar(resumen, excel_original, glosa_ids, db):
        envio_llamado["n"] += 1
        return {"enviados": 3, "glosa_ids": list(glosa_ids)}

    monkeypatch.setattr(ar, "procesar_lote", _fake_procesar_lote)
    import app.services.email_service as es

    monkeypatch.setattr(
        es,
        "enviar_excel_recepcion_con_respuestas",
        _fake_enviar,
    )

    class _DB:
        def close(self):
            pass

    monkeypatch.setattr(ar, "SessionLocal", lambda: _DB(), raising=False)
    import app.database as dbmod

    monkeypatch.setattr(dbmod, "SessionLocal", lambda: _DB())

    res = await ar.procesar_lote_y_enviar_excel(
        glosa_ids=[10, 11],
        excel_original=b"xlsxbytes",
        resumen={"total": 0},
        ids_ia=[],
    )

    assert lote_llamado["n"] == 0, "no debe correr la IA si ids_ia vacío"
    assert envio_llamado["n"] == 1, "el Excel-respuesta debe enviarse igual"
    assert res.get("lote_omitido") is True
    assert res["excel_emails"]["enviados"] == 3
    assert res["excel_emails"]["glosa_ids"] == [10, 11]


def test_lanzar_background_sin_ia_pero_con_excel_programa_task(monkeypatch):
    """glosa_ids no vacío + ids_ia vacío + excel presente → se programa
    la task (antes: gate en glosa_ids vacío abortaba todo)."""
    import app.services.auto_responder_service as ar

    creado = {"task": False}

    class _Loop:
        def create_task(self, coro):
            creado["task"] = True
            coro.close()
            return "task-obj"

    monkeypatch.setattr(ar.asyncio, "get_event_loop", lambda: _Loop())
    monkeypatch.setattr(ar, "_registrar_bg_task", lambda t, n: t)

    ar.lanzar_lote_y_enviar_excel_background(
        glosa_ids=[5],
        excel_original=b"xlsx",
        resumen={},
        ids_ia=[],
    )
    assert creado["task"] is True
