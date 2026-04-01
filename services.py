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
# 1. EXTRACCIÓN DE PDF (Minería de Datos)
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
        if len(unido) > 6000:
            unido = unido[:3000] + "\n\n...[ANÁLISIS TÉCNICO INTERMEDIO]...\n\n" + unido[-3000:]
        return unido
    except Exception:
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# 2. SERVICIO DE AUDITORÍA Y JURÍDICA E.S.E. HUS
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
        
        tiene_contrato = False
        info_c = "AUSENCIA DE CONTRATO VIGENTE. Rige la RESOLUCIÓN INSTITUCIONAL 054 DE 2026 de la ESE HUS (TARIFA SOAT PLENO 100%)."
        
        for k, v in contratos_db.items():
            if k in eps_segura and "OTRA" not in k:
                info_c = v
                tiene_contrato = True
                break

        texto_base = str(data.tabla_excel).strip()
        val_ac_num = self.convertir_numero(data.valor_aceptado)
        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_detectado[:2].upper() if codigo_detectado != "N/A" else "XX"
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

        # 🛡️ 3. GUILLOTINAS LEGALES (TRATO DE INJUSTIFICADAS)
        if "RATIF" in etapa_segura and val_ac_num <= 0:
            tabla = _tabla_simple(codigo_detectado, "RATIFICACIÓN", valor_obj_raw, "RE9901", "GLOSA INJUSTIFICADA")
            texto_rat = (
                "ESE HUS RECHAZA DE PLANO LA RATIFICACIÓN DE LA GLOSA POR CONSIDERARLA ABSOLUTAMENTE INJUSTIFICADA. "
                "LA INSTITUCIÓN SE RATIFICA EN LA DEFENSA INICIAL, TODA VEZ QUE LA ENTIDAD GLOSANTE NO APORTA NUEVOS "
                "ELEMENTOS DE JUICIO O SOPORTES QUE DESVIRTÚEN LA FACTURACIÓN.\n\n"
                "SE DA POR AGOTADA LA INSTANCIA Y SE SOLICITA CONCILIACIÓN SEGÚN LEY 1438 DE 2011."
            )
            return GlosaResult(tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO DE RATIFICACIÓN", dictamen=tabla + _div(texto_rat), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600")

        if es_extemporanea and val_ac_num <= 0:
            tabla = _tabla_simple(codigo_detectado, f"EXTEMPORÁNEA", valor_obj_raw, "RE9502", "GLOSA INJUSTIFICADA", color_estado="#b91c1c")
            texto_ext = (
                f"ESE HUS RECHAZA LA GLOSA POR CONSIDERARLA INJUSTIFICADA DEBIDO A SU EXTEMPORANEIDAD. AL TRANSCURRIR {dias} DÍAS HÁBILES, "
                "OPERA DE PLENO DERECHO LA ACEPTACIÓN TÁCITA (ART. 57 LEY 1438/2011). SE EXIGE EL PAGO INMEDIATO."
            )
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO POR EXTEMPORANEIDAD", dictamen=tabla + _div(texto_ext), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

        # 🧠 4. CEREBRO IA (ESTRUCTURA DE 3 PÁRRAFOS)
        base_normativa = info_c if tiene_contrato else "LA RESOLUCIÓN 054 Y 120 DE 2026 DE LA ESE HUS."
        
        system_prompt = f"""Eres el DIRECTOR JURÍDICO DE LA ESE HUS. 
        REGLAS:
        1. TODO EN MAYÚSCULAS.
        2. MÍNIMO 3 PÁRRAFOS TÉCNICOS Y EXTENSOS.
        3. USA SIEMPRE 'VALOR OBJETADO'.
        4. DEFIENDE ESTE MARCO: {base_normativa}
        5. FORMATO XML: <paciente>, <codigo_glosa>, <valor_objetado>, <servicio_glosado>, <motivo_resumido>, <argumento>."""

        user_prompt = f"EPS: {eps_segura}\nGLOSA: {texto_base}\nSOPORTES PDF: {contexto_pdf[:6000]}"

        res_ia = ""
        for intento in range(2):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.3,
                    max_tokens=2500
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception: await asyncio.sleep(15)

        # 5. ENSAMBLAJE FINAL
        paciente      = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_final  = self.xml("codigo_glosa", res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado", res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento", res_ia, "") or re.sub(r'<[^>]+>', '', res_ia).strip()

        if val_ac_num > 0:
            valor_acep_fmt = f"$ {val_ac_num:,.0f}".replace(",", ".")
            apertura = f"ESE HUS ACEPTA LA GLOSA {codigo_final} POR UN VALOR DE {valor_acep_fmt}: "
            cod_res, desc_res = "RE9801", "GLOSA ACEPTADA"
            tabla_html = _tabla_aceptacion(codigo_final, valor_xml, valor_acep_fmt, cod_res, desc_res)
        else:
            # ❗ LA FRASE DE PODER SOLICITADA ❗
            apertura = f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} POR CONSIDERARLA INJUSTIFICADA, TODA VEZ QUE LA OBJECIÓN POR {motivo} CARECE DE SUSTENTO CONTRACTUAL Y NORMATIVO, SUSTENTANDO NUESTRA POSICIÓN ASÍ: "
            cod_res, desc_res = "RE9602", "GLOSA INJUSTIFICADA"
            tabla_html = _tabla_defensa(codigo_final, servicio, valor_xml, cod_res, desc_res)

        if not re.search(r'^ESE HUS', argumento_ia, re.IGNORECASE):
            dictamen_final = apertura + "\n\n" + argumento_ia
        else:
            dictamen_final = argumento_ia

        return GlosaResult(tipo="TÉCNICO-LEGAL", resumen=f"DEFENSA FACTURA – {paciente}", dictamen=tabla_html + _div(dictamen_final.replace("\n", "<br/><br/>")), codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────

def _div(texto): 
    return f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{texto}</div>'

def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_header="#1e3a8a", color_estado=None):
    e_st = f'background-color:{color_estado};color:white;' if color_estado else ''
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:{color_header};color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">ESTADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;{e_st}"><b>{estado}</b></td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

def _tabla_aceptacion(codigo, valor_obj, valor_acep, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor_obj}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;color:#d97706;">{valor_acep}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

# ─────────────────────────────────────────────────────────────────────────────
# 6. GENERADOR DE OFICIO PDF
# ─────────────────────────────────────────────────────────────────────────────

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle('n', parent=estilos['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=16)
    estilo_titulo = ParagraphStyle('titulo', parent=estilos['Heading1'], alignment=1, fontSize=14, spaceAfter=20)
    
    match = re.search(r'<div[^>]*>(.*?)</div>', conclusion, re.IGNORECASE | re.DOTALL)
    cuerpo = match.group(1) if match else conclusion
    clean  = re.sub(r'<br\s*/?>', '\n', re.sub(r'<[^>]+>', '', cuerpo)).strip()
    
    fecha = datetime.now().strftime("%d/%m/%Y")
    elements = []
    
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=250, height=60)
            img.hAlign = 'LEFT'
            elements.extend([img, Spacer(1, 15)])
        except: pass

    elements.extend([
        Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", estilo_titulo),
        Paragraph("<b>OFICINA DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS</b>", ParagraphStyle('sub', alignment=1, fontSize=12)),
        Spacer(1, 30), Paragraph(f"Bucaramanga, {fecha}", estilo_n), Spacer(1, 20),
        Paragraph(f"<b>Señores:</b><br/>{eps.upper()}", estilo_n), Spacer(1, 20),
        Paragraph(f"<b>ASUNTO:</b> {resumen}", estilo_n), Spacer(1, 20),
    ])
    
    for parrafo in clean.split('\n'):
        if parrafo.strip(): elements.extend([Paragraph(parrafo.strip(), estilo_n), Spacer(1, 8)])
    
    elements.extend([Spacer(1, 40), Paragraph("__________________________________________", estilo_n), Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n)])
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
