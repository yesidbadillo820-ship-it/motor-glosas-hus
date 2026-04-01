import os
import io
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from groq import AsyncGroq
from models.schemas import GlosaInput, GlosaResult

logger = logging.getLogger("motor_glosas_v2")

# ── 1. CALENDARIO OFICIAL DE FERIADOS COLOMBIA (2025-2026) ──
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

# ── 2. MARCO CONTRACTUAL INTEGRAL (14 ENTIDADES ESE HUS) ──
_CONTRATOS_BASE = {
    "NUEVA EPS": "CONTRATO 440-DIGSA/DMBUG-2025. TARIFA: SOAT SMLV -20% E INSTITUCIONALES.",
    "SALUD TOTAL": "ACUERDO 120-2024. TARIFA: ISS + 15% SOBRE MANUAL VIGENTE.",
    "COOSALUD": "CONTRATO CAPITACIÓN 2025. INSUMOS INCLUIDOS EN TARIFA GLOBAL.",
    "ASMET SALUD": "CONTRATO EVENTO 2025. TARIFA: SOAT PLENO PARA URGENCIAS Y EVENTO PACTADO.",
    "COMPENSAR": "ACUERDO MARCO 2025. TARIFA: ISS + 10% SEGÚN PORTAFOLIO DE SERVICIOS HUS.",
    "SURA": "CONTRATO PREPAGADA Y POS 2025. TARIFA: MANUAL PROPIO EPS + 5% EN ALTA COMPLEJIDAD.",
    "FAMISANAR": "CONTRATO SUBSIDIADO 2025. TARIFA: SOAT -10%. REVISAR ANEXO DE INSUMOS.",
    "MUTUAL SER": "CONTRATO EVENTO 2025. TARIFA: SOAT PLENO. NO SE ACEPTAN DESCUENTOS SIN SOPORTE.",
    "PIJAOS SALUD": "RÉGIMEN INDÍGENA 2025. TARIFA: SOAT PLENO. RESPETAR USOS Y COSTUMBRES EN SALUD.",
    "AIC": "ASOCIACIÓN INDÍGENA DEL CAUCA. TARIFA: SOAT PLENO. ATENCIÓN INTEGRAL PRIORIZADA.",
    "MALLAMAS": "CONTRATO EVENTO 2025. TARIFA: SOAT PLENO. SIN DESCUENTO POR PRONTO PAGO.",
    "SAVIA SALUD": "CONTRATO DE RED 2025. TARIFA: SOAT -15% SEGÚN DECRETO DE INTERVENCIÓN.",
    "ECOOPSOS": "CONTRATO EVENTO 2025. TARIFA: SOAT PLENO. PAGO SEGÚN RADICACIÓN EFECTIVA.",
    "EMSSANAR": "CONTRATO 2025. TARIFA: SOAT PLENO PARA ATENCIÓN DE ALTA COMPLEJIDAD.",
    "OTRA / SIN DEFINIR": "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO (RESOLUCIÓN 054 Y 120 DE 2026)."
}

# ── 3. ESTRATEGIAS TÉCNICO-LEGALES (ANEXO 5 RES. 3047) ──
ESTRATEGIAS_HUS = {
    "TA": "RECHAZO POR TARIFA. El cobro cumple el contrato o el manual SOAT pleno. La EPS no puede aplicar descuentos unilaterales.",
    "SO": "SOPORTES SUFICIENTES. La Historia Clínica es plena prueba (Res. 1995/1999). El servicio se prestó y los anexos cumplen la norma.",
    "AU": "AUTORIZACIÓN NO REQUERIDA. Urgencia vital o atención prioritaria amparada por la Ley 100 y Ley 1438. No requiere autorización previa.",
    "CO": "COBERTURA LEGAL. El servicio es obligación de la EPS bajo Ley 1751/2015. No se aceptan exclusiones sin sustento técnico.",
    "PE": "PERTINENCIA CLÍNICA. Autonomía médica protegida por Ley 1751/2015 Art. 17. Prevalece el criterio del médico tratante del HUS.",
    "FA": "FACTURACIÓN CORRECTA. Errores formales son subsanables (Circular 030/2013). La prestación del servicio genera obligación de pago.",
    "SE": "OBJECIÓN INDETERMINADA. La EPS glosa sin especificar el servicio. Se exige pago por violación al debido proceso.",
    "DEFAULT": "RECHAZO TOTAL. La glosa carece de fundamento técnico-legal. Exigir pago por servicio efectivamente prestado."
}

class GlosaService:
    def __init__(self, groq_api_key: str):
        self.groq = AsyncGroq(api_key=groq_api_key) if groq_api_key else None
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        texto_base = str(data.tabla_excel).strip().upper()
        codigo_det = self._extraer_codigo_glosa(texto_base)
        prefijo    = codigo_det[:2] if codigo_det != "N/A" else "SE"
        valor_raw  = self._extraer_valor(texto_base)
        
        # ── Lógica de Tiempos y Extemporaneidad ──
        dias = self._calcular_dias_habiles(str(data.fecha_radicacion), str(data.fecha_recepcion))
        es_extemporanea = dias > 20

        # ── DETERMINACIÓN DEL CÓDIGO LEGAL (NORMATIVA REAL) ──
        if es_extemporanea:
            cod_res, desc_res = "RE9502", "LA GLOSA NO PROCEDE POR HABER SIDO GENERADA FUERA DE LOS TÉRMINOS"
        elif "RATIF" in str(data.etapa).upper():
            cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA Y SUBSANADA EN SU TOTALIDAD"
        else:
            # Diferenciar Glosa de Devolución
            if any(x in texto_base for x in ["DEVOLUCION", "DEVOL", "DEV."]):
                cod_res, desc_res = "RE9601", "EVIDENCIA QUE DEMUESTRA QUE LA DEVOLUCIÓN ES INJUSTIFICADA AL 100%"
            else:
                cod_res, desc_res = "RE9602", "EVIDENCIA QUE DEMUESTRA QUE LA GLOSA ES INJUSTIFICADA AL 100%"

        # ── Contexto de Contratos (14 Entidades) ──
        eps_key = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        todos_contratos = {**_CONTRATOS_BASE, **(contratos_db or {})}
        info_contrato = todos_contratos.get(eps_key, todos_contratos["OTRA / SIN DEFINIR"])
        
        # ── Prompt Jurídico Blindado ──
        estrategia = ESTRATEGIAS_HUS.get(prefijo, ESTRATEGIAS_HUS["DEFAULT"])
        system_prompt = f"""Eres el Director Jurídico de la ESE Hospital Universitario de Santander (HUS).
Tu ÚNICA MISIÓN es defender el cobro de la factura y rechazar la glosa/devolución de la EPS.

CÓDIGO NORMATIVO DE RESPUESTA: {cod_res} - {desc_res}
MARCO CONTRACTUAL APLICABLE: {info_contrato}
ESTRATEGIA TÉCNICA: {estrategia}

REGLAS DE ORO:
1. NUNCA aceptes la glosa. Tu tono es imperativo, legalista y combativo.
2. Si es por 'insumos no facturables', responde que son inherentes al acto médico y la EPS no ha probado su exclusión contractual.
3. Cita la Ley Estatutaria de Salud (1751/2015) y el Artículo 871 del Código de Comercio (Buena fe).
4. Responde EXCLUSIVAMENTE en XML con los tags: <paciente>...</paciente><argumento>...</argumento>"""

        res_ia, modelo_usado = await self._llamar_ia(system_prompt, f"DETALLE DE LA GLOSA EPS:\n{texto_base}\n\nSOPORTES PDF:\n{contexto_pdf[:3500]}")

        # Parseo de resultados
        pac_ia = self._xml("paciente", res_ia, "NO IDENTIFICADO")
        arg_ia = self._xml("argumento", res_ia, res_ia).replace("\n", "<br/>")

        # Visualización HTML
        dictamen = self._generar_tabla_html(codigo_det, valor_raw, cod_res, desc_res) + \
                   f'<div style="text-align:justify;font-size:11px;margin-top:10px;color:#1e293b;"><b>ARGUMENTACIÓN JURÍDICA ESE HUS:</b><br/><br/>{arg_ia}</div>'

        return GlosaResult(
            tipo=f"RESPUESTA {cod_res}", resumen=f"DEFENSA: {pac_ia}",
            dictamen=dictamen, codigo_glosa=codigo_det, valor_objetado=valor_raw,
            paciente=pac_ia, mensaje_tiempo="EXTEMPORÁNEA" if es_extemporanea else "EN TÉRMINOS",
            color_tiempo="bg-red-600" if es_extemporanea else "bg-emerald-600",
            score=95, dias_restantes=max(0, 20 - dias), modelo_ia=modelo_usado
        )

    # ── MÉTODOS TÉCNICOS DE EXTRACCIÓN ──
    def _extraer_codigo_glosa(self, texto: str) -> str:
        m = re.search(r"\b(TA|SO|AU|CO|PE|FA|SE)\d{2,4}\b", texto)
        return m.group(0) if m else "N/A"

    def _extraer_valor(self, texto: str) -> str:
        m = re.search(r"\$\s*([\d\.,]+)", texto)
        return f"$ {m.group(1)}" if m else "$ 0.00"

    def _xml(self, tag: str, texto: str, default: str) -> str:
        m = re.search(fr"<{tag}>(.*?)</{tag}>", texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    def _calcular_dias_habiles(self, f1, f2):
        try:
            d1, d2 = datetime.strptime(f1[:10], "%Y-%m-%d"), datetime.strptime(f2[:10], "%Y-%m-%d")
            dias, curr = 0, d1
            while curr < d2:
                curr += timedelta(days=1)
                if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in FERIADOS_CO: dias += 1
            return dias
        except: return 0

    async def _llamar_ia(self, system: str, user: str) -> tuple[str, str]:
        try:
            resp = await self.groq.chat.completions.create(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                model="llama-3.3-70b-versatile", temperature=0.1
            )
            return resp.choices[0].message.content, "groq/llama-3.3"
        except Exception:
            if self.anthropic_key:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post("https://api.anthropic.com/v1/messages", 
                        headers={"x-api-key": self.anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": "claude-3-5-sonnet-20240620", "max_tokens": 1500, "system": system, "messages": [{"role": "user", "content": user}]})
                    return resp.json()["content"][0]["text"], "anthropic/claude-3.5"
            return "<argumento>ERROR DE CONEXIÓN IA - REVISIÓN MANUAL REQUERIDA</argumento>", "fallback"

    def _generar_tabla_html(self, codigo, valor, cod_res, desc_res):
        return f'''<table border="1" style="width:100%;border-collapse:collapse;font-size:10px;text-transform:uppercase;margin-bottom:10px;">
        <tr style="background-color:#1e3a8a;color:white;"><th style="padding:5px;">CÓDIGO GLOSA</th><th style="padding:5px;">VALOR OBJ.</th><th style="padding:5px;">CÓDIGO DE RESPUESTA (ANEXO 6)</th></tr>
        <tr><td style="text-align:center;padding:5px;">{codigo}</td><td style="text-align:center;padding:5px;">{valor}</td>
        <td style="text-align:center;padding:5px;"><b>{cod_res}</b><br>{desc_res}</td></tr></table>'''
