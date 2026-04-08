import logging
import re
from contextlib import asynccontextmanager
from typing import Optional

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
from app.core.config import get_settings
from app.auth import get_password_hash
from app.core.logging_utils import set_request_id, logger

logging.basicConfig(level=logging.INFO)

CONTRATOS_DEFAULT = {
    "COOSALUD": "CONTRATOS: 68001S00060339-24 y 68001C00060340-24. TARIFA: SOAT -15% e Institucionales.",
    "COMPENSAR": "CONTRATO: CSS009-2024. TARIFA: SOAT -15% y Tarifas Propias.",
    "FAMISANAR": "CARTA DE INTENCIÓN. TARIFA: SOAT UVB -5% e Institucionales.",
    "FOMAG": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15%.",
    "LA PREVISORA": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15%.",
    "DISPENSARIO MEDICO": "CONTRATO: 440-DIGSA/DMBUG-2025. TARIFA: SOAT SMLV -20%.",
    "POLICIA NACIONAL": "CONTRATOS: 068-5-200004-26 y 068-5-200006-26. TARIFA: SOAT UVB -8%.",
    "NUEVA EPS": "CONTRATO: 02-01-06-00077-2017. TARIFA: SOAT -20%.",
    "PPL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%.",
    "FIDUCIARIA CENTRAL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%.",
    "POSITIVA": "CONTRATO: 525 - OTROSÍ 3. TARIFA: SOAT SMLV -15%.",
    "SALUD MIA": "CONTRATOS: SSA2025EVE3A005 y CSA2025EVE3A005. TARIFA: SOAT -15%.",
    "COLPATRIA": "CONTRATO: COLP-2024-001. TARIFA: SOAT -15%.",
    "AXA COLPATRIA": "CONTRATO: AXA-2024-001. TARIFA: SOAT -12%.",
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== INICIANDO APLICACIÓN ===")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    cfg = get_settings()
    try:
        # Cargar contratos iniciales
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
            ))
            logger.warning(
                "Usuario admin creado. Cambiar contraseña inmediatamente "
                "usando la variable de entorno ADMIN_PASSWORD."
            )

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

### Códigos de Respuesta
| Código | Descripción |
|--------|-------------|
| RE9502 | Glosa Extemporánea - Improcedente |
| RE9901 | Glosa Ratificada - No aceptada |
| RE9602 | Glosa Injustificada |
| RE9601 | Devolución Injustificada |
    """,
    version="5.1.0",
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
from app.services.glosa_service import GlosaService
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.glosa_repository import GlosaRepository

app.include_router(auth_router)
app.include_router(glosas_router)
app.include_router(contratos_router)
app.include_router(analytics_router)
app.include_router(plantillas_router)


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
  "tipo": "RESPUESTA RE9502",
  "resumen": "DEFENSA TÉCNICA: EXTEMPORÁNEA",
  "codigo_glosa": "TA0201",
  "valor_objetado": "$ 1,500,000",
  "mensaje_tiempo": "EXTEMPORÁNEA (25 DÍAS HÁBILES - LÍMITE: 20)",
  "score": 99.0,
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
):
    req_id = set_request_id()
    logger.info(f"[{req_id}] Iniciando análisis | eps={eps}")

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

    # CORRECCIÓN: lógica de estado correcta
    # RESPONDIDA = respuesta enviada, pendiente de resolución
    # ACEPTADA = la IPS acepta la glosa (valor_aceptado = valor total)
    # PARCIALMENTE_ACEPTADA = la IPS acepta parte
    # LEVANTADA = la EPS retira la glosa
    if val_ac >= val_obj and val_obj > 0:
        estado = "ACEPTADA"
    elif val_ac > 0:
        estado = "PARCIALMENTE_ACEPTADA"
    else:
        estado = "RESPONDIDA"

    glosa = glosa_repo.crear(
        eps=eps,
        paciente=resultado.paciente,
        codigo_glosa=resultado.codigo_glosa,
        valor_objetado=val_obj,
        valor_aceptado=val_ac,
        etapa=etapa,
        estado=estado,
        dictamen=resultado.dictamen,
        dias_restantes=resultado.dias_restantes,
        modelo_ia=resultado.modelo_ia,
        score=resultado.score,
    )

    logger.info(f"[{req_id}] Glosa guardada ID={glosa.id} | estado={estado}")
    return resultado


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": cfg.app_version}
