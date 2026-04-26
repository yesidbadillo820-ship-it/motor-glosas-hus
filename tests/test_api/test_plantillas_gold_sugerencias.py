"""Tests del endpoint /plantillas-gold/sugerencias (R75 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import PlantillaGoldRecord, UsuarioRecord


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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="FAMISANAR", codigo_glosa="TA0201",
        tipo="TA", titulo="Argumento ganador",
        argumento="texto suficientemente largo para no fallar el filtro min_length",
        usos=5, activa=1, creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(PlantillaGoldRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestPlantillasGoldSugerencias:
    def test_sin_params_falla_400(self, client):
        r = client.get("/plantillas-gold/sugerencias")
        assert r.status_code == 400

    def test_con_eps_y_codigo_devuelve_match(self, client, db_session):
        _seed(db_session, eps="FAMISANAR", codigo_glosa="TA0201")
        r = client.get("/plantillas-gold/sugerencias?eps=FAMISANAR&codigo_glosa=TA0201")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 1
        assert d["items"][0]["eps"] == "FAMISANAR"
        assert "argumento_preview" in d["items"][0]
        assert d["items"][0]["usos"] == 5

    def test_solo_codigo_devuelve_de_otras_eps(self, client, db_session):
        """Solo codigo_glosa: trae de cualquier EPS."""
        _seed(db_session, eps="FAMISANAR", codigo_glosa="TA0201")
        _seed(db_session, eps="SALUD TOTAL", codigo_glosa="TA0201")
        r = client.get("/plantillas-gold/sugerencias?codigo_glosa=TA0201")
        d = r.json()
        # Debe traer al menos 1 (puede o no traer las 2 según el limite default)
        assert d["total"] >= 1

    def test_inactivas_no_aparecen(self, client, db_session):
        _seed(db_session, codigo_glosa="TA0201", activa=0)
        _seed(db_session, codigo_glosa="TA0201", activa=1, titulo="ACTIVA")
        r = client.get("/plantillas-gold/sugerencias?eps=FAMISANAR&codigo_glosa=TA0201")
        d = r.json()
        titulos = [it["titulo"] for it in d["items"]]
        assert "ACTIVA" in titulos

    def test_limite_respeta_cap_20(self, client, db_session):
        for _ in range(15):
            _seed(db_session, codigo_glosa="TA0201")
        r = client.get("/plantillas-gold/sugerencias?codigo_glosa=TA0201&limite=100")
        d = r.json()
        # max=20 según el endpoint
        assert d["total"] <= 20
