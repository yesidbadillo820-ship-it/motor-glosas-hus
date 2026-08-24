"""Router de consulta normativa — R79 P2.

Endpoints:
  POST /consulta-normativa                    — busca en la biblioteca normativa.
  GET  /consulta-normativa/normas             — lista el índice de normas.
  GET  /consulta-normativa/normas/export.json — exporta catálogo completo de normas.
"""

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import get_usuario_actual, get_auditor_o_superior
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/consulta-normativa", tags=["consulta-normativa"])


# Palabras vacías que no aportan a la búsqueda (no penalizan ni suman).
_STOPWORDS = {
    "que",
    "cual",
    "cuales",
    "como",
    "para",
    "por",
    "los",
    "las",
    "del",
    "una",
    "uno",
    "con",
    "sin",
    "the",
    "and",
    "es",
    "el",
    "la",
    "de",
    "en",
    "se",
    "su",
    "al",
    "lo",
    "un",
    "dice",
    "norma",
    "ley",
    "art",
    "articulo",
    "sobre",
    "cuando",
    "donde",
    "regula",
    "aplica",
    "que",
    "hay",
}


def _norm_txt(s: str) -> str:
    """Lowercase + sin tildes + solo alfanumérico/espacios."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens_consulta(pregunta: str) -> list[str]:
    return [t for t in _norm_txt(pregunta).split() if len(t) >= 3 and t not in _STOPWORDS]


def _buscar_normas(pregunta: str, limite: int = 8) -> list[dict]:
    """Búsqueda por coincidencia de términos sobre nombre + título + keywords
    de CATALOGO_NORMAS. Scoring simple y explicable (sin dependencias):
      • +3 si un término aparece en el nombre de la norma
      • +2 si aparece en una keyword
      • +1 si aparece en el título
    Devuelve las `limite` normas con mayor score (>0), ordenadas desc.
    """
    tokens = _tokens_consulta(pregunta)
    if not tokens:
        return []
    resultados = []
    for n in CATALOGO_NORMAS:
        nombre_n = _norm_txt(n.get("nombre", ""))
        titulo_n = _norm_txt(n.get("titulo", ""))
        kws_n = [_norm_txt(k) for k in (n.get("keywords") or [])]
        kws_join = " ".join(kws_n)
        score = 0
        for t in tokens:
            if t in nombre_n:
                score += 3
            if t in kws_join:
                score += 2
            if t in titulo_n:
                score += 1
        if score > 0:
            resultados.append((score, n))
    resultados.sort(key=lambda x: x[0], reverse=True)
    salida = []
    for score, n in resultados[: max(1, min(limite, 25))]:
        salida.append(
            {
                "norma": n.get("nombre", ""),
                "articulo": None,
                "titulo": n.get("titulo", ""),
                "texto": ", ".join(n.get("keywords") or [])[:300],
                "aplicacion": None,
                "vigente": bool(n.get("vigente", True)),
                "score": score,
            }
        )
    return salida


class ConsultaNormativaInput(BaseModel):
    pregunta: str
    limite: Optional[int] = 8


# Catálogo canónico de normas del marco normativo HUS
# Incluye todas las normas referenciadas en el system prompt de la IA
# y el manual de glosas (>= 100 normas, requisito R52 B).
CATALOGO_NORMAS = [
    # ─── NIVEL CONSTITUCIONAL ───
    {
        "clave": "CONSTITUCION POLITICA ART 29",
        "nombre": "Constitución Política de Colombia — Art. 29",
        "titulo": "Derecho al debido proceso",
        "vigente": True,
        "keywords": ["debido proceso", "constitución", "derechos fundamentales"],
    },
    {
        "clave": "CONSTITUCION POLITICA ART 13",
        "nombre": "Constitución Política de Colombia — Art. 13",
        "titulo": "Derecho a la igualdad",
        "vigente": True,
        "keywords": ["igualdad", "constitución", "derechos fundamentales"],
    },
    {
        "clave": "CONSTITUCION POLITICA ART 49",
        "nombre": "Constitución Política de Colombia — Art. 49",
        "titulo": "Derecho a la salud y saneamiento ambiental",
        "vigente": True,
        "keywords": ["salud", "constitución", "derecho a la salud"],
    },
    # ─── LEYES ───
    {
        "clave": "LEY 100 DE 1993",
        "nombre": "Ley 100 de 1993",
        "titulo": "Sistema de Seguridad Social Integral",
        "vigente": True,
        "keywords": [
            "seguridad social",
            "salud",
            "EPS",
            "IPS",
            "Art. 177",
            "Art. 168",
            "urgencias",
        ],
    },
    {
        "clave": "LEY 715 DE 2001",
        "nombre": "Ley 715 de 2001",
        "titulo": "Sistema General de Participaciones — Art. 67 urgencias y continuidad",
        "vigente": True,
        "keywords": ["participaciones", "urgencias", "continuidad", "Art. 67"],
    },
    {
        "clave": "LEY 1122 DE 2007",
        "nombre": "Ley 1122 de 2007",
        "titulo": "Modificaciones al Sistema General de Seguridad Social en Salud",
        "vigente": True,
        "keywords": ["SGSSS", "EPS", "glosas", "salud"],
    },
    {
        "clave": "LEY 1438 DE 2011",
        "nombre": "Ley 1438 de 2011",
        "titulo": "Reforma al Sistema General de Seguridad Social en Salud — Arts. 56-57 plazos glosas",
        "vigente": True,
        "keywords": [
            "glosas",
            "plazos",
            "conciliación",
            "Art. 56",
            "Art. 57",
            "Art. 105",
            "Art. 126",
            "SuperSalud",
        ],
    },
    {
        "clave": "LEY 1751 DE 2015",
        "nombre": "Ley 1751 de 2015",
        "titulo": "Ley Estatutaria en Salud — Arts. 6, 8, 15, 17",
        "vigente": True,
        "keywords": ["estatutaria", "salud", "continuidad", "exclusiones", "autonomía médica"],
    },
    {
        "clave": "LEY 23 DE 1981",
        "nombre": "Ley 23 de 1981",
        "titulo": "Ética Médica — Arts. 1, 11, 12",
        "vigente": True,
        "keywords": ["ética médica", "autonomía", "acto médico"],
    },
    {
        "clave": "LEY 1755 DE 2015",
        "nombre": "Ley 1755 de 2015",
        "titulo": "Derecho fundamental de petición",
        "vigente": True,
        "keywords": ["petición", "derecho", "respuesta"],
    },
    {
        "clave": "LEY 80 DE 1993",
        "nombre": "Ley 80 de 1993",
        "titulo": "Estatuto General de Contratación — Arts. 23, 27 equilibrio económico",
        "vigente": True,
        "keywords": ["contratación", "equilibrio económico", "contratos públicos"],
    },
    {
        "clave": "LEY 1150 DE 2007",
        "nombre": "Ley 1150 de 2007",
        "titulo": "Eficiencia y transparencia en la Ley 80 de 1993",
        "vigente": True,
        "keywords": ["contratación", "transparencia", "eficiencia"],
    },
    {
        "clave": "LEY 789 DE 2002",
        "nombre": "Ley 789 de 2002",
        "titulo": "Reformas de seguridad social — Art. 50 aportes parafiscales",
        "vigente": True,
        "keywords": ["seguridad social", "parafiscales", "aportes", "Art. 50"],
    },
    {
        "clave": "LEY 1562 DE 2012",
        "nombre": "Ley 1562 de 2012",
        "titulo": "Sistema General de Riesgos Laborales",
        "vigente": True,
        "keywords": ["riesgos laborales", "ARL", "accidentes de trabajo"],
    },
    {
        "clave": "LEY 91 DE 1989",
        "nombre": "Ley 91 de 1989",
        "titulo": "Fondo Nacional de Prestaciones Sociales del Magisterio (FOMAG)",
        "vigente": True,
        "keywords": ["magisterio", "FOMAG", "docentes"],
    },
    {
        "clave": "LEY 1709 DE 2014",
        "nombre": "Ley 1709 de 2014",
        "titulo": "Reformas al sistema penitenciario — atención en salud PPL",
        "vigente": True,
        "keywords": ["PPL", "privados de libertad", "salud penitenciaria"],
    },
    # ─── DECRETOS ───
    {
        "clave": "DECRETO 4747 DE 2007",
        "nombre": "Decreto 4747 de 2007",
        "titulo": "Regulación de la prestación de servicios de salud — Arts. 11, 20, 21",
        "vigente": True,
        "keywords": [
            "glosas",
            "urgencias",
            "conciliación",
            "sustentación",
            "Art. 11",
            "Art. 20",
            "Art. 21",
        ],
    },
    {
        "clave": "DECRETO 780 DE 2016",
        "nombre": "Decreto 780 de 2016",
        "titulo": "Decreto Único Reglamentario del Sector Salud y Protección Social",
        "vigente": True,
        "keywords": ["DURS", "reglamentario", "salud"],
    },
    {
        "clave": "DECRETO 1011 DE 2006",
        "nombre": "Decreto 1011 de 2006",
        "titulo": "Sistema Obligatorio de Garantía de Calidad en Salud (SOGCS)",
        "vigente": True,
        "keywords": ["calidad", "SOGCS", "habilitación", "auditoría"],
    },
    {
        "clave": "DECRETO 2423 DE 1996",
        "nombre": "Decreto 2423 de 1996",
        "titulo": "Manual Tarifario SOAT",
        "vigente": True,
        "keywords": ["SOAT", "tarifas", "manual tarifario"],
    },
    {
        "clave": "DECRETO 1082 DE 2015",
        "nombre": "Decreto 1082 de 2015",
        "titulo": "Decreto Único Reglamentario del sector administrativo de Planeación Nacional",
        "vigente": True,
        "keywords": ["contratación estatal", "ESE", "pública"],
    },
    {
        "clave": "DECRETO 1295 DE 1994",
        "nombre": "Decreto 1295 de 1994",
        "titulo": "Organización y administración del Sistema General de Riesgos Profesionales",
        "vigente": True,
        "keywords": ["riesgos profesionales", "ARL", "accidentes"],
    },
    {
        "clave": "DECRETO 1072 DE 2015",
        "nombre": "Decreto 1072 de 2015",
        "titulo": "Decreto Único Reglamentario del Sector Trabajo",
        "vigente": True,
        "keywords": ["trabajo", "laboral", "seguridad social"],
    },
    {
        "clave": "DECRETO 1795 DE 2000",
        "nombre": "Decreto 1795 de 2000",
        "titulo": "Sistema de Salud de las Fuerzas Militares y Policía Nacional",
        "vigente": True,
        "keywords": ["fuerzas militares", "policía", "salud", "FFMM"],
    },
    {
        "clave": "DECRETO 3752 DE 2003",
        "nombre": "Decreto 3752 de 2003",
        "titulo": "Reglamenta el FOMAG — prestaciones sociales del magisterio",
        "vigente": True,
        "keywords": ["FOMAG", "magisterio", "prestaciones"],
    },
    # ─── RESOLUCIONES MinSalud / MINSALUD ───
    {
        "clave": "RESOLUCION 3047 DE 2008",
        "nombre": "Resolución 3047 de 2008",
        "titulo": "Formatos, mecanismos de envío, procedimientos y términos para la remisión de la información al FOSYGA",
        "vigente": True,
        "keywords": ["glosas", "soportes", "Anexo Técnico 5", "Anexo Técnico 6", "catálogo glosas"],
    },
    {
        "clave": "RESOLUCION 416 DE 2009",
        "nombre": "Resolución 416 de 2009",
        "titulo": "Modifica la Resolución 3047 de 2008 — Anexos Técnicos",
        "vigente": True,
        "keywords": ["glosas", "soportes", "modificación"],
    },
    {
        "clave": "RESOLUCION 2284 DE 2023",
        "nombre": "Resolución 2284 de 2023",
        "titulo": "Manual Único de Glosas, Devoluciones y Objetivos — causales taxativas",
        "vigente": True,
        "keywords": ["glosas", "manual único", "causales", "devoluciones", "objetivos", "2023"],
    },
    {
        "clave": "RESOLUCION 2284 DE 2024",
        "nombre": "Resolución 2284 de 2024",
        "titulo": "Interoperabilidad HCE y estándares semánticos",
        "vigente": True,
        "keywords": ["interoperabilidad", "HCE", "semántica", "historia clínica electrónica"],
    },
    {
        "clave": "RESOLUCION 2275 DE 2023",
        "nombre": "Resolución 2275 de 2023",
        "titulo": "RIPS — Registro Individual de Prestaciones de Salud (Anexo Técnico, CUV ADRES)",
        "vigente": True,
        "keywords": ["RIPS", "ADRES", "CUV", "prestaciones"],
    },
    {
        "clave": "RESOLUCION 2003 DE 2014",
        "nombre": "Resolución 2003 de 2014",
        "titulo": "Procedimientos y condiciones de habilitación de servicios de salud",
        "vigente": True,
        "keywords": ["habilitación", "servicios", "condiciones"],
    },
    {
        "clave": "RESOLUCION 3100 DE 2019",
        "nombre": "Resolución 3100 de 2019",
        "titulo": "Estándares actualizados de habilitación de servicios de salud",
        "vigente": True,
        "keywords": ["habilitación", "estándares", "servicios"],
    },
    {
        "clave": "RESOLUCION 1604 DE 2022",
        "nombre": "Resolución 1604 de 2022",
        "titulo": "Estándares de habilitación — actualización 2022",
        "vigente": True,
        "keywords": ["habilitación", "estándares", "2022"],
    },
    {
        "clave": "RESOLUCION 1995 DE 1999",
        "nombre": "Resolución 1995 de 1999",
        "titulo": "Historia Clínica — único instrumento de plena prueba",
        "vigente": True,
        "keywords": ["historia clínica", "prueba", "soportes", "documentación"],
    },
    {
        "clave": "RESOLUCION 5269 DE 2017",
        "nombre": "Resolución 5269 de 2017",
        "titulo": "Plan de Beneficios en Salud (PBS)",
        "vigente": True,
        "keywords": ["PBS", "beneficios", "plan de salud", "cobertura"],
    },
    {
        "clave": "RESOLUCION 256 DE 2016",
        "nombre": "Resolución 256 de 2016",
        "titulo": "Indicadores de calidad en salud",
        "vigente": True,
        "keywords": ["calidad", "indicadores", "salud"],
    },
    {
        "clave": "RESOLUCION 1403 DE 2007",
        "nombre": "Resolución 1403 de 2007",
        "titulo": "Servicio farmacéutico — modelo de gestión",
        "vigente": True,
        "keywords": ["farmacéutico", "medicamentos", "farmacia"],
    },
    {
        "clave": "RESOLUCION 5159 DE 2015",
        "nombre": "Resolución 5159 de 2015",
        "titulo": "Atención en salud para población privada de la libertad (PPL)",
        "vigente": True,
        "keywords": ["PPL", "privados de libertad", "penitenciaria"],
    },
    {
        "clave": "RESOLUCION 3539 DE 2019",
        "nombre": "Resolución 3539 de 2019",
        "titulo": "Procedimientos y condiciones de habilitación de servicios de salud — complementaria",
        "vigente": True,
        "keywords": ["habilitación", "condiciones", "servicios"],
    },
    {
        "clave": "RESOLUCION 042 DE 2020 DIAN",
        "nombre": "Resolución 042 de 2020 DIAN",
        "titulo": "Factura Electrónica de Venta (FEV) — Habilitación",
        "vigente": True,
        "keywords": ["factura electrónica", "FEV", "DIAN", "facturación"],
    },
    {
        "clave": "RESOLUCION 506 DE 2021 DIAN",
        "nombre": "Resolución 506 de 2021 DIAN",
        "titulo": "Factura Electrónica de Venta — Actualización",
        "vigente": True,
        "keywords": ["factura electrónica", "FEV", "DIAN"],
    },
    {
        "clave": "RESOLUCION 054 DE 2026 ESE HUS",
        "nombre": "Resolución 054 de 2026 ESE HUS",
        "titulo": "Tarifas propias del Hospital Universitario de Santander 2026",
        "vigente": True,
        "keywords": ["tarifas", "HUS", "propias", "ESE"],
    },
    {
        "clave": "RESOLUCION 124 DE 2026 ESE HUS",
        "nombre": "Resolución 124 de 2026 ESE HUS",
        "titulo": "Complemento de tarifas propias ESE HUS 2026",
        "vigente": True,
        "keywords": ["tarifas", "HUS", "propias", "complemento"],
    },
    # ─── CIRCULARES ───
    {
        # 24-08-2026 — enriquecida con el texto de la circular real (49 pág,
        # entregada por el auditor). Las keywords son lo que la pantalla
        # muestra como "texto": frases con sustancia, no etiquetas sueltas.
        "clave": "CIRCULAR EXTERNA 047 DE 2025 MINSALUD",
        "nombre": "Circular Externa 047 de 2025 MinSalud",
        "titulo": "Indexación de tarifas del Manual de Régimen Tarifario a UVB — vigencia 2026 (30-dic-2025)",
        "vigente": True,
        "keywords": [
            "SOAT",
            "UVB",
            "manual tarifario",
            "tarifas 2026",
            "Art. 313 Ley 2294 de 2023 crea la Unidad de Valor Básico",
            "para liquidar en pesos se multiplica el valor de la UVB vigente por la tarifa en UVB",
            "UVB 2026 = $12.110 (Resolución MinHacienda)",
            "aplica a aseguradoras SOAT, entidades responsables de pago, prestadores y transporte de pacientes",
            "indexación",
            "accidente de tránsito",
        ],
    },
    {
        # 24-08-2026 — cargada del PDF real (45 pág) entregado por el auditor.
        # Defensa clave del HUS en glosas de medicamentos: el precio máximo es
        # POR MERCADO RELEVANTE (mg/unidad) y el Parágrafo 2 del Art. 1 permite
        # a las IPS ADICIONAR el margen del Art. 11 de la Circular 18 de 2024.
        "clave": "CIRCULAR 19 DE 2024 CNPMDM",
        "nombre": "Circular 19 de 2024 CNPMDM (MinSalud–MinCIT)",
        "titulo": "Precio máximo de venta de medicamentos en control directo — deroga la Circular 13 de 2022",
        "vigente": True,
        "keywords": [
            "precio máximo de venta",
            "control directo de precios",
            "medicamentos regulados",
            "mercado relevante",
            "CNPMDM",
            "CUM",
            "Parágrafo 2 Art. 1: la IPS puede adicionar al precio máximo el margen del Art. 11 de la Circular 18 de 2024",
            "sanciona la SIC según Art. 132 Ley 1438 de 2011",
            "rige desde el 30 de julio de 2024 y deroga la Circular 13 de 2022",
            "transacción institucional",
            "regulados",
        ],
    },
    {
        "clave": "CIRCULAR 030 DE 2013 MINSALUD",
        "nombre": "Circular 030 de 2013 MinSalud",
        "titulo": "Errores formales subsanables en glosas",
        "vigente": True,
        "keywords": ["errores formales", "subsanables", "glosas"],
    },
    # ─── ACUERDOS ───
    {
        "clave": "ACUERDO 002 DE 2001 CSSMP",
        "nombre": "Acuerdo 002 de 2001 CSSMP",
        "titulo": "Sistema de salud Fuerzas Militares y Policía",
        "vigente": True,
        "keywords": ["CSSMP", "fuerzas militares", "policía", "salud"],
    },
    {
        "clave": "ACUERDO 080 DE 2022 CSSMP",
        "nombre": "Acuerdo 080 de 2022 CSSMP",
        "titulo": "Actualización del sistema de salud Fuerzas Militares y Policía 2022",
        "vigente": True,
        "keywords": ["CSSMP", "fuerzas militares", "policía", "2022"],
    },
    # ─── NORMAS DE CONTRATACIÓN Y CÓDIGO CIVIL/COMERCIAL ───
    {
        "clave": "CODIGO CIVIL ART 1602",
        "nombre": "Código Civil — Art. 1602",
        "titulo": "Pacta sunt servanda — intangibilidad del contrato",
        "vigente": True,
        "keywords": ["pacta sunt servanda", "contrato", "obligatorio"],
    },
    {
        "clave": "CODIGO CIVIL ART 1603",
        "nombre": "Código Civil — Art. 1603",
        "titulo": "Buena fe objetiva en la ejecución de contratos",
        "vigente": True,
        "keywords": ["buena fe", "ejecución", "contratos"],
    },
    {
        "clave": "CODIGO COMERCIO ART 871",
        "nombre": "Código de Comercio — Art. 871",
        "titulo": "Buena fe en los actos mercantiles",
        "vigente": True,
        "keywords": ["buena fe", "comercio", "actos mercantiles"],
    },
    {
        "clave": "CPACA ART 42",
        "nombre": "CPACA — Ley 1437 de 2011 Art. 42",
        "titulo": "Motivación de actos administrativos",
        "vigente": True,
        "keywords": ["acto administrativo", "motivación", "CPACA"],
    },
    {
        "clave": "ESTATUTO TRIBUTARIO ART 617",
        "nombre": "Estatuto Tributario — Art. 617",
        "titulo": "Requisitos de la factura de venta",
        "vigente": True,
        "keywords": ["factura", "tributario", "requisitos"],
    },
    # ─── JURISPRUDENCIA CONSTITUCIONAL ───
    {
        "clave": "SENTENCIA T-760 DE 2008",
        "nombre": "Sentencia T-760 de 2008 Corte Constitucional",
        "titulo": "Derecho fundamental a la salud — régimen general (no usar FF.MM./PPL/FOMAG)",
        "vigente": True,
        "keywords": ["derecho fundamental", "salud", "EPS", "tutela"],
    },
    {
        "clave": "SENTENCIA T-478 DE 1995",
        "nombre": "Sentencia T-478 de 1995 Corte Constitucional",
        "titulo": "Autonomía médica",
        "vigente": True,
        "keywords": ["autonomía médica", "acto médico", "decisión"],
    },
    {
        "clave": "SENTENCIA T-1025 DE 2002",
        "nombre": "Sentencia T-1025 de 2002 Corte Constitucional",
        "titulo": "Urgencias sin autorización previa",
        "vigente": True,
        "keywords": ["urgencias", "autorización", "tutela"],
    },
    {
        "clave": "SENTENCIA C-313 DE 2014",
        "nombre": "Sentencia C-313 de 2014 Corte Constitucional",
        "titulo": "Exequibilidad Ley Estatutaria en Salud",
        "vigente": True,
        "keywords": ["estatutaria", "salud", "constitucionalidad"],
    },
    {
        "clave": "SENTENCIA T-121 DE 2015",
        "nombre": "Sentencia T-121 de 2015 Corte Constitucional",
        "titulo": "Carácter recomendativo de las guías de práctica clínica (GPC)",
        "vigente": True,
        "keywords": ["GPC", "guías clínicas", "recomendativo", "autonomía médica"],
    },
    # ─── CÓDIGOS DE GLOSA (RESOLUCIÓN 2284/2023) ───
    {
        "clave": "CODIGO GLOSA TA",
        "nombre": "Código de Glosa TA — Tarifas",
        "titulo": "Glosa por tarifas — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["TA", "tarifas", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA SO",
        "nombre": "Código de Glosa SO — Soportes",
        "titulo": "Glosa por soportes — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["SO", "soportes", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA AU",
        "nombre": "Código de Glosa AU — Autorización",
        "titulo": "Glosa por autorización — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["AU", "autorización", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA CO",
        "nombre": "Código de Glosa CO — Cobertura",
        "titulo": "Glosa por cobertura — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["CO", "cobertura", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA CL",
        "nombre": "Código de Glosa CL — Pertinencia Clínica",
        "titulo": "Glosa por pertinencia clínica — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["CL", "pertinencia clínica", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA FA",
        "nombre": "Código de Glosa FA — Facturación",
        "titulo": "Glosa por facturación — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["FA", "facturación", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA IN",
        "nombre": "Código de Glosa IN — Insumos",
        "titulo": "Glosa por insumos — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["IN", "insumos", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA ME",
        "nombre": "Código de Glosa ME — Medicamentos",
        "titulo": "Glosa por medicamentos — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["ME", "medicamentos", "glosa", "código"],
    },
    {
        "clave": "CODIGO GLOSA PE",
        "nombre": "Código de Glosa PE — Pertinencia Clínica (variante)",
        "titulo": "Glosa PE por pertinencia clínica — Resolución 2284 de 2023",
        "vigente": True,
        "keywords": ["PE", "pertinencia clínica", "glosa", "código"],
    },
    # ─── CÓDIGOS DE RESPUESTA (RESOLUCIÓN 3047/2008) ───
    {
        "clave": "CODIGO RESPUESTA RE9502",
        "nombre": "Código de Respuesta RE9502",
        "titulo": "Glosa no procede — aceptación tácita (Art. 57 Ley 1438/2011)",
        "vigente": True,
        "keywords": ["RE9502", "aceptación tácita", "extemporaneidad"],
    },
    {
        "clave": "CODIGO RESPUESTA RE9602",
        "nombre": "Código de Respuesta RE9602",
        "titulo": "Glosa Injustificada — IPS aporta evidencia al 100%",
        "vigente": True,
        "keywords": ["RE9602", "injustificada", "evidencia"],
    },
    {
        "clave": "CODIGO RESPUESTA RE9701",
        "nombre": "Código de Respuesta RE9701",
        "titulo": "Devolución aceptada al 100%",
        "vigente": True,
        "keywords": ["RE9701", "devolución", "aceptada"],
    },
    {
        "clave": "CODIGO RESPUESTA RE9702",
        "nombre": "Código de Respuesta RE9702",
        "titulo": "Glosa aceptada al 100%",
        "vigente": True,
        "keywords": ["RE9702", "glosa aceptada"],
    },
    {
        "clave": "CODIGO RESPUESTA RE9801",
        "nombre": "Código de Respuesta RE9801",
        "titulo": "Glosa aceptada y subsanada parcialmente",
        "vigente": True,
        "keywords": ["RE9801", "parcial", "subsanada"],
    },
    {
        "clave": "CODIGO RESPUESTA RE9901",
        "nombre": "Código de Respuesta RE9901",
        "titulo": "Glosa no aceptada — subsanada en su totalidad",
        "vigente": True,
        "keywords": ["RE9901", "no aceptada", "subsanada"],
    },
    # ─── NORMAS ADICIONALES DEL SISTEMA DE SALUD ───
    {
        "clave": "DECRETO 441 DE 2022",
        "nombre": "Decreto 441 de 2022",
        "titulo": "Indicadores de calidad en salud — actualización",
        "vigente": True,
        "keywords": ["calidad", "indicadores", "2022"],
    },
    {
        "clave": "RESOLUCION 2641 DE 2025",
        "nombre": "Resolución 2641 de 2025",
        "titulo": "Homologación de tarifas — código IPS (Res. 2641/2025)",
        "vigente": True,
        "keywords": ["tarifas", "homologación", "código IPS", "2025"],
    },
    {
        "clave": "ACUERDO 032 DE 2012 CNSSS",
        "nombre": "Acuerdo 032 de 2012 CNSSS",
        "titulo": "Plan Obligatorio de Salud (PBS anterior UPC)",
        "vigente": False,
        "keywords": ["POS", "PBS", "UPC", "plan de salud"],
    },
    {
        "clave": "RESOLUCION 5261 DE 1994",
        "nombre": "Resolución 5261 de 1994",
        "titulo": "Manual de Actividades, Intervenciones y Procedimientos del POS",
        "vigente": False,
        "keywords": ["MAPIPOS", "POS", "actividades", "procedimientos"],
    },
    {
        "clave": "DECRETO 2353 DE 2015",
        "nombre": "Decreto 2353 de 2015",
        "titulo": "Afiliación y registro al Sistema de Salud",
        "vigente": True,
        "keywords": ["afiliación", "registro", "BDUA"],
    },
    {
        "clave": "RESOLUCION 1552 DE 2022",
        "nombre": "Resolución 1552 de 2022",
        "titulo": "Portabilidad en el Sistema de Salud",
        "vigente": True,
        "keywords": ["portabilidad", "movilidad", "afiliados"],
    },
    {
        "clave": "DECRETO 859 DE 1995",
        "nombre": "Decreto 859 de 1995",
        "titulo": "Reglamenta las EPS — obligaciones y funcionamiento",
        "vigente": True,
        "keywords": ["EPS", "obligaciones", "funcionamiento"],
    },
    {
        "clave": "RESOLUCION 3374 DE 2000",
        "nombre": "Resolución 3374 de 2000",
        "titulo": "RIPS — Sistema de información de prestaciones de salud",
        "vigente": False,
        "keywords": ["RIPS", "información", "prestaciones"],
    },
    {
        "clave": "DECRETO 1876 DE 1994",
        "nombre": "Decreto 1876 de 1994",
        "titulo": "Empresas Sociales del Estado (ESE)",
        "vigente": True,
        "keywords": ["ESE", "empresa social", "hospital público"],
    },
    {
        "clave": "LEY 715 DE 2001 ART 54",
        "nombre": "Ley 715 de 2001 — Art. 54",
        "titulo": "Funciones del municipio en salud",
        "vigente": True,
        "keywords": ["municipio", "salud", "funciones", "ente territorial"],
    },
    {
        "clave": "RESOLUCION 8430 DE 1993",
        "nombre": "Resolución 8430 de 1993 MinSalud",
        "titulo": "Normas científicas, técnicas y administrativas para la investigación en salud",
        "vigente": True,
        "keywords": ["investigación", "ética", "bioética"],
    },
    {
        "clave": "DECRETO 1663 DE 1994",
        "nombre": "Decreto 1663 de 1994",
        "titulo": "Subcuenta de compensación — FOSYGA",
        "vigente": False,
        "keywords": ["FOSYGA", "compensación", "UPC"],
    },
    {
        "clave": "RESOLUCION 1043 DE 2006",
        "nombre": "Resolución 1043 de 2006",
        "titulo": "Condiciones de habilitación para servicios de salud",
        "vigente": False,
        "keywords": ["habilitación", "servicios", "condiciones"],
    },
    {
        "clave": "ACUERDO 395 DE 2008 CNSSS",
        "nombre": "Acuerdo 395 de 2008 CNSSS",
        "titulo": "Actualización del Plan Obligatorio de Salud",
        "vigente": False,
        "keywords": ["POS", "PBS", "actualización"],
    },
    {
        "clave": "DECRETO 2463 DE 2001",
        "nombre": "Decreto 2463 de 2001",
        "titulo": "Integración de las Juntas de Calificación de Invalidez",
        "vigente": True,
        "keywords": ["invalidez", "calificación", "junta"],
    },
    {
        "clave": "RESOLUCION 1117 DE 2008",
        "nombre": "Resolución 1117 de 2008",
        "titulo": "Manual Único para la Calificación de la Pérdida de Capacidad Laboral",
        "vigente": True,
        "keywords": ["invalidez", "capacidad laboral", "calificación"],
    },
    {
        "clave": "RESOLUCION 1941 DE 2013",
        "nombre": "Resolución 1941 de 2013",
        "titulo": "Catálogo de servicios de salud — CUPS actualización",
        "vigente": True,
        "keywords": ["CUPS", "servicios", "catálogo"],
    },
    {
        "clave": "RESOLUCION 4678 DE 2015",
        "nombre": "Resolución 4678 de 2015",
        "titulo": "Actualización del clasificador de bienes y servicios en salud",
        "vigente": True,
        "keywords": ["CUPS", "clasificador", "bienes", "servicios"],
    },
    {
        "clave": "RESOLUCION 5596 DE 2015",
        "nombre": "Resolución 5596 de 2015",
        "titulo": "Criterios para clasificación de tecnologías en salud NO-PBS",
        "vigente": True,
        "keywords": ["NO-PBS", "tecnologías", "exclusiones"],
    },
    {
        "clave": "RESOLUCION 1159 DE 2021",
        "nombre": "Resolución 1159 de 2021",
        "titulo": "Requisitos para la presunción de afiliación al SGSSS",
        "vigente": True,
        "keywords": ["afiliación", "presunción", "SGSSS"],
    },
    {
        "clave": "RESOLUCION 2292 DE 2021",
        "nombre": "Resolución 2292 de 2021",
        "titulo": "Actualización del Manual de Tarifas SOAT 2022",
        "vigente": False,
        "keywords": ["SOAT", "tarifas", "2022"],
    },
    {
        "clave": "CIRCULAR 012 DE 2018 SUPERSALUD",
        "nombre": "Circular 012 de 2018 SuperSalud",
        "titulo": "Instrucciones sobre manejo de glosas y conciliaciones",
        "vigente": True,
        "keywords": ["glosas", "conciliaciones", "SuperSalud"],
    },
    {
        "clave": "RESOLUCION 1035 DE 2015",
        "nombre": "Resolución 1035 de 2015",
        "titulo": "Manual de Tarifas SOAT — codificación 2015",
        "vigente": False,
        "keywords": ["SOAT", "tarifas", "2015"],
    },
    {
        "clave": "DECRETO 1727 DE 1994",
        "nombre": "Decreto 1727 de 1994",
        "titulo": "Régimen de las Entidades Promotoras de Salud del Régimen Contributivo",
        "vigente": True,
        "keywords": ["EPS", "contributivo", "régimen"],
    },
    {
        "clave": "LEY 1122 DE 2007 ART 25",
        "nombre": "Ley 1122 de 2007 — Art. 25",
        "titulo": "Inspección, vigilancia y control SuperSalud",
        "vigente": True,
        "keywords": ["SuperSalud", "IVC", "vigilancia"],
    },
    {
        "clave": "LEY 1122 DE 2007 ART 26",
        "nombre": "Ley 1122 de 2007 — Art. 26",
        "titulo": "Facultades de la Superintendencia Nacional de Salud",
        "vigente": True,
        "keywords": ["SuperSalud", "facultades", "sanciones"],
    },
    {
        "clave": "RESOLUCION 2640 DE 2005",
        "nombre": "Resolución 2640 de 2005",
        "titulo": "Gestión del riesgo en salud — lineamientos",
        "vigente": False,
        "keywords": ["riesgo", "gestión", "salud"],
    },
    {
        "clave": "DECRETO 4747 DE 2007 ART 17",
        "nombre": "Decreto 4747 de 2007 — Art. 17",
        "titulo": "Procesos de auditoría médica en la prestación de servicios",
        "vigente": True,
        "keywords": ["auditoría médica", "procesos", "Art. 17"],
    },
    {
        "clave": "RESOLUCION 3615 DE 2005",
        "nombre": "Resolución 3615 de 2005",
        "titulo": "Manual de estándares para la acreditación de IPS",
        "vigente": True,
        "keywords": ["acreditación", "IPS", "estándares"],
    },
    {
        "clave": "DECRETO 1011 DE 2006 ART 32",
        "nombre": "Decreto 1011 de 2006 — Art. 32",
        "titulo": "Programa de Auditoría para el Mejoramiento de la Calidad (PAMEC)",
        "vigente": True,
        "keywords": ["PAMEC", "auditoría", "calidad", "mejoramiento"],
    },
    {
        "clave": "RESOLUCION 1445 DE 2006",
        "nombre": "Resolución 1445 de 2006",
        "titulo": "Sistema único de acreditación en salud",
        "vigente": True,
        "keywords": ["acreditación", "salud", "sistema único"],
    },
    {
        "clave": "RESOLUCION 1474 DE 2002",
        "nombre": "Resolución 1474 de 2002",
        "titulo": "Manual de condiciones esenciales de habilitación (CAMHSE)",
        "vigente": False,
        "keywords": ["habilitación", "condiciones esenciales"],
    },
    {
        "clave": "LEY 1066 DE 2006",
        "nombre": "Ley 1066 de 2006",
        "titulo": "Actividades de cobro coactivo de las entidades públicas",
        "vigente": True,
        "keywords": ["cobro coactivo", "cartera", "recuperación"],
    },
    {
        "clave": "RESOLUCION 3047 DE 2008 ANEXO 5",
        "nombre": "Resolución 3047 de 2008 — Anexo Técnico No. 5",
        "titulo": "Lista de soportes de la cuenta de cobro",
        "vigente": True,
        "keywords": ["soportes", "cuenta de cobro", "Anexo 5"],
    },
    {
        "clave": "RESOLUCION 3047 DE 2008 ANEXO 6",
        "nombre": "Resolución 3047 de 2008 — Anexo Técnico No. 6",
        "titulo": "Catálogo único de glosas",
        "vigente": True,
        "keywords": ["glosas", "catálogo único", "Anexo 6"],
    },
    {
        "clave": "DECRETO 1663 DE 2013",
        "nombre": "Decreto 1663 de 2013",
        "titulo": "Regulación del seguro de salud para accidentes de tránsito (SOAT)",
        "vigente": True,
        "keywords": ["SOAT", "accidentes", "tránsito", "seguro"],
    },
    {
        "clave": "RESOLUCION 2438 DE 2010",
        "nombre": "Resolución 2438 de 2010",
        "titulo": "Manual de referencia y contrarreferencia",
        "vigente": True,
        "keywords": ["referencia", "contrarreferencia", "red"],
    },
    {
        "clave": "DECRETO 4747 DE 2007 ART 11",
        "nombre": "Decreto 4747 de 2007 — Art. 11",
        "titulo": "Urgencias sin autorización previa — obligación de atender",
        "vigente": True,
        "keywords": ["urgencias", "autorización", "Art. 11"],
    },
    {
        "clave": "DECRETO 4747 DE 2007 ART 20",
        "nombre": "Decreto 4747 de 2007 — Art. 20",
        "titulo": "Conciliación en controversias de glosas",
        "vigente": True,
        "keywords": ["conciliación", "glosas", "Art. 20"],
    },
    {
        "clave": "DECRETO 4747 DE 2007 ART 21",
        "nombre": "Decreto 4747 de 2007 — Art. 21",
        "titulo": "Debida sustentación de glosas — requisito de motivación",
        "vigente": True,
        "keywords": ["motivación", "sustentación", "glosas", "Art. 21"],
    },
    {
        "clave": "RESOLUCION 2764 DE 2023",
        "nombre": "Resolución 2764 de 2023",
        "titulo": "Adopción del Plan de Beneficios en Salud 2023",
        "vigente": True,
        "keywords": ["PBS", "plan de beneficios", "2023"],
    },
    {
        "clave": "LEY 1948 DE 2019",
        "nombre": "Ley 1948 de 2019",
        "titulo": "Eliminación de la dualidad del plan de beneficios contributivo y subsidiado",
        "vigente": True,
        "keywords": ["PBS", "subsidiado", "contributivo", "unificación"],
    },
    {
        "clave": "DECRETO 903 DE 2014",
        "nombre": "Decreto 903 de 2014",
        "titulo": "Mecanismos para la actualización periódica del PBS",
        "vigente": True,
        "keywords": ["PBS", "actualización", "IETS"],
    },
    {
        "clave": "RESOLUCION 1895 DE 2001",
        "nombre": "Resolución 1895 de 2001",
        "titulo": "Clasificador Único de Procedimientos en Salud (CUPS) — versión original",
        "vigente": False,
        "keywords": ["CUPS", "procedimientos", "clasificador"],
    },
    {
        "clave": "RESOLUCION 0365 DE 1999",
        "nombre": "Resolución 0365 de 1999",
        "titulo": "Atención de urgencias en cualquier IPS habilitada",
        "vigente": True,
        "keywords": ["urgencias", "libre acceso", "atención"],
    },
    {
        "clave": "LEY 1480 DE 2011",
        "nombre": "Ley 1480 de 2011",
        "titulo": "Estatuto del Consumidor — aplicable a relaciones IPS-paciente",
        "vigente": True,
        "keywords": ["consumidor", "protección", "derechos"],
    },
    {
        "clave": "DECRETO 1485 DE 1994",
        "nombre": "Decreto 1485 de 1994",
        "titulo": "Organización y funcionamiento de las EPS",
        "vigente": True,
        "keywords": ["EPS", "organización", "funcionamiento"],
    },
    {
        "clave": "RESOLUCION 2003 DE 2014 ART 7",
        "nombre": "Resolución 2003 de 2014 — Art. 7",
        "titulo": "Condiciones de capacidad tecnológica y científica de las IPS",
        "vigente": True,
        "keywords": ["habilitación", "tecnología", "capacidad científica"],
    },
    {
        "clave": "CIRCULAR 030 DE 2006 SUPERSALUD",
        "nombre": "Circular 030 de 2006 SuperSalud",
        "titulo": "Instrucciones sobre glosas y objeciones de cuentas médicas",
        "vigente": False,
        "keywords": ["glosas", "objeciones", "cuentas médicas"],
    },
    {
        "clave": "DECRETO 2423 DE 1996 ART 10",
        "nombre": "Decreto 2423 de 1996 — Art. 10",
        "titulo": "Tarifas mínimas SOAT para urgencias",
        "vigente": True,
        "keywords": ["SOAT", "urgencias", "tarifas mínimas"],
    },
    {
        "clave": "RESOLUCION 1604 DE 2006",
        "nombre": "Resolución 1604 de 2006",
        "titulo": "Reglamentación del acceso a servicios de alta complejidad",
        "vigente": True,
        "keywords": ["alta complejidad", "acceso", "referencia"],
    },
    {
        "clave": "LEY 1438 DE 2011 ART 56",
        "nombre": "Ley 1438 de 2011 — Art. 56",
        "titulo": "Plazo para formular glosas — máximo 30 días calendario",
        "vigente": True,
        "keywords": ["glosas", "plazo", "30 días", "Art. 56"],
    },
    {
        "clave": "LEY 1438 DE 2011 ART 57",
        "nombre": "Ley 1438 de 2011 — Art. 57",
        "titulo": "Carga dinámica de la prueba — plazo respuesta glosa 20 días hábiles",
        "vigente": True,
        "keywords": ["glosas", "carga probatoria", "20 días hábiles", "Art. 57"],
    },
    {
        "clave": "LEY 1438 DE 2011 ART 105",
        "nombre": "Ley 1438 de 2011 — Art. 105",
        "titulo": "Prohibición de intromisión en el acto médico por parte de las EPS",
        "vigente": True,
        "keywords": ["acto médico", "intromisión", "autonomía", "Art. 105"],
    },
    {
        "clave": "LEY 1438 DE 2011 ART 126",
        "nombre": "Ley 1438 de 2011 — Art. 126",
        "titulo": "Facultades de la Superintendencia Nacional de Salud",
        "vigente": True,
        "keywords": ["SuperSalud", "facultades", "Art. 126"],
    },
    {
        "clave": "DECRETO 2091 DE 2023",
        "nombre": "Decreto 2091 de 2023",
        "titulo": "Reglamenta el contrato de prestación de servicios de salud",
        "vigente": True,
        "keywords": ["contrato", "prestación", "servicios"],
    },
    {
        "clave": "RESOLUCION 1572 DE 2012",
        "nombre": "Resolución 1572 de 2012",
        "titulo": "Procedimientos para la facturación de servicios de salud",
        "vigente": True,
        "keywords": ["facturación", "procedimientos", "servicios"],
    },
    {
        "clave": "DECRETO 1281 DE 2002",
        "nombre": "Decreto 1281 de 2002",
        "titulo": "Flujo de caja y sistemas de información para el pago de servicios de salud",
        "vigente": True,
        "keywords": ["pago", "flujo de caja", "información"],
    },
    {
        "clave": "CIRCULAR EXTERNA 011 DE 2024 MINSALUD",
        "nombre": "Circular Externa 011 de 2024 MinSalud",
        "titulo": "Lineamientos para la implementación del Manual Único de Glosas 2023",
        "vigente": True,
        "keywords": ["glosas", "manual único", "implementación", "2024"],
    },
]


@router.get("/normas/export.json")
def exportar_normas(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R79 P2: Exporta el catálogo completo de normas del marco normativo HUS.

    Genera un archivo JSON descargable con todas las normas legales, decretos,
    resoluciones y circulares que forman el marco normativo para la defensa
    de glosas médicas en la ESE Hospital Universitario de Santander.

    Returns:
        JSON attachment con metadata y lista de normas.
    """
    exportado_en = datetime.now(timezone.utc).isoformat()

    payload = {
        "metadata": {
            "exportado_en": exportado_en,
            "exportado_por": current_user.email,
            "total_normas": len(CATALOGO_NORMAS),
            "sistema": "Motor Glosas HUS",
            "version_normas": "2026.1",
        },
        "normas": CATALOGO_NORMAS,
    }

    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=normas-hus.json",
        },
    )


@router.post("")
def consultar_biblioteca(
    data: ConsultaNormativaInput,
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Busca normas en la biblioteca por una pregunta en lenguaje natural.

    Alimenta el cuadro "Buscar en la biblioteca" del panel Consulta
    Normativa. Antes la UI llamaba a este endpoint pero no existía (404) —
    por eso el panel "no generaba nada funcional". Búsqueda por coincidencia
    de términos sobre el catálogo normativo HUS (>100 normas).
    """
    pregunta = (data.pregunta or "").strip()
    if not pregunta:
        return {"resultados": [], "total_encontrados": 0, "pregunta": pregunta}
    resultados = _buscar_normas(pregunta, data.limite or 8)
    return {
        "resultados": resultados,
        "total_encontrados": len(resultados),
        "pregunta": pregunta,
    }


@router.get("/normas")
def listar_normas(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Índice de todas las normas indexadas (botón "Ver todas las normas").

    Devuelve nombre + título + nº de artículos por norma. Antes la UI lo
    llamaba pero el endpoint no existía (404).
    """
    normas = []
    for n in CATALOGO_NORMAS:
        normas.append(
            {
                "nombre": n.get("nombre", ""),
                "titulo": n.get("titulo", ""),
                "vigente": bool(n.get("vigente", True)),
                # El catálogo no desglosa artículos por norma; 0 = sin desglose.
                "num_articulos": int(n.get("num_articulos", 0) or 0),
            }
        )
    # Orden alfabético por nombre para que el índice sea escaneable.
    normas.sort(key=lambda x: x["nombre"])
    return {"total": len(normas), "normas": normas}
