import os
import io
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import pdfplumber
import PyPDF2
import httpx  # para llamar a Claude como fallback

from groq import AsyncGroq
# ── CORRECCIÓN DE IMPORTS PARA LA NUEVA ESTRUCTURA ──
from models.schemas import GlosaInput, GlosaResult

logger = logging.getLogger("motor_glosas_v2")

# ── Constantes de tiempo ──────────────────────────────────────────────────────
FERIADOS_CO = [
    "2025-01-01","2025-01-06","2025-03-24","2025-04-17","2025-04-18",
    "2025-05-01","2025-06-02","2025-06-23","2025-06-30","2025-07-20",
    "2025-08-07","2025-08-18","2025-10-13","2025-11-03","2025-11-17",
    "2025-12-08","2025-12-25",
    "2026-01-01","2026-01-12","2026-03-23","2026-04-02","2026-04-03",
    "2026-05-01","2026-05-18","2026-06-08","2026-06-15","2026-06-29",
    "2026-07-20","2026-08-07","2026-08-17","2026-10-12","2026-11-02",
    "2026-11-16","2026-12-08","2026-12-25",
]

# ── CORRECCIÓN: Definir los contratos base que el código intenta usar ──
_CONTRATOS_BASE = {
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO (RESOLUCIÓN 054 Y 120 DE 2026)."
}

# ── Funciones de Diseño HTML (Helpers) ────────────────────────────────────────
def _div(texto): 
    return f'<div style="text-align:justify;line-height:1.6;font-size:11px;margin-top:10px;color:#1e293b;">{texto}</div>'

def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_h="#1e3a8a", color_e="#b91c1c"):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:10px;margin-bottom:10px;"><tr style="background-color:{color_h};color:white;"><th style="padding:5px;border:1px solid #ddd;">CÓDIGO GLOSA</th><th style="padding:5px;border:1px solid #ddd;">ESTADO</th><th style="padding:5px;border:1px solid #ddd;">VALOR OBJETADO</th><th style="padding:5px;border:1px solid #ddd;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:5px;border:1px solid #ddd;text-align:center;">{codigo}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;background-color:{color_e};color:white;"><b>{estado}</b></td><td style="padding:5px;border:1px solid #ddd;text-align:center;">{valor}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;font-weight:bold;">{cod_res}<br>{desc_res}</td></tr></table>'

def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:10px;margin-bottom:10px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:5px;border:1px solid #ddd;">CÓDIGO GLOSA</th><th style="padding:5px;border:1px solid #ddd;">SERVICIO RECLAMADO</th><th style="padding:5px;border:1px solid #ddd;">VALOR OBJ.</th><th style="padding:5px;border:1px solid #ddd;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:5px;border:1px solid #ddd;text-align:center;">{codigo}</td><td style="padding:5px;border:1px solid #ddd;">{servicio}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;">{valor}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;font-weight:bold;">{cod_res}<br>{desc_res}</td></tr></table>'

# ── Helpers PDF ───────────────────────────────────────────────────────────────
def _procesar_pdf_sync(file_content: bytes) -> str:
    paginas = []
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text() or ""
                for table in page.extract_tables() or []:
                    for row in table:
                        txt += " | ".join([str(c).replace("\n", " ") if c else "" for c in row]) + "\n"
                paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")
    except Exception:
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        for i in range(len(reader.pages)):
            txt = reader.pages[i].extract_text() or ""
            paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")

    if not paginas: return ""
    if len(paginas) <= 4: return "".join(paginas)
    
    inicio = "".join(paginas[:2])
    fin    = "".join(paginas[-2:])
    medio  = "".join(paginas[2:-2])
    return inicio[:3000] + "\n...[PÁGINAS INTERMEDIAS]...\n" + medio[:2000] + "\n...\n" + fin[:2000]

def calcular_dias_habiles(f_rad: str, f_rec: str) -> int:
    try:
        d1, d2 = datetime.strptime(f_rad, "%Y-%m-%d"), datetime.strptime(f_rec, "%Y-%m-%d")
        dias, current = 0, d1
        while current < d2:
            current += timedelta(days=1)
            if current.weekday() < 5 and current.strftime("%Y-%m-%d") not in FERIADOS_CO: dias += 1
        return dias
    except Exception: return 0

# ── Estrategias y Prompts ─────────────────────────────────────────────────────
SSYSTEM_ROL = """Eres el Director Jurídico de la ESE Hospital Universitario de Santander (HUS).
Tu función es DEFENDER a la institución y LOGRAR EL PAGO de las facturas.

IDENTIDAD INQUEBRANTABLE:
- Eres un abogado COMBATIVO y técnico.
- PROHIBIDO: Nunca aceptes una glosa. Nunca digas que la EPS tiene razón.
- PROHIBIDO: Nunca digas que 'no se puede objetar' o que 'la glosa es válida'.
- Si la glosa es confusa o no tiene servicio, argumenta que la EPS viola el debido proceso por falta de claridad."""

SYSTEM_FORMATO = """FORMATO DE RESPUESTA — OBLIGATORIO:
Responde ÚNICAMENTE con XML válido. Cero texto fuera del XML.
<paciente/><codigo_glosa/><valor_objetado/><servicio_glosado/><score_confianza/><argumento>DEFENSA EN MAYÚSCULAS...</argumento>"""

ESTRATEGIAS_LEGALES = {
    "TA_sin_contrato": (
        "ESTRATEGIA: Glosa tarifaria SIN CONTRATO. \n"
        "1. ENFATIZAR que no hay acuerdo de voluntades. \n"
        "2. Aplicar Art. 11 Dec. 4747/2007 (Manual SOAT 100%). \n"
        "3. Rechazar cualquier descuento unilateral por falta de base legal."
    ),
    "TA_con_contrato": "ESTRATEGIA: Cobro según tarifas pactadas. Art 871 C.Co. La EPS no puede glosar lo que ya firmó.",
    "SO": "ESTRATEGIA: La Historia Clínica es plena prueba (Res 1995/1999). Cualquier soporte faltante es subsanable y no anula el pago.",
    "SE": (
        "ESTRATEGIA: Glosa SIN SERVICIO ESPECÍFICO o por INSUMOS. \n"
        "1. RECHAZAR la glosa por INDETERMINACIÓN. La EPS debe ser clara en qué servicio objeta (Res. 3047/2008). \n"
        "2. Si es por insumos, argumentar que estos hacen parte integral del acto quirúrgico o médico prestado. \n"
        "3. EXIGIR el pago inmediato ya que el servicio principal SÍ fue prestado y soportado en la HC."
    ),
    "AU": "ESTRATEGIA: Urgencia vital no requiere autorización (Art 168 Ley 100/93).",
    "CO": "ESTRATEGIA: El servicio es obligación legal de la EPS bajo la Ley Estatutaria 1751/2015.",
    "PE": "ESTRATEGIA: Autonomía médica Ley 1751/2015 Art 17. La EPS no es médico tratante.",
    "FA": "ESTRATEGIA: Errores de facturación son subsanables (Circular 030/2013). No son causal de glosa definitiva.",
    "DEFAULT": "ESTRATEGIA DE CHOQUE: Rechazar la glosa por falta de fundamento técnico-legal claro. Exigir pago basado en la prestación efectiva del servicio."
}    

def _construir_prompt(info_contrato: str, estrategia: str, texto_glosa: str, contexto_pdf: str, eps: str) -> tuple[str, str]:
    system = "\n\n".join([SYSTEM_ROL, f"CONTRATO CON {eps.upper()}:\n{info_contrato}", f"ESTRATEGIA:\n{estrategia}", SYSTEM_FORMATO])
    user = f"GLOSA:\n{texto_glosa}\n\nSOPORTES:\n{contexto_pdf or 'Sin soportes.'}"
    return system, user

# ── Clase de Servicio Principal ───────────────────────────────────────────────
class GlosaService:
    def __init__(self, groq_api_key: str):
        self.groq = AsyncGroq(api_key=groq_api_key) if groq_api_key else None
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def extraer_pdf(self, file_content: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _procesar_pdf_sync, file_content)

    def _xml(self, tag: str, texto: str, default: str = "") -> str:
        m = re.search(fr"<{tag}>(.*?)</{tag}>", texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip().replace("**", "") if m else default

    async def _llamar_ia(self, system: str, user: str) -> tuple[str, str]:
        try:
            resp = await self.groq.chat.completions.create(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                model="llama-3.3-70b-versatile", temperature=0.15
            )
            return resp.choices[0].message.content, "groq/llama-3.3-70b"
        except Exception:
            if self.anthropic_key:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post("https://api.anthropic.com/v1/messages", 
                        headers={"x-api-key": self.anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": "claude-3-5-sonnet-20240620", "max_tokens": 1500, "system": system, "messages": [{"role": "user", "content": user}]})
                    return resp.json()["content"][0]["text"], "anthropic/claude-3.5-sonnet"
        return "<argumento>ERROR CONEXIÓN IA - REVISIÓN MANUAL</argumento>", "fallback/manual"

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        texto_base = str(data.tabla_excel).strip().upper()
        val_ac_num = float(re.sub(r"[^\d]", "", str(data.valor_aceptado)) or 0)
        codigo_det = self._extraer_codigo_glosa(texto_base)
        prefijo    = codigo_det[:2] if codigo_det != "N/A" else "XX"
        val_m      = re.search(r"\$\s*([\d\.,]+)", texto_base)
        valor_raw  = f"$ {val_m.group(1)}" if val_m else "$ 0.00"
        
        dias = calcular_dias_habiles(str(data.fecha_radicacion), str(data.fecha_recepcion)) if data.fecha_radicacion and data.fecha_recepcion else 0
        es_extemporanea = dias > 20
        msg_tiempo = f"EXTEMPORÁNEA ({dias} DÍAS)" if es_extemporanea else f"EN TÉRMINOS ({dias} DÍAS)"

        if "RATIF" in str(data.etapa).upper(): return self._respuesta_ratificacion(codigo_det, valor_raw, msg_tiempo, dias)
        if es_extemporanea and val_ac_num <= 0: return self._respuesta_extemporanea(codigo_det, valor_raw, msg_tiempo, dias)

        eps_key = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        todos_contratos = {**_CONTRATOS_BASE, **(contratos_db or {})}
        info_contrato = todos_contratos.get(eps_key, todos_contratos["OTRA / SIN DEFINIR"])
        
        estrategia = self._seleccionar_estrategia(prefijo, eps_key in ("OTRA", ""))
        system, user = _construir_prompt(info_contrato, estrategia, texto_base, contexto_pdf, eps_key)
        res_ia, modelo_usado = await self._llamar_ia(system, user)

        paciente = self._xml("paciente", res_ia, "NO IDENTIFICADO")
        servicio = self._xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        arg      = self._xml("argumento", res_ia, "SIN ARGUMENTO").replace("\n", "<br/>")
        
        dictamen = _tabla_defensa(codigo_det, servicio, valor_raw, "RE9602", "GLOSA INJUSTIFICADA") + _div(f"<b>ESE HUS NO ACEPTA GLOSA INJUSTIFICADA:</b><br/><br/>{arg}")
        return GlosaResult(tipo=f"TÉCNICO-LEGAL [{prefijo}]", resumen=f"DEFENSA: {paciente}", dictamen=dictamen, codigo_glosa=codigo_det, valor_objetado=valor_raw, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo="bg-emerald-500", score=80, dias_restantes=max(0, 20-dias))

    def _extraer_codigo_glosa(self, texto: str) -> str:
        patrones = [r"\b(TA\d{2,4})\b", r"\b(SO\d{2,4})\b", r"\b(AU\d{2,4})\b", r"\b(CO\d{2,4})\b", r"\b(PE\d{2,4})\b", r"\b(FA\d{2,4})\b", r"\b(MCV\d*)\b"]
        for p in patrones:
            m = re.search(p, texto)
            if m: return m.group(1)
        return "N/A"

    def _seleccionar_estrategia(self, prefijo: str, es_sin_contrato: bool) -> str:
        if prefijo == "TA": return ESTRATEGIAS_LEGALES["TA_sin_contrato" if es_sin_contrato else "TA_con_contrato"]
        return ESTRATEGIAS_LEGALES.get(prefijo, ESTRATEGIAS_LEGALES["DEFAULT"])

    def _respuesta_ratificacion(self, codigo, valor, msg_tiempo, dias):
        txt = "ESE HUS NO ACEPTA GLOSA RATIFICADA... (SE MANTIENE RESPUESTA INICIAL)"
        tabla = _tabla_simple(codigo, "RATIFICACIÓN", valor, "RE9901", "GLOSA NO ACEPTADA", color_e="#2563eb")
        return GlosaResult(tipo="LEGAL - RATIFICADA", resumen="RECHAZO RATIFICACIÓN", dictamen=tabla + _div(txt), codigo_glosa=codigo, valor_objetado=valor, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600", score=100, dias_restantes=max(0, 20-dias))

    def _respuesta_extemporanea(self, codigo, valor, msg_tiempo, dias):
        txt = f"ESE HUS NO ACEPTA GLOSA EXTEMPORÁNEA ({dias} DÍAS). OPERA ACEPTACIÓN TÁCITA (ART 57 LEY 1438/2011)."
        tabla = _tabla_simple(codigo, "EXTEMPORÁNEA", valor, "RE9502", "GLOSA FUERA DE TIEMPO")
        return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORANEIDAD", dictamen=tabla + _div(txt), codigo_glosa=codigo, valor_objetado=valor, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-red-600", score=100, dias_restantes=0)
