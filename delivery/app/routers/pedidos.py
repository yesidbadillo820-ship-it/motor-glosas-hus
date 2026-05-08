from datetime import datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ESTADOS_PEDIDO, Cliente, Comercio, Pedido, Repartidor, Zona
from app.schemas import (
    AsignarRepartidorIn,
    CambiarEstadoIn,
    PedidoIn,
    PedidoOut,
    PedidoUpdate,
)

router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])


def _generar_codigo(db: Session) -> str:
    hoy = datetime.utcnow().strftime("%y%m%d")
    inicio = datetime.combine(datetime.utcnow().date(), time.min)
    n = db.query(Pedido).filter(Pedido.creado_en >= inicio).count() + 1
    return f"P{hoy}-{n:04d}"


def _serialize(p: Pedido) -> PedidoOut:
    return PedidoOut(
        id=p.id,
        codigo=p.codigo,
        cliente_id=p.cliente_id,
        comercio_id=p.comercio_id,
        repartidor_id=p.repartidor_id,
        zona_id=p.zona_id,
        descripcion=p.descripcion,
        direccion_entrega=p.direccion_entrega,
        telefono_entrega=p.telefono_entrega,
        notas=p.notas,
        valor_productos=p.valor_productos,
        costo_envio=p.costo_envio,
        total=p.total,
        metodo_pago=p.metodo_pago,
        estado=p.estado,
        creado_en=p.creado_en,
        asignado_en=p.asignado_en,
        en_ruta_en=p.en_ruta_en,
        entregado_en=p.entregado_en,
        cancelado_en=p.cancelado_en,
        motivo_cancelacion=p.motivo_cancelacion,
        cliente_nombre=p.cliente.nombre if p.cliente else None,
        cliente_telefono=p.cliente.telefono if p.cliente else None,
        comercio_nombre=p.comercio.nombre if p.comercio else None,
        repartidor_nombre=p.repartidor.nombre if p.repartidor else None,
        zona_nombre=p.zona.nombre if p.zona else None,
    )


@router.get("", response_model=list[PedidoOut])
def listar(
    estado: Optional[str] = Query(None),
    repartidor_id: Optional[int] = Query(None),
    cliente_id: Optional[int] = Query(None),
    solo_hoy: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Pedido)
    if estado:
        q = q.filter(Pedido.estado == estado.upper())
    if repartidor_id:
        q = q.filter(Pedido.repartidor_id == repartidor_id)
    if cliente_id:
        q = q.filter(Pedido.cliente_id == cliente_id)
    if solo_hoy:
        inicio = datetime.combine(datetime.utcnow().date(), time.min)
        q = q.filter(Pedido.creado_en >= inicio)
    pedidos = q.order_by(desc(Pedido.creado_en)).limit(limit).all()
    return [_serialize(p) for p in pedidos]


@router.get("/{pid}", response_model=PedidoOut)
def detalle(pid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    p = db.get(Pedido, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    return _serialize(p)


@router.post("", response_model=PedidoOut, status_code=201)
def crear(payload: PedidoIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not db.get(Cliente, payload.cliente_id):
        raise HTTPException(400, "Cliente inexistente")
    if payload.comercio_id and not db.get(Comercio, payload.comercio_id):
        raise HTTPException(400, "Comercio inexistente")
    if payload.zona_id and not db.get(Zona, payload.zona_id):
        raise HTTPException(400, "Zona inexistente")

    if payload.zona_id and payload.costo_envio == 0:
        zona = db.get(Zona, payload.zona_id)
        if zona:
            payload.costo_envio = zona.tarifa_base

    p = Pedido(
        codigo=_generar_codigo(db),
        **payload.model_dump(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.put("/{pid}", response_model=PedidoOut)
def actualizar(pid: int, payload: PedidoUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    p = db.get(Pedido, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    if p.estado in ("ENTREGADO", "CANCELADO"):
        raise HTTPException(400, f"No se puede editar un pedido en estado {p.estado}")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.post("/{pid}/asignar", response_model=PedidoOut)
def asignar(pid: int, payload: AsignarRepartidorIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    p = db.get(Pedido, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    if p.estado in ("ENTREGADO", "CANCELADO"):
        raise HTTPException(400, f"No se puede reasignar un pedido {p.estado}")
    r = db.get(Repartidor, payload.repartidor_id)
    if not r or not r.activo:
        raise HTTPException(400, "Repartidor inválido o inactivo")
    p.repartidor_id = r.id
    if p.estado == "PENDIENTE":
        p.estado = "ASIGNADO"
        p.asignado_en = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.post("/{pid}/estado", response_model=PedidoOut)
def cambiar_estado(pid: int, payload: CambiarEstadoIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    p = db.get(Pedido, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    nuevo = payload.estado.upper()
    if nuevo not in ESTADOS_PEDIDO:
        raise HTTPException(400, f"Estado inválido. Use uno de {ESTADOS_PEDIDO}")

    if nuevo == "EN_RUTA":
        if not p.repartidor_id:
            raise HTTPException(400, "Debe asignar un repartidor antes de marcar EN_RUTA")
        p.estado = "EN_RUTA"
        p.en_ruta_en = datetime.utcnow()
    elif nuevo == "ENTREGADO":
        if not p.repartidor_id:
            raise HTTPException(400, "Debe asignar un repartidor antes de entregar")
        p.estado = "ENTREGADO"
        p.entregado_en = datetime.utcnow()
    elif nuevo == "CANCELADO":
        p.estado = "CANCELADO"
        p.cancelado_en = datetime.utcnow()
        p.motivo_cancelacion = payload.motivo
    elif nuevo == "ASIGNADO":
        if not p.repartidor_id:
            raise HTTPException(400, "Debe asignar un repartidor")
        p.estado = "ASIGNADO"
        p.asignado_en = p.asignado_en or datetime.utcnow()
    else:
        p.estado = nuevo

    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.delete("/{pid}", status_code=204)
def eliminar(pid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    p = db.get(Pedido, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    if p.estado not in ("PENDIENTE", "CANCELADO"):
        raise HTTPException(400, "Solo se pueden eliminar pedidos PENDIENTE o CANCELADO")
    db.delete(p)
    db.commit()
