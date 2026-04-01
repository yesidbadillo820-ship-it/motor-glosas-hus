import io
import re
import asyncio
import logging
from datetime import datetime, timedelta

import pdfplumber
import PyPDF2
from groq import AsyncGroq
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_RIGHT
from reportlab.lib import colors

from models import GlosaInput, GlosaResult

logger = logging.getLogger("motor_glosas_v2")

FERIADOS_CO = [
    "2025-01-01", "2025-01-06", "2025-03-24", "2025-04-17", "2025-04-18", "2025-05-01", "2025-06-02", "2025-06-23", "2025-06-30", "2025-07-20", "2025-08-07", "2025-08-18", "2025-10-13", "2025-11-03", "2025-11-17", "2025-12-08", "2025-12-25",
    "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03", "2026-05-01", "2026-05-18", "2026-06-08", "2026-06-15", "2026-06-29", "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25"
]

CONTRATOS_FIJOS = {
    "COOSALUD": "CONTRATOS: 68001S00060339-24 y 68001C00060340-24. TARIFA: SOAT -15% e Institucionales. OBS: MAOS por HUS, Oncológicos por EPS.",
    "COMPENSAR": "CONTRATO: CSS009-2024. TARIFA: SOAT -15% y Tarifas Propias. OBS: Excluye oncológicos. MAOS por EPS.",
    "FAMISANAR": "CARTA DE INTENCIÓN. TARIFA: SOAT UVB -5% e Institucionales.",
    "FOMAG": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15%, Institucionales y Paquetes (Tórax, IVE, Columna, Terapias, Gastro).",
    "LA PREVISORA": "CONTRATO: 12076-359-2025. TARIFA: SOAT -15% y Paquetes.",
    "DISPENSARIO MEDICO": "CONTRATO: 440-DIGSA/DMBUG-2025. TARIFA: SOAT SMLV -20% e Institucionales.",
    "POLICIA NACIONAL": "CONTRATOS: 068-5-200004-26 y 068-5-200006-26. TARIFA: SOAT UVB -8% e Institucionales. OBS: Contrato 0006-26 INCLUYE medicamentos oncológicos.",
    "NUEVA EPS": "CONTRATO: 02-01-06-00077-2017. TARIFA: SOAT -20% e Institucionales. OBS: Meds Oncológicos por HUS.",
    "PPL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%. OBS: MAOS y Meds por HUS.",
    "FIDUCIARIA CENTRAL": "CONTRATO: IPS-001B-2022 (Otrosí 26). TARIFA: SOAT -15%.",
    "POSITIVA": "CONTRATO: 525 - OTROSÍ 3. TARIFA: SOAT SMLV -15%. OBS: Solo accidentes/laboral.",
    "PRECIMED": "CONTRATO: 319 DE 2024. TARIFA: Tarifas anexos / Institucionales.",
    "SALUD MIA": "CONTRATOS: SSA2025EVE3A005 y CSA2025EVE3A005. TARIFA: SOAT -15%. OBS: Urgencias Circular 019/2023.",
    "AURORA": "CONTRATOS: GID ARL 0090 y GID AP 0090. TARIFA: SOAT -3%.",
    "SECRETARIA DE SANTANDER": "MARCO LEGAL: Resolución 15997 de 2017 (Tarifas obligatorias ente territorial).",
    "SUMIMEDICAL": "CONTRATO: FPS23-050. TARIFA: SOAT -15%. OBS: MAOS y Oncológicos por EPS.",
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO (RESOLUCIÓN 054 DE 2026_0001 / DECRETO 441 DE 2022)."
}

ESTRATEGIAS = {
    "TA": "ESTRATEGIA TARIFARIA: Citar contrato o Res. 054. Demostrar liquidación correcta. Invocar Art. 871 C.Co (Buena Fe).",
    "SO": "ESTRATEGIA SOPORTES: Demostrar que la Historia Clínica es plena prueba (Res. 1995/99). Identificar envío de documentos.",
    "PE": "ESTRATEGIA PERTINENCIA: Autonomía médica (Ley 1751/15). Justificar acto médico basado en diagnóstico.",
    "AU": "ESTRATEGIA AUTORIZACIÓN: Urgencia vital (Art. 168 Ley 100/93). Trámite oportuno de autorizaciones."
}

def _div(texto): 
    return f'<div style="text-align:justify;line-height:1.6;font-size:11px;margin-top:10px;color:#1e293b;">{texto}</div>'

def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_h="#1e3a8a", color_e="#b91c1c"):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:10px;margin-bottom:10px;"><tr style="background-color:{color_h};color:white;"><th style="padding:5px;border:1px solid #ddd;">CÓDIGO GLOSA</th><th style="padding:5px;border:1px solid #ddd;">ESTADO</th><th style="padding:5px;border:1px solid #ddd;">VALOR OBJETADO</th><th style="padding:5px;border:1px solid #ddd;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:5px;border:1px solid #ddd;text-align:center;">{codigo}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;background-color:{color_e};color:white;"><b>{estado}</b></td><td style="padding:5px;border:1px solid #ddd;text-align:center;">{valor}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;font-weight:bold;">{cod_res}<br>{desc_res}</td></tr></table>'

def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:10px;margin-bottom:10px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:5px;border:1px solid #ddd;">CÓDIGO GLOSA</th><th style="padding:5px;border:1px solid #ddd;">SERVICIO RECLAMADO</th><th style="padding:5px;border:1px solid #ddd;">VALOR OBJ.</th><th style="padding:5px;border:1px solid #ddd;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:5px;border:1px solid #ddd;text-align:center;">{codigo}</td><td style="padding:5px;border:1px solid #ddd;">{servicio}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;">{valor}</td><td style="padding:5px;border:1px solid #ddd;text-align:center;font-weight:bold;">{cod_res}<br>{desc_res}</td></tr></table>'

def _procesar_pdf_sync(file_content: bytes) -> str:
    unido = ""
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text() or ""
                for table in page.extract_tables() or []:
                    for row in table:
                        txt += " | ".join([str(c).replace('\n', ' ') if c else "" for c in row]) + "\n"
                unido += f"\n--- PÁG {i+1} ---\n{txt}"
    except:
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        for i in range(len(reader.pages)):
            txt = reader.pages[i].extract_text()
            if txt: unido += f"\n--- PÁG {i+1} ---\n{txt}"
    return unido[:4000] + "\n...[RECORTADO]...\n" + unido[-4000:] if len(unido) > 8000 else unido

def calcular_dias_habiles(f_rad, f_rec):
    try:
        d1, d2 = datetime.strptime(f_rad, "%Y-%m-%d"), datetime.strptime(f_rec, "%Y-%m-%d")
        dias, current = 0, d1
        while current < d2:
            current += timedelta(days=1)
            if current.weekday() < 5 and current.strftime("%Y-%m-%d") not in FERIADOS_CO: dias += 1
        return dias
    except: return 0

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
        etapa_str = str(data.etapa).upper()
        texto_base = str(data.tabla_excel).strip().upper()
        val_ac_num = float(re.sub(r'[^\d]', '', str(data.valor_aceptado)) or 0)
        
        cod_m = re.search(r'\b([A-Z]{2,3}\d{0,4})\b', texto_base)
        codigo_det = cod_m.group(1) if cod_m else "N/A"
        if codigo_det == "N/A" and ("MCV" in texto_base or "MV" in texto_base): codigo_det = "MCV"
        
        prefijo = codigo_det[:2]
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        dias = calcular_dias_habiles(data.fecha_radicacion, data.fecha_recepcion) if data.fecha_radicacion and data.fecha_recepcion else 0
        es_extemporanea = dias > 20
        msg_tiempo = f"EXTEMPORÁNEA ({dias} DÍAS)" if es_extemporanea else f"EN TÉRMINOS ({dias} DÍAS)"

        # RATIFICACIÓN
        if "RATIF" in etapa_str:
            txt_ratif = ("ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE DE LA GLOSA INICIAL "
                         "Y CONTINUACIÓN DEL PROCESO DE ACUERDO CON LA NORMA. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE LA "
                         "CONCILIACIÓN DE LA AUDITORÍA MÉDICA Y/O TÉCNICA ENTRE LAS PARTES. CUALQUIER INFORMACIÓN AL CORREO "
                         "ELECTRÓNICO INSTITUCIONAL CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO, VENTANILLA ÚNICA DE "
                         "LA ESE HUS CARRERA 33 NO. 28-126. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, "
                         "DE NO OBTENERSE LA RATIFICACIÓN DE LA RESPUESTA A LA GLOSA EN LOS TÉRMINOS ESTABLECIDOS, SE DARÁ POR "
                         "LEVANTADA LA RESPECTIVA OBJECIÓN.")
            tabla = _tabla_simple(codigo_det, "RATIFICACIÓN", valor_raw, "RE9901", "GLOSA NO ACEPTADA Y SUBSANADA EN SU TOTALIDAD", color_e="#2563eb")
            return GlosaResult(tipo="LEGAL - RATIFICADA", resumen="RECHAZO RATIFICACIÓN", dictamen=tabla + _div(txt_ratif), codigo_glosa=codigo_det, valor_objetado=valor_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600", dias_restantes=max(0, 20-dias))

        # EXTEMPORÁNEA (Texto Legal Solicitado con variable dinámica)
        if es_extemporanea and val_ac_num <= 0:
            txt_ext = (
                f"ESE HUS NO ACEPTA GLOSA EXTEMPORÁNEA. AL HABERSE SUPERADO DICHO PLAZO LEGAL (HAN TRANSCURRIDO {dias} DÍAS HÁBILES "
                "ENTRE LA RADICACIÓN Y LA RECEPCIÓN) SIN QUE NUESTRA INSTITUCIÓN RECIBIERA NOTIFICACIÓN FORMAL DE LAS OBJECIONES "
                "DENTRO DEL TÉRMINO ESTABLECIDO, HA OPERADO DE PLENO DERECHO EL FENÓMENO JURÍDICO DE LA ACEPTACIÓN TÁCITA DE LA FACTURA. "
                "EN CONSECUENCIA, HA PRECLUIDO DEFINITIVAMENTE LA OPORTUNIDAD LEGAL DE LA EPS PARA AUDITAR, GLOSAR O RETENER LOS RECURSOS "
                "ASOCIADOS A ESTA CUENTA, DE CONFORMIDAD CON LO DISPUESTO EN EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 Y EL ARTÍCULO 13 "
                "(LITERAL D) DE LA LEY 1122 DE 2007, ASÍ COMO LO REGLAMENTADO EN EL DECRETO 4747 DE 2007 (ACTUALMENTE COMPILADO EN EL "
                "DECRETO ÚNICO REGLAMENTARIO 780 DE 2016) Y LA RESOLUCIÓN 3047 DE 2008 CON SUS RESPECTIVAS MODIFICACIONES, LAS ENTIDADES "
                "RESPONSABLES DEL PAGO (EPS) CUENTAN CON UN TÉRMINO MÁXIMO, PERENTÓRIO E IMPRORROGABLE DE VEINTE (20) DÍAS HÁBILES, "
                "CONTADOS A PARTIR DE LA FECHA DE RADICACIÓN DE LA FACTURA CON SUS RESPECTIVOS SOPORTES, PARA FORMULAR Y COMUNICAR DE "
                "MANERA SIMULTÁNEA TODAS LAS GLOSAS A LAS QUE HAYA LUGAR, SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA "
                "TOTALIDAD DE LAS GLOSAS APLICADAS."
            )
            tabla = _tabla_simple(codigo_det, "EXTEMPORÁNEA", valor_raw, "RE9502", "GLOSA O DEVOLUCIÓN EXTEMPORÁNEA")
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORANEIDAD", dictamen=tabla + _div(txt_ext), codigo_glosa=codigo_det, valor_objetado=valor_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-red-600", dias_restantes=0)

       # CASO INICIAL (IA) 
        eps_key = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        info_c = {**CONTRATOS_FIJOS, **(contratos_db or {})}.get(eps_key, CONTRATOS_FIJOS["OTRA / SIN DEFINIR"])
        
        est_actual = ESTRATEGIAS.get(prefijo, "ESTRATEGIA GENERAL: Desvirtuar la glosa apelando a la pertinencia médica, los soportes clínicos adjuntos y el principio de buena fe (Art 871 C.Co). Exigir pago.")

        # --- INICIO DEL CÓDIGO A REEMPLAZAR ---
        sys_p = f"""Eres el Director Jurídico y de Auditoría de Cuentas de la ESE HUS (Colombia).
        MARCO CONTRACTUAL A APLICAR: {info_c}
        ESTRATEGIA DE DEFENSA: {est_actual}
        
        REGLAS ESTRICTAS:
        1. Tu respuesta debe ser ÚNICAMENTE en código XML válido. Cero saludos, cero texto fuera del XML.
        2. El <argumento> debe contener una defensa técnica y jurídica robusta, de mínimo 2 párrafos.
        3. TODO EL TEXTO DEL ARGUMENTO DEBE ESTAR EN MAYÚSCULAS.
        4. No inventes datos que no estén en la glosa.

        FORMATO OBLIGATORIO:
        <paciente>Nombre del paciente (o NO IDENTIFICADO)</paciente>
        <codigo_glosa>Código alfanumérico (ej. TA0201, o N/A)</codigo_glosa>
        <valor_objetado>Monto en pesos (ej. $ 1.500.000, o N/A)</valor_objetado>
        <servicio_glosado>Nombre del servicio (o SERVICIOS ASISTENCIALES)</servicio_glosado>
        <argumento>AQUÍ VA TU REDACCIÓN LEGAL Y TÉCNICA DEFENDIENDO A LA ESE HUS...</argumento>"""
        
        try:
            comp = await self.cliente.chat.completions.create(
                messages=[
                    {"role": "system", "content": sys_p}, 
                    {"role": "user", "content": f"GLOSA:\n{texto_base}\n\nSOPORTES:\n{contexto_pdf[:3000]}"}
                ],
                model="llama-3.3-70b-versatile", 
                temperature=0.2
            )
            res_ia = comp.choices[0].message.content
        except Exception as e: 
            res_ia = f"<argumento>ERROR DE CONEXIÓN CON IA: {str(e)}</argumento>"
        # --- FIN DEL CÓDIGO A REEMPLAZAR ---

        paciente = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        servicio = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        arg = self.xml("argumento", res_ia, "SIN ARGUMENTO").replace('\n', '<br/>')

        paciente = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        servicio = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        arg = self.xml("argumento", res_ia, "SIN ARGUMENTO").replace('\n', '<br/>')
        
        dictamen = _tabla_defensa(codigo_det, servicio, valor_raw, "RE9602", "GLOSA O DEVOLUCIÓN INJUSTIFICADA") + _div(f"<b>ESE HUS NO ACEPTA GLOSA INJUSTIFICADA:</b><br/><br/>{arg}")
        
        return GlosaResult(tipo=f"TÉCNICO-LEGAL [{prefijo}]", resumen=f"DEFENSA: {paciente}", dictamen=dictamen, codigo_glosa=codigo_det, valor_objetado=valor_raw, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo="bg-emerald-500", score=95, dias_restantes=max(0, 20-dias))

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str, codigo: str = "N/A", valor: str = "$ 0.00") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=2.4*cm, leftMargin=2.4*cm, topMargin=2.2*cm, bottomMargin=2.2*cm)
    
    navy = colors.HexColor("#0b1829")
    st_body = ParagraphStyle('B', fontName='Helvetica', fontSize=10, leading=16, alignment=TA_JUSTIFY, textColor=navy)
    st_center = ParagraphStyle('C', fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER, textColor=navy)
    
    cuerpo = re.sub(r'<table.*?>.*?</table>', '', conclusion, flags=re.IGNORECASE | re.DOTALL)
    cuerpo = re.sub(r'<br\s*/?>', '\n', re.sub(r'<[^>]+>', '', cuerpo)).strip()
    
    elems = []
    elems.append(Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", ParagraphStyle('T', fontName='Helvetica-Bold', fontSize=13, alignment=TA_CENTER, textColor=navy)))
    elems.append(HRFlowable(width="100%", thickness=1, color=navy))
    elems.append(Spacer(1, 20))
    elems.append(Paragraph(f"Bucaramanga, {datetime.now().strftime('%d de %m de %Y')}", st_body))
    elems.append(Spacer(1, 15))
    elems.append(Paragraph(f"<b>Señores:</b><br/>{eps.upper()}<br/><b>Ref:</b> {resumen}", st_body))
    elems.append(Spacer(1, 15))

    # TABLA NATIVA DE REPORTLAB PARA EL PDF
    tabla_datos = [
        [Paragraph("<b>CÓDIGO GLOSA</b>", st_center), Paragraph("<b>VALOR OBJETADO</b>", st_center)],
        [Paragraph(codigo, st_center), Paragraph(valor, st_center)]
    ]
    t = Table(tabla_datos, colWidths=[7*cm, 7*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#e2eaf5")),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 15))

    for parr in cuerpo.split('\n'):
        if parr.strip():
            elems.append(Paragraph(parr.strip(), st_body))
            elems.append(Spacer(1, 10))

    doc.build(elems)
    buf.seek(0)
    return buf.read()

def exportar_excel_pro(glosas: list) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ID", "Fecha", "EPS", "Paciente", "Código", "Valor", "Estado"])
    for g in glosas: ws.append([g.id, g.creado_en.strftime("%d/%m/%Y"), g.eps, g.paciente, g.codigo_glosa, g.valor_objetado, g.estado])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
