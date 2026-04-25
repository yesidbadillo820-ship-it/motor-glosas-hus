"""Endpoint /pdf/ocr — extracción de texto de PDF con OCR opcional (R51 P6).

Extraído de app/main.py para reducir su tamaño.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.models.db import UsuarioRecord
from app.services.pdf_service import PdfService

router = APIRouter(tags=["pdf"])

cfg = get_settings()


@router.post("/pdf/ocr")
async def pdf_ocr(
    archivo: UploadFile = File(...),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Sube un PDF y devuelve su texto. Si el PDF es escaneado y hay
    ANTHROPIC_API_KEY configurada, usa Claude Vision como OCR."""
    contenido = await archivo.read()
    if contenido[:4] != b"%PDF":
        raise HTTPException(400, "El archivo no es un PDF válido")
    if len(contenido) > 30_000_000:
        raise HTTPException(400, "PDF muy grande (>30 MB)")

    pdf_svc = PdfService()
    texto, metodo = await pdf_svc.extraer_con_ocr(
        contenido,
        anthropic_api_key=cfg.anthropic_api_key,
        anthropic_model=cfg.anthropic_model,
    )
    return {
        "metodo": metodo,
        "caracteres": len(texto),
        "texto": texto,
        "archivo": archivo.filename,
    }
