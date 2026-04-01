import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://hus_user:hus_password@localhost:5432/motor_glosas"
)

# QueuePool es crítico en producción: evita que FastAPI agote conexiones
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,          # conexiones permanentes en el pool
    max_overflow=20,       # conexiones extra permitidas en picos
    pool_pre_ping=True,    # detecta conexiones muertas antes de usarlas
    pool_recycle=3600,     # recicla conexiones cada hora
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
