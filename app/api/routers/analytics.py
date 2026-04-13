from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, get_usuario_actual
from app.models.db import UsuarioRecord, GlosaRecord
from app.models.schemas import AnalyticsResult
from app.repositories.glosa_repository import GlosaRepository
from app.api.deps import get_coordinador_o_admin

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/", response_model=AnalyticsResult)
def obtener_metricas_desempeno(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Calcula en tiempo real:
    - Total de glosas procesadas.
    - Valor total objetado.
    - Valor recuperado (levantado).
    - Tasa de éxito porcentual.
    """
    repo = GlosaRepository(db)
    return repo.analytics()

@router.get("/metrics")
def obtener_metrics(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Obtiene métricas por EPS y por estado"""
    repo = GlosaRepository(db)
    return repo.metrics()

@router.get("/tendencias")
def obtener_tendencias(
    meses: int = 6,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Obtiene tendencias mensuales"""
    repo = GlosaRepository(db)
    return repo.tendencias_mensuales(meses)

@router.get("/top")
def obtener_top(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Obtiene top glosas por valor"""
    repo = GlosaRepository(db)
    return repo.top_glosas(limit)

@router.get("/reporte-ejecutivo")
def obtener_reporte_ejecutivo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Genera datos para reporte ejecutivo PDF"""
    repo = GlosaRepository(db)
    
    # Métricas generales
    analytics = repo.analytics()
    metrics = repo.metrics()
    tendencias = repo.tendencias_mensuales(6)
    top = repo.top_glosas(5)
    
    return {
        "resumen": {
            "total_glosas": analytics.glosas_mes,
            "valor_objetado": analytics.valor_objetado_mes,
            "valor_recuperado": analytics.valor_recuperado_mes,
            "tasa_exito": analytics.tasa_exito_pct,
        },
        "por_eps": metrics.get("by_eps", []),
        "por_estado": metrics.get("by_estado", []),
        "tendencias": tendencias,
        "top_glosas": top,
    }


@router.get("/ranking-eps")
def ranking_eps(db: Session = Depends(get_db),
                current_user: UsuarioRecord = Depends(get_usuario_actual)):
    resultados = db.query(
        GlosaRecord.eps,
        func.count(GlosaRecord.id).label("total_glosas"),
        func.sum(GlosaRecord.valor_objetado).label("valor_objetado"),
        func.sum(GlosaRecord.valor_recuperado).label("valor_recuperado"),
    ).filter(GlosaRecord.decision_eps.isnot(None)).group_by(GlosaRecord.eps).all()

    ranking = []
    for r in resultados:
        levantadas = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.eps == r.eps, GlosaRecord.decision_eps == "LEVANTADA").scalar() or 0
        aceptadas = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.eps == r.eps, GlosaRecord.decision_eps == "ACEPTADA").scalar() or 0
        total_con_decision = levantadas + aceptadas
        tasa_exito = round(levantadas / total_con_decision * 100, 1) if total_con_decision > 0 else None
        ranking.append({
            "eps": r.eps, "total_glosas": r.total_glosas,
            "valor_objetado": float(r.valor_objetado or 0),
            "valor_recuperado": float(r.valor_recuperado or 0),
            "glosas_levantadas": levantadas, "glosas_aceptadas": aceptadas,
            "tasa_exito_real_pct": tasa_exito,
        })
    ranking.sort(key=lambda x: x["valor_objetado"], reverse=True)
    return {"ranking": ranking}


@router.get("/eficiencia-auditores")
def eficiencia_auditores(db: Session = Depends(get_db),
                         current_user: UsuarioRecord = Depends(get_coordinador_o_admin)):
    resultados = db.query(
        GlosaRecord.auditor_email,
        func.count(GlosaRecord.id).label("total"),
        func.sum(GlosaRecord.valor_objetado).label("valor_obj"),
        func.sum(GlosaRecord.valor_recuperado).label("valor_rec"),
    ).filter(GlosaRecord.auditor_email.isnot(None)).group_by(GlosaRecord.auditor_email).all()

    auditores = []
    for r in resultados:
        levantadas = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.auditor_email == r.auditor_email,
            GlosaRecord.decision_eps == "LEVANTADA").scalar() or 0
        total_dec = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.auditor_email == r.auditor_email,
            GlosaRecord.decision_eps.isnot(None)).scalar() or 0
        auditores.append({
            "auditor": r.auditor_email, "total_glosas": r.total,
            "valor_objetado": float(r.valor_obj or 0),
            "valor_recuperado": float(r.valor_rec or 0),
            "glosas_con_decision": total_dec,
            "tasa_exito_pct": round(levantadas / total_dec * 100, 1) if total_dec > 0 else None,
        })
    auditores.sort(key=lambda x: x["total_glosas"], reverse=True)
    return {"auditores": auditores}


@router.get("/patrones-exitosos")
def patrones_exitosos(db: Session = Depends(get_db),
                      current_user: UsuarioRecord = Depends(get_usuario_actual)):
    from sqlalchemy import case
    tipo_case = case(
        (GlosaRecord.codigo_glosa.like('TA%'), 'TARIFA'),
        (GlosaRecord.codigo_glosa.like('SO%'), 'SOPORTES'),
        (GlosaRecord.codigo_glosa.like('AU%'), 'AUTORIZACION'),
        (GlosaRecord.codigo_glosa.like('CO%'), 'COBERTURA'),
        (GlosaRecord.codigo_glosa.like('PE%'), 'PERTINENCIA'),
        (GlosaRecord.codigo_glosa.like('FA%'), 'FACTURACION'),
        (GlosaRecord.codigo_glosa.like('IN%'), 'INSUMOS'),
        (GlosaRecord.codigo_glosa.like('ME%'), 'MEDICAMENTOS'),
        else_='OTROS'
    )
    resultados = db.query(
        tipo_case.label("tipo"), func.count(GlosaRecord.id).label("total"),
        func.avg(GlosaRecord.score).label("score_promedio"),
        func.sum(GlosaRecord.valor_objetado).label("valor_total"),
    ).filter(GlosaRecord.decision_eps.isnot(None)).group_by(tipo_case).all()

    patrones = []
    for r in resultados:
        levantadas = db.query(func.count(GlosaRecord.id)).filter(
            tipo_case == r.tipo, GlosaRecord.decision_eps == "LEVANTADA").scalar() or 0
        patrones.append({
            "tipo": r.tipo, "total_con_decision": r.total, "levantadas": levantadas,
            "tasa_exito_pct": round(levantadas / r.total * 100, 1) if r.total > 0 else 0,
            "score_ia_promedio": round(float(r.score_promedio or 0), 1),
            "valor_total": float(r.valor_total or 0),
        })
    patrones.sort(key=lambda x: x["tasa_exito_pct"], reverse=True)
    return {"patrones": patrones}


@router.get("/recuperacion-proyectada")
def recuperacion_proyectada(db: Session = Depends(get_db),
                            current_user: UsuarioRecord = Depends(get_usuario_actual)):
    total_con_decision = db.query(func.count(GlosaRecord.id)).filter(
        GlosaRecord.decision_eps.isnot(None)).scalar() or 0
    total_levantadas = db.query(func.count(GlosaRecord.id)).filter(
        GlosaRecord.decision_eps == "LEVANTADA").scalar() or 0
    tasa_historica = (total_levantadas / total_con_decision) if total_con_decision > 0 else 0.75
    pendientes = db.query(
        func.count(GlosaRecord.id).label("total"),
        func.sum(GlosaRecord.valor_objetado).label("valor"),
    ).filter(GlosaRecord.decision_eps.is_(None), GlosaRecord.estado == "RESPONDIDA").first()
    total_pendientes = pendientes.total or 0
    valor_pendiente = float(pendientes.valor or 0)
    return {
        "tasa_exito_historica_pct": round(tasa_historica * 100, 1),
        "glosas_pendientes_decision": total_pendientes,
        "valor_pendiente": valor_pendiente,
        "valor_recuperacion_proyectada": round(valor_pendiente * tasa_historica, 0),
        "nota": f"Proyección basada en {total_con_decision} casos históricos.",
    }
