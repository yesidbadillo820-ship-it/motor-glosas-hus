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

from app.core.logging_utils import request_id_var

HEADER = "X-Request-ID"


def get_request_id() -> str:
    """Retorna el correlation ID del contexto actual (vacío fuera de un request)."""
    return request_id_var.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inyecta/propaga X-Request-ID en cada ciclo request/response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get(HEADER) or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[HEADER] = req_id
        return response
