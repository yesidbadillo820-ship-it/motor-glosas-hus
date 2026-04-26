"""Tests del endpoint GET /admin/eps-cartera-detalle (R292 P1)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, eps, factura, codigo, estado="RADICADA",
          saldo=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo, factura=factura,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        saldo_factura=saldo,
    ))
    db.commit()


class TestEPSCarteraDetalle:
    def test_resumen_y_tops(self, client, db_session):
        _seed(db_session, "SANITAS", "F100", "TA0801", saldo=5000)
        _seed(db_session, "SANITAS", "F200", "TA0801", saldo=10000)
        _seed(
            db_session, "SANITAS", "F300", "FA0603",
            estado="LEVANTADA",
        )
        # Otra EPS, no debe aparecer
        _seed(db_session, "OTRA", "F999", "X", saldo=999999)

        r = client.get("/admin/eps-cartera-detalle?eps=SANITAS")
        d = r.json()
        assert d["eps"] == "SANITAS"
        assert d["resumen"]["total"] == 3
        assert d["resumen"]["abiertas"] == 2
        assert d["resumen"]["cerradas"] == 1
        # Top facturas: solo abiertas
        facturas = {f["factura"]: f["saldo"] for f in d["top_facturas"]}
        assert facturas["F200"] == 10000
        assert facturas["F100"] == 5000
        # Top códigos: solo abiertas (TA0801 dos veces)
        codigos = {c["codigo_glosa"]: c["count"] for c in d["top_codigos"]}
        assert codigos["TA0801"] == 2

    def test_eps_sin_glosas(self, client):
        r = client.get("/admin/eps-cartera-detalle?eps=NOEXISTE")
        d = r.json()
        assert d["resumen"]["total"] == 0
        assert d["top_facturas"] == []
