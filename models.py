from typing import Optional
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.sql import func
from database import Base

class GlosaInput(BaseModel):
    eps: str
    etapa: str = "INICIAL"
    fecha_radicacion: Optional[str] = None
    fecha_recepcion: Optional[str] = None
    valor_aceptado: str = "0"
    tabla_excel: str

class GlosaResult(BaseModel):
    tipo: str
    resumen: str
    dictamen: str
    codigo_glosa: str
    valor_objetado: str
    paciente: str
    mensaje_tiempo: str
    color_tiempo: str

class PDFRequest(BaseModel):
    eps: str
    resumen: str
    dictamen: str

class ContratoInput(BaseModel):
    eps: str
    detalles: str

class GlosaRecord(Base):
    __tablename__ = "glosas_historial"

    id = Column(Integer, primary_key=True, index=True)
    eps = Column(String, index=True)
    paciente = Column(String)
    codigo_glosa = Column(String, index=True)
    valor_objetado = Column(Float, default=0.0)
    valor_aceptado = Column(Float, default=0.0)
    etapa = Column(String)
    estado = Column(String) 
    dictamen = Column(Text)
    creado_en = Column(DateTime, server_default=func.now())

class PlantillaGlosa(Base):
    __tablename__ = "plantillas"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, index=True)
    texto = Column(String)

class ContratoRecord(Base):
    __tablename__ = "contratos_config"
    
    id = Column(Integer, primary_key=True, index=True)
    eps = Column(String, unique=True, index=True)
    detalles = Column(Text)

class UsuarioRecord(Base):
    __tablename__ = "usuarios_sistema"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    activo = Column(Boolean, default=True)
