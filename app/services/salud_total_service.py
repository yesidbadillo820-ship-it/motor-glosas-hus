from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

from app.services.glosa_service import _suavizar_tono

NIT_HUS = "900006037"
DIAS_LIMITE = 20

CONCEPTOS = {
    "RE9502": "La glosa o devolución no procede por haber sido generada por fuera de los términos establecidos por la Ley, configurándose la aceptación tácita de la factura de venta en salud.",
    "RE9602": "El prestador de servicios de salud o proveedor de tecnologías en salud aporta a la entidad responsable de pago la evidencia que demuestra que la glosa es injustificada al 100%.",
    "RE9701": "La devolución es aceptada al 100% por el prestador de servicios de salud.",
    "RE9702": "La glosa es aceptada al 100% por el prestador de servicios de salud.",
    "RE9801": "La glosa es aceptada y subsanada parcialmente por el prestador de servicios de salud.",
    "RE9901": "El prestador de servicios de salud o proveedor de tecnologías en salud informa a la entidad responsable de pago que la glosa siendo justificada ha podido ser subsanada totalmente.",
}

# Límite OBLIGATORIO según especificación Salud Total para Observacion IPS.
# Salud Total EPS rechaza el archivo TXT si cualquier fila supera los 500
# caracteres en este campo. Para ratificadas se usa una versión COMPACTA
# (OBS_RATIFICADA abajo) adaptada a este tope.
OBS_MAX_CARACTERES = 500

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

OBS_EXTEMPORANEA = "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. CONFORME AL MARCO CONTRACTUAL VIGENTE Y A LA RES. 3047/2008, EL PLAZO APLICABLE PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES DESDE LA RECEPCIÓN DE LA FACTURA (CRITERIO INSTITUCIONAL HUS). AUN CONSIDERANDO EL ART. 57 LEY 1438/2011 (30 DÍAS EPS + 15 DÍAS IPS), LA GLOSA SIGUE SIENDO EXTEMPORÁNEA AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CARTERA@HUS.GOV.CO."

# Version COMPACTA del texto de ratificadas para Salud Total (≤500 chars).
# El texto canonico completo (TEXTO_RATIFICADA, 883 chars) se usa en PDF y
# UI via _dictamen_ratificada. Aqui se adapta para caber en el campo
# Observacion IPS del TXT que exige max 500 chars.
# Mantiene los 4 puntos clave:
#   1. No acepta la glosa ratificada, mantiene respuesta inicial.
#   2. Cita normativa (Art. 57 Ley 1438, Art. 20 Dec. 4747, Res. 2284/2023).
#   3. Solicita mesa de conciliacion.
#   4. Advierte levantamiento tacito + correo institucional.
OBS_RATIFICADA = (
    "ESE HUS NO ACEPTA GLOSA RATIFICADA Y MANTIENE LA RESPUESTA DE LA GLOSA "
    "INICIAL, SUFICIENTEMENTE SUSTENTADA. ART. 57 LEY 1438/2011, ART. 20 DEC. "
    "4747/2007 Y RES. 2284/2023 (MANUAL ÚNICO DE GLOSAS): SE SOLICITA MESA DE "
    "CONCILIACIÓN DE AUDITORÍA MÉDICA/TÉCNICA PARA LLEGAR A UN ACUERDO EN "
    "TÉRMINOS LEGALES. DE NO OBTENERSE RESPUESTA, OPERA EL LEVANTAMIENTO "
    "TÁCITO DE LA OBJECIÓN. CONTACTO: CARTERA@HUS.GOV.CO, "
    "GLOSASYDEVOLUCIONES@HUS.GOV.CO. VENTANILLA: CRA. 33 NO. 28-126 "
    "BUCARAMANGA."
)

OBS_TA_POR_TIPO = {
    "TA": "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. CONFORME AL MARCO CONTRACTUAL VIGENTE Y A LA RES. 3047/2008, EL PLAZO APLICABLE PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES DESDE LA RECEPCIÓN DE LA FACTURA (CRITERIO INSTITUCIONAL HUS). AUN CONSIDERANDO EL ART. 57 LEY 1438/2011 (30 DÍAS EPS + 15 DÍAS IPS), LA GLOSA SIGUE SIENDO EXTEMPORÁNEA AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CARTERA@HUS.GOV.CO.",
    "FA": "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. CONFORME AL MARCO CONTRACTUAL VIGENTE Y A LA RES. 3047/2008, EL PLAZO APLICABLE PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES DESDE LA RECEPCIÓN DE LA FACTURA (CRITERIO INSTITUCIONAL HUS). AUN CONSIDERANDO EL ART. 57 LEY 1438/2011 (30 DÍAS EPS + 15 DÍAS IPS), LA GLOSA SIGUE SIENDO EXTEMPORÁNEA AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CARTERA@HUS.GOV.CO.",
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
        # Con AM/PM
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %I:%M %p",
        # 24h con segundos
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        # 24h sin segundos (ej. "3/11/2026 6:53")
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M",
        # Solo fecha
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
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

    def _argumento_tecnico_por_codigo(self, codigo_respuesta: str = "RE9901") -> str:
        """Genera el argumento técnico-jurídico por código de glosa Salud Total.

        REGLA: La Observación IPS debe caber en ≤500 caracteres (OBS_MAX_CARACTERES).
        Las plantillas están calibradas para quedar dentro del límite incluso con
        el nombre del servicio. Si el servicio es muy largo, se trunca.

        El calificativo inicial se alinea con el código de respuesta:
          - RE9502 → "GLOSA EXTEMPORÁNEA"
          - RE9602 → "GLOSA INJUSTIFICADA"
          - RE9901 → "GLOSA" (subsanada en su totalidad)
        """
        cod = (self.cod_motv_glosa_general or "").upper().strip()
        cod_esp = (self.cod_motv_glosa_espc or "").upper().strip()
        codigo_glosa = cod_esp or cod or "GENERAL"
        # Recortar servicio para no desbordar 500 chars
        servicio_raw = (self.nombre_servicio or "EL SERVICIO FACTURADO").upper().strip()
        servicio = servicio_raw[:80] if len(servicio_raw) > 80 else servicio_raw

        # Calificativo de apertura según código RE
        CALIFICATIVO = {
            "RE9502": "LA GLOSA EXTEMPORÁNEA",
            "RE9602": "LA GLOSA INJUSTIFICADA",
            "RE9701": "LA DEVOLUCIÓN",
            "RE9702": "LA GLOSA",
            "RE9801": "LA GLOSA",
            "RE9901": "LA GLOSA",
        }
        cal = CALIFICATIVO.get(codigo_respuesta, "LA GLOSA")

        # Plantillas NUEVAS (abr 2026) con estilo TÉCNICO ESPECÍFICO al caso:
        # mencionan los soportes reales del expediente clínico (notas enfermería,
        # kardex, evoluciones, HC, RIPS) en vez de solo citar leyes genericas.
        # Todas ≤ 500 chars incluso con servicio de 80 chars + codigo corto.
        plantillas = {
            "TA": (
                # TARIFAS — NO hay contrato con Salud Total / entidad similar
                # SIEMPRE INJUSTIFICADA: no existe tarifa pactada, rige SOAT pleno.
                f"ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE TARIFAS {codigo_glosa} "
                f"SOBRE {servicio}, CONSIDERADA INJUSTIFICADA al no existir "
                "contrato vigente entre las partes que contemple tarifas pactadas "
                "distintas al Manual SOAT vigente (Resolución 054/2026; Decreto "
                "2423/1996). El valor cobrado corresponde a tarifa SOAT plena, "
                "sin descuentos unilaterales admisibles (Art. 871 C.Comercio). "
                "Se solicita el reconocimiento íntegro. CARTERA@HUS.GOV.CO"
            ),
            "SO": (
                # SOPORTES — evidencia en HC + RIPS
                f"ESE HUS NO ACEPTA {cal} POR SOPORTES {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en historia clínica, RIPS y evoluciones médicas del "
                "expediente clínico, donde consta la prestación efectiva del "
                "servicio y todos los soportes requeridos conforme a la Resolución "
                "3047/2008. Se solicita el levantamiento de la glosa. "
                "CARTERA@HUS.GOV.CO"
            ),
            "AU": (
                # AUTORIZACION — urgencia documentada
                f"ESE HUS NO ACEPTA {cal} POR AUTORIZACIÓN {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en nota de urgencias y evoluciones del expediente "
                "clínico que documentan la atención prestada bajo condición de "
                "urgencia vital. La atención no requiere autorización previa "
                "(Art. 168 Ley 100/1993). Se solicita el levantamiento. "
                "CARTERA@HUS.GOV.CO"
            ),
            "CO": (
                # COBERTURA — PBS
                f"ESE HUS NO ACEPTA {cal} POR COBERTURA {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en historia clínica y orden médica del expediente "
                "clínico, donde consta que el servicio facturado está incluido en "
                "el Plan de Beneficios en Salud (Res. 5269/2017) y no corresponde "
                "a exclusión taxativa. Se solicita el levantamiento. "
                "CARTERA@HUS.GOV.CO"
            ),
            "CL": (
                # PERTINENCIA (clínica)
                f"ESE HUS NO ACEPTA {cal} POR PERTINENCIA {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en historia clínica, evoluciones médicas y órdenes "
                "del médico tratante en el expediente, donde consta la indicación "
                "clínica del servicio. La autonomía médica (Art. 17 Ley 1751/2015) "
                "prevalece. Se solicita el levantamiento. CARTERA@HUS.GOV.CO"
            ),
            "PE": (
                # PERTINENCIA (variante)
                f"ESE HUS NO ACEPTA {cal} POR PERTINENCIA {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en historia clínica y evoluciones médicas del "
                "expediente que documentan la indicación clínica suscrita por el "
                "médico tratante. La autonomía profesional (Art. 17 Ley 1751/2015) "
                "respalda la conducta. Se solicita el levantamiento. "
                "CARTERA@HUS.GOV.CO"
            ),
            "FA": (
                # FACTURACION — notas enfermería + kardex + evoluciones
                f"ESE HUS NO ACEPTA {cal} POR FACTURACIÓN {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en notas de enfermería, kardex de medicamentos y "
                "evoluciones médicas del expediente clínico, donde consta la "
                "prescripción, preparación y aplicación del servicio facturado, "
                "conforme a Resolución 3047/2008. Se solicita el levantamiento "
                "de la glosa. CARTERA@HUS.GOV.CO"
            ),
            "IN": (
                # INSUMOS — nota operatoria + kardex
                f"ESE HUS NO ACEPTA {cal} POR INSUMOS {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en nota operatoria, historia clínica y kardex del "
                "expediente, donde consta el uso efectivo del insumo durante el "
                "procedimiento. Los insumos son inherentes al acto médico "
                "(Dec. 780/2016). Se solicita el levantamiento. "
                "CARTERA@HUS.GOV.CO"
            ),
            "ME": (
                # MEDICAMENTOS — fórmula + kardex + notas + evoluciones
                f"ESE HUS NO ACEPTA {cal} POR MEDICAMENTOS {codigo_glosa} SOBRE {servicio}, "
                "evidenciado en fórmula médica, kardex, notas de enfermería y "
                "evoluciones del expediente clínico, donde consta la prescripción, "
                "dispensación y administración del medicamento facturado. "
                "Se solicita el levantamiento. CARTERA@HUS.GOV.CO"
            ),
        }
        # Primero prueba por código específico (TA02, FA01, etc), luego general
        for key in (cod_esp[:2] if cod_esp else "", cod[:2] if cod else ""):
            if key in plantillas:
                return plantillas[key]
        # Fallback por tipo detectado desde el texto
        tipo_detectado = _detectar_tipo_motivo(
            self.descripcion_motivo, self.motv_glosa_general
        )
        mapeo = {"TARIFA":"TA","SOPORTE":"SO","AUTORIZACION":"AU",
                 "PERTINENCIA":"CL","COBERTURA":"CO","FACTURACION":"FA"}
        return plantillas.get(mapeo.get(tipo_detectado, "FA"), plantillas["FA"])

    def generar_respuesta(self) -> Dict[str, Any]:
        dias = self.dias_transcurridos()

        # REGLA SALUD TOTAL: NO hay contrato vigente con Salud Total EPS, por lo
        # que las glosas por TARIFAS (TA*) son INJUSTIFICADAS al 100% → RE9602.
        cod_general = (self.cod_motv_glosa_general or "").upper().strip()
        cod_espc = (self.cod_motv_glosa_espc or "").upper().strip()
        es_tarifa = cod_general.startswith("TA") or cod_espc.startswith("TA")

        if self.tipo_respuesta == "extemporanea":
            if dias > DIAS_LIMITE:
                codigo_respuesta = "RE9502"
                observacion = self.obtener_observacion()
                valor_aceptado = 0
            else:
                codigo_respuesta = "RE9602"
                observacion = self.obtener_observacion()
                valor_aceptado = 0
        elif self.tipo_respuesta == "ratificada":
            codigo_respuesta = "RE9602"
            observacion = self.obtener_observacion()
            valor_aceptado = 0
        elif es_tarifa:
            # Tarifas sin contrato → injustificada al 100%
            codigo_respuesta = "RE9602"
            observacion = self._argumento_tecnico_por_codigo(codigo_respuesta)
            valor_aceptado = 0
        else:
            # Otros tipos → glosa subsanada en su totalidad con argumento
            codigo_respuesta = "RE9901"
            observacion = self._argumento_tecnico_por_codigo(codigo_respuesta)
            valor_aceptado = 0

        concepto = CONCEPTOS[codigo_respuesta]
        observacion = _suavizar_tono(observacion)

        # Límite OBLIGATORIO 500 caracteres para Observacion IPS (Salud Total).
        # Recortamos de forma inteligente: buscamos último punto antes del límite
        # para que el texto cierre correctamente.
        if len(observacion) > OBS_MAX_CARACTERES:
            recorte = observacion[:OBS_MAX_CARACTERES]
            ultimo_punto = max(recorte.rfind(". "), recorte.rfind(".\n"))
            if ultimo_punto > OBS_MAX_CARACTERES * 0.7:
                observacion = recorte[:ultimo_punto + 1]
            else:
                observacion = recorte.rstrip() + "."

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

def _detectar_separador(primera_linea: str) -> str:
    """Auto-detecta el separador del archivo TXT.

    Salud Total acepta 2 formatos:
      • Pipe "|" (formato canónico histórico).
      • Tab "\\t" (export directo desde Excel con los headers FechaRad_,
        NumeroRad_, etc.).
    Se prefiere el que más ocurrencias tenga en la primera línea.
    """
    tabs = primera_linea.count("\t")
    pipes = primera_linea.count("|")
    if tabs > pipes:
        return "\t"
    if pipes > 0:
        return "|"
    # Fallback: si no hay ni tabs ni pipes, intenta tab (común en export Excel)
    return "\t"


def procesar_glosas_salud_total(contenido_txt: str, tipo_respuesta: str = "extemporanea", fecha_recepcion: Optional[datetime] = None) -> List[Dict[str, Any]]:
    lineas = contenido_txt.strip().split("\n")
    if not lineas:
        return []

    # Auto-detectar separador (pipe "|" o tab "\t")
    sep = _detectar_separador(lineas[0])

    header = lineas[0].split(sep)

    respuestas = []
    errores: list[str] = []
    for idx, linea in enumerate(lineas[1:], start=2):
        if not linea.strip():
            continue
        campos = linea.split(sep)
        # Validación: mínimo 14 columnas para que la glosa tenga datos básicos
        # (fecha + factura + servicio + valor_glosa_final).
        if len(campos) < 14:
            errores.append(f"Fila {idx}: solo {len(campos)} columnas (esperadas ≥14, separador detectado: {'TAB' if sep == chr(9) else 'PIPE'})")
            continue
        try:
            glosa = GlosaSaludTotal(campos, tipo_respuesta, fecha_recepcion)
            respuestas.append(glosa.generar_respuesta())
        except Exception as e:
            errores.append(f"Fila {idx}: {type(e).__name__}: {e}")
            continue

    # Si NADA se pudo parsear, arrojar con detalle para que el front no caiga
    # en un 500 sin información útil.
    if not respuestas and errores:
        raise ValueError(
            "No se pudo procesar ninguna línea del archivo. "
            "Separador detectado: " + ("TAB" if sep == "\t" else "PIPE") +
            ". Primeros errores: " + " | ".join(errores[:3])
        )
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
