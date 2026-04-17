"""Biblioteca de plantillas 'gold' — argumentos que ganaron la glosa.

Se guardan respuestas exitosas (glosa levantada por la EPS) y se usan como
few-shot examples al generar respuestas para nuevas glosas del mismo
(EPS, código). Efecto compuesto: cada victoria mejora las próximas.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.db import PlantillaGoldRecord, GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual, get_coordinador_o_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/plantillas-gold", tags=["plantillas-gold"])


class PlantillaGoldInput(BaseModel):
    eps: str
    codigo_glosa: str
    titulo: str = Field(..., max_length=200)
    argumento: str
    tipo: Optional[str] = None
    glosa_origen_id: Optional[int] = None
    valor_recuperado: Optional[float] = 0.0
    notas: Optional[str] = None


class PlantillaGoldUpdate(BaseModel):
    titulo: Optional[str] = None
    argumento: Optional[str] = None
    notas: Optional[str] = None
    activa: Optional[bool] = None


@router.get("/")
def listar(
    eps: Optional[str] = None,
    codigo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista plantillas gold. Acepta filtros por EPS y código."""
    q = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.activa == 1)
    if eps:
        q = q.filter(PlantillaGoldRecord.eps.ilike(f"%{eps}%"))
    if codigo:
        q = q.filter(PlantillaGoldRecord.codigo_glosa == codigo.upper())
    q = q.order_by(PlantillaGoldRecord.usos.desc(), PlantillaGoldRecord.creado_en.desc())
    return [
        {
            "id": p.id,
            "eps": p.eps,
            "codigo_glosa": p.codigo_glosa,
            "tipo": p.tipo,
            "titulo": p.titulo,
            "argumento": p.argumento,
            "glosa_origen_id": p.glosa_origen_id,
            "valor_recuperado": float(p.valor_recuperado or 0),
            "usos": p.usos or 0,
            "creado_por": p.creado_por,
            "creado_en": p.creado_en.isoformat() if p.creado_en else None,
            "ultima_uso_en": p.ultima_uso_en.isoformat() if p.ultima_uso_en else None,
            "notas": p.notas,
        }
        for p in q.limit(500).all()
    ]


@router.post("/", status_code=201)
def crear(
    data: PlantillaGoldInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Guarda una respuesta exitosa como plantilla gold."""
    if len(data.argumento.strip()) < 50:
        raise HTTPException(400, "El argumento debe tener al menos 50 caracteres")

    rec = PlantillaGoldRecord(
        eps=(data.eps or "").upper().strip(),
        codigo_glosa=(data.codigo_glosa or "").upper().strip(),
        tipo=data.tipo,
        titulo=data.titulo.strip(),
        argumento=data.argumento.strip(),
        glosa_origen_id=data.glosa_origen_id,
        valor_recuperado=data.valor_recuperado or 0.0,
        notas=data.notas,
        creado_por=current_user.email,
        activa=1,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_CREAR",
        tabla="plantillas_gold",
        registro_id=rec.id,
        detalle=f"{rec.eps} · {rec.codigo_glosa} · {rec.titulo}",
    )
    return {"id": rec.id, "message": "Plantilla gold creada"}


@router.post("/desde-glosa/{glosa_id}")
def crear_desde_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea una plantilla gold a partir de una glosa que fue LEVANTADA o
    ACEPTADA por la EPS. Extrae el argumento del dictamen automáticamente."""
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(404, "Glosa no encontrada")
    if not g.dictamen:
        raise HTTPException(400, "La glosa no tiene dictamen generado")

    # Extraer argumento limpio del HTML
    import re as _re
    from html import unescape
    txt = _re.sub(r"<[^>]+>", " ", g.dictamen)
    txt = _re.sub(r"\s+", " ", unescape(txt)).strip()
    for marker in ("ARGUMENTACIÓN JURÍDICA", "RESPUESTA A GLOSA"):
        if marker in txt and len(txt.split(marker, 1)[0]) < 500:
            txt = txt.split(marker, 1)[1].strip()
            break
    for cierre in ("Nota: Generado con asistencia", "RESUMEN DE VALORES"):
        if cierre in txt:
            txt = txt.split(cierre)[0].strip()

    if len(txt) < 80:
        raise HTTPException(400, "No se pudo extraer un argumento suficientemente largo")

    titulo = f"{g.codigo_glosa or '—'} · {g.eps or '—'}"
    valor_recuperado = (g.valor_objetado or 0) - (g.valor_aceptado or 0)

    rec = PlantillaGoldRecord(
        eps=(g.eps or "").upper().strip(),
        codigo_glosa=(g.codigo_glosa or "").upper().strip(),
        tipo=None,
        titulo=titulo[:200],
        argumento=txt,
        glosa_origen_id=g.id,
        valor_recuperado=float(valor_recuperado),
        creado_por=current_user.email,
        activa=1,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_CREAR",
        tabla="plantillas_gold",
        registro_id=rec.id,
        detalle=f"desde glosa #{glosa_id} · ${valor_recuperado:,.0f} recuperados",
    )
    return {"id": rec.id, "message": "Plantilla gold creada desde glosa"}


@router.patch("/{plantilla_id}")
def actualizar(
    plantilla_id: int,
    data: PlantillaGoldUpdate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    p = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.id == plantilla_id).first()
    if not p:
        raise HTTPException(404, "Plantilla no encontrada")

    if data.titulo is not None:
        p.titulo = data.titulo.strip()[:200]
    if data.argumento is not None:
        p.argumento = data.argumento.strip()
    if data.notas is not None:
        p.notas = data.notas
    if data.activa is not None:
        p.activa = 1 if data.activa else 0
    db.commit()

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_UPDATE",
        tabla="plantillas_gold",
        registro_id=plantilla_id,
    )
    return {"id": plantilla_id, "message": "Plantilla actualizada"}


@router.delete("/{plantilla_id}")
def eliminar(
    plantilla_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    p = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.id == plantilla_id).first()
    if not p:
        raise HTTPException(404, "Plantilla no encontrada")
    db.delete(p)
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_DELETE",
        tabla="plantillas_gold",
        registro_id=plantilla_id,
    )
    return {"message": "Plantilla eliminada"}


def obtener_few_shot(db: Session, eps: str, codigo_glosa: str, limite: int = 2) -> list[PlantillaGoldRecord]:
    """Obtiene las mejores plantillas gold para inyectar como ejemplo en el
    prompt. Prioriza: match exacto de EPS y código, luego mismo código para
    cualquier EPS, ordenando por número de usos."""
    if not codigo_glosa:
        return []
    codigo = codigo_glosa.upper().strip()
    eps_u = (eps or "").upper().strip()

    # Match exacto primero
    exactas = (
        db.query(PlantillaGoldRecord)
        .filter(
            PlantillaGoldRecord.activa == 1,
            PlantillaGoldRecord.codigo_glosa == codigo,
            PlantillaGoldRecord.eps == eps_u,
        )
        .order_by(PlantillaGoldRecord.usos.desc())
        .limit(limite)
        .all()
    )
    if len(exactas) >= limite:
        return exactas

    # Completar con mismo código en otras EPS
    faltan = limite - len(exactas)
    ids_ya = [p.id for p in exactas]
    genericas = (
        db.query(PlantillaGoldRecord)
        .filter(
            PlantillaGoldRecord.activa == 1,
            PlantillaGoldRecord.codigo_glosa == codigo,
            ~PlantillaGoldRecord.id.in_(ids_ya) if ids_ya else True,
        )
        .order_by(PlantillaGoldRecord.usos.desc())
        .limit(faltan)
        .all()
    )
    return exactas + genericas


def marcar_usos(db: Session, plantilla_ids: list[int]):
    """Incrementa el contador de usos y actualiza ultima_uso_en."""
    if not plantilla_ids:
        return
    now = datetime.utcnow()
    db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.id.in_(plantilla_ids)).update(
        {
            PlantillaGoldRecord.usos: PlantillaGoldRecord.usos + 1,
            PlantillaGoldRecord.ultima_uso_en: now,
        },
        synchronize_session=False,
    )
    db.commit()
