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
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip().replace("**", "").replace("*", "")
            return val if val else default
        return default

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        if contratos_db is None:
            contratos_db = {}

        eps_segura = str(data.eps).upper() if data.eps else "OTRA / SIN DEFINIR"
        info_c = contratos_db.get(
            "OTRA / SIN DEFINIR",
            "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO. SE EXIGE EL PAGO AL 100% DE LA TARIFA VIGENTE."
        )
        for k, v in contratos_db.items():
            if k in eps_segura:
                info_c = v
                break

        texto_base    = str(data.tabla_excel).strip()
        val_ac_num    = self.convertir_numero(data.valor_aceptado)
        is_ratificada = str(data.etapa).strip().upper() == "RATIFICADA"

        cod_m = re.search(r'\b([A-Z]{2,3}\d{3,4})\b', texto_base)
        codigo_detectado = cod_m.group(1) if cod_m else texto_base.split()[0][:10].upper() if texto_base else "N/A"
        prefijo = codigo_detectado[:2].upper() if codigo_detectado != "N/A" else "XX"

        val_m = re.search(r'\$\s*([\d\.,]+)', texto_base)
        valor_obj_raw = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        msg_tiempo, color_tiempo, es_extemporanea, dias = "Fechas no ingresadas", "bg-slate-500", False, 0
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
            except Exception: pass

        # ── A) GLOSA RATIFICADA ──
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
            return GlosaResult(tipo="LEGAL - RATIFICACIÓN", resumen="RECHAZO DE RATIFICACIÓN", dictamen=tabla + _div(texto), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600")

        # ── B) GLOSA EXTEMPORÁNEA ──
        if es_extemporanea and val_ac_num == 0:
            tabla = _tabla_simple(codigo_detectado, f"EXTEMPORÁNEA ({dias} DÍAS)", valor_obj_raw, "RE9502", "ACEPTACIÓN TÁCITA", color_estado="#b91c1c")
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
            return GlosaResult(tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO POR EXTEMPORANEIDAD", dictamen=tabla + _div(texto), codigo_glosa=codigo_detectado, valor_objetado=valor_obj_raw, paciente="N/A", mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)

        # ── CEREBRO ADAPTATIVO POR CAUSAL ──
        if val_ac_num > 0:
            valor_acep_fmt = f"${val_ac_num:,.0f}".replace(",", ".")
            estrategia = f"CASO ACEPTACIÓN: La ESE HUS acepta la glosa por valor de {valor_acep_fmt}. En <argumento> redacta máximo 3 líneas explicando el motivo de forma formal. Sin leyes, sin viñetas, en MAYÚSCULAS."
        
        elif prefijo == "TA":
            estrategia = f"""DEFENSA TARIFARIA (MAYOR VALOR / TARIFAS):
1. PROHIBIDO USAR "VALOR FACTURADO". USA "VALOR OBJETADO".
2. Busca en los soportes nombre del médico, fecha y folio. ÚSALOS SOLO SI ESTÁN CLAROS. ¡CERO INVENTOS!
3. Invoca el contrato {info_c}. La EPS incurre en glosa temeraria al desconocer el acuerdo.
4. Si detectas lateralidad (bilateral) o varios tiempos, ataca ese punto justificando la liquidación.
5. Cita el Art. 871 del Código de Comercio (Buena Fe)."""

        # 🔥 LA CURA DEFINITIVA PARA EL CÓDIGO "SO" (BIFURCACIÓN INTELIGENTE) 🔥
        elif prefijo == "SO":
            estrategia = """DEFENSA DE SOPORTES (CLÍNICOS O DE INSUMOS):
1. PROHIBIDO USAR "VALOR FACTURADO". USA "VALOR OBJETADO".
2. IDENTIFICA QUÉ TIPO DE SOPORTE ESTÁ RECLAMANDO LA EPS EN EL MOTIVO DE LA GLOSA Y APLICA SOLO UNA DE ESTAS DOS DEFENSAS:
   - CASO A (Falta Documento Clínico): Si la EPS objeta que falta una lectura de imagenología/patología, resultado, epicrisis o descripción quirúrgica, LOCALIZA esa información en los anexos. Nombra la fecha, el médico (con RM) y el hallazgo. Argumenta que el documento SÍ ESTÁ en el expediente, desvirtuando la objeción por completo. PROHIBIDO hablar de facturas de compra o proveedores en este caso.
   - CASO B (Falta Factura de Insumo/Medicamento): Si la EPS objeta un insumo o medicamento por falta de soporte de compra, exige el pago en virtud del Anexo 5 Res. 3047/2008 (Costo de adquisición + administración) amparado en la factura del proveedor.
3. ARGUMENTO NORMATIVO BASE: La historia clínica y sus anexos son el soporte probatorio asistencial pleno (Res. 1995/1999). La realidad fáctica documental obliga al levantamiento de la glosa."""

        elif prefijo == "FA":
            estrategia = """DEFENSA DE FACTURACIÓN Y CONCURRENCIA:
1. PROHIBIDO USAR "VALOR FACTURADO". USA "VALOR OBJETADO".
2. Demuestra que el VALOR OBJETADO corresponde a un acto en salud AUTÓNOMO, no incluido en estancias o paquetes.
3. Cita el Anexo Técnico N.° 3 Res. 3047/2008 exigiendo a la EPS revelar la norma puntual de inclusión."""
        elif prefijo in ["CO", "CL", "PE"]:
            estrategia = """DEFENSA TÉCNICO-CIENTÍFICA (PERTINENCIA/COBERTURA):
1. PROHIBIDO USAR "VALOR FACTURADO". USA "VALOR OBJETADO".
2. Extrae diagnósticos y justificación clínica. SI NO HAY NOMBRES DE MÉDICOS, NO LOS INVENTES, di "el especialista tratante".
3. Defiende el JUICIO MÉDICO. El auditor administrativo no puede glosar desconociendo la necesidad vital. Invoca Ley 1751 de 2015."""
        else:
            estrategia = f"DEFENSA CONTRACTUAL INTEGRAL: PROHIBIDO DECIR 'VALOR FACTURADO', USA 'VALOR OBJETADO'. Fundamenta en el cumplimiento del contrato ({info_c}) basándote ÚNICAMENTE en datos reales del expediente."

        system_prompt = f"""Eres el DIRECTOR NACIONAL DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS de la ESE HUS. Eres estricto, técnico y 100% APEGADO A LA VERDAD.

REGLAS DE ORO — NUNCA LAS INCUMPLAS:
1. TODO EN MAYÚSCULAS.
2. CERO ALUCINACIONES: DEBES basar tu defensa SOLO en la información real. Busca nombres de médicos, RM, fechas y folios. SI NO EXISTEN, TIENES ESTRICTAMENTE PROHIBIDO INVENTAR DATOS. Limítate a decir "el profesional tratante", "la fecha de atención" o "el expediente clínico".
3. NO USES LA FRASE "VALOR FACTURADO". REEMPLÁZALO SIEMPRE POR "VALOR OBJETADO".
4. Usa jerga superior: "Sinalagma contractual", "Carga probatoria", "Realidad fáctica documental".
5. APLICA EXACTAMENTE ESTA ESTRATEGIA ENFOCADA: {estrategia}
6. No escribas introducciones. Ve directo a la defensa dentro de la etiqueta <argumento>.
7. RESPONDE ÚNICAMENTE con el bloque XML pedido."""

        user_prompt = f"""EPS: {eps_segura}
CONTRATO VIGENTE: {info_c}
GLOSA RECIBIDA: "{texto_base}"
SOPORTES CLÍNICOS DEL EXPEDIENTE (SOLO USA DATOS QUE PUEDAS LEER AQUÍ, NO INVENTES NADA):
{contexto_pdf[:12000]}

RESPONDE ÚNICAMENTE CON ESTE FORMATO XML EXACTO:
<paciente>Nombre completo o N/A</paciente>
<codigo_glosa>Código de objeción</codigo_glosa>
<valor_objetado>Valor en pesos o N/A</valor_objetado>
<servicio_glosado>Nombre del servicio</servicio_glosado>
<motivo_resumido>Máximo 6 palabras: argumento de EPS</motivo_resumido>
<argumento>Tu texto de defensa en MAYÚSCULAS.</argumento>"""

        # ── Llamada a Groq con modelo rápido y backoff inteligente ───────────
        res_ia = ""
        for intento in range(3):
            try:
                completion = await self.cliente.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt}
                    ],
                    # 🔥 CAMBIO CRÍTICO: Usamos el modelo 8b. Es rapidísimo y no bloquea tanto.
                    model="llama3-8b-8192", 
                    temperature=0.15,
                    max_tokens=1500, # Ahorramos tokens
                )
                res_ia = completion.choices[0].message.content
                break
            except Exception as e:
                logger.error(f"Intento {intento + 1} falló al contactar Groq: {e}", exc_info=True)
                if intento == 2:
                    return GlosaResult(
                        tipo="Error", resumen="Error de Conexión IA",
                        dictamen="Límite de velocidad de Groq superado (Error 429). Por favor, espera 60 segundos y vuelve a intentarlo.",
                        codigo_glosa="N/A", valor_objetado="0",
                        paciente="N/A", mensaje_tiempo="", color_tiempo=""
                    )
                # 🔥 CAMBIO CRÍTICO: Si Groq nos bloquea, esperamos 10 segundos antes de reintentar
                await asyncio.sleep(10 * (intento + 1))

        paciente      = self.xml("paciente", res_ia, "NO IDENTIFICADO")
        codigo_xml    = self.xml("codigo_glosa", res_ia, codigo_detectado)
        valor_xml     = self.xml("valor_objetado", res_ia, valor_obj_raw)
        servicio      = self.xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        motivo        = self.xml("motivo_resumido", res_ia, "OBJECIÓN DE LA EPS").upper()
        argumento_ia  = self.xml("argumento", res_ia, "SE RECHAZA LA GLOSA EN CUMPLIMIENTO DEL CONTRATO.")

        codigo_final = codigo_xml if (codigo_xml != "N/A" and re.match(r'[A-Z]{2,3}\d{3,4}', codigo_xml)) else codigo_detectado
        argumento_ia  = re.sub(r'[ \t]+', ' ', argumento_ia).strip()

        if val_ac_num > 0:
            val_obj_num = self.convertir_numero(valor_xml)
            valor_acep_fmt = f"$ {val_ac_num:,.0f}".replace(",", ".")
            apertura = f"ESE HUS ACEPTA LA GLOSA {codigo_final} POR UN VALOR DE {valor_acep_fmt}. "
            cod_res  = "RE9702" if val_ac_num >= val_obj_num and val_obj_num > 0 else "RE9801"
            desc_res = "GLOSA ACEPTADA TOTALMENTE" if cod_res == "RE9702" else "GLOSA PARCIALMENTE ACEPTADA"
            tabla_html = _tabla_aceptacion(codigo_final, valor_xml, valor_acep_fmt, cod_res, desc_res)
            tipo_final, resumen_final = "AUDITORÍA - ACEPTACIÓN", f"ACEPTACIÓN DE GLOSA – {paciente}"
        else:
            apertura = f"ESE HUS NO ACEPTA LA GLOSA {codigo_final} INTERPUESTA POR {motivo}, Y SUSTENTA SU POSICIÓN EN LOS SIGUIENTES ARGUMENTOS TÉCNICOS, CONTRACTUALES Y NORMATIVOS: "
            cod_res  = "RE9206" if (prefijo == "TA" and ("OTRA" in eps_segura or "SIN DEFINIR" in eps_segura)) else "RE9901"
            desc_res = "GLOSA INJUSTIFICADA 100%" if cod_res == "RE9206" else "GLOSA NO ACEPTADA"
            tabla_html = _tabla_defensa(codigo_final, servicio, valor_xml, cod_res, desc_res)
            tipo_final, resumen_final = "TÉCNICO-LEGAL", f"DEFENSA FACTURA – {paciente}"

        if re.search(r'^ESE HUS (NO |)ACEPTA', argumento_ia.strip(), re.IGNORECASE):
            dictamen_texto = argumento_ia
        else:
            dictamen_texto = apertura + "\n\n" + argumento_ia

        dictamen_html = dictamen_texto.replace('\n', '<br/>')

        return GlosaResult(tipo=tipo_final, resumen=resumen_final, dictamen=tabla_html + f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{dictamen_html}</div>', codigo_glosa=codigo_final, valor_objetado=valor_xml, paciente=paciente, mensaje_tiempo=msg_tiempo, color_tiempo=color_tiempo)


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES DE TABLAS HTML Y PDF
# ─────────────────────────────────────────────────────────────────────────────
def _div(texto: str) -> str: return f'<div style="text-align:justify;line-height:1.8;font-size:11px;">{texto}</div>'
def _tabla_simple(codigo, estado, valor, cod_res, desc_res, color_header="#1e3a8a", color_estado=None):
    e_estado = f'background-color:{color_estado};color:white;' if color_estado else ''
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:{color_header};color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">ESTADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;{e_estado}"><b>{estado}</b></td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'
def _tabla_defensa(codigo, servicio, valor, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">SERVICIO RECLAMADO</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJ.</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;">{servicio}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'
def _tabla_aceptacion(codigo, valor_obj, valor_acep, cod_res, desc_res):
    return f'<table border="1" style="width:100%;border-collapse:collapse;text-transform:uppercase;font-size:11px;margin-bottom:15px;"><tr style="background-color:#1e3a8a;color:white;"><th style="padding:8px;border:1px solid #cbd5e1;">CÓDIGO GLOSA</th><th style="padding:8px;border:1px solid #cbd5e1;">VALOR OBJETADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#d97706;">VALOR ACEPTADO</th><th style="padding:8px;border:1px solid #cbd5e1;background-color:#10b981;">CONCEPTO</th></tr><tr><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{codigo}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;">{valor_obj}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;color:#d97706;">{valor_acep}</td><td style="padding:8px;border:1px solid #cbd5e1;text-align:center;font-weight:bold;">{cod_res}<br><span style="font-size:9px;">{desc_res}</span></td></tr></table>'

def crear_oficio_pdf(eps: str, resumen: str, conclusion: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    estilos = getSampleStyleSheet()
    estilo_n = ParagraphStyle('n', parent=estilos['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=16)
    estilo_titulo = ParagraphStyle('titulo', parent=estilos['Heading1'], alignment=1, fontSize=14, spaceAfter=20)
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
        elements.extend([img, Spacer(1, 15)])
    elements.extend([
        Paragraph("<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>", estilo_titulo),
        Paragraph("<b>OFICINA DE AUDITORÍA Y JURÍDICA DE CUENTAS MÉDICAS</b>", ParagraphStyle('sub', alignment=1, fontSize=12)),
        Spacer(1, 30), Paragraph(f"Bucaramanga, {fecha}", estilo_n), Spacer(1, 20),
        Paragraph(f"<b>Señores:</b><br/>{eps.upper()}", estilo_n), Spacer(1, 20),
        Paragraph(f"<b>ASUNTO:</b> {resumen}", estilo_n), Spacer(1, 20),
    ])
    for parrafo in clean.split('\n'):
        if parrafo.strip(): elements.extend([Paragraph(parrafo.strip(), estilo_n), Spacer(1, 6)])
    elements.extend([Spacer(1, 40), Paragraph("__________________________________________", estilo_n), Paragraph("<b>DEPARTAMENTO DE AUDITORÍA</b><br/>ESE HOSPITAL UNIVERSITARIO DE SANTANDER", estilo_n)])
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
