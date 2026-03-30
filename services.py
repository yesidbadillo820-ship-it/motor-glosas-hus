import os
import io
import re
import asyncio
import logging
from datetime import datetime, timedelta

import PyPDF2
from groq import AsyncGroq
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY

from models import GlosaInput, GlosaResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("motor_glosas")

# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN DE PDF
# ─────────────────────────────────────────────────────────────────────────────

def _procesar_pdf_sync(file_content: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        total = len(reader.pages)
        paginas = []
        for i in range(total):
            txt = reader.pages[i].extract_text()
            if txt:
                paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")
        unido = "".join(paginas)
        if len(unido) > 8000:
            unido = unido[:4000] + "\n\n...[ANÁLISIS TÉCNICO]...\n\n" + unido[-4000:]
        return unido
    except Exception:
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO DE AUDITORÍA Y JURÍDICA E.S.E. HUS
# ─────────────────────────────────────────────────────────────────────────────

class GlosaService:
    def __init__(self, api_key: str):
        self.cliente = AsyncGroq(api_key=api_key)

    async def extraer_pdf(self, file_content: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _procesar_pdf_sync, file_content)
        except Exception:
            return ""

    def convertir_numero(self, m_str: str) -> float:
        if not m_str: return 0.0
        clean = re.sub(r'[^\d]', '', str(m_str))
        try: return float(clean)
        except ValueError: return 0.0

    def xml(self, tag: str, texto: str, default: str = "") -> str:
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip().replace("**", "").replace("*", "")
            return val if val else default
        return default

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}

        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        etapa_segura = str(data.etapa).strip().upper()
        
        # 1. DETERMINAR SI EXISTE CONTRATO O USAMOS RESOLUCIÓN
        tiene_contrato = False
        info_c = "AUSENCIA DE CONTRATO VIGENTE. Rige la RESOLUCIÓN 054 DE 2026 (SOAT PLENO)."
        
        for k, v in contratos_db.items():
            if k in eps_segura and "OTRA" not in k:
                info_c = v
                tiene_contrato = True
                break

        # 2. PRE-PROCESAMIENTO
        texto_base = str(data.tabla_excel).strip()
        val_ac_num = self.convertir_numero(data.valor_aceptado)
        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_detectado[:2].upper()
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        # ── CÁLCULO DE EXTEMPORANEIDAD ──
        msg_tiempo, color_tiempo, es_extemporanea, dias = "Fechas no ingresadas", "bg-slate-500", False, 0
        if data.fecha_radicacion and data.fecha_recepcion:
            try:
                f1 = datetime.strptime(data.fecha_radicacion, "%Y-%m-%d")
                f2 = datetime.strptime(data.fecha_recepcion, "%Y-%m-%d")
                dias = sum(1 for d in range((f2 - f1).days) if (f1 + timedelta(days=d+1)).weekday() < 5)
                if dias > 20:
                    es_extemporanea, msg_tiempo, color_tiempo = True, f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES)", "bg-red-600"
                else:
                    msg_tiempo, color_tiempo = f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)", "bg-emerald-500"
            except Exception: pass

        # 🛡️ GUILLOTINAS LEGALES (RATIFICACIÓN / EXTEMPORÁNEA)
        if "RATIF" in etapa_segura and val_ac_num <= 0:
            tabla = _tabla_simple(codigo_detectado, "RATIFICACIÓN", valor_obj_raw, "RE9901", "GLOSA SUBSANADA TOTALMENTE")
            texto_rat = "ESE HUS NO ACEPTA LA GLOSA RATIFICADA. SE MANTIENE LA DEFENSA INICIAL. SE SOLICITA CONCILIACIÓN SEGÚN LEY 1438 DE 2011."
            return GlosaResult(tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO DE RATIFICACIÓN", dictamen=tabla + _div(texto_rat), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600")

        if es_extemporanea and val_ac_num <= 0:
            tabla = _tabla_simple(codigo_detectado, f"EXTEMPORÁNEA ({dias} DÍAS)", valor_obj_raw, "RE9502", "ACEPTACIÓN TÁCITA", color_estado="#b91c1c")
            texto_ext = f"ESE HUS NO ACEPTA POR EXTEMPORANEIDAD (ART. 57 LEY 1438/2011). OPERA ACEPTACIÓN TÁCITA."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO POR EXTEMPORANEIDAD", dictamen=tabla + _div(texto_ext), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

        # 🧠 3. ESTRATEGIA SEGÚN ESCENARIO CONTRACTUAL
        if tiene_contrato:
            base_normativa = f"EL ACUERDO DE VOLUNTADES PACTADO: {info_c}"
            prioridad = "PRIORIZA EL CONTRATO. Cita el número de contrato y las tarifas (Ej: SOAT -20%). Explica que el cobro se ajusta estrictamente a lo pactado."
        else:
            base_normativa = "LA RESOLUCIÓN INSTITUCIONAL 054 DE 2026 y 120 DE 2026 de la E.S.E. HUS."
            prioridad = "DEFIENDE LA SOBERANÍA TARIFARIA. Explica que ante falta de contrato, rige la Res. 054/2026 (TARIFA SOAT PLENO 100%)."

        system_prompt = f"""Eres el DIRECTOR DE JURÍDICA Y AUDITORÍA DE LA ESE HUS.
        REGLAS:
        1. TODO EN MAYÚSCULAS.
        2. {prioridad}
        3. USA 'VALOR OBJETADO'. NUNCA 'valor facturado'.
        4. DICTAMEN EXTENSO (MÍNIMO 2 PÁRRAFOS TÉCNICOS).
        5. FORMATO XML: <paciente>, <codigo_glosa>, <valor_objetado>, <servicio_glosado>, <motivo_resumido>, <argumento>."""

        user_prompt = f"EPS: {eps_segura}\nBASE NORMATIVA: {base_normativa}\nGLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:8000]}"

        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    temperature=0.25,
                    max_tokens=2500
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception: await asyncio.sleep(20)

        # 4. ENSAMBLAJE
        paciente      = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_final  = self.xml("codigo_glosa", res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado", res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento", res_ia, "") or re.sub(r'<[^>]+>', '', res_ia).strip()

        apertura = f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} INTERPUESTA POR {motivo}, Y SUSTENTA SU POSICIÓN ASÍ: "
        cod_res, desc_res = ("RE9602", "GLOSA NO ACEPTADA") if (prefijo in ["TA", "SO"] or not tiene_contrato) else ("RE9901", "GLOSA NO ACEPTADA")
        
        if val_ac_num > 0:
            # Lógica de aceptación si el usuario puso un valor aceptado
            # ... (se mantiene igual que antes)
            pass

        tabla_html = _tabla_defensa(codigo_final, servicio, valor_xml, cod_res, desc_res)
        return GlosaResult(tipo="TÉCNICO-LEGAL", resumen=f"DEFENSA FACTURA – {paciente}", dictamen=tabla_html + _div(apertura + "\n\n" + argumento_ia), codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

# ... [Mantenemos las funciones auxiliares _div, _tabla_simple, _tabla_defensa, _tabla_aceptacion y crear_oficio_pdf]
