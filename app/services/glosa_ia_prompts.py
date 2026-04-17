"""
glosa_ia_prompts.py  —  Motor de Glosas HUS v6.0
=======================================================
Prompts especializados, contratos reales y 4 variantes de respuesta
por concepto (FA · SO · CO · CL · TA) para la ESE HUS.

CONTRATOS VIGENTES INDEXADOS
─────────────────────────────
EPS / PAGADOR              N° CONTRATO               TARIFA BASE
─────────────────────────────────────────────────────────────────
NUEVA EPS                  Acta 1388/2024 + 2025      SOAT – 20 %
COOSALUD                   68001C00060340-24           SOAT – 15 %
COMPENSAR                  Acuerdo Tarifario 2025      SOAT – 10 %
POSITIVA                   0525 de 2017 + Otrosí 03   SOAT – 15 %
PPL (Fiduprevisora)        IPS-001B-2022 / Otrosí 26  SOAT – 15 %
FOMAG (Fiduprevisora)      12076-359-2025              SOAT – 15 %
POLICÍA NAL. (Med/Alta)    068-5-200004-26 (SFI 004)  UVB – 8 %
POLICÍA NAL. (Oncología)   068-5-200006-26             Inst. HUS
SUMIMEDICAL                Tarifario 2025              SOAT – 15 %
DISPENSARIO MÉD. (DMBUG)   440-DIGSA/DMBUG-2025       SOAT/SMLV – 20 %
SALUD MIA                  CSA2025EVE3A005             SOAT – 15 %
PRECIMED                   Contrato 319 de 2024        SOAT – 15 %
AURORA (ARL/Vida)          Minuta ARL firmada 2024     SOAT pleno
SIN CONTRATO               —                           SOAT pleno
"""

import re
from typing import Optional

# ══════════════════════════════════════════════════════════════════
#  1.  BASE DE CONOCIMIENTO CONTRACTUAL
# ══════════════════════════════════════════════════════════════════

CONTRATOS_HUS: dict[str, dict] = {
    "NUEVA EPS": {
        "numero":   "ACTA DE NEGOCIACIÓN No. 1388 DE 2024 / ACTA 2025",
        "tarifa":   "SOAT -20 %",
        "factor":   0.80,
        "tipo":     "EPS CONTRIBUTIVO / RÉGIMEN SUBSIDIADO",
        "nit":      "800.149.436-2",
        "vigencia": "2025",
        "contacto": "john.sanabria@nuevaeps.com.co — Coordinador Estructuración de Redes y Contratación, Regional Nororiente",
        "nota":     "Incluye contrato MAOS No. 319 de 2024 para servicios oncológicos y de alta complejidad.",
    },
    "COOSALUD": {
        "numero":   "68001C00060340-24 / 68001S00060339-24",
        "tarifa":   "SOAT -15 %",
        "factor":   0.85,
        "tipo":     "EPS SUBSIDIADO / CONTRIBUTIVO",
        "nit":      "800.250.119-4",
        "vigencia": "2025",
        "contacto": "Reunión de proveedores presencial — Acta 21-01-2025",
        "nota":     "Dos contratos activos: contributivo C00060340 y subsidiado S00060339. Tarifario HUS 2025 en dos hojas: SOAT y Servicios Institucionales.",
    },
    "COMPENSAR": {
        "numero":   "ACUERDO TARIFARIO ESE HUS — EPS COMPENSAR 2025",
        "tarifa":   "SOAT -10 %",
        "factor":   0.90,
        "tipo":     "EPS CONTRIBUTIVO",
        "nit":      "860.063.996-9",
        "vigencia": "2025",
        "contacto": "Notificación contrato septiembre 2025",
        "nota":     "Acuerdo tarifario con dos componentes: SOAT homologado CUPS (descuento -10%) y servicios institucionales HUS valorados en tarifa propia.",
    },
    "POSITIVA": {
        "numero":   "CONTRATO No. 0525 DE 2017 + OTROSÍ No. 03 (diciembre 2025)",
        "tarifa":   "SOAT -15 %",
        "factor":   0.85,
        "tipo":     "ARL / RIESGOS LABORALES",
        "nit":      "860.011.153-6",
        "vigencia": "Extendida hasta diciembre 2025, prorrogada por Otrosí 03",
        "contacto": "CHARLES RODOLFO BAYONA MOLANO — Vicepresidente Técnico Positiva",
        "nota":     "Contrato de riesgos laborales. El Otrosí 03 modifica obligaciones del contratista, duración, interventoría y garantías.",
    },
    "PPL": {
        "numero":   "CONTRATO IPS-001B-2022 — OTROSÍ No. 26 (2025)",
        "tarifa":   "SOAT -15 % (homologación CUPS-SOAT HUS 2022)",
        "factor":   0.85,
        "tipo":     "POBLACIÓN PRIVADA DE LA LIBERTAD",
        "nit":      "830.053.105-3",
        "vigencia": "2025",
        "contacto": "MARÍA FERNANDA JARAMILLO GUTIÉRREZ — Vicepresidente Negocios Fiduciarios, Fiduprevisora S.A.",
        "nota":     "Fondo de Atención en Salud PPL 2025 administrado por Fiduprevisora. Marco normativo especial: Resolución 5159/2015 y Ley 1709/2014.",
    },
    "FOMAG": {
        "numero":   "CONTRATO No. 12076-359-2025",
        "tarifa":   "SOAT -15 %",
        "factor":   0.85,
        "tipo":     "MAGISTERIO — DOCENTES OFICIALES",
        "nit":      "830.053.105-3",
        "vigencia": "2025",
        "contacto": "CHRISTIAN RAMIRO FANDIÑO RIVEROS — Vicepresidente de Contratación, Fiduprevisora S.A. | notjudicial@fiduprevisora.com.co",
        "nota":     "Patrimonio Autónomo FOMAG administrado por Fiduprevisora. Registro especial IPS: 680010079201. Dirección: Carrera 33 # 28-126, Bucaramanga.",
    },
    "POLICIA NACIONAL": {
        "numero":   "CONTRATO No. 068-5-200004-26 (SFI 004) — MEDIANA Y ALTA COMPLEJIDAD",
        "tarifa":   "UVB 2026 – 8 %",
        "factor":   0.92,
        "tipo":     "POLICÍA NACIONAL — SUBSISTEMA DE SALUD",
        "nit":      "804.012.688-5",
        "vigencia": "2026",
        "contacto": "TTE. CRNL. ANDREA CAROLINA CONTRERAS BOHORQUEZ — Jefe Regional de Aseguramiento en Salud N° 5",
        "nota":     "Contrato interadministrativo. Cobertura: consulta ambulatoria, urgencias, hospitalización, UCI, procedimientos quirúrgicos, diagnósticos y terapéuticos. Resolución 00011 de enero 2025 y Orden Interna 26-055.",
    },
    "POLICIA NACIONAL ONCOLOGIA": {
        "numero":   "CONTRATO No. 068-5-200006-26 — ONCOLOGÍA",
        "tarifa":   "TARIFAS INSTITUCIONALES HUS",
        "factor":   1.00,
        "tipo":     "POLICÍA NACIONAL — ONCOLOGÍA",
        "nit":      "804.012.688-5",
        "vigencia": "2026",
        "contacto": "MAYOR LEONARDO VEGA CALA — Jefe Regional Aseguramiento en Salud N° 5 | Delegación Res. 00011/2025 + Resolución 364/12-02-2025",
        "nota":     "Contrato interadministrativo exclusivo oncología. Minuta firmada marzo 2026. Inicio de ejecución certificado.",
    },
    "SUMIMEDICAL": {
        "numero":   "TARIFARIO ESE HUS 2025 — SUMIMEDICAL",
        "tarifa":   "SOAT -15 %",
        "factor":   0.85,
        "tipo":     "EMPRESA COMPLEMENTARIA DE SALUD",
        "nit":      "N/D",
        "vigencia": "2025",
        "contacto": "Correo contratación HUS",
        "nota":     "Tarifario en dos hojas: SOAT homologado CUPS y servicios institucionales HUS.",
    },
    "DISPENSARIO MEDICO": {
        "numero":   "CONTRATO No. 440-DIGSA/DMBUG-2025 (Proceso CD477)",
        "tarifa":   "SOAT/SMLV -20 % (Manual tarifario homologado SOAT-SMLV con descuento del 20%)",
        "factor":   0.80,
        "tipo":     "FUERZAS MILITARES — EJÉRCITO NACIONAL",
        "nit":      "901.541.137-1",
        "vigencia": "Dic 2025 – Jul 2026 o hasta agotar presupuesto",
        "contacto": "DIRECCIÓN DE SANIDAD EJÉRCITO — DISPENSARIO MÉDICO BUCARAMANGA | gerencia@hus.gov.co",
        "nota":     "Contrato interadministrativo. Valor: $3.235.050.000 M/CTE. Cobertura: servicios de salud mediana y alta complejidad para afiliados Fuerzas Militares Regional 2. Tarifa pactada: SOAT/SMLV -20%. Objeto idéntico al ACUERDO 002 del 27-04-2001 del Consejo Superior de Salud FF.MM.",
    },
    "SALUD MIA": {
        "numero":   "CONTRATO CSA2025EVE3A005",
        "tarifa":   "SOAT -15 %",
        "factor":   0.85,
        "tipo":     "EPS / ASEGURADORA",
        "nit":      "N/D",
        "vigencia": "2025",
        "contacto": "Correo contratación HUS",
        "nota":     "Dos documentos firmados: CSA2025EVE3A005 y SSA2025EVE3A005.",
    },
    "PRECIMED": {
        "numero":   "CONTRATO No. 319 DE 2024",
        "tarifa":   "SOAT -15 %",
        "factor":   0.85,
        "tipo":     "EMPRESA DE MEDICINA PREPAGADA",
        "nit":      "N/D",
        "vigencia": "2024-2025",
        "contacto": "Correo contratación HUS",
        "nota":     "Contrato de prestación de servicios de salud.",
    },
    "AURORA": {
        "numero":   "MINUTA ARL + MINUTA VIDA AP — FIRMADAS SEP 2024",
        "tarifa":   "SOAT PLENO (sin descuento)",
        "factor":   1.00,
        "tipo":     "COMPAÑÍA DE SEGUROS — ARL Y VIDA",
        "nit":      "N/D",
        "vigencia": "2024-2025",
        "contacto": "Compañía de Seguros de Vida Aurora S.A.",
        "nota":     "Dos minutas: ARL y Vida AP. SOAT pleno aplicable.",
    },
}

def get_contrato(eps: str) -> dict:
    """Retorna los datos del contrato para una EPS dada (búsqueda flexible)."""
    eps_upper = eps.upper().strip()
    for key, val in CONTRATOS_HUS.items():
        if key in eps_upper or eps_upper in key:
            return val
    return {
        "numero":   "SIN CONTRATO PACTADO",
        "tarifa":   "SOAT PLENO — Resolución 054 de 2026",
        "factor":   1.00,
        "tipo":     "SIN RELACIÓN CONTRACTUAL",
        "nit":      "N/D",
        "vigencia": "N/A",
        "contacto": "cartera@hus.gov.co",
        "nota":     "Sin contrato. Se aplica tarifa SOAT plena según Res. 054/2026 y Decreto 2423/1996.",
    }


# ══════════════════════════════════════════════════════════════════
#  2.  DETECCIÓN DE CONTEXTO (tipo atención, CUPS, CIE-10, médico)
# ══════════════════════════════════════════════════════════════════

TIPO_ATENCION_KEYWORDS = {
    "CONSULTA EXTERNA":   ["consulta externa", "consulta medica", "cita medica", "consulta ambulatoria", "valoracion ambulatoria"],
    "URGENCIAS":          ["urgencia", "urgente", "emergencia", "triage", "reanimacion", "shock", "rcp"],
    "HOSPITALIZACIÓN":    ["hospitalizacion", "hospitalizado", "cama hospitalaria", "internacion", "estancia hospitalaria", "dia cama"],
    "CIRUGÍA":            ["cirugia", "quirurgico", "procedimiento quirurgico", "sala de cirugia", "procedimiento", "intervencion quirurgica"],
    "UCI":                ["uci", "unidad de cuidados intensivos", "cuidado critico", "ventilacion mecanica", "cuidado intensivo"],
    "ONCOLOGÍA":          ["oncologia", "quimioterapia", "radioterapia", "oncologico", "cancer", "tumor", "neoplasia"],
    "PROCEDIMIENTO Dx":   ["imagen diagnostica", "ecografia", "tomografia", "resonancia", "endoscopia", "biopsia", "laboratorio"],
}

def extraer_tipo_atencion(contexto_pdf: str, texto_glosa: str) -> str:
    texto = (contexto_pdf + " " + texto_glosa).lower()
    for tipo, palabras in TIPO_ATENCION_KEYWORDS.items():
        if any(p in texto for p in palabras):
            return tipo
    return "NO ESPECIFICADO EN SOPORTES"

def extraer_datos_soporte(contexto_pdf: str) -> dict:
    datos = {
        "cups":          "NO IDENTIFICADO",
        "diagnostico":   "NO IDENTIFICADO",
        "medico":        "NO IDENTIFICADO",
        "fecha_atencion":"NO IDENTIFICADA",
        "servicio":      "NO IDENTIFICADO",
        "paciente":      "NO IDENTIFICADO",
        "edad":          "NO IDENTIFICADA",
        "sexo":          "NO IDENTIFICADO",
        "signos_vitales":"NO IDENTIFICADOS",
        "glasgow":       "NO IDENTIFICADO",
        "laboratorios":  "NO IDENTIFICADOS",
        "medicamentos":  "NO IDENTIFICADOS",
        "evolucion":     "NO IDENTIFICADA",
    }
    if not contexto_pdf:
        return datos

    # CUPS
    m = re.search(r'\b(\d{5,6})\b', contexto_pdf)
    if m: datos["cups"] = m.group(1)

    # CIE-10
    m = re.search(r'\b([A-Z]\d{2}\.?\d*)\b', contexto_pdf)
    if m: datos["diagnostico"] = m.group(1)

    # Médico tratante
    m = re.search(
        r'(?:m[eé]dico|dr\.?|dra\.?|profesional|especialista|tratante)[:\s]+([A-ZÁÉÍÓÚ][a-záéíóú]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóú]+){1,3})',
        contexto_pdf, re.I
    )
    if m: datos["medico"] = m.group(1).strip()

    # Fecha atención
    m = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', contexto_pdf)
    if m: datos["fecha_atencion"] = m.group(1)

    # Servicio / procedimiento
    m = re.search(
        r'(?:servicio|procedimiento|actividad|descripci[oó]n)[:\s]+([A-ZÁÉÍÓÚ][^\n]{5,80})',
        contexto_pdf, re.I
    )
    if m: datos["servicio"] = m.group(1).strip()[:100]

    # Paciente
    m = re.search(
        r'(?:paciente|nombre\s+del\s+paciente|nombres?\s+y\s+apellidos?)[:\s]+([A-ZÁÉÍÓÚ][a-záéíóú]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóú]+){1,4})',
        contexto_pdf, re.I
    )
    if m: datos["paciente"] = m.group(1).strip()

    # Edad
    m = re.search(r'(?:edad|años)[:\s]*(\d{1,3})\s*(?:años?)?', contexto_pdf, re.I)
    if m and int(m.group(1)) < 120:
        datos["edad"] = f"{m.group(1)} años"

    # Sexo
    m = re.search(r'(?:sexo|g[eé]nero)[:\s]*(masculino|femenino|hombre|mujer|m|f)\b', contexto_pdf, re.I)
    if m:
        s = m.group(1).upper()
        datos["sexo"] = "MASCULINO" if s in ("MASCULINO", "HOMBRE", "M") else "FEMENINO"

    # Signos vitales
    sv = []
    m = re.search(r'(?:ta|tensi[oó]n\s+arterial|presi[oó]n)[:\s]*(\d{2,3}/\d{2,3})', contexto_pdf, re.I)
    if m: sv.append(f"TA {m.group(1)} mmHg")
    m = re.search(r'(?:fc|frecuencia\s+cardiaca)[:\s]*(\d{2,3})', contexto_pdf, re.I)
    if m: sv.append(f"FC {m.group(1)} lpm")
    m = re.search(r'(?:fr|frecuencia\s+respiratoria)[:\s]*(\d{2})', contexto_pdf, re.I)
    if m: sv.append(f"FR {m.group(1)} rpm")
    m = re.search(r'(?:t°|temp|temperatura)[:\s]*(\d{2}[\.,]?\d?)', contexto_pdf, re.I)
    if m: sv.append(f"T° {m.group(1)}°C")
    m = re.search(r'(?:sa?02|saturaci[oó]n)[:\s]*(\d{2,3})', contexto_pdf, re.I)
    if m: sv.append(f"SatO2 {m.group(1)}%")
    if sv: datos["signos_vitales"] = " | ".join(sv)

    # Glasgow
    m = re.search(r'(?:glasgow|gcs)[:\s]*(\d{1,2}\s*/\s*15|\d{1,2})', contexto_pdf, re.I)
    if m: datos["glasgow"] = f"Glasgow {m.group(1).replace(' ', '')}"

    # Laboratorios relevantes
    labs = []
    for pat, label in [
        (r'(?:leucocitos?)[:\s]*(\d{3,6})', "leucocitos"),
        (r'(?:hemoglobina|hb)[:\s]*(\d{1,2}[\.,]?\d?)', "Hb"),
        (r'(?:pcr|prote[ií]na\s+c\s+reactiva)[:\s]*(\d+[\.,]?\d*)', "PCR"),
        (r'(?:creatinina)[:\s]*(\d+[\.,]?\d*)', "creatinina"),
        (r'(?:troponina)[:\s]*(\d+[\.,]?\d*)', "troponina"),
    ]:
        m = re.search(pat, contexto_pdf, re.I)
        if m: labs.append(f"{label} {m.group(1)}")
    if labs: datos["laboratorios"] = " | ".join(labs)

    # Evolución / notas relevantes (primeras líneas tras "EVOLUCIÓN" o "NOTA")
    m = re.search(
        r'(?:evoluci[oó]n|nota\s+m[eé]dica|diagnostico\s+principal)[:\s]+([^\n]{20,250})',
        contexto_pdf, re.I
    )
    if m: datos["evolucion"] = m.group(1).strip()[:300]

    return datos

def tiene_soportes_reales(contexto_pdf: str) -> bool:
    return bool(contexto_pdf and len(contexto_pdf.strip()) > 80)


# ══════════════════════════════════════════════════════════════════
#  3.  SYSTEM PROMPTS BASE Y ESPECIALIZADOS
# ══════════════════════════════════════════════════════════════════

SYSTEM_BASE = """\
Eres el ABOGADO DIRECTOR DE CARTERA Y GLOSAS de la ESE HOSPITAL UNIVERSITARIO DE SANTANDER (HUS), NIT 890.210.024-0, Bucaramanga, Santander, Colombia.

IDENTIDAD INSTITUCIONAL:
- IPS pública de alta complejidad, referente regional del nororiente colombiano.
- Representante legal: RICARDO ARTURO HOYOS LANZIANO, C.C. 72.251.369.
- Dirección: Carrera 33 No. 28-126, Bucaramanga. Tel. 6076912010.
- Correo institucional: cartera@hus.gov.co | glosasydevoluciones@hus.gov.co

MISIÓN: Proteger los recursos institucionales rechazando glosas injustificadas con argumentos sólidos, precisos y completamente redactados. NUNCA dejes un campo en blanco ni con placeholder.

══════════════════════════════════════════════════════════════════
🚫 REGLAS ABSOLUTAS ANTI-ALUCINACIÓN (CRÍTICO — NO INVENTES NADA)
══════════════════════════════════════════════════════════════════
1. NUNCA inventes datos que no estén en los datos del caso.
   - Si no se proporciona el número de factura, di "FACTURA INDICADA EN EL EXPEDIENTE" o usa el dato real del campo "Factura". NO inventes uno.
   - Si no se proporciona el número de contrato, NO inventes uno; usa "según contrato vigente con la EPS" o di "SIN CONTRATO PACTADO" si así viene en los datos contractuales.
   - Si la EPS es "OTRA / SIN DEFINIR" o aparece como "SIN CONTRATO PACTADO", NO le asignes un nombre de EPS específico (NUNCA digas "PRECIMED", "NUEVA EPS", etc. si no aparece en los datos contractuales).
   - Si no hay datos del paciente en los soportes, escribe "PACIENTE IDENTIFICADO EN EXPEDIENTE", NO inventes nombres.
   - Si no hay nombre de médico tratante en los soportes, escribe "MÉDICO TRATANTE", NO inventes nombres.

2. Cita SOLO normas reales del listado autorizado más abajo. NO inventes números de leyes, decretos o sentencias.

3. EL TIPO DE GLOSA debe coincidir con el código:
   - TA → DEFENSA TARIFARIA. NUNCA digas "FACTURACIÓN" para una glosa TA.
   - SO → DEFENSA POR SOPORTES.
   - AU → DEFENSA POR AUTORIZACIÓN PREVIA (urgencia, T-1025/2002).
   - CO → DEFENSA POR COBERTURA (PBS o régimen especial).
   - CL/PE → DEFENSA POR PERTINENCIA CLÍNICA (autonomía médica).
   - FA → DEFENSA POR FACTURACIÓN (errores formales).
   - IN → DEFENSA POR INSUMOS.
   - ME → DEFENSA POR MEDICAMENTOS.

4. Si la glosa es TARIFARIA y conoces la tarifa pactada, MUESTRA el cálculo aritmético en el argumento (Valor SOAT pleno, factor contractual, valor pactado, valor reconocido por EPS, diferencia adeudada).

5. Si en los soportes aparecen datos clínicos (Glasgow, leucocitos, signos vitales, escala de dolor, ecografía, CIE-10), ÚSALOS textualmente como evidencia objetiva en el argumento.

6. Si no estás seguro de un dato concreto, DI "SEGÚN CONSTA EN EL EXPEDIENTE" en lugar de inventar.
══════════════════════════════════════════════════════════════════

MARCO NORMATIVO COMPLETO 2026:
1.  Ley 100/1993 — Art. 168 (urgencias obligatorias), Art. 177 (obligaciones EPS)
2.  Ley 1438/2011 — Art. 56 (plazos: 20 días hábiles EPS para glosar / 15 días IPS para responder / 10 días EPS para ratificar)
3.  Ley 1751/2015 — Art. 2 (salud derecho fundamental), Art. 17 (autonomía médica)
4.  Ley 1122/2007 — Art. 13 (flujo de recursos EPS→IPS)
5.  Decreto 4747/2007 — Art. 20 (conciliación), Art. 11 (documentos de cobro)
6.  Decreto 780/2016 — Decreto Único Reglamentario del Sector Salud
7.  Resolución 3047/2008 — Anexo Técnico 5 (procedimiento glosas y respuestas)
8.  Resolución 5269/2017 — Plan de Beneficios en Salud (PBS)
9.  Resolución 1995/1999 — Historia clínica como documento médico-legal
10. Resolución 054/2026 — Tarifas SOAT plenas vigentes 2026
11. Decreto 2423/1996 — Manual de Tarifas SOAT (base de cálculo)
12. Circular 030/2013 MINSALUD — Errores formales subsanables, no constituyen glosa
13. Circular ADRES 016/2024 — Auditoría integral de cuentas médicas ADRES
14. Circular 0000022/2023 — Facturación electrónica en salud
15. Ley 2015/2020 — Historia Clínica Electrónica Interoperable
16. Resolución 866/2021 — RIPS (Registros Individuales de Prestación de Servicios)
17. Código de Comercio Art. 871 — Principio de buena fe contractual
18. Sentencia T-760/2008 — Obligaciones de las EPS en prestación de servicios
19. Sentencia T-1025/2002 — Urgencias no requieren autorización previa
20. Sentencia T-478/1995 — Autonomía médica como derecho fundamental protegido

══════════════════════════════════════════════════════════════════
ESTÁNDAR DE REDACCIÓN TÉCNICO-JURÍDICA (OBLIGATORIO)
══════════════════════════════════════════════════════════════════
1. REGISTRO: Escribir SIEMPRE en MAYÚSCULAS SOSTENIDAS. Tono formal de abogado de cartera hospitalaria.
2. ESTRUCTURA: Usar numerales romanos para secciones (I, II, III, IV) cuando el argumento lo amerite. Cada numeral trata UN tema: (I) Antecedente del caso, (II) Fundamento contractual/tarifario, (III) Sustento normativo y jurisprudencial, (IV) Petición concreta.
3. EXTENSIÓN: MÍNIMO 450 palabras en el argumento principal (no inflar con muletillas; usar sustancia). Máximo razonable: 900 palabras.
4. CITAS NORMATIVAS ESPECÍFICAS: Cita SIEMPRE el ARTÍCULO concreto, no solo la norma. Ejemplo:
   ✓ "El artículo 177 de la Ley 100 de 1993 establece que..."
   ✗ "La Ley 100 establece que..."
5. JURISPRUDENCIA: Cuando apliques una sentencia, menciona el CONCEPTO que decidió. Ejemplo:
   ✓ "La Sentencia T-1025 de 2002 estableció que las EPS no pueden exigir autorización previa en urgencias."
   ✗ "La T-1025 aplica."
6. DATOS DEL CASO: Usa DATOS CLÍNICOS y números del caso concreto (paciente, CUPS, CIE-10, Glasgow, leucocitos, signos vitales, valor objetado, fechas, número de factura). NUNCA dejes frases abstractas sin anclarlas en el caso.
7. CONCLUSIÓN: Cierra con una petición concreta: "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO DE LA FACTURA N° [X] POR VALOR DE $[Y]".
8. VARIEDAD LÉXICA: Evita repetir el mismo conector. Alterna entre "en ese sentido", "así las cosas", "adicionalmente", "complementariamente", "por su parte".
9. NORMAS FINALES: Cierra con 3-5 normas en formato: Norma1 | Norma2 | Norma3 (las más pertinentes al caso).
10. PROHIBIDO:
   - Placeholders ([EPS], [FACTURA], etc.)
   - Frases genéricas tipo "la EPS debe cumplir con la normativa vigente" sin citar cuál
   - Muletillas repetidas: "en consecuencia", "por lo tanto" más de 2 veces
   - Párrafos de relleno sin información jurídica ni clínica
══════════════════════════════════════════════════════════════════
"""

SYSTEM_TA = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA TARIFARIA (TA)

CONTEXTO TARIFARIO HUS 2026:
- Resolución 054/2026: Tarifas SOAT plenas vigentes (piso, no techo).
- Consulta médica general: $35.800 | Especializada: $65.700 | Urgencias: $42.500
- UCI/día: $892.400 | Hospitalización/día: $198.600 | SMLMV 2026: $1.423.500
- El contrato y sus anexos son LEY entre las partes (Art. 1601 C. Civil).
- La EPS no puede aplicar descuentos unilaterales sin soporte contractual (Art. 871 C. Comercio).
- IPC: referente macroeconómico, NO obliga a la IPS a reducir tarifas.
- Si no hay contrato: SOAT pleno sin descuentos.

ARGUMENTOS TARIFARIOS:
1. La diferencia tarifaria no puede determinarse unilateralmente por el auditor EPS.
2. El descuento aplicado por la EPS debe estar expresamente pactado en el contrato.
3. Si hay incremento institucional por acto administrativo, la EPS debe reconocerlo.
4. Glosa tarifaria sin soporte del contrato específico es infundada.
5. El SOAT es piso mínimo; los contratos pueden superar ese valor.
"""

SYSTEM_SO = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA POR SOPORTES (SO)

ARGUMENTOS CLAVE:
1. Historia clínica = documento médico-legal por excelencia (Res. 1995/1999).
   Contiene diagnóstico, evolución, órdenes médicas y justificación clínica.
2. Los errores formales (código incorrecto, fecha, firma) son SUBSANABLES,
   NO causan glosa ni rechazo (Circular 030/2013 MINSALUD).
3. La Res. 3047/2008 define TAXATIVAMENTE los documentos exigibles.
4. El incumplimiento de la EPS al no solicitar documentos en tiempo no puede
   trasladarse a la IPS.
5. SOLO mencionar el plazo de 20 días hábiles (Art. 56 Ley 1438/2011) si la
   glosa ES EXTEMPORÁNEA. Si está dentro de términos, NO mencionar el plazo.
6. En urgencias: la documentación puede tramitarse con posterioridad (Art. 168 Ley 100/93).
"""

SYSTEM_CO = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA POR COBERTURA (CO)

PLAN DE BENEFICIOS EN SALUD:
- Res. 5269/2017: Define el PBS. Todo servicio dentro del PBS DEBE ser pagado.
- Ley 1751/2015 Art. 15: Exclusiones son EXCEPCIONALES y deben estar expresamente listadas.
- Principio de inclusión tácita: si el servicio no está excluido, está incluido.
- Para urgencias: la cobertura aplica independientemente del régimen (Art. 168 Ley 100/93).
- Servicios NO PBS: la EPS debe gestionarlos ante ADRES, NO glosarlos a la IPS.
- Población especial (PPL, FOMAG, PONAL, Fuerzas Militares): marco normativo propio.

REGÍMENES ESPECIALES SEGÚN EPS:
- PPL: Res. 5159/2015 y Ley 1709/2014 (reclusos). Cobertura total.
- FOMAG: Régimen docentes oficiales. Decreto 3752/2003.
- POLICÍA/FF.MM.: Acuerdo 002/2001 Consejo Superior de Salud.
- ARL (Positiva/Aurora): Decreto 1072/2015. Cobertura riesgos laborales.
"""

SYSTEM_CL = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA POR PERTINENCIA CLÍNICA (CL)

PRINCIPIO DE AUTONOMÍA MÉDICA (Art. 17 Ley 1751/2015):
- El médico tratante examina al paciente y toma decisiones clínicas.
- La EPS NO puede reemplazar el criterio médico desde una revisión administrativa.
- La pertinencia médica es un juicio CLÍNICO, no administrativo.
- T-478/1995: La autonomía médica es derecho fundamental protegido.

ARGUMENTOS:
1. La historia clínica documenta la evaluación del médico y su razonamiento diagnóstico.
2. Un auditor de la EPS no puede invalidar el criterio del médico tratante sin examen presencial.
3. El procedimiento realizado está respaldado por las guías de práctica clínica aplicables.
4. La comunidad médica reconoce la indicación del procedimiento para el diagnóstico documentado.
5. El principio de benef inúmera obliga al médico a actuar ante la duda clínica, no a omitir.

CIERRE: Solicitar conciliación de auditoría médica conjunta (Art. 20 Decreto 4747/2007, Res. 2175/2015).
"""

SYSTEM_FA = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA POR FACTURACIÓN (FA)

ARGUMENTOS FACTURACIÓN:
1. Los errores formales de facturación son SUBSANABLES (Circular 030/2013 MINSALUD).
2. La prestación real del servicio genera la obligación de pago independientemente de error formal.
3. RIPS radicados conforme a Res. 866/2021 respaldan la atención prestada.
4. Circular 0000022/2023: Requisitos de facturación electrónica cumplidos por la IPS.
5. Art. 56 Ley 1438/2011: Los errores formales no constituyen causal válida de glosa.
6. El incumplimiento de requisitos formales no exime a la EPS de su obligación de pago.
"""

SYSTEM_AU = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA POR AUTORIZACIÓN PREVIA (AU)

PRINCIPIO: La atención de URGENCIAS no requiere autorización previa.

ARGUMENTOS AUTORIZACIÓN:
1. Art. 168 Ley 100/1993: Las urgencias son obligación legal de prestación inmediata.
2. Sentencia T-1025/2002 (Corte Constitucional): Las urgencias no requieren autorización previa, son cobertura obligatoria.
3. Sentencia T-760/2008: Las EPS no pueden negar servicios cuando hay riesgo vital o documentación clínica que respalda la indicación.
4. Decreto 4747/2007 Art. 11: La IPS está obligada a prestar urgencias independientemente de la autorización.
5. Si en los soportes aparecen Glasgow ≤8, hipotensión, shock, signos de gravedad, RCP, dolor torácico, hemorragia, fractura abierta, abdomen agudo: cita el dato CLÍNICO específico como evidencia de la urgencia vital.
6. Si la atención fue programada Y aún así no había autorización: invocar Decreto 780/2016 (responsabilidad de la EPS de gestionar la autorización a tiempo).

CIERRE OBLIGATORIO: "ESE HUS EXIGE EL PAGO ÍNTEGRO POR TRATARSE DE ATENCIÓN DE URGENCIA OBLIGATORIA. LA AUTORIZACIÓN PREVIA NO ES REQUISITO LEGAL EN URGENCIAS."

PROHIBIDO: Llamar esta glosa "FACTURACIÓN", "SOPORTES" o cualquier otro tipo. ES POR AUTORIZACIÓN.
"""

SYSTEM_IN = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA POR INSUMOS (IN)

ARGUMENTOS INSUMOS:
1. Los insumos son inherentes al acto médico (Decreto 780/2016).
2. Se facturan al costo de adquisición + porcentaje administrativo pactado (Art. 871 C. Comercio).
3. Las facturas de compra y los registros de inventario hospitalario respaldan los insumos utilizados.
4. Para insumos de alto costo (prótesis, dispositivos), la HCE documenta la necesidad clínica.
5. Res. 5269/2017 incluye insumos asociados a procedimientos cubiertos en el PBS.
6. Si la EPS pide soportes adicionales, estos OBRAN EN EL EXPEDIENTE clínico.

PROHIBIDO: Decir que es "FACTURACIÓN" o "SOPORTES" — es INSUMOS.
"""

SYSTEM_ME = SYSTEM_BASE + """
ESPECIALIZACIÓN: DEFENSA POR MEDICAMENTOS (ME)

ARGUMENTOS MEDICAMENTOS:
1. Los medicamentos se dispensan bajo fórmula médica del médico tratante (Art. 17 Ley 1751/2015).
2. Res. 5269/2017 define el listado del PBS — todo medicamento incluido es obligatorio para la EPS.
3. Para medicamentos NO PBS, la EPS debe gestionarlos ante ADRES (Decreto 780/2016), NO glosarlos a la IPS.
4. Sentencia T-760/2008: La EPS no puede negar medicamentos prescritos cuando la condición clínica los exige.
5. Si el medicamento fue prescrito por necesidad clínica documentada en la historia clínica, su pago es obligatorio.
6. La prescripción del médico tratante prevalece sobre el criterio del auditor administrativo (T-478/1995).

PROHIBIDO: Decir que es "FACTURACIÓN" o "SOPORTES" — es MEDICAMENTOS.
"""

SYSTEM_MAP = {
    "TA": SYSTEM_TA,
    "SO": SYSTEM_SO,
    "CO": SYSTEM_CO,
    "CL": SYSTEM_CL,
    "PE": SYSTEM_CL,
    "FA": SYSTEM_FA,
    "AU": SYSTEM_AU,
    "IN": SYSTEM_IN,
    "ME": SYSTEM_ME,
}

# Bloques de normativa especial por tipo de pagador
REGIMEN_ESPECIAL = {
    "PPL": (
        "RÉGIMEN ESPECIAL — POBLACIÓN PRIVADA DE LA LIBERTAD\n"
        "- Ley 1709/2014: Reforma al Código Penitenciario y Carcelario.\n"
        "- Resolución 5159/2015: Procedimiento atención salud PPL — cobertura integral.\n"
        "- Decreto 1142/2016: Modelo de atención en salud PPL.\n"
        "- Fondo de Atención en Salud PPL administrado por Fiduprevisora S.A.\n"
        "- La cobertura es INTEGRAL y NO se rige solo por el PBS regular.\n"
        "OBLIGACIÓN: Citar SIEMPRE Res. 5159/2015 + Ley 1709/2014 al defender cobertura PPL."
    ),
    "FOMAG": (
        "RÉGIMEN ESPECIAL — MAGISTERIO (DOCENTES OFICIALES)\n"
        "- Decreto 3752/2003: Plan de Salud del Magisterio.\n"
        "- Ley 91/1989: Fondo Nacional de Prestaciones Sociales del Magisterio.\n"
        "- Cobertura definida por el Plan de Salud del Magisterio, NO por el PBS regular.\n"
        "- Administrado por Fiduprevisora S.A.\n"
        "OBLIGACIÓN: Citar Decreto 3752/2003 + Ley 91/1989 al defender cobertura FOMAG."
    ),
    "POLICIA NACIONAL": (
        "RÉGIMEN ESPECIAL — SUBSISTEMA DE SALUD POLICÍA NACIONAL\n"
        "- Ley 352/1997: Régimen de Salud de las Fuerzas Militares y Policía.\n"
        "- Decreto 1795/2000: Reglamenta sistema de salud FF.MM. y Policía.\n"
        "- Acuerdo 002/2001 Consejo Superior de Salud FF.MM.\n"
        "- Cobertura especial para uniformados y beneficiarios.\n"
        "OBLIGACIÓN: Citar Decreto 1795/2000 + Acuerdo 002/2001 CSSFFMM."
    ),
    "DISPENSARIO": (
        "RÉGIMEN ESPECIAL — DISPENSARIO MILITAR / EJÉRCITO\n"
        "- Decreto 1795/2000: Sistema de salud de las Fuerzas Militares.\n"
        "- Acuerdo 002/2001 Consejo Superior de Salud FF.MM.\n"
        "- Cobertura por convenio con el Comando General FF.MM."
    ),
    "POSITIVA": (
        "RÉGIMEN ESPECIAL — RIESGOS LABORALES (ARL)\n"
        "- Decreto 1295/1994: Sistema General de Riesgos Profesionales.\n"
        "- Decreto 1072/2015: Decreto Único Reglamentario Sector Trabajo, Libro 2 Parte 2 Título 4.\n"
        "- Ley 1562/2012: Modifica el Sistema de Riesgos Laborales.\n"
        "- Las atenciones por accidente de trabajo o enfermedad laboral NO se rigen por el PBS."
    ),
    "AURORA": (
        "RÉGIMEN ESPECIAL — RIESGOS LABORALES (ARL)\n"
        "- Decreto 1295/1994 + Decreto 1072/2015 + Ley 1562/2012.\n"
        "- Cobertura accidente de trabajo y enfermedad laboral, NO PBS regular."
    ),
}


def _detectar_regimen_especial(eps: str, contrato_tipo: str) -> str:
    """Devuelve bloque de normativa especial según EPS o tipo de contrato."""
    eps_up = (eps or "").upper()
    tipo_up = (contrato_tipo or "").upper()
    for key, bloque in REGIMEN_ESPECIAL.items():
        if key in eps_up or key in tipo_up:
            return bloque
    return ""


def get_system_prompt(prefijo: str, eps: str) -> str:
    """Retorna el system prompt especializado + datos contractuales + régimen especial."""
    base = SYSTEM_MAP.get(prefijo.upper(), SYSTEM_FA)
    contrato = get_contrato(eps)

    # Cálculo SOAT explícito si conocemos el factor
    factor = contrato.get("factor", 1.0)
    bloque_calculo = ""
    if prefijo.upper() == "TA" and factor < 1.0:
        descuento_pct = int(round((1 - factor) * 100))
        bloque_calculo = f"""
CALCULADORA TARIFARIA OBLIGATORIA (USA EN EL ARGUMENTO):
- Tarifa SOAT pleno (Res. 054/2026)  : Buscarla en el manual de tarifas para el CUPS facturado.
- Factor contractual aplicable       : {factor} (descuento {descuento_pct}%)
- Valor pactado = SOAT × {factor}
- Diferencia adeudada = Valor pactado - Valor reconocido por la EPS
- DEBES mostrar este cálculo en el argumento si la EPS aplicó otro descuento.
"""
    elif prefijo.upper() == "TA" and factor >= 1.0:
        bloque_calculo = """
CALCULADORA TARIFARIA OBLIGATORIA:
- Sin contrato pactado: aplica SOAT PLENO (Res. 054/2026), SIN descuentos.
- Cualquier descuento de la EPS es UNILATERAL y carece de soporte contractual.
"""

    bloque_regimen = _detectar_regimen_especial(eps, contrato.get("tipo", ""))
    if bloque_regimen:
        bloque_regimen = "\n══════════════════════════════════════════════\n" + bloque_regimen + "\n══════════════════════════════════════════════\n"

    return base + f"""
DATOS CONTRACTUALES VERIFICADOS (USA EXACTAMENTE ESTO, NO INVENTES OTROS):
─────────────────────────────────────────────────
EPS / PAGADOR : {eps}
CONTRATO      : {contrato['numero']}
TARIFA PACTADA: {contrato['tarifa']}
NIT PAGADOR   : {contrato['nit']}
VIGENCIA      : {contrato['vigencia']}
TIPO          : {contrato['tipo']}
NOTA CONTRATO : {contrato['nota']}
─────────────────────────────────────────────────
{bloque_calculo}
{bloque_regimen}
"""


# ══════════════════════════════════════════════════════════════════════════
#  4.  CUATRO VARIANTES DE RESPUESTA POR CONCEPTO
# ═══════════════���══════════════════════════════════════════════════

_VARIANTES: dict[str, list[str]] = {
    "TA": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CONTRATO: {numero_contrato} | TARIFA: {tarifa}

INSTRUCCIONES VARIANTE A — ARGUMENTO CONTRACTUAL:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR TARIFAS." + diferencia concreta entre lo glosado y lo pactado.
2. PÁRRAFO 2: Citar el contrato {numero_contrato} con {eps}, la tarifa pactada ({tarifa}) y que la EPS aplica un descuento NO AUTORIZADO contractualmente.
3. PÁRRAFO 3: Art. 871 Código de Comercio (buena fe contractual) + Art. 1601 C. Civil (el contrato es ley entre las partes). El IPC no es obligatorio para la IPS.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO DE LA FACTURA CONFORME A LAS TARIFAS PACTADAS EN EL CONTRATO VIGENTE."
NORMAS: Res. 054/2026 | Art. 871 C. Comercio | Decreto 2423/1996
PROHIBIDO: No mencionar urgencias ni historia clínica (no aplica para glosa tarifaria).""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CONTRATO: {numero_contrato} | TARIFA: {tarifa}
CUPS DETECTADO EN SOPORTES: {cups} | SERVICIO: {servicio} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES SUBIDOS:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — ARGUMENTO CUPS+TARIFA:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR TARIFAS PARA EL SERVICIO {servicio} (CUPS {cups})."
2. PÁRRAFO 2: El contrato {numero_contrato} fija la tarifa {tarifa}. El valor facturado corresponde exactamente a este parámetro contractual.
3. PÁRRAFO 3: La EPS aplica un descuento no pactado. Art. 1601 C. Civil + Art. 871 C. Comercio.
4. CIERRE: "SE EXIGE EL PAGO CORRESPONDIENTE AL CUPS {cups} SEGÚN TARIFARIO CONTRACTUAL VIGENTE."
NORMAS: Res. 054/2026 | Art. 1601 C. Civil | Art. 871 C. Comercio""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CONTRATO: {numero_contrato} | TARIFA: {tarifa}
CUPS: {cups} | DX: {diagnostico} | SERVICIO: {servicio} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — ARGUMENTO ACTO ADMINISTRATIVO:
1. INICIO: "ESE HUS RECHAZA EN SU TOTALIDAD LA GLOSA TARIFARIA POR IMPROCEDENTE."
2. PÁRRAFO 2: La ESE HUS es una entidad pública que fija sus tarifas mediante RESOLUCIÓN INTERNA DE PRECIOS, expedida anualmente como acto administrativo.
3. PÁRRAFO 3: El contrato {numero_contrato} reconoce estas tarifas institucionales.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. LA GLOSA CARECE DE FUNDAMENTO CONTRACTUAL Y NORMATIVO."
NORMAS: Res. 054/2026 | Decreto 2423/1996 | Art. 871 C. Comercio""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CONTRATO: {numero_contrato} | TARIFA: {tarifa}
CUPS: {cups} | SERVICIO: {servicio} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — ARGUMENTO HOMOLOGACIÓN CUPS-SOAT:
1. INICIO: "ESE HUS RECHAZA LA GLOSA TARIFARIA. LA HOMOLOGACIÓN CUPS-SOAT FUE CORRECTAMENTE APLICADA."
2. PÁRRAFO 2: El Anexo Tarifario del contrato {numero_contrato} establece la tabla de homologación CUPS-SOAT.
3. PÁRRAFO 3: La diferencia tarifaria que alega la EPS proviene de aplicar un código de homologación erróneo o un descuento distinto al pactado.
4. CIERRE: "SE SOLICITA LA CORRECCIÓN INMEDIATA Y EL PAGO DEL SALDO GLOSADO CONFORME AL TARIFARIO PACTADO."
NORMAS: Decreto 2423/1996 | Res. 054/2026 | Art. 1601 C. Civil""",
    ],
    "SO": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
TIPO ATENCIÓN: {tipo_atencion}

INSTRUCCIONES VARIANTE A — DEFENSA NORMATIVA SOPORTES:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR SOPORTES."
2. PÁRRAFO 2: La historia clínica del paciente constituye plena prueba médico-legal (Res. 1995/1999). {condicional_urgencia}
3. PÁRRAFO 3: Los documentos solicitados por la EPS obran en el expediente. Los errores formales son subsanables (Circular 030/2013 MINSALUD).
4. CIERRE: "SE EXIGE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA Y EL PAGO ÍNTEGRO DEL SERVICIO."
NORMAS: Res. 1995/1999 | Circular 030/2013 | Res. 3047/2008""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES SUBIDOS POR EL AUDITOR:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — DEFENSA CON DOCUMENTOS:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR SOPORTES. LOS DOCUMENTOS REQUERIDOS OBRAN EN EL EXPEDIENTE."
2. PÁRRAFO 2: En los soportes adjuntos se acredita: (a) historia clínica del {tipo_atencion} con diagnóstico {diagnostico}; (b) orden médica expedida por el Dr./Dra. {medico}.
3. PÁRRAFO 3: La EPS alega falta de documentos que efectivamente existen.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO."
NORMAS: Res. 1995/1999 | Res. 3047/2008 | Circular 030/2013""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | FECHA: {fecha_atencion} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — HISTORIA CLÍNICA ELECTRÓNICA:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR SOPORTES. LA HISTORIA CLÍNICA ELECTRÓNICA ACREDITA ÍNTEGRAMENTE LA ATENCIÓN."
2. PÁRRAFO 2: La ESE HUS implementa historia clínica electrónica interoperable conforme a la Ley 2015/2020.
3. CIERRE: "SE ALLEGAN SOPORTES COMPLEMENTARIOS. SE EXIGE EL PAGO ÍNTEGRO SIN DESCUENTO."
NORMAS: Ley 2015/2020 | Res. 1995/1999 | Res. 866/2021""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — ATENCIÓN ESPECIAL:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR SOPORTES EN {tipo_atencion}."
2. PÁRRAFO 2: La atención prestada corresponde a {tipo_atencion}. {condicional_urgencia}
3. PÁRRAFO 3: El médico tratante {medico} realizó el procedimiento con CUPS {cups}.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. LA GLOSA ES IMPROCEDENTE."
NORMAS: Res. 3047/2008 | Res. 1995/1999 | Circular 030/2013""",
    ],
    "CO": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
TIPO PAGADOR: {tipo_contrato} | NORMA ESPECIAL APLICABLE: {norma_especial}
TIPO ATENCIÓN: {tipo_atencion}

INSTRUCCIONES VARIANTE A — COBERTURA (PBS o RÉGIMEN ESPECIAL):
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR COBERTURA."
2. PÁRRAFO 2: Si el TIPO PAGADOR es PPL, FOMAG, POLICÍA NACIONAL, DISPENSARIO MILITAR, ARL o régimen especial, OBLIGATORIO citar la NORMA ESPECIAL APLICABLE indicada arriba ({norma_especial}) y NO solo el PBS regular. Si es EPS regular, cita Res. 5269/2017 y aplica PBS.
3. PÁRRAFO 3: Indica el fundamento de obligación de pago según corresponda al régimen (Art. 177 Ley 100/1993 para EPS regulares; o el marco normativo especial si aplica).
4. CIERRE: "SE EXIGE EL RECONOCIMIENTO Y PAGO ÍNTEGRO DEL SERVICIO PRESTADO."
NORMAS: {norma_especial} | Res. 5269/2017 | Art. 15 Ley 1751/2015
PROHIBIDO: Si es PPL/FOMAG/POLICÍA, NO digas "EPS" — usa "ENTIDAD PAGADORA" o "FONDO" o "FIDUCIARIA".""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — CUPS EN PBS:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR COBERTURA. EL CUPS {cups} ESTÁ INCLUIDO EN EL PBS."
2. PÁRRAFO 2: El servicio con CUPS {cups} no figura en el listado de exclusiones de la Res. 5269/2017.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO DEL CUPS {cups}."
NORMAS: Res. 5269/2017 | Art. 177 Ley 100/1993 | Art. 15 Ley 1751/2015""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — RÉGIMEN ESPECIAL:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR COBERTURA BAJO EL MARCO NORMATIVO ESPECIAL DE {eps}."
2. PÁRRAFO 2: Los beneficiarios del {tipo_contrato} gozan de cobertura integral conforme al marco normativo especial.
3. CIERRE: "SE EXIGE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA Y EL PAGO DEL SERVICIO."
NORMAS: Res. 5269/2017 | {norma_especial} | Contrato {numero_contrato}""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — URGENCIA Y COBERTURA:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR COBERTURA. LA ATENCIÓN DE {tipo_atencion} ES DE COBERTURA OBLIGATORIA."
2. PÁRRAFO 2: El Art. 168 de la Ley 100/1993 establece que TODA IPS está obligación de prestar atención de urgencias.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. LA ESE HUS CUMPLIÓ SU DEBER LEGAL DE ATENCIÓN."
NORMAS: Art. 168 Ley 100/1993 | Res. 5269/2017 | T-760/2008""",
    ],
    "CL": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
TIPO ATENCIÓN: {tipo_atencion}

INSTRUCCIONES VARIANTE A — AUTONOMÍA MÉDICA:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR PERTINENCIA CLÍNICA."
2. PÁRRAFO 2: El médico tratante es el único profesional que examina directamente al paciente (Art. 17 Ley 1751/2015).
3. PÁRRAFO 3: La sentencia T-478/1995 protege la autonomía médica como derecho fundamental.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. SE SOLICITA CONCILIACIÓN DE AUDITORÍA MÉDICA CONJUNTA."
NORMAS: Art. 17 Ley 1751/2015 | T-478/1995 | Art. 20 Decreto 4747/2007""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — PERTINENCIA CON HISTORIA CLÍNICA:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR PERTINENCIA CLÍNICA. LA HISTORIA CLÍNICA JUSTIFICA PLENAMENTE EL PROCEDIMIENTO."
2. PÁRRAFO 2: El médico tratante {medico} indicó el procedimiento CUPS {cups} para el diagnóstico {diagnostico}.
3. PÁRRAFO 3: El auditor de la EPS no examinó al paciente.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. SE SOLICITA AUDITORÍA MÉDICA CONJUNTA."
NORMAS: Art. 17 Ley 1751/2015 | T-478/1995 | Res. 2175/2015""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — GUÍAS DE PRÁCTICA CLÍNICA:
1. INICIO: "ESE HUS RECHAZA LA GLOSA DE PERTINENCIA. EL PROCEDIMIENTO SIGUE LA GUÍA DE PRÁCTICA CLÍNICA VIGENTE."
2. PÁRRAFO 2: El procedimiento CUPS {cups} es la conducta estándar recomendada para el diagnóstico {diagnostico}.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO."
NORMAS: Art. 17 Ley 1751/2015 | T-478/1995 | Decreto 4747/2007 Art. 20""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — PROCEDIMIENTO COMPLEJO:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR PERTINENCIA. EL PROCEDIMIENTO FUE MÉDICAMENTE NECESARIO E INDICADO."
2. PÁRRAFO 2: La condición clínica del paciente justificó la realización del procedimiento {cups}.
3. PÁRRAFO 3: La sentencia T-760/2008 reitera que las EPS no pueden negar servicios cuando la historia clínica soporta la indicación médica.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO."
NORMAS: Art. 17 Ley 1751/2015 | T-760/2008 | Art. 20 Decreto 4747/2007""",
    ],
    "FA": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
TIPO ATENCIÓN: {tipo_atencion}

INSTRUCCIONES VARIANTE A — ERROR FORMAL SUBSANABLE:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR FACTURACIÓN."
2. PÁRRAFO 2: El error de facturación alegado por la EPS es de naturaleza FORMAL y por tanto SUBSANABLE (Circular 030/2013).
3. PÁRRAFO 3: Los RIPS radicados respaldan la atención prestada.
4. CIERRE: "SE SUBSANA EL ERROR SEÑALADO Y SE EXIGE EL PAGO ÍNTEGRO DE LA FACTURA."
NORMAS: Circular 030/2013 | Res. 866/2021 | Circular 0000022/2023""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | FECHA: {fecha_atencion} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — CORRECCIÓN DOCUMENTADA:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR FACTURACIÓN. EL ERROR SEÑALADO ES SUBSANABLE Y SE CORRIGE MEDIANTE ESTE DOCUMENTO."
2. PÁRRAFO 2: El servicio CUPS {cups} fue efectivamente prestado el {fecha_atencion}.
3. CIERRE: "SE ALLEGA CORRECCIÓN. SE EXIGE EL PAGO ÍNTEGRO DEL SERVICIO CORREGIDO."
NORMAS: Circular 030/2013 | Art. 13 Ley 1122/2007 | Res. 866/2021""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | FECHA: {fecha_atencion} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — FACTURA ELECTRÓNICA:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR FACTURACIÓN. LA FACTURA ELECTRÓNICA FUE EXPEDIDA CONFORME A LA NORMATIVA VIGENTE."
2. PÁRRAFO 2: La factura electrónica fue expedida conforme a la Circular 0000022/2023.
3. CIERRE: "SE ADJUNTA NOTE DE CORRECCIÓN ELECTRÓNICA. SE EXIGE PAGO ÍNTEGRO."
NORMAS: Circular 0000022/2023 | Circular 030/2013 | Res. 866/2021""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — ERROR DE CÓDIGO O DUPLICADO:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR FACTURACIÓN. NO SE TRATA DE UN COBRO DUPLICADO NI DE UN ERROR DE CÓDIGO INVALIDANTE."
2. PÁRRAFO 2: El CUPS {cups} facturado corresponde exactamente al procedimiento realizado.
3. CIERRE: "SE EXIGE EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO DE LA FACTURA."
NORMAS: Circular 030/2013 | Res. 866/2021 | Art. 56 Ley 1438/2011""",
    ],
    "AU": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
TIPO ATENCIÓN: {tipo_atencion}

INSTRUCCIONES VARIANTE A — URGENCIA SIN AUTORIZACIÓN PREVIA:
1. INICIO OBLIGATORIO: "ESE HUS NO ACEPTA GLOSA POR AUTORIZACIÓN PREVIA. LA ATENCIÓN PRESTADA CORRESPONDE A URGENCIA VITAL DE COBERTURA OBLIGATORIA."
2. PÁRRAFO 2: El Art. 168 Ley 100/1993 obliga a TODA IPS a prestar atención de urgencias INDEPENDIENTEMENTE de la autorización previa. La Sentencia T-1025/2002 de la Corte Constitucional reitera que las urgencias son de cobertura obligatoria sin requisito de autorización.
3. PÁRRAFO 3: La atención fue documentada en historia clínica conforme a Res. 1995/1999 y radicada en RIPS conforme a Res. 866/2021.
4. CIERRE OBLIGATORIO: "SE EXIGE EL PAGO ÍNTEGRO POR TRATARSE DE URGENCIA OBLIGATORIA. LA AUTORIZACIÓN PREVIA NO ES REQUISITO LEGAL EN URGENCIAS."
NORMAS: Art. 168 Ley 100/1993 | T-1025/2002 | Decreto 4747/2007 Art. 11
PROHIBIDO: NO digas "FACTURACIÓN", "SOPORTES" ni "TARIFAS". Es por AUTORIZACIÓN.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — URGENCIA CON DATOS CLÍNICOS:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR AUTORIZACIÓN. LA EVIDENCIA CLÍNICA DOCUMENTADA RESPALDA LA URGENCIA VITAL."
2. PÁRRAFO 2: La historia clínica acredita el diagnóstico {diagnostico} con CUPS {cups}. Si en los soportes aparecen Glasgow ≤8, hipotensión, sangrado activo, deterioro neurológico, RCP, dolor torácico irradiado, abdomen agudo, fractura abierta o hemorragia: CITA EL DATO CLÍNICO CONCRETO como evidencia de la gravedad.
3. PÁRRAFO 3: Sentencia T-1025/2002 + Sentencia T-760/2008: la EPS no puede negar atenciones cuando hay riesgo vital documentado.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. LA AUTORIZACIÓN PREVIA NO APLICA EN URGENCIAS VITALES."
NORMAS: Art. 168 Ley 100/1993 | T-1025/2002 | T-760/2008
PROHIBIDO: NO digas "FACTURACIÓN" ni "SOPORTES". Es por AUTORIZACIÓN.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — PROCEDIMIENTO DE ALTA COMPLEJIDAD EN URGENCIAS:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR AUTORIZACIÓN. EL PROCEDIMIENTO {cups} FUE INDICACIÓN VITAL DEL MÉDICO TRATANTE."
2. PÁRRAFO 2: El médico tratante {medico}, ejerciendo su autonomía profesional (Art. 17 Ley 1751/2015), ordenó el procedimiento ante la condición clínica documentada del paciente.
3. PÁRRAFO 3: Decreto 4747/2007 Art. 11: la IPS está obligada a prestar la urgencia. El Decreto 780/2016 establece que la EPS debe gestionar la autorización a tiempo, no trasladar el problema a la IPS.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO."
NORMAS: Art. 168 Ley 100/1993 | T-1025/2002 | Decreto 780/2016
PROHIBIDO: NO digas "FACTURACIÓN" ni "SOPORTES". Es por AUTORIZACIÓN.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — ATENCIÓN PROGRAMADA SIN AUTORIZACIÓN OPORTUNA:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR AUTORIZACIÓN. LA EPS NO GESTIONÓ LA AUTORIZACIÓN EN TÉRMINOS LEGALES."
2. PÁRRAFO 2: El Decreto 780/2016 establece que la responsabilidad de gestionar la autorización oportuna es de la EPS. La IPS prestó el servicio que el paciente requería clínicamente.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. LA EPS NO PUEDE TRASLADAR A LA IPS SU OMISIÓN ADMINISTRATIVA."
NORMAS: Decreto 780/2016 | Decreto 4747/2007 Art. 11 | T-760/2008
PROHIBIDO: NO digas "FACTURACIÓN" ni "SOPORTES". Es por AUTORIZACIÓN.""",
    ],
    "IN": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CONTRATO: {numero_contrato} | TARIFA: {tarifa}

INSTRUCCIONES VARIANTE A — INSUMOS GENÉRICOS:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR INSUMOS. LOS INSUMOS UTILIZADOS SON INHERENTES AL ACTO MÉDICO."
2. PÁRRAFO 2: Los insumos se facturan al costo de adquisición más el porcentaje administrativo pactado en el contrato {numero_contrato}.
3. PÁRRAFO 3: Las facturas de compra y los registros de inventario hospitalario respaldan el insumo utilizado y obran en el expediente institucional.
4. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO POR LOS INSUMOS UTILIZADOS EN LA ATENCIÓN."
NORMAS: Decreto 780/2016 | Art. 871 C. Comercio | Res. 5269/2017
PROHIBIDO: NO digas "FACTURACIÓN" ni "SOPORTES". Es por INSUMOS.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — INSUMOS CON DOCUMENTOS:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR INSUMOS. LOS INSUMOS UTILIZADOS ESTÁN DOCUMENTADOS Y JUSTIFICADOS CLÍNICAMENTE."
2. PÁRRAFO 2: Los insumos asociados al CUPS {cups} para el DX {diagnostico} corresponden a los necesarios según la guía de práctica clínica institucional.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO."
NORMAS: Res. 5269/2017 | Decreto 780/2016 | Circular 030/2013
PROHIBIDO: NO digas "FACTURACIÓN". Es por INSUMOS.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — INSUMOS DE ALTO COSTO:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR INSUMOS DE ALTO COSTO. LA NECESIDAD CLÍNICA ESTÁ PLENAMENTE DOCUMENTADA."
2. PÁRRAFO 2: La historia clínica documenta la necesidad clínica del insumo de alto costo (prótesis, dispositivo médico) prescrito por el médico tratante.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. SE ADJUNTAN FACTURAS DE COMPRA Y REGISTRO DE INVENTARIO."
NORMAS: Res. 5269/2017 | Art. 17 Ley 1751/2015 | T-760/2008
PROHIBIDO: NO digas "FACTURACIÓN". Es por INSUMOS.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | TIPO ATENCIÓN: {tipo_atencion}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — INSUMOS EN URGENCIAS:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR INSUMOS. LA ATENCIÓN DE URGENCIAS REQUIERE EL USO INMEDIATO DE INSUMOS DE SOPORTE VITAL."
2. PÁRRAFO 2: En urgencias los insumos son consumidos en el acto médico y forman parte indivisible del procedimiento.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO POR LOS INSUMOS APLICADOS EN URGENCIAS."
NORMAS: Art. 168 Ley 100/1993 | Res. 5269/2017 | Decreto 780/2016
PROHIBIDO: NO digas "FACTURACIÓN". Es por INSUMOS.""",
    ],
    "ME": [
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
TIPO ATENCIÓN: {tipo_atencion}

INSTRUCCIONES VARIANTE A — MEDICAMENTOS PBS:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR MEDICAMENTOS. EL MEDICAMENTO DISPENSADO CORRESPONDE A FÓRMULA MÉDICA AUTORIZADA."
2. PÁRRAFO 2: La Res. 5269/2017 incluye este tipo de medicamento en el Plan de Beneficios en Salud. La fórmula médica fue expedida por médico tratante en ejercicio de su autonomía profesional (Art. 17 Ley 1751/2015).
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO DEL MEDICAMENTO DISPENSADO."
NORMAS: Res. 5269/2017 | Art. 17 Ley 1751/2015 | T-760/2008
PROHIBIDO: NO digas "FACTURACIÓN" ni "SOPORTES". Es por MEDICAMENTOS.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE B — MEDICAMENTO CON FÓRMULA MÉDICA:
1. INICIO: "ESE HUS NO ACEPTA GLOSA POR MEDICAMENTOS. EL FÁRMACO FUE PRESCRITO POR EL MÉDICO TRATANTE {medico} POR INDICACIÓN CLÍNICA."
2. PÁRRAFO 2: La fórmula médica está respaldada por el DX {diagnostico} documentado en la historia clínica institucional.
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO DEL MEDICAMENTO."
NORMAS: Art. 17 Ley 1751/2015 | Res. 5269/2017 | Res. 1995/1999
PROHIBIDO: NO digas "FACTURACIÓN". Es por MEDICAMENTOS.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE C — MEDICAMENTO NO PBS GESTIÓN ADRES:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR MEDICAMENTOS. LOS MEDICAMENTOS NO PBS DEBEN GESTIONARSE ANTE ADRES, NO GLOSARSE A LA IPS."
2. PÁRRAFO 2: Decreto 780/2016: la EPS es la responsable de gestionar el reconocimiento de medicamentos no incluidos en el PBS ante la ADRES (Administradora de los Recursos del SGSSS).
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO. LA EPS NO PUEDE TRASLADAR A LA IPS LA OBLIGACIÓN DE GESTIONAR ANTE ADRES."
NORMAS: Decreto 780/2016 | T-760/2008 | Art. 17 Ley 1751/2015
PROHIBIDO: NO digas "FACTURACIÓN". Es por MEDICAMENTOS.""",
        """GLOSA: {texto_glosa}
CÓDIGO: {codigo} | EPS: {eps} | {trazabilidad} | {contexto_tiempo}
CUPS: {cups} | DX: {diagnostico} | MÉDICO: {medico}

SOPORTES:
{contexto_pdf}

INSTRUCCIONES VARIANTE D — MEDICAMENTO ONCOLÓGICO O ALTO COSTO:
1. INICIO: "ESE HUS RECHAZA LA GLOSA POR MEDICAMENTOS DE ALTO COSTO. LA INDICACIÓN MÉDICA ES INCUESTIONABLE."
2. PÁRRAFO 2: El médico tratante {medico} prescribió el medicamento ante la condición clínica del paciente. La autonomía médica está protegida (T-478/1995).
3. CIERRE: "SE EXIGE EL PAGO ÍNTEGRO DEL MEDICAMENTO PRESCRITO."
NORMAS: Art. 17 Ley 1751/2015 | T-478/1995 | T-760/2008
PROHIBIDO: NO digas "FACTURACIÓN". Es por MEDICAMENTOS.""",
    ],
}

FALLBACK_SIN_SOPORTES = (
    "NO SE APORTARON DOCUMENTOS COMPLEMENTARIOS. EL REGISTRO CLÍNICO INSTITUCIONAL "
    "RESPALDA ÍNTEGRAMENTE LA ATENCIÓN PRESTADA. LA HISTORIA CLÍNICA (RES. 1995/1999) Y "
    "LOS RIPS (RES. 866/2021) DAN CUENTA DE LA PRESTACIÓN. SE EXIGE EL PAGO ÍNTEGRO. "
    "CARTERA@HUS.GOV.CO | GLOSASYDEVOLUCIONES@HUS.GOV.CO"
)


def build_user_prompt(
    texto_glosa: str,
    contexto_pdf: str,
    codigo: str,
    eps: str,
    numero_factura: Optional[str] = None,
    numero_radicado: Optional[str] = None,
    dias_habiles: Optional[int] = None,
    es_extemporanea: bool = False,
    variante: int = -1,
) -> str:
    tipo_atencion = extraer_tipo_atencion(contexto_pdf, texto_glosa)
    datos = extraer_datos_soporte(contexto_pdf)
    cups        = datos["cups"]
    diagnostico = datos["diagnostico"]
    medico      = datos["medico"]
    fecha       = datos["fecha_atencion"]
    servicio    = datos["servicio"]
    hay_soportes = tiene_soportes_reales(contexto_pdf)

    contrato = get_contrato(eps)
    numero_contrato = contrato["numero"]
    tarifa          = contrato["tarifa"]
    tipo_contrato   = contrato["tipo"]

    norma_especial_map = {
        "PPL":    "Res. 5159/2015 + Ley 1709/2014",
        "FOMAG":  "Decreto 3752/2003",
        "POLICIA NACIONAL": "Acuerdo 002/2001 Consejo Superior de Salud FF.MM.",
        "DISPENSARIO": "Acuerdo 002/2001 Consejo Superior de Salud FF.MM.",
    }
    norma_especial = "Ley 100/1993 Art. 177"
    for k, v in norma_especial_map.items():
        if k in eps.upper():
            norma_especial = v
            break

    partes = []
    if numero_factura:  partes.append(f"Factura: {numero_factura}")
    if numero_radicado: partes.append(f"Radicado: {numero_radicado}")
    trazabilidad = " | ".join(partes) if partes else "SIN DATOS DE TRAZABILIDAD"

    if dias_habiles is not None:
        if es_extemporanea:
            contexto_tiempo = f"⚠ GLOSA EXTEMPORÁNEA ({dias_habiles} días hábiles — límite: 20)"
            plazo_dias = str(dias_habiles)
        else:
            contexto_tiempo = f"✓ DENTRO DE TÉRMINOS ({dias_habiles} días hábiles)"
            plazo_dias = str(dias_habiles)
    else:
        contexto_tiempo = "FECHAS NO INGRESADAS"
        plazo_dias = "N/D"

    if "URGENCIA" in tipo_atencion:
        condicional_urgencia = (
            "EN URGENCIAS LA DOCUMENTACIÓN PUEDE TRAMITARSE CON POSTERIORIDAD A LA ATENCIÓN "
            "(ART. 168 LEY 100/1993). LA FALTA DE ORDEN MÉDICA PREVIA NO APLICA EN URGENCIAS VITALES."
        )
        condicional_urgencia_corto = "atención de urgencias"
    elif tipo_atencion == "NO ESPECIFICADO EN SOPORTES":
        # Texto neutro cuando no se identifica el tipo de atención
        condicional_urgencia = (
            "TODOS LOS DOCUMENTOS EXIGIDOS POR LA RESOLUCIÓN 3047/2008 OBRAN EN EL EXPEDIENTE "
            "CLÍNICO INSTITUCIONAL Y RESPALDAN LA ATENCIÓN PRESTADA."
        )
        condicional_urgencia_corto = "la atención prestada"
    else:
        condicional_urgencia = (
            f"EN LA ATENCIÓN DE {tipo_atencion} TODOS LOS DOCUMENTOS EXIGIDOS OBRAN "
            "EN EL EXPEDIENTE CONFORME A LA RESOLUCIÓN 3047/2008."
        )
        condicional_urgencia_corto = f"atención de {tipo_atencion.lower()}"

    # Resumen de datos clínicos identificados del PDF (úsalos en el argumento si están)
    paciente_ex  = datos.get("paciente", "NO IDENTIFICADO")
    edad_ex      = datos.get("edad", "NO IDENTIFICADA")
    sexo_ex      = datos.get("sexo", "NO IDENTIFICADO")
    signos_ex    = datos.get("signos_vitales", "NO IDENTIFICADOS")
    glasgow_ex   = datos.get("glasgow", "NO IDENTIFICADO")
    labs_ex      = datos.get("laboratorios", "NO IDENTIFICADOS")
    evolucion_ex = datos.get("evolucion", "NO IDENTIFICADA")

    resumen_lines = []
    if paciente_ex != "NO IDENTIFICADO":  resumen_lines.append(f"  • PACIENTE       : {paciente_ex}")
    if edad_ex != "NO IDENTIFICADA":      resumen_lines.append(f"  • EDAD           : {edad_ex}")
    if sexo_ex != "NO IDENTIFICADO":      resumen_lines.append(f"  • SEXO           : {sexo_ex}")
    if diagnostico != "NO IDENTIFICADO":  resumen_lines.append(f"  • CIE-10         : {diagnostico}")
    if cups != "NO IDENTIFICADO":         resumen_lines.append(f"  • CUPS           : {cups}")
    if servicio != "NO IDENTIFICADO":     resumen_lines.append(f"  • SERVICIO       : {servicio}")
    if medico != "NO IDENTIFICADO":       resumen_lines.append(f"  • MÉDICO TRATANTE: {medico}")
    if fecha != "NO IDENTIFICADA":        resumen_lines.append(f"  • FECHA ATENCIÓN : {fecha}")
    if signos_ex != "NO IDENTIFICADOS":   resumen_lines.append(f"  • SIGNOS VITALES : {signos_ex}")
    if glasgow_ex != "NO IDENTIFICADO":   resumen_lines.append(f"  • {glasgow_ex}")
    if labs_ex != "NO IDENTIFICADOS":     resumen_lines.append(f"  • LABORATORIOS   : {labs_ex}")
    if evolucion_ex != "NO IDENTIFICADA": resumen_lines.append(f"  • EVOLUCIÓN      : {evolucion_ex}")

    datos_clinicos_str = (
        "\n".join(resumen_lines)
        if resumen_lines
        else "  • NO SE EXTRAJERON DATOS CLÍNICOS DE LOS SOPORTES"
    )

    prefijo = (codigo[:2].upper() if codigo and len(codigo) >= 2 else "FA")
    if prefijo not in _VARIANTES:
        prefijo = "FA"

    if variante == -1:
        if not hay_soportes:
            idx = 0
        elif cups != "NO IDENTIFICADO" and medico != "NO IDENTIFICADO":
            idx = 1
        elif cups != "NO IDENTIFICADO":
            idx = 2
        else:
            idx = 3
    else:
        idx = max(0, min(3, variante))

    template = _VARIANTES[prefijo][idx]
    ctx_pdf_truncado = (contexto_pdf[:4000] if contexto_pdf else FALLBACK_SIN_SOPORTES)

    instruccion_final = f"""

══════════════════════════════════════════════════════════════════
INSTRUCCIONES OBLIGATORIAS PARA ESTA RESPUESTA
══════════════════════════════════════════════════════════════════

【 1 】 DATOS CLÍNICOS EXTRAÍDOS DEL EXPEDIENTE:
{datos_clinicos_str}

  → Si aparecen datos arriba (paciente, CIE-10, CUPS, Glasgow, signos vitales,
    laboratorios), DEBES incorporarlos literalmente en el argumento como
    evidencia objetiva. Ejemplo correcto:
    "EL PACIENTE [NOMBRE], [EDAD] DE SEXO [SEXO], INGRESÓ POR URGENCIAS CON
     TA [VALOR], FC [VALOR] Y GLASGOW [VALOR], DIAGNÓSTICO [CIE-10]..."
  → Si un dato dice "NO IDENTIFICADO", NO lo menciones (NO inventes valores).

【 2 】 TIPO DE GLOSA = {prefijo}
  → Llama la glosa por su nombre correcto. NO mezcles tipos.
  → Las secciones "PROHIBIDO" de la variante son de cumplimiento obligatorio.

【 3 】 TRAZABILIDAD DEL CASO:
  {trazabilidad}
  → Si la trazabilidad indica factura o radicado concretos, cítalos
    TEXTUALMENTE en la petición final.
  → Si dice SIN DATOS, NO inventes números.

【 4 】 ESTRUCTURA ESPERADA DEL ARGUMENTO (USA ROMANOS I-IV):
   I.  ANTECEDENTES DEL CASO (resumen breve: paciente, servicio, valor objetado, motivo de glosa).
  II.  FUNDAMENTO CONTRACTUAL Y/O TÉCNICO (contrato aplicable, tarifa pactada, cálculo aritmético si es TA, evidencia clínica si es AU/CL/SO).
 III.  SUSTENTO NORMATIVO Y JURISPRUDENCIAL (artículos específicos + sentencias con su concepto, NO solo citar números).
  IV.  PETICIÓN CONCRETA (monto exacto, factura, radicado) + plazo legal de respuesta.

【 5 】 EXTENSIÓN MÍNIMA: 450 palabras. MÁXIMA: 900 palabras.
  → NO inflar con muletillas. Cada párrafo debe aportar un dato nuevo.

【 6 】 CIERRE CON NORMAS: 3-5 normas más pertinentes al caso en formato
  "Norma1 | Norma2 | Norma3 | Norma4"

══════════════════════════════════════════════════════════════════
CASO CONCRETO A RESOLVER (usa la plantilla de variante A–D abajo como guía):
══════════════════════════════════════════════════════════════════
"""

    return instruccion_final + template.format(
        texto_glosa        = texto_glosa,
        codigo             = codigo,
        eps                = eps,
        trazabilidad       = trazabilidad,
        contexto_tiempo    = contexto_tiempo,
        numero_contrato    = numero_contrato,
        tarifa             = tarifa,
        tipo_contrato      = tipo_contrato,
        norma_especial     = norma_especial,
        tipo_atencion      = tipo_atencion,
        cups               = cups,
        diagnostico        = diagnostico,
        medico             = medico,
        fecha_atencion     = fecha,
        servicio           = servicio,
        contexto_pdf       = ctx_pdf_truncado,
        plazo_dias         = plazo_dias,
        condicional_urgencia      = condicional_urgencia,
        condicional_urgencia_corto= condicional_urgencia_corto,
    )


def build_all_variants(
    texto_glosa: str,
    contexto_pdf: str,
    codigo: str,
    eps: str,
    numero_factura: Optional[str] = None,
    numero_radicado: Optional[str] = None,
    dias_habiles: Optional[int] = None,
    es_extemporanea: bool = False,
) -> list[str]:
    return [
        build_user_prompt(
            texto_glosa, contexto_pdf, codigo, eps,
            numero_factura, numero_radicado, dias_habiles, es_extemporanea,
            variante=i
        )
        for i in range(4)
    ]