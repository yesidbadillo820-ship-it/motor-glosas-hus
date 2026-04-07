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
    rol:          Optional[str] = "auditor"
    eps_asignadas: Optional[list[str]] = []


class UsuarioCreate(BaseModel):
    nombre:        str = Field(..., min_length=2)
    email:         str = Field(..., email=True)
    password:      str = Field(..., min_length=6)
    rol:           str = Field(default="auditor")
    eps_asignadas: Optional[list[str]] = []


class UsuarioResponse(BaseModel):
    id:             int
    nombre:         str
    email:          str
    rol:            str
    eps_asignadas:  Optional[list[str]] = []
    activo:         bool
    
    model_config = {"from_attributes": True}


class WorkflowTransition(BaseModel):
    glosa_id:      int
    nuevo_estado:   str
    motivo:        Optional[str] = None
    
    @field_validator("nuevo_estado")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        estados_validos = ["RADICADA", "EN_REVISION", "RESPONDIDA", "ACEPTADA", "RECHAZADA", "CERRADA"]
        v_upper = v.upper()
        if v_upper not in estados_validos:
            raise ValueError(f"Estado debe ser uno de: {estados_validos}")
        return v_upper


class GlosaDetail(BaseModel):
    id:               int
    eps:              str
    paciente:         str
    codigo_glosa:     str
    valor_objetado:   float
    valor_aceptado:   float
    etapa:            str
    estado:           str
    estado_workflow:  str
    prioridad:        str
    score:            int
    dias_restantes:   int
    responsable_id:   Optional[int] = None
    comentario:       Optional[str] = None
    modelo_ia:        Optional[str] = None
    created_at:       str
    updated_at:       str
    
    model_config = {"from_attributes": True}


class GlosaScoreRequest(BaseModel):
    glosa_id: int


class GlosaScoreResponse(BaseModel):
    glosa_id: int
    score: float
    prioridad: str
    valor_ajustado: float
    probabilidad_recuperacion: float
    dias_hasta_vencimiento: int


class AsyncTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class ReglaEvaluacion(BaseModel):
    nombre: str
    cumple: bool
    mensaje: str
    severidad: str


class ReglasResponse(BaseModel):
    glosa_id: int
    reglas: list[ReglaEvaluacion]
    tiene_infracciones_criticas: bool


class ContratoVersionInput(BaseModel):
    eps:      str = Field(..., min_length=2)
    version:  int
    detalles: str = Field(..., min_length=10)


class ContratoVersionResponse(BaseModel):
    id:       int
    eps:      str
    version:  int
    detalles: str
    activo:   bool
    creado_en: str
    
    model_config = {"from_attributes": True}
