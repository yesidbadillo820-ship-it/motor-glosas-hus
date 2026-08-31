"""La malla de contratación del HUS, como dato — y qué contrato regía cuándo.

DE DÓNDE SALE. Del documento oficial `MALLA_CONTRATACIÓN_28072026.pdf` que
mantiene el área de contratación. Es la fuente de verdad sobre qué contrato
tiene cada pagador, con qué tarifa y hasta cuándo.

LOS DOS PROBLEMAS QUE RESUELVE

1. EL CONTRATO SE ELEGÍA POR NOMBRE, NO POR FECHA. `CONTRATOS_HUS` guardaba
   la vigencia como texto libre —`'2025'`, `'15/04/2026 — 14/04/2027'`— y
   nadie la leía. Así, una atención de marzo de 2026 se defendía citando el
   contrato de FAMISANAR que empezó el 15 de abril: un contrato que **no
   regía el día del hecho**. La EPS ratifica la glosa y tiene razón.

2. UN PAGADOR PUEDE TENER VARIOS CONTRATOS A LA VEZ. COOSALUD tiene dos
   —subsidiado y contributivo— con fechas distintas, y el PPL tiene el
   contrato original más un otrosí que lo extiende. Un diccionario con una
   entrada por nombre no puede representar eso.

LA REGLA. Se resuelve por **la fecha del hecho**: qué contrato estaba vigente
el día en que se prestó el servicio, no el que esté cargado hoy. Es la misma
regla que rige la extemporaneidad y la tarifa.

CÓMO SE ACTUALIZA. Cuando contratación publique una malla nueva, se
actualizan las fichas de `MALLA` y las pruebas de vigencia lo confirman. Los
números de contrato van tal cual aparecen en el documento: un dígito cambiado
hace que el dictamen cite un contrato que no existe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# Fecha del documento del que salieron estos datos. Sirve para que la pantalla
# pueda decir "malla al 28-jul-2026" y para saber cuándo toca actualizarla.
FECHA_MALLA = date(2026, 7, 28)

# A partir de cuántos días de anticipación se avisa que un contrato se acaba.
# Renegociar un contrato hospitalario toma semanas; 60 días es lo que el área
# necesita para no quedar sin marco contractual.
DIAS_AVISO_VENCIMIENTO = 60


@dataclass(frozen=True)
class Contrato:
    """Un contrato del HUS con un pagador, tal como está en la malla."""

    pagador: str  # nombre canónico, en mayúsculas
    nombre_malla: str  # cómo aparece en el documento oficial
    numero: str  # exacto, con guiones; "" si la malla no lo trae
    desde: date
    hasta: date | None  # None = indeterminado / hasta agotar recurso
    tarifa_texto: str  # literal de la columna TARIFAS
    factor: float | None  # multiplicador sobre la base; None si no aplica
    base: str  # SOAT | SOAT_UVB | SOAT_SMLV | PROPIA | PACTADA | MIXTA
    tecnologias: str = ""
    exclusiones: tuple[str, ...] = ()
    observacion: str = ""
    # Algunos contratos terminan "o hasta agotar recurso, lo que primero
    # ocurra". La fecha es el techo, pero el dinero puede acabarse antes: si
    # el área no lo vigila, se factura contra un contrato ya agotado.
    hasta_agotar_recurso: bool = False
    alias: tuple[str, ...] = field(default=())

    def vigente_en(self, dia: date) -> bool:
        if dia < self.desde:
            return False
        return self.hasta is None or dia <= self.hasta

    def dias_para_vencer(self, hoy: date) -> int | None:
        """Negativo si ya venció. None si es indeterminado."""
        return None if self.hasta is None else (self.hasta - hoy).days

    def como_dict(self) -> dict[str, Any]:
        return {
            "pagador": self.pagador,
            "nombre_malla": self.nombre_malla,
            "numero": self.numero,
            "desde": self.desde.isoformat(),
            "hasta": self.hasta.isoformat() if self.hasta else None,
            "hasta_agotar_recurso": self.hasta_agotar_recurso,
            "tarifa_texto": self.tarifa_texto,
            "factor": self.factor,
            "base": self.base,
            "tecnologias": self.tecnologias,
            "exclusiones": list(self.exclusiones),
            "observacion": self.observacion,
        }


_D = date

# ─── La malla, al 28-jul-2026 ─────────────────────────────────────────────

MALLA: tuple[Contrato, ...] = (
    Contrato(
        pagador="COOSALUD",
        nombre_malla="COOSALUD (Subsidiado)",
        numero="68001S00060339-24",
        desde=_D(2024, 5, 1),
        hasta=_D(2026, 4, 30),
        tarifa_texto="SOAT -15%, TARIFAS INSTITUCIONALES",
        factor=0.85,
        base="MIXTA",
        tecnologias="Los demás servicios no excluidos en el cuadro anexo",
        exclusiones=(
            "Medicamentos oncológicos: los suministra COOSALUD",
            "Material de osteosíntesis: cotización remitida a la EPS",
        ),
        observacion=(
            "Medicamentos y dispositivos proporcionados por la ESE HUS se reconocen "
            "a tarifas de las Resoluciones HUS y anexo tarifario."
        ),
        alias=("COOSALUD SUBSIDIADO",),
    ),
    Contrato(
        pagador="COOSALUD",
        nombre_malla="COOSALUD (Contributivo)",
        numero="68001C00060340-24",
        desde=_D(2024, 5, 1),
        hasta=_D(2027, 4, 30),
        tarifa_texto="SOAT -15%, TARIFAS INSTITUCIONALES",
        factor=0.85,
        base="MIXTA",
        tecnologias="Los demás servicios no excluidos en el cuadro anexo",
        exclusiones=(
            "Medicamentos oncológicos: los suministra COOSALUD",
            "Material de osteosíntesis: cotización remitida a la EPS",
        ),
        alias=("COOSALUD CONTRIBUTIVO",),
    ),
    Contrato(
        pagador="COMPENSAR",
        nombre_malla="COMPENSAR EPS",
        numero="CSS009-2024",
        desde=_D(2025, 4, 4),
        hasta=_D(2026, 4, 3),
        tarifa_texto="SOAT -15% Y TARIFAS PROPIAS",
        factor=0.85,
        base="MIXTA",
        tecnologias="Todos los servicios que presta la ESE HUS (mediana y alta complejidad)",
        exclusiones=(
            "Medicamentos oncológicos",
            "Medicamentos ambulatorios",
            "MAOS: lo entrega la EPS",
        ),
    ),
    Contrato(
        pagador="FAMISANAR",
        nombre_malla="FAMISANAR EPS",
        numero="S13103104958",
        desde=_D(2026, 4, 15),
        hasta=_D(2027, 4, 14),
        tarifa_texto=(
            "SOAT UVB -5%, TARIFAS INSTITUCIONALES BAJO RESOLUCIÓN "
            "Y TARIFAS ESPECIALES AMBULATORIOS"
        ),
        factor=0.95,
        base="SOAT_UVB",
        tecnologias="Todos los servicios prestados por la ESE HUS",
        observacion=(
            "El material de osteosíntesis debe reportarse a la EPS para enlace con el "
            "operador logístico: autorizacioneshospitalarias2@famisanar.com.co"
        ),
    ),
    Contrato(
        pagador="FOMAG",
        nombre_malla="PREVISORA FOMAG",
        numero="",
        desde=_D(2025, 8, 1),
        hasta=None,
        tarifa_texto=("SOAT -15%, TARIFAS INSTITUCIONALES, TARIFAS ESPECIALES AMBULATORIOS"),
        factor=0.85,
        base="MIXTA",
        tecnologias="Todos los servicios prestados por la ESE HUS",
        observacion=(
            "Continúan las condiciones iniciales hasta formalizar el contrato (carta de intención)."
        ),
        alias=("PREVISORA", "LA PREVISORA"),
    ),
    Contrato(
        pagador="DISPENSARIO MEDICO",
        nombre_malla="DIRECCIÓN DE SANIDAD EJÉRCITO — DISPENSARIO MÉDICO DE BUCARAMANGA",
        numero="440-DIGSA/DMBUG-2025",
        desde=_D(2025, 12, 30),
        hasta=_D(2026, 7, 30),
        hasta_agotar_recurso=True,
        tarifa_texto="SOAT SMLV -20%, TARIFAS INSTITUCIONALES",
        factor=0.80,
        base="SOAT_SMLV",
        tecnologias="Todos los servicios que presta la ESE HUS",
        observacion="2025: $3.235.000.000 · 2026: acta de reconocimiento 01 de abril de 2026.",
        alias=("DISPENSARIO", "DSE EJERCITO", "EJERCITO", "DMBUG"),
    ),
    Contrato(
        pagador="POLICIA NACIONAL ONCOLOGIA",
        nombre_malla="REGIONAL DE ASEGURAMIENTO EN SALUD No. 5 — POLICÍA (oncología)",
        numero="068-5-200006-26",
        desde=_D(2026, 3, 4),
        hasta=_D(2026, 7, 31),
        hasta_agotar_recurso=True,
        tarifa_texto="SOAT UVB -8%, TARIFAS INSTITUCIONALES",
        factor=0.92,
        base="SOAT_UVB",
        tecnologias=(
            "Servicios en el marco del servicio de oncología, incluidos los "
            "medicamentos requeridos para el tratamiento"
        ),
        observacion="$1.440.000.000 para 2026.",
    ),
    Contrato(
        pagador="POLICIA NACIONAL",
        nombre_malla="REGIONAL DE ASEGURAMIENTO EN SALUD No. 5 — POLICÍA",
        numero="068-5-200004-26",
        desde=_D(2026, 2, 21),
        hasta=_D(2026, 8, 15),
        hasta_agotar_recurso=True,
        tarifa_texto="SOAT UVB -8%, TARIFAS INSTITUCIONALES",
        factor=0.92,
        base="SOAT_UVB",
        tecnologias="Servicios prestados por la ESE HUS",
    ),
    Contrato(
        pagador="NUEVA EPS",
        nombre_malla="NUEVA EPS (Subsidiado/Contributivo)",
        numero="02-01-06-00077-2017",
        desde=_D(2017, 3, 31),
        hasta=_D(2026, 3, 31),
        tarifa_texto="SOAT -20%",
        factor=0.80,
        base="SOAT",
        tecnologias="Todos los servicios que presta la ESE HUS",
        exclusiones=(
            "Material de osteosíntesis: previa solicitud a la EPS puede entregarlo el HUS",
        ),
        observacion=(
            "Medicamentos de hematología y oncología los suministra el HUS. Radiología "
            "intervencionista y angiografía requieren autorización previa."
        ),
    ),
    Contrato(
        pagador="PPL",
        nombre_malla="CONSORCIO PPL FIDUCIARIA CENTRAL S.A.",
        numero="IPS-001B-2022",
        desde=_D(2022, 1, 1),
        hasta=_D(2025, 11, 30),
        tarifa_texto="SOAT -15%, TARIFAS INSTITUCIONALES",
        factor=0.85,
        base="MIXTA",
        tecnologias="Todos los servicios que presta la ESE HUS",
        observacion="Adición $730.095.000 sobre $8.801.799.646.",
        alias=("CONSORCIO PPL", "FIDUCIARIA CENTRAL"),
    ),
    Contrato(
        pagador="PPL",
        nombre_malla="CONSORCIO PPL FIDUCIARIA CENTRAL S.A. — Otrosí N° 26",
        numero="IPS-001B-2022 Otrosí N° 26",
        desde=_D(2026, 1, 1),
        hasta=_D(2026, 7, 31),
        tarifa_texto="SOAT -15%, TARIFAS INSTITUCIONALES",
        factor=0.85,
        base="MIXTA",
        tecnologias="Todos los servicios que presta la ESE HUS",
        observacion="Adición $654.472.000 sobre $10.735.855.646.",
        alias=("CONSORCIO PPL", "FIDUCIARIA CENTRAL"),
    ),
    Contrato(
        pagador="POSITIVA",
        nombre_malla="POSITIVA",
        numero="525 - OTROSÍ",
        desde=_D(2025, 12, 12),
        hasta=_D(2026, 12, 11),
        tarifa_texto="SOAT SMLV -15%, TARIFAS PROPIAS",
        factor=0.85,
        base="SOAT_SMLV",
        tecnologias="Todos los servicios que presta la ESE HUS",
        observacion=(
            "ARL: accidente de trabajo, enfermedad profesional y accidentes personales. "
            "Excluye lo que no contribuya al diagnóstico, tratamiento o rehabilitación "
            "de la patología del evento calificado."
        ),
    ),
    Contrato(
        pagador="SUMIMEDICAL",
        nombre_malla="SUMIMEDICAL S.A.S",
        numero="FPS23-050",
        desde=_D(2023, 7, 27),
        hasta=_D(2026, 7, 31),
        tarifa_texto="SOAT -15%",
        factor=0.85,
        base="SOAT",
        tecnologias="Todos los servicios que presta la ESE HUS",
        exclusiones=(
            "Material de osteosíntesis: lo suministra la EPS",
            "Medicamentos de hematología y oncología: los suministra la EPS",
        ),
        observacion="Fondo de Pasivo Social de Ferrocarriles Nacionales de Colombia.",
        alias=("FERROCARRILES", "FPS"),
    ),
    Contrato(
        pagador="SALUD MIA",
        nombre_malla="SALUD MIA (subsidiado)",
        numero="SSA2025EVE3A005",
        desde=_D(2025, 6, 1),
        hasta=_D(2026, 5, 31),
        tarifa_texto="SOAT -15% Y TARIFAS PROPIAS",
        factor=0.85,
        base="MIXTA",
        tecnologias="Plan canguro, IVE y demás servicios de portafolio, previa autorización",
        exclusiones=("Medicamentos ambulatorios", "Medicamentos oncológicos"),
        observacion=(
            "Los procedimientos de alto costo requieren autorización de la ERP, salvo lo "
            "establecido en la Circular 019 de 2023 del Ministerio de Salud."
        ),
    ),
    Contrato(
        pagador="SALUD MIA",
        nombre_malla="SALUD MIA (contributivo)",
        numero="CSA2025EVE3A005",
        desde=_D(2025, 6, 1),
        hasta=_D(2026, 5, 31),
        tarifa_texto="SOAT -15% Y TARIFAS PROPIAS",
        factor=0.85,
        base="MIXTA",
        tecnologias="Plan canguro, IVE y demás servicios de portafolio, previa autorización",
        exclusiones=("Medicamentos ambulatorios", "Medicamentos oncológicos"),
    ),
    Contrato(
        pagador="AURORA",
        nombre_malla="SEGUROS AURORA / ARL",
        numero="GID ARL 0090",
        desde=_D(2025, 9, 1),
        hasta=_D(2026, 8, 31),
        tarifa_texto="SOAT -3%, TARIFAS INSTITUCIONALES",
        factor=0.97,
        base="MIXTA",
        tecnologias="Servicios prestados por la ESE HUS, previa autorización",
        exclusiones=("Medicamentos ambulatorios",),
        observacion=(
            "El MAOS puede entregarlo el HUS si se autoriza, o si habiéndolo solicitado "
            "la ARL no lo entrega en un plazo máximo de 12 horas."
        ),
        alias=("SEGUROS AURORA",),
    ),
    Contrato(
        pagador="AURORA",
        nombre_malla="SEGUROS AURORA / AP",
        numero="GID AP 0090",
        desde=_D(2025, 9, 1),
        hasta=_D(2026, 8, 31),
        tarifa_texto="SOAT -3%, TARIFAS INSTITUCIONALES",
        factor=0.97,
        base="MIXTA",
        tecnologias="Accidentes personales",
        alias=("SEGUROS AURORA",),
    ),
    Contrato(
        pagador="HDI SEGUROS",
        nombre_malla="HDI SEGUROS ARL",
        numero="",
        desde=_D(2026, 4, 15),
        hasta=_D(2027, 4, 14),
        tarifa_texto="SOAT UVB -3%, TARIFAS INSTITUCIONALES",
        factor=0.97,
        base="SOAT_UVB",
        tecnologias="Servicios prestados por la ESE HUS, previa autorización",
        exclusiones=("Medicamentos ambulatorios",),
        alias=("HDI",),
    ),
    Contrato(
        pagador="SEGUROS MUNDIAL",
        nombre_malla="SEGUROS MUNDIAL ARL",
        numero="",
        desde=_D(2026, 5, 15),
        hasta=_D(2027, 5, 14),
        tarifa_texto="SOAT UVB -3%, TARIFAS INSTITUCIONALES",
        factor=0.97,
        base="SOAT_UVB",
        tecnologias="Servicios prestados por la ESE HUS, previa autorización",
        exclusiones=("Medicamentos ambulatorios",),
        alias=("MUNDIAL",),
    ),
    Contrato(
        pagador="COLMENA",
        nombre_malla="COLMENA SEGUROS ARL",
        numero="",
        desde=_D(2026, 4, 15),
        hasta=_D(2027, 4, 14),
        tarifa_texto="SOAT UVB -3%, TARIFAS INSTITUCIONALES",
        factor=0.97,
        base="SOAT_UVB",
        tecnologias="Servicios prestados por la ESE HUS, previa autorización",
        exclusiones=("Medicamentos ambulatorios",),
        alias=("COLMENA SEGUROS",),
    ),
    Contrato(
        pagador="VITALQ",
        nombre_malla="VITALQ S.A.S. - BIC",
        numero="",
        desde=_D(2023, 5, 17),
        hasta=_D(2028, 5, 17),
        tarifa_texto="TARIFAS PACTADAS",
        factor=None,
        base="PACTADA",
        tecnologias="Solo suministro de hemoderivados (plasma)",
    ),
    Contrato(
        pagador="EVOLUZION",
        nombre_malla="EVOLUZION (referencia y contrarreferencia)",
        numero="",
        desde=_D(2025, 11, 26),
        hasta=_D(2026, 5, 26),
        tarifa_texto="TARIFAS PACTADAS",
        factor=None,
        base="PACTADA",
        tecnologias="Servicios de referencia y contrarreferencia",
    ),
    Contrato(
        pagador="MESSER COLOMBIA",
        nombre_malla="MESSER COLOMBIA S.A.",
        numero="",
        desde=_D(2022, 11, 1),
        hasta=_D(2026, 11, 1),
        tarifa_texto="TARIFAS PACTADAS",
        factor=None,
        base="PACTADA",
        tecnologias="Suministro de sangre y hemocomponentes",
        alias=("MESSER",),
    ),
    Contrato(
        pagador="CLINICA REVIVIR",
        nombre_malla="CLÍNICA REVIVIR",
        numero="",
        desde=_D(2026, 2, 10),
        hasta=_D(2027, 2, 9),
        tarifa_texto="TARIFAS PROPIAS",
        factor=None,
        base="PROPIA",
        tecnologias="Solo servicio de suministro de hemoderivados",
        alias=("REVIVIR",),
    ),
    Contrato(
        pagador="FCV",
        nombre_malla="FCV",
        numero="LABC - HIC - 2025 - 427",
        desde=_D(2026, 4, 22),
        hasta=_D(2027, 4, 21),
        tarifa_texto="TARIFAS PROPIAS",
        factor=None,
        base="PROPIA",
        tecnologias="Necropsias, irradiación de hemocomponentes, GeneXpert BK y cultivo",
    ),
)


def _normalizar(texto: str) -> str:
    """Deja el nombre del pagador comparable con el de la malla.

    31-08-2026 — LOS PUNTOS ROMPÍAN EL MATCH, Y CON EL PAGADOR MÁS FRECUENTE.
    En la base del hospital NUEVA EPS aparece escrita «NUEVA E.P.S. S.A. -
    SUBSIDIADO». Como la comparación es por PALABRA COMPLETA, «E.P.S.» nunca
    era «EPS» y esa entidad se quedaba sin ningún contrato: el motor la trataba
    como si nunca hubiera existido relación contractual y liquidaba a SOAT
    pleno, sin avisar siquiera que había un contrato.

    Es el mismo daño que el contrato vencido pero peor, porque ni se nota.

    Se quitan los puntos DENTRO de las siglas (E.P.S. → EPS, S.A. → SA) y se
    normaliza la puntuación de separación a espacios. No se toca nada más: los
    nombres siguen comparándose por palabra completa, que es lo que impide
    darle a una glosa el contrato de otra entidad.
    """
    t = (texto or "").strip().upper()
    t = t.translate(str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN"))
    # E.P.S. → EPS  ·  S.A.S → SAS  (punto entre dos letras sueltas)
    t = re.sub(r"(?<=\b[A-Z])\.(?=[A-Z]\b|[A-Z]\.)", "", t)
    # Lo que queda de puntuación separa palabras, no las pega.
    t = re.sub(r"[.,;:/\\|]+", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def contratos_de(pagador: str) -> list[Contrato]:
    """Todos los contratos de un pagador, sin filtrar por fecha.

    El match es por nombre canónico o por alias, y tolera que el pagador venga
    escrito como lo escribe la EPS —"SEGUROS AURORA / ARL", "DSE EJERCITO"—.
    """
    p = _normalizar(pagador)
    if not p:
        return []
    palabras = set(p.split())

    # 31-08-2026 — LA ASEGURADORA SOAT NO ES EL MAGISTERIO.
    #
    # «LA PREVISORA» es alias de FOMAG en esta malla, y con razón: La Previsora
    # administra el Fondo del Magisterio. Pero LA MISMA COMPAÑÍA es también una
    # aseguradora SOAT, y ahí es otro pagador y otro régimen.
    #
    # Resultado: «LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB» recibía el
    # contrato de FOMAG (factor 0.85, SOAT −15 %) cuando una reclamación SOAT
    # se liquida a tarifa plena. Es darle a una glosa el contrato de otra
    # entidad — justo lo que los guardianes de abajo existen para impedir— y
    # pega donde más duele: en el export real de la base, ese pagador es el que
    # más glosas tiene.
    #
    # La regla es de régimen, no de nombre propio: si el pagador se identifica
    # a sí mismo como SOAT, ningún alias puede llevarlo a un contrato que no
    # sea de SOAT. Vale para cualquier aseguradora, no solo para esta.
    _es_soat = bool(re.search(r"(?<![A-Z0-9])SOAT(?![A-Z0-9])", p))

    def _como_palabra(aguja: str, pajar: str) -> bool:
        """`aguja` dentro de `pajar`, pero como palabra completa.

        Sin esto, "AURORA" encontraba el contrato ARL dentro de "CLINICA
        LAURORA IPS", y "SA" lo encontraba dentro de "FAMISANAR" y
        "DISPENSARIO". Son dos formas de darle a una glosa el contrato de
        otra entidad.
        """
        return bool(re.search(rf"(?<![A-Z0-9]){re.escape(aguja)}(?![A-Z0-9])", pajar))

    def _encaja(nombre: str) -> bool:
        n = _normalizar(nombre)
        if not n:
            return False
        # Un pagador SOAT no puede caer en un contrato que no lo sea. El
        # nombre canónico exacto sí manda: si alguien se llama literalmente
        # así, es ese.
        if _es_soat and n != p and not re.search(r"(?<![A-Z0-9])SOAT(?![A-Z0-9])", n):
            return False
        if n == p:
            return True
        # Una consulta de menos de 4 caracteres no alcanza para identificar a
        # nadie: "EPS", "SA", "IPS" están dentro de media docena de nombres.
        if len(p) >= 4 and _como_palabra(p, n):
            return True
        if _como_palabra(n, p):
            return True
        # Por PALABRAS, no solo por subcadena: la EPS escribe "DIRECCIÓN DE
        # SANIDAD POLICÍA NACIONAL - SERVICIO ONCOLOGÍA" y "POLICIA NACIONAL
        # ONCOLOGIA" no aparece ahí de corrido, aunque sea exactamente ese
        # contrato. Sin esto, esa glosa caía en el contrato general —otro
        # objeto y otro presupuesto—.
        return all(t in palabras for t in n.split())

    encontrados = [c for c in MALLA if _encaja(c.pagador) or any(_encaja(a) for a in c.alias)]

    # El orden importa y no es "el nombre más largo primero". La Policía tiene
    # DOS contratos: uno de oncología y otro de mediana y alta complejidad.
    # Ordenar por longitud hacía que "POLICIA NACIONAL" devolviera siempre el
    # de oncología —el nombre más largo—, que cubre otro objeto y otro
    # presupuesto. Gana el que coincide EXACTO; entre parciales, el que
    # menos palabras agrega a lo que se preguntó.
    def _puntaje(c: Contrato) -> tuple[int, int, int]:
        nombre = _normalizar(c.pagador)
        if nombre == p:
            return (0, 0, 0)
        palabras_consulta = set(p.split())
        sobran = len([t for t in nombre.split() if t not in palabras_consulta])
        # Y entre dos que no sobran nada, gana el que reconoce MÁS palabras de
        # lo que se preguntó: "DIRECCION DE SANIDAD POLICIA NACIONAL -
        # SERVICIO ONCOLOGIA" tiene que caer en el contrato de oncología, no
        # en el general, aunque los dos encajen sin sobrar.
        reconoce = len([t for t in nombre.split() if t in palabras_consulta])
        return (1, sobran, -reconoce)

    encontrados.sort(key=_puntaje)
    return encontrados


def vigente(pagador: str, dia: date) -> Contrato | None:
    """El contrato que regía ese día. None si ninguno lo cubría.

    Devolver None es una respuesta útil, no un fallo: significa que ese día no
    había marco contractual, y eso cambia por completo la defensa de la glosa.
    """
    candidatos = [c for c in contratos_de(pagador) if c.vigente_en(dia)]
    if not candidatos:
        return None

    # `contratos_de` ya los devolvió del más específico al más general, y ese
    # orden NO se puede perder: la Policía tiene un contrato de oncología y
    # otro general, y ordenar por fecha hacía ganar al de oncología —empezó
    # después— para cualquier glosa de la Policía. Otro objeto, otro
    # presupuesto, y el dictamen citando el contrato equivocado.
    #
    # La fecha solo desempata entre contratos del MISMO pagador: ahí sí manda
    # el que empezó después, porque es el que renovó o modificó al anterior
    # (el PPL y su otrosí, COOSALUD subsidiado y contributivo).
    mas_especifico = candidatos[0].pagador
    del_mismo = [c for c in candidatos if c.pagador == mas_especifico]
    del_mismo.sort(key=lambda c: c.desde, reverse=True)
    return del_mismo[0]


def estado_vigencia(hoy: date, dias_aviso: int = DIAS_AVISO_VENCIMIENTO) -> dict[str, Any]:
    """Qué está vencido, qué se acaba pronto y qué sigue vigente.

    Facturar contra un contrato vencido es una glosa segura, y renegociar toma
    semanas: el aviso tiene que llegar antes, no el día que se acaba.
    """
    vencidos, por_vencer, vigentes, indeterminados = [], [], [], []
    for c in MALLA:
        dias = c.dias_para_vencer(hoy)
        if dias is None:
            indeterminados.append(c)
        elif dias < 0:
            vencidos.append((c, dias))
        elif dias <= dias_aviso:
            por_vencer.append((c, dias))
        else:
            vigentes.append(c)
    vencidos.sort(key=lambda x: x[1])
    por_vencer.sort(key=lambda x: x[1])
    return {
        "fecha_malla": FECHA_MALLA.isoformat(),
        "evaluado_en": hoy.isoformat(),
        "dias_aviso": dias_aviso,
        "vencidos": [{**c.como_dict(), "dias": d} for c, d in vencidos],
        "por_vencer": [{**c.como_dict(), "dias": d} for c, d in por_vencer],
        "vigentes": [c.como_dict() for c in vigentes],
        "indeterminados": [c.como_dict() for c in indeterminados],
        "total": len(MALLA),
    }


def pagadores() -> list[str]:
    return sorted({c.pagador for c in MALLA})
