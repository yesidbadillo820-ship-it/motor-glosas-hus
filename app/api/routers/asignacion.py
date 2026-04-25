"""Asignación automática inteligente de glosas.

Heurística basada en:
- Tasa de éxito del gestor en ese tipo de glosa (TA/SO/AU/CO/PE/FA/IN/ME)
- Carga actual (glosas activas sin resolver del gestor)
- Historia del gestor con esa EPS específica

Devuelve el mejor gestor recomendado. El endpoint puede ejecutar la
asignación directa (auditor_email + gestor_nombre) o solo sugerir.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel

from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual, get_coordinador_o_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/asignacion", tags=["asignacion"])


class SugerenciaInput(BaseModel):
    aplicar: bool = False  # si True, asigna directo; si False solo sugiere


@router.get("/sugerencia/{glosa_id}")
def sugerir(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Sugiere el mejor gestor para una glosa basado en historial."""
    return _calcular_sugerencia(db, glosa_id)


@router.post("/aplicar/{glosa_id}")
def aplicar(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Aplica la sugerencia como asignación real."""
    sug = _calcular_sugerencia(db, glosa_id)
    if not sug.get("recomendado"):
        raise HTTPException(400, "Sin gestor disponible para sugerir")
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    rec = sug["recomendado"]
    glosa.auditor_email = rec["email"]
    glosa.gestor_nombre = rec["nombre"]
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="ASIGNACION_AUTO", tabla="historial",
        registro_id=glosa_id,
        detalle=f"Asignada a {rec['email']} (score {rec['score']})",
    )
    return {"message": "Asignada", "gestor": rec}


def _calcular_sugerencia(db: Session, glosa_id: int) -> dict:
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    tipo = (glosa.codigo_glosa or "")[:2].upper()
    eps = (glosa.eps or "").upper()

    usuarios = (
        db.query(UsuarioRecord)
        .filter(UsuarioRecord.activo == 1, UsuarioRecord.rol.in_(["AUDITOR", "COORDINADOR", "SUPER_ADMIN"]))
        .all()
    )

    candidatos = []
    for u in usuarios:
        # Métricas del gestor:
        # 1. Tasa de éxito en ese tipo (últimas 90 días)
        from datetime import timedelta
        from app.core.tz import ahora_utc
        desde = ahora_utc() - timedelta(days=90)
        cond = [GlosaRecord.auditor_email == u.email]
        if u.nombre:
            cond.append(GlosaRecord.gestor_nombre.ilike(f"%{u.nombre.strip()}%"))
        historicas = db.query(GlosaRecord).filter(
            or_(*cond),
            GlosaRecord.creado_en >= desde,
            GlosaRecord.codigo_glosa.ilike(f"{tipo}%"),
        ).all()
        total_tipo = len(historicas) or 1
        exitosas = sum(
            1 for g in historicas
            if (g.valor_objetado or 0) > 0 and
               ((g.valor_objetado or 0) - (g.valor_aceptado or 0)) / (g.valor_objetado or 1) > 0.7
        )
        tasa_tipo = exitosas / total_tipo if total_tipo > 0 else 0

        # 2. Carga actual (glosas activas sin cerrar)
        carga_q = db.query(func.count(GlosaRecord.id)).filter(
            or_(*cond),
            GlosaRecord.workflow_state.in_(["BORRADOR", "EN_REVISION"]),
        ).scalar()
        carga = int(carga_q or 0)

        # 3. Historia con esa EPS
        cond_eps = list(cond)
        cond_eps.append(GlosaRecord.eps == eps)
        hist_eps = db.query(func.count(GlosaRecord.id)).filter(or_(*cond_eps)).scalar()

        # Score: +tasa_tipo * 60, -carga * 2, +historia_eps * 0.5
        score = round(tasa_tipo * 60 - carga * 2 + int(hist_eps or 0) * 0.5, 2)

        candidatos.append({
            "email": u.email,
            "nombre": u.nombre or u.email.split("@")[0],
            "rol": u.rol,
            "tasa_tipo": round(tasa_tipo * 100, 1),
            "carga_actual": carga,
            "hist_con_eps": int(hist_eps or 0),
            "score": score,
        })

    # Ordenar por score desc
    candidatos.sort(key=lambda c: c["score"], reverse=True)
    recomendado = candidatos[0] if candidatos else None

    return {
        "glosa_id": glosa_id,
        "tipo_glosa": tipo,
        "eps": eps,
        "recomendado": recomendado,
        "candidatos": candidatos[:5],
        "explicacion": (
            f"Se calcula score = tasa de éxito en {tipo} * 60 - carga_actual * 2 + "
            f"historial_con_eps * 0.5. Se escoge el gestor con score más alto."
        ),
    }
