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
    # CONFIGURACIÓN PRO PARA POSTGRESQL (Producción en el HUS)
    engine = create_engine(
        db_url,
        poolclass=QueuePool,
        pool_size=10,          # Conexiones simultáneas permitidas
        max_overflow=20,       # Conexiones extra en picos de tráfico
        pool_pre_ping=True,    # Verifica si la conexión está viva antes de usarla
        pool_recycle=3600,     # Refresca las conexiones cada hora
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
