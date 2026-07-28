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
        ],
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
            "smtp_configurado": bool(__import__("os").getenv("SMTP_USER")),
            "destinatarios_configurados": bool(__import__("os").getenv("ALERTAS_EMAIL")),
        },
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
        "destinatarios": os.getenv("ALERTAS_EMAIL", "").split(",")
        if os.getenv("ALERTAS_EMAIL")
        else [],
        "umbral_default": 5,
    }


# ─── Motor de Vencimientos ───────────────────────────────────────────────
# El semáforo tenía estado NEGRO para lo vencido y no disparaba nada: tres
# facturas de junio por $20.054.751 se descubrieron 45 días tarde. Estos dos
# endpoints exponen la capacidad del núcleo (`motor_vencimientos`), que
# clasifica por urgencia y resuelve a quién le toca cada glosa.


@router.get("/vencimientos")
def tablero_vencimientos(
    incluir_cerradas: bool = Query(False, description="Incluir glosas ya resueltas"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Fotografía del riesgo por vencimiento: cuántas, de qué urgencia y cuánta plata.

    Funciona SIEMPRE, esté o no configurado el correo: es preferible que el
    área vea el listado en pantalla a que nadie se entere.
    """
    from app.models.db import GlosaRecord
    from app.services.motor_vencimientos import Destinatarios, Umbrales, evaluar

    q = db.query(GlosaRecord)
    if not incluir_cerradas:
        q = q.filter(GlosaRecord.dias_restantes.isnot(None))
    resumen = evaluar(q.all())

    umbrales = Umbrales.desde_entorno()
    destinatarios = Destinatarios.desde_entorno()
    return {
        **resumen.como_dict(),
        "umbrales": {
            "preventivo": umbrales.preventivo,
            "alta": umbrales.alta,
            "critica": umbrales.critica,
        },
        "avisos_configurados": destinatarios.hay_alguno,
        "escalamiento_configurado": destinatarios.hay_escalamiento,
    }


@router.post("/vencimientos/notificar")
def notificar_vencimientos(
    simular: bool = Query(True, description="Solo mostrar a quién se avisaría, sin enviar"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Avisa a cada responsable de lo suyo: un correo por persona, no por glosa.

    Por defecto SIMULA (`simular=true`): devuelve a quién le llegaría qué, sin
    enviar nada. Es la forma segura de estrenar la configuración.
    """
    from app.models.db import GlosaRecord
    from app.services.motor_vencimientos import (
        Destinatarios,
        agrupar_por_destinatario,
        evaluar,
    )

    destinatarios = Destinatarios.desde_entorno()
    if not destinatarios.hay_alguno:
        return {
            "enviados": 0,
            "simulado": simular,
            "detalle": (
                "No hay destinatarios configurados. Definí VENCIMIENTOS_CORREO_ALTA, "
                "_CRITICA y _VENCIDA (o dejá VENCIMIENTOS_CORREO_GESTOR=1) antes de "
                "activar los avisos."
            ),
            "bandejas": {},
        }

    resumen = evaluar(db.query(GlosaRecord).filter(GlosaRecord.dias_restantes.isnot(None)).all())
    bandejas = agrupar_por_destinatario(resumen, destinatarios)

    plan = {
        correo: {
            "total": len(items),
            "por_urgencia": {
                n: len([i for i in items if i.urgencia.value == n])
                for n in ("VENCIDA", "CRITICA", "ALTA", "PREVENTIVO")
            },
        }
        for correo, items in bandejas.items()
    }

    if simular:
        return {"enviados": 0, "simulado": True, "bandejas": plan}

    servicio = AlertaService()
    enviados, fallidos = 0, []
    for correo, items in bandejas.items():
        try:
            ok, msg = servicio.email_service.enviar_alerta_glosas(
                [i.glosa for i in items],
                dias_limite=max((i.dias_restantes or 0) for i in items),
                destinatarios=[correo],
            )
            if ok:
                enviados += 1
            else:
                fallidos.append({"correo": correo, "error": msg})
        except Exception as e:  # el fallo de un correo no puede tumbar el resto
            fallidos.append({"correo": correo, "error": str(e)[:200]})

    return {"enviados": enviados, "simulado": False, "fallidos": fallidos, "bandejas": plan}
