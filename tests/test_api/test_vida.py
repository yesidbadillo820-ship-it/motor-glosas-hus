"""Capa de Vida (ronda 32): endpoints /vida/saludo y /vida/celebraciones."""

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
    return UsuarioRecord(id=1, email="yesid@hus.com", nombre="Yesid Pérez", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _glosa(db, **kw):
    kw.setdefault("auditor_email", "yesid@hus.com")
    kw.setdefault("creado_en", ahora_utc())
    db.add(GlosaRecord(**kw))
    db.commit()


class TestSaludo:
    def test_estructura_basica(self, client):
        r = client.get("/vida/saludo")
        assert r.status_code == 200
        d = r.json()
        assert d["nombre"] == "Yesid"
        assert d["saludo"] in (
            "Buenos días",
            "Buenas tardes",
            "Buenas noches",
            "Trabajando temprano",
        )
        assert isinstance(d["frase"], str) and d["frase"]
        assert d["nuevas_hoy"] == 0
        assert d["sin_pendientes"] is True

    def test_cuenta_nuevas_hoy_y_recuperado(self, client, db_session):
        _glosa(db_session, eps="COMPENSAR", estado="PENDIENTE", valor_objetado=1_000_000)
        _glosa(
            db_session,
            eps="FAMISANAR",
            estado="LEVANTADA",
            valor_objetado=6_400_000,
            valor_recuperado=6_400_000,
            fecha_decision_eps=ahora_utc(),
        )
        d = client.get("/vida/saludo").json()
        assert d["nuevas_hoy"] == 2
        assert d["recuperado_semana"] == 6_400_000


class TestCelebraciones:
    def test_sin_eventos(self, client):
        d = client.get("/vida/celebraciones").json()
        assert d["total"] == 0
        assert d["eventos"] == []

    def test_glosa_ganada_reciente_genera_celebracion(self, client, db_session):
        _glosa(
            db_session,
            eps="COMPENSAR",
            factura="HUS900",
            estado="LEVANTADA",
            valor_objetado=6_400_000,
            valor_recuperado=6_400_000,
            fecha_decision_eps=ahora_utc(),
        )
        d = client.get("/vida/celebraciones").json()
        tipos = {e["tipo"] for e in d["eventos"]}
        assert "levantada" in tipos
        lev = next(e for e in d["eventos"] if e["tipo"] == "levantada")
        assert "COMPENSAR" in lev["mensaje"]
        assert lev["valor"] == 6_400_000


class TestConfianza:
    def test_glosa_inexistente_404(self, client):
        assert client.get("/vida/confianza/999").status_code == 404

    def test_dictamen_con_soportes_y_norma(self, client, db_session):
        _glosa(
            db_session,
            eps="FAMISANAR",
            estado="RESPONDIDA",
            dictamen=(
                "ESE HUS NO ACEPTA. Conforme al folio 2 de la historia clínica "
                "y a la Ley 1438 de 2011, se solicita el levantamiento."
            ),
            score=8,
        )
        gid = db_session.query(GlosaRecord).first().id
        d = client.get(f"/vida/confianza/{gid}").json()
        assert d["nivel"] in ("alta", "media")
        assert d["senales"]["cita_soportes"] is True
        assert d["senales"]["cita_norma"] is True

    def test_sin_dictamen(self, client, db_session):
        _glosa(db_session, eps="X", estado="PENDIENTE")
        gid = db_session.query(GlosaRecord).first().id
        d = client.get(f"/vida/confianza/{gid}").json()
        assert d["nivel"] == "baja"


class TestOcrImagen:
    def test_sin_gemini_key_503(self, client, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setenv("GEMINI_API_KEY", "")
        get_settings.cache_clear()
        r = client.post(
            "/vida/ocr-imagen",
            files={"archivo": ("glosa.png", b"\x89PNG\r\n", "image/png")},
        )
        get_settings.cache_clear()
        assert r.status_code == 503

    def test_tipo_invalido_400(self, client):
        r = client.post(
            "/vida/ocr-imagen",
            files={"archivo": ("glosa.pdf", b"%PDF", "application/pdf")},
        )
        assert r.status_code == 400

    def test_ocr_ok_mockeando_gemini(self, client, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        get_settings.cache_clear()

        class _FakeGemini:
            def __init__(self, *a, **k):
                pass

            async def completar(self, *a, **k):
                return ("TA0801 CONSULTA URGENCIAS VALOR OBJETADO $149.000", "gemini-fake")

        import app.services.gemini_service as gs

        monkeypatch.setattr(gs, "GeminiService", _FakeGemini)
        r = client.post(
            "/vida/ocr-imagen",
            files={"archivo": ("glosa.png", b"\x89PNG\r\nfakeimg", "image/png")},
        )
        get_settings.cache_clear()
        assert r.status_code == 200
        assert "TA0801" in r.json()["texto"]
