from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.db import UsuarioRecord, GlosaRecord
from app.repositories.conciliacion_repository import ConciliacionRepository
from app.repositories.audit_repository import AuditRepository
from app.api.deps import get_usuario_actual, get_auditor_o_superior

router = APIRouter(prefix="/conciliaciones", tags=["conciliacion"])


class ConciliacionCreate(BaseModel):
    glosa_id: int
    fecha_audiencia: str
    lugar: Optional[str] = ""
    participantes_hus: Optional[str] = ""
    participantes_eps: Optional[str] = ""
    observaciones: Optional[str] = ""
    acta_numero: Optional[str] = ""


class ResultadoUpdate(BaseModel):
    resultado: str
    valor_conciliado: float = 0.0
    observaciones: Optional[str] = ""
    siguiente_paso: Optional[str] = ""
    acta_numero: Optional[str] = ""


@router.post("/", status_code=201)
def crear_conciliacion(data: ConciliacionCreate, db: Session = Depends(get_db),
                       current_user: UsuarioRecord = Depends(get_auditor_o_superior)):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == data.glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    try:
        fecha = datetime.fromisoformat(data.fecha_audiencia)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use ISO: 2026-05-10T10:00:00")
    c = ConciliacionRepository(db).crear(
        glosa_id=data.glosa_id, creado_por=current_user.email, fecha_audiencia=fecha,
        lugar=data.lugar or "", participantes_hus=data.participantes_hus or "",
        participantes_eps=data.participantes_eps or "",
        observaciones=data.observaciones or "", acta_numero=data.acta_numero or "",
    )
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="CREAR", tabla="conciliaciones", registro_id=c.id,
        detalle=f"Conciliación programada para glosa #{data.glosa_id} — fecha: {fecha.date()}")
    return {"message": "Conciliación programada correctamente", "id": c.id,
            "glosa_id": c.glosa_id,
            "fecha_audiencia": c.fecha_audiencia.isoformat() if c.fecha_audiencia else None}


@router.get("/")
def listar_conciliaciones(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100),
                          resultado: Optional[str] = None, db: Session = Depends(get_db),
                          current_user: UsuarioRecord = Depends(get_usuario_actual)):
    res = ConciliacionRepository(db).listar(page=page, per_page=per_page, resultado=resultado)
    return {"items": [_serializar(c) for c in res["items"]], "total": res["total"],
            "page": res["page"], "per_page": res["per_page"], "pages": res["pages"]}


@router.get("/estadisticas")
def estadisticas_conciliaciones(db: Session = Depends(get_db),
                                current_user: UsuarioRecord = Depends(get_usuario_actual)):
    return ConciliacionRepository(db).estadisticas()


@router.get("/glosa/{glosa_id}")
def conciliaciones_por_glosa(glosa_id: int, db: Session = Depends(get_db),
                              current_user: UsuarioRecord = Depends(get_usuario_actual)):
    return [_serializar(c) for c in ConciliacionRepository(db).listar_por_glosa(glosa_id)]


@router.patch("/{conciliacion_id}/resultado")
def registrar_resultado(conciliacion_id: int, data: ResultadoUpdate,
                        db: Session = Depends(get_db),
                        current_user: UsuarioRecord = Depends(get_auditor_o_superior)):
    RESULTADOS_VALIDOS = {"ACUERDO_TOTAL", "ACUERDO_PARCIAL", "SIN_ACUERDO"}
    if data.resultado.upper() not in RESULTADOS_VALIDOS:
        raise HTTPException(status_code=400,
                            detail=f"Resultado inválido. Use: {', '.join(RESULTADOS_VALIDOS)}")
    c = ConciliacionRepository(db).actualizar_resultado(
        conciliacion_id=conciliacion_id, resultado=data.resultado.upper(),
        valor_conciliado=data.valor_conciliado, observaciones=data.observaciones or "",
        siguiente_paso=data.siguiente_paso or "", acta_numero=data.acta_numero or "")
    if not c:
        raise HTTPException(status_code=404, detail="Conciliación no encontrada")
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="ACTUALIZAR", tabla="conciliaciones", registro_id=conciliacion_id,
        campo="resultado", valor_nuevo=data.resultado,
        detalle=f"Resultado conciliación #{conciliacion_id}: {data.resultado} — valor: ${data.valor_conciliado:,.0f}")
    return {"message": "Resultado registrado", "conciliacion": _serializar(c)}


def _serializar(c) -> dict:
    return {"id": c.id, "glosa_id": c.glosa_id, "creado_por": c.creado_por,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
            "fecha_audiencia": c.fecha_audiencia.isoformat() if c.fecha_audiencia else None,
            "lugar": c.lugar, "participantes_hus": c.participantes_hus,
            "participantes_eps": c.participantes_eps, "resultado": c.resultado,
            "valor_conciliado": c.valor_conciliado, "observaciones": c.observaciones,
            "siguiente_paso": c.siguiente_paso, "acta_numero": c.acta_numero}
