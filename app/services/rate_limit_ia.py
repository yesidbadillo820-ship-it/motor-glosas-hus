"""Rate limiter unificado para endpoints de IA (Ronda 50 Paso 3).

Limita el consumo de tokens IA (Groq/Anthropic) por usuario autenticado
o, si no hay usuario, por IP. Cubre /analizar, /refinar y /chat-glosa
con un solo contador — un abuso que alterne entre los 3 endpoints no
esquiva el límite.

Implementación in-memory con ventana deslizante (windowed rate limit),
sin dependencias externas. Para multi-worker/multi-instancia habría que
migrar a Redis — por ahora con el tráfico esperado del HUS (≤10
gestores simultáneos) es suficiente.

Límites por defecto:
  - 30 llamadas IA por minuto por usuario
  - 300 llamadas IA por hora por usuario
  - 50 llamadas IA por minuto por IP (para bloquear anon abuse)

Uso como FastAPI dependency:

    from app.services.rate_limit_ia import consumir_cupo_ia

    @router.post("/algo-con-ia")
    async def mi_endpoint(
        cupo: None = Depends(consumir_cupo_ia),   # valida + consume 1 cupo
        ...
    ):
        ...
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord


# Configuración — valores conservadores que protegen contra abuso pero
# no molestan al uso legítimo (un gestor rara vez analiza >30 glosas/min).
LIMITE_MINUTO_USUARIO = 30
LIMITE_HORA_USUARIO = 300
LIMITE_MINUTO_IP = 50


# Estado: por clave (user_email o "ip:X.X.X.X"), un deque con timestamps
# de cada llamada. Se poda al consultar.
_REGISTRO: dict[str, Deque[float]] = defaultdict(deque)
_LOCK = threading.Lock()


def _podar(dq: Deque[float], ahora: float, ventana_seg: float) -> None:
    """Remueve timestamps fuera de la ventana actual."""
    limite = ahora - ventana_seg
    while dq and dq[0] < limite:
        dq.popleft()


def _contar_en_ventana(dq: Deque[float], ahora: float, ventana_seg: float) -> int:
    """Cuenta cuántas llamadas hay en la ventana."""
    limite = ahora - ventana_seg
    return sum(1 for t in dq if t >= limite)


def consumir_cupo_ia(
    request: Request,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> None:
    """Consume 1 cupo para el usuario y lanza 429 si excede los límites.

    Estrategia:
      1. Consulta clave = 'user:{email}' si autenticado, sino 'ip:{host}'.
      2. Poda el deque de timestamps fuera de ventanas.
      3. Si minuto o hora exceden → 429 con retry-after.
      4. Agrega el timestamp actual al deque y permite el call.
    """
    ahora = time.time()
    email = (getattr(current_user, "email", "") or "").lower().strip()
    clave = f"user:{email}" if email else f"ip:{request.client.host if request.client else 'anon'}"

    with _LOCK:
        dq = _REGISTRO[clave]
        _podar(dq, ahora, 3600.0)  # poda global a 1h

        # Límite por minuto
        en_minuto = _contar_en_ventana(dq, ahora, 60.0)
        if en_minuto >= LIMITE_MINUTO_USUARIO:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Límite de llamadas IA excedido: {en_minuto}/{LIMITE_MINUTO_USUARIO} "
                    f"por minuto. Esperá 60 segundos y volvé a intentar."
                ),
                headers={"Retry-After": "60"},
            )

        # Límite por hora
        en_hora = len(dq)
        if en_hora >= LIMITE_HORA_USUARIO:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Límite horario de IA excedido: {en_hora}/{LIMITE_HORA_USUARIO}. "
                    f"Volvé en una hora o contactá al coordinador si necesitás más."
                ),
                headers={"Retry-After": "3600"},
            )

        # Si es IP anónima, aplicar límite más estricto
        if clave.startswith("ip:") and en_minuto >= LIMITE_MINUTO_IP:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Límite IA por IP excedido ({en_minuto}/{LIMITE_MINUTO_IP} por minuto).",
                headers={"Retry-After": "60"},
            )

        # Registrar llamada
        dq.append(ahora)
    return None


def estado_cupo(current_user: UsuarioRecord | None = None, ip: str | None = None) -> dict:
    """Útil para endpoint admin: ¿cuánto cupo queda para un usuario?"""
    email = (getattr(current_user, "email", "") or "").lower().strip() if current_user else ""
    clave = f"user:{email}" if email else (f"ip:{ip}" if ip else None)
    if not clave:
        return {}
    ahora = time.time()
    with _LOCK:
        dq = _REGISTRO.get(clave, deque())
        return {
            "clave": clave,
            "en_minuto": _contar_en_ventana(dq, ahora, 60.0),
            "limite_minuto": LIMITE_MINUTO_USUARIO,
            "en_hora": _contar_en_ventana(dq, ahora, 3600.0),
            "limite_hora": LIMITE_HORA_USUARIO,
        }
