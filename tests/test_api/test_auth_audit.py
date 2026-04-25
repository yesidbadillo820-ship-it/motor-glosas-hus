"""Tests de auditoría de autenticación (R54 P2).

Verifica que los intentos de login (exitoso y fallido) y los intentos
2FA fallidos se registren en el logger estructurado para auditoría
de seguridad y detección de brute-force.
"""
from __future__ import annotations

import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_password_hash
from app.database import Base
from app.models.db import UsuarioRecord


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    s.add(UsuarioRecord(
        email="auditor@hus.com",
        nombre="Auditor Test",
        rol="AUDITOR",
        password_hash=get_password_hash("Pass1234!"),
        activo=1,
    ))
    s.commit()
    try:
        yield s
    finally:
        s.close()


def _request_real(ip="127.0.0.1"):
    """slowapi exige starlette.Request real, no mock."""
    from starlette.requests import Request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/token",
        "headers": [],
        "client": (ip, 0),
        "query_string": b"",
    }
    return Request(scope)


class _FakeForm:
    def __init__(self, username, password):
        self.username = username
        self.password = password


@pytest.mark.asyncio
async def test_login_fallido_se_logea_warning(db, caplog):
    """REGRESIÓN R54 P2: intentos con credenciales malas deben quedar
    en el log con [AUTH-FAIL] para auditoría."""
    from app.api.routers.auth_router import login_for_access_token
    from fastapi import HTTPException
    caplog.set_level(logging.WARNING, logger="motor_glosas")
    with pytest.raises(HTTPException) as exc:
        await login_for_access_token(
            request=_request_real(),
            form_data=_FakeForm("auditor@hus.com", "wrong-pass"),
            totp=None,
            db=db,
        )
    assert exc.value.status_code == 401
    # Debe haber un warning con AUTH-FAIL y el email del intento
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "AUTH-FAIL" in msgs
    assert "auditor@hus.com" in msgs


@pytest.mark.asyncio
async def test_login_exitoso_se_logea_info(db, caplog):
    from app.api.routers.auth_router import login_for_access_token
    caplog.set_level(logging.INFO, logger="motor_glosas")
    resp = await login_for_access_token(
        request=_request_real(),
        form_data=_FakeForm("auditor@hus.com", "Pass1234!"),
        totp=None,
        db=db,
    )
    assert resp["access_token"]
    assert resp["rol"] == "AUDITOR"
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "AUTH-OK" in msgs
