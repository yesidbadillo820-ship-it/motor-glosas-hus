from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

# 🚀 NUEVO IMPORT: Ahora la configuración viene del Core, no de os.getenv
from app.core.config import get_settings

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
        pool_size=5,           # Render Free Postgres = 97 conexiones max,
                                # con N workers podemos saturar fácil. Bajamos.
        max_overflow=10,       # Conexiones extra en picos de tráfico
        pool_pre_ping=True,    # Verifica si la conexión está viva antes de usarla
        pool_recycle=1800,     # Refresca cada 30 min — Render dropea ~1h
        pool_timeout=30,       # Espera 30s antes de TimeoutError en pool exhausto
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
    # CONFIGURACIÓN BÁSICA PARA SQLITE (Fallback local)
    engine = create_engine(
        db_url, connect_args={"check_same_thread": False}
    )

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
