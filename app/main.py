import logging
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
from app.api.deps import get_usuario_actual
from app.services.glosa_ia_prompts import get_contrato


def _detectar_servicio_desde_texto(texto_glosa: str, contexto_pdf: str = "") -> Optional[str]:
    """Intenta extraer el nombre del servicio/procedimiento y el CUPS desde el texto
    de la glosa y/o los soportes adjuntos.

    Retorna una cadena tipo "ESTUDIO DE COLORACIÓN BÁSICA EN BIOPSIA (CUPS 898040)"
    cuando puede identificarlo; None en caso contrario.
    """
    if not texto_glosa and not contexto_pdf:
        return None
    fuente = f"{texto_glosa}\n{contexto_pdf}".upper()

    # 1. Buscar CUPS (código numérico de 5-6 dígitos)
    cups_match = re.search(r"\b(\d{5,6})\b", fuente)
    cups = cups_match.group(1) if cups_match else None

    # 2. Buscar una descripción de servicio después de palabras clave comunes
    desc = None
    patrones = [
        # Servicio explícito con etiqueta previa
        r"(?:SERVICIO|PROCEDIMIENTO|DESCRIPCI[ÓO]N\s+DEL\s+SERVICIO|ACTIVIDAD)\s*[:\-]\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,\-/]{5,70})",
        # Menciones clínicas típicas (cortadas antes de signos de puntuación o fin de oración)
        r"\b(CONSULTA\s+(?:DE|EN|EXTERNA|CONTROL|URGENCIA|ESPECIALIZADA)[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(CIRUG[ÍI]A\s+(?:DE|POR|LAPAROSC[ÓO]PICA|ABIERTA)[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(ESTUDIO\s+(?:DE|DEL|POR|EN)[A-ZÁÉÍÓÚÑ ,\-]{5,60})",
        r"\b(TOMOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(RESONANCIA\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(ECOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(BIOPSIA\s+[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(RADIOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(HEMOGRAMA[A-ZÁÉÍÓÚÑ ,\-]{0,40})",
        r"\b(HOSPITALIZACI[ÓO]N\s+[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(CRANEOTOM[ÍI]A[A-ZÁÉÍÓÚÑ ,\-]{0,60})",
        r"\b(APENDICECTOM[ÍI]A[A-ZÁÉÍÓÚÑ ,\-]{0,40})",
        r"\b(COLECISTECTOM[ÍI]A[A-ZÁÉÍÓÚÑ ,\-]{0,40})",
    ]
    for pat in patrones:
        m = re.search(pat, fuente)
        if m:
            desc = (m.group(1) if m.groups() else m.group(0)).strip()
            # Cortar en separadores que indican fin natural de la descripción
            desc = re.split(r"\s+(?:COBRO|DIFERENCIA|VALOR|SIN|CON|POR\s+VALOR|MOTIVO|OBSERVACI)", desc)[0]
            desc = re.sub(r"\s+", " ", desc).strip().rstrip(",-.")
            if 5 <= len(desc) <= 80:
                break
            desc = None

    if desc and cups:
        return f"{desc} (CUPS {cups})"
    if desc:
        return desc
    if cups:
        return f"CUPS {cups}"
    return None


# Concepto oficial (Anexo Técnico 6 Res. 3047/2008) por código de glosa.
# Se usa mostrar en la tabla de historial. Si no hay match exacto, se usa el
# concepto por prefijo.
CONCEPTOS_CODIGOS: dict[str, str] = {
    # Tarifa (TA)
    "TA01": "Los cargos por consulta, interconsulta o atención (visita) domiciliaria, presentan diferencias con los valores pactados o establecidos por la norma",
    "TA02": "Los cargos por estancia presentan diferencias con los valores pactados o establecidos por la norma",
    "TA03": "Los cargos por honorarios (médicos o quirúrgicos) presentan diferencias con los valores pactados o establecidos por la norma",
    "TA04": "Los cargos por derechos de sala presentan diferencias con los valores pactados o establecidos por la norma",
    "TA05": "Los cargos por materiales presentan diferencias con los valores pactados o establecidos por la norma",
    "TA06": "Los cargos por medicamentos o APME presentan diferencias con los valores pactados o establecidos por la norma",
    "TA07": "Los cargos por medicamentos o APME que vienen relacionados o justificados en los soportes de cobro, presentan diferencias con los valores pactados o establecidos por la norma",
    "TA08": "Los cargos por procedimientos quirúrgicos o no quirúrgicos presentan diferencias con los valores pactados o establecidos por la norma",
    "TA09": "Los cargos por apoyo diagnóstico terapéutico presentan diferencias con los valores pactados o establecidos por la norma",
    # Soportes (SO)
    "SO01": "Faltan soportes de la atención, historia clínica o documentación exigida",
    "SO02": "Los soportes presentan inconsistencias o están incompletos",
    "SO42": "Lista de precios no aportada o insuficiente",
    # Autorización (AU)
    "AU01": "Servicio prestado sin autorización previa",
    "AU02": "Diferencia con el servicio autorizado",
    # Cobertura (CO)
    "CO01": "Servicio no incluido en el PBS o régimen aplicable",
    "CO02": "Servicio no cubierto por régimen especial",
    "CO03": "Servicio no incluido en el PBS del régimen subsidiado o contributivo",
    # Pertinencia (CL / PE)
    "CL01": "Procedimiento no pertinente según criterio clínico",
    "PE01": "Procedimiento no pertinente según criterio clínico",
    # Facturación (FA)
    "FA01": "Error formal en la facturación (código, fecha, firma)",
    "FA02": "Error en código CUPS o código no corresponde",
    # Insumos (IN)
    "IN01": "Insumos no reconocidos o no pactados",
    "IN02": "Diferencia en valor de insumos",
    # Medicamentos (ME)
    "ME01": "Medicamento no incluido en PBS o fuera de cobertura",
    "ME02": "Medicamento no justificado por fórmula médica",
}


def _extraer_motivo_glosa(texto: str) -> str:
    """Extrae solo el motivo/observación de la glosa, quitando código, concepto,
    CUPS, servicio y valores numéricos (que ya están en columnas separadas).

    Formato típico del Excel:
      CODIGO - CONCEPTO - CUPS - SERVICIO - VALOR_OBJ - MOTIVO - VALOR_ACEP
    Devuelve el último segmento TEXTUAL que no sea un código ni un valor.
    Si no logra identificarlo, devuelve el texto original.
    """
    if not texto:
        return ""
    t = texto.strip()
    partes = [p.strip() for p in t.split(" - ")]
    if len(partes) <= 2:
        return t

    def _es_descartable(p: str) -> bool:
        if not p:
            return True
        # Valor monetario o numérico puro (solo dígitos, puntos, comas, $, espacios)
        if re.fullmatch(r"[\d\.,\s\$\-]+", p):
            return True
        # Código de glosa: 2 letras mayúsculas + 2-6 dígitos (TA0801, SO0101, etc.)
        if re.fullmatch(r"[A-Z]{2}\d{2,6}", p):
            return True
        return False

    textuales = [p for p in partes if not _es_descartable(p)]
    if not textuales:
        return t
    # El motivo real suele ser el ÚLTIMO segmento textual del listado
    return textuales[-1]


def _concepto_glosa(codigo_glosa: str) -> str:
    """Devuelve la descripción oficial del código de glosa (Anexo Técnico 6)."""
    if not codigo_glosa:
        return ""
    # Intentar match por los primeros 4 caracteres (ej. 'TA07' de 'TA0701')
    key = codigo_glosa[:4].upper()
    if key in CONCEPTOS_CODIGOS:
        return CONCEPTOS_CODIGOS[key]
    # Fallback por prefijo de 2 letras
    prefijo = codigo_glosa[:2].upper()
    fallbacks = {
        "TA": "Diferencia tarifaria con los valores pactados o establecidos por la norma",
        "SO": "Falta de soportes o documentación requerida",
        "AU": "Ausencia o diferencia de autorización previa",
        "CO": "Servicio no incluido en cobertura",
        "CL": "Procedimiento no pertinente según criterio clínico",
        "PE": "Procedimiento no pertinente según criterio clínico",
        "FA": "Error formal en la facturación",
        "IN": "Diferencia o no reconocimiento de insumos",
        "ME": "Diferencia o no reconocimiento de medicamentos",
    }
    return fallbacks.get(prefijo, "Glosa sin concepto específico asignado")


def _extraer_cups_servicio(texto_glosa: str, contexto_pdf: str = "") -> tuple[str, str]:
    """Extrae tupla (CUPS, descripción_servicio) desde el texto de la glosa/PDF.

    Retorna ("", "") si no logra identificarlos.
    """
    if not texto_glosa and not contexto_pdf:
        return "", ""
    fuente = f"{texto_glosa}\n{contexto_pdf}"

    cups = ""
    # CUPS estándar: 5-6 dígitos, opcionalmente con sufijo -X
    m = re.search(r"\b(\d{5,8}(?:-\d)?)\b", fuente)
    if m:
        cups = m.group(1)

    servicio = ""
    # Buscar descripción del servicio con patrones comunes
    for pat in [
        r"(?:SERVICIO|PROCEDIMIENTO|DESCRIPCI[ÓO]N)\s*[:\-]\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,\-/]{5,120})",
        r"\b(CONSULTA\s+[A-ZÁÉÍÓÚÑ ,\-]{3,100})",
        r"\b(CIRUG[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,100})",
        r"\b(ESTUDIO\s+[A-ZÁÉÍÓÚÑ ,\-]{3,100})",
        r"\b(TOMOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,80})",
        r"\b(RESONANCIA\s+[A-ZÁÉÍÓÚÑ ,\-]{3,80})",
        r"\b(ECOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,80})",
        r"\b(BIOPSIA[A-ZÁÉÍÓÚÑ ,\-]{0,80})",
        r"\b(ACETAMINOFEN[A-ZÁÉÍÓÚÑ0-9 ,\-/]{0,80})",
    ]:
        m = re.search(pat, fuente, re.IGNORECASE)
        if m:
            servicio = (m.group(1) if m.groups() else m.group(0)).strip()
            servicio = re.split(r"\s+(?:COBRO|DIFERENCIA|MAYOR|VALOR|MOTIVO)", servicio)[0]
            servicio = re.sub(r"\s+", " ", servicio).strip().rstrip(",-.")[:200]
            break

    return cups, servicio


def _descripcion_servicio(codigo_glosa: str, texto_glosa: str = "", contexto_pdf: str = "") -> str:
    """Devuelve una descripción del servicio detectado en la glosa/soportes.
    Si no logra detectar un servicio específico, devuelve una frase neutra según el
    prefijo del código (TA, SO, AU...)."""
    detectado = _detectar_servicio_desde_texto(texto_glosa, contexto_pdf)
    if detectado:
        return f"AL SERVICIO FACTURADO {detectado}"

    # Fallback neutro según el tipo de glosa (sin ejemplos entre paréntesis)
    if not codigo_glosa:
        return "AL SERVICIO FACTURADO"
    prefijo = codigo_glosa[:2].upper()
    return {
        "TA": "AL SERVICIO FACTURADO",
        "SO": "AL SERVICIO FACTURADO Y SUS SOPORTES DOCUMENTALES",
        "AU": "AL PROCEDIMIENTO AUTORIZADO",
        "CO": "AL SERVICIO CUBIERTO",
        "CL": "AL PROCEDIMIENTO MÉDICO PRESTADO",
        "PE": "AL PROCEDIMIENTO MÉDICO PRESTADO",
        "FA": "AL CARGO FACTURADO",
        "IN": "AL INSUMO O DISPOSITIVO MÉDICO UTILIZADO",
        "ME": "AL MEDICAMENTO DISPENSADO",
    }.get(prefijo, "AL SERVICIO FACTURADO")

logging.basicConfig(level=logging.INFO)

CONTRATOS_DEFAULT = {
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
    from sqlalchemy import text

    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' AND column_name='creado_en'"))
        if not result.fetchone():
            logger.warning("MIGRACIÓN: Agregando columna 'creado_en' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW()"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN creado_en: {e}")

    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' AND column_name='activo'"))
        if not result.fetchone():
            logger.warning("MIGRACIÓN: Agregando columna 'activo' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN activo INTEGER DEFAULT 1"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN activo: {e}")

    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' AND column_name='rol'"))
        if not result.fetchone():
            logger.warning("MIGRACIÓN: Agregando columna 'rol' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN rol VARCHAR(50) DEFAULT 'AUDITOR'"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN rol: {e}")

    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' AND column_name='workload'"))
        if not result.fetchone():
            logger.warning("MIGRACIÓN: Agregando columna 'workload' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN workload INTEGER DEFAULT 100"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN workload: {e}")

    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' AND column_name='nota_workflow'"))
        if not result.fetchone():
            logger.warning("MIGRACIÓN: Agregando columna 'nota_workflow' a tabla usuarios")
            db.execute(text("ALTER TABLE usuarios ADD COLUMN nota_workflow TEXT"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN nota_workflow: {e}")

    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='historial' AND column_name='numero_radicado'"))
        if not result.fetchone():
            logger.warning("MIGRACIÓN: Agregando columna 'numero_radicado' a historial")
            db.execute(text("ALTER TABLE historial ADD COLUMN numero_radicado VARCHAR(50)"))
            db.commit()
    except Exception as e:
        logger.warning(f"MIGRACIÓN numero_radicado: {e}")

    try:
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='historial' AND column_name='request_id'"))
        if not result.fetchone():
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
    ]
    for col_name, col_ddl in _HISTORIAL_MISSING_COLUMNS:
        try:
            result = db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='historial' AND column_name=:col"
            ), {"col": col_name})
            if not result.fetchone():
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a historial")
                db.execute(text(f"ALTER TABLE historial ADD COLUMN {col_name} {col_ddl}"))
                db.commit()
        except Exception as e:
            logger.warning(f"MIGRACIÓN {col_name}: {e}")

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
            result = db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='conciliaciones' AND column_name=:col"
            ), {"col": col_name})
            if not result.fetchone():
                logger.warning(f"MIGRACIÓN: Agregando columna '{col_name}' a conciliaciones")
                db.execute(text(f"ALTER TABLE conciliaciones ADD COLUMN {col_name} {col_ddl}"))
                db.commit()
        except Exception as e:
            logger.warning(f"MIGRACIÓN conciliaciones {col_name}: {e}")

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
        # CORRECCIÓN: contraseña desde variable de entorno, sin hardcodear "admin123"
        if db.query(UsuarioRecord).count() == 0:
            admin_pass = cfg.admin_password
            db.add(UsuarioRecord(
                nombre="Auditor Principal",
                email="admin@hus.gov.co",
                password_hash=get_password_hash(admin_pass),
                rol="SUPER_ADMIN",
                activo=1,
            ))
            logger.warning(
                "Usuario admin creado. Cambiar contraseña inmediatamente "
                "usando la variable de entorno ADMIN_PASSWORD."
            )

        # Asegurar que admin@hus.gov.co tenga rol SUPER_ADMIN
        admin = db.query(UsuarioRecord).filter(UsuarioRecord.email == "admin@hus.gov.co").first()
        if admin and admin.rol != "SUPER_ADMIN":
            logger.warning("Actualizando rol de admin@hus.gov.co a SUPER_ADMIN")
            admin.rol = "SUPER_ADMIN"

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
            ("carterahus04@sinacsc.com",     "AUDITOR",     "MILENA"),
            ("carterahus05@sinacsc.com",     "AUDITOR",     "PATRICIA QUIÑONES"),
            ("radicadevoluciones@sinacsc.com","AUDITOR",    "KAREN ORTIZ"),
            ("devoluciones01@sinacsc.com",   "AUDITOR",     "YUDY"),
            ("coordinacioncartera@hus.gov.co","AUDITOR",    "YUDY"),
            ("glosashus08@sinacsc.com",      "AUDITOR",     "CLAUDIA"),
            ("glosashus07@sinacsc.com",      "AUDITOR",     "YENFERSON ORTEGA"),
            ("glosashus12@sinacsc.com",      "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("devoluciones02@sinacsc.com",   "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("glosashus10@sinacsc.com",      "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
            ("glosashus16@sinacsc.com",      "AUDITOR",     "A_A_A_A (EQUIPO ASEGURADORAS)"),
        ]
        password_hash_default = get_password_hash(cfg.admin_password)
        for email, rol, nombre in USUARIOS_CORPORATIVOS:
            existente = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
            if not existente:
                db.add(UsuarioRecord(
                    nombre=nombre,
                    email=email,
                    password_hash=password_hash_default,
                    rol=rol,
                    activo=1,
                ))
                logger.warning(f"Usuario sembrado: {email} ({rol}) nombre={nombre}")
            else:
                cambios = []
                if existente.rol != rol:
                    cambios.append(f"rol {existente.rol}->{rol}")
                    existente.rol = rol
                if existente.nombre != nombre:
                    cambios.append(f"nombre '{existente.nombre}'->'{nombre}'")
                    existente.nombre = nombre
                if cambios:
                    logger.warning(f"Usuario {email} actualizado: {', '.join(cambios)}")

        db.commit()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando BD: {e}")
        db.rollback()
    finally:
        db.close()
    yield
    logger.info("=== APLICACIÓN CERRADA ===")


cfg = get_settings()

# Rate limiter para proteger endpoints de IA
limiter = Limiter(key_func=get_remote_address)

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
from app.api.routers.admin import router as admin_router
from app.api.routers.plantillas_gold import router as plantillas_gold_router
from app.api.routers.comentarios import router as comentarios_router
from app.api.routers.informes import router as informes_router
from app.api.routers.mi_desempeno import router as mi_desempeno_router
from app.api.routers.busqueda_semantica import router as busqueda_semantica_router
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
app.include_router(admin_router)
app.include_router(plantillas_gold_router)
app.include_router(comentarios_router)
app.include_router(informes_router)
app.include_router(mi_desempeno_router)
app.include_router(busqueda_semantica_router)


def get_glosa_service() -> GlosaService:
    return GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
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
@limiter.limit("30/minute")
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
    archivos: Optional[list[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    service: GlosaService = Depends(get_glosa_service),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    req_id = set_request_id()
    logger.info(f"[{req_id}] Análisis solicitado por: {current_user.email} | eps={eps}")

    try:
        data = GlosaInput(
            eps=eps, etapa=etapa,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
            valor_aceptado=valor_aceptado,
            tabla_excel=tabla_excel,
            numero_factura=numero_factura,
            numero_radicado=numero_radicado,
        )
    except Exception as e:
        logger.error(f"[{req_id}] Validación fallida: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    from app.services.pdf_service import PdfService
    contexto_pdf = ""
    if archivos:
        pdf_svc = PdfService()
        for archivo in archivos:
            if archivo.filename:
                try:
                    contenido = await archivo.read()
                    if contenido[:4] != b"%PDF":
                        logger.warning(f"[{req_id}] Archivo ignorado (no es PDF): {archivo.filename}")
                        continue
                    if len(contenido) > 10_000_000:
                        logger.warning(f"[{req_id}] PDF muy grande: {archivo.filename}")
                        continue
                    # OCR automático con Claude si el PDF es escaneado y hay key
                    texto, metodo = await pdf_svc.extraer_con_ocr(
                        contenido,
                        anthropic_api_key=cfg.anthropic_api_key,
                        anthropic_model=cfg.anthropic_model,
                    )
                    contexto_pdf += texto
                    logger.info(f"[{req_id}] PDF {archivo.filename}: {metodo} ({len(texto)} chars)")
                except Exception as e:
                    logger.warning(f"[{req_id}] Error extrayendo PDF {archivo.filename}: {e}")

    contrato_repo = ContratoRepository(db)
    contratos = contrato_repo.como_dict()

    # Few-shots de plantillas gold según (EPS, código) si las hay
    from app.api.routers.plantillas_gold import obtener_few_shot, marcar_usos
    codigo_match = re.search(r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b", tabla_excel.upper())
    cod_pref = codigo_match.group(0) if codigo_match else ""
    plantillas_gold = obtener_few_shot(db, eps=eps, codigo_glosa=cod_pref, limite=2) if cod_pref else []
    few_shots = [p.argumento for p in plantillas_gold]

    resultado = await service.analizar(data, contexto_pdf, contratos, few_shots=few_shots)
    if plantillas_gold:
        marcar_usos(db, [p.id for p in plantillas_gold])
    logger.info(f"[{req_id}] Análisis completado | modelo={resultado.modelo_ia} | few_shots={len(few_shots)}")

    glosa_repo = GlosaRepository(db)
    val_obj = float(re.sub(r"[^\d]", "", resultado.valor_objetado) or 0)
    val_ac = float(re.sub(r"[^\d]", "", valor_aceptado) or 0)

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
    return resultado


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/importar-masiva")
def importar_masiva():
    return FileResponse("static/importar-masiva.html")


@app.get("/importar-recepcion")
def importar_recepcion_page():
    return FileResponse("static/importar-recepcion.html")


@app.get("/presentacion")
def presentacion_ia():
    """Presentación institucional del sistema IA (pública, sin login)."""
    return FileResponse("static/presentacion-ia.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": cfg.app_version}


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
