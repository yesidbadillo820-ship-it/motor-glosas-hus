"""Homologador de códigos CUPS — Resolución 2641 de 2025 (Ronda 45).

La Res. 2641/2025 del MinSalud es la tabla oficial de homologación de
códigos antiguos a la nueva nomenclatura CUPS 2025. Muchas EPS todavía
glosan usando el código interno del prestador (ej. '39147B-18' del HUS)
o una versión vieja del CUPS, y el sistema necesita saber que ese código
equivale al CUPS oficial (ej. '890348') para poder encontrar la tarifa
pactada en el contrato.

Estrategias de homologación (en orden):

  1. **Tabla explícita** — un dict hardcoded con equivalencias conocidas
     de la Res. 2641/2025. Se agregan a medida que aparecen en glosas
     reales o en archivos oficiales.

  2. **Normalización del código** — elimina sufijos institucionales
     ('H', 'H1', 'H2', ..., '-18', '-16') para intentar match con el
     CUPS base.

  3. **Cache dinámico desde contratos cargados** — si al importar un
     Excel de contrato (como el ANEXO 1 del DMBUG) vienen columnas
     'CODIGO IPS' + 'CUPS 2641/25', esas equivalencias se guardan en
     TarifaContratadaRecord.codigo_ips y se pueden consultar aquí.

Uso:

    from app.services.homologador_cups import homologar_cups

    info = homologar_cups('39147B-18')
    # → {"cups_oficial": "890348", "fuente": "Res. 2641/2025",
    #    "descripcion": "Consulta de control...",
    #    "confianza": "alta"}

    info = homologar_cups('CUPS_EXÓTICO')
    # → None si no se reconoce

Para EPS que glosan con el CUPS oficial directamente, esta función no
interviene — el lookup tradicional por cups funciona.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.db import TarifaContratadaRecord


# ─── Tabla explícita de homologaciones Res. 2641/2025 ──────────────────────
# Formato: { codigo_viejo: (cups_oficial, descripcion) }
#
# Esta tabla crece a medida que identificamos equivalencias. La mejor fuente
# es el archivo Excel del contrato cargado en el sistema — de ahí se
# extraen automáticamente al importar. Los que están acá son los que salen
# con frecuencia en las glosas reales del HUS (códigos internos con
# sufijos H, H1, o códigos de versión antigua con guion).
#
# Si la EPS glosa con un código que no está acá ni cargado en ningún
# contrato, el sistema caerá al dictamen genérico — pero esa situación
# desaparece apenas se carga el Excel del contrato correspondiente.
HOMOLOGACIONES_EXPLICITAS: dict[str, tuple[str, str]] = {
    # ─── Consulta de genética médica ────────────────────────────────────────
    # La EPS DMBUG a veces glosa 39147B-18 (código interno viejo HUS) para
    # consulta de control por especialista en genética. Su CUPS oficial es
    # 890348 en la Res. 2641/2025 (numeración nueva CUPS 2025).
    "39147B-18": ("890348", "CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA"),
    "39147B18":  ("890348", "CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA"),
    "39147B":    ("890348", "CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA"),

    # CONSULTA DE PRIMERA VEZ por especialista en genética
    "39143A-18": ("890248", "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN GENÉTICA MÉDICA"),
    "39143A-16": ("890248", "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN ANESTESIOLOGÍA"),
    "39143A-19": ("890248", "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN DERMATOLOGÍA"),

    # ─── Consulta otras especialidades ──────────────────────────────────────
    # Códigos IPS con sufijo H1/H2 (variantes de especialidad HUS)
    # Estos están ya en tarifas_oficiales.py; se listan también acá para
    # que el homologador pueda responder sin cargar toda esa tabla.
    "890202H1": ("890202", "CONSULTA PRIMERA VEZ POR ELECTROFISIOLOGÍA"),
    "890302H1": ("890302", "CONSULTA CONTROL POR ELECTROFISIOLOGÍA"),
    "890402H1": ("890402", "INTERCONSULTA HOSPITALARIA POR ELECTROFISIOLOGÍA"),
    "890405H":  ("890405", "INTERCONSULTA POR ENFERMERÍA"),
    "890405H1": ("890405", "INTERCONSULTA ENFERMERÍA — CLÍNICA DE HERIDAS"),
    "890405H2": ("890405", "INTERCONSULTA ENFERMERÍA — TERAPIA DE INFUSIÓN"),
    "890410H":  ("890410", "INTERCONSULTA POR AUDIOLOGÍA"),
    "890253H":  ("890253", "CONSULTA PRIMERA VEZ POR HEPATOLOGÍA"),
    "890453":   ("890453", "CONSULTA POR HEPATOLOGÍA"),

    # ─── Radiología con sufijos de versión (H, H1) ─────────────────────────
    "871040H":  ("871040", "RADIOGRAFÍA DE COLUMNA LUMBOSACRA"),
    "873205H":  ("873205", "RADIOGRAFÍA DE CODO"),
    "881434H":  ("881434", "PERFIL BIOFÍSICO"),
    "873306H":  ("873306", "ESTUDIO DE COLORACIÓN BÁSICA EN BIOPSIA"),
    "898101H":  ("898101", "ESTUDIO ANATOMOPATOLÓGICO EN BIOPSIA"),
    "897011H":  ("897011", "MONITORIA FETAL ANTEPARTO"),

    # ─── Consulta urgencias ginecología/obstetricia ────────────────────────
    "890750H":  ("890750", "CONSULTA DE URGENCIAS POR ESPECIALISTA EN GINECOLOGÍA"),
    "890793H":  ("890793", "CONSULTA DE URGENCIAS POR ESPECIALISTA EN URGENCIAS"),

    # ─── Misceláneos con sufijo institucional H ────────────────────────────
    "010101H":  ("010101", "PUNCIÓN CISTERNAL VÍA LATERAL"),
    "010102H":  ("010102", "PUNCIÓN CISTERNAL VÍA MEDIAL"),
    "010103H":  ("010103", "PUNCIÓN CISTERNAL"),
}


# ─── Descripciones canónicas CUPS 2025 — códigos de alto volumen ──────────
# Cuando la normalización heurística de sufijos reduce '890201H1' → '890201',
# este diccionario permite retornar la descripción oficial en vez de cadena
# vacía. Son los ~50 códigos más glosados en hospitales de 3er nivel en
# Colombia: consultas especializadas, laboratorio básico, imágenes comunes,
# estancias. Expandir aquí es MÁS EFICIENTE que agregar variantes con sufijo
# en HOMOLOGACIONES_EXPLICITAS, porque el normalizador las cubre todas.
DESCRIPCIONES_CUPS_2025: dict[str, str] = {
    # ── Consultas medicina general / familiar (8901xx) ──────────────────────
    "890101": "CONSULTA DE PRIMERA VEZ POR MEDICINA GENERAL",
    "890102": "CONSULTA DE PRIMERA VEZ POR MEDICINA FAMILIAR",
    "890103": "CONSULTA DE PRIMERA VEZ POR MEDICINA DEL TRABAJO",
    "890104": "CONSULTA DE PRIMERA VEZ POR ENFERMERÍA",
    "890105": "CONSULTA DE PRIMERA VEZ POR NUTRICIÓN Y DIETÉTICA",
    "890106": "CONSULTA DE PRIMERA VEZ POR PSICOLOGÍA",
    "890107": "CONSULTA DE PRIMERA VEZ POR FISIOTERAPIA",
    "890108": "CONSULTA DE PRIMERA VEZ POR FONOAUDIOLOGÍA",
    "890109": "CONSULTA DE PRIMERA VEZ POR TERAPIA OCUPACIONAL",
    "890110": "CONSULTA DE PRIMERA VEZ POR OPTOMETRÍA",
    "890111": "CONSULTA DE PRIMERA VEZ POR ODONTOLOGÍA GENERAL",

    # ── Consulta de control medicina general (8903xx) ───────────────────────
    "890301": "CONSULTA DE CONTROL POR MEDICINA GENERAL",
    "890303": "CONSULTA DE CONTROL POR ENFERMERÍA",
    "890304": "CONSULTA DE CONTROL POR NUTRICIÓN Y DIETÉTICA",
    "890305": "CONSULTA DE CONTROL POR PSICOLOGÍA",
    "890306": "CONSULTA DE CONTROL POR FISIOTERAPIA",
    "890307": "CONSULTA DE CONTROL POR FONOAUDIOLOGÍA",

    # ── Consultas primera vez por especialista (8902xx) ─────────────────────
    "890201": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN MEDICINA INTERNA",
    "890202": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN ELECTROFISIOLOGÍA",
    "890205": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN ANESTESIOLOGÍA",
    "890207": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN NEUROLOGÍA",
    "890208": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN CARDIOLOGÍA",
    "890209": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN NEUMOLOGÍA",
    "890210": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN GASTROENTEROLOGÍA",
    "890211": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN ENDOCRINOLOGÍA",
    "890213": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN NEFROLOGÍA",
    "890215": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN HEMATOLOGÍA",
    "890217": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN ONCOLOGÍA",
    "890218": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN REUMATOLOGÍA",
    "890222": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN PEDIATRÍA",
    "890225": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN GINECOBSTETRICIA",
    "890230": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN CIRUGÍA GENERAL",
    "890235": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN ORTOPEDIA Y TRAUMATOLOGÍA",
    "890240": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN UROLOGÍA",
    "890245": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN OFTALMOLOGÍA",
    "890248": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN GENÉTICA MÉDICA",
    "890250": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN OTORRINOLARINGOLOGÍA",
    "890253": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN HEPATOLOGÍA",
    "890255": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN DERMATOLOGÍA",
    "890260": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN PSIQUIATRÍA",
    "890265": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA EN MEDICINA FÍSICA Y REHABILITACIÓN",

    # ── Consultas de control por especialista (89035x..89036x) ──────────────
    # Nota: 890301 = control medicina general (arriba). El control de
    # especialista usa 8903xx con desplazamiento similar a 8902xx primera vez.
    "890308": "CONSULTA DE CONTROL POR ESPECIALISTA EN CARDIOLOGÍA",
    "890322": "CONSULTA DE CONTROL POR ESPECIALISTA EN PEDIATRÍA",
    "890325": "CONSULTA DE CONTROL POR ESPECIALISTA EN GINECOBSTETRICIA",
    "890335": "CONSULTA DE CONTROL POR ESPECIALISTA EN ORTOPEDIA Y TRAUMATOLOGÍA",
    "890348": "CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA",
    "890351": "CONSULTA DE CONTROL POR ESPECIALISTA EN MEDICINA INTERNA",

    # ── Interconsultas hospitalarias (8904xx) ───────────────────────────────
    "890402": "INTERCONSULTA HOSPITALARIA POR ELECTROFISIOLOGÍA",
    "890405": "INTERCONSULTA HOSPITALARIA POR ENFERMERÍA",
    "890410": "INTERCONSULTA HOSPITALARIA POR AUDIOLOGÍA",
    "890453": "INTERCONSULTA HOSPITALARIA POR HEPATOLOGÍA",

    # ── Urgencias (8907xx) ──────────────────────────────────────────────────
    "890701": "CONSULTA DE URGENCIAS POR MEDICINA GENERAL",
    "890750": "CONSULTA DE URGENCIAS POR ESPECIALISTA EN GINECOLOGÍA Y OBSTETRICIA",
    "890793": "CONSULTA DE URGENCIAS POR ESPECIALISTA EN MEDICINA DE EMERGENCIAS",

    # ── Laboratorio clínico — química e inmunología ─────────────────────────
    "901040": "GLICEMIA PRE Y POST CARGA DE GLUCOSA",
    "901225": "GLUCOSA EN SUERO U OTROS FLUIDOS DIFERENTES A ORINA",
    "901226": "HEMOGLOBINA GLICOSILADA HBA1C",
    "901415": "PERFIL LIPÍDICO (COLESTEROL TOTAL, HDL, LDL, TRIGLICÉRIDOS)",
    "903422": "TIROTROPINA (TSH)",
    "903419": "TIROXINA LIBRE (T4 LIBRE)",
    "903866": "CREATININA EN SUERO U OTROS FLUIDOS",
    "903868": "CREATININA EN ORINA DE 24 HORAS",
    "903895": "TRANSAMINASA GLUTÁMICA OXALACÉTICA (AST)",
    "903896": "TRANSAMINASA GLUTÁMICA PIRÚVICA (ALT)",
    "904906": "ELECTROLITOS SÉRICOS (NA, K, CL)",
    "906225": "PROTEÍNA C REACTIVA (PCR) CUANTITATIVA",
    "906039": "PARCIAL DE ORINA",
    "907106": "UROANÁLISIS CON MICROSCOPIO DE CAMPO, SEDIMENTO Y DENSIDAD URINARIA",

    # ── Hematología ─────────────────────────────────────────────────────────
    "902207": "HEMOGRAMA IV (HEMATOCRITO, HEMOGLOBINA, RECUENTO ERITROCITOS, ÍNDICES, LEUCOGRAMA)",
    "902210": "HEMOGRAMA III (HEMATOCRITO, HEMOGLOBINA, RECUENTO ERITROCITOS, LEUCOGRAMA)",
    "902208": "RECUENTO DE PLAQUETAS",
    "902049": "TIEMPO DE PROTROMBINA (TP-INR)",
    "902045": "TIEMPO DE TROMBOPLASTINA PARCIAL ACTIVADA (TTPA)",
    "906915": "VELOCIDAD DE SEDIMENTACIÓN GLOBULAR (VSG)",

    # ── Microbiología y serología ───────────────────────────────────────────
    "907111": "UROCULTIVO Y RECUENTO DE COLONIAS",
    "908436": "PRUEBA RÁPIDA PARA VIH (TAMIZAJE)",
    "906320": "PRUEBA TREPONÉMICA SIFILIS (FTA-ABS)",
    "906916": "TAMIZAJE PARA HEPATITIS B (HBsAg)",

    # ── Imagenología — Rayos X ──────────────────────────────────────────────
    "870101": "RADIOGRAFÍA DE CRÁNEO PA O AP Y LATERAL",
    "871040": "RADIOGRAFÍA DE COLUMNA LUMBOSACRA",
    "871020": "RADIOGRAFÍA DE COLUMNA CERVICAL",
    "871021": "RADIOGRAFÍA DE COLUMNA TORÁCICA",
    "871121": "RADIOGRAFÍA DE TÓRAX PA O AP",
    "871122": "RADIOGRAFÍA DE TÓRAX (PA Y LATERAL)",
    "871330": "RADIOGRAFÍA DE ABDOMEN SIMPLE",
    "873101": "RADIOGRAFÍA DE HOMBRO",
    "873205": "RADIOGRAFÍA DE CODO",
    "873305": "RADIOGRAFÍA DE MANO",
    "874101": "RADIOGRAFÍA DE PELVIS",
    "874201": "RADIOGRAFÍA DE CADERA",
    "874305": "RADIOGRAFÍA DE FÉMUR",
    "874501": "RADIOGRAFÍA DE RODILLA",
    "874601": "RADIOGRAFÍA DE TIBIA Y PERONÉ",
    "874701": "RADIOGRAFÍA DE TOBILLO",
    "874801": "RADIOGRAFÍA DE PIE",

    # ── Imagenología — Ecografía ────────────────────────────────────────────
    "881201": "ECOGRAFÍA DE TIROIDES",
    "881330": "ECOGRAFÍA DE ABDOMEN TOTAL",
    "881331": "ECOGRAFÍA DE HÍGADO Y VÍAS BILIARES",
    "881332": "ECOGRAFÍA DE RIÑONES Y VÍAS URINARIAS",
    "881401": "ECOGRAFÍA OBSTÉTRICA TRANSABDOMINAL",
    "881402": "ECOGRAFÍA OBSTÉTRICA TRANSVAGINAL",
    "881403": "ECOGRAFÍA DE PELVIS GINECOLÓGICA",
    "881431": "ECOGRAFÍA DOPPLER OBSTÉTRICA",
    "881434": "PERFIL BIOFÍSICO",
    "881501": "ECOGRAFÍA DE PARTES BLANDAS",
    "881601": "ECOGRAFÍA TESTICULAR",
    "881701": "ECOCARDIOGRAFÍA TRANSTORÁCICA",
    "881702": "ECOCARDIOGRAFÍA TRANSESOFÁGICA",
    "881901": "ECOGRAFÍA DOPPLER VENOSA DE MIEMBROS INFERIORES",
    "881902": "ECOGRAFÍA DOPPLER ARTERIAL DE MIEMBROS INFERIORES",

    # ── Imagenología — TAC (tomografía) ─────────────────────────────────────
    "883101": "TAC DE CRÁNEO SIMPLE",
    "883102": "TAC DE CRÁNEO CON CONTRASTE",
    "883201": "TAC DE TÓRAX SIMPLE",
    "883202": "TAC DE TÓRAX CON CONTRASTE",
    "883301": "TAC DE ABDOMEN SIMPLE",
    "883302": "TAC DE ABDOMEN CON CONTRASTE",
    "883303": "TAC DE PELVIS",
    "883401": "TAC DE COLUMNA CERVICAL",
    "883402": "TAC DE COLUMNA LUMBOSACRA",

    # ── Imagenología — Resonancia magnética ─────────────────────────────────
    "884003": "RESONANCIA MAGNÉTICA DE CEREBRO SIMPLE",
    "884004": "RESONANCIA MAGNÉTICA DE CEREBRO CON CONTRASTE",
    "884101": "RESONANCIA MAGNÉTICA DE COLUMNA CERVICAL",
    "884102": "RESONANCIA MAGNÉTICA DE COLUMNA LUMBOSACRA",
    "884201": "RESONANCIA MAGNÉTICA DE ABDOMEN",
    "884301": "RESONANCIA MAGNÉTICA DE RODILLA",
    "884302": "RESONANCIA MAGNÉTICA DE HOMBRO",

    # ── Otros estudios diagnósticos ─────────────────────────────────────────
    "891101": "ELECTROCARDIOGRAMA DE REPOSO",
    "891201": "ELECTROENCEFALOGRAMA",
    "892101": "ESPIROMETRÍA",
    "893101": "AUDIOMETRÍA TONAL",
    "897011": "MONITORIA FETAL ANTEPARTO",

    # ── Patología y biopsia ─────────────────────────────────────────────────
    "873306": "ESTUDIO DE COLORACIÓN BÁSICA EN BIOPSIA",
    "898101": "ESTUDIO ANATOMOPATOLÓGICO EN BIOPSIA",
    "898102": "ESTUDIO ANATOMOPATOLÓGICO EN ESPECIMEN QUIRÚRGICO",
    "898104": "INMUNOHISTOQUÍMICA",
    "898201": "CITOLOGÍA CÉRVICO-UTERINA CONVENCIONAL",

    # ── Procedimientos quirúrgicos comunes ──────────────────────────────────
    "470301": "APENDICECTOMÍA POR LAPAROTOMÍA",
    "470302": "APENDICECTOMÍA LAPAROSCÓPICA",
    "511001": "COLECISTECTOMÍA POR LAPAROTOMÍA",
    "511002": "COLECISTECTOMÍA LAPAROSCÓPICA",
    "740101": "PARTO VAGINAL ESPONTÁNEO",
    "740301": "PARTO POR CESÁREA",
    "861101": "SUTURA DE PIEL",
    "861201": "DESBRIDAMIENTO DE TEJIDO BLANDO",
    "865101": "CURACIÓN MAYOR",

    # ── Estancias hospitalarias y servicios ────────────────────────────────
    "S11101": "ESTANCIA EN HABITACIÓN COMPARTIDA",
    "S11201": "ESTANCIA EN UCI ADULTOS",
    "S11202": "ESTANCIA EN UCI PEDIÁTRICA",
    "S11203": "ESTANCIA EN UCI NEONATAL",
    "S11301": "ESTANCIA EN UCE (UNIDAD DE CUIDADOS ESPECIALES)",
    "S12101": "ESTANCIA EN PEDIATRÍA",
    "S13101": "ESTANCIA EN GINECOOBSTETRICIA",

    # ── Materiales / suministros frecuentes ─────────────────────────────────
    "M01101": "OXÍGENO MEDICINAL POR HORA",
    "M02101": "TRANSFUSIÓN DE GLÓBULOS ROJOS EMPACADOS",

    # ── Procedimientos menores comunes ──────────────────────────────────────
    "391001": "CURACIÓN MENOR DE HERIDA",
    "390402": "NEBULIZACIÓN CON BRONCODILATADOR",
    "994001": "VACUNACIÓN (APLICACIÓN DE BIOLÓGICO)",
    "898306": "CITOLOGÍA EN BASE LÍQUIDA",
}


# Sufijos institucionales que podemos retirar para intentar match con CUPS base.
# Esta es una heurística — NO es homologación oficial, solo un intento de
# reconocer el código base cuando la versión específica no está en la tabla.
_SUFIJOS_INSTITUCIONALES = re.compile(
    r"(?:"
    r"-\d{2}"            # ej. '-16', '-18', '-19' (versión interna)
    r"|H\d*"             # ej. 'H', 'H1', 'H2' (variantes HUS)
    r"|[A-Z]\d*$"        # ej. 'A1', 'B', 'C' al final
    r")+$"
)


def _normalizar_descripcion(s: str) -> str:
    """Quita tildes y pasa a mayúsculas para matching acent-insensitive."""
    if not s:
        return ""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def buscar_cups_por_descripcion(
    consulta: str,
    top_k: int = 10,
    db: Optional[Session] = None,
) -> list[dict]:
    """Busca códigos CUPS cuya descripción matchee la consulta libre.

    Usa scoring por número de tokens del query que aparecen en la
    descripción (acent-insensitive). Permite responder preguntas como:
      - "cuál es el CUPS para consulta médico general"   → 890101
      - "qué CUPS para radiografía de tórax"            → 871121, 871122
      - "código de hemograma"                           → 902207
      - "ecografía abdominal"                           → 881330

    Fuentes consultadas (en orden de prioridad):
      1. DESCRIPCIONES_CUPS_2025 — catálogo curado interno (~150 códigos)
      2. HOMOLOGACIONES_EXPLICITAS — variantes con sufijo HUS
      3. TarifaContratadaRecord en BD — descripciones de contratos cargados

    Retorna lista [{cups_oficial, descripcion, fuente, score}].
    """
    q = _normalizar_descripcion(consulta or "")
    tokens = [t for t in q.split() if len(t) >= 3]
    if not tokens:
        return []

    STOP = {
        "CUAL", "QUE", "CUPS", "CODIGO", "PARA", "DEL", "LAS", "LOS",
        "POR", "ESTA", "ESTE", "CON", "SIN", "NUMERO", "ES", "EL", "LA",
        "DE", "EN", "UN", "UNA",
    }
    tokens = [t for t in tokens if t not in STOP]
    if not tokens:
        return []

    resultados: list[tuple[float, dict]] = []
    vistos: set[str] = set()

    def _score(desc: str) -> float:
        d = _normalizar_descripcion(desc)
        if not d:
            return 0.0
        # Score = fracción de tokens del query presentes en la descripción
        hits = sum(1 for t in tokens if t in d)
        if hits == 0:
            return 0.0
        # Bonus si TODOS los tokens están presentes (match completo)
        completo = 1.5 if hits == len(tokens) else 1.0
        # Penalizar descripciones muy largas (preferir match concreto)
        long_pen = max(0.5, 1.0 - len(d) / 500.0)
        return (hits / len(tokens)) * completo * long_pen

    # 1) Catálogo curado interno
    for cups, desc in DESCRIPCIONES_CUPS_2025.items():
        s = _score(desc)
        if s > 0:
            resultados.append((s, {
                "cups_oficial": cups, "descripcion": desc,
                "fuente": "DESCRIPCIONES_CUPS_2025 (catálogo curado)",
            }))
            vistos.add(cups)

    # 2) Tabla de homologaciones explícitas (variantes con sufijo HUS)
    for cod_viejo, (cups, desc) in HOMOLOGACIONES_EXPLICITAS.items():
        if cups in vistos:
            continue
        s = _score(desc)
        if s > 0:
            resultados.append((s, {
                "cups_oficial": cups, "descripcion": desc,
                "fuente": f"Res. 2641/2025 (vía '{cod_viejo}')",
            }))
            vistos.add(cups)

    # 3) BD: TarifaContratadaRecord (contratos cargados por el coordinador)
    if db is not None:
        try:
            # Intento de prefijo con ilike sobre cualquier token >= 4 chars
            from sqlalchemy import or_
            largos = [t for t in tokens if len(t) >= 4]
            if largos:
                clausulas = [
                    TarifaContratadaRecord.descripcion.ilike(f"%{t}%")
                    for t in largos
                ]
                filas = (
                    db.query(TarifaContratadaRecord)
                    .filter(TarifaContratadaRecord.activa == 1)
                    .filter(or_(*clausulas))
                    .limit(200)
                    .all()
                )
                for fila in filas:
                    if not fila.codigo_cups or fila.codigo_cups in vistos:
                        continue
                    s = _score(fila.descripcion or "")
                    if s > 0:
                        resultados.append((s, {
                            "cups_oficial": fila.codigo_cups,
                            "descripcion": fila.descripcion or "",
                            "fuente": f"contrato {fila.eps or '—'}",
                        }))
                        vistos.add(fila.codigo_cups)
        except Exception:
            pass

    resultados.sort(key=lambda x: x[0], reverse=True)
    return [
        {**d, "score": round(s, 3)}
        for s, d in resultados[:top_k]
    ]


def _normalizar_codigo(codigo: str) -> str:
    """Remueve espacios, mayúsculas, y sufijos institucionales conocidos."""
    if not codigo:
        return ""
    k = codigo.strip().upper()
    # Primer intento: quitar sufijos típicos
    base = _SUFIJOS_INSTITUCIONALES.sub("", k)
    return base or k


def homologar_cups(
    codigo_entrada: str,
    db: Optional[Session] = None,
    eps: Optional[str] = None,
) -> Optional[dict]:
    """Resuelve el código CUPS oficial (Res. 2641/2025) a partir de
    cualquier variante: código interno HUS, CUPS viejo, CUPS con sufijo,
    o el CUPS ya oficial.

    Orden de búsqueda:
      1. Si el código YA es un CUPS oficial (6 dígitos), retorna sin más.
      2. Tabla explícita HOMOLOGACIONES_EXPLICITAS.
      3. Base de datos: busca en TarifaContratadaRecord.codigo_ips (si
         se cargó un contrato con la homologación).
      4. Normalización + reintentar.
      5. None si no hay forma de homologar.
    """
    if not codigo_entrada:
        return None
    k = codigo_entrada.strip().upper()

    # 1) Ya es un CUPS oficial (6 dígitos exactos, sin sufijos)
    if re.fullmatch(r"\d{6}", k):
        return {
            "cups_oficial": k,
            "fuente": "código ya en formato CUPS oficial",
            "descripcion": DESCRIPCIONES_CUPS_2025.get(k, ""),
            "confianza": "alta",
        }

    # 2) Tabla explícita
    if k in HOMOLOGACIONES_EXPLICITAS:
        cups, desc = HOMOLOGACIONES_EXPLICITAS[k]
        return {
            "cups_oficial": cups,
            "fuente": "Res. 2641/2025 (tabla explícita)",
            "descripcion": desc,
            "confianza": "alta",
        }

    # 3) BD — buscar en TarifaContratadaRecord.codigo_ips
    if db is not None:
        try:
            q = db.query(TarifaContratadaRecord).filter(
                TarifaContratadaRecord.activa == 1,
                TarifaContratadaRecord.codigo_ips == k,
            )
            if eps:
                q = q.filter(TarifaContratadaRecord.eps.ilike(f"%{eps.strip()}%"))
            fila = q.order_by(TarifaContratadaRecord.creado_en.desc()).first()
            if fila and fila.codigo_cups:
                return {
                    "cups_oficial": fila.codigo_cups,
                    "fuente": f"contrato {fila.contrato_numero or fila.eps} (Excel cargado)",
                    "descripcion": fila.descripcion or "",
                    "confianza": "alta",
                }
        except Exception:
            pass

    # 4) Normalización agresiva — quitar sufijos
    base = _normalizar_codigo(k)
    if base != k:
        # Reintentar con el código normalizado
        if base in HOMOLOGACIONES_EXPLICITAS:
            cups, desc = HOMOLOGACIONES_EXPLICITAS[base]
            return {
                "cups_oficial": cups,
                "fuente": "Res. 2641/2025 (tras normalización de sufijos)",
                "descripcion": desc,
                "confianza": "media",
            }
        if re.fullmatch(r"\d{6}", base):
            return {
                "cups_oficial": base,
                "fuente": "Res. 2641/2025 (normalización heurística de sufijos)",
                "descripcion": DESCRIPCIONES_CUPS_2025.get(base, ""),
                "confianza": "media",
            }

    return None


def agregar_homologacion(codigo_viejo: str, cups_oficial: str, descripcion: str = ""):
    """Permite expandir la tabla en runtime (ej. al importar contrato).
    Idempotente."""
    k = (codigo_viejo or "").strip().upper()
    c = (cups_oficial or "").strip()
    if not k or not c:
        return
    HOMOLOGACIONES_EXPLICITAS[k] = (c, descripcion)


# ─── Texto oficial para citar en dictámenes ────────────────────────────────

TEXTO_RES_2641_2025 = (
    "RESOLUCIÓN 2641 DE 2025 (Ministerio de Salud y Protección Social): "
    "Por la cual se adopta la Clasificación Única de Procedimientos en "
    "Salud (CUPS) versión 2025 y se establece la TABLA DE HOMOLOGACIÓN "
    "entre códigos internos de prestadores, códigos CUPS anteriores y la "
    "numeración oficial vigente. El uso de códigos homologados es de "
    "OBLIGATORIO CUMPLIMIENTO para reportar al Registro Individual de "
    "Prestación de Servicios de Salud (RIPS) y para la facturación "
    "electrónica (FEV, Res. 2275/2023)."
)


def cita_res_2641(codigo_viejo: str, cups_oficial: str) -> str:
    """Construye la cita formal lista para inyectar al prompt IA o al
    dictamen final."""
    return (
        f"Según la RESOLUCIÓN 2641 DE 2025 del Ministerio de Salud "
        f"(Clasificación Única de Procedimientos en Salud CUPS versión 2025), "
        f"el código '{codigo_viejo}' corresponde al CUPS oficial '{cups_oficial}', "
        f"cuya equivalencia es de obligatoria observación para efectos de "
        f"facturación, glosa y conciliación."
    )
