"""Tests del endpoint GET /audit/export.csv (R62 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord


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


@pytest.fixture
def usuario_admin():
    return UsuarioRecord(id=1, email="admin@hus.gov.co", rol="ADMIN", activo=1)


def _seed(db, **kw):
    base = dict(
        usuario_email="auditor@hus.com", usuario_rol="AUDITOR",
        accion="CREAR", tabla="glosas", registro_id=1,
        timestamp=ahora_utc(),
    )
    base.update(kw)
    db.add(AuditLogRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario_admin):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestAuditExportCsv:
    def test_csv_vacio_genera_solo_header(self, client):
        r = client.get("/audit/export.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        # Debe traer al menos la línea del header
        body = r.text
        assert "id,timestamp,usuario_email" in body
        # Y nada más
        lineas = [ln for ln in body.split("\n") if ln.strip()]
        assert len(lineas) == 1

    def test_csv_con_filas(self, client, db_session):
        _seed(db_session, accion="CREAR", usuario_email="X@hus.com")
        _seed(db_session, accion="ELIMINAR", usuario_email="Y@hus.com")
        r = client.get("/audit/export.csv")
        assert r.status_code == 200
        body = r.text
        assert "X@hus.com" in body
        assert "Y@hus.com" in body
        assert "CREAR" in body
        assert "ELIMINAR" in body

    def test_filtro_accion(self, client, db_session):
        _seed(db_session, accion="CREAR")
        _seed(db_session, accion="ELIMINAR")
        r = client.get("/audit/export.csv?accion=ELIMINAR")
        assert r.status_code == 200
        body = r.text
        assert "ELIMINAR" in body
        assert "CREAR" not in body or body.count(",CREAR,") == 0

    def test_filtro_tabla(self, client, db_session):
        _seed(db_session, tabla="glosas")
        _seed(db_session, tabla="contratos")
        r = client.get("/audit/export.csv?tabla=contratos")
        assert r.status_code == 200
        body = r.text
        assert "contratos" in body
        # Glosas filtrado afuera
        assert body.count(",glosas,") == 0

    def test_filtro_fecha_desde(self, client, db_session):
        _seed(db_session, accion="VIEJO",
              timestamp=ahora_utc() - timedelta(days=60))
        _seed(db_session, accion="NUEVO",
              timestamp=ahora_utc() - timedelta(days=2))
        desde = (ahora_utc() - timedelta(days=7)).strftime("%Y-%m-%d")
        r = client.get(f"/audit/export.csv?desde={desde}")
        assert r.status_code == 200
        body = r.text
        assert "NUEVO" in body
        assert "VIEJO" not in body

    def test_filtro_fecha_invalida_no_explota(self, client, db_session):
        """Fecha mal formada debe ignorarse silenciosamente."""
        _seed(db_session)
        r = client.get("/audit/export.csv?desde=NO-ES-FECHA")
        assert r.status_code == 200

    def test_content_disposition_attachment(self, client):
        r = client.get("/audit/export.csv")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".csv" in cd

    def test_truncado_de_campos_largos(self, client, db_session):
        """Campos detalle/valor_anterior >1000 chars se truncan en CSV."""
        _seed(db_session, detalle="X" * 5000)
        r = client.get("/audit/export.csv")
        assert r.status_code == 200
        body = r.text
        # No debería tener una secuencia de 5000 X
        assert "X" * 1500 not in body
