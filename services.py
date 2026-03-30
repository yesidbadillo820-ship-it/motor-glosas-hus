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
# EXTRACCIÓN DE PDF (PROCESAMIENTO DE SOPORTES)
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
        if total > 8:
            unido = "".join(paginas[:2]) + "\n\n...[ANÁLISIS TÉCNICO E INSTITUCIONAL]...\n\n" + "".join(paginas[-4:])
        return unido[:16000]
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
            logger.error("Error al extraer PDF", exc_info=True)
            return ""

    def convertir_numero(self, m_str: str) -> float:
        if not m_str: return 0.0
        clean = re.sub(r'[^\d]', '', str(m_str))
        try: return float(clean)
        except ValueError: return 0.0

    def xml(self, tag: str, texto: str, default: str = "N/A") -> str:
        """Parser XML blindado para extracción segura de datos de la IA."""
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip().replace("**", "").replace("*", "")
            return val if val else default
        return default

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}

        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        BASE_LEGAL_HUS = """
        - RESOLUCIÓN INSTITUCIONAL 054 DE 2026: Realiza la unificación de las Resoluciones de tarifas Institucionales y adopta el Manual de Tarifas de la E.S.E. HUS. El cumplimiento de este manual es OBLIGATORIO para facturar a las ERP (Artículo Segundo).
        - RESOLUCIÓN INSTITUCIONAL 120 DE 2026: Crea códigos y tarifas institucionales específicos (incluyendo Gastroenterología) e incorpora estos al Manual de Tarifas Unificado.
        - TARIFA SOBERANA: En ausencia de contrato pactado, rige el Manual Tarifario Institucional y la Resolución 054 de 2026, aplicando TARIFA SOAT PLENO (100% del Decreto 2423 de 1996) sin descuentos.
        """

        info_c = contratos_db.get("OTRA / SIN DEFINIR", 
            f"AUSENCIA DE CONTRATO VIGENTE. Rige de manera vinculante la RESOLUCIÓN 054 DE 2026 y la RESOLUCIÓN 120 DE 2026 de la E.S.E. HUS. La tarifa institucional obligatoria es SOAT PLENO (100% del Decreto 2423 de 1996) según el Artículo Segundo de la norma citada.")
        
        for k, v in contratos_db.items():
            if k in eps_segura:
                info_c = v
                break

        texto_base    = str(data.tabla_excel).strip()
        val_ac_num    = self.convertir_numero(data.valor_aceptado)
        is_ratificada = str(data.etapa).strip().upper() == "RATIFICADA"

        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_detectado[:2].upper()
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        msg_tiempo, color_tiempo, es_extemporanea, dias = "Fechas no ingresadas", "bg-slate-500", False, 0
        if data.fecha_radicacion and data.fecha_recepcion:
            try:
                f1 = datetime.strptime(data.fecha_radicacion, "%Y-%m-%d")
                f2 = datetime.strptime(data.fecha_recepcion, "%Y-%m-%d")
                dia_actual = f1
                while dia_actual < f2:
                    dia_actual += timedelta(days=1)
                    if dia_actual.weekday() < 5: dias += 1
                if dias > 20:
                    es_extemporanea, msg_tiempo, color_tiempo = True, f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES)", "bg-red-600"
                else:
                    msg_tiempo, color_tiempo = f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)", "bg-emerald-500"
            except Exception: pass

        if is_ratificada and val_ac_num == 0:
            tabla = _tabla_simple(codigo_detectado, "RATIFICACIÓN", valor_obj_raw, "RE9901", "GLOSA SUBSANADA TOTALMENTE", color_header="#1e3a8a")
            texto_rat = "ESE HUS NO ACEPTA LA GLOSA RATIFICADA. SE MANTIENE EN SU INTEGRIDAD LA RESPUESTA DE DEFENSA TÉCNICA PRESENTADA INICIALMENTE, TODA VEZ QUE LA ENTIDAD GLOSANTE NO APORTA NUEVOS ELEMENTOS QUE DESVIRTÚEN LA FACTURACIÓN. SE SOLICITA CONCILIACIÓN (CARTERA@HUS.GOV.CO) SEGÚN LEY 1438 DE 2011."
            return GlosaResult(tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO DE RATIFICACIÓN", dictamen=tabla + _div(texto_rat), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600")

        if es_extemporanea and val_ac_num == 0:
            tabla = _tabla_simple(codigo_detectado, f"EXTEMPORÁNEA ({dias} DÍAS)", valor_obj_raw, "RE9502", "ACEPTACIÓN TÁCITA", color_estado="#b91c1c")
            texto_ext = f"ESE HUS NO ACEPTA LA GLOSA POR EXTEMPORANEIDAD. AL HABER TRANSCURRIDO {dias} DÍAS HÁBILES, SE HA SUPERADO EL TÉRMINO LEGAL DEL ART. 57 LEY 1438 DE 2011. OPERA LA ACEPTACIÓN TÁCITA DE LA FACTURA. SE EXIGE EL PAGO INMEDIATO."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO POR EXTEMPORANEIDAD", dictamen=tabla + _div(texto_ext), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

        if val_ac_num > 0:
            tesis = "CASO ACEPTACIÓN: Redacta en <argumento> que la ESE HUS acepta el valor por pertinencia administrativa, ajustando la cuenta."
        elif prefijo == "TA":
            tesis = f"ESTRATEGIA TARIFARIA: Cita Res 054/2026 y 120/2026. Hospital factura SOAT PLENO. Prohibido 'valor facturado', usa 'VALOR OBJETADO'. Código RE9602."
        elif prefijo == "SO":
            tesis = "ESTRATEGIA SOPORTES: Localiza resultado clínico (Ej. Patología Dr. García). Cita médico/hallazgo. Invoca Res 1995/1999. Usa 'VALOR OBJETADO'."
        elif prefijo == "FA":
            tesis = "ESTRATEGIA FACTURACIÓN: Defiende acto médico autónomo. Cita Anexo 3 Res 3047. Exige norma de inclusión."
        else:
            tesis = "ESTRATEGIA INTEGRAL: Defiende pertinencia según Ley 1751/2015 y realidad clínica."

        system_prompt = f"""Eres el DIRECTOR NACIONAL DE AUDITORÍA Y JURÍDICA DE LA ESE HUS. 30 años de experiencia. 
        TODO EN MAYÚSCULAS. PROHIBIDO RESPUESTAS CORTAS. 
        USA SIEMPRE 'VALOR OBJETADO'. FUNDAMENTO: {BASE_LEGAL_HUS}"""

        user_prompt = f"EPS: {eps_segura}\nCONTRATO: {info_c}\nESTRATEGIA: {tesis}\nGLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:10000]}"

        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.15,
                    max_tokens=2500
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception: await asyncio.sleep(25)

        paciente      = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_final  = self.xml("codigo_glosa", res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado", res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento", res_ia, "RECHAZO POR CARECER DE SUSTENTO NORMATIVO.")
        argumento_ia  = re.sub(r'[ \t]+', ' ', argumento_ia).strip()

        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor_xml)
            valor_acep_fmt = f"$ {val_ac_num:,.0f}".replace(",", ".")
            apertura = f"ESE HUS ACEPTA LA GLOSA {codigo_final} POR UN VALOR DE {valor_acep_fmt}. "
            cod_res, desc_res = ("RE9702", "GLOSA ACEPTADA TOTALMENTE") if val_ac_num >= val_obj_num else ("RE9801", "GLOSA PARCIALMENTE ACEPTADA")
            tabla_html = _tabla_aceptacion(codigo_final, valor_xml, valor_acep_fmt, cod_res, desc_res)
            tipo_final, res_final = "AUDITORÍA - ACEPTACIÓN", f"ACEPTACIÓN DE GLOSA – {paciente}"
        else:
            apertura = f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} INTERPUESTA POR {motivo}, Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS TÉCNICOS, CONTRACTUALES Y NORMATIVOS: "
            cod_res, desc_res = ("RE9602", "GLOSA NO ACEPTADA") if (prefijo in ["TA", "SO"] or "OTRA" in eps_segura) else ("RE9901", "GLOSA NO ACEPTADA")
            tabla_html = _tabla_defensa(codigo_final, servicio, valor_xml, cod_res, desc_res)
            tipo_final, res_final = "TÉCNICO-LEGAL", f"DEFENSA FACTURA – {paciente}"

        if not re.search(r'^ESE HUS (NO |)ACEPTA', argumento_ia, re.IGNORECASE):
            argumento_ia = apertura + "\n\n" + argumento_ia

        return GlosaResult(tipo=tipo_final, resumen=res_final, dictamen=tabla_html + f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{argumento_ia.replace("\n", "<br/>")}</div>', codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES DE TABLAS HTML
# ─────────────────────────────────────────────────────────────────────────────

def _div(texto): return f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{texto}</div>'

def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_header="#1e3a8a", color_estado=None):
    e_st = f'background-color:{color_estado};color:white;' if color_estado else ''
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:{color_header};color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">ESTADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;{e_st}"><b>{estado}</b></td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

def _tabla_aceptacion(codigo, valor_obj, valor_acep, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor_obj}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;color:#d97706;">{valor_acep}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

# ─────────────────────────────────────────────────────────────────────────────
# GENERADOR DE OFICIO PDF (ReportLab)
# ─────────────────────────────────────────────────────────────────────────────

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle('n', parent=estilos['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=16)
    estilo_titulo = ParagraphStyle('titulo', parent=estilos['Heading1'], alignment=1, fontSize=14, spaceAfter=20)
    
    # Limpiamos HTML del dictamen para el PDF
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
        Spacer(1, 30),
        Paragraph(f"Bucaramanga, {fecha}", estilo_n),
        Spacer(1, 20),
        Paragraph(f"<b>Señores:</b><br/>{eps.upper()}", estilo_n),
        Spacer(1, 20),
        Paragraph(f"<b>ASUNTO:</b> {resumen}", estilo_n),
        Spacer(1, 20),
    ])
    
    for parrafo in clean.split('\n'):
        if parrafo.strip():
            elements.extend([Paragraph(parrafo.strip(), estilo_n), Spacer(1, 6)])
            
    elements.extend([
        Spacer(1, 40),
        Paragraph("__________________________________________", estilo_n),
        Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n)
    ])
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
