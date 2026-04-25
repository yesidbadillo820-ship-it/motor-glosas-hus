"""Tareas de mantenimiento de BD (R57 P1).

Funciones idempotentes que se pueden invocar:
  - manualmente vía endpoint admin (para forzar limpieza)
  - desde un scheduler diario (cron en startup hooks de la app)

Diseño: cada función retorna un dict con stats para que el caller
loguee/registre cuántas filas se afectaron y cuánto espacio se liberó.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.core.tz import ahora_utc


def purgar_ai_cache_viejo(
    db: Session,
    dias: int = 30,
    dry_run: bool = False,
) -> dict:
    """Elimina entradas de ai_cache con creado_en < ahora() - dias.

    Estrategia:
      - El cache se considera obsoleto pasados N días sin importar hits
        (el modelo IA puede haber cambiado, las normas pueden haber sido
        actualizadas, etc.). El TTL lazy ya lo aplica al leer, pero
        entradas nunca-leídas se quedan.
      - dry_run=True solo cuenta sin eliminar.

    Retorna:
      {
        "total_antes": int,
        "obsoletas": int,
        "purgadas": int,           # 0 si dry_run
        "espacio_caracteres_liberado": int,  # estimación
        "dias_corte": int,
        "dry_run": bool,
      }
    """
    from app.models.db import AICacheRecord

    corte = ahora_utc() - timedelta(days=max(1, int(dias)))
    total_antes = db.query(AICacheRecord).count()

    obsoletas = (
        db.query(AICacheRecord)
        .filter(AICacheRecord.creado_en < corte)
        .all()
    )
    espacio_chars = sum(len(r.respuesta or "") for r in obsoletas)

    purgadas = 0
    if not dry_run and obsoletas:
        ids = [r.id for r in obsoletas]
        # Bulk delete por IDs (más eficiente que delete uno-a-uno)
        db.query(AICacheRecord).filter(AICacheRecord.id.in_(ids)).delete(
            synchronize_session=False,
        )
        db.commit()
        purgadas = len(ids)

    stats = {
        "total_antes": total_antes,
        "obsoletas": len(obsoletas),
        "purgadas": purgadas,
        "espacio_caracteres_liberado": espacio_chars,
        "dias_corte": dias,
        "dry_run": bool(dry_run),
    }
    logger.info(
        f"[MANTENIMIENTO] purga ai_cache: total_antes={total_antes} "
        f"obsoletas={len(obsoletas)} purgadas={purgadas} "
        f"espacio_libre={espacio_chars}c dry_run={dry_run}"
    )
    return stats


def purgar_ai_calls_viejos(
    db: Session,
    dias: int = 90,
    dry_run: bool = False,
) -> dict:
    """Elimina filas de ai_calls > N días (default 90).

    El historial de calls es útil para análisis a corto plazo (cobranza,
    detección de abuso). Mantenerlo indefinidamente infla la BD —
    típicamente 100-500 filas/día en producción.
    """
    from app.models.db import AICallRecord

    corte = ahora_utc() - timedelta(days=max(1, int(dias)))
    total_antes = db.query(AICallRecord).count()

    q_obsoletas = db.query(AICallRecord).filter(
        AICallRecord.creado_en < corte,
    )
    obsoletas = q_obsoletas.count()

    purgadas = 0
    if not dry_run and obsoletas:
        q_obsoletas.delete(synchronize_session=False)
        db.commit()
        purgadas = obsoletas

    stats = {
        "total_antes": total_antes,
        "obsoletas": obsoletas,
        "purgadas": purgadas,
        "dias_corte": dias,
        "dry_run": bool(dry_run),
    }
    logger.info(
        f"[MANTENIMIENTO] purga ai_calls: total_antes={total_antes} "
        f"obsoletas={obsoletas} purgadas={purgadas} dry_run={dry_run}"
    )
    return stats


def purgar_papelera_caducada(
    db: Session,
    dias: int = 30,
    dry_run: bool = False,
) -> dict:
    """Purga DEFINITIVAMENTE de glosas_eliminadas las que pasaron los 30
    días de ventana de restauración (regla de negocio R52 prev).
    """
    from app.models.db import GlosaEliminadaRecord

    corte = ahora_utc() - timedelta(days=max(1, int(dias)))
    total_antes = db.query(GlosaEliminadaRecord).count()
    q = db.query(GlosaEliminadaRecord).filter(
        GlosaEliminadaRecord.eliminado_en < corte,
    )
    obsoletas = q.count()
    purgadas = 0
    if not dry_run and obsoletas:
        q.delete(synchronize_session=False)
        db.commit()
        purgadas = obsoletas
    stats = {
        "total_antes": total_antes,
        "obsoletas": obsoletas,
        "purgadas": purgadas,
        "dias_corte": dias,
        "dry_run": bool(dry_run),
    }
    logger.info(
        f"[MANTENIMIENTO] purga papelera: total_antes={total_antes} "
        f"obsoletas={obsoletas} purgadas={purgadas} dry_run={dry_run}"
    )
    return stats


def ejecutar_mantenimiento_completo(db: Session, dry_run: bool = False) -> dict:
    """Ejecuta todas las purgas en orden. Útil para el scheduler diario."""
    return {
        "ai_cache": purgar_ai_cache_viejo(db, dias=30, dry_run=dry_run),
        "ai_calls": purgar_ai_calls_viejos(db, dias=90, dry_run=dry_run),
        "papelera": purgar_papelera_caducada(db, dias=30, dry_run=dry_run),
        "ejecutado_en": ahora_utc().isoformat(),
    }
