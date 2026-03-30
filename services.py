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
            unido = "".join(paginas[:2]) + "\n\n...[ANÁLISIS TÉCNICO INTERMEDIO]...\n\n" + "".join(paginas[-4:])
        return unido[:15000]
    except Exception:
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO PRINCIPAL - CEREBRO 70B ELITE
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

        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        info_c = contratos_db.get("OTRA / SIN DEFINIR", "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.")
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

        # ── GUILLOTINAS LEGALES (Sin cambios, ya son Pro) ──
        # ... [Mantenemos la lógica de Extemporaneidad y Ratificación que ya tienes] ...

        # 🧠 ESTRATEGIA DE AUDITORÍA FORENSE POR CAUSAL
        if prefijo == "TA":
            tesis = f"""ESTRATEGIA TARIFARIA ELITE:
            1. REGLA ORO: USA SIEMPRE 'VALOR OBJETADO'. 
            2. INDEXACIÓN 2026: Si la glosa menciona SMLV o UVB, invoca la Circular Externa 047 de 2025: las tarifas se indexan obligatoriamente a la Unidad de Valor Básico (UVB).
            3. CONTRATO: Cita {info_c}. Argumenta que la EPS intenta una reliquidación unilateral que vulnera el equilibrio económico del hospital.
            4. Realiza un cruce con la descripción quirúrgica (folios, médico) para justificar lateralidad o grupos quirúrgicos según Manual SOAT o Institucional."""
        elif prefijo == "FA":
            tesis = """ESTRATEGIA DE FACTURACIÓN (INCLUSIONES):
            1. Desvirtúa la 'Inclusión': El procedimiento objetado es un ACTO MÉDICO AUTÓNOMO con código CUPS independiente.
            2. Cita el Anexo 3 de la Res. 3047/2008. Exige a la EPS que demuestre bajo qué norma técnica o párrafo del Manual SOAT/ISS se subsume dicho servicio.
            3. Si es interconsulta (IC) por anestesia, defiende su pertinencia si hubo manejo de dolor o condiciones pre-anestésicas especiales documentadas."""
        elif prefijo == "SO":
            tesis = """ESTRATEGIA DE SOPORTES (BIFURCADA):
            - CASO SOPORTE CLÍNICO: Localiza el resultado (TAC, Biopsia, Lectura). Cita al profesional (con RM) y los hallazgos. Invoca la Res. 1995/1999 (Historia Clínica como plena prueba).
            - CASO INSUMOS: Si falta factura de compra, menciona que se anexa. Exige pago al costo + administración según Anexo 5 Res. 3047."""
        else:
            tesis = """ESTRATEGIA DE PERTINENCIA: Defiende la integralidad del servicio (Ley 1751/2015). El auditor administrativo no tiene facultad para revocar el criterio del médico especialista tratante sin un sustento técnico-científico individualizado."""

        system_prompt = f"""Eres el DIRECTOR NACIONAL DE JURÍDICA Y AUDITORÍA DE CUENTAS MÉDICAS de la ESE HUS.
        Tu nivel de redacción es el de un Abogado Especialista con 30 años de éxito. 
        Eres agresivo, técnico y no aceptas respuestas genéricas.

        REGLAS DE ORO:
        1. TODO EN MAYÚSCULAS.
        2. MINERÍA DE DATOS AGRESIVA: Debes buscar nombres de médicos, Registros Médicos (RM), números de folio, fechas y resultados clínicos exactos. ÚSALOS COMO ARMA.
        3. SI NO ENCUENTRAS UN DATO, NO LO INVENTES. Di "el soporte documental anexo".
        4. TERMINOLOGÍA: Prohibido 'valor facturado'. Usa 'VALOR OBJETADO'.
        5. LÉXICO: Sinalagma contractual, Realidad fáctica, Preclusión de la oportunidad, Acervo probatorio.
        6. ESTRATEGIA APLICABLE: {tesis}"""

        user_prompt = f"EPS: {eps_segura}\nCONTRATO: {info_c}\nGLOSA: {texto_base}\nSOPORTES: {contexto_pdf[:10000]}"

        # ── LLAMADA AL CEREBRO 70B (MÁS INTELIGENTE) ──
        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    model="llama-3.3-70b-versatile", # <--- EL CEREBRO MÁS POTENTE
                    temperature=0.15,
                    max_tokens=2500
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception:
                await asyncio.sleep(30) # Espera larga para resetear TPM de Groq

        # ... [El resto de la función xml, inyección de apertura y retorno GlosaResult se mantiene igual] ...
