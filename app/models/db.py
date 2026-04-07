from sqlalchemy import Column, Integer, String, Float, DateTime, Index, Text
from sqlalchemy.sql import func
from app.database import Base


class GlosaRecord(Base):
    __tablename__ = "historial"

    id              = Column(Integer, primary_key=True, index=True)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())
    eps             = Column(String, nullable=False, index=True)
    paciente        = Column(String)
    factura         = Column(String, default="N/A")
    codigo_glosa    = Column(String, index=True)
    valor_objetado  = Column(Float, default=0.0)
    valor_aceptado  = Column(Float, default=0.0)
    etapa           = Column(String)
    estado          = Column(String, index=True, default="RADICADA")
    dictamen        = Column(Text)
    dias_restantes  = Column(Integer, default=0)
    score           = Column(Integer, default=0, index=True)
    modelo_ia       = Column(String, nullable=True)
    responsable    = Column(String, nullable=True)
    fecha_radicacion = Column(DateTime(timezone=True), nullable=True)
    fecha_recepcion = Column(DateTime(timezone=True), nullable=True)
    probabilidad_recuperacion = Column(Float, default=0.8)

    __table_args__ = (
        Index("ix_historial_alertas", "dias_restantes", "estado"),
        Index("ix_historial_score", "score", "estado"),
        Index("ix_historial_eps_estado", "eps", "estado"),
    )

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
