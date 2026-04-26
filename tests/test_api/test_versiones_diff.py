"""Tests del endpoint GET /glosas/{id}/versiones/diff (R63 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    DictamenVersionRecord, GlosaRecord, UsuarioRecord,
)


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


@pytest.fixture
def glosa(db_session):
    g = GlosaRecord(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


def _seed_version(db, glosa_id, html, accion="CREAR"):
    v = DictamenVersionRecord(
        glosa_id=glosa_id, dictamen_html=html,
        accion=accion, autor_email="x@hus.com",
        creado_en=ahora_utc(),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestDiffVersiones:
    def test_diff_basico(self, client, db_session, glosa):
        v1 = _seed_version(db_session, glosa.id, "<p>linea uno</p><p>linea dos</p>")
        v2 = _seed_version(db_session, glosa.id, "<p>linea uno</p><p>linea TRES</p>",
                           accion="REANALIZAR")
        r = client.get(
            f"/glosas/{glosa.id}/versiones/diff?v1={v1.id}&v2={v2.id}"
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["v1"]["id"] == v1.id
        assert d["v2"]["id"] == v2.id
        # Una línea cambió: dos → TRES
        assert d["lineas_agregadas"] >= 1
        assert d["lineas_removidas"] >= 1
        assert "TRES" in d["diff_unificado"]
        assert d["sin_cambios"] is False

    def test_diff_sin_cambios(self, client, db_session, glosa):
        """Misma versión repetida → sin_cambios=True."""
        html = "<p>identico contenido</p>"
        v1 = _seed_version(db_session, glosa.id, html)
        v2 = _seed_version(db_session, glosa.id, html, accion="REANALIZAR")
        r = client.get(
            f"/glosas/{glosa.id}/versiones/diff?v1={v1.id}&v2={v2.id}"
        )
        assert r.status_code == 200
        d = r.json()
        assert d["sin_cambios"] is True
        assert d["lineas_agregadas"] == 0
        assert d["lineas_removidas"] == 0

    def test_diff_v1_igual_v2_devuelve_400(self, client, db_session, glosa):
        v = _seed_version(db_session, glosa.id, "<p>x</p>")
        r = client.get(
            f"/glosas/{glosa.id}/versiones/diff?v1={v.id}&v2={v.id}"
        )
        assert r.status_code == 400

    def test_diff_version_inexistente_404(self, client, db_session, glosa):
        v = _seed_version(db_session, glosa.id, "<p>x</p>")
        r = client.get(
            f"/glosas/{glosa.id}/versiones/diff?v1={v.id}&v2=99999"
        )
        assert r.status_code == 404

    def test_diff_html_se_strippea(self, client, db_session, glosa):
        """Cambio en CSS/style del HTML pero MISMO texto → sin_cambios=True."""
        v1 = _seed_version(
            db_session, glosa.id,
            '<div style="color:red">contenido principal</div>',
        )
        v2 = _seed_version(
            db_session, glosa.id,
            '<div style="color:blue;padding:10px">contenido principal</div>',
            accion="REANALIZAR",
        )
        r = client.get(
            f"/glosas/{glosa.id}/versiones/diff?v1={v1.id}&v2={v2.id}"
        )
        assert r.status_code == 200
        d = r.json()
        # El cambio fue solo en el style — el texto plano es el mismo
        assert d["sin_cambios"] is True

    def test_diff_unifica_saltos_de_linea(self, client, db_session, glosa):
        """Cambios en saltos de línea o whitespace NO cuentan como diff."""
        v1 = _seed_version(db_session, glosa.id, "<p>una linea</p>")
        v2 = _seed_version(
            db_session, glosa.id,
            "<p>una   linea</p>",  # mismo texto con espacios extras
            accion="REANALIZAR",
        )
        r = client.get(
            f"/glosas/{glosa.id}/versiones/diff?v1={v1.id}&v2={v2.id}"
        )
        d = r.json()
        # Normalización de espacios → equivalentes
        assert d["sin_cambios"] is True
