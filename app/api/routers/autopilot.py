"""Router del autopilot de recomendación (Ronda 18).

Expone el servicio `autopilot_service` al frontend:

  GET /autopilot/glosa/{id}
    → evalúa UNA glosa específica y devuelve estado + confianza + razones

  GET /autopilot/bandeja?auditor_email=...
    → evalúa la bandeja (PENDIENTE) del auditor actual (o de otro si es
      coordinador/super_admin). Devuelve conteo por estado + lista completa.

  GET /autopilot/mi-bandeja
    → atajo: fuerza el auditor_email al usuario autenticado.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_coordinador_o_admin
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord, ROL_COORDINADOR, ROL_SUPER_ADMIN
from pydantic import BaseModel, Field

from app.services.autopilot_service import (
    evaluar_bandeja,
    evaluar_glosa_autopilot,
)


class BatchAprobarBody(BaseModel):
    """Ronda 34: payload para aprobar en lote glosas LISTA_ENVIAR."""
    ids: list[int] = Field(..., description="IDs de glosas a marcar respondidas")
    confianza_minima: float = Field(0.85, ge=0.0, le=1.0)
    dry_run: bool = False
from app.services.texto_fijo_detector import (
    aplicar_texto_fijo_si_corresponde,
    clasificar_texto_fijo,
)
from app.services.texto_fijo_batch import retro_aplicar
from app.services.metricas_autopilot import metricas_autopilot

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.get("/glosa/{glosa_id}")
def evaluar_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    # Auditores solo pueden evaluar sus propias glosas
    if current_user.rol not in (ROL_COORDINADOR, ROL_SUPER_ADMIN):
        if g.auditor_email and g.auditor_email != current_user.email:
            raise HTTPException(
                status_code=403,
                detail="Solo podés evaluar glosas asignadas a vos.",
            )
    res = evaluar_glosa_autopilot(db, g)
    return {
        "glosa_id": glosa_id,
        "estado_autopilot": res.estado,
        "confianza": res.confianza,
        "razones_a_favor": res.razones_a_favor,
        "razones_en_contra": res.razones_en_contra,
        "acciones_sugeridas": res.acciones_sugeridas,
        "detalle": res.detalle,
    }


@router.get("/bandeja")
def bandeja(
    auditor_email: Optional[str] = Query(None),
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Solo coordinador/super_admin puede mirar bandejas ajenas."""
    return evaluar_bandeja(db, auditor_email=auditor_email, limite=limite)


@router.get("/mi-bandeja")
def mi_bandeja(
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    return evaluar_bandeja(db, auditor_email=current_user.email, limite=limite)


@router.get("/texto-fijo/{glosa_id}")
def previsualizar_texto_fijo(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Muestra qué texto fijo aplicaría (Ronda 21). No muta la BD."""
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    clase = clasificar_texto_fijo(g)
    if clase is None:
        return {
            "glosa_id": glosa_id,
            "aplica": False,
            "mensaje": "La glosa no es RATIFICADA ni EXTEMPORÁNEA — requiere análisis IA.",
        }
    return {"glosa_id": glosa_id, "aplica": True, **clase}


@router.post("/preparar-dia")
def preparar_dia(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Ronda 37: master action que corre toda la higiene matinal en un
    solo click. Ideal para el coordinador apenas abre el sistema.

    Ejecuta en orden:
      1. Aplicar texto fijo a todas las glosas RATIFICADAS/EXTEMPORÁNEAS
         sin dictamen (Ronda 22).
      2. Marcar RESPONDIDAS las que ya tienen texto fijo pero seguían
         en workflow pendiente (Ronda 34 hotfix).
      3. Contabilizar el impacto total.

    Idempotente. Seguro correrlo muchas veces al día.
    """
    from datetime import datetime, timezone as _tz
    from app.services.texto_fijo_batch import retro_aplicar

    # Paso 1: aplicar texto fijo al backlog
    stats_aplicar = retro_aplicar(db, dry_run=False, ventana_dias=365)

    # Paso 2: marcar respondidas las que tienen texto fijo pero están pendientes
    q = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.modelo_ia.ilike("%texto_fijo%"))
        .filter(~GlosaRecord.workflow_state.in_(["RESPONDIDA", "CONCILIADA", "LEVANTADA"]))
    )
    candidatas = q.all()
    marcadas_respondidas = 0
    for g in candidatas:
        try:
            g.workflow_state = "RESPONDIDA"
            if not g.fecha_decision_eps:
                g.fecha_decision_eps = datetime.now(_tz.utc)
            if not (g.nota_workflow or "").strip():
                m = (g.modelo_ia or "").lower()
                tipo = "RATIFICADA" if "ratificada" in m else ("EXTEMPORANEA" if "extemporanea" in m else "texto_fijo")
                g.nota_workflow = f"Respondida automáticamente: texto fijo {tipo}"
            marcadas_respondidas += 1
        except Exception:
            pass

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return {
            "error": str(e)[:200],
            "aplicar_texto_fijo": stats_aplicar,
            "marcadas_respondidas": marcadas_respondidas,
        }

    return {
        "ok": True,
        "timestamp": datetime.now(_tz.utc).isoformat(),
        "aplicar_texto_fijo": {
            "total_analizadas": stats_aplicar.get("total_analizadas", 0),
            "aplicadas": stats_aplicar.get("aplicadas", 0),
            "ratificadas_detectadas": stats_aplicar.get("aplicarian_ratificada", 0),
            "extemporaneas_detectadas": stats_aplicar.get("aplicarian_extemporanea", 0),
            "skip_por_idempotencia": stats_aplicar.get("skip_por_idempotencia", 0),
        },
        "marcadas_respondidas": marcadas_respondidas,
        "resumen_humano": (
            f"Se aplicó texto fijo a {stats_aplicar.get('aplicadas', 0)} glosa(s). "
            f"Se marcaron como RESPONDIDAS {marcadas_respondidas} que ya tenían el texto. "
            f"El equipo puede empezar el día sin tocar casos mecánicos."
        ),
    }


@router.post("/texto-fijo/marcar-respondidas")
def marcar_respondidas_texto_fijo(
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Hotfix Ronda 34: barre TODAS las glosas que tienen dictamen texto fijo
    aplicado (RATIFICADA o EXTEMPORÁNEA) pero aún están en workflow pendiente,
    y las mueve a RESPONDIDA. Es lo que permite que los casos mecánicos salgan
    de 'Pendientes' sin que el auditor haga click.

    Idempotente — corrida múltiples veces no duplica nada.
    """
    from datetime import datetime, timezone as _tz
    q = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.modelo_ia.ilike("%texto_fijo%"))
        .filter(~GlosaRecord.workflow_state.in_(["RESPONDIDA", "CONCILIADA", "LEVANTADA"]))
    )
    candidatas = q.all()
    stats = {
        "dry_run": bool(dry_run),
        "total_candidatas": len(candidatas),
        "marcadas": 0,
        "errores": 0,
        "ids": [],
    }
    if dry_run:
        stats["ids"] = [g.id for g in candidatas[:200]]
        return stats
    for g in candidatas:
        try:
            g.workflow_state = "RESPONDIDA"
            if not g.fecha_decision_eps:
                g.fecha_decision_eps = datetime.now(_tz.utc)
            if not (g.nota_workflow or "").strip():
                tipo = ""
                m = (g.modelo_ia or "").lower()
                if "ratificada" in m: tipo = "RATIFICADA"
                elif "extemporanea" in m: tipo = "EXTEMPORANEA"
                g.nota_workflow = f"Respondida automáticamente: texto fijo {tipo}".strip()
            stats["marcadas"] += 1
            stats["ids"].append(g.id)
        except Exception:
            stats["errores"] += 1
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": str(e)[:200], **stats}
    return stats


@router.post("/batch-aprobar")
def batch_aprobar(
    body: BatchAprobarBody,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Aprueba en lote las glosas LISTA_ENVIAR con alta confianza (Ronda 34).

    Revalida cada glosa contra el autopilot. Solo marca RESPONDIDA si:
      - estado_autopilot == 'LISTA_ENVIAR'
      - confianza >= confianza_minima
      - el usuario es dueño de la glosa (o coordinador/super_admin)

    dry_run=True solo reporta qué se HARÍA sin mutar.
    Devuelve estadísticas por id.
    """
    from datetime import datetime, timezone
    resultados = []
    aprobadas = 0
    saltadas = 0
    errores = 0
    es_coord = current_user.rol in (ROL_COORDINADOR, ROL_SUPER_ADMIN)

    for gid in body.ids[:200]:  # safety cap
        g = db.query(GlosaRecord).filter(GlosaRecord.id == gid).first()
        if not g:
            resultados.append({"id": gid, "accion": "no_encontrada"})
            errores += 1
            continue
        if not es_coord and g.auditor_email and g.auditor_email != current_user.email:
            resultados.append({"id": gid, "accion": "sin_permiso"})
            saltadas += 1
            continue
        try:
            res = evaluar_glosa_autopilot(db, g)
        except Exception as e:
            resultados.append({"id": gid, "accion": "error_evaluando", "error": str(e)[:100]})
            errores += 1
            continue

        if res.estado != "LISTA_ENVIAR" or res.confianza < body.confianza_minima:
            resultados.append({
                "id": gid,
                "accion": "saltada",
                "estado_autopilot": res.estado,
                "confianza": res.confianza,
            })
            saltadas += 1
            continue

        if body.dry_run:
            resultados.append({
                "id": gid,
                "accion": "aprobaria",
                "confianza": res.confianza,
            })
            aprobadas += 1
            continue

        try:
            g.estado = "RESPONDIDA"
            g.workflow_state = "RESPONDIDA"
            g.fecha_decision_eps = g.fecha_decision_eps or datetime.now(timezone.utc)
            g.nota_workflow = "Batch autopilot LISTA_ENVIAR"
            aprobadas += 1
            resultados.append({
                "id": gid,
                "accion": "aprobada",
                "confianza": res.confianza,
            })
        except Exception as e:
            errores += 1
            resultados.append({"id": gid, "accion": "error_mutando", "error": str(e)[:100]})
            db.rollback()

    if not body.dry_run:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            return {"error": str(e)[:200], "resultados": resultados}

    return {
        "dry_run": body.dry_run,
        "aprobadas": aprobadas,
        "saltadas": saltadas,
        "errores": errores,
        "confianza_minima": body.confianza_minima,
        "total_pedidas": len(body.ids),
        "resultados": resultados[:50],  # no saturar respuesta
    }


@router.get("/metricas")
def metricas(
    periodo: str = Query("hoy", pattern="^(hoy|semana|mes)$"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Impacto del autopilot (Ronda 32): cuántas glosas cerró la IA sola,
    cuánto ahorró en tokens/USD/horas. Sirve para demostrar valor del
    sistema en capacitaciones y comités."""
    return metricas_autopilot(db, periodo=periodo)


@router.post("/texto-fijo/batch")
def batch_texto_fijo(
    dry_run: bool = Query(True, description="Si True, solo reporta — no muta."),
    limite: Optional[int] = Query(None, ge=1, le=5000),
    ventana_dias: int = Query(365, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Retro-aplica el detector a todas las glosas candidatas (Ronda 22).

    Corre una sola vez después del deploy para limpiar el backlog. Es
    idempotente — corridas posteriores no duplican efectos. Recomendado
    correr primero con dry_run=true para revisar los conteos, y luego
    con dry_run=false para ejecutar.
    """
    return retro_aplicar(db, dry_run=dry_run, limite=limite, ventana_dias=ventana_dias)


@router.post("/texto-fijo/{glosa_id}/aplicar")
def aplicar_texto_fijo(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Aplica el texto fijo a la glosa (muta). Solo coordinador/super_admin."""
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    clase = aplicar_texto_fijo_si_corresponde(g)
    if clase is None:
        return {
            "glosa_id": glosa_id,
            "aplicado": False,
            "mensaje": "No aplica texto fijo para esta glosa (o ya tiene dictamen IA).",
        }
    db.commit()
    return {"glosa_id": glosa_id, "aplicado": True, **clase}
