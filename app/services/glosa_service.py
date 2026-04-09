import os
import re
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import httpx
from cachetools import TTLCache
from groq import AsyncGroq
from app.models.schemas import GlosaInput, GlosaResult
from app.core.logging_utils import logger
from app.services.glosa_ia_prompts import get_system_prompt, build_user_prompt

_CACHE_IA: TTLCache = TTLCache(maxsize=500, ttl=3600)
_CACHE_TTL = 3600

FERIADOS_CO = [
    # 2025
    "2025-01-01","2025-01-06","2025-03-24","2025-04-17","2025-04-18",
    "2025-05-01","2025-06-02","2025-06-23","2025-06-30","2025-07-20",
    "2025-08-07","2025-08-18","2025-10-13","2025-11-03","2025-11-17",
    "2025-12-08","2025-12-25",
    # 2026
    "2026-01-01","2026-01-12","2026-03-23","2026-04-02","2026-04-03",
    "2026-05-01","2026-05-18","2026-06-08","2026-06-15","2026-06-29",
    "2026-07-20","2026-08-07","2026-08-17","2026-10-12","2026-11-02",
    "2026-11-16","2026-12-08","2026-12-25",
    # 2027 (Ley 1393/2010 - puentes psicológicos automáticos)
    "2027-01-01","2027-01-11","2027-03-22","2027-04-01","2027-04-02",
    "2027-05-01","2027-05-17","2027-06-07","2027-06-14","2027-06-28",
    "2027-07-20","2027-08-07","2027-08-16","2027-10-11","2027-11-01",
    "2027-11-15","2027-12-08","2027-12-25",
    # 2028 (estimados - verificar publicado)
    "2028-01-01","2028-01-10","2028-03-20","2028-04-13","2028-04-14",
    "2028-05-01","2028-05-15","2028-06-05","2028-06-12","2028-06-26",
    "2028-07-20","2028-08-07","2028-08-14","2028-10-09","2028-10-30",
    "2028-11-06","2028-11-13","2028-12-08","2028-12-25",
]

# PLAZO LEGAL: 20 días hábiles según Art. 56 Ley 1438 de 2011
# Las glosas extemporáneas son improcedentes, abusivas y no deben disminuir el pago a las IPS
DIAS_HABILES_LIMITE_EXTEMPORANEA = 20

NORMATIVA_COLOMBIA = """
NORMATIVA APLICABLE:
- Ley 100 de 1993: Sistema de Seguridad Social Integral (Art. 168 - Urgencias)
- Ley 1438 de 2011: Reforma al Sistema de Salud (Artículo 56 - Plazo 20 días hábiles para glosas)
- Ley 1751 de 2015: Ley Estatutaria de Salud (Derecho fundamental a la salud)
- Ley 1122 de 2007: Flujo de recursos entre EPS e IPS (Art. 13)
- Decreto 4747 de 2007: Regulaciones sobre glosas y devoluciones (Art. 20 - Conciliación)
- Decreto 780 de 2016: Decreto Único Reglamentario del Sector Salud
- Resolución 2175 de 2015: Procedimiento de conciliación de glosas médicas
- Resolución 3047 de 2008: Anexo Técnico 5 (Procedimiento glosas)
- Resolución 5269 de 2017: Plan de Beneficios en Salud
- Resolución 054 de 2026: Tarifas SOAT Plenas
- Decreto 2423 de 1996: Manual de Tarifas SOAT
- Código de Comercio: Artículo 871 (Principio de Buena Fe)
- Circular 030 de 2013: Subsanación de errores formales en facturación
- Resolución 1995 de 1999: Historia clínica como prueba plena
- Sentencia T-760 de 2008: Obligaciones de las EPS en prestación de servicios
- Sentencia T-1025 de 2002: Urgencias no requieren autorización previa
- Sentencia T-478 de 1995: Autonomía médica como derecho fundamental
"""

ESTRATEGIAS_TIPO = {
    "TA_TARIFA": """ESTRATEGIA TARIFARIA PROFESIONAL:
- Verificar la tarifa liquidada vs tarifa contractual vigente (SOAT -15% o según convenio)
- Citar específicamente el contrato vigente y sus anexos tarifarios
- Invocar la Resolución Interna de Precios de la institución
- Principio de buena fe contractual (Art. 871 Código Comercio)
- Mencionar que la EPS no puede aplicar descuentos unilaterales sin sustento
- El IPC es un referente NO una obligación para la IPS
- Si hay incremento institucional debidamente aprobado, citar acto administrativo""",
    "SO_SOPORTES": "ESTRATEGIA SOPORTES: Historia clínica es plena prueba según Res. 1995/1999. Documentos cumplen norma. EPS tuvo 20 días hábiles para objetar (Art. 56 Ley 1438/2011).",
    "AU_AUTORIZACION": "ESTRATEGIA AUTORIZACIÓN: Atención por urgencia vital. No requiere autorización previa. Art. 168 Ley 100/1993 y Resolución 5269/2017.",
    "CO_COBERTURA": "ESTRATEGIA COBERTURA: Servicio dentro del Plan de Beneficios en Salud (Res. 5269/2017). EPS tiene obligación de pago. No hay exclusiones.",
    "PE_PERTINENCIA": "ESTRATEGIA PERTINENCIA: Autonomía médica protegida por Art. 17 Ley 1751/2015. Criterio del médico tratante prevalece. Historia clínica soporta la decisión.",
    "FA_FACTURACION": "ESTRATEGIA FACTURACIÓN: Error formal no es causal de glosa (Circular 030/2013). Los errores formales son subsanables. La prestación del servicio genera obligación de pago.",
    "IN_INSUMOS": "ESTRATEGIA INSUMOS: Inherentes al acto médico. Se facturan al costo de adquisición más porcentaje administrativo pactado. Factura de compra disponible como soporte.",
    "ME_MEDICAMENTOS": "ESTRATEGIA MEDICAMENTOS: Dispensados bajo fórmula médica. Plan de Beneficios los incluye (Res. 5269/2017). No existe alternativa terapéutica equivalente.",
    "EXT_EXTEMPORANEA": "ESTRATEGIA EXTEMPORÁNEA: Glosa improcedente por extemporaneidad. Art. 56 Ley 1438/2011 establece 20 días hábiles. EPS perdió el derecho a glosar. Estas glosas son abusivas y no pueden disminuir el pago a la IPS."
}

CODIGOS_GLOSA = {
    "TA": "OBJECIÓN POR TARIFA", "SO": "OBJECIÓN POR SOPORTES",
    "AU": "OBJECIÓN POR AUTORIZACIÓN", "CO": "OBJECIÓN POR COBERTURA",
    "PE": "OBJECIÓN POR PERTINENCIA", "FA": "OBJECIÓN POR FACTURACIÓN",
    "IN": "OBJECIÓN POR INSUMOS", "ME": "OBJECIÓN POR MEDICAMENTOS",
    "SE": "OBJECIÓN SIN ESPECIFICACIÓN", "EX": "OBJECIÓN EXTEMPORÁNEA"
}

PLANTILLAS_CODIGO = {
    "TA0201": {
        "nombre": "Diferencia en valor de consulta/interconsulta",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR TARIFA. LA OBJECIÓN RELATIVA AL CARGO POR CONSULTA, INTERCONSULTA O ATENCIÓN DOMICILIARIA SE RECHAZA DE PLANO POR CUANTO EL VALOR FACTURADO SE AJUSTA ESTRICTAMENTE A LA RESOLUCIÓN INTERNA DE PRECIOS VIGENTE DE ESTA INSTITUCIÓN, LA CUAL CONSTITUYE LA TARIFA INSTITUCIONAL RECONOCIDA CONTRACTUALMENTE. SEGÚN CONTRATO VIGENTE Y TARIFA SOAT ACORDADA, SE DEBE RECONOCER EL INCREMENTO QUE LA ENTIDAD ADOPTE PARA LA VIGENCIA CORRESPONDIENTE. LA PRETENSIÓN DE LA ENTIDAD PAGADORA DE LIMITAR UNILATERALMENTE EL COBRO BASÁNDOSE EN UN INCREMENTO DEL IPC SIN CONSIDERAR EL ACTO ADMINISTRATIVO INSTITUCIONAL CARECE DE SUSTENTO LEGAL Y CONTRACTUAL (ART. 871 C. COMERCIO). SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO."""
    },
    "TA0202": {
        "nombre": "Diferencia en valor de procedimiento",
        "plantilla": """ESE HUS NO ACEPTA GLOSA TARIFARIA. EL VALOR DEL PROCEDIMIENTO FACTURADO SE ENCUENTRA DENTRO DE LOS PARÁMETROS ESTABLECIDOS EN EL CONTRATO VIGENTE Y LA RESOLUCIÓN INTERNA DE TARIFAS. LA LIQUIDACIÓN REALIZADA CUMPLE CON LOS LINEAMIENTOS DEL MANUAL TARIFARIO SOAT (DECRETO 2423/1996) Y LAS NORMAS CONTRACTUALES VIGENTES. CUALQUIER DIFERENCIA TARIFARIA DEBE SER RESUELTA EN EL MARCO DE LA AUDITORÍA MÉDICA CONCERTADA (DECRETO 4747/2007 ART. 20). SE EXIGE EL PAGO ÍNTEGRO DEL SERVICIO PRESTADO."""
    },
    "TA0203": {
        "nombre": "Aplicación incorrecta de porcentaje de descuento",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR APLICACIÓN INCORRECTA DE DESCUENTOS. LA ENTIDAD PAGADORA NO PUEDE APLICAR DESCUENTOS UNILATERALES SIN EL ACUERDO PREVIO DE LAS PARTES CONTRATANTES. EL PORCENTAJE APLICADO DEBE CORRESPONDER EXACTAMENTE A LO PACTADO EN EL CONTRATO VIGENTE. CUALQUIER MODIFICACIÓN REQUIERE CONVENIO EXPRESO ENTRE LAS PARTES (ART. 871 C. COMERCIO). SE RECHAZA LA GLOSA Y SE SOLICITA EL PAGO ÍNTEGRO SEGÚN TARIFAS CONTRACTUALES."""
    },
    "SO0101": {
        "nombre": "Falta de orden médica",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR FALTA DE ORDEN MÉDICA. LA ATENCIÓN PRESTADA SE ENCUENTRA AMPARADA EN LA HISTORIA CLÍNICA DEL PACIENTE, LA CUAL CONTIENE LA INDICACIÓN MÉDICA CORRESPONDIENTE Y CONSTITUYE PLENA PRUEBA DE LA ATENCIÓN BRINDADA (RESOLUCIÓN 1995/1999). ADEMÁS, LA EPS TUVO UN PLAZO DE 20 DÍAS HÁBILES PARA OBJETAR SEGÚN EL ARTÍCULO 56 DE LA LEY 1438/2011 Y NO EJERCIÓ SU DERECHO OPORTUNAMENTE. SE SOLICITA EL LEVANTAMIENTO INMEDIATO DE LA GLOSA."""
    },
    "SO0102": {
        "nombre": "Soportes incompletos",
        "plantilla": """ESE HUS RECHAZA LA GLOSA POR SOPORTES INCOMPLETOS. TODOS LOS DOCUMENTOS DE FACTURACIÓN CUMPLEN CON LA NORMATIVA VIGENTE Y FUERON RADICADOS EN TÉRMINO. LA EPS TUVO EL PLAZO LEGAL DE 20 DÍAS HÁBILES PARA SOLICITAR DOCUMENTACIÓN ADICIONAL (ART. 56 LEY 1438/2011 Y DECRETO 4747/2007) Y NO LO HIZO. SE EXIGE EL PAGO ÍNTEGRO."""
    },
    "AU0101": {
        "nombre": "Falta de autorización previa",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR FALTA DE AUTORIZACIÓN PREVIA. LA ATENCIÓN FUE PRESTADA POR URGENCIA VITAL, CONDICIÓN QUE EXIME DEL REQUISITO DE AUTORIZACIÓN PREVIA SEGÚN EL ARTÍCULO 168 DE LA LEY 100 DE 1993 Y LA RESOLUCIÓN 5269 DE 2017. LA URGENCIA MÉDICA CONSTITUYE CAUSA JUSTIFICADA PARA LA ATENCIÓN INMEDIATA SIN AUTORIZACIÓN PREVIA. NO PROCEDE GLOSA POR ESTE CONCEPTO. SE SOLICITA EL LEVANTAMIENTO Y PAGO ÍNTEGRO."""
    },
    "CO0101": {
        "nombre": "Servicio no cubierto POS",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR COBERTURA. EL SERVICIO PRESTADO SE ENCUENTRA DENTRO DEL PLAN DE BENEFICIOS EN SALUD SEGÚN LA LEY 1751 DE 2015 Y LA RESOLUCIÓN 5269 DE 2017. LA EPS TIENE OBLIGACIÓN DE PAGO INDEPENDIENTEMENTE DEL RÉGIMEN DE AFILIACIÓN. NO EXISTEN EXCLUSIONES CONTRACTUALES APLICABLES AL CASO ESPECÍFICO. EL SERVICIO FUE VITAL PARA LA ATENCIÓN DEL PACIENTE. SE RECHAZA LA GLOSA Y SE SOLICITA PAGO ÍNTEGRO."""
    },
    "PE0101": {
        "nombre": "Falta de pertinencia",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR FALTA DE PERTINENCIA. LA DECISIÓN MÉDICA SE BASA EN EL CRITERIO CLÍNICO DEL MÉDICO TRATANTE, QUIEN GOZA DE AUTONOMÍA PROFESIONAL PROTEGIDA POR EL ARTÍCULO 17 DE LA LEY 1751 DE 2015. LA HISTORIA CLÍNICA FUNDAMENTA CLARAMENTE LA NECESIDAD DEL PROCEDIMIENTO. EL CRITERIO DEL MÉDICO TRATANTE PREVALECE SOBRE LA VALORACIÓN EXTERNA DE LA EPS. SE SOLICITA LEVANTAMIENTO DE LA GLOSA."""
    },
    "FA0101": {
        "nombre": "Error en código de facturación",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR ERROR EN CÓDIGO. SEGÚN LA CIRCULAR 030 DE 2013, LOS ERRORES FORMALES EN FACTURACIÓN SON SUBSANABLES Y NO CONSTITUYEN CAUSAL VÁLIDA DE GLOSA. LA INSTITUCIÓN PROCEDE A CORREGIR CUALQUIER ERROR MATERIAL DETECTADO MEDIANTE NOTA ACLARATORIA. LA PRESTACIÓN EFECTIVA DEL SERVICIO GENERA LA OBLIGACIÓN DE PAGO (DECRETO 4747/2007). SE RECHAZA LA GLOSA."""
    },
    "FA0102": {
        "nombre": "Duplicidad en facturación",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR DUPLICIDAD. SE CLARIFICA QUE CADA FACTURA CORRESPONDE A SERVICIOS DISTINTOS Y/O PACIENTES DIFERENTES, SEGÚN CONSTA EN LOS REGISTROS DE HISTORIA CLÍNICA. SE ADJUNTAN LOS SOPORTES QUE DEMUESTRAN LA NO DUPLICIDAD. EN CASO DE IDENTIFICARSE ALGÚN PAGO DUPLICADO, SE PROCEDERÁ A LA RESPECTIVA LIQUIDACIÓN DE CONFORMIDAD. SE SOLICITA REVISIÓN Y LEVANTAMIENTO DE LA OBJECIÓN."""
    },
    "IN0101": {
        "nombre": "Insumo no reconocido",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR INSUMO NO RECONOCIDO. LOS INSUMOS UTILIZADOS SON INHERENTES AL ACTO MÉDICO PRESTADO Y SE FACTURAN AL COSTO DE ADQUISICIÓN MÁS EL PORCENTAJE ADMINISTRATIVO PACTADO CONTRACTUALMENTE. SE ADJUNTA FACTURA DE COMPRA COMO SOPORTE. EL CÓDIGO TARIFARIO NO LISTA EXPRESAMENTE ESTOS INSUMOS COMO EXCLUIDOS. SE RECHAZA LA GLOSA."""
    },
    "ME0101": {
        "nombre": "Medicamento no cubierto",
        "plantilla": """ESE HUS NO ACEPTA GLOSA POR MEDICAMENTO NO CUBIERTO. LOS MEDICAMENTOS FUERON DISPENSADOS BAJO FÓRMULA MÉDICA Y SE ENCUENTRAN DENTRO DEL PLAN DE BENEFICIOS EN SALUD (RESOLUCIÓN 5269/2017 - LEY 1751/2015). NO EXISTE FÓRMULA ALTERNATIVA IGUALMENTE EFECTIVA DOCUMENTADA. SE RECHAZA Y SE SOLICITA PAGO ÍNTEGRO."""
    }
}


def obtener_plantilla_por_codigo(codigo: str) -> Optional[dict]:
    """Obtiene la plantilla específica para un código de glosa."""
    return PLANTILLAS_CODIGO.get(codigo.upper())


TEXTO_RATIFICADA = (
    "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE "
    "DE LA GLOSA INICIAL Y SE DA CONTINUACIÓN AL PROCESO DE CONFORMIDAD CON EL ARTÍCULO "
    "56 DE LA LEY 1438 DE 2011, EL ARTÍCULO 20 DEL DECRETO 4747 DE 2007 Y LA RESOLUCIÓN "
    "2175 DE 2015. SE SOLICITA LA PROGRAMACIÓN DE LA FECHA DE CONCILIACIÓN DE AUDITORÍA "
    "MÉDICA Y/O TÉCNICA ENTRE LAS PARTES SEGÚN EL PROCEDIMIENTO ESTABLECIDO. DE NO "
    "LLEGARSE A ACUERDO, SE ELEVARÁ EL CONFLICTO ANTE LA SUPERINTENDENCIA NACIONAL "
    "DE SALUD SEGÚN LO DISPUESTO EN EL ART. 126 DE LA LEY 1438/2011. CUALQUIER "
    "INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO, "
    "GLOSASYDEVOLUCIONES@HUS.GOV.CO, VENTANILLA ÚNICA DE LA ESE HUS CARRERA 33 NO. 28-126. "
    "NOTA: DE ACUERDO CON EL ARTÍCULO 56 DE LA LEY 1438 DE 2011, DE NO OBTENERSE "
    "RESPUESTA A LA GLOSA RATIFICADA EN LOS TÉRMINOS ESTABLECIDOS, SE DARÁ POR "
    "LEVANTADA LA RESPECTIVA OBJECIÓN."
)


def generar_texto_extemporanea(dias: int) -> str:
    return (
        f"ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. SEGÚN EL ARTÍCULO 56 "
        f"DE LA LEY 1438 DE 2011, EL PLAZO LEGAL PARA QUE LA EPS FORMULE GLOSAS ES DE "
        f"20 DÍAS HÁBILES CONTADOS A PARTIR DE LA RECEPCIÓN DE LA FACTURA. AL HABERSE "
        f"SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {dias} DÍAS HÁBILES), LA GLOSA CARECE "
        f"DE TODO SUSTENTO LEGAL Y CONSTITUYE UN ACTO ABUSIVO E IMPROCEDENTE POR PARTE DE "
        f"LA ENTIDAD PAGADORA. LA LEY 1751 DE 2015 Y EL PRINCIPIO DE BUENA FE CONTRACTUAL "
        f"(ART. 871 CÓDIGO DE COMERCIO) PROTEGEN EL DERECHO DE LA IPS A RECIBIR EL PAGO "
        f"ÍNTEGRO DE LOS SERVICIOS PRESTADOS. ESTAS GLOSAS EXTEMPORÁNEAS NO DEBEN DISMINUIR "
        f"EL PAGO DEBIDO A LA IPS BAJO NINGUNA CIRCUNSTANCIA. SE EXIGE EL LEVANTAMIENTO "
        f"INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CUALQUIER INFORMACIÓN "
        f"AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO."
    )


def generar_texto_injustificada(eps: str) -> str:
    return (
        f"ESE HUS NO ACEPTA GLOSA INJUSTIFICADA. NO EXISTE CONTRATO PACTADO CON LA "
        f"ENTIDAD {eps}. SE FACTURÓ BAJO TARIFA SOAT PLENA (RESOLUCIÓN 054/2026 - "
        f"DECRETO 2423/1996). LA GLOSA CARECE DE SUSTENTO CONTRACTUAL Y LEGAL. "
        f"SE EXIGE EL PAGO ÍNTEGRO DE LA FACTURA SEGÚN MANUAL TARIFARIO SOAT PLENO "
        f"SIN DESCUENTOS. CUALQUIER INFORMACIÓN A CARTERA@HUS.GOV.CO."
    )


class GlosaService:
    def __init__(self, groq_api_key: str = None, anthropic_api_key: str = None):
        self.groq = AsyncGroq(api_key=groq_api_key) if groq_api_key else None
        self.anthropic_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")

    async def analizar(self, data: GlosaInput, contexto_pdf: str = "", contratos_db: dict = None) -> GlosaResult:
        texto_base = str(data.tabla_excel).strip().upper()

        codigo_det = self._extraer_codigo_glosa(texto_base)
        prefijo = codigo_det[:2] if codigo_det and codigo_det != "N/A" else "SE"
        valor_raw = self._extraer_valor(texto_base)

        msg_tiempo, color_tiempo, dias = "Fechas no ingresadas", "bg-slate-500", 0
        if data.fecha_radicacion and data.fecha_recepcion:
            try:
                dias = self._calcular_dias_habiles(str(data.fecha_radicacion), str(data.fecha_recepcion))
                # PLAZO LEGAL: 20 días hábiles según Art. 56 Ley 1438/2011
                es_extemporanea = dias > DIAS_HABILES_LIMITE_EXTEMPORANEA
                msg_tiempo = (
                    f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES - LÍMITE: {DIAS_HABILES_LIMITE_EXTEMPORANEA})"
                    if es_extemporanea
                    else f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)"
                )
                color_tiempo = "bg-red-600" if es_extemporanea else "bg-emerald-500"
            except Exception as e:
                logger.error(f"Error fechas: {e}")

        # CORRECCIÓN: inicializar tipo_glosa antes de usarlo para evitar UnboundLocalError
        tipo_glosa = self._determinar_tipo_glosa(prefijo, texto_base)

        es_extemporanea = dias > DIAS_HABILES_LIMITE_EXTEMPORANEA
        es_ratificacion = "RATIF" in str(data.etapa).upper()
        tiene_pdf = bool(contexto_pdf and len(contexto_pdf.strip()) > 0)
        es_urgencia = "URGENCIA" in texto_base or "URGENTE" in texto_base
        es_tarifa = prefijo == "TA" or "TARIFA" in texto_base

        eps_key = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        tiene_contrato = eps_key in (contratos_db or {})
        info_contrato = (contratos_db or {}).get(eps_key, "SIN CONTRATO PACTADO. TARIFA: SOAT PLENO.")

        argumento_fijo = None
        if es_ratificacion:
            argumento_fijo = TEXTO_RATIFICADA
            tipo_glosa = "RATIFICADA"
        elif es_extemporanea:
            argumento_fijo = generar_texto_extemporanea(dias)
            tipo_glosa = "EXTEMPORANEA"
        elif es_tarifa and not tiene_contrato:
            argumento_fijo = generar_texto_injustificada(eps_key)
            tipo_glosa = "TA_TARIFA"

        if es_extemporanea:
            cod_res, desc_res = "RE9502", "GLOSA EXTEMPORÁNEA - IMPROCEDENTE (Art. 56 Ley 1438/2011)"
        elif es_ratificacion:
            cod_res, desc_res = "RE9901", "GLOSA RATIFICADA - NO ACEPTADA"
        elif prefijo == "AU":
            cod_res, desc_res = "RE0101", "NO SE ACEPTA GLOSA POR AUTORIZACIÓN"
        elif prefijo == "SO":
            cod_res, desc_res = "RE0201", "NO SE ACEPTA GLOSA POR SOPORTES"
        elif prefijo == "CO":
            cod_res, desc_res = "RE0401", "NO SE ACEPTA GLOSA POR COBERTURA"
        elif prefijo == "FA":
            cod_res, desc_res = "RE0601", "NO SE ACEPTA GLOSA POR FACTURACIÓN"
        elif prefijo == "PE":
            cod_res, desc_res = "RE0501", "NO SE ACEPTA GLOSA POR PERTINENCIA"
        elif es_tarifa and not tiene_contrato:
            cod_res, desc_res = "RE9602", "GLOSA INJUSTIFICADA - SIN CONTRATO"
        elif "DEVOLUCION" in texto_base or "DEV." in texto_base:
            cod_res, desc_res = "RE9601", "DEVOLUCIÓN INJUSTIFICADA"
        else:
            cod_res, desc_res = "RE9901", "NO SE ACEPTA LA GLOSA"

        plantilla = obtener_plantilla_por_codigo(codigo_det)
        usa_plantilla = plantilla is not None

        if argumento_fijo:
            pac_ia = "N/A"
            arg_ia = argumento_fijo
            modelo_usado = "texto_fijo"
        elif usa_plantilla:
            pac_ia = "N/A (PLANTILLA)"
            arg_ia = plantilla["plantilla"]
            modelo_usado = "plantilla"
        else:
            system_prompt = get_system_prompt(
                tipo_glosa=tipo_glosa,
                eps=data.eps,
                contrato=info_contrato,
                cod_res=cod_res,
                desc_res=desc_res
            )
            user_prompt = build_user_prompt(
                texto_glosa=texto_base,
                contexto_pdf=contexto_pdf,
                codigo=codigo_det,
                eps=data.eps,
                numero_factura=data.numero_factura,
                numero_radicado=data.numero_radicado,
                dias_habiles=dias,
                es_extemporanea=es_extemporanea
            )
            res_ia, modelo_usado = await self._llamar_ia(system_prompt, user_prompt)
            
            razonamiento = self._xml("razonamiento", res_ia, "")
            if razonamiento:
                logger.info(f"IA razonamiento: {razonamiento[:200]}")

            pac_ia = self._xml("paciente", res_ia, "NO IDENTIFICADO")
            arg_ia = self._xml("argumento", res_ia, "")

            if not arg_ia or arg_ia == res_ia:
                if "<argumento>" in res_ia:
                    start = res_ia.find("<argumento>") + len("<argumento>")
                    end = res_ia.find("</argumento>")
                    arg_ia = res_ia[start:end].strip() if end > start else res_ia
                else:
                    arg_ia = res_ia

            if "<paciente>" in arg_ia:
                arg_ia = arg_ia.split("</paciente>")[-1].strip()
            arg_limpio = arg_ia.replace("<br/>", " ").replace("*", "")
            arg_ia = arg_ia.replace("\n", "<br/>").replace("*", "")

        score = self._calcular_score(tipo_glosa, es_extemporanea, es_ratificacion, tiene_pdf, es_urgencia, es_tarifa, arg_limpio)

        dictamen = self._generar_dictamen_html(
            codigo_det, valor_raw, cod_res, desc_res, arg_ia, data.eps, tipo_glosa,
            numero_factura=data.numero_factura, numero_radicado=data.numero_radicado
        )

        return GlosaResult(
            tipo=f"RESPUESTA {cod_res}",
            resumen=f"DEFENSA TÉCNICA: {pac_ia}",
            dictamen=dictamen,
            codigo_glosa=codigo_det,
            valor_objetado=valor_raw,
            paciente=pac_ia,
            mensaje_tiempo=msg_tiempo,
            color_tiempo=color_tiempo,
            score=score,
            dias_restantes=max(0, DIAS_HABILES_LIMITE_EXTEMPORANEA - dias),
            modelo_ia=modelo_usado
        )

    def _calcular_score(self, tipo_glosa: str, es_extemporanea: bool, es_ratificacion: bool,
                        tiene_pdf: bool, es_urgencia: bool, es_tarifa: bool,
                        argumento_generado: str = "") -> float:
        if es_extemporanea:
            base = 99.0
        elif es_ratificacion:
            base = 92.0
        elif es_urgencia:
            base = 90.0
        elif es_tarifa:
            base = 75.0
        else:
            base = 85.0
        
        if tiene_pdf:
            base = min(100.0, base + 5.0)
        
        if argumento_generado:
            normas_citadas = len(re.findall(
                r'(LEY\s*\d+|DECRETO\s*\d+|RESOLUCIÓN|RESOLUCIÓN\s*\d+|ART\.\s*\d+|ARTÍCULO\s*\d+|SENTENCIA)',
                argumento_generado.upper()
            ))
            bonus_normas = min(5.0, normas_citadas * 0.5)
            
            bonus_longitud = min(3.0, len(argumento_generado) / 300)
            
            base = min(100.0, base + bonus_normas + bonus_longitud)
            
            if normas_citadas >= 3:
                logger.info(f"Score bonus: {normas_citadas} normas citadas, {len(argumento_generado)} chars")
        
        return round(base, 1)

    def _xml(self, tag: str, texto: str, default: str) -> str:
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    def _determinar_tipo_glosa(self, prefijo: str, texto: str) -> str:
        texto_lower = texto.lower()
        if "extempor" in texto_lower or prefijo == "EX":
            return "EXT_EXTEMPORANEA"
        if prefijo == "TA": return "TA_TARIFA"
        elif prefijo == "SO": return "SO_SOPORTES"
        elif prefijo == "AU": return "AU_AUTORIZACION"
        elif prefijo == "CO": return "CO_COBERTURA"
        elif prefijo == "PE": return "PE_PERTINENCIA"
        elif prefijo == "FA": return "FA_FACTURACION"
        if any(p in texto_lower for p in ["insumo", "material", "precio"]):
            return "IN_INSUMOS"
        if any(p in texto_lower for p in ["medicamento", "fármaco", "fórmula"]):
            return "ME_MEDICAMENTOS"
        return "FA_FACTURACION"

    def _extraer_codigo_glosa(self, texto: str) -> str:
        m = re.search(r"\b(TA|SO|AU|CO|PE|FA|SE|IN|ME|EX)\d{2,4}\b", texto)
        return m.group(0) if m else "SE-N/A"

    def _extraer_valor(self, texto: str) -> str:
        m = re.search(r"\$\s*([\d\.,]+)", texto)
        return f"$ {m.group(1)}" if m else "$ 0.00"

    def _calcular_dias_habiles(self, f1, f2):
        try:
            d1 = datetime.strptime(f1[:10], "%Y-%m-%d")
            d2 = datetime.strptime(f2[:10], "%Y-%m-%d")
            dias, curr = 0, d1
            while curr < d2:
                curr += timedelta(days=1)
                if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in FERIADOS_CO:
                    dias += 1
            return dias
        except Exception:
            return 0

    def _construir_prompt(self, cod_res: str, desc_res: str, eps: str, contrato: str, estrategia: str, tipo_glosa: str) -> str:
        if tipo_glosa == "TA_TARIFA":
            return f"""Eres el Abogado Director de la ESE HOSPITAL UNIVERSITARIO DE SANTANDER.
ESPECIALISTA EN DEFENSA DE OBJECIONES TARIFARIAS.

CÓDIGO: {cod_res} - {desc_res}
EPS: {eps}
CONTRATO VIGENTE: {contrato}

{estrategia}

NORMATIVA TARIFARIA ESPECÍFICA:
- Ley 100/1993 Art. 168: Obligación de pago de servicios de urgencias
- Decreto 2423/1996: Manual de Tarifas SOAT
- Resolución 054/2026: Tarifas SOAT Plenas vigentes
- Resolución Interna HUS: Tarifario institucional actualizado
- Principio de buena fe contractual (Art. 871 Código de Comercio)
- Autonomía contractual de las partes (Art. 1601 Código Civil)
- Ley 1751/2015 Art. 2: Derecho fundamental a la salud

INSTRUCCIONES OBLIGATORIAS:
1. REDACTA una defensa técnico-jurídica ESPECÍFICA para objeciones tarifarias
2. NUNCA aceptes la glosa - recházala de plano
3. Cita el contrato específico vigente y sus tarifas pactadas
4. Argumenta que la factura se ajusta a la Resolución Interna de Precios
5. Explica que el IPC es un referente NO una obligación legal
6. La respuesta debe ser PROFESIONAL y DETALLADA - mínimo 3 párrafos
7. Estructura: <paciente>Nombre</paciente><argumento>Tu defensa...</argumento>
8. TODO en MAYÚSCULAS"""

        return f"""Eres el Abogado Director de la ESE HOSPITAL UNIVERSITARIO DE SANTANDER.
Tu misión es DEFENDER el cobro y RECHAZAR las glosas de manera técnico-jurídica.

CÓDIGO: {cod_res} - {desc_res}
EPS: {eps}
CONTRATO: {contrato}

{estrategia}

NORMATIVA: Ley 100/1993, Ley 1438/2011 Art.56 (20 días hábiles), Ley 1751/2015,
Decreto 4747/2007, Resolución 3047/2008, Resolución 5269/2017.

INSTRUCCIONES:
1. Redacta DEFENSA LEGAL COMPLETA
2. Usa lenguaje jurídico formal colombiano
3. Cita normas específicas con artículos
4. NUNCA aceptes la glosa
5. Estructura: <paciente>Nombre</paciente><argumento>Tu defensa...</argumento>
6. Argumento en PÁRRAFO CONTINUO en mayúsculas."""

    def _construir_user_prompt(self, texto_glosa: str, contexto_pdf: str, codigo: str) -> str:
        prompt = f"GLOSA: {texto_glosa}\n\nCÓDIGO: {codigo}"
        if contexto_pdf:
            prompt += f"\n\nSOPORTES: {contexto_pdf[:5000]}"
        prompt += "\n\n<paciente>Nombre</paciente><argumento>TU DEFENSA...</argumento>"
        return prompt

    def _generar_dictamen_html(self, codigo: str, valor: str, cod_res: str, desc_res: str,
                               argumento: str, eps: str, tipo: str,
                               numero_factura: Optional[str] = None,
                               numero_radicado: Optional[str] = None) -> str:
        colores = {
            "TA_TARIFA": "#1e40af", "SO_SOPORTES": "#7c3aed", "AU_AUTORIZACION": "#059669",
            "CO_COBERTURA": "#dc2626", "PE_PERTINENCIA": "#d97706", "FA_FACTURACION": "#0891b2",
            "IN_INSUMOS": "#e11d48", "ME_MEDICAMENTOS": "#4f46e5", "EXT_EXTEMPORANEA": "#991b1b",
            "RATIFICADA": "#7c3aed", "EXTEMPORANEA": "#991b1b"
        }
        color = colores.get(tipo, "#1e3a8a")

        # NUEVOS: mostrar factura y radicado si están disponibles
        fila_trazabilidad = ""
        if numero_factura or numero_radicado:
            fila_trazabilidad = f"""
            <tr>
                <td colspan="3" style="padding:6px 10px;font-size:10px;color:#64748b;border-top:1px dashed #e2e8f0;">
                    {'N° Factura: <b>' + numero_factura + '</b>' if numero_factura else ''}
                    {'&nbsp;&nbsp;|&nbsp;&nbsp;' if numero_factura and numero_radicado else ''}
                    {'N° Radicado: <b>' + numero_radicado + '</b>' if numero_radicado else ''}
                </td>
            </tr>"""

        # CORRECCIÓN: nota de pie en español
        return f"""
        <table border="1" style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:15px;background:white;">
            <tr style="background-color:{color};color:white;">
                <th style="padding:10px;text-align:center;">CÓDIGO GLOSA</th>
                <th style="padding:10px;text-align:center;">VALOR OBJETADO</th>
                <th style="padding:10px;text-align:center;">CÓDIGO RESPUESTA</th>
            </tr>
            <tr>
                <td style="padding:10px;text-align:center;font-weight:bold;">{codigo}</td>
                <td style="padding:10px;text-align:center;font-weight:bold;color:{color};">{valor}</td>
                <td style="padding:10px;text-align:center;"><b>{cod_res}</b><br><span style="font-size:10px">{desc_res}</span></td>
            </tr>
            {fila_trazabilidad}
        </table>

        <div style="background:#f8fafc;border-radius:12px;padding:20px;border-left:4px solid {color};margin-top:15px;">
            <div style="display:flex;gap:10px;margin-bottom:15px;">
                <span style="background:{color};color:white;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:700;">{eps}</span>
                <span style="background:#fef3c7;color:#92400e;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:600;">{tipo.replace('_', ' ')}</span>
            </div>
            <h4 style="color:#0f172a;margin:0 0 10px 0;font-size:14px;">ARGUMENTACIÓN JURÍDICA</h4>
            <div style="font-size:12px;line-height:1.9;color:#334155;white-space:pre-wrap;">{argumento}</div>
        </div>

        <div style="margin-top:15px;padding:12px;background:#fef2f2;border-radius:8px;font-size:10px;color:#991b1b;">
            <b>Nota:</b> Generado con asistencia de IA. Verificar antes de radicar ante la EPS.
        </div>"""

    async def _llamar_groq_con_retry(self, system: str, user: str, max_intentos: int = 3) -> tuple[str, str]:
        """Llama a Groq con retry exponencial para manejar rate limits."""
        import asyncio
        
        for intento in range(max_intentos):
            try:
                resp = await self.groq.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.1,
                    max_tokens=2500
                )
                content = resp.choices[0].message.content
                return content, "groq/llama-3.3"
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "rate" in error_msg or "limit" in error_msg:
                    if intento < max_intentos - 1:
                        espera = 2 ** intento
                        logger.warning(f"Groq rate limit, reintento {intento + 2}/{max_intentos} en {espera}s")
                        await asyncio.sleep(espera)
                        continue
                raise
        raise Exception("Groq: todos los reintentos fallaron")

    async def _llamar_ia(self, system: str, user: str) -> tuple[str, str]:
        clave_cache = hashlib.sha256(f"{system}:{user}".encode()).hexdigest()

        if clave_cache in _CACHE_IA:
            cached = _CACHE_IA[clave_cache]
            if isinstance(cached, tuple):
                respuesta, modelo = cached[0], cached[1]
            else:
                respuesta, modelo = cached, "cache"
            logger.info(f"Cache: usando respuesta guardada ({len(respuesta)} chars)")
            return respuesta, modelo

        logger.info(f"IA: {len(system)} + {len(user)} chars (sin cache)")

        if not self.groq:
            return "<paciente>ERROR</paciente><argumento>API key no configurada</argumento>", "error"

        try:
            content, modelo = await self._llamar_groq_con_retry(system, user)
            _CACHE_IA[clave_cache] = (content, modelo)
            return content, modelo
        except Exception as e:
            logger.error(f"IA Error Groq: {e}")
            if self.anthropic_key:
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={
                                "x-api-key": self.anthropic_key,
                                "anthropic-version": "2023-06-01",
                                "content-type": "application/json"
                            },
                            json={
                                "model": "claude-sonnet-4-5",
                                "max_tokens": 2500,
                                "system": system,
                                "messages": [{"role": "user", "content": user}]
                            }
                        )
                        data = resp.json()
                        if "content" in data:
                            content = data["content"][0]["text"]
                            _CACHE_IA[clave_cache] = (content, "anthropic/claude")
                            return content, "anthropic/claude"
                except Exception as e2:
                    logger.error(f"Fallback Anthropic error: {e2}")
            return f"<paciente>ERROR</paciente><argumento>{str(e)}</argumento>", "error"
