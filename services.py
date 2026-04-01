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

def _div(texto): 
    return f'<div style="text-align:justify;line-height:1.6;font-size:11px;margin-top:10px;">{texto}</div>'

def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_header="#1e3a8a", color_estado="#b91c1c"):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:10px;"><tr style="background-color:{color_header};color:white;"><th style="padding:5px;">CÓDIGO GLOSA</th><th style="padding:5px;">ESTADO</th><th style="padding:5px;">VALOR OBJETADO</th><th style="padding:5px;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:5px;text-align:center;">{codigo}</td><td style="padding:5px;text-align:center;background-color:{color_estado};color:white;"><b>{estado}</b></td><td style="padding:5px;text-align:center;">{valor}</td><td style="padding:5px;text-align:center;font-weight:bold;">{cod_res}<br>{desc_res}</td></tr></table>'

def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:10px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:5px;">CÓDIGO GLOSA</th><th style="padding:5px;">SERVICIO RECLAMADO</th><th style="padding:5px;">VALOR OBJ.</th><th style="padding:5px;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:5px;text-align:center;">{codigo}</td><td style="padding:5px;">{servicio}</td><td style="padding:5px;text-align:center;">{valor}</td><td style="padding:5px;text-align:center;font-weight:bold;">{cod_res}<br>{desc_res}</td></tr></table>'

def _procesar_pdf_sync(file_content: bytes) -> str:
    unido = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text() or ""
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
        etapa_str = str(data.etapa).upper()
        texto_base = str(data.tabla_excel).strip().upper()
        val_ac_num = float(re.sub(r'[^\d]', '', str(data.valor_aceptado)) or 0)
        
        # Detección de Código y Prefijo
        cod_m = re.search(r'\b([A-Z]{2,3}\d{0,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        if codigo_detectado == "N/A" and ("MCV" in texto_base or "MV" in texto_base):
            codigo_detectado = "MCV"
        
        prefijo = codigo_detectado[:2]
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        dias = _calcular_dias_habiles(data.fecha_radicacion, data.fecha_recepcion) if data.fecha_radicacion and data.fecha_recepcion else 0
        es_extemporanea = dias > 20
        msg_tiempo = f"EXTEMPORÁNEA ({dias} DÍAS)" if es_extemporanea else f"EN TÉRMINOS ({dias} DÍAS)"

        # 1. CASO RATIFICADA (PRIORIDAD ALTA)
        if "RATIF" in etapa_str:
            txt_ratif = ("ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE DE LA GLOSA INICIAL "
                         "Y CONTINUACIÓN DEL PROCESO DE ACUERDO CON LA NORMA. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE LA "
                         "CONCILIACIÓN DE LA AUDITORÍA MÉDICA Y/O TÉCNICA ENTRE LAS PARTES. CUALQUIER INFORMACIÓN AL CORREO "
                         "ELECTRÓNICO INSTITUCIONAL CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO, VENTANILLA ÚNICA DE "
                         "LA ESE HUS CARRERA 33 NO. 28-126. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, "
                         "DE NO OBTENERSE LA RATIFICACIÓN DE LA RESPUESTA A LA GLOSA EN LOS TÉRMINOS ESTABLECIDOS, SE DARÁ POR "
                         "LEVANTADA LA RESPECTIVA OBJECIÓN.")
            tabla = _tabla_simple(codigo_detectado, "RATIFICACIÓN", valor_obj_raw, "RE9901", "GLOSA INJUSTIFICADA", color_estado="#2563eb")
            return GlosaResult(tipo="LEGAL - RATIFICADA", resumen="RECHAZO RATIFICACIÓN", dictamen=tabla + _div(txt_ratif), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600", dias_restantes=max(0, 20-dias))

        # 2. CASO EXTEMPORÁNEA
        if es_extemporanea and val_ac_num <= 0:
            nombre_tipo = "TARIFAS" if prefijo in ["TA", "MC", "MV"] else "OBJECIONES VARIAS"
            txt_ext = f"ESE HUS NO ACEPTA LA GLOSA POR {nombre_tipo} ({codigo_detectado}) POR EXTEMPORANEIDAD ({dias} DÍAS HÁBILES). OPERA ACEPTACIÓN TÁCITA DE PLENO DERECHO (ART. 57 LEY 1438/2011). SE EXIGE EL PAGO INMEDIATO."
            tabla = _tabla_simple(codigo_detectado, "EXTEMPORÁNEA", valor_obj_raw, "RE9502", "GLOSA FUERA DE TIEMPOS")
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORANEIDAD", dictamen=tabla + _div(txt_ext), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-red-600", dias_restantes=0)

        # 3. CASO INICIAL (IA)
        eps_key = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        info_c = {**CONTRATOS_FIJOS, **(contratos_db or {})}.get(eps_key, CONTRATOS_FIJOS["OTRA / SIN DEFINIR"])
        
        system_prompt = f"""DIRECTOR JURÍDICO ESE HUS. TODO EN MAYÚSCULAS. XML. 
        MARCO: {info_c}. ESTRATEGIA: Citar contrato, desvirtuar glosa tarifaria/mayor valor, exigir pago Buena Fe Art 871 C.Co.
        XML: <paciente>, <codigo_glosa>, <valor_objetado>, <servicio_glosado>, <argumento>."""
        
        try:
            comp = await self.cliente.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"GLOSA: {texto_base}"}],
                model="llama-3.3-70b-versatile", temperature=0.2
            )
            res_ia = comp.choices[0].message.content
        except: res_ia = "<argumento>ERROR IA</argumento>"

        paciente = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        servicio = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        arg = self.xml("argumento", res_ia, "SIN ARGUMENTO").replace('\n', '<br/>')
        
        apertura = f"ESE HUS NO ACEPTA LA GLOSA POR CONSIDERARLA INJUSTIFICADA, SUSTENTANDO ASÍ:"
        tabla = _tabla_defensa(codigo_detectado, servicio, valor_obj_raw, "RE9602", "GLOSA INJUSTIFICADA")
        
        return GlosaResult(tipo="TÉCNICO-LEGAL", resumen=f"DEFENSA: {paciente}", dictamen=tabla + _div(f"<b>{apertura}</b><br/><br/>{arg}"), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo="bg-emerald-500", score=95, dias_restantes=max(0, 20-dias))

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = [Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", ParagraphStyle('h1', alignment=TA_CENTER, fontSize=14)), Spacer(1, 20)]
    clean_text = re.sub(r'<table.*?>.*?</table>', '', conclusion, flags=re.IGNORECASE | re.DOTALL)
    elements.append(Paragraph(clean_text.replace('<br/>', '\n'), ParagraphStyle('n', alignment=TA_JUSTIFY, fontSize=11)))
    doc.build(elements)
    return buffer.getvalue()
