from pydantic import BaseModel
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from database import Base

# --- Esquemas Pydantic ---

class GlosaInput(BaseModel):
    eps: str
    etapa: str
    fecha_radicacion: Optional[str] = None
    fecha_recepcion: Optional[str] = None
    valor_aceptado: str
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
    factura: Optional[str] = "N/A"
    autorizacion: Optional[str] = "N/A"
    score: Optional[int] = 100
    dias_restantes: Optional[int] = 0

class PDFRequest(BaseModel):
    eps: str
    resumen: str
    dictamen: str
    codigo: Optional[str] = "N/A"
    valor: Optional[str] = "N/A"

class ContratoInput(BaseModel):
    eps: str
    detalles: str

# --- Modelos SQLAlchemy ---

class GlosaRecord(Base):
    __tablename__ = "historial"
    
    id = Column(Integer, primary_key=True, index=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    eps = Column(String)
    paciente = Column(String)
    factura = Column(String, default="N/A")
    codigo_glosa = Column(String)
    valor_objetado = Column(Float)
    valor_aceptado = Column(Float)
    etapa = Column(String)
    estado = Column(String)
    dictamen = Column(String)
    dias_restantes = Column(Integer, default=0)

class ContratoRecord(Base):
    __tablename__ = "contratos"
    
    eps = Column(String, primary_key=True, index=True)
    detalles = Column(String)

class UsuarioRecord(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
