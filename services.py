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
            texto_unido = "".join(paginas[:2]) + "\n\n... [ANÁLISIS DE CONTENIDO INTERMEDIO RESERVADO] ...\n\n" + "".join(paginas[-4:])
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

    # Extractor XML a prueba de balas
    def extraer_xml(self, tag: str, texto: str, default: str = "N/A") -> str:
        match = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        if match:
            clean = match.group(1).strip().replace("*", "")
            return clean if clean else default
        return default

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}
        
        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        info_c = contratos_db.get("OTRA / SIN DEFINIR", "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.")
        for k, v in contratos_db.items():
            if k in eps_segura: 
                info_c = v
                break

        # 1. Extracción Inicial Básica
        texto_base = str(data.tabla_excel)
        cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        if codigo_detectado == "N/A" and len(texto_base.split()) > 0:
            codigo_detectado = texto_base.split()[0][:10].upper() # Fallback por si escriben "MVC" o algo raro
        
        prefijo = codigo_detectado[:2].upper()
        val_ac_num = self.convertir_numero(data.valor_aceptado)
        is_ratificada = str(data.etapa).strip().upper() == "RATIFICADA"

        # 2. Análisis Implacable de Tiempos (Extemporaneidad)
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

        # =====================================================================
        # 🛡️ GILLOTINA LEGAL: CORTES DIRECTOS (SIN IA)
        # =====================================================================
        
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        # A) GUILLOTINA RATIFICADA
        if is_ratificada and val_ac_num == 0:
            tabla = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">ETAPA</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_detectado}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;"><b>RATIFICACIÓN</b></td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9901<br><span style="font-size:9px;">GLOSA SUBSANADA TOTALMENTE</span></td></tr></table>"""
            texto_rat = "ESE HUS NO ACEPTA LA GLOSA RATIFICADA. SE MANTIENE LA RESPUESTA DE DEFENSA DADA EN EL TRÁMITE DE LA GLOSA INICIAL, TODA VEZ QUE LA EPS NO APORTA NUEVOS ELEMENTOS DE JUICIO QUE DESVIRTÚEN NUESTRA FACTURACIÓN. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE CONCILIACIÓN DE AUDITORÍA MÉDICA ENTRE LAS PARTES (CORREO: CARTERA@HUS.GOV.CO). NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, DE NO LLEGARSE A UN ACUERDO, SE CONTINUARÁ CON LAS ACCIONES DE COBRO COACTIVO RESPECTIVAS."
            return GlosaResult(tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO DE RATIFICACIÓN", dictamen=tabla+f'<div style="text-align:justify; line-height:1.7;">{texto_rat}</div>', codigo_glosa=codigo_detectado, valor_objetado=valor_obj, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600")

        # B) GUILLOTINA EXTEMPORÁNEA
        if es_extemporanea and val_ac_num == 0:
            tabla = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">ESTADO</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_detectado}</td><td style="padding:8px; border:1px solid #b91c1c; text-align:center; color:white;"><b>EXTEMPORÁNEA ({dias} DÍAS)</b></td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9502<br><span style="font-size:9px;">ACEPTACIÓN TÁCITA</span></td></tr></table>"""
            texto_ext = f"ESE HUS NO ACEPTA LA GLOSA POR EXTEMPORANEIDAD. AL HABERSE SUPERADO EL PLAZO LEGAL (HAN TRANSCURRIDO {dias} DÍAS HÁBILES ENTRE LA RADICACIÓN DE LA FACTURA Y LA RECEPCIÓN DE LA GLOSA) SIN RECIBIR NOTIFICACIÓN DENTRO DEL TÉRMINO ESTABLECIDO, HA OPERADO DE PLENO DERECHO EL FENÓMENO JURÍDICO DE LA ACEPTACIÓN TÁCITA DE LA FACTURA. EN CONSECUENCIA, PRECLUYÓ DEFINITIVAMENTE LA OPORTUNIDAD LEGAL DE LA EPS PARA AUDITAR O RETENER LOS RECURSOS, CONFORME AL ART. 57 DE LA LEY 1438 DE 2011, LEY 1122 DE 2007 Y RESOLUCIÓN 3047 DE 2008. SE EXIGE EL PAGO INMEDIATO."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO POR EXTEMPORANEIDAD", dictamen=tabla+f'<div style="text-align:justify; line-height:1.7;">{texto_ext}</div>', codigo_glosa=codigo_detectado, valor_objetado=valor_obj, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)


        # =====================================================================
        # 🧠 EL CEREBRO DE AUDITORÍA ADAPTATIVA (SOLO SE EJECUTA SI PASA LOS FILTROS)
        # =====================================================================
        
        if val_ac_num > 0:
            tesis_causal = "ACEPTACIÓN: Extrae los datos y en <argumento> redacta brevemente que la ESE HUS acepta el valor objetado por pertinencia administrativa/médica, ajustando la cuenta."
        elif prefijo == "TA":
            tesis_causal = f"""DEFENSA TARIFARIA LEY 1602: Ataca la interpretación errónea del manual por parte de la EPS.
            1. Si los soportes revelan bilateralidad o múltiples tiempos, justifica el cobro exacto.
            2. Obligatorio citar el contrato: {info_c}.
            3. Argumento: La EPS vulnera la buena fe y el Art 1602 del Código Civil. No puede recibir un servicio y pretender liquidar por debajo de la norma pactada."""
        elif prefijo == "SO":
            tesis_causal = """DEFENSA TECNOLÓGICA (SOPORTES):
            1. Localiza el insumo/medicamento en la Epicrisis u Hoja de Gastos. Demuestra que era VITAL para el paciente.
            2. Argumento Letal: La Historia Clínica es soporte pleno (Res. 1995/1999). Si el insumo no tiene tarifa pactada, por Ley rige el Anexo 5 Res 3047: Se cobra al Costo de Adquisición + Porcentaje de Administración, soportado con Factura del Proveedor."""
        elif prefijo == "FA":
            tesis_causal = """DEFENSA FACTURACIÓN (CONCURRENCIA):
            1. Demuestra que el procedimiento cobrado es AUTÓNOMO. No está incluido ni en derechos de sala ni en estancia.
            2. Argumento Letal: Cita el Anexo 3 de la Res. 3047. Exige a la EPS que cite la norma exacta que obligue a su inclusión, lo cual es improcedente."""
        elif prefijo in ["PE", "CL", "CO"]:
            tesis_causal = """DEFENSA TÉCNICO-CIENTÍFICA (PERTINENCIA):
            1. El auditor administrativo no puede sobreponerse al JUICIO MÉDICO ESPECIALIZADO.
            2. Cita los diagnósticos (CIE-10), la evolución y la gravedad del caso.
            3. Argumento Letal: Invoca la Ley 1751 de 2015 (Derecho a la Salud e Integralidad). La atención fue pertinente, idónea y necesaria para salvaguardar la vida."""
        else:
            tesis_causal = f"DEFENSA CONTRACTUAL INTEGRAL: Basa tu argumento en el cumplimiento estricto del contrato {info_c} y la prestación efectiva del servicio evidenciado en la historia clínica."

        prompt = f"""ACTÚA COMO EL DIRECTOR NACIONAL DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS DE LA ESE HUS. (Experiencia: 30 años).
        
        SOPORTES CLÍNICOS: {contexto_pdf[:12000]}
        GLOSA REPORTADA: "{texto_base}"
        
        INSTRUCCIONES DE ALTO NIVEL:
        1. Eres implacable, profesional y técnico. Usa lenguaje como: "Sinalagma contractual", "Acervo probatorio", "Precluyó".
        2. NO RESUMAS la historia clínica; usa los datos (nombres de médicos, RM, folios) como ARMAS para fundamentar tu tesis.
        3. APLICA ESTA ESTRATEGIA EXACTA: {tesis_causal}
        4. No escribas frases introductorias en el argumento. Ve directo al fundamento técnico.
        
        RESPONDE ESTRICTA Y ÚNICAMENTE USANDO ESTE FORMATO XML:
        <paciente>Nombre del paciente</paciente>
        <codigo_glosa>Código de la glosa</codigo_glosa>
        <valor_objetado>Valor en pesos</valor_objetado>
        <servicio_glosado>Nombre del servicio</servicio_glosado>
        <motivo_resumido>Resumen muy breve (max 6 palabras) de lo que alega la EPS</motivo_resumido>
        <argumento>Aquí va todo tu texto de defensa argumentativa en MAYÚSCULAS y en un solo bloque continuo.</argumento>
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

        # 3. Extracción Limpia y Segura desde XML
        paciente = self.extraer_xml("paciente", res_ia, "NO DISPONIBLE")
        codigo_xml = self.extraer_xml("codigo_glosa", res_ia, codigo_detectado)
        codigo_final = codigo_xml if codigo_xml != "N/A" else codigo_detectado
        valor = self.extraer_xml("valor_objetado", res_ia, valor_obj)
        servicio = self.extraer_xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo_resumen = self.extraer_xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia = self.extraer_xml("argumento", res_ia, "SE RECHAZA LA GLOSA AMPARADOS EN EL CUMPLIMIENTO DE LA NORMA Y EL CONTRATO VIGENTE.")
        
        # Aseguramos que sea un solo bloque
        argumento_ia = " ".join(argumento_ia.split())

        # =====================================================================
        # 🔨 INYECCIÓN FORZADA DEL "ACEPTA" / "NO ACEPTA" POR PARTE DE PYTHON
        # =====================================================================
        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor)
            valor_acep_formato = f"$ {val_ac_num:,.0f}".replace(",", ".")
            texto_inicio = f"ESE HUS ACEPTA LA GLOSA {codigo_final} POR UN VALOR DE {valor_acep_formato}, SUSTENTANDO LO SIGUIENTE: "
            cod_res, desc_res = ("RE9702", "GLOSA ACEPTADA TOTALMENTE") if val_ac_num >= val_obj_num else ("RE9801", "GLOSA PARCIALMENTE ACEPTADA")
            
            tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_final}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold; color:#d97706;">{valor_acep_formato}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
            tipo_f = "AUDITORÍA - ACEPTACIÓN"
            
        else:
            texto_inicio = f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} INTERPUESTA POR {motivo_resumen}, Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS CONTRACTUALES, TÉCNICOS Y NORMATIVOS: "
            cod_res, desc_res = ("RE9206", "GLOSA INJUSTIFICADA 100%") if (prefijo == "TA" and "OTRA" in eps_segura) else ("RE9901", "GLOSA NO ACEPTADA")
            
            tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_final}</td><td style="padding:8px; border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
            tipo_f = "TÉCNICO-LEGAL"

        # Ensamblaje Perfecto
        dictamen_final = f"{texto_inicio}{argumento_ia}"

        return GlosaResult(
            tipo=tipo_f, 
            resumen=f"DEFENSA FACTURA - {paciente}", 
            dictamen=tabla_html + f'<div style="text-align:justify; line-height:1.7; font-size:11px;">{dictamen_final}</div>', 
            codigo_glosa=codigo_final, valor_objetado=valor, paciente=paciente, 
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
