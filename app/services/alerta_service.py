"""
Servicio de alertas por correo electrónico para el Motor de Glosas HUS.
Envía notificaciones cuando las glosas están próximas a vencer.
"""
import os
from datetime import datetime
from typing import Optional, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.logging_utils import logger

try:
    import smtplib
    SMTP_DISPONIBLE = True
except ImportError:
    SMTP_DISPONIBLE = False


class EmailService:
    """Servicio de envío de correos electrónicos."""
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM", "noreply@hus.gov.co")
        
        if not SMTP_DISPONIBLE:
            logger.warning("smtplib no disponible. Correos no se enviarán.")
    
    def enviar_alerta_glosas(self, glosas: list, dias_limite: int = 5) -> tuple[bool, str]:
        """
        Envía correo con glosas próximas a vencer.
        
        Args:
            glosas: Lista de glosas con dias_restantes <= dias_limite
            dias_limite: Umbral de días para alertar
        
        Returns:
            tuple: (exito, mensaje)
        """
        if not SMTP_DISPONIBLE:
            return False, "smtplib no disponible"
        
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP no configurado. Configure SMTP_USER y SMTP_PASSWORD")
            return False, "SMTP no configurado"
        
        if not glosas:
            return True, "No hay glosas para alertar"
        
        destinatarios = self._obtener_destinatarios()
        if not destinatarios:
            return False, "No hay destinatarios configurados"
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[ALERTA] Glosas próximas a vencer - {len(glosas)} casos"
            msg["From"] = self.from_email
            msg["To"] = ", ".join(destinatarios)
            
            html_content = self._generar_html_alerta(glosas, dias_limite)
            text_content = self._generar_texto_alerta(glosas, dias_limite)
            
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, destinatarios, msg.as_string())
            
            logger.info(f"Alerta enviada a {len(destinatarios)} destinatarios")
            return True, f"Alerta enviada a {len(destinatarios)} destinatarios"
            
        except Exception as e:
            logger.error(f"Error enviando correo: {e}")
            return False, f"Error: {str(e)}"
    
    def _generar_html_alerta(self, glosas: list, dias_limite: int) -> str:
        """Genera contenido HTML para el correo."""
        filas = ""
        for g in sorted(glosas, key=lambda x: x.dias_restantes or 999):
            color_urgencia = "#ef4444" if (g.dias_restantes or 0) <= 2 else "#f59e0b"
            filas += f"""
            <tr style="border-bottom: 1px solid #e5e7eb;">
                <td style="padding: 12px;">{g.id}</td>
                <td style="padding: 12px;">{g.eps}</td>
                <td style="padding: 12px;">{g.codigo_glosa or 'N/A'}</td>
                <td style="padding: 12px; text-align: right;">${(g.valor_objetado or 0):,.0f}</td>
                <td style="padding: 12px; text-align: center; color: {color_urgencia}; font-weight: bold;">
                    {g.dias_restantes or 0} días
                </td>
                <td style="padding: 12px;">{g.estado}</td>
            </tr>"""
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background: #1e40af; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #3b82f6; color: white; padding: 12px; text-align: left; }}
                .footer {{ background: #f1f5f9; padding: 15px; text-align: center; font-size: 12px; color: #64748b; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>ESE Hospital Universitario de Santander</h1>
                <p>Sistema de Gestión de Glosas - ALERTA</p>
            </div>
            <div class="content">
                <h2>Glosas próximas a vencer ({dias_limite} días)</h2>
                <p>Se encontraron <strong>{len(glosas)}</strong> glosas que requieren atención inmediata:</p>
                
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>EPS</th>
                            <th>Código</th>
                            <th>Valor</th>
                            <th>Días Rest.</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filas}
                    </tbody>
                </table>
                
                <p style="margin-top: 20px;">
                    <a href="#" style="background: #1e40af; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                        Ver en el sistema
                    </a>
                </p>
            </div>
            <div class="footer">
                <p>Este es un mensaje automático del Motor de Glosas HUS.</p>
                <p>No responda a este correo.</p>
            </div>
        </body>
        </html>
        """
    
    def _generar_texto_alerta(self, glosas: list, dias_limite: int) -> str:
        """Genera contenido de texto plano para el correo."""
        linea = "=" * 70
        texto = f"""
{linea}
ESE HOSPITAL UNIVERSITARIO DE SANTANDER
SISTEMA DE GESTIÓN DE GLOSAS - ALERTA
{linea}

Glosas próximas a vencer ({dias_limite} días): {len(glosas)} casos

"""
        for i, g in enumerate(sorted(glosas, key=lambda x: x.dias_restantes or 999), 1):
            texto += f"""
{i}. ID: {g.id} | EPS: {g.eps}
   Código: {g.codigo_glosa or 'N/A'} | Valor: ${(g.valor_objetado or 0):,.0f}
   Días restantes: {g.dias_restantes or 0} | Estado: {g.estado}
"""
        
        texto += f"""
{linea}
Este es un mensaje automático. No responda a este correo.
Motor de Glosas HUS - {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        return texto.strip()
    
    def _obtener_destinatarios(self) -> List[str]:
        """Obtiene la lista de destinatarios desde configuración."""
        destinatarios_str = os.getenv("ALERTAS_EMAIL", "")
        if not destinatarios_str:
            logger.warning("ALERTAS_EMAIL no configurado en variables de entorno")
            return []
        return [d.strip() for d in destinatarios_str.split(",") if d.strip()]


class AlertaService:
    """Servicio de generación y envío de alertas."""
    
    def __init__(self):
        self.email_service = EmailService()
        self.dias_umbral_default = 5
    
    def verificar_y_enviar_alertas(
        self,
        db,
        dias_limite: Optional[int] = None,
        forzar: bool = False,
    ) -> tuple[bool, str]:
        """
        Verifica glosas próximas a vencer y envía alertas.
        
        Args:
            db: Sesión de base de datos
            dias_limite: Días umbral para alertar (default: 5)
            forzar: Si True, envía aunque no haya nuevas alertas
        
        Returns:
            tuple: (exito, mensaje_detallado)
        """
        from app.repositories.glosa_repository import GlosaRepository
        
        dias = dias_limite or self.dias_umbral_default
        repo = GlosaRepository(db)
        
        alertas = repo.alertas_proximas(dias_limite=dias)
        
        if not alertas and not forzar:
            logger.info(f"No hay glosas para alertar (umbral: {dias} días)")
            return True, "No hay glosas para alertar"
        
        return self.email_service.enviar_alerta_glosas(alertas, dias)
