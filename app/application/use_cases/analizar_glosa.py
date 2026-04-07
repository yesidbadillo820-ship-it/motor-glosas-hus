import json
import logging
import re
from datetime import datetime
from typing import Optional

from app.domain.entities import GlosaEntity, EstadoGlosa
from app.domain.services import MotorReglas, ServicioScoring, ServicioTemporal, WorkflowEngine
from app.domain.value_objects import ScoringInput, WorkflowTransition
from app.infrastructure.repositories import GlosaRepository, ContratoRepository
from app.infrastructure.external.ia_service import IAService
from app.models.schemas import GlosaInput, GlosaResult

logger = logging.getLogger("analizar_glosa_use_case")

ESTRATEGIAS_HUS = {
    "TA": "RECHAZO POR TARIFA. El cobro cumple el contrato o el manual SOAT pleno.",
    "SO": "SOPORTES SUFICIENTES. La Historia Clínica es plena prueba (Res. 1995/1999).",
    "AU": "AUTORIZACIÓN NO REQUERIDA. Urgencia vital o atención prioritaria.",
    "CO": "COBERTURA LEGAL. El servicio es obligación de la EPS bajo Ley 1751/2015.",
    "PE": "PERTINENCIA CLÍNICA. Autonomía médica protegida por Ley 1751/2015 Art. 17.",
    "FA": "FACTURACIÓN CORRECTA. Errores formales son subsanables (Circular 030/2013).",
    "SE": "OBJECIÓN INDETERMINADA. La EPS glosa sin especificar el servicio.",
    "DEFAULT": "RECHAZO TOTAL. La glosa carece de fundamento técnico-legal."
}


class AnalizarGlosaUseCase:
    def __init__(self, glosa_repo: GlosaRepository, contrato_repo: ContratoRepository, ia_service: IAService):
        self.glosa_repo = glosa_repo
        self.contrato_repo = contrato_repo
        self.ia_service = ia_service
        self.motor_reglas = MotorReglas()
        self.servicio_scoring = ServicioScoring()

    async def ejecutar(
        self,
        data: GlosaInput,
        contexto_pdf: str = "",
        usuario_id: Optional[int] = None,
    ) -> GlosaResult:
        logger.info(f"Iniciando análisis para EPS: {data.eps}")
        
        texto_base = str(data.tabla_excel).strip().upper()
        codigo_det = self._extraer_codigo_glosa(texto_base)
        prefijo = codigo_det[:2] if codigo_det != "N/A" else "SE"
        valor_raw = self._extraer_valor(texto_base)
        valor_aceptado_num = self._convertir_numero(data.valor_aceptado)
        
        info_temporal = None
        if data.fecha_radicacion and data.fecha_recepcion:
            info_temporal = ServicioTemporal.calcular_dias_habiles(
                str(data.fecha_radicacion), str(data.fecha_recepcion)
            )
        
        es_extemporanea = info_temporal.es_extemporanea if info_temporal else False
        es_ratificacion = "RATIF" in str(data.etapa).upper()
        
        contexto_reglas = {
            "dias_habiles": info_temporal.dias_habiles if info_temporal else 0,
            "dias_limite": 20,
            "es_ratificacion": es_ratificacion,
            "valor_objetado": valor_raw,
            "cobertura_eps": True,
        }
        
        resultados_reglas = self.motor_reglas.evaluar(contexto_reglas)
        codigo_principal = self.motor_reglas.obtener_codigo_principal(resultados_reglas)
        
        if es_extemporanea:
            cod_res, desc_res = "RE9502", "GLOSA EXTEMPORÁNEA - NO PROCEDE"
        elif es_ratificacion:
            cod_res, desc_res = "RE9901", "GLOSA DE RATIFICACIÓN - NO ACEPTADA"
        elif "DEVOLUCION" in texto_base or "DEVOL" in texto_base:
            cod_res, desc_res = "RE9601", "DEVOLUCIÓN INJUSTIFICADA"
        else:
            cod_res, desc_res = codigo_principal, "GLOSA EVALUADA"
        
        eps_key = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        contratos = self.contrato_repo.como_dict()
        info_contrato = contratos.get(eps_key, "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.")
        
        estrategia = ESTRATEGIAS_HUS.get(prefijo, ESTRATEGIAS_HUS["DEFAULT"])
        
        system_prompt = f"""Eres el Director Jurídico de la ESE Hospital Universitario de Santander (HUS).
Tu MISIÓN es defender el cobro y rechazar la glosa.

CÓDIGO: {cod_res}
MARCO CONTRACTUAL: {info_contrato}
ESTRATEGIA: {estrategia}

REGLAS:
1. NUNCA aceptes la glosa. Tono legalista y combativo.
2. Cita la Ley 1751/2015 y el Artículo 871 del Código de Comercio.
3. Responde en XML: <paciente>...</paciente><argumento>...</argumento>"""
        
        user_prompt = f"DETALLE GLOSA:\n{texto_base}\n\nSOPORTES PDF:\n{contexto_pdf[:3500]}"
        
        res_ia, modelo_usado = await self.ia_service.analizar(system_prompt, user_prompt)
        
        pac_ia = self._xml("paciente", res_ia, "NO IDENTIFICADO")
        arg_ia = self._xml("argumento", res_ia, res_ia).replace("\n", "<br/>")
        
        scoring_input = ScoringInput(
            valor_objetado=float(re.sub(r"[^\d]", "", valor_raw) or 0),
            valor_aceptado=valor_aceptado_num,
            dias_restantes=info_temporal.dias_restantes if info_temporal else 0,
            dias_vencidos=info_temporal.dias_habiles - 20 if info_temporal and info_temporal.es_extemporanea else 0,
            probabilidad_recuperacion=0.8 if not es_extemporanea else 0.1,
            es_extemporanea=es_extemporanea,
            es_ratificacion=es_ratificacion,
            eps=data.eps,
        )
        
        scoring_result = self.servicio_scoring.calcular(scoring_input)
        
        msg_tiempo = info_temporal.mensaje_estado if info_temporal else "Fechas no ingresadas"
        color_tiempo = info_temporal.color_estado if info_temporal else "bg-slate-500"
        
        dictamen = self._generar_tabla_html(codigo_det, valor_raw, cod_res, desc_res) + \
                   f'<div style="text-align:justify;font-size:11px;margin-top:10px;color:#1e293b;"><b>ARGUMENTACIÓN JURÍDICA ESE HUS:</b><br/><br/>{arg_ia}</div>'
        
        glosa = self.glosa_repo.crear(
            eps=data.eps,
            paciente=pac_ia,
            codigo_glosa=codigo_det,
            valor_objetado=float(re.sub(r"[^\d]", "", valor_raw) or 0),
            valor_aceptado=valor_aceptado_num,
            etapa=data.etapa,
            estado="ACEPTADA" if valor_aceptado_num > 0 else "LEVANTADA",
            dictamen=dictamen,
            dias_restantes=scoring_result.score_total if info_temporal else 0,
            responsable_id=usuario_id,
            score=scoring_result.score_total,
            prioridad=scoring_result.prioridad,
            modelo_ia=modelo_usado,
        )
        
        logger.info(f"Glosa {glosa.id} creada con score {scoring_result.score_total} y prioridad {scoring_result.prioridad}")
        
        return GlosaResult(
            tipo=f"RESPUESTA {cod_res}",
            resumen=f"DEFENSA: {pac_ia}",
            dictamen=dictamen,
            codigo_glosa=codigo_det,
            valor_objetado=valor_raw,
            paciente=pac_ia,
            mensaje_tiempo=msg_tiempo,
            color_tiempo=color_tiempo,
            score=scoring_result.score_total,
            dias_restantes=info_temporal.dias_restantes if info_temporal else 0,
            modelo_ia=modelo_usado,
        )

    def _extraer_codigo_glosa(self, texto: str) -> str:
        m = re.search(r"\b(TA|SO|AU|CO|PE|FA|SE)\d{2,4}\b", texto)
        return m.group(0) if m else "N/A"

    def _extraer_valor(self, texto: str) -> str:
        m = re.search(r"\$\s*([\d\.,]+)", texto)
        return f"$ {m.group(1)}" if m else "$ 0.00"

    def _convertir_numero(self, valor_str: str) -> float:
        try:
            return float(valor_str.replace(".", "").replace(",", "."))
        except:
            return 0.0

    def _xml(self, tag: str, texto: str, default: str) -> str:
        m = re.search(fr"<{tag}>(.*?)</{tag}>", texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    def _generar_tabla_html(self, codigo, valor, cod_res, desc_res):
        return f'''<table border="1" style="width:100%;border-collapse:collapse;font-size:10px;text-transform:uppercase;margin-bottom:10px;">
        <tr style="background-color:#1e3a8a;color:white;"><th style="padding:5px;">CÓDIGO GLOSA</th><th style="padding:5px;">VALOR OBJ.</th><th style="padding:5px;">CÓDIGO RESPUESTA</th></tr>
        <tr><td style="text-align:center;padding:5px;">{codigo}</td><td style="text-align:center;padding:5px;">{valor}</td>
        <td style="text-align:center;padding:5px;"><b>{cod_res}</b><br>{desc_res}</td></tr></table>'''