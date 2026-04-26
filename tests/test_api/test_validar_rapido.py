"""Tests del endpoint /glosas/{id}/validar-rapido (R70 P1)."""
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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed_glosa(db, **kw):
    base = dict(
        eps="FAMISANAR", paciente="X", codigo_glosa="TA0201",
        valor_objetado=168_563, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    g = GlosaRecord(**base)
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


class TestValidarRapido:
    def test_glosa_inexistente_404(self, client):
        r = client.get("/glosas/99999/validar-rapido")
        assert r.status_code == 404

    def test_sin_dictamen_400(self, client, db_session):
        g = _seed_glosa(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/validar-rapido")
        assert r.status_code == 400

    def test_dictamen_completo_score_alto(self, client, db_session):
        """Dictamen completo con todos los componentes → score alto."""
        dictamen_ok = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS "
            "SOBRE EL CÓDIGO TA0201, INTERPUESTA POR FAMISANAR. "
            "El valor facturado $168.563 corresponde a tarifa pactada "
            "según Contrato S-13-1-03-1-04958. "
            "EN PRIMER LUGAR, conforme al Artículo 57 de la Ley 1438 de 2011 "
            "y la Resolución 2284 de 2023 (Manual Único de Glosas), "
            "EN SEGUNDO LUGAR, según el Artículo 871 del Código de Comercio "
            "(buena fe contractual), se solicita el LEVANTAMIENTO. "
            "En subsidio, se invita a MESA DE CONCILIACIÓN de auditoría "
            "conforme al Art. 20 Dec. 4747. "
        ) * 5
        g = _seed_glosa(
            db_session, dictamen=dictamen_ok,
            codigo_respuesta="RE9901",
        )
        r = client.get(f"/glosas/{g.id}/validar-rapido")
        d = r.json()
        # Estructura
        assert "score" in d
        assert "checks" in d
        assert "total" in d
        assert "aprobados" in d
        assert d["glosa_id"] == g.id
        # Score razonable para dictamen completo
        assert d["score"] >= 60
        assert d["aprobados"] >= 5

    def test_dictamen_pobre_score_bajo(self, client, db_session):
        g = _seed_glosa(db_session, dictamen="<p>texto muy corto sin nada</p>")
        r = client.get(f"/glosas/{g.id}/validar-rapido")
        d = r.json()
        # Texto corto + sin normas + sin enumeración → score bajo
        assert d["score"] < 60

    def test_response_estructura_checks(self, client, db_session):
        g = _seed_glosa(
            db_session,
            dictamen="<p>" + ("texto " * 50) + "</p>",
        )
        r = client.get(f"/glosas/{g.id}/validar-rapido")
        d = r.json()
        # cada check debe tener id, nombre, peso, aprobado, mensaje
        for check in d["checks"]:
            assert "id" in check
            assert "nombre" in check
            assert "aprobado" in check
            assert isinstance(check["aprobado"], bool)
