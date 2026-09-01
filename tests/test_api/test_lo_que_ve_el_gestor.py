"""Directiva del 31-08-2026: los gestores pueden MIRAR sus espacios de trabajo.

Yesid, textual: «quiero que todos los gestores tengan permisos para mirar:
Conciliación, Papelera, Glosas ADRES… que los auditores puedan ver esos
espacios». Al revisar ruta por ruta, la única que de verdad les negaba el
mirar era la Papelera (quedó abierta en su propio cambio); las demás ya
estaban abiertas — y esta prueba lo deja ESCRITO, para que un cambio de
permisos futuro no se las cierre sin que nadie se entere.

Es la misma lección de la pantalla «Salud Total»: lo que no tiene prueba se
rompe en silencio.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ROL_AUDITOR, UsuarioRecord

# La pantalla → su consulta principal. Si el gestor puede esto, puede mirar.
PANTALLAS = [
    ("Conciliación", "/conciliaciones/"),
    ("Conciliación (estadísticas)", "/conciliaciones/estadisticas"),
    ("Papelera", "/papelera/"),
    ("Glosas ADRES (paquetes)", "/glosas-adres/paquetes"),
    ("Glosas ADRES (facturas)", "/glosas-adres/facturas"),
    ("Contratos", "/contratos/"),
    ("Consulta Normativa", "/consulta-normativa/normas"),
    ("Importación masiva (lotes)", "/lotes/"),
    ("Pre-auditoría (consolidado)", "/preauditoria/consolidado"),
    ("Pre-auditoría (oficios)", "/preauditoria/oficios"),
]


@pytest.fixture()
def gestor_client():
    from app.api.deps import get_usuario_actual
    from app.main import app

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    gestor = UsuarioRecord(
        id=1, email="gestor@hus.gov.co", rol=ROL_AUDITOR, activo=1, nombre="Gestor"
    )
    app.dependency_overrides[get_db] = lambda: iter([s]).__next__()
    # Solo se suplanta la identidad: los chequeos de rol corren de verdad.
    app.dependency_overrides[get_usuario_actual] = lambda: gestor
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        s.close()
        engine.dispose()


class TestElGestorPuedeMirarSusEspacios:
    @pytest.mark.parametrize("pantalla,ruta", PANTALLAS, ids=[p for p, _ in PANTALLAS])
    def test_la_consulta_principal_no_le_da_403(self, gestor_client, pantalla, ruta):
        r = gestor_client.get(ruta)
        assert r.status_code != 403, (
            f"{pantalla}: al gestor (rol AUDITOR) le negaron {ruta} — "
            "la directiva del 31-08-2026 dice que puede mirar este espacio"
        )
        assert r.status_code == 200, f"{pantalla}: {ruta} contestó {r.status_code}: {r.text[:200]}"
