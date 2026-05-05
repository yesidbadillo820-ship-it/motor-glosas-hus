from __future__ import annotations
import re
from typing import Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator, model_validator

# ── Entrada ───────────────────────────────────────────────────────────────────

class GlosaInput(BaseModel):
    eps: str                  = Field(..., min_length=2, max_length=100)
    etapa: str                = Field(..., min_length=3)
    fecha_radicacion: Optional[date] = None
    fecha_recepcion:  Optional[date] = None

    @field_validator("fecha_radicacion", "fecha_recepcion", mode="before")
    @classmethod
    def parse_fecha_vacia(cls, v):
        if v == "" or v is None:
            return None
        return v

    valor_aceptado: str       = Field(default="0")
    # R55 P1: max_length para evitar payloads abusivos (50KB es 5x más
    # de lo que ocupa una glosa real bien detallada).
    tabla_excel: str          = Field(..., min_length=3, max_length=50_000,
                                      description="Texto copiado de la glosa en Excel")
    # NUEVOS: campos exigidos por Resolución 3047/2008 para trazabilidad
    numero_factura:   Optional[str] = Field(default=None, max_length=50,
                                            description="Número de factura objetada")
    numero_radicado:  Optional[str] = Field(default=None, max_length=50,
                                            description="Número de radicado de la glosa")
    # Tono de la respuesta: conciliador (default), neutral o firme
    tono: Optional[str] = Field(default="conciliador", max_length=20,
                                description="Tono de la respuesta: conciliador | neutral | firme")
    # Modo de respuesta por concepto:
    #   "defender"          → argumento IA completo (default)
    #   "aceptar_total"     → RE9702, sin IA, plantilla corta
    #   "aceptar_parcial"   → RE9801, argumento IA sobre la diferencia + aceptacion parcial
    #   "auditoria_previa"  → R59: la IA NO redacta dictamen, da diagnóstico
    #                         neutral (hallazgos, riesgos, recomendación) para
    #                         que el gestor decida qué hacer.
    modo_respuesta: Optional[str] = Field(default="defender", max_length=30,
                                           description="defender | aceptar_total | aceptar_parcial | auditoria_previa")
    # Para aceptar_parcial: valor que se acepta (el resto se defiende)
    valor_aceptado_parcial: Optional[float] = Field(default=0.0, ge=0,
                                                     description="Valor COP aceptado por el prestador (solo aplica en aceptar_parcial)")
    # Multi-modal soportes (Tier 1 #5): cuando True, los PDFs adjuntos
    # se envían binarios directos a Claude (soporte nativo Messages API)
    # en lugar de pre-procesarse con pdfplumber/OCR. Más caro en tokens
    # (~3-5x) pero mucho más preciso para PDFs con tablas complejas,
    # escaneos con OCR incrustado o fonts no estándar — equivalente al
    # patrón ya validado en /contratos/{eps}/pdf.
    usar_pdf_nativo_soportes: Optional[bool] = Field(default=False,
                                                      description="Lectura PDF avanzada de soportes (más caro, más preciso)")

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
        cleaned = re.sub(r"[^\d]", "", v)
        return cleaned or "0"

    # R55 P1: validators de enumeración para tono y modo_respuesta.
    # Si el cliente envía un valor desconocido, fallback al default
    # silenciosamente (no romper la request, solo prevenir injection).
    @field_validator("tono", mode="before")
    @classmethod
    def tono_valido(cls, v):
        if not v:
            return "conciliador"
        v_norm = str(v).strip().lower()
        if v_norm in ("conciliador", "neutral", "firme"):
            return v_norm
        return "conciliador"

    @field_validator("modo_respuesta", mode="before")
    @classmethod
    def modo_valido(cls, v):
        if not v:
            return "defender"
        v_norm = str(v).strip().lower()
        if v_norm in ("defender", "aceptar_total", "aceptar_parcial", "auditoria_previa"):
            return v_norm
        return "defender"

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
    # CORRECCIÓN: era int, pero _calcular_score retorna float
    score:           float         = Field(default=0.0, ge=0.0, le=100.0)
    dias_restantes:  int           = Field(default=0, ge=0)
    modelo_ia:       Optional[str] = None
    # Indicador de riesgo de ratificación (0-100, más bajo = más probable levantamiento)
    riesgo_ratificacion: Optional[dict] = None
    # ID en BD (llenado por main.py después de persistir) — permite refinar/gold
    glosa_id:        Optional[int] = None
    # R-cerebro #8: decisión autónoma de la IA sobre la glosa.
    # Valores posibles: DEFENDER_TOTAL | ACEPTAR_PARCIAL | ACEPTAR_TOTAL | REVISAR
    accion_ia:       Optional[str] = None
    valor_aceptar_ia: Optional[float] = None
    valor_defender_ia: Optional[float] = None
    # Verificación de citas legales (citation_verifier) y score de
    # confianza (confidence_scorer) — calculados post-dictamen para que
    # la UI pueda mostrar warnings y badge de calidad. Opcionales para
    # no romper consumidores que no los esperan.
    verificacion_citas: Optional[dict] = None
    confianza:          Optional[dict] = None


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

    model_config = {"from_attributes": True}


class AnalyticsResult(BaseModel):
    glosas_mes:            int
    valor_objetado_mes:    float
    valor_recuperado_mes:  float
    tasa_exito_pct:        float


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    nombre:       str
    rol:          Optional[str] = None
    # True si el usuario debe cambiar su password antes de operar
    must_change_password: Optional[bool] = False


class CambiarPasswordRequest(BaseModel):
    password_actual: str = Field(..., min_length=1, max_length=200)
    password_nueva: str = Field(..., min_length=8, max_length=200,
                                 description="Mínimo 8 caracteres")
    password_nueva_confirmacion: str = Field(..., min_length=8, max_length=200)
