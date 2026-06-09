from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, get_usuario_actual
from app.core.tz import ahora_utc
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
def ranking_eps(
    db: Session = Depends(get_db), current_user: UsuarioRecord = Depends(get_usuario_actual)
):
    resultados = (
        db.query(
            GlosaRecord.eps,
            func.count(GlosaRecord.id).label("total_glosas"),
            func.sum(GlosaRecord.valor_objetado).label("valor_objetado"),
            func.sum(GlosaRecord.valor_recuperado).label("valor_recuperado"),
        )
        .filter(GlosaRecord.decision_eps.isnot(None))
        .group_by(GlosaRecord.eps)
        .all()
    )

    ranking = []
    for r in resultados:
        levantadas = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.eps == r.eps, GlosaRecord.decision_eps == "LEVANTADA")
            .scalar()
            or 0
        )
        aceptadas = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.eps == r.eps, GlosaRecord.decision_eps == "ACEPTADA")
            .scalar()
            or 0
        )
        total_con_decision = levantadas + aceptadas
        tasa_exito = (
            round(levantadas / total_con_decision * 100, 1) if total_con_decision > 0 else None
        )
        ranking.append(
            {
                "eps": r.eps,
                "total_glosas": r.total_glosas,
                "valor_objetado": float(r.valor_objetado or 0),
                "valor_recuperado": float(r.valor_recuperado or 0),
                "glosas_levantadas": levantadas,
                "glosas_aceptadas": aceptadas,
                "tasa_exito_real_pct": tasa_exito,
            }
        )
    ranking.sort(key=lambda x: x["valor_objetado"], reverse=True)
    return {"ranking": ranking}


@router.get("/eficiencia-auditores")
def eficiencia_auditores(
    db: Session = Depends(get_db), current_user: UsuarioRecord = Depends(get_coordinador_o_admin)
):
    resultados = (
        db.query(
            GlosaRecord.auditor_email,
            func.count(GlosaRecord.id).label("total"),
            func.sum(GlosaRecord.valor_objetado).label("valor_obj"),
            func.sum(GlosaRecord.valor_recuperado).label("valor_rec"),
        )
        .filter(GlosaRecord.auditor_email.isnot(None))
        .group_by(GlosaRecord.auditor_email)
        .all()
    )

    auditores = []
    for r in resultados:
        levantadas = (
            db.query(func.count(GlosaRecord.id))
            .filter(
                GlosaRecord.auditor_email == r.auditor_email,
                GlosaRecord.decision_eps == "LEVANTADA",
            )
            .scalar()
            or 0
        )
        total_dec = (
            db.query(func.count(GlosaRecord.id))
            .filter(
                GlosaRecord.auditor_email == r.auditor_email, GlosaRecord.decision_eps.isnot(None)
            )
            .scalar()
            or 0
        )
        auditores.append(
            {
                "auditor": r.auditor_email,
                "total_glosas": r.total,
                "valor_objetado": float(r.valor_obj or 0),
                "valor_recuperado": float(r.valor_rec or 0),
                "glosas_con_decision": total_dec,
                "tasa_exito_pct": round(levantadas / total_dec * 100, 1) if total_dec > 0 else None,
            }
        )
    auditores.sort(key=lambda x: x["total_glosas"], reverse=True)
    return {"auditores": auditores}


@router.get("/patrones-exitosos")
def patrones_exitosos(
    db: Session = Depends(get_db), current_user: UsuarioRecord = Depends(get_usuario_actual)
):
    from sqlalchemy import case

    tipo_case = case(
        (GlosaRecord.codigo_glosa.like("TA%"), "TARIFA"),
        (GlosaRecord.codigo_glosa.like("SO%"), "SOPORTES"),
        (GlosaRecord.codigo_glosa.like("AU%"), "AUTORIZACION"),
        (GlosaRecord.codigo_glosa.like("CO%"), "COBERTURA"),
        (GlosaRecord.codigo_glosa.like("PE%"), "PERTINENCIA"),
        (GlosaRecord.codigo_glosa.like("FA%"), "FACTURACION"),
        (GlosaRecord.codigo_glosa.like("IN%"), "INSUMOS"),
        (GlosaRecord.codigo_glosa.like("ME%"), "MEDICAMENTOS"),
        else_="OTROS",
    )
    resultados = (
        db.query(
            tipo_case.label("tipo"),
            func.count(GlosaRecord.id).label("total"),
            func.avg(GlosaRecord.score).label("score_promedio"),
            func.sum(GlosaRecord.valor_objetado).label("valor_total"),
        )
        .filter(GlosaRecord.decision_eps.isnot(None))
        .group_by(tipo_case)
        .all()
    )

    patrones = []
    for r in resultados:
        levantadas = (
            db.query(func.count(GlosaRecord.id))
            .filter(tipo_case == r.tipo, GlosaRecord.decision_eps == "LEVANTADA")
            .scalar()
            or 0
        )
        patrones.append(
            {
                "tipo": r.tipo,
                "total_con_decision": r.total,
                "levantadas": levantadas,
                "tasa_exito_pct": round(levantadas / r.total * 100, 1) if r.total > 0 else 0,
                "score_ia_promedio": round(float(r.score_promedio or 0), 1),
                "valor_total": float(r.valor_total or 0),
            }
        )
    patrones.sort(key=lambda x: x["tasa_exito_pct"], reverse=True)
    return {"patrones": patrones}


@router.get("/recuperacion-proyectada")
def recuperacion_proyectada(
    db: Session = Depends(get_db), current_user: UsuarioRecord = Depends(get_usuario_actual)
):
    total_con_decision = (
        db.query(func.count(GlosaRecord.id)).filter(GlosaRecord.decision_eps.isnot(None)).scalar()
        or 0
    )
    total_levantadas = (
        db.query(func.count(GlosaRecord.id))
        .filter(GlosaRecord.decision_eps == "LEVANTADA")
        .scalar()
        or 0
    )
    tasa_historica = (total_levantadas / total_con_decision) if total_con_decision > 0 else 0.75
    pendientes = (
        db.query(
            func.count(GlosaRecord.id).label("total"),
            func.sum(GlosaRecord.valor_objetado).label("valor"),
        )
        .filter(GlosaRecord.decision_eps.is_(None), GlosaRecord.estado == "RESPONDIDA")
        .first()
    )
    total_pendientes = pendientes.total or 0
    valor_pendiente = float(pendientes.valor or 0)
    return {
        "tasa_exito_historica_pct": round(tasa_historica * 100, 1),
        "glosas_pendientes_decision": total_pendientes,
        "valor_pendiente": valor_pendiente,
        "valor_recuperacion_proyectada": round(valor_pendiente * tasa_historica, 0),
        "nota": f"Proyección basada en {total_con_decision} casos históricos.",
    }


@router.get("/win-rate-detalle")
def win_rate_detalle(
    dias: int = 90,
    eps: str | None = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Win-rate por combinación (EPS, código), con tendencia trimestral.

    Granularidad que NO existe en el resto de /analytics — los endpoints
    actuales agregan por EPS o por familia (TA/SO/...), nunca por la
    combinación EPS+código completa, que es la que de verdad le importa
    al coordinador para decidir qué plantillas mantener vivas.

    Devuelve una lista ordenada por valor recuperado descendente:
      [{
        eps, codigo, n_total, n_levantadas, n_ratificadas,
        valor_objetado_total, valor_recuperado_total,
        tasa_levantamiento_pct,
        tendencia_3m_pct   (delta vs los 3 meses anteriores)
      }]

    Filtros: ventana de N días sobre fecha_decision_eps (sólo glosas ya
    decididas), y opcionalmente una EPS específica.
    """
    dias = max(7, min(int(dias or 90), 365))
    ahora = ahora_utc()
    desde = ahora - timedelta(days=dias)
    # Ventana previa de igual duración para calcular tendencia
    desde_previa = desde - timedelta(days=dias)

    base_q = db.query(GlosaRecord).filter(
        GlosaRecord.codigo_glosa.isnot(None),
        GlosaRecord.eps.isnot(None),
        GlosaRecord.estado.in_(["LEVANTADA", "RATIFICADA", "ACEPTADA"]),
    )
    if eps:
        eps_norm = eps.strip()
        base_q = base_q.filter(GlosaRecord.eps.ilike(eps_norm))

    # Periodo actual
    rows_actual = (
        base_q.filter(GlosaRecord.fecha_decision_eps >= desde)
        .with_entities(
            GlosaRecord.eps,
            GlosaRecord.codigo_glosa,
            GlosaRecord.estado,
            GlosaRecord.valor_objetado,
            GlosaRecord.valor_recuperado,
        )
        .all()
    )
    # Periodo previo (para tendencia)
    rows_previo = (
        base_q.filter(GlosaRecord.fecha_decision_eps >= desde_previa)
        .filter(GlosaRecord.fecha_decision_eps < desde)
        .with_entities(
            GlosaRecord.eps,
            GlosaRecord.codigo_glosa,
            GlosaRecord.estado,
        )
        .all()
    )

    def _agregar(rows, incluir_valores: bool) -> dict:
        agregado: dict[tuple[str, str], dict] = {}
        for r in rows:
            key = ((r.eps or "").strip(), (r.codigo_glosa or "").strip().upper())
            d = agregado.setdefault(
                key,
                {
                    "n_total": 0,
                    "n_levantadas": 0,
                    "n_ratificadas": 0,
                    "n_aceptadas": 0,
                    "valor_objetado_total": 0.0,
                    "valor_recuperado_total": 0.0,
                },
            )
            d["n_total"] += 1
            if r.estado == "LEVANTADA":
                d["n_levantadas"] += 1
            elif r.estado == "RATIFICADA":
                d["n_ratificadas"] += 1
            elif r.estado == "ACEPTADA":
                d["n_aceptadas"] += 1
            if incluir_valores:
                d["valor_objetado_total"] += float(r.valor_objetado or 0)
                d["valor_recuperado_total"] += float(r.valor_recuperado or 0)
        return agregado

    actual = _agregar(rows_actual, incluir_valores=True)
    previo = _agregar(rows_previo, incluir_valores=False)

    items = []
    for (eps_k, cod_k), d in actual.items():
        tasa = (d["n_levantadas"] / d["n_total"] * 100) if d["n_total"] else 0
        prev = previo.get((eps_k, cod_k))
        if prev and prev["n_total"]:
            tasa_prev = prev["n_levantadas"] / prev["n_total"] * 100
            tendencia = tasa - tasa_prev
        else:
            tendencia = None
        items.append(
            {
                "eps": eps_k,
                "codigo": cod_k,
                "n_total": d["n_total"],
                "n_levantadas": d["n_levantadas"],
                "n_ratificadas": d["n_ratificadas"],
                "n_aceptadas": d["n_aceptadas"],
                "valor_objetado_total": round(d["valor_objetado_total"], 2),
                "valor_recuperado_total": round(d["valor_recuperado_total"], 2),
                "tasa_levantamiento_pct": round(tasa, 1),
                "tendencia_3m_pct": round(tendencia, 1) if tendencia is not None else None,
            }
        )

    # Orden por valor recuperado descendente — el coordinador ve primero
    # las combinaciones que más plata han traído.
    items.sort(key=lambda x: -x["valor_recuperado_total"])

    return {
        "ventana_dias": dias,
        "desde": desde.isoformat(),
        "hasta": ahora.isoformat(),
        "filtro_eps": eps,
        "total_combinaciones": len(items),
        "items": items,
    }
