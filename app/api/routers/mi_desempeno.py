"""Dashboard individual del gestor con KPIs personales, ranking y logros."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord, AuditLogRecord
from app.api.deps import get_usuario_actual

router = APIRouter(prefix="/mi-desempeno", tags=["mi-desempeno"])


def _glosas_del_gestor(db: Session, usuario: UsuarioRecord, desde: Optional[datetime] = None):
    """Devuelve query de glosas asignadas al usuario (email o nombre match)."""
    condiciones = [GlosaRecord.auditor_email == usuario.email]
    if usuario.nombre:
        condiciones.append(GlosaRecord.gestor_nombre.ilike(f"%{usuario.nombre.strip()}%"))
    prefijo = usuario.email.split("@")[0]
    condiciones.append(GlosaRecord.gestor_nombre.ilike(f"%{prefijo}%"))
    q = db.query(GlosaRecord).filter(or_(*condiciones))
    if desde:
        q = q.filter(GlosaRecord.creado_en >= desde)
    return q


@router.get("/")
def mi_desempeno(
    ventana_dias: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """KPIs personales del usuario actual en la ventana indicada."""
    desde = datetime.utcnow() - timedelta(days=ventana_dias)

    q = _glosas_del_gestor(db, current_user, desde)
    glosas = q.all()

    total = len(glosas)
    v_obj = sum(float(g.valor_objetado or 0) for g in glosas)
    v_ac = sum(float(g.valor_aceptado or 0) for g in glosas)
    v_rec = v_obj - v_ac
    tasa = round((v_rec / v_obj * 100) if v_obj > 0 else 0, 1)

    # Estados del workflow
    por_workflow = {"BORRADOR": 0, "EN_REVISION": 0, "APROBADA": 0, "RADICADA": 0}
    for g in glosas:
        k = g.workflow_state or "BORRADOR"
        por_workflow[k] = por_workflow.get(k, 0) + 1

    # Semáforo
    semaforo = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0, "NEGRO": 0}
    for g in glosas:
        k = g.prioridad or "VERDE"
        semaforo[k] = semaforo.get(k, 0) + 1

    # Tiempo promedio de respuesta (de creación a radicación/dictamen)
    # Simplificado: tomamos las que tienen dictamen como "respondidas"
    respondidas = [g for g in glosas if g.dictamen and g.estado not in ("BORRADOR",)]

    # Logros (calculados en caliente)
    logros = []
    if total >= 10:
        logros.append({"nombre": "Operador activo", "icono": "🏃", "desc": f"{total} glosas procesadas"})
    if tasa >= 80 and total >= 5:
        logros.append({"nombre": "Francotirador", "icono": "🎯", "desc": f"Tasa de éxito {tasa}%"})
    if v_rec >= 5_000_000:
        logros.append({"nombre": "Recuperador", "icono": "💰", "desc": f"{v_rec/1_000_000:.1f}M recuperados"})

    # Racha: días consecutivos con al menos 1 glosa respondida
    racha = _calcular_racha(glosas)
    if racha >= 3:
        logros.append({"nombre": f"Racha {racha} días", "icono": "🔥", "desc": "Días consecutivos activo"})
    if por_workflow.get("APROBADA", 0) + por_workflow.get("RADICADA", 0) >= 20:
        logros.append({"nombre": "Cierre consistente", "icono": "✅", "desc": "20+ glosas aprobadas/radicadas"})

    # Ranking vs equipo (por tasa de éxito)
    ranking = _ranking_equipo(db, desde)
    mi_posicion = None
    for i, r in enumerate(ranking):
        if r["email"] == current_user.email:
            mi_posicion = i + 1
            break

    # Alertas personales
    alertas = []
    if semaforo["NEGRO"] > 0:
        alertas.append({"nivel": "critico", "msg": f"Tienes {semaforo['NEGRO']} glosa(s) VENCIDA(S). Atender ya."})
    if semaforo["ROJO"] > 0:
        alertas.append({"nivel": "alto", "msg": f"{semaforo['ROJO']} glosa(s) en rojo (menos de 5 días)."})
    if por_workflow.get("BORRADOR", 0) >= 5:
        alertas.append({"nivel": "info", "msg": f"{por_workflow['BORRADOR']} borradores sin enviar a revisión."})

    return {
        "ventana_dias": ventana_dias,
        "usuario": {
            "email": current_user.email,
            "nombre": current_user.nombre,
            "rol": current_user.rol,
        },
        "kpis": {
            "total_glosas": total,
            "valor_objetado": v_obj,
            "valor_recuperado": v_rec,
            "tasa_exito": tasa,
            "respondidas": len(respondidas),
        },
        "por_workflow": por_workflow,
        "semaforo": semaforo,
        "logros": logros,
        "racha_dias": racha,
        "ranking": {
            "mi_posicion": mi_posicion,
            "total_participantes": len(ranking),
            "top_5": ranking[:5],
        },
        "alertas": alertas,
    }


def _calcular_racha(glosas: list[GlosaRecord]) -> int:
    """Calcula días consecutivos (hacia atrás desde hoy) con al menos 1 glosa."""
    if not glosas:
        return 0
    dias_con_actividad = set()
    for g in glosas:
        if g.creado_en:
            dias_con_actividad.add(g.creado_en.date())
    hoy = datetime.utcnow().date()
    racha = 0
    while hoy in dias_con_actividad:
        racha += 1
        hoy -= timedelta(days=1)
    return racha


def _ranking_equipo(db: Session, desde: datetime) -> list[dict]:
    """Ranking del equipo por tasa de éxito en la ventana."""
    usuarios = db.query(UsuarioRecord).filter(UsuarioRecord.activo == 1).all()
    ranking = []
    for u in usuarios:
        condiciones = [GlosaRecord.auditor_email == u.email]
        if u.nombre:
            condiciones.append(GlosaRecord.gestor_nombre.ilike(f"%{u.nombre.strip()}%"))
        glosas = db.query(GlosaRecord).filter(
            or_(*condiciones), GlosaRecord.creado_en >= desde
        ).all()
        if not glosas:
            continue
        obj = sum(float(g.valor_objetado or 0) for g in glosas)
        ace = sum(float(g.valor_aceptado or 0) for g in glosas)
        tasa = ((obj - ace) / obj * 100) if obj > 0 else 0
        ranking.append({
            "email": u.email,
            "nombre": u.nombre or u.email.split("@")[0],
            "rol": u.rol,
            "glosas": len(glosas),
            "recuperado": obj - ace,
            "tasa_exito": round(tasa, 1),
        })
    # Ordena por tasa, luego por volumen
    ranking.sort(key=lambda x: (-x["tasa_exito"], -x["glosas"]))
    return ranking


@router.get("/ranking")
def ranking_equipo(
    ventana_dias: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Ranking completo del equipo (para tabla)."""
    desde = datetime.utcnow() - timedelta(days=ventana_dias)
    return {
        "ventana_dias": ventana_dias,
        "ranking": _ranking_equipo(db, desde),
    }
