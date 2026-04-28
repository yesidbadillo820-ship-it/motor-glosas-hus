"""Catálogo completo del Manual Único de Devoluciones, Glosas y Respuestas
(Anexo Técnico No. 3) — fuente oficial para la IA.

Este archivo contiene TODOS los códigos oficiales con su definición exacta,
de modo que la IA no tenga que adivinar qué significa cada código.
"""
from __future__ import annotations

# ─── CATÁLOGO DE GLOSAS POR FACTURACIÓN (FA) ─────────────────────────────
CODIGOS_FA = {
    "FA": "FACTURACIÓN — Diferencias en cantidad al comparar servicios prestados con facturados; recaudo de copagos no descontados; o errores administrativos en facturación.",

    "FA0101": "Estancia u observación de urgencias: el cargo relacionado/justificado en soportes presenta diferencia con las cantidades facturadas.",
    "FA0102": "Consultas, interconsultas o atenciones domiciliarias facturadas que están INCLUIDAS en la estancia u observación de urgencias de acuerdo con lo pactado.",
    "FA0103": "Estancia u observación de urgencias cobrada que ya está INCLUIDA en una atención agrupada (paquete), de acuerdo con lo pactado.",
    "FA0105": "Servicios o tecnologías facturados que están INCLUIDOS en la estancia u observación de urgencias de acuerdo con lo pactado.",

    "FA0201": "Consulta/interconsulta/atención domiciliaria: el cargo relacionado/justificado en soportes presenta diferencias con las cantidades facturadas.",
    "FA0202": "Consultas o atenciones (visitas) domiciliarias cobradas que se encuentran INCLUIDAS en los honorarios profesionales POST QUIRÚRGICOS. Defensa central: demostrar que el servicio facturado (CUPS específico) NO es visita domiciliaria ni parte del seguimiento del cirujano tratante, sino un servicio intrahospitalario independiente prestado por otra especialidad.",
    "FA0203": "Consultas/atenciones domiciliarias cobradas que ya están INCLUIDAS en una atención agrupada (paquete).",
    "FA0205": "Consultas cobradas que están INCLUIDAS en los honorarios profesionales del procedimiento, de acuerdo con lo pactado.",
    "FA0206": "Interconsulta registrada en la factura que originó la práctica de un procedimiento quirúrgico/intervencionista realizado por el mismo prestador.",

    "FA0301": "Honorarios profesionales en procedimientos quirúrgicos/intervencionistas: el cargo presenta diferencias con las cantidades facturadas.",
    "FA0302": "Honorarios de anestesia: el cargo presenta diferencias con las cantidades facturadas.",
    "FA0303": "Honorarios profesionales cobrados que ya están INCLUIDOS en una atención agrupada.",

    "FA0501": "Derechos de sala: el cargo presenta diferencias con las cantidades facturadas.",
    "FA0502": "Tecnologías en salud cobradas que ya están INCLUIDAS en el ítem derechos de sala o materiales quirúrgicos.",
    "FA0503": "Derechos de sala cobrados que ya están INCLUIDOS en una atención agrupada.",

    "FA0601": "Dispositivos médicos: el cargo presenta diferencias con las cantidades facturadas.",
    "FA0602": "Dispositivos médicos cobrados que ya están INCLUIDOS en el ítem materiales por grupo quirúrgico.",
    "FA0603": "Dispositivos médicos cobrados que ya están INCLUIDOS en una atención agrupada.",

    "FA0701": "Medicamentos o APME: el cargo presenta diferencias con las cantidades facturadas.",
    "FA0702": "Principios activos facturados separadamente cuando fueron dispensados en una presentación combinada.",
    "FA0703": "Medicamentos o APME cobrados que ya están INCLUIDOS en una atención agrupada.",
    "FA0705": "Medicamentos cobrados que ya están INCLUIDOS en el procedimiento quirúrgico.",

    "FA0801": "Apoyo diagnóstico: el cargo presenta diferencias con las cantidades facturadas.",
    "FA0802": "Apoyos diagnósticos facturados separadamente cuando están INCLUIDOS uno en el otro. Defensa central: demostrar que el apoyo diagnóstico (ej. TP, laboratorios, imágenes) es un ESTUDIO INDEPENDIENTE solicitado por criterio médico, NO es un estudio derivado o incluido dentro de otro. Citar Manual Tarifario SOAT (Decreto 2423/1996) como referente.",
    "FA0803": "Apoyos diagnósticos cobrados que ya están INCLUIDOS en una atención agrupada.",
    "FA0805": "Apoyos diagnósticos cobrados que ya están INCLUIDOS en el procedimiento quirúrgico o intervencionista.",

    "FA1305": "Factura incluye servicios/tecnologías con cobertura diferente (multiusuario); se glosa lo correspondiente a cobertura distinta.",
    "FA1605": "Factura relaciona una o varias personas que en el momento de la prestación correspondían a otro responsable de pago.",
    "FA1606": "Factura relaciona uno o varios servicios/tecnologías que corresponden a otro responsable de pago.",
    "FA1905": "Descuentos otorgados que fueron aplicados de manera diferente a lo pactado o no fueron aplicados.",
    "FA2006": "Recaudos efectivos de copagos/cuotas moderadoras no corresponden a lo informado por la entidad responsable de pago.",

    "FA2301": "Otros procedimientos no quirúrgicos: el cargo presenta diferencias con las cantidades facturadas.",
    "FA2302": "Otros procedimientos no quirúrgicos facturados separadamente incluidos en otro.",
    "FA2303": "Otros procedimientos no quirúrgicos cobrados que ya están INCLUIDOS en una atención agrupada.",

    "FA2702": "Servicios o tecnologías ya cobrados dentro de la misma u otra factura (doble facturación).",
    "FA2805": "Servicio o tecnología ya pagado por la entidad responsable de pago.",

    "FA3801": "Traslado asistencial: el cargo presenta diferencias con las cantidades facturadas.",
    "FA3803": "Traslado asistencial cobrado que ya está INCLUIDO en una atención agrupada.",

    "FA5103": "Servicio o tecnología incluido en atención agrupada, prestado por otro prestador en caso de urgencias o por proceso de referencia (descuento del paquete).",
    "FA5105": "Servicio o tecnología incluido en atención agrupada que hace parte de RIAS, prestado por otro prestador.",
    "FA5106": "Servicio o tecnología incluido en atención agrupada prestado por otro prestador, con la finalidad de determinar control o complicaciones.",

    "FA5205": "Número de personas incluidas en modalidad de pago prospectiva disminuido por novedades en base de datos.",
    "FA5206": "Persona incluida en modalidad prospectiva fallece, aplica deducción proporcional.",

    "FA5701": "Apoyo terapéutico: el cargo presenta diferencias con las cantidades facturadas.",
    "FA5702": "Apoyos terapéuticos facturados separadamente cuando están incluidos en otro.",
    "FA5703": "Apoyos terapéuticos cobrados que ya están INCLUIDOS en una atención agrupada.",

    "FA5801": "Procedimientos quirúrgicos o intervencionistas: el cargo presenta diferencias con las cantidades facturadas.",
    "FA5802": "Procedimientos quirúrgicos/intervencionistas facturados separadamente cuando están incluidos en otro.",
    "FA5803": "Procedimientos quirúrgicos cobrados que ya están INCLUIDOS en una atención agrupada.",

    "FA5901": "Transporte no asistencial ambulatorio: el cargo presenta diferencias con las cantidades facturadas.",
    "FA5903": "Transporte no asistencial ambulatorio cobrado que ya está INCLUIDO en una atención agrupada.",
}

# ─── CATÁLOGO DE GLOSAS POR TARIFAS (TA) ─────────────────────────────────
CODIGOS_TA = {
    "TA": "TARIFAS — Diferencias al comparar valores facturados con los pactados en el contrato o los definidos por la normatividad.",

    "TA0101": "Estancia u observación de urgencias: el cargo presenta diferencia con los valores pactados o establecidos por la norma.",
    "TA0201": "Consulta, interconsulta o atención domiciliaria: el cargo presenta diferencias con los valores pactados o establecidos por la norma.",
    "TA0301": "Honorarios profesionales en procedimientos quirúrgicos/intervencionistas: diferencias con valores pactados.",
    "TA0302": "Honorarios de anestesia: diferencias con valores pactados.",
    "TA0401": "Honorarios de otro talento humano que interviene en la atención: diferencias con valores pactados.",
    "TA0501": "Derechos de sala: diferencias con valores pactados o establecidos por la norma.",
    "TA0601": "Dispositivos médicos: diferencias con valores pactados.",
    "TA0701": "Medicamentos o APME: diferencias con valores pactados.",
    "TA0801": "Apoyo diagnóstico: diferencias con valores pactados o establecidos por la norma.",
    "TA0901": "Atención agrupada: el cargo sobrepasa el valor pactado en modalidades de pago (paquete/capitación/global).",
    "TA2301": "Otros procedimientos no quirúrgicos: diferencias con valores pactados.",
    "TA2901": "Recargos no pactados previamente entre las partes o establecidos por la norma.",
    "TA3801": "Traslado asistencial: diferencias con valores pactados.",
    "TA5701": "Apoyo terapéutico: diferencias con valores pactados.",
    "TA5801": "Procedimientos quirúrgicos o intervencionistas: diferencias con valores pactados.",
    "TA5901": "Transporte no asistencial ambulatorio: diferencias con valores pactados.",
}

# ─── CATÁLOGO DE GLOSAS POR SOPORTES (SO) ────────────────────────────────
CODIGOS_SO = {
    "SO": "SOPORTES — Ausencia total/parcial o inconsistencia en los soportes, o porque no corresponden a la persona atendida.",

    "SO0101": "Ausencia/inconsistencia en la epicrisis que soporta la estancia u observación de urgencias.",
    "SO0102": "Soportes de estancia u observación de urgencias no corresponden a la persona atendida.",
    "SO0201": "Ausencia/inconsistencia en soportes que evidencian la realización de la consulta/interconsulta/atención domiciliaria.",
    "SO0202": "Soportes de consulta/interconsulta/atención domiciliaria no corresponden a la persona atendida.",
    "SO0301": "Ausencia/inconsistencia en soportes que evidencian honorarios profesionales en procedimientos.",
    "SO0302": "Soportes de honorarios profesionales no corresponden a la persona atendida.",
    "SO0303": "Ausencia/inconsistencia en soportes que evidencian honorarios de anestesia.",
    "SO0401": "Ausencia/inconsistencia en soportes de honorarios de otro talento humano.",
    "SO0402": "Soportes de honorarios de otros profesionales asistenciales no corresponden a la persona atendida.",
    "SO0601": "Ausencia/inconsistencia en soportes de dispositivos médicos en procedimientos quirúrgicos/intervencionistas.",
    "SO0602": "Soportes de dispositivos médicos no corresponden a la persona atendida.",
    "SO0603": "Ausencia/inconsistencia en soportes de dispositivos médicos en procedimientos no quirúrgicos.",
    "SO0604": "Ausencia/inconsistencia en soportes de dispositivos médicos entregados como protección específica o tratamiento.",
    "SO0701": "Ausencia/inconsistencia en la hoja de administración de medicamentos.",
    "SO0702": "Soportes de medicamentos suministrados no corresponden a la persona atendida.",
    "SO0703": "Ausencia/inconsistencia en el comprobante de recibido de medicamentos.",
    "SO0801": "Ausencia/inconsistencia en soportes que evidencian la práctica del apoyo diagnóstico.",
    "SO0802": "Soportes del apoyo diagnóstico no corresponden a la persona atendida.",
    "SO0803": "Ausencia en soportes de lectura/interpretación del apoyo diagnóstico.",

    "SO2101": "Número de autorización no está incluido en el RIPS.",
    "SO2102": "Número de autorización en RIPS no corresponde al prestador.",
    "SO2103": "Número de autorización en RIPS no corresponde al servicio o tecnología prestada.",
    "SO2104": "Número de autorización en RIPS no corresponde a la persona atendida.",

    "SO2301": "Ausencia/inconsistencia en soportes de otros procedimientos no quirúrgicos.",
    "SO2302": "Soportes de otros procedimientos no quirúrgicos no corresponden a la persona atendida.",

    "SO3401": "Ausencia/inconsistencia en la epicrisis.",
    "SO3402": "Epicrisis no corresponde a la persona atendida.",
    "SO3403": "Ausencia/inconsistencia en la hoja de atención de urgencias.",
    "SO3404": "Hoja de atención de urgencias no corresponde a la persona atendida.",
    "SO3405": "Ausencia/inconsistencia en el resumen de atención.",
    "SO3406": "Resumen de atención no corresponde a la persona atendida.",
    "SO3407": "Ausencia/inconsistencia en la hoja de atención odontológica.",
    "SO3408": "Hoja de atención odontológica no corresponde a la persona atendida.",

    "SO3601": "Ausencia/inconsistencia en copias de factura enviada a SOAT/ADRES.",
    "SO3602": "Copias de factura enviada a SOAT/ADRES no corresponden a la persona atendida.",
    "SO3701": "Ausencia/inconsistencia en la orden o prescripción facultativa.",
    "SO3702": "Orden o prescripción facultativa no corresponde a la persona atendida.",
    "SO3801": "Ausencia/inconsistencia en la hoja de traslado asistencial.",
    "SO3802": "Hoja de traslado asistencial no corresponde a la persona atendida.",
    "SO3901": "Ausencia/inconsistencia en el comprobante de recibido del usuario.",
    "SO3902": "Comprobante de recibido del usuario no corresponde a la persona atendida.",
    "SO4001": "Ausencia/inconsistencia de copia del registro de anestesia.",
    "SO4002": "Registro de anestesia no corresponde a la persona atendida.",
    "SO4101": "Ausencia/inconsistencia de copia de la descripción quirúrgica.",
    "SO4102": "Descripción quirúrgica no corresponde a la persona atendida.",
    "SO4201": "Ausencia/inconsistencia de lista de precios.",
    "SO4701": "No se incluyen soportes de servicios/tecnologías para recobros ADRES/ARL.",
    "SO4801": "Ausencia/inconsistencia en la evidencia del envío del trámite respectivo.",
    "SO4802": "Informe de atención de urgencias no corresponde a la persona atendida.",

    "SO5701": "Ausencia/inconsistencia en soportes que evidencian apoyo terapéutico.",
    "SO5702": "Soportes de apoyo terapéutico no corresponden a la persona atendida.",
    "SO5801": "Ausencia/inconsistencia en soportes de procedimientos quirúrgicos/intervencionistas.",
    "SO5802": "Soportes de procedimientos quirúrgicos/intervencionistas no corresponden a la persona atendida.",
    "SO5901": "Ausencia/inconsistencia en soporte de transporte no asistencial ambulatorio.",
    "SO5902": "Tiquete de transporte no corresponde a la persona atendida.",
    "SO6101": "Campo(s) de RIPS con inconsistencias respecto a la atención prestada.",
    "SO6102": "Campo(s) de RIPS con inconsistencias respecto al contrato.",
}

# ─── CATÁLOGO DE GLOSAS POR AUTORIZACIÓN (AU) ────────────────────────────
CODIGOS_AU = {
    "AU": "AUTORIZACIÓN — Servicios/tecnologías no autorizados, difieren de la autorización, o documentos/firmas adulteradas. Las urgencias NO requieren autorización previa (Art. 168 Ley 100/1993).",

    "AU0101": "Número de días en habitación difiere de los días autorizados.",
    "AU0102": "Servicio de internación no corresponde al autorizado.",
    "AU0201": "Número de consultas/interconsultas/atenciones domiciliarias difiere de las autorizadas.",
    "AU0202": "Consulta/interconsulta/atención domiciliaria no corresponde a la autorizada.",
    "AU0302": "Honorarios profesionales no corresponden a los autorizados.",
    "AU0303": "EPS emitió autorización directamente al profesional, y la IPS está facturando a su nombre.",
    "AU0601": "Número de dispositivos médicos difiere de lo autorizado, sin justificación.",
    "AU0602": "Dispositivos médicos no corresponden a los autorizados.",
    "AU0701": "Número de unidades de forma farmacéutica difiere de lo autorizado.",
    "AU0702": "Forma farmacéutica difiere de la autorizada.",
    "AU0703": "Principio activo difiere del autorizado.",
    "AU0704": "Concentración difiere de la autorizada.",
    "AU0801": "Número de apoyos diagnósticos difiere de lo autorizado.",
    "AU0802": "Apoyos diagnósticos no corresponden a los autorizados.",
    "AU2103": "Número de autorización en factura o RIPS no corresponde al servicio prestado.",
    "AU2301": "Número de procedimientos no quirúrgicos difiere de lo autorizado.",
    "AU2302": "Procedimiento no quirúrgico no corresponde al autorizado.",
    "AU3803": "Traslado asistencial sin autorización (no aplica en urgencias).",
    "AU4303": "Orden/prescripción o autorización vencida al momento de dispensación.",
    "AU4304": "Orden/prescripción no corresponde a la autorización reemplazada por vencimiento.",
    "AU5701": "Número de apoyos terapéuticos difiere de lo autorizado.",
    "AU5702": "Apoyos terapéuticos no corresponden a los autorizados.",
    "AU5801": "Número de procedimientos quirúrgicos/intervencionistas difiere de lo autorizado.",
    "AU5802": "Procedimientos quirúrgicos/intervencionistas no corresponden a los autorizados.",
    "AU5903": "Transporte no asistencial ambulatorio sin autorización.",
}

# ─── CATÁLOGO DE GLOSAS POR COBERTURA (CO) ───────────────────────────────
CODIGOS_CO = {
    "CO": "COBERTURA — Cobro de servicios/tecnologías no incluidos en el plan de beneficios, o servicios a cargo de otro responsable.",

    "CO0101": "Días en observación/habitación no están incluidos en la cobertura.",
    "CO0201": "Consulta/interconsulta/atención domiciliaria no incluida en la cobertura.",
    "CO0301": "Honorarios profesionales no incluidos en la cobertura.",
    "CO0401": "Honorarios de otros profesionales no incluidos en la cobertura.",
    "CO0601": "Dispositivos médicos no incluidos en la cobertura.",
    "CO0701": "Medicamentos o APME no incluidos en la cobertura.",
    "CO0801": "Apoyos diagnósticos no incluidos en la cobertura.",
    "CO2301": "Procedimientos no quirúrgicos no incluidos en la cobertura.",
    "CO3801": "Traslado asistencial no incluido en la cobertura.",
    "CO4601": "Servicios facturados a EPS sin agotar topes de SOAT/ADRES.",
    "CO5701": "Apoyos terapéuticos no incluidos en cobertura o cobrados adicionalmente cuando hacen parte integral.",
    "CO5801": "Procedimientos quirúrgicos/intervencionistas no incluidos en cobertura.",
    "CO5901": "Transporte no asistencial ambulatorio no incluido en cobertura.",
}

# ─── CATÁLOGO DE GLOSAS POR CALIDAD / PERTINENCIA (CL) ───────────────────
CODIGOS_CL = {
    "CL": "CALIDAD / PERTINENCIA — Ausencia de coherencia entre evento/condición de salud y los servicios prestados. Se defiende con autonomía médica (Art. 17 Ley 1751/2015) y criterio del médico tratante.",

    "CL0101": "Estancia (observación urgencias u habitación) no es pertinente.",
    "CL0201": "Consulta/interconsulta/atención domiciliaria no es pertinente.",
    "CL0301": "Honorarios profesionales en procedimientos quirúrgicos/hemodinamia/radiología/otros no son pertinentes.",
    "CL0302": "Honorarios de anestesia no son pertinentes.",
    "CL0601": "Dispositivos médicos no son pertinentes.",
    "CL0701": "Medicamentos o APME no son pertinentes.",
    "CL0703": "Medicamentos/APME corresponden a suministro incompleto según orden médica.",
    "CL0801": "Apoyo diagnóstico no es pertinente.",
    "CL2301": "Otros procedimientos no quirúrgicos/actividades no son pertinentes.",
    "CL3801": "Traslado asistencial no es pertinente.",
    "CL5301": "Servicios prestados no obedecen a atención de urgencia según normativa vigente.",
    "CL5701": "Apoyo terapéutico no es pertinente.",
    "CL5801": "Procedimientos quirúrgicos/intervencionistas no son pertinentes.",
    "CL5901": "Transporte no asistencial ambulatorio no es pertinente.",
}

# ─── CATÁLOGO DE GLOSAS POR SEGUIMIENTO A LOS ACUERDOS (SA) ──────────────
CODIGOS_SA = {
    "SA": "SEGUIMIENTO A LOS ACUERDOS — Glosas por incumplimiento de indicadores pactados en el acuerdo de voluntades (intervenciones obligatorias RIAS, modalidades prospectivas, indicadores de calidad/gestión/resultados).",

    "SA5401": "Incumplimiento de indicadores de intervenciones para promoción y mantenimiento de salud (Res. 3280/2018).",
    "SA5402": "Incumplimiento de indicadores de intervenciones para población materno perinatal.",
    "SA5403": "Incumplimiento de indicadores para atención de condiciones crónicas y de alto costo.",
    "SA5501": "Disminución en número de población inicial en modalidad de pago prospectiva.",
    "SA5502": "Disminución en frecuencia observada de uso de servicios respecto a la nota técnica.",
    "SA5601": "Incumplimiento de indicadores de calidad pactados.",
    "SA5602": "Incumplimiento de indicadores de gestión pactados.",
    "SA5603": "Incumplimiento de indicadores de resultados en salud pactados.",
}

# ─── CÓDIGOS DE RESPUESTA (RE) ───────────────────────────────────────────
CODIGOS_RESPUESTA = {
    "RE9501": "Devolución no procede por haberse generado fuera de los términos (extemporánea).",
    "RE9502": "Glosa no procede por extemporánea — aceptación tácita de la factura (Art. 57 Ley 1438/2011).",
    "RE9601": "Devolución injustificada al 100% (IPS aporta evidencia que lo demuestra).",
    "RE9602": "Glosa injustificada al 100% (IPS aporta evidencia que lo demuestra).",
    "RE9701": "Devolución/glosa aceptada al 100% por la IPS.",
    "RE9801": "Glosa aceptada y subsanada PARCIALMENTE por la IPS.",
    "RE9901": "Glosa no aceptada y subsanada en su totalidad por la IPS (RESPUESTA MÁS COMÚN EN DEFENSAS).",
    "RE2201": "EPS informa que respuesta de devolución IPS fue extemporánea — aceptación tácita de la devolución.",
    "RE2202": "EPS informa que respuesta de glosa IPS fue extemporánea — aceptación tácita de la glosa.",
}

# ─── CATÁLOGO MAESTRO ─────────────────────────────────────────────────────
CATALOGO_COMPLETO: dict[str, str] = {}
CATALOGO_COMPLETO.update(CODIGOS_FA)
CATALOGO_COMPLETO.update(CODIGOS_TA)
CATALOGO_COMPLETO.update(CODIGOS_SO)
CATALOGO_COMPLETO.update(CODIGOS_AU)
CATALOGO_COMPLETO.update(CODIGOS_CO)
CATALOGO_COMPLETO.update(CODIGOS_CL)
CATALOGO_COMPLETO.update(CODIGOS_SA)
CATALOGO_COMPLETO.update(CODIGOS_RESPUESTA)


def obtener_concepto(codigo: str) -> str:
    """Devuelve la definición oficial del Manual Único para un código dado.
    Si no se encuentra exacto, busca el grupo (ej. FA02 para FA0202)."""
    if not codigo:
        return ""
    codigo = codigo.upper().strip()
    if codigo in CATALOGO_COMPLETO:
        return CATALOGO_COMPLETO[codigo]
    # Fallback: buscar por grupo (prefijo 4 chars)
    if len(codigo) >= 4:
        grupo = codigo[:4]
        if grupo in CATALOGO_COMPLETO:
            return CATALOGO_COMPLETO[grupo]
    # Fallback: tipo general (primeras 2 letras)
    if len(codigo) >= 2:
        tipo = codigo[:2]
        if tipo in CATALOGO_COMPLETO:
            return CATALOGO_COMPLETO[tipo]
    return ""


def pertenece_a_tipo(codigo: str) -> str:
    """Devuelve el tipo general del código (FA, TA, SO, AU, CO, CL, SA, RE)."""
    if not codigo:
        return ""
    c = codigo.upper().strip()
    for prefijo in ("FA", "TA", "SO", "AU", "CO", "CL", "PE", "SA", "RE", "IN", "ME", "EX"):
        if c.startswith(prefijo):
            return prefijo
    return ""


def sugerir_codigo_respuesta(tipo_glosa: str, es_extemporanea: bool = False,
                              aceptada_parcial: bool = False,
                              aceptada_total: bool = False,
                              ratificada: bool = False,
                              subsanada: bool = False) -> str:
    """Sugiere el código de respuesta correcto según la situación.

    Default: RE9602 (defensa por injustificación con evidencia).
    RE9901 solo cuando hay subsanación efectiva o la EPS ratificó la glosa
    y el flujo legal exige insistir en la respuesta inicial.
    """
    if ratificada:
        return "RE9901"
    if aceptada_total:
        return "RE9701"
    if aceptada_parcial:
        return "RE9801"
    if es_extemporanea:
        return "RE9502"
    if subsanada:
        return "RE9901"
    # Default: defensa por injustificación con evidencia
    return "RE9602"
