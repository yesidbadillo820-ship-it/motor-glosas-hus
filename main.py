import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import engine, Base, SessionLocal
from models.db import ContratoRecord, UsuarioRecord
from core.config import get_settings
from auth import get_password_hash

# Routers
from api.routers import glosas, contratos, analytics, exports
from api.routers.auth_router import router as auth_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("motor_glosas")

CONTRATOS_DEFAULT = { ... }  # igual que antes

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
app.include_router(exports.router)

@app.get("/")
def root():
    return FileResponse("static/index.html")
