from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class RolUsuario(str, enum.Enum):
    ADMIN = "admin"
    AUDITOR = "auditor"
    CARTERA = "cartera"


class UsuarioRecord(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="auditor")
    activo = Column(Boolean, default=True)
    eps_asignadas = Column(String, default="")
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())


class GlosaRecord(Base):
    __tablename__ = "historial"
    
    id = Column(Integer, primary_key=True, index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    eps = Column(String, nullable=False, index=True)
    paciente = Column(String)
    factura = Column(String, default="N/A")
    codigo_glosa = Column(String, index=True)
    valor_objetado = Column(Float, default=0.0)
    valor_aceptado = Column(Float, default=0.0)
    etapa = Column(String)
    estado = Column(String, index=True)
    dictamen = Column(String)
    dias_restantes = Column(Integer, default=0)
    dias_habiles = Column(Integer, default=0)
    es_extemporanea = Column(Boolean, default=False)
    score = Column(Integer, default=0)
    prioridad = Column(String, default="BAJA")
    modelo_ia = Column(String, nullable=True)
    responsable_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observaciones = Column(String, default="")
    fecha_radicacion = Column(DateTime, nullable=True)
    fecha_recepcion = Column(DateTime, nullable=True)
    fecha_estado = Column(DateTime, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    responsable = relationship("UsuarioRecord", foreign_keys=[responsable_id])


class ContratoRecord(Base):
    __tablename__ = "contratos"
    eps = Column(String, primary_key=True, index=True)
    detalles = Column(String)
    version = Column(Integer, default=1)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    activo = Column(Boolean, default=True)


class ReglaRecord(Base):
    __tablename__ = "reglas"
    id = Column(String, primary_key=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(String)
    tipo = Column(String)
    activa = Column(Boolean, default=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    parametros = Column(String, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
