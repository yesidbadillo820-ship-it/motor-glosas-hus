"""El contrato de la Pre-Auditoría Concurrente (V3, Pilar 2).

Acá viven las dos formas del trato con el HIS del hospital: lo que MANDA
antes de timbrar una factura y lo que RECIBE de vuelta. Están en un módulo
aparte a propósito: el router, las reglas duras, el cruce clínico y las
pruebas hablan todos el mismo idioma sin importarse entre sí.

Regla de oro del contrato: **rígido en la salida, tolerante en la entrada**.
El HIS es un sistema viejo que manda lo que puede; si falta un campo que no
es indispensable, la evaluación sigue con lo que haya y lo dice. Lo que
nunca cambia es la forma de la respuesta —`status`, `alertas`,
`valor_en_riesgo`, `recomendacion_accion`— porque del otro lado hay un
programa, no una persona.

Arquitectura: docs/ARQUITECTURA_V3_PILAR2_PREAUDITORIA.md
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.db import (
    PA_ACCION_CORREGIR,
    PA_ACCION_REVISAR,
    PA_ACCION_TIMBRAR,
    PA_ADVERTENCIA,
    PA_APROBADO,
    PA_BLOQUEO,
)

Severidad = Literal["ADVERTENCIA", "BLOQUEO"]
Origen = Literal["REGLA_DURA", "IA"]


# ═══════════════════════════════════════════════════════════════════════
#  LO QUE ENTRA — la factura que el HIS está a punto de timbrar
# ═══════════════════════════════════════════════════════════════════════


def _a_fecha(valor: Any) -> Optional[datetime]:
    """Acepta lo que un HIS suele mandar y devuelve fecha-hora o None.

    Nunca levanta: una fecha ilegible no puede tumbar la evaluación entera
    de una factura. La regla de coherencia temporal se encarga de avisar
    cuando falta lo que sí importa.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    texto = str(valor).strip().replace("/", "-")
    for formato in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(texto[: len(formato) + 4], formato)
        except ValueError:
            continue
    try:  # último intento: ISO con zona horaria
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


class Paciente(BaseModel):
    """Lo mínimo del paciente para cruzar género y edad.

    NO se pide ni se guarda el nombre: para pre-auditar una factura basta
    con el sexo, la edad y el documento (que sirve de ancla si hay que
    volver sobre el caso). Menos dato personal circulando, menos riesgo.
    """

    model_config = ConfigDict(extra="ignore")

    documento: str = Field(default="", max_length=30)
    sexo: str = Field(default="", max_length=20)
    edad_anios: Optional[float] = None
    edad_dias: Optional[int] = None
    fecha_nacimiento: Optional[datetime] = None

    @field_validator("fecha_nacimiento", mode="before")
    @classmethod
    def _fn(cls, v):
        return _a_fecha(v)

    @field_validator("sexo", mode="before")
    @classmethod
    def _sexo(cls, v):
        return str(v or "").strip().upper()

    def sexo_normalizado(self) -> str:
        """«M» / «F» / «» — un HIS manda M, MASCULINO, HOMBRE o 1."""
        s = (self.sexo or "").strip().upper()
        if s in ("M", "MASCULINO", "HOMBRE", "MALE", "1"):
            return "M"
        if s in ("F", "FEMENINO", "MUJER", "FEMALE", "2"):
            return "F"
        return ""

    def edad_en_dias(self, referencia: Optional[datetime] = None) -> Optional[int]:
        """Edad en días. Prefiere lo declarado; si no, la calcula."""
        if self.edad_dias is not None and self.edad_dias >= 0:
            return int(self.edad_dias)
        if self.edad_anios is not None and self.edad_anios >= 0:
            return int(round(float(self.edad_anios) * 365.25))
        if self.fecha_nacimiento:
            ref = referencia or datetime.now()
            dias = (ref - self.fecha_nacimiento).days
            return dias if dias >= 0 else None
        return None

    def edad_en_anios(self, referencia: Optional[datetime] = None) -> Optional[float]:
        dias = self.edad_en_dias(referencia)
        return round(dias / 365.25, 2) if dias is not None else None


class Atencion(BaseModel):
    """El episodio asistencial que se está facturando."""

    model_config = ConfigDict(extra="ignore")

    tipo: str = Field(default="", max_length=40)  # URGENCIAS / HOSPITALIZACION / AMBULATORIO
    fecha_ingreso: Optional[datetime] = None
    fecha_egreso: Optional[datetime] = None
    dias_estancia: Optional[int] = None
    dias_uci: Optional[int] = None
    diagnostico_principal: str = Field(default="", max_length=20)
    diagnosticos: list[str] = Field(default_factory=list)

    @field_validator("fecha_ingreso", "fecha_egreso", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    def dias_calendario(self) -> Optional[int]:
        """Días entre ingreso y egreso. None si falta alguna fecha."""
        if not (self.fecha_ingreso and self.fecha_egreso):
            return None
        return (self.fecha_egreso.date() - self.fecha_ingreso.date()).days


class ItemFactura(BaseModel):
    """Una línea de la factura: qué se cobra, cuánto y de qué tipo."""

    model_config = ConfigDict(extra="ignore")

    cups: str = Field(default="", max_length=30)
    descripcion: str = Field(default="", max_length=500)
    # ESTANCIA / CONSULTA / QUIRURGICO / HONORARIOS / ANESTESIA / SALA /
    # DISPOSITIVO / MEDICAMENTO / APOYO_DIAGNOSTICO / APOYO_TERAPEUTICO /
    # PROCEDIMIENTO_NO_QX / TRASLADO — se usa para proyectar la causal.
    tipo: str = Field(default="", max_length=40)
    cantidad: float = 1.0
    valor_unitario: float = 0.0
    valor_total: float = 0.0
    fecha: Optional[datetime] = None
    via: str = Field(default="", max_length=40)  # ABIERTA / LAPAROSCOPICA / ...

    @field_validator("fecha", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator("cups", "tipo", "via", mode="before")
    @classmethod
    def _mayus(cls, v):
        return str(v or "").strip().upper()

    def total_calculado(self) -> float:
        return round(float(self.cantidad or 0.0) * float(self.valor_unitario or 0.0), 2)

    def total_efectivo(self) -> float:
        """El valor de la línea. Si el HIS no mandó total, se calcula."""
        if self.valor_total:
            return float(self.valor_total)
        return self.total_calculado()

    def etiqueta(self) -> str:
        """Cómo se nombra este ítem en una alerta."""
        return self.cups or (self.descripcion[:60] if self.descripcion else "ÍTEM SIN CÓDIGO")


class PayloadFactura(BaseModel):
    """Lo que el HIS manda antes de timbrar."""

    model_config = ConfigDict(extra="ignore")

    factura: str = Field(default="", max_length=50)
    eps: str = Field(..., min_length=1, max_length=200)
    regimen: str = Field(default="", max_length=40)
    paciente: Paciente = Field(default_factory=Paciente)
    atencion: Atencion = Field(default_factory=Atencion)
    items: list[ItemFactura] = Field(default_factory=list, max_length=2000)
    valor_total: float = 0.0
    epicrisis: str = Field(default="", max_length=40000)

    @field_validator("eps", mode="before")
    @classmethod
    def _eps(cls, v):
        return str(v or "").strip().upper()

    def total_items(self) -> float:
        return round(sum(i.total_efectivo() for i in self.items), 2)

    def total_efectivo(self) -> float:
        """El valor de la factura. Si el HIS no lo mandó, se suma."""
        return float(self.valor_total) if self.valor_total else self.total_items()


# ═══════════════════════════════════════════════════════════════════════
#  LO QUE SALE — el dictamen
# ═══════════════════════════════════════════════════════════════════════


class Alerta(BaseModel):
    """Una glosa proyectada: lo que la EPS objetaría si esto se timbra así."""

    model_config = ConfigDict(extra="forbid")

    codigo_glosa: str = Field(default="", max_length=10)
    titulo: str = Field(default="", max_length=200)
    detalle: str = Field(default="", max_length=1500)
    severidad: Severidad = "ADVERTENCIA"
    origen: Origen = "REGLA_DURA"
    regla: str = Field(default="", max_length=60)
    # El ítem al que se le atribuye el riesgo — para no contarlo dos veces.
    item: str = Field(default="", max_length=60)
    valor_en_riesgo: float = 0.0


class CruceClinico(BaseModel):
    """Cómo le fue al tramo de IA. Se responde siempre, haya corrido o no."""

    model_config = ConfigDict(extra="forbid")

    # OK / OMITIDO_SIN_IA / OMITIDO_POR_TIEMPO / TIMEOUT / ERROR
    estado: str = "OMITIDO_SIN_IA"
    modelo_utilizado: str = ""
    duracion_ms: int = 0
    detalle: str = ""


class RespuestaPreAuditoria(BaseModel):
    """El JSON rígido que recibe el HIS. Los cuatro primeros campos son el
    contrato; el resto es trazabilidad que el hospital sí necesita."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["APROBADO", "ADVERTENCIA", "BLOQUEO"] = PA_APROBADO
    alertas: list[Alerta] = Field(default_factory=list)
    valor_en_riesgo: float = 0.0
    recomendacion_accion: Literal[
        "TIMBRAR", "REVISAR_ANTES_DE_TIMBRAR", "CORREGIR_ANTES_DE_TIMBRAR"
    ] = PA_ACCION_TIMBRAR

    # ── Trazabilidad ──
    evento_id: Optional[int] = None
    factura: str = ""
    eps: str = ""
    valor_factura: float = 0.0
    duracion_ms: int = 0
    cruce_clinico: CruceClinico = Field(default_factory=CruceClinico)


def estado_de(alertas: list[Alerta]) -> str:
    """El dictamen sale de las alertas, no al revés."""
    if any(a.severidad == "BLOQUEO" for a in alertas):
        return PA_BLOQUEO
    if alertas:
        return PA_ADVERTENCIA
    return PA_APROBADO


def accion_de(estado: str) -> str:
    """Qué hace el facturador con ese dictamen."""
    if estado == PA_BLOQUEO:
        return PA_ACCION_CORREGIR
    if estado == PA_ADVERTENCIA:
        return PA_ACCION_REVISAR
    return PA_ACCION_TIMBRAR


def consolidar_valor_en_riesgo(alertas: list[Alerta], valor_factura: float) -> float:
    """Suma el riesgo SIN contarlo dos veces.

    Un mismo ítem puede disparar tres reglas —tarifa por encima, cobrado dos
    veces y sin respaldo clínico—. Sumar las tres da una cifra inflada que
    nadie se cree y que desprestigia la herramienta. El riesgo de un ítem es
    **el mayor** de sus alertas, y el total jamás supera la factura.
    """
    por_item: dict[str, float] = {}
    sueltas = 0.0
    for a in alertas:
        valor = max(0.0, float(a.valor_en_riesgo or 0.0))
        if not valor:
            continue
        if a.item:
            por_item[a.item] = max(por_item.get(a.item, 0.0), valor)
        else:
            sueltas += valor
    total = round(sum(por_item.values()) + sueltas, 2)
    if valor_factura > 0:
        total = min(total, round(float(valor_factura), 2))
    return round(total, 2)
