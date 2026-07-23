"""API del módulo de PRE-AUDITORÍA SINAC.

Flujo del proceso:
  1. Se registra el oficio radicado por Facturación (número + fecha y hora
     de recibido).
  2. Se importa el Excel del consecutivo de DGH con las facturas del oficio
     (el sistema informa cuántas facturas trae cada número de envío).
  3. Cada factura se audita: RADICAR (soportes OK) o DEVUELTA (con motivo).
     Una factura se acepta devuelta máximo 3 veces; cuando vuelve corregida
     (ronda 2+) queda SUBSANADA o NUEVAMENTE DEVUELTA.
  4. Con las devueltas se genera el oficio de devolución en PDF con
     consecutivo SINAC (DEV-PRE-AUD-####-AAAA), logo y firmas.
  5. Semáforo de plazo (3 días hábiles desde el día siguiente al recibo)
     y estadísticas por auditor, resultado y reincidencia.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.tz import TZ_BOGOTA, a_utc, ahora_utc
from app.database import get_db
from app.models.db import (
    FacturaPreauditoriaRecord,
    OficioDevolucionRecord,
    OficioRecepcionRecord,
    UsuarioRecord,
)
from app.services import preauditoria_service as svc
from app.services.oficio_devolucion_pdf import generar_pdf_oficio_devolucion

router = APIRouter(prefix="/preauditoria", tags=["preauditoria"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class OficioIn(BaseModel):
    numero_radicado: str = Field(..., min_length=3, max_length=60)
    # "2026-07-22T14:35" (hora local de Bogotá)
    fecha_recibido: str = Field(..., min_length=10)
    observaciones: Optional[str] = Field(None, max_length=2000)


class AuditarIn(BaseModel):
    resultado: str = Field(..., pattern="^(RADICAR|DEVUELTA|PENDIENTE)$")
    motivo_devolucion: Optional[str] = Field(None, max_length=4000)
    observaciones: Optional[str] = Field(None, max_length=2000)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parsear_fecha_local(texto: str) -> datetime:
    """'2026-07-22T14:35' (hora Bogotá) → datetime TZ-aware en UTC.

    Se persiste en UTC para que el valor sea el mismo en Postgres
    (TIMESTAMPTZ) y en SQLite (que guarda el datetime sin offset).
    """
    limpio = texto.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(limpio, fmt)
            return naive.replace(tzinfo=TZ_BOGOTA).astimezone(timezone.utc)
        except ValueError:
            continue
    raise HTTPException(400, "Fecha de recibido inválida (use AAAA-MM-DDTHH:MM)")


def _nombre_auditor(u: UsuarioRecord) -> str:
    return (u.nombre or u.email or "").strip() or "SIN NOMBRE"


def _fecha_iso(dt) -> Optional[str]:
    if dt is None:
        return None
    dt = a_utc(dt)
    return dt.astimezone(TZ_BOGOTA).isoformat()


def _factura_dict(f: FacturaPreauditoriaRecord, devoluciones_totales: int = None) -> dict:
    return {
        "id": f.id,
        "oficio_id": f.oficio_id,
        "envio": f.envio,
        "factura": f.factura,
        "fecha_factura": _fecha_iso(f.fecha_factura),
        "valor": f.valor,
        "nit": f.nit,
        "entidad": f.entidad,
        "correo_fe": f.correo_fe,
        "ronda": f.ronda,
        "es_subsanacion": f.ronda > 1,
        "estado_subsanacion": svc.estado_subsanacion(f),
        "resultado": f.resultado,
        "motivo_devolucion": f.motivo_devolucion,
        "observaciones": f.observaciones,
        "auditor": f.auditor,
        "fecha_auditoria": _fecha_iso(f.fecha_auditoria),
        "oficio_devolucion_id": f.oficio_devolucion_id,
        "devoluciones_totales": devoluciones_totales,
        "max_devoluciones": svc.MAX_DEVOLUCIONES,
    }


def _oficio_dict(db: Session, o: OficioRecepcionRecord, con_facturas: bool = False) -> dict:
    facturas = (
        db.query(FacturaPreauditoriaRecord)
        .filter(FacturaPreauditoriaRecord.oficio_id == o.id)
        .order_by(FacturaPreauditoriaRecord.envio, FacturaPreauditoriaRecord.factura)
        .all()
    )
    pendientes = sum(1 for f in facturas if f.resultado == svc.RESULTADO_PENDIENTE)
    radicar = sum(1 for f in facturas if f.resultado == svc.RESULTADO_RADICAR)
    devueltas = sum(1 for f in facturas if f.resultado == svc.RESULTADO_DEVUELTA)
    semaforo = svc.calcular_semaforo(
        o.fecha_recibido, completado=svc.oficio_completado(facturas)
    )
    d = {
        "id": o.id,
        "numero_radicado": o.numero_radicado,
        "fecha_recibido": _fecha_iso(o.fecha_recibido),
        "observaciones": o.observaciones,
        "archivo_dgh": o.archivo_dgh,
        "creado_por": o.creado_por,
        "total_facturas": len(facturas),
        "pendientes": pendientes,
        "radicar": radicar,
        "devueltas": devueltas,
        "valor_total": sum(float(f.valor or 0) for f in facturas),
        "semaforo": semaforo,
        "envios": svc.resumen_por_envio(facturas),
    }
    if con_facturas:
        # nº de devoluciones acumuladas por factura (todas las rondas)
        nombres = [f.factura for f in facturas]
        conteos = {}
        if nombres:
            filas = (
                db.query(
                    FacturaPreauditoriaRecord.factura,
                    sa_func.count(FacturaPreauditoriaRecord.id),
                )
                .filter(
                    FacturaPreauditoriaRecord.factura.in_(nombres),
                    FacturaPreauditoriaRecord.resultado == svc.RESULTADO_DEVUELTA,
                )
                .group_by(FacturaPreauditoriaRecord.factura)
                .all()
            )
            conteos = {fac: n for fac, n in filas}
        d["facturas"] = [_factura_dict(f, conteos.get(f.factura, 0)) for f in facturas]
    return d


# ------------------------------------------------------------------
# 1-2. Oficios de recepción (radicado + fecha/hora de recibido)
# ------------------------------------------------------------------


@router.post("/oficios")
def crear_oficio(
    body: OficioIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    radicado = body.numero_radicado.strip().upper()
    existe = (
        db.query(OficioRecepcionRecord)
        .filter(OficioRecepcionRecord.numero_radicado == radicado)
        .first()
    )
    if existe:
        raise HTTPException(409, f"El oficio {radicado} ya está registrado (id {existe.id})")
    o = OficioRecepcionRecord(
        numero_radicado=radicado,
        fecha_recibido=_parsear_fecha_local(body.fecha_recibido),
        observaciones=(body.observaciones or "").strip() or None,
        creado_por=_nombre_auditor(current_user),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _oficio_dict(db, o)


@router.get("/oficios")
def listar_oficios(
    estado: Optional[str] = Query(None, description="VERDE|AMARILLO|ROJO|VENCIDO|COMPLETADO"),
    q: Optional[str] = Query(None, description="Busca en el número de radicado"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    consulta = db.query(OficioRecepcionRecord)
    if q:
        consulta = consulta.filter(OficioRecepcionRecord.numero_radicado.ilike(f"%{q.strip()}%"))
    oficios = consulta.order_by(OficioRecepcionRecord.fecha_recibido.desc()).all()
    items = [_oficio_dict(db, o) for o in oficios]
    if estado:
        items = [i for i in items if i["semaforo"]["estado"] == estado.strip().upper()]
    total = len(items)
    inicio = (page - 1) * per_page
    return {
        "items": items[inicio : inicio + per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/oficios/{oficio_id}")
def ver_oficio(
    oficio_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    o = db.get(OficioRecepcionRecord, oficio_id)
    if not o:
        raise HTTPException(404, "Oficio no encontrado")
    return _oficio_dict(db, o, con_facturas=True)


# ------------------------------------------------------------------
# 3-5. Importar el Excel del consecutivo DGH (facturas por envío)
# ------------------------------------------------------------------


@router.post("/oficios/{oficio_id}/importar-dgh")
async def importar_dgh(
    oficio_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    o = db.get(OficioRecepcionRecord, oficio_id)
    if not o:
        raise HTTPException(404, "Oficio no encontrado")
    nombre = archivo.filename or "consecutivo_dgh.xlsx"
    if not nombre.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "El archivo debe ser un Excel (.xlsx) del consecutivo DGH")
    contenido = await archivo.read()
    if len(contenido) > 15 * 1024 * 1024:
        raise HTTPException(400, "Archivo demasiado grande (máx. 15 MB)")
    try:
        resultado = svc.parsear_excel_dgh(contenido)
    except Exception:
        raise HTTPException(400, "No se pudo leer el Excel: verifique el formato DGH")

    existentes = {
        fila[0]
        for fila in db.query(FacturaPreauditoriaRecord.factura)
        .filter(FacturaPreauditoriaRecord.oficio_id == oficio_id)
        .all()
    }
    advertencias = list(resultado["advertencias"])
    nuevas = 0
    alertas_limite = []
    for datos in resultado["facturas"]:
        if datos["factura"] in existentes:
            advertencias.append(f"{datos['factura']} ya estaba en este oficio: no se duplicó")
            continue
        ronda = svc.calcular_ronda(db, datos["factura"], oficio_id=oficio_id)
        devueltas = svc.devoluciones_previas(db, datos["factura"])
        if devueltas >= svc.MAX_DEVOLUCIONES:
            alertas_limite.append(
                f"{datos['factura']} ya fue devuelta {devueltas} veces "
                f"(máximo {svc.MAX_DEVOLUCIONES}): en esta ronda solo debería radicarse"
            )
        f = FacturaPreauditoriaRecord(
            oficio_id=oficio_id,
            envio=datos["envio"],
            factura=datos["factura"],
            fecha_factura=datos["fecha_factura"],
            valor=datos["valor"],
            nit=datos["nit"],
            entidad=datos["entidad"],
            correo_fe=datos["correo_fe"],
            ronda=ronda,
            resultado=svc.RESULTADO_PENDIENTE,
        )
        db.add(f)
        nuevas += 1
    o.archivo_dgh = nombre
    db.commit()
    db.refresh(o)

    detalle = _oficio_dict(db, o)
    detalle["importadas"] = nuevas
    detalle["advertencias"] = advertencias
    detalle["alertas_limite_devoluciones"] = alertas_limite
    return detalle


# ------------------------------------------------------------------
# 6-7. Auditar factura (RADICAR / DEVOLVER, máx. 3 devoluciones)
# ------------------------------------------------------------------


@router.patch("/facturas/{factura_id}/auditar")
def auditar_factura(
    factura_id: int,
    body: AuditarIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    f = db.get(FacturaPreauditoriaRecord, factura_id)
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    if f.oficio_devolucion_id and body.resultado != svc.RESULTADO_DEVUELTA:
        raise HTTPException(
            409,
            "Esta factura ya salió en un oficio de devolución; "
            "regístrela cuando vuelva en un oficio nuevo (subsanación)",
        )

    if body.resultado == svc.RESULTADO_DEVUELTA:
        if not (body.motivo_devolucion or "").strip():
            raise HTTPException(400, "Para devolver la factura debe escribir el motivo")
        previas = svc.devoluciones_previas(db, f.factura, excluir_id=f.id)
        if previas >= svc.MAX_DEVOLUCIONES:
            raise HTTPException(
                409,
                f"La factura {f.factura} ya fue devuelta {previas} veces; "
                f"el proceso acepta máximo {svc.MAX_DEVOLUCIONES} devoluciones. "
                "Debe resolverse en esta ronda (radicar o escalar al coordinador).",
            )

    f.resultado = body.resultado
    f.motivo_devolucion = (
        (body.motivo_devolucion or "").strip() or None
        if body.resultado == svc.RESULTADO_DEVUELTA
        else None
    )
    f.observaciones = (body.observaciones or "").strip() or f.observaciones
    if body.resultado == svc.RESULTADO_PENDIENTE:
        f.auditor = None
        f.fecha_auditoria = None
    else:
        f.auditor = _nombre_auditor(current_user)
        f.fecha_auditoria = ahora_utc()
    db.commit()
    db.refresh(f)
    return _factura_dict(f, svc.devoluciones_previas(db, f.factura))


@router.get("/facturas")
def listar_facturas(
    q: Optional[str] = Query(None, description="Factura, entidad o NIT"),
    oficio_id: Optional[int] = None,
    envio: Optional[str] = None,
    auditor: Optional[str] = None,
    resultado: Optional[str] = Query(None, description="PENDIENTE|RADICAR|DEVUELTA"),
    solo_reincidentes: bool = Query(False, description="Solo facturas con ronda 2+"),
    desde: Optional[str] = Query(None, description="AAAA-MM-DD (fecha de recibido)"),
    hasta: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    consulta = db.query(FacturaPreauditoriaRecord).join(
        OficioRecepcionRecord,
        FacturaPreauditoriaRecord.oficio_id == OficioRecepcionRecord.id,
    )
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.filter(
            FacturaPreauditoriaRecord.factura.ilike(patron)
            | FacturaPreauditoriaRecord.entidad.ilike(patron)
            | FacturaPreauditoriaRecord.nit.ilike(patron)
        )
    if oficio_id:
        consulta = consulta.filter(FacturaPreauditoriaRecord.oficio_id == oficio_id)
    if envio:
        consulta = consulta.filter(FacturaPreauditoriaRecord.envio == envio.strip())
    if auditor:
        consulta = consulta.filter(FacturaPreauditoriaRecord.auditor.ilike(f"%{auditor.strip()}%"))
    if resultado:
        consulta = consulta.filter(
            FacturaPreauditoriaRecord.resultado == resultado.strip().upper()
        )
    if solo_reincidentes:
        consulta = consulta.filter(FacturaPreauditoriaRecord.ronda >= 2)
    if desde:
        consulta = consulta.filter(
            OficioRecepcionRecord.fecha_recibido >= _parsear_fecha_local(desde)
        )
    if hasta:
        consulta = consulta.filter(
            OficioRecepcionRecord.fecha_recibido <= _parsear_fecha_local(hasta + "T23:59:59")
        )
    total = consulta.count()
    filas = (
        consulta.order_by(FacturaPreauditoriaRecord.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "items": [_factura_dict(f) for f in filas],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/facturas/{factura_id}")
def ver_factura(
    factura_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Vista individual: la factura y todo su historial de rondas."""
    f = db.get(FacturaPreauditoriaRecord, factura_id)
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    historial = (
        db.query(FacturaPreauditoriaRecord)
        .filter(FacturaPreauditoriaRecord.factura == f.factura)
        .order_by(FacturaPreauditoriaRecord.ronda, FacturaPreauditoriaRecord.id)
        .all()
    )
    devueltas = sum(1 for h in historial if h.resultado == svc.RESULTADO_DEVUELTA)
    oficios = {
        o.id: o
        for o in db.query(OficioRecepcionRecord)
        .filter(OficioRecepcionRecord.id.in_({h.oficio_id for h in historial}))
        .all()
    }
    hist = []
    for h in historial:
        d = _factura_dict(h, devueltas)
        of = oficios.get(h.oficio_id)
        d["oficio_radicado"] = of.numero_radicado if of else None
        d["oficio_fecha_recibido"] = _fecha_iso(of.fecha_recibido) if of else None
        hist.append(d)
    return {
        "actual": _factura_dict(f, devueltas),
        "historial": hist,
        "devoluciones_totales": devueltas,
        "max_devoluciones": svc.MAX_DEVOLUCIONES,
    }


# ------------------------------------------------------------------
# 8. Oficio de devolución en PDF (consecutivo SINAC, logo y firma)
# ------------------------------------------------------------------


@router.post("/oficios/{oficio_id}/oficio-devolucion")
def generar_oficio_devolucion(
    oficio_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    o = db.get(OficioRecepcionRecord, oficio_id)
    if not o:
        raise HTTPException(404, "Oficio no encontrado")
    devueltas = (
        db.query(FacturaPreauditoriaRecord)
        .filter(
            FacturaPreauditoriaRecord.oficio_id == oficio_id,
            FacturaPreauditoriaRecord.resultado == svc.RESULTADO_DEVUELTA,
            FacturaPreauditoriaRecord.oficio_devolucion_id.is_(None),
        )
        .order_by(FacturaPreauditoriaRecord.envio, FacturaPreauditoriaRecord.factura)
        .all()
    )
    if not devueltas:
        raise HTTPException(
            400,
            "No hay facturas devueltas sin oficio en este radicado: "
            "primero marque las devoluciones con su motivo",
        )
    consecutivo, numero, anio = svc.siguiente_consecutivo(db)
    dev = OficioDevolucionRecord(
        consecutivo=consecutivo,
        anio=anio,
        numero=numero,
        oficio_recepcion_id=oficio_id,
        generado_por=_nombre_auditor(current_user),
        total_facturas=len(devueltas),
        total_valor=sum(float(f.valor or 0) for f in devueltas),
    )
    db.add(dev)
    db.flush()
    for f in devueltas:
        f.oficio_devolucion_id = dev.id
    db.commit()
    db.refresh(dev)
    return {
        "id": dev.id,
        "consecutivo": dev.consecutivo,
        "total_facturas": dev.total_facturas,
        "total_valor": dev.total_valor,
        "pdf_url": f"/preauditoria/oficios-devolucion/{dev.id}/pdf",
    }


@router.get("/oficios-devolucion")
def listar_oficios_devolucion(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    consulta = db.query(OficioDevolucionRecord).order_by(
        OficioDevolucionRecord.anio.desc(), OficioDevolucionRecord.numero.desc()
    )
    total = consulta.count()
    filas = consulta.offset((page - 1) * per_page).limit(per_page).all()
    recepciones = {
        o.id: o.numero_radicado
        for o in db.query(OficioRecepcionRecord)
        .filter(OficioRecepcionRecord.id.in_({f.oficio_recepcion_id for f in filas if f.oficio_recepcion_id}))
        .all()
    }
    return {
        "items": [
            {
                "id": d.id,
                "consecutivo": d.consecutivo,
                "fecha_generado": _fecha_iso(d.fecha_generado),
                "generado_por": d.generado_por,
                "oficio_radicado": recepciones.get(d.oficio_recepcion_id),
                "total_facturas": d.total_facturas,
                "total_valor": d.total_valor,
                "pdf_url": f"/preauditoria/oficios-devolucion/{d.id}/pdf",
            }
            for d in filas
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/oficios-devolucion/{dev_id}/pdf")
def descargar_pdf_oficio_devolucion(
    dev_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    dev = db.get(OficioDevolucionRecord, dev_id)
    if not dev:
        raise HTTPException(404, "Oficio de devolución no encontrado")
    facturas = (
        db.query(FacturaPreauditoriaRecord)
        .filter(FacturaPreauditoriaRecord.oficio_devolucion_id == dev_id)
        .order_by(FacturaPreauditoriaRecord.envio, FacturaPreauditoriaRecord.factura)
        .all()
    )
    recepcion = (
        db.get(OficioRecepcionRecord, dev.oficio_recepcion_id)
        if dev.oficio_recepcion_id
        else None
    )
    fecha_local = a_utc(dev.fecha_generado)
    pdf = generar_pdf_oficio_devolucion(
        consecutivo=dev.consecutivo,
        fecha_generado=fecha_local.astimezone(TZ_BOGOTA) if fecha_local else None,
        numero_radicado=recepcion.numero_radicado if recepcion else "",
        facturas=[
            {
                "envio": f.envio,
                "factura": f.factura,
                "fecha_factura": f.fecha_factura,
                "valor": f.valor,
                "nit": f.nit,
                "entidad": f.entidad,
                "motivo_devolucion": f.motivo_devolucion,
            }
            for f in facturas
        ],
        generado_por=dev.generado_por or "",
    )
    nombre = f"{dev.consecutivo}.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


# ------------------------------------------------------------------
# 9-10. Semáforo global y estadísticas
# ------------------------------------------------------------------


@router.get("/estadisticas")
def estadisticas(
    desde: Optional[str] = Query(None, description="AAAA-MM-DD (fecha de recibido)"),
    hasta: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    consulta = db.query(FacturaPreauditoriaRecord).join(
        OficioRecepcionRecord,
        FacturaPreauditoriaRecord.oficio_id == OficioRecepcionRecord.id,
    )
    if desde:
        consulta = consulta.filter(
            OficioRecepcionRecord.fecha_recibido >= _parsear_fecha_local(desde)
        )
    if hasta:
        consulta = consulta.filter(
            OficioRecepcionRecord.fecha_recibido <= _parsear_fecha_local(hasta + "T23:59:59")
        )
    facturas = consulta.all()

    total = len(facturas)
    radicar = sum(1 for f in facturas if f.resultado == svc.RESULTADO_RADICAR)
    devueltas = sum(1 for f in facturas if f.resultado == svc.RESULTADO_DEVUELTA)
    pendientes = total - radicar - devueltas
    auditadas = radicar + devueltas

    por_auditor: dict[str, dict] = {}
    for f in facturas:
        if not f.auditor:
            continue
        a = por_auditor.setdefault(
            f.auditor,
            {"auditor": f.auditor, "auditadas": 0, "radicar": 0, "devueltas": 0, "valor": 0.0},
        )
        a["auditadas"] += 1
        a["valor"] += float(f.valor or 0)
        if f.resultado == svc.RESULTADO_RADICAR:
            a["radicar"] += 1
        elif f.resultado == svc.RESULTADO_DEVUELTA:
            a["devueltas"] += 1
    lista_auditores = sorted(
        por_auditor.values(), key=lambda a: a["auditadas"], reverse=True
    )

    # Reincidencia: cuántas veces fue devuelta cada factura (histórico completo)
    filas_dev = (
        db.query(
            FacturaPreauditoriaRecord.factura,
            sa_func.count(FacturaPreauditoriaRecord.id),
        )
        .filter(FacturaPreauditoriaRecord.resultado == svc.RESULTADO_DEVUELTA)
        .group_by(FacturaPreauditoriaRecord.factura)
        .all()
    )
    reincidentes = sorted(
        (
            {"factura": fac, "veces_devuelta": n}
            for fac, n in filas_dev
            if n >= 2
        ),
        key=lambda r: r["veces_devuelta"],
        reverse=True,
    )
    en_limite = [r for r in reincidentes if r["veces_devuelta"] >= svc.MAX_DEVOLUCIONES]

    # Subsanaciones (rondas 2+ ya auditadas)
    subsanadas = sum(
        1 for f in facturas if f.ronda > 1 and f.resultado == svc.RESULTADO_RADICAR
    )
    nuevamente_devueltas = sum(
        1 for f in facturas if f.ronda > 1 and f.resultado == svc.RESULTADO_DEVUELTA
    )

    # Semáforo de todos los oficios del rango
    oficios = db.query(OficioRecepcionRecord).all()
    conteo_semaforo = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0, "VENCIDO": 0, "COMPLETADO": 0}
    for o in oficios:
        fo = (
            db.query(FacturaPreauditoriaRecord)
            .filter(FacturaPreauditoriaRecord.oficio_id == o.id)
            .all()
        )
        s = svc.calcular_semaforo(o.fecha_recibido, completado=svc.oficio_completado(fo))
        conteo_semaforo[s["estado"]] = conteo_semaforo.get(s["estado"], 0) + 1

    return {
        "total_facturas": total,
        "auditadas": auditadas,
        "pendientes": pendientes,
        "radicar": radicar,
        "devueltas": devueltas,
        "subsanadas": subsanadas,
        "nuevamente_devueltas": nuevamente_devueltas,
        "valor_total": sum(float(f.valor or 0) for f in facturas),
        "por_auditor": lista_auditores,
        "reincidentes": reincidentes[:50],
        "en_limite_devoluciones": en_limite,
        "semaforo_oficios": conteo_semaforo,
        "max_devoluciones": svc.MAX_DEVOLUCIONES,
    }
