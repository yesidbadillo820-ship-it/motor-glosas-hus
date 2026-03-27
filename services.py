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
            texto_unido = "".join(paginas[:2]) + "\n\n... [PÁGINAS OMITIDAS PARA AHORRAR MEMORIA] ...\n\n" + "".join(paginas[-4:])
        return texto_unido[:14000]
    except Exception:
        return ""

class GlosaService:
    def __init__(self, api_key: str):
        self.cliente = AsyncGroq(api_key=api_key)

    async def extraer_pdf(self, file_content: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            texto = await loop.run_in_executor(None, _procesar_pdf_sync, file_content)
            return texto
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
        info_c = contratos_db.get("OTRA / SIN DEFINIR", "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO. Se exige el pago al 100% de la tarifa vigente.")
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
                dias = 0
                while dia_actual < f2:
                    dia_actual += timedelta(days=1)
                    if dia_actual.weekday() < 5: 
                        dias += 1
                if dias > 20:
                    es_extemporanea = True
                    msg_tiempo, color_tiempo = f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES)", "bg-red-600"
                else:
                    msg_tiempo, color_tiempo = f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)", "bg-emerald-500"
            except Exception as e: 
                logger.error(f"Error procesando fechas: {e}")
                msg_tiempo, color_tiempo = "Error en fechas", "bg-slate-500"

        val_ac_num = self.convertir_numero(data.valor_aceptado)
        texto_base = str(data.tabla_excel)

        # Extracción previa del código de glosa en Python para ruteo inteligente
        cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
        codigo_real = cod_m.group(1) if cod_m else "N/A"
        prefijo_glosa = codigo_real[:2].upper() if codigo_real != "N/A" else "XX"

        if data.etapa == "RATIFICADA" and val_ac_num == 0:
            val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
            valor_obj = f"$ {val_m.group(1)}" if val_m else "$ 0.00"
            tabla = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">ETAPA</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_real}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;"><b>RATIFICACIÓN</b></td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9901<br><span style="font-size:9px;">GLOSA SUBSANADA TOTALMENTE</span></td></tr></table>"""
            texto_rat = "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE DE LA GLOSA INICIAL Y CONTINUACIÓN DEL PROCESO DE ACUERDO CON LA NORMA. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE LA CONCILIACIÓN DE LA AUDITORÍA MÉDICA Y/O TÉCNICA ENTRE LAS PARTES. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL CARTERA@HUS.GOV.CO. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, DE NO OBTENERSE LA RATIFICACIÓN DE LA RESPUESTA EN LOS TÉRMINOS ESTABLECIDOS, SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN."
            return GlosaResult(tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO RATIFICACIÓN", dictamen=tabla+f'<div style="text-align:justify; line-height:1.7;">{texto_rat}</div>', codigo_glosa=codigo_real, valor_objetado=valor_obj, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600")

        if es_extemporanea and val_ac_num == 0 and data.etapa != "RATIFICADA":
            val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
            valor_obj = f"$ {val_m.group(1)}" if val_m else "$ 0.00"
            tabla = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">ESTADO</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_real}</td><td style="padding:8px; border:1px solid #b91c1c; text-align:center; color:white;"><b>EXTEMPORÁNEA ({dias} DÍAS)</b></td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9502<br><span style="font-size:9px;">ACEPTACIÓN TÁCITA</span></td></tr></table>"""
            texto_ext = f"ESE HUS NO ACEPTA GLOSA EXTEMPORANEA. AL HABERSE SUPERADO DICHO PLAZO LEGAL (HAN TRANSCURRIDO {dias} DÍAS HÁBILES ENTRE LA RADICACIÓN Y LA RECEPCIÓN) SIN QUE NUESTRA INSTITUCIÓN RECIBIERA NOTIFICACIÓN FORMAL DE LAS OBJECIONES DENTRO DEL TÉRMINO ESTABLECIDO, HA OPERADO DE PLENO DERECHO EL FENÓMENO JURÍDICO DE LA ACEPTACIÓN TÁCITA DE LA FACTURA. EN CONSECUENCIA, HA PRECLUIDO DEFINITIVAMENTE LA OPORTUNIDAD LEGAL DE LA EPS PARA AUDITAR, GLOSAR O RETENER LOS RECURSOS ASOCIADOS A ESTA CUENTA, DE CONFORMIDAD CON LO DISPUESTO EN EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 Y EL ARTÍCULO 13 (LITERAL D) DE LA LEY 1122 DE 2007, ASÍ COMO LO REGLAMENTADO EN EL DECRETO 4747 DE 2007 Y LA RESOLUCIÓN 3047 DE 2008, SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS APLICADAS."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORÁNEA", dictamen=tabla+f'<div style="text-align:justify; line-height:1.7;">{texto_ext}</div>', codigo_glosa=codigo_real, valor_objetado=valor_obj, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

        # 🔥 ESTRATEGIA DINÁMICA (Aislamiento de Causal)
        estrategia_especifica = ""
        if prefijo_glosa == "TA":
            estrategia_especifica = f"""ESTRATEGIA ÚNICA: La glosa es de TARIFAS/MAYOR VALOR. Tu única misión es justificar el valor cobrado.
            - Revisa en los soportes si la cirugía fue BILATERAL o MÚLTIPLE (Ej. hernia bilateral). Si lo fue, justifica el cobro de unidades adicionales.
            - Cita estrictamente este contrato: "{info_c}".
            - Invoca el principio de buena fe (Art. 871 Código de Comercio).
            - PROHIBICIÓN ABSOLUTA: No listes medicamentos, ni anestesias, ni jeringas, ni hables de facturas de compra. Enfócate SOLO en el valor y el contrato."""
        elif prefijo_glosa == "SO":
            estrategia_especifica = """ESTRATEGIA ÚNICA: La glosa es de SOPORTES/INSUMOS. Tu única misión es defender el material cobrado.
            - Argumenta que el insumo/material es indispensable para la técnica quirúrgica o tratamiento (menciona su nombre).
            - Exige el pago amparado en el "costo de adquisición más porcentaje de administración".
            - Menciona explícitamente que se adjunta la factura de compra del proveedor como soporte.
            - Cita el Anexo 5 de la Resolución 3047 de 2008."""
        elif prefijo_glosa == "FA":
            estrategia_especifica = """ESTRATEGIA ÚNICA: La glosa es de FACTURACIÓN. Tu única misión es defender la autonomía del cobro.
            - Demuestra que el servicio o ítem cobrado NO está incluido en los derechos de sala, estancia o enfermería.
            - Exige que la EPS señale la norma exacta que sustente la inclusión (la cual no existe).
            - Cita el Anexo 3 de la Resolución 3047 de 2008."""
        else:
            estrategia_especifica = """ESTRATEGIA ÚNICA: La glosa es de COBERTURA/PERTINENCIA. Tu única misión es defender el acto médico.
            - Basa tu argumento en la historia clínica, la evolución del paciente y la pertinencia médica.
            - Habla sobre el derecho a la salud integral (Ley 1751 de 2015)."""

        if val_ac_num > 0:
            prompt = f"""ACTÚA COMO ABOGADO AUDITOR. Extrae datos y en CUERPO_ARGUMENTATIVO redacta en MAYÚSCULAS que se acepta la glosa por ${val_ac_num:,.0f}."""
        else:
            prompt = f"""ACTÚA COMO ABOGADO AUDITOR SENIOR Y ESPECIALISTA EN FACTURACIÓN DE LA ESE HUS.
            EPS: {eps_segura}
            GLOSA: "{texto_base}"
            SOPORTES CLÍNICOS: {contexto_pdf[:10000]}
            
            INSTRUCCIONES OBLIGATORIAS:
            1. Extrae los datos solicitados. (Si no existen, escribe N/A).
            2. CODIGO_GLOSA: Código alfanumérico detectado.
            3. MOTIVO_GLOSA_RESUMIDO: Resumen de máximo 6 palabras del motivo de la EPS.
            4. CUERPO_ARGUMENTATIVO: Redacta tu defensa técnica basándote ESTRICTAMENTE en la siguiente regla:
            
            {estrategia_especifica}
            
            5. Usa nombres de médicos, fechas o folios que encuentres, pero SOLO si apoyan tu estrategia principal.
            6. Termina exigiendo el levantamiento íntegro de la glosa objetada.
            7. FORMATO: TODO EN MAYÚSCULAS. SIN INTRODUCCIONES. SIN SALUDOS. SOLO LA ARGUMENTACIÓN.

            RESPONDE ESTRICTAMENTE CON ESTE FORMATO EXACTO:
            PACIENTE: 
            INGRESO: 
            EGRESO: 
            DIAGNOSTICO: 
            EPICRISIS_NO: 
            CODIGO_GLOSA: 
            VALOR_OBJETADO: 
            SERVICIO_GLOSADO: 
            MOTIVO_GLOSA_RESUMIDO: 
            CUERPO_ARGUMENTATIVO: 
            """
        
        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}], 
                    model="llama-3.3-70b-versatile", 
                    temperature=0.1
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception as e: 
                logger.error(f"Intento {intento + 1} fallo al contactar Groq: {e}", exc_info=True)
                if intento == 2:
                    return GlosaResult(
                        tipo="Error", resumen="Error de Conexión IA",
                        dictamen="Error persistente al contactar el modelo. Por favor reintente.",
                        codigo_glosa="N/A", valor_objetado="0", paciente="N/A",
                        mensaje_tiempo="", color_tiempo=""
                    )
                await asyncio.sleep(2 ** intento)

        def b(e):
            m = re.search(fr'{e}:\s*(.*?)(?=\n[A-Z_]+:|$)', res_ia, re.IGNORECASE | re.DOTALL)
            if not m: return "N/A"
            val = m.group(1).strip().replace("*", "") 
            return val.strip() if val.strip() else "N/A"

        paciente = b("PACIENTE")
        codigo = b("CODIGO_GLOSA") if b("CODIGO_GLOSA") != "N/A" else codigo_real
        valor = b("VALOR_OBJETADO")
        servicio = b("SERVICIO_GLOSADO")
        motivo_resumen = b("MOTIVO_GLOSA_RESUMIDO").upper()
        cuerpo_arg = b("CUERPO_ARGUMENTATIVO")

        if motivo_resumen == "N/A" or not motivo_resumen:
            motivo_resumen = "OBJECIÓN INJUSTIFICADA"

        # 🔥 APLASTADOR DE PÁRRAFOS ACTIVADO (Fuerza UN SOLO bloque de texto continuo)
        cuerpo_arg_plano = " ".join(cuerpo_arg.split())

        # 🔥 INYECCIÓN OBLIGATORIA DEL ARRANQUE MEDIANTE PYTHON
        if val_ac_num == 0:
            arranque_obligatorio = f"ESE HUS NO ACEPTA LA GLOSA {codigo} INTERPUESTA POR {motivo_resumen}, Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS CONTRACTUALES, TÉCNICOS Y NORMATIVOS: "
            cuerpo_dictamen = arranque_obligatorio + cuerpo_arg_plano
        else:
            cuerpo_dictamen = cuerpo_arg_plano

        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor)
            valor_acep_formato = f"$ {val_ac_num:,.0f}".replace(",", ".")
            if val_ac_num >= val_obj_num and val_obj_num > 0:
                cod_res, desc_res = "RE9702", "GLOSA ACEPTADA TOTALMENTE"
            else:
                cod_res, desc_res = "RE9801", "GLOSA PARCIALMENTE ACEPTADA"
            tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold; color:#d97706;">{valor_acep_formato}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
            tipo_final = "AUDITORÍA - ACEPTACIÓN"
        else:
            prefijo = str(codigo[:2]).upper() if codigo else "XX"
            cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA"
            if prefijo == "TA" and ("OTRA" in eps_segura or "SIN DEFINIR" in eps_segura):
                cod_res, desc_res = "RE9206", "GLOSA INJUSTIFICADA 100%"
            tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td><td style="padding:8px; border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
            tipo_final = "TÉCNICO-LEGAL"

        return GlosaResult(
            tipo=tipo_final, 
            resumen=f"DEFENSA FACTURA - {paciente if paciente != 'N/A' else 'PACIENTE EN MENCIÓN'}", 
            dictamen=tabla_html + f'<div style="text-align:justify; line-height:1.7; font-size:11px;">{cuerpo_dictamen}</div>', 
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
