"""Ingest IMAP de la bandeja institucional (skeleton).

Configurar con env vars:
- IMAP_HOST (ej: imap.gmail.com)
- IMAP_USER (ej: cartera@hus.gov.co)
- IMAP_PASSWORD (app password)
- IMAP_FOLDER (INBOX por defecto)

Endpoint POST /bandeja/poll-ahora procesa correos pendientes con adjuntos
Excel/PDF y los encola para importación. La automatización completa
(worker periódico) se puede programar con cron externo llamando este
endpoint cada N minutos.
"""
import os
import email
import imaplib
import base64
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db import UsuarioRecord
from app.api.deps import get_admin
from app.repositories.audit_repository import AuditRepository
from app.core.logging_utils import logger

router = APIRouter(prefix="/bandeja", tags=["bandeja"])


@router.get("/estado")
def estado(current_user: UsuarioRecord = Depends(get_admin)):
    return {
        "configurado": bool(os.getenv("IMAP_HOST") and os.getenv("IMAP_USER")),
        "host": os.getenv("IMAP_HOST", ""),
        "user": os.getenv("IMAP_USER", ""),
        "folder": os.getenv("IMAP_FOLDER", "INBOX"),
    }


@router.post("/poll-ahora")
def poll_ahora(
    max_mensajes: int = 20,
    marcar_leidos: bool = True,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Lee correos NO leídos de la bandeja institucional y devuelve los
    adjuntos encontrados. La IMPORTACIÓN real se dispara manualmente desde
    /glosas/importar-recepcion con el Excel bajado."""
    host = os.getenv("IMAP_HOST")
    user = os.getenv("IMAP_USER")
    pwd = os.getenv("IMAP_PASSWORD")
    if not (host and user and pwd):
        raise HTTPException(503, "Bandeja IMAP no configurada. Setea IMAP_HOST, IMAP_USER, IMAP_PASSWORD.")

    folder = os.getenv("IMAP_FOLDER", "INBOX")
    resultados = []
    try:
        M = imaplib.IMAP4_SSL(host)
        M.login(user, pwd)
        M.select(folder)
        typ, data = M.search(None, "UNSEEN")
        ids = data[0].split() if data and data[0] else []
        for raw_id in ids[:max_mensajes]:
            typ, msg_data = M.fetch(raw_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            adj = []
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None:
                    continue
                filename = part.get_filename()
                if not filename:
                    continue
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext not in ("xlsx", "xls", "pdf"):
                    continue
                content = part.get_payload(decode=True) or b""
                adj.append({
                    "filename": filename,
                    "tamano_bytes": len(content),
                    "mime": part.get_content_type(),
                    "base64_preview": base64.b64encode(content[:200]).decode("ascii"),
                })
            resultados.append({
                "id": raw_id.decode(),
                "asunto": msg.get("Subject", ""),
                "de": msg.get("From", ""),
                "fecha": msg.get("Date", ""),
                "adjuntos": adj,
            })
            if marcar_leidos:
                M.store(raw_id, "+FLAGS", "\\Seen")
        M.logout()
    except Exception as e:
        logger.error(f"IMAP error: {e}")
        raise HTTPException(500, f"Error IMAP: {e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="BANDEJA_POLL", tabla="historial",
        detalle=f"Mensajes procesados: {len(resultados)}",
    )
    return {
        "total_mensajes": len(resultados),
        "procesados_en": datetime.utcnow().isoformat(),
        "mensajes": resultados,
    }
