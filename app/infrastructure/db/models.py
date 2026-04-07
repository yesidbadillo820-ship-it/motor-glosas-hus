from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class GlosaRecord(Base):
    __tablename__ = "glosas"

    id              = Column(Integer, primary_key=True, index=True)
    eps             = Column(String, nullable=False, index=True)
    paciente        = Column(String)
    factura         = Column(String, default="N/A")
    autorizacion    = Column(String, default="N/A")
    codigo_glosa    = Column(String, index=True)
    valor_objetado  = Column(Float, default=0.0)
    valor_aceptado  = Column(Float, default=0.0)
    etapa           = Column(String)
    estado          = Column(String, default="RADICADA", index=True)
    dictamen        = Column(String)
    dias_restantes  = Column(Integer, default=0)
    score           = Column(Integer, default=0)
    prioridad       = Column(String, default="BAJA")
    modelo_ia       = Column(String, nullable=True)
    responsable_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en  = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_glosas_eps_estado", "eps", "estado"),
        Index("ix_glosas_prioridad", "prioridad", "score"),
    )


class ContratoRecord(Base):
    __tablename__ = "contratos"

    eps             = Column(String, primary_key=True)
    detalles        = Column(String)
    version         = Column(Integer, default=1)
    vigente         = Column(Boolean, default=True)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en  = Column(DateTime(timezone=True), onupdate=func.now())


class UsuarioRecord(Base):
    __tablename__ = "usuarios"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String, nullable=False)
    email           = Column(String, unique=True, index=True, nullable=False)
    password_hash   = Column(String, nullable=False)
    rol             = Column(String, default="auditor", index=True)
    eps_permitidos  = Column(String, default="")
    activo          = Column(Boolean, default=True)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())


class HistorialGlosaRecord(Base):
    __tablename__ = "historial_glosas"

    id              = Column(Integer, primary_key=True, index=True)
    glosa_id        = Column(Integer, ForeignKey("glosas.id"), nullable=False)
    estado_anterior = Column(String)
    estado_nuevo    = Column(String)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observacion     = Column(String)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())


class ReglaRecord(Base):
    __tablename__ = "reglas"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String, unique=True, nullable=False)
    codigo          = Column(String, unique=True, nullable=False)
    descripcion     = Column(String)
    parametros      = Column(String)
    activa          = Column(Boolean, default=True)
    version         = Column(Integer, default=1)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en  = Column(DateTime(timezone=True), onupdate=func.now())