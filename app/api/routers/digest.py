"""Router del digest ejecutivo (Ronda 19).

Endpoints:

  GET  /digest/preview?periodo=dia|semana|mes
    Preview del digest (no envía). Solo coordinador/super_admin.

  POST /digest/enviar?periodo=dia&canal=whatsapp
    Genera digest + envía vía bot_mensajeria al destinatario indicado
    en el body. Útil para que el coordinador programe un envío manual.

  GET  /digest/texto?periodo=dia
    Versión en texto plano, listo para copiar/pegar.

  GET  /digest/html?periodo=dia
    Versión HTML, lista para email.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.bot_mensajeria import enviar_notificacion
from app.services.digest_ejecutivo import (
    formatear_digest_html,
    formatear_digest_texto,
    generar_digest,
)
from app.services.digest_scheduler import (
    ejecutar_envio_digest as _ejecutar_envio_digest,
    obtener_estado as _obtener_estado_scheduler,
)

router = APIRouter(prefix="/digest", tags=["digest"])


Periodo = Literal["dia", "semana", "mes"]


class EnvioDigestBody(BaseModel):
    destinatario: str = Field(..., description="Teléfono E.164 o chat_id de Telegram")
    canal: Literal["whatsapp", "telegram", "mock"] = "mock"


@router.get("/preview")
def preview(
    periodo: Periodo = Query("dia"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    return generar_digest(db, periodo=periodo)


@router.get("/texto")
def digest_texto(
    periodo: Periodo = Query("dia"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    d = generar_digest(db, periodo=periodo)
    return {"periodo": periodo, "texto": formatear_digest_texto(d)}


@router.get("/html")
def digest_html(
    periodo: Periodo = Query("dia"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    d = generar_digest(db, periodo=periodo)
    return {"periodo": periodo, "html": formatear_digest_html(d)}


@router.get("/scheduler/estado")
def scheduler_estado(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Estado del scheduler automático del digest (Ronda 20)."""
    return _obtener_estado_scheduler()


@router.post("/scheduler/disparar")
async def scheduler_disparar(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Fuerza la ejecución del scheduler ahora mismo (útil para probar
    que los destinatarios están correctamente configurados)."""
    return await _ejecutar_envio_digest()


@router.post("/enviar")
def enviar_digest(
    body: EnvioDigestBody,
    periodo: Periodo = Query("dia"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    if not body.destinatario or not body.destinatario.strip():
        raise HTTPException(status_code=400, detail="destinatario requerido")
    d = generar_digest(db, periodo=periodo)
    texto = formatear_digest_texto(d)
    resultado = enviar_notificacion(
        destinatario=body.destinatario.strip(),
        mensaje=texto,
        canal=body.canal,
    )
    return {
        "periodo": periodo,
        "canal": body.canal,
        "destinatario": body.destinatario,
        "envio": resultado,
    }
