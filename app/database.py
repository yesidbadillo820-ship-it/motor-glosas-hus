import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

# 🚀 NUEVO IMPORT: Ahora la configuración viene del Core, no de os.getenv
from app.core.config import get_settings


def registrar_pragmas_sqlite(target_engine) -> None:
    """Registra los PRAGMAs de SQLite que hacen viable producción en el
    volumen Fly: WAL (lectores no bloquean al escritor), busy_timeout
    (escrituras esperan 30s ante lock), synchronous=NORMAL (durable+rápido
    con WAL) y foreign_keys=ON. Extraído como función para poder testearlo
    sobre un engine aislado sin tocar el engine global."""

    @event.listens_for(target_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


settings = get_settings()
db_url = settings.database_url

# Corrección automática del prefijo (Render a veces usa postgres:// en vez de postgresql://)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Lógica de conexión inteligente
if db_url.startswith("postgresql"):
    # CONFIGURACIÓN PRO PARA POSTGRESQL (Producción en el HUS).
    # Tunning para Render Free Postgres que sufre SSL drops y pausas
    # de inactividad: pool más chico (Render Free limita conexiones),
    # recycle más agresivo, y connect_args con keepalives TCP para
    # detectar conexiones zombies más rápido.
    engine = create_engine(
        db_url,
        poolclass=QueuePool,
        pool_size=5,  # Render Free Postgres = 97 conexiones max,
        # con N workers podemos saturar fácil. Bajamos.
        max_overflow=10,  # Conexiones extra en picos de tráfico
        pool_pre_ping=True,  # Verifica si la conexión está viva antes de usarla
        pool_recycle=1800,  # Refresca cada 30 min — Render dropea ~1h
        pool_timeout=30,  # Espera 30s antes de TimeoutError en pool exhausto
        connect_args={
            # Keepalives TCP para detectar conexiones SSL muertas más rápido.
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "connect_timeout": 10,
        },
    )
else:
    # CONFIGURACIÓN SQLITE — local (dev/tests) y PRODUCCIÓN en volumen Fly.
    # (17-jun-2026) Migración desde Neon Postgres: el free tier de Neon
    # agotó la cuota de transferencia y tumbó producción. SQLite vive en el
    # disco persistente /data de Fly → cero egress, cero cuota, gratis.
    #
    # Para que SQLite aguante producción (1 worker uvicorn + schedulers
    # asyncio en threadpool) hay que:
    #   • check_same_thread=False  → FastAPI usa threadpool
    #   • timeout=30               → el driver espera ante "database locked"
    #   • PRAGMA journal_mode=WAL  → lectores no bloquean al escritor
    #   • PRAGMA busy_timeout      → reintenta escrituras bloqueadas 30s
    #   • PRAGMA synchronous=NORMAL→ durable con WAL, mucho más rápido
    #   • PRAGMA foreign_keys=ON   → integridad referencial (SQLite la apaga
    #                                por defecto)
    # Si la URL apunta a un archivo (sqlite:////data/x.db), crear el dir.
    if db_url.startswith("sqlite:///") and ":memory:" not in db_url:
        _ruta = db_url.replace("sqlite:///", "", 1)
        _dir = os.path.dirname(_ruta)
        if _dir:
            os.makedirs(_dir, exist_ok=True)

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    registrar_pragmas_sqlite(engine)


# Fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base para que nuestros modelos de datos (tablas) se registren aquí
Base = declarative_base()


def get_db():
    """
    Inyector de dependencias para FastAPI.
    Garantiza que la conexión se abra y se cierre de forma segura por cada petición.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
