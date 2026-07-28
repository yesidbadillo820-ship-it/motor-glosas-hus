"""Middleware de Correlation ID para trazabilidad end-to-end.

Cada request recibe un ID único (UUID4) en el header X-Request-ID.
Si el cliente ya envía ese header, se reutiliza (útil para retry traces).
El ID se propaga en la respuesta y queda disponible via ContextVar
para que cualquier logger lo incluya sin modificar firmas de función.

Usa el mismo request_id_var que logging_utils.py para que los logs
estructurados incluyan el ID automáticamente.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_utils import client_ip_var, request_id_var

HEADER = "X-Request-ID"


def _ip_del_cliente(request: Request) -> str:
    """IP real del cliente detrás del túnel de Cloudflare.

    Orden de confianza: CF-Connecting-IP (lo pone Cloudflare y el cliente no
    puede falsificarlo a través del túnel) → primer salto de X-Forwarded-For →
    la IP del socket. Se recorta a 45 caracteres, que es el largo de una IPv6.
    """
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip()[:45]
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()[:45]
    cliente = getattr(request, "client", None)
    return (getattr(cliente, "host", "") or "")[:45]


def get_request_id() -> str:
    """Retorna el correlation ID del contexto actual (vacío fuera de un request)."""
    return request_id_var.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inyecta/propaga X-Request-ID en cada ciclo request/response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get(HEADER) or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        token_ip = client_ip_var.set(_ip_del_cliente(request))
        try:
            response: Response = await call_next(request)
        finally:
            client_ip_var.reset(token_ip)
            request_id_var.reset(token)
        response.headers[HEADER] = req_id
        return response
