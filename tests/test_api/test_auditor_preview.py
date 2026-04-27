"""Tests del endpoint preview-auditoria (R-cerebro #9)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ContratoRecord, UsuarioRecord


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
def auditor():
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice",
        rol="AUDITOR", activo=1,
    )


def _client(db_session, user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: user
    return TestClient(app)


def _clear():
    from app.main import app
    app.dependency_overrides.clear()


class TestPreview:
    def test_caso_real_TA0801(self, db_session, auditor):
        # Cargar contrato para que el detector "sin contrato" se dispare
        db_session.add(ContratoRecord(
            eps="DISPENSARIO MEDICO BUCARAMANGA",
            detalles="Contrato 440-DIGSA-2025"
        ))
        db_session.commit()
        with _client(db_session, auditor) as c:
            r = c.post("/glosas/preview-auditoria", json={
                "texto_glosa": (
                    "TA0801 - CUPS 902210 - HEMOGRAMA - Valor objetado: $3.151 "
                    "- SE GLOSA MVC SIN CONTRATO ENTRE LAS PARTES "
                    "SE RECONOCE A SOAT VIGENTE. SE GLOSA LA DIFERENCIA"
                ),
                "eps": "DISPENSARIO MEDICO BUCARAMANGA",
            })
            assert r.status_code == 200
            d = r.json()
            ids = [h["id"] for h in d["hallazgos"]]
            assert "afirmacion_sin_contrato_falsa" in ids
            assert "soat_sustituto_indebido" in ids
            assert "diferencia_sin_referente" in ids
            assert d["score_evidencia"] >= 60
            assert d["accion_sugerida"] == "DEFENDER_FUERTE"
            assert d["tiene_contrato_detectado"] is True
        _clear()

    def test_sin_eps_sin_contrato_detectable(self, db_session, auditor):
        # Sin contrato cargado → "sin contrato" no es mentira → no flag
        with _client(db_session, auditor) as c:
            r = c.post("/glosas/preview-auditoria", json={
                "texto_glosa": "SE GLOSA MVC SIN CONTRATO ENTRE LAS PARTES",
                "eps": "EPS_X_NO_REGISTRADA",
            })
            assert r.status_code == 200
            d = r.json()
            ids = [h["id"] for h in d["hallazgos"]]
            assert "afirmacion_sin_contrato_falsa" not in ids
            assert d["tiene_contrato_detectado"] is False
        _clear()

    def test_texto_corto_422(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/glosas/preview-auditoria", json={"texto_glosa": ""})
            assert r.status_code == 422
        _clear()
