"""El tablero de plata recuperada — GET /dashboard-ejecutivo/plata-recuperada.

Lo que tiene que quedar probado no es que sume: es que **no rellene**. Un
tablero que se inventa el dato que le falta miente con más autoridad que uno
que se queda corto y lo dice.
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
def coordinador():
    return UsuarioRecord(id=1, email="coord@hus.com", rol="COORDINADOR", activo=1)


@pytest.fixture
def client(db_session, coordinador):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: coordinador
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _glosa(db, **kw):
    base = dict(
        eps="NUEVA EPS",
        paciente="X",
        codigo_glosa="FA0301",
        valor_objetado=1_000_000.0,
        etapa="RESPUESTA",
        estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    return g


def _pedir(client, **params):
    r = client.get("/dashboard-ejecutivo/plata-recuperada", params=params)
    assert r.status_code == 200, r.text
    return r.json()


class TestLaCuentaQuePideLaGerencia:
    def test_sin_glosas_no_inventa_cifras(self, client):
        d = _pedir(client)
        assert d["total"]["glosado"] == 0
        assert d["total"]["levantado"] == 0
        assert d["meses"] == []
        assert d["eps"] == []

    def test_lo_glosado_es_la_suma_de_lo_objetado(self, client, db_session):
        _glosa(db_session, valor_objetado=300_000)
        _glosa(db_session, valor_objetado=200_000)
        d = _pedir(client)
        assert d["total"]["glosas"] == 2
        assert d["total"]["glosado"] == 500_000

    def test_levantada_suma_lo_recuperado_no_lo_objetado(self, client, db_session):
        _glosa(
            db_session,
            valor_objetado=1_000_000,
            decision_eps="LEVANTADA",
            valor_recuperado=800_000,
        )
        d = _pedir(client)
        assert d["total"]["levantado"] == 800_000, (
            "la EPS levantó la glosa, pero lo que entró fue lo recuperado"
        )
        assert d["total"]["ratificado"] == 0

    def test_ratificada_y_aceptada_van_a_su_casilla(self, client, db_session):
        _glosa(db_session, valor_objetado=400_000, decision_eps="RATIFICADA")
        _glosa(db_session, valor_objetado=100_000, decision_eps="ACEPTADA")
        d = _pedir(client)
        assert d["total"]["ratificado"] == 400_000
        assert d["total"]["aceptado"] == 100_000
        assert d["total"]["sin_decision"] == 0

    def test_sin_decision_es_lo_que_la_eps_no_ha_contestado(self, client, db_session):
        _glosa(db_session, valor_objetado=250_000)
        _glosa(db_session, valor_objetado=250_000, decision_eps="PENDIENTE")
        d = _pedir(client)
        assert d["total"]["sin_decision"] == 500_000


class TestNoRellenaLoQueNoSabe:
    """Lo que el motor no puede probar se cuenta aparte. Nunca se supone."""

    def test_levantada_sin_valor_no_se_da_por_el_objetado(self, client, db_session):
        _glosa(
            db_session,
            valor_objetado=900_000,
            decision_eps="LEVANTADA",
            valor_recuperado=0,
        )
        d = _pedir(client)
        assert d["total"]["levantado"] == 0, (
            "nadie anotó cuánta plata era: no se puede suponer que fue todo lo objetado"
        )
        assert d["total"]["sin_dato"]["levantadas_sin_valor"] == 1

    def test_sin_fecha_de_vencimiento_no_se_cuenta_como_perdida(self, client, db_session):
        _glosa(db_session, valor_objetado=700_000, fecha_vencimiento=None)
        d = _pedir(client)
        assert d["total"]["perdido_por_vencimiento"] == 0
        assert d["total"]["sin_dato"]["sin_fecha_vencimiento"] == 1

    def test_sin_fecha_de_radicacion_se_avisa(self, client, db_session):
        _glosa(db_session, radicado_en=None)
        d = _pedir(client)
        assert d["total"]["sin_dato"]["sin_fecha_radicacion"] == 1

    def test_la_nota_le_dice_al_lector_que_no_se_rellena(self, client):
        d = _pedir(client)
        assert "sin_dato" in d["nota"] and "supuesto" in d["nota"].lower()


class TestRespondidoATiempo:
    def test_radicada_antes_del_vencimiento_es_a_tiempo(self, client, db_session):
        ahora = ahora_utc()
        _glosa(
            db_session,
            valor_objetado=500_000,
            radicado_en=ahora - timedelta(days=3),
            fecha_vencimiento=ahora + timedelta(days=2),
        )
        d = _pedir(client)
        assert d["total"]["respondido_a_tiempo"] == 500_000
        assert d["total"]["respondido_tarde"] == 0

    def test_radicada_despues_del_vencimiento_es_tarde(self, client, db_session):
        ahora = ahora_utc()
        _glosa(
            db_session,
            valor_objetado=500_000,
            radicado_en=ahora - timedelta(days=1),
            fecha_vencimiento=ahora - timedelta(days=10),
        )
        d = _pedir(client)
        assert d["total"]["respondido_tarde"] == 500_000
        assert d["total"]["respondido_a_tiempo"] == 0

    def test_vencida_sin_radicar_y_sin_decision_es_plata_perdida(self, client, db_session):
        ahora = ahora_utc()
        _glosa(
            db_session,
            valor_objetado=650_000,
            radicado_en=None,
            fecha_vencimiento=ahora - timedelta(days=5),
        )
        d = _pedir(client)
        assert d["total"]["perdido_por_vencimiento"] == 650_000

    def test_vencida_pero_ya_levantada_no_cuenta_como_perdida(self, client, db_session):
        ahora = ahora_utc()
        _glosa(
            db_session,
            valor_objetado=650_000,
            radicado_en=None,
            fecha_vencimiento=ahora - timedelta(days=5),
            decision_eps="LEVANTADA",
            valor_recuperado=650_000,
        )
        d = _pedir(client)
        assert d["total"]["perdido_por_vencimiento"] == 0, (
            "la EPS ya la levantó: esa plata no se perdió aunque falte el radicado"
        )


class TestPorMesYPorEps:
    def test_agrupa_por_eps_y_ordena_por_lo_glosado(self, client, db_session):
        _glosa(db_session, eps="COOSALUD", valor_objetado=100_000)
        _glosa(db_session, eps="NUEVA EPS", valor_objetado=900_000)
        d = _pedir(client)
        assert [e["eps"] for e in d["eps"]] == ["NUEVA EPS", "COOSALUD"]

    def test_la_eps_vacia_no_se_pierde(self, client, db_session):
        _glosa(db_session, eps="", valor_objetado=50_000)
        d = _pedir(client)
        assert d["eps"][0]["eps"] == "SIN EPS"

    def test_el_mes_se_lee_en_espanol(self, client, db_session):
        _glosa(db_session)
        d = _pedir(client)
        assert d["meses"], "debía haber al menos el mes en curso"
        etiqueta = d["meses"][0]["etiqueta"]
        assert any(
            m in etiqueta
            for m in (
                "enero",
                "febrero",
                "marzo",
                "abril",
                "mayo",
                "junio",
                "julio",
                "agosto",
                "septiembre",
                "octubre",
                "noviembre",
                "diciembre",
            )
        ), etiqueta

    def test_lo_viejo_queda_fuera_del_periodo(self, client, db_session):
        _glosa(db_session, valor_objetado=100_000, creado_en=ahora_utc() - timedelta(days=400))
        d = _pedir(client, meses=2)
        assert d["total"]["glosado"] == 0

    def test_se_puede_filtrar_una_sola_eps(self, client, db_session):
        _glosa(db_session, eps="COOSALUD", valor_objetado=100_000)
        _glosa(db_session, eps="NUEVA EPS", valor_objetado=900_000)
        d = _pedir(client, eps="COOSALUD")
        assert d["total"]["glosado"] == 100_000
        assert d["eps_filtrada"] == "COOSALUD"

    def test_la_tasa_es_lo_levantado_sobre_lo_glosado(self, client, db_session):
        _glosa(
            db_session,
            valor_objetado=1_000_000,
            decision_eps="LEVANTADA",
            valor_recuperado=250_000,
        )
        d = _pedir(client)
        assert d["total"]["tasa_levantado_pct"] == 25.0


class TestBordes:
    def test_pedir_cero_meses_no_rompe(self, client):
        d = _pedir(client, meses=0)
        assert d["meses_pedidos"] == 1

    def test_pedir_cien_meses_se_topa(self, client):
        d = _pedir(client, meses=100)
        assert d["meses_pedidos"] == 24

    def test_factura_en_cero_no_desbarata_la_tasa(self, client, db_session):
        _glosa(db_session, valor_objetado=0, decision_eps="LEVANTADA", valor_recuperado=0)
        d = _pedir(client)
        assert d["total"]["tasa_levantado_pct"] == 0
