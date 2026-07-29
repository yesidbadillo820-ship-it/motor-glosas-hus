"""El Centro de Inteligencia dirige: detecta, prioriza y dice a dónde ir.

La regla de la épica es que la IA deje de solo responder: el diagnóstico
barre vencimientos, malla, verificaciones sin contrato, audiencias y actas
a medio cuadrar, y entrega acciones ordenadas por prioridad y plata. Si una
fuente se cae, las demás llegan igual y el barrido lo declara.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import ConciliacionRecord, GlosaRecord, UsuarioRecord
from app.services import centro_inteligencia as ci


@pytest.fixture
def db_session():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _glosa(db, dias_restantes, valor=1_000_000, estado="RADICADA"):
    g = GlosaRecord(
        eps="COMPENSAR",
        codigo_glosa="TA0601",
        valor_objetado=valor,
        estado=estado,
        etapa="RESPUESTA",
        dias_restantes=dias_restantes,
    )
    db.add(g)
    db.commit()
    return g


class TestDiagnostico:
    def test_lo_vencido_es_prioridad_uno_y_trae_la_plata(self, db_session):
        _glosa(db_session, dias_restantes=-2, valor=5_000_000)
        _glosa(db_session, dias_restantes=3, valor=1_200_000)

        d = ci.diagnostico(db_session)

        assert d["urgentes"] >= 1
        primera = d["acciones"][0]
        assert primera["prioridad"] == 1
        assert "VENCIDAS" in primera["titulo"]
        assert primera["valor_en_juego"] == 5_000_000
        assert primera["pantalla"] == "vencimientos"
        assert "$5.000.000" in primera["por_que"]

    def test_la_malla_real_entra_al_barrido(self, db_session):
        """Con la malla de hoy siempre hay contratos vencidos o por vencer:
        el diagnóstico los trae con destino a la pantalla Contratos."""
        d = ci.diagnostico(db_session)
        pantallas = {a["pantalla"] for a in d["acciones"]}
        assert "malla" in pantallas

    def test_audiencia_pasada_sin_resultado_es_urgente(self, db_session):
        g = _glosa(db_session, dias_restantes=10)
        db_session.add(
            ConciliacionRecord(
                glosa_id=g.id,
                fecha_audiencia=datetime.now(timezone.utc) - timedelta(days=2),
                resultado=None,
            )
        )
        db_session.commit()

        d = ci.diagnostico(db_session)
        urgentes = [a for a in d["acciones"] if a["prioridad"] == 1]
        assert any("audiencia" in a["titulo"].lower() for a in urgentes)

    def test_una_fuente_caida_no_tumba_el_barrido(self, db_session, monkeypatch):
        def _explota(_db):
            raise RuntimeError("fuente rota a propósito")

        monkeypatch.setattr(ci, "_FUENTES", (("rota", _explota),) + ci._FUENTES[1:])
        d = ci.diagnostico(db_session)
        assert "rota" in d["fuentes_caidas"]
        assert isinstance(d["acciones"], list)  # las demás fuentes llegaron

    def test_ordena_por_prioridad_y_luego_por_plata(self, db_session):
        _glosa(db_session, dias_restantes=-1, valor=100_000)
        _glosa(db_session, dias_restantes=2, valor=9_000_000)

        d = ci.diagnostico(db_session)
        prioridades = [a["prioridad"] for a in d["acciones"]]
        assert prioridades == sorted(prioridades)


class TestEndpoint:
    def test_cualquier_autenticado_lo_ve(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app

        usuario = UsuarioRecord(id=1, email="viewer@hus.gov.co", nombre="V", rol="VIEWER", activo=1)
        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: usuario
        with TestClient(app) as c:
            r = c.get("/inteligencia/diagnostico")
        app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        d = r.json()
        assert "titular" in d and "acciones" in d and "urgentes" in d


class TestIADirige:
    def test_la_tool_esta_declarada_y_ejecuta(self):
        from app.services import asistente_maestro as am

        assert any(t["name"] == "diagnostico_operacion" for t in am.TOOLS_ASISTENTE)
        # La regla dura del director quedó en el prompt
        assert "DIRECTOR DE OPERACIONES" in am.SYSTEM_ASISTENTE_MAESTRO
        assert "diagnostico_operacion" in am.SYSTEM_ASISTENTE_MAESTRO

    async def test_la_tool_devuelve_el_diagnostico(self, db_session):
        from app.services import asistente_maestro as am

        _glosa(db_session, dias_restantes=-5, valor=2_000_000)
        crudo = await am.execute_tool_asistente(
            "diagnostico_operacion", {}, db=db_session, current_user=None
        )
        d = json.loads(crudo)
        assert d["urgentes"] >= 1
        assert any(a["prioridad"] == 1 for a in d["acciones"])


class TestPantalla:
    def test_existe_con_badge_y_navegacion(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert 'id="p-inteligencia"' in html
        assert 'id="sn-inteligencia"' in html
        assert 'id="intel-badge-side"' in html
        assert "function intelCargar" in html
        assert "intelIrA" in html  # cada acción lleva a su pantalla
        assert "intelBadge, 2500" in html  # el badge se entera solo al arrancar
        import re

        area = re.search(r"\.intel-area\{[^}]*\}", html).group(0)
        assert "overflow-y:auto" in area
