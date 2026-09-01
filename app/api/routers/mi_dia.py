"""«Mi día» — la pantalla de entrada del gestor.

Tres columnas y nada más: responder lo que llegó, revisar lo que el motor
marcó y radicar lo que está listo. El resto de pantallas sigue ahí para
quien las necesite, pero dejan de ser el punto de partida.

El reparto y el orden viven en `app/services/mi_dia.py`; aquí solo se
resuelve de quién son las glosas y se responde.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord
from app.repositories.glosa_repository import GlosaRepository
from app.services.mi_dia import armar_mi_dia

# OJO CON LA RUTA: `GET /mi-dia` ya existe desde antes en `health.py` — es el
# resumen personal del gestor (tareas del día, saludo, alertas). Este tablero
# cuelga de `/mi-dia/tablero` para no pisarlo. Se pisó una vez, el 26-08-2026:
# como este router se registra antes que el de health, la ruta vieja quedó
# muerta sin que nada lo dijera. Lo cazó el CI, y quedó una prueba que impide
# que dos rutas compartan camino y método.
router = APIRouter(prefix="/mi-dia", tags=["mi-dia"])


class GlosaDelDiaOut(BaseModel):
    id: int | None = None
    factura: str = ""
    eps: str = ""
    codigo_glosa: str = ""
    valor_objetado: float = 0
    dias_que_faltan: int | None = None
    plazo_sin_fecha: bool = False
    vencida: bool = False
    motivo: str = ""


class ColumnaOut(BaseModel):
    cantidad: int = 0
    valor: float = 0
    vencidas: int = 0
    glosas: list[GlosaDelDiaOut] = []
    hay_mas: int = 0


class MiDiaOut(BaseModel):
    generado_en: str
    responder: ColumnaOut
    revisar: ColumnaOut
    radicar: ColumnaOut
    total_abiertas: int = 0
    valor_en_riesgo: float = 0
    vencidas: int = 0


@router.get("/tablero", response_model=MiDiaOut)
def mi_dia(
    por_columna: int = Query(25, ge=5, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Las tres cosas que el gestor hace hoy, ordenadas por lo que más urge.

    Dentro de cada columna: primero lo que vence antes; a igualdad de días,
    lo de más plata. Lo que no tiene plazo conocido va al final — no se le
    inventa uno.
    """
    repo = GlosaRepository(db)
    equipo = getattr(current_user, "equipo", None)
    emails_equipo = repo.emails_del_mismo_equipo(equipo) if equipo else None
    glosas = repo.listar_por_gestor(
        current_user.email,
        current_user.nombre,
        emails_equipo=emails_equipo,
    )
    return armar_mi_dia(glosas, limite_por_columna=por_columna)
