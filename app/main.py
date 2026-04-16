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
    "DISPENSARIO MEDICO": "CONTRATO No. 440-DIGSA/DMBUG-2025. TARIFA: SOAT -15%.",
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
            ("radicadevoluciones@sinacsc.com","AUDITOR",    "KAREN ORTIZ"),
            ("devoluciones01@sinacsc.com",   "AUDITOR",     "YUDY"),
            ("coordinacioncartera@hus.gov.co","AUDITOR",    "YUDY"),
            ("glosashus08@sinacsc.com",      "AUDITOR",     "CLAUDIA"),
            ("glosashus07@sinacsc.com",      "AUDITOR",     "YENFERSON ORTEGA"),
            ("carterahus04@sinacsc.com",     "AUDITOR",     "MILENA"),
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


def get_glosa_service() -> GlosaService:
    return GlosaService(groq_api_key=cfg.groq_api_key, anthropic_api_key=cfg.anthropic_api_key)


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
                    contexto_pdf += await pdf_svc.extraer(contenido)
                except Exception as e:
                    logger.warning(f"[{req_id}] Error extrayendo PDF {archivo.filename}: {e}")

    contrato_repo = ContratoRepository(db)
    contratos = contrato_repo.como_dict()

    resultado = await service.analizar(data, contexto_pdf, contratos)
    logger.info(f"[{req_id}] Análisis completado | modelo={resultado.modelo_ia}")

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
        texto_aceptacion = f"ESE HUS ACEPTA LA GLOSA POR VALOR DE ${val_ac:,.0f}"
    elif val_ac >= val_obj and val_obj > 0:
        estado = "ACEPTADA"
        cod_res_aceptacion = "RE9702"
        desc_res_aceptacion = "GLOSA ACEPTADA AL 100%"
        texto_aceptacion = f"ESE HUS ACEPTA LA GLOSA POR VALOR DE ${val_obj:,.0f}"
    elif val_ac > 0:
        estado = "PARCIALMENTE_ACEPTADA"
        cod_res_aceptacion = "RE9801"
        desc_res_aceptacion = "GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE"
        texto_aceptacion = f"ESE HUS ACEPTA PARCIALMENTE LA GLOSA POR VALOR DE ${val_ac:,.0f}"
    else:
        estado = "RADICADA"
        cod_res_aceptacion = None
        desc_res_aceptacion = None
        texto_aceptacion = None

    # Si hay aceptación, generar dictamen completamente nuevo
    dictamen_final = resultado.dictamen
    if estado in ("ACEPTADA", "PARCIALMENTE_ACEPTADA"):
        val_rechazado = val_obj - val_ac
        
        # Generar texto de aceptación apropiado
        if estado == "ACEPTADA":
            argumento_aceptacion = f"""
            <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:20px;margin:15px 0;border-radius:8px;">
                <h4 style="color:#15803d;margin:0 0 10px 0;">RESPUESTA A GLOSA</h4>
                <p style="font-size:13px;line-height:1.8;color:#166534;">
                    EL HOSPITAL UNIVERSITARIO DE SANTANDER INFORMA A {eps.upper()} QUE ACEPTA LA PRESENTE GLOSA 
                    POR VALOR DE <strong>${val_ac:,.0f}</strong> (VALOR TOTAL OBJETADO), 
                    DE CONFORMIDAD CON LO ESTABLECIDO EN LA RESOLUCIÓN 3047 DE 2008 Y DEMÁS NORMATIVA VIGENTE.
                </p>
                <p style="font-size:13px;line-height:1.8;color:#166534;">
                    SE SOLICITA PROCEDER CON EL RECONOCIMIENTO Y PAGO CORRESPONDIENTE EN EL PRÓXIMO CICLO DE PAGOS.
                </p>
            </div>"""
        else:
            # BUG 2 FIX: Usar "VALOR EN DISPUTA" en lugar de "SALDO PENDIENTE"
            val_en_disputa = abs(val_rechazado)  # Garantizar valor positivo
            argumento_aceptacion = f"""
            <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:20px;margin:15px 0;border-radius:8px;">
                <h4 style="color:#92400e;margin:0 0 10px 0;">RESPUESTA A GLOSA</h4>
                <p style="font-size:13px;line-height:1.8;color:#78350f;">
                    EL HOSPITAL UNIVERSITARIO DE SANTANDER INFORMA A {eps.upper()} QUE ACEPTA PARCIALMENTE 
                    LA PRESENTE GLOSA POR VALOR DE <strong>${val_ac:,.0f}</strong>, 
                    QUEDANDO UN <strong>VALOR EN DISPUTA DE ${val_en_disputa:,.0f}</strong>.
                </p>
                <p style="font-size:13px;line-height:1.8;color:#78350f;">
                    EL VALOR EN DISPUTA DE <strong>${val_en_disputa:,.0f}</strong> NO ES ACEPTADO POR ESE HUS 
                    Y SE MANTIENE EN TRÁMITE PARA LO CUAL SE ADJUNTAN LOS ARGUMENTOS TÉCNICOS Y JURÍDICOS RESPECTIVOS.
                </p>
            </div>"""
        
        # Tabla con valores
        tabla_valores = f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:15px;margin-top:15px;">
            <div style="font-weight:bold;color:#475569;margin-bottom:10px;font-size:12px;">RESUMEN DE VALORES</div>
            <table style="width:100%;border-collapse:collapse;font-size:12px;">
                <tr style="background:#f1f5f9;">
                    <td style="padding:8px;font-weight:bold;color:#64748b;">VALOR OBJETADO:</td>
                    <td style="padding:8px;text-align:right;font-weight:bold;">$ {val_obj:,.0f}</td>
                </tr>
                <tr style="background:#dcfce7;">
                    <td style="padding:8px;font-weight:bold;color:#166534;">VALOR ACEPTADO:</td>
                    <td style="padding:8px;text-align:right;font-weight:bold;color:#16a34a;">$ {val_ac:,.0f}</td>
                </tr>"""
        
        if estado == "PARCIALMENTE_ACEPTADA":
            tabla_valores += f"""
                <tr style="background:#fee2e2;">
                    <td style="padding:8px;font-weight:bold;color:#991b1b;">VALOR EN DISPUTA:</td>
                    <td style="padding:8px;text-align:right;font-weight:bold;color:#dc2626;">$ {val_en_disputa:,.0f}</td>
                </tr>"""
        
        tabla_valores += """
            </table>
        </div>"""

        # Generar dictamen nuevo completo
        dictamen_final = f"""
        <table border="1" style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:15px;background:white;">
            <tr style="background-color:#16a34a;color:white;">
                <th style="padding:10px;text-align:center;">CÓDIGO GLOSA</th>
                <th style="padding:10px;text-align:center;">VALOR OBJETADO</th>
                <th style="padding:10px;text-align:center;">CÓDIGO RESPUESTA</th>
            </tr>
            <tr>
                <td style="padding:10px;text-align:center;font-weight:bold;">{resultado.codigo_glosa}</td>
                <td style="padding:10px;text-align:center;font-weight:bold;color:#16a34a;">$ {val_obj:,.0f}</td>
                <td style="padding:10px;text-align:center;"><b>{cod_res_aceptacion}</b><br><span style="font-size:10px">{desc_res_aceptacion}</span></td>
            </tr>
        </table>

        <div style="background:#f8fafc;border-radius:12px;padding:20px;border-left:4px solid #16a34a;margin-top:15px;">
            <div style="display:flex;gap:10px;margin-bottom:15px;">
                <span style="background:#16a34a;color:white;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:700;">{eps.upper()}</span>
                <span style="background:#fef3c7;color:#92400e;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:600;">{resultado.codigo_glosa}</span>
            </div>
        </div>

        {argumento_aceptacion}
        {tabla_valores}

        <div style="margin-top:20px;padding:15px;background:#fef3c7;border-radius:8px;font-size:11px;color:#92400e;">
            <b>FECHA DE RESPUESTA:</b> {fecha_hoy_espanol()}
        </div>

        <div style="margin-top:15px;padding:12px;background:#f0fdf4;border-radius:8px;font-size:10px;color:#166534;">
            <b>Nota:</b> Este documento constituye la respuesta formal a la glosa objetada, de conformidad con la normativa colombiana vigente.
        </div>"""

    # Crear glosa con el resultado
    tipo_final = f"RESPUESTA {cod_res_aceptacion}" if cod_res_aceptacion else resultado.tipo
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
    )

    if estado == "RADICADA":
        glosa_repo.actualizar_estado(glosa.id, "RESPONDIDA", responsable=current_user.email)

    logger.info(f"[{req_id}] Glosa guardada ID={glosa.id} | estado={estado}")
    
    # Retornar resultado actualizado con el nuevo tipo
    resultado.tipo = tipo_final
    resultado.dictamen = dictamen_final
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


@app.get("/health")
def health():
    return {"status": "ok", "version": cfg.app_version}
