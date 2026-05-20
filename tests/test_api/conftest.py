"""
Pytest configuration for API tests.

El fixture `client` ANTES hacía ``with TestClient(app)``, lo que dispara
el lifespan de producción (retry de BD con sleeps de hasta ~60s,
schedulers, reindex de soportes, chequeos de red). En el entorno de test
ese startup se bloqueaba y colgaba la suite entera: 56 archivos de
test_api quedaban en timeout y `pytest` nunca terminaba.

Ahora el fixture replica SOLO lo que los tests necesitan del lifespan
(crear tablas + sembrar el admin) y usa ``TestClient(app)`` SIN el
context manager, de modo que el lifespan pesado no corre.
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _preparar_db():
    """Crea las tablas y siembra el admin, como hace el lifespan pero
    sin sleeps/schedulers/red. Best-effort: no debe romper la fixture."""
    from app.database import Base, engine, SessionLocal

    Base.metadata.create_all(bind=engine)

    try:
        import os
        from app.models.db import UsuarioRecord
        from app.auth import get_password_hash

        db = SessionLocal()
        try:
            if db.query(UsuarioRecord).count() == 0:
                admin_pass = os.getenv("ADMIN_PASSWORD") or "admin12345"
                db.add(
                    UsuarioRecord(
                        nombre="Auditor Principal",
                        email="admin@hus.gov.co",
                        password_hash=get_password_hash(admin_pass),
                        rol="SUPER_ADMIN",
                        activo=1,
                        must_change_password=0,
                    )
                )
                db.commit()
        finally:
            db.close()
    except Exception:
        # Si el seed falla, los tests que no usan auth siguen corriendo.
        pass


@pytest.fixture
def client():
    """FastAPI test client SIN ejecutar el lifespan de producción.

    Las tablas y el admin se preparan acá directamente.
    """
    from app.main import app

    _preparar_db()
    # Sin `with`: Starlette NO dispara startup/shutdown (lifespan), que
    # en test se bloqueaba (retry BD + schedulers + red).
    test_client = TestClient(app)
    yield test_client
