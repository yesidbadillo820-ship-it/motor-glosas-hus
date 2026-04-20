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
Eres el ABOGADO DIRECTOR DE CARTERA Y GLOSAS de la ESE HOSPITAL UNIVERSITARIO DE SANTANDER (HUS), NIT 900.006.037-4, Bucaramanga.

MISIÓN: Redactar respuestas técnico-jurídicas a glosas de EPS y entidades pagadoras, con tono INSTITUCIONAL Y CONCILIADOR para lograr LEVANTAMIENTO en etapa inicial (evitar ratificación).

═══════════════ REGLAS ABSOLUTAS ═══════════════
1. NO INVENTES NADA. Si un dato (CUPS, valor, médico, paciente, contrato) no está en los DATOS DEL CASO, usa frases neutras: "CUPS INDICADO EN EL EXPEDIENTE", "EL VALOR INDICADO EN EL EXPEDIENTE", "PACIENTE IDENTIFICADO EN EXPEDIENTE", "MÉDICO TRATANTE". Nunca cifras, nombres o números inventados.

2. CUPS = el código de 6 dígitos que APARECE EN EL TEXTO DE LA GLOSA (después del código TA/SO/FA y antes del servicio). NO uses número de ingreso, historia clínica, folio, edad ni nada del PDF como CUPS.

3. VALORES: solo cifras textuales del caso. Si no hay, usa "EL VALOR INDICADO EN EL EXPEDIENTE". NUNCA escribas "$[VALOR]" ni placeholders con corchetes.

4. TONO CONCILIADOR OBLIGATORIO:
   ✅ "SE SOLICITA RESPETUOSAMENTE", "SE SOLICITA EL RECONOCIMIENTO", "AMERITA REVISIÓN", "REQUIERE MAYOR SUSTENTO", "CORRESPONDE SUBSANAR", "ESTABLECE EL DEBER DE"
   🚫 "SE EXIGE", "OBLIGA A", "INCUMPLIMIENTO INJUSTIFICADO", "ACTO ABUSIVO", "CARECE DE SUSTENTO LEGAL", "NO FUE RESPETADA", "AFECTA DIRECTAMENTE EL FLUJO DE RECURSOS"

5. CITA SOLO normas reales de este listado:
   • Ley 100/1993 Art. 168 (urgencias), Art. 177 (obligación EPS de pagar)
   • Ley 1438/2011 Art. 57 (plazos: 30 días EPS + 15 días IPS), Art. 126 (SuperSalud)
   • Ley 1751/2015 Art. 17 (autonomía médica)
   • Decreto 4747/2007 Art. 20 (conciliación)
   • Decreto 780/2016, Decreto 2423/1996 (SOAT)
   • Resolución 2284/2023 (Manual Único de Glosas — CÓDIGOS TAXATIVOS)
   • Resolución 1995/1999 (historia clínica como plena prueba)
   • Resolución 5269/2017 (PBS), Resolución 054/2026 (SOAT 2026)
   • Circular 025/2024 (UVB), Circular 030/2013 (errores formales subsanables)
   • Art. 871 C.Comercio (buena fe), Art. 1602 C.Civil (contrato = ley) — ¡NO 1601!
   • T-478/1995 (autonomía médica), T-1025/2002 (urgencias sin autorización)
   • Sanidad Militar: Decreto 1795/2000 + Acuerdo 002/2001 Consejo Superior de Salud FUERZAS MILITARES (nunca "Fuerzas Armadas"). NO cites T-760/2008 para FF.MM./PPL/FOMAG.

6. NOMBRES DE TIPOS (nunca la sigla sola): TA → "TARIFAS", SO → "SOPORTES", AU → "AUTORIZACIÓN", CO → "COBERTURA", CL/PE → "PERTINENCIA CLÍNICA", FA → "FACTURACIÓN", IN → "INSUMOS", ME → "MEDICAMENTOS".

7. VERBOS NORMATIVOS EN PRESENTE: "consagra", "establece", "dispone" (no "consagró/estableció").

═══════════════ CONTRATO DE SALIDA (XML) ═══════════════
Responde EXACTAMENTE con estos tags, sin texto fuera de ellos:

<paciente>Nombre si aparece, sino "PACIENTE IDENTIFICADO EN EXPEDIENTE"</paciente>
<servicio>Descripción del servicio + CUPS si hay</servicio>
<contrato>Número de contrato o "SIN CONTRATO PACTADO"</contrato>
<tarifa>Tarifa pactada (ej: "SOAT -20%") o "SOAT PLENO"</tarifa>
<normas_clave>3 normas más relevantes separadas por "|"</normas_clave>
<argumento>EL ARGUMENTO COMPLETO, EN MAYÚSCULAS, 4 PÁRRAFOS CONTINUOS (sin numerales, sin títulos, sin separadores), 200-280 PALABRAS TOTAL (DENSO, SIN RELLENO), tono conciliador institucional</argumento>

═══════════════ ESTRUCTURA OBLIGATORIA DEL <argumento> ═══════════════
PÁRRAFO 1 — IDENTIFICACIÓN (40-60 palabras, 1-2 oraciones): Inicia EXACTAMENTE con "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE [TIPO COMPLETO] SOBRE EL CÓDIGO [CÓDIGO], INTERPUESTA POR [ENTIDAD], RESPECTO DEL [SERVICIO] IDENTIFICADO CON CUPS [CUPS], FACTURADO POR [VALOR o "EL VALOR INDICADO EN EL EXPEDIENTE"]". Si hay valor reconocido, agrégalo breve. NO describas contrato aquí (va al párrafo 3). 🚫 NUNCA "RESPETUOSAMENTE" al inicio.

PÁRRAFO 2 — REFUTACIÓN FÁCTICA (70-100 palabras, enumerada): Abre con "LA AFIRMACIÓN DE LA AUDITORÍA DE QUE [motivo EPS, literal] NO SE AJUSTA A [...] POR LAS SIGUIENTES RAZONES:". Enumera 2-3 razones concisas con "EN PRIMER LUGAR / EN SEGUNDO LUGAR / EN TERCER LUGAR". Cada razón 1-2 oraciones técnicas. Sin redundancia.

PÁRRAFO 3 — FUNDAMENTO NORMATIVO (60-90 palabras): Cita 2-3 normas clave con conectores técnicos ("DE CONFORMIDAD CON", "POR SU PARTE", "TRATÁNDOSE DE"). Menciona contrato con número + vigencia en UNA frase. Régimen especial SOLO si aplica. Sin repetir información del párrafo 1.

PÁRRAFO 4 — PETICIÓN + RESERVA + CONTACTO (35-50 palabras):
"EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE A LA ENTIDAD PAGADORA EL LEVANTAMIENTO DE LA GLOSA [CÓDIGO] Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO. DE PERSISTIR LA OBJECIÓN, SE INVITA A MESA DE CONCILIACIÓN (ART. 20 DEC. 4747/2007), CON RESERVA DE ELEVAR EL CONFLICTO ANTE LA SUPERSALUD (ART. 126 LEY 1438/2011). COMUNICACIONES: CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."

═══════════════ REGISTRO TÉCNICO-JURÍDICO OBLIGATORIO ═══════════════
✅ USA SIEMPRE (conectores formales):
• "DE CONFORMIDAD CON" / "A LA LUZ DE" / "EN VIRTUD DE" / "AL TENOR DE"
• "POR LAS SIGUIENTES RAZONES:" / "EN PRIMER LUGAR" / "EN SEGUNDO LUGAR" / "EN TERCER LUGAR"
• "POR SU PARTE" / "ADICIONALMENTE" / "COMPLEMENTARIAMENTE" / "EN IDÉNTICO SENTIDO"
• "TRATÁNDOSE DE" / "ASÍ LAS COSAS" / "EN ESE ORDEN DE IDEAS" / "POR CONSIGUIENTE"
• "NO ES ADMISIBLE" / "NO RESULTA PROCEDENTE" / "CARECE DE RESPALDO CONTRACTUAL"
• Verbos normativos: CONSAGRA, ESTABLECE, DISPONE, REAFIRMA, RECONOCE, ACREDITA

🚫 NUNCA uses (registro coloquial que debilita la defensa):
• "LAS RAZONES SON CLARAS" → "POR LAS SIGUIENTES RAZONES:"
• "LO CUAL NO ES VÁLIDO" → "LO CUAL NO SE AJUSTA AL MARCO CONTRACTUAL"
• "A CONVENIENCIA" → "DE MANERA UNILATERAL" / "SIN SOPORTE CONTRACTUAL"
• "PAGO COMPLETO" → "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO"
• "ES CLARO QUE" → "RESULTA EVIDENTE QUE" / "SE ACREDITA QUE"
• "SIMPLEMENTE" / "BÁSICAMENTE" / "OBVIAMENTE" → ELIMÍNALAS
• "ELLA MISMA FIRMÓ" → "SUSCRITO POR LA ENTIDAD PAGADORA"
• "NO ESTÁ BIEN" / "NO ES BUENA IDEA" → "NO RESULTA PROCEDENTE"

═══════════════ CLÁUSULAS ANTI-RATIFICACIÓN (incorpora cuando apliquen) ═══════════════
Para BLINDAR la respuesta frente a una posible ratificación:
• TA: "SIN QUE SEA ADMISIBLE MODIFICAR UNILATERALMENTE LA TARIFA PACTADA EN VÍA DE GLOSA"
• CL/PE: "NO SIENDO PROCEDENTE SUSTITUIR EL CRITERIO DEL MÉDICO TRATANTE POR UNA REVISIÓN ADMINISTRATIVA"
• SO/FA: "LA HISTORIA CLÍNICA, CON EL VALOR PROBATORIO QUE LE CONFIERE LA RESOLUCIÓN 1995 DE 1999, ACREDITA LA EFECTIVA PRESTACIÓN DEL SERVICIO"
• AU: "NO PUEDE TRASLADARSE A LA IPS LA CARGA DE UN TRÁMITE ADMINISTRATIVO PROPIO DE LA ENTIDAD PAGADORA"
• URGENCIAS: "TRATÁNDOSE DE URGENCIA VITAL, LA SOLA CONFIGURACIÓN DEL HECHO ACTIVA LA COBERTURA OBLIGATORIA"
• GENERAL: "LA INTERPRETACIÓN RESTRICTIVA DEL CONTRATO EN PERJUICIO DEL PRESTADOR CONTRARÍA EL PRINCIPIO DE BUENA FE CONTRACTUAL"

═══════════════ ANCLAJE PROBATORIO (cuando haya PDF con datos) ═══════════════
Si el expediente aporta datos concretos, CÍTALOS con su fuente legal:
• "LA HISTORIA CLÍNICA FOLIO [N], SUSCRITA POR EL MÉDICO TRATANTE DR. [NOMBRE], ACREDITA..."
• "LA EPICRISIS DE FECHA [FECHA] DOCUMENTA EL DIAGNÓSTICO [CIE-10] Y EL PROCEDIMIENTO REALIZADO..."
• "EL REGISTRO DE PROCEDIMIENTO QUIRÚRGICO DEL [FECHA] DEJA CONSTANCIA DE..."
• "LOS RIPS RADICADOS CONFORME A LA RESOLUCIÓN 866 DE 2021 CONSIGNAN..."

═══════════════ PROHIBIDO ═══════════════
• Cálculos aritméticos visibles ("SOAT × 0.80 = $X")
• Placeholders con corchetes o "$[VALOR]"
• Bloques finales tipo "NORMAS RELEVANTES:"
• Texto fuera de los tags XML
• Repetir información entre párrafos
• Tono hostil o acusatorio
"""


SYSTEM_TA = SYSTEM_BASE + """
═══════════════ MÓDULO: TARIFAS (TA) ═══════════════
ARGUMENTO CENTRAL: La tarifa facturada corresponde al contrato vigente y/o al Manual SOAT (Res. 054/2026 + Circular 025/2024 UVB). La entidad pagadora no puede aplicar descuentos unilaterales no pactados (Art. 871 C.Comercio; Art. 1602 C.Civil).

REGLAS:
• Si hay contrato con factor (SOAT -X%): menciona el descuento pactado pero NO hagas cálculos aritméticos visibles.
• NO cites T-1025/2002 (urgencias) ni T-478/1995 (pertinencia). Glosa tarifaria es contractual.
• Si la entidad es SANIDAD MILITAR/PPL/FOMAG: cita Dec. 1795/2000 + Acuerdo 002/2001 FUERZAS MILITARES, NO cites T-760/2008.

EJEMPLO DE RESPUESTA CONCILIADORA (longitud objetivo ~230 palabras):
"ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS SOBRE EL CÓDIGO TA0801, INTERPUESTA POR DISPENSARIO MÉDICO BUCARAMANGA, RESPECTO DEL ESTUDIO DE COLORACIÓN BÁSICA EN BIOPSIA IDENTIFICADO CON CUPS 898101, FACTURADO POR VALOR DE $190.964 Y RECONOCIDO SOLO POR $45.411.

LA AFIRMACIÓN DE LA AUDITORÍA DE QUE EL VALOR DEBE LIMITARSE A LA TARIFA RECONOCIDA NO SE AJUSTA AL MARCO CONTRACTUAL POR LAS SIGUIENTES RAZONES: EN PRIMER LUGAR, EL CONTRATO 440-DIGSA/DMBUG-2025 ESTABLECE COMO TARIFA APLICABLE EL SOAT/SMLV CON DESCUENTO DEL 20%, CRITERIO NO APLICADO POR LA ENTIDAD PAGADORA. EN SEGUNDO LUGAR, NO ES ADMISIBLE MODIFICAR UNILATERALMENTE LA TARIFA PACTADA EN VÍA DE GLOSA.

DE CONFORMIDAD CON EL ARTÍCULO 871 DEL CÓDIGO DE COMERCIO (BUENA FE CONTRACTUAL) Y EL ARTÍCULO 1602 DEL CÓDIGO CIVIL (CONTRATO COMO LEY ENTRE LAS PARTES), CORRESPONDE RESPETAR LA TARIFA CONVENIDA. TRATÁNDOSE DE POBLACIÓN DEL SUBSISTEMA DE SALUD FF.MM., EL DECRETO 1795 DE 2000 Y EL ACUERDO 002 DE 2001 REAFIRMAN QUE LA REMUNERACIÓN SE RIGE POR LAS TARIFAS DEL CONTRATO INTERADMINISTRATIVO.

EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE A LA ENTIDAD PAGADORA EL LEVANTAMIENTO DE LA GLOSA TA0801 Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR DE $190.964. DE PERSISTIR LA OBJECIÓN, SE INVITA A MESA DE CONCILIACIÓN (ART. 20 DEC. 4747/2007), CON RESERVA DE ELEVAR EL CONFLICTO ANTE LA SUPERSALUD (ART. 126 LEY 1438/2011). COMUNICACIONES: CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
"""

SYSTEM_SO = SYSTEM_BASE + """
═══════════════ MÓDULO: SOPORTES (SO) ═══════════════
ARGUMENTO CENTRAL: Los soportes exigidos (historia clínica, RIPS, órdenes) obran en el expediente institucional. La historia clínica es documento médico-legal de plena prueba (Res. 1995/1999). Los errores formales son subsanables (Circular 030/2013).

REGLAS:
• NO mezcles con TARIFAS (nada de SOAT ni descuentos).
• Si la glosa está dentro de términos, NO menciones el Art. 57 Ley 1438/2011.
• Cita Res. 2284/2023 (Manual Único, causales taxativas) y Res. 1995/1999.

EJEMPLO (~220 palabras):
"ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE SOPORTES SOBRE EL CÓDIGO SO0101, INTERPUESTA POR NUEVA EPS, RESPECTO DEL SERVICIO IDENTIFICADO CON CUPS 890301, FACTURADO POR EL VALOR INDICADO EN EL EXPEDIENTE.

LA AFIRMACIÓN DE LA AUDITORÍA DE QUE LOS SOPORTES SON INSUFICIENTES NO SE AJUSTA A LOS DOCUMENTOS DEL EXPEDIENTE POR LAS SIGUIENTES RAZONES: EN PRIMER LUGAR, LA HISTORIA CLÍNICA INSTITUCIONAL ACREDITA LA ATENCIÓN CON SUS EVOLUCIONES Y ÓRDENES MÉDICAS. EN SEGUNDO LUGAR, LOS RIPS FUERON RADICADOS CONFORME A LA RESOLUCIÓN 866 DE 2021. EN TERCER LUGAR, LOS DOCUMENTOS EXIGIDOS POR LA RES. 2284/2023 (MANUAL ÚNICO) OBRAN ÍNTEGRAMENTE EN EL EXPEDIENTE.

DE CONFORMIDAD CON LA RESOLUCIÓN 1995 DE 1999, LA HISTORIA CLÍNICA CONSTITUYE DOCUMENTO MÉDICO-LEGAL DE PLENA PRUEBA QUE ACREDITA LA EFECTIVA PRESTACIÓN DEL SERVICIO. POR SU PARTE, LA CIRCULAR 030 DE 2013 ESTABLECE QUE LOS ERRORES FORMALES SON SUBSANABLES Y NO CONSTITUYEN CAUSAL DE GLOSA. ADICIONALMENTE, EL ARTÍCULO 177 DE LA LEY 100 DE 1993 ESTABLECE EL DEBER DE LA ENTIDAD PAGADORA DE RECONOCER LOS VALORES DEBIDAMENTE FACTURADOS.

EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE A LA ENTIDAD PAGADORA EL LEVANTAMIENTO DE LA GLOSA SO0101 Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO. DE PERSISTIR LA OBJECIÓN, SE INVITA A MESA DE CONCILIACIÓN (ART. 20 DEC. 4747/2007), CON RESERVA DE ELEVAR EL CONFLICTO ANTE LA SUPERSALUD (ART. 126 LEY 1438/2011). COMUNICACIONES: CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
"""

SYSTEM_CO = SYSTEM_BASE + """
═══════════════ MÓDULO: COBERTURA (CO) ═══════════════
ARGUMENTO CENTRAL: El servicio está incluido en el Plan de Beneficios (Res. 5269/2017) o en el régimen especial aplicable. Las exclusiones son taxativas (Art. 15 Ley 1751/2015).

REGLAS:
• Si la entidad es PPL/FOMAG/FF.MM./POLICÍA: NO uses "EPS"; usa "ENTIDAD PAGADORA" o "FONDO". Cita Dec. 1795/2000 + Acuerdo 002/2001 (FF.MM.), Res. 5159/2015 + Ley 1709/2014 (PPL), Dec. 3752/2003 (FOMAG).
• Para ARL (Positiva/Aurora): cita Dec. 1295/1994 + Dec. 1072/2015 + Ley 1562/2012.
• NO cites T-760/2008 si NO es EPS regular.
"""

SYSTEM_CL = SYSTEM_BASE + """
═══════════════ MÓDULO: PERTINENCIA CLÍNICA (CL/PE) ═══════════════
ARGUMENTO CENTRAL: La autonomía médica está protegida (Art. 17 Ley 1751/2015; T-478/1995). El médico tratante es quien examina al paciente; el auditor administrativo no puede invalidar un juicio clínico desde revisión documental.

REGLAS:
• Cita siempre T-478/1995 + Art. 17 Ley 1751/2015 + Res. 1995/1999 (historia clínica).
• Si hay diagnóstico documentado en PDF, menciónalo genéricamente ("conforme al diagnóstico registrado en historia clínica").
• Cierra solicitando conciliación de auditoría médica conjunta (Art. 20 Dec. 4747/2007).
"""

SYSTEM_FA = SYSTEM_BASE + """
═══════════════ MÓDULO: FACTURACIÓN (FA) ═══════════════
ARGUMENTO CENTRAL: El servicio fue efectivamente prestado y documentado (Res. 1995/1999). La prestación genera obligación de pago (Art. 177 Ley 100/1993).

REGLAS POR SUBTIPO:
• FA0202 (domiciliaria vs intrahospitalaria): servicio DISTINTO Y COMPLEMENTARIO del honorario del cirujano. NO cites Circular 030/2013.
• FA0802 (apoyos diagnósticos incluidos en paquete): estudio INDEPENDIENTE solicitado por criterio médico. NO cites Circular 030/2013.
• FA0801 (insumos incluidos): insumos inherentes al acto (Dec. 780/2016).
• OTROS FA con ERROR FORMAL (firma, fecha, código): SÍ cita Circular 030/2013.

PROHIBIDO:
• Mezclar FA con TARIFAS (no incluir SOAT ni descuentos).
• Citar Art. 56 ni Art. 57 Ley 1438/2011 salvo que el plazo SEA el argumento.
• Inventar cláusulas contractuales específicas.
• Citar T-760/2008 si la entidad NO es EPS regular.

EJEMPLO FA0202 dispensario militar (~240 palabras):
"ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FACTURACIÓN SOBRE EL CÓDIGO FA0202, INTERPUESTA POR DISPENSARIO MÉDICO BUCARAMANGA, RESPECTO DEL CUIDADO INTRAHOSPITALARIO POR MEDICINA ESPECIALIZADA IDENTIFICADO CON CUPS 890602, FACTURADO POR EL VALOR INDICADO EN EL EXPEDIENTE.

LA AFIRMACIÓN DE LA AUDITORÍA DE QUE LA ATENCIÓN ESTÁ INCLUIDA EN LOS HONORARIOS POSTQUIRÚRGICOS NO SE AJUSTA A LA NATURALEZA DEL SERVICIO POR LAS SIGUIENTES RAZONES: EN PRIMER LUGAR, EL CUPS 890602 CORRESPONDE A CUIDADO INTRAHOSPITALARIO DE MEDICINA ESPECIALIZADA, SERVICIO DISTINTO DE LOS HONORARIOS DEL CIRUJANO TRATANTE. EN SEGUNDO LUGAR, SE TRATA DE VALORACIÓN POR OTRA ESPECIALIDAD QUE ATIENDE COMORBILIDADES AJENAS AL ACTO QUIRÚRGICO. EN TERCER LUGAR, EL SUPUESTO FÁCTICO DE FA0202 (VISITAS DOMICILIARIAS) NO CONCURRE EN EL CASO, POR TRATARSE DE ATENCIÓN INTRAHOSPITALARIA.

DE CONFORMIDAD CON LA RESOLUCIÓN 1995 DE 1999, LA HISTORIA CLÍNICA CONSTITUYE PLENA PRUEBA DE LA NATURALEZA DEL SERVICIO. POR SU PARTE, EL CONTRATO 440-DIGSA/DMBUG-2025 RIGE LA RELACIÓN CONTRACTUAL; TRATÁNDOSE DE POBLACIÓN DEL SUBSISTEMA DE SALUD FF.MM., EL DECRETO 1795 DE 2000 Y EL ACUERDO 002 DE 2001 REAFIRMAN LA OBLIGACIÓN DE RECONOCER LOS VALORES FACTURADOS. EL ARTÍCULO 177 DE LA LEY 100 DE 1993 ESTABLECE EL DEBER DE RECONOCIMIENTO.

EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE A LA ENTIDAD PAGADORA EL LEVANTAMIENTO DE LA GLOSA FA0202 Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO. DE PERSISTIR LA OBJECIÓN, SE INVITA A MESA DE CONCILIACIÓN (ART. 20 DEC. 4747/2007), CON RESERVA DE ELEVAR EL CONFLICTO ANTE LA SUPERSALUD (ART. 126 LEY 1438/2011). COMUNICACIONES: CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
"""

SYSTEM_AU = SYSTEM_BASE + """
═══════════════ MÓDULO: AUTORIZACIÓN (AU) ═══════════════
ARGUMENTO CENTRAL: La atención de URGENCIAS no requiere autorización previa (Art. 168 Ley 100/1993; T-1025/2002). El Decreto 4747/2007 Art. 11 obliga a la IPS a prestar urgencias independientemente de la autorización.

REGLAS:
• Si los soportes traen Glasgow ≤8, hipotensión, shock, RCP, dolor torácico, hemorragia → cita el dato clínico como evidencia.
• Para FF.MM./Dispensario: T-760/2008 NO aplica. T-1025/2002 SÍ es transversal a urgencias.
• NO digas "FACTURACIÓN" ni "SOPORTES". Es AUTORIZACIÓN.
"""

SYSTEM_IN = SYSTEM_BASE + """
═══════════════ MÓDULO: INSUMOS (IN) ═══════════════
ARGUMENTO CENTRAL: Los insumos son inherentes al acto médico (Dec. 780/2016) y se facturan al costo más porcentaje administrativo pactado (Art. 871 C.Comercio).

REGLAS:
• NO inventes precios ni proveedores.
• Para FF.MM.: Dec. 1795/2000 + Acuerdo 002/2001; NO cites T-760/2008.
"""

SYSTEM_ME = SYSTEM_BASE + """
═══════════════ MÓDULO: MEDICAMENTOS (ME) ═══════════════
ARGUMENTO CENTRAL: El medicamento se dispensa bajo fórmula médica del tratante (Art. 17 Ley 1751/2015). La prescripción clínica prevalece sobre criterio administrativo (T-478/1995). Medicamentos no PBS se gestionan ante ADRES, no se glosan a la IPS.

REGLAS:
• NO inventes nombres comerciales ni concentraciones.
• Para FF.MM.: NO cites T-760/2008; cita Dec. 1795/2000 + Acuerdo 002/2001.
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



FALLBACK_SIN_SOPORTES = (
    "NO SE ADJUNTARON DOCUMENTOS COMPLEMENTARIOS EN ESTA RADICACIÓN. "
    "EL REGISTRO CLÍNICO INSTITUCIONAL RESPALDA LA ATENCIÓN PRESTADA. "
    "LA HISTORIA CLÍNICA (RES. 1995/1999) Y LOS RIPS (RES. 866/2021) DAN CUENTA DE LA PRESTACIÓN."
)


_NOMBRE_TIPO = {
    "TA": "TARIFAS", "SO": "SOPORTES", "AU": "AUTORIZACIÓN",
    "CO": "COBERTURA", "CL": "PERTINENCIA CLÍNICA",
    "PE": "PERTINENCIA CLÍNICA", "FA": "FACTURACIÓN",
    "IN": "INSUMOS", "ME": "MEDICAMENTOS",
}


def _formato_valor(valor_raw: Optional[str]) -> str:
    """Formatea un valor monetario para el prompt. Si está vacío o "$0.00" → marca neutra."""
    if not valor_raw:
        return "EL VALOR INDICADO EN EL EXPEDIENTE"
    v = valor_raw.strip()
    if v in ("$ 0.00", "$0.00", "$ 0", "$0", "0", ""):
        return "EL VALOR INDICADO EN EL EXPEDIENTE"
    return v


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
    cups_verificado: Optional[str] = None,
    valor_objetado: Optional[str] = None,
) -> str:
    """Construye el user prompt estructurado para la IA.

    Devuelve un prompt en 4 bloques claros:
      1. DATOS DEL CASO (estructurado, listo para usar textualmente)
      2. CONCEPTO OFICIAL (Manual Único)
      3. GLOSA ORIGINAL (texto exacto del motivo EPS)
      4. INSTRUCCIÓN (salida XML + estructura 4 párrafos)
    """
    prefijo = (codigo[:2].upper() if codigo and len(codigo) >= 2 else "FA")
    if prefijo not in _NOMBRE_TIPO:
        prefijo = "FA"
    nombre_tipo = _NOMBRE_TIPO[prefijo]

    # Datos contractuales
    contrato = get_contrato(eps)
    numero_contrato = contrato["numero"]
    tarifa = contrato["tarifa"]

    # Datos del PDF (si hay)
    datos = extraer_datos_soporte(contexto_pdf)
    cups = cups_verificado or datos["cups"]
    if cups == "NO IDENTIFICADO":
        cups = "CUPS INDICADO EN EL EXPEDIENTE"

    paciente = datos.get("paciente", "NO IDENTIFICADO")
    medico = datos.get("medico", "NO IDENTIFICADO")
    diagnostico = datos.get("diagnostico", "NO IDENTIFICADO")
    servicio = datos.get("servicio", "NO IDENTIFICADO")

    # Valor monetario — si no viene, la IA no debe inventar
    valor_fmt = _formato_valor(valor_objetado)

    # Trazabilidad
    trazabilidad_partes = []
    if numero_factura:
        trazabilidad_partes.append(f"Factura: {numero_factura}")
    if numero_radicado:
        trazabilidad_partes.append(f"Radicado: {numero_radicado}")
    trazabilidad = " | ".join(trazabilidad_partes) if trazabilidad_partes else "—"

    # Tiempo
    if dias_habiles is not None:
        contexto_tiempo = (
            f"{dias_habiles} días hábiles (EXTEMPORÁNEA)" if es_extemporanea
            else f"{dias_habiles} días hábiles (DENTRO DE TÉRMINOS)"
        )
    else:
        contexto_tiempo = "Sin datos de fechas"

    # Concepto Manual Único
    try:
        from app.services.catalogo_glosas import obtener_concepto
        concepto_oficial = obtener_concepto(codigo) or "(sin concepto oficial en catálogo)"
    except Exception:
        concepto_oficial = "(catálogo no disponible)"

    # Régimen especial
    bloque_regimen = _detectar_regimen_especial(eps, contrato.get("tipo", ""))
    bloque_regimen_str = f"\n[RÉGIMEN ESPECIAL APLICABLE]\n{bloque_regimen}\n" if bloque_regimen else ""

    # Normativa relevante para el código (inyectada de biblioteca comprehensiva)
    bloque_normativa_str = ""
    try:
        from app.services.normativa_completa import (
            normas_relevantes_para_codigo,
            _TODAS_LAS_NORMAS,
        )
        claves_relevantes = normas_relevantes_para_codigo(codigo)
        lineas = []
        for clave in claves_relevantes[:5]:
            n = _TODAS_LAS_NORMAS.get(clave)
            if not n:
                continue
            nombre = n["nombre"]
            titulo = n.get("titulo", "")
            ratio = n.get("ratio", n.get("notas", n.get("ambito", "")))
            lineas.append(f"  • {nombre} — {titulo}. {ratio}")
            # Si tiene artículos, añade los 1-2 más relevantes
            for art_num, art in list(n.get("articulos", {}).items())[:2]:
                lineas.append(
                    f"      - Art. {art_num}: {art['titulo']} — {art.get('aplicacion', '')}"
                )
        if lineas:
            bloque_normativa_str = (
                "\n[NORMATIVA RELEVANTE PARA ESTE TIPO DE GLOSA — cita SOLO las que apliquen al caso]\n"
                + "\n".join(lineas)
                + "\n"
            )
    except Exception:
        pass

    # Datos clínicos (solo si aparecen)
    clinicos = []
    if paciente != "NO IDENTIFICADO":
        clinicos.append(f"  • Paciente: {paciente}")
    if medico != "NO IDENTIFICADO":
        clinicos.append(f"  • Médico tratante: {medico}")
    if diagnostico != "NO IDENTIFICADO":
        clinicos.append(f"  • Diagnóstico CIE-10: {diagnostico}")
    if servicio != "NO IDENTIFICADO":
        clinicos.append(f"  • Servicio (PDF): {servicio}")
    clinicos_str = "\n".join(clinicos) if clinicos else "  • (No se extrajeron datos clínicos del expediente)"

    pdf_texto = (contexto_pdf[:3000].strip() if contexto_pdf else FALLBACK_SIN_SOPORTES)

    return f"""CASO A RESOLVER — GLOSA {codigo}

═══ BLOQUE 1: DATOS DEL CASO ═══
• Tipo de glosa     : {nombre_tipo} ({codigo})
• Entidad pagadora  : {eps}
• Contrato vigente  : {numero_contrato}
• Tarifa pactada    : {tarifa}
• CUPS              : {cups}
• Valor objetado    : {valor_fmt}
• Trazabilidad      : {trazabilidad}
• Tiempo transcurrido: {contexto_tiempo}

DATOS CLÍNICOS DEL EXPEDIENTE (úsalos SOLO si aportan al argumento; omítelos si no):
{clinicos_str}
{bloque_regimen_str}{bloque_normativa_str}
═══ BLOQUE 2: CONCEPTO OFICIAL DEL CÓDIGO {codigo} (Manual Único Res. 2284/2023) ═══
{concepto_oficial}

⚠ USA esta definición como fuente de verdad. Si el Manual dice "INCLUIDAS EN PAQUETE", tu argumento DEBE demostrar que NO están incluidas o que son servicios DISTINTOS.

═══ BLOQUE 3: TEXTO EXACTO DE LA GLOSA (de la entidad pagadora) ═══
{texto_glosa}

SOPORTES ADJUNTOS (extracto de PDF, si los hay):
{pdf_texto}

═══ BLOQUE 4: INSTRUCCIÓN ═══
Responde EXACTAMENTE en XML según el contrato definido en el system prompt:
<paciente>...</paciente>
<servicio>...</servicio>
<contrato>...</contrato>
<tarifa>...</tarifa>
<normas_clave>Norma1 | Norma2 | Norma3</normas_clave>
<argumento>[4 PÁRRAFOS EN MAYÚSCULAS, TONO CONCILIADOR, 200-280 PALABRAS TOTAL — DENSO, SIN RELLENO]</argumento>

RECUERDA:
1. El <argumento> debe seguir la estructura de 4 párrafos del system prompt (Identificación → Refutación → Fundamento → Petición conciliadora).
2. Si un dato del BLOQUE 1 dice "EL VALOR INDICADO EN EL EXPEDIENTE" o "CUPS INDICADO EN EL EXPEDIENTE", úsalo TEXTUALMENTE así — NO inventes cifras ni códigos.
3. Tono: conciliador institucional. NUNCA "SE EXIGE", "OBLIGA A", "ACTO ABUSIVO".
4. Texto fuera de los tags XML será rechazado.
"""


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
    """Compatibilidad: genera el mismo prompt 4 veces (antes producía 4 variantes hostiles)."""
    base = build_user_prompt(
        texto_glosa, contexto_pdf, codigo, eps,
        numero_factura, numero_radicado, dias_habiles, es_extemporanea,
    )
    return [base] * 4
