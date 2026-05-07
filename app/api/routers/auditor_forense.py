"""
auditor_forense.py — Endpoint para auditoria conversacional de soportes
por factura.

POST /auditor-forense
  Body: {factura: "HUS487233", pregunta: "buscar baciloscopia..."}
  Returns: {html, modelo, tokens, ...}

POST /auditor-forense/upload  (multipart)
  files[]: PDFs subidos por el browser desde el servidor local del HUS
  factura, pregunta, refrescar
  Returns: igual que el endpoint anterior

El gestor pregunta en lenguaje natural sobre los soportes de una
factura y la IA responde con un análisis estructurado citando folios.

Variantes:
  - /auditor-forense       — el motor lee soportes desde el indexer
                             local (jump-box/mount). Requiere mirror.
  - /auditor-forense/upload — el browser del gestor descarga los PDFs
                             del servidor HTTP local del HUS y los
                             sube al motor. NO requiere mirror.
"""
from __future__ import annotations
import os
import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger("motor_glosas")

router = APIRouter(prefix="/auditor-forense", tags=["auditor-forense"])


class AuditorForenseRequest(BaseModel):
    factura: str = Field(..., min_length=3, max_length=50)
    pregunta: str = Field(..., min_length=5, max_length=2000)
    # Si True, manda los PDFs binarios a Claude (más caro, más preciso).
    # Default True porque el caso de uso del gestor (citar folios) lo
    # exige. Si soportes son muchos o pesados, fallback a texto extraído.
    usar_pdf_nativo: bool = True
    # Si True, ignora el cache y re-llama a Claude. Util cuando los
    # soportes cambiaron y queremos respuesta fresca antes del TTL (14d).
    refrescar: bool = False


@router.post("/")
async def auditar_factura(
    payload: AuditorForenseRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Auditoria conversacional sobre los soportes de una factura.

    Flow:
      1. Indexer.lookup(factura) -> lista de archivos disponibles
      2. Lee cada PDF (binario para multi-modal o texto si no)
      3. Llama a Claude con prompt forense focalizado
      4. Devuelve HTML estructurado en 4 secciones

    Rate-limit: 10/min — cada llamada cuesta ~$0.10-0.30 USD.

    Auditoria: cada llamada queda registrada (PHI: revisar historias
    clínicas es sensible).
    """
    from app.services.soportes_autodiscovery_service import get_indexer
    from app.services.auditor_forense import auditar_forense

    factura = payload.factura.strip().upper()
    pregunta = payload.pregunta.strip()

    indexer = get_indexer()
    soportes = indexer.lookup(factura)
    if not soportes:
        raise HTTPException(
            404,
            f"No hay soportes indexados para la factura {factura}. "
            f"Verificá que el jump-box haya subido los archivos."
        )

    # Cap: max 5 PDFs (Claude PDF nativo) o ~30k chars de texto
    pdfs_raw: list[tuple[str, bytes]] = []
    contexto_texto = ""
    soportes_usados: list[str] = []

    if payload.usar_pdf_nativo:
        for s in soportes[:5]:
            ruta = s.get("ruta")
            if not ruta:
                continue
            try:
                if not os.path.exists(ruta):
                    continue
                size = os.path.getsize(ruta)
                if size > 30 * 1024 * 1024:
                    logger.warning(f"[AUDITOR-FORENSE] {ruta} >30MB, saltado")
                    continue
                with open(ruta, "rb") as f:
                    data = f.read()
                pdfs_raw.append((s.get("nombre_archivo", "soporte.pdf"), data))
                soportes_usados.append(s.get("nombre_archivo", ""))
            except Exception as e:
                logger.warning(f"[AUDITOR-FORENSE] No se pudo leer {ruta}: {e}")

    if not pdfs_raw:
        # Fallback: extraer texto con pdf_service
        from app.services.pdf_service import PdfService
        pdf_svc = PdfService()
        for s in soportes[:5]:
            ruta = s.get("ruta")
            if not ruta or not os.path.exists(ruta):
                continue
            try:
                with open(ruta, "rb") as f:
                    data = f.read()
                texto = await pdf_svc.extraer(data)
                if texto:
                    contexto_texto += f"\n═══ DOCUMENTO: {s.get('nombre_archivo', '')} ═══\n\n{texto}\n"
                    soportes_usados.append(s.get("nombre_archivo", ""))
            except Exception as e:
                logger.warning(f"[AUDITOR-FORENSE] PDF extract falló {ruta}: {e}")
            if len(contexto_texto) > 60000:
                break

    if not pdfs_raw and not contexto_texto:
        raise HTTPException(500, "No se pudo leer ningún soporte de esta factura")

    # Llamar al auditor forense (con cache TTL 14d, key: factura+pregunta+pdfs+modelo)
    resultado = await auditar_forense(
        factura=factura,
        pregunta_gestor=pregunta,
        pdfs_raw=pdfs_raw if pdfs_raw else None,
        contexto_pdf_texto=contexto_texto if not pdfs_raw else "",
        bypass_cache=bool(payload.refrescar),
    )

    if resultado.get("error"):
        raise HTTPException(500, resultado["error"])

    # Audit log PHI (consulta de historia clínica)
    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="AUDITOR_FORENSE",
            tabla="soportes_share",
            detalle=(
                f"factura={factura} soportes_usados={len(soportes_usados)} "
                f"pregunta={pregunta[:200]}"
            ),
            ip=request.client.host if request.client else None,
        )
    except Exception:
        pass

    return {
        "factura": factura,
        "pregunta": pregunta,
        "html": resultado["html"],
        "modelo": resultado.get("modelo"),
        "input_tokens": resultado.get("input_tokens", 0),
        "output_tokens": resultado.get("output_tokens", 0),
        "soportes_usados": soportes_usados,
        "modo": "pdf_nativo" if pdfs_raw else "texto_extraido",
        "cache_hit": bool(resultado.get("cache_hit")),
    }


# ─── Variante multipart: el browser sube los PDFs ─────────────────────
# Caso de uso: el gestor del HUS tiene un servidor HTTP local que
# expone Y:\FEBRERO 2026 ... como directory listing (Python http.server,
# Apache, etc). El browser descarga los PDFs de la factura desde ese
# servidor, los empaca como multipart y los sube al motor. El motor los
# pasa a Claude. NO requiere que el motor tenga acceso al share local.
#
# Ventaja: cero infraestructura adicional (sin jump-box sync, sin
# mirror, sin tunnels).
# Limites: max 5 PDFs por request, 30MB cada uno (alineado con
# limites de Claude Messages PDF nativo).
@router.post("/upload")
async def auditar_factura_con_uploads(
    request: Request,
    factura: str = Form(...),
    pregunta: str = Form(...),
    refrescar: bool = Form(False),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Auditoria forense usando PDFs que el browser sube directamente.

    El frontend descarga los PDFs del servidor HTTP local (que expone
    Y:\\FEBRERO 2026 ...) y los manda como multipart. El motor los
    pasa a Claude PDF-nativo sin necesidad de tener acceso al share.

    Cache TTL 14d por (factura+pregunta+hash_pdfs+modelo). Bypass con
    refrescar=true.
    """
    from app.services.auditor_forense import auditar_forense

    factura = (factura or "").strip().upper()
    pregunta = (pregunta or "").strip()
    if len(factura) < 3:
        raise HTTPException(400, "factura invalida")
    if len(pregunta) < 5:
        raise HTTPException(400, "pregunta muy corta (min 5 chars)")
    if not files:
        raise HTTPException(400, "Sin archivos adjuntos")
    if len(files) > 5:
        raise HTTPException(400, "Max 5 PDFs por request")

    pdfs_raw: list[tuple[str, bytes]] = []
    soportes_usados: list[str] = []
    total_bytes = 0
    MAX_PDF = 30 * 1024 * 1024
    MAX_TOTAL = 100 * 1024 * 1024

    for f in files:
        nombre = f.filename or "soporte.pdf"
        if not nombre.lower().endswith(".pdf"):
            continue  # ignora no-PDFs silenciosamente
        data = await f.read(MAX_PDF + 1)
        if len(data) > MAX_PDF:
            logger.warning(f"[FORENSE-UPLOAD] {nombre} >30MB, saltado")
            continue
        if len(data) < 1024:
            continue  # vacío o corrupto
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL:
            logger.warning(f"[FORENSE-UPLOAD] total >100MB, corte en {nombre}")
            break
        pdfs_raw.append((nombre, data))
        soportes_usados.append(nombre)

    if not pdfs_raw:
        raise HTTPException(400, "Ningun PDF valido en los archivos adjuntos")

    resultado = await auditar_forense(
        factura=factura,
        pregunta_gestor=pregunta,
        pdfs_raw=pdfs_raw,
        bypass_cache=bool(refrescar),
    )
    if resultado.get("error"):
        raise HTTPException(500, resultado["error"])

    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="AUDITOR_FORENSE_UPLOAD",
            tabla="soportes_share",
            detalle=(
                f"factura={factura} pdfs={len(pdfs_raw)} "
                f"bytes={total_bytes} pregunta={pregunta[:200]}"
            ),
            ip=request.client.host if request.client else None,
        )
    except Exception:
        pass

    return {
        "factura": factura,
        "pregunta": pregunta,
        "html": resultado["html"],
        "modelo": resultado.get("modelo"),
        "input_tokens": resultado.get("input_tokens", 0),
        "output_tokens": resultado.get("output_tokens", 0),
        "soportes_usados": soportes_usados,
        "modo": "pdf_nativo_upload",
        "cache_hit": bool(resultado.get("cache_hit")),
        "bytes_recibidos": total_bytes,
    }
