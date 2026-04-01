import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

# Render inyectará esta variable. Si no la encuentra, usa SQLite como salvavidas.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./glosas.db")

# Corrección automática (Render a veces da la URL como postgres:// en vez de postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("postgresql"):
    # CONFIGURACIÓN PRO PARA POSTGRESQL (Evita que la base de datos se bloquee)
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    # CONFIGURACIÓN BÁSICA PARA SQLITE
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
