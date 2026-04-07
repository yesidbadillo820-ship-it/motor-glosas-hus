from sqlalchemy import Column, Integer, String, Float, DateTime, Index, ForeignKey, Text, Boolean
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
    estado          = Column(String, index=True)
    dictamen        = Column(String)
    dias_restantes  = Column(Integer, default=0)
    modelo_ia       = Column(String, nullable=True)
    
    score           = Column(Integer, default=0)
    prioridad       = Column(String, default="media")
    estado_workflow = Column(String, default="RADICADA")
    
    responsable_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    comentario      = Column(Text, nullable=True)
    
    fecha_cambio_estado = Column(DateTime(timezone=True), nullable=True)
    sla_vencimiento    = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_historial_alertas", "dias_restantes", "estado"),
        Index("ix_historial_workflow", "estado_workflow", "eps"),
        Index("ix_historial_score", "score", "estado"),
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
    rol           = Column(String, default="auditor")
    eps_asignadas = Column(Text, nullable=True)
    activo        = Column(Boolean, default=True)


class ContratoVersionRecord(Base):
    __tablename__ = "contratos_version"
    id          = Column(Integer, primary_key=True, index=True)
    eps         = Column(String, nullable=False, index=True)
    version     = Column(Integer, nullable=False)
    detalles    = Column(Text, nullable=False)
    creado_en   = Column(DateTime(timezone=True), server_default=func.now())
    activo      = Column(Boolean, default=True)
    
    __table_args__ = (
        Index("ix_contrato_version_eps", "eps", "version"),
    )


class ReglaVersionRecord(Base):
    __tablename__ = "reglas_version"
    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String, nullable=False)
    descripcion = Column(Text)
    config      = Column(Text)
    version     = Column(Integer, nullable=False)
    activo      = Column(Boolean, default=True)
    creado_en   = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index("ix_reglas_version_nombre", "nombre", "version"),
    )
