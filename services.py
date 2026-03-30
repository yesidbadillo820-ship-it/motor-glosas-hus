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

# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN DE PDF
# ─────────────────────────────────────────────────────────────────────────────

def _procesar_pdf_sync(file_content: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        total = len(reader.pages)
        paginas = []
        for i in range(total):
            txt = reader.pages[i].extract_text()
            if txt:
                paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")
        unido = "".join(paginas)
        if total > 8:
            unido = "".join(paginas[:2]) + "\n\n...[ANÁLISIS TÉCNICO]...\n\n" + "".join(paginas[-4:])
        return unido[:16000]
    except Exception:
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO PRINCIPAL - CEREBRO 70B ELITE (BLINDAJE INSTITUCIONAL)
# ─────────────────────────────────────────────────────────────────────────────

class GlosaService:
    def __init__(self, api_key: str):
        self.cliente = AsyncGroq(api_key=api_key)

    async def extraer_pdf(self, file_content: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _procesar_pdf_sync, file_content)
        except Exception:
            logger.error("Error al extraer PDF", exc_info=True)
            return ""

    def convertir_numero(self, m_str: str) -> float:
        if not m_str: return 0.0
        clean = re.sub(r'[^\d]', '', str(m_str))
        try: return float(clean)
        except ValueError: return 0.0

    def xml(self, tag: str, texto: str, default: str = "N/A") -> str:
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip().replace("**", "").replace("*", "")
            return val if val else default
        return default

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None: contratos_db = {}

        # 1. ORDEN INSTITUCIONAL BASADA EN LOS NUEVOS SOPORTES (RESOLUCIONES 054 Y 120)
        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        
        # Inyectamos la base legal real del hospital en el sistema
        BASE_LEGAL_HUS = """
        - RESOLUCIÓN INSTITUCIONAL 054 DE 2026: Realiza la unificación de las Resoluciones de tarifas Institucionales y adopta el Manual de Tarifas de la E.S.E. HUS. El cumplimiento de este manual es OBLIGATORIO para facturar a las ERP (Artículo Segundo).
        - RESOLUCIÓN INSTITUCIONAL 120 DE 2026: Crea códigos y tarifas institucionales específicos (incluyendo Gastroenterología) e incorpora estos al Manual de Tarifas Unificado.
        - TARIFA SOBERANA: En ausencia de contrato pactado, rige el Manual Tarifario Institucional y la Resolución 054 de 2026, aplicando TARIFA SOAT PLENO (100% del Decreto 2423 de 1996) sin descuentos.
        """

        info_c = contratos_db.get("OTRA / SIN DEFINIR", 
            f"AUSENCIA DE CONTRATO VIGENTE. Rige de manera vinculante la RESOLUCIÓN 054 DE 2026 y la RESOLUCIÓN 120 DE 2026 de la E.S.E. HUS. La tarifa institucional obligatoria es SOAT PLENO (100% del Decreto 2423 de 1996) según el Artículo Segundo de la norma citada.")
        
        for k, v in contratos_db.items():
            if k in eps_segura:
                info_c = v
                break

        texto_base    = str(data.tabla_excel).strip()
        val_ac_num    = self.convertir_numero(data.valor_aceptado)
        is_ratificada = str(data.etapa).strip().upper() == "RATIFICADA"

        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else "N/A"
        prefijo = codigo_detectado[:2].upper()

        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        # ── CÁLCULO DE TIEMPOS ──
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

        # 🧠 ESTRATEGIA DE DEFENSA SENIOR (REFORZADA CON RESOLUCIONES)
        if prefijo == "TA":
            tesis = f"""TESIS TARIFARIA INSTITUCIONAL:
            1. REGLA OBLIGATORIA: Cita siempre la RESOLUCIÓN 054 DE 2026 y la RESOLUCIÓN 120 DE 2026 como la norma soberana que rige el Manual de Tarifas de la E.S.E. HUS.
            2. ARGUMENTO DE SOBERANÍA: El Hospital es una entidad descentralizada con autonomía administrativa (Decreto 0025 de 2005). Ante la falta de un acuerdo de voluntades bilateral, la EPS no puede imponer descuentos ni indexaciones (SMLV/ISS) de forma unilateral. El cobro se realiza a TARIFA SOAT PLENO (100%) bajo el amparo de la Resolución 054 de 2026.
            3. TERMINOLOGÍA: Prohibido 'valor facturado'. Usa 'VALOR OBJETADO'.
            4. DESARROLLO: Explica que la reliquidación de la EPS carece de sustento jurídico al pretender ignorar el Manual Tarifario Institucional vigente."""
        elif prefijo == "SO":
            tesis = """TESIS DE SOPORTES CLÍNICOS: Localiza el resultado o nota técnica (Ej. Patología, TAC, Cirugía). Cita médico, RM y hallazgo. Invoca la Res. 1995/1999: la Historia Clínica es plena prueba asistencial. La omisión administrativa de la EPS no anula la realidad fáctica de la prestación del servicio."""
        elif prefijo == "FA":
            tesis = """TESIS DE FACTURACIÓN (AUTONOMÍA): Defiende que el código glosado es un acto médico autónomo e independiente. Cita el Anexo 3 de la Res. 3047/2008. Exige a la aseguradora la norma exacta de inclusión; de lo contrario, la glosa es improcedente."""
        else:
            tesis = """TESIS INTEGRAL: Cruce milimétrico entre la descripción del servicio en la historia clínica y el Manual Tarifario Institucional de la E.S.E. HUS."""

        system_prompt = f"""Eres el DIRECTOR NACIONAL DE JURÍDICA Y AUDITORÍA DE LA ESE HUS. (30 años de experiencia).
        No aceptas glosas injustificadas. Eres agresivo, técnico y profundamente argumentativo.

        REGLAS DE ORO PARA EL DICTAMEN:
        1. TODO EN MAYÚSCULAS.
        2. PROHIBIDO LAS RESPUESTAS CORTAS: Cada dictamen debe tener mínimo 2 párrafos de análisis técnico.
        3. FUNDAMENTO OBLIGATORIO: {BASE_LEGAL_HUS}
        4. MINERÍA DE SOPORTES: Extrae nombres de médicos, Registros Médicos (RM), folios y resultados reales. Úsalos como proyectiles contra la EPS.
        5. TERMINOLOGÍA: Nunca digas 'valor facturado'. Usa SIEMPRE 'VALOR OBJETADO'.
        6. LÉXICO SUPERIOR: Sinalagma contractual, Realidad fáctica, Preclusión de la oportunidad auditora, Autonomía administrativa, Acuerdo de voluntades."""

        user_prompt = f"EPS: {eps_segura}\nCONTRATO/NORMA: {info_c}\nESTRATEGIA REQUERIDA: {tesis}\nGLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:10000]}"

        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.15,
                    max_tokens=2500
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception: await asyncio.sleep(30)

        # Extracción segura
        paciente      = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_final  = self.xml("codigo_glosa", res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado", res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento", res_ia, "ERROR: LA IA NO GENERÓ EL ARGUMENTO.")
        argumento_ia  = re.sub(r'[ \t]+', ' ', argumento_ia).strip()

        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor_xml)
            valor_acep_fmt = f"$ {val_ac_num:,.0f}".replace(",", ".")
            apertura = f"ESE HUS ACEPTA LA GLOSA {codigo_final} POR UN VALOR DE {valor_acep_fmt}, SUSTENTANDO LO SIGUIENTE: "
            cod_res, desc_res = ("RE9702", "GLOSA ACEPTADA TOTALMENTE") if val_ac_num >= val_obj_num else ("RE9801", "GLOSA PARCIALMENTE ACEPTADA")
            tabla_html = _tabla_aceptacion(codigo_final, valor_xml, valor_acep_fmt, cod_res, desc_res)
            tipo_final, res_final = "AUDITORÍA - ACEPTACIÓN", f"ACEPTACIÓN DE GLOSA – {paciente}"
        else:
            apertura = f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} INTERPUESTA POR {motivo}, Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS TÉCNICOS, CONTRACTUALES Y NORMATIVOS: "
            
            # 🔥 USAMOS RE9602 PARA TA O CASOS INSTITUCIONALES SIN CONTRATO 🔥
            if (prefijo in ["TA", "SO"] or "OTRA" in eps_segura or "SIN DEFINIR" in eps_segura):
                cod_res, desc_res = "RE9602", "GLOSA NO ACEPTADA"
            else:
                cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA"
            
            tabla_html = _tabla_defensa(codigo_final, servicio, valor_xml, cod_res, desc_res)
            tipo_final, res_final = "TÉCNICO-LEGAL", f"DEFENSA FACTURA – {paciente}"

        # Ensamblaje perfecto: Evita que sea una sola línea
        if not re.search(r'^ESE HUS (NO |)ACEPTA', argumento_ia, re.IGNORECASE):
            dictamen_final = apertura + "\n\n" + argumento_ia
        else:
            dictamen_final = argumento_ia

        return GlosaResult(tipo=tipo_final, resumen=res_final, dictamen=tabla_html + f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{dictamen_final.replace("\n", "<br/>")}</div>', codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

# ... [Mantenemos las funciones de tablas y PDF iguales] ...
