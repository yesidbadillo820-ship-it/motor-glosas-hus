"""Retro-aplicación batch del detector de texto fijo (Ronda 22).

Después de desplegar Ronda 21, hay un backlog de glosas pre-existentes
que caen en RATIFICADA o EXTEMPORÁNEA pero no tienen dictamen pre-rellenado
(porque el detector aún no existía cuando entraron). Este módulo recorre
la BD una sola vez y aplica el detector a todas las candidatas.

Modo dry_run (default True):
  Solo reporta qué glosas SERÍAN afectadas sin mutar nada. Útil para que
  el coordinador revise antes de apretar el gatillo.

Modo ejecución (dry_run=False):
  Aplica el detector y persiste los cambios. Respeta la regla idempotente
  de aplicar_texto_fijo_si_corresponde:
    - No sobreescribe dictamen IA válido
    - No reescribe texto fijo del mismo tipo

La función es segura de correr múltiples veces.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.models.db import GlosaRecord
from app.services.texto_fijo_detector import (
    aplicar_texto_fijo_si_corresponde,
    clasificar_texto_fijo,
)


def retro_aplicar(
    db: Session,
    dry_run: bool = True,
    limite: Optional[int] = None,
    ventana_dias: int = 365,
) -> dict:
    """Recorre glosas candidatas y aplica texto fijo donde corresponda.

    Candidatas:
      - creadas dentro de la ventana_dias
      - sin dictamen, O con dictamen pero sin modelo_ia 'texto_fijo'
        (potenciales candidatas a reescritura si ahora aplica RATIFICADA)
      - estado no RESUELTA ni ARCHIVADA

    Retorna stats con contadores por tipo y lista de IDs afectados
    (limitada a 200 para no saturar el response).
    """
    desde = datetime.utcnow() - timedelta(days=max(1, int(ventana_dias)))

    q = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= desde)
        .filter(
            ~GlosaRecord.estado.in_(["RESUELTA", "ARCHIVADA", "CERRADA"])
        )
    )
    if limite:
        q = q.limit(int(limite))
    candidatas = q.all()

    stats = {
        "dry_run": bool(dry_run),
        "total_analizadas": len(candidatas),
        "aplicarian_ratificada": 0,
        "aplicarian_extemporanea": 0,
        "no_aplican": 0,
        "skip_por_idempotencia": 0,
        "aplicadas": 0,
        "errores": 0,
        "ejemplos_ratificada": [],
        "ejemplos_extemporanea": [],
    }

    for g in candidatas:
        try:
            clase = clasificar_texto_fijo(g)
            if clase is None:
                stats["no_aplican"] += 1
                continue

            tipo = clase["tipo"]
            if tipo == "RATIFICADA":
                stats["aplicarian_ratificada"] += 1
                if len(stats["ejemplos_ratificada"]) < 50:
                    stats["ejemplos_ratificada"].append({
                        "glosa_id": g.id,
                        "eps": g.eps,
                        "codigo": g.codigo_glosa,
                    })
            elif tipo == "EXTEMPORANEA":
                stats["aplicarian_extemporanea"] += 1
                if len(stats["ejemplos_extemporanea"]) < 50:
                    stats["ejemplos_extemporanea"].append({
                        "glosa_id": g.id,
                        "eps": g.eps,
                        "codigo": g.codigo_glosa,
                        "dias": clase.get("dias_extemporaneidad"),
                    })

            if dry_run:
                continue

            # Ejecución real
            r = aplicar_texto_fijo_si_corresponde(g)
            if r is None:
                # Idempotente (ya tenía dictamen IA o mismo tipo)
                stats["skip_por_idempotencia"] += 1
            else:
                stats["aplicadas"] += 1
        except Exception as e:
            stats["errores"] += 1
            logger.warning(f"[TEXTO-FIJO-BATCH] Glosa {g.id} falló: {e}")
            if not dry_run:
                db.rollback()

    if not dry_run:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            stats["errores"] += 1
            logger.error(f"[TEXTO-FIJO-BATCH] commit final falló: {e}")

    stats["timestamp"] = datetime.utcnow().isoformat()
    return stats
