"""Tests del rate_limit (R78 P2)."""
from __future__ import annotations

from app.core.rate_limit import _limit_key_user_or_ip, limiter


class _FakeReq:
    """Mock minimal de Request para el key-func."""
    def __init__(self, headers=None, ip="1.2.3.4"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": ip})()
        self.scope = {"client": (ip, 0)}


def test_limiter_es_singleton():
    """Múltiples imports deben devolver el mismo objeto."""
    from app.core.rate_limit import limiter as l1
    from app.core.rate_limit import limiter as l2
    assert l1 is l2


def test_limit_key_sin_token_usa_ip():
    """Sin Authorization header, fallback a IP del cliente."""
    req = _FakeReq()
    key = _limit_key_user_or_ip(req)
    assert "1.2.3.4" in key


def test_limit_key_con_token_invalido_usa_ip():
    """Bearer mal formado → fallback a IP."""
    req = _FakeReq(headers={"authorization": "Bearer xyz-not-jwt"})
    key = _limit_key_user_or_ip(req)
    # Debe caer a IP, no romper
    assert "1.2.3.4" in key


def test_limit_key_authorization_no_bearer_usa_ip():
    """Header Authorization que NO es Bearer → IP."""
    req = _FakeReq(headers={"authorization": "Basic abc"})
    key = _limit_key_user_or_ip(req)
    assert "1.2.3.4" in key


def test_limit_key_con_token_valido_devuelve_email():
    """JWT válido con sub=email → key 'user:email'."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt as _jwt

    from app.core.config import get_settings
    cfg = get_settings()
    payload = {
        "sub": "auditor@hus.com",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = _jwt.encode(payload, cfg.secret_key, algorithm=cfg.algorithm)
    req = _FakeReq(headers={"authorization": f"Bearer {token}"})
    key = _limit_key_user_or_ip(req)
    assert key == "user:auditor@hus.com"
