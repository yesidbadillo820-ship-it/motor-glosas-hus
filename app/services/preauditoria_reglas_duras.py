"""Las reglas duras de la Pre-Auditoría Concurrente (V3, Pilar 2).

Son las que corren **antes** de la IA y sin pedirle permiso a nadie: cuentas,
fechas, sexo, edad y tarifas. Todas son deterministas —mismo payload, mismo
dictamen— y ninguna toca la red salvo la de tarifas, que consulta la base de
datos del propio hospital.

Doctrina del proyecto, aplicada aquí sin excepción:

  · **Python decide, la IA opina.** Lo que se puede probar con una resta no
    se le pregunta a un modelo de lenguaje.
  · **No inventar.** Si no hay tarifa cargada para ese CUPS, la regla de
    topes NO estima: se calla. Un valor inventado en pre-auditoría manda al
    facturador a corregir una factura que estaba bien.
  · **Los códigos son los oficiales.** Cada alerta proyecta la causal del
    Manual Único (Anexo Técnico 3) con la que la EPS glosaría de verdad;
    salen de `catalogo_glosas.py`, no de nuestra imaginación.

Cada regla es una función `(payload, ctx) -> list[Alerta]`. Puras salvo el
acceso de lectura a la base: se prueban con `pytest` sin montar el motor.

Arquitectura: docs/ARQUITECTURA_V3_PILAR2_PREAUDITORIA.md
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.services.preauditoria_contrato import Alerta, ItemFactura, PayloadFactura
from app.services.reglas_casos_fno import sexo_exigido_por_el_procedimiento

# Tolerancia de redondeo en pesos. Un peso de diferencia es redondeo del HIS,
# no un error de facturación.
TOLERANCIA_PESOS = 1.0
# Tolerancia relativa contra la tarifa pactada: la misma que ya usa el motor
# de glosas para decidir si un valor "coincide" con lo pactado (0,5 %).
TOLERANCIA_TARIFA = 0.005


# ═══════════════════════════════════════════════════════════════════════
#  DE QUÉ TIPO ES CADA LÍNEA Y CON QUÉ CAUSAL SE GLOSARÍA
# ═══════════════════════════════════════════════════════════════════════
# El Manual Único organiza las causales por TIPO DE SERVICIO: la misma falta
# tiene código distinto si es una estancia o un medicamento. Esta tabla es la
# traducción, y es la única fuente de códigos de este módulo.
#
#   TA = diferencia con el valor pactado
#   FA = diferencia en cantidad / error de facturación
#   CL = no pertinente (calidad)
#   CO = no cubierto
CAUSAL_POR_TIPO: dict[str, dict[str, str]] = {
    "ESTANCIA": {"TA": "TA0101", "FA": "FA0101", "CL": "CL0101", "CO": "CO0101"},
    "CONSULTA": {"TA": "TA0201", "FA": "FA0201", "CL": "CL0201", "CO": "CO0201"},
    "HONORARIOS": {"TA": "TA0301", "FA": "FA0301", "CL": "CL0301", "CO": "CO0301"},
    "ANESTESIA": {"TA": "TA0302", "FA": "FA0302", "CL": "CL0302", "CO": "CO0401"},
    "SALA": {"TA": "TA0501", "FA": "FA0501", "CL": "CL0301", "CO": "CO0301"},
    "DISPOSITIVO": {"TA": "TA0601", "FA": "FA0601", "CL": "CL0601", "CO": "CO0601"},
    "MEDICAMENTO": {"TA": "TA0701", "FA": "FA0701", "CL": "CL0701", "CO": "CO0701"},
    "APOYO_DIAGNOSTICO": {"TA": "TA0801", "FA": "FA0801", "CL": "CL0801", "CO": "CO0801"},
    "APOYO_TERAPEUTICO": {"TA": "TA5701", "FA": "FA5701", "CL": "CL5701", "CO": "CO5701"},
    "PROCEDIMIENTO_NO_QX": {"TA": "TA2301", "FA": "FA2301", "CL": "CL2301", "CO": "CO2301"},
    "QUIRURGICO": {"TA": "TA5801", "FA": "FA5801", "CL": "CL5801", "CO": "CO5801"},
    "TRASLADO": {"TA": "TA3801", "FA": "FA3801", "CL": "CL3801", "CO": "CO3801"},
}
# Cuando el HIS no manda el tipo y la descripción no delata nada, se usa el
# grupo quirúrgico: es el de mayor valor y el que más se glosa.
TIPO_POR_DEFECTO = "QUIRURGICO"

# Pistas para deducir el tipo cuando el HIS no lo manda. Se leen en orden.
_PISTAS_TIPO: tuple[tuple[str, str], ...] = (
    (r"\bUCI\b|CUIDADO\s+INTENSIVO|ESTANCIA|HABITACI[ÓO]N|OBSERVACI[ÓO]N", "ESTANCIA"),
    (r"CONSULTA|INTERCONSULTA|VALORACI[ÓO]N", "CONSULTA"),
    (r"ANESTESIA|ANEST[ÉE]SIC", "ANESTESIA"),
    (r"DERECHOS?\s+DE\s+SALA|SALA\s+DE\s+CIRUG[ÍI]A", "SALA"),
    (r"HONORARIOS", "HONORARIOS"),
    (r"TRASLADO|AMBULANCIA", "TRASLADO"),
    (r"TERAPIA|REHABILITACI[ÓO]N|FISIOTERAPIA", "APOYO_TERAPEUTICO"),
    (
        r"LABORATORIO|HEMOGRAMA|RADIOGRAF[ÍI]A|TOMOGRAF[ÍI]A|ECOGRAF[ÍI]A|BIOPSIA|CITOLOG",
        "APOYO_DIAGNOSTICO",
    ),
    (
        r"OX[ÍI]GENO|TRANSFUSI[ÓO]N|SUTURA|CURACI[ÓO]N|NEBULIZACI[ÓO]N|VACUNACI[ÓO]N",
        "PROCEDIMIENTO_NO_QX",
    ),
)


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()


def tipo_de(item: ItemFactura) -> str:
    """El tipo de servicio de una línea. Lo declarado manda; si no, se deduce."""
    declarado = (item.tipo or "").strip().upper()
    if declarado in CAUSAL_POR_TIPO:
        return declarado
    texto = f"{item.descripcion} {item.cups}"
    for patron, tipo in _PISTAS_TIPO:
        if re.search(patron, texto, re.IGNORECASE):
            return tipo
    return TIPO_POR_DEFECTO


def causal(item: ItemFactura, familia: str) -> str:
    """El código oficial con el que se glosaría esta línea por esa familia."""
    return CAUSAL_POR_TIPO.get(tipo_de(item), CAUSAL_POR_TIPO[TIPO_POR_DEFECTO])[familia]


def _texto_del_item(item: ItemFactura) -> str:
    """Descripción para leer reglas. Si el HIS no la manda, se busca el CUPS
    en el homologador del hospital antes de darse por vencido."""
    if item.descripcion:
        return item.descripcion
    if not item.cups:
        return ""
    try:
        from app.services.homologador_cups import DESCRIPCIONES_CUPS_2025

        return DESCRIPCIONES_CUPS_2025.get(item.cups, "")
    except Exception:
        return ""


def _pesos(valor: float) -> str:
    return "$" + f"{int(round(valor)):,}".replace(",", ".")


@dataclass
class Contexto:
    """Lo que las reglas necesitan del mundo exterior. Nada más."""

    db: Optional[Session] = None
    ahora: Optional[datetime] = None


Regla = Callable[[PayloadFactura, Contexto], list[Alerta]]


# ═══════════════════════════════════════════════════════════════════════
#  1. ARITMÉTICA — lo que no cuadra no se discute, se corrige
# ═══════════════════════════════════════════════════════════════════════
def regla_aritmetica(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Cantidad × valor unitario, y la suma de las líneas contra el total.

    Es la regla más aburrida y la que más plata salva: una factura que no
    suma se devuelve entera y el hospital pierde el turno de radicación.
    """
    alertas: list[Alerta] = []
    for item in payload.items:
        if not item.valor_total or not item.valor_unitario:
            continue  # sin los dos datos no hay nada que cuadrar
        diferencia = abs(item.total_efectivo() - item.total_calculado())
        if diferencia > TOLERANCIA_PESOS:
            alertas.append(
                Alerta(
                    codigo_glosa=causal(item, "FA"),
                    titulo="La línea no cuadra: cantidad × valor unitario ≠ total",
                    detalle=(
                        f"{item.etiqueta()}: {item.cantidad:g} × "
                        f"{_pesos(item.valor_unitario)} da "
                        f"{_pesos(item.total_calculado())}, pero la factura dice "
                        f"{_pesos(item.total_efectivo())}. Diferencia de "
                        f"{_pesos(diferencia)}."
                    ),
                    severidad="BLOQUEO",
                    regla="aritmetica_linea",
                    item=item.etiqueta(),
                    valor_en_riesgo=round(diferencia, 2),
                )
            )

    if payload.valor_total and payload.items:
        diferencia = abs(float(payload.valor_total) - payload.total_items())
        if diferencia > TOLERANCIA_PESOS:
            alertas.append(
                Alerta(
                    codigo_glosa="FA0101",
                    titulo="La factura no cuadra con la suma de sus líneas",
                    detalle=(
                        f"Las líneas suman {_pesos(payload.total_items())} y el total "
                        f"declarado es {_pesos(float(payload.valor_total))}. "
                        f"Diferencia de {_pesos(diferencia)}."
                    ),
                    severidad="BLOQUEO",
                    regla="aritmetica_factura",
                    valor_en_riesgo=round(diferencia, 2),
                )
            )
    return alertas


# ═══════════════════════════════════════════════════════════════════════
#  2. TOPES TARIFARIOS — cobrar por encima de lo pactado
# ═══════════════════════════════════════════════════════════════════════
def regla_topes_tarifarios(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Compara el unitario de cada línea contra la tarifa pactada.

    Silencio deliberado cuando no hay tarifa: sin contrato cargado para ese
    CUPS no hay con qué comparar, y estimarla sería inventar. La consulta se
    hace UNA VEZ por CUPS (una factura repite el mismo código en varias
    líneas y no vamos a golpear la base una vez por línea).

    SIN EPS TAMPOCO SE OPINA (04-09-2026). El RIPS de la Resolución 2275 no
    dice quién paga, y sin pagador no existe «tarifa pactada»: la búsqueda
    caía al catálogo oficial del HUS y comparaba la factura contra el precio
    propio del hospital. En la primera factura real de verdad —HUS559077—
    eso produjo 48 BLOQUEOS que el facturador no podía resolver, y encima la
    respuesta decía en `omisiones` que la tarifa NO se había cruzado. Un
    tablero que se contradice a sí mismo deja de leerse a la semana.
    """
    if ctx.db is None or not (payload.eps or "").strip():
        return []
    from app.services.tarifa_lookup_service import tarifa_pactada_de

    alertas: list[Alerta] = []
    cache: dict[str, Optional[dict]] = {}
    for item in payload.items:
        if not item.cups or item.valor_unitario <= 0:
            continue
        if item.cups not in cache:
            try:
                cache[item.cups] = tarifa_pactada_de(ctx.db, payload.eps, item.cups)
            except Exception:
                cache[item.cups] = None
        tarifa = cache[item.cups]
        if not tarifa:
            continue
        pactado = float(tarifa["valor_pactado"])
        techo = pactado * (1 + TOLERANCIA_TARIFA)
        if item.valor_unitario <= techo:
            continue
        exceso = round((item.valor_unitario - pactado) * max(1.0, float(item.cantidad or 1.0)), 2)
        fuente = (
            "la tarifa pactada con la EPS"
            if tarifa["fuente"] == "TARIFA_CONTRATADA"
            else "el catálogo oficial de tarifas del HUS"
        )
        alertas.append(
            Alerta(
                codigo_glosa=causal(item, "TA"),
                titulo="Valor por encima de la tarifa pactada",
                detalle=(
                    f"{item.etiqueta()} se cobra a {_pesos(item.valor_unitario)} y "
                    f"{fuente} dice {_pesos(pactado)}. Sobrecobro de "
                    f"{_pesos(exceso)} en esta línea"
                    + (
                        f" (contrato {tarifa['contrato_numero']})."
                        if tarifa.get("contrato_numero")
                        else "."
                    )
                ),
                severidad="BLOQUEO",
                regla="topes_tarifarios",
                item=item.etiqueta(),
                valor_en_riesgo=exceso,
            )
        )
    return alertas


# ═══════════════════════════════════════════════════════════════════════
#  3. CRUCE DE GÉNERO — un imposible biológico
# ═══════════════════════════════════════════════════════════════════════
def regla_cruce_genero(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Procedimiento propio de un sexo en un paciente del sexo contrario.

    Reutiliza los patrones del Caso I de `reglas_casos_fno` — los mismos con
    los que el motor ya reconoce este error cuando la glosa YA llegó. Acá se
    aplican doce horas antes, que es cuando todavía sirve de algo.
    """
    sexo = payload.paciente.sexo_normalizado()
    if not sexo:
        return []  # sin sexo declarado no se infiere nada
    alertas: list[Alerta] = []
    for item in payload.items:
        exigido = sexo_exigido_por_el_procedimiento(_texto_del_item(item))
        if not exigido or exigido == sexo:
            continue
        legible = "FEMENINO" if exigido == "F" else "MASCULINO"
        paciente = "FEMENINO" if sexo == "F" else "MASCULINO"
        alertas.append(
            Alerta(
                codigo_glosa=causal(item, "FA"),
                titulo="Procedimiento incompatible con el sexo del paciente",
                detalle=(
                    f"{item.etiqueta()} es un procedimiento propio del sexo {legible} "
                    f"y el paciente está registrado como {paciente}. O el sexo está mal "
                    "digitado o la línea no corresponde a esta atención; en ambos casos "
                    "es un error de facturación que se corrige antes de timbrar."
                ),
                severidad="BLOQUEO",
                regla="cruce_genero",
                item=item.etiqueta(),
                valor_en_riesgo=round(item.total_efectivo(), 2),
            )
        )
    return alertas


# ═══════════════════════════════════════════════════════════════════════
#  4. CRUCE DE EDAD — servicios con edad de por medio
# ═══════════════════════════════════════════════════════════════════════
# Bandas explícitas y discutibles a propósito: están acá, escritas, para que
# el auditor las pueda revisar y ajustar. No salen de ninguna norma tarifaria
# —son criterio clínico corriente— y por eso las dudosas avisan en vez de
# bloquear. Solo se bloquea lo materialmente imposible.
DIAS_NEONATO = 28
ANIOS_MAYORIA = 18
# Franja en la que un embarazo es esperable. Fuera de ella NO se bloquea:
# existen embarazos en los extremos y no somos quién para negarlos.
ANIOS_OBSTETRICO_MIN = 10
ANIOS_OBSTETRICO_MAX = 55

_RE_NEONATAL = re.compile(r"NEONAT|RECIEN\s+NACID", re.IGNORECASE)
_RE_PEDIATRICO = re.compile(r"PEDIATRIC", re.IGNORECASE)
_RE_ADULTO = re.compile(r"\bADULTO", re.IGNORECASE)
_RE_OBSTETRICO = re.compile(r"PARTO|CESAREA|OBSTETRIC|GESTACION|PRENATAL", re.IGNORECASE)


# En estos tipos de línea las palabras «neonatal», «pediátrico» y «adulto»
# describen el TAMAÑO del artículo, no la edad de quien lo recibe: una sonda
# pediátrica o un catéter neonatal se le ponen a un adulto todos los días, y
# la dosis pediátrica de un medicamento también se usa fuera de pediatría.
# Caso real (HUS559077, 04-09-2026): el insumo FMQ0098 salió BLOQUEADO como
# «servicio pediátrico en un paciente adulto». Era un calibre.
_TIPOS_DONDE_LA_EDAD_ES_TAMANO = {"DISPOSITIVO", "MEDICAMENTO"}


def regla_cruce_edad(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Servicio marcado para una edad que no es la del paciente.

    Mira SERVICIOS, no artículos: en un insumo o un medicamento la palabra
    que nombra una edad es una talla o una dosis (ver la constante de arriba).
    """
    dias = payload.paciente.edad_en_dias(payload.atencion.fecha_ingreso or ctx.ahora)
    if dias is None:
        return []
    anios = dias / 365.25
    alertas: list[Alerta] = []

    def _alerta(item: ItemFactura, titulo: str, detalle: str, severidad: str) -> Alerta:
        return Alerta(
            codigo_glosa=causal(item, "FA" if severidad == "BLOQUEO" else "CL"),
            titulo=titulo,
            detalle=detalle,
            severidad=severidad,  # type: ignore[arg-type]
            regla="cruce_edad",
            item=item.etiqueta(),
            valor_en_riesgo=round(item.total_efectivo(), 2),
        )

    for item in payload.items:
        if tipo_de(item) in _TIPOS_DONDE_LA_EDAD_ES_TAMANO:
            continue
        texto = _sin_tildes(_texto_del_item(item))
        if _RE_NEONATAL.search(texto) and dias > DIAS_NEONATO:
            alertas.append(
                _alerta(
                    item,
                    "Servicio neonatal en un paciente que no es recién nacido",
                    f"{item.etiqueta()} es un servicio de recién nacido y el paciente "
                    f"tiene {anios:.1f} años ({dias} días). Recién nacido es hasta "
                    f"{DIAS_NEONATO} días.",
                    "BLOQUEO",
                )
            )
        elif _RE_PEDIATRICO.search(texto) and anios >= ANIOS_MAYORIA:
            alertas.append(
                _alerta(
                    item,
                    "Servicio pediátrico en un paciente adulto",
                    f"{item.etiqueta()} es un servicio pediátrico y el paciente tiene "
                    f"{anios:.1f} años.",
                    "BLOQUEO",
                )
            )
        elif _RE_ADULTO.search(texto) and anios < ANIOS_MAYORIA:
            alertas.append(
                _alerta(
                    item,
                    "Servicio de adultos en un paciente menor de edad",
                    f"{item.etiqueta()} está marcado para adultos y el paciente tiene "
                    f"{anios:.1f} años.",
                    "BLOQUEO",
                )
            )
        elif _RE_OBSTETRICO.search(texto) and not (
            ANIOS_OBSTETRICO_MIN <= anios <= ANIOS_OBSTETRICO_MAX
        ):
            alertas.append(
                _alerta(
                    item,
                    "Servicio obstétrico fuera de la edad esperable",
                    f"{item.etiqueta()} es un servicio obstétrico y la paciente tiene "
                    f"{anios:.1f} años. No es imposible, pero la EPS lo va a mirar: "
                    "conviene que la historia clínica lo respalde de forma explícita.",
                    "ADVERTENCIA",
                )
            )
    return alertas


# ═══════════════════════════════════════════════════════════════════════
#  5. VÍAS QUIRÚRGICAS — dos caminos para un mismo acto
# ═══════════════════════════════════════════════════════════════════════
# Las vías son excluyentes entre sí: una colecistectomía es abierta o es
# laparoscópica, nunca las dos. Facturar las dos es cobrar dos veces el mismo
# acto quirúrgico, y es glosa segura.
_VIAS: tuple[tuple[str, str], ...] = (
    ("LAPAROSCOPICA", r"LAPAROSCOP|VIDEOLAPAROSCOP"),
    ("ENDOSCOPICA", r"ENDOSCOP"),
    ("PERCUTANEA", r"PERCUTANE"),
    ("CESAREA", r"CESAREA"),
    ("VAGINAL", r"VAGINAL"),
    ("ABIERTA", r"LAPAROTOM|ABIERT|CIELO\s+ABIERTO|TORACOTOM"),
)
# Palabras que no forman parte del acto sino de cómo se llegó a él: se quitan
# para saber si dos líneas hablan del MISMO procedimiento.
_RE_RELLENO_VIA = re.compile(
    r"\b(POR|VIA|MEDIANTE|CON|DE|LA|EL|TECNICA|ABORDAJE)\b|"
    r"LAPAROSCOPIC\w*|VIDEOLAPAROSCOPIC\w*|LAPAROTOMIA|ENDOSCOPIC\w*|PERCUTANE\w*|"
    r"ABIERT\w*|CIELO\s+ABIERTO|TORACOTOMIA|CESAREA|VAGINAL|ESPONTANE\w*",
    re.IGNORECASE,
)


def via_de(item: ItemFactura) -> str:
    """La vía quirúrgica de una línea. Lo declarado manda; si no, la descripción."""
    declarada = (item.via or "").strip().upper()
    for nombre, _ in _VIAS:
        if declarada == nombre:
            return nombre
    texto = _sin_tildes(f"{item.via} {_texto_del_item(item)}")
    for nombre, patron in _VIAS:
        if re.search(patron, texto, re.IGNORECASE):
            return nombre
    return ""


def familia_quirurgica(item: ItemFactura) -> str:
    """El acto quirúrgico sin la vía. «COLECISTECTOMÍA POR LAPAROTOMÍA» y
    «COLECISTECTOMÍA LAPAROSCÓPICA» dan la misma familia: COLECISTECTOMIA."""
    texto = _sin_tildes(_texto_del_item(item))
    limpio = _RE_RELLENO_VIA.sub(" ", texto)
    limpio = re.sub(r"[^A-Z0-9 ]+", " ", limpio)
    palabras = [p for p in limpio.split() if len(p) >= 5]
    return " ".join(palabras[:2])


def regla_vias_quirurgicas(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Dos vías distintas para el mismo acto quirúrgico en la misma factura."""
    por_familia: dict[str, list[tuple[ItemFactura, str]]] = {}
    for item in payload.items:
        via = via_de(item)
        if not via:
            continue
        familia = familia_quirurgica(item)
        if not familia:
            continue
        por_familia.setdefault(familia, []).append((item, via))

    alertas: list[Alerta] = []
    for familia, lineas in por_familia.items():
        vias = {via for _, via in lineas}
        if len(vias) < 2:
            continue
        items = [item for item, _ in lineas]
        en_riesgo = round(max(i.total_efectivo() for i in items), 2)
        # El parto es la excepción honesta: en un embarazo múltiple puede
        # haber un nacimiento vaginal y otro por cesárea. Se avisa, no se
        # bloquea, y se dice qué soporte lo salva.
        es_parto = "PARTO" in familia
        alertas.append(
            Alerta(
                codigo_glosa=causal(items[0], "FA"),
                titulo="Dos vías quirúrgicas excluyentes para el mismo acto",
                detalle=(
                    f"Se facturan {len(items)} líneas de «{familia.title()}» por vías "
                    f"distintas ({', '.join(sorted(vias))}): "
                    + "; ".join(f"{i.etiqueta()} {_pesos(i.total_efectivo())}" for i in items)
                    + (
                        ". En un embarazo múltiple puede ser correcto: si es el caso, "
                        "la epicrisis debe dejarlo explícito antes de timbrar."
                        if es_parto
                        else ". Un mismo acto quirúrgico se hace por una sola vía; "
                        "facturar las dos es cobrar dos veces el mismo procedimiento."
                    )
                ),
                severidad="ADVERTENCIA" if es_parto else "BLOQUEO",
                regla="vias_quirurgicas",
                item=items[0].etiqueta(),
                valor_en_riesgo=en_riesgo,
            )
        )
    return alertas


# ═══════════════════════════════════════════════════════════════════════
#  6. COHERENCIA TEMPORAL Y ESTANCIA
# ═══════════════════════════════════════════════════════════════════════
def regla_fechas_y_estancia(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Egreso antes del ingreso, días facturados de más, UCI más larga que la
    estancia y líneas fechadas fuera del episodio."""
    alertas: list[Alerta] = []
    at = payload.atencion
    ingreso, egreso = at.fecha_ingreso, at.fecha_egreso

    if ingreso and egreso and egreso.date() < ingreso.date():
        # Una factura con las fechas invertidas no se glosa: se DEVUELVE
        # entera. Por eso el riesgo es toda la factura, no una línea.
        alertas.append(
            Alerta(
                codigo_glosa="FA0101",
                titulo="La fecha de egreso es anterior a la de ingreso",
                detalle=(
                    f"Ingreso {ingreso.strftime('%d/%m/%Y')} y egreso "
                    f"{egreso.strftime('%d/%m/%Y')}. Es materialmente imposible y hace "
                    "que la factura se devuelva completa, con pérdida del turno de "
                    "radicación."
                ),
                severidad="BLOQUEO",
                regla="fechas_invertidas",
                valor_en_riesgo=round(payload.total_efectivo(), 2),
            )
        )

    calendario = at.dias_calendario()
    if calendario is not None and at.dias_estancia is not None:
        # Un día de ingreso y egreso el mismo día se factura como 1 día.
        esperado = max(calendario, 1)
        if int(at.dias_estancia) > esperado:
            sobra = int(at.dias_estancia) - esperado
            unitario = next(
                (i.valor_unitario for i in payload.items if tipo_de(i) == "ESTANCIA"), 0.0
            )
            alertas.append(
                Alerta(
                    codigo_glosa="FA0101",
                    titulo="Se facturan más días de estancia que los del episodio",
                    detalle=(
                        f"Entre el ingreso y el egreso hay {esperado} día(s) y se "
                        f"facturan {int(at.dias_estancia)}. Sobran {sobra}."
                    ),
                    severidad="BLOQUEO",
                    regla="estancia_mayor_que_episodio",
                    valor_en_riesgo=round(sobra * float(unitario or 0.0), 2),
                )
            )

    if at.dias_uci is not None and int(at.dias_uci) > 0:
        tope = at.dias_estancia if at.dias_estancia is not None else calendario
        if tope is not None and int(at.dias_uci) > max(int(tope), 1):
            alertas.append(
                Alerta(
                    codigo_glosa="FA0101",
                    titulo="Más días de UCI que días de estancia",
                    detalle=(
                        f"Se facturan {int(at.dias_uci)} días de UCI dentro de una "
                        f"estancia de {int(tope)} día(s). La UCI no puede durar más que "
                        "la hospitalización que la contiene."
                    ),
                    severidad="BLOQUEO",
                    regla="uci_mayor_que_estancia",
                    valor_en_riesgo=0.0,
                )
            )

    if ingreso and egreso and egreso.date() >= ingreso.date():
        for item in payload.items:
            if not item.fecha:
                continue
            if ingreso.date() <= item.fecha.date() <= egreso.date():
                continue
            alertas.append(
                Alerta(
                    codigo_glosa=causal(item, "FA"),
                    titulo="Línea fechada fuera del episodio de atención",
                    detalle=(
                        f"{item.etiqueta()} está fechada el "
                        f"{item.fecha.strftime('%d/%m/%Y')} y el episodio va del "
                        f"{ingreso.strftime('%d/%m/%Y')} al {egreso.strftime('%d/%m/%Y')}."
                    ),
                    severidad="ADVERTENCIA",
                    regla="linea_fuera_del_episodio",
                    item=item.etiqueta(),
                    valor_en_riesgo=round(item.total_efectivo(), 2),
                )
            )
    return alertas


# ═══════════════════════════════════════════════════════════════════════
#  7. DOBLE FACTURACIÓN
# ═══════════════════════════════════════════════════════════════════════
# Hay servicios que se repiten legítimamente el mismo día —dosis de un
# medicamento, días de estancia, insumos—: esos NO se miran.
_TIPOS_QUE_SE_REPITEN = {"MEDICAMENTO", "DISPOSITIVO", "ESTANCIA"}


def regla_doble_facturacion(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Mismo CUPS, misma fecha, dos veces en la misma factura."""
    vistos: dict[tuple[str, str], list[ItemFactura]] = {}
    for item in payload.items:
        if not item.cups or tipo_de(item) in _TIPOS_QUE_SE_REPITEN:
            continue
        clave = (item.cups, item.fecha.strftime("%Y-%m-%d") if item.fecha else "")
        vistos.setdefault(clave, []).append(item)

    alertas: list[Alerta] = []
    for (cups, fecha), items in vistos.items():
        if len(items) < 2:
            continue
        repetido = round(sum(i.total_efectivo() for i in items[1:]), 2)
        cuando = f" el {datetime.strptime(fecha, '%Y-%m-%d').strftime('%d/%m/%Y')}" if fecha else ""
        alertas.append(
            Alerta(
                codigo_glosa="FA2702",
                titulo="El mismo servicio aparece más de una vez",
                detalle=(
                    f"{cups} se factura {len(items)} veces{cuando}. Si de verdad se "
                    "prestó más de una vez, la historia clínica tiene que sustentarlo; "
                    "si no, es doble facturación."
                ),
                severidad="ADVERTENCIA",
                regla="doble_facturacion",
                item=cups,
                valor_en_riesgo=repetido,
            )
        )
    return alertas


# ═══════════════════════════════════════════════════════════════════════
#  8. CONTRATO VIGENTE EL DÍA DE LA ATENCIÓN
# ═══════════════════════════════════════════════════════════════════════
def regla_contrato_vigente(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """¿Había contrato con esa EPS el día en que se prestó el servicio?

    Riesgo de proceso, no de pesos: por eso el valor en riesgo es cero. Lo
    que se avisa es que esa factura va a viajar sin marco contractual.
    """
    dia = payload.atencion.fecha_ingreso
    if not dia:
        return []
    try:
        from app.services.malla_contractual import contratos_de, vigente

        if not contratos_de(payload.eps):
            return []  # la EPS no está en la malla: no se opina
        if vigente(payload.eps, dia.date()):
            return []
    except Exception:
        return []
    return [
        Alerta(
            codigo_glosa="CO5801",
            titulo="Sin contrato vigente el día de la atención",
            detalle=(
                f"En la malla de contratación no aparece contrato con {payload.eps} "
                f"vigente el {dia.strftime('%d/%m/%Y')}. Verificar con el área de "
                "contratación antes de timbrar: sin marco contractual la EPS objeta "
                "el valor completo y la defensa queda sin piso."
            ),
            severidad="ADVERTENCIA",
            regla="contrato_vigente",
            valor_en_riesgo=0.0,
        )
    ]


# ═══════════════════════════════════════════════════════════════════════
#  9. UCI SIN MARCADOR CLÍNICO EN LA EPICRISIS
# ═══════════════════════════════════════════════════════════════════════
# Los marcadores con los que el propio hospital defiende una UCI glosada
# (banco de respuestas del HUS, causal CL0101): puntajes de gravedad, soporte
# vasopresor, ventilación mecánica, falla multiorgánica. Si la epicrisis no
# nombra ninguno, la UCI se va a glosar — y esta vez tendrían razón.
_RE_MARCADOR_UCI = re.compile(
    r"APACHE|\bSOFA\b|VASOPRESOR|NORADRENALINA|NORE?PINEFRINA|ADRENALINA|DOBUTAMINA|"
    r"VENTILACION\s+MECANICA|INTUBAC|ORO\s?TRAQUEAL|SHOCK|CHOQUE\s+SEPTIC|"
    r"FALLA\s+MULTIORGANICA|SEPSIS|INESTABILIDAD\s+HEMODINAMICA|GLASGOW|"
    r"CUIDADO\s+CRITICO|MONITOREO\s+INVASIVO|SOPORTE\s+INOTROPIC",
    re.IGNORECASE,
)
_RE_ITEM_UCI = re.compile(r"\bUCI\b|CUIDADO[S]?\s+INTENSIVO", re.IGNORECASE)


def regla_uci_sin_soporte(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Se factura UCI y la epicrisis no nombra un solo criterio de gravedad."""
    items_uci = [i for i in payload.items if _RE_ITEM_UCI.search(_sin_tildes(_texto_del_item(i)))]
    hay_uci = bool(items_uci) or bool(payload.atencion.dias_uci)
    if not hay_uci:
        return []
    epicrisis = _sin_tildes(payload.epicrisis)
    if not epicrisis:
        detalle = (
            "Se factura UCI y el HIS no mandó epicrisis. Sin ella no se puede "
            "verificar el criterio de ingreso, y la EPS glosa la estancia completa."
        )
    elif _RE_MARCADOR_UCI.search(epicrisis):
        return []
    else:
        detalle = (
            "Se factura UCI y la epicrisis no nombra ningún criterio de gravedad "
            "(APACHE II / SOFA, soporte vasopresor, ventilación mecánica, falla "
            "multiorgánica). Es exactamente lo que la EPS objeta como «ingreso a UCI "
            "injustificado»: conviene que el intensivista deje escrito el criterio "
            "antes de timbrar."
        )
    en_riesgo = round(sum(i.total_efectivo() for i in items_uci), 2)
    return [
        Alerta(
            codigo_glosa="CL0101",
            titulo="Estancia en UCI sin criterio de ingreso documentado",
            detalle=detalle,
            severidad="ADVERTENCIA",
            regla="uci_sin_soporte",
            item=items_uci[0].etiqueta() if items_uci else "",
            valor_en_riesgo=en_riesgo,
        )
    ]


# La cadena, en orden. Primero lo que cuesta cero y prueba más.
REGLAS_DURAS: tuple[Regla, ...] = (
    regla_aritmetica,
    regla_fechas_y_estancia,
    regla_cruce_genero,
    regla_cruce_edad,
    regla_vias_quirurgicas,
    regla_doble_facturacion,
    regla_uci_sin_soporte,
    regla_contrato_vigente,
    regla_topes_tarifarios,  # la única que consulta la base: va al final
)


def correr_reglas_duras(payload: PayloadFactura, ctx: Contexto) -> list[Alerta]:
    """Corre toda la cadena. Una regla que se cae NO tumba a las demás.

    El facturador quiere ver TODOS los reparos de una vez: por eso una regla
    que dispara BLOQUEO no corta la cadena. Corregir de a un reparo por
    consulta es la forma más rápida de que nadie use la herramienta.
    """
    from app.core.logging_utils import logger

    alertas: list[Alerta] = []
    for regla in REGLAS_DURAS:
        try:
            alertas.extend(regla(payload, ctx))
        except Exception as e:  # pragma: no cover - defensa
            logger.warning(f"[PRE-AUDITORIA] la regla {regla.__name__} falló: {e}")
    return alertas
