from __future__ import annotations
import re
from typing import Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator, model_validator

# ── Entrada ───────────────────────────────────────────────────────────────────

class GlosaInput(BaseModel):
    eps: str                  = Field(..., min_length=2, max_length=100)
    etapa: str                = Field(..., pattern=r"^(INICIAL|RATIF| RATIFICACION|RESPUESTA)$")
    fecha_radicacion: Optional[date] = None
    fecha_recepcion:  Optional[date] = None
    valor_aceptado: str       = Field(default="0")
    tabla_excel: str          = Field(..., min_length=5,
                                      description="Texto copiado de la glosa en Excel")

    @field_validator("etapa")
    @classmethod
    def etapa_uppercase(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("eps")
    @classmethod
    def eps_uppercase(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("valor_aceptado")
    @classmethod
    def valor_solo_numeros(cls, v: str) -> str:
        # Limpia $ , . y espacios — acepta "$ 1.500.000" o "1500000"
        cleaned = re.sub(r"[^\d]", "", v)
        return cleaned or "0"

    @model_validator(mode="after")
    def fechas_coherentes(self) -> GlosaInput:
        if self.fecha_radicacion and self.fecha_recepcion:
            if self.fecha_recepcion < self.fecha_radicacion:
                raise ValueError(
                    "fecha_recepcion no puede ser anterior a fecha_radicacion"
                )
        return self

class ContratoInput(BaseModel):
    eps:      str = Field(..., min_length=2, max_length=100)
    detalles: str = Field(..., min_length=10)

    @field_validator("eps")
    @classmethod
    def eps_uppercase(cls, v: str) -> str:
        return v.strip().upper()

class PDFRequest(BaseModel):
    eps:      str
    resumen:  str
    dictamen: str
    codigo:   Optional[str] = "N/A"
    valor:    Optional[str] = "N/A"

# ── Salida ────────────────────────────────────────────────────────────────────

class GlosaResult(BaseModel):
    tipo:            str
    resumen:         str
    dictamen:        str
    codigo_glosa:    str
    valor_objetado:  str
    paciente:        str
    mensaje_tiempo:  str
    color_tiempo:    str
    factura:         Optional[str] = "N/A"
    autorizacion:    Optional[str] = "N/A"
    score:           int           = Field(default=0, ge=0, le=100)
    dias_restantes:  int           = Field(default=0, ge=0)
    modelo_ia:       Optional[str] = None   # nuevo: qué modelo respondió

class GlosaHistorialItem(BaseModel):
    id:              int
    eps:             str
    paciente:        str
    codigo_glosa:    str
    valor_objetado:  float
    valor_aceptado:  float
    etapa:           str
    estado:          str
    dias_restantes:  int
    creado_en:       str

    model_config = {"from_attributes": True}  # permite crear desde ORM

class AnalyticsResult(BaseModel):
    glosas_mes:            int
    valor_objetado_mes:    float
    valor_recuperado_mes:  float
    tasa_exito_pct:        float

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    nombre:       str
