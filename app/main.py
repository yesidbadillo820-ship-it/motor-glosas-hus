import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

MESES_ES = {
    "January": "ENERO",
    "February": "FEBRERO",
    "March": "MARZO",
    "April": "ABRIL",
    "May": "MAYO",
    "June": "JUNIO",
    "July": "JULIO",
    "August": "AGOSTO",
    "September": "SEPTIEMBRE",
    "October": "OCTUBRE",
    "November": "NOVIEMBRE",
    "December": "DICIEMBRE",
}


def fecha_hoy_espanol() -> str:
    now = datetime.now()
    mes_en = now.strftime("%B")
    return f"{now.day} DE {MESES_ES.get(mes_en, mes_en.upper())} DE {now.year}"


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.correlation import CorrelationIdMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import engine, Base, SessionLocal
from app.models.db import ContratoRecord, UsuarioRecord
from app.core.config import get_settings, check_security_config
from app.auth import get_password_hash
from app.core.logging_utils import logger
from app.core.sentry_init import init_sentry
from app.services.posthog_service import init_posthog

# Sentry debe inicializarse ANTES de cualquier import que pueda fallar.
# Si SENTRY_DSN no está definido, no hace nada.
init_sentry()

# PostHog product analytics — server-side event tracking.
# Si POSTHOG_API_KEY no está definida, no hace nada.
init_posthog()


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
    "FOMAG": "CONTRATO No. 12076-359-2025 (FIDUPREVISORA – Acta 012). TARIFA: SOAT -20%.",
    "POLICIA NACIONAL": "CONTRATO No. 068-5-200004-26 (SFI 004). TARIFA: UVB – 8%.",
    "SUMIMEDICAL": "TARIFARIO ESE HUS 2025 — SUMIMEDICAL. TARIFA: SOAT -15%.",
    "DISPENSARIO MEDICO": "CONTRATO No. 440-DIGSA/DMBUG-2025. TARIFA: SOAT/SMLV -20%.",
    "SALUD MIA": "CONTRATO CSA2025EVE3A005. TARIFA: SOAT -15%.",
    "AURORA": "CONTRATO GID-ARL-0090 — ARL + VIDA AP (2024). TARIFA: PROPIAS HUS / SOAT -3% SUBSIDIARIA.",
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.",
}


def _sembrar_contratos_default(db, *, force_reseed: bool = False) -> None:
    """Siembra los contratos default SOLO cuando faltan en la BD.

    La BD es la fuente de verdad: los textos editados por la coordinación
    desde la UI (POST /contratos) NO se sobrescriben en cada arranque.
    Antes este seed hacía `existente.detalles = v` en cada boot (revirtiendo
    las ediciones de las 14 EPS default) y además BORRABA cualquier contrato
    cuyo EPS no estuviera en CONTRATOS_DEFAULT — perdiendo contratos creados
    por el equipo. Auditoría jun-2026, P1 #4.

    FORCE_RESEED_CONTRATOS=1 restaura la re-sincronización masiva
    (sobrescribe textos con el default y elimina los no-default), espejo
    del toggle FORCE_RESEED_USERS para usuarios.
    """
    for k, v in CONTRATOS_DEFAULT.items():
        existente = db.query(ContratoRecord).filter(ContratoRecord.eps == k).first()
        if not existente:
            db.add(ContratoRecord(eps=k, detalles=v))
            logger.info(f"Contrato default sembrado: {k}")
        elif force_reseed and existente.detalles != v:
            logger.warning(f"[FORCE_RESEED_CONTRATOS] {k}: detalles re-sincronizados al default")
            existente.detalles = v

    if force_reseed:
        eps_default = set(CONTRATOS_DEFAULT.keys())
        for contrato in db.query(ContratoRecord).all():
            if contrato.eps not in eps_default:
                logger.warning(
                    f"[FORCE_RESEED_CONTRATOS] ELIMINANDO contrato no-default: {contrato.eps}"
                )
                db.delete(contrato)


# Índices calientes de historial, creados de forma idempotente en el
# lifespan (CREATE INDEX IF NOT EXISTS) porque create_all() no agrega
# índices a tablas pre-existentes. Los nombres DEBEN coincidir con los
# Index() declarados en GlosaRecord.__table_args__ (app/models/db.py)
# para que ambos mecanismos converjan sin duplicados.
_INDICES_HISTORIAL = [
    ("ix_historial_creado_en", "creado_en"),
    ("ix_historial_factura", "factura"),
    ("ix_historial_workflow_state", "workflow_state"),
]

# El chequeo de motores duplicados corre UNA vez por proceso: en las pruebas
# el lifespan arranca cientos de veces y recorrer la tabla de procesos en
# cada una sería puro peaje.
_MOTOR_YA_CHEQUEADO = False

# Huella de la plantilla ya corregida: la que pone adelante la norma vigente
# (Res. 2284/2023) y deja la 3047/2008 como antecedente. Sirve para saber si
# una plantilla sembrada en la base todavía trae el texto viejo, sin
# reescribir a ciegas las que el auditor ya aprobó.
_MARCAS_NORMA_VIGENTE = (
    "SUSTITUYÓ EL ANEXO",
    "EN REEMPLAZO DEL ANEXO",
    "(RESOLUCIÓN 2284 DE 2023).",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== INICIANDO APLICACIÓN ===")
    check_security_config()

    # Conexión inicial DB con retry — Render Free Postgres a veces tiene
    # SSL drops o pausas por inactividad. Antes el startup fallaba en
    # frío y el contenedor nunca respondía. Ahora reintentamos hasta 5
    # veces con backoff exponencial (2s, 4s, 8s, 16s, 32s = ~1 min total).
    import time as _time
    from sqlalchemy.exc import OperationalError, DBAPIError

    _max_intentos_db = 5
    for _intento in range(1, _max_intentos_db + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info(f"Base de datos inicializada (intento {_intento})")
            break
        except (OperationalError, DBAPIError) as e:
            if _intento >= _max_intentos_db:
                logger.error(
                    f"DB inalcanzable tras {_max_intentos_db} intentos: {e}. "
                    "El motor va a arrancar igual; los endpoints que necesiten "
                    "DB van a devolver 503 hasta que se resuelva."
                )
                break
            espera = 2**_intento
            logger.warning(
                f"DB no disponible (intento {_intento}/{_max_intentos_db}): "
                f"{type(e).__name__}. Reintento en {espera}s."
            )
            _time.sleep(espera)

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
            db.execute(
                text(f"ALTER TABLE usuarios ADD COLUMN creado_en {_TS_TIPO} DEFAULT {_TS_DEFAULT}")
            )
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN creado_en: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "activo"):
            logger.warning("MIGRACIÓN: Agregando columna 'activo' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN activo INTEGER DEFAULT 1"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN activo: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "rol"):
            logger.warning("MIGRACIÓN: Agregando columna 'rol' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN rol VARCHAR(50) DEFAULT 'AUDITOR'"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN rol: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "workload"):
            logger.warning("MIGRACIÓN: Agregando columna 'workload' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN workload INTEGER DEFAULT 100"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN workload: {e}")

    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "nota_workflow"):
            logger.warning("MIGRACIÓN: Agregando columna 'nota_workflow' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN nota_workflow TEXT"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN nota_workflow: {e}")

    # Campo must_change_password (forzar cambio en primer login)
    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "must_change_password"):
            logger.warning("MIGRACIÓN: Agregando columna 'must_change_password' a tabla usuarios")
            db.execute(
                text(
                    "ALTER TABLE usuarios ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"
                )
            )
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN must_change_password: {e}")

    # Campo password_changed_at (timestamp último cambio)
    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "password_changed_at"):
            logger.warning("MIGRACIÓN: Agregando columna 'password_changed_at' a tabla usuarios")
            db.execute(text(f"ALTER TABLE usuarios ADD COLUMN password_changed_at {_TS_TIPO}"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN password_changed_at: {e}")

    # Campo equipo (agrupación de usuarios que comparten bandeja)
    try:
        if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", "equipo"):
            logger.warning("MIGRACIÓN: Agregando columna 'equipo' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN equipo VARCHAR(50)"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN equipo: {e}")

    try:
        if _tiene_tabla("historial") and not _tiene_columna("historial", "numero_radicado"):
            logger.warning("MIGRACIÓN: Agregando columna 'numero_radicado' a historial")
            db.execute(text("ALTER TABLE historial ADD COLUMN numero_radicado VARCHAR(50)"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN numero_radicado: {e}")

    try:
        if _tiene_tabla("historial") and not _tiene_columna("historial", "request_id"):
            logger.warning("MIGRACIÓN: Agregando columnas a historial")
            db.execute(text("ALTER TABLE historial ADD COLUMN request_id VARCHAR(50)"))
            db.execute(text("ALTER TABLE historial ADD COLUMN nota_workflow VARCHAR(500)"))
            db.execute(
                text("ALTER TABLE historial ADD COLUMN prioridad VARCHAR(50) DEFAULT 'NORMAL'")
            )
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
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
        # Evidencia de radicación ante la entidad (marcar-radicada)
        ("radicado_en", "TIMESTAMP WITH TIME ZONE"),
        ("radicado_por", "VARCHAR(200)"),
        ("radicado_observacion", "TEXT"),
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
                col_ddl_adapted = (
                    col_ddl.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP")
                    if _is_sqlite
                    else col_ddl
                )
                col_ddl_adapted = (
                    col_ddl_adapted.replace("DOUBLE PRECISION", "REAL")
                    if _is_sqlite
                    else col_ddl_adapted
                )
                db.execute(text(f"ALTER TABLE historial ADD COLUMN {col_name} {col_ddl_adapted}"))
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"MIGRACIÓN {col_name}: {e}")

    # Glosas ADRES: columnas que se agregaron después del primer cargue. Sin
    # esto, un servidor que ya tenía el paquete 31068 cargado revienta con
    # "no such column" apenas alguien abre la pantalla, porque create_all()
    # crea tablas nuevas pero NO agrega columnas a las que ya existen.
    _ADRES_MISSING_COLUMNS = [
        # (tabla, columna, tipo)
        ("glosas_adres", "glosa_total", "BOOLEAN DEFAULT 0"),
        ("glosas_adres", "centro_costos_por", "VARCHAR(200)"),
        ("glosas_adres", "requiere_asignacion", "BOOLEAN DEFAULT 0"),
        ("glosas_adres", "area_sugerida", "VARCHAR(60)"),
        ("glosas_adres", "motivo_area", "TEXT"),
        ("glosas_adres", "area_asignada_por", "VARCHAR(200)"),
        ("glosas_adres", "area_asignada_en", "TIMESTAMP WITH TIME ZONE"),
        ("paquetes_adres", "catalogo_centros", "TEXT"),
        ("glosas_adres", "cuenta_valor", "BOOLEAN DEFAULT 1"),
        ("facturas_adres", "valor_glosado_oficial", "DOUBLE PRECISION"),
    ]
    for tabla, col_name, col_ddl in _ADRES_MISSING_COLUMNS:
        try:
            if _tiene_tabla(tabla) and not _tiene_columna(tabla, col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a {tabla}")
                col_ddl_adapted = (
                    col_ddl.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP")
                    if _is_sqlite
                    else col_ddl
                )
                col_ddl_adapted = (
                    col_ddl_adapted.replace("DOUBLE PRECISION", "REAL")
                    if _is_sqlite
                    else col_ddl_adapted
                )
                db.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {col_name} {col_ddl_adapted}"))
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"MIGRACIÓN {tabla}.{col_name}: {e}")

    # Las glosas que ya estaban cargadas no traen marcada la glosa total (la
    # columna nació después). Se deduce igual que al importar: sin causal
    # propia, es el desglose de una reclamación glosada entera por el FURIPS.
    # Se corrige por el contenido, no por si la columna está en NULL: el ALTER
    # la creó con DEFAULT 0, así que las filas viejas quedaron en 0 aunque sean
    # glosa total. Es idempotente: la segunda vez no encuentra nada que hacer.
    # OJO: acá NO se usa `_tiene_columna`, porque el inspector tiene cacheada la
    # lista de columnas de ANTES del ALTER de arriba y diría que no existe. Si
    # de verdad falta, la consulta falla y queda el aviso en el log.
    try:
        if _tiene_tabla("glosas_adres"):
            sin_marcar = db.execute(
                text(
                    "SELECT COUNT(*) FROM glosas_adres "
                    "WHERE (causal_codigo IS NULL OR TRIM(causal_codigo) = '') "
                    "  AND (glosa_total IS NULL OR glosa_total = 0)"
                )
            ).scalar()
            if sin_marcar:
                logger.warning(f"MIGRACIÓN: marcando glosa_total en {sin_marcar} glosa(s) ADRES")
                db.execute(
                    text(
                        "UPDATE glosas_adres SET glosa_total = 1 "
                        "WHERE (causal_codigo IS NULL OR TRIM(causal_codigo) = '') "
                        "  AND (glosa_total IS NULL OR glosa_total = 0)"
                    )
                )
                db.execute(
                    text(
                        "UPDATE glosas_adres SET glosa_total = 0 "
                        "WHERE causal_codigo IS NOT NULL AND TRIM(causal_codigo) <> '' "
                        "  AND glosa_total IS NULL"
                    )
                )
                db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN glosa_total (relleno): {e}")

    # `facturas_adres` es tabla nueva: create_all() la crea vacía. Los paquetes
    # que ya estaban cargados no tendrían ni una factura y la lista de trabajo
    # saldría en blanco. Se rellena desde las glosas que ya hay.
    try:
        if _tiene_tabla("facturas_adres") and _tiene_tabla("glosas_adres"):
            faltan = db.execute(
                text(
                    "SELECT COUNT(*) FROM (SELECT DISTINCT paquete_id, factura_clave "
                    "FROM glosas_adres g WHERE NOT EXISTS (SELECT 1 FROM facturas_adres f "
                    "WHERE f.paquete_id = g.paquete_id AND f.factura_clave = g.factura_clave)) x"
                )
            ).scalar()
            if faltan:
                logger.warning(f"MIGRACIÓN: creando {faltan} factura(s) ADRES para la lista")
                db.execute(
                    text(
                        "INSERT INTO facturas_adres "
                        "(paquete_id, factura_clave, factura, radicacion, doc_victima, "
                        " gestor, medico, estado) "
                        "SELECT g.paquete_id, g.factura_clave, MIN(g.factura), "
                        "       MIN(g.radicacion), MIN(g.doc_victima), MIN(g.gestor), "
                        "       MIN(g.medico), 'PENDIENTE' "
                        "FROM glosas_adres g "
                        "WHERE NOT EXISTS (SELECT 1 FROM facturas_adres f "
                        "  WHERE f.paquete_id = g.paquete_id "
                        "    AND f.factura_clave = g.factura_clave) "
                        "GROUP BY g.paquete_id, g.factura_clave"
                    )
                )
                # Las que ya traían alguna decisión no están «pendientes».
                db.execute(
                    text(
                        "UPDATE facturas_adres SET estado = 'EN PROCESO' "
                        "WHERE estado = 'PENDIENTE' AND EXISTS ("
                        "  SELECT 1 FROM glosas_adres g "
                        "  WHERE g.paquete_id = facturas_adres.paquete_id "
                        "    AND g.factura_clave = facturas_adres.factura_clave "
                        "    AND g.decision IS NOT NULL AND TRIM(g.decision) <> '')"
                    )
                )
                db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN facturas_adres (relleno): {e}")

    # Índice idempotente sobre numero_nota_credito (declarado index=True en
    # el modelo). create_all() no lo agrega para tablas pre-existentes.
    try:
        if _tiene_tabla("historial") and _tiene_columna("historial", "numero_nota_credito"):
            db.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_historial_numero_nota_credito "
                    "ON historial (numero_nota_credito)"
                )
            )
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN índice nota_credito: {e}")

    # Índices idempotentes para caminos calientes de historial (auditoría
    # jun-2026 P2 #10): /historial ordena por creado_en, "responder por
    # factura" filtra por factura y el tablero de workflow por
    # workflow_state. Mismo mecanismo que el índice de nota_credito; los
    # nombres coinciden con los Index() de GlosaRecord.__table_args__.
    for _ix_nombre, _ix_col in _INDICES_HISTORIAL:
        try:
            if _tiene_tabla("historial") and _tiene_columna("historial", _ix_col):
                db.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {_ix_nombre} ON historial ({_ix_col})")
                )
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"MIGRACIÓN índice {_ix_nombre}: {e}")

    # Pre-auditoría v2: la tabla `preaud_facturas` cambió de forma
    # oficio-céntrica (Modelo A, con `oficio_id`) a factura canónica (Modelo B,
    # con `num_subsanacion`). create_all() NO altera una tabla existente, así
    # que si quedó el esquema viejo Y está vacía, la recreamos con la forma
    # nueva. Si tuviera datos, se avisa para migración manual (no se destruye).
    try:
        if (
            _tiene_tabla("preaud_facturas")
            and _tiene_columna("preaud_facturas", "oficio_id")
            and not _tiene_columna("preaud_facturas", "num_subsanacion")
        ):
            _n_preaud = db.execute(text("SELECT COUNT(*) FROM preaud_facturas")).scalar() or 0
            if _n_preaud == 0:
                logger.warning(
                    "MIGRACIÓN pre-auditoría: recreando preaud_facturas con el esquema v2"
                )
                db.execute(text("DROP TABLE preaud_facturas"))
                db.commit()
                from app.models.db import FacturaPreauditoriaRecord

                FacturaPreauditoriaRecord.__table__.create(bind=engine)
            else:
                logger.warning(
                    "preaud_facturas tiene datos con esquema v1; requiere migración manual a v2"
                )
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN pre-auditoría v2: {e}")

    # Pre-auditoría: la observación que escribe el auditor ahora también queda
    # en el historial de la factura (antes solo se guardaba el motivo de las
    # devoluciones y lo escrito al radicar se perdía).
    try:
        if _tiene_tabla("preaud_factura_eventos") and not _tiene_columna(
            "preaud_factura_eventos", "observaciones"
        ):
            logger.warning("MIGRACIÓN pre-auditoría: agregando observaciones a los eventos")
            db.execute(text("ALTER TABLE preaud_factura_eventos ADD COLUMN observaciones TEXT"))
            db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN pre-auditoría observaciones: {e}")

    # Pre-auditoría: el mismo envío puede volver en un oficio posterior —
    # facturación reenvía las subsanaciones con el MISMO número de envío
    # (caso real 30-07-2026). El candado único pasa de (envio) a
    # (envio, oficio_id): sigue bloqueando el doble clic en el mismo oficio.
    try:
        if _tiene_tabla("preaud_envios_cargados"):
            from sqlalchemy import inspect as _sa_inspect

            _idx_envio = next(
                (
                    i
                    for i in _sa_inspect(engine).get_indexes("preaud_envios_cargados")
                    if i.get("name") == "ix_preaud_envio_cargado"
                ),
                None,
            )
            _cols = list((_idx_envio or {}).get("column_names") or [])
            _es_correcto = (
                _idx_envio is not None
                and _cols == ["envio", "oficio_id"]
                and bool(_idx_envio.get("unique"))
            )
            # Se repara SIEMPRE que el candado no sea el correcto: ausente
            # (p. ej. un arranque anterior murió entre el DROP y el CREATE —
            # en SQLite el DDL no es transaccional), con la forma vieja
            # (solo envio), o recreado a mano sin UNIQUE. Así la migración
            # se auto-repara en el siguiente arranque en vez de dejar la
            # tabla sin candado para siempre.
            if not _es_correcto:
                logger.warning(
                    "MIGRACIÓN pre-auditoría: candado de envíos por oficio (envio, oficio_id)"
                )
                if _idx_envio is not None:
                    db.execute(text("DROP INDEX ix_preaud_envio_cargado"))
                # Si la tabla estuvo un tiempo sin candado pudieron colarse
                # duplicados exactos (doble clic): se retiran conservando la
                # fila más antigua, o el índice único no se podría crear.
                db.execute(
                    text(
                        "DELETE FROM preaud_envios_cargados WHERE id NOT IN "
                        "(SELECT MIN(id) FROM preaud_envios_cargados "
                        "GROUP BY envio, oficio_id)"
                    )
                )
                db.execute(
                    text(
                        "CREATE UNIQUE INDEX ix_preaud_envio_cargado "
                        "ON preaud_envios_cargados (envio, oficio_id)"
                    )
                )
                db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"MIGRACIÓN pre-auditoría envíos por oficio: {e}")

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
                if _tiene_tabla("historial") and _tiene_columna("historial", col_name):
                    db.execute(
                        text(f"ALTER TABLE historial ALTER COLUMN {col_name} TYPE {col_ddl}")
                    )
                    db.commit()
            except Exception as e:
                try:
                    db.rollback()
                except Exception:
                    pass
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
            try:
                db.rollback()
            except Exception:
                pass
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
                col_ddl_adapted = (
                    col_ddl.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMP")
                    if _is_sqlite
                    else col_ddl
                )
                db.execute(
                    text(f"ALTER TABLE conciliaciones ADD COLUMN {col_name} {col_ddl_adapted}")
                )
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
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
            if _tiene_tabla("tarifas_contratadas") and not _tiene_columna(
                "tarifas_contratadas", col_name
            ):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a tarifas_contratadas")
                col_ddl_adapted = (
                    col_ddl.replace("DOUBLE PRECISION", "REAL") if _is_sqlite else col_ddl
                )
                db.execute(
                    text(f"ALTER TABLE tarifas_contratadas ADD COLUMN {col_name} {col_ddl_adapted}")
                )
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
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
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"MIGRACIÓN conceptos_glosa {col_name}: {e}")

    # Migraciones para contratos (PDF + cláusulas extraídas con IA)
    # pdf_path / pdf_subido_en se llenan cuando el usuario sube el PDF del
    # contrato vigente; las cláusulas viven en tabla nueva clausulas_contrato
    # creada vía Base.metadata.create_all (no requiere ALTER TABLE).
    _CONTRATOS_MISSING = [
        ("pdf_path", "VARCHAR(500)"),
        ("pdf_subido_en", _TS_TIPO),
        # Metadatos enriquecidos (auditoría 10-jun-2026 P0-CITADA): la
        # otra IA cita NIT, número de proceso SECOP, fecha exacta y
        # plazo. Sin esto el sistema producía dictámenes genéricos.
        ("numero_contrato", "VARCHAR(120)"),
        ("nit_eps", "VARCHAR(40)"),
        ("nit_ips", "VARCHAR(40)"),
        ("razon_social_eps", "VARCHAR(300)"),
        ("razon_social_ips", "VARCHAR(300)"),
        ("numero_proceso_secop", "VARCHAR(120)"),
        ("secop_url", "VARCHAR(500)"),
        ("fecha_suscripcion", _TS_TIPO),
        ("fecha_inicio", _TS_TIPO),
        ("fecha_fin", _TS_TIPO),
        ("objeto_contractual", "TEXT"),
        ("anexos_descripcion", "TEXT"),
        ("modalidades_tarifarias", "TEXT"),
    ]
    for col_name, col_ddl in _CONTRATOS_MISSING:
        try:
            if _tiene_tabla("contratos") and not _tiene_columna("contratos", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a contratos")
                db.execute(text(f"ALTER TABLE contratos ADD COLUMN {col_name} {col_ddl}"))
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"MIGRACIÓN contratos {col_name}: {e}")

    # IM F1.3: tabla nueva `lotes_importacion` — la crea Base.metadata
    # .create_all automaticamente si no existe. No requiere ALTER TABLE.

    # RustDesk: 2 columnas opcionales en usuarios para acceso remoto
    _USUARIOS_RUSTDESK = [
        ("rustdesk_id", "VARCHAR(40)"),
        ("rustdesk_etiqueta", "VARCHAR(120)"),
    ]
    for col_name, col_ddl in _USUARIOS_RUSTDESK:
        try:
            if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a usuarios")
                db.execute(text(f"ALTER TABLE usuarios ADD COLUMN {col_name} {col_ddl}"))
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"MIGRACIÓN usuarios {col_name}: {e}")

    # Vacaciones / delegacion temporal: 4 columnas opcionales
    _USUARIOS_VACACIONES = [
        ("vacaciones_desde", _TS_TIPO),
        ("vacaciones_hasta", _TS_TIPO),
        ("delega_a_email", "VARCHAR(200)"),
        ("vacaciones_motivo", "VARCHAR(200)"),
    ]
    for col_name, col_ddl in _USUARIOS_VACACIONES:
        try:
            if _tiene_tabla("usuarios") and not _tiene_columna("usuarios", col_name):
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a usuarios")
                db.execute(text(f"ALTER TABLE usuarios ADD COLUMN {col_name} {col_ddl}"))
                db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"MIGRACIÓN usuarios {col_name}: {e}")

    db.close()

    db = SessionLocal()

    try:
        # Contratos default: solo sembrar los que FALTAN. Los textos
        # editados desde la UI persisten entre deploys (la BD manda);
        # FORCE_RESEED_CONTRATOS=1 fuerza la re-sincronización masiva.
        _sembrar_contratos_default(
            db,
            force_reseed=os.getenv("FORCE_RESEED_CONTRATOS", "").lower() in ("1", "true", "yes"),
        )

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
            db.add(
                UsuarioRecord(
                    nombre="Auditor Principal",
                    email="admin@hus.gov.co",
                    password_hash=get_password_hash(admin_pass),
                    rol="SUPER_ADMIN",
                    activo=1,
                    must_change_password=1,  # forzar cambio en primer login
                )
            )
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
            ("glosashus09@sinacsc.com", "SUPER_ADMIN", "YESID PEREZ"),
            ("glosashus11@sinacsc.com", "AUDITOR", "DIANEYDA QUINTERO"),
            ("glosashus02@sinacsc.com", "AUDITOR", "CAROLINA CIFUENTES"),
            ("glosashus04@sinacsc.com", "AUDITOR", "JHON JAIMES"),
            ("glosashus05@sinacsc.com", "AUDITOR", "MARICELA ROJAS"),
            ("carterahus01@sinacsc.com", "AUDITOR", "IRMA RIOS"),
            ("carterahus04@sinacsc.com", "AUDITOR", "RUBY MILENA"),
            ("carterahus05@sinacsc.com", "AUDITOR", "PATRICIA QUIÑONES"),
            ("radicadevoluciones@sinacsc.com", "AUDITOR", "KAREN ORTIZ"),
            ("devoluciones01@sinacsc.com", "AUDITOR", "SEBASTIAN SANCHES"),
            ("coordinacioncartera@hus.gov.co", "AUDITOR", "YUDY AMAYA"),
            ("glosashus08@sinacsc.com", "AUDITOR", "CLAUDIA SUAREZ"),
            ("glosashus07@sinacsc.com", "AUDITOR", "YENFERSON ORTEGA"),
            ("glosashus12@sinacsc.com", "AUDITOR", "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("devoluciones02@sinacsc.com", "AUDITOR", "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("glosashus10@sinacsc.com", "AUDITOR", "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("glosashus16@sinacsc.com", "AUDITOR", "A_A_A_A (EQUIPO ASEGURADORAS)"),
            # Usuarios adicionales creados desde la UI (añadidos al seed
            # para que reaparezcan si alguna vez la DB se recrea desde cero):
            ("auditorhus01@sinacsc.com", "AUDITOR", "LAURA DIAZ"),
            ("auditorhus02@sinacsc.com", "AUDITOR", "LEIDY JHOANA SANGUINO"),
            ("auditorhus03@sinacsc.com", "AUDITOR", "LEYDI ZULAY GONZALEZ"),
            ("devoluciones03@sinacsc.com", "AUDITOR", "JOHANNA MORENO"),
            ("carterahus02@sinacsc.com", "AUDITOR", "EDGAR SILVA"),
            ("glosashus03@sinacsc.com", "AUDITOR", "OSCAR VILLAMIZAR"),
            # Pedido 03-08-2026: ELIAS con todos los permisos de admin.
            ("glosashus15@sinacsc.com", "SUPER_ADMIN", "ELIAS CARVAJAL"),
        ]
        # POLÍTICA DE PASSWORD INICIAL: cada usuario corporativo recibe como
        # contraseña el prefijo de su correo (ej. glosashus04@sinacsc.com →
        # password "glosashus04"). El usuario debe cambiarla en el primer login.
        force_reseed = os.getenv("FORCE_RESEED_USERS", "").lower() in ("1", "true", "yes")
        force_reset_pwd = os.getenv("FORCE_RESET_PASSWORDS", "").lower() in ("1", "true", "yes")
        for email, rol, nombre in USUARIOS_CORPORATIVOS:
            password_inicial = email.split("@")[0]  # prefijo
            existente = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
            if not existente:
                db.add(
                    UsuarioRecord(
                        nombre=nombre,
                        email=email,
                        password_hash=get_password_hash(password_inicial),
                        rol=rol,
                        activo=1,
                        must_change_password=1,  # obligado a cambiar en primer login
                    )
                )
                logger.warning(
                    f"Usuario sembrado: {email} ({rol}) nombre={nombre} password=<prefijo>"
                )
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
                    existente.password_hash = get_password_hash(password_inicial)
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

        # ─── Seed Plantillas Gold canónicas (contratos ya se siembran arriba) ──
        # Pone los textos institucionales fijos como "Gold" desde el día 1
        # para que el motor IA los use como few-shot sin esperar que glosas
        # LEVANTADAS los pueblen. Idempotente: solo agrega lo que falta.
        try:
            from app.models.db import PlantillaGoldRecord as _PGR
            from app.services.glosa_service import (
                TEXTO_RATIFICADA as _TXT_RAT,
                TEXTO_DMBUG_TARIFAS as _TXT_DMBUG,
            )

            _GOLD_CANONICAS = [
                {
                    "eps": "TODAS",
                    "codigo_glosa": "RATIFICADA",
                    "tipo": "RATIFICADA",
                    "titulo": "Glosa ratificada — texto canónico HUS",
                    "argumento": _TXT_RAT,
                    "notas": "Plantilla institucional para ratificadas.",
                },
                {
                    "eps": "DISPENSARIO MEDICO",
                    "codigo_glosa": "TA",
                    "tipo": "TARIFAS_DMBUG",
                    "titulo": "DMBUG — Tarifas con contrato 440-DIGSA/DMBUG-2025",
                    "argumento": _TXT_DMBUG,
                    "notas": "Texto fijo institucional aprobado por Yesid.",
                },
            ]
            gold_creadas = 0
            gold_actualizadas = 0
            for p in _GOLD_CANONICAS:
                existe = (
                    db.query(_PGR)
                    .filter(
                        _PGR.eps == p["eps"],
                        _PGR.codigo_glosa == p["codigo_glosa"],
                        _PGR.titulo == p["titulo"],
                    )
                    .first()
                )
                if existe:
                    # Norma derogada en una plantilla ya sembrada: la
                    # Resolución 3047 de 2008 la derogó la 2284 de 2023, y
                    # el texto viejo sigue en la base alimentando los
                    # ejemplos que ve la IA. Se corrige en su sitio (decisión
                    # de Yesid, 05-08-2026); el resto de la plantilla queda
                    # intacto porque lo aprobó él.
                    if "3047" in (existe.argumento or "") and "3047" not in p["argumento"]:
                        existe.argumento = p["argumento"]
                        gold_actualizadas += 1
                    continue
                db.add(
                    _PGR(
                        eps=p["eps"],
                        codigo_glosa=p["codigo_glosa"],
                        tipo=p["tipo"],
                        titulo=p["titulo"],
                        argumento=p["argumento"],
                        glosa_origen_id=0,
                        valor_recuperado=0.0,
                        usos=0,
                        creado_por="auto_seed_lifespan",
                        notas=p["notas"],
                        activa=1,
                    )
                )
                gold_creadas += 1
            if gold_creadas or gold_actualizadas:
                db.commit()
                logger.info(
                    f"Seed Plantillas Gold canónicas: {gold_creadas} creadas · "
                    f"{gold_actualizadas} corregidas (norma derogada)."
                )
        except Exception as _e:
            logger.warning(f"Seed Gold canónicas falló (no crítico): {_e}")
            db.rollback()

        # Seed del banco HUS: 50 plantillas jurídicas genéricas (TA/SO/CO/FA/CL)
        # Idempotente — sólo crea las que no existen aún (match por eps+codigo+titulo).
        try:
            import json as _json
            from pathlib import Path as _Path

            archivo_hus = (
                _Path(__file__).resolve().parent.parent / "data" / "plantillas_hus_base.json"
            )
            if not archivo_hus.exists():
                logger.warning(
                    f"[SEED-HUS] archivo no encontrado en {archivo_hus} — "
                    "el banco HUS NO se cargará. Verificar COPY data/*.json en Dockerfile."
                )
            else:
                with archivo_hus.open(encoding="utf-8") as _fh:
                    _data_hus = _json.load(_fh)
                _filas_hus = _data_hus.get("plantillas", [])
                hus_creadas = 0
                hus_existentes = 0
                hus_actualizadas = 0
                for fila in _filas_hus:
                    eps = (fila.get("eps") or "").upper().strip()
                    cod = (fila.get("codigo_glosa") or "").upper().strip()
                    tit = (fila.get("titulo") or "").strip()[:200]
                    arg = (fila.get("argumento") or "").strip()
                    if not eps or not cod or not arg:
                        continue
                    existe = (
                        db.query(_PGR)
                        .filter(
                            _PGR.eps == eps,
                            _PGR.codigo_glosa == cod,
                            _PGR.titulo == tit,
                        )
                        .first()
                    )
                    if existe:
                        hus_existentes += 1
                        # 06-08-2026 — la misma corrección en sitio que ya se
                        # le hizo a las plantillas Gold. Seis plantillas del
                        # banco fundaban la defensa en la Resolución 3047 de
                        # 2008, que la 2284 de 2023 reemplazó; se vio en dos
                        # dictámenes de prueba (SUMIMEDICAL SO0101 y MUTUAL
                        # SER SO0201) citándola como norma propia y de
                        # primera. Fundar en norma derogada le regala el
                        # argumento a la entidad. Ahora va adelante la
                        # vigente y la vieja queda como antecedente. Este
                        # bloque solo toca las que traen el texto viejo: el
                        # resto del banco queda intacto porque lo aprobó
                        # Yesid.
                        _arg_bd = existe.argumento or ""
                        if (
                            "3047" in _arg_bd
                            and not any(m in _arg_bd for m in _MARCAS_NORMA_VIGENTE)
                            and any(m in arg for m in _MARCAS_NORMA_VIGENTE)
                        ):
                            existe.argumento = arg
                            hus_actualizadas += 1
                        continue
                    db.add(
                        _PGR(
                            eps=eps,
                            codigo_glosa=cod,
                            tipo=fila.get("tipo") or "PLANTILLA_HUS_BASE",
                            titulo=tit,
                            argumento=arg,
                            valor_recuperado=0.0,
                            usos=0,
                            creado_por="auto_seed_lifespan",
                            notas=fila.get("notas") or None,
                            activa=1,
                        )
                    )
                    hus_creadas += 1
                if hus_creadas or hus_actualizadas:
                    db.commit()
                logger.info(
                    f"[SEED-HUS] {hus_creadas} creadas · {hus_existentes} ya existían · "
                    f"{hus_actualizadas} actualizadas (norma derogada) · "
                    f"total filas en archivo: {len(_filas_hus)}"
                )
        except Exception as _e:
            logger.warning(f"Seed banco HUS falló (no crítico): {_e}")
            db.rollback()

        # ── Cláusulas reales de contrato (06-08-2026) ────────────────────
        # data/clausulas_contrato_base.json trae 26 cláusulas LITERALES de
        # contratos firmados, pero solo se cargaban corriendo a mano
        # scripts/seed_clausulas_contrato.py. Nadie lo corrió: el
        # Diagnóstico del hospital reporta "0 cláusulas extraídas de 0
        # contratos" y por eso TODOS los dictámenes pierden puntos por
        # «falta cláusula del contrato vigente con esta EPS», el motor no
        # tiene una cláusula real que citar, y el verificador de citas no
        # puede validar ninguna cita contractual.
        #
        # Se siembra al arrancar, igual que el banco de plantillas.
        # Idempotente por (eps, numero_clausula): si el texto cambió se
        # actualiza; si es igual no se toca.
        try:
            from app.models.db import ClausulaContrato as _CCR

            archivo_cl = (
                _Path(__file__).resolve().parent.parent / "data" / "clausulas_contrato_base.json"
            )
            if not archivo_cl.exists():
                logger.warning(f"[SEED-CLAUSULAS] archivo no encontrado en {archivo_cl}")
            else:
                with archivo_cl.open(encoding="utf-8") as _fh:
                    _filas_cl = _json.load(_fh).get("clausulas", [])
                # La cláusula cuelga del contrato (llave foránea) y el motor
                # la busca por la MISMA clave de EPS que usa el auditor en
                # pantalla. El archivo trae razones sociales largas —
                # "SEGUROS DE VIDA AURORA S.A." por "AURORA", "COMPENSAR
                # EPS" por "COMPENSAR", "FAMISANAR" por "FAMISANAR EPS"— así
                # que sin traducir la clave las 26 cláusulas o no entran o
                # entran donde nadie las va a encontrar. Se resuelve por
                # contención y solo cuando la coincidencia es ÚNICA; lo que
                # no resuelva se salta con aviso, sin inventar un contrato.
                _eps_contratos = [c.eps for c in db.query(ContratoRecord).all() if c.eps]

                def _clave_de_contrato(nombre: str) -> str:
                    n = (nombre or "").upper().strip()
                    if not n:
                        return ""
                    if n in _eps_contratos:
                        return n
                    candidatos = [k for k in _eps_contratos if k in n or n in k]
                    return candidatos[0] if len(candidatos) == 1 else ""

                cl_creadas = cl_actualizadas = cl_saltadas = 0
                for fila in _filas_cl:
                    eps_cl = _clave_de_contrato(fila.get("eps") or "")
                    if not eps_cl:
                        logger.warning(
                            f"[SEED-CLAUSULAS] sin contrato registrado para "
                            f"«{fila.get('eps')}» — cláusula no cargada"
                        )
                        cl_saltadas += 1
                        continue
                    texto_cl = (fila.get("texto_literal") or "").strip()
                    # Un placeholder sin llenar es peor que nada: la IA lo
                    # citaría como si fuera texto del contrato.
                    if not eps_cl or not texto_cl:
                        cl_saltadas += 1
                        continue
                    if texto_cl.startswith("[") and texto_cl.endswith("]"):
                        cl_saltadas += 1
                        continue
                    tema_cl = (fila.get("tema") or "NN").upper().strip()
                    if tema_cl not in {"TA", "SO", "AU", "CO", "FA", "NN"}:
                        tema_cl = "NN"
                    num_cl = (fila.get("numero_clausula") or "").strip()
                    existe_cl = (
                        db.query(_CCR)
                        .filter(_CCR.eps == eps_cl, _CCR.numero_clausula == num_cl)
                        .first()
                    )
                    if existe_cl:
                        if (existe_cl.texto_literal or "").strip() != texto_cl:
                            existe_cl.tema = tema_cl
                            existe_cl.titulo = (fila.get("titulo") or "").strip()
                            existe_cl.texto_literal = texto_cl
                            existe_cl.pagina = fila.get("pagina")
                            cl_actualizadas += 1
                        continue
                    db.add(
                        _CCR(
                            eps=eps_cl,
                            numero_clausula=num_cl,
                            tema=tema_cl,
                            titulo=(fila.get("titulo") or "").strip(),
                            texto_literal=texto_cl,
                            pagina=fila.get("pagina"),
                        )
                    )
                    cl_creadas += 1
                if cl_creadas or cl_actualizadas:
                    db.commit()
                logger.info(
                    f"[SEED-CLAUSULAS] {cl_creadas} creadas · {cl_actualizadas} actualizadas · "
                    f"{cl_saltadas} saltadas (sin texto real) · "
                    f"total en archivo: {len(_filas_cl)}"
                )
        except Exception as _e_cl:
            logger.warning(f"Seed de cláusulas falló (no crítico): {_e_cl}")
            db.rollback()

        db.commit()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando BD: {e}")
        db.rollback()
    finally:
        db.close()

    try:
        _ant = os.getenv("ANTHROPIC_API_KEY", "")
        _gem = os.getenv("GEMINI_API_KEY", "")
        _grq = os.getenv("GROQ_API_KEY", "")
        _prim = os.getenv("PRIMARY_AI", "groq")
        logger.info(
            f"[IA-PROVIDERS] primary={_prim} (dictamen: groq+anthropic) | "
            f"groq={'OK ' + _grq[:10] + '...' if _grq else 'AUSENTE'} | "
            f"anthropic={'OK ' + _ant[:10] + '...' if _ant else 'AUSENTE'} | "
            f"gemini(solo OCR)={'OK ' + _gem[:10] + '...' if _gem else 'AUSENTE'}"
        )
    except Exception as _e_diag:
        logger.warning(f"[IA-PROVIDERS] no se pudo loguear estado: {_e_diag}")

    # ¿Quedó otro motor vivo del arranque anterior? (04-08-2026)
    # En Windows el uvicorn nuevo puede convivir con el viejo sobre el mismo
    # puerto: las peticiones caen en cualquiera de los dos y el viejo
    # responde con la clave y el código anteriores. Se avisa UNA vez por
    # proceso, aquí, que es el momento en que todavía se puede cerrar el
    # sobrante antes de trabajar.
    global _MOTOR_YA_CHEQUEADO
    if not _MOTOR_YA_CHEQUEADO:
        _MOTOR_YA_CHEQUEADO = True
        try:
            from app.services.motor_proceso import estado_motor

            _est = estado_motor()
            if _est["estado"] == "ok":
                logger.info(f"[MOTOR] {_est['mensaje']}")
            elif _est["estado"] == "error":
                # Dos en el MISMO puerto: eso sí es un problema.
                logger.warning(f"[MOTOR-DUPLICADO] {_est['mensaje']}")
            else:
                # Puertos distintos: normal en el PC del hospital (el 8080
                # sirve la página por internet). Etiqueta aparte para que el
                # bot no mande a cerrar nada — la etiqueta anterior lo metía
                # en un bucle de «cerrá y volvé a intentar» que nunca
                # terminaba, porque el vigilante revive el otro motor.
                logger.warning(f"[MOTORES] {_est['mensaje']}")
        except Exception as _e_motor:
            logger.warning(f"[MOTOR] no se pudo inspeccionar el proceso: {_e_motor}")

    # Guard global: DISABLE_SCHEDULERS=1 salta TODOS los schedulers en background.
    # Útil en CI/tests donde múltiples TestClient arrancan lifespan y crean
    # decenas de asyncio tasks que se acumulan hasta OOM.
    _SKIP_SCHEDULERS = os.environ.get("DISABLE_SCHEDULERS", "").lower() in ("1", "true", "yes")
    if _SKIP_SCHEDULERS:
        logger.info("[SCHEDULERS] DISABLE_SCHEDULERS=1 — schedulers desactivados")

    # Ronda 2: iniciar scheduler de IA auditora proactiva (6 AM diario).
    # No bloquea el startup si falla; sólo deja logs.
    if not _SKIP_SCHEDULERS:
        try:
            from app.services.ia_auditora_proactiva import iniciar_scheduler

            iniciar_scheduler()
        except Exception as _e:
            logger.warning(f"No se pudo iniciar scheduler de pre-análisis: {_e}")

    # Ronda 20: scheduler del digest ejecutivo (sólo si DIGEST_DESTINATARIOS
    # está configurado). No bloquea startup si falla.
    if not _SKIP_SCHEDULERS:
        try:
            from app.services.digest_scheduler import iniciar_scheduler as iniciar_digest_scheduler

            iniciar_digest_scheduler()
        except Exception as _e:
            logger.warning(f"No se pudo iniciar scheduler del digest: {_e}")

    # R57 P2: scheduler diario de mantenimiento (3 AM) — purga
    # ai_cache > 30d, ai_calls > 90d, papelera > 30d. No bloquea
    # startup ni rompe si falla — el mantenimiento es secundario.
    if not _SKIP_SCHEDULERS:
        try:
            from app.services.mantenimiento_scheduler import (
                iniciar_scheduler as iniciar_mant_scheduler,
            )

            iniciar_mant_scheduler()
        except Exception as _e:
            logger.warning(f"No se pudo iniciar scheduler de mantenimiento: {_e}")

    # Reindex diario del share de soportes (2 AM) + build inicial al
    # arrancar para que el primer gestor del día encuentre el índice
    # caliente. No bloquea startup si el mount aún no está disponible
    # — el healthz lo refleja y el reintento ocurre al día siguiente.
    if not _SKIP_SCHEDULERS:
        try:
            from app.services.soportes_reindex_scheduler import (
                iniciar_scheduler as iniciar_soportes_scheduler,
            )

            iniciar_soportes_scheduler()
        except Exception as _e:
            logger.warning(f"No se pudo iniciar scheduler de soportes: {_e}")

    # 03-09-2026 (V2, Pilar 4) — el reloj del plazo legal. `dias_restantes` se
    # calculaba una sola vez, al analizar, y quedaba congelado: el semáforo
    # nunca se ponía rojo solo. Este demonio lo recalcula periódicamente contra
    # la fecha de hoy. No arranca en pruebas (el lifespan se levanta cientos de
    # veces) y se puede apagar con VENCIMIENTOS_DEMONIO=0.
    try:
        from app.services.demonio_vencimientos import iniciar as iniciar_vencimientos

        iniciar_vencimientos(app)
    except Exception as _e:
        logger.warning(f"No se pudo iniciar el demonio de vencimientos: {_e}")

    yield

    try:
        from app.services.demonio_vencimientos import detener as detener_vencimientos

        detener_vencimientos(app)
    except Exception:
        pass

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
app.add_middleware(CorrelationIdMiddleware)


# Ronda 50 Paso 10: middleware de tenant.
# Resuelve el tenant_id desde header X-Tenant-ID, query ?tenant=, o
# subdominio (hus.ia-glosas.com → 'HUS'). Por defecto 'HUS' para no
# romper el flujo single-tenant actual. Cuando entre cliente #2 solo
# hay que setear tenant_id en sus glosas y este middleware ya filtra.
# Saber si hay alguien trabajando, para que un despliegue no le tumbe la
# pagina a las gestoras en plena jornada (24-08-2026). Ver
# app/services/actividad.py: distingue lo que pide una persona de lo que el
# propio portal se pregunta solo cada tanto.
#
# Va antes de todo y no puede fallar: si algo se rompe aca, el portal entero
# deja de responder. Por eso el try/except mudo.
@app.middleware("http")
async def _actividad_middleware(request, call_next):
    try:
        from app.services.actividad import marcar_actividad

        marcar_actividad(request.method, request.url.path)
    except Exception:
        pass
    return await call_next(request)


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
from app.api.routers.glosas_adres import router as glosas_adres_router
from app.api.routers.automatizaciones import router as automatizaciones_router
from app.api.routers.inteligencia import router as inteligencia_router
from app.api.routers.bots import router as bots_router
from app.api.routers.gobierno_ia import router as gobierno_ia_router
from app.api.routers.malla import router as malla_router
from app.api.routers.maos import router as maos_router
from app.api.routers.contratos import router as contratos_router
from app.api.routers.analytics import router as analytics_router
from app.api.routers.plantillas import router as plantillas_router
from app.api.routers.workflow import router as workflow_router
from app.api.routers.alertas import router as alertas_router
from app.api.routers.usuarios import router as usuarios_router
from app.api.routers.conciliacion import router as conciliacion_router
from app.api.routers.audit import router as audit_router

from app.api.routers.salud_total import router as salud_total_router
from app.api.routers.tarifas_contratadas import router as tarifas_contratadas_router
from app.api.routers.tarifa_liquidador import router as tarifa_liquidador_router
from app.api.routers.credenciales import router as credenciales_router
from app.api.routers.admin import router as admin_router
from app.api.routers.plantillas_gold import router as plantillas_gold_router
from app.api.routers.comentarios import router as comentarios_router
from app.api.routers.informes import router as informes_router
from app.api.routers.mi_desempeno import router as mi_desempeno_router
from app.api.routers.mi_dia import router as mi_dia_router
from app.api.routers.vida import router as vida_router
from app.api.routers.busqueda_semantica import router as busqueda_semantica_router
from app.api.routers.dos_fa import router as dos_fa_router
from app.api.routers.asistente_predictivo import router as asistente_predictivo_router
from app.api.routers.quality_gate_stats import router as quality_gate_stats_router
from app.api.routers.versiones import router as versiones_router
from app.api.routers.papelera import router as papelera_router
from app.api.routers.export_erp import router as export_erp_router
from app.api.routers.exportar import router as exportar_router
from app.api.routers.asignacion import router as asignacion_router
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
from app.api.routers.auditor_forense import router as auditor_forense_router
from app.api.routers.push import router as push_router

# control_center: stub removido — prefijo /_removed/ (mayo 2026)
from app.api.routers.notificaciones import router as notificaciones_router
from app.api.routers.eventos_live import router as eventos_live_router

from app.api.routers.preset_filtros import router as preset_filtros_router
from app.api.routers.notas_privadas import router as notas_privadas_router
from app.api.routers.rutas_factura import router as rutas_factura_router
from app.api.routers.snippets import router as snippets_router

from app.api.routers.chat_history import router as chat_history_router
from app.api.routers.dictamen_pdf import router as dictamen_pdf_router

from app.api.routers.comentarios_thread import router as comentarios_thread_router

# webhooks: stub removido — prefijo /_removed/ (mayo 2026)
from app.api.routers.ia_status import router as ia_status_router

app.include_router(auth_router)
app.include_router(asistente_predictivo_router)  # Ola 4: inteligencia ambiental
app.include_router(quality_gate_stats_router)  # Ola 1: estado del Quality Gate
app.include_router(glosas_router)
app.include_router(glosas_adres_router)  # Paquetes de glosas del ADRES
app.include_router(automatizaciones_router)
app.include_router(inteligencia_router)
app.include_router(bots_router)
app.include_router(gobierno_ia_router)
app.include_router(malla_router)
app.include_router(maos_router)
app.include_router(contratos_router)
app.include_router(analytics_router)
app.include_router(plantillas_router)
app.include_router(workflow_router)
app.include_router(alertas_router)
app.include_router(usuarios_router)
app.include_router(conciliacion_router)
app.include_router(audit_router)
app.include_router(salud_total_router)
app.include_router(tarifas_contratadas_router)
app.include_router(tarifa_liquidador_router)
app.include_router(credenciales_router)  # Vault cifrado de credenciales EPS
app.include_router(admin_router)
app.include_router(plantillas_gold_router)
app.include_router(comentarios_router)
app.include_router(informes_router)
app.include_router(mi_desempeno_router)
app.include_router(mi_dia_router)
app.include_router(vida_router)  # Capa de Vida (ronda 32): saludo + celebraciones
app.include_router(busqueda_semantica_router)
app.include_router(dos_fa_router)
app.include_router(versiones_router)
app.include_router(papelera_router)
app.include_router(export_erp_router)
app.include_router(exportar_router)  # Formato DGH (reconectado en ronda 29)
app.include_router(asignacion_router)
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
# control_center_router: stub removido
app.include_router(notificaciones_router)
app.include_router(eventos_live_router)
app.include_router(preset_filtros_router)
app.include_router(notas_privadas_router)
app.include_router(rutas_factura_router)
app.include_router(snippets_router)
app.include_router(chat_history_router)
app.include_router(dictamen_pdf_router)
app.include_router(comentarios_thread_router)
# webhooks_router: stub removido
app.include_router(ia_status_router)
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

from app.api.routers.preauditoria import router as preauditoria_router

app.include_router(preauditoria_router)
# auditor_preview: stub removido — POST /glosas/preview-auditoria está en glosas.py
from app.api.routers.soportes import router as soportes_auto_router

# 13-08-2026: el validador ADRES y el buscador de autorizaciones dejan de
# ser programas aparte y entran al portal, con la sesión y los roles del
# hospital. Por ahí suben soportes con historia clínica: auditor o superior.
from app.api.routers.validador_adres import router as validador_adres_router

app.include_router(soportes_auto_router)
app.include_router(validador_adres_router)

from app.api.routers.diagnostico import router as diagnostico_router

app.include_router(diagnostico_router)
# OJO: auditor_forense (analiza soportes) y auditoria_forense (busca por IP)
# son DOS cosas distintas. La limpieza de mayo los confundió y dejó la
# pantalla del Auditor Forense llamando a una ruta que no existía.
app.include_router(auditor_forense_router)
app.include_router(push_router)
from app.api.routers.asistente_maestro import router as asistente_maestro_router

app.include_router(asistente_maestro_router)

# Lotes de portal (Fase 1 app unificada): subida del Excel consolidado
# + cola del agente local que corre los bots en el PC del hospital.
from app.api.routers.lotes import router as lotes_router, agente_router as agente_lotes_router

app.include_router(lotes_router)
app.include_router(agente_lotes_router)
