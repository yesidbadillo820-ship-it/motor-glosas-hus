from pydantic import BaseModel
from typing import Optional, List

class GlosaInput(BaseModel):
    eps: str
    etapa: str
    fecha_radicacion: str
    fecha_recepcion: str
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
