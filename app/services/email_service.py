import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.core.logging_utils import logger

_executor = ThreadPoolExecutor(max_workers=2)


def _build_html_base(titulo: str, contenido: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{titulo}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:'Segoe UI',Arial,sans-serif">
    <div style="max-width:600px;margin:0 auto;background:#ffffff">
        <div style="background:#0e1f3d;padding:20px;text-align:center">
            <h1 style="color:#ffffff;margin:0;font-size:24px">ESE Hospital Universitario de Santander</h1>
            <p style="color:#94a3b8;margin:5px 0 0;font-size:12px">Sistema Automatizado de Glosas</p>
        </div>
        <div style="padding:30px">
            <h2 style="color:#1f2937;margin:0 0 20px;font-size:20px">{titulo}</h2>
            {contenido}
        </div>
        <div style="background:#f9fafb;padding:20px;text-align:center;border-top:1px solid #e5e7eb">
            <p style="color:#6b7280;font-size:12px;margin:0">
                Este es un mensaje automático del Sistema de Glosas HUS.<br>
                No responder directamente este correo.
            </p>
        </div>
    </div>
</body>
</html>
"""


def _enviar_sync(destinatario: str, asunto: str, html: str) -> bool:
    cfg = get_settings()
    if not cfg.smtp_user or not cfg.smtp_password:
        logger.warning("Email no configurado: SMTP_USER o SMTP_PASSWORD vacíos")
        return False
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = cfg.smtp_user
        msg["To"] = destinatario
        msg.attach(MIMEText(html, "html"))
        
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.send_message(msg)
        
        logger.info(f"Email enviado a {destinatario}: {asunto}")
        return True
    except Exception as e:
        logger.error(f"Error enviando email a {destinatario}: {e}")
        return False


async def enviar_email(destinatario: str, asunto: str, html: str) -> bool:
    loop = __import__("asyncio").get_event_loop()
    return await loop.run_in_executor(_executor, _enviar_sync, destinatario, asunto, html)


async def notificar_alerta_vencimiento(eps: str, dias_restantes: int, valor: float, destinatario: str):
    cfg = get_settings()
    if not cfg.alertas_email:
        return
    
    asunto = f"🔔 Alerta: Glosa próximo a vencer - {eps}"
    contenido = f"""
    <p style="color:#374151;font-size:14px;line-height:1.6">
        Se ha detectado una glosa que vence en <strong>{dias_restantes} día(s)</strong> para la EPS <strong>{eps}</strong>.
    </p>
    <div style="background:#fef3c7;border-radius:8px;padding:15px;margin:20px 0">
        <p style="margin:0;font-size:14px">
            <strong>EPS:</strong> {eps}<br>
            <strong>Días restantes:</strong> {dias_restantes}<br>
            <strong>Valor objetado:</strong> ${valor:,.0f}
        </p>
    </div>
    <p style="color:#6b7280;font-size:12px">
        Por favor revisar el sistema para tomar las acciones pertinentes.
    </p>
    """
    await enviar_email(destinatario, asunto, _build_html_base(asunto, contenido))


async def notificar_batch_completado(batch_id: str, total: int, exitosas: int, destinatario: str):
    cfg = get_settings()
    if not cfg.alertas_email:
        return
    
    asunto = f"✅ Importación masiva completada - {batch_id}"
    contenido = f"""
    <p style="color:#374151;font-size:14px;line-height:1.6">
        La importación masiva de glosas ha sido procesada.
    </p>
    <div style="background:#d1fae5;border-radius:8px;padding:15px;margin:20px 0">
        <p style="margin:0;font-size:14px">
            <strong>ID Lote:</strong> {batch_id}<br>
            <strong>Total procesadas:</strong> {total}<br>
            <strong>Exitosas:</strong> {exitosas}<br>
            <strong>Fallidas:</strong> {total - exitosas}
        </p>
    </div>
    """
    await enviar_email(destinatario, asunto, _build_html_base(asunto, contenido))


async def enviar_resumen_semanal(destinatario: str, metricas: dict):
    cfg = get_settings()
    if not cfg.alertas_email:
        return
    
    asunto = "📊 Resumen semanal - Sistema de Glosas HUS"
    ahora = datetime.now()
    contenido = f"""
    <p style="color:#374151;font-size:14px;line-height:1.6">
        Resumen de la semana del {ahora.strftime('%d de %B de %Y')}
    </p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:20px 0">
        <div style="background:#eff6ff;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#1e40af">{metricas.get('total_glosas', 0)}</div>
            <div style="font-size:12px;color:#6b7280">Glosas procesadas</div>
        </div>
        <div style="background:#f0fdf4;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#15803d">${metricas.get('valor_recuperado', 0):,.0f}</div>
            <div style="font-size:12px;color:#6b7280">Valor recuperado</div>
        </div>
        <div style="background:#fef3c7;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#b45309">{metricas.get('tasa_exito', 0)}%</div>
            <div style="font-size:12px;color:#6b7280">Tasa de éxito</div>
        </div>
        <div style="background:#fce7f3;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#9d174d">{metricas.get('glosas_pendientes', 0)}</div>
            <div style="font-size:12px;color:#6b7280">Pendientes</div>
        </div>
    </div>
    """
    await enviar_email(destinatario, asunto, _build_html_base(asunto, contenido))
