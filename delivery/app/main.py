import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import hash_password
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Usuario, Zona
from app.routers import auth, clientes, comercios, dashboard, pedidos, repartidores, zonas

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("delivery")

settings = get_settings()


def _seed(db):
    if db.query(Usuario).count() == 0:
        admin = Usuario(
            nombre="Administrador",
            email=settings.admin_email.lower(),
            password_hash=hash_password(settings.admin_password),
            rol="ADMIN",
            activo=1,
        )
        db.add(admin)
        logger.info(f"Admin creado: {settings.admin_email}")

    if db.query(Zona).count() == 0:
        for nombre, tarifa in [
            ("Centro", 4000),
            ("Norte", 5500),
            ("Sur", 5500),
            ("Cabecera", 6000),
            ("Floridablanca", 8000),
        ]:
            db.add(Zona(nombre=nombre, tarifa_base=tarifa))
        logger.info("Zonas iniciales creadas")

    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed(db)
    finally:
        db.close()
    logger.info(f"=== {settings.app_name} listo ===")
    yield


app = FastAPI(
    title=settings.app_name,
    description="Panel de operaciones para gestión de domicilios — pedidos, repartidores, zonas y métricas en vivo.",
    version="0.1.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(pedidos.router)
app.include_router(repartidores.router)
app.include_router(clientes.router)
app.include_router(comercios.router)
app.include_router(zonas.router)
app.include_router(dashboard.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "app": settings.app_name}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse("static/login.html")
