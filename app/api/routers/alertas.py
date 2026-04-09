from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.glosa_repository import GlosaRepository
from app.services.alerta_service import AlertaService
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/alertas", tags=["alertas"])


@router.get("/proximas")
def obtener_alertas_proximas(
    dias: int = Query(5, ge=1, le=30, description="Días de anticipación"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Obtiene lista de glosas próximas a vencer.
    
    Requiere autenticación JWT.
    """
    repo = GlosaRepository(db)
    alertas = repo.alertas_proximas(dias_limite=dias)
    
    return {
        "total": len(alertas),
        "dias_umbral": dias,
        "alertas": [
            {
                "id": a.id,
                "eps": a.eps,
                "paciente": a.paciente,
                "codigo_glosa": a.codigo_glosa,
                "valor_objetado": a.valor_objetado,
                "dias_restantes": a.dias_restantes,
                "estado": a.estado,
                "workflow_state": a.workflow_state,
                "creado_en": a.creado_en.isoformat() if a.creado_en else None,
            }
            for a in alertas
        ]
    }


@router.post("/enviar")
def enviar_alertas_email(
    dias: int = Query(5, ge=1, le=30, description="Días de anticipación"),
    forzar: bool = Query(False, description="Enviar aunque no haya nuevas alertas"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Envía alerta por correo electrónico con las glosas próximas a vencer.
    
    Requiere autenticación JWT.
    Configurar SMTP_USER, SMTP_PASSWORD y ALERTAS_EMAIL en variables de entorno.
    """
    servicio = AlertaService()
    exito, mensaje = servicio.verificar_y_enviar_alertas(
        db=db,
        dias_limite=dias,
        forzar=forzar,
    )
    
    return {
        "success": exito,
        "message": mensaje,
        "configuracion": {
            "smtp_configurado": bool(__import__('os').getenv("SMTP_USER")),
            "destinatarios_configurados": bool(__import__('os').getenv("ALERTAS_EMAIL")),
        }
    }


@router.get("/config")
def obtener_config_alertas(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Retorna la configuración actual de alertas.
    
    Requiere autenticación JWT.
    """
    import os
    
    return {
        "smtp": {
            "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
            "puerto": os.getenv("SMTP_PORT", "587"),
            "usuario_configurado": bool(os.getenv("SMTP_USER")),
            "desde": os.getenv("SMTP_FROM", "noreply@hus.gov.co"),
        },
        "destinatarios": os.getenv("ALERTAS_EMAIL", "").split(",") if os.getenv("ALERTAS_EMAIL") else [],
        "umbral_default": 5,
    }
