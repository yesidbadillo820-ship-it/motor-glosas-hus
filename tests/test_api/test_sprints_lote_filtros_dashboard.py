"""Tests de los Sprints #3, #4, #5, #6 y #7.

Cubre los nuevos endpoints:
  • PATCH /glosas/decision-eps-lote   (Sprint #4)
  • GET   /glosas/similares-bloque    (Sprint #3)
  • GET   /glosas/mis-asignaciones?vista=...  (Sprint #5)
  • GET   /glosas/vencen-24h          (Sprint #6)
  • GET   /glosas/dashboard-plata-recuperada  (Sprint #7)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord, ContratoRecord


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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
        nombre="ADMIN",
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual, get_auditor_o_superior
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    app.dependency_overrides[get_auditor_o_superior] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_glosa(db, **kw):
    defaults = dict(
        eps="SALUD TOTAL", paciente="JUAN", factura="F1",
        codigo_glosa="TA0201", valor_objetado=100000.0, etapa="INICIAL",
        estado="RADICADA", creado_en=ahora_utc(), dias_restantes=10,
        cups_servicio="890301",
    )
    defaults.update(kw)
    g = GlosaRecord(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# ─── Sprint #4 — Decisión EPS en lote ────────────────────────────────
class TestDecisionEpsLote:
    def test_levantada_marca_recuperado_y_estado(self, client, db_session):
        g1 = _seed_glosa(db_session, factura="F1", valor_objetado=500000)
        g2 = _seed_glosa(db_session, factura="F2", valor_objetado=300000)

        r = client.patch(
            "/glosas/decision-eps-lote",
            json={"glosa_ids": [g1.id, g2.id], "decision_eps": "LEVANTADA"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["procesadas"] == 2
        assert d["valor_recuperado_total"] == 800000
        # Verificar persistencia en DB
        db_session.expire_all()
        gg1 = db_session.get(GlosaRecord, g1.id)
        assert gg1.estado == "LEVANTADA"
        assert gg1.valor_recuperado == 500000

    def test_decision_invalida_400(self, client, db_session):
        g = _seed_glosa(db_session)
        r = client.patch(
            "/glosas/decision-eps-lote",
            json={"glosa_ids": [g.id], "decision_eps": "INVENTADA"},
        )
        assert r.status_code == 400

    def test_lista_vacia_422(self, client):
        r = client.patch(
            "/glosas/decision-eps-lote",
            json={"glosa_ids": [], "decision_eps": "LEVANTADA"},
        )
        assert r.status_code == 422  # min_length=1

    def test_glosa_inexistente_va_a_fallidas(self, client, db_session):
        g = _seed_glosa(db_session)
        r = client.patch(
            "/glosas/decision-eps-lote",
            json={"glosa_ids": [g.id, 99999], "decision_eps": "LEVANTADA"},
        )
        d = r.json()
        assert d["procesadas"] == 1
        assert len(d["fallidas"]) == 1
        assert d["fallidas"][0]["glosa_id"] == 99999


# ─── Sprint #3 — Similares en bloque ─────────────────────────────────
class TestSimilaresBloque:
    def test_agrupa_glosas_misma_combinacion(self, client, db_session):
        # 3 glosas (SALUD TOTAL, TA0201, 890301) — agrupable
        for i in range(3):
            _seed_glosa(db_session, factura=f"F{i}", valor_objetado=100000)
        # 1 glosa de otra combinación — NO agrupable (queda sola)
        _seed_glosa(
            db_session, factura="OTRA", codigo_glosa="SO0101",
            cups_servicio="999999",
        )
        r = client.get("/glosas/similares-bloque")
        assert r.status_code == 200
        d = r.json()
        # Solo el grupo de 3 (los grupos de 1 se filtran)
        assert d["total_grupos"] == 1
        g = d["grupos"][0]
        assert g["n_glosas"] == 3
        assert g["valor_total"] == 300000
        assert g["codigo_glosa"] == "TA0201"

    def test_excluye_levantadas(self, client, db_session):
        _seed_glosa(db_session, factura="F1")
        _seed_glosa(db_session, factura="F2", estado="LEVANTADA")
        r = client.get("/glosas/similares-bloque")
        d = r.json()
        # Solo queda 1, no agrupa
        assert d["total_grupos"] == 0


# ─── Sprint #5 — Vistas guardadas ────────────────────────────────────
class TestVistasGuardadas:
    def test_vista_alta_cuantia(self, client, db_session):
        _seed_glosa(db_session, factura="F1", valor_objetado=10_000_000)
        _seed_glosa(db_session, factura="F2", valor_objetado=200_000)
        r = client.get("/glosas/mis-asignaciones?vista=alta_cuantia&todas=true")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["factura"] == "F1"

    def test_vista_requieren_soportes(self, client, db_session):
        _seed_glosa(db_session, factura="F1", estado="REQUIERE_SOPORTES")
        _seed_glosa(db_session, factura="F2", estado="RADICADA")
        r = client.get("/glosas/mis-asignaciones?vista=requieren_soportes&todas=true")
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["factura"] == "F1"

    def test_vista_ta_sin_contrato(self, client, db_session):
        # SALUD TOTAL sin contrato + TA0201 → entra
        _seed_glosa(
            db_session, factura="F1", eps="SALUD TOTAL", codigo_glosa="TA0201",
        )
        # SANITAS con contrato + TA0201 → NO entra
        db_session.add(ContratoRecord(eps="SANITAS", detalles="contrato vigente"))
        db_session.commit()
        _seed_glosa(
            db_session, factura="F2", eps="SANITAS", codigo_glosa="TA0201",
        )
        # SALUD TOTAL sin contrato + SO0101 → NO entra (no es TA)
        _seed_glosa(
            db_session, factura="F3", eps="SALUD TOTAL", codigo_glosa="SO0101",
        )
        r = client.get("/glosas/mis-asignaciones?vista=ta_sin_contrato&todas=true")
        rows = r.json()
        facturas = {row["factura"] for row in rows}
        assert facturas == {"F1"}


# ─── Sprint #6 — Vencen 24h ──────────────────────────────────────────
class TestVencen24h:
    def test_solo_dias_menor_igual_1(self, client, db_session):
        _seed_glosa(db_session, factura="F1", dias_restantes=0,
                    valor_objetado=1000)
        _seed_glosa(db_session, factura="F2", dias_restantes=1,
                    valor_objetado=2000)
        _seed_glosa(db_session, factura="F3", dias_restantes=5,
                    valor_objetado=3000)  # no
        r = client.get("/glosas/vencen-24h")
        d = r.json()
        assert d["total"] == 2
        assert d["valor_total_riesgo"] == 3000

    def test_excluye_terminales(self, client, db_session):
        _seed_glosa(db_session, dias_restantes=0, estado="LEVANTADA")
        r = client.get("/glosas/vencen-24h")
        assert r.json()["total"] == 0


# ─── Sprint #7 — Dashboard plata recuperada ─────────────────────────
class TestDashboardPlataRecuperada:
    def test_totales_y_agregados(self, client, db_session):
        _seed_glosa(
            db_session, factura="F1", valor_objetado=1000, valor_aceptado=200,
            valor_recuperado=800, estado="LEVANTADA",
        )
        _seed_glosa(
            db_session, factura="F2", valor_objetado=500, valor_aceptado=500,
            valor_recuperado=0, estado="RATIFICADA",
        )
        r = client.get("/glosas/dashboard-plata-recuperada")
        assert r.status_code == 200
        d = r.json()
        t = d["totales"]
        assert t["valor_objetado"] == 1500
        assert t["valor_aceptado"] == 700
        assert t["valor_recuperado"] == 800
        assert t["n_levantadas"] == 1
        assert t["n_ratificadas"] == 1
        # 1 levantada / 2 decididas = 50%
        assert t["tasa_efectividad_pct"] == 50.0
        assert len(d["por_eps"]) >= 1
        assert len(d["por_codigo"]) >= 1

    def test_db_vacia_no_explota(self, client):
        """Edge case sugerido por audit: dashboard con 0 glosas debe
        responder 200 con totales en 0 y listas vacías, NO 500 ni
        ZeroDivisionError en la tasa de efectividad."""
        r = client.get("/glosas/dashboard-plata-recuperada")
        assert r.status_code == 200, r.text
        d = r.json()
        t = d["totales"]
        assert t["n_glosas"] == 0
        assert t["n_levantadas"] == 0
        assert t["n_ratificadas"] == 0
        assert t["valor_objetado"] == 0
        assert t["valor_recuperado"] == 0
        # Sin decisiones → tasa = 0% (NO division by zero)
        assert t["tasa_efectividad_pct"] == 0.0
        assert d["por_eps"] == []
        assert d["por_codigo"] == []
        assert d["por_mes"] == []
