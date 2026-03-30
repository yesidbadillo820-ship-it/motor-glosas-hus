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
# EXTRACCIÓN DE PDF (Minería de Datos Asistencial)
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
        # Limitamos el contexto para no saturar los tokens de Groq
        if total > 8:
            unido = "".join(paginas[:2]) + "\n\n...[ANÁLISIS TÉCNICO INTERMEDIO]...\n\n" + "".join(paginas[-4:])
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
        
        # 🏛️ PILARES LEGALES DE LA E.S.E. HUS (Inyectados directamente en el cerebro)
        BASE_LEGAL_HUS = """
        - RESOLUCIÓN 054 DE 2026: Unifica tarifas institucionales y adopta el Manual de Tarifas Institucionales de la E.S.E. HUS. Es de OBLIGATORIO CUMPLIMIENTO para todas las Entidades Responsables de Pago (Art. 2).
        - RESOLUCIÓN 120 DE 2026: Crea y actualiza códigos y tarifas (especialmente Gastroenterología) incorporándolos al Manual de Tarifas Institucionales (Art. 2 y 4).
        - TARIFA SOBERANA: Ante ausencia de acuerdo contractual, la E.S.E. HUS liquida servicios a TARIFA SOAT PLENO (100% del Decreto 2423 de 1996) según lo dictado en el parágrafo de la Res. 054/2026.
        - AUTONOMÍA: La entidad es descentralizada con personería jurídica y autonomía administrativa (Decreto 0025 de 2005).
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

        # 🧠 ESTRATEGIA DE AUDITORÍA FORENSE - INSTRUCCIONES MILITARES
        if prefijo == "TA":
            estrategia = """ESTRATEGIA TARIFARIA OBLIGATORIA (MÍNIMO 3 PÁRRAFOS):
            - PÁRRAFO 1: Cita la RESOLUCIÓN 054 DE 2026 y la RESOLUCIÓN 120 DE 2026. Explica que estas normas unifican las tarifas de la E.S.E. HUS y son de cumplimiento OBLIGATORIO para las EPS.
            - PÁRRAFO 2: Defiende el cobro a TARIFA SOAT PLENO (100%). Argumenta que la EPS intenta imponer unilateralmente tarifas (como SMLV o indexaciones no pactadas) que vulneran la autonomía administrativa del hospital otorgada por el Decreto 0025 de 2005.
            - PÁRRAFO 3: Exige el pago del VALOR OBJETADO invocando el Art. 871 del Código de Comercio (Buena fe contractual). Finaliza indicando que el CÓDIGO DE RESPUESTA ES RE9602.
            - REGLA: Prohibido decir 'valor facturado'. Usa SIEMPRE 'VALOR OBJETADO'."""
        elif prefijo == "SO":
            estrategia = """ESTRATEGIA SOPORTES: Localiza en los anexos el documento clínico que la EPS dice que falta. Cita el médico, RM, hallazgos y fecha. Invoca la Res. 1995/1999 (Historia Clínica como plena prueba). PROHIBIDO hablar de facturas si es un soporte clínico. Código RE9602."""
        elif prefijo == "FA":
            estrategia = "ESTRATEGIA FACTURACIÓN: Defiende la autonomía del código CUPS glosado. Cita el Anexo 3 Res 3047/2008. Exige a la EPS la norma técnica que justifique la inclusión; de lo contrario, la glosa es improcedente."
        else:
            estrategia = "ESTRATEGIA INTEGRAL: Cruce milimétrico de la realidad fáctica del PDF contra el Manual de Tarifas Institucional."

        system_prompt = f"""Eres el DIRECTOR NACIONAL DE JURÍDICA Y AUDITORÍA DE LA ESE HUS. Tienes 30 años de experiencia ganando defensas contra EPS.
        REGLAS DE ORO:
        1. TODO EN MAYÚSCULAS.
        2. PROHIBIDO LAS RESPUESTAS CORTAS: Debes redactar un argumento extenso, técnico y legal (Mínimo 150 palabras).
        3. TERMINOLOGÍA: Nunca digas 'valor facturado'. Usa SIEMPRE 'VALOR OBJETADO'.
        4. FUNDAMENTO: {BASE_LEGAL_HUS}
        5. LÉXICO: Sinalagma contractual, Autonomía administrativa, Preclusión, Realidad fáctica, Acuerdo de voluntades.
        6. RESPUESTA XML: <paciente><codigo_glosa><valor_objetado><servicio_glosado><motivo_resumido><argumento>"""

        user_prompt = f"EPS: {eps_segura}\nNORMA: {info_c}\nESTRATEGIA: {estrategia}\nGLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:10000]}"

        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.2, # Mayor temperatura para fomentar redacción extensa
                    max_tokens=3000
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception: await asyncio.sleep(25)

        # Extracción segura
        paciente      = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_final  = self.xml("codigo_glosa", res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado", res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento", res_ia, "ERROR: LA IA NO GENERÓ EL ARGUMENTO.")
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
            # Lógica RE9602 para tarifas o SO institucional
            if (prefijo in ["TA", "SO"] or "OTRA" in eps_segura or "SIN DEFINIR" in eps_segura):
                cod_res, desc_res = "RE9602", "GLOSA NO ACEPTADA"
            else:
                cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA"
            
            tabla_html = _tabla_defensa(codigo_final, servicio, valor_xml, cod_res, desc_res)
            tipo_final, res_final = "TÉCNICO-LEGAL", f"DEFENSA FACTURA – {paciente}"

        if not re.search(r'^ESE HUS (NO |)ACEPTA', argumento_ia, re.IGNORECASE):
            dictamen_final = apertura + "\n\n" + argumento_ia
        else:
            dictamen_final = argumento_ia

        return GlosaResult(tipo=tipo_final, resumen=res_final, dictamen=tabla_html + f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{dictamen_final.replace("\n", "<br/>")}</div>', codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

# ── FUNCIONES TABLAS ──
def _div(texto): return f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{texto}</div>'
def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_header="#1e3a8a", color_estado=None):
    e_st = f'background-color:{color_estado};color:white;' if color_estado else ''
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:{color_header};color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">ESTADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;{e_st}"><b>{estado}</b></td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'
def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'
def _tabla_aceptacion(codigo, valor_obj, valor_acep, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor_obj}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;color:#d97706;">{valor_acep}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

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
