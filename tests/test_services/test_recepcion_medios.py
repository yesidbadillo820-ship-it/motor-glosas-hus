"""Fase 3 MEDIOS: _a_fecha robusto + estado del registro de importación."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.recepcion_service import _a_fecha


@pytest.mark.parametrize("entrada,esperado", [
    ("15/01/2025", datetime(2025, 1, 15)),
    ("2025-01-15", datetime(2025, 1, 15)),
    ("2025.01.15", datetime(2025, 1, 15)),       # puntos
    ("2025/01/15", datetime(2025, 1, 15)),       # %Y/%m/%d
    ("15 01 2025", datetime(2025, 1, 15)),       # espacios
    ("2025-01-15T00:00:00", datetime(2025, 1, 15)),  # ISO con T
    (45672, datetime(2025, 1, 15)),              # serial Excel (num)
    ("45672", datetime(2025, 1, 15)),            # serial Excel (texto)
])
def test_a_fecha_formatos_ampliados(entrada, esperado):
    assert _a_fecha(entrada) == esperado


@pytest.mark.parametrize("entrada", [None, "", "no es fecha", "32/13/2025"])
def test_a_fecha_invalida_devuelve_none(entrada):
    assert _a_fecha(entrada) is None


@pytest.fixture
def db_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


@pytest.mark.parametrize("envio,esperado", [
    ({"enviados": 5, "gestores_sin_email": []}, "ENVIADO"),
    ({"enviados": 3, "gestores_sin_email": ["JUAN"]}, "PARCIAL"),
    ({"enviados": 0, "gestores_sin_email": ["JUAN"]}, "SIN_DESTINATARIOS"),
    ({"enviados": 0}, "SIN_DESTINATARIOS"),
])
def test_actualizar_estado_recepcion(monkeypatch, db_session, envio, esperado):
    from app.models.db import ImportacionRecepcionRecord
    import app.services.auto_responder_service as ar

    rec = ImportacionRecepcionRecord(
        usuario_email="x@hus.com", archivo_nombre="r.xlsx",
        total_glosas=1, glosa_ids="[1]", estado="LISTO",
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)

    # _actualizar_estado_recepcion hace `from app.database import
    # SessionLocal` adentro → hay que parchear ahí.
    import app.database as dbmod
    monkeypatch.setattr(dbmod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    ar._actualizar_estado_recepcion(rec.id, envio)
    db_session.refresh(rec)
    assert rec.estado == esperado


def test_actualizar_estado_recepcion_sin_rec_id_no_rompe():
    import app.services.auto_responder_service as ar
    ar._actualizar_estado_recepcion(None, {"enviados": 1})
