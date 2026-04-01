import os
import io
import re
import asyncio
import logging
from datetime import datetime, timedelta

import PyPDF2
from groq import AsyncGroq
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from models import GlosaInput, GlosaResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("motor_glosas_v2")

# FESTIVOS COLOMBIA 2025-2026 (Para cálculo exacto de vencimientos)
FERIADOS_CO = [
    "2025-01-01", "2025-01-06", "2025-03-24", "2025-04-17", "2025-04-18", "2025-05-01", "2025-06-02", "2025-06-23", "2025-06-30", "2025-07-20", "2025-08-07", "2025-08-18", "2025-10-13", "2025-11-03", "2025-11-17", "2025-12-08", "2025-12-25",
    "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03", "2026-05-01", "2026-05-18", "2026-06-08", "2026-06-15", "2026-06-29", "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25"
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. EXTRACCIÓN AVANZADA DE PDF (pdfplumber + Fallback a PyPDF2)
# ─────────────────────────────────────────────────────────────────────────────
def _procesar_pdf_sync(file_content: bytes) -> str:
    unido = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text() or ""
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        txt += " | ".join([str(c).replace('\n', ' ') if c else "" for c in row]) + "\n"
                unido += f"\n--- PÁG {i+1} ---\n{txt}"
    except Exception as e:
        logger.warning(f"Fallo pdfplumber, usando PyPDF2: {e}")
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        for i in range(len(reader.pages)):
            txt = reader.pages[i].extract_text()
            if txt: unido += f"\n--- PÁG {i+1} ---\n{txt}"

    if len(unido) > 8000:
        unido = unido[:4000] + "\n\n...[ANÁLISIS RECORTADO]...\n\n" + unido[-4000:]
    return unido

def _calcular_dias_habiles(f_rad, f_rec):
    try:
        d1 = datetime.strptime(f_rad, "%Y-%m-%d")
        d2 = datetime.strptime(f_rec, "%Y-%m-%d")
        dias = 0
        current = d1
        while current < d2:
            current += timedelta(days=1)
            if current.weekday() < 5 and current.strftime("%Y-%m-%d") not in FERIADOS_CO:
                dias += 1
        return dias
    except: return 0

# ─────────────────────────────────────────────────────────────────────────────
# 2. MOTOR IA GROQ (Con Fallback)
# ─────────────────────────────────────────────────────────────────────────────
class GlosaService:
    def __init__(self, api_key: str):
        self.cliente = AsyncGroq(api_key=api_key)

    async def extraer_pdf(self, file_content: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _procesar_pdf_sync, file_content)

    def xml(self, tag: str, texto: str, default: str = "") -> str:
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip().replace("**", "") if m else default

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}

        eps_segura = str(data.eps).upper() if data.eps else "OTRA"
        etapa_segura = str(data.etapa).strip().upper()
        
        info_c = contratos_db.get(eps_segura, "AUSENCIA DE CONTRATO. RIGE RESOLUCIÓN INSTITUCIONAL 054/2026 (SOAT PLENO).")
        tiene_contrato = eps_segura in contratos_db

        texto_base = str(data.tabla_excel).strip()
        val_ac_num = float(re.sub(r'[^\d]', '', str(data.valor_aceptado)) or 0)
        
        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_detectado[:2].upper() if codigo_detectado != "N/A" else "XX"
        
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        dias = _calcular_dias_habiles(data.fecha_radicacion, data.fecha_recepcion) if data.fecha_radicacion and data.fecha_recepcion else 0
        es_extemporanea = dias > 20
        dias_restantes = max(0, 20 - dias)

        msg_tiempo = f"EXTEMPORÁNEA ({dias} DÍAS)" if es_extemporanea else f"EN TÉRMINOS ({dias} DÍAS - FALTAN {dias_restantes})"
        color_tiempo = "bg-red-600" if es_extemporanea else "bg-emerald-500"

        # GUILLOTINAS
        if "RATIF" in etapa_segura and val_ac_num <= 0:
            txt = "ESE HUS RECHAZA DE PLANO LA RATIFICACIÓN POR INJUSTIFICADA. NO SE APORTAN NUEVOS ELEMENTOS DE JUICIO. SE SOLICITA CONCILIACIÓN (ART. 57 LEY 1438 DE 2011)."
            return GlosaResult(tipo="LEGAL - RATIFICADA", resumen="RECHAZO RATIFICACIÓN", dictamen=txt, codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600", dias_restantes=dias_restantes)

        if es_extemporanea and val_ac_num <= 0:
            txt = f"ESE HUS RECHAZA LA GLOSA POR INJUSTIFICADA Y EXTEMPORÁNEA ({dias} DÍAS HÁBILES). OPERA ACEPTACIÓN TÁCITA DE PLENO DERECHO. SE EXIGE EL PAGO INMEDIATO."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORANEIDAD", dictamen=txt, codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo, dias_restantes=0)

        # LAS 6 ESTRATEGIAS
        estrategias = {
            "TA": "P1: Cita contrato/Res. 054. P2: Desvirtúa descuento abusivo de EPS justificando liquidación HUS. P3: Exige pago por Buena Fe (Art 871 C.Co).",
            "SO": "P1: Cita contrato. P2: Demuestra que el soporte existe o que la Historia Clínica es plena prueba (Res 1995/99). P3: Exige pago.",
            "PE": "P1: Cita contrato. P2: Justifica pertinencia clínica del acto médico basado en la autonomía profesional (Ley 1751/15). P3: Exige pago.",
            "AU": "P1: Cita contrato. P2: Demuestra que se tramitó la autorización o que era una urgencia vital (Decreto 4747/07). P3: Exige pago.",
            "CO": "P1: Cita contrato. P2: Demuestra cobertura del servicio en el plan de beneficios o contrato. P3: Exige pago.",
            "FA": "P1: Cita contrato. P2: Aclara que la estructura de la factura cumple con la norma vigente. P3: Exige pago."
        }
        est_actual = estrategias.get(prefijo, estrategias["PE"])

        system_prompt = f"""Eres el DIRECTOR JURÍDICO de la ESE HUS. 
        REGLAS: TODO EN MAYÚSCULAS. MÍNIMO 3 PÁRRAFOS TÉCNICOS.
        MARCO: {info_c}
        ESTRATEGIA: {est_actual}
        DEVUELVE XML: <paciente>, <factura>, <autorizacion>, <codigo_glosa>, <valor_objetado>, <servicio_glosado>, <motivo_resumido>, <score> (0-100 nivel confianza), <argumento> (TU REDACCIÓN AQUÍ)."""

        user_prompt = f"EPS: {eps_segura}\nGLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:5000]}"

        res_ia = ""
        # FALLBACK ENGINE: Intenta 70B, si falla intenta Mixtral
        try:
            comp = await self.cliente.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                model="llama-3.3-70b-versatile", temperature=0.2, max_tokens=2000
            )
            res_ia = comp.choices[0].message.content
        except:
            try:
                comp = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="mixtral-8x7b-32768", temperature=0.2, max_tokens=2000
                )
                res_ia = comp.choices[0].message.content
            except Exception as e:
                res_ia = f"<argumento>ERROR DE IA: {str(e)}</argumento>"

        paciente = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        factura = self.xml("factura", res_ia, "N/A")
        autorizacion = self.xml("autorizacion", res_ia, "N/A")
        score = int(self.xml("score", res_ia, "100") or 100)
        argumento_ia = self.xml("argumento", res_ia, "").replace('\n', '<br/><br/>')
        
        if val_ac_num > 0:
            apertura = f"ESE HUS ACEPTA PARCIALMENTE LA GLOSA {codigo_detectado} POR $ {val_ac_num:,.0f}."
            tipo = "AUDITORÍA - ACEPTADA"
        else:
            apertura = f"ESE HUS NO ACEPTA LA GLOSA {codigo_detectado} POR CONSIDERARLA INJUSTIFICADA, SUSTENTANDO ASÍ:<br/><br/>"
            tipo = "TÉCNICO-LEGAL"

        return GlosaResult(
            tipo=tipo, resumen=f"DEFENSA: {paciente}", dictamen=apertura + argumento_ia,
            codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente=paciente,
            mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo,
            factura=factura, autorizacion=autorizacion, score=score, dias_restantes=dias_restantes
        )

# ─────────────────────────────────────────────────────────────────────────────
# 3. GENERADOR OFICIO PDF PRO (Membrete y Marca de Agua)
# ─────────────────────────────────────────────────────────────────────────────
def add_watermark(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica-Bold", 60)
    canvas_obj.setFillColor(colors.lightgrey)
    canvas_obj.translate(300, 400)
    canvas_obj.rotate(45)
    canvas_obj.drawCentredString(0, 0, "ESE H.U.S.")
    canvas_obj.restoreState()

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str, codigo: str = "N/A", valor: str = "N/A") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle('n', alignment=TA_JUSTIFY, fontSize=11, leading=16)
    
    elements = []
    fecha_str = datetime.now().strftime("%d de %B de %Y")
    radicado = f"ACMG-2026-{datetime.now().strftime('%m%d%H%M')}"

    # Encabezado
    elements.append(Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", ParagraphStyle('h1', alignment=TA_CENTER, fontSize=14)))
    elements.append(Paragraph("NIT: 890.201.222-0 | Oficina de Auditoría Médica", ParagraphStyle('h2', alignment=TA_CENTER, fontSize=10)))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Bucaramanga, {fecha_str}</b><br/><b>Radicado Oficio:</b> {radicado}", estilo_n))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Señores:</b><br/>{eps.upper()}<br/><b>Ref:</b> {resumen}", estilo_n))
    elements.append(Spacer(1, 15))

    # Tabla Resumen
    t_data = [['CÓDIGO GLOSA', 'VALOR OBJETADO', 'ESTADO'], [codigo, valor, 'GLOSA INJUSTIFICADA / RECHAZADA']]
    t = Table(t_data, colWidths=[120, 150, 200])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1c3460")),
                           ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                           ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                           ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                           ('BOTTOMPADDING', (0,0), (-1,0), 8),
                           ('GRID', (0,0), (-1,-1), 1, colors.black)]))
    elements.append(t)
    elements.append(Spacer(1, 20))

    # Cuerpo
    clean_text = re.sub(r'<br\s*/?>', '\n', conclusion).strip()
    for p in clean_text.split('\n\n'):
        if p.strip(): elements.append(Paragraph(p.strip(), estilo_n))
        elements.append(Spacer(1, 8))

    # Firmas
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("__________________________________________<br/><b>JEFE DE AUDITORÍA DE CUENTAS MÉDICAS</b><br/>ESE Hospital Universitario de Santander", estilo_n))

    doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)
    buffer.seek(0)
    return buffer.read()

# ─────────────────────────────────────────────────────────────────────────────
# 4. EXPORTACIÓN EXCEL PRO
# ─────────────────────────────────────────────────────────────────────────────
def exportar_excel_pro(glosas: list) -> bytes:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte Glosas HUS"

    headers = ["Fecha", "EPS", "Factura", "Paciente", "Código", "Valor", "Estado", "Días Restantes"]
    ws.append(headers)

    header_fill = PatternFill(start_color="1C3460", end_color="1C3460", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    
    for col_num, cell in enumerate(ws[1], 1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = 18

    ws.column_dimensions['B'].width = 30 # EPS
    ws.column_dimensions['D'].width = 30 # Paciente

    for g in glosas:
        ws.append([
            g['creado_en'][:10], g['eps'], g.get('factura', 'N/A'), 
            g['paciente'], g['codigo_glosa'], g['valor_objetado'], 
            g['estado'], g.get('dias_restantes', 0)
        ])

    # Auto-filter
    ws.auto_filter.ref = ws.dimensions

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
