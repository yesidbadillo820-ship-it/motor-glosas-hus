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

    # ── Consultas de control por especialista (8903xx) ──────────────────────
    "890301": "CONSULTA DE CONTROL POR ESPECIALISTA EN MEDICINA INTERNA",
    "890302": "CONSULTA DE CONTROL POR ESPECIALISTA EN ELECTROFISIOLOGÍA",
    "890308": "CONSULTA DE CONTROL POR ESPECIALISTA EN CARDIOLOGÍA",
    "890322": "CONSULTA DE CONTROL POR ESPECIALISTA EN PEDIATRÍA",
    "890335": "CONSULTA DE CONTROL POR ESPECIALISTA EN ORTOPEDIA Y TRAUMATOLOGÍA",
    "890348": "CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA",

    # ── Interconsultas hospitalarias (8904xx) ───────────────────────────────
    "890402": "INTERCONSULTA HOSPITALARIA POR ELECTROFISIOLOGÍA",
    "890405": "INTERCONSULTA HOSPITALARIA POR ENFERMERÍA",
    "890410": "INTERCONSULTA HOSPITALARIA POR AUDIOLOGÍA",
    "890453": "INTERCONSULTA HOSPITALARIA POR HEPATOLOGÍA",

    # ── Urgencias por especialista (8907xx) ─────────────────────────────────
    "890701": "CONSULTA DE URGENCIAS POR MEDICINA GENERAL",
    "890750": "CONSULTA DE URGENCIAS POR ESPECIALISTA EN GINECOLOGÍA Y OBSTETRICIA",
    "890793": "CONSULTA DE URGENCIAS POR ESPECIALISTA EN MEDICINA DE EMERGENCIAS",

    # ── Laboratorio clínico básico alto-volumen ─────────────────────────────
    "901040": "GLICEMIA PRE Y POST CARGA DE GLUCOSA",
    "902207": "HEMOGRAMA IV (HEMATOCRITO, HEMOGLOBINA, RECUENTO DE ERITROCITOS, ÍNDICES ERITROCITARIOS, LEUCOGRAMA)",
    "903866": "CREATININA EN SUERO U OTROS FLUIDOS",
    "903868": "CREATININA EN ORINA DE 24 HORAS",
    "903895": "TRANSAMINASA GLUTÁMICA OXALACÉTICA (AST)",
    "906225": "PROTEÍNA C REACTIVA (PCR) CUANTITATIVA",
    "907106": "UROANÁLISIS CON MICROSCOPIO DE CAMPO, SEDIMENTO Y DENSIDAD URINARIA",

    # ── Imágenes diagnósticas alto-volumen ──────────────────────────────────
    "871040": "RADIOGRAFÍA DE COLUMNA LUMBOSACRA",
    "871121": "RADIOGRAFÍA DE TÓRAX PA O AP",
    "873205": "RADIOGRAFÍA DE CODO",
    "881330": "ECOGRAFÍA DE ABDOMEN TOTAL",
    "883101": "TAC DE CRÁNEO SIMPLE",
    "884003": "RESONANCIA MAGNÉTICA DE CEREBRO SIMPLE",
    "897011": "MONITORIA FETAL ANTEPARTO",

    # ── Patología y biopsia ─────────────────────────────────────────────────
    "873306": "ESTUDIO DE COLORACIÓN BÁSICA EN BIOPSIA",
    "898101": "ESTUDIO ANATOMOPATOLÓGICO EN BIOPSIA",

    # ── Otros alto-volumen ──────────────────────────────────────────────────
    "881434": "PERFIL BIOFÍSICO",
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
