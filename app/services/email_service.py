import re
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


# Google muestra la contraseña de aplicación en cuatro grupos de cuatro
# —«abcd efgh ijkl mnop»— y uno la pega tal cual, que es lo natural. Los
# espacios son solo para leerla: no son parte de la clave. Algunos servidores
# la aceptan igual y otros la rechazan, y el error que devuelven es el mismo
# «Username and Password not accepted» que sale cuando la clave está de verdad
# equivocada — así que uno se pone a generar claves nuevas sin necesidad.
#
# 20-08-2026. Se quitan los espacios SOLO cuando la clave tiene la forma exacta
# de una contraseña de aplicación de Google (16 letras o números en 4 grupos de
# 4). Cualquier otra clave se manda tal cual: hay servidores de correo donde un
# espacio sí es parte de la contraseña, y tocarla ahí sería romperla.
_APP_PASSWORD_GOOGLE = re.compile(r"^[A-Za-z0-9]{4}(?: [A-Za-z0-9]{4}){3}$")


def clave_para_el_servidor(clave: str) -> str:
    """La contraseña como la espera el servidor de correo."""
    limpia = (clave or "").strip()
    if _APP_PASSWORD_GOOGLE.match(limpia):
        return limpia.replace(" ", "")
    return limpia


def _anotar(destinatario: str, asunto: str, aceptado: bool, error: str = "") -> None:
    """Envoltura a prueba de todo alrededor del registro.

    20-08-2026. `_anotar_envio` ya se protege por dentro, pero eso solo cubre
    los fallos que él conoce. Si algo revienta antes —un import roto, la base
    caída de otra forma—, la excepción subiría y tumbaría un correo que ya
    estaba listo para salir. El registro es secundario: JAMÁS puede costar un
    envío.
    """
    try:
        _anotar_envio(destinatario, asunto, aceptado, error)
    except Exception:  # pragma: no cover - defensivo a propósito
        pass


def _anotar_envio(destinatario: str, asunto: str, aceptado: bool, error: str = "") -> None:
    """Deja constancia del intento en la base (20-08-2026).

    Yesid configuró el correo y preguntó «¿cómo miro eso acá?». Hasta ahora no
    se podía: cada correo salía sin dejar rastro en el portal, y para saber si
    algo se había enviado había que entrar a la bandeja de Gmail de la cuenta
    que envía — justo lo que un auditor no debería tener que hacer.

    Nunca tumba un envío: si el registro falla, el correo ya salió y eso es lo
    que importa.
    """
    try:
        from app.database import SessionLocal
        from app.models.db import EnvioCorreoRecord

        db = SessionLocal()
        try:
            db.add(
                EnvioCorreoRecord(
                    destinatario=(destinatario or "")[:200],
                    asunto=(asunto or "")[:300],
                    contexto=_contexto_de(asunto),
                    aceptado=bool(aceptado),
                    error=(error or "")[:2000] or None,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as e:  # pragma: no cover - el registro es secundario
        logger.debug(f"No se pudo anotar el envío de correo: {e}")


def _contexto_de(asunto: str) -> str:
    """De qué pantalla salió el correo, deducido del asunto."""
    a = (asunto or "").lower()
    if "prueba" in a:
        return "prueba"
    if "recepción" in a or "recepcion" in a:
        return "recepcion"
    if "vence" in a or "vencimiento" in a:
        return "vencimientos"
    if "lote" in a or "batch" in a:
        return "lote"
    return "otro"


def _enviar_sync(
    destinatario: str,
    asunto: str,
    html: str,
    adjuntos: Optional[Sequence[Adjunto]] = None,
) -> bool:
    cfg = get_settings()
    if not cfg.smtp_user or not cfg.smtp_password:
        logger.warning("Email no configurado: SMTP_USER o SMTP_PASSWORD vacíos")
        _anotar(destinatario, asunto, False, "El servidor no tiene correo configurado")
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
                    "Content-Disposition",
                    "attachment",
                    filename=nombre,
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
            server.login(cfg.smtp_user, clave_para_el_servidor(cfg.smtp_password))
            server.send_message(msg)

        logger.info(
            f"Email enviado a {destinatario}: {asunto}"
            + (f" (con {len(adjuntos)} adjunto/s)" if adjuntos else "")
        )
        _anotar(destinatario, asunto, True)
        return True
    except Exception as e:
        logger.error(f"Error enviando email a {destinatario}: {e}")
        _anotar(destinatario, asunto, False, f"{type(e).__name__}: {e}")
        return False


async def enviar_email(
    destinatario: str,
    asunto: str,
    html: str,
    adjuntos: Optional[Sequence[Adjunto]] = None,
) -> bool:
    loop = __import__("asyncio").get_event_loop()
    return await loop.run_in_executor(
        _executor,
        _enviar_sync,
        destinatario,
        asunto,
        html,
        adjuntos,
    )


async def notificar_alerta_vencimiento(
    eps: str, dias_restantes: int, valor: float, destinatario: str
):
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
                # "A_A_A_A (EQUIPO ASEGURADORAS)" vs "EQUIPO ASEGURADORAS").
                #
                # 20-08-2026: el "contains" exige 4 caracteres. Sin ese piso,
                # una celda de gestor con una letra suelta —una «A» por un
                # dedazo en el Excel— le mandaba el correo a 22 de los 24
                # usuarios, porque casi todo nombre contiene una A. Cada quien
                # recibía un plan de trabajo que no era el suyo, y el dueño de
                # verdad podía no aparecer. Una «S» alcanzaba a 17.
                #
                # El match EXACTO sigue valiendo para cualquier longitud: si
                # alguien se llama literalmente así, es esa persona.
                if nombre_upper == g:
                    emails.add(u.email.strip().lower())
                    break
                if len(g) >= 4 and (g in nombre_upper or nombre_upper in g):
                    emails.add(u.email.strip().lower())
                    break
        return sorted(emails)
    except Exception as e:
        logger.warning(f"Error buscando usuarios por gestor: {e}")
        return []


def emails_por_gestor(gestores_nombres: list, db=None) -> dict[str, list[str]]:
    """A qué correo concreto le llega lo de cada gestor. `{}` si no hay BD.

    20-08-2026. `_buscar_emails_por_gestor` devuelve la lista de correos toda
    junta, y con eso el resumen solo podía decir «se enviaron 3 correos». El
    auditor no tenía cómo saber que CAROLINA se quedó por fuera, porque su
    nombre en el Excel no coincide con ningún usuario del portal — que es la
    falla que de verdad ocurre, no que se caiga el SMTP.

    Acá se devuelve el cruce abierto: gestor → correos. El que no cruza queda
    con lista vacía y sale nombrado en pantalla.
    """
    if db is None:
        return {}
    salida: dict[str, list[str]] = {}
    for nombre in gestores_nombres or []:
        if not nombre or not str(nombre).strip():
            continue
        salida[str(nombre)] = _buscar_emails_por_gestor([nombre], db=db)
    return salida


def _hay_glosas_medicas(resumen: dict) -> bool:
    """¿El lote trae glosas de pertinencia o calidad?

    Son las que no se pueden contestar desde cartera sin concepto clínico: el
    plan de trabajo ya las marca con `con_medico`.
    """
    for glosas in (resumen.get("por_gestor") or {}).values():
        for g in glosas or []:
            if (g.get("plan") or {}).get("con_medico"):
                return True
    return False


def _doctoras_nombradas(resumen: dict) -> list[str]:
    """Las médicas que el Excel nombra en las glosas médicas del lote.

    20-08-2026. El archivo del HUS trae una columna PROFESIONAL(MEDICO) que
    dice QUÉ doctora lleva cada glosa —«LAURA DIAZ», «LEIDY SANGUINO»,
    «ZULAY GONZALEZ»—. Con eso, a cada una le llega lo suyo en vez de
    mandarles a las tres el lote entero: quien recibe treinta glosas que no
    son suyas deja de abrir el correo, y ahí se pierden también las que sí.
    """
    nombres: list[str] = []
    for glosas in (resumen.get("por_gestor") or {}).values():
        for g in glosas or []:
            plan = g.get("plan") or {}
            if not plan.get("con_medico"):
                continue
            quien = (plan.get("profesional_medico") or "").strip()
            if quien and quien.upper() not in {n.upper() for n in nombres}:
                nombres.append(quien)
    return nombres


def emails_de_las_doctoras(resumen: dict, db=None) -> tuple[dict[str, str], list[str]]:
    """Resuelve cada doctora nombrada en el lote a su correo.

    Devuelve (`{nombre del Excel: correo}`, `[nombres sin correo]`).

    Se usa el mismo resolvedor que para los gestores, que compara por tokens:
    el Excel escribe «LEIDY SANGUINO» y el portal la tiene como «LEIDY JHOANA
    SANGUINO»; sin comparar por tokens, ese correo no saldría nunca.
    """
    nombres = _doctoras_nombradas(resumen)
    if not nombres or db is None:
        return {}, nombres
    try:
        from app.services.recepcion_service import (
            construir_indice_usuarios,
            resolver_gestor_a_email,
        )

        indice = construir_indice_usuarios(db)
    except Exception as e:  # pragma: no cover - sin índice no se inventa nada
        logger.warning(f"No se pudo construir el índice de usuarios: {e}")
        return {}, nombres

    encontradas: dict[str, str] = {}
    sin_correo: list[str] = []
    for nombre in nombres:
        email, _motivo = resolver_gestor_a_email(nombre, indice)
        if email:
            encontradas[nombre] = email
        else:
            sin_correo.append(nombre)
    return encontradas, sin_correo


def emails_de_medicos_auditores(db=None) -> list[str]:
    """A qué correos llega lo médico. Vacío si nadie los ha señalado.

    20-08-2026 (pedido de Yesid: «que también les llegue al correo de las
    doctoras»). Dos maneras de decir quiénes son, y sirve cualquiera:

      · `MEDICOS_AUDITORES_EMAIL` en el .env, separados por coma;
      · el campo «equipo» del usuario, con algo que diga MEDIC.

    A propósito NO se deduce del rol ni del correo: que alguien sea
    SUPER_ADMIN, o que su correo empiece por «auditor», no lo vuelve médico.
    Mandarle historia clínica a quien no es del área por una corazonada del
    sistema sería peor que no mandarla.
    """
    correos: set[str] = set()
    try:
        crudo = get_settings().medicos_auditores_email or ""
        correos.update(e.strip().lower() for e in crudo.split(",") if e.strip())
    except Exception:  # pragma: no cover - una config rota no tumba el envío
        pass

    if db is not None:
        try:
            from app.models.db import UsuarioRecord

            for u in db.query(UsuarioRecord).filter(UsuarioRecord.activo == 1).all():
                if u.email and "MEDIC" in (u.equipo or "").upper():
                    correos.add(u.email.strip().lower())
        except Exception as e:  # pragma: no cover
            logger.warning(f"No se pudo leer el equipo de los usuarios: {e}")
    return sorted(correos)


_COLOR_URGENCIA = {
    "VENCIDA": "#111827",
    "HOY": "#b91c1c",
    "URGENTE": "#dc2626",
    "PRONTO": "#d97706",
    "NORMAL": "#16a34a",
}


def _tarjeta_de_glosa(g: dict) -> str:
    """Una glosa con su plan de trabajo, no un renglón suelto."""
    plan = g.get("plan") or {}
    urgencia = plan.get("urgencia", "NORMAL")
    color = _COLOR_URGENCIA.get(urgencia, "#6b7280")
    try:
        valor = f"${float(g.get('valor') or 0):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        valor = "$0"

    avisos = "".join(
        f'<div style="background:#fffbeb;border-left:3px solid #d97706;padding:6px 9px;'
        f'margin-top:5px;font-size:11.5px;color:#7c2d12;line-height:1.5">⚠ {a}</div>'
        for a in (plan.get("avisos") or [])
    )

    medico = ""
    if plan.get("con_medico"):
        medico = (
            '<div style="background:#eef2ff;border-left:3px solid #4f46e5;padding:6px 9px;'
            'margin-top:5px;font-size:11.5px;color:#3730a3;line-height:1.5">'
            f"🩺 {plan.get('ruta', '')}</div>"
        )

    texto_listo = ""
    if plan.get("texto_listo"):
        texto_listo = (
            '<details style="margin-top:6px"><summary style="cursor:pointer;font-size:11.5px;'
            'color:#5b21b6;font-weight:600">📋 Texto de la ratificada — listo para copiar'
            '</summary><div style="background:#faf5ff;border:1px solid #d8b4fe;border-radius:6px;'
            "padding:9px;margin-top:5px;font-size:11px;color:#4c1d95;line-height:1.6;"
            f'white-space:pre-wrap">{plan["texto_listo"]}</div></details>'
        )

    return f"""
    <div style="border:1px solid #e5e7eb;border-left:4px solid {color};border-radius:8px;
                padding:10px 12px;margin:9px 0;background:white">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px">
        <div style="font-weight:700;color:#111827;font-size:13px">{g.get("factura", "")}</div>
        <div><span style="background:{color};color:white;border-radius:4px;padding:2px 7px;
             font-size:10px;font-weight:700">{urgencia}</span></div>
      </div>
      <div style="color:#4b5563;font-size:12px;margin-top:2px">{g.get("eps", "")}</div>
      <div style="color:#111827;font-size:12px;margin-top:3px">
        <b>{valor}</b> · vence {g.get("vence", "")}
        {"· causal <b>" + g["causal"] + "</b>" if g.get("causal") else ""}
      </div>
      <div style="color:#1e40af;font-size:11.5px;margin-top:5px;font-weight:600">
        {plan.get("titular", "")}</div>
      <div style="background:#f0fdf4;border-left:3px solid #16a34a;padding:6px 9px;margin-top:5px;
                  font-size:11.5px;color:#14532d;line-height:1.5">
        ✔ <b>Qué responder:</b> {plan.get("respuesta_sugerida", "")}</div>
      {medico}{avisos}{texto_listo}
    </div>"""


def _bloque_del_gestor(gestor: str, glosas: list) -> str:
    """Las glosas de un gestor, ordenadas por lo que no puede esperar."""
    ordenadas = sorted(
        glosas,
        key=lambda g: (
            (g.get("plan") or {}).get("prioridad", 3),
            -float((g.get("valor") or 0) if isinstance(g.get("valor"), (int, float)) else 0),
        ),
    )
    urgentes = sum(1 for g in ordenadas if (g.get("plan") or {}).get("prioridad", 3) <= 1)
    medicas = sum(1 for g in ordenadas if (g.get("plan") or {}).get("con_medico"))

    # «Prioritarias», no «para hoy»: la prioridad sube por extemporaneidad,
    # por ratificación o por monto, no solo porque venza pronto. Decir «para
    # hoy» sobre una glosa etiquetada NORMAL se contradice en la misma línea.
    resumen_linea = f"{len(ordenadas)} glosa{'s' if len(ordenadas) != 1 else ''}"
    if urgentes:
        resumen_linea += f" · <b style='color:#b91c1c'>{urgentes} de atención prioritaria</b>"
    if medicas:
        resumen_linea += f" · {medicas} con médico auditor"

    tarjetas = "".join(_tarjeta_de_glosa(g) for g in ordenadas[:20])
    extra = (
        f'<div style="font-size:11.5px;color:#6b7280;padding:6px">…y {len(ordenadas) - 20} '
        "más. Están todas en el portal, en «Mis glosas».</div>"
        if len(ordenadas) > 20
        else ""
    )
    return f"""
    <div style="margin:18px 0;padding:12px;background:#f9fafb;border-radius:10px;
                border-left:4px solid #3b82f6">
      <div style="font-weight:bold;color:#1e40af;margin-bottom:4px;font-size:14px">👤 {gestor}</div>
      <div style="color:#6b7280;font-size:12px;margin-bottom:8px">{resumen_linea}</div>
      <div style="color:#6b7280;font-size:11px;margin-bottom:8px">
        Van en orden: lo de arriba es lo que no puede esperar.</div>
      {tarjetas}{extra}
    </div>"""


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

    # Las médicas auditoras entran SOLO si el lote trae glosas médicas: si no,
    # se les llenaría el buzón de tarifas y facturación que no les competen, y
    # terminarían ignorando también las que sí.
    hay_medicas = _hay_glosas_medicas(resumen)
    # A cada doctora lo suyo: el Excel dice quién lleva cada glosa médica.
    doctoras, doctoras_sin_correo = (
        emails_de_las_doctoras(resumen, db=db) if hay_medicas else ({}, [])
    )
    emails_medicos = sorted(set(doctoras.values()))
    if hay_medicas and not emails_medicos:
        # Nadie nombrado en el Excel, o ninguna resolvió: se cae a la lista
        # del servidor para que las glosas médicas no queden sin avisar.
        emails_medicos = emails_de_medicos_auditores(db=db)

    # Union sin duplicados
    destinatarios = sorted(
        {*(e.lower() for e in destinatarios_base), *emails_gestores, *emails_medicos}
    )
    if not destinatarios:
        logger.warning("Sin destinatarios: ni ALERTAS_EMAIL ni usuarios-gestor matcheados")
        # Este es el peor caso y el más silencioso: NADIE recibió nada. Se
        # deja escrito en el resumen para que salga en pantalla, en vez de un
        # «0 correos» que se lee como si no hubiera nada que enviar.
        resumen["correo"] = {
            "smtp_configurado": bool(cfg.smtp_user and cfg.smtp_password),
            "enviados": 0,
            "intentados": 0,
            "destinatarios": [],
            "por_gestor": emails_por_gestor(gestores, db=db),
            "gestores_sin_correo": sorted(g for g in gestores if g),
            "difusion_general": sorted(destinatarios_base),
        }
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
            <div style="font-size:22px;font-weight:bold">{semaforo.get("VERDE", 0)}</div>
            <div style="font-size:11px">🟢 VERDE (>10d)</div>
        </div>
        <div style="background:#eab308;color:white;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{semaforo.get("AMARILLO", 0)}</div>
            <div style="font-size:11px">🟡 AMARILLO (5-10d)</div>
        </div>
        <div style="background:#dc2626;color:white;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{semaforo.get("ROJO", 0)}</div>
            <div style="font-size:11px">🔴 ROJO (&lt;5d)</div>
        </div>
        <div style="background:#111827;color:white;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:22px;font-weight:bold">{semaforo.get("NEGRO", 0)}</div>
            <div style="font-size:11px">⚫ VENCIDAS</div>
        </div>
    </div>
    """

    # Tabla por gestor
    #
    # 20-08-2026. Yesid: «está muy plana, no explica muy bien». Antes cada
    # glosa era un renglón con factura, EPS, valor y vencimiento — el gestor
    # abría el correo y seguía sin saber por dónde empezar ni qué responder.
    # Ahora cada una trae su plan: por qué es urgente, cómo se trabaja, qué se
    # responde, y los avisos que pueden costar plata. Y van ORDENADAS: primero
    # lo que no puede esperar.
    filas_gestor = [_bloque_del_gestor(g, gs) for g, gs in sorted(por_gestor.items())]

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
    {"".join(filas_gestor) or '<p style="color:#6b7280">No hay asignaciones.</p>'}

    <p style="margin-top:30px;padding:15px;background:#fef3c7;border-radius:8px;font-size:13px;color:#92400e">
        <b>Acción requerida:</b> ingresa al sistema para revisar las glosas asignadas y responderlas antes de su vencimiento.<br>
        🔗 <a href="{get_settings().app_base_url}" style="color:#1e40af">Abrir Motor Glosas HUS</a>
    </p>
    """

    html = _build_html_base(asunto, contenido)
    exitos = 0
    # 20-08-2026: se anota QUÉ pasó con cada correo, uno por uno. Antes solo
    # se devolvía el total, y un «3 de 5» no dice cuáles dos fallaron.
    detalle: list[dict] = []
    for destinatario in destinatarios:
        ok = await enviar_email(destinatario, asunto, html)
        if ok:
            exitos += 1
        detalle.append({"email": destinatario, "ok": bool(ok)})
    logger.info(f"Resumen de importación enviado a {exitos}/{len(destinatarios)} destinatarios")

    cruce = emails_por_gestor(gestores, db=db)
    resumen["correo"] = {
        "smtp_configurado": bool(cfg.smtp_user and cfg.smtp_password),
        "enviados": exitos,
        "intentados": len(destinatarios),
        "destinatarios": detalle,
        "por_gestor": cruce,
        # Los que el motor NO sabe a quién mandarle: su nombre en el Excel no
        # coincide con ningún usuario activo del portal.
        "gestores_sin_correo": sorted(g for g, correos in cruce.items() if not correos),
        "difusion_general": sorted(destinatarios_base),
        "hay_glosas_medicas": hay_medicas,
        "medicos_auditores": emails_medicos,
        "doctoras": doctoras,
        "doctoras_sin_correo": doctoras_sin_correo,
    }
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
        return {
            "destinatarios": 0,
            "correos_enviados": 0,
            "glosas_alertadas": 0,
            "error": "ALERTAS_EMAIL vacío",
        }

    destinatarios = [e.strip() for e in cfg.alertas_email.split(",") if e.strip()]
    if not destinatarios:
        return {"destinatarios": 0, "correos_enviados": 0, "glosas_alertadas": 0}

    from app.models.db import GlosaRecord

    rojas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.prioridad == "ROJO",
            GlosaRecord.estado.notin_(["LEVANTADA", "ACEPTADA", "CONCILIADA"]),
        )
        .all()
    )
    negras = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.prioridad == "NEGRO",
            GlosaRecord.estado.notin_(["LEVANTADA", "ACEPTADA", "CONCILIADA"]),
        )
        .all()
    )

    if not rojas and not negras:
        return {
            "destinatarios": len(destinatarios),
            "correos_enviados": 0,
            "glosas_alertadas": 0,
            "mensaje": "Sin glosas críticas",
        }

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
            filas.append(
                f'<tr><td colspan="5" style="padding:6px 10px;color:#6b7280;font-style:italic">...y {len(lista) - 40} glosas más</td></tr>'
            )
        return "".join(filas)

    rojas_html = _filas(rojas, "#b91c1c")
    negras_html = _filas(negras, "#0f172a")

    total = len(rojas) + len(negras)
    asunto = (
        f"⚠ Motor Glosas HUS — {total} glosas críticas ({len(rojas)} rojas, {len(negras)} vencidas)"
    )

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
        🔗 <a href="{get_settings().app_base_url}" style="color:#1e40af">Abrir Motor Glosas HUS</a>
    </p>
    """

    html = _build_html_base(asunto, contenido)
    enviados = 0
    for d in destinatarios:
        if await enviar_email(d, asunto, html):
            enviados += 1

    logger.info(
        f"Alertas de vencimiento enviadas: {enviados}/{len(destinatarios)} | {total} glosas críticas"
    )
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
        Resumen de la semana del {ahora.strftime("%d de %B de %Y")}
    </p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:20px 0">
        <div style="background:#eff6ff;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#1e40af">{metricas.get("total_glosas", 0)}</div>
            <div style="font-size:12px;color:#6b7280">Glosas procesadas</div>
        </div>
        <div style="background:#f0fdf4;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#15803d">${metricas.get("valor_recuperado", 0):,.0f}</div>
            <div style="font-size:12px;color:#6b7280">Valor recuperado</div>
        </div>
        <div style="background:#fef3c7;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#b45309">{metricas.get("tasa_exito", 0)}%</div>
            <div style="font-size:12px;color:#6b7280">Tasa de éxito</div>
        </div>
        <div style="background:#fce7f3;border-radius:8px;padding:15px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#9d174d">{metricas.get("glosas_pendientes", 0)}</div>
            <div style="font-size:12px;color:#6b7280">Pendientes</div>
        </div>
    </div>
    """
    await enviar_email(destinatario, asunto, _build_html_base(asunto, contenido))


_XLSX_MIME_SUBTYPE = "vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


def _emails_para_gestor(nombre_gestor: str, mapa_gestor_emails: dict[str, list[str]]) -> list[str]:
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

    Orden de envío:
      1. PRIMERO el broadcast a ALERTAS_EMAIL (sin resaltado) — así
         coordinación siempre recibe una copia aunque después fallen
         las generaciones individuales por gestor.
      2. Luego un correo por cada gestor con su nombre resaltado.

    Retorna {'destinatarios', 'enviados', 'gestores_atendidos', 'broadcast_ok'}.
    """
    cfg = get_settings()
    # 20-08-2026 (caso real de Yesid). Cuando esto devolvía «enviados: 0» a
    # secas, la pantalla marcaba la importación como «✗ sin destinatarios» —
    # que suena a que no se encontró a quién mandarle. Pero la causa de
    # verdad era otra: el servidor no tiene el correo configurado. Yesid
    # importó dos veces buscando el error donde no estaba.
    #
    # El motivo viaja para que la pantalla diga cuál de las tres cosas pasó.
    if not cfg.smtp_user or not cfg.smtp_password:
        logger.warning("[EXCEL-EMAIL] no enviado: SMTP_USER/SMTP_PASSWORD vacíos")
        return {
            "destinatarios": 0,
            "enviados": 0,
            "gestores_atendidos": 0,
            "motivo": "SIN_CORREO_CONFIG",
        }

    if not excel_original:
        logger.warning("[EXCEL-EMAIL] no enviado: archivo original vacío")
        return {
            "destinatarios": 0,
            "enviados": 0,
            "gestores_atendidos": 0,
            "motivo": "SIN_ARCHIVO_ORIGINAL",
        }

    # Imports diferidos para evitar ciclo email_service ↔ recepcion_*
    from app.services.recepcion_excel_response import (
        construir_respuestas_por_clave,
        generar_excel_con_respuestas,
    )

    respuestas_por_clave = construir_respuestas_por_clave(db, list(glosa_ids or []))
    logger.info(
        f"[EXCEL-EMAIL] respuestas_por_clave: {len(respuestas_por_clave)} "
        f"glosas con dictamen persistido / {len(glosa_ids or [])} pedidas"
    )
    if not respuestas_por_clave:
        logger.info(
            "[EXCEL-EMAIL] sin glosas auto-procesadas para anotar — "
            "se envía Excel original sin columnas IA."
        )

    por_gestor = resumen.get("por_gestor", {}) or {}
    mapa = _mapear_gestor_a_emails(db)
    logger.info(
        f"[EXCEL-EMAIL] por_gestor={len(por_gestor)} gestores en el lote, "
        f"mapa_usuarios={len(mapa)} usuarios activos con email, "
        f"alertas_email='{cfg.alertas_email}'"
    )
    total = resumen.get("total", 0)
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo_base = f"glosas_recepcion_{fecha}.xlsx"

    enviados = 0
    destinatarios_unicos: set[str] = set()
    gestores_atendidos = 0
    broadcast_ok = False
    gestores_sin_email: list[str] = []
    gestores_detalle: list[dict] = []

    # ── 1. BROADCAST a ALERTAS_EMAIL primero ────────────────────────
    # Lo hacemos antes del loop por-gestor para garantizar que al menos
    # coordinación reciba una copia aunque después falle algo.
    if cfg.alertas_email:
        try:
            logger.info("[EXCEL-EMAIL] generando broadcast sin resaltado...")
            xlsx_broadcast = generar_excel_con_respuestas(
                excel_original,
                respuestas_por_clave,
                gestor_destacar=None,
            )
            logger.info(f"[EXCEL-EMAIL] broadcast generado: {len(xlsx_broadcast)} bytes")
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
                    broadcast_ok = True
            logger.info(f"[EXCEL-EMAIL] broadcast: enviados={enviados}, ok={broadcast_ok}")
        except Exception as e:
            logger.error(
                f"[EXCEL-EMAIL] broadcast coordinación falló: {type(e).__name__}: {e}",
                exc_info=True,
            )
    else:
        logger.warning("[EXCEL-EMAIL] ALERTAS_EMAIL vacío — no hay broadcast de respaldo")

    # ── 2. Loop por gestor ──────────────────────────────────────────
    for nombre_gestor, filas in sorted(por_gestor.items()):
        emails = _emails_para_gestor(nombre_gestor, mapa)
        if not emails:
            gestores_sin_email.append(nombre_gestor)
            gestores_detalle.append(
                {
                    "gestor": nombre_gestor,
                    "glosas": len(filas),
                    "emails": 0,
                    "enviado": False,
                    "motivo": "sin email en UsuarioRecord",
                }
            )
            logger.info(
                f"[EXCEL-EMAIL] Gestor '{nombre_gestor}' ({len(filas)} glosas) "
                f"sin email asociado en UsuarioRecord — su Excel queda solo "
                f"en la app. Nombres en mapa: {list(mapa.keys())[:5]}..."
            )
            continue
        gestores_atendidos += 1
        logger.info(f"[EXCEL-EMAIL] Gestor '{nombre_gestor}' → emails={emails}")

        try:
            xlsx_bytes = generar_excel_con_respuestas(
                excel_original,
                respuestas_por_clave,
                gestor_destacar=nombre_gestor,
            )
        except Exception as e:
            logger.error(
                f"[EXCEL-EMAIL] generación falló para gestor "
                f"'{nombre_gestor}': {type(e).__name__}: {e}",
                exc_info=True,
            )
            continue

        n_filas = len(filas)
        n_respondidas = sum(
            1
            for f in filas
            if respuestas_por_clave.get(
                (
                    (f.get("factura") or "").strip().upper(),
                    (f.get("consecutivo_dgh") or "").strip().upper(),
                ),
                {},
            )
            .get("estado", "")
            .upper()
            == "RESPONDIDA"
        )
        n_requieren = sum(
            1
            for f in filas
            if respuestas_por_clave.get(
                (
                    (f.get("factura") or "").strip().upper(),
                    (f.get("consecutivo_dgh") or "").strip().upper(),
                ),
                {},
            )
            .get("estado", "")
            .upper()
            == "REQUIERE_SOPORTES"
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
            🔗 <a href="{get_settings().app_base_url}" style="color:#92400e;font-weight:600">Abrir Motor Glosas HUS</a>
            — revisá los borradores y radicá los que estén OK.
        </p>
        """
        html = _build_html_base(asunto, contenido)
        adjunto: Adjunto = (archivo_base, xlsx_bytes, _XLSX_MIME_SUBTYPE)

        enviado_gestor = False
        for email in emails:
            destinatarios_unicos.add(email)
            if await enviar_email(email, asunto, html, adjuntos=[adjunto]):
                enviados += 1
                enviado_gestor = True
        gestores_detalle.append(
            {
                "gestor": nombre_gestor,
                "glosas": len(filas),
                "emails": len(emails),
                "enviado": enviado_gestor,
                "motivo": "" if enviado_gestor else "fallo SMTP",
            }
        )

    logger.info(
        f"[EXCEL-EMAIL] ✅ flujo terminó: enviados={enviados}, "
        f"destinatarios_unicos={len(destinatarios_unicos)}, "
        f"gestores_atendidos={gestores_atendidos}, "
        f"sin_email={len(gestores_sin_email)} {gestores_sin_email[:5]}, "
        f"broadcast_ok={broadcast_ok}"
    )
    return {
        "destinatarios": len(destinatarios_unicos),
        "enviados": enviados,
        "gestores_atendidos": gestores_atendidos,
        "gestores_sin_email": gestores_sin_email,
        "gestores_detalle": gestores_detalle,
        "broadcast_ok": broadcast_ok,
        # 20-08-2026. Sin esto, «no salió ningún correo» se mostraba SIEMPRE
        # como «nadie a quien enviarlo», aunque sí hubiera destinatarios y lo
        # que fallara fuera el servidor de correo. El auditor se pone a revisar
        # la lista de gestores —que está bien— mientras el problema está en
        # otro lado. Ya nos pasó hoy con el correo mal configurado.
        "motivo": ("FALLO_ENVIO" if (enviados <= 0 and destinatarios_unicos) else ""),
    }
