"""Endpoints públicos del ticker de noticias del sector salud Colombia.

GET /noticias/recientes — para el dashboard del auditor
GET /noticias/stats     — estadísticas de fuentes (admin)
POST /noticias/refrescar — fuerza un fetch ahora (admin)
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.api.deps import get_usuario_actual, get_admin as get_super_admin
from app.models.db import UsuarioRecord, NoticiaSaludRecord

logger = logging.getLogger("motor_glosas")

router = APIRouter(prefix="/noticias", tags=["noticias"])


@router.get("/recientes")
async def noticias_recientes(
    limite: int = 5,
    dias: int = 14,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve las N noticias más recientes del sector salud, activas y
    publicadas en los últimos `dias` (default 14).

    Usado por el widget del dashboard al iniciar sesión el auditor.

    Si la tabla está vacía (primer arranque, scheduler aún no corrió),
    dispara un fetch en línea — UX: el primer auditor en loguear el día
    del deploy ya ve noticias en vez de un widget vacío.
    """
    if limite < 1 or limite > 50:
        limite = 5
    if dias < 1 or dias > 90:
        dias = 14

    # Si BD vacía y la app lleva 5+ minutos corriendo, dispara fetch
    # ahora (no esperamos al scheduler de 4h). Cap defensivo: solo si
    # NO hay noticias en absoluto, para no spammear las fuentes.
    total_existente = (
        db.query(NoticiaSaludRecord)
        .filter(NoticiaSaludRecord.activa == 1)
        .count()
    )
    if total_existente == 0:
        try:
            from app.services.noticias_salud_co import actualizar_noticias
            stats = await actualizar_noticias()
            logger.info(f"[NOTICIAS:auto-fetch] vacío al inicio → {stats}")
        except Exception as e:
            logger.warning(f"[NOTICIAS:auto-fetch] falló: {e}")

    # Filtrar por fecha_publicacion si existe; sino por indexada_en
    umbral = datetime.now(timezone.utc) - timedelta(days=dias)
    rows = (
        db.query(NoticiaSaludRecord)
        .filter(NoticiaSaludRecord.activa == 1)
        .filter(NoticiaSaludRecord.indexada_en >= umbral)
        .order_by(
            desc(NoticiaSaludRecord.fecha_publicacion),
            desc(NoticiaSaludRecord.indexada_en),
        )
        .limit(limite)
        .all()
    )
    return {
        "total": len(rows),
        "noticias": [
            {
                "id": r.id,
                "titulo": r.titulo,
                "resumen": r.resumen,
                "url": r.url,
                "fuente": r.fuente,
                "categoria": r.categoria,
                "fecha_publicacion": (
                    r.fecha_publicacion.isoformat() if r.fecha_publicacion else None
                ),
                "indexada_en": r.indexada_en.isoformat() if r.indexada_en else None,
            }
            for r in rows
        ],
    }


@router.get("/stats")
def noticias_stats(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_super_admin),
):
    """Estadísticas: cuántas por fuente, cuántas activas, última actualización."""
    from sqlalchemy import func
    total = db.query(func.count(NoticiaSaludRecord.id)).scalar() or 0
    activas = (
        db.query(func.count(NoticiaSaludRecord.id))
        .filter(NoticiaSaludRecord.activa == 1)
        .scalar() or 0
    )
    por_fuente = dict(
        db.query(NoticiaSaludRecord.fuente, func.count(NoticiaSaludRecord.id))
        .filter(NoticiaSaludRecord.activa == 1)
        .group_by(NoticiaSaludRecord.fuente)
        .all()
    )
    ultima = (
        db.query(NoticiaSaludRecord.indexada_en)
        .order_by(desc(NoticiaSaludRecord.indexada_en))
        .first()
    )
    return {
        "total_acumuladas": total,
        "activas": activas,
        "por_fuente": por_fuente,
        "ultima_actualizacion": ultima[0].isoformat() if ultima and ultima[0] else None,
    }


@router.post("/refrescar")
async def noticias_refrescar(
    current_user: UsuarioRecord = Depends(get_super_admin),
):
    """Fuerza un fetch ahora — útil para admin que no quiere esperar
    al scheduler cada 4h."""
    from app.services.noticias_salud_co import actualizar_noticias
    stats = await actualizar_noticias()
    return {"ok": True, "stats": stats}
