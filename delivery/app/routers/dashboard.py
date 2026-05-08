from datetime import datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Pedido, Repartidor, Zona
from app.schemas import DashboardMetricas

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metricas", response_model=DashboardMetricas)
def metricas(db: Session = Depends(get_db), _=Depends(get_current_user)):
    inicio_dia = datetime.combine(datetime.utcnow().date(), time.min)

    pedidos_hoy_q = db.query(Pedido).filter(Pedido.creado_en >= inicio_dia)
    pedidos_hoy = pedidos_hoy_q.count()

    por_estado_rows = (
        db.query(Pedido.estado, func.count(Pedido.id))
        .filter(Pedido.creado_en >= inicio_dia)
        .group_by(Pedido.estado)
        .all()
    )
    por_estado = {estado: cnt for estado, cnt in por_estado_rows}

    pendientes = por_estado.get("PENDIENTE", 0)
    asignados = por_estado.get("ASIGNADO", 0)
    en_ruta = por_estado.get("EN_RUTA", 0)
    entregados_hoy = por_estado.get("ENTREGADO", 0)
    cancelados_hoy = por_estado.get("CANCELADO", 0)

    rep_total = db.query(Repartidor).filter(Repartidor.activo == 1).count()
    rep_disp = db.query(Repartidor).filter(Repartidor.activo == 1, Repartidor.disponible == 1).count()

    ingresos_hoy = (
        db.query(func.coalesce(func.sum(Pedido.valor_productos + Pedido.costo_envio), 0.0))
        .filter(Pedido.estado == "ENTREGADO", Pedido.entregado_en >= inicio_dia)
        .scalar()
        or 0.0
    )
    ticket_promedio = (ingresos_hoy / entregados_hoy) if entregados_hoy else 0.0

    pedidos_por_zona_rows = (
        db.query(Zona.nombre, func.count(Pedido.id))
        .join(Pedido, Pedido.zona_id == Zona.id)
        .filter(Pedido.creado_en >= inicio_dia)
        .group_by(Zona.nombre)
        .order_by(func.count(Pedido.id).desc())
        .limit(10)
        .all()
    )
    pedidos_por_zona = [{"zona": z, "pedidos": c} for z, c in pedidos_por_zona_rows]

    top_rep_rows = (
        db.query(Repartidor.nombre, func.count(Pedido.id), func.coalesce(func.sum(Pedido.costo_envio), 0.0))
        .join(Pedido, Pedido.repartidor_id == Repartidor.id)
        .filter(Pedido.estado == "ENTREGADO", Pedido.entregado_en >= inicio_dia)
        .group_by(Repartidor.nombre)
        .order_by(func.count(Pedido.id).desc())
        .limit(5)
        .all()
    )
    top_rep = [
        {"repartidor": n, "entregas": int(c), "comisiones": float(s)}
        for n, c, s in top_rep_rows
    ]

    return DashboardMetricas(
        pedidos_hoy=pedidos_hoy,
        pendientes=pendientes,
        asignados=asignados,
        en_ruta=en_ruta,
        entregados_hoy=entregados_hoy,
        cancelados_hoy=cancelados_hoy,
        repartidores_disponibles=rep_disp,
        repartidores_total=rep_total,
        ingresos_hoy=float(ingresos_hoy),
        ticket_promedio_hoy=float(ticket_promedio),
        pedidos_por_estado=por_estado,
        pedidos_por_zona=pedidos_por_zona,
        top_repartidores_hoy=top_rep,
    )
