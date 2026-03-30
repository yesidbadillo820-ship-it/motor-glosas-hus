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
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip().replace("**", "").replace("*", "")
            return val if val else default
        return default

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}

        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        
        # 📘 BASE DE DATOS LEGAL INTERNA DE LA IA (Extraído de Resoluciones 054 y 120 de 2026)
        # Sustenta con: [cite: 51, 85, 86, 77, 234, 1425, 1460]
        CONOCIMIENTO_INSTITUCIONAL = """
        DERECHO APLICABLE DE LA E.S.E. HUS:
        1. RESOLUCIÓN 054 DE 2026 (30 ENE 2026): Unifica tarifas y adopta el Manual de Tarifas Institucionales. Es de OBLIGATORIO CUMPLIMIENTO para facturar servicios, medicamentos e insumos a las Entidades Responsables de Pago (Art. Segundo).
        2. TARIFA SOBERANA: Según el numeral 9 de la Res. 054/2026, la E.S.E. HUS podrá utilizar el sistema de codificación y tarifas que considere apropiado para efectos de facturación.
        3. CASO SIN CONTRATO: El parágrafo de la Res. 054 establece que la facturación a entidades sin contrato se realizará según el manual tarifario vigente. En ausencia de acuerdo, la institución aplica TARIFA SOAT PLENO (100% del Decreto 2423 de 1996) sin descuentos.
        4. RESOLUCIÓN 120 DE 2026 (19 MAR 2026): Crea códigos y tarifas para Gastroenterología e incorpora estas tarifas al listado institucional unificado de la Res. 054.
        """

        info_c = contratos_db.get("OTRA / SIN DEFINIR", 
            f"AUSENCIA DE CONTRATO VIGENTE. Rige de manera vinculante la RESOLUCIÓN 054 DE 2026 y la RESOLUCIÓN 120 DE 2026 de la E.S.E. HUS. La tarifa institucional obligatoria es SOAT PLENO (100% del Decreto 2423 de 1996).")
        
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

        # ── ANÁLISIS DE TIEMPOS ──
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

        # 🧠 ESTRATEGIA DE DEFENSA SENIOR (RECONSTRUIDA)
        if prefijo == "TA":
            tesis = """DEBES REDACTAR UNA DEFENSA EXTENSA (MÍNIMO 3 PÁRRAFOS):
            1. FUNDAMENTO: Cita la RESOLUCIÓN 054 DE 2026 y explica que, según su ARTÍCULO SEGUNDO, el Manual de Tarifas Institucionales es de cumplimiento obligatorio.
            2. ARGUMENTO SOAT PLENO: Explica que al no existir contrato con descuentos, la E.S.E. HUS ejerce su autonomía administrativa (Decreto 0025 de 2005) facturando a TARIFA SOAT PLENO (100%).
            3. CRÍTICA A LA EPS: Señala que la reliquidación unilateral de la EPS vulnera el principio de buena fe (Art. 871 C.Co) y el equilibrio económico del hospital.
            4. TERMINOLOGÍA: USA SIEMPRE 'VALOR OBJETADO'. NUNCA 'VALOR FACTURADO'."""
        elif prefijo == "SO":
            tesis = """ESTRATEGIA SOPORTES: Localiza en el PDF el resultado clínico específico (Ej. Notas del médico, Patología). Cita nombre, Registro Médico y fecha. Invoca la Res. 1995/1999 para demostrar que el soporte clínico es plena prueba. Exige el reconocimiento del VALOR OBJETADO."""
        elif prefijo == "FA":
            tesis = """ESTRATEGIA FACTURACIÓN: Defiende que el servicio es un acto médico autónomo e independiente con código CUPS propio. Cita el Anexo 3 de la Res. 3047/2008."""
        else:
            tesis = "ESTRATEGIA INTEGRAL: Defiende la pertinencia médica y el derecho fundamental a la salud (Ley 1751/2015), contrastando los soportes con el Manual Tarifario Institucional."

        system_prompt = f"""Eres el DIRECTOR NACIONAL DE JURÍDICA Y AUDITORÍA DE LA ESE HUS. Tienes 30 años de experiencia ganando defensas contra las EPS. 
        TU MISIÓN: Redactar dictámenes contundentes, técnicos y legales.
        
        REGLAS DE ORO:
        1. TODO EN MAYÚSCULAS.
        2. PROHIBIDO LAS RESPUESTAS CORTAS O GENÉRICAS. Debes redactar mínimo 150 palabras de sustento legal.
        3. CONOCIMIENTO INSTITUCIONAL OBLIGATORIO: {CONOCIMIENTO_INSTITUCIONAL}
        4. TERMINOLOGÍA: Usa 'VALOR OBJETADO'. Está prohibido decir 'valor facturado'.
        5. LÉXICO: Sinalagma contractual, Realidad fáctica, Preclusión, Autonomía administrativa, Acuerdo de voluntades."""

        user_prompt = f"EPS: {eps_segura}\nCONTRATO/NORMA: {info_c}\nESTRATEGIA: {tesis}\nGLOSA: {texto_base}\nSOPORTES CLÍNICOS: {contexto_pdf[:12000]}"

        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.2, # Un poco más de libertad para que redacte más
                    max_tokens=3000
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception: await asyncio.sleep(25)

        # Extracción y Construcción
        paciente      = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_final  = self.xml("codigo_glosa", res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado", res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento", res_ia, "ERROR: LA IA NO GENERÓ SUFICIENTE ARGUMENTO.")
        argumento_ia  = re.sub(r'[ \t]+', ' ', argumento_ia).strip()

        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor_xml)
            valor_acep_fmt = f"$ {val_ac_num:,.0f}".replace(",", ".")
            apertura = f"ESE HUS ACEPTA LA GLOSA {codigo_final} POR UN VALOR DE {valor_acep_fmt}, CONSIDERANDO LO SIGUIENTE: "
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

# ── FUNCIONES TABLAS (Mantenemos las que tienes en main) ──
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
        if parrafo.strip(): elements.extend([Paragraph(parrafo.strip(), estilo_n), Spacer(1, 6)])
    elements.extend([Spacer(1, 40), Paragraph("__________________________________________", estilo_n), Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n)])
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
