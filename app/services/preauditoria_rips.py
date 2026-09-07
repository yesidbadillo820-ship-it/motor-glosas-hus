"""Del RIPS del HIS al lenguaje del motor (V3, Pilar 2 — 04-09-2026).

El HIS del hospital (SINAC) no manda una «factura» a nuestra medida: manda el
**RIPS** de la Resolución 2275 de 2023, que es la estructura oficial con la
que se le reporta al Ministerio cada atención. Este módulo la recibe tal
cual y la traduce a `PayloadFactura`, que es lo que las nueve reglas duras y
el cruce clínico ya saben leer.

Se traduce en vez de reescribir las reglas: funcionan, tienen 108 pruebas,
y el día que otra fuente mande otra cosa (una nota crédito, un lote de
Dinámica) solo hace falta otro traductor.

QUÉ TRAE EL RIPS Y QUÉ NO — verificado contra `Rips_HUS558039.json`, el
primer archivo real que entregó el HIS:

  · TRAE: número de factura, el usuario (documento, sexo, fecha de
    nacimiento) y sus servicios en arreglos por tipo. En el archivo real
    venía `consultas`; la norma también contempla `procedimientos`,
    `urgencias`, `hospitalizacion`, `recienNacidos`, `medicamentos` y
    `otrosServicios`, y acá se leen todos.
  · NO TRAE LA EPS. `numDocumentoIdObligado` es el NIT del propio hospital,
    no del pagador. Sin EPS no hay tarifa pactada ni contrato que cruzar:
    esas reglas se callan y la respuesta lo dice en `omisiones`.
  · NO TRAE TEXTO CLÍNICO. Ni epicrisis ni notas. El cruce clínico con IA
    se omite limpiamente (estado `OMITIDO_SIN_NOTAS`) y la factura se
    dictamina con las reglas duras. No se aborta nada.
  · NO TRAE EL TOTAL DE LA FACTURA: cada servicio trae su `vrServicio` y el
    total se suma. La regla que compara líneas contra el total declarado no
    tiene con qué comparar y no opina.

Los dos datos que el RIPS no trae pueden venir como ACOMPAÑANTES fuera de la
norma (`eps`, `notasClinicas`): si el HIS los agrega al lado del RIPS, el
motor los usa; si no, sigue sin ellos.

Los campos de las otras familias de servicios siguen el Anexo Técnico de la
Resolución 2275/2023. Se leen con tolerancia —un nombre que no aparezca se
ignora, nunca revienta— porque solo `consultas` se ha visto en un archivo
real del HIS.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.preauditoria_contrato import (
    Atencion,
    ItemFactura,
    Paciente,
    PayloadFactura,
    _a_fecha,
)

# `grupoServicios` del RIPS (Res. 2275/2023) → tipo de servicio del motor.
# Es lo que decide con qué causal oficial se proyecta la glosa.
TIPO_POR_GRUPO_SERVICIOS = {
    "01": "CONSULTA",  # consulta externa
    "02": "APOYO_DIAGNOSTICO",  # apoyo diagnóstico y complementación terapéutica
    "03": "ESTANCIA",  # internación
    "04": "QUIRURGICO",  # quirúrgico
    "05": "PROCEDIMIENTO_NO_QX",  # atención inmediata
}
# `tipoOS` de otrosServicios → tipo del motor.
TIPO_POR_TIPO_OS = {
    "01": "DISPOSITIVO",  # materiales e insumos
    "02": "TRASLADO",  # traslados
    "03": "ESTANCIA",  # estancias
    "04": "HONORARIOS",  # honorarios
}
# `viaIngresoServicioSalud` de hospitalización → tipo de atención.
_RE_UCI = re.compile(r"\bUCI\b|CUIDADO[S]?\s+INTENSIVO", re.IGNORECASE)


class _Base(BaseModel):
    """Todo lo del RIPS se lee con `extra="ignore"`: la norma trae decenas
    de campos que la pre-auditoría no necesita, y un campo nuevo del HIS
    no puede tumbar la evaluación."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class RipsConsulta(_Base):
    codConsulta: str = ""
    fechaInicioAtencion: Optional[datetime] = None
    grupoServicios: str = "01"
    codDiagnosticoPrincipal: str = ""
    codDiagnosticoRelacionado1: str = ""
    codDiagnosticoRelacionado2: str = ""
    codDiagnosticoRelacionado3: str = ""
    vrServicio: float = 0.0
    numAutorizacion: str = ""

    @field_validator("fechaInicioAtencion", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator(
        "codConsulta",
        "grupoServicios",
        "codDiagnosticoPrincipal",
        "codDiagnosticoRelacionado1",
        "codDiagnosticoRelacionado2",
        "codDiagnosticoRelacionado3",
        "numAutorizacion",
        mode="before",
    )
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()


class RipsProcedimiento(_Base):
    codProcedimiento: str = ""
    fechaInicioAtencion: Optional[datetime] = None
    grupoServicios: str = "04"
    viaIngresoServicioSalud: str = ""
    codDiagnosticoPrincipal: str = ""
    codDiagnosticoRelacionado: str = ""
    codComplicacion: str = ""
    vrServicio: float = 0.0
    numAutorizacion: str = ""

    @field_validator("fechaInicioAtencion", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator(
        "codProcedimiento",
        "grupoServicios",
        "viaIngresoServicioSalud",
        "codDiagnosticoPrincipal",
        "codDiagnosticoRelacionado",
        "codComplicacion",
        "numAutorizacion",
        mode="before",
    )
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()


class RipsEpisodio(_Base):
    """Urgencias y hospitalización: NO son cobros, son el episodio. De acá
    salen las fechas de ingreso y egreso y los diagnósticos."""

    fechaInicioAtencion: Optional[datetime] = None
    fechaEgreso: Optional[datetime] = None
    viaIngresoServicioSalud: str = ""
    codDiagnosticoPrincipal: str = ""
    codDiagnosticoPrincipalE: str = ""
    codDiagnosticoRelacionadoE1: str = ""
    codDiagnosticoRelacionadoE2: str = ""
    codDiagnosticoRelacionadoE3: str = ""
    codComplicacion: str = ""
    condicionDestinoUsuarioEgreso: str = ""

    @field_validator("fechaInicioAtencion", "fechaEgreso", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator(
        "viaIngresoServicioSalud",
        "codDiagnosticoPrincipal",
        "codDiagnosticoPrincipalE",
        "codDiagnosticoRelacionadoE1",
        "codDiagnosticoRelacionadoE2",
        "codDiagnosticoRelacionadoE3",
        "codComplicacion",
        "condicionDestinoUsuarioEgreso",
        mode="before",
    )
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()


class RipsMedicamento(_Base):
    codTecnologiaSalud: str = ""
    nomTecnologiaSalud: str = ""
    fechaDispensAdmon: Optional[datetime] = None
    cantidadMedicamento: float = 1.0
    vrUnitMedicamento: float = 0.0
    vrServicio: float = 0.0
    codDiagnosticoPrincipal: str = ""

    @field_validator("fechaDispensAdmon", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator(
        "codTecnologiaSalud", "nomTecnologiaSalud", "codDiagnosticoPrincipal", mode="before"
    )
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()


class RipsOtroServicio(_Base):
    tipoOS: str = ""
    codTecnologiaSalud: str = ""
    nomTecnologiaSalud: str = ""
    fechaSuministroTecnologia: Optional[datetime] = None
    cantidadOS: float = 1.0
    vrUnitOS: float = 0.0
    vrServicio: float = 0.0

    @field_validator("fechaSuministroTecnologia", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator("tipoOS", "codTecnologiaSalud", "nomTecnologiaSalud", mode="before")
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()


class RipsRecienNacido(_Base):
    fechaNacimiento: Optional[datetime] = None
    codSexoBiologico: str = ""
    codDiagnosticoPrincipal: str = ""
    fechaEgreso: Optional[datetime] = None

    @field_validator("fechaNacimiento", "fechaEgreso", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator("codSexoBiologico", "codDiagnosticoPrincipal", mode="before")
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()


class RipsServicios(_Base):
    consultas: list[RipsConsulta] = Field(default_factory=list)
    procedimientos: list[RipsProcedimiento] = Field(default_factory=list)
    urgencias: list[RipsEpisodio] = Field(default_factory=list)
    hospitalizacion: list[RipsEpisodio] = Field(default_factory=list)
    recienNacidos: list[RipsRecienNacido] = Field(default_factory=list)
    medicamentos: list[RipsMedicamento] = Field(default_factory=list)
    otrosServicios: list[RipsOtroServicio] = Field(default_factory=list)

    @field_validator(
        "consultas",
        "procedimientos",
        "urgencias",
        "hospitalizacion",
        "recienNacidos",
        "medicamentos",
        "otrosServicios",
        mode="before",
    )
    @classmethod
    def _nulo_es_vacio(cls, v):
        # El HIS manda `null` en los arreglos que no aplican.
        return [] if v is None else v


class RipsUsuario(_Base):
    tipoDocumentoIdentificacion: str = ""
    numDocumentoIdentificacion: str = ""
    fechaNacimiento: Optional[datetime] = None
    codSexo: str = ""
    consecutivo: int = 1
    servicios: RipsServicios = Field(default_factory=RipsServicios)

    @field_validator("fechaNacimiento", mode="before")
    @classmethod
    def _f(cls, v):
        return _a_fecha(v)

    @field_validator(
        "tipoDocumentoIdentificacion", "numDocumentoIdentificacion", "codSexo", mode="before"
    )
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()

    @field_validator("servicios", mode="before")
    @classmethod
    def _servicios_nulos(cls, v):
        return {} if v is None else v


class RipsFactura(_Base):
    """La cabecera del RIPS tal como la manda el HIS, más los acompañantes."""

    numDocumentoIdObligado: str = ""
    numFactura: str = Field(..., min_length=1, max_length=50)
    tipoNota: Optional[str] = None
    numNota: Optional[str] = None
    usuarios: list[RipsUsuario] = Field(..., min_length=1)

    # ── Acompañantes fuera de la norma RIPS. Opcionales. ──
    eps: str = Field(default="", max_length=200)
    notasClinicas: str = Field(default="", max_length=40000, alias="notasClinicas")

    @field_validator("numDocumentoIdObligado", "numFactura", "eps", mode="before")
    @classmethod
    def _texto(cls, v):
        return "" if v is None else str(v).strip()

    @field_validator("notasClinicas", mode="before")
    @classmethod
    def _notas(cls, v):
        return "" if v is None else str(v)


def es_rips(cuerpo: Any) -> bool:
    """¿Esto que llegó es un RIPS? Se reconoce por el arreglo `usuarios`."""
    return isinstance(cuerpo, dict) and "usuarios" in cuerpo


# ═══════════════════════════════════════════════════════════════════════
#  LA TRADUCCIÓN
# ═══════════════════════════════════════════════════════════════════════


def _descripcion_de(cups: str, nombre: str = "") -> str:
    """El nombre del servicio: el que mandó el HIS o, si no, el del catálogo
    del hospital. Las reglas de sexo, edad y vías leen la descripción."""
    if nombre:
        return nombre
    if not cups:
        return ""
    try:
        from app.services.homologador_cups import DESCRIPCIONES_CUPS_2025

        return DESCRIPCIONES_CUPS_2025.get(cups, "")
    except Exception:
        return ""


def _diagnosticos_de(objeto: Any) -> list[str]:
    """Todos los códigos CIE-10 que traiga un servicio, sin repetir."""
    codigos: list[str] = []
    for nombre in (
        "codDiagnosticoPrincipal",
        "codDiagnosticoPrincipalE",
        "codDiagnosticoRelacionado",
        "codDiagnosticoRelacionado1",
        "codDiagnosticoRelacionado2",
        "codDiagnosticoRelacionado3",
        "codDiagnosticoRelacionadoE1",
        "codDiagnosticoRelacionadoE2",
        "codDiagnosticoRelacionadoE3",
        "codComplicacion",
    ):
        valor = getattr(objeto, nombre, "") or ""
        if valor and valor not in codigos:
            codigos.append(valor)
    return codigos


def _items_de(servicios: RipsServicios) -> list[ItemFactura]:
    items: list[ItemFactura] = []

    for c in servicios.consultas:
        items.append(
            ItemFactura(
                cups=c.codConsulta,
                descripcion=_descripcion_de(c.codConsulta),
                tipo=TIPO_POR_GRUPO_SERVICIOS.get(c.grupoServicios, "CONSULTA"),
                cantidad=1,
                valor_unitario=float(c.vrServicio or 0.0),
                valor_total=float(c.vrServicio or 0.0),
                fecha=c.fechaInicioAtencion,
            )
        )

    for p in servicios.procedimientos:
        items.append(
            ItemFactura(
                cups=p.codProcedimiento,
                descripcion=_descripcion_de(p.codProcedimiento),
                tipo=TIPO_POR_GRUPO_SERVICIOS.get(p.grupoServicios, "QUIRURGICO"),
                cantidad=1,
                valor_unitario=float(p.vrServicio or 0.0),
                valor_total=float(p.vrServicio or 0.0),
                fecha=p.fechaInicioAtencion,
            )
        )

    for m in servicios.medicamentos:
        cantidad = float(m.cantidadMedicamento or 1.0)
        unitario = float(m.vrUnitMedicamento or 0.0)
        total = float(m.vrServicio or 0.0) or round(cantidad * unitario, 2)
        items.append(
            ItemFactura(
                cups=m.codTecnologiaSalud,
                descripcion=_descripcion_de(m.codTecnologiaSalud, m.nomTecnologiaSalud),
                tipo="MEDICAMENTO",
                cantidad=cantidad,
                valor_unitario=unitario,
                valor_total=total,
                fecha=m.fechaDispensAdmon,
            )
        )

    for o in servicios.otrosServicios:
        cantidad = float(o.cantidadOS or 1.0)
        unitario = float(o.vrUnitOS or 0.0)
        total = float(o.vrServicio or 0.0) or round(cantidad * unitario, 2)
        items.append(
            ItemFactura(
                cups=o.codTecnologiaSalud,
                descripcion=_descripcion_de(o.codTecnologiaSalud, o.nomTecnologiaSalud),
                tipo=TIPO_POR_TIPO_OS.get(o.tipoOS, "DISPOSITIVO"),
                cantidad=cantidad,
                valor_unitario=unitario,
                valor_total=total,
                fecha=o.fechaSuministroTecnologia,
            )
        )
    return items


def _atencion_de(servicios: RipsServicios) -> Atencion:
    """El episodio: de dónde salen ingreso, egreso, estancia y diagnósticos."""
    episodio: Optional[RipsEpisodio] = None
    tipo = "AMBULATORIO"
    if servicios.hospitalizacion:
        episodio, tipo = servicios.hospitalizacion[0], "HOSPITALIZACION"
    elif servicios.urgencias:
        episodio, tipo = servicios.urgencias[0], "URGENCIAS"

    diagnosticos: list[str] = []
    principal = ""
    fuentes: list[Any] = (
        list(servicios.hospitalizacion)
        + list(servicios.urgencias)
        + list(servicios.consultas)
        + list(servicios.procedimientos)
        + list(servicios.medicamentos)
    )
    for s in fuentes:
        if not principal:
            principal = getattr(s, "codDiagnosticoPrincipal", "") or ""
        for d in _diagnosticos_de(s):
            if d not in diagnosticos:
                diagnosticos.append(d)

    # Días de estancia y de UCI: salen de otrosServicios con tipoOS=03.
    dias_estancia = 0.0
    dias_uci = 0.0
    for o in servicios.otrosServicios:
        if o.tipoOS != "03":
            continue
        dias_estancia += float(o.cantidadOS or 0.0)
        if _RE_UCI.search(o.nomTecnologiaSalud or "") or _RE_UCI.search(
            _descripcion_de(o.codTecnologiaSalud)
        ):
            dias_uci += float(o.cantidadOS or 0.0)

    fecha_ingreso = episodio.fechaInicioAtencion if episodio else None
    fecha_egreso = episodio.fechaEgreso if episodio else None
    if fecha_ingreso is None:
        # Ambulatorio: el episodio es el día de la primera atención.
        fechas = [
            s.fechaInicioAtencion
            for s in list(servicios.consultas) + list(servicios.procedimientos)
            if s.fechaInicioAtencion
        ]
        if fechas:
            fecha_ingreso = min(fechas)
            fecha_egreso = fecha_egreso or max(fechas)

    return Atencion(
        tipo=tipo,
        fecha_ingreso=fecha_ingreso,
        fecha_egreso=fecha_egreso,
        dias_estancia=int(dias_estancia) if dias_estancia else None,
        dias_uci=int(dias_uci) if dias_uci else None,
        diagnostico_principal=principal[:20],
        diagnosticos=diagnosticos[:30],
    )


def traducir(rips: RipsFactura) -> tuple[PayloadFactura, list[str]]:
    """RIPS → PayloadFactura, más la lista de lo que NO se pudo cubrir.

    Devuelve las omisiones aparte para que la respuesta las muestre sin
    convertirlas en alertas: no son reparos a la factura, son límites de lo
    que se tuvo a la vista.
    """
    omisiones: list[str] = []

    if not rips.eps:
        omisiones.append(
            "El RIPS no trae la EPS (numDocumentoIdObligado es el NIT del hospital): "
            "no se cruzó la tarifa pactada ni el contrato vigente. Si el HIS agrega "
            "el campo `eps` junto al RIPS, el motor los cruza."
        )

    # El paciente: solo cuando hay UNO. Con varios usuarios en la misma
    # factura, los cruces de sexo y edad no saben de quién es cada línea y
    # es preferible callar a acusar a la persona equivocada.
    if len(rips.usuarios) == 1:
        u = rips.usuarios[0]
        paciente = Paciente(
            documento=(u.numDocumentoIdentificacion or "")[:30],
            sexo=u.codSexo,
            fecha_nacimiento=u.fechaNacimiento,
        )
    else:
        paciente = Paciente()
        omisiones.append(
            f"Factura con {len(rips.usuarios)} usuarios: los cruces de sexo y edad "
            "no aplican porque el RIPS no dice de qué usuario es cada servicio "
            "cuando se leen juntos."
        )

    # Los ítems y el episodio se toman de TODOS los usuarios: la aritmética,
    # las tarifas, los duplicados y las fechas son de la factura entera.
    items: list[ItemFactura] = []
    servicios_fusionados = RipsServicios()
    for u in rips.usuarios:
        items.extend(_items_de(u.servicios))
        servicios_fusionados.consultas += u.servicios.consultas
        servicios_fusionados.procedimientos += u.servicios.procedimientos
        servicios_fusionados.urgencias += u.servicios.urgencias
        servicios_fusionados.hospitalizacion += u.servicios.hospitalizacion
        servicios_fusionados.medicamentos += u.servicios.medicamentos
        servicios_fusionados.otrosServicios += u.servicios.otrosServicios
        servicios_fusionados.recienNacidos += u.servicios.recienNacidos

    atencion = _atencion_de(servicios_fusionados)

    if not rips.notasClinicas.strip():
        omisiones.append(
            "El RIPS no trae notas clínicas ni epicrisis: el cruce clínico con IA no "
            "corrió. La factura se dictaminó con las reglas duras y el cruce de "
            "tarifas y CUPS. Si el HIS adjunta `notasClinicas`, el motor las cruza."
        )

    payload = PayloadFactura(
        factura=rips.numFactura,
        eps=rips.eps,
        paciente=paciente,
        atencion=atencion,
        items=items,
        valor_total=0.0,  # el RIPS no trae total: se suma de las líneas
        epicrisis=rips.notasClinicas,
    )
    return payload, omisiones
