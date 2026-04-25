import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

MESES_ES = {
    "January": "ENERO", "February": "FEBRERO", "March": "MARZO",
    "April": "ABRIL", "May": "MAYO", "June": "JUNIO",
    "July": "JULIO", "August": "AGOSTO", "September": "SEPTIEMBRE",
    "October": "OCTUBRE", "November": "NOVIEMBRE", "December": "DICIEMBRE"
}

def fecha_hoy_espanol() -> str:
    now = datetime.now()
    mes_en = now.strftime("%B")
    return f"{now.day} DE {MESES_ES.get(mes_en, mes_en.upper())} DE {now.year}"

from fastapi import FastAPI, Form, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.database import engine, Base, SessionLocal, get_db
from app.models.db import ContratoRecord, UsuarioRecord
from app.models.schemas import GlosaInput, GlosaResult
from app.core.config import get_settings, check_security_config
from app.auth import get_password_hash
from app.core.logging_utils import set_request_id, logger
from app.core.sentry_init import init_sentry

# Sentry debe inicializarse ANTES de cualquier import que pueda fallar.
# Si SENTRY_DSN no está definido, no hace nada.
init_sentry()
from app.api.deps import get_usuario_actual
from app.services.glosa_ia_prompts import get_contrato


# Ronda 50 Paso 9: parsers extraídos a app/utils/parsers_glosa.py
# para reducir main.py de 1757 → 1280 líneas.
from app.utils.parsers_glosa import (  # noqa: E402,F401
    _detectar_servicio_desde_texto,
    _extraer_motivo_glosa,
    _concepto_glosa,
    _extraer_valores_glosa,
    _generar_banner_tarifa_html,
    _extraer_cups_servicio,
    _descripcion_servicio,
)


logging.basicConfig(level=logging.INFO)

CONTRATOS_DEFAULT = {
    "FAMISANAR EPS": "CONTRATO S-13-1-03-1-04958 (vig. 15/04/2026 — 14/04/2027). TARIFA: SOAT UVB VIGENTE -5% para servicios CUPS (Anexo 3) / VALOR FIJO para medicamentos (Anexo 3.1) y suministros (Anexo 3.2). Catálogo completo cargado en panel Tarifas.",
    "NUEVA EPS": "ACTA DE NEGOCIACIÓN No. 1388 DE 2024 / ACTA 2025. TARIFA: SOAT -20%.",
    "COOSALUD": "68001C00060340-24 / 68001S00060339-24. TARIFA: SOAT -15%.",
    "COMPENSAR": "ACUERDO TARIFARIO ESE HUS — EPS COMPENSAR 2025. TARIFA: SOAT -10%.",
    "POSITIVA": "CONTRATO No. 0525 DE 2017 + OTROSÍ No. 03. TARIFA: SOAT -15%.",
    "PPL": "CONTRATO IPS-001B-2022 — OTROSÍ No. 26. TARIFA: SOAT -15%.",
    "FOMAG": "CONTRATO No. 12076-359-2025. TARIFA: SOAT -15%.",
    "POLICIA NACIONAL": "CONTRATO No. 068-5-200004-26 (SFI 004). TARIFA: UVB – 8%.",
    "SUMIMEDICAL": "TARIFARIO ESE HUS 2025 — SUMIMEDICAL. TARIFA: SOAT -15%.",
    "DISPENSARIO MEDICO": "CONTRATO No. 440-DIGSA/DMBUG-2025. TARIFA: SOAT/SMLV -20%.",
    "SALUD MIA": "CONTRATO CSA2025EVE3A005. TARIFA: SOAT -15%.",
    "PRECIMED": "CONTRATO No. 319 DE 2024. TARIFA: SOAT -15%.",
    "AURORA": "MINUTA ARL + MINUTA VIDA AP — FIRMADAS SEP 2024. TARIFA: SOAT PLENO.",
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== INICIANDO APLICACIÓN ===")
    check_security_config()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    cfg = get_settings()
    from sqlalchemy import text, inspect

    # Helper dialect-agnostic para verificar si una columna existe.
    # Funciona tanto en SQLite (dev) como en PostgreSQL (prod).
    inspector = inspect(engine)
    def _tiene_columna(tabla: str, columna: str) -> bool:
        try:
            cols = [c["name"] for c in inspector.get_columns(tabla)]
            return columna in cols
        except Exception:
            return False

    def _tiene_tabla(tabla: str) -> bool:
        try:
            return inspector.has_table(tabla)
        except Exception:
            return False

    # Tipo de timestamp compatible con ambos motores
    from app.core.config import get_settings as _gs
    _cfg_local = _gs()
    _is_sqlite = _cfg_local.database_url.startswith("sqlite")
    _TS_TIPO = "TIMESTAMP" if _is_sqlite else "TIMESTAMP WITH TIME ZONE"
    _TS_DEFAULT = "CURRENT_TIMESTAMP" if _is_sqlite else "NOW()"

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "creado_en"):
            logger.warning("MIGRACIÓN: Agregando columna 'creado_en' a tabla usuarios")
            db.execute(text(f"ALTER TABLE usuarios ADD COLUMN creado_en {_TS_TIPO} DEFAULT {_TS_DEFAULT}"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN creado_en: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "activo"):
            logger.warning("MIGRACIÓN: Agregando columna 'activo' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN activo INTEGER DEFAULT 1"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN activo: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "rol"):
            logger.warning("MIGRACIÓN: Agregando columna 'rol' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN rol VARCHAR(50) DEFAULT 'AUDITOR'"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN rol: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "workload"):
            logger.warning("MIGRACIÓN: Agregando columna 'workload' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN workload INTEGER DEFAULT 100"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN workload: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "nota_workflow"):
            logger.warning("MIGRACIÓN: Agregando columna 'nota_workflow' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN nota_workflow TEXT"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN nota_workflow: {e}")

    # Campo must_change_password (forzar cambio en primer login)
    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "must_change_password"):
            logger.warning("MIGRACIÓN: Agregando columna 'must_change_password' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN must_change_password: {e}")

    # Campo password_changed_at (timestamp último cambio)
    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "password_changed_at"):
            logger.warning("MIGRACIÓN: Agregando columna 'password_changed_at' a tabla usuarios")
            db.execute(text(f"ALTER TABLE usuarios ADD COLUMN password_changed_at {_TS_TIPO}"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN password_changed_at: {e}")

    # Campo equipo (agrupación de usuarios que comparten bandeja)
    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "equipo"):
            logger.warning("MIGRACIÓN: Agregando columna 'equipo' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN equipo VARCHAR(50)"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN equipo: {e}")

    try:
        if _tiene_tabla("historial") and not _tiene_columna("historial", "numero_radicado"):
            logger.warning("MIGRACIÓN: Agregando columna 'numero_radicado' a historial")
            db.execute(text("ALTER TABLE historial ADD COLUMN numero_radicado VARCHAR(50)"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN numero_radicado: {e}")

    try:
        if _tiene_tabla("historial") and not _tiene_columna("historial", "request_id"):
            logger.warning("MIGRACIÓN: Agregando columnas a historial")
            db.execute(text("ALTER TABLE historial ADD COLUMN request_id VARCHAR(50)"))
            db.execute(text("ALTER TABLE historial ADD COLUMN nota_workflow VARCHAR(500)"))
            db.execute(text("ALTER TABLE historial ADD COLUMN prioridad VARCHAR(50) DEFAULT 'NORMAL'"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN historial: {e}")

    _HISTORIAL_MISSING_COLUMNS = [
        ("workflow_state", "VARCHAR(50) DEFAULT 'RADICADA'"),
        ("responsable", "VARCHAR(200)"),
        ("fecha_vencimiento", "TIMESTAMP WITH TIME ZONE"),
        ("auditor_email", "VARCHAR(200)"),
        ("decision_eps", "VARCHAR(50)"),
        ("fecha_decision_eps", "TIMESTAMP WITH TIME ZONE"),
        ("valor_recuperado", "DOUBLE PRECISION DEFAULT 0"),
        ("observacion_eps", "TEXT"),
        ("gestor_nombre", "VARCHAR(200)"),
        ("fecha_radicacion_factura", "TIMESTAMP WITH TIME ZONE"),
        ("fecha_documento_dgh", "TIMESTAMP WITH TIME ZONE"),
        ("fecha_recepcion", "TIMESTAMP WITH TIME ZONE"),
        ("fecha_entrega", "TIMESTAMP WITH TIME ZONE"),
        ("consecutivo_dgh", "VARCHAR(50)"),
        ("es_devolucion", "VARCHAR(1)"),
        ("radicado_info", "VARCHAR(200)"),
        ("referencia", "VARCHAR(300)"),
        ("observacion_tecnico", "TEXT"),
        ("tipo_glosa_excel", "VARCHAR(50)"),
        ("profesional_medico", "VARCHAR(200)"),
        ("texto_glosa_original", "TEXT"),
        ("codigo_respuesta", "VARCHAR(20)"),
        ("cups_servicio", "VARCHAR(50)"),
        ("servicio_descripcion", "VARCHAR(400)"),
        ("concepto_glosa", "TEXT"),
        ("eps_codigo", "VARCHAR(20)"),
        ("tecnico_recepcion", "VARCHAR(200)"),
        ("fecha_objecion_eps", "TIMESTAMP WITH TIME ZONE"),
        ("saldo_factura", "DOUBLE PRECISION DEFAULT 0"),
        ("valor_factura", "DOUBLE PRECISION DEFAULT 0"),
        ("tercero_nit", "VARCHAR(30)"),
        ("dias_radicacion_dgh", "INTEGER DEFAULT 0"),
        ("tercero_nombre", "VARCHAR(300)"),
    ]
    for col_name, col_ddl in _HISTORIAL_MISSING_COLUMNS:
        try:
            if _tiene_tabla("historial") and not _tiene_columna("historial", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a historial")
                # Reemplazar TIMESTAMP WITH TIME ZONE por TIMESTAMP en SQLite
                col_ddl_adapted = col_ddl.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP") if _is_sqlite else col_ddl
                col_ddl_adapted = col_ddl_adapted.replace("DOUBLE PRECISION", "REAL") if _is_sqlite else col_ddl_adapted
                db.execute(text(f"ALTER TABLE historial ADD COLUMN {col_name} {col_ddl_adapted}"))
                db.commit()
        except Exception as e:
            logger.warning(f"MIGRACIÓN {col_name}: {e}")

    # Migraciones para usuarios - 2FA TOTP
    _USUARIOS_MISSING_2FA = [
        ("totp_secret", "VARCHAR(64)"),
        ("totp_activo", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_ddl in _USUARIOS_MISSING_2FA:
        try:
            if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a usuarios")
                db.execute(text(f"ALTER TABLE usuarios ADD COLUMN {col_name} {col_ddl}"))
                db.commit()
        except Exception as e:
            logger.warning(f"MIGRACIÓN usuarios {col_name}: {e}")

    # Migraciones para conciliaciones - trazabilidad bilateral
    _CONCILIACION_MISSING = [
        ("contra_respuesta_eps", "TEXT"),
        ("fecha_contra_respuesta_eps", "TIMESTAMP WITH TIME ZONE"),
        ("postura_hus", "TEXT"),
        ("fecha_acta", "TIMESTAMP WITH TIME ZONE"),
        ("valor_ratificado_hus", "FLOAT DEFAULT 0"),
        ("estado_bilateral", "VARCHAR(40) DEFAULT 'PROGRAMADA'"),
    ]
    for col_name, col_ddl in _CONCILIACION_MISSING:
        try:
            if _tiene_tabla("conciliaciones") and not _tiene_columna("conciliaciones", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a conciliaciones")
                col_ddl_adapted = col_ddl.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP") if _is_sqlite else col_ddl
                db.execute(text(f"ALTER TABLE conciliaciones ADD COLUMN {col_name} {col_ddl_adapted}"))
                db.commit()
        except Exception as e:
            logger.warning(f"MIGRACIÓN conciliaciones {col_name}: {e}")

    # Migraciones para tarifas_contratadas - soporte formulaic (SOAT %)
    # + Ronda 45: codigo_ips para homologación Res. 2641/2025
    _TARIFAS_MISSING = [
        ("tipo_tarifa", "VARCHAR(30) DEFAULT 'VALOR_FIJO'"),
        ("factor_ajuste", "DOUBLE PRECISION DEFAULT 0"),
        ("codigo_ips", "VARCHAR(30)"),
    ]
    for col_name, col_ddl in _TARIFAS_MISSING:
        try:
            if _tiene_tabla("tarifas_contratadas") and not _tiene_columna("tarifas_contratadas", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a tarifas_contratadas")
                col_ddl_adapted = col_ddl.replace("DOUBLE PRECISION", "REAL") if _is_sqlite else col_ddl
                db.execute(text(f"ALTER TABLE tarifas_contratadas ADD COLUMN {col_name} {col_ddl_adapted}"))
                db.commit()
        except Exception as e:
            logger.warning(f"MIGRACIÓN tarifas_contratadas {col_name}: {e}")

    # Migraciones para conceptos_glosa (Ronda 50 — bug #4 DGH)
    # codigo_syscafe: código interno numérico del DGH (ej. "423") distinto
    # del código canónico Res. 2284/2023 (ej. "TA0201"). Se guarda al
    # importar si viene, y se usa al exportar para DGH.
    _CONCEPTOS_GLOSA_MISSING = [
        ("codigo_syscafe", "VARCHAR(20)"),
    ]
    for col_name, col_ddl in _CONCEPTOS_GLOSA_MISSING:
        try:
            if _tiene_tabla("conceptos_glosa") and not _tiene_columna("conceptos_glosa", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a conceptos_glosa")
                db.execute(text(f"ALTER TABLE conceptos_glosa ADD COLUMN {col_name} {col_ddl}"))
                db.commit()
        except Exception as e:
            logger.warning(f"MIGRACIÓN conceptos_glosa {col_name}: {e}")

    db.close()

    db = SessionLocal()

    try:
        # Cargar contratos iniciales
        # Primero eliminar contratos que ya no existen en la lista actual
        eps_actuales = list(CONTRATOS_DEFAULT.keys())
        contratos_existentes = db.query(ContratoRecord).all()
        for contrato in contratos_existentes:
            if contrato.eps not in eps_actuales:
                logger.warning(f"ELIMINANDO contrato obsoleto: {contrato.eps}")
                db.delete(contrato)

        for k, v in CONTRATOS_DEFAULT.items():
            existente = db.query(ContratoRecord).filter(ContratoRecord.eps == k).first()
            if existente:
                existente.detalles = v
            else:
                db.add(ContratoRecord(eps=k, detalles=v))

        # Crear admin solo si no existe
        # CORRECCIÓN: contraseña desde variable de entorno, sin hardcodear.
        # Si ADMIN_PASSWORD no está configurada, usamos un fallback aleatorio
        # distinto en cada arranque → obliga al operador a configurar la env.
        if db.query(UsuarioRecord).count() == 0:
            from app.core.config import _UNCONFIGURED_ADMIN_PASSWORD
            import secrets as _secrets
            admin_pass = cfg.admin_password
            if admin_pass == _UNCONFIGURED_ADMIN_PASSWORD:
                # Genera password aleatorio imposible de adivinar —
                # operador DEBE configurar ADMIN_PASSWORD y correr el reset.
                admin_pass = _secrets.token_urlsafe(32)
                logger.error(
                    "ADMIN_PASSWORD no configurada. Admin creado con password "
                    "aleatorio IMPOSIBLE de adivinar. Define ADMIN_PASSWORD en "
                    "Environment y usa FORCE_RESET_ADMIN_PASSWORD=1 para setear "
                    "tu password conocido."
                )
            db.add(UsuarioRecord(
                nombre="Auditor Principal",
                email="admin@hus.gov.co",
                password_hash=get_password_hash(admin_pass),
                rol="SUPER_ADMIN",
                activo=1,
                must_change_password=1,  # forzar cambio en primer login
            ))
            logger.warning(
                "Usuario admin creado. Cambiar contraseña inmediatamente "
                "usando la variable de entorno ADMIN_PASSWORD + "
                "FORCE_RESET_ADMIN_PASSWORD=1."
            )

        # Asegurar que admin@hus.gov.co tenga rol SUPER_ADMIN
        admin = db.query(UsuarioRecord).filter(UsuarioRecord.email == "admin@hus.gov.co").first()
        if admin and admin.rol != "SUPER_ADMIN":
            logger.warning("Actualizando rol de admin@hus.gov.co a SUPER_ADMIN")
            admin.rol = "SUPER_ADMIN"

        # Reset controlado de password para admin@hus.gov.co.
        # Toggle: FORCE_RESET_ADMIN_PASSWORD=1 en Render Environment.
        # Al arrancar con este flag activo, el password del admin se actualiza
        # al valor actual de ADMIN_PASSWORD env var. Usar UNA SOLA VEZ para el
        # cambio inicial a un password fuerte, luego QUITAR la variable.
        if os.getenv("FORCE_RESET_ADMIN_PASSWORD", "").lower() in ("1", "true", "yes"):
            if admin:
                nuevo_pass = cfg.admin_password
                # Validación básica: no permitir passwords débiles conocidos
                passwords_debiles = {"admin", "admin123", "password", "123456", "hus2026"}
                if nuevo_pass.lower() in passwords_debiles:
                    logger.error(
                        "[FORCE_RESET_ADMIN_PASSWORD] ABORTADO: ADMIN_PASSWORD "
                        "coincide con un password débil conocido. Usa un password "
                        "de al menos 12 caracteres con mayúsculas, números y símbolos."
                    )
                elif len(nuevo_pass) < 10:
                    logger.error(
                        "[FORCE_RESET_ADMIN_PASSWORD] ABORTADO: ADMIN_PASSWORD "
                        f"tiene solo {len(nuevo_pass)} caracteres. Mínimo requerido: 10."
                    )
                else:
                    admin.password_hash = get_password_hash(nuevo_pass)
                    admin.must_change_password = 1  # forzar cambio en primer login
                    logger.warning(
                        "[FORCE_RESET_ADMIN_PASSWORD] Password de admin@hus.gov.co "
                        f"actualizado al valor de ADMIN_PASSWORD ({len(nuevo_pass)} chars) "
                        "+ must_change_password=1. QUITAR la variable "
                        "FORCE_RESET_ADMIN_PASSWORD del entorno después de este redeploy."
                    )
            else:
                logger.error(
                    "[FORCE_RESET_ADMIN_PASSWORD] No se encontró admin@hus.gov.co "
                    "en la base de datos."
                )

        # Sembrar usuarios corporativos de gestores de glosas
        # Contraseña inicial: ADMIN_PASSWORD (cambiar en primer login)
        # El 'nombre' debe coincidir con la columna GESTOR del Excel de recepción
        # para que cada gestor vea sus asignaciones (matching ILIKE).
        USUARIOS_CORPORATIVOS = [
            ("glosashus09@sinacsc.com",      "SUPER_ADMIN", "YESID PEREZ"),
            ("glosashus11@sinacsc.com",      "AUDITOR",     "DIANEYDA QUINTERO"),
            ("glosashus02@sinacsc.com",      "AUDITOR",     "CAROLINA CIFUENTES"),
            ("glosashus04@sinacsc.com",      "AUDITOR",     "JHON JAIMES"),
            ("glosashus05@sinacsc.com",      "AUDITOR",     "MARICELA ROJAS"),
            ("carterahus01@sinacsc.com",     "AUDITOR",     "IRMA RIOS"),
            ("carterahus04@sinacsc.com",     "AUDITOR",     "RUBY MILENA"),
            ("carterahus05@sinacsc.com",     "AUDITOR",     "PATRICIA QUIÑONES"),
            ("radicadevoluciones@sinacsc.com","AUDITOR",    "KAREN ORTIZ"),
            ("devoluciones01@sinacsc.com",   "AUDITOR",     "SEBASTIAN SANCHES"),
            ("coordinacioncartera@hus.gov.co","AUDITOR",    "YUDY AMAYA"),
            ("glosashus08@sinacsc.com",      "AUDITOR",     "CLAUDIA SUAREZ"),
            ("glosashus07@sinacsc.com",      "AUDITOR",     "YENFERSON ORTEGA"),
            ("glosashus12@sinacsc.com",      "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("devoluciones02@sinacsc.com",   "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("glosashus10@sinacsc.com",      "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("glosashus16@sinacsc.com",      "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
            # Usuarios adicionales creados desde la UI (añadidos al seed
            # para que reaparezcan si alguna vez la DB se recrea desde cero):
            ("auditorhus01@sinacsc.com",     "AUDITOR",     "LAURA DIAZ"),
            ("auditorhus02@sinacsc.com",     "AUDITOR",     "LEIDY JHOANA SANGUINO"),
            ("auditorhus03@sinacsc.com",     "AUDITOR",     "LEYDI ZULAY GONZALEZ"),
            ("devoluciones03@sinacsc.com",   "AUDITOR",     "JOHANNA MORENO"),
            ("devoluciones1@sinacsc.com",    "AUDITOR",     "EDGAR SILVA"),
            ("glosashus03@sinacsc.com",      "AUDITOR",     "OSCAR VILLAMIZAR"),
        ]
        # POLÍTICA DE PASSWORD INICIAL: cada usuario corporativo recibe como
        # contraseña el prefijo de su correo (ej. glosashus04@sinacsc.com →
        # password "glosashus04"). El usuario debe cambiarla en el primer login.
        force_reseed = os.getenv("FORCE_RESEED_USERS", "").lower() in ("1", "true", "yes")
        force_reset_pwd = os.getenv("FORCE_RESET_PASSWORDS", "").lower() in ("1", "true", "yes")
        for email, rol, nombre in USUARIOS_CORPORATIVOS:
            password_inicial = email.split("@")[0]  # prefijo
            password_hash_inicial = get_password_hash(password_inicial)
            existente = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
            if not existente:
                db.add(UsuarioRecord(
                    nombre=nombre,
                    email=email,
                    password_hash=password_hash_inicial,
                    rol=rol,
                    activo=1,
                    must_change_password=1,  # obligado a cambiar en primer login
                ))
                logger.warning(f"Usuario sembrado: {email} ({rol}) nombre={nombre} password=<prefijo>")
            # Si el usuario YA existe, la base de datos es la fuente de verdad:
            # NO sobrescribimos nombre/rol/password. Los cambios hechos por un
            # SUPER_ADMIN desde la UI deben persistir a través de redeploys.
            # Toggles de re-sincronización masiva:
            #   FORCE_RESEED_USERS=1 → resincroniza nombre y rol
            #   FORCE_RESET_PASSWORDS=1 → resetea password al prefijo + must_change=1
            elif force_reseed or force_reset_pwd:
                cambios = []
                if force_reseed and existente.rol != rol:
                    cambios.append(f"rol {existente.rol}->{rol}")
                    existente.rol = rol
                if force_reseed and existente.nombre != nombre:
                    cambios.append(f"nombre '{existente.nombre}'->'{nombre}'")
                    existente.nombre = nombre
                if force_reset_pwd:
                    existente.password_hash = password_hash_inicial
                    existente.must_change_password = 1
                    cambios.append("password reset a prefijo email + must_change=1")
                if cambios:
                    logger.warning(f"[FORCE_RESEED] {email}: {', '.join(cambios)}")

        # EQUIPOS COMPARTIDOS: los 4 correos del EQUIPO ASEGURADORAS comparten
        # bandeja de "Mis glosas" e "Historial". Seteamos campo equipo para
        # que las queries los agrupen.
        EQUIPOS_COMPARTIDOS = {
            "EQUIPO_ASEGURADORAS": [
                "glosashus12@sinacsc.com",
                "devoluciones02@sinacsc.com",
                "glosashus10@sinacsc.com",
                "glosashus16@sinacsc.com",
            ],
        }
        for equipo_codigo, emails_equipo in EQUIPOS_COMPARTIDOS.items():
            for email_eq in emails_equipo:
                u = db.query(UsuarioRecord).filter(UsuarioRecord.email == email_eq).first()
                if u and u.equipo != equipo_codigo:
                    u.equipo = equipo_codigo
                    logger.info(f"Usuario {email_eq} asignado a equipo {equipo_codigo}")

        db.commit()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando BD: {e}")
        db.rollback()
    finally:
        db.close()

    # Ronda 2: iniciar scheduler de IA auditora proactiva (6 AM diario).
    # No bloquea el startup si falla; sólo deja logs.
    try:
        from app.services.ia_auditora_proactiva import iniciar_scheduler
        iniciar_scheduler()
    except Exception as _e:
        logger.warning(f"No se pudo iniciar scheduler de pre-análisis: {_e}")

    # Ronda 20: scheduler del digest ejecutivo (sólo si DIGEST_DESTINATARIOS
    # está configurado). No bloquea startup si falla.
    try:
        from app.services.digest_scheduler import iniciar_scheduler as iniciar_digest_scheduler
        iniciar_digest_scheduler()
    except Exception as _e:
        logger.warning(f"No se pudo iniciar scheduler del digest: {_e}")

    yield

    # Shutdown: detener schedulers limpiamente
    try:
        from app.services.ia_auditora_proactiva import detener_scheduler
        detener_scheduler()
    except Exception:
        pass
    try:
        from app.services.digest_scheduler import detener_scheduler as detener_digest_scheduler
        detener_digest_scheduler()
    except Exception:
        pass
    logger.info("=== APLICACIÓN CERRADA ===")


cfg = get_settings()


def _limit_key_user_or_ip(request):
    """Key-func del rate limiter: prioriza el email del usuario autenticado
    (JWT) sobre la IP. Evita que un usuario abra varias pestañas/VPN y se
    escape del límite; y evita que una oficina compartiendo NAT tumbe a
    todos sus usuarios por un solo spammer. Optimización #6.
    """
    try:
        auth = (request.headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer ") and len(auth) > 16:
            from jose import jwt as _jwt
            payload = _jwt.decode(
                auth.split(" ", 1)[1].strip(),
                cfg.secret_key,
                algorithms=[cfg.algorithm],
            )
            email = (payload or {}).get("sub") or (payload or {}).get("email")
            if email:
                return f"user:{email}"
    except Exception:
        pass
    return get_remote_address(request)


# Rate limiter para proteger endpoints de IA
limiter = Limiter(key_func=_limit_key_user_or_ip)

app = FastAPI(
    title="Motor Glosas HUS",
    description="""
## API del Motor de Glosas - ESE Hospital Universitario de Santander

Sistema automatizado de defensa de glosas médicas con asistencia de IA.

### Funcionalidades
- **Análisis automático** de glosas mediante Groq/Anthropic
- **Detección de extemporaneidad** (20 días hábiles - Art. 56 Ley 1438/2011)
- **Plantillas especializadas** por tipo de glosa
- **Gestión de contratos** EPS con tarifas específicas
- **Historial y métricas** de glosas

### Autenticación
Todos los endpoints excepto `/health` requieren token JWT.
Obtener token en `/api/auth/login`.

### Códigos de Respuesta (Resolución 3047/2008 - Normativa Colombiana)
| Código | Descripción |
|--------|-------------|
| RE9502 | Glosa no procede - Aceptación tácita de la factura (Art. 56 Ley 1438/2011) |
| RE9602 | Glosa Injustificada - Aporta evidencia de que la glosa es injustificada al 100% |
| RE9701 | Devolución aceptada al 100% |
| RE9702 | Glosa aceptada al 100% |
| RE9801 | Glosa aceptada y subsanada parcialmente |
| RE9901 | Glosa no aceptada - Subsanada en su totalidad |
    """,
    version="5.5.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORRECCIÓN: CORS restringido a orígenes configurados, no "*"
allowed_origins = cfg.get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Ronda 50 Paso 10: middleware de tenant.
# Resuelve el tenant_id desde header X-Tenant-ID, query ?tenant=, o
# subdominio (hus.ia-glosas.com → 'HUS'). Por defecto 'HUS' para no
# romper el flujo single-tenant actual. Cuando entre cliente #2 solo
# hay que setear tenant_id en sus glosas y este middleware ya filtra.
@app.middleware("http")
async def _tenant_middleware(request, call_next):
    try:
        from app.services.tenancy import (
            resolver_tenant_desde_request,
            set_tenant_id,
        )
        tenant = resolver_tenant_desde_request(request)
        set_tenant_id(tenant)
    except Exception:
        # No bloquear request si algo en la resolución falla
        pass
    response = await call_next(request)
    return response


app.mount("/static", StaticFiles(directory="static"), name="static")

from app.api.routers.auth_router import router as auth_router
from app.api.routers.glosas import router as glosas_router
from app.api.routers.contratos import router as contratos_router
from app.api.routers.analytics import router as analytics_router
from app.api.routers.plantillas import router as plantillas_router
from app.api.routers.exportar import router as exportar_router
from app.api.routers.workflow import router as workflow_router
from app.api.routers.alertas import router as alertas_router
from app.api.routers.usuarios import router as usuarios_router
from app.api.routers.conciliacion import router as conciliacion_router
from app.api.routers.audit import router as audit_router
from app.api.routers.salud_total import router as salud_total_router
from app.api.routers.tarifas_contratadas import router as tarifas_contratadas_router
from app.api.routers.admin import router as admin_router
from app.api.routers.plantillas_gold import router as plantillas_gold_router
from app.api.routers.comentarios import router as comentarios_router
from app.api.routers.informes import router as informes_router
from app.api.routers.mi_desempeno import router as mi_desempeno_router
from app.api.routers.busqueda_semantica import router as busqueda_semantica_router
from app.api.routers.dos_fa import router as dos_fa_router
from app.api.routers.versiones import router as versiones_router
from app.api.routers.papelera import router as papelera_router
from app.api.routers.simulador import router as simulador_router
from app.api.routers.export_erp import router as export_erp_router
from app.api.routers.asignacion import router as asignacion_router
from app.api.routers.push import router as push_router
from app.api.routers.bandeja import router as bandeja_router
from app.api.routers.adjuntos import router as adjuntos_router
from app.api.routers.consulta_normativa import router as consulta_normativa_router
from app.api.routers.validador import router as validador_router
from app.api.routers.herramientas_avanzadas import router as herramientas_router
from app.api.routers.chat_glosa import router as chat_glosa_router
from app.api.routers.dashboard_ejecutivo import router as dashboard_ejecutivo_router
from app.api.routers.auditoria_forense import router as auditoria_forense_router
from app.api.routers.anomalias import router as anomalias_router
from app.api.routers.sistema import router as sistema_router
from app.api.routers.autopilot import router as autopilot_router
from app.api.routers.digest import router as digest_router
from app.api.routers.control_center import router as control_center_router
from app.api.routers.notificaciones import router as notificaciones_router
from app.services.glosa_service import GlosaService
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.glosa_repository import GlosaRepository

app.include_router(auth_router)
app.include_router(glosas_router)
app.include_router(contratos_router)
app.include_router(analytics_router)
app.include_router(plantillas_router)
app.include_router(exportar_router)
app.include_router(workflow_router)
app.include_router(alertas_router)
app.include_router(usuarios_router)
app.include_router(conciliacion_router)
app.include_router(audit_router)
app.include_router(salud_total_router)
app.include_router(tarifas_contratadas_router)
app.include_router(admin_router)
app.include_router(plantillas_gold_router)
app.include_router(comentarios_router)
app.include_router(informes_router)
app.include_router(mi_desempeno_router)
app.include_router(busqueda_semantica_router)
app.include_router(dos_fa_router)
app.include_router(versiones_router)
app.include_router(papelera_router)
app.include_router(simulador_router)
app.include_router(export_erp_router)
app.include_router(asignacion_router)
app.include_router(push_router)
app.include_router(bandeja_router)
app.include_router(adjuntos_router)
app.include_router(consulta_normativa_router)
app.include_router(validador_router)
app.include_router(herramientas_router)
app.include_router(chat_glosa_router)
app.include_router(dashboard_ejecutivo_router)
app.include_router(auditoria_forense_router)
app.include_router(anomalias_router)
app.include_router(sistema_router)
app.include_router(autopilot_router)
app.include_router(digest_router)
app.include_router(control_center_router)
app.include_router(notificaciones_router)
from app.api.routers.cups import router as cups_router
app.include_router(cups_router)


def get_glosa_service() -> GlosaService:
    return GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
    )


@app.post(
    "/analizar",
    response_model=GlosaResult,
    summary="Analizar Glosa",
    description="""
Analiza una glosa y genera respuesta técnico-jurídica automática.

**Ejemplo de uso:**
```bash
curl -X POST http://localhost:8000/analizar \\
  -H "Authorization: Bearer $TOKEN" \\
  -F "eps=EPS SANITAS" \\
  -F "etapa=RESPUESTA A GLOSA" \\
  -F "fecha_radicacion=2026-03-01" \\
  -F "fecha_recepcion=2026-03-25" \\
  -F "tabla_excel=TA0201 $1,500,000 Diferencia en consulta"
```

**Respuesta de ejemplo:**
```json
{
  "tipo": "RESPUESTA RE9901",
  "resumen": "DEFENSA TÉCNICA: Glosa No Aceptada - Subsanada",
  "codigo_glosa": "TA0201",
  "valor_objetado": "$ 1,500,000",
  "mensaje_tiempo": "EN TÉRMINOS (10 DÍAS HÁBILES - LÍMITE: 20)",
  "score": 85.5,
  "modelo_ia": "groq/llama-3.3"
}
```
    """,
    responses={
        200: {"description": "Análisis completado exitosamente"},
        422: {"description": "Datos de entrada inválidos"},
        429: {"description": "Límite de requests excedido (30/min)"},
    },
)
@limiter.limit("60/minute")
async def analizar(
    request: Request,
    eps: str = Form(...),
    etapa: str = Form(...),
    fecha_radicacion: Optional[str] = Form(None),
    fecha_recepcion: Optional[str] = Form(None),
    valor_aceptado: str = Form("0"),
    tabla_excel: str = Form(...),
    numero_factura: Optional[str] = Form(None),
    numero_radicado: Optional[str] = Form(None),
    tono: Optional[str] = Form("conciliador"),
    modo_respuesta: Optional[str] = Form("defender"),
    valor_aceptado_parcial: Optional[float] = Form(0.0),
    archivos: Optional[list[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    service: GlosaService = Depends(get_glosa_service),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    req_id = set_request_id()
    logger.info(
        f"[{req_id}] Análisis solicitado por: {current_user.email} | "
        f"eps={eps} | tono={tono} | modo={modo_respuesta}"
    )

    try:
        data = GlosaInput(
            eps=eps, etapa=etapa,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
            valor_aceptado=valor_aceptado,
            tabla_excel=tabla_excel,
            numero_factura=numero_factura,
            numero_radicado=numero_radicado,
            tono=tono,
            modo_respuesta=modo_respuesta or "defender",
            valor_aceptado_parcial=valor_aceptado_parcial or 0.0,
        )
    except Exception as e:
        logger.error(f"[{req_id}] Validación fallida: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    from app.services.pdf_service import PdfService
    contexto_pdf = ""
    archivos_procesados = 0
    MAX_ARCHIVOS = 10  # Límite de soportes PDF por glosa
    if archivos:
        pdf_svc = PdfService()
        for archivo in archivos:
            if archivos_procesados >= MAX_ARCHIVOS:
                logger.warning(f"[{req_id}] Máximo {MAX_ARCHIVOS} archivos alcanzado, ignorando restantes")
                break
            if archivo.filename:
                try:
                    contenido = await archivo.read()
                    if contenido[:4] != b"%PDF":
                        logger.warning(f"[{req_id}] Archivo ignorado (no es PDF): {archivo.filename}")
                        continue
                    if len(contenido) > 15_000_000:  # 15MB por archivo
                        logger.warning(f"[{req_id}] PDF muy grande: {archivo.filename}")
                        continue
                    # OCR automático con Claude si el PDF es escaneado y hay key
                    texto, metodo = await pdf_svc.extraer_con_ocr(
                        contenido,
                        anthropic_api_key=cfg.anthropic_api_key,
                        anthropic_model=cfg.anthropic_model,
                    )
                    # Separador claro entre PDFs para que la IA los distinga
                    if contexto_pdf:
                        contexto_pdf += f"\n\n═══ DOCUMENTO: {archivo.filename} ═══\n\n"
                    else:
                        contexto_pdf = f"═══ DOCUMENTO: {archivo.filename} ═══\n\n"
                    contexto_pdf += texto
                    archivos_procesados += 1
                    logger.info(f"[{req_id}] PDF {archivo.filename}: {metodo} ({len(texto)} chars)")
                except Exception as e:
                    logger.warning(f"[{req_id}] Error extrayendo PDF {archivo.filename}: {e}")
        if archivos_procesados:
            logger.info(f"[{req_id}] Total PDFs procesados: {archivos_procesados}/{MAX_ARCHIVOS} | {len(contexto_pdf)} chars")

    contrato_repo = ContratoRepository(db)
    contratos = contrato_repo.como_dict()

    # Few-shots de plantillas gold según (EPS, código) si las hay
    from app.api.routers.plantillas_gold import obtener_few_shot, marcar_usos
    codigo_match = re.search(r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b", tabla_excel.upper())
    cod_pref = codigo_match.group(0) if codigo_match else ""
    plantillas_gold = obtener_few_shot(db, eps=eps, codigo_glosa=cod_pref, limite=2) if cod_pref else []
    few_shots = [p.argumento for p in plantillas_gold]

    # Pre-lookup de tarifa pactada: si hay match perfecto, el service
    # puede saltarse la llamada al LLM (optimización #7, ahorro ~8k tokens).
    info_tarifa_pre = None
    try:
        _cod_pref_ta = cod_pref.upper() if cod_pref else ""
        if _cod_pref_ta.startswith("TA"):
            cups_pre, _ = _extraer_cups_servicio(tabla_excel or "", contexto_pdf)
            if cups_pre:
                from app.services.tarifa_lookup_service import evaluar_glosa_tarifa as _evaltar
                vals_pre = _extraer_valores_glosa(tabla_excel or "")
                info_tarifa_pre = _evaltar(
                    db, eps=eps, cups=cups_pre,
                    valor_facturado=vals_pre.get("facturado", 0.0),
                    valor_objetado=0.0,
                    valor_reconocido=vals_pre.get("reconocido", 0.0),
                )
                if not info_tarifa_pre.get("encontrada"):
                    # Fallback a catálogo oficial HUS/SOAT si no hay en BD
                    from app.services.tarifas_oficiales import tarifa_a_banner_dict as _tbd
                    ofic = _tbd(cups_pre)
                    if ofic:
                        info_tarifa_pre = {
                            "encontrada": True,
                            "tarifa": ofic,
                            "valor_facturado": vals_pre.get("facturado", 0.0),
                            "valor_objetado": 0.0,
                            "valor_reconocido": vals_pre.get("reconocido", 0.0),
                            "valor_pactado_calc": ofic["valor_pactado"],
                            "recomendacion": {
                                "accion": "DEFENDER_TOTAL" if abs(vals_pre.get("facturado", 0.0) - ofic["valor_pactado"]) < max(1.0, ofic["valor_pactado"] * 0.005) else "REVISAR",
                                "titulo": "Valor oficial conocido",
                                "razon": "",
                            },
                        }
    except Exception as e:
        logger.warning(f"[{req_id}] pre-lookup tarifa falló: {e}")

    resultado = await service.analizar(
        data, contexto_pdf, contratos,
        few_shots=few_shots, info_tarifa=info_tarifa_pre,
    )
    if plantillas_gold:
        marcar_usos(db, [p.id for p in plantillas_gold])
    logger.info(
        f"[{req_id}] Análisis completado | modelo={resultado.modelo_ia} "
        f"| few_shots={len(few_shots)} | tarifa_match={bool(info_tarifa_pre and info_tarifa_pre.get('encontrada'))}"
    )

    glosa_repo = GlosaRepository(db)
    val_obj = float(re.sub(r"[^\d]", "", resultado.valor_objetado) or 0)
    val_ac = float(re.sub(r"[^\d]", "", valor_aceptado) or 0)

    # Fase 3: consultar tarifa pactada en el contrato de la EPS.
    # Solo aplica a glosas TA (tarifas) donde tengamos CUPS identificado.
    # El banner se prepend al dictamen para guiar al auditor con datos duros.
    try:
        es_ta = (resultado.codigo_glosa or "").upper().startswith("TA")
        cups_ext, _ = _extraer_cups_servicio(tabla_excel or "", contexto_pdf)
        if es_ta and cups_ext:
            from app.services.tarifa_lookup_service import (
                evaluar_glosa_tarifa,
            )
            # Extraer facturado/reconocido del texto de la glosa ("facturado
            # por $X y reconocido por $Y"). Cuando no se encuentren, val = 0.
            vals_txt = _extraer_valores_glosa(tabla_excel or "")
            val_fact = vals_txt["facturado"]
            val_rec = vals_txt["reconocido"]
            # Si no se extrajo facturado del texto, val_fact = 0.
            # El banner mostrará los datos que sí tiene sin inventar valores
            # falsos; la IA decide con los datos reales del BLOQUE 1.
            info_tarifa = evaluar_glosa_tarifa(
                db,
                eps=eps,
                cups=cups_ext,
                valor_facturado=val_fact,
                valor_objetado=val_obj,
                valor_reconocido=val_rec,
            )
            # Fallback: si no hay tarifa cargada por el coordinador, consultar
            # el catálogo oficial HUS (Res. 124/2026) + SOAT (Circular 047/2025)
            if not info_tarifa.get("encontrada"):
                from app.services.tarifas_oficiales import tarifa_a_banner_dict
                oficial = tarifa_a_banner_dict(cups_ext)
                if oficial:
                    # Construir info_tarifa sintético desde el catálogo
                    info_tarifa = {
                        "encontrada": True,
                        "tarifa": oficial,
                        "valor_facturado": val_fact,
                        "valor_objetado": val_obj,
                        "valor_reconocido": val_rec,
                        "valor_pactado_calc": oficial["valor_pactado"],
                        "recomendacion": {
                            "accion": "DEFENDER_TOTAL" if val_fact <= oficial["valor_pactado"] + 1 else "REVISAR",
                            "titulo": "✅ Valor oficial HUS/SOAT conocido — defender",
                            "razon": (
                                f"El valor oficial publicado para este CUPS es "
                                f"${oficial['valor_pactado']:,.0f} según {oficial['contrato_numero']}. "
                                "Defender este valor citando la norma institucional."
                            ),
                            "valor_a_defender": val_obj,
                            "valor_a_aceptar": 0.0,
                            "diferencia": 0.0,
                        },
                    }
            if info_tarifa.get("encontrada"):
                banner = _generar_banner_tarifa_html(info_tarifa)
                if banner:
                    resultado.dictamen = banner + (resultado.dictamen or "")
                    rec = info_tarifa.get("recomendacion") or {}
                    logger.info(
                        f"[{req_id}] Tarifa pactada: cups={cups_ext} "
                        f"fact=${val_fact:,.0f} rec=${val_rec:,.0f} "
                        f"obj=${val_obj:,.0f} accion={rec.get('accion')}"
                    )
    except Exception as e:
        logger.warning(f"[{req_id}] No se pudo agregar banner de tarifa: {e}")

    # Determinar estado y código de respuesta según aceptación
    # BUG 1 FIX: Si val_obj=0 y hay aceptacion, usar val_ac como referencia (aceptacion total)
    if val_obj == 0 and val_ac > 0:
        val_obj = val_ac
        estado = "ACEPTADA"
        cod_res_aceptacion = "RE9702"
        desc_res_aceptacion = "GLOSA ACEPTADA AL 100%"
    elif val_ac >= val_obj and val_obj > 0:
        estado = "ACEPTADA"
        cod_res_aceptacion = "RE9702"
        desc_res_aceptacion = "GLOSA ACEPTADA AL 100%"
    elif val_ac > 0:
        estado = "PARCIALMENTE_ACEPTADA"
        cod_res_aceptacion = "RE9801"
        desc_res_aceptacion = "GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE"
    else:
        estado = "RADICADA"
        cod_res_aceptacion = None
        desc_res_aceptacion = None

    # Si hay aceptación, generar dictamen completamente nuevo
    dictamen_final = resultado.dictamen
    if estado in ("ACEPTADA", "PARCIALMENTE_ACEPTADA"):
        val_rechazado = val_obj - val_ac
        
        # Obtener número de contrato vigente con la EPS para citar en el texto
        _contrato_info = get_contrato(eps)
        _num_contrato = _contrato_info.get("numero") or "CONTRATO VIGENTE ENTRE LAS PARTES"
        # Detectar el servicio concreto (nombre + CUPS) desde el texto de la glosa y el PDF
        _servicio_descr = _descripcion_servicio(
            resultado.codigo_glosa,
            texto_glosa=tabla_excel,
            contexto_pdf=contexto_pdf,
        )

        # Generar texto de aceptación apropiado
        if estado == "ACEPTADA":
            argumento_aceptacion = f"""
            <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:20px;margin:15px 0;border-radius:8px;">
                <h4 style="color:#15803d;margin:0 0 10px 0;">RESPUESTA A GLOSA</h4>
                <p style="font-size:13px;line-height:1.8;color:#166534;">
                    ESE HUS ACEPTA GLOSA TOTAL POR VALOR DE <strong>${val_ac:,.0f}</strong>,
                    CORRESPONDIENTE {_servicio_descr}. ESTO CORRESPONDE A UN MAYOR VALOR COBRADO
                    SEGÚN <strong>{_num_contrato}</strong> PACTADO ENTRE LAS PARTES. SE AJUSTAN LOS VALORES
                    DANDO CUMPLIMIENTO A ESTAS TARIFAS.
                </p>
            </div>"""
        else:
            val_en_disputa = abs(val_rechazado)  # Garantizar valor positivo
            argumento_aceptacion = f"""
            <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:20px;margin:15px 0;border-radius:8px;">
                <h4 style="color:#92400e;margin:0 0 10px 0;">RESPUESTA A GLOSA</h4>
                <p style="font-size:13px;line-height:1.8;color:#78350f;">
                    ESE HUS ACEPTA GLOSA PARCIAL POR VALOR DE <strong>${val_ac:,.0f}</strong>,
                    CORRESPONDIENTE {_servicio_descr}. ESTO CORRESPONDE A UN MAYOR VALOR COBRADO
                    SEGÚN <strong>{_num_contrato}</strong> PACTADO ENTRE LAS PARTES. SE AJUSTAN LOS VALORES
                    DANDO CUMPLIMIENTO A ESTAS TARIFAS.
                </p>
                <p style="font-size:13px;line-height:1.8;color:#78350f;">
                    EL VALOR RESTANTE DE <strong>${val_en_disputa:,.0f}</strong> NO SE ACEPTA POR LA ESE HUS
                    YA QUE SE EVIDENCIA QUE ESTE VALOR CORRESPONDE AL VALOR PACTADO ENTRE LAS PARTES.
                </p>
            </div>"""
        
        # Tabla de encabezado con código de glosa, valor objetado y código de respuesta
        tabla_codigos = f"""
        <table style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:15px;background:white;border:1px solid #cbd5e1;">
            <thead>
                <tr style="background:#0f172a;color:white;">
                    <th style="padding:10px;text-align:center;font-weight:700;letter-spacing:.3px;">CÓDIGO GLOSA</th>
                    <th style="padding:10px;text-align:center;font-weight:700;letter-spacing:.3px;">VALOR OBJETADO</th>
                    <th style="padding:10px;text-align:center;font-weight:700;letter-spacing:.3px;">CÓDIGO RESPUESTA</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="padding:10px;text-align:center;font-weight:700;border-bottom:1px solid #e2e8f0;">{resultado.codigo_glosa}</td>
                    <td style="padding:10px;text-align:center;font-weight:700;color:#0f172a;border-bottom:1px solid #e2e8f0;">$ {val_obj:,.0f}</td>
                    <td style="padding:10px;text-align:center;border-bottom:1px solid #e2e8f0;">
                        <b>{cod_res_aceptacion}</b><br>
                        <span style="font-size:10px;color:#64748b;">{desc_res_aceptacion}</span>
                    </td>
                </tr>
            </tbody>
        </table>"""

        # Tabla resumen de valores (VALOR OBJETADO / ACEPTADO / EN DISPUTA)
        tabla_valores = f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;margin-top:15px;">
            <div style="font-weight:700;color:#334155;margin-bottom:10px;font-size:11px;letter-spacing:.4px;text-transform:uppercase;">Resumen de valores</div>
            <table style="width:100%;border-collapse:collapse;font-size:12px;">
                <tr>
                    <td style="padding:6px 8px;color:#475569;">Valor objetado</td>
                    <td style="padding:6px 8px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums;">$ {val_obj:,.0f}</td>
                </tr>
                <tr>
                    <td style="padding:6px 8px;color:#047857;">Valor aceptado</td>
                    <td style="padding:6px 8px;text-align:right;font-weight:700;color:#047857;font-variant-numeric:tabular-nums;">$ {val_ac:,.0f}</td>
                </tr>"""
        if estado == "PARCIALMENTE_ACEPTADA":
            tabla_valores += f"""
                <tr>
                    <td style="padding:6px 8px;color:#b91c1c;">Valor en disputa</td>
                    <td style="padding:6px 8px;text-align:right;font-weight:700;color:#b91c1c;font-variant-numeric:tabular-nums;">$ {val_en_disputa:,.0f}</td>
                </tr>"""
        tabla_valores += """
            </table>
        </div>"""

        # Dictamen completo: tabla de códigos + argumento narrativo + resumen de valores
        dictamen_final = tabla_codigos + argumento_aceptacion + tabla_valores

    # Crear glosa con el resultado
    tipo_final = f"RESPUESTA {cod_res_aceptacion}" if cod_res_aceptacion else resultado.tipo
    # Derivar campos nuevos para historial detallado
    _cup_ext, _servicio_ext = _extraer_cups_servicio(tabla_excel or "", contexto_pdf)
    # Extraer código de respuesta del tipo (ej. "RESPUESTA RE9901" -> "RE9901")
    _cod_resp_m = re.search(r"\bRE\d{4}\b", tipo_final or "")
    _cod_resp = _cod_resp_m.group(0) if _cod_resp_m else (cod_res_aceptacion or "")
    glosa = glosa_repo.crear(
        eps=eps,
        paciente=resultado.paciente,
        codigo_glosa=resultado.codigo_glosa,
        valor_objetado=val_obj,
        valor_aceptado=val_ac,
        etapa=etapa,
        estado=estado,
        dictamen=dictamen_final,
        dias_restantes=resultado.dias_restantes,
        modelo_ia=resultado.modelo_ia,
        score=resultado.score,
        numero_radicado=numero_radicado,
        factura=numero_factura,
        texto_glosa_original=tabla_excel,
        codigo_respuesta=_cod_resp,
        cups_servicio=_cup_ext or None,
        servicio_descripcion=_servicio_ext or None,
        concepto_glosa=_concepto_glosa(resultado.codigo_glosa),
        fecha_recepcion=data.fecha_recepcion,
    )

    if estado == "RADICADA":
        glosa_repo.actualizar_estado(glosa.id, "RESPONDIDA", responsable=current_user.email)

    logger.info(f"[{req_id}] Glosa guardada ID={glosa.id} | estado={estado}")
    
    # Retornar resultado actualizado con el nuevo tipo
    resultado.tipo = tipo_final
    resultado.dictamen = dictamen_final
    resultado.glosa_id = glosa.id
    # Guardar snapshot inicial del dictamen en historial de versiones
    try:
        from app.api.routers.versiones import guardar_version
        guardar_version(
            db=db, glosa_id=glosa.id, dictamen_html=dictamen_final,
            accion="CREAR", autor_email=current_user.email,
        )
    except Exception as _e:
        logger.warning(f"No se pudo guardar version: {_e}")
    return resultado


_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/")
def root():
    # no-store a nivel servidor: sortea service workers viejos que sirven
    # HTML cacheado. Esto es crítico cuando se despliegan cambios de UI.
    return FileResponse("static/index.html", headers=_NO_STORE_HEADERS)


@app.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse("static/manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def pwa_service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")


def _generar_icono_pwa(size: int) -> bytes:
    """Genera un icono PWA cuadrado con el azul institucional y 'HUS'."""
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO
    img = Image.new("RGB", (size, size), "#0b5d8a")
    draw = ImageDraw.Draw(img)
    # Círculo de acento
    pad = int(size * 0.08)
    draw.ellipse([pad, pad, size - pad, size - pad], outline="#ffffff", width=max(2, size // 80))
    # Texto "HUS"
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.42))
    except Exception:
        font = ImageFont.load_default()
    texto = "HUS"
    bbox = draw.textbbox((0, 0), texto, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2 - int(size * 0.03)), texto, fill="#ffffff", font=font)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@app.get("/icon-192.png")
def icon_192():
    from fastapi.responses import Response
    return Response(content=_generar_icono_pwa(192), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/icon-512.png")
def icon_512():
    from fastapi.responses import Response
    return Response(content=_generar_icono_pwa(512), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/importar-masiva")
def importar_masiva():
    return FileResponse("static/importar-masiva.html", headers=_NO_STORE_HEADERS)


@app.get("/importar-recepcion")
def importar_recepcion_page():
    return FileResponse("static/importar-recepcion.html", headers=_NO_STORE_HEADERS)


@app.get("/sw.js")
def service_worker():
    """El SW debe servirse SIEMPRE con no-store; si el navegador cachea sw.js
    viejo, los clientes quedan pegados en una versión anterior."""
    return FileResponse(
        "static/sw.js",
        media_type="application/javascript",
        headers=_NO_STORE_HEADERS,
    )


@app.get("/reset-sw.html")
def reset_sw():
    """Página de emergencia que desregistra cualquier service worker viejo y
    limpia el cache del navegador. Útil cuando un usuario queda pegado con
    una UI vieja. Uso: abrir https://.../reset-sw.html y esperar 3 seg."""
    from fastapi.responses import HTMLResponse
    html = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Limpiando cache…</title>
<style>body{font-family:sans-serif;max-width:600px;margin:80px auto;padding:20px;
text-align:center;color:#1f2937}h1{color:#059669}.ok{color:#059669;font-size:48px}</style>
</head><body>
<h1>🧹 Limpiando caché del navegador…</h1>
<p id="status">Procesando…</p>
<script>
(async () => {
  const log = (msg) => document.getElementById('status').innerHTML += '<br>' + msg;
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      for (const r of regs) { await r.unregister(); log('✓ SW desregistrado'); }
    }
    if ('caches' in window) {
      const keys = await caches.keys();
      for (const k of keys) { await caches.delete(k); log('✓ Cache borrado: ' + k); }
    }
    log('<br><span class="ok">✅ Listo</span>');
    log('<p>Redirigiendo a la aplicación en 2 segundos…</p>');
    setTimeout(() => { location.href = '/'; }, 2000);
  } catch (e) {
    log('⚠ Error: ' + e.message);
  }
})();
</script></body></html>"""
    return HTMLResponse(content=html, headers=_NO_STORE_HEADERS)


@app.get("/presentacion")
def presentacion_ia():
    """Presentación institucional del sistema IA (pública, sin login)."""
    return FileResponse("static/presentacion-ia.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": cfg.app_version,
        "banner": (cfg.banner_capacitacion or "").strip(),
    }


@app.get("/debug/sentry-test", include_in_schema=False)
def sentry_test(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Endpoint para verificar que Sentry captura errores.

    Solo accesible por SUPER_ADMIN. Lanza una excepción intencional —
    debería aparecer en el dashboard de Sentry a los pocos segundos.
    """
    if current_user.rol != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Solo SUPER_ADMIN puede correr este test")
    # Excepción intencional para verificar integración Sentry
    raise RuntimeError(
        f"[SENTRY_TEST] Test de integración disparado por {current_user.email} "
        f"en {datetime.now().isoformat()}. Si ves este mensaje en Sentry, funciona correctamente."
    )


@app.post("/pdf/ocr")
async def pdf_ocr(
    archivo: UploadFile = File(...),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Sube un PDF y devuelve su texto. Si el PDF es escaneado y hay
    ANTHROPIC_API_KEY configurada, usa Claude Vision como OCR."""
    contenido = await archivo.read()
    if contenido[:4] != b"%PDF":
        raise HTTPException(400, "El archivo no es un PDF válido")
    if len(contenido) > 30_000_000:
        raise HTTPException(400, "PDF muy grande (>30 MB)")

    from app.services.pdf_service import PdfService
    pdf_svc = PdfService()
    texto, metodo = await pdf_svc.extraer_con_ocr(
        contenido,
        anthropic_api_key=cfg.anthropic_api_key,
        anthropic_model=cfg.anthropic_model,
    )
    return {
        "metodo": metodo,
        "caracteres": len(texto),
        "texto": texto,
        "archivo": archivo.filename,
    }
