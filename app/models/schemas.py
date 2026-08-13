from __future__ import annotations
from typing import Optional
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.moneda import parse_valor_cop

# ── Entrada ───────────────────────────────────────────────────────────────────


class GlosaInput(BaseModel):
    eps: str = Field(..., min_length=2, max_length=100)
    etapa: str = Field(..., min_length=3)
    fecha_radicacion: Optional[date] = None
    fecha_recepcion: Optional[date] = None

    @field_validator("fecha_radicacion", "fecha_recepcion", mode="before")
    @classmethod
    def parse_fecha_vacia(cls, v):
        if v == "" or v is None:
            return None
        return v

    valor_aceptado: str = Field(default="0")
    # R55 P1: max_length para evitar payloads abusivos (50KB es 5x más
    # de lo que ocupa una glosa real bien detallada).
    tabla_excel: str = Field(
        ..., min_length=3, max_length=50_000, description="Texto copiado de la glosa en Excel"
    )
    # NUEVOS: campos exigidos por Resolución 3047/2008 para trazabilidad
    numero_factura: Optional[str] = Field(
        default=None, max_length=50, description="Número de factura objetada"
    )
    numero_radicado: Optional[str] = Field(
        default=None, max_length=50, description="Número de radicado de la glosa"
    )
    # Tono de la respuesta: conciliador (default), neutral o firme
    tono: Optional[str] = Field(
        default="conciliador",
        max_length=20,
        description="Tono de la respuesta: conciliador | neutral | firme",
    )
    # Modo de respuesta por concepto:
    #   "defender"          → argumento IA completo (default)
    #   "aceptar_total"     → RE9702, sin IA, plantilla corta
    #   "aceptar_parcial"   → RE9801, argumento IA sobre la diferencia + aceptacion parcial
    #   "auditoria_previa"  → R59: la IA NO redacta dictamen, da diagnóstico
    #                         neutral (hallazgos, riesgos, recomendación) para
    #                         que el gestor decida qué hacer.
    modo_respuesta: Optional[str] = Field(
        default="defender",
        max_length=30,
        description="defender | aceptar_total | aceptar_parcial | auditoria_previa",
    )
    # Para aceptar_parcial: valor que se acepta (el resto se defiende)
    valor_aceptado_parcial: Optional[float] = Field(
        default=0.0,
        ge=0,
        description="Valor COP aceptado por el prestador (solo aplica en aceptar_parcial)",
    )
    # Multi-modal soportes (Tier 1 #5): cuando True, los PDFs adjuntos
    # se envían binarios directos a Claude (soporte nativo Messages API)
    # en lugar de pre-procesarse con pdfplumber/OCR. Más caro en tokens
    # (~3-5x) pero mucho más preciso para PDFs con tablas complejas,
    # escaneos con OCR incrustado o fonts no estándar — equivalente al
    # patrón ya validado en /contratos/{eps}/pdf.
    usar_pdf_nativo_soportes: Optional[bool] = Field(
        default=False, description="Lectura PDF avanzada de soportes (más caro, más preciso)"
    )

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
        # Normaliza a forma canónica COP re-parseable. El patrón anterior
        # re.sub(r"[^\d]") convertía "7.700,00" en "770000" (100× — auditoría
        # jun-2026 P0 #1). parse_valor_cop entiende puntos=miles, coma=decimal.
        valor = parse_valor_cop(v)
        if valor == int(valor):
            return str(int(valor))
        # Decimales reales: conservarlos con coma (formato colombiano) para
        # que cualquier re-parse con parse_valor_cop devuelva el mismo valor.
        return f"{valor:.2f}".replace(".", ",")

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
                raise ValueError("fecha_recepcion no puede ser anterior a fecha_radicacion")
        return self


class ContratoInput(BaseModel):
    eps: str = Field(..., min_length=2, max_length=100)
    detalles: str = Field(..., min_length=10)

    @field_validator("eps")
    @classmethod
    def eps_uppercase(cls, v: str) -> str:
        return v.strip().upper()


class PDFRequest(BaseModel):
    eps: str
    resumen: str
    dictamen: str
    codigo: Optional[str] = "N/A"
    valor: Optional[str] = "N/A"


# ── Salida ────────────────────────────────────────────────────────────────────


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
    # CORRECCIÓN: era int, pero _calcular_score retorna float
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    dias_restantes: int = Field(default=0, ge=0)
    modelo_ia: Optional[str] = None
    # Indicador de riesgo de ratificación (0-100, más bajo = más probable levantamiento)
    riesgo_ratificacion: Optional[dict] = None
    # ID en BD (llenado por main.py después de persistir) — permite refinar/gold
    glosa_id: Optional[int] = None
    # R-cerebro #8: decisión autónoma de la IA sobre la glosa.
    # Valores posibles: DEFENDER_TOTAL | ACEPTAR_PARCIAL | ACEPTAR_TOTAL | REVISAR
    accion_ia: Optional[str] = None
    valor_aceptar_ia: Optional[float] = None
    valor_defender_ia: Optional[float] = None
    # Verificación de citas legales (citation_verifier) y score de
    # confianza (confidence_scorer) — calculados post-dictamen para que
    # la UI pueda mostrar warnings y badge de calidad. Opcionales para
    # no romper consumidores que no los esperan.
    verificacion_citas: Optional[dict] = None
    confianza: Optional[dict] = None
    # Decisión auto-pilot v2 (Yesid mayo 2026): si confianza >= 0.90 y
    # no es "caso difícil" (>= 5M COP + multi-conceptos), el sistema
    # propone AUTO_ENVIABLE. El gestor decide si activa el envío
    # automático global. Por defecto, cada caso requiere revisión.
    auto_pilot: Optional[dict] = None
    # Mejora #3 (jun-2026): salida estructurada incremental. Bloque de los
    # 6 campos críticos que el LLM confirmó (eps_efectiva, servicio_objetado,
    # contrato_citado, clausulas_respondidas, sancion_rechazada,
    # subconceptos_refutados) ya cruzados contra los valores deterministas,
    # más telemetría de divergencias. None cuando el flag está OFF o el LLM
    # no emitió el bloque (degradación elegante). Opcional para no romper
    # consumidores que no lo esperan.
    campos_estructurados: Optional[dict] = None


class GlosaHistorialItem(BaseModel):
    id: int
    eps: str
    paciente: str
    codigo_glosa: str
    valor_objetado: float
    valor_aceptado: float
    etapa: str
    estado: str
    dias_restantes: int
    creado_en: str

    model_config = {"from_attributes": True}


class AnalyticsResult(BaseModel):
    glosas_mes: int
    valor_objetado_mes: float
    valor_recuperado_mes: float
    tasa_exito_pct: float


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    nombre: str
    rol: Optional[str] = None
    # True si el usuario debe cambiar su password antes de operar
    must_change_password: Optional[bool] = False


class CambiarPasswordRequest(BaseModel):
    password_actual: str = Field(..., min_length=1, max_length=200)
    password_nueva: str = Field(
        ..., min_length=8, max_length=200, description="Mínimo 8 caracteres"
    )
    password_nueva_confirmacion: str = Field(..., min_length=8, max_length=200)


# ─────────────────────────────────────────────────────────────────────────
# Contratos de respuesta — Fase 2 del programa de mejora (13-08-2026)
#
# Por qué existen. De las 595 rutas del motor, solo 8 declaraban qué
# devuelven. Las demás sueltan un diccionario y nada garantiza que el campo
# que el JavaScript lee siga ahí mañana: cuando desaparece, la pantalla no da
# error, se queda callada. Es la misma familia de fallo que dejó la pantalla
# «Salud Total» tres meses devolviendo «Not Found».
#
# Estos esquemas describen lo que las rutas devuelven HOY, campo por campo,
# leído del código. No se inventó ninguno ni se cambió ningún nombre: si un
# campo se llama `creado_en` y viaja como texto ISO, así queda.
#
# Todos los campos que hoy pueden venir vacíos van Optional. Poner un tipo
# estricto donde la base admite nulos haría que la ruta reventara con un 500
# en vez de responder — el remedio sería peor que la enfermedad.
# ─────────────────────────────────────────────────────────────────────────


class TarifaContratadaOut(BaseModel):
    """Una tarifa pactada. Alimenta la tabla de Gestión → Tarifas."""

    id: int
    eps: str
    contrato_numero: Optional[str] = None
    codigo_cups: str
    codigo_ips: Optional[str] = None
    descripcion: Optional[str] = None
    valor_pactado: float
    modalidad: Optional[str] = None
    tipo_tarifa: str = "VALOR_FIJO"
    factor_ajuste: float = 0.0
    fuente_archivo: Optional[str] = None
    # Fechas en texto ISO: así las manda la ruta y así las lee la pantalla.
    vigencia_desde: Optional[str] = None
    vigencia_hasta: Optional[str] = None
    creado_en: Optional[str] = None
    creado_por: Optional[str] = None
    activa: bool = True

    model_config = ConfigDict(from_attributes=True)


class TarifasPorEps(BaseModel):
    eps: str
    cantidad: int


class TarifasStatsOut(BaseModel):
    """Resumen del catálogo de tarifas cargado."""

    total_activas: int
    por_eps: list[TarifasPorEps] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ConciliacionOut(BaseModel):
    """Un acta de conciliación. Alimenta la tabla de Conciliaciones."""

    id: int
    glosa_id: Optional[int] = None
    creado_por: Optional[str] = None
    creado_en: Optional[str] = None
    fecha_audiencia: Optional[str] = None
    lugar: Optional[str] = None
    participantes_hus: Optional[str] = None
    participantes_eps: Optional[str] = None
    resultado: Optional[str] = None
    valor_conciliado: Optional[float] = None
    observaciones: Optional[str] = None
    siguiente_paso: Optional[str] = None
    acta_numero: Optional[str] = None
    # Trámite bilateral (contra-respuesta de la EPS y postura del hospital).
    contra_respuesta_eps: Optional[str] = None
    fecha_contra_respuesta_eps: Optional[str] = None
    postura_hus: Optional[str] = None
    fecha_acta: Optional[str] = None
    valor_ratificado_hus: float = 0.0
    estado_bilateral: str = "PROGRAMADA"

    model_config = ConfigDict(from_attributes=True)


class ConciliacionesPagina(BaseModel):
    """Una página de conciliaciones. La pantalla lee estas cinco llaves."""

    items: list[ConciliacionOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 50
    pages: int = 0

    model_config = ConfigDict(from_attributes=True)


class SaludTotalGlosaOut(BaseModel):
    """Una fila de la vista previa de Salud Total.

    Los nombres NO son de estilo Python a propósito: son los de la
    notificación de la entidad, y la pantalla los lee así.
    """

    NumeroRad: str = ""
    PrefijoFac: str = ""
    NumeroFac: str = ""
    NUMREG: str = ""
    NombreServicio: str = ""
    ValorGlosaTotalxServ: float = 0.0
    CodMotvGlosaGeneral: str = ""
    CodMotvGlosaEspc: str = ""
    ValorAceptadoIPS: float = 0.0
    Codigo_Respuesta_a_glosas: str = ""
    ConceptoRespuesta: str = ""
    Observacion_IPS: str = ""
    TipoRespuesta: Optional[str] = None
    DiasTranscurridos: int = 0
    SinFechaRecepcion: bool = False


class SaludTotalPreviewOut(BaseModel):
    """Lo que pinta la pantalla «Salud Total» antes de descargar."""

    total_registros: int
    total_glosado: float
    total_aceptado: float
    total_rechazado: float
    # Avisa que no hay con qué contar el plazo del Art. 57 de la Ley
    # 1438/2011: sin fecha de recepción no se alega extemporaneidad.
    sin_fecha_recepcion: bool = False
    glosas: list[SaludTotalGlosaOut] = Field(default_factory=list)


class ValidacionAdresEstadoOut(BaseModel):
    """Cómo va una validación FURIPS. La pantalla pregunta cada 3 segundos."""

    estado: str
    mensaje: str = ""
    progreso: int = 0
    total: int = 0
    facturas: int = 0


class ValidacionAdresIniciadaOut(BaseModel):
    """Respuesta al subir los soportes: el identificador del trabajo."""

    trabajo_id: str
    archivos: int
    estado: str = "EN_COLA"


class ContratoOut(BaseModel):
    """Un contrato del banco contractual.

    Hoy la ruta declara `List[dict]`, que no dice nada: describir los campos
    es lo que permite que una prueba note si uno desaparece.
    """

    id: int
    eps: str
    numero_contrato: Optional[str] = None
    modalidad: Optional[str] = None
    vigencia_desde: Optional[str] = None
    vigencia_hasta: Optional[str] = None
    activo: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)
