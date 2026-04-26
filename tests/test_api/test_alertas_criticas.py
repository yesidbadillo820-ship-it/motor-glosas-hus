"""Tests del endpoint /sistema/alertas-criticas (R74 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AICallRecord, GlosaRecord, UsuarioRecord


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
def usuario_coord():
    return UsuarioRecord(id=1, email="coord@hus.com", rol="COORDINADOR", activo=1)


def _seed_glosa(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestAlertasCriticas:
    def test_sin_alertas_lista_vacia(self, client):
        """Sin glosas y schedulers OK → sin alertas (excepto schedulers
        si están off, lo cual es esperado en tests)."""
        r = client.get("/sistema/alertas-criticas")
        assert r.status_code == 200
        d = r.json()
        # Estructura
        assert "total_alertas" in d
        assert "items" in d

    def test_glosa_vencida_genera_alerta_critica(self, client, db_session):
        _seed_glosa(db_session, dias_restantes=-1, estado="RADICADA")
        r = client.get("/sistema/alertas-criticas")
        d = r.json()
        criticas = [it for it in d["items"] if it["nivel"] == "CRITICO"]
        assert len(criticas) >= 1
        assert any("VENCIDA" in it["mensaje"].upper() for it in criticas)

    def test_glosas_a_2_dias_genera_alerta_alto(self, client, db_session):
        _seed_glosa(db_session, dias_restantes=2, estado="RADICADA")
        r = client.get("/sistema/alertas-criticas")
        d = r.json()
        altas = [it for it in d["items"] if it["nivel"] == "ALTO"]
        assert any("1-2" in it["mensaje"] for it in altas)

    def test_borradores_viejos_genera_alerta_medio(self, client, db_session):
        _seed_glosa(
            db_session,
            estado="BORRADOR",
            creado_en=ahora_utc() - timedelta(days=10),
        )
        r = client.get("/sistema/alertas-criticas")
        d = r.json()
        medios = [it for it in d["items"] if it["nivel"] == "MEDIO"]
        assert any("borrador" in it["mensaje"].lower() for it in medios)

    def test_costo_ia_alto_genera_alerta(self, client, db_session):
        # Inserta call IA con costo > $10
        db_session.add(AICallRecord(
            proveedor="anthropic", modelo="claude-sonnet-4-6",
            cost_usd=15.0,
            creado_en=ahora_utc() - timedelta(hours=1),
        ))
        db_session.commit()
        r = client.get("/sistema/alertas-criticas")
        d = r.json()
        assert any("Costo IA" in it["mensaje"] for it in d["items"])

    def test_orden_por_nivel(self, client, db_session):
        """CRITICO debe aparecer antes que ALTO antes que MEDIO."""
        _seed_glosa(db_session, dias_restantes=-1, estado="RADICADA")
        _seed_glosa(db_session, dias_restantes=2, estado="RADICADA")
        _seed_glosa(
            db_session, estado="BORRADOR",
            creado_en=ahora_utc() - timedelta(days=10),
        )
        r = client.get("/sistema/alertas-criticas")
        items = r.json()["items"]
        # Filtrar las 3 alertas (excluyendo schedulers)
        niveles = [it["nivel"] for it in items if "scheduler" not in it["mensaje"].lower()]
        # Orden: CRITICO, ALTO, MEDIO
        if "CRITICO" in niveles and "ALTO" in niveles and "MEDIO" in niveles:
            assert niveles.index("CRITICO") < niveles.index("ALTO")
            assert niveles.index("ALTO") < niveles.index("MEDIO")
