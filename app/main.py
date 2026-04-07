import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base, SessionLocal
from app.models.db import ContratoRecord, UsuarioRecord
from app.core.config import get_settings
from app.auth import get_password_hash

# Routers
from app.api.routers import glosas, contratos, analytics
from app.api.routers.auth_router import router as auth_router


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("motor_glosas")
for h in logger.handlers:
    h.setFormatter(JsonFormatter())

CONTRATOS_DEFAULT = {
    "COOSALUD": "CONTRATOS: 68001S00060339-24 y 68001C00060340-24. TARIFA: SOAT -15% e Institucionales. OBS: MAOS por HUS, Oncológicos por EPS.",
    "COMPENSAR": "CONTRATO: CSS009-2024. TARIFA: SOAT -15% y Tarifas Propias. OBS: Excluye oncológicos. MAOS por EPS.",
    "FAMISANAR": "CARTA DE INTENCIÓN. TARIFA: SOAT UVB -5% e Institucionales.",
    "FOMAG": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15%, Institucionales y Paquetes (Tórax, IVE, Columna, Terapias, Gastro).",
    "LA PREVISORA": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15% y Paquetes.",
    "DISPENSARIO MEDICO": "CONTRATO: 440-DIGSA/DMBUG-2025. TARIFA: SOAT SMLV -20% e Institucionales.",
    "POLICIA NACIONAL": "CONTRATOS: 068-5-200004-26 y 068-5-200006-26. TARIFA: SOAT UVB -8% e Institucionales. OBS: Contrato 0006-26 INCLUYE medicamentos oncológicos.",
    "NUEVA EPS": "CONTRATO: 02-01-06-00077-2017. TARIFA: SOAT -20% e Institucionales. OBS: Meds Oncológicos por HUS.",
    "PPL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%. OBS: MAOS y Meds por HUS.",
    "FIDUCIARIA CENTRAL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%.",
    "POSITIVA": "CONTRATO: 525 - OTROSÍ 3. TARIFA: SOAT SMLV -15%. OBS: Solo accidentes/laboral.",
    "PRECIMED": "CONTRATO: 319 DE 2024. TARIFA: Tarifas anexos / Institucionales.",
    "SALUD MIA": "CONTRATOS: SSA2025EVE3A005 y CSA2025EVE3A005. TARIFA: SOAT -15%. OBS: Urgencias Circular 019/2023.",
    "AURORA": "CONTRATOS: GID ARL 0090 y GID AP 0090. TARIFA: SOAT -3%.",
    "SECRETARIA DE SANTANDER": "MARCO LEGAL: Resolución 15997 de 2017 (Tarifas obligatorias ente territorial).",
    "SUMIMEDICAL": "CONTRATO: FPS23-050. TARIFA: SOAT -15%. OBS: MAOS y Oncológicos por EPS.",
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO (RESOLUCIÓN 054 DE 2026_0001 / DECRETO 441 DE 2022)."
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(ContratoRecord).count() == 0:
            for k, v in CONTRATOS_DEFAULT.items():
                db.add(ContratoRecord(eps=k, detalles=v))
        if db.query(UsuarioRecord).count() == 0:
            db.add(UsuarioRecord(
                nombre="Auditor Principal",
                email="admin@hus.gov.co",
                password_hash=get_password_hash("admin123"),
            ))
        db.commit()
    finally:
        db.close()
    yield

cfg = get_settings()

app = FastAPI(title=cfg.app_name, version=cfg.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://hus.gov.co"],   # ya no es *
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Registrar todos los routers
app.include_router(auth_router)
app.include_router(glosas.router)
app.include_router(contratos.router)
app.include_router(analytics.router)


@app.get("/")
def root():
    return FileResponse("static/index.html")
