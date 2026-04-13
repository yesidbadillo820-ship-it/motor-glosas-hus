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
    try:
        contenido_decoded = contenido.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Error al decodificar el archivo")
    
    fecha_recepcion = None
    respuestas = procesar_glosas_salud_total(contenido_decoded, tipo_respuesta, fecha_recepcion)
    
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
        try:
            contenido_decoded = contenido.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Error al decodificar el archivo")
    else:
        contenido_decoded = ""
    
    fecha_recepcion_dt = None
    if fecha_recepcion:
        try:
            fecha_recepcion_dt = datetime.strptime(fecha_recepcion, "%Y-%m-%d")
        except ValueError:
            pass
    
    respuestas = procesar_glosas_salud_total(contenido_decoded, tipo_respuesta, fecha_recepcion_dt)
    
    if not respuestas:
        raise HTTPException(status_code=400, detail="No se encontraron glosas en el archivo")
    
    txt_salida = generar_txt_respuesta(respuestas)
    nombre_archivo = generar_nombre_archivo(tipo_respuesta)
    
    return StreamingResponse(
        io.BytesIO(txt_salida.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )
