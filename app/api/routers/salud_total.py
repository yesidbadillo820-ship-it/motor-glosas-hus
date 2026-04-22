import io
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db import UsuarioRecord
from app.api.deps import get_usuario_actual
from app.services.salud_total_service import (
    procesar_glosas_salud_total,
    generar_txt_respuesta,
    generar_nombre_archivo,
)

router = APIRouter(prefix="/api/salud-total", tags=["Salud Total"])

def _decodificar_contenido(contenido: bytes) -> str:
    """Decodifica UTF-8, cayendo a Latin-1 si el archivo no es UTF-8 válido."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return contenido.decode(enc)
        except UnicodeDecodeError:
            continue
    # Último recurso: ignorar bytes inválidos
    return contenido.decode("utf-8", errors="ignore")


@router.post("/preview")
async def preview_glosas(
    file: UploadFile = File(...),
    tipo_respuesta: str = Form("extemporanea"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .txt")

    contenido = await file.read()
    contenido_decoded = _decodificar_contenido(contenido)

    fecha_recepcion = None
    try:
        respuestas = procesar_glosas_salud_total(contenido_decoded, tipo_respuesta, fecha_recepcion)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not respuestas:
        raise HTTPException(status_code=400, detail="No se encontraron glosas en el archivo")

    total_glosado = sum(r.get("ValorGlosaTotalxServ", 0) for r in respuestas)
    total_aceptado = sum(r.get("ValorAceptadoIPS", 0) for r in respuestas)

    return {
        "total_registros": len(respuestas),
        "total_glosado": total_glosado,
        "total_aceptado": total_aceptado,
        "total_rechazado": total_glosado - total_aceptado,
        "glosas": respuestas[:50],
    }

@router.post("/procesar")
async def procesar_glosas(
    file: UploadFile = File(None),
    tipo_respuesta: str = Form("extemporanea"),
    fecha_recepcion: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if tipo_respuesta == "ia" and not file:
        raise HTTPException(status_code=400, detail="Debe subir archivo TXT para análisis con IA")
    
    if tipo_respuesta != "ia" and (not file or not file.filename.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Debe subir archivo TXT")
    
    contenido = None
    if file:
        contenido = await file.read()
        contenido_decoded = _decodificar_contenido(contenido)
    else:
        contenido_decoded = ""

    fecha_recepcion_dt = None
    if fecha_recepcion:
        try:
            fecha_recepcion_dt = datetime.strptime(fecha_recepcion, "%Y-%m-%d")
        except ValueError:
            pass

    try:
        respuestas = procesar_glosas_salud_total(contenido_decoded, tipo_respuesta, fecha_recepcion_dt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not respuestas:
        raise HTTPException(status_code=400, detail="No se encontraron glosas en el archivo")
    
    txt_salida = generar_txt_respuesta(respuestas)
    nombre_archivo = generar_nombre_archivo(tipo_respuesta)
    
    return StreamingResponse(
        io.BytesIO(txt_salida.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )
