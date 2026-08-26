"""«Mi día» — GET /mi-dia/tablero y el reparto en tres columnas.

Idea del 26-08-2026: 32 pantallas para un gestor que hace tres cosas.
Lo que se prueba aquí es que cada glosa caiga donde le toca, que el orden
sea el que le hace perder plata al hospital si no lo mira, y que lo cerrado
no le llene el día de trabajo que ya hizo.
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
from app.services.mi_dia import armar_mi_dia


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
def gestor(db_session):
    u = UsuarioRecord(id=1, email="gestor@hus.com", nombre="ANA GESTORA", rol="AUDITOR", activo=1)
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, gestor):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: gestor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _glosa(db, **kw):
    base = dict(
        eps="NUEVA EPS",
        paciente="X",
        factura="HUS1",
        codigo_glosa="FA0301",
        valor_objetado=1_000_000.0,
        etapa="RESPUESTA",
        estado="RADICADA",
        auditor_email="gestor@hus.com",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    return g


def _pedir(client):
    r = client.get("/mi-dia/tablero")
    assert r.status_code == 200, r.text
    return r.json()


class TestLasTresCosasDelDia:
    def test_sin_nada_asignado_las_tres_columnas_estan_vacias(self, client):
        d = _pedir(client)
        for col in ("responder", "revisar", "radicar"):
            assert d[col]["cantidad"] == 0
            assert d[col]["glosas"] == []
        assert d["total_abiertas"] == 0

    def test_sin_respuesta_escrita_va_a_responder(self, client, db_session):
        _glosa(db_session, dictamen=None)
        d = _pedir(client)
        assert d["responder"]["cantidad"] == 1
        assert d["responder"]["glosas"][0]["motivo"] == "Sin respuesta escrita"

    def test_aprobada_sin_radicar_va_a_radicar(self, client, db_session):
        _glosa(db_session, workflow_state="APROBADA", dictamen="TEXTO", radicado_en=None)
        d = _pedir(client)
        assert d["radicar"]["cantidad"] == 1
        assert "portal" in d["radicar"]["glosas"][0]["motivo"]

    def test_aprobada_pero_ya_radicada_no_vuelve_a_pedirse(self, client, db_session):
        _glosa(
            db_session,
            workflow_state="APROBADA",
            dictamen="TEXTO",
            radicado_en=ahora_utc(),
        )
        d = _pedir(client)
        assert d["radicar"]["cantidad"] == 0, "ya se subió al portal: no es trabajo de hoy"

    def test_la_que_pide_soportes_va_a_revisar(self, client, db_session):
        _glosa(db_session, estado="REQUIERE_SOPORTES")
        d = _pedir(client)
        assert d["revisar"]["cantidad"] == 1
        assert d["revisar"]["glosas"][0]["motivo"] == "Pide soportes"

    def test_la_que_el_motor_marco_va_a_revisar(self, client, db_session):
        _glosa(
            db_session,
            dictamen="ESE HUS NO ACEPTA. ⚠ ANTES DE RADICAR, LÉALO COMO EL AUDITOR",
        )
        d = _pedir(client)
        assert d["revisar"]["cantidad"] == 1
        assert d["revisar"]["glosas"][0]["motivo"] == "El motor le dejó un aviso"

    def test_con_dictamen_pero_sin_aprobar_va_a_revisar(self, client, db_session):
        _glosa(db_session, dictamen="ESE HUS NO ACEPTA LA GLOSA.")
        d = _pedir(client)
        assert d["revisar"]["cantidad"] == 1
        assert "aprobarla" in d["revisar"]["glosas"][0]["motivo"]

    def test_cada_glosa_cae_en_una_sola_columna(self, client, db_session):
        _glosa(db_session, estado="REQUIERE_SOPORTES", dictamen="⚠ FALTA EL SOPORTE")
        d = _pedir(client)
        total = sum(d[c]["cantidad"] for c in ("responder", "revisar", "radicar"))
        assert total == 1


class TestLoCerradoNoEsTrabajoDeHoy:
    @pytest.mark.parametrize("estado", ["LEVANTADA", "ACEPTADA", "RATIFICADA", "CONCILIADA"])
    def test_las_decididas_no_aparecen(self, client, db_session, estado):
        _glosa(db_session, estado=estado)
        d = _pedir(client)
        assert d["total_abiertas"] == 0

    def test_la_respondida_por_workflow_tampoco(self, client, db_session):
        _glosa(db_session, workflow_state="RESPONDIDA", dictamen="TEXTO")
        d = _pedir(client)
        assert d["total_abiertas"] == 0


class TestElOrdenEsElQueCuestaPlata:
    def test_primero_lo_que_vence_antes(self, client, db_session):
        ahora = ahora_utc()
        _glosa(db_session, factura="LEJOS", fecha_vencimiento=ahora + timedelta(days=20))
        _glosa(db_session, factura="CERCA", fecha_vencimiento=ahora + timedelta(days=1))
        d = _pedir(client)
        assert [g["factura"] for g in d["responder"]["glosas"]] == ["CERCA", "LEJOS"]

    def test_a_igual_dia_manda_la_plata(self, client, db_session):
        vence = ahora_utc() + timedelta(days=3)
        _glosa(db_session, factura="POCA", valor_objetado=10_000, fecha_vencimiento=vence)
        _glosa(db_session, factura="MUCHA", valor_objetado=9_000_000, fecha_vencimiento=vence)
        d = _pedir(client)
        assert [g["factura"] for g in d["responder"]["glosas"]] == ["MUCHA", "POCA"]

    def test_la_que_no_tiene_plazo_va_al_final_no_se_le_inventa_uno(self, client, db_session):
        _glosa(db_session, factura="SINPLAZO", fecha_vencimiento=None, dias_restantes=None)
        _glosa(
            db_session,
            factura="CONPLAZO",
            fecha_vencimiento=ahora_utc() + timedelta(days=30),
        )
        d = _pedir(client)
        assert [g["factura"] for g in d["responder"]["glosas"]] == ["CONPLAZO", "SINPLAZO"]
        assert d["responder"]["glosas"][-1]["dias_que_faltan"] is None

    def test_la_vencida_se_marca(self, client, db_session):
        _glosa(db_session, fecha_vencimiento=ahora_utc() - timedelta(days=4))
        d = _pedir(client)
        g = d["responder"]["glosas"][0]
        assert g["vencida"] is True
        assert g["dias_que_faltan"] < 0
        assert d["vencidas"] == 1


class TestLosTotalesDelDia:
    def test_la_plata_en_riesgo_suma_las_tres_columnas(self, client, db_session):
        _glosa(db_session, valor_objetado=100_000)
        _glosa(db_session, valor_objetado=200_000, estado="REQUIERE_SOPORTES")
        _glosa(
            db_session,
            valor_objetado=300_000,
            workflow_state="APROBADA",
            dictamen="T",
        )
        d = _pedir(client)
        assert d["valor_en_riesgo"] == 600_000
        assert d["total_abiertas"] == 3


class TestBordesDelReparto:
    """Sin base de datos de por medio — el reparto solo."""

    def test_una_lista_vacia_no_rompe(self):
        d = armar_mi_dia([])
        assert d["total_abiertas"] == 0

    def test_none_no_rompe(self):
        d = armar_mi_dia(None)
        assert d["total_abiertas"] == 0

    def test_avisa_cuando_hay_mas_de_las_que_muestra(self):
        glosas = [
            GlosaRecord(id=i, eps="X", valor_objetado=1000, estado="RADICADA") for i in range(30)
        ]
        d = armar_mi_dia(glosas, limite_por_columna=10)
        assert len(d["responder"]["glosas"]) == 10
        assert d["responder"]["hay_mas"] == 20
        assert d["responder"]["cantidad"] == 30, (
            "el contador debe decir cuántas hay, no cuántas alcanzó a mostrar"
        )

    def test_factura_en_cero_no_rompe_el_orden(self):
        glosas = [
            GlosaRecord(id=1, eps="X", valor_objetado=0, estado="RADICADA"),
            GlosaRecord(id=2, eps="X", valor_objetado=None, estado="RADICADA"),
        ]
        d = armar_mi_dia(glosas)
        assert d["responder"]["cantidad"] == 2
        assert d["responder"]["valor"] == 0


class TestElCeroQueNoSeSabeSiEsCero:
    """La columna `dias_restantes` vale 0 por defecto. Un 0 sin fecha de
    vencimiento puede ser «se venció» o «nadie le calculó el plazo», y en la
    base se ven idénticas. No se escoge ninguna: se dice que no se sabe."""

    def test_cero_sin_fecha_no_se_disfraza_de_vence_hoy(self, client, db_session):
        _glosa(db_session, factura="DEFECTO", fecha_vencimiento=None, dias_restantes=0)
        d = _pedir(client)
        g = d["responder"]["glosas"][0]
        assert g["dias_que_faltan"] is None, (
            "un 0 que puede ser el valor por defecto de la columna no puede "
            "leerse como «vence hoy»: empujaría hacia abajo lo que sí vence"
        )
        assert g["vencida"] is False

    def test_el_contador_con_numero_de_verdad_si_se_usa(self, client, db_session):
        _glosa(db_session, factura="CONTADOR", fecha_vencimiento=None, dias_restantes=4)
        d = _pedir(client)
        g = d["responder"]["glosas"][0]
        assert g["dias_que_faltan"] == 4, "ese número lo calculó alguien: sirve"
        assert g["plazo_sin_fecha"] is True, (
            "hay que poder decirle al gestor que ese plazo no viene de una fecha"
        )

    def test_la_fecha_le_gana_al_contador(self, client, db_session):
        _glosa(
            db_session,
            fecha_vencimiento=ahora_utc() + timedelta(days=10),
            dias_restantes=99,
        )
        d = _pedir(client)
        g = d["responder"]["glosas"][0]
        assert g["dias_que_faltan"] in (9, 10)
        assert g["plazo_sin_fecha"] is False
