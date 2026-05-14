import smtplib
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Sequence, Tuple

from app.core.config import get_settings
from app.core.logging_utils import logger

_executor = ThreadPoolExecutor(max_workers=2)

# Tipo: lista de (nombre_archivo, bytes, mime_subtype). mime_subtype
# es opcional — para .xlsx usar
# "vnd.openxmlformats-officedocument.spreadsheetml.sheet".
Adjunto = Tuple[str, bytes, Optional[str]]


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


def _enviar_sync(
    destinatario: str,
    asunto: str,
    html: str,
    adjuntos: Optional[Sequence[Adjunto]] = None,
) -> bool:
    cfg = get_settings()
    if not cfg.smtp_user or not cfg.smtp_password:
        logger.warning("Email no configurado: SMTP_USER o SMTP_PASSWORD vacíos")
        return False

    try:
        # Si hay adjuntos usamos multipart/mixed con el cuerpo HTML
        # anidado como multipart/alternative; sin adjuntos basta el
        # alternative directo (más simple para clientes antiguos).
        if adjuntos:
            msg = MIMEMultipart("mixed")
            cuerpo = MIMEMultipart("alternative")
            cuerpo.attach(MIMEText(html, "html"))
            msg.attach(cuerpo)
            for nombre, contenido, subtype in adjuntos:
                if subtype:
                    parte = MIMEApplication(contenido, _subtype=subtype)
                else:
                    parte = MIMEApplication(contenido)
                parte.add_header(
                    "Content-Disposition", "attachment", filename=nombre,
                )
                msg.attach(parte)
        else:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(html, "html"))

        msg["Subject"] = asunto
        msg["From"] = cfg.smtp_user
        msg["To"] = destinatario

        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.send_message(msg)

        logger.info(
            f"Email enviado a {destinatario}: {asunto}"
            + (f" (con {len(adjuntos)} adjunto/s)" if adjuntos else "")
        )
        return True
    except Exception as e:
        logger.error(f"Error enviando email a {destinatario}: {e}")
        return False


async def enviar_email(
    destinatario: str,
    asunto: str,
    html: str,
    adjuntos: Optional[Sequence[Adjunto]] = None,
) -> bool:
    loop = __import__("asyncio").get_event_loop()
    return await loop.run_in_executor(
        _executor, _enviar_sync, destinatario, asunto, html, adjuntos,
    )


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


def _buscar_emails_por_gestor(gestores_nombres: list, db=None) -> list:
    """Busca correos de UsuarioRecord cuyo nombre coincida con alguno de los
    gestores dados (comparación case-insensitive, fuzzy por contains).

    Sirve para que al importar recepción con gestores "EQUIPO ASEGURADORAS",
    "IRMA RIOS", etc., se envíe el correo a TODOS los usuarios con ese
    nombre (ej. los 4 correos del equipo aseguradoras).
    """
    if db is None:
        return []
    try:
        from app.models.db import UsuarioRecord
        usuarios = db.query(UsuarioRecord).filter(UsuarioRecord.activo == 1).all()
        emails = set()
        gestores_norm = [g.strip().upper() for g in gestores_nombres if g and g.strip()]
        for u in usuarios:
            if not u.nombre or not u.email:
                continue
            nombre_upper = u.nombre.strip().upper()
            for g in gestores_norm:
                # Match exacto O contains (para manejar prefijos tipo
                # "A_A_A_A (EQUIPO ASEGURADORAS)" vs "EQUIPO ASEGURADORAS")
                if nombre_upper == g or g in nombre_upper or nombre_upper in g:
                    emails.add(u.email.strip().lower())
                    break
        return sorted(emails)
    except Exception as e:
        logger.warning(f"Error buscando usuarios por gestor: {e}")
        return []


async def enviar_resumen_importacion_recepcion(resumen: dict, db=None) -> int:
    """Envía un correo broadcast a todos los gestores listando las glosas importadas.

    Destinatarios = ALERTAS_EMAIL (broadcast global) UNION correos de
    usuarios cuyo nombre matchee con los gestores del resumen. Así, si
    se importa una glosa con gestor "EQUIPO ASEGURADORAS", los 4 usuarios
    del sistema con ese nombre reciben el correo aunque no estén en
    ALERTAS_EMAIL.

    Retorna el número de destinatarios a los que se envió correctamente.
    """
    cfg = get_settings()
    destinatarios_base = []
    if cfg.alertas_email:
        destinatarios_base = [e.strip() for e in cfg.alertas_email.split(",") if e.strip()]

    # Añadir correos de usuarios cuyo nombre matchea con los gestores del resumen
    por_gestor_dict = resumen.get("por_gestor", {}) or {}
    gestores = list(por_gestor_dict.keys())
    emails_gestores = _buscar_emails_por_gestor(gestores, db=db) if db is not None else []

    # Union sin duplicados
    destinatarios = sorted({*(e.lower() for e in destinatarios_base), *emails_gestores})
    if not destinatarios:
        logger.warning("Sin destinatarios: ni ALERTAS_EMAIL ni usuarios-gestor matcheados")
        return 0
    logger.info(
        f"Destinatarios importación recepción: {len(destinatarios)} "
        f"(ALERTAS_EMAIL={len(destinatarios_base)}, por-gestor={len(emails_gestores)})"
    )

    total = resumen.get("total", 0)
    creadas = resumen.get("creadas", 0)
    actualizadas = resumen.get("actualizadas", 0)
    ratificadas = resumen.get("ratificadas", 0)
    extemporaneas = resumen.get("extemporaneas", 0)
    semaforo = resumen.get("semaforo", {})
    por_gestor = resumen.get("por_gestor", {})

    # Tabla de semáforo
    sem_html = f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0">
        <div style="background:#16a34a;color:white;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{semaforo.get('VERDE', 0)}</div>
            <div style="font-size:11px">🟢 VERDE (>10d)</div>
        </div>
        <div style="background:#eab308;color:white;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{semaforo.get('AMARILLO', 0)}</div>
            <div style="font-size:11px">🟡 AMARILLO (5-10d)</div>
        </div>
        <div style="background:#dc2626;color:white;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{semaforo.get('ROJO', 0)}</div>
            <div style="font-size:11px">🔴 ROJO (&lt;5d)</div>
        </div>
        <div style="background:#111827;color:white;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{semaforo.get('NEGRO', 0)}</div>
            <div style="font-size:11px">⚫ VENCIDAS</div>
        </div>
    </div>
    """

    # Tabla por gestor
    filas_gestor = []
    for gestor, glosas in sorted(por_gestor.items()):
        lista_facturas = "".join(
            f"<li>{g['factura']} — {g['eps']} — ${g['valor']:,.0f} — vence {g['vence']}"
            f" <span style='padding:2px 6px;border-radius:4px;font-size:10px;background:{_color_semaforo(g['semaforo'])};color:white'>{g['semaforo']}</span></li>"
            for g in glosas[:15]
        )
        extra = f"<li><i>...y {len(glosas) - 15} más</i></li>" if len(glosas) > 15 else ""
        filas_gestor.append(f"""
        <div style="margin:15px 0;padding:12px;background:#f9fafb;border-radius:8px;border-left:3px solid #3b82f6">
            <div style="font-weight:bold;color:#1e40af;margin-bottom:8px">
                👤 {gestor} <span style="color:#6b7280;font-weight:normal">({len(glosas)} glosa{'s' if len(glosas) != 1 else ''})</span>
            </div>
            <ul style="margin:0;padding-left:20px;font-size:12px;color:#374151">
                {lista_facturas}{extra}
            </ul>
        </div>
        """)

    asunto = f"📥 Motor Glosas HUS — {total} glosas importadas desde recepción"
    contenido = f"""
    <p style="color:#374151;font-size:14px;line-height:1.6">
        Se importó un nuevo archivo de recepción de glosas. A continuación el resumen:
    </p>
    <div style="background:#eff6ff;border-radius:8px;padding:15px;margin:15px 0">
        <div style="display:flex;justify-content:space-around;text-align:center">
            <div>
                <div style="font-size:24px;font-weight:bold;color:#1e40af">{total}</div>
                <div style="font-size:11px;color:#6b7280">TOTAL</div>
            </div>
            <div>
                <div style="font-size:24px;font-weight:bold;color:#15803d">{creadas}</div>
                <div style="font-size:11px;color:#6b7280">NUEVAS</div>
            </div>
            <div>
                <div style="font-size:24px;font-weight:bold;color:#2563eb">{actualizadas}</div>
                <div style="font-size:11px;color:#6b7280">ACTUALIZADAS</div>
            </div>
            <div>
                <div style="font-size:24px;font-weight:bold;color:#7c3aed">{ratificadas}</div>
                <div style="font-size:11px;color:#6b7280">RATIFICADAS</div>
            </div>
            <div>
                <div style="font-size:24px;font-weight:bold;color:#dc2626">{extemporaneas}</div>
                <div style="font-size:11px;color:#6b7280">EXTEMPORÁNEAS</div>
            </div>
        </div>
    </div>

    <h3 style="color:#111827;font-size:16px;margin:25px 0 10px">Semáforo de vencimientos</h3>
    {sem_html}

    <h3 style="color:#111827;font-size:16px;margin:25px 0 10px">Asignaciones por gestor</h3>
    {''.join(filas_gestor) or '<p style="color:#6b7280">No hay asignaciones.</p>'}

    <p style="margin-top:30px;padding:15px;background:#fef3c7;border-radius:8px;font-size:13px;color:#92400e">
        <b>Acción requerida:</b> ingresa al sistema para revisar las glosas asignadas y responderlas antes de su vencimiento.<br>
        🔗 <a href="https://motor-glosas-hus.onrender.com/" style="color:#1e40af">Abrir Motor Glosas HUS</a>
    </p>
    """

    html = _build_html_base(asunto, contenido)
    exitos = 0
    for destinatario in destinatarios:
        if await enviar_email(destinatario, asunto, html):
            exitos += 1
    logger.info(f"Resumen de importación enviado a {exitos}/{len(destinatarios)} destinatarios")
    return exitos


def _color_semaforo(sem: str) -> str:
    return {
        "VERDE": "#16a34a",
        "AMARILLO": "#eab308",
        "ROJO": "#dc2626",
        "NEGRO": "#111827",
    }.get(sem, "#6b7280")


async def enviar_alertas_vencimiento_masivo(db) -> dict:
    """Envía correo broadcast con glosas próximas a vencer o vencidas.

    Contenido:
    - Glosas ROJO (<5 días)
    - Glosas VENCIDAS (0 o negativo)
    - Agrupadas por gestor.

    Retorna resumen {destinatarios, correos_enviados, glosas_alertadas}.
    """
    cfg = get_settings()
    if not cfg.alertas_email:
        return {"destinatarios": 0, "correos_enviados": 0, "glosas_alertadas": 0, "error": "ALERTAS_EMAIL vacío"}

    destinatarios = [e.strip() for e in cfg.alertas_email.split(",") if e.strip()]
    if not destinatarios:
        return {"destinatarios": 0, "correos_enviados": 0, "glosas_alertadas": 0}

    from app.models.db import GlosaRecord
    rojas = db.query(GlosaRecord).filter(
        GlosaRecord.prioridad == "ROJO",
        GlosaRecord.estado.notin_(["LEVANTADA", "ACEPTADA", "CONCILIADA"]),
    ).all()
    negras = db.query(GlosaRecord).filter(
        GlosaRecord.prioridad == "NEGRO",
        GlosaRecord.estado.notin_(["LEVANTADA", "ACEPTADA", "CONCILIADA"]),
    ).all()

    if not rojas and not negras:
        return {"destinatarios": len(destinatarios), "correos_enviados": 0, "glosas_alertadas": 0, "mensaje": "Sin glosas críticas"}

    def _filas(lista, color_hex):
        if not lista:
            return ""
        filas = []
        for g in lista[:40]:
            dias = g.dias_restantes if g.dias_restantes else 0
            filas.append(
                f'<tr><td style="padding:6px 10px;border-bottom:1px solid #e5e7eb">{g.gestor_nombre or "—"}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb">{g.eps or "—"}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:11px">{g.factura or "—"}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:bold">$ {(g.valor_objetado or 0):,.0f}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:center;color:{color_hex};font-weight:bold">{dias} días</td></tr>'
            )
        if len(lista) > 40:
            filas.append(f'<tr><td colspan="5" style="padding:6px 10px;color:#6b7280;font-style:italic">...y {len(lista) - 40} glosas más</td></tr>')
        return "".join(filas)

    rojas_html = _filas(rojas, "#b91c1c")
    negras_html = _filas(negras, "#0f172a")

    total = len(rojas) + len(negras)
    asunto = f"⚠ Motor Glosas HUS — {total} glosas críticas ({len(rojas)} rojas, {len(negras)} vencidas)"

    contenido = f"""
    <p style="color:#374151;font-size:14px;line-height:1.6">
        Alerta automática: hay <strong>{total} glosas</strong> en estado crítico.
        Por favor revísalas y responde cuanto antes para evitar aceptación tácita.
    </p>
    """

    if negras:
        contenido += f"""
        <h3 style="color:#0f172a;margin-top:20px;font-size:16px">⚫ Glosas VENCIDAS ({len(negras)})</h3>
        <p style="color:#991b1b;font-size:12px">Requieren acción inmediata — pueden derivar en aceptación tácita.</p>
        <table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb">
            <thead><tr style="background:#0f172a;color:#fff">
                <th style="padding:8px;text-align:left">Gestor</th>
                <th style="padding:8px;text-align:left">EPS</th>
                <th style="padding:8px;text-align:left">Factura</th>
                <th style="padding:8px;text-align:right">Valor</th>
                <th style="padding:8px;text-align:center">Días</th>
            </tr></thead>
            <tbody>{negras_html}</tbody>
        </table>
        """

    if rojas:
        contenido += f"""
        <h3 style="color:#b91c1c;margin-top:25px;font-size:16px">🔴 Glosas en ROJO — menos de 5 días ({len(rojas)})</h3>
        <table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb">
            <thead><tr style="background:#b91c1c;color:#fff">
                <th style="padding:8px;text-align:left">Gestor</th>
                <th style="padding:8px;text-align:left">EPS</th>
                <th style="padding:8px;text-align:left">Factura</th>
                <th style="padding:8px;text-align:right">Valor</th>
                <th style="padding:8px;text-align:center">Días</th>
            </tr></thead>
            <tbody>{rojas_html}</tbody>
        </table>
        """

    contenido += """
    <p style="margin-top:30px;padding:15px;background:#fef3c7;border-radius:8px;font-size:13px;color:#92400e">
        <b>Acción requerida:</b> ingresa al sistema, revisa las glosas asignadas a ti y responde.<br>
        🔗 <a href="https://motor-glosas-hus.onrender.com/" style="color:#1e40af">Abrir Motor Glosas HUS</a>
    </p>
    """

    html = _build_html_base(asunto, contenido)
    enviados = 0
    for d in destinatarios:
        if await enviar_email(d, asunto, html):
            enviados += 1

    logger.info(f"Alertas de vencimiento enviadas: {enviados}/{len(destinatarios)} | {total} glosas críticas")
    return {
        "destinatarios": len(destinatarios),
        "correos_enviados": enviados,
        "glosas_alertadas": total,
        "rojas": len(rojas),
        "vencidas": len(negras),
    }


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


_XLSX_MIME_SUBTYPE = (
    "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _mapear_gestor_a_emails(db) -> dict[str, list[str]]:
    """Devuelve {nombre_gestor_upper: [emails]} desde UsuarioRecord
    activos. Sirve para dirigir el Excel-respuesta al gestor concreto.
    """
    if db is None:
        return {}
    try:
        from app.models.db import UsuarioRecord
        usuarios = db.query(UsuarioRecord).filter(UsuarioRecord.activo == 1).all()
        out: dict[str, list[str]] = {}
        for u in usuarios:
            if not u.nombre or not u.email:
                continue
            nombre = u.nombre.strip().upper()
            out.setdefault(nombre, []).append(u.email.strip().lower())
        return out
    except Exception as e:
        logger.warning(f"_mapear_gestor_a_emails falló: {e}")
        return {}


def _emails_para_gestor(
    nombre_gestor: str, mapa_gestor_emails: dict[str, list[str]]
) -> list[str]:
    """Match flexible: igualdad, contains en ambos sentidos."""
    g = (nombre_gestor or "").strip().upper()
    if not g:
        return []
    candidatos: set[str] = set()
    for nombre, emails in mapa_gestor_emails.items():
        if nombre == g or g in nombre or nombre in g:
            candidatos.update(emails)
    return sorted(candidatos)


async def enviar_excel_recepcion_con_respuestas(
    resumen: dict,
    excel_original: bytes,
    glosa_ids: list,
    db,
) -> dict:
    """Envía el Excel original + respuestas IA a cada gestor.

    Cada gestor recibe el archivo completo (todas las filas) con las
    suyas resaltadas en amarillo. Además, ALERTAS_EMAIL recibe una
    copia broadcast sin resaltado para la coordinación.

    Retorna {'destinatarios', 'enviados', 'gestores_atendidos'}.
    """
    cfg = get_settings()
    if not cfg.smtp_user or not cfg.smtp_password:
        logger.warning(
            "Excel-respuesta no enviado: SMTP_USER/SMTP_PASSWORD vacíos"
        )
        return {"destinatarios": 0, "enviados": 0, "gestores_atendidos": 0}

    if not excel_original:
        logger.warning("Excel-respuesta no enviado: archivo original vacío")
        return {"destinatarios": 0, "enviados": 0, "gestores_atendidos": 0}

    # Imports diferidos para evitar ciclo email_service ↔ recepcion_*
    from app.services.recepcion_excel_response import (
        construir_respuestas_por_clave,
        generar_excel_con_respuestas,
    )

    respuestas_por_clave = construir_respuestas_por_clave(db, list(glosa_ids or []))
    if not respuestas_por_clave:
        logger.info(
            "Excel-respuesta: sin glosas auto-procesadas para anotar — "
            "se envía Excel original sin columnas IA."
        )

    por_gestor = resumen.get("por_gestor", {}) or {}
    mapa = _mapear_gestor_a_emails(db)
    total = resumen.get("total", 0)
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo_base = f"glosas_recepcion_{fecha}.xlsx"

    enviados = 0
    destinatarios_unicos: set[str] = set()
    gestores_atendidos = 0

    for nombre_gestor, filas in sorted(por_gestor.items()):
        emails = _emails_para_gestor(nombre_gestor, mapa)
        if not emails:
            logger.info(
                f"Gestor '{nombre_gestor}' sin email asociado — su Excel "
                "no se envía por correo (queda solo en la app)."
            )
            continue
        gestores_atendidos += 1

        try:
            xlsx_bytes = generar_excel_con_respuestas(
                excel_original,
                respuestas_por_clave,
                gestor_destacar=nombre_gestor,
            )
        except Exception as e:
            logger.error(
                f"Excel-respuesta: falló generación para gestor "
                f"'{nombre_gestor}': {e}"
            )
            continue

        n_filas = len(filas)
        n_respondidas = sum(
            1 for f in filas
            if respuestas_por_clave.get((
                (f.get("factura") or "").strip().upper(),
                (f.get("consecutivo_dgh") or "").strip().upper(),
            ), {}).get("estado", "").upper() == "RESPONDIDA"
        )
        n_requieren = sum(
            1 for f in filas
            if respuestas_por_clave.get((
                (f.get("factura") or "").strip().upper(),
                (f.get("consecutivo_dgh") or "").strip().upper(),
            ), {}).get("estado", "").upper() == "REQUIERE_SOPORTES"
        )

        asunto = (
            f"📋 Recepción HUS — {n_filas} glosas para {nombre_gestor} "
            f"(IA respondió {n_respondidas}, manual {n_requieren})"
        )
        contenido = f"""
        <p style="color:#374151;font-size:14px;line-height:1.6">
            Hola <b>{nombre_gestor}</b>, adjuntamos el Excel de recepción del día.
        </p>
        <div style="background:#eff6ff;border-radius:8px;padding:15px;margin:15px 0;border-left:3px solid #2563eb">
            <p style="margin:0 0 8px;font-size:14px;color:#1e40af;font-weight:600">
                🤖 La IA ya procesó tus glosas
            </p>
            <ul style="margin:0;padding-left:20px;font-size:13px;color:#374151;line-height:1.6">
                <li><b>{n_filas}</b> glosas asignadas a ti (resaltadas en amarillo en la columna GESTOR)</li>
                <li><b>{n_respondidas}</b> con respuesta IA lista (estado <span style="background:#dcfce7;padding:1px 6px;border-radius:4px;color:#166534;font-weight:600">RESPONDIDA</span>)</li>
                <li><b>{n_requieren}</b> requieren tu revisión manual + PDFs (estado <span style="background:#fee2e2;padding:1px 6px;border-radius:4px;color:#991b1b;font-weight:600">REQUIERE_SOPORTES</span>)</li>
            </ul>
        </div>
        <p style="color:#374151;font-size:13px;line-height:1.6">
            Abrí el archivo adjunto: las nuevas columnas <b>RESPUESTA IA</b>, <b>ESTADO IA</b> e
            <b>ID GLOSA</b> al final tienen todo lo que la IA generó. Las que dicen
            <i>REQUIERE_SOPORTES</i> son las que necesitan que cargues PDFs y le des
            "Re-analizar" en la app antes de radicar.
        </p>
        <p style="margin-top:25px;padding:15px;background:#fef3c7;border-radius:8px;font-size:13px;color:#92400e">
            🔗 <a href="https://motor-glosas-hus.fly.dev/" style="color:#92400e;font-weight:600">Abrir Motor Glosas HUS</a>
            — revisá los borradores y radicá los que estén OK.
        </p>
        """
        html = _build_html_base(asunto, contenido)
        adjunto: Adjunto = (archivo_base, xlsx_bytes, _XLSX_MIME_SUBTYPE)

        for email in emails:
            destinatarios_unicos.add(email)
            if await enviar_email(email, asunto, html, adjuntos=[adjunto]):
                enviados += 1

    # Copia broadcast a ALERTAS_EMAIL (sin resaltado) — para coordinación.
    if cfg.alertas_email:
        try:
            xlsx_broadcast = generar_excel_con_respuestas(
                excel_original, respuestas_por_clave, gestor_destacar=None,
            )
            asunto_bc = (
                f"📋 Recepción HUS — {total} glosas procesadas por la IA (copia coordinación)"
            )
            contenido_bc = """
            <p style="color:#374151;font-size:14px;line-height:1.6">
                Copia de seguimiento para la coordinación. El Excel adjunto trae el archivo
                de recepción del día con las respuestas IA en las últimas columnas.
            </p>
            <p style="color:#6b7280;font-size:12px">
                Cada gestor recibió su propio correo con su nombre resaltado en amarillo.
            </p>
            """
            html_bc = _build_html_base(asunto_bc, contenido_bc)
            adj_bc: Adjunto = (
                f"glosas_recepcion_{fecha}_coordinacion.xlsx",
                xlsx_broadcast,
                _XLSX_MIME_SUBTYPE,
            )
            for d in (e.strip() for e in cfg.alertas_email.split(",") if e.strip()):
                destinatarios_unicos.add(d.lower())
                if await enviar_email(d, asunto_bc, html_bc, adjuntos=[adj_bc]):
                    enviados += 1
        except Exception as e:
            logger.error(f"Excel-respuesta broadcast coordinación falló: {e}")

    logger.info(
        f"Excel-respuesta: {enviados} correos enviados a "
        f"{len(destinatarios_unicos)} destinatarios "
        f"({gestores_atendidos} gestor/es con email)"
    )
    return {
        "destinatarios": len(destinatarios_unicos),
        "enviados": enviados,
        "gestores_atendidos": gestores_atendidos,
    }
