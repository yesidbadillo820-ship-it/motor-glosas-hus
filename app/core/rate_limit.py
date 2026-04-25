"""Rate limiter compartido (R53 P1).

Vive en su propio módulo para que tanto app/main.py como los routers que
necesitan @limiter.limit(...) lo puedan importar sin disparar imports
circulares (main importa los routers, los routers importan el limiter).
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


def _limit_key_user_or_ip(request) -> str:
    """Key-func del rate limiter: prioriza el email del usuario autenticado
    (JWT) sobre la IP. Evita que un usuario abra varias pestañas/VPN y se
    escape del límite; y evita que una oficina compartiendo NAT tumbe a
    todos sus usuarios por un solo spammer.
    """
    cfg = get_settings()
    try:
        auth = (request.headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer ") and len(auth) > 16:
            from jose import jwt as _jwt
            payload = _jwt.decode(
                auth.split(" ", 1)[1].strip(),
                cfg.secret_key,
                algorithms=[cfg.algorithm],
            )
            email = (payload or {}).get("sub") or (payload or {}).get("email")
            if email:
                return f"user:{email}"
    except Exception:
        pass
    return get_remote_address(request)


# Instancia única — la importan main.py (para registrar handler y middleware)
# y los routers que decoran endpoints con @limiter.limit("X/minute").
limiter = Limiter(key_func=_limit_key_user_or_ip)
