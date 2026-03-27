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

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}
        
        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        info_c = contratos_db.get("OTRA / SIN DEFINIR", "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.")
        for k, v in contratos_db.items():
            if k in eps_segura: 
                info_c = v
                break

        # Extracción lógica del prefijo de glosa
        texto_base = str(data.tabla_excel)
        cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
        codigo_real = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_real[:2].upper()

        # 🧠 PROTOCOLO DE DEFENSA POR CAUSAL (Nivel Dirección Administrativa)
        if prefijo == "TA":
            tesis_causal = f"""TESIS DE DEFENSA TARIFARIA: Ataca la interpretación errónea del manual por parte de la EPS.
            1. Justifica la liquidación técnica: Si hubo bilateralidad o procedimientos múltiples, fundamenta el cobro basándote en la descripción quirúrgica y el manual pactado (Ej. 100% primer procedimiento y porcentajes de ley para subsiguientes).
            2. Cita el nexo causal: Cruza folio de descripción quirúrgica, cirujano (con RM) y el acuerdo contractual: {info_c}.
            3. Argumento legal: La EPS no puede modificar unilateralmente lo pactado (Art. 1602 C.C. y 871 C.Co), incurriendo en un enriquecimiento sin causa al recibir un servicio y pretender pagar una tarifa inferior a la acordada."""
        elif prefijo == "SO":
            tesis_causal = """TESIS DE DEFENSA DE SOPORTES Y TECNOLOGÍAS:
            1. Fundamento en Historia Clínica: La HC es soporte pleno (Res. 1995/1999). Identifica el insumo en la hoja de gastos/enfermería, cita folio, hora y pertinencia para la vida del paciente.
            2. Vacío Tarifario: Si el insumo no tiene tarifa en el anexo, aplica la norma supletoria: Anexo 5 Res. 3047 (Costo de adquisición + administración). Menciona que se anexa factura de compra del proveedor.
            3. Realidad Fáctica: La falta de un código administrativo no anula el gasto real incurrido por el hospital para garantizar la atención."""
        elif prefijo == "FA":
            tesis_causal = """TESIS DE DEFENSA DE FACTURACIÓN (CONCURRENCIA):
            1. Autonomía del Acto: Demuestra que el código cobrado es un servicio independiente y no está incluido en estancias o derechos de sala.
            2. Inaplicabilidad de Inclusiones: Desvirtúa la interpretación de 'integralidad' de la EPS citando el Anexo Técnico No. 3 de la Res. 3047. Exige a la aseguradora la norma exacta que obligue a la inclusión (la cual es inexistente)."""
        elif prefijo in ["PE", "CL", "CO"]:
            tesis_causal = """TESIS DE DEFENSA TÉCNICO-CIENTÍFICA (PERTINENCIA):
            1. Prevalencia del Criterio Clínico: El auditor administrativo de la EPS no puede sustituir el juicio del médico tratante. Cita diagnósticos CIE-10, evolución clínica y comorbilidades documentadas.
            2. Marco Constitucional: Invoca la Ley 1751 de 2015 (Derecho Fundamental e Integralidad). El HUS garantizó la salud ante una necesidad médica imperativa que no admite glosas de carácter puramente formal."""
        else:
            tesis_causal = "ESTRATEGIA INTEGRAL: Realiza un cruce de datos entre lo facturado y lo documentado, exigiendo el cumplimiento del sinalagma contractual."

        prompt = f"""ACTÚA COMO EL DIRECTOR NACIONAL DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS DE LA ESE HUS.
        Tu misión es redactar un dictamen administrativo de alta complejidad que desvirtúe totalmente la objeción de la EPS.
        
        SOPORTES CLÍNICOS DISPONIBLES: {contexto_pdf[:12000]}
        DETALLES DE LA OBJECIÓN: "{texto_base}"
        VÍNCULO CONTRACTUAL: {info_c}
        
        DIRECTRICES SENIOR DE REDACCIÓN:
        1. NO SEAS PASIVO: No digas "el médico puso tal cosa". Di: "La realidad fáctica documentada por el especialista [Nombre] con RM [Número] en el folio [Número] demuestra la absoluta pertinencia y veracidad del cobro".
        2. {tesis_causal}
        3. LÉXICO SUPERIOR: Emplea términos como: "Sinalagma contractual", "Carga de la prueba", "Principio de confianza legítima", "Precluyó la facultad auditora", "Acuerdo de voluntades".
        4. ESTRUCTURA OBLIGATORIA: Inicia con: "ESE HUS NO ACEPTA LA GLOSA [CÓDIGO] INTERPUESTA POR [MOTIVO], Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS CONTRACTUALES, TÉCNICOS Y NORMATIVOS:".
        5. CIERRE: Finaliza exigiendo el levantamiento inmediato de la glosa y el pago de la obligación principal más los intereses de mora si aplican.
        6. FORMATO: TODO EN MAYÚSCULAS. UN SOLO BLOQUE DE TEXTO CONTINUO SIN SALTOS DE LÍNEA NI VIÑETAS.

        RESPONDE ÚNICAMENTE CON ESTE FORMATO:
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
                    temperature=0.28
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
        dictamen = " ".join(b("DICTAMEN_INTEGRAL").split())

        # [Lógica de retorno GlosaResult y generación de PDF idéntica a la anterior para mantener estabilidad visual]
        # ... (Mantener el resto de la función analizar y crear_oficio_pdf como en la versión anterior)import os
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

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}
        
        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        info_c = contratos_db.get("OTRA / SIN DEFINIR", "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.")
        for k, v in contratos_db.items():
            if k in eps_segura: 
                info_c = v
                break

        # Extracción lógica del prefijo de glosa
        texto_base = str(data.tabla_excel)
        cod_m = re.search(r'([A-Z]{2,3}\d{3,4})', texto_base)
        codigo_real = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_real[:2].upper()

        # 🧠 PROTOCOLO DE DEFENSA POR CAUSAL (Nivel Dirección Administrativa)
        if prefijo == "TA":
            tesis_causal = f"""TESIS DE DEFENSA TARIFARIA: Ataca la interpretación errónea del manual por parte de la EPS.
            1. Justifica la liquidación técnica: Si hubo bilateralidad o procedimientos múltiples, fundamenta el cobro basándote en la descripción quirúrgica y el manual pactado (Ej. 100% primer procedimiento y porcentajes de ley para subsiguientes).
            2. Cita el nexo causal: Cruza folio de descripción quirúrgica, cirujano (con RM) y el acuerdo contractual: {info_c}.
            3. Argumento legal: La EPS no puede modificar unilateralmente lo pactado (Art. 1602 C.C. y 871 C.Co), incurriendo en un enriquecimiento sin causa al recibir un servicio y pretender pagar una tarifa inferior a la acordada."""
        elif prefijo == "SO":
            tesis_causal = """TESIS DE DEFENSA DE SOPORTES Y TECNOLOGÍAS:
            1. Fundamento en Historia Clínica: La HC es soporte pleno (Res. 1995/1999). Identifica el insumo en la hoja de gastos/enfermería, cita folio, hora y pertinencia para la vida del paciente.
            2. Vacío Tarifario: Si el insumo no tiene tarifa en el anexo, aplica la norma supletoria: Anexo 5 Res. 3047 (Costo de adquisición + administración). Menciona que se anexa factura de compra del proveedor.
            3. Realidad Fáctica: La falta de un código administrativo no anula el gasto real incurrido por el hospital para garantizar la atención."""
        elif prefijo == "FA":
            tesis_causal = """TESIS DE DEFENSA DE FACTURACIÓN (CONCURRENCIA):
            1. Autonomía del Acto: Demuestra que el código cobrado es un servicio independiente y no está incluido en estancias o derechos de sala.
            2. Inaplicabilidad de Inclusiones: Desvirtúa la interpretación de 'integralidad' de la EPS citando el Anexo Técnico No. 3 de la Res. 3047. Exige a la aseguradora la norma exacta que obligue a la inclusión (la cual es inexistente)."""
        elif prefijo in ["PE", "CL", "CO"]:
            tesis_causal = """TESIS DE DEFENSA TÉCNICO-CIENTÍFICA (PERTINENCIA):
            1. Prevalencia del Criterio Clínico: El auditor administrativo de la EPS no puede sustituir el juicio del médico tratante. Cita diagnósticos CIE-10, evolución clínica y comorbilidades documentadas.
            2. Marco Constitucional: Invoca la Ley 1751 de 2015 (Derecho Fundamental e Integralidad). El HUS garantizó la salud ante una necesidad médica imperativa que no admite glosas de carácter puramente formal."""
        else:
            tesis_causal = "ESTRATEGIA INTEGRAL: Realiza un cruce de datos entre lo facturado y lo documentado, exigiendo el cumplimiento del sinalagma contractual."

        prompt = f"""ACTÚA COMO EL DIRECTOR NACIONAL DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS DE LA ESE HUS.
        Tu misión es redactar un dictamen administrativo de alta complejidad que desvirtúe totalmente la objeción de la EPS.
        
        SOPORTES CLÍNICOS DISPONIBLES: {contexto_pdf[:12000]}
        DETALLES DE LA OBJECIÓN: "{texto_base}"
        VÍNCULO CONTRACTUAL: {info_c}
        
        DIRECTRICES SENIOR DE REDACCIÓN:
        1. NO SEAS PASIVO: No digas "el médico puso tal cosa". Di: "La realidad fáctica documentada por el especialista [Nombre] con RM [Número] en el folio [Número] demuestra la absoluta pertinencia y veracidad del cobro".
        2. {tesis_causal}
        3. LÉXICO SUPERIOR: Emplea términos como: "Sinalagma contractual", "Carga de la prueba", "Principio de confianza legítima", "Precluyó la facultad auditora", "Acuerdo de voluntades".
        4. ESTRUCTURA OBLIGATORIA: Inicia con: "ESE HUS NO ACEPTA LA GLOSA [CÓDIGO] INTERPUESTA POR [MOTIVO], Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS CONTRACTUALES, TÉCNICOS Y NORMATIVOS:".
        5. CIERRE: Finaliza exigiendo el levantamiento inmediato de la glosa y el pago de la obligación principal más los intereses de mora si aplican.
        6. FORMATO: TODO EN MAYÚSCULAS. UN SOLO BLOQUE DE TEXTO CONTINUO SIN SALTOS DE LÍNEA NI VIÑETAS.

        RESPONDE ÚNICAMENTE CON ESTE FORMATO:
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
                    temperature=0.28
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
        dictamen = " ".join(b("DICTAMEN_INTEGRAL").split())

        # [Lógica de retorno GlosaResult y generación de PDF idéntica a la anterior para mantener estabilidad visual]
        # ... (Mantener el resto de la función analizar y crear_oficio_pdf como en la versión anterior)
