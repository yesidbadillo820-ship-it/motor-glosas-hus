"""Diagnóstico de calidad del dictamen, por HTTP (09-09-2026).

El auditor preguntó por qué la confianza no sube de ~40%. Buena parte de la
respuesta solo se puede dar con la base REAL del hospital, que no se ve
desde el entorno de desarrollo. Pedirle que corriera un script por consola
era pasarle trabajo manual; esto lo vuelve un enlace que abre y copia.
"""

from __future__ import annotations

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
def admin():
    return UsuarioRecord(id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1)


@pytest.fixture
def client(db_session, admin):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _glosa(db, *, eps="COOSALUD", estado="RADICADA", score=40.0, modelo="groq/openai/gpt-oss-120b"):
    db.add(
        GlosaRecord(
            eps=eps,
            paciente="X",
            codigo_glosa="TA0701",
            valor_objetado=1000,
            etapa="INICIAL",
            estado=estado,
            creado_en=ahora_utc(),
            score=score,
            modelo_ia=modelo,
        )
    )
    db.commit()


class TestConLaBaseVacia:
    def test_no_truena_y_lo_dice(self, client):
        r = client.get("/admin/diagnostico-calidad")
        assert r.status_code == 200
        d = r.json()
        assert d["glosas_analizadas"] == 0
        assert "nota" in d


class TestLosNumerosQueImportan:
    def test_cuenta_las_eps_genericas(self, client, db_session):
        _glosa(db_session, eps="OTRA / SIN DEFINIR")
        _glosa(db_session, eps="OTRA / SIN DEFINIR")
        _glosa(db_session, eps="COOSALUD")
        d = client.get("/admin/diagnostico-calidad").json()
        assert d["eps"]["genericas"] == 2
        assert d["eps"]["pct_genericas"] == pytest.approx(66.7, abs=0.1)

    def test_lista_las_eps_con_nombre_real(self, client, db_session):
        _glosa(db_session, eps="COOSALUD")
        _glosa(db_session, eps="OTRA")
        d = client.get("/admin/diagnostico-calidad").json()
        nombres = [x["eps"] for x in d["eps"]["con_nombre_real"]]
        assert nombres == ["COOSALUD"], "«OTRA» no es una entidad pagadora"

    def test_avisa_si_las_tarifas_por_cups_estan_vacias(self, client, db_session):
        _glosa(db_session)
        d = client.get("/admin/diagnostico-calidad").json()
        assert d["tarifas_pactadas_por_cups"]["filas"] == 0
        assert "VACÍA" in d["tarifas_pactadas_por_cups"]["diagnostico"]

    def test_mide_el_veredicto_final_de_la_eps(self, client, db_session):
        for _ in range(8):
            _glosa(db_session, estado="RADICADA")
        _glosa(db_session, estado="LEVANTADA")
        _glosa(db_session, estado="RATIFICADA")
        d = client.get("/admin/diagnostico-calidad").json()["veredicto_final_eps"]
        assert d["con_veredicto"] == 2 and d["pct"] == 20.0
        assert "sin combustible" in d["diagnostico"], (
            "por debajo del 30% hay que decir qué se está frenando"
        )

    def test_compara_la_confianza_por_modelo(self, client, db_session):
        _glosa(db_session, score=40, modelo="groq/openai/gpt-oss-120b")
        _glosa(db_session, score=44, modelo="groq/openai/gpt-oss-120b")
        _glosa(db_session, score=70, modelo="claude-sonnet-4-5")
        por_modelo = {
            x["modelo"]: x
            for x in client.get("/admin/diagnostico-calidad").json()["confianza_por_modelo"]
        }
        assert por_modelo["groq/openai/gpt-oss-120b"]["confianza_promedio"] == 42.0
        assert por_modelo["claude-sonnet-4-5"]["confianza_promedio"] == 70.0

    def test_proyecta_el_costo_mensual_con_el_volumen_real(self, client, db_session):
        for _ in range(10):
            _glosa(db_session)
        db_session.add(
            AICallRecord(
                proveedor="anthropic",
                modelo="claude-sonnet-4-5",
                latency_ms=4000,
                input_tokens=11000,
                output_tokens=1400,
                cost_usd=0.05,
            )
        )
        db_session.commit()
        costo = client.get("/admin/diagnostico-calidad").json()["costo_ia"][0]
        assert costo["proveedor"] == "anthropic"
        assert costo["costo_promedio_usd"] == 0.05
        # 10 glosas × $0.05 = $0.50 si TODAS pasaran por este proveedor.
        assert costo["proyeccion_mensual_usd_a_este_volumen"] == 0.5


class TestSoloAdmin:
    def test_un_auditor_no_entra(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app

        auditor = UsuarioRecord(id=2, email="a@hus.com", rol="AUDITOR", activo=1)
        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: auditor
        with TestClient(app) as c:
            assert c.get("/admin/diagnostico-calidad").status_code == 403
        app.dependency_overrides.clear()

    def test_sin_sesion_tampoco(self):
        from app.main import app

        with TestClient(app) as c:
            assert c.get("/admin/diagnostico-calidad").status_code == 401
