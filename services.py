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

from models import GlosaInput, GlosaResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("motor_glosas_v2")

FERIADOS_CO = [
    "2025-01-01", "2025-01-06", "2025-03-24", "2025-04-17", "2025-04-18", "2025-05-01", "2025-06-02", "2025-06-23", "2025-06-30", "2025-07-20", "2025-08-07", "2025-08-18", "2025-10-13", "2025-11-03", "2025-11-17", "2025-12-08", "2025-12-25",
    "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03", "2026-05-01", "2026-05-18", "2026-06-08", "2026-06-15", "2026-06-29", "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25"
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. EXTRACCIÓN AVANZADA DE PDF (pdfplumber + Fallback)
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
# 2. MOTOR IA GROQ (FEW-SHOT EXAMPLES + FALLBACK)
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
        
        info_c = contratos_db.get(eps_segura, "AUSENCIA DE CONTRATO VIGENTE. RIGE RESOLUCIÓN INSTITUCIONAL 054 Y 120 DE 2026 (SOAT PLENO 100%).")
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

        # GUILLOTINAS LEGALES
        if "RATIF" in etapa_segura and val_ac_num <= 0:
            txt = "ESE HUS NO ACEPTA GLOSA RATIFICADA. NO SE APORTAN NUEVOS ELEMENTOS DE JUICIO. SE SOLICITA CONCILIACIÓN (ART. 57 LEY 1438 DE 2011)."
            return GlosaResult(tipo="LEGAL - RATIFICADA", resumen="RECHAZO RATIFICACIÓN", dictamen=txt, codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600", dias_restantes=dias_restantes)

        if es_extemporanea and val_ac_num <= 0:
            txt = f"ESE HUS NO ACEPTA GLOSA EXTEMPORÁNEA ({dias} DÍAS HÁBILES). OPERA ACEPTACIÓN TÁCITA DE PLENO DERECHO. SE EXIGE EL PAGO INMEDIATO."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORANEIDAD", dictamen=txt, codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo, dias_restantes=0)

        # 🎯 FEW-SHOT EXAMPLES (Ejemplos de entrenamiento en vivo)
        few_shot_examples = """
        <ejemplos_de_respuestas_perfectas>
        --- EJEMPLO 1 (GLOSA TARIFARIA - TA) ---
        USUARIO: EPS: SANITAS. GLOSA: TA0201 Diferencia tarifa. CUPS 890793 CONSULTA URGENCIAS. Valor Glosado: $ 150.000.
        ASISTENTE:
        <paciente>CARLOS PEREZ</paciente>
        <factura>F-1020</factura>
        <autorizacion>N/A</autorizacion>
        <codigo_glosa>TA0201</codigo_glosa>
        <valor_objetado>$ 150.000</valor_objetado>
        <servicio_glosado>CONSULTA DE URGENCIAS</servicio_glosado>
        <motivo_resumido>DIFERENCIA DE TARIFA</motivo_resumido>
        <score>98</score>
        <argumento>EN PRIMER LUGAR, ES IMPORTANTE DESTACAR QUE EL MARCO INSTITUCIONAL QUE RIGE LA PRESENTE FACTURACIÓN ES LA RESOLUCIÓN 054 Y 120 DE 2026 DE LA E.S.E. HUS, LA CUAL ESTABLECE LA LIQUIDACIÓN A TARIFA SOAT PLENO 100% ANTE LA AUSENCIA DE OTRO ACUERDO VIGENTE.
        
        EN SEGUNDO LUGAR, SE DESVIRTÚA TOTALMENTE EL DESCUENTO ABUSIVO APLICADO POR LA EPS, YA QUE EL HOSPITAL LIQUIDÓ EL VALOR DEL SERVICIO CORRECTAMENTE Y CON APEGO ESTRICTO AL MANUAL TARIFARIO ESTABLECIDO. LA ENTIDAD RESPONSABLE DEL PAGO NO PUEDE IMPONER TARIFAS UNILATERALES QUE NO HAN SIDO PACTADAS PREVIAMENTE MEDIANTE UN ACUERDO DE VOLUNTADES.
        
        EN TERCER LUGAR, EXIGIMOS EL PAGO INMEDIATO DEL VALOR OBJETADO, TODA VEZ QUE EL ARTÍCULO 871 DEL CÓDIGO DE COMERCIO COLOMBIANO OBLIGA A LAS PARTES A EJECUTAR SUS ACTUACIONES DE BUENA FE. POR LO TANTO, LA NEGATIVA AL PAGO CONSTITUYE UN INCUMPLIMIENTO INJUSTIFICADO, REQUIRIENDO EL REINTEGRO TOTAL A FAVOR DE NUESTRA INSTITUCIÓN.</argumento>

        --- EJEMPLO 2 (GLOSA SOPORTES - SO) ---
        USUARIO: EPS: NUEVA EPS. GLOSA: SO0409 Soportes ilegibles. CUPS 903825 CREATININA. Valor Glosado: $ 45.000.
        ASISTENTE:
        <paciente>MARIA GOMEZ</paciente>
        <factura>F-2040</factura>
        <autorizacion>A-992</autorizacion>
        <codigo_glosa>SO0409</codigo_glosa>
        <valor_objetado>$ 45.000</valor_objetado>
        <servicio_glosado>CREATININA EN SUERO</servicio_glosado>
        <motivo_resumido>FALTA DE SOPORTES</motivo_resumido>
        <score>95</score>
        <argumento>EN PRIMER LUGAR, SE EVIDENCIA QUE LA ATENCIÓN PRESTADA SE ENCUENTRA AMPARADA POR EL CONTRATO VIGENTE ENTRE LAS PARTES, EL CUAL ESTABLECE CLARAMENTE LOS REQUISITOS DE SOPORTE PARA EL COBRO DE ESTOS SERVICIOS.
        
        EN SEGUNDO LUGAR, LA OBJECIÓN CARECE DE FUNDAMENTO, PUESTO QUE LA HISTORIA CLÍNICA ADJUNTA A LA FACTURACIÓN CONSTITUYE PLENA PRUEBA DE LA REALIZACIÓN DEL PROCEDIMIENTO, TAL COMO LO ESTABLECE LA RESOLUCIÓN 1995 DE 1999 DEL MINISTERIO DE SALUD. EL REGISTRO MÉDICO DEMUESTRA LA TOMA DE LA MUESTRA Y EL ANÁLISIS PERTINENTE, CUMPLIENDO CON LOS REQUISITOS LEGALES EXIGIDOS.
        
        EN TERCER LUGAR, SE REQUIERE EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO DEL VALOR OBJETADO, YA QUE LA INSTITUCIÓN HA DEMOSTRADO FEHACIENTEMENTE LA PRESTACIÓN EFECTIVA DEL SERVICIO. LA RETENCIÓN DE ESTOS RECURSOS VULNERA EL EQUILIBRIO CONTRACTUAL Y EL PRINCIPIO DE BUENA FE ESTABLECIDO EN LA NORMATIVIDAD COMERCIAL Y EN SALUD VIGENTE.</argumento>
        </ejemplos_de_respuestas_perfectas>
        """

        estrategias = {
            "TA": "P1: Cita contrato o Res. 054. P2: Desvirtúa descuento abusivo de EPS. P3: Exige pago por Buena Fe (Art 871 C.Co).",
            "SO": "P1: Cita contrato. P2: Demuestra que la Historia Clínica es plena prueba (Res 1995/99). P3: Exige pago.",
            "PE": "P1: Cita contrato. P2: Justifica pertinencia clínica del acto médico basado en autonomía profesional (Ley 1751/15). P3: Exige pago.",
            "AU": "P1: Cita contrato. P2: Demuestra urgencia vital o trámite de autorización (Decreto 4747/07). P3: Exige pago."
        }
        est_actual = estrategias.get(prefijo, estrategias["PE"])

        system_prompt = f"""Eres el DIRECTOR JURÍDICO de la ESE HUS.
        REGLAS INQUEBRANTABLES:
        1. DEBES IMITAR EXACTAMENTE EL FORMATO, TONO Y ESTRUCTURA DE LOS <ejemplos_de_respuestas_perfectas>.
        2. TODO TU TEXTO DEBE ESTAR EN MAYÚSCULAS.
        3. LA ETIQUETA <argumento> DEBE TENER EXACTAMENTE 3 PÁRRAFOS TÉCNICOS.
        4. DEFIENDE ESTE MARCO: {info_c}
        5. APLICA ESTA ESTRATEGIA: {est_actual}
        
        {few_shot_examples}
        
        DEVUELVE ÚNICAMENTE EL XML: <paciente>, <factura>, <autorizacion>, <codigo_glosa>, <valor_objetado>, <servicio_glosado>, <motivo_resumido>, <score> (0-100), <argumento> (TRES PÁRRAFOS)."""

        user_prompt = f"USUARIO: EPS: {eps_segura}. GLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:5000]}\nASISTENTE:"

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

        # EXTRACCIÓN Y BLINDAJE REGEX (A PRUEBA DE FALLOS)
        paciente = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        factura = self.xml("factura", res_ia, "N/A")
        autorizacion = self.xml("autorizacion", res_ia, "N/A")
        
        codigo_final = self.xml("codigo_glosa", res_ia, codigo_detectado)
        if len(codigo_final) > 10 or codigo_final == "N/A": codigo_final = codigo_detectado
        
        valor_xml = self.xml("valor_objetado", res_ia, valor_obj_raw)
        if "$" not in valor_xml and not any(char.isdigit() for char in valor_xml): valor_xml = valor_obj_raw
            
        score = int(self.xml("score", res_ia, "100") or 100)
        argumento_ia = self.xml("argumento", res_ia, "").replace('\n', '<br/><br/>')
        
        if val_ac_num > 0:
            apertura = f"ESE HUS ACEPTA PARCIALMENTE LA GLOSA {codigo_final} POR $ {val_ac_num:,.0f}.<br/><br/>"
            tipo = "AUDITORÍA - ACEPTADA"
        else:
            apertura = f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} POR CONSIDERARLA INJUSTIFICADA, SUSTENTANDO ASÍ:<br/><br/>"
            tipo = "TÉCNICO-LEGAL"

        return GlosaResult(
            tipo=tipo, resumen=f"DEFENSA: {paciente}", dictamen=apertura + argumento_ia,
            codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente,
            mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo,
            factura=factura, autorizacion=autorizacion, score=score, dias_restantes=dias_restantes
        )

# ─────────────────────────────────────────────────────────────────────────────
# 3. GENERADOR OFICIO PDF PRO
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

    elements.append(Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", ParagraphStyle('h1', alignment=TA_CENTER, fontSize=14)))
    elements.append(Paragraph("NIT: 890.201.222-0 | Oficina de Auditoría Médica", ParagraphStyle('h2', alignment=TA_CENTER, fontSize=10)))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Bucaramanga, {fecha_str}</b><br/><b>Radicado Oficio:</b> {radicado}", estilo_n))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Señores:</b><br/>{eps.upper()}<br/><b>Ref:</b> {resumen}", estilo_n))
    elements.append(Spacer(1, 15))

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

    clean_text = re.sub(r'<br\s*/?>', '\n', conclusion).strip()
    for p in clean_text.split('\n\n'):
        if p.strip(): elements.append(Paragraph(p.strip(), estilo_n))
        elements.append(Spacer(1, 8))

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

    ws.column_dimensions['B'].width = 30 
    ws.column_dimensions['D'].width = 30 

    for g in glosas:
        ws.append([
            g['creado_en'][:10], g['eps'], g.get('factura', 'N/A'), 
            g['paciente'], g['codigo_glosa'], g['valor_objetado'], 
            g['estado'], g.get('dias_restantes', 0)
        ])

    ws.auto_filter.ref = ws.dimensions

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
