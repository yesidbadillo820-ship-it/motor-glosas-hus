import io
import re
import asyncio
import logging
from datetime import datetime, timedelta

import PyPDF2
from groq import AsyncGroq
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY

from models import GlosaInput, GlosaResult

# Configuración del logging para producción
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("motor_glosas")


def _procesar_pdf_sync(file_content: bytes) -> str:
    """Función síncrona aislada para procesar PDFs sin bloquear el event loop."""
    reader = PyPDF2.PdfReader(io.BytesIO(file_content))
    total_paginas = len(reader.pages)
    paginas = []

    for i in range(total_paginas):
        txt = reader.pages[i].extract_text()
        if txt:
            paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")

    texto_unido = "".join(paginas)

    # Para documentos largos: lee las primeras 2 y las últimas 4 páginas
    if total_paginas > 8:
        texto_unido = (
            "".join(paginas[:2])
            + "\n\n... [PÁGINAS OMITIDAS PARA AHORRAR MEMORIA] ...\n\n"
            + "".join(paginas[-4:])
        )

    return texto_unido[:14000]  # Límite seguro para la API


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
        if not m_str:
            return 0.0
        clean = re.sub(r'[^\d]', '', str(m_str))
        try:
            return float(clean)
        except ValueError:
            return 0.0

    async def analizar(
        self,
        data: GlosaInput,
        contexto_pdf: str = "",
        contratos_db: dict = None,
    ) -> GlosaResult:
        if contratos_db is None:
            contratos_db = {}

        # Resolución de contrato por EPS
        info_c = contratos_db.get(
            "OTRA / SIN DEFINIR",
            "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO (RESOLUCIÓN 054 DE 2026_0001 / DECRETO 441 DE 2022)."
        )
        for k, v in contratos_db.items():
            if k in data.eps.upper():
                info_c = v
                break

        # Cálculo de términos (días hábiles)
        msg_tiempo = "Fechas no ingresadas"
        color_tiempo = "bg-slate-500"
        es_extemporanea = False
        dias = 0

        if data.fecha_radicacion and data.fecha_recepcion:
            try:
                f1 = datetime.strptime(data.fecha_radicacion, "%Y-%m-%d")
                f2 = datetime.strptime(data.fecha_recepcion, "%Y-%m-%d")

                dia_actual = f1
                while dia_actual < f2:
                    dia_actual += timedelta(days=1)
                    if dia_actual.weekday() < 5:
                        dias += 1

                if dias > 20:
                    es_extemporanea = True
                    msg_tiempo = f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES)"
                    color_tiempo = "bg-red-600"
                else:
                    msg_tiempo = f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)"
                    color_tiempo = "bg-emerald-500"
            except Exception:
                logger.error("Error calculando días hábiles entre fechas", exc_info=True)
                msg_tiempo = "Error en fechas"
                color_tiempo = "bg-slate-500"

        val_ac_num = self.convertir_numero(data.valor_aceptado)
        texto_base = data.tabla_excel

        # --- CASO: RATIFICADA sin valor aceptado ---
        if data.etapa == "RATIFICADA" and val_ac_num == 0:
            cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
            codigo_real = cod_m.group(1) if cod_m else "N/A"
            val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
            valor_obj = f"$ {val_m.group(1)}" if val_m else "$ 0.00"
            tabla = (
                f'<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;">'
                f'<tr style="background-color:#1e3a8a; color:white;">'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">ETAPA</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr>'
                f'<tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_real}</td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center;"><b>RATIFICACIÓN</b></td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9901<br>'
                f'<span style="font-size:9px;">GLOSA SUBSANADA TOTALMENTE</span></td></tr></table>'
            )
            texto_rat = (
                "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE DE LA GLOSA INICIAL "
                "Y CONTINUACIÓN DEL PROCESO DE ACUERDO CON LA NORMA. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE LA "
                "CONCILIACIÓN DE LA AUDITORÍA MÉDICA Y/O TÉCNICA ENTRE LAS PARTES. CUALQUIER INFORMACIÓN AL CORREO "
                "ELECTRÓNICO INSTITUCIONAL CARTERA@HUS.GOV.CO. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 "
                "DE 2011, DE NO OBTENERSE LA RATIFICACIÓN DE LA RESPUESTA EN LOS TÉRMINOS ESTABLECIDOS, SE DARÁ POR "
                "LEVANTADA LA RESPECTIVA OBJECIÓN."
            )
            return GlosaResult(
                tipo="LEGAL - RATIFICACIÓN",
                resumen="RECHAZO RATIFICACIÓN",
                dictamen=tabla + f'<div style="text-align:justify; line-height:1.7;">{texto_rat}</div>',
                codigo_glosa=codigo_real,
                valor_objetado=valor_obj,
                paciente="N/A",
                mensaje_tiempo=msg_tiempo,
                color_tiempo="bg-blue-600",
            )

        # --- CASO: EXTEMPORÁNEA sin valor aceptado ---
        if es_extemporanea and val_ac_num == 0 and data.etapa != "RATIFICADA":
            cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
            codigo_real = cod_m.group(1) if cod_m else "N/A"
            val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
            valor_obj = f"$ {val_m.group(1)}" if val_m else "$ 0.00"
            tabla = (
                f'<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;">'
                f'<tr style="background-color:#1e3a8a; color:white;">'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">ESTADO</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">VALOR</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr>'
                f'<tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo_real}</td>'
                f'<td style="padding:8px; border:1px solid #b91c1c; text-align:center; color:white;"><b>EXTEMPORÁNEA ({dias} DÍAS)</b></td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor_obj}</td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">RE9502<br>'
                f'<span style="font-size:9px;">ACEPTACIÓN TÁCITA</span></td></tr></table>'
            )
            texto_ext = (
                f"ESE HUS NO ACEPTA GLOSA EXTEMPORANEA. AL HABERSE SUPERADO DICHO PLAZO LEGAL (HAN TRANSCURRIDO "
                f"{dias} DÍAS HÁBILES ENTRE LA RADICACIÓN Y LA RECEPCIÓN) SIN QUE NUESTRA INSTITUCIÓN RECIBIERA "
                f"NOTIFICACIÓN FORMAL DE LAS OBJECIONES DENTRO DEL TÉRMINO ESTABLECIDO, HA OPERADO DE PLENO DERECHO "
                f"EL FENÓMENO JURÍDICO DE LA ACEPTACIÓN TÁCITA DE LA FACTURA. EN CONSECUENCIA, HA PRECLUIDO "
                f"DEFINITIVAMENTE LA OPORTUNIDAD LEGAL DE LA EPS PARA AUDITAR, GLOSAR O RETENER LOS RECURSOS "
                f"ASOCIADOS A ESTA CUENTA, DE CONFORMIDAD CON LO DISPUESTO EN EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 "
                f"Y EL ARTÍCULO 13 (LITERAL D) DE LA LEY 1122 DE 2007, ASÍ COMO LO REGLAMENTADO EN EL DECRETO 4747 "
                f"DE 2007 (ACTUALMENTE COMPILADO EN EL DECRETO ÚNICO REGLAMENTARIO 780 DE 2016) Y LA RESOLUCIÓN 3047 "
                f"DE 2008 CON SUS RESPECTIVAS MODIFICACIONES, LAS ENTIDADES RESPONSABLES DEL PAGO (EPS) CUENTAN CON "
                f"UN TÉRMINO MÁXIMO, PERENTÓRIO E IMPRORROGABLE DE VEINTE (20) DÍAS HÁBILES, CONTADOS A PARTIR DE LA "
                f"FECHA DE RADICACIÓN DE LA FACTURA CON SUS RESPECTIVOS SOPORTES, PARA FORMULAR Y COMUNICAR DE MANERA "
                f"SIMULTÁNEA TODAS LAS GLOSAS A LAS QUE HAYA LUGAR. SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO "
                f"DE LA TOTALIDAD DE LAS GLOSAS APLICADAS."
            )
            return GlosaResult(
                tipo="LEGAL - EXTEMPORÁNEA",
                resumen="RECHAZO EXTEMPORÁNEA",
                dictamen=tabla + f'<div style="text-align:justify; line-height:1.7;">{texto_ext}</div>',
                codigo_glosa=codigo_real,
                valor_objetado=valor_obj,
                paciente="N/A",
                mensaje_tiempo=msg_tiempo,
                color_tiempo=color_tiempo,
            )

        # --- INSTRUCCIÓN IA según valor aceptado ---
        if val_ac_num > 0:
            instruccion_ia = "JUSTIFICACION_DEFENSA: Redacta 3 líneas explicando formalmente por qué el hospital ACEPTA esta glosa. NO uses leyes ni viñetas."
        else:
            instruccion_ia = (
                "JUSTIFICACION_DEFENSA: Redacta un argumento MÉDICO-ASISTENCIAL sólido (máximo 4 líneas) "
                "defendiendo al hospital y justificando por qué el cobro facturado ES CORRECTO según los soportes. "
                "MENCIONA LA PÁGINA EXACTA donde encontraste la evidencia (Ej: 'Como se evidencia en la PÁG 84...'). "
                "¡DEFIENDE AL HUS!"
            )

        system_prompt = (
            "Eres un Médico Auditor experto de la ESE Hospital Universitario de Santander (HUS). "
            "Tu objetivo es defender la facturación del hospital frente a las EPS con argumentos técnicos, "
            "médicos y legales, basándote estrictamente en los soportes proporcionados. Eres preciso, formal, "
            "contundente y obedeces el formato de salida al pie de la letra sin inventar datos ni alucinar."
        )

        MAX_CONTEXTO = 12000
        contexto_seguro = contexto_pdf[:MAX_CONTEXTO]

        user_prompt = f"""
        EPS: {data.eps}
        GLOSA: "{texto_base}"
        SOPORTES: {contexto_seguro}
        
        INSTRUCCIONES OBLIGATORIAS:
        1. Extrae los datos solicitados. Si un dato no existe, escribe exactamente N/A.
        2. El CODIGO_GLOSA es estrictamente el código de objeción (Ej: FA0701, SO0201).
        3. NO uses asteriscos (**), viñetas (-), ni saltos de línea en tus respuestas.
        4. {instruccion_ia}
        
        RESPONDE ESTRICTAMENTE CON ESTE FORMATO EXACTO, USANDO SALTOS DE LÍNEA ENTRE CADA DATO:
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

        # Retry con exponential backoff
        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.1,
                    max_tokens=600
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception:
                logger.error(f"Intento {intento + 1} fallido al contactar Groq", exc_info=True)
                if intento == 2:
                    return GlosaResult(
                        tipo="Error",
                        resumen="Error de Conexión IA",
                        dictamen="Ocurrió un error persistente al contactar el modelo tras varios intentos. Por favor, reintente en unos minutos.",
                        codigo_glosa="N/A",
                        valor_objetado="0",
                        paciente="N/A",
                        mensaje_tiempo="",
                        color_tiempo="",
                    )
                await asyncio.sleep(2 ** intento)

        # Parser de respuesta IA
        def b(e):
            claves = ["PACIENTE", "INGRESO", "EGRESO", "DIAGNOSTICO", "EPICRISIS_NO",
                      "CODIGO_GLOSA", "VALOR_OBJETADO", "SERVICIO_GLOSADO", "JUSTIFICACION_DEFENSA"]
            patron_claves = "|".join(claves)
            m = re.search(fr'{e}:\s*(.*?)(?=(?:{patron_claves}):|$)', res_ia, re.IGNORECASE | re.DOTALL)
            if not m:
                return "N/A"
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
            if not texto_defensa.endswith("."):
                texto_defensa += "."

        # --- CASO: Aceptación parcial o total ---
        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor)
            valor_acep_formato = f"$ {val_ac_num:,.0f}".replace(",", ".")

            if val_ac_num >= val_obj_num and val_obj_num > 0:
                cod_res, desc_res = "RE9702", "GLOSA ACEPTADA TOTALMENTE"
                cuerpo = (
                    f"ESE HUS ACEPTA GLOSA TOTAL POR VALOR DE {valor_acep_formato} POR CONCEPTO DE {servicio}."
                    f"{texto_defensa} EN CONSECUENCIA, SE PROCEDE CON LA ACEPTACIÓN DEL 100% DEL VALOR OBJETADO."
                )
            else:
                cod_res, desc_res = "RE9801", "GLOSA PARCIALMENTE ACEPTADA"
                cuerpo = (
                    f"ESE HUS ACEPTA GLOSA PARCIAL POR VALOR DE {valor_acep_formato} POR CONCEPTO DE {servicio}."
                    f"{texto_defensa} SIN EMBARGO, ESTA INSTITUCIÓN RECHAZA EL EXCEDENTE DEL VALOR GLOSADO Y "
                    f"EXIGE EL PAGO ÍNTEGRO DEL SALDO RESTANTE."
                )

            tabla_html = (
                f'<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;">'
                f'<tr style="background-color:#1e3a8a; color:white;">'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJETADO</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1; background-color:#d97706;">VALOR ACEPTADO</th>'
                f'<th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr>'
                f'<tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold; color:#d97706;">{valor_acep_formato}</td>'
                f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br>'
                f'<span style="font-size:9px;">{desc_res}</span></td></tr></table>'
            )
            return GlosaResult(
                tipo="AUDITORÍA - ACEPTACIÓN",
                resumen=f"ACEPTACIÓN DE GLOSA - {paciente if paciente != 'N/A' else 'PACIENTE EN MENCIÓN'}",
                dictamen=tabla_html + f'<div style="text-align:justify; line-height:1.7;">{cuerpo.upper()}</div>',
                codigo_glosa=codigo,
                valor_objetado=valor,
                paciente=paciente,
                mensaje_tiempo=msg_tiempo,
                color_tiempo=color_tiempo,
            )

        # --- CASO: Defensa técnico-legal por prefijo ---
        prefijo = codigo[:2].upper() if codigo and codigo != "N/A" else "XX"
        cod_res = "RE9901"
        desc_res = "GLOSA NO ACEPTADA"

        if prefijo == "TA" and ("OTRA" in data.eps.upper() or "SIN DEFINIR" in data.eps.upper()):
            cod_res = "RE9206"
            desc_res = "GLOSA INJUSTIFICADA 100%"

        if prefijo == "TA":
            cuerpo = (
                f"ESE HUS NO ACEPTA GLOSA {codigo} DEL SERVICIO {servicio}{txt_paciente}{txt_ingreso}, "
                f"ARGUMENTANDO UNA PRESUNTA DIFERENCIA ENTRE EL VALOR OBJETADO Y LA TARIFA PACTADA. AL RESPECTO, "
                f"SE PRECISA TÉCNICA Y CONTRACTUALMENTE LO SIGUIENTE: EL VALOR OBJETADO DE {valor} SE LIQUIDÓ EN "
                f"ESTRICTO CUMPLIMIENTO DE LAS CONDICIONES ESTABLECIDAS EN EL ACUERDO VIGENTE CON {data.eps} "
                f"({info_c}). EN CONSECUENCIA, EL VALOR COBRADO ES PLENAMENTE CONCORDANTE CON LO ACORDADO ENTRE "
                f"LAS PARTES.{texto_defensa} CONFORME AL DECRETO 441 DE 2022, LOS ACUERDOS TARIFARIOS DEBEN "
                f"RESPETARSE EN SU INTEGRIDAD."
            )
        elif prefijo == "CO":
            cuerpo = (
                f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE COBERTURA AL SERVICIO {servicio}"
                f"{txt_paciente}, POR CUANTO LOS SERVICIOS FACTURADOS FUERON PRESCRITOS Y EJECUTADOS BAJO CRITERIO "
                f"MÉDICO JUSTIFICADO, GUARDANDO RELACIÓN DIRECTA CON EL DIAGNÓSTICO QUE MOTIVÓ LA ATENCIÓN, SIENDO "
                f"SU USO NECESARIO Y PERTINENTE.{texto_defensa} NORMATIVAMENTE, LA LEY 1751 DE 2015 CONSAGRA LA "
                f"SALUD COMO DERECHO FUNDAMENTAL E IMPIDE NEGAR SERVICIOS CLÍNICAMENTE NECESARIOS; LA RESOLUCIÓN "
                f"3512 DE 2019 ESTABLECE QUE SOLO LO TAXATIVAMENTE EXCLUIDO DEL PBS PUEDE SER OBJETADO, POR LO QUE "
                f"EN AUSENCIA DE EXCLUSIÓN EXPRESA, LA COBERTURA DEBE PRESUMIRSE; Y LAS RUTAS INTEGRALES (RESOLUCIÓN "
                f"3280 DE 2018) HACEN OBLIGATORIO EL CUMPLIMIENTO DE LAS INTERVENCIONES. EL ACUERDO VIGENTE "
                f"({info_c}) CONTEMPLA LA ATENCIÓN INTEGRAL. SE EXIGE LEVANTAMIENTO."
            )
        elif prefijo == "FA":
            cuerpo = (
                f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE FACTURACIÓN SOBRE EL SERVICIO "
                f"{servicio}{txt_paciente} POR VALOR DE {valor}, POR CUANTO LA FACTURACIÓN PRESENTADA CUMPLE "
                f"ÍNTEGRAMENTE CON LOS REQUISITOS NORMATIVOS Y EL ACUERDO VIGENTE ({info_c}). EL SERVICIO "
                f"CONSTITUYE UN ACTO MÉDICO AUTÓNOMO E INDEPENDIENTE.{texto_defensa} LA RESOLUCIÓN 1885 DE 2018 "
                f"EXIGE QUE TODA GLOSA SEA SUSTENTADA DE MANERA ESPECÍFICA, Y EL DECRETO 441 DE 2022 PROHÍBE LA "
                f"APLICACIÓN UNILATERAL DE CRITERIOS DE PAGO NO PACTADOS."
            )
        elif prefijo == "SO":
            cuerpo = (
                f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE SOPORTES AL SERVICIO {servicio}"
                f"{txt_paciente}{txt_ingreso}, POR CUANTO LA DOCUMENTACIÓN TÉCNICA Y CLÍNICA QUE SOPORTA LA "
                f"PRESTACIÓN DEL SERVICIO REPOSA ÍNTEGRAMENTE EN EL EXPEDIENTE REMITIDO.{texto_defensa} OBRA EN "
                f"EL EXPEDIENTE LA INFORMACIÓN ASISTENCIAL{txt_epi}{txt_egreso}{txt_dx}, DOCUMENTO QUE CONFORME "
                f"A LA RESOLUCIÓN 1995 DE 1999 Y LA RESOLUCIÓN 1645 DE 2016 CONSTITUYE SOPORTE CLÍNICO SUFICIENTE "
                f"Y FEHACIENTE. ASÍ MISMO, EL ANEXO TÉCNICO N.° 5 DE LA RESOLUCIÓN 3047 DE 2008 RECONOCE ESTOS "
                f"SOPORTES COMO VÁLIDOS."
            )
        elif prefijo in ["CL", "PE"]:
            cuerpo = (
                f"ESE HUS NO ACEPTA GLOSA {codigo} APLICADA POR CONCEPTO DE PERTINENCIA AL SERVICIO {servicio}"
                f"{txt_paciente}{txt_ingreso}, POR CUANTO LA PERTINENCIA CLÍNICA ESTÁ PLENAMENTE ACREDITADA EN "
                f"LOS SOPORTES REMITIDOS.{texto_defensa} EL SERVICIO FUE INDICADO COMO PARTE DEL MANEJO "
                f"TERAPÉUTICO REQUERIDO, SIENDO NECESARIO E INSUSTITUIBLE SEGÚN LOS PROTOCOLOS VIGENTES. "
                f"CONFORME A LA RESOLUCIÓN 1995 DE 1999 Y LA RESOLUCIÓN 3047 DE 2008, LA HISTORIA CLÍNICA ES "
                f"SOPORTE SUFICIENTE, SIENDO IMPROCEDENTE OBJETAR LA PERTINENCIA SIN QUE EL ASEGURADOR APORTE "
                f"UN CONCEPTO MÉDICO INDIVIDUALIZADO."
            )
        else:
            cuerpo = (
                f"ESE HUS RECHAZA GLOSA {codigo} AL SERVICIO {servicio}.{texto_defensa} "
                f"SE EXIGE LEVANTAMIENTO ACORDE AL CONTRATO ({info_c})."
            )

        tabla_html = (
            f'<table border="1" style="width:100%; border-collapse:collapse; text-transform:uppercase; font-size:11px; margin-bottom:15px;">'
            f'<tr style="background-color:#1e3a8a; color:white;">'
            f'<th style="padding:8px; border:1px solid #cbd5e1;">CÓDIGO GLOSA</th>'
            f'<th style="padding:8px; border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th>'
            f'<th style="padding:8px; border:1px solid #cbd5e1;">VALOR OBJ.</th>'
            f'<th style="padding:8px; border:1px solid #cbd5e1; background-color:#10b981;">CONCEPTO</th></tr>'
            f'<tr><td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{codigo}</td>'
            f'<td style="padding:8px; border:1px solid #cbd5e1;">{servicio}</td>'
            f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center;">{valor}</td>'
            f'<td style="padding:8px; border:1px solid #cbd5e1; text-align:center; font-weight:bold;">{cod_res}<br>'
            f'<span style="font-size:9px;">{desc_res}</span></td></tr></table>'
        )

        return GlosaResult(
            tipo="TÉCNICO-LEGAL",
            resumen=f"DEFENSA FACTURA - {paciente if paciente != 'N/A' else 'PACIENTE EN MENCIÓN'}",
            dictamen=tabla_html + f'<div style="text-align:justify; line-height:1.7;">{cuerpo.upper()}</div>',
            codigo_glosa=codigo,
            valor_objetado=valor,
            paciente=paciente,
            mensaje_tiempo=msg_tiempo,
            color_tiempo=color_tiempo,
        )


def crear_oficio_pdf(eps: str, resumen: str, conclusion: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50
    )
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle('n', parent=estilos['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=16)
    estilo_titulo = ParagraphStyle('titulo', parent=estilos['Heading1'], alignment=1, fontSize=14, spaceAfter=20)
    estilo_sub = ParagraphStyle('sub', parent=estilos['Normal'], alignment=1, fontSize=12)

    match = re.search(r'<div[^>]*>(.*?)</div>', conclusion, re.IGNORECASE | re.DOTALL)
    cuerpo_texto = match.group(1) if match else conclusion

    clean_text = re.sub('<br>', '\n', cuerpo_texto)
    clean_text = re.sub('<[^<]+?>', ' ', clean_text).strip()
    fecha_actual = datetime.now().strftime("%d/%m/%Y")

    elements = [
        Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", estilo_titulo),
        Paragraph("<b>OFICINA DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS</b>", estilo_sub),
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
        Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n),
    ]
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
