"""Los conceptos de nota crédito del HUS, como dato.

DE DÓNDE SALE. Del archivo `CONCEPTO_DE_NOTAS_NUEVA_DINAMICA.xlsx` que
mantiene el área contable — «conceptos de notas a manejar (cuentas
definitivas), nueva dinámica». Es la fuente de verdad sobre qué cuenta
contable y qué concepto de nota le corresponde a cada glosa.

PARA QUÉ SIRVE. Cuando en una mesa de conciliación se acepta una glosa, el
hospital tiene que emitir una nota crédito, y esa nota necesita cuenta y
concepto. El acta trae tres columnas para eso —CENTRO DE COSTO, CUENTA
CONTABLE y CONCEPTO NOTA CRÉDITO— que hasta ahora salían en «-» y se
llenaban a mano después.

CÓMO SE BUSCA. Por tres cosas:

  · **el tipo de nota** — GLOSA (se aceptó la objeción), MVC (mayor valor
    cobrado) o REFACTURACION;
  · **la vía** — INICIAL o **ACTAS**. Una conciliación es SIEMPRE por acta,
    así que el concepto es el de la columna de actas, no el de glosa
    inicial. No es el mismo número: UCI adultos es 004 por glosa inicial y
    **020** por acta;
  · **el centro de costo**, que sale del DGH (`conceptos_glosa.centro_costo`).

LO QUE NO SE ADIVINA. El catálogo tiene 42 centros de costo y el DGH maneja
más: `734005 - LABORATORIO - INMUNOLOGIA`, por ejemplo, no está —el catálogo
solo trae `734001 - LABORATORIOS`—. Acercarlo al más parecido sería inventar
un asiento contable, y eso lo corrige contabilidad meses después. Cuando el
centro no está, se devuelve None y quien arma la nota lo resuelve.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

# Los tres tipos de nota que dependen del centro de costo.
TIPO_GLOSA = "GLOSA"
TIPO_MVC = "MVC"
TIPO_REFACTURACION = "REFACTURACION"

# Las dos vías. En conciliación SIEMPRE es ACTAS.
VIA_INICIAL = "INICIAL"
VIA_ACTAS = "ACTAS"

# Cuando la factura es de una vigencia anterior, la cuenta deja de depender
# del servicio: todo va a esta, con su propio concepto. (Filas 58 y 115 del
# archivo de contabilidad; la nota del archivo dice «Cambia cta 58909009».)
CUENTA_VIGENCIA_ANTERIOR = "58909020"
CONCEPTO_VIGENCIA_ANTERIOR = {
    (TIPO_GLOSA, VIA_INICIAL): "133",
    (TIPO_GLOSA, VIA_ACTAS): "134",
    (TIPO_MVC, VIA_INICIAL): "135",
    (TIPO_MVC, VIA_ACTAS): "136",
    (TIPO_REFACTURACION, VIA_INICIAL): "137",
    (TIPO_REFACTURACION, VIA_ACTAS): "138",
}

# Reversión por el Decreto 1095: tampoco depende del centro de costo.
CUENTA_REVERSION = "24079001"
CONCEPTO_REVERSION_DEBITO = "126"
CONCEPTO_REVERSION_CREDITO = "127"


class Concepto(NamedTuple):
    cuenta: str
    concepto: str
    centro_costo: str
    nombre_centro: str


# (tipo, vía, centro de costo) -> (cuenta contable, concepto nuevo de nota)
TABLA: dict[tuple[str, str, str], tuple[str, str]] = {
    ("GLOSA", "ACTAS", "510205"): ("43120801", "017"),
    ("GLOSA", "ACTAS", "510208"): ("43125601", "028"),
    ("GLOSA", "ACTAS", "580109"): ("43126301", "032"),
    ("GLOSA", "ACTAS", "730101"): ("43120801", "017"),
    ("GLOSA", "ACTAS", "730102"): ("43120801", "017"),
    ("GLOSA", "ACTAS", "731101"): ("43121801", "018"),
    ("GLOSA", "ACTAS", "732001"): ("43122701", "019"),
    ("GLOSA", "ACTAS", "732002"): ("43120801", "017"),
    ("GLOSA", "ACTAS", "732003"): ("43120801", "017"),
    ("GLOSA", "ACTAS", "732004"): ("43122701", "019"),
    ("GLOSA", "ACTAS", "732005"): ("43122701", "019"),
    ("GLOSA", "ACTAS", "732006"): ("43122701", "019"),
    ("GLOSA", "ACTAS", "732007"): ("43122701", "019"),
    ("GLOSA", "ACTAS", "732101"): ("43122801", "020"),
    ("GLOSA", "ACTAS", "732102"): ("43122801", "020"),
    ("GLOSA", "ACTAS", "732301"): ("43123001", "108"),
    ("GLOSA", "ACTAS", "732501"): ("43123201", "021"),
    ("GLOSA", "ACTAS", "733001"): ("43123601", "022"),
    ("GLOSA", "ACTAS", "733101"): ("43120801", "017"),
    ("GLOSA", "ACTAS", "734001"): ("43124601", "024"),
    ("GLOSA", "ACTAS", "734101"): ("43124701", "025"),
    ("GLOSA", "ACTAS", "734102"): ("43124701", "025"),
    ("GLOSA", "ACTAS", "734103"): ("43124701", "025"),
    ("GLOSA", "ACTAS", "734104"): ("43124701", "025"),
    ("GLOSA", "ACTAS", "734107"): ("43124701", "025"),
    ("GLOSA", "ACTAS", "734108"): ("43124701", "025"),
    ("GLOSA", "ACTAS", "734201"): ("43124801", "026"),
    ("GLOSA", "ACTAS", "734301"): ("43124901", "027"),
    ("GLOSA", "ACTAS", "734302"): ("43124901", "027"),
    ("GLOSA", "ACTAS", "734303"): ("43124901", "027"),
    ("GLOSA", "ACTAS", "734901"): ("43125601", "028"),
    ("GLOSA", "ACTAS", "734902"): ("43125601", "028"),
    ("GLOSA", "ACTAS", "735101"): ("43125801", "029"),
    ("GLOSA", "ACTAS", "735201"): ("43125901", "030"),
    ("GLOSA", "ACTAS", "735401"): ("43126101", "031"),
    ("GLOSA", "ACTAS", "735602"): ("43126301", "032"),
    ("GLOSA", "ACTAS", "738702"): ("43121801", "018"),
    ("GLOSA", "ACTAS", "738703"): ("43126101", "031"),
    ("GLOSA", "INICIAL", "510205"): ("43120801", "001"),
    ("GLOSA", "INICIAL", "510208"): ("43125601", "012"),
    ("GLOSA", "INICIAL", "580109"): ("43126301", "016"),
    ("GLOSA", "INICIAL", "730101"): ("43120801", "001"),
    ("GLOSA", "INICIAL", "730102"): ("43120801", "001"),
    ("GLOSA", "INICIAL", "731101"): ("43121801", "002"),
    ("GLOSA", "INICIAL", "732001"): ("43122701", "003"),
    ("GLOSA", "INICIAL", "732002"): ("43120801", "001"),
    ("GLOSA", "INICIAL", "732003"): ("43120801", "001"),
    ("GLOSA", "INICIAL", "732004"): ("43122701", "003"),
    ("GLOSA", "INICIAL", "732005"): ("43122701", "003"),
    ("GLOSA", "INICIAL", "732006"): ("43122701", "003"),
    ("GLOSA", "INICIAL", "732007"): ("43122701", "003"),
    ("GLOSA", "INICIAL", "732101"): ("43122801", "004"),
    ("GLOSA", "INICIAL", "732102"): ("43122801", "004"),
    ("GLOSA", "INICIAL", "732202"): ("43122901", "139"),
    ("GLOSA", "INICIAL", "732301"): ("43123001", "107"),
    ("GLOSA", "INICIAL", "732501"): ("43123201", "005"),
    ("GLOSA", "INICIAL", "733001"): ("43123601", "006"),
    ("GLOSA", "INICIAL", "733101"): ("43120801", "001"),
    ("GLOSA", "INICIAL", "734001"): ("43124601", "008"),
    ("GLOSA", "INICIAL", "734101"): ("43124701", "009"),
    ("GLOSA", "INICIAL", "734102"): ("43124701", "009"),
    ("GLOSA", "INICIAL", "734103"): ("43124701", "009"),
    ("GLOSA", "INICIAL", "734104"): ("43124701", "009"),
    ("GLOSA", "INICIAL", "734107"): ("43124701", "009"),
    ("GLOSA", "INICIAL", "734108"): ("43124701", "009"),
    ("GLOSA", "INICIAL", "734201"): ("43124801", "010"),
    ("GLOSA", "INICIAL", "734301"): ("43124901", "011"),
    ("GLOSA", "INICIAL", "734302"): ("43124901", "011"),
    ("GLOSA", "INICIAL", "734303"): ("43124901", "011"),
    ("GLOSA", "INICIAL", "734901"): ("43125601", "012"),
    ("GLOSA", "INICIAL", "734902"): ("43125601", "012"),
    ("GLOSA", "INICIAL", "735101"): ("43125801", "013"),
    ("GLOSA", "INICIAL", "735201"): ("43125901", "014"),
    ("GLOSA", "INICIAL", "735401"): ("43126101", "015"),
    ("GLOSA", "INICIAL", "735602"): ("43126301", "016"),
    ("GLOSA", "INICIAL", "738702"): ("43121801", "002"),
    ("GLOSA", "INICIAL", "738703"): ("43126101", "015"),
    ("MVC", "ACTAS", "510205"): ("43120801", "049"),
    ("MVC", "ACTAS", "510208"): ("43125601", "060"),
    ("MVC", "ACTAS", "580109"): ("43126301", "064"),
    ("MVC", "ACTAS", "730101"): ("43120801", "049"),
    ("MVC", "ACTAS", "730102"): ("43120801", "049"),
    ("MVC", "ACTAS", "731101"): ("43121801", "050"),
    ("MVC", "ACTAS", "732001"): ("43122701", "051"),
    ("MVC", "ACTAS", "732002"): ("43120801", "049"),
    ("MVC", "ACTAS", "732003"): ("43120801", "049"),
    ("MVC", "ACTAS", "732004"): ("43122701", "051"),
    ("MVC", "ACTAS", "732005"): ("43122701", "051"),
    ("MVC", "ACTAS", "732006"): ("43122701", "051"),
    ("MVC", "ACTAS", "732007"): ("43122701", "051"),
    ("MVC", "ACTAS", "732101"): ("43122801", "052"),
    ("MVC", "ACTAS", "732102"): ("43122801", "052"),
    ("MVC", "ACTAS", "732301"): ("43123001", "110"),
    ("MVC", "ACTAS", "732501"): ("43123201", "053"),
    ("MVC", "ACTAS", "733001"): ("43123601", "054"),
    ("MVC", "ACTAS", "733101"): ("43120801", "049"),
    ("MVC", "ACTAS", "734001"): ("43124601", "056"),
    ("MVC", "ACTAS", "734101"): ("43124701", "057"),
    ("MVC", "ACTAS", "734102"): ("43124701", "057"),
    ("MVC", "ACTAS", "734103"): ("43124701", "057"),
    ("MVC", "ACTAS", "734104"): ("43124701", "057"),
    ("MVC", "ACTAS", "734107"): ("43124701", "057"),
    ("MVC", "ACTAS", "734108"): ("43124701", "057"),
    ("MVC", "ACTAS", "734201"): ("43124801", "058"),
    ("MVC", "ACTAS", "734301"): ("43124901", "059"),
    ("MVC", "ACTAS", "734302"): ("43124901", "059"),
    ("MVC", "ACTAS", "734303"): ("43124901", "059"),
    ("MVC", "ACTAS", "734901"): ("43125601", "060"),
    ("MVC", "ACTAS", "734902"): ("43125601", "060"),
    ("MVC", "ACTAS", "735101"): ("43125801", "061"),
    ("MVC", "ACTAS", "735201"): ("43125901", "062"),
    ("MVC", "ACTAS", "735401"): ("43126101", "063"),
    ("MVC", "ACTAS", "735602"): ("43126301", "064"),
    ("MVC", "ACTAS", "738702"): ("43121801", "050"),
    ("MVC", "ACTAS", "738703"): ("43126101", "063"),
    ("MVC", "INICIAL", "510205"): ("43120801", "033"),
    ("MVC", "INICIAL", "510208"): ("43125601", "044"),
    ("MVC", "INICIAL", "580109"): ("43126301", "048"),
    ("MVC", "INICIAL", "730101"): ("43120801", "033"),
    ("MVC", "INICIAL", "730102"): ("43120801", "033"),
    ("MVC", "INICIAL", "731101"): ("43121801", "034"),
    ("MVC", "INICIAL", "732001"): ("43122701", "035"),
    ("MVC", "INICIAL", "732002"): ("43120801", "033"),
    ("MVC", "INICIAL", "732003"): ("43120801", "033"),
    ("MVC", "INICIAL", "732004"): ("43122701", "035"),
    ("MVC", "INICIAL", "732005"): ("43122701", "035"),
    ("MVC", "INICIAL", "732006"): ("43122701", "035"),
    ("MVC", "INICIAL", "732007"): ("43122701", "035"),
    ("MVC", "INICIAL", "732101"): ("43122801", "036"),
    ("MVC", "INICIAL", "732102"): ("43122801", "036"),
    ("MVC", "INICIAL", "732301"): ("43123001", "109"),
    ("MVC", "INICIAL", "732501"): ("43123201", "037"),
    ("MVC", "INICIAL", "733001"): ("43123601", "038"),
    ("MVC", "INICIAL", "733101"): ("43120801", "033"),
    ("MVC", "INICIAL", "734001"): ("43124601", "040"),
    ("MVC", "INICIAL", "734101"): ("43124701", "041"),
    ("MVC", "INICIAL", "734102"): ("43124701", "041"),
    ("MVC", "INICIAL", "734103"): ("43124701", "041"),
    ("MVC", "INICIAL", "734104"): ("43124701", "041"),
    ("MVC", "INICIAL", "734107"): ("43124701", "041"),
    ("MVC", "INICIAL", "734108"): ("43124701", "041"),
    ("MVC", "INICIAL", "734201"): ("43124801", "042"),
    ("MVC", "INICIAL", "734301"): ("43124901", "043"),
    ("MVC", "INICIAL", "734302"): ("43124901", "043"),
    ("MVC", "INICIAL", "734303"): ("43124901", "043"),
    ("MVC", "INICIAL", "734901"): ("43125601", "044"),
    ("MVC", "INICIAL", "734902"): ("43125601", "044"),
    ("MVC", "INICIAL", "735101"): ("43125801", "045"),
    ("MVC", "INICIAL", "735201"): ("43125901", "046"),
    ("MVC", "INICIAL", "735401"): ("43126101", "047"),
    ("MVC", "INICIAL", "735602"): ("43126301", "048"),
    ("MVC", "INICIAL", "738702"): ("43121801", "034"),
    ("MVC", "INICIAL", "738703"): ("43126101", "047"),
    ("REFACTURACION", "ACTAS", "510205"): ("43120801", "081"),
    ("REFACTURACION", "ACTAS", "510208"): ("43125601", "092"),
    ("REFACTURACION", "ACTAS", "510215"): ("48082622", "125"),
    ("REFACTURACION", "ACTAS", "580109"): ("43126301", "096"),
    ("REFACTURACION", "ACTAS", "730101"): ("43120801", "081"),
    ("REFACTURACION", "ACTAS", "730102"): ("43120801", "081"),
    ("REFACTURACION", "ACTAS", "731101"): ("43121801", "082"),
    ("REFACTURACION", "ACTAS", "732001"): ("43122701", "083"),
    ("REFACTURACION", "ACTAS", "732002"): ("43120801", "081"),
    ("REFACTURACION", "ACTAS", "732003"): ("43120801", "081"),
    ("REFACTURACION", "ACTAS", "732004"): ("43122701", "083"),
    ("REFACTURACION", "ACTAS", "732005"): ("43122701", "083"),
    ("REFACTURACION", "ACTAS", "732006"): ("43122701", "083"),
    ("REFACTURACION", "ACTAS", "732007"): ("43122701", "083"),
    ("REFACTURACION", "ACTAS", "732101"): ("43122801", "084"),
    ("REFACTURACION", "ACTAS", "732102"): ("43122801", "084"),
    ("REFACTURACION", "ACTAS", "732301"): ("43123001", "NO CREADO"),
    ("REFACTURACION", "ACTAS", "732501"): ("43123201", "085"),
    ("REFACTURACION", "ACTAS", "733001"): ("43123601", "086"),
    ("REFACTURACION", "ACTAS", "733101"): ("43120801", "081"),
    ("REFACTURACION", "ACTAS", "734001"): ("43124601", "088"),
    ("REFACTURACION", "ACTAS", "734101"): ("43124701", "089"),
    ("REFACTURACION", "ACTAS", "734102"): ("43124701", "089"),
    ("REFACTURACION", "ACTAS", "734103"): ("43124701", "089"),
    ("REFACTURACION", "ACTAS", "734104"): ("43124701", "089"),
    ("REFACTURACION", "ACTAS", "734107"): ("43124701", "089"),
    ("REFACTURACION", "ACTAS", "734108"): ("43124701", "089"),
    ("REFACTURACION", "ACTAS", "734201"): ("43124801", "090"),
    ("REFACTURACION", "ACTAS", "734301"): ("43124901", "091"),
    ("REFACTURACION", "ACTAS", "734302"): ("43124901", "091"),
    ("REFACTURACION", "ACTAS", "734303"): ("43124901", "091"),
    ("REFACTURACION", "ACTAS", "734901"): ("43125601", "092"),
    ("REFACTURACION", "ACTAS", "734902"): ("43125601", "092"),
    ("REFACTURACION", "ACTAS", "735101"): ("43125801", "093"),
    ("REFACTURACION", "ACTAS", "735201"): ("43125901", "094"),
    ("REFACTURACION", "ACTAS", "735401"): ("43126101", "095"),
    ("REFACTURACION", "ACTAS", "735403"): ("43126101", "095"),
    ("REFACTURACION", "ACTAS", "735602"): ("43126301", "096"),
    ("REFACTURACION", "ACTAS", "738702"): ("43121801", "082"),
    ("REFACTURACION", "ACTAS", "738703"): ("43126101", "095"),
    ("REFACTURACION", "INICIAL", "480826"): ("48082608", "101"),
    ("REFACTURACION", "INICIAL", "510205"): ("43120801", "065"),
    ("REFACTURACION", "INICIAL", "510208"): ("43125601", "076"),
    ("REFACTURACION", "INICIAL", "510215"): ("48082622", "124"),
    ("REFACTURACION", "INICIAL", "580109"): ("43126301", "080"),
    ("REFACTURACION", "INICIAL", "730101"): ("43120801", "065"),
    ("REFACTURACION", "INICIAL", "730102"): ("43120801", "065"),
    ("REFACTURACION", "INICIAL", "731101"): ("43121801", "066"),
    ("REFACTURACION", "INICIAL", "732001"): ("43122701", "067"),
    ("REFACTURACION", "INICIAL", "732002"): ("43120801", "065"),
    ("REFACTURACION", "INICIAL", "732003"): ("43120801", "065"),
    ("REFACTURACION", "INICIAL", "732004"): ("43122701", "067"),
    ("REFACTURACION", "INICIAL", "732005"): ("43122701", "067"),
    ("REFACTURACION", "INICIAL", "732006"): ("43122701", "067"),
    ("REFACTURACION", "INICIAL", "732007"): ("43122701", "067"),
    ("REFACTURACION", "INICIAL", "732101"): ("43122801", "068"),
    ("REFACTURACION", "INICIAL", "732102"): ("43122801", "068"),
    ("REFACTURACION", "INICIAL", "732301"): ("43123001", "NO CREADO"),
    ("REFACTURACION", "INICIAL", "732501"): ("43123201", "069"),
    ("REFACTURACION", "INICIAL", "733001"): ("43123601", "070"),
    ("REFACTURACION", "INICIAL", "733101"): ("43120801", "065"),
    ("REFACTURACION", "INICIAL", "734001"): ("43124601", "072"),
    ("REFACTURACION", "INICIAL", "734101"): ("43124701", "073"),
    ("REFACTURACION", "INICIAL", "734102"): ("43124701", "073"),
    ("REFACTURACION", "INICIAL", "734103"): ("43124701", "073"),
    ("REFACTURACION", "INICIAL", "734104"): ("43124701", "073"),
    ("REFACTURACION", "INICIAL", "734107"): ("43124701", "073"),
    ("REFACTURACION", "INICIAL", "734108"): ("43124701", "073"),
    ("REFACTURACION", "INICIAL", "734201"): ("43124801", "074"),
    ("REFACTURACION", "INICIAL", "734301"): ("43124901", "075"),
    ("REFACTURACION", "INICIAL", "734302"): ("43124901", "075"),
    ("REFACTURACION", "INICIAL", "734303"): ("43124901", "075"),
    ("REFACTURACION", "INICIAL", "734901"): ("43125601", "076"),
    ("REFACTURACION", "INICIAL", "734902"): ("43125601", "076"),
    ("REFACTURACION", "INICIAL", "735101"): ("43125801", "077"),
    ("REFACTURACION", "INICIAL", "735201"): ("43125901", "078"),
    ("REFACTURACION", "INICIAL", "735401"): ("43126101", "079"),
    ("REFACTURACION", "INICIAL", "735403"): ("43126101", "079"),
    ("REFACTURACION", "INICIAL", "735602"): ("43126301", "080"),
    ("REFACTURACION", "INICIAL", "738702"): ("43121801", "066"),
    ("REFACTURACION", "INICIAL", "738703"): ("43126101", "079"),
}

# El nombre del centro tal como lo escribe contabilidad, para mostrarlo.
NOMBRE_CENTRO: dict[str, str] = {
    "480826": "08 - 510215 - REFACTURACIONES PROCEDIMIENTO .AÑOS ANT.",
    "510205": "FACTURACION Y LIQUIDACION",
    "510208": "REFACTURACION MEDICAMENTOS MESES ANTERIORES",
    "510215": "REFACTURACION PROCEDIMIENTO AÑOS ANTERIORES -  FACTURAS    VIG ANTERIOR",
    "580109": "LACTARIO",
    "730101": "URGENCIAS PEDIATRICAS",
    "730102": "URGENCIAS ADULTOS",
    "731101": "CONSULTA EXTERNA ESPECIALIZADA",
    "732001": "HOSP GINECOOBSTETRICIA",
    "732002": "HOSP PEDIATRIA",
    "732003": "HOSP MEDICIN INTERNA",
    "732004": "HOSP ORTOPEDIA",
    "732005": "HOSP NEUROCIRUGÍA",
    "732006": "HOSP CIRUGÍA PLÁSTICA",
    "732007": "HOSP CIRUGÍA GENERAL",
    "732101": "UCI ADULTOS",
    "732102": "UCI PEDIATRICA",
    "732202": "HOSPITALIZACION CUIDADOS INTENSIVOS",
    "732301": "RECIEN NACIDO",
    "732501": "QUEMADO",
    "733001": "QUIROFANO",
    "733101": "SALA DE PARTOS",
    "734001": "LABORATORIOS",
    "734101": "RADIOLOGIA",
    "734102": "EOGRFAIAS APOYO DIAGNOSTICO",
    "734103": "ESCANOGRAFIA",
    "734104": "MEDICINA NUCLEAR",
    "734107": "CONTRATO ANGIOGRAFIA",
    "734108": "CONTRATO RESONANCIA",
    "734201": "PATOLOGIA",
    "734301": "ECOGRAFIA GINECOBSTETRA",
    "734302": "GASTROENTEROLOGIA",
    "734303": "CARDIOLOGIA Y HERMODINAMIA",
    "734901": "FISIOTERAPIA Y REHABILITACION",
    "734902": "PROTESIS Y ORTESIS",
    "735101": "BANCO DE SANGRE",
    "735201": "UNIDAD RENAL",
    "735401": "ONCOLOGIA",
    "735403": "RADIOTERAPIA",
    "735602": "CENTRAL DE MEZCLAS",
    "738702": "MADRE CANGURO",
    "738703": "UNIDAD DE ALIVIO AL DOLOR",
}


def codigo_centro(texto) -> str:
    """El código de seis dígitos de un centro de costo.

    El DGH lo entrega pegado al nombre —«734005 - LABORATORIO -
    INMUNOLOGIA»— y el catálogo también. Solo el número identifica.
    """
    import re

    m = re.match(r"\s*(\d{6})", str(texto or ""))
    return m.group(1) if m else ""


def buscar(
    centro_costo,
    tipo: str = TIPO_GLOSA,
    via: str = VIA_ACTAS,
    vigencia_anterior: bool = False,
) -> Optional[Concepto]:
    """Cuenta y concepto de nota para una glosa. None si no se puede saber.

    Ese None es una respuesta, no una falla: significa que ese centro de
    costo no está en el catálogo de contabilidad y que la nota la arma una
    persona. Devolver el concepto «más parecido» sería inventar un asiento.
    """
    centro = codigo_centro(centro_costo)
    if not centro:
        return None

    if vigencia_anterior:
        concepto = CONCEPTO_VIGENCIA_ANTERIOR.get((tipo, via))
        if not concepto:
            return None
        return Concepto(CUENTA_VIGENCIA_ANTERIOR, concepto, centro, NOMBRE_CENTRO.get(centro, ""))

    par = TABLA.get((tipo, via, centro))
    if par is None:
        return None
    return Concepto(par[0], par[1], centro, NOMBRE_CENTRO.get(centro, ""))


def centros_conocidos() -> set[str]:
    """Los centros de costo que el catálogo sí cubre."""
    return {centro for _, _, centro in TABLA}
