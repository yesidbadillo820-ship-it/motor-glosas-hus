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

def _procesar_pdf_sync(file_content: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        total_paginas = len(reader.pages)
        paginas = []
        for i in range(total_paginas):
            txt = reader.pages[i].extract_text()
            if txt:
                paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")
        texto_unido = "".join(paginas)
        if total_paginas > 8:
            texto_unido = "".join(paginas[:2]) + "\n\n... [ANÁLISIS DE CONTENIDO INTERMEDIO] ...\n\n" + "".join(paginas[-4:])
        return texto_unido[:16000]
    except Exception:
        return ""

class GlosaService:
    def __init__(self, api_key: str):
        self.cliente = AsyncGroq(api_key=api_key)

    async def extraer_pdf(self, file_content: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _procesar_pdf_sync, file_content)
        except Exception:
            logger.error("Error al extraer texto del PDF", exc_info=True)
            return ""

    def convertir_numero(self, m_str: str) -> float:
        if not m_str: return 0.0
        clean = re.sub(r'[^\d]', '', str(m_str))
        try: return float(clean)
        except ValueError: return 0.0

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}
        
        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        info_c = contratos_db.get("OTRA / SIN DEFINIR", "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.")
        for k, v in contratos_db.items():
            if k in eps_segura: 
                info_c = v
                break

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

        val_ac_num = self.convertir_numero(data.valor_aceptado)
        texto_base = str(data.tabla_excel)
        cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
        codigo_real = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_real[:2].upper()

        if prefijo == "TA":
            tesis_causal = f"""TESIS DE DEFENSA TARIFARIA: Ataca la interpretación errónea del manual por parte de la EPS. 1. Justifica la liquidación técnica: Si hubo bilateralidad o procedimientos múltiples, fundamenta el cobro basándote en la descripción quirúrgica y el manual pactado. 2. Cita el nexo causal: Cruza folio de descripción quirúrgica, cirujano (con RM) y el acuerdo contractual: {info_c}. 3. Argumento legal: La EPS no puede modificar lo pactado (Art. 1602 C.C. y 871 C.Co)."""
        elif prefijo == "SO":
            tesis_causal = """TESIS DE DEFENSA DE SOPORTES Y TECNOLOGÍAS: 1. Fundamento en Historia Clínica: La HC es soporte pleno (Res. 1995/1999). Identifica el insumo, cita folio, hora y pertinencia vital. 2. Vacío Tarifario: Si no tiene tarifa, aplica Anexo 5 Res. 3047 (Costo de adquisición + administración). 3. Realidad Fáctica: La falta de código no anula el gasto real."""
        elif prefijo == "FA":
            tesis_causal = """TESIS DE DEFENSA DE FACTURACIÓN (CONCURRENCIA): 1. Autonomía del Acto: El código es independiente y no está incluido en estancias o sala. 2. Cita el Anexo Técnico No. 3 de la Res. 3047. Exige la norma exacta que obligue a la inclusión."""
        elif prefijo in ["PE", "CL", "CO"]:
            tesis_causal = """TESIS DE DEFENSA TÉCNICO-CIENTÍFICA: 1. Prevalencia del Criterio Clínico: El auditor administrativo no sustituye al médico tratante. Cita diagnósticos CIE-10 y evolución. 2. Marco Constitucional: Invoca Ley 1751 de 2015 (Derecho Fundamental e Integralidad)."""
        else:
            tesis_causal = "ESTRATEGIA INTEGRAL: Cruce de datos entre lo facturado y lo documentado para exigir el cumplimiento del contrato."

        prompt = f"""ACTÚA COMO EL DIRECTOR NACIONAL DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS DE LA ESE HUS.
        SOPORTES CLÍNICOS: {contexto_pdf[:12000]}
        GLOSA: "{texto_base}"
        VÍNCULO CONTRACTUAL: {info_c}
        
        DIRECTRICES SENIOR:
        1. NO SEAS PASIVO: Usa la data como arma (cita nombres, RM, folios).
        2. {tesis_causal}
        3. LÉXICO SUPERIOR: Usa "Sinalagma contractual", "Carga de la prueba", "Principio de confianza legítima", "Realidad fáctica".
        4. ESTRUCTURA: Inicia con: "ESE HUS NO ACEPTA LA GLOSA [CÓDIGO] INTERPUESTA POR [MOTIVO], Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS CONTRACTUALES, TÉCNICOS Y NORMATIVOS:".
        5. CIERRE: Exige levantamiento inmediato y pago íntegro.
        6. FORMATO: TODO EN MAYÚSCULAS. UN SOLO BLOQUE DE TEXTO CONTINUO SIN SALTOS DE LÍNEA.

        RESPONDE EXACTAMENTE ASÍ:
        PACIENTE:
        INGRESO:
        EGRESO:
        DIAGNOSTICO:
        EPICRISIS_NO:
        CODIGO_GLOSA:
        VALOR_OBJETADO:
        SERVICIO_GLOSADO:
        MOTIVO_GLOSA_RESUMIDO:
        DICTAMEN_INTEGRAL:
        """
        
        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}], 
                    model="llama-3.3-70b-versatile", 
                    temperature=0.25
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception:
                await asyncio.sleep(2)

        def b(e):
            m = re.search(fr'{e}:\s*(.*?)(?=\n[A-Z_]+:|$)', res_ia, re.IGNORECASE | re.DOTALL)
            return m.group(1).strip().replace("*", "") if m else "N/A"

        paciente = b("PACIENTE")
        codigo = b("CODIGO_GLOSA") if b("CODIGO_GLOSA") != "N/A" else codigo_real
        valor = b("VALOR_OBJETADO")
        servicio = b("SERVICIO_GLOSADO")
        dictamen_ia = b("DICTAMEN_INTEGRAL")
        
        # Aplastador de párrafos
        dictamen_final = " ".join(dictamen_ia.split())

        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor)
            valor_acep_formato = f"$ {val_ac_num:,.0f}".replace(",", ".")
            cod_res, desc_res = ("RE9702", "GLOSA ACEPTADA TOTALMENTE") if val_ac_num >= val_obj_num else ("RE9801", "GLOSA PARCIALMENTE ACEPTADA")
            tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold; color:#d97706;">{valor_acep_formato}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
            tipo_f = "AUDITORÍA - ACEPTACIÓN"
        else:
            cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA"
            tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td><td style="padding:8px; border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
            tipo_f = "TÉCNICO-LEGAL"

        return GlosaResult(
            tipo=tipo_f, 
            resumen=f"DEFENSA FACTURA - {paciente}", 
            dictamen=tabla_html + f'<div style="text-align:justify; line-height:1.7; font-size:11px;">{dictamen_final}</div>', 
            codigo_glosa=codigo, valor_objetado=valor, paciente=paciente, 
            mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo
        )

def crear_oficio_pdf(eps, resumen, conclusion):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle('n', parent=estilos['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=16)
    estilo_titulo = ParagraphStyle('titulo', parent=estilos['Heading1'], alignment=1, fontSize=14, spaceAfter=20)
    
    match = re.search(r'<div[^>]*>(.*?)</div>', conclusion, re.IGNORECASE | re.DOTALL)
    cuerpo_texto = match.group(1) if match else conclusion
    clean_text = re.sub(r'<[^>]+>', '', cuerpo_texto).strip()
    
    fecha_actual = datetime.now().strftime("%d/%m/%Y")
    elements = []
    
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        img = Image(logo_path, width=250, height=60)
        img.hAlign = 'LEFT'
        elements.append(img)
        elements.append(Spacer(1, 15))
    
    elements.extend([
        Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", estilo_titulo),
        Paragraph("<b>OFICINA DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS</b>", ParagraphStyle('sub', alignment=1, fontSize=12)),
        Spacer(1, 30),
        Paragraph(f"Bucaramanga, {fecha_actual}", estilo_n),
        Spacer(1, 20),
        Paragraph(f"<b>Señores:</b><br/>{eps.upper()}", estilo_n),
        Spacer(1, 20),
        Paragraph(f"<b>ASUNTO:</b> {resumen}", estilo_n),
        Spacer(1, 20),
        Paragraph(clean_text, estilo_n),
        Spacer(1, 40),
        Paragraph("__________________________________________", estilo_n),
        Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n)
    ])
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
