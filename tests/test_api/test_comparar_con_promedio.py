"""Tests del endpoint GET /glosas/{id}/comparar-con-promedio (R133 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


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
def usuario():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, eps="SANITAS", codigo="TA0201", valor=10000, estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestCompararConPromedio:
    def test_404(self, client):
        r = client.get("/glosas/99999/comparar-con-promedio")
        assert r.status_code == 404

    def test_sin_cohorte(self, client, db_session):
        # Glosa única en su cohorte
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/comparar-con-promedio")
        d = r.json()
        assert "razon_no_evaluable" in d

    def test_compara_con_cohorte(self, client, db_session):
        # Glosa target: $10k
        g = _seed(db_session, valor=10000)
        # Cohorte: $5k, $15k, $20k → promedio $13.33k
        _seed(db_session, valor=5000)
        _seed(db_session, valor=15000)
        _seed(db_session, valor=20000)

        r = client.get(f"/glosas/{g.id}/comparar-con-promedio")
        d = r.json()
        assert d["cohorte"]["count"] == 3
        assert 13000 < d["cohorte"]["valor_promedio"] < 14000
        # 10k está entre 5k y 15k → percentil ~33%
        assert 30 <= d["posicion"]["percentil_valor"] <= 40

    def test_valor_atipico_alto(self, client, db_session):
        # Glosa target: $1M (atípica)
        g = _seed(db_session, valor=1_000_000)
        # Cohorte: 4 glosas de ~$10k
        for _ in range(4):
            _seed(db_session, valor=10000)

        r = client.get(f"/glosas/{g.id}/comparar-con-promedio")
        d = r.json()
        # ratio_vs_promedio = 1_000_000 / 10_000 = 100x
        assert d["flags"]["valor_atipico"] is True

    def test_aislamiento_por_cohorte(self, client, db_session):
        # Glosa target: SANITAS+TA0201
        g = _seed(db_session, eps="SANITAS", codigo="TA0201",
                  valor=10000)
        # Cohorte directo (mismo eps+codigo)
        _seed(db_session, eps="SANITAS", codigo="TA0201", valor=5000)
        # Otro EPS — NO debe entrar en cohorte
        _seed(db_session, eps="NUEVA EPS", codigo="TA0201",
              valor=999_999)
        # Mismo EPS pero distinto código — NO debe entrar
        _seed(db_session, eps="SANITAS", codigo="FA0603",
              valor=999_999)

        r = client.get(f"/glosas/{g.id}/comparar-con-promedio")
        d = r.json()
        assert d["cohorte"]["count"] == 1
        assert d["cohorte"]["valor_promedio"] == 5000.0
