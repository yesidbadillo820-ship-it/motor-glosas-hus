from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base

class GlosaRecord(Base):
    __tablename__ = "historial"

    id              = Column(Integer, primary_key=True, index=True)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())
    eps             = Column(String, nullable=False, index=True)
    paciente        = Column(String)
    factura         = Column(String(50), default="N/A")
    numero_radicado = Column(String(50))
    codigo_glosa    = Column(String, index=True)
    valor_objetado  = Column(Float, default=0.0)
    valor_aceptado  = Column(Float, default=0.0)
    etapa           = Column(String)
    estado          = Column(String, index=True)
    dictamen        = Column(String)
    dias_restantes  = Column(Integer, default=0)
    modelo_ia       = Column(String(100))
    workflow_state  = Column(String(50), default="RADICADA")
    score           = Column(Float, default=0.0)
    prioridad       = Column(String(50), default="BAJA")
    responsable     = Column(String(200))
    fecha_vencimiento = Column(DateTime(timezone=True))
    request_id      = Column(String(50))

    __table_args__ = (
        Index("ix_historial_alertas", "dias_restantes", "estado"),
    )

class PlantillaRecord(Base):
    """Plantillas de respuestas guardadas por el usuario"""
    __tablename__ = "plantillas"
    
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(200), nullable=False)
    codigo      = Column(String(20))  # TA0101, SO0101, etc.
    tipo        = Column(String(50))   # TARIFA, SOPORTES, etc.
    eps         = Column(String(200)) # Null = todas las EPS
    plantilla   = Column(String, nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    activa      = Column(Integer, default=1)  # 1 = activa, 0 = inactiva

class ContratoRecord(Base):
    __tablename__ = "contratos"
    eps      = Column(String, primary_key=True, index=True)
    detalles = Column(String)

class UsuarioRecord(Base):
    __tablename__ = "usuarios"
    id            = Column(Integer, primary_key=True, index=True)
    nombre        = Column(String)
    email         = Column(String, unique=True, index=True)
    password_hash = Column(String)
