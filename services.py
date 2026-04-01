import os
import io
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import pdfplumber
import PyPDF2
import httpx  # para llamar a Claude como fallback

from groq import AsyncGroq
from models import GlosaInput, GlosaResult

logger = logging.getLogger("motor_glosas_v2")

# ── Constantes de tiempo ──────────────────────────────────────────────────────
FERIADOS_CO = [
    "2025-01-01","2025-01-06","2025-03-24","2025-04-17","2025-04-18",
    "2025-05-01","2025-06-02","2025-06-23","2025-06-30","2025-07-20",
    "2025-08-07","2025-08-18","2025-10-13","2025-11-03","2025-11-17",
    "2025-12-08","2025-12-25",
    "2026-01-01","2026-01-12","2026-03-23","2026-04-02","2026-04-03",
    "2026-05-01","2026-05-18","2026-06-08","2026-06-15","2026-06-29",
    "2026-07-20","2026-08-07","2026-08-17","2026-10-12","2026-11-02",
    "2026-11-16","2026-12-08","2026-12-25",
]


# ── Helpers PDF ───────────────────────────────────────────────────────────────
def _procesar_pdf_sync(file_content: bytes) -> str:
    """Extrae texto del PDF priorizando las primeras y últimas páginas."""
    paginas = []
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text() or ""
                for table in page.extract_tables() or []:
                    for row in table:
                        txt += " | ".join(
                            [str(c).replace("\n", " ") if c else "" for c in row]
                        ) + "\n"
                paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")
    except Exception:
        reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        for i in range(len(reader.pages)):
            txt = reader.pages[i].extract_text() or ""
            paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")

    if not paginas:
        return ""

    # Estrategia inteligente: primeras 2 páginas (encabezado/paciente)
    # + últimas 2 (totales/firmas) en lugar de corte lineal ciego
    if len(paginas) <= 4:
        return "".join(paginas)

    inicio = "".join(paginas[:2])
    fin    = "".join(paginas[-2:])
    medio  = "".join(paginas[2:-2])

    # Presupuesto: 3000 chars inicio + 2000 fin + lo que quede del medio
    resultado = inicio[:3000] + "\n...[PÁGINAS INTERMEDIAS]...\n" + medio[:2000] + "\n...\n" + fin[:2000]
    return resultado


def calcular_dias_habiles(f_rad: str, f_rec: str) -> int:
    try:
        d1 = datetime.strptime(f_rad, "%Y-%m-%d")
        d2 = datetime.strptime(f_rec, "%Y-%m-%d")
        dias, current = 0, d1
        while current < d2:
            current += timedelta(days=1)
            if current.weekday() < 5 and current.strftime("%Y-%m-%d") not in FERIADOS_CO:
                dias += 1
        return dias
    except Exception:
        return 0


# ── Construcción del prompt ───────────────────────────────────────────────────
# Separar el prompt en secciones hace que el modelo mantenga el rol
# sin "olvidar" las instrucciones de formato al final del bloque.

SYSTEM_ROL = """Eres el Director Jurídico de la ESE Hospital Universitario de Santander (HUS).
Tu única función es redactar respuestas a glosas médicas con argumentos legales precisos.

IDENTIDAD ESTRICTA:
- Representas EXCLUSIVAMENTE a la ESE HUS como prestador de servicios de salud.
- Nunca defiendas a la EPS ni adoptes una postura neutral.
- Nunca inventes contratos, resoluciones, sentencias ni fechas que no estén en el contexto.
- Si un dato no está en el contexto, omítelo — no lo suplas con información genérica."""

SYSTEM_FORMATO = """FORMATO DE RESPUESTA — OBLIGATORIO:
Responde ÚNICAMENTE con XML válido. Cero texto, cero markdown, cero explicaciones fuera del XML.

<paciente>Nombre completo o NO IDENTIFICADO si no aparece</paciente>
<codigo_glosa>Código alfanumérico exacto de la glosa</codigo_glosa>
<valor_objetado>Monto con signo $ tal como aparece en el documento</valor_objetado>
<servicio_glosado>Nombre del servicio o procedimiento objetado</servicio_glosado>
<score_confianza>Número del 0 al 100 según estos criterios:
  - 90-100: datos completos, código claro, contrato vigente identificado
  - 70-89: datos suficientes pero algún campo inferido
  - 50-69: información parcial, PDF poco legible o código ambiguo
  - 0-49: datos insuficientes, no se puede construir defensa sólida
</score_confianza>
<argumento>
DEFENSA JURÍDICA EN MAYÚSCULAS. MÍNIMO DOS PÁRRAFOS:
PÁRRAFO 1: Contexto del caso (paciente, servicio, valor, contrato aplicable).
PÁRRAFO 2: Fundamento legal específico con normas vigentes.
PÁRRAFO 3 (si aplica): Jurisprudencia o precedente administrativo.
CIERRE: Exigencia explícita de levantamiento de la glosa.
</argumento>"""

# Estrategias legales por prefijo de código — separadas del prompt principal
# para facilitar mantenimiento sin tocar la lógica de IA
ESTRATEGIAS_LEGALES = {
    "TA_sin_contrato": (
        "ESTRATEGIA: Glosa tarifaria SIN CONTRATO VIGENTE.\n"
        "1. Declara que no existe contrato entre la ESE HUS y esta entidad.\n"
        "2. Aplica Art. 11 Decreto 4747/2007: sin contrato rige el manual tarifario oficial.\n"
        "3. Cita Resoluciones HUS 054 y 120 de 2026 que fijan SOAT PLENO (100%).\n"
        "4. La EPS no puede imponer descuentos unilaterales sin acuerdo (Art. 871 C.Co, buena fe)."
    ),
    "TA_con_contrato": (
        "ESTRATEGIA: Glosa tarifaria CON CONTRATO VIGENTE.\n"
        "1. El cobro corresponde exactamente a las tarifas pactadas en el contrato vigente.\n"
        "2. La EPS no puede desconocer lo que suscribió (Art. 871 C.Co).\n"
        "3. Cita Circular 030/2013 SUPERSALUD: EPS no puede objetar tarifas que ella misma pactó."
    ),
    "SO": (
        "ESTRATEGIA: Glosa por soportes documentales.\n"
        "1. La Historia Clínica es plena prueba según Resolución 1995/1999.\n"
        "2. Soportes subsanables no extinguen la obligación de pago (Art. 56 Ley 1438/2011).\n"
        "3. Si es urgencia vital: no requiere autorización previa (Art. 168 Ley 100/1993)."
    ),
    "AU": (
        "ESTRATEGIA: Glosa por autorización.\n"
        "1. Urgencia vital — atención obligatoria sin autorización previa (Art. 168 Ley 100/1993).\n"
        "2. La EPS tiene 5 días para objetar la urgencia (Res. 3047/2008), si no lo hizo, acepta.\n"
        "3. El trámite de autorización se realizó de manera oportuna según los registros."
    ),
    "CO": (
        "ESTRATEGIA: Glosa por cobertura.\n"
        "1. El servicio es obligación legal de la EPS (Ley 1751/2015 Art. 15).\n"
        "2. Atención de urgencias: Art. 168 Ley 100/1993 y Art. 32 Ley 1438/2011.\n"
        "3. Si la EPS alega exclusión, debe demostrarlo — la carga probatoria es suya."
    ),
    "PE": (
        "ESTRATEGIA: Glosa por pertinencia clínica.\n"
        "1. Autonomía médica protegida: Ley 1751/2015 Art. 17.\n"
        "2. Sentencia T-760/2008: prevalece el criterio médico sobre el administrativo.\n"
        "3. La EPS debe especificar el criterio técnico-científico usado para objetar (Res. 3047/2008)."
    ),
    "FA": (
        "ESTRATEGIA: Glosa por facturación.\n"
        "1. Errores subsanables no son causal de no pago (Circular 030/2013 SUPERSALUD).\n"
        "2. Principio de realidad sobre formalidad: el servicio fue prestado.\n"
        "3. La obligación de pago subsiste independientemente del error formal."
    ),
    "DEFAULT": (
        "ESTRATEGIA: Glosa de tipo no especificado.\n"
        "1. Defender la prestación del servicio con base en la Historia Clínica.\n"
        "2. Invocar el principio de continuidad de la atención (Art. 32 Ley 1438/2011).\n"
        "3. Exigir que la EPS especifique el fundamento técnico-legal de la objeción."
    ),
}


def _construir_prompt(
    info_contrato: str,
    estrategia: str,
    texto_glosa: str,
    contexto_pdf: str,
    eps: str,
) -> tuple[str, str]:
    """
    Retorna (system_prompt, user_prompt) separados.
    Separar system/user mejora el seguimiento de instrucciones
    en modelos que distinguen estos roles.
    """
    system = "\n\n".join([
        SYSTEM_ROL,
        f"MARCO CONTRACTUAL VIGENTE CON {eps.upper()}:\n{info_contrato}",
        f"INSTRUCCIÓN ESTRATÉGICA:\n{estrategia}",
        SYSTEM_FORMATO,
    ])

    user = (
        f"DATOS DE LA GLOSA A CONTESTAR:\n{texto_glosa}\n\n"
        f"CONTEXTO EXTRAÍDO DE LOS SOPORTES PDF:\n{contexto_pdf or 'Sin soportes adjuntos.'}"
    )

    return system, user


# ── Cliente IA con fallback ───────────────────────────────────────────────────
class GlosaService:
    def __init__(self, groq_api_key: str):
        self.groq = AsyncGroq(api_key=groq_api_key) if groq_api_key else None
        # Claude como fallback — lee la key de env, no la recibe como parámetro
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def extraer_pdf(self, file_content: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _procesar_pdf_sync, file_content)

    def _xml(self, tag: str, texto: str, default: str = "") -> str:
        m = re.search(fr"<{tag}>(.*?)</{tag}>", texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip().replace("**", "") if m else default

    async def _llamar_groq(self, system: str, user: str) -> str:
        """Llama a Groq/Llama. Lanza excepción si falla para activar fallback."""
        if not self.groq:
            raise ValueError("GROQ_API_KEY no configurada")

        resp = await self.groq.chat.completions.create(
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.15,       # más bajo = menos alucinaciones
            max_tokens=1500,
            # Forzar que la respuesta sea XML válido
            response_format={"type": "text"},
        )
        contenido = resp.choices[0].message.content or ""

        # Validación básica: si no tiene tags XML, rechazar
        if "<argumento>" not in contenido:
            raise ValueError(f"Respuesta sin XML válido: {contenido[:200]}")

        return contenido

    async def _llamar_claude(self, system: str, user: str) -> str:
        """
        Fallback a Claude claude-sonnet-4-20250514 vía API REST directa.
        Se usa solo si Groq falla o está caído.
        """
        if not self.anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY no configurada para fallback")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1500,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            contenido = data["content"][0]["text"]

            if "<argumento>" not in contenido:
                raise ValueError(f"Claude: respuesta sin XML válido: {contenido[:200]}")

            return contenido

    async def _llamar_ia(self, system: str, user: str) -> tuple[str, str]:
        """
        Orquesta Groq → Claude → error controlado.
        Retorna (xml_respuesta, modelo_usado).
        """
        # Intento 1: Groq (más rápido, gratuito)
        try:
            resultado = await self._llamar_groq(system, user)
            logger.info("IA: respuesta obtenida de Groq")
            return resultado, "groq/llama-3.3-70b"
        except Exception as e_groq:
            logger.warning(f"Groq falló ({type(e_groq).__name__}: {e_groq}), intentando Claude...")

        # Intento 2: Claude como fallback
        try:
            resultado = await self._llamar_claude(system, user)
            logger.info("IA: respuesta obtenida de Claude (fallback)")
            return resultado, "anthropic/claude-sonnet-4"
        except Exception as e_claude:
            logger.error(f"Claude también falló: {e_claude}")

        # Si ambos fallan: respuesta de error estructurada (no rompe el flujo)
        fallback_xml = (
            "<paciente>NO IDENTIFICADO</paciente>"
            "<codigo_glosa>N/A</codigo_glosa>"
            "<valor_objetado>$ 0.00</valor_objetado>"
            "<servicio_glosado>ERROR — REVISAR MANUALMENTE</servicio_glosado>"
            "<score_confianza>0</score_confianza>"
            "<argumento>ERROR DE CONEXIÓN CON LOS SERVICIOS DE IA. "
            "ESTA GLOSA REQUIERE REVISIÓN MANUAL POR EL AUDITOR. "
            "LOS SERVICIOS DE IA NO ESTÁN DISPONIBLES EN ESTE MOMENTO.</argumento>"
        )
        return fallback_xml, "fallback/manual"

    async def analizar(
        self,
        data: GlosaInput,
        contexto_pdf: str = "",
        contratos_db: dict = None,
    ) -> GlosaResult:
        etapa_str    = str(data.etapa).upper()
        texto_base   = str(data.tabla_excel).strip().upper()
        val_ac_num   = float(re.sub(r"[^\d]", "", str(data.valor_aceptado)) or 0)

        # Extracción de código de glosa — más robusta que antes
        codigo_det = self._extraer_codigo_glosa(texto_base)
        prefijo    = codigo_det[:2] if codigo_det != "N/A" else "XX"

        val_m      = re.search(r"\$\s*([\d\.,]+)", texto_base)
        valor_raw  = f"$ {val_m.group(1)}" if val_m else "$ 0.00"

        dias             = calcular_dias_habiles(data.fecha_radicacion, data.fecha_recepcion) \
                           if data.fecha_radicacion and data.fecha_recepcion else 0
        es_extemporanea  = dias > 20
        msg_tiempo       = f"EXTEMPORÁNEA ({dias} DÍAS)" if es_extemporanea \
                           else f"EN TÉRMINOS ({dias} DÍAS)"

        # ── Casos sin IA (reglas puras) ────────────────────────────────────────
        if "RATIF" in etapa_str:
            return self._respuesta_ratificacion(codigo_det, valor_raw, msg_tiempo, dias)

        if es_extemporanea and val_ac_num <= 0:
            return self._respuesta_extemporanea(codigo_det, valor_raw, msg_tiempo, dias)

        # ── Caso IA ────────────────────────────────────────────────────────────
        eps_key     = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        todos_contratos = {**_CONTRATOS_BASE, **(contratos_db or {})}
        info_contrato   = todos_contratos.get(eps_key, todos_contratos["OTRA / SIN DEFINIR"])
        es_sin_contrato = eps_key in ("OTRA", "")

        estrategia = self._seleccionar_estrategia(prefijo, es_sin_contrato)
        system, user = _construir_prompt(info_contrato, estrategia, texto_base, contexto_pdf, eps_key)

        res_ia, modelo_usado = await self._llamar_ia(system, user)

        # Parseo de campos con defaults seguros
        paciente  = self._xml("paciente",        res_ia, "NO IDENTIFICADO")
        servicio  = self._xml("servicio_glosado", res_ia, "SERVICIOS ASISTENCIALES")
        arg       = self._xml("argumento",        res_ia, "SIN ARGUMENTO").replace("\n", "<br/>")
        score_raw = self._xml("score_confianza",  res_ia, "0")

        # Score dinámico: penalizar si algún campo quedó vacío o en default
        try:
            score = int(re.sub(r"[^\d]", "", score_raw) or 0)
        except ValueError:
            score = 0

        if paciente == "NO IDENTIFICADO":  score = max(0, score - 15)
        if not contexto_pdf:               score = max(0, score - 10)
        if modelo_usado.startswith("fallback"): score = 0

        # Tag de modelo usado (ayuda al auditor a saber qué IA respondió)
        nota_modelo = f'<div style="font-size:9px;color:#94a3b8;margin-top:8px;">Generado por: {modelo_usado}</div>'

        dictamen = (
            _tabla_defensa(codigo_det, servicio, valor_raw, "RE9602",
                           "GLOSA O DEVOLUCIÓN INJUSTIFICADA")
            + _div(f"<b>ESE HUS NO ACEPTA GLOSA INJUSTIFICADA:</b><br/><br/>{arg}")
            + nota_modelo
        )

        return GlosaResult(
            tipo=f"TÉCNICO-LEGAL [{prefijo}]",
            resumen=f"DEFENSA: {paciente}",
            dictamen=dictamen,
            codigo_glosa=codigo_det,
            valor_objetado=valor_raw,
            paciente=paciente,
            mensaje_tiempo=msg_tiempo,
            color_tiempo="bg-emerald-500",
            score=score,
            dias_restantes=max(0, 20 - dias),
        )

    def _extraer_codigo_glosa(self, texto: str) -> str:
        """
        Jerarquía de extracción: patrones específicos primero,
        regex genérico como último recurso.
        """
        patrones_conocidos = [
            r"\b(TA\d{2,4})\b",   # Tarifas
            r"\b(SO\d{2,4})\b",   # Soportes
            r"\b(AU\d{2,4})\b",   # Autorización
            r"\b(CO\d{2,4})\b",   # Cobertura
            r"\b(PE\d{2,4})\b",   # Pertinencia
            r"\b(FA\d{2,4})\b",   # Facturación
            r"\b(MCV\d*)\b",      # Código especial HUS
        ]
        for patron in patrones_conocidos:
            m = re.search(patron, texto)
            if m:
                return m.group(1)

        # Fallback genérico
        m = re.search(r"\b([A-Z]{2,3}\d{2,4})\b", texto)
        return m.group(1) if m else "N/A"

    def _seleccionar_estrategia(self, prefijo: str, es_sin_contrato: bool) -> str:
        if prefijo == "TA":
            return ESTRATEGIAS_LEGALES["TA_sin_contrato" if es_sin_contrato else "TA_con_contrato"]
        return ESTRATEGIAS_LEGALES.get(prefijo, ESTRATEGIAS_LEGALES["DEFAULT"])

    # ── Respuestas de reglas puras (sin IA) ────────────────────────────────────
    def _respuesta_ratificacion(self, codigo, valor, msg_tiempo, dias):
        txt = (
            "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE "
            "DE LA GLOSA INICIAL Y CONTINUACIÓN DEL PROCESO DE ACUERDO CON LA NORMA. "
            "SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE LA CONCILIACIÓN DE LA AUDITORÍA "
            "MÉDICA Y/O TÉCNICA ENTRE LAS PARTES. CONTACTO: CARTERA@HUS.GOV.CO, "
            "GLOSASYDEVOLUCIONES@HUS.GOV.CO. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA "
            "LEY 1438 DE 2011, DE NO OBTENERSE LA RATIFICACIÓN EN LOS TÉRMINOS ESTABLECIDOS, "
            "SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN."
        )
        tabla = _tabla_simple(codigo, "RATIFICACIÓN", valor, "RE9901",
                              "GLOSA NO ACEPTADA Y SUBSANADA EN SU TOTALIDAD",
                              color_e="#2563eb")
        return GlosaResult(
            tipo="LEGAL - RATIFICADA", resumen="RECHAZO RATIFICACIÓN",
            dictamen=tabla + _div(txt), codigo_glosa=codigo,
            valor_objetado=valor, paciente="N/A",
            mensaje_tiempo=msg_tiempo, color_tiempo="bg-blue-600",
            score=100, dias_restantes=max(0, 20 - dias),
        )

    def _respuesta_extemporanea(self, codigo, valor, msg_tiempo, dias):
        txt = (
            f"ESE HUS NO ACEPTA GLOSA EXTEMPORÁNEA. AL HABERSE SUPERADO DICHO PLAZO LEGAL "
            f"(HAN TRANSCURRIDO {dias} DÍAS HÁBILES ENTRE LA RADICACIÓN Y LA RECEPCIÓN) SIN "
            "QUE NUESTRA INSTITUCIÓN RECIBIERA NOTIFICACIÓN FORMAL DE LAS OBJECIONES DENTRO "
            "DEL TÉRMINO ESTABLECIDO, HA OPERADO DE PLENO DERECHO EL FENÓMENO JURÍDICO DE LA "
            "ACEPTACIÓN TÁCITA DE LA FACTURA. EN CONSECUENCIA, HA PRECLUIDO DEFINITIVAMENTE "
            "LA OPORTUNIDAD LEGAL DE LA EPS PARA AUDITAR, GLOSAR O RETENER LOS RECURSOS "
            "ASOCIADOS A ESTA CUENTA, DE CONFORMIDAD CON LO DISPUESTO EN EL ARTÍCULO 57 DE "
            "LA LEY 1438 DE 2011 Y EL ARTÍCULO 13 (LITERAL D) DE LA LEY 1122 DE 2007."
        )
        tabla = _tabla_simple(codigo, "EXTEMPORÁNEA", valor, "RE9502",
                              "GLOSA O DEVOLUCIÓN EXTEMPORÁNEA")
        return GlosaResult(
            tipo="LEGAL - EXTEMPORÁNEA", resumen="RECHAZO EXTEMPORANEIDAD",
            dictamen=tabla + _div(txt), codigo_glosa=codigo,
            valor_objetado=valor, paciente="N/A",
            mensaje_tiempo=msg_tiempo, color_tiempo="bg-red-600",
            score=100, dias_restantes=0,
        )
