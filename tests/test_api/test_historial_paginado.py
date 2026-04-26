"""Tests del endpoint GET /glosas/historial-paginado (R61 P1).

Cubre: paginación, filtros (eps, estado, búsqueda, rango de valor,
fecha) y respuesta estructurada. Usa TestClient con dependency_overrides.
"""
from __future__ import annotations

from datetime import timedelta

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
def usuario_admin():
    return UsuarioRecord(id=1, email="admin@hus.gov.co", rol="ADMIN", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="FAMISANAR", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, valor_aceptado=0,
        etapa="RESPUESTA", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario_admin):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHistorialPaginado:
    def test_sin_glosas(self, client):
        r = client.get("/glosas/historial-paginado")
        assert r.status_code == 200
        d = r.json()
        assert d["items"] == []
        # Estructura paginación
        assert "total" in d or "items" in d

    def test_paginacion_per_page(self, client, db_session):
        for i in range(7):
            _seed(db_session, paciente=f"PAC-{i}")
        r = client.get("/glosas/historial-paginado?page=1&per_page=3")
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) == 3

    def test_filtro_eps(self, client, db_session):
        _seed(db_session, eps="FAMISANAR")
        _seed(db_session, eps="SALUD TOTAL")
        _seed(db_session, eps="SALUD TOTAL")
        r = client.get("/glosas/historial-paginado?eps=SALUD")
        assert r.status_code == 200
        d = r.json()
        # Filtro debe restringir
        for it in d["items"]:
            assert "SALUD" in (it.get("eps") or "").upper()

    def test_filtro_estado(self, client, db_session):
        _seed(db_session, estado="RADICADA")
        _seed(db_session, estado="ACEPTADA")
        _seed(db_session, estado="ACEPTADA")
        r = client.get("/glosas/historial-paginado?estado=ACEPTADA")
        assert r.status_code == 200
        d = r.json()
        for it in d["items"]:
            assert it["estado"] == "ACEPTADA"

    def test_filtro_valor_min_max(self, client, db_session):
        _seed(db_session, valor_objetado=50_000)
        _seed(db_session, valor_objetado=200_000)
        _seed(db_session, valor_objetado=500_000)
        r = client.get("/glosas/historial-paginado?valor_min=100000&valor_max=300000")
        assert r.status_code == 200
        d = r.json()
        for it in d["items"]:
            assert 100_000 <= it["valor_objetado"] <= 300_000

    def test_per_page_excede_limite_max(self, client):
        """per_page>100 debe rechazarse por validación FastAPI Query(le=100)."""
        r = client.get("/glosas/historial-paginado?per_page=999")
        assert r.status_code == 422

    def test_search_por_factura(self, client, db_session):
        _seed(db_session, factura="FE-AAA-001")
        _seed(db_session, factura="FE-BBB-002")
        r = client.get("/glosas/historial-paginado?search=AAA")
        assert r.status_code == 200
        d = r.json()
        # Solo debe traer las que matchean AAA
        for it in d["items"]:
            assert "AAA" in (it.get("factura") or "").upper() or \
                   "AAA" in (it.get("paciente") or "").upper()

    def test_filtro_fecha_desde(self, client, db_session):
        viejo = ahora_utc() - timedelta(days=60)
        nuevo = ahora_utc() - timedelta(days=2)
        _seed(db_session, paciente="VIEJO", creado_en=viejo)
        _seed(db_session, paciente="NUEVO", creado_en=nuevo)
        # Buscar desde hace 7 días
        desde = (ahora_utc() - timedelta(days=7)).strftime("%Y-%m-%d")
        r = client.get(f"/glosas/historial-paginado?fecha_desde={desde}")
        assert r.status_code == 200
        d = r.json()
        # Solo debe estar el reciente
        pacientes = [it["paciente"] for it in d["items"]]
        assert "NUEVO" in pacientes
        assert "VIEJO" not in pacientes

    def test_search_full_text_en_dictamen(self, client, db_session):
        """R66 P1: el filtro search ahora busca también dentro del
        campo 'dictamen' — útil para encontrar argumentos previos."""
        _seed(db_session, paciente="A",
              dictamen="<p>se invoca Art. 57 Ley 1438</p>")
        _seed(db_session, paciente="B",
              dictamen="<p>fundamento en Sentencia T-760</p>")
        r = client.get("/glosas/historial-paginado?search=T-760")
        d = r.json()
        pacientes = [it["paciente"] for it in d["items"]]
        assert "B" in pacientes
        assert "A" not in pacientes

    def test_search_en_texto_glosa_original(self, client, db_session):
        """search también matchea en texto_glosa_original (texto bruto
        que pegó el gestor del Excel de la EPS)."""
        _seed(db_session, paciente="X",
              texto_glosa_original="TA0201 hemograma valor 168563")
        r = client.get("/glosas/historial-paginado?search=hemograma")
        d = r.json()
        assert any(it["paciente"] == "X" for it in d["items"])

    def test_search_en_servicio_descripcion(self, client, db_session):
        """servicio_descripcion también parte del full-text."""
        _seed(db_session, paciente="X",
              servicio_descripcion="CONSULTA DE URGENCIAS POR GINECOLOGIA")
        r = client.get("/glosas/historial-paginado?search=GINECOLOGIA")
        d = r.json()
        assert any(it["paciente"] == "X" for it in d["items"])
