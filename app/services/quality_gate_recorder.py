"""Registro determinístico de ejecuciones del Quality Gate en BD.

Persiste cada `QualityGateResult` en la tabla `quality_gate_runs` para
que el dashboard pueda mostrar métricas reales:
  - Tasa de aprobación global
  - % rechazos en pre vs post
  - Modelos que más aprueban
  - Razones de rechazo recurrentes
  - Trend temporal

Llamado desde el adapter después de ejecutar el orchestrator.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.services.quality_gate import QualityGateResult

logger = logging.getLogger("motor_glosas.qg_recorder")


def registrar_run(
    db: Session,
    resultado: QualityGateResult,
    *,
    glosa_id: int | None = None,
    eps: str = "",
    codigo_glosa: str = "",
    creado_por: str = "",
    tiempo_ms: int | None = None,
) -> int | None:
    """Persiste un run del Quality Gate en BD.

    Returns:
        El ID del registro creado, o None si falló (no bloquea el flujo).
    """
    try:
        from app.models.db import QualityGateRunRecord
    except ImportError:
        logger.warning("[QG-Rec] QualityGateRunRecord no disponible aún")
        return None

    try:
        razones = []
        if resultado.intentos:
            for i in resultado.intentos:
                if i.post_validation and i.post_validation.razones_rechazo:
                    razones.extend(i.post_validation.razones_rechazo[:3])
            razones = list(set(razones))[:10]  # dedup + cap

        rec = QualityGateRunRecord(
            glosa_id=glosa_id,
            estado=resultado.estado,
            score_final=resultado.score_final,
            modelo_final=resultado.modelo_final or "",
            n_intentos=len(resultado.intentos),
            n_regeneraciones=resultado.n_regeneraciones,
            razones_rechazo=json.dumps(razones, ensure_ascii=False) if razones else None,
            pre_aprobado=1 if resultado.pre_validation and resultado.pre_validation.aprobado else 0,
            tiempo_ms=tiempo_ms,
            eps=eps[:120],
            codigo_glosa=codigo_glosa[:20],
            familia_codigo=(
                resultado.pre_validation.familia_codigo[:5] if resultado.pre_validation else ""
            ),
            es_ratificacion=0,  # se podría parametrizar
            creado_por=creado_por[:200],
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec.id
    except Exception as e:
        logger.warning(f"[QG-Rec] No se pudo persistir: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


class QGTimer:
    """Context manager para medir tiempo del run en ms."""

    def __init__(self) -> None:
        self.start = 0.0
        self.elapsed_ms = 0

    def __enter__(self) -> "QGTimer":
        self.start = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        self.elapsed_ms = int((time.time() - self.start) * 1000)


def estadisticas_recientes(db: Session, dias: int = 7) -> dict:
    """Calcula estadísticas agregadas de los últimos N días."""
    try:
        from datetime import datetime, timedelta, timezone

        from app.models.db import QualityGateRunRecord
    except ImportError:
        return {"total": 0, "error": "QualityGateRunRecord no disponible"}

    try:
        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        rows = db.query(QualityGateRunRecord).filter(QualityGateRunRecord.creado_en >= desde).all()

        if not rows:
            return {
                "total": 0,
                "dias": dias,
                "por_estado": {},
                "score_promedio": 0,
                "tiempo_promedio_ms": 0,
                "tasa_aprobacion_pct": 0,
                "por_modelo": {},
                "por_familia": {},
            }

        # Agregaciones
        por_estado: dict[str, int] = {}
        por_modelo: dict[str, dict[str, int]] = {}  # modelo → {aprobado, rechazado}
        por_familia: dict[str, int] = {}
        suma_score = 0
        suma_tiempo = 0
        n_con_tiempo = 0
        aprobados = 0
        n_regeneraciones = 0

        for r in rows:
            por_estado[r.estado] = por_estado.get(r.estado, 0) + 1
            if r.modelo_final:
                m = por_modelo.setdefault(r.modelo_final, {"aprobado": 0, "rechazado": 0})
                if r.estado == "APROBADO":
                    m["aprobado"] += 1
                else:
                    m["rechazado"] += 1
            if r.familia_codigo:
                por_familia[r.familia_codigo] = por_familia.get(r.familia_codigo, 0) + 1
            suma_score += r.score_final or 0
            if r.tiempo_ms:
                suma_tiempo += r.tiempo_ms
                n_con_tiempo += 1
            if r.estado == "APROBADO":
                aprobados += 1
            n_regeneraciones += r.n_regeneraciones or 0

        total = len(rows)
        return {
            "total": total,
            "dias": dias,
            "por_estado": por_estado,
            "score_promedio": round(suma_score / total, 1),
            "tiempo_promedio_ms": round(suma_tiempo / n_con_tiempo) if n_con_tiempo else 0,
            "tasa_aprobacion_pct": round(100 * aprobados / total, 1),
            "regeneraciones_promedio": round(n_regeneraciones / total, 2),
            "por_modelo": por_modelo,
            "por_familia": por_familia,
        }
    except Exception as e:
        logger.warning(f"[QG-Rec] estadisticas_recientes falló: {e}")
        return {"total": 0, "error": str(e)}
