"""Tests del endpoint /glosas/{id}/firma-dictamen (R84 P1)."""
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


def _seed(db, dictamen):
    g = GlosaRecord(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado="RADICADA",
        dictamen=dictamen, creado_en=ahora_utc(),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestFirmaDictamen:
    def test_404_glosa_inexistente(self, client):
        r = client.get("/glosas/99999/firma-dictamen")
        assert r.status_code == 404

    def test_400_sin_dictamen(self, client, db_session):
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/firma-dictamen")
        assert r.status_code == 400

    def test_devuelve_firma_completa(self, client, db_session):
        g = _seed(db_session, dictamen="<p>contenido del dictamen</p>")
        r = client.get(f"/glosas/{g.id}/firma-dictamen")
        assert r.status_code == 200, r.text
        d = r.json()
        # Estructura
        assert d["glosa_id"] == g.id
        assert "hash" in d
        assert "firma" in d
        assert "timestamp" in d
        assert "firmante" in d
        assert "alg" in d
        # Firmante = current_user
        assert d["firmante"] == "auditor@hus.com"
        # Hash es SHA256 (64 hex chars)
        assert len(d["hash"]) == 64
        # Firma no vacía
        assert len(d["firma"]) > 10

    def test_dictamen_diferente_genera_hash_diferente(self, client, db_session):
        g1 = _seed(db_session, dictamen="<p>texto A</p>")
        g2 = _seed(db_session, dictamen="<p>texto B distinto</p>")
        r1 = client.get(f"/glosas/{g1.id}/firma-dictamen")
        r2 = client.get(f"/glosas/{g2.id}/firma-dictamen")
        assert r1.json()["hash"] != r2.json()["hash"]

    def test_hash_estable_para_mismo_contenido(self, client, db_session):
        """Mismo dictamen → mismo hash, distintas firmas (timestamp distinto)."""
        g = _seed(db_session, dictamen="<p>idéntico</p>")
        r1 = client.get(f"/glosas/{g.id}/firma-dictamen")
        r2 = client.get(f"/glosas/{g.id}/firma-dictamen")
        # Hash idéntico (mismo input)
        assert r1.json()["hash"] == r2.json()["hash"]
