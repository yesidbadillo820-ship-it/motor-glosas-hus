from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import get_settings

settings = get_settings()
db_url = settings.database_url

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if db_url.startswith("postgresql"):
    engine = create_engine(
        db_url,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    engine = create_engine(
        db_url, connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_all_models():
    from app.infrastructure.db.models import GlosaRecord, ContratoRecord, UsuarioRecord, ReglaRecord
    return [GlosaRecord, ContratoRecord, UsuarioRecord, ReglaRecord]


def create_all_tables():
    for model in get_all_models():
        Base.metadata.create_all(bind=engine)
