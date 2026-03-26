import os
import io
import re
from datetime import datetime, timedelta
import PyPDF2
from groq import AsyncGroq
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from models import GlosaInput, GlosaResult

class GlosaService:
    def __init__(self, api_key: str):
        self.cliente = AsyncGroq(api_key=api_key)

    async def extraer_pdf(self, file_content: bytes) -> str:
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            return "\n".join([p.extract_text() for p in reader.pages])
        except Exception as e:
            print(f"Error al extraer PDF: {e}")
            return ""

    def convertir_numero(self, m_str):
        if not m_str: return 0.0
        clean = re.sub(r'[^\d]', '', m_str)
        try: 
            return float(clean)
        except ValueError: 
            return 0.0

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None:
            contratos_db = {}
            
        info_c = contratos_db.get("OTRA / SIN DEFINIR", "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO (RESOLUCIÓN 054 DE 2026_0001 / DECRETO 441 DE 2022).")
        for k, v in contratos_db.items():
            if k in data.eps.upper(): info_c = v; break

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
                print(f"Error procesando fechas: {e}")
                msg_tiempo, color_tiempo = "Error en fechas", "bg-slate-500"

        val_ac_num = self.convertir_numero(data.valor_aceptado)
        texto_base = data.tabla_excel

        if data.etapa == "RATIFICADA" and val_ac_num == 0:
            cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
            codigo_real = cod_m.group(1) if cod_m else "N/A"
            val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
            valor_obj = f"$ {val_m.group(1)}" if val_m else "$ 0.00"
            tabla = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">ETAPA</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_real}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;"><b>RATIFICACIÓN</b></td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9901<br><span style="font-size:9px;">GLOSA SUBSANADA TOTALMENTE</span></td></tr></table>"""
            texto_rat = "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE DE LA GLOSA INICIAL Y CONTINUACIÓN DEL PROCESO DE ACUERDO CON LA NORMA. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE LA CONCILIACIÓN DE LA AUDITORÍA MÉDICA Y/O TÉCNICA ENTRE LAS PARTES. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL CARTERA@HUS.GOV.CO. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, DE NO OBTENERSE LA RATIFICACIÓN DE LA RESPUESTA EN LOS TÉRMINOS ESTABLECIDOS, SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN."
            return GlosaResult(tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO RATIFICACIÓN", dictamen=tabla+f'<div style="text-align:justify; line-height:1.7;">{texto_rat}</div>', codigo_glosa=codigo_real, valor_objetado=valor_obj, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600")

        if es_extemporanea and val_ac_num == 0 and data.etapa != "RATIFICADA":
            cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
            codigo_real = cod_m.group(1) if cod_m else "N/A"
            val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
            valor_obj = f"$ {val_m.group(1)}" if val_m else "$ 0.00"
            tabla = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">ESTADO</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_real}</td><td style="padding:8px; border:1px solid #b91c1c; text-align:center; color:white;"><b>EXTEMPORÁNEA ({dias} DÍAS)</b></td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9502<br><span style="font-size:9px;">ACEPTACIÓN TÁCITA</span></td></tr></table>"""
            texto_ext = f"ESE HUS NO ACEPTA GLOSA EXTEMPORANEA. AL HABERSE SUPERADO DICHO PLAZO LEGAL (HAN TRANSCURRIDO {dias} DÍAS HÁBILES ENTRE LA RADICACIÓN Y LA RECEPCIÓN) SIN QUE NUESTRA INSTITUCIÓN RECIBIERA NOTIFICACIÓN FORMAL DE LAS OBJECIONES DENTRO DEL TÉRMINO ESTABLECIDO, HA OPERADO DE PLENO DERECHO EL FENÓMENO JURÍDICO DE LA ACEPTACIÓN TÁCITA DE LA FACTURA. EN CONSECUENCIA, HA PRECLUIDO DEFINITIVAMENTE LA OPORTUNIDAD LEGAL DE LA EPS PARA AUDITAR, GLOSAR O RETENER LOS RECURSOS ASOCIADOS A ESTA CUENTA, DE CONFORMIDAD CON LO DISPUESTO EN EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 Y EL ARTÍCULO 13 (LITERAL D) DE LA LEY 1122 DE 2007, ASÍ COMO LO REGLAMENTADO EN EL DECRETO 4747 DE 2007 (ACTUALMENTE COMPILADO EN EL DECRETO ÚNICO REGLAMENTARIO 780 DE 2016) Y LA RESOLUCIÓN 3047 DE 2008 CON SUS RESPECTIVAS MODIFICACIONES, LAS ENTIDADES RESPONSABLES DEL PAGO (EPS) CUENTAN CON UN TÉRMINO MÁXIMO, PERENTÓRIO E IMPRORROGABLE DE VEINTE (20) DÍAS HÁBILES, CONTADOS A PARTIR DE LA FECHA DE RADICACIÓN DE LA FACTURA CON SUS RESPECTIVOS SOPORTES, PARA FORMULAR Y COMUNICAR DE MANERA SIMULTÁNEA TODAS LAS GLOSAS A LAS QUE HAYA LUGAR, SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS APLICADAS."
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORÁNEA", dictamen=tabla+f'<div style="text-align:justify; line-height:1.7;">{texto_ext}</div>', codigo_glosa=codigo_real, valor_objetado=valor_obj, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

        instruccion_ia = "JUSTIFICACION_DEFENSA: Redacta un argumento MÉDICO-ASISTENCIAL (máximo 3 líneas) justificando la necesidad clínica del servicio."
        if val_ac_num > 0:
            instruccion_ia = "JUSTIFICACION_DEFENSA: Redacta 3 líneas explicando formalmente por qué el hospital ACEPTA esta glosa. NO uses leyes ni viñetas."

        prompt = f"""ACTÚA COMO AUDITOR DE LA ESE HUS.
        EPS: {data.eps}
        GLOSA: "{texto_base}"
        SOPORTES: {contexto_pdf[:4000]}
        
        INSTRUCCIONES OBLIGATORIAS:
        1. Extrae los datos solicitados. Si un dato no existe, escribe exactamente N/A.
        2. IMPORTANTE: El CODIGO_GLOSA es estrictamente el código de objeción que empieza con dos letras (Ej: TA0201, CO5701, FA0801, CO0601). NUNCA extraigas el código del insumo (Ej: 861801H o FMQ01811).
        3. NO uses asteriscos (**), viñetas (-), ni saltos de línea.
        4. {instruccion_ia}
        
        RESPONDE ESTRICTAMENTE CON ESTE FORMATO EXACTO:
        PACIENTE: 
        INGRESO: 
        EGRESO: 
        DIAGNOSTICO: 
        EPICRISIS_NO: 
        CODIGO_GLOSA: 
        VALOR_OBJETADO: 
        SERVICIO_GLOSADO: 
        JUSTIFICACION_DEFENSA: 
        """
        
        try:
            completion = await self.cliente.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0)
            res_ia = completion.choices[0].message.content
        except Exception as e: 
            print(f"Error con la IA: {e}")
            return GlosaResult(tipo="Error", resumen="Error Groq", dictamen="Ocurrió un error al contactar el modelo. Reintente.", codigo_glosa="N/A", valor_objetado="0", paciente="N/A", mensaje_tiempo="", color_tiempo="")

        def b(e):
            m = re.search(fr'{e}:\s*(.*?)(?=\n[A-Z_]+:|$)', res_ia, re.IGNORECASE | re.DOTALL)
            if not m: return "N/A"
            val = m.group(1).strip()
            val = val.replace("*", "").replace("-", "").replace('"', '') 
            val = re.sub(r'^(JUSTIFICACI[OÓ]N DE DEFENSA|JUSTIFICACION):?\s*', '', val, flags=re.IGNORECASE)
            return val.strip() if val.strip() else "N/A"

        paciente = b("PACIENTE")
        ingreso = b("INGRESO")
        egreso = b("EGRESO")
        dx = b("DIAGNOSTICO")
        epi = b("EPICRISIS_NO")
        codigo = b("CODIGO_GLOSA")
        valor = b("VALOR_OBJETADO")
        servicio = b("SERVICIO_GLOSADO")
        defensa_ia = b("JUSTIFICACION_DEFENSA")

        txt_paciente = f" CORRESPONDIENTE AL PACIENTE {paciente}" if paciente != "N/A" else " CORRESPONDIENTE AL PACIENTE EN MENCIÓN"
        txt_ingreso = f", IDENTIFICADO CON INGRESO N.° {ingreso}" if ingreso != "N/A" else ""
        txt_egreso = f" CON FECHA DE EGRESO {egreso}" if egreso != "N/A" else ""
        txt_epi = f" (EPICRISIS N.° {epi})" if epi != "N/A" else ""
        txt_dx = f" Y DIAGNÓSTICO {dx}" if dx != "N/A" else ""

        texto_defensa = ""
        if defensa_ia.upper() != "N/A" and defensa_ia:
            texto_defensa = f" TÉCNICAMENTE SE ACLARA: {defensa_ia.upper()}"
            if not texto_defensa.endswith("."): texto_defensa += "."

        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor)
            valor_acep_formato = f"$ {val_ac_num:,.0f}".replace(",", ".")
            
            if val_ac_num >= val_obj_num and val_obj_num > 0:
                cod_res, desc_res = "RE9702", "GLOSA ACEPTADA TOTALMENTE"
                cuerpo = f"ESE HUS ACEPTA GLOSA TOTAL POR VALOR DE {valor_acep_formato} POR CONCEPTO DE {servicio}.{texto_defensa} EN CONSECUENCIA, SE PROCEDE CON LA ACEPTACIÓN DEL 100% DEL VALOR OBJETADO."
            else:
                cod_res, desc_res = "RE9801", "GLOSA PARCIALMENTE ACEPTADA"
                cuerpo = f"ESE HUS ACEPTA GLOSA PARCIAL POR VALOR DE {valor_acep_formato} POR CONCEPTO DE {servicio}.{texto_defensa} SIN EMBARGO, ESTA INSTITUCIÓN RECHAZA EL EXCEDENTE DEL VALOR GLOSADO Y EXIGE EL PAGO ÍNTEGRO DEL SALDO RESTANTE."

            tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold; color:#d97706;">{valor_acep_formato}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
            return GlosaResult(tipo="AUDITORÍA - ACEPTACIÓN", resumen=f"ACEPTACIÓN DE GLOSA - {paciente if paciente != 'N/A' else 'PACIENTE EN MENCIÓN'}", dictamen=tabla_html + f'<div style="text-align:justify; line-height:1.7;">{cuerpo.upper()}</div>', codigo_glosa=codigo, valor_objetado=valor, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

        prefijo = codigo[:2].upper()
        cod_res = "RE9901"
        desc_res = "GLOSA NO ACEPTADA"
        
        if prefijo == "TA" and ("OTRA" in data.eps.upper() or "SIN DEFINIR" in data.eps.upper()):
            cod_res = "RE9206"
            desc_res = "GLOSA INJUSTIFICADA 100%"

        if prefijo == "TA":
            cuerpo = f"ESE HUS NO ACEPTA GLOSA {codigo} DEL SERVICIO {servicio}{txt_paciente}{txt_ingreso}, ARGUMENTANDO UNA PRESUNTA DIFERENCIA ENTRE EL VALOR OBJETADO Y LA TARIFA PACTADA. AL RESPECTO, SE PRECISA TÉCNICA Y CONTRACTUALMENTE LO SIGUIENTE: EL VALOR OBJETADO DE {valor} SE LIQUIDÓ EN ESTRICTO CUMPLIMIENTO DE LAS CONDICIONES ESTABLECIDAS EN EL ACUERDO VIGENTE CON {data.eps} ({info_c}). EN CONSECUENCIA, EL VALOR COBRADO ES PLENAMENTE CONCORDANTE CON LO ACORDADO ENTRE LAS PARTES.{texto_defensa} CONFORME AL DECRETO 441 DE 2022, LOS ACUERDOS TARIFARIOS DEBEN RESPETARSE EN SU INTEGRIDAD."
        elif prefijo == "CO":
            cuerpo = f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE COBERTURA AL SERVICIO {servicio}{txt_paciente}, POR CUANTO LOS SERVICIOS FACTURADOS FUERON PRESCRITOS Y EJECUTADOS BAJO CRITERIO MÉDICO JUSTIFICADO, GUARDANDO RELACIÓN DIRECTA CON EL DIAGNÓSTICO QUE MOTIVÓ LA ATENCIÓN, SIENDO SU USO NECESARIO Y PERTINENTE.{texto_defensa} NORMATIVAMENTE, LA LEY 1751 DE 2015 CONSAGRA LA SALUD COMO DERECHO FUNDAMENTAL E IMPIDE NEGAR SERVICIOS CLÍNICAMENTE NECESARIOS; LA RESOLUCIÓN 3512 DE 2019 ESTABLECE QUE SOLO LO TAXATIVAMENTE EXCLUIDO DEL PBS PUEDE SER OBJETADO, POR LO QUE EN AUSENCIA DE EXCLUSIÓN EXPRESA, LA COBERTURA DEBE PRESUMIRSE; Y LAS RUTAS INTEGRALES (RESOLUCIÓN 3280 DE 2018) HACEN OBLIGATORIO EL CUMPLIMIENTO DE LAS INTERVENCIONES. EL ACUERDO VIGENTE ({info_c}) CONTEMPLA LA ATENCIÓN INTEGRAL. SE EXIGE LEVANTAMIENTO."
        elif prefijo == "FA":
            cuerpo = f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE FACTURACIÓN SOBRE EL SERVICIO {servicio}{txt_paciente} POR VALOR DE {valor}, POR CUANTO LA FACTURACIÓN PRESENTADA CUMPLE ÍNTEGRAMENTE CON LOS REQUISITOS NORMATIVOS Y EL ACUERDO VIGENTE ({info_c}). EL SERVICIO CONSTITUYE UN ACTO MÉDICO AUTÓNOMO E INDEPENDIENTE.{texto_defensa} LA RESOLUCIÓN 1885 DE 2018 EXIGE QUE TODA GLOSA SEA SUSTENTADA DE MANERA ESPECÍFICA, Y EL DECRETO 441 DE 2022 PROHÍBE LA APLICACIÓN UNILATERAL DE CRITERIOS DE PAGO NO PACTADOS."
        elif prefijo == "SO":
            cuerpo = f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE SOPORTES AL SERVICIO {servicio}{txt_paciente}{txt_ingreso}, POR CUANTO LA DOCUMENTACIÓN TÉCNICA Y CLÍNICA QUE SOPORTA LA PRESTACIÓN DEL SERVICIO REPOSA ÍNTEGRAMENTE EN EL EXPEDIENTE REMITIDO.{texto_defensa} OBRA EN EL EXPEDIENTE LA INFORMACIÓN ASISTENCIAL{txt_epi}{txt_egreso}{txt_dx}, DOCUMENTO QUE CONFORME A LA RESOLUCIÓN 1995 DE 1999 Y LA RESOLUCIÓN 1645 DE 2016 CONSTITUYE SOPORTE CLÍNICO SUFICIENTE Y FEHACIENTE. ASÍ MISMO, EL ANEXO TÉCNICO N.° 5 DE LA RESOLUCIÓN 3047 DE 2008 RECONOCE ESTOS SOPORTES COMO VÁLIDOS."
        elif prefijo in ["CL", "PE"]:
            cuerpo = f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE PERTINENCIA AL SERVICIO {servicio}{txt_paciente}{txt_ingreso}, POR CUANTO LA PERTINENCIA CLÍNICA ESTÁ PLENAMENTE ACREDITADA EN LOS SOPORTES REMITIDOS.{texto_defensa} EL SERVICIO FUE INDICADO COMO PARTE DEL MANEJO TERAPÉUTICO REQUERIDO, SIENDO NECESARIO E INSUSTITUIBLE SEGÚN LOS PROTOCOLO VIGENTES. CONFORME A LA RESOLUCIÓN 1995 DE 1999 Y LA RESOLUCIÓN 3047 DE 2008, LA HISTORIA CLÍNICA ES SOPORTE SUFICIENTE, SIENDO IMPROCEDENTE OBJETAR LA PERTINENCIA SIN QUE EL ASEGURADOR APORTE UN CONCEPTO MÉDICO INDIVIDUALIZADO."
        else:
            cuerpo = f"ESE HUS RECHAZA GLOSA {codigo} AL SERVICIO {servicio}.{texto_defensa} SE EXIGE LEVANTAMIENTO ACORDE AL CONTRATO ({info_c})."

        tabla_html = f"""<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;"><tr style="background-color:#1e3a8a; color:white;"><th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px; border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td><td style="padding:8px; border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td><td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>"""
        
        return GlosaResult(
            tipo="TÉCNICO-LEGAL", 
            resumen=f"DEFENSA FACTURA - {paciente if paciente != 'N/A' else 'PACIENTE EN MENCIÓN'}", 
            dictamen=tabla_html + f'<div style="text-align:justify; line-height:1.7;">{cuerpo.upper()}</div>', 
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
    
    clean_text = re.sub('<br>', '\n', cuerpo_texto)
    clean_text = re.sub('<[^<]+?>', ' ', clean_text).strip()
    fecha_actual = datetime.now().strftime("%d/%m/%Y")
    
    elements = [
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
        Spacer(1, 60),
        Paragraph("__________________________________________", estilo_n),
        Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n)
    ]
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
