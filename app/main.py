import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import engine, Base, SessionLocal
from app.models.db import ContratoRecord, UsuarioRecord
from app.core.config import get_settings, check_security_config
from app.auth import get_password_hash
from app.core.logging_utils import logger
from app.core.sentry_init import init_sentry

# Sentry debe inicializarse ANTES de cualquier import que pueda fallar.
# Si SENTRY_DSN no está definido, no hace nada.
init_sentry()


# Ronda 50 Paso 9: parsers extraídos a app/utils/parsers_glosa.py
# para reducir main.py de 1757 → 1280 líneas.
# Re-exports para otros módulos (`from app.main import _extraer_cups_servicio`)
from app.utils.parsers_glosa import (
    _detectar_servicio_desde_texto,
    _extraer_motivo_glosa,
    _concepto_glosa,
    _extraer_valores_glosa,
    _generar_banner_tarifa_html,
    _extraer_cups_servicio,
    _descripcion_servicio,
)

# __all__ declara los nombres públicos del módulo — pyflakes y otras
# herramientas reconocen los re-exports como "usados" para este fin.
__all__ = [
    "_detectar_servicio_desde_texto",
    "_extraer_motivo_glosa",
    "_concepto_glosa",
    "_extraer_valores_glosa",
    "_generar_banner_tarifa_html",
    "_extraer_cups_servicio",
    "_descripcion_servicio",
]


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
        # Nota crédito (commit cfafe7d / hotfix 4adbb7b)
        ("numero_nota_credito", "VARCHAR(60)"),
        ("fecha_nota_credito", "TIMESTAMP WITH TIME ZONE"),
        ("valor_nota_credito", "DOUBLE PRECISION DEFAULT 0"),
        ("nota_credito_observacion", "TEXT"),
        # Stale-detection del dictamen vs tarifas/contratos cargados después.
        ("dictamen_generado_en", "TIMESTAMP WITH TIME ZONE"),
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

    # Índice idempotente sobre numero_nota_credito (declarado index=True en
    # el modelo). create_all() no lo agrega para tablas pre-existentes.
    try:
        if _tiene_tabla("historial") and _tiene_columna("historial", "numero_nota_credito"):
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_historial_numero_nota_credito "
                "ON historial (numero_nota_credito)"
            ))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN índice nota_credito: {e}")

    # Resize de columnas TEXT/VARCHAR cuyo tamaño original quedó corto.
    # Caso 27-abr-2026: importación de Excel falla con
    # "value too long for type character varying(50)" en EPS oficial
    # "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO
    # BUCARAMANG" (71 chars). Ampliamos a 300 para tener margen.
    # Los ALTER TYPE en Postgres son seguros mientras la nueva
    # longitud sea >= a la actual y los datos existentes quepan.
    if not _is_sqlite:
        _HISTORIAL_RESIZE = [
            ("eps", "VARCHAR(300)"),
            ("paciente", "VARCHAR(300)"),
            ("etapa", "VARCHAR(120)"),
            ("estado", "VARCHAR(50)"),
            ("modelo_ia", "VARCHAR(120)"),
        ]
        for col_name, col_ddl in _HISTORIAL_RESIZE:
            try:
                if (
                    _tiene_tabla("historial")
                    and _tiene_columna("historial", col_name)
                ):
                    db.execute(text(
                        f"ALTER TABLE historial "
                        f"ALTER COLUMN {col_name} TYPE {col_ddl}"
                    ))
                    db.commit()
            except Exception as e:
                logger.warning(f"MIGRACIÓN resize {col_name}: {e}")

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

    # R57 P2: scheduler diario de mantenimiento (3 AM) — purga
    # ai_cache > 30d, ai_calls > 90d, papelera > 30d. No bloquea
    # startup ni rompe si falla — el mantenimiento es secundario.
    try:
        from app.services.mantenimiento_scheduler import iniciar_scheduler as iniciar_mant_scheduler
        iniciar_mant_scheduler()
    except Exception as _e:
        logger.warning(f"No se pudo iniciar scheduler de mantenimiento: {_e}")

    # Reindex diario del share de soportes (2 AM) + build inicial al
    # arrancar para que el primer gestor del día encuentre el índice
    # caliente. No bloquea startup si el mount aún no está disponible
    # — el healthz lo refleja y el reintento ocurre al día siguiente.
    try:
        from app.services.soportes_reindex_scheduler import iniciar_scheduler as iniciar_soportes_scheduler
        iniciar_soportes_scheduler()
    except Exception as _e:
        logger.warning(f"No se pudo iniciar scheduler de soportes: {_e}")

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
    try:
        from app.services.mantenimiento_scheduler import detener_scheduler as detener_mant
        detener_mant()
    except Exception:
        pass
    try:
        from app.services.soportes_reindex_scheduler import detener_scheduler as detener_soportes
        detener_soportes()
    except Exception:
        pass
    logger.info("=== APLICACIÓN CERRADA ===")


cfg = get_settings()


from app.core.rate_limit import limiter  # noqa: E402

app = FastAPI(
    title="Motor Glosas HUS",
    description="""
## API del Motor de Glosas - ESE Hospital Universitario de Santander

Sistema automatizado de defensa de glosas médicas con asistencia de IA.

### Funcionalidades
- **Análisis automático** de glosas mediante Groq/Anthropic
- **Detección de extemporaneidad** (20 días hábiles - Art. 57 Ley 1438/2011 + Manual Único Res. 2284/2023)
- **Plantillas especializadas** por tipo de glosa
- **Gestión de contratos** EPS con tarifas específicas
- **Historial y métricas** de glosas

### Autenticación
Todos los endpoints excepto `/health` requieren token JWT.
Obtener token en `/api/auth/login`.

### Códigos de Respuesta (Resolución 3047/2008 - Normativa Colombiana)
| Código | Descripción |
|--------|-------------|
| RE9502 | Glosa no procede - Aceptación tácita de la factura (Art. 57 Ley 1438/2011) |
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

# R61 P2: GZip para responses >1KB. Reduce ~70% el peso de payloads
# JSON grandes (historial-paginado, dashboard, dictamenes HTML largos).
# El umbral 1024 evita comprimir respuestas pequeñas donde el overhead
# de CPU supera el ahorro de bytes.
app.add_middleware(GZipMiddleware, minimum_size=1024)


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
from app.api.routers.tarifa_liquidador import router as tarifa_liquidador_router
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
app.include_router(tarifa_liquidador_router)
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
from app.api.routers.pwa import router as pwa_router
app.include_router(pwa_router)
from app.api.routers.pdf import router as pdf_router
app.include_router(pdf_router)
from app.api.routers.health import router as health_router
app.include_router(health_router)
from app.api.routers.analizar import router as analizar_router
app.include_router(analizar_router)
from app.api.routers.firma import router as firma_router
app.include_router(firma_router)
from app.api.routers.sugerencias import router as sugerencias_router
app.include_router(sugerencias_router)
from app.api.routers.tareas_diarias import router as tareas_diarias_router
app.include_router(tareas_diarias_router)
from app.api.routers.nota_credito import router as nota_credito_router
app.include_router(nota_credito_router)
from app.api.routers.auditor_preview import router as auditor_preview_router
app.include_router(auditor_preview_router)
from app.api.routers.soportes import router as soportes_auto_router
app.include_router(soportes_auto_router)






