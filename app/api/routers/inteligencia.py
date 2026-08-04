"""Centro de Inteligencia: el sistema dice qué hacer hoy, no solo qué pasó.

Un solo endpoint de lectura que barre toda la operación (vencimientos,
malla contractual, verificaciones sin contrato, conciliaciones próximas,
actas a medio cuadrar) y devuelve la lista priorizada de acciones con su
plata en juego. Lo consumen la pantalla Inteligencia y la IA del chat.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services import centro_inteligencia

router = APIRouter(prefix="/inteligencia", tags=["inteligencia"])


@router.get("/diagnostico")
def diagnostico_operacion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Qué hay que hacer hoy, ordenado por prioridad y valor.

    Es de solo lectura y lo ve cualquier usuario autenticado: dirigir el
    día no es información reservada — esconderla es lo que hace que lo
    urgente se entere tarde.
    """
    return centro_inteligencia.diagnostico(db)
