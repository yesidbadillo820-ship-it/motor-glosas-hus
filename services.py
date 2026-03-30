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
            unido = "".join(paginas[:2]) + "\n\n...[PÁGINAS INTERMEDIAS OMITIDAS]...\n\n" + "".join(paginas[-4:])
        return unido[:16000]
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO PRINCIPAL
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
        if not m_str:
            return 0.0
        clean = re.sub(r'[^\d]', '', str(m_str))
        try:
            return float(clean)
        except ValueError:
            return 0.0

    def xml(self, tag: str, texto: str, default: str = "N/A") -> str:
        """Parser XML a prueba de balas. Nunca falla."""
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip().replace("**", "").replace("*", "")
            return val if val else default
        return default

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL
    # ──────────────────────────────────────────────────────────────────────────

    async def analizar(
        self,
        data: GlosaInput,
        contexto_pdf: str = "",
        contratos_db: dict = None
    ) -> GlosaResult:

        if contratos_db is None:
            contratos_db = {}

        # ── Contexto de contrato ──────────────────────────────────────────────
        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        info_c = contratos_db.get(
            "OTRA / SIN DEFINIR",
            "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO. SE EXIGE EL PAGO AL 100% DE LA TARIFA VIGENTE."
        )
        for k, v in contratos_db.items():
            if k in eps_segura:
                info_c = v
                break

        # ── Pre-procesamiento de entradas ─────────────────────────────────────
        texto_base    = str(data.tabla_excel).strip()
        val_ac_num    = self.convertir_numero(data.valor_aceptado)
        is_ratificada = str(data.etapa).strip().upper() == "RATIFICADA"

        # Detectar código de glosa desde el texto
        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else texto_base.split()[0][:10].upper() if texto_base else "N/A"
        prefijo = codigo_detectado[:2].upper() if codigo_detectado != "N/A" else "XX"

        # Detectar valor desde el texto
        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        # ── Cálculo de días hábiles ───────────────────────────────────────────
        msg_tiempo, color_tiempo, es_extemporanea, dias = (
            "Fechas no ingresadas", "bg-slate-500", False, 0
        )
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
                    msg_tiempo      = f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES)"
                    color_tiempo    = "bg-red-600"
                else:
                    msg_tiempo   = f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)"
                    color_tiempo = "bg-emerald-500"
            except Exception as e:
                logger.error(f"Error procesando fechas: {e}")

        # ══════════════════════════════════════════════════════════════════════
        # 🛡️  GUILLOTINAS LEGALES — RETORNO DIRECTO SIN LLAMAR A LA IA
        # ══════════════════════════════════════════════════════════════════════

        # ── A) GLOSA RATIFICADA ───────────────────────────────────────────────
        if is_ratificada and val_ac_num == 0:
            tabla = _tabla_simple(codigo_detectado, "RATIFICACIÓN", valor_obj_raw, "RE9901", "GLOSA SUBSANADA TOTALMENTE", color_header="#1e3a8a")
            texto = (
                "ESE HUS NO ACEPTA LA GLOSA RATIFICADA. SE MANTIENE EN SU INTEGRIDAD LA RESPUESTA DE "
                "DEFENSA TÉCNICA, CONTRACTUAL Y NORMATIVA PRESENTADA EN EL TRÁMITE DE LA GLOSA INICIAL, "
                "TODA VEZ QUE LA ENTIDAD GLOSANTE NO APORTA NUEVOS ELEMENTOS DE JUICIO QUE DESVIRTÚEN "
                "LA FACTURACIÓN NI LA PRESTACIÓN DEL SERVICIO. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA "
                "DE CONCILIACIÓN DE AUDITORÍA MÉDICA ENTRE LAS PARTES (CORREO: CARTERA@HUS.GOV.CO). "
                "NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, DE NO LLEGARSE A UN "
                "ACUERDO EN LA INSTANCIA DE CONCILIACIÓN, SE CONTINUARÁ CON LAS ACCIONES DE COBRO "
                "PERTINENTES EN LOS TÉRMINOS LEGALES VIGENTES."
            )
            return GlosaResult(
                tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO DE RATIFICACIÓN",
                dictamen=tabla + _div(texto),
                codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw,
                paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600"
            )

        # ── B) GLOSA EXTEMPORÁNEA ─────────────────────────────────────────────
        if es_extemporanea and val_ac_num == 0:
            tabla = _tabla_simple(
                codigo_detectado,
                f"EXTEMPORÁNEA ({dias} DÍAS)",
                valor_obj_raw, "RE9502", "ACEPTACIÓN TÁCITA",
                color_estado="#b91c1c"
            )
            texto = (
                f"ESE HUS NO ACEPTA LA GLOSA POR EXTEMPORANEIDAD. AL HABER TRANSCURRIDO {dias} DÍAS "
                f"HÁBILES ENTRE LA FECHA DE RADICACIÓN DE LA FACTURA Y LA RECEPCIÓN DE LA GLOSA, "
                f"SUPERANDO EL TÉRMINO MÁXIMO PERENTORIO E IMPRORROGABLE DE VEINTE (20) DÍAS HÁBILES "
                f"ESTABLECIDO EN EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, EN EL ARTÍCULO 13 (LITERAL D) "
                f"DE LA LEY 1122 DE 2007 Y EN EL DECRETO 4747 DE 2007 (COMPILADO EN EL D.U.R. 780 DE "
                f"2016), HA OPERADO DE PLENO DERECHO EL FENÓMENO JURÍDICO DE LA ACEPTACIÓN TÁCITA DE "
                f"LA FACTURA. EN CONSECUENCIA, PRECLUYÓ DEFINITIVAMENTE LA OPORTUNIDAD PROCESAL DE LA "
                f"EPS PARA FORMULAR, COMUNICAR O MANTENER GLOSA ALGUNA SOBRE ESTA CUENTA. SE EXIGE EL "
                f"PAGO INMEDIATO E ÍNTEGRO DE LA TOTALIDAD DE LOS VALORES FACTURADOS."
            )
            return GlosaResult(
                tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO POR EXTEMPORANEIDAD",
                dictamen=tabla + _div(texto),
                codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw,
                paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo
            )

        # ══════════════════════════════════════════════════════════════════════
        # 🧠  CEREBRO DE AUDITORÍA ADAPTATIVA — PASA LOS FILTROS → LLAMA A IA
        # ══════════════════════════════════════════════════════════════════════

        # Estrategia específica por tipo de glosa
        if val_ac_num > 0:
            valor_acep_fmt = f"${val_ac_num:,.0f}".replace(",", ".")
            estrategia = (
                f"CASO ACEPTACIÓN: La ESE HUS acepta la glosa por valor de {valor_acep_fmt}. "
                f"En <argumento> redacta máximo 3 líneas explicando el motivo de la aceptación "
                f"(error de codificación, soporte insuficiente, etc.) de forma formal. "
                f"Sin leyes, sin viñetas, en MAYÚSCULAS."
            )
        elif prefijo == "TA":
            estrategia = f"""DEFENSA TARIFARIA:
1. Detecta si hay BILATERALIDAD o MÚLTIPLES TIEMPOS QUIRÚRGICOS en los soportes y úsalo como argumento principal.
2. Cita el contrato vigente: {info_c}. Extrae cualquier cláusula o acta de negociación que aparezca en los soportes.
3. Si hay tabla de ítems con valores individuales, insértala dentro de <argumento> usando esta estructura HTML exacta:
   <table border="1" style="width:100%;border-collapse:collapse;font-size:11px;margin:10px 0;"><tr style="background:#1e3a8a;color:white;"><th style="padding:6px;border:1px solid #ccc;">ÍTEM</th><th style="padding:6px;border:1px solid #ccc;">CONCEPTO</th><th style="padding:6px;border:1px solid #ccc;">VALOR FACTURADO</th></tr><!-- filas aquí --></table>
4. Argumento letal: La EPS vulnera el Art. 871 del C.Co. y el principio de buena fe contractual. No puede recibir el servicio y liquidar por debajo de lo pactado."""
        elif prefijo == "SO":
            estrategia = """DEFENSA DE SOPORTES E INSUMOS:
1. Localiza el insumo/medicamento en la Epicrisis o Hoja de Gastos. Cita el FOLIO o PÁGINA EXACTA.
2. Menciona que la factura de adquisición del insumo se adjunta como soporte de precio (costo + margen contractual).
3. Normas clave: Res. 1995/1999 y Res. 1645/2016 (la historia clínica es soporte asistencial pleno), Anexo 5 Res. 3047/2008 (factura de compra = soporte válido para insumos sin tarifa SOAT).
4. Cierre: el insumo era INDISPENSABLE para el procedimiento y sin su uso no habría sido posible realizarlo."""
        elif prefijo == "FA":
            estrategia = """DEFENSA DE FACTURACIÓN (AUTONOMÍA DEL ACTO):
1. Demuestra que el procedimiento cobrado es un ACTO MÉDICO AUTÓNOMO con código CUPS y tarifa PROPIOS en el Decreto 2423/1996.
2. Cita la documentación que acredita su ejecución (registro de enfermería, hoja de gastos, folio exacto).
3. Argumento letal: Cita el Anexo Técnico N.° 3 Res. 3047/2008: la glosa debe señalar la NORMA EXACTA que establece la inclusión en otro concepto. La EPS no la cita porque no existe.
4. Ningún concepto facturado en esta cuenta incorpora dicho procedimiento en su descripción tarifaria."""
        elif prefijo in ["CO", "CL", "PE"]:
            estrategia = """DEFENSA DE PERTINENCIA Y COBERTURA:
1. Extrae diagnósticos CIE-10, nombre del médico tratante (con RM), fecha y tipo de procedimiento de los soportes.
2. Demuestra que la atención fue PERTINENTE, IDÓNEA y NECESARIA para salvaguardar la salud/vida del paciente.
3. Normas: Ley 1751/2015 (salud = derecho fundamental, garantía de integralidad), Res. 3280/2018 (rutas integrales de atención en salud).
4. Argumento letal: El auditor administrativo no puede sobreponerse al JUICIO MÉDICO ESPECIALIZADO sin aportar un concepto médico individualizado que desvirtúe la indicación clínica. Exige que lo aporten."""
        else:
            estrategia = (
                f"DEFENSA CONTRACTUAL INTEGRAL: Fundamenta en el cumplimiento del contrato ({info_c}), "
                f"la prestación efectiva del servicio y los soportes del expediente clínico."
            )

        # ── Construcción del prompt ───────────────────────────────────────────
        system_prompt = f"""Eres el DIRECTOR NACIONAL DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS de la ESE HUS.
30 años de experiencia. Eres implacable, técnico y profesional.

REGLAS DE ORO — NUNCA LAS INCUMPLAS:
1. TODO EN MAYÚSCULAS. Sin excepción.
2. MINERÍA DE SOPORTES: Lee los soportes clínicos y extrae DATOS CONCRETOS para usar como armas:
   - Nombres de médicos con Registro Médico (RM).
   - Números de folio, página exacta, consecutivo quirúrgico, número de orden/autorización.
   - Fechas exactas, diagnósticos CIE-10, códigos CUPS de procedimientos realizados.
   - Códigos de insumos, valores individuales ($X.XXX), referencias comerciales.
   Si no hay soportes, usa los datos disponibles en el texto de la glosa.
3. El campo <argumento> debe ir directo a los fundamentos. SIN introducción, SIN saludo.
4. Usa lenguaje técnico-jurídico: "sinalagma contractual", "acervo probatorio", "precluyó", "de pleno derecho".
5. APLICA EXACTAMENTE ESTA ESTRATEGIA: {estrategia}
6. Termina <argumento> con UNA SOLA oración de exigencia que nombre el código de glosa, el ítem y el valor exacto.
7. RESPONDE ÚNICAMENTE con el bloque XML pedido. Cero texto fuera de las etiquetas."""

        user_prompt = f"""EPS: {eps_segura}
CONTRATO VIGENTE: {info_c}
GLOSA RECIBIDA: "{texto_base}"
SOPORTES CLÍNICOS DEL EXPEDIENTE:
{contexto_pdf[:12000]}

RESPONDE ÚNICAMENTE CON ESTE FORMATO XML EXACTO (sin ningún texto fuera de las etiquetas):
<paciente>Nombre completo del paciente o N/A</paciente>
<codigo_glosa>Código de objeción (ej: FA0802, SO4201, TA5801)</codigo_glosa>
<valor_objetado>Valor en pesos (ej: $ 2.030.800) o N/A</valor_objetado>
<servicio_glosado>Nombre del servicio o procedimiento glosado</servicio_glosado>
<motivo_resumido>Máximo 6 palabras: el argumento que usa la EPS</motivo_resumido>
<argumento>Aquí va TODO el texto de defensa en MAYÚSCULAS, párrafos separados con saltos de línea, sin viñetas ni asteriscos.</argumento>"""

        # ── Llamada a Groq con retry + backoff ────────────────────────────────
        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt}
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.2,
                    max_tokens=2000,
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception as e:
                logger.error(f"Intento {intento + 1} falló al contactar Groq: {e}", exc_info=True)
                if intento == 2:
                    return GlosaResult(
                        tipo="Error", resumen="Error de Conexión IA",
                        dictamen="Error persistente al contactar el modelo. Por favor reintente.",
                        codigo_glosa="N/A", valor_objetado="0",
                        paciente="N/A", mensaje_tiempo="", color_tiempo=""
                    )
                await asyncio.sleep(2 ** intento)

        # ── Extracción de campos desde XML ────────────────────────────────────
        paciente      = self.xml("paciente",      res_ia, "NO IDENTIFICADO")
        codigo_xml    = self.xml("codigo_glosa",  res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado",res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido",  res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento",     res_ia,
                                  "SE RECHAZA LA GLOSA EN CUMPLIMIENTO DEL CONTRATO Y LA NORMA VIGENTE.")

        # Usar código detectado por regex si la IA no lo encontró bien
        codigo_final = codigo_xml if (codigo_xml != "N/A" and re.match(r'[A-Z]{2,3}\d{3,4}', codigo_xml)) else codigo_detectado
        # Compactar espacios pero preservar saltos de línea para el HTML
        argumento_ia  = re.sub(r'[ \t]+', ' ', argumento_ia).strip()

        # ══════════════════════════════════════════════════════════════════════
        # 🔨  INYECCIÓN PYTHON: APERTURA "ESE HUS ACEPTA / NO ACEPTA"
        # ══════════════════════════════════════════════════════════════════════
        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor_xml)
            valor_acep_fmt = f"$ {val_ac_num:,.0f}".replace(",", ".")
            apertura = f"ESE HUS ACEPTA LA GLOSA {codigo_final} POR UN VALOR DE {valor_acep_fmt}. "
            cod_res  = "RE9702" if val_ac_num >= val_obj_num and val_obj_num > 0 else "RE9801"
            desc_res = "GLOSA ACEPTADA TOTALMENTE" if cod_res == "RE9702" else "GLOSA PARCIALMENTE ACEPTADA"
            tabla_html = _tabla_aceptacion(codigo_final, valor_xml, valor_acep_fmt, cod_res, desc_res)
            tipo_final    = "AUDITORÍA - ACEPTACIÓN"
            resumen_final = f"ACEPTACIÓN DE GLOSA – {paciente}"
        else:
            apertura = (
                f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} INTERPUESTA POR {motivo}, "
                f"Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS TÉCNICOS, "
                f"CONTRACTUALES Y NORMATIVOS: "
            )
            cod_res  = "RE9206" if (prefijo == "TA" and ("OTRA" in eps_segura or "SIN DEFINIR" in eps_segura)) else "RE9901"
            desc_res = "GLOSA INJUSTIFICADA 100%" if cod_res == "RE9206" else "GLOSA NO ACEPTADA"
            tabla_html = _tabla_defensa(codigo_final, servicio, valor_xml, cod_res, desc_res)
            tipo_final    = "TÉCNICO-LEGAL"
            resumen_final = f"DEFENSA FACTURA – {paciente}"

        # Si la IA ya empieza con "ESE HUS NO ACEPTA..." no duplicamos la apertura
        if re.search(r'^ESE HUS (NO |)ACEPTA', argumento_ia.strip(), re.IGNORECASE):
            dictamen_texto = argumento_ia
        else:
            dictamen_texto = apertura + argumento_ia

        # Convertir saltos de línea a <br/> para el HTML
        dictamen_html = dictamen_texto.replace('\n', '<br/>')

        return GlosaResult(
            tipo=tipo_final,
            resumen=resumen_final,
            dictamen=tabla_html + f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{dictamen_html}</div>',
            codigo_glosa=codigo_final,
            valor_objetado=valor_xml,
            paciente=paciente,
            mensaje_tiempo=msg_tiempo,
            color_tiempo=color_tiempo,
        )


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES DE TABLAS HTML
# ─────────────────────────────────────────────────────────────────────────────

def _div(texto: str) -> str:
    return f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{texto}</div>'

def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_header="#1e3a8a", color_estado=None):
    estilo_estado = f'background-color:{color_estado};color:white;' if color_estado else ''
    return (
        f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;'
        f'font-size:11px;margin-bottom:15px;">'
        f'<tr style="background-color:{color_header};color:white;">'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">ESTADO</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">VALOR</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr>'
        f'<tr>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;{estilo_estado}"><b>{estado}</b></td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">'
        f'{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td>'
        f'</tr></table>'
    )

def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return (
        f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;'
        f'font-size:11px;margin-bottom:15px;">'
        f'<tr style="background-color:#1e3a8a;color:white;">'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJ.</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr>'
        f'<tr>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;">{servicio}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">'
        f'{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td>'
        f'</tr></table>'
    )

def _tabla_aceptacion(codigo, valor_obj, valor_acep, cod_res, desc_res):
    return (
        f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;'
        f'font-size:11px;margin-bottom:15px;">'
        f'<tr style="background-color:#1e3a8a;color:white;">'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJETADO</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;background-color:#d97706;">VALOR ACEPTADO</th>'
        f'<th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr>'
        f'<tr>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor_obj}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;color:#d97706;">{valor_acep}</td>'
        f'<td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">'
        f'{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td>'
        f'</tr></table>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# GENERADOR DE OFICIO PDF
# ─────────────────────────────────────────────────────────────────────────────

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50
    )
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle(
        'n', parent=estilos['Normal'],
        alignment=TA_JUSTIFY, fontSize=11, leading=16
    )
    estilo_titulo = ParagraphStyle(
        'titulo', parent=estilos['Heading1'],
        alignment=1, fontSize=14, spaceAfter=20
    )

    match = re.search(r'<div[^>]*>(.*?)</div>', conclusion, re.IGNORECASE | re.DOTALL)
    cuerpo = match.group(1) if match else conclusion
    clean  = re.sub(r'<br\s*/?>', '\n', cuerpo)
    clean  = re.sub(r'<[^>]+>', '', clean).strip()

    fecha = datetime.now().strftime("%d/%m/%Y")
    elements = []

    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        img = Image(logo_path, width=250, height=60)
        img.hAlign = 'LEFT'
        elements.append(img)
        elements.append(Spacer(1, 15))

    elements += [
        Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", estilo_titulo),
        Paragraph("<b>OFICINA DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS</b>",
                  ParagraphStyle('sub', alignment=1, fontSize=12)),
        Spacer(1, 30),
        Paragraph(f"Bucaramanga, {fecha}", estilo_n),
        Spacer(1, 20),
        Paragraph(f"<b>Señores:</b><br/>{eps.upper()}", estilo_n),
        Spacer(1, 20),
        Paragraph(f"<b>ASUNTO:</b> {resumen}", estilo_n),
        Spacer(1, 20),
    ]

    for parrafo in clean.split('\n'):
        if parrafo.strip():
            elements.append(Paragraph(parrafo.strip(), estilo_n))
            elements.append(Spacer(1, 6))

    elements += [
        Spacer(1, 40),
        Paragraph("__________________________________________", estilo_n),
        Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n),
    ]

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
