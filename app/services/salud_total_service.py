from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.services.glosa_service import _suavizar_tono
from app.utils.moneda import parse_valor_cop

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
    # Texto REAL que radica el HUS para Salud Total (archivo OK del 10-08-2026).
    # ANTES decía "CONFORME AL CONTRATO VIGENTE": era falso — con Salud Total
    # NO hay contrato, y afirmarlo en un documento que se radica le regala a la
    # entidad el argumento de que sí lo había. Ahora dice la verdad: sin
    # contrato, se factura a SOAT vigente y los insumos a tarifas institucionales.
    "TARIFA": "ESE HUS NO ACEPTA GLOSA INJUSTIFICADA POR MVC EN TARIFAS, ENTIDAD SALUD TOTAL SIN CONTRATO VIGENTE ENTRE LAS PARTES AL MOMENTO DE LA ATENCION, POR LO TANTO, SE FACTURA A SOAT VIGENTE Y LOS INSUMOS Y O MEDICAMENTOS SE FACTURAN A TARIFAS INSTITUCIONALES. NOTA: SEGÚN NORMATIVIDAD VIGENTE DE NO OBTENERSE RATIFICACIÓN DE LA GLOSA EN LOS TÉRMINOS LEGALES, SE DARÁ POR LEVANTADA LA OBJECIÓN DE ACUERDO ARTÍCULO 57 DE LA LEY 1438 DE 2011",
    # Texto REAL del HUS para soportes (archivo OK). Postura de subsanación:
    # los soportes van adjuntos a la factura, se soportan de nuevo → RE9901.
    "SOPORTE": "ESE HUS NO ACEPTA GLOSA SE REVISA Y SE EVIDENCIA SOPORTES ADJUNTOS A LA FACTURA RADICADA A LA ENTIDAD SE SOPORTA NUEVAMENTE PARA LA SUBSANACION DE LA GLOSA. NOTA: DE ACUERDO AL ARTÍCULO 57 DE LA LEY 1438 DE 2011, DE NO OBTENERSE RATIFICACIÓN DE LA RESPUESTA A LA GLOSA EN LOS TÉRMINOS ESTABLECIDOS, SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN",
    "AUTORIZACION": "ESE HUS RECHAZA LA GLOSA POR AUTORIZACIÓN. LA ATENCIÓN PRESTADA CUMPLIÓ CON LOS PROTOCOLOS ESTABLECIDOS. ART. 168 LEY 100/1993 Y ART. 20 DECRETO 4747/2007. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
    "PERTINENCIA": "ESE HUS RECHAZA LA GLOSA POR PERTINENCIA. EL CRITERIO MÉDICO ES AUTÓNOMO (ART. 17 LEY 1751/2015). LA HISTORIA CLÍNICA DOCUMENTA LA INDICACIÓN. EL AUDITOR DE LA EPS NO REEMPLAZA AL MÉDICO TRATANTE. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
    "COBERTURA": "ESE HUS RECHAZA LA GLOSA POR COBERTURA. EL SERVICIO ESTÁ INCLUIDO EN EL PLAN DE BENEFICIOS (RES. 5269/2017). LAS EXCLUSIONES SON TAXATIVAS. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
    "FACTURACION": "ESE HUS RECHAZA LA GLOSA POR FACTURACIÓN. LOS ERRORES FORMALES SON SUBSANABLES Y NO CONSTITUYEN CAUSAL DE GLOSA (CIRCULAR 030/2013). LA PRESTACIÓN DEL SERVICIO GENERA LA OBLIGACIÓN DE PAGO. SE EXIGE EL PAGO ÍNTEGRO. CARTERA@HUS.GOV.CO",
}


def _detectar_tipo_motivo(descripcion_motivo: str, motv_glosa: str) -> str:
    """Identifica el tipo de motivo desde la descripción real del archivo TXT."""
    texto = (descripcion_motivo + " " + motv_glosa).upper()
    if any(k in texto for k in ["TARIFA", "PRECIO", "VALOR", "COSTO"]):
        return "TARIFA"
    if any(k in texto for k in ["SOPORTE", "DOCUMENTO", "HISTORIA", "FACTURA", "FIRMA"]):
        return "SOPORTE"
    if any(k in texto for k in ["AUTORIZA", "ORDEN", "REMISION"]):
        return "AUTORIZACION"
    if any(k in texto for k in ["PERTINEN", "INDICACION", "NECESIDAD", "CLINICO"]):
        return "PERTINENCIA"
    if any(k in texto for k in ["COBERTURA", "PBS", "PLAN", "BENEFICIO"]):
        return "COBERTURA"
    return "FACTURACION"


OBS_EXTEMPORANEA = "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. CONFORME AL MARCO CONTRACTUAL VIGENTE Y A LA RES. 3047/2008, EL PLAZO APLICABLE PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES DESDE LA RECEPCIÓN DE LA FACTURA (CRITERIO INSTITUCIONAL HUS). CONFORME AL ART. 57 LEY 1438/2011 OPERACIONALIZADO POR EL MANUAL ÚNICO RES. 2284/2023 (20 DÍAS EPS FORMULAR | 15 DÍAS IPS RESPONDER | 10 DÍAS EPS DECIDIR), LA GLOSA ES EXTEMPORÁNEA AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CARTERA@HUS.GOV.CO."

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
    "TA": "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. CONFORME AL MARCO CONTRACTUAL VIGENTE Y A LA RES. 3047/2008, EL PLAZO APLICABLE PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES DESDE LA RECEPCIÓN DE LA FACTURA (CRITERIO INSTITUCIONAL HUS). CONFORME AL ART. 57 LEY 1438/2011 OPERACIONALIZADO POR EL MANUAL ÚNICO RES. 2284/2023 (20 DÍAS EPS FORMULAR | 15 DÍAS IPS RESPONDER | 10 DÍAS EPS DECIDIR), LA GLOSA ES EXTEMPORÁNEA AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CARTERA@HUS.GOV.CO.",
    "FA": "ESE HUS RECHAZA LA GLOSA COMO EXTEMPORÁNEA E IMPROCEDENTE. CONFORME AL MARCO CONTRACTUAL VIGENTE Y A LA RES. 3047/2008, EL PLAZO APLICABLE PARA QUE LA EPS FORMULE GLOSAS ES DE 20 DÍAS HÁBILES DESDE LA RECEPCIÓN DE LA FACTURA (CRITERIO INSTITUCIONAL HUS). CONFORME AL ART. 57 LEY 1438/2011 OPERACIONALIZADO POR EL MANUAL ÚNICO RES. 2284/2023 (20 DÍAS EPS FORMULAR | 15 DÍAS IPS RESPONDER | 10 DÍAS EPS DECIDIR), LA GLOSA ES EXTEMPORÁNEA AL HABERSE SUPERADO ESTE PLAZO (HAN TRANSCURRIDO {DIAS} DÍAS HÁBILES). SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD DE LAS GLOSAS. CARTERA@HUS.GOV.CO.",
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
    def __init__(
        self,
        campos: List[str],
        tipo_respuesta: str = "extemporanea",
        fecha_recepcion: Optional[datetime] = None,
    ):
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
        """Lee un valor en pesos del TXT con el lector único del repo.

        18-08-2026. Antes hacía `float(valor.replace(",", ""))`. Eso solo
        sirve para el formato gringo (280000.00). Si el portal manda el valor
        a la colombiana leía mal o se caía:
            "280.000"      -> 280.0        (mil veces menos)
            "1.589.100,00" -> se reventaba
        Y esos valores alimentan los totales de la pantalla y el archivo que
        se radica. `parse_valor_cop` entiende los dos formatos y deja el
        actual igual (280000.00 -> 280000.0)."""
        return parse_valor_cop(valor)

    @property
    def sin_fecha_recepcion(self) -> bool:
        """No hay con qué contar el plazo del Art. 57 de la Ley 1438/2011.

        El plazo corre desde que la EPS RECIBE la factura hasta que radica
        la glosa. Sin la fecha de recepción no existe el punto de partida.
        """
        if not (self.fecha_recepcion and self.fecha_rad):
            return True
        # La EPS no puede glosar una factura antes de recibirla. Si las dos
        # fechas vienen al revés, el dato está mal digitado y no sirve para
        # contar el plazo: se trata igual que si no estuviera.
        return self.fecha_recepcion > self.fecha_rad

    def dias_transcurridos(self) -> int:
        """Días hábiles entre la recepción de la factura y la radicación.

        Si falta la fecha de recepción devuelve 0 y NO se alega
        extemporaneidad. Antes se contaba desde la radicación de la glosa
        hasta HOY, que es un intervalo que no mide ningún plazo legal: una
        notificación de julio respondida en agosto daba «han transcurrido
        X días hábiles» y con eso se afirmaba en un documento radicable un
        hecho que nadie había comprobado. Cuando no hay evidencia, no se
        afirma: se responde de fondo.
        """
        if self.sin_fecha_recepcion:
            return 0
        return calcular_dias_habiles(self.fecha_recepcion, self.fecha_rad)

    def es_extemporanea(self) -> bool:
        return self.dias_transcurridos() > DIAS_LIMITE

    def obtener_observacion(self) -> str:
        dias = self.dias_transcurridos()

        if self.tipo_respuesta == "extemporanea" and dias > DIAS_LIMITE:
            return OBS_EXTEMPORANEA.replace("{DIAS}", str(dias))

        if self.tipo_respuesta == "ratificada":
            return OBS_RATIFICADA

        # NUEVO: detectar tipo desde el contenido REAL del archivo TXT
        tipo_detectado = _detectar_tipo_motivo(self.descripcion_motivo, self.motv_glosa_general)
        obs_base = MOTIVOS_SALUD_TOTAL.get(tipo_detectado, MOTIVOS_SALUD_TOTAL["FACTURACION"])

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

        # Calificativo de apertura según código RE.
        # REGLA DE NEGOCIO (abr 2026): "LA GLOSA INJUSTIFICADA" SÍ aplica
        # cuando la entidad NO tiene contrato y glosa por TARIFAS (TA**) —
        # porque sin contrato no existe tarifa pactada y la objeción carece
        # de sustento. Este servicio (salud_total_service) está dedicado a
        # entidades SIN contrato (Salud Total, Dispensarios, Sanidad
        # Militar, etc.), por lo que RE9602 → "LA GLOSA INJUSTIFICADA" es
        # correcto aquí. Para entidades CON contrato se usa RE9901 con
        # argumento técnico, NO RE9602 (lo enruta otro flujo).
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
                "distintas al Manual Tarifario SOAT 2026 (Circular 047/2025 MinSalud "
                "indexado a UVB — UVB 2026 $12.110; Decreto 780/2016). El valor "
                "cobrado corresponde a tarifa SOAT plena, "
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
        tipo_detectado = _detectar_tipo_motivo(self.descripcion_motivo, self.motv_glosa_general)
        mapeo = {
            "TARIFA": "TA",
            "SOPORTE": "SO",
            "AUTORIZACION": "AU",
            "PERTINENCIA": "CL",
            "COBERTURA": "CO",
            "FACTURACION": "FA",
        }
        return plantillas.get(mapeo.get(tipo_detectado, "FA"), plantillas["FA"])

    def _familia(self) -> str:
        """Familia del motivo de glosa: TA, FA, SO, CL, AU, CO (Res. 2284/2023).
        Se toma del código general, y si no viene, del específico."""
        cg = (self.cod_motv_glosa_general or "").upper().strip()
        ce = (self.cod_motv_glosa_espc or "").upper().strip()
        return cg[:2] or ce[:2] or "FA"

    def _respuesta_de_fondo(self) -> tuple[str, str]:
        """La respuesta de fondo de Salud Total (entidad SIN contrato), por
        familia de motivo. Reproduce lo que el HUS radica de verdad
        (archivo OK del 10-08-2026):

          • TA (tarifas) y FA (facturación) → RE9602 «injustificada al 100%»:
            sin contrato, se factura a SOAT vigente / tarifas institucionales.
          • SO (soportes) y CL (pertinencia) → RE9901 «subsanada»: los soportes
            van adjuntos, se soporta de nuevo.
          • AU/CO: sin ejemplo real; se mantienen como subsanables (RE9901).

        El texto sale por familia de MOTIVOS_SALUD_TOTAL, SIN pegarle el nombre
        del servicio: el archivo real no lo lleva y el campo tiene tope de 500.
        """
        fam = self._familia()
        codigo = "RE9602" if fam in ("TA", "FA") else "RE9901"
        clave_texto = {
            "TA": "TARIFA",
            "FA": "FACTURACION",
            "SO": "SOPORTE",
            "CL": "PERTINENCIA",
            "AU": "AUTORIZACION",
            "CO": "COBERTURA",
        }.get(fam, "FACTURACION")
        observacion = MOTIVOS_SALUD_TOTAL.get(clave_texto, MOTIVOS_SALUD_TOTAL["FACTURACION"])
        return codigo, observacion

    def generar_respuesta(self) -> Dict[str, Any]:
        dias = self.dias_transcurridos()
        valor_aceptado = 0

        if self.tipo_respuesta == "extemporanea" and dias > DIAS_LIMITE:
            # Solo cuando hay evidencia del plazo vencido se alega extemporaneidad.
            codigo_respuesta = "RE9502"
            observacion = self.obtener_observacion()
        elif self.tipo_respuesta == "ratificada":
            codigo_respuesta = "RE9602"
            observacion = self.obtener_observacion()
        else:
            # Respuesta de fondo por familia: es lo que el HUS radica de verdad
            # para Salud Total. Cubre la opción "extemporánea" cuando no se puede
            # sustentar el plazo (sin fecha o dentro de términos).
            codigo_respuesta, observacion = self._respuesta_de_fondo()

        concepto = CONCEPTOS[codigo_respuesta]
        observacion = _suavizar_tono(observacion)

        # Límite OBLIGATORIO 500 caracteres para Observacion IPS (Salud Total).
        # Recortamos de forma inteligente: buscamos último punto antes del límite
        # para que el texto cierre correctamente.
        if len(observacion) > OBS_MAX_CARACTERES:
            recorte = observacion[:OBS_MAX_CARACTERES]
            ultimo_punto = max(recorte.rfind(". "), recorte.rfind(".\n"))
            if ultimo_punto > OBS_MAX_CARACTERES * 0.7:
                observacion = recorte[: ultimo_punto + 1]
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
            # Para que la pantalla avise: sin este dato no se puede alegar
            # extemporaneidad, y la respuesta salió argumentada de fondo.
            "SinFechaRecepcion": self.sin_fecha_recepcion,
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


def procesar_glosas_salud_total(
    contenido_txt: str,
    tipo_respuesta: str = "extemporanea",
    fecha_recepcion: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    lineas = contenido_txt.strip().split("\n")
    if not lineas:
        return []

    # Auto-detectar separador (pipe "|" o tab "\t")
    sep = _detectar_separador(lineas[0])

    respuestas = []
    errores: list[str] = []
    for idx, linea in enumerate(lineas[1:], start=2):
        if not linea.strip():
            continue
        campos = linea.split(sep)
        # Validación: mínimo 14 columnas para que la glosa tenga datos básicos
        # (fecha + factura + servicio + valor_glosa_final).
        if len(campos) < 14:
            errores.append(
                f"Fila {idx}: solo {len(campos)} columnas (esperadas ≥14, separador detectado: {'TAB' if sep == chr(9) else 'PIPE'})"
            )
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
            "Separador detectado: "
            + ("TAB" if sep == "\t" else "PIPE")
            + ". Primeros errores: "
            + " | ".join(errores[:3])
        )
    return respuestas


def _pesos(valor: Any) -> str:
    """Escribe un valor de peso como lo escribe la entidad: sin el «.0».

    La notificación trae «93340» y Python venía escribiendo «93340.0» por ser
    float. Se mantiene el decimal solo cuando el valor de verdad lo tiene.
    """
    try:
        n = float(valor or 0)
    except (TypeError, ValueError):
        return str(valor or "")
    return str(int(n)) if n == int(n) else f"{n:.2f}"


def _una_linea(texto: Any) -> str:
    """Aplana el texto a una sola línea.

    Un salto de línea dentro de la Observación parte la fila en dos y la
    entidad recibe un archivo con más filas que glosas.
    """
    return " ".join(str(texto or "").split())


def generar_txt_respuesta(respuestas: List[Dict[str, Any]]) -> str:
    if not respuestas:
        return ""

    header = "NumeroRad|PrefijoFac|NumeroFac|NUMREG|NombreServicio|ValorGlosaTotalxServ|CodMotvGlosaGeneral|CodMotvGlosaEspc|ValorAceptadoIPS|Codigo Respuesta a glosas|ConceptoRespuesta|Observacion IPS"
    lineas = [header]

    for r in respuestas:
        linea = "|".join(
            [
                str(r.get("NumeroRad", "")),
                str(r.get("PrefijoFac", "")),
                str(r.get("NumeroFac", "")),
                str(r.get("NUMREG", "")),
                _una_linea(r.get("NombreServicio", "")),
                _pesos(r.get("ValorGlosaTotalxServ", "")),
                str(r.get("CodMotvGlosaGeneral", "")),
                str(r.get("CodMotvGlosaEspc", "")),
                _pesos(r.get("ValorAceptadoIPS", "")),
                str(r.get("Codigo_Respuesta_a_glosas", "")),
                _una_linea(r.get("ConceptoRespuesta", "")),
                _una_linea(r.get("Observacion_IPS", "")),
            ]
        )
        lineas.append(linea)

    return "\n".join(lineas)


# Signos Unicode que NO existen en Windows-1252 y que la IA suele meter
# (guiones largos, comillas curvas, puntos suspensivos). Se transliteran para
# no perder el signo cuando se pasa a ANSI.
_TRANSLIT_PORTAL = {
    "\u2014": "-",
    "\u2013": "-",
    "\u2012": "-",
    "\u2011": "-",
    "\u2010": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u2022": "-",
    "\u00a0": " ",
}


def a_bytes_portal(texto: str) -> bytes:
    """Codifica la respuesta como la espera el portal de Salud Total.

    18-08-2026. El portal lee el TXT en ANSI (Windows-1252): el archivo que el
    HUS sube y que SÍ funciona está en ese formato. El sistema venía enviando
    UTF-8, así que en el portal los acentos salían rotos: «clínica» se veía
    «clÃ­nica» y «CÓDIGO» «CÃDIGO», en un documento que se radica.

    Se transliteran primero los signos Unicode que no existen en 1252 (los que
    mete la IA: guiones largos, comillas curvas) y lo que aún no encaje se
    reemplaza en vez de reventar la descarga.
    """
    for uni, ascii_ in _TRANSLIT_PORTAL.items():
        texto = texto.replace(uni, ascii_)
    return texto.encode("cp1252", errors="replace")


def generar_nombre_archivo(tipo_respuesta: str = "extemporanea") -> str:
    now = datetime.now()
    fecha_str = now.strftime("%d%m%Y")
    sufijo = (
        "1" if tipo_respuesta == "extemporanea" else "2" if tipo_respuesta == "ratificada" else "3"
    )
    return f"RTAGLOSA_{NIT_HUS}_{fecha_str}_{sufijo}.txt"


# ─────────────────────────────────────────────────────────────────────────
# Lectura de la notificación a diccionarios (OT-045)
#
# El camino por plantilla lee el TXT por posición y va directo a la
# respuesta. El camino por IA necesita algo distinto: cada glosa como un
# diccionario con nombre y apellido, para armar con ella el texto que el
# motor analiza. Se lee UNA vez y se reparte, en vez de abrir el archivo dos
# veces con dos lectores que podrían separarse.
# ─────────────────────────────────────────────────────────────────────────

CABECERA_ESPERADA = ("NumeroRad_", "Numreg")


def leer_notificacion_dict(contenido: bytes) -> tuple[List[Dict[str, Any]], List[str]]:
    """Lee el TXT de la notificación y devuelve (glosas, avisos).

    Las notificaciones de Salud Total vienen en latin-1: leerlas como UTF-8
    parte las tildes de los nombres y de los motivos.

    El radicado y el registro viajan como TEXTO de principio a fin.
    Convertirlos a número fue lo que produjo «3,5E+14» en el archivo del
    13-08 y lo dejó inservible: la entidad no puede casar ninguna respuesta
    con su glosa.
    """
    avisos: List[str] = []
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = contenido.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        return [], ["El archivo no se pudo leer: no está en UTF-8 ni en latin-1."]

    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if len(lineas) < 2:
        return [], ["El archivo no tiene filas de glosa debajo del encabezado."]

    sep = _detectar_separador(lineas[0])
    cabecera = [c.strip() for c in lineas[0].split(sep)]
    if not all(c in cabecera for c in CABECERA_ESPERADA):
        return [], [
            "El encabezado no corresponde a una notificación de Salud Total "
            "(faltan NumeroRad_ o Numreg)."
        ]

    def _num(v) -> float:
        try:
            return float(str(v or "0").replace(",", "").strip() or 0)
        except ValueError:
            return 0.0

    glosas: List[Dict[str, Any]] = []
    for n, linea in enumerate(lineas[1:], start=2):
        campos = linea.split(sep)
        if len(campos) < 14:
            avisos.append(f"Línea {n}: tiene {len(campos)} campos y se esperaban 14 o más.")
            continue
        f = dict(zip(cabecera, campos))
        glosas.append(
            {
                "FechaRad": (f.get("FechaRad_") or "").strip(),
                "NumeroRad": (f.get("NumeroRad_") or "").strip(),
                "PrefijoFac": (f.get("PrefijoFac_") or "").strip(),
                "NumeroFac": (f.get("NumeroFac_") or "").strip(),
                "NUMREG": (f.get("Numreg") or "").strip(),
                "NumeroDocAfl": (f.get("NumeroDocAfl_") or "").strip(),
                "NombreServicio": (f.get("NombreServicio") or "").strip(),
                "ValorTotalServ": _num(f.get("ValorTotalServ")),
                # El valor de la glosa es ValorGlosaTotalxServ, NO el valor
                # total del servicio, y NO se reescala.
                "ValorGlosaTotalxServ": _num(f.get("ValorGlosaTotalxServ")),
                "ValorBrutoFactura": _num(f.get("ValorBrutoFactura")),
                # El código es la sigla (TA), no la descripción (Tarifas).
                "CodMotvGlosaGeneral": (f.get("CodMotvGlosaGeneral") or "").strip(),
                "MotvGlosaGeneral": (f.get("MotvGlosaGeneral") or "").strip(),
                "CodMotvGlosaEspc": (f.get("CodMotvGlosaEspc") or "").strip(),
                "MotvGlosaEspc": (f.get("MotvGlosaEspc") or "").strip(),
                "DescripcionMotivo": (f.get("DescripcionMotivo") or "").strip(),
            }
        )
    return glosas, avisos
