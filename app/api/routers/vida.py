"""Capa de Vida — endpoints que le dan calidez y proactividad al motor.

Todo es ADITIVO y de solo-lectura: agrega personalidad (saludo, ánimo,
celebración de logros) sobre los datos que ya existen (GlosaRecord), sin
tocar la generación de dictámenes ni ningún endpoint previo.

  GET /vida/saludo        → saludo por hora + resumen del día + frase cálida
  GET /vida/celebraciones → victorias recientes del gestor para festejar
"""

from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.api.routers.mi_desempeno import _calcular_racha, _glosas_del_gestor
from app.core.tz import ahora_bogota, ahora_utc
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services import copy_calido

router = APIRouter(prefix="/vida", tags=["vida"])

_ESTADOS_GANADA = {"LEVANTADA", "ACEPTADA"}


def _aware(dt):
    """Normaliza a UTC-aware — SQLite devuelve datetimes naive y compararlos
    con un aware revienta (mismo cuidado que en el resto del motor)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _nombre_corto(usuario: UsuarioRecord) -> str:
    """Primer nombre para el saludo (o el prefijo del email)."""
    if usuario.nombre and usuario.nombre.strip():
        return usuario.nombre.strip().split()[0].title()
    return (usuario.email or "").split("@")[0].title() or "auditor"


@router.get("/saludo")
def saludo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Saludo personalizado + resumen humano del día del gestor."""
    ahora_b = ahora_bogota()
    inicio_hoy = ahora_utc().replace(hour=0, minute=0, second=0, microsecond=0)

    # Glosas del gestor (últimos 30 días para racha; hoy para el conteo).
    glosas_30 = _glosas_del_gestor(db, current_user, ahora_utc() - timedelta(days=30)).all()
    nuevas_hoy = sum(
        1 for g in glosas_30 if _aware(g.creado_en) and _aware(g.creado_en) >= inicio_hoy
    )

    # Próximas a vencer (≤ 3 días, no cerradas).
    por_vencer = sum(
        1
        for g in glosas_30
        if (g.dias_restantes is not None and 0 <= g.dias_restantes <= 3)
        and (g.estado or "").upper() not in {"LEVANTADA", "ACEPTADA", "ARCHIVADA", "CONCILIADA"}
    )

    # Recuperado en los últimos 7 días (glosas ganadas).
    hace_7 = ahora_utc() - timedelta(days=7)
    recuperado_semana = sum(
        float(g.valor_recuperado or 0)
        for g in glosas_30
        if _aware(g.fecha_decision_eps)
        and _aware(g.fecha_decision_eps) >= hace_7
        and (g.estado or "").upper() in _ESTADOS_GANADA
    )

    racha = _calcular_racha(glosas_30)

    return {
        "saludo": copy_calido.saludo_por_hora(ahora_b.hour),
        "nombre": _nombre_corto(current_user),
        "frase": copy_calido.frase_animo(ahora_b.timetuple().tm_yday),
        "nuevas_hoy": nuevas_hoy,
        "por_vencer": por_vencer,
        "recuperado_semana": round(recuperado_semana),
        "racha_dias": racha,
        "sin_pendientes": por_vencer == 0,
        "mensaje_pendientes": (copy_calido.mensaje_sin_pendientes() if por_vencer == 0 else None),
    }


@router.get("/celebraciones")
def celebraciones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista de logros recientes del gestor listos para festejar en la UI."""
    glosas = _glosas_del_gestor(db, current_user, ahora_utc() - timedelta(days=30)).all()
    eventos: list[dict] = []

    # Victorias de las últimas 48h (glosas ganadas con decisión reciente).
    hace_48 = ahora_utc() - timedelta(hours=48)
    ganadas = [
        g
        for g in glosas
        if _aware(g.fecha_decision_eps)
        and _aware(g.fecha_decision_eps) >= hace_48
        and (g.estado or "").upper() in _ESTADOS_GANADA
    ]
    ganadas.sort(key=lambda g: float(g.valor_recuperado or 0), reverse=True)
    for g in ganadas[:5]:
        eventos.append(
            {
                "tipo": "levantada",
                "mensaje": copy_calido.celebrar_levantada(g.eps, float(g.valor_recuperado or 0)),
                "valor": round(float(g.valor_recuperado or 0)),
                "factura": g.factura,
            }
        )

    # Racha destacable.
    racha = _calcular_racha(glosas)
    msg_racha = copy_calido.celebrar_racha(racha)
    if msg_racha:
        eventos.append({"tipo": "racha", "mensaje": msg_racha, "dias": racha})

    # Hito de monto recuperado acumulado (ventana 30 días).
    total_rec = sum(
        float(g.valor_recuperado or 0)
        for g in glosas
        if (g.estado or "").upper() in _ESTADOS_GANADA
    )
    msg_hito = copy_calido.celebrar_hito_recuperado(total_rec)
    if msg_hito:
        eventos.append({"tipo": "hito", "mensaje": msg_hito, "total": round(total_rec)})

    return {"eventos": eventos, "total": len(eventos)}
