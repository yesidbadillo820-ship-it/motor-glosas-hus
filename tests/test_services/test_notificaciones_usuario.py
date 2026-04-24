"""Tests del consolidador de notificaciones por usuario (Ronda 25)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import (
    ComentarioGlosaRecord,
    GlosaRecord,
    PlantillaGoldRecord,
)
from app.services.notificaciones_usuario import (
    _glosas_criticas,
    _glosas_texto_fijo_listas,
    _glosas_vencidas,
    _gold_nuevas_de_mis_eps,
    _menciones_pendientes,
    notificaciones_de,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


EMAIL = "ana@hus.com"


def _g(db, **kw):
    defaults = dict(
        eps="FAMISANAR", paciente="X", factura="F",
        codigo_glosa="TA0201", valor_objetado=100_000,
        estado="PENDIENTE", dias_restantes=10,
        auditor_email=EMAIL, creado_en=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    g = GlosaRecord(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


class TestCriticas:
    def test_sin_criticas(self, db_session):
        _g(db_session, dias_restantes=10)
        assert _glosas_criticas(db_session, EMAIL) == 0

    def test_detecta_glosa_a_2d(self, db_session):
        _g(db_session, dias_restantes=2)
        assert _glosas_criticas(db_session, EMAIL) == 1

    def test_solo_cuenta_mis_glosas(self, db_session):
        _g(db_session, dias_restantes=2, auditor_email="otro@hus.com")
        assert _glosas_criticas(db_session, EMAIL) == 0


class TestVencidas:
    def test_detecta_vencida(self, db_session):
        _g(db_session, dias_restantes=-3)
        assert _glosas_vencidas(db_session, EMAIL) == 1

    def test_pendiente_no_vencida(self, db_session):
        _g(db_session, dias_restantes=5)
        assert _glosas_vencidas(db_session, EMAIL) == 0


class TestTextoFijoListas:
    def test_detecta_con_modelo_texto_fijo(self, db_session):
        _g(db_session, modelo_ia="pre-analisis/texto_fijo/RATIFICADA")
        items = _glosas_texto_fijo_listas(db_session, EMAIL)
        assert len(items) == 1

    def test_ignora_IA_normal(self, db_session):
        _g(db_session, modelo_ia="anthropic/claude-sonnet")
        assert _glosas_texto_fijo_listas(db_session, EMAIL) == []


class TestMenciones:
    def test_menciones_pendientes(self, db_session):
        g = _g(db_session)
        c = ComentarioGlosaRecord(
            glosa_id=g.id, autor_email="x@hus.com",
            autor_nombre="X", texto="hola @ana", mencion=EMAIL,
            resuelto=0, creado_en=datetime.now(timezone.utc),
        )
        db_session.add(c)
        db_session.commit()
        assert len(_menciones_pendientes(db_session, EMAIL)) == 1

    def test_mencion_resuelta_no_cuenta(self, db_session):
        g = _g(db_session)
        c = ComentarioGlosaRecord(
            glosa_id=g.id, autor_email="x@hus.com", autor_nombre="X",
            texto="hola @ana", mencion=EMAIL, resuelto=1,
            creado_en=datetime.now(timezone.utc),
        )
        db_session.add(c)
        db_session.commit()
        assert _menciones_pendientes(db_session, EMAIL) == []


class TestGold:
    def test_gold_de_mis_eps(self, db_session):
        _g(db_session)  # crea trabajo histórico con FAMISANAR
        p = PlantillaGoldRecord(
            eps="FAMISANAR", codigo_glosa="TA0201", activa=1,
            argumento="X", creado_en=datetime.now(timezone.utc),
        )
        db_session.add(p)
        db_session.commit()
        assert len(_gold_nuevas_de_mis_eps(db_session, EMAIL)) == 1

    def test_gold_de_otra_eps_no_cuenta(self, db_session):
        _g(db_session, eps="FAMISANAR")
        p = PlantillaGoldRecord(
            eps="SANITAS", codigo_glosa="TA0201", activa=1,
            argumento="X", creado_en=datetime.now(timezone.utc),
        )
        db_session.add(p)
        db_session.commit()
        assert _gold_nuevas_de_mis_eps(db_session, EMAIL) == []


class TestConsolidado:
    def test_suma_total_correcta(self, db_session):
        _g(db_session, dias_restantes=2)            # critica
        _g(db_session, dias_restantes=-1, factura="F2")   # vencida
        _g(db_session, modelo_ia="pre-analisis/texto_fijo/RATIFICADA", factura="F3")
        usuario = SimpleNamespace(email=EMAIL)
        r = notificaciones_de(db_session, usuario)
        assert r["total"] == 3
        assert r["items"]["criticas_48h"]["conteo"] == 1
        assert r["items"]["vencidas"]["conteo"] == 1
        assert r["items"]["listas_para_enviar"]["conteo"] == 1

    def test_usuario_sin_email(self, db_session):
        r = notificaciones_de(db_session, SimpleNamespace(email=""))
        assert r["total"] == 0
