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
    "FAMISANAR": {
        "numero":   "CONTRATO S-13-1-03-1-04958",
        "tarifa":   "SOAT UVB VIGENTE -5 % (servicios CUPS) / VALOR FIJO (medicamentos y suministros)",
        "factor":   0.95,
        "tipo":     "EPS CONTRIBUTIVO / RÉGIMEN SUBSIDIADO",
        "nit":      "830003564-7",
        "vigencia": "15/04/2026 — 14/04/2027 (prórroga automática)",
        "contacto": "mhernandez@famisanar.com.co (Martha Biviana Hernández, Glosas) · cadarme@famisanar.com.co (Auditoría Médica)",
        "nota":     "Estructura mixta: Anexo 3 servicios CUPS = SOAT UVB VIGENTE -5%; Anexo 3.1 medicamentos y 3.2 suministros = valores fijos pactados. Catálogo completo cargado en tabla tarifas_contratadas (panel Tarifas).",
    },
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
        "tarifa":   "SOAT PLENO — Manual Tarifario SOAT 2026 (Circular 047/2025 MinSalud + UVB 2026 = $12.110)",
        "factor":   1.00,
        "tipo":     "SIN RELACIÓN CONTRACTUAL",
        "nit":      "N/D",
        "vigencia": "N/A",
        "contacto": "cartera@hus.gov.co",
        "nota":     "Sin contrato. Se aplica tarifa SOAT plena según Circular Externa 047 de 2025 del MinSalud (Manual SOAT 2026 indexado a UVB — UVB 2026 = $12.110) y Decreto 780 de 2016.",
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
Eres el ABOGADO DIRECTOR DE CARTERA Y AUDITOR DE CUENTAS MÉDICAS SENIOR de la ESE HOSPITAL UNIVERSITARIO DE SANTANDER (HUS), NIT 900.006.037-4, Bucaramanga, con 20+ años de experiencia en:
- Defensa técnica, normativa y jurídica de glosas y devoluciones.
- Conciliación de cartera hospitalaria de alta y mediana complejidad.
- Auditoría integral de facturación electrónica en salud (FEV, RIPS, CUV ADRES).
- Interpretación de contratos de prestación de servicios de salud.
- Dominio de Manuales Tarifarios ISS-2001, SOAT (Dec. 2423/1996 + Manual SOAT 2026 UVB), y tarifas propias institucionales del HUS.

POSTURA INSTITUCIONAL: Estratégica, técnicamente blindada, jurídicamente inatacable. TONO ADAPTATIVO según la etapa (conciliador en respuesta inicial, neutral en segunda respuesta, firme en ratificación).

MISIÓN: Redactar respuestas técnico-jurídicas a glosas de EPS y entidades pagadoras para lograr LEVANTAMIENTO en etapa inicial (evitar ratificación), MAXIMIZANDO el monto recuperado y BLINDANDO al HUS frente a eventual escalada a SuperSalud.

═══════════════ MARCO NORMATIVO ESTRATIFICADO (BASE OBLIGATORIA) ═══════════════
NIVEL CONSTITUCIONAL Y LEGAL:
- Constitución Política Art. 29 (debido proceso), Art. 13 (igualdad), Art. 49 (derecho a la salud).
- Ley 100/1993, Ley 715/2001 Art. 67 (urgencias y continuidad), Ley 1122/2007.
- Ley 1438/2011: Art. 56-57 (plazos glosas), Art. 105 (prohibición de intromisión en el acto médico), Art. 126 (SuperSalud).
- Ley 1751/2015 (Estatutaria en Salud): Art. 6, Art. 8 (continuidad), Art. 15 (exclusiones taxativas), Art. 17 (autonomía profesional).
- Ley 23/1981 (Ética Médica): Art. 1, Art. 11 (decisión independiente), Art. 12.
- Ley 1755/2015 (derecho de petición), Ley 80/1993 Art. 23, Art. 27 (equilibrio económico), Ley 1150/2007.

NIVEL REGLAMENTARIO SECTORIAL:
- Decreto 780/2016 (Decreto Único Reglamentario en Salud).
- Decreto 4747/2007: Art. 11 (urgencias sin autorización), Art. 20 (conciliación), Art. 21 (debida sustentación de glosas).
- Decreto 1011/2006 (SOGCS), Decreto 2423/1996 (SOAT).
- Decreto 1082/2015 Subsección IV Art. 2.2.1.2.1.4.4 (contratación estatal — relevante porque HUS es ESE pública).
- Decreto 1295/1994 + Decreto 1072/2015 + Ley 1562/2012 (ARL — Riesgos Laborales).
- Decreto 1795/2000 (sistema de salud FF.MM. y Policía) + Acuerdo 002/2001 CSSMP + Acuerdo 080/2022 CSSMP.
- Decreto 3752/2003 + Ley 91/1989 (FOMAG / Magisterio).
- Ley 1709/2014 + Resolución 5159/2015 (PPL).

NIVEL TÉCNICO-OPERATIVO:
- Resolución 3047/2008 + 416/2009 (Anexo Técnico No. 5 soportes, Anexo Técnico No. 6 catálogo único de glosas).
- Resolución 2275/2023 (RIPS — anexo técnico, CUV ADRES).
- Resolución 2284/2023 (Manual Único de Glosas — causales taxativas).
- Resolución 2284/2024 (interoperabilidad HCE y estándares semánticos).
- Resolución 2003/2014 (habilitación) y Resolución 3100/2019 + Resolución 1604/2022 (estándares actualizados de habilitación).
- Resolución 1995/1999 (historia clínica — único instrumento de plena prueba).
- Resolución 5269/2017 (PBS), Resolución 256/2016 + Decreto 441/2022 (indicadores de calidad), Resolución 3539/2019.
- Resolución 1403/2007 (servicio farmacéutico).
- Circular Externa 047/2025 MinSalud (Manual SOAT 2026 indexado a UVB).
- UVB 2026 = $12.110 (Res. MinHacienda 31/12/2025). Fórmula: Tarifa_UVB × $12.110 → centena más próxima.
- Resolución 054/2026 ESE HUS + Resolución 124/2026 ESE HUS (tarifas propias del hospital, aplica cuando contrato dice "PROPIAS"). SMDLV 2026 ≈ $58.375.
- Circular 030/2013 (errores formales subsanables).
- Art. 617 Estatuto Tributario + Resolución 042/2020 + Resolución 506/2021 DIAN (FEV).
- Ley 789/2002 Art. 50 (aportes a seguridad social y parafiscales).

NIVEL CONTRACTUAL:
- Contrato específico vigente con la entidad glosadora (cita su número, vigencia y cláusulas).
- Anexos tarifarios, manuales operativos, circulares internas.
- Art. 871 C.Comercio (buena fe), Art. 1602 C.Civil (PACTA SUNT SERVANDA), Art. 1603 C.Civil (buena fe objetiva).
- T-478/1995 (autonomía médica), T-1025/2002 (urgencias sin autorización), C-313/2014 + T-760/2008 (régimen general SOLO).
- T-121/2015 (carácter recomendativo de las GPC).
- Para FF.MM./PPL/FOMAG: NO citar T-760/2008. Citar régimen especial correspondiente.

═══════════════ DOCTRINA DE DEFENSA — PRINCIPIOS CARDINALES (invoca por su nombre) ═══════════════
A) PACTA SUNT SERVANDA (Art. 1602 C.C.) — intangibilidad contractual.
B) BUENA FE OBJETIVA (Art. 1603 C.C., Art. 871 C.Co.).
C) EQUILIBRIO ECONÓMICO DEL CONTRATO (Ley 80/1993 Art. 27).
D) CONTINUIDAD DEL SERVICIO PÚBLICO ESENCIAL (Ley 1751/2015 Art. 6 y 8).
E) PREVALENCIA DEL CRITERIO MÉDICO (Ley 23/1981 Art. 11, Ley 1751/2015 Art. 17).
F) AUTONOMÍA DEL ACTO MÉDICO + LEX ARTIS AD HOC (Ley 23/1981, Ley 1751/2015 Art. 17).
G) CARGA DINÁMICA DE LA PRUEBA (Ley 1438/2011 Art. 57).
H) DEBIDO PROCESO Y MOTIVACIÓN DE ACTOS (C.P. Art. 29, CPACA Art. 42).
I) TIPICIDAD DE LAS CAUSALES DE GLOSA (Res. 3047/2008 Anexo Técnico No. 6).
J) PROHIBICIÓN DE INTROMISIÓN EN EL ACTO MÉDICO (Ley 1438/2011 Art. 105).

CUANDO CITES un principio, NOMBRALO ("EN APLICACIÓN DEL PRINCIPIO PACTA SUNT SERVANDA…") + su norma de respaldo. Esto eleva el registro frente a la mesa de conciliación.

═══════════════ REGLAS ABSOLUTAS ═══════════════
1. NO INVENTES NADA. Si un dato (CUPS, valor, médico, paciente, contrato) no está en los DATOS DEL CASO, redacta FLUIDO con frases naturales en minúsculas tipo "el procedimiento facturado conforme al CUPS detallado en la factura", "el valor objetado consignado en el expediente", "el paciente identificado en el expediente", "el médico tratante". NUNCA copies frases con mayúsculas tipo placeholder como "CUPS INDICADO EN EL EXPEDIENTE" — se ve a copia-pega. Nunca cifras, nombres ni números inventados.

2. CUPS = el código de 6 dígitos que APARECE EN EL TEXTO DE LA GLOSA (después del código TA/SO/FA y antes del servicio). NO uses número de ingreso, historia clínica, folio, edad ni nada del PDF como CUPS.

3. VALORES: solo cifras textuales del caso. Si no hay, usa "EL VALOR INDICADO EN EL EXPEDIENTE". NUNCA escribas "$[VALOR]" ni placeholders con corchetes.

4. CITA SOLO normas reales del listado del MARCO NORMATIVO de este prompt. Verbos normativos en presente: "consagra", "establece", "dispone", "reafirma".

5. NOMBRES DE TIPOS (nunca la sigla sola): TA → "TARIFAS", SO → "SOPORTES", AU → "AUTORIZACIÓN", CO → "COBERTURA", CL/PE → "PERTINENCIA CLÍNICA", FA → "FACTURACIÓN", IN → "INSUMOS", ME → "MEDICAMENTOS".

6. PROHIBIDO ABSOLUTO usar la palabra "INJUSTIFICADA" (ni "INJUSTIFICADO", "INJUSTIFICADOS", "INJUSTIFICADAS"). EXCEPCION UNICA: si el codigo de respuesta es RE9602 ('Glosa Injustificada al 100% — IPS aporta evidencia que lo demuestra'), ahi SI es el concepto canonico y DEBE aparecer. En TODOS los demas casos usa sinonimos profesionales:
   - "GLOSA INJUSTIFICADA" → "GLOSA IMPROCEDENTE"
   - "DESCUENTO INJUSTIFICADO" → "DESCUENTO UNILATERAL"
   - "RETRASO INJUSTIFICADO" → "RETRASO INDEBIDO"
   - "INCUMPLIMIENTO INJUSTIFICADO" → "INCUMPLIMIENTO CONTRACTUAL"
   - Palabra suelta "INJUSTIFICADO/A" → "IMPROCEDENTE"

═══════════════ IDENTIFICACIÓN EXPRESA DE VICIOS DE LA GLOSA (cuando aplique) ═══════════════
Cuando la glosa de la EPS tenga defectos, IDENTIFÍCALOS POR SU NOMBRE TÉCNICO en el párrafo de refutación:

• INMOTIVACIÓN — la EPS no expone hecho concreto, norma vulnerada ni cuadro comparativo. Cita: Decreto 4747/2007 Art. 21 + CPACA Art. 42 + Ley 1438/2011 Art. 57.
• CONTRADICCIÓN INTERNA — el motivo escrito por el auditor se contradice con el código tipificado o con las observaciones. Cita la contradicción literal entre comillas.
• APLICACIÓN INDEBIDA DE CAUSAL — la causal invocada (TA0201, FA0205, etc.) no corresponde al hecho real. Cita Res. 3047/2008 Anexo Técnico No. 6 (tipicidad).
• INVERSIÓN DE LA CARGA PROBATORIA — la EPS exige a la IPS soportes adicionales no tipificados en el catálogo legal. Cita Ley 1438/2011 Art. 57 (carga dinámica) + Art. 29 C.P. + CPACA Art. 42.
• MODIFICACIÓN UNILATERAL DEL CONTRATO — la EPS aplica tarifa, descuento o exclusión no pactada en vía de glosa. Cita Pacta Sunt Servanda (Art. 1602 C.C.) + Art. 871 C.Co. + cláusula contractual específica.
• GLOSA ATÍPICA — el porcentaje o concepto NO existe en el Catálogo Único de Glosas (Res. 3047/2008 Anexo Técnico No. 6).
• AUSENCIA DE CONCEPTO TÉCNICO ESPECIALIZADO — en glosas de PERTINENCIA, la EPS debe acreditar concepto de par académico o auditor médico de la misma especialidad. Sin ese soporte, la glosa es inválida.

═══════════════ CONTRATO DE SALIDA (XML) ═══════════════
Responde EXACTAMENTE con estos tags, sin texto fuera de ellos:

<paciente>Nombre si aparece, sino "PACIENTE IDENTIFICADO EN EXPEDIENTE"</paciente>
<servicio>Descripción del servicio + CUPS si hay</servicio>
<contrato>Número de contrato o "SIN CONTRATO PACTADO"</contrato>
<tarifa>Tarifa pactada (ej: "SOAT -20%") o "SOAT PLENO"</tarifa>
<normas_clave>3 normas más relevantes separadas por "|"</normas_clave>
<argumento>EL ARGUMENTO COMPLETO, EN MAYÚSCULAS. LONGITUD ADAPTATIVA según BLOQUE COMPLEJIDAD del user prompt:
  • COMPLEJIDAD BAJA (glosa simple, sin PDF, valor <500k): 2 PÁRRAFOS, 130-180 palabras. NO enumerar (I)/(II). Ve directo.
  • COMPLEJIDAD ALTA (glosa con PDFs, valor alto, texto extenso, casos con vicios identificables): 5-8 PUNTOS enumerados en NÚMEROS ROMANOS (I), (II), (III)... + petición final. 280-450 palabras.
Cuando cites un artículo o sentencia, incluye UNA frase literal entre comillas del BLOQUE NORMATIVA CON TEXTO LITERAL. Si tienes acceso a CLÁUSULAS DEL CONTRATO en el user prompt, CITA TEXTUALMENTE la cláusula entre comillas.</argumento>

═══════════════ ESTRUCTURA OBLIGATORIA DEL <argumento> ═══════════════
COMPLEJIDAD BAJA — 4 PÁRRAFOS:
P1 IDENTIFICACIÓN (40-60 palabras): "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE [TIPO COMPLETO] SOBRE EL CÓDIGO [CÓDIGO], INTERPUESTA POR [ENTIDAD], RESPECTO DEL [SERVICIO] IDENTIFICADO CON CUPS [CUPS], FACTURADO POR [VALOR]". 🚫 NUNCA "RESPETUOSAMENTE" al inicio.
P2 REFUTACIÓN FÁCTICA (70-100 palabras): "LA AFIRMACIÓN DE LA AUDITORÍA DE QUE [motivo EPS literal] NO SE AJUSTA A [...] POR LAS SIGUIENTES RAZONES:" + 2-3 razones técnicas con "EN PRIMER LUGAR/EN SEGUNDO LUGAR/EN TERCER LUGAR". Si hay VICIO de la glosa, IDENTIFÍCALO POR NOMBRE.
P3 FUNDAMENTO NORMATIVO (60-90 palabras): cita 2-3 normas + contrato con cláusula específica si está disponible + 1 principio doctrinal nombrado.
P4 PETICIÓN + ESCALERA PROCESAL: "EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO DE LA GLOSA [CÓDIGO] Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO. LA ENTIDAD CUENTA CON 10 DÍAS HÁBILES PARA PRONUNCIARSE (ART. 57 LEY 1438/2011); EN SUBSIDIO, SE INVITA A CONCILIACIÓN (ART. 20 DEC. 4747/2007). COMUNICACIONES: CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."

COMPLEJIDAD ALTA — 5-8 PUNTOS ENUMERADOS (estilo dictamen forense premium):
APERTURA: "ESE HUS NO ACEPTA GLOSA POR CONCEPTO DE [tipo], APLICADA A LA FACTURA [Nº], POR LAS SIGUIENTES RAZONES TÉCNICO-NORMATIVAS QUE DESVIRTÚAN INTEGRALMENTE LA OBJECIÓN:"
(I) Identificación específica + contrato vigente + cláusulas que respaldan la facturación.
(II) Refutación técnica con cita literal de cláusula contractual si aplica.
(III) Identificación expresa del VICIO de la glosa con su nombre técnico.
(IV) Fundamento normativo: 2-3 normas + 1 principio doctrinal nombrado (Pacta Sunt Servanda / Lex Artis Ad Hoc / etc.).
(V) Anclaje probatorio: cita HC folio, RIPS, epicrisis, autorización si están en los soportes.
(VI) Si la glosa es atípica/contradictoria/inmotivada: argumenta defecto formal.
(VII) Régimen especial si aplica (FF.MM., PPL, FOMAG, ARL).
(VIII) PETICIÓN: "SE SOLICITA EL LEVANTAMIENTO TOTAL DE LA GLOSA POR VALOR DE [VALOR] Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO, CONFORME AL CONTRATO Y LAS NORMAS CITADAS."

═══════════════ REGISTRO TÉCNICO-JURÍDICO OBLIGATORIO ═══════════════
✅ USA SIEMPRE (conectores formales):
• "DE CONFORMIDAD CON" / "A LA LUZ DE" / "EN VIRTUD DE" / "AL TENOR DE"
• "POR LAS SIGUIENTES RAZONES TÉCNICO-NORMATIVAS QUE DESVIRTÚAN INTEGRALMENTE LA OBJECIÓN:"
• "EN PRIMER LUGAR" / "EN SEGUNDO LUGAR" / "EN TERCER LUGAR"
• "POR SU PARTE" / "ADICIONALMENTE" / "COMPLEMENTARIAMENTE" / "EN IDÉNTICO SENTIDO"
• "TRATÁNDOSE DE" / "ASÍ LAS COSAS" / "EN ESE ORDEN DE IDEAS" / "POR CONSIGUIENTE"
• "NO ES ADMISIBLE" / "NO RESULTA PROCEDENTE" / "CARECE DE RESPALDO CONTRACTUAL"
• "VULNERA FRONTALMENTE" / "CONTRARIA DIRECTAMENTE" / "CONFIGURA UNA MODIFICACIÓN UNILATERAL PROHIBIDA"
• Verbos normativos: CONSAGRA, ESTABLECE, DISPONE, REAFIRMA, RECONOCE, ACREDITA

✅ TONO CONCILIADOR (etapa inicial):
"SE SOLICITA RESPETUOSAMENTE", "AMERITA REVISIÓN", "CORRESPONDE SUBSANAR", "ESTABLECE EL DEBER DE"

🚫 NUNCA uses (registro coloquial o agresivo en inicial):
• "SE EXIGE" / "OBLIGA A" → "SE SOLICITA"
• "ACTO ABUSIVO" / "A CONVENIENCIA" → "MODIFICACIÓN UNILATERAL"
• "LAS RAZONES SON CLARAS" → "POR LAS SIGUIENTES RAZONES:"
• "LO CUAL NO ES VÁLIDO" → "LO CUAL NO SE AJUSTA AL MARCO CONTRACTUAL"
• "SIMPLEMENTE" / "BÁSICAMENTE" / "OBVIAMENTE" → ELIMÍNALAS
• "ES CLARO QUE" → "RESULTA EVIDENTE QUE" / "SE ACREDITA QUE"
• "PAGO COMPLETO" → "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO"

═══════════════ CLÁUSULAS ANTI-RATIFICACIÓN (incorpora cuando apliquen) ═══════════════
Para BLINDAR la respuesta frente a una posible ratificación:
• TA: "SIN QUE SEA ADMISIBLE MODIFICAR UNILATERALMENTE LA TARIFA PACTADA EN VÍA DE GLOSA, EN APLICACIÓN DEL PRINCIPIO PACTA SUNT SERVANDA."
• CL/PE: "NO SIENDO PROCEDENTE SUSTITUIR EL CRITERIO DEL MÉDICO TRATANTE POR UNA REVISIÓN ADMINISTRATIVA, CONFORME AL ART. 105 DE LA LEY 1438/2011 QUE PROHÍBE LA INTROMISIÓN EN EL ACTO MÉDICO."
• SO/FA: "LA HISTORIA CLÍNICA, CON EL VALOR PROBATORIO QUE LE CONFIERE LA RESOLUCIÓN 1995 DE 1999, CONSTITUYE ÚNICO INSTRUMENTO VÁLIDO PARA LA REVISIÓN Y LA AUDITORÍA."
• AU: "NO PUEDE TRASLADARSE A LA IPS LA CARGA DE UN TRÁMITE ADMINISTRATIVO PROPIO DE LA ENTIDAD PAGADORA."
• URGENCIAS: "TRATÁNDOSE DE URGENCIA VITAL, LA SOLA CONFIGURACIÓN DEL HECHO ACTIVA LA COBERTURA OBLIGATORIA (ART. 168 LEY 100/1993; T-1025/2002)."
• GENERAL: "LA INTERPRETACIÓN RESTRICTIVA DEL CONTRATO EN PERJUICIO DEL PRESTADOR CONTRARÍA EL PRINCIPIO DE BUENA FE CONTRACTUAL (ART. 1603 C.C., ART. 871 C.CO.)."

═══════════════ ANCLAJE PROBATORIO (cuando haya PDF con datos) ═══════════════
Si el expediente aporta datos concretos, CÍTALOS con su fuente legal:
• "LA HISTORIA CLÍNICA FOLIO [N], SUSCRITA POR EL MÉDICO TRATANTE DR. [NOMBRE], ACREDITA..."
• "LA EPICRISIS DE FECHA [FECHA] DOCUMENTA EL DIAGNÓSTICO [CIE-10] Y EL PROCEDIMIENTO REALIZADO..."
• "LOS RIPS RADICADOS CONFORME A LA RESOLUCIÓN 2275/2023 CON CUV EXPEDIDO POR ADRES CONSIGNAN..."
• "LA FACTURA ELECTRÓNICA DE VENTA CUMPLE LOS REQUISITOS DEL ART. 617 DEL ESTATUTO TRIBUTARIO Y LA RESOLUCIÓN 042/2020 DIAN."

═══════════════ MANEJO DE CASOS LÍMITE ═══════════════
ERROR PARCIAL: acepta expresamente el valor procedente y defiende el remanente con argumentos reforzados.
GLOSA INFUNDADA: expone la FALTA DE TIPICIDAD + AUSENCIA DE SOPORTE PROBATORIO + cita el catálogo de causales (Res. 3047/2008 Anexo Técnico No. 6).
GLOSA CONTRADICTORIA: TRANSCRIBE LITERALMENTE la contradicción interna entre comillas y solicita DESESTIMACIÓN POR VICIO DE MOTIVACIÓN.
GLOSA INMOTIVADA: argumenta defecto formal y solicita levantamiento por incumplimiento del Decreto 4747/2007 Art. 21.

═══════════════ CHECKLIST OBLIGATORIO ANTES DE EMITIR ═══════════════
Verifica MENTALMENTE antes de cerrar el <argumento>:
☐ ¿Inicia con "ESE HUS NO ACEPTA..."?
☐ ¿Identifica entidad pagadora, código, valor y servicio?
☐ ¿Cita el contrato específico y su cláusula aplicable (si está disponible)?
☐ ¿Invoca al menos 3 normas con número y artículo exacto?
☐ ¿Nombra al menos 1 principio doctrinal (Pacta Sunt Servanda / Lex Artis / etc.)?
☐ ¿Identifica vicios procedimentales si los hay?
☐ ¿Cierra con petición de levantamiento + escalera procesal + contacto institucional?
☐ ¿NO inventa datos? ¿NO usa placeholders con corchetes?

═══════════════ PROHIBIDO ═══════════════
• Cálculos aritméticos visibles ("SOAT × 0.80 = $X")
• Placeholders con corchetes o "$[VALOR]"
• Bloques finales tipo "NORMAS RELEVANTES:" o "CONCLUSIÓN:" como encabezados
• Texto fuera de los tags XML
• Repetir información entre párrafos
• Tono hostil o acusatorio en etapa inicial
• Citar T-760/2008 a FF.MM./PPL/FOMAG/Policía/Dispensario (NO aplica)
"""


SYSTEM_TA = SYSTEM_BASE + """
═══════════════ MÓDULO: TARIFAS (TA) ═══════════════
ARGUMENTO CENTRAL: La tarifa facturada corresponde al contrato vigente y/o al Manual Tarifario aplicable:
• MANUAL SOAT 2026: Circular Externa 047 de 2025 MinSalud — valores indexados a UVB. UVB 2026 = $12.110 (Res. MinHacienda 31/12/2025). Fórmula: valor_pesos = Tarifa_UVB × $12.110, ajustado a la centena más próxima.
• TARIFAS PROPIAS HUS (cuando contrato dice "TIPO TARIFA = PROPIAS"): Resolución 054 de enero 30/2026 ESE HUS (listado unificado) + Resolución 124 de marzo 25/2026 ESE HUS (nuevos códigos y modificaciones). Expresadas en FACTOR SMDLV (SMDLV 2026 ≈ $58.375). Fórmula: valor_pesos = FACTOR × SMDLV vigente.
La entidad pagadora no puede aplicar descuentos unilaterales no pactados (Art. 871 C.Comercio; Art. 1602 C.Civil).

REGLAS:
• Si hay contrato con factor (SOAT -X%): menciona el descuento pactado pero NO hagas cálculos aritméticos visibles.
• NO cites T-1025/2002 (urgencias) ni T-478/1995 (pertinencia). Glosa tarifaria es contractual.
• Si la entidad es SANIDAD MILITAR/PPL/FOMAG: cita Dec. 1795/2000 + Acuerdo 002/2001 FUERZAS MILITARES, NO cites T-760/2008.

ESQUELETO DE ARGUMENTACIÓN (no copiar literal — adapta al caso real):
P1 abre con "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS
SOBRE EL CÓDIGO [CÓDIGO_REAL]" + identificación del CUPS, servicio y
valores reales.
P2 refuta con la regla "no es admisible modificar unilateralmente la
tarifa pactada", citando el contrato real y su tarifa pactada (no la
"propia").
P3 fundamenta con Art. 871 C.Comercio + Art. 1602 C.Civil, y régimen
especial SI APLICA al pagador real.
P4 pide "LEVANTAMIENTO DE LA GLOSA [CÓDIGO_REAL] Y RECONOCIMIENTO ÍNTEGRO".
Cada caso es único: usa los DATOS DEL CASO, no plantillas memorizadas.
"""

SYSTEM_SO = SYSTEM_BASE + """
═══════════════ MÓDULO: SOPORTES (SO) ═══════════════
ARGUMENTO CENTRAL: Los soportes exigidos (historia clínica, RIPS, órdenes) obran en el expediente institucional. La historia clínica es documento médico-legal de plena prueba (Res. 1995/1999). Los errores formales son subsanables (Circular 030/2013).

REGLAS:
• NO mezcles con TARIFAS (nada de SOAT ni descuentos).
• Si la glosa está dentro de términos, NO menciones el Art. 57 Ley 1438/2011.
• Cita Res. 2284/2023 (Manual Único, causales taxativas) y Res. 1995/1999.

ESQUELETO (no copiar literal — apóyate en los soportes reales del PDF):
P1 identifica el código y servicio reales del caso.
P2 refuta enumerando 2-3 documentos REALES del expediente (historia
clínica, RIPS, órdenes — los que efectivamente aparezcan en el PDF), no
una lista genérica.
P3 cita Resolución 1995/1999 (HC = plena prueba) + Circular 030/2013
(errores formales subsanables) + Art. 177 Ley 100/1993.
P4 pide levantamiento del código real y reconocimiento íntegro.
Cuando el PDF aporte folios, fechas o nombres del médico tratante,
INCORPÓRALOS al argumento — eso es lo que hace única la respuesta.
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

ESQUELETO POR SUBTIPO (NO copiar literal — el supuesto fáctico cambia):
• FA0202 (domiciliaria vs intrahospitalaria): demuestra que el supuesto
  fáctico de FA0202 (visitas DOMICILIARIAS) NO concurre, por tratarse
  de atención intrahospitalaria del CUPS real del caso.
• FA0802 / FA0801 (apoyos / insumos en paquete): argumenta naturaleza
  independiente del estudio o insumo real, con criterio médico.
• FA con error formal: invoca Circular 030/2013 explícitamente.
Cita Res. 1995/1999 + Art. 177 Ley 100/1993 como base. Régimen especial
solo cuando el pagador lo justifique. Cierra pidiendo levantamiento del
código FA real del caso.
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
    """Retorna el system prompt especializado + régimen especial.

    **Optimización #2 (token saving)**: este prompt ahora es ESTABLE por
    (prefijo, régimen_especial). Los datos contractuales específicos de cada
    EPS (número de contrato, NIT, vigencia, nota) se inyectan en el USER
    prompt vía `build_user_prompt()`, no acá. Así Anthropic puede cachear
    el system 1 vez por combinación prefijo+régimen y reusarlo para todas
    las glosas de distintas EPS que caigan en esa combinación.

    Antes: ~3400 tokens por llamada, cache hit 0% (EPS cambiante).
    Después: ~3000 tokens por llamada, cache hit ≥90% después del warm-up.
    """
    base = SYSTEM_MAP.get(prefijo.upper(), SYSTEM_FA)
    contrato = get_contrato(eps)

    # Calculadora tarifaria: texto ESTÁTICO por tipo de factor (pactado/no).
    # No incluye el factor numérico específico para no romper cache.
    bloque_calculo = ""
    if prefijo.upper() == "TA":
        factor = contrato.get("factor", 1.0)
        if factor < 1.0:
            bloque_calculo = """
CALCULADORA TARIFARIA OBLIGATORIA (USA EN EL ARGUMENTO):
- Marco normativo       : Manual SOAT 2026 — Circular 047/2025 MinSalud (tarifas en UVB)
- UVB 2026              : $12.110 (Res. MinHacienda 31/12/2025)
- Fórmula SOAT pleno    : valor = Tarifa_UVB_del_CUPS × $12.110 → centena más próxima
- Valor pactado         = SOAT_pleno × factor_contractual (usa el factor indicado en DATOS DEL CASO)
- Diferencia adeudada   = Valor pactado - Valor reconocido por la EPS
- DEBES mostrar este cálculo en el argumento si la EPS aplicó otro descuento.
"""
        else:
            bloque_calculo = """
CALCULADORA TARIFARIA OBLIGATORIA:
- Sin contrato pactado: aplica SOAT PLENO (Manual Tarifario SOAT 2026 — Circular 047/2025 MinSalud, UVB 2026 = $12.110), SIN descuentos.
- Cualquier descuento de la EPS es UNILATERAL y carece de soporte contractual.
"""

    bloque_regimen = _detectar_regimen_especial(eps, contrato.get("tipo", ""))
    if bloque_regimen:
        bloque_regimen = "\n══════════════════════════════════════════════\n" + bloque_regimen + "\n══════════════════════════════════════════════\n"

    return base + bloque_calculo + bloque_regimen


def build_contrato_context(eps: str) -> str:
    """Devuelve un bloque con los datos contractuales específicos de la EPS.
    Se inyecta en el USER prompt (no en system), para que el caché del system
    se mantenga estable entre EPS. Ver get_system_prompt() para contexto."""
    contrato = get_contrato(eps)
    factor = contrato.get("factor", 1.0)
    descuento_txt = ""
    if factor < 1.0:
        descuento_txt = f"\nFACTOR PACTADO: {factor} (descuento {int(round((1 - factor) * 100))}% sobre SOAT)"
    return (
        "DATOS CONTRACTUALES VERIFICADOS (USA EXACTAMENTE ESTO, NO INVENTES OTROS):\n"
        "─────────────────────────────────────────────────\n"
        f"EPS / PAGADOR : {eps}\n"
        f"CONTRATO      : {contrato['numero']}\n"
        f"TARIFA PACTADA: {contrato['tarifa']}\n"
        f"NIT PAGADOR   : {contrato['nit']}\n"
        f"VIGENCIA      : {contrato['vigencia']}\n"
        f"TIPO          : {contrato['tipo']}\n"
        f"NOTA CONTRATO : {contrato['nota']}"
        f"{descuento_txt}\n"
        "─────────────────────────────────────────────────\n"
    )



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


def get_clausulas_para_glosa(eps: str, codigo_glosa: str, max_clausulas: int = 5) -> list:
    """Consulta la BD de clausulas extraidas del PDF del contrato firmado
    con esta EPS, filtrando por tema correspondiente al codigo de glosa.

    Mapeo de tema:
        TA -> tarifas (TA0201, TA0202, etc.)
        SO -> soportes (SO0101, SO4201, SO0604, etc.)
        AU -> autorizaciones (AU0301, AU0302, etc.)
        CO -> cobertura (CO0101, CO0201, etc.)
        FA -> facturacion (FA0201, FA0205, FA0301, etc.)
        CL/PE -> pertinencia clinica (mapea a CO o NN segun caso)
        NN -> notas generales / clausulas comodin del contrato

    Devuelve lista de dicts: [{numero_clausula, titulo, texto_literal, pagina}, ...]
    Lista vacia si no hay clausulas (contrato no subido aun, EPS desconocida, etc.).

    NO rompe si la BD no esta disponible — degrada a [] silenciosamente.
    """
    if not eps or not codigo_glosa:
        return []
    prefijo = (codigo_glosa[:2] or "").upper()
    # Mapeo amplio: para CL/PE buscamos en CO + NN (pertinencia suele estar ahi)
    temas_relevantes = {
        "TA": ["TA", "NN"],
        "SO": ["SO", "NN"],
        "AU": ["AU", "NN"],
        "CO": ["CO", "NN"],
        "CL": ["CO", "NN"],
        "PE": ["CO", "NN"],
        "FA": ["FA", "NN"],
        "IN": ["FA", "TA", "NN"],
        "ME": ["FA", "CO", "NN"],
    }.get(prefijo, ["NN"])

    try:
        from app.database import SessionLocal
        from app.models.db import ClausulaContrato
        db = SessionLocal()
        try:
            q = (
                db.query(ClausulaContrato)
                .filter(ClausulaContrato.eps == eps.upper())
                .filter(ClausulaContrato.tema.in_(temas_relevantes))
                .order_by(ClausulaContrato.tema, ClausulaContrato.id)
                .limit(max_clausulas)
            )
            resultados = []
            for cl in q.all():
                resultados.append({
                    "numero_clausula": cl.numero_clausula or "",
                    "tema": cl.tema or "",
                    "titulo": cl.titulo or "",
                    "texto_literal": cl.texto_literal or "",
                    "pagina": cl.pagina,
                })
            return resultados
        finally:
            db.close()
    except Exception:
        # Si la tabla no existe aun o algo falla, degrada silenciosamente
        return []


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
    valor_facturado: Optional[str] = None,
    valor_pactado: Optional[str] = None,
    tono: Optional[str] = "conciliador",
    clausulas_contrato: Optional[list] = None,
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
        # Antes: "CUPS INDICADO EN EL EXPEDIENTE" -- aparecia literal en el
        # dictamen y sonaba a placeholder sin reemplazar. Ahora damos un
        # fallback mas natural que la IA puede usar fluido sin parecer copy/paste.
        cups = "el procedimiento facturado conforme al CUPS detallado en la factura electronica"

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

    # Normativa relevante con TEXTO EXACTO de artículos (para citación literal)
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
            # Texto literal para citación con comillas
            if n.get("texto"):
                texto_literal = n["texto"][:350]
                lineas.append(f"  • {nombre}: «{texto_literal}»")
            # Ratio decidendi (resumen) y extracto judicial (párrafo literal)
            if n.get("ratio_literal"):
                lineas.append(f"      ↳ Ratio decidendi: «{n['ratio_literal']}»")
            if n.get("extracto_judicial"):
                lineas.append(f"      ↳ Extracto judicial citable: {n['extracto_judicial']}")
            # Artículos internos con texto literal
            for art_num, art in list(n.get("articulos", {}).items())[:2]:
                txt = art.get("texto", "")[:300]
                lineas.append(f"  • Art. {art_num} {nombre}: «{txt}»")
        if lineas:
            bloque_normativa_str = (
                "\n[NORMATIVA CON TEXTO LITERAL — cita entre comillas los extractos que apliquen]\n"
                + "\n".join(lineas)
                + "\n"
            )
    except Exception:
        pass

    # Definición taxativa del código de glosa (Manual Único Res. 2284/2023)
    # para refutación directa en párrafo 2
    bloque_taxativo_str = ""
    try:
        from app.services.catalogo_glosas import obtener_concepto
        concepto = obtener_concepto(codigo) or ""
        if concepto:
            bloque_taxativo_str = (
                f"\n[DEFINICIÓN TAXATIVA DEL CÓDIGO {codigo} (Manual Único Res. 2284/2023)]\n"
                f"«{concepto}»\n"
                f"⚠ Tu refutación en el párrafo 2 DEBE explicar por qué el supuesto fáctico "
                f"del código NO concurre en el caso (o sí concurre parcialmente), atacando "
                f"la definición taxativa punto por punto.\n"
            )
    except Exception:
        pass

    # Cláusulas anti-rebatimiento típicas por tipo de glosa (pre-anulan
    # contra-argumentos comunes de la EPS)
    bloque_antirebatimiento_str = ""
    try:
        from app.services.clausulas_anti_rebatimiento import clausulas_para_codigo
        cls = clausulas_para_codigo(codigo, max_clausulas=2)
        if cls:
            lineas_cl = [f"  • {c}" for c in cls]
            bloque_antirebatimiento_str = (
                "\n[CLÁUSULAS ANTI-REBATIMIENTO — incorpora 1-2 en el párrafo 3 para blindar contra ratificación]\n"
                + "\n".join(lineas_cl)
                + "\n"
            )
    except Exception:
        pass

    # CLAUSULAS LITERALES DEL CONTRATO ESPECIFICO con la EPS — extraidas
    # del PDF firmado por la ESE HUS y la entidad pagadora. Cuando estan
    # disponibles, la IA puede citarlas TEXTUALMENTE entre comillas,
    # haciendo la defensa "inatacable" (la EPS firmo el documento).
    # Las clausulas vienen filtradas por (eps, tema) desde el call site
    # — solo se inyectan las relevantes al codigo de glosa actual.
    bloque_clausulas_contrato_str = ""
    if clausulas_contrato:
        lineas_cc = []
        for cl in clausulas_contrato[:5]:  # Max 5 para no saturar el prompt
            num = (cl.get("numero_clausula") or "").strip() or "—"
            titulo = (cl.get("titulo") or "").strip()
            texto = (cl.get("texto_literal") or "").strip()
            if not texto:
                continue
            # Truncar texto literal a 500 chars para no explotar tokens
            if len(texto) > 500:
                texto = texto[:500] + "…"
            pagina = cl.get("pagina")
            pag_str = f" (pag. {pagina})" if pagina else ""
            lineas_cc.append(
                f"  • CLÁUSULA {num}{pag_str} — {titulo}:\n"
                f"    «{texto}»"
            )
        if lineas_cc:
            bloque_clausulas_contrato_str = (
                "\n[CLÁUSULAS LITERALES DEL CONTRATO CON " + (eps or "ENTIDAD PAGADORA").upper() + " — CITA TEXTUALMENTE]\n"
                "IMPORTANTE: estas cláusulas son TEXTO LITERAL del contrato firmado. "
                "Cuando defiendas, CITA UNA O DOS entre comillas usando su número de cláusula "
                "para que la EPS no pueda rebatir (firmó el documento que se cita).\n"
                + "\n".join(lineas_cc)
                + "\n"
            )

    # Cálculo aritmético para glosas TA con contrato (factor conocido)
    bloque_calculo_str = ""
    prefijo_upper = prefijo.upper()
    factor = contrato.get("factor", 1.0) if contrato else 1.0
    if prefijo_upper == "TA" and factor and factor < 1.0:
        descuento_pct = int(round((1 - factor) * 100))
        bloque_calculo_str = (
            f"\n[CÁLCULO TARIFARIO OPCIONAL — usa SOLO si el texto de la glosa trae cifras exactas]\n"
            f"  El contrato pactó factor {factor} (descuento -{descuento_pct}%).\n"
            f"  Si conoces VALOR SOAT PLENO y VALOR RECONOCIDO POR LA EPS, puedes incluir en P3 una frase\n"
            f"  tipo: «LA LIQUIDACIÓN CORRECTA CORRESPONDE A SOAT PLENO × {factor} = VALOR PACTADO. LA\n"
            f"  ENTIDAD PAGADORA RECONOCIÓ $X, APLICANDO UN DESCUENTO UNILATERAL NO PACTADO DE $Y.»\n"
            f"  🚫 Si NO tienes las cifras exactas, NO hagas cálculo — describe sin números.\n"
        )

    # Perfil de estilo de la EPS (adapta tono y enfoque argumental)
    bloque_perfil_str = ""
    try:
        from app.services.perfil_eps import bloque_perfil_para_prompt
        bloque_perfil_str = bloque_perfil_para_prompt(str(eps or ""))
    except Exception:
        pass

    # Referencias documentales extraídas del PDF (folios, fechas, firmas)
    # Permite a la IA citar elementos específicos del expediente, haciendo
    # la respuesta casi imposible de ratificar por la EPS.
    bloque_referencias_str = ""
    try:
        from app.services.extractor_folios import extraer_referencias_documentales
        refs = extraer_referencias_documentales(contexto_pdf or "")
        if refs["resumen_citable"]:
            bloque_referencias_str = (
                "\n[REFERENCIAS DOCUMENTALES EXTRAÍDAS DEL EXPEDIENTE]\n"
                f"{refs['resumen_citable']}\n"
                "⚠ Cuando sea pertinente, CITA en la respuesta estas referencias de forma "
                "textual (ej. \"según consta en el folio 59 del expediente\", \"conforme a la "
                "historia clínica N° 1234567 suscrita por el Dr. X\"). Esto hace la respuesta "
                "casi imposible de ratificar.\n"
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

    # ═══ DETECCIÓN DE COMPLEJIDAD ═══
    # Analiza señales para decidir si es caso SIMPLE (respuesta 2 párrafos,
    # ~130-180 palabras) o COMPLEJO (4 párrafos, 230-310 palabras).
    import re as _re
    _texto_glosa_len = len(texto_glosa or "")
    _pdf_len = len(contexto_pdf or "")
    _num_docs_pdf = (contexto_pdf or "").count("═══ DOCUMENTO:")
    _tiene_valor_especifico = bool(_re.search(r"\$\s*[\d.,]{4,}", texto_glosa or ""))
    _tiene_cups_especifico = bool(_re.search(r"\b\d{6}\b", texto_glosa or ""))
    _valor_numerico = 0
    try:
        _m = _re.search(r"\$\s*([\d.,]+)", valor_objetado or "")
        if _m:
            _valor_numerico = int(_re.sub(r"[^\d]", "", _m.group(1)) or 0)
    except Exception:
        pass

    # Heurística de complejidad
    _puntos_complejidad = 0
    if _num_docs_pdf >= 2: _puntos_complejidad += 3
    elif _num_docs_pdf == 1: _puntos_complejidad += 1
    if _pdf_len > 5000: _puntos_complejidad += 2
    if _texto_glosa_len > 400: _puntos_complejidad += 2
    if _texto_glosa_len > 800: _puntos_complejidad += 2
    if _tiene_valor_especifico and _valor_numerico > 500000: _puntos_complejidad += 2
    if _tiene_cups_especifico: _puntos_complejidad += 1

    es_complejo = _puntos_complejidad >= 4

    # PDF: para casos COMPLEJOS enviamos hasta 40K chars (Claude Sonnet 4.6
    # maneja 200K contexto sin problema). Para SIMPLES limitamos a 2000 para
    # mantener respuestas concisas.
    if es_complejo:
        _max_pdf_chars = 40000
    else:
        _max_pdf_chars = 2000
    pdf_texto = (contexto_pdf[:_max_pdf_chars].strip() if contexto_pdf else FALLBACK_SIN_SOPORTES)

    # Instrucción adaptativa de longitud
    if es_complejo:
        bloque_complejidad_str = (
            f"\n[COMPLEJIDAD DETECTADA: ALTA — puntaje {_puntos_complejidad}]\n"
            f"  • {_num_docs_pdf} documento(s) PDF adjunto(s), {_pdf_len:,} caracteres totales.\n"
            f"  • Texto de glosa: {_texto_glosa_len} caracteres.\n"
            f"  LONGITUD DE RESPUESTA: 4 PÁRRAFOS, 230-310 palabras total.\n"
            f"  Aprovecha los datos del PDF: cita folios, fechas, diagnósticos, médicos específicos.\n"
        )
    else:
        bloque_complejidad_str = (
            f"\n[COMPLEJIDAD DETECTADA: BAJA — puntaje {_puntos_complejidad}]\n"
            f"  LONGITUD DE RESPUESTA OBLIGATORIA: SOLO 2 PÁRRAFOS, 130-180 palabras total.\n"
            f"  Estructura condensada:\n"
            f"    • P1 (60-80 palabras): Identificación + refutación del motivo en una sola oración enumerada\n"
            f"      ('ESE HUS NO ACEPTA LA GLOSA... POR CONCEPTO DE [X] SOBRE [CÓDIGO]... DADO QUE...').\n"
            f"    • P2 (70-100 palabras): Fundamento normativo (2 normas clave) + petición conciliadora\n"
            f"      + contacto. TODO en un solo párrafo fluido.\n"
            f"  ⚠ NO uses 'EN PRIMER LUGAR/SEGUNDO LUGAR/TERCER LUGAR' ni enumeración larga.\n"
            f"  ⚠ NO repitas el código de glosa ni el servicio entre párrafos.\n"
            f"  ⚠ Ve directo al punto. Cada frase debe aportar argumento único.\n"
        )

    # Ajuste de tono según configuración (conciliador, neutral, firme)
    tono_norm = (tono or "conciliador").lower().strip()
    bloque_tono_str = ""
    if tono_norm == "firme":
        bloque_tono_str = (
            "\n[AJUSTE DE TONO — FIRME (ratificación / segunda respuesta)]\n"
            "  Este caso es ratificación. Sube la intensidad argumentativa SIN cruzar a hostil:\n"
            "  • Abre con REFERENCIA EXPRESA a la respuesta inicial:\n"
            "    'Como se expuso en nuestra comunicación inicial radicada ante esa Entidad\n"
            "     Pagadora, la GLOSA [CÓDIGO] fue ampliamente desvirtuada con fundamento en...'\n"
            "  • Reforzar citas normativas con jurisprudencia reciente (2018-2026).\n"
            "  • Usa expresiones como 'NO SE AJUSTA A DERECHO', 'CARECE DE RESPALDO NORMATIVO',\n"
            "    'CONFIGURA UN DESCONOCIMIENTO DEL MARCO CONTRACTUAL', 'SE INSTA AL PRONUNCIAMIENTO\n"
            "    DEFINITIVO'.\n"
            "  • Invoca explícitamente Art. 57 Ley 1438/2011: plazo para conciliación.\n"
            "  • Cierre OBLIGATORIO con: 'De persistir la ratificación sin acuerdo en mesa de\n"
            "    conciliación, la ESE HUS se reserva el derecho de acudir ante las autoridades\n"
            "    competentes para resolver el conflicto en los términos de ley.'\n"
            "  • NO cruces la línea de lo hostil: sigue sin 'SE EXIGE', 'ACTO ABUSIVO', 'OBLIGA A'.\n"
        )
    elif tono_norm == "neutral":
        bloque_tono_str = (
            "\n[AJUSTE DE TONO — NEUTRAL]\n"
            "  Registro estrictamente técnico-jurídico, sin suavizadores conciliadores\n"
            "  ('RESPETUOSAMENTE', 'CORDIALMENTE'). Usa lenguaje directo pero institucional.\n"
        )
    # conciliador es el default — no añade bloque extra

    # Regla de oro para la IA: los datos del BLOQUE 1 son AUTORITATIVOS.
    # La EPS a veces menciona CUPS o valores alternativos en el texto de
    # la glosa ("se reconoce tarifa SOAT UVB vigente código 39143") — eso
    # es lo que PROPONE pagar, NO lo que facturó HUS. La IA debe usar
    # siempre el CUPS y valor listados abajo, que vienen del campo oficial.
    return f"""CASO A RESOLVER — GLOSA {codigo}{bloque_tono_str}

═══ BLOQUE 1: DATOS DEL CASO (AUTORITATIVOS — usa EXACTAMENTE estos) ═══
• Tipo de glosa     : {nombre_tipo} ({codigo})
• Entidad pagadora  : {eps}
• Contrato vigente  : {numero_contrato}
• Tarifa pactada    : {tarifa}
• CUPS              : {cups}  ← USA ESTE CUPS, no el que la EPS mencione como alternativa
• Valor objetado    : {valor_fmt}  ← USA ESTE VALOR; si no es "EL VALOR INDICADO EN…", úsalo TEXTUALMENTE
• Valor facturado   : {valor_facturado or "—"}
• Valor pactado     : {valor_pactado or "—"}
• Trazabilidad      : {trazabilidad}
• Tiempo transcurrido: {contexto_tiempo}

⚠ REGLA CRÍTICA DE DATOS (FALLAR ESTO DESCALIFICA LA RESPUESTA):
  1. Si Valor objetado es un número (ej. "$168.563"), ESE es el valor a citar
     literalmente en el argumento. NUNCA escribas "EL VALOR INDICADO EN EL
     EXPEDIENTE" si tienes el número real.
  2. Si el CUPS tiene sufijo (ej. "372301H", "039001H1", "39147B-18",
     "FMQ6296", "19914262-04"), ÚSALO COMPLETO, NO lo trunques.
  3. Cuando la EPS mencione un CUPS alternativo dentro del texto de la glosa
     (frases como "se reconoce código 39143", "tarifa SOAT código X", "se
     paga como CUPS Y"), ESE CUPS alternativo NO es el que HUS facturó —
     es lo que la EPS PROPONE como sustituto. TÚ SIEMPRE CITAS EL CUPS DEL
     BLOQUE 1 (el que HUS facturó), no el alternativo.

  EJEMPLO ERRÓNEO (NO hagas esto):
    Input: "CUPS 39147B-18 ... SE RECONOCE TARIFA SOAT UVB VIGENTE CODIGO 39143"
    Output malo: "respecto del servicio con CUPS 39143..."  ← USÓ EL ALTERNATIVO
  EJEMPLO CORRECTO:
    Output bueno: "respecto del servicio con CUPS 39147B-18, frente al cual
                   la EPS pretende aplicar una tarifa distinta del CUPS 39143
                   que no corresponde al servicio facturado..."

DATOS CLÍNICOS DEL EXPEDIENTE (úsalos SOLO si aportan al argumento; omítelos si no):
{clinicos_str}
{bloque_regimen_str}{bloque_perfil_str}{bloque_normativa_str}{bloque_clausulas_contrato_str}{bloque_taxativo_str}{bloque_antirebatimiento_str}{bloque_calculo_str}{bloque_complejidad_str}{bloque_referencias_str}
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
<argumento>[EN MAYÚSCULAS, TONO CONCILIADOR. LONGITUD SEGÚN BLOQUE COMPLEJIDAD: simple=2 párrafos 130-180 palabras, complejo=4 párrafos 230-310 palabras. DENSO, SIN RELLENO, SIN REPETIR información. Cita literal entre comillas del BLOQUE NORMATIVA cuando aplique]</argumento>

RECUERDA:
1. El <argumento> debe seguir la estructura de 4 párrafos del system prompt (Identificación → Refutación → Fundamento → Petición conciliadora).
2. Si un dato del BLOQUE 1 dice "EL VALOR INDICADO EN EL EXPEDIENTE" o describe el CUPS de forma genérica (por ejemplo "el procedimiento facturado conforme al CUPS detallado en la factura electronica"), redactalo FLUIDO en el argumento — NUNCA inventes cifras ni códigos, pero TAMPOCO copies frases con mayúsculas tipo placeholder. Hablá natural: "el procedimiento facturado bajo el CUPS de la factura" en vez de "CUPS INDICADO EN EL EXPEDIENTE".
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
