"""El endpoint /glosas/importar-recepcion procesa en background:
responde al instante con PROCESANDO y el id; el BackgroundTask hace
el parseo y deja el resumen disponible en /status. Garantiza que un
Excel pesado NO bloquee el worker (incidente 2026-05-19)."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


@pytest.fixture
def engine_mem():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


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
    ws.append(
        [
            "YESID PEREZ",
            "DISAN EJERCITO",
            "HUS0000500077",
            "175108",
            "1.234,50",
            "05/05/2026",
            "25/05/2026",
        ]
    )
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_importar_recepcion_async_flow(engine_mem, tmp_path, monkeypatch):
    monkeypatch.setenv("SOPORTES_ROOT", str(tmp_path))
    Session = sessionmaker(bind=engine_mem)

    # SessionLocal usado por el background → engine en memoria
    import app.database as dbmod

    monkeypatch.setattr(dbmod, "SessionLocal", Session)

    # Mockear lo pesado/externo que dispara el background
    import app.services.auto_responder_service as ar
    import app.services.email_service as es
    import app.services.posthog_service as ph

    async def _fake_lote(*a, **k):
        return {"excel_emails": {"enviados": 0}}

    async def _fake_resumen_email(*a, **k):
        return 0

    monkeypatch.setattr(ar, "procesar_lote_y_enviar_excel", _fake_lote)
    monkeypatch.setattr(es, "enviar_resumen_importacion_recepcion", _fake_resumen_email)
    monkeypatch.setattr(ph, "capture", lambda *a, **k: None)

    from app.api.deps import get_usuario_actual
    from app.main import app

    u = UsuarioRecord(
        id=1, email="y@hus.com", nombre="Y", rol="AUDITOR", activo=1, password_hash="x"
    )
    app.dependency_overrides[get_db] = lambda: iter([Session()]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u

    try:
        c = TestClient(app)
        files = {
            "archivo": (
                "recepcion.xlsx",
                _excel(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        r = c.post("/glosas/importar-recepcion", files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estado"] == "PROCESANDO"
        assert d["procesando"] is True
        rec_id = d["recepcion_import_id"]
        assert rec_id

        # TestClient corre los BackgroundTasks antes de devolver el control,
        # así que el procesamiento ya terminó: /status debe traer resumen.
        s = c.get(f"/glosas/importar-recepcion/{rec_id}/status")
        assert s.status_code == 200, s.text
        sd = s.json()
        assert sd["procesando"] is False
        assert sd["resumen"] is not None
        assert sd["resumen"]["total"] == 1
        assert sd["resumen"]["recepcion_import_id"] == rec_id
        # El valor monetario en formato colombiano se parseó bien.
        from app.models.db import GlosaRecord

        g = Session().query(GlosaRecord).first()
        assert abs(float(g.valor_objetado) - 1234.50) < 0.01

        # Historial lo lista y es descargable.
        h = c.get("/glosas/importar-recepcion/historial")
        assert h.status_code == 200
        ids = [x["id"] for x in h.json()["importaciones"]]
        assert rec_id in ids
    finally:
        app.dependency_overrides.clear()


def test_status_404_si_no_existe(engine_mem, monkeypatch):
    Session = sessionmaker(bind=engine_mem)
    from app.api.deps import get_usuario_actual
    from app.main import app

    u = UsuarioRecord(
        id=1, email="y@hus.com", nombre="Y", rol="AUDITOR", activo=1, password_hash="x"
    )
    app.dependency_overrides[get_db] = lambda: iter([Session()]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    try:
        c = TestClient(app)
        r = c.get("/glosas/importar-recepcion/99999/status")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
