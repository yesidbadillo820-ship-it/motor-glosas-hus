"""Panel Operacional: dónde se atasca el trabajo y quién lleva cuánto.

Justificación de diseño: ya existía «Mando ejecutivo» (pantalla única con
auto-refresh); crear otra pantalla operacional habría duplicado. Se amplió
el Mando con las dos cosas que ninguna vista mostraba — los cuellos de
botella por estado (con la antigüedad de lo más viejo) y la carga real por
auditor (abiertas, vencidas y valor).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


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


def _glosa(db, estado, auditor=None, valor=1_000_000, dias_restantes=5, dias_vieja=0):
    g = GlosaRecord(
        eps="COMPENSAR",
        codigo_glosa="TA0601",
        etapa="RESPUESTA",
        estado=estado,
        valor_objetado=valor,
        auditor_email=auditor,
        dias_restantes=dias_restantes,
        creado_en=ahora_utc() - timedelta(days=dias_vieja),
    )
    db.add(g)
    db.commit()
    return g


def _cliente(db_session, rol="COORDINADOR"):
    from app.api.deps import get_usuario_actual
    from app.main import app

    u = UsuarioRecord(id=1, email="coord@hus.gov.co", nombre="C", rol=rol, activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    return TestClient(app)


class TestCuellosDeBotella:
    def test_agrupa_por_estado_con_valor_y_antiguedad(self, db_session):
        from app.main import app

        _glosa(db_session, "RADICADA", valor=5_000_000, dias_vieja=40)
        _glosa(db_session, "RADICADA", valor=1_000_000, dias_vieja=2)
        _glosa(db_session, "RESPONDIDA", valor=800_000, dias_vieja=3)
        _glosa(db_session, "LEVANTADA", valor=9_000_000)  # cerrada: no cuenta

        with _cliente(db_session) as c:
            d = c.get("/dashboard-ejecutivo/operacion").json()
        app.dependency_overrides.clear()

        assert d["total_abiertas"] == 3
        estados = {x["estado"]: x for x in d["cuellos_por_estado"]}
        assert "LEVANTADA" not in estados  # lo cerrado no es cuello
        assert estados["RADICADA"]["cantidad"] == 2
        assert estados["RADICADA"]["valor"] == 6_000_000
        assert estados["RADICADA"]["mas_vieja_dias"] >= 40
        # Ordenado por plata atascada
        assert d["cuellos_por_estado"][0]["estado"] == "RADICADA"


class TestCargaPorAuditor:
    def test_cuenta_abiertas_vencidas_y_valor(self, db_session):
        from app.main import app

        _glosa(db_session, "RADICADA", auditor="ana@hus.gov.co", dias_restantes=-3)
        _glosa(db_session, "RADICADA", auditor="ana@hus.gov.co", dias_restantes=4)
        _glosa(db_session, "RADICADA", auditor="luis@hus.gov.co", dias_restantes=6)
        _glosa(db_session, "RADICADA", auditor=None)

        with _cliente(db_session) as c:
            d = c.get("/dashboard-ejecutivo/operacion").json()
        app.dependency_overrides.clear()

        carga = {a["auditor"]: a for a in d["carga_por_auditor"]}
        assert carga["ana@hus.gov.co"]["abiertas"] == 2
        assert carga["ana@hus.gov.co"]["vencidas"] == 1
        assert carga["luis@hus.gov.co"]["vencidas"] == 0
        assert d["sin_asignar"] == 1
        # Quien tiene vencidas aparece primero
        assert d["carga_por_auditor"][0]["auditor"] == "ana@hus.gov.co"

    def test_auditor_no_ve_el_panel(self, db_session):
        from app.main import app

        with _cliente(db_session, rol="AUDITOR") as c:
            assert c.get("/dashboard-ejecutivo/operacion").status_code == 403
        app.dependency_overrides.clear()


class TestPantalla:
    def test_el_mando_lo_muestra(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert 'id="mando-cuellos"' in html
        assert 'id="mando-carga"' in html
        assert "function loadOperacion" in html
        assert "/dashboard-ejecutivo/operacion" in html
        assert "loadOperacion();" in html  # se carga al abrir Mando
