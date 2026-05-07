"""
auditor_forense.py — Endpoint para auditoria conversacional de soportes
por factura.

POST /auditor-forense
  Body: {factura: "HUS487233", pregunta: "buscar baciloscopia..."}
  Returns: {html, modelo, tokens, ...}

El gestor pregunta en lenguaje natural sobre los soportes de una
factura y la IA responde con un análisis estructurado citando folios.
"""
from __future__ import annotations
import os
import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request
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

    # Llamar al auditor forense
    resultado = await auditar_forense(
        factura=factura,
        pregunta_gestor=pregunta,
        pdfs_raw=pdfs_raw if pdfs_raw else None,
        contexto_pdf_texto=contexto_texto if not pdfs_raw else "",
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
    }
