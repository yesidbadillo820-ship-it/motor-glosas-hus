import io
import re
import asyncio
import logging
from datetime import datetime, timedelta

import PyPDF2
from groq import AsyncGroq
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
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
    except Exception:
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        for i in range(len(reader.pages)):
            txt = reader.pages[i].extract_text()
            if txt: unido += f"\n--- PÁG {i+1} ---\n{txt}"
    return unido[:4000] + "\n...[RECORTADO]...\n" + unido[-4000:] if len(unido) > 8000 else unido

def _calcular_dias_habiles(f_rad, f_rec):
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
        eps_segura = str(data.eps).upper() if data.eps else "OTRA"
        info_c = (contratos_db or {}).get(eps_segura.replace(" / SIN DEFINIR", "").strip(), CONTRATOS_FIJOS["OTRA / SIN DEFINIR"])
        
        texto_base = str(data.tabla_excel).strip()
        val_ac_num = float(re.sub(r'[^\d]', '', str(data.valor_aceptado)) or 0)
        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_detectado[:2].upper() if codigo_detectado != "N/A" else "XX"
        
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        nombres_glosa = {"TA": "TARIFAS", "SO": "SOPORTES", "FA": "FACTURACIÓN", "PE": "PERTINENCIA", "AU": "AUTORIZACIÓN", "CO": "COBERTURA"}
        nombre_tipo = nombres_glosa.get(prefijo, "OBJECIONES VARIAS")

        dias = _calcular_dias_habiles(data.fecha_radicacion, data.fecha_recepcion) if data.fecha_radicacion and data.fecha_recepcion else 0
        es_extemporanea = dias > 20
        dias_restantes = max(0, 20 - dias)

        msg_tiempo = f"EXTEMPORÁNEA ({dias} DÍAS)" if es_extemporanea else f"EN TÉRMINOS ({dias} DÍAS)"
        color_tiempo = "bg-red-600" if es_extemporanea else "bg-emerald-500"

        if "RATIF" in str(data.etapa).upper() and val_ac_num <= 0:
            txt = f"ESE HUS NO ACEPTA LA GLOSA POR {nombre_tipo} ({codigo_detectado}) EN INSTANCIA DE RATIFICACIÓN. NO SE APORTAN NUEVOS ELEMENTOS. SE SOLICITA CONCILIACIÓN."
            return GlosaResult(tipo="LEGAL - RATIFICADA", resumen="RECHAZO RATIFICACIÓN", dictamen=txt, codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600", dias_restantes=dias_restantes)

        if es_extemporanea and val_ac_num <= 0:
            txt = f"ESE HUS NO ACEPTA LA GLOSA POR {nombre_tipo} ({codigo_detectado}) POR HABER SIDO NOTIFICADA DE MANERA EXTEMPORÁNEA ({dias} DÍAS HÁBILES). OPERA ACEPTACIÓN TÁCITA DE PLENO DERECHO. SE EXIGE EL PAGO INMEDIATO."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORANEIDAD", dictamen=txt, codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo, dias_restantes=0)

        estrategia = "P1: Cita contrato. P2: Desvirtúa glosa. P3: Exige pago por Buena Fe (Art 871 C.Co)."
        system_prompt = f"""Eres el DIRECTOR JURÍDICO de la ESE HUS. DEBES RESPONDER EN XML. TODO EN MAYÚSCULAS. 3 PÁRRAFOS TÉCNICOS.
        MARCO: {info_c}. ESTRATEGIA: {estrategia}.
        DEVUELVE: <paciente>, <factura>, <autorizacion>, <codigo_glosa>, <valor_objetado>, <servicio_glosado>, <score> (0-100), <argumento> (TRES PÁRRAFOS)."""
        user_prompt = f"EPS: {eps_segura}. GLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:5000]}"

        try:
            comp = await self.cliente.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                model="llama-3.3-70b-versatile", temperature=0.2, max_tokens=2000
            )
            res_ia = comp.choices[0].message.content
        except Exception as e:
            res_ia = f"<argumento>ERROR DE IA: {str(e)}</argumento>"

        paciente = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_final = self.xml("codigo_glosa", res_ia, codigo_detectado)
        if len(codigo_final) > 10 or codigo_final == "N/A": codigo_final = codigo_detectado
        
        valor_xml = self.xml("valor_objetado", res_ia, valor_obj_raw)
        if "$" not in valor_xml and not any(char.isdigit() for char in valor_xml): valor_xml = valor_obj_raw
        
        argumento_ia = self.xml("argumento", res_ia, "").replace('\n', '<br/><br/>')
        
        apertura = f"ESE HUS NO ACEPTA LA GLOSA POR {nombre_tipo} ({codigo_final}) POR CONSIDERARLA INJUSTIFICADA, SUSTENTANDO ASÍ:<br/><br/>"

        return GlosaResult(
            tipo="TÉCNICO-LEGAL", resumen=f"DEFENSA: {paciente}", dictamen=apertura + argumento_ia,
            codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente,
            mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo, factura=self.xml("factura", res_ia, "N/A"), 
            autorizacion=self.xml("autorizacion", res_ia, "N/A"), score=int(self.xml("score", res_ia, "100") or 100), dias_restantes=dias_restantes
        )

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle('n', alignment=TA_JUSTIFY, fontSize=11, leading=16)
    
    elements = [
        Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", ParagraphStyle('h1', alignment=TA_CENTER, fontSize=14)),
        Spacer(1, 20), Paragraph(f"<b>Señores:</b><br/>{eps.upper()}<br/><b>Ref:</b> {resumen}", estilo_n), Spacer(1, 15)
    ]
    
    clean_text = re.sub(r'<br\s*/?>', '\n', conclusion).strip()
    for p in clean_text.split('\n\n'):
        if p.strip(): elements.append(Paragraph(p.strip(), estilo_n))
        elements.append(Spacer(1, 8))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()

def exportar_excel_pro(glosas: list) -> bytes:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte Glosas HUS"

    headers = ["ID", "Fecha Procesamiento", "EPS / Pagador", "Paciente", "Codigo Glosa", "Valor Objetado", "Valor Aceptado", "Etapa Procesal", "Estado Final"]
    ws.append(headers)

    header_fill = PatternFill(start_color="1C3460", end_color="1C3460", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    
    for col_num, cell in enumerate(ws[1], 1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = 18

    ws.column_dimensions['C'].width = 30 
    ws.column_dimensions['D'].width = 30 

    for g in glosas:
        ws.append([
            g.id, g.creado_en.strftime("%d/%m/%Y %H:%M"), g.eps, g.paciente, 
            g.codigo_glosa, g.valor_objetado, g.valor_aceptado, g.etapa, g.estado
        ])

    ws.auto_filter.ref = ws.dimensions

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()
