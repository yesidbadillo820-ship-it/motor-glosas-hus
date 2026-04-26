"""Tests del endpoint GET /usuarios/{id}/actividad (R95 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, GlosaRecord, UsuarioRecord


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
def usuario_coord(db_session):
    u = UsuarioRecord(
        id=1, email="coord@hus.gov.co", nombre="Coord", rol="COORDINADOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def usuario_target(db_session):
    u = UsuarioRecord(
        id=2, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_audit(db, usuario, accion, tabla, dias_atras=0):
    db.add(AuditLogRecord(
        usuario_email=usuario, usuario_rol="AUDITOR",
        accion=accion, tabla=tabla,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


def _seed_glosa(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestUsuarioActividad:
    def test_404(self, client):
        r = client.get("/usuarios/99999/actividad")
        assert r.status_code == 404

    def test_usuario_sin_actividad(self, client, usuario_target):
        r = client.get(f"/usuarios/{usuario_target.id}/actividad")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["usuario"]["email"] == "alice@hus.com"
        assert d["audit"]["total_eventos"] == 0
        assert d["glosas"]["asignadas_como_gestor"] == 0
        assert d["glosas"]["auditadas"] == 0

    def test_cuenta_eventos_audit(self, client, db_session, usuario_target):
        _seed_audit(db_session, "alice@hus.com", "UPDATE", "glosas")
        _seed_audit(db_session, "alice@hus.com", "UPDATE", "glosas")
        _seed_audit(db_session, "alice@hus.com", "DELETE", "usuarios")
        # Ruido de otro usuario
        _seed_audit(db_session, "bob@hus.com", "UPDATE", "glosas")

        r = client.get(f"/usuarios/{usuario_target.id}/actividad")
        d = r.json()
        assert d["audit"]["total_eventos"] == 3
        assert d["audit"]["por_accion"] == {"UPDATE": 2, "DELETE": 1}
        assert d["audit"]["por_tabla"] == {"glosas": 2, "usuarios": 1}

    def test_excluye_eventos_fuera_de_ventana(self, client, db_session,
                                              usuario_target):
        _seed_audit(db_session, "alice@hus.com", "X", "T", dias_atras=5)
        _seed_audit(db_session, "alice@hus.com", "X", "T", dias_atras=60)
        r = client.get(f"/usuarios/{usuario_target.id}/actividad")
        d = r.json()
        # default 30 días → solo 1
        assert d["audit"]["total_eventos"] == 1

    def test_ventana_custom(self, client, db_session, usuario_target):
        _seed_audit(db_session, "alice@hus.com", "X", "T", dias_atras=5)
        _seed_audit(db_session, "alice@hus.com", "X", "T", dias_atras=60)
        r = client.get(f"/usuarios/{usuario_target.id}/actividad?dias=90")
        d = r.json()
        assert d["audit"]["total_eventos"] == 2
        assert d["ventana_dias"] == 90

    def test_glosas_asignadas_y_auditadas(self, client, db_session,
                                          usuario_target):
        # gestor_nombre = nombre del usuario
        _seed_glosa(db_session, gestor_nombre="Alice")
        _seed_glosa(db_session, gestor_nombre="Alice")
        _seed_glosa(db_session, auditor_email="alice@hus.com")
        # Otra de Bob
        _seed_glosa(db_session, gestor_nombre="Bob")

        r = client.get(f"/usuarios/{usuario_target.id}/actividad")
        d = r.json()
        assert d["glosas"]["asignadas_como_gestor"] == 2
        assert d["glosas"]["auditadas"] == 1
