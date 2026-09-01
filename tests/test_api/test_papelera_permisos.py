"""«Que los gestores tengan permisos para MIRAR la papelera» (31-08-2026).

Directiva de Yesid. Antes, hasta los listados de la papelera exigían rol de
coordinación: el gestor que no encontraba una glosa no tenía cómo saber si
alguien la había eliminado — abría la pantalla y recibía un 403.

La línea que se prueba acá:

  · MIRAR (listar, buscar, estadísticas) — AUDITOR o superior.
  · RESTAURAR y PURGAR — siguen siendo SOLO de coordinación: eso ya no es
    mirar, revive o destruye registros.
  · VIEWER sigue sin ver: mirar es de los gestores, no de cualquier sesión.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import (
    ROL_AUDITOR,
    ROL_COORDINADOR,
    ROL_VIEWER,
    GlosaEliminadaRecord,
    UsuarioRecord,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(
        GlosaEliminadaRecord(
            glosa_id_original=1,
            snapshot_json=json.dumps({"eps": "FAMISANAR", "factura": "FE-1"}),
            eliminado_por="coordinacion@hus.gov.co",
            eliminado_en=datetime.now(timezone.utc) - timedelta(days=2),
            motivo="prueba",
        )
    )
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _cliente(db_session, rol: str) -> TestClient:
    from app.api.deps import get_usuario_actual
    from app.main import app

    usuario = UsuarioRecord(id=1, email=f"{rol.lower()}@hus.gov.co", rol=rol, activo=1, nombre=rol)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    # Solo se suplanta la identidad: los chequeos de rol corren de verdad.
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    return TestClient(app)


@pytest.fixture()
def limpiar_overrides():
    from app.main import app

    yield
    app.dependency_overrides.clear()


MIRAR = ["/papelera/", "/papelera/stats", "/papelera/buscar"]


class TestElGestorPuedeMirar:
    @pytest.mark.parametrize("ruta", MIRAR)
    def test_auditor_ve(self, db_session, limpiar_overrides, ruta):
        r = _cliente(db_session, ROL_AUDITOR).get(ruta)
        assert r.status_code == 200, r.text

    def test_y_el_listado_trae_lo_eliminado_con_quien_y_cuando(self, db_session, limpiar_overrides):
        d = _cliente(db_session, ROL_AUDITOR).get("/papelera/").json()
        assert len(d) == 1
        assert d[0]["eps"] == "FAMISANAR"
        assert d[0]["eliminado_por"] == "coordinacion@hus.gov.co"


class TestMirarNoEsTocar:
    """Restaurar y purgar reviven o destruyen registros: siguen de coordinación."""

    def test_auditor_no_puede_restaurar(self, db_session, limpiar_overrides):
        r = _cliente(db_session, ROL_AUDITOR).post("/papelera/1/restaurar")
        assert r.status_code == 403
        assert "COORDINADOR" in r.json()["detail"]

    def test_auditor_no_puede_purgar(self, db_session, limpiar_overrides):
        assert _cliente(db_session, ROL_AUDITOR).delete("/papelera/1").status_code == 403

    def test_coordinacion_conserva_todo(self, db_session, limpiar_overrides):
        c = _cliente(db_session, ROL_COORDINADOR)
        assert c.get("/papelera/").status_code == 200
        assert c.post("/papelera/1/restaurar").status_code == 200
        # Restaurada: purgar esa entrada ya no aplica, pero el permiso sí pasa
        # el chequeo de rol (404 = no existe, no 403 = prohibido).
        assert c.delete("/papelera/1").status_code in (200, 404)


class TestElViewerSigueAfuera:
    @pytest.mark.parametrize("ruta", MIRAR)
    def test_viewer_no_ve(self, db_session, limpiar_overrides, ruta):
        assert _cliente(db_session, ROL_VIEWER).get(ruta).status_code == 403
