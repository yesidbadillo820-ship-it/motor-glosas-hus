from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

NIT_HUS = "900006037"
DIAS_LIMITE = 20

CONCEPTOS = {
    "RE9502": "La glosa no procede por haber sido generada fuera de los términos establecidos por la Ley configurándose la aceptación tácita de la factura de venta en salud",
    "RE9602": "La glosa es injustificada - Se aporta evidencia de que la glosa es injustificada al 100%",
    "RE9701": "Devolución aceptada al 100%",
    "RE9702": "Glosa aceptada al 100%",
    "RE9801": "Glosa aceptada y subsanada parcialmente",
    "RE9901": "Glosa no aceptada - Subsanada en su totalidad",
}

MOTIVOS_SALUD_TOTAL = {
    "TARIFA": "ESE HUS RECHAZA LA GLOSA POR TARIFAS. LA LIQUIDACIÓN SE REALIZÓ CONFORME AL CONTRATO VIGENTE Y AL MANUAL TARIFARIO SOAT (RES. 054/2026). LA EPS NO PUEDE APLICAR DESCUENTOS UNILATERALES SIN SOPORTE CONTRACTUAL. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
    "SOPORTE": "ESE HUS RECHAZA LA GLOSA POR SOPORTES. LOS DOCUMENTOS EXIGIDOS POR LA RES. 3047/2008 OBRAN EN LA HISTORIA CLÍNICA (RES. 1995/1999), PLENA PRUEBA MÉDICO-LEGAL. LOS ERRORES FORMALES SON SUBSANABLES (CIRCULAR 030/2013). SE EXIGE EL LEVANTAMIENTO INMEDIATO. CARTERA@HUS.GOV.CO",
    "AUTORIZACION": "ESE HUS RECHAZA LA GLOSA POR AUTORIZACIÓN. LA ATENCIÓN PRESTADA CUMPLIÓ CON LOS PROTOCOLOS ESTABLECIDOS. ART. 168 LEY 100/1993 Y T-1025/2002. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
    "PERTINENCIA": "ESE HUS RECHAZA LA GLOSA POR PERTINENCIA. EL CRITERIO MÉDICO ES AUTÓNOMO (ART. 17 LEY 1751/2015 - T-478/1995). LA HISTORIA CLÍNICA DOCUMENTA LA INDICACIÓN. EL AUDITOR DE LA EPS NO REEMPLAZA AL MÉDICO TRATANTE. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
    "COBERTURA": "ESE HUS RECHAZA LA GLOSA POR COBERTURA. EL SERVICIO ESTÁ INCLUIDO EN EL PLAN DE BENEFICIOS (RES. 5269/2017). LAS EXCLUSIONES SON TAXATIVAS. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
    "FACTURACION": "ESE HUS RECHAZA LA GLOSA POR FACTURACIÓN. LOS ERRORES FORMALES SON SUBSANABLES Y NO CONSTITUYEN CAUSAL DE GLOSA (CIRCULAR 030/2013). LA PRESTACIÓN DEL SERVICIO GENERA LA OBLIGACIÓN DE PAGO. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
}

def _detectar_tipo_motivo(descripcion_motivo: str, motv_glosa: str) -> str:
    """Identifica el tipo de motivo desde la descripción real del archivo TXT."""
    texto = (descripcion_motivo + ' ' + motv_glosa).upper()
    if any(k in texto for k in ['TARIFA', 'PRECIO', 'VALOR', 'COSTO']):
        return 'TARIFA'
    if any(k in texto for k in ['SOPORTE', 'DOCUMENTO', 'HISTORIA', 'FACTURA', 'FIRMA']):
        return 'SOPORTE'
    if any(k in texto for k in ['AUTORIZA', 'ORDEN', 'REMISION']):
        return 'AUTORIZACION'
    if any(k in texto for k in ['PERTINEN', 'INDICACION', 'NECESIDAD', 'CLINICO']):
        return 'PERTINENCIA'
    if any(k in texto for k in ['COBERTURA', 'PBS', 'PLAN', 'BENEFICIO']):
        return 'COBERTURA'
    return 'FACTURACION'

OBS_EXTEMPORANEA = "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. EL PLAZO LEGAL PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES CONTADOS A PARTIR DE LA RECEPCIÓN DE LA FACTURA. AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO."

OBS_RATIFICADA = "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE E INJUSTIFICADA. NO SE EVIDENCIA INCUMPLIMIENTO CONTRACTUAL NI NORMATIVO. SE REQUIERE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO."

OBS_TA_POR_TIPO = {
    "TA": "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. EL PLAZO LEGAL PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES CONTADOS A PARTIR DE LA RECEPCIÓN DE LA FACTURA. AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "FA": "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. EL PLAZO LEGAL PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES CONTADOS A PARTIR DE LA RECEPCIÓN DE LA FACTURA. AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "IN": "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE. NO SE EVIDENCIA INCUMPLIMIENTO DEL CONTRATO O LA NORMATIVA VIGENTE. SE REQUIERE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "AU": "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE. NO SE EVIDENCIA AUTORIZACIÓN DEFICIENTE O INSUFICIENTE. SE REQUIERE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "NA": "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE. NO SE EVIDENCIA NO AFILIACIÓN O PROBLEMAS DE AFILIACIÓN. SE REQUIERE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "NC": "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE. NO SE EVIDENCIA DUPLICIDAD O ERROR EN COBRO. SE REQUIERE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "CM": "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE. NO SE EVIDENCIA CUMPLIMIENTO PARCIAL DEL MANEJO CLÍNICO. SE REQUIERE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "US": "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE. LOS SERVICIOS PRESTADOS FUERON MÉDICAMENTE NECESARIOS Y ADECUADOS. SE REQUIERE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
    "AP": "ESE HUS RECHAZA LA GLOSA COMO IMPROCEDENTE. LOS INSUMOS Y MATERIALES FUERON NECESARIOS Y ADECUADOS PARA LA ATENCIÓN. SE REQUIERE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO.",
}

def es_dia_habil(fecha: datetime) -> bool:
    return fecha.weekday() < 5

def calcular_dias_habiles(fecha_inicio: datetime, fecha_fin: datetime) -> int:
    dias = 0
    actual = fecha_inicio
    while actual <= fecha_fin:
        if es_dia_habil(actual):
            dias += 1
        actual += timedelta(days=1)
    return dias

def parsear_fecha(fecha_str: str) -> datetime:
    fecha_str = fecha_str.strip()
    formatos = [
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]
    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato de fecha no reconocido: {fecha_str}")

class GlosaSaludTotal:
    def __init__(self, campos: List[str], tipo_respuesta: str = "extemporanea", fecha_recepcion: Optional[datetime] = None):
        self.campos = campos
        self.tipo_respuesta = tipo_respuesta
        self.fecha_recepcion = fecha_recepcion
        self.fecha_rad = parsear_fecha(campos[0]) if campos[0] else None
        self.numero_rad = campos[1] if len(campos) > 1 else ""
        self.prefijo_fac = campos[2] if len(campos) > 2 else ""
        self.numero_fac = campos[3] if len(campos) > 3 else ""
        self.numreg = campos[4] if len(campos) > 4 else ""
        self.numero_doc_afl = campos[5] if len(campos) > 5 else ""
        self.nombre_afl = campos[6] if len(campos) > 6 else ""
        self.nap = campos[7] if len(campos) > 7 else ""
        self.nombre_servicio = campos[8] if len(campos) > 8 else ""
        self.valor_total_serv = self._parse_float(campos[9]) if len(campos) > 9 else 0
        self.cantidad_fac = self._parse_float(campos[10]) if len(campos) > 10 else 0
        self.valor_unitario = self._parse_float(campos[11]) if len(campos) > 11 else 0
        self.valor_glosa_final = self._parse_float(campos[12]) if len(campos) > 12 else 0
        self.valor_glosa_total_serv = self._parse_float(campos[13]) if len(campos) > 13 else 0
        self.descripcion_motivo = campos[14] if len(campos) > 14 else ""
        self.observaciones = campos[15] if len(campos) > 15 else ""
        self.cod_motv_glosa_general = campos[16] if len(campos) > 16 else ""
        self.motv_glosa_general = campos[17] if len(campos) > 17 else ""
        self.cod_motv_glosa_espc = campos[18] if len(campos) > 18 else ""
        self.motv_glosa_espc = campos[19] if len(campos) > 19 else ""
        self.descripcion_devolucion = campos[20] if len(campos) > 20 else ""
        self.causal_devolucion = campos[21] if len(campos) > 21 else ""
        self.motivo_devolucion = campos[22] if len(campos) > 22 else ""
        self.valor_bruto_factura = self._parse_float(campos[23]) if len(campos) > 23 else 0

    def _parse_float(self, valor: str) -> float:
        if not valor:
            return 0
        return float(valor.replace(",", ""))

    def dias_transcurridos(self) -> int:
        if self.fecha_recepcion and self.fecha_rad:
            return calcular_dias_habiles(self.fecha_recepcion, self.fecha_rad)
        if not self.fecha_rad:
            return 0
        return calcular_dias_habiles(self.fecha_rad, datetime.now())

    def es_extemporanea(self) -> bool:
        return self.dias_transcurridos() > DIAS_LIMITE

    def obtener_observacion(self) -> str:
        dias = self.dias_transcurridos()
        
        if self.tipo_respuesta == "extemporanea" and dias > DIAS_LIMITE:
            return OBS_EXTEMPORANEA.replace("{DIAS}", str(dias))
        
        if self.tipo_respuesta == "ratificada":
            return OBS_RATIFICADA
        
        # NUEVO: detectar tipo desde el contenido REAL del archivo TXT
        tipo_detectado = _detectar_tipo_motivo(
            self.descripcion_motivo, self.motv_glosa_general
        )
        obs_base = MOTIVOS_SALUD_TOTAL.get(tipo_detectado, MOTIVOS_SALUD_TOTAL['FACTURACION'])
        
        # Personalizar con nombre del servicio
        if self.nombre_servicio:
            return f"{obs_base} SERVICIO: {self.nombre_servicio.upper()}."
        return obs_base

    def generar_respuesta(self) -> Dict[str, Any]:
        dias = self.dias_transcurridos()
        
        if self.tipo_respuesta == "extemporanea":
            if dias > DIAS_LIMITE:
                codigo_respuesta = "RE9502"
                concepto = CONCEPTOS["RE9502"]
                observacion = self.obtener_observacion()
                valor_aceptado = 0
            else:
                codigo_respuesta = "RE9602"
                concepto = CONCEPTOS["RE9602"]
                observacion = self.obtener_observacion()
                valor_aceptado = 0
        elif self.tipo_respuesta == "ratificada":
            codigo_respuesta = "RE9602"
            concepto = CONCEPTOS["RE9602"]
            observacion = self.obtener_observacion()
            valor_aceptado = 0
        else:
            codigo_respuesta = "RE9901"
            concepto = CONCEPTOS["RE9901"]
            observacion = "PENDIENTE DE ANÁLISIS CON IA"
            valor_aceptado = 0

        return {
            "NumeroRad": self.numero_rad,
            "PrefijoFac": self.prefijo_fac,
            "NumeroFac": self.numero_fac,
            "NUMREG": self.numreg,
            "NombreServicio": self.nombre_servicio,
            "ValorGlosaTotalxServ": self.valor_glosa_total_serv,
            "CodMotvGlosaGeneral": self.cod_motv_glosa_general,
            "CodMotvGlosaEspc": self.cod_motv_glosa_espc,
            "ValorAceptadoIPS": valor_aceptado,
            "Codigo_Respuesta_a_glosas": codigo_respuesta,
            "ConceptoRespuesta": concepto,
            "Observacion_IPS": observacion,
            "TipoRespuesta": self.tipo_respuesta,
            "DiasTranscurridos": dias,
        }

def procesar_glosas_salud_total(contenido_txt: str, tipo_respuesta: str = "extemporanea", fecha_recepcion: Optional[datetime] = None) -> List[Dict[str, Any]]:
    lineas = contenido_txt.strip().split("\n")
    if not lineas:
        return []
    
    header = lineas[0].split("|")
    
    respuestas = []
    for linea in lineas[1:]:
        if not linea.strip():
            continue
        campos = linea.split("|")
        glosa = GlosaSaludTotal(campos, tipo_respuesta, fecha_recepcion)
        respuestas.append(glosa.generar_respuesta())
    
    return respuestas

def generar_txt_respuesta(respuestas: List[Dict[str, Any]]) -> str:
    if not respuestas:
        return ""
    
    header = "NumeroRad|PrefijoFac|NumeroFac|NUMREG|NombreServicio|ValorGlosaTotalxServ|CodMotvGlosaGeneral|CodMotvGlosaEspc|ValorAceptadoIPS|Codigo Respuesta a glosas|ConceptoRespuesta|Observacion IPS"
    lineas = [header]
    
    for r in respuestas:
        linea = "|".join([
            str(r.get("NumeroRad", "")),
            str(r.get("PrefijoFac", "")),
            str(r.get("NumeroFac", "")),
            str(r.get("NUMREG", "")),
            str(r.get("NombreServicio", "")),
            str(r.get("ValorGlosaTotalxServ", "")),
            str(r.get("CodMotvGlosaGeneral", "")),
            str(r.get("CodMotvGlosaEspc", "")),
            str(r.get("ValorAceptadoIPS", "")),
            str(r.get("Codigo_Respuesta_a_glosas", "")),
            str(r.get("ConceptoRespuesta", "")),
            str(r.get("Observacion_IPS", "")),
        ])
        lineas.append(linea)
    
    return "\n".join(lineas)

def generar_nombre_archivo(tipo_respuesta: str = "extemporanea") -> str:
    now = datetime.now()
    fecha_str = now.strftime("%d%m%Y")
    sufijo = "1" if tipo_respuesta == "extemporanea" else "2" if tipo_respuesta == "ratificada" else "3"
    return f"RTAGLOSA_{NIT_HUS}_{fecha_str}_{sufijo}.txt"
