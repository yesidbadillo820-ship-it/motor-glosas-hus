# glosa_motor.py — FUENTE ÚNICA del clasificador y las plantillas de respuesta
# de glosas del Dispensario Médico Bucaramanga (DSE Ejército) para SIMED.
#
# Estado: versión final endurecida por 4 rondas de verificación adversarial
# (lotes 14-jul y 17-jul de 2026). Las decisiones normativas NO son opcionales:
# - NO citar la Res. 3047/2008 (derogada por la Res. 2284/2023).
# - NO citar el Decreto 780/2016 art. 2.6.1.4.2.4 (es la base del SOAT-UVB del
#   pagador: autogol).
# - NO citar el Decreto 2423/1996 art. 87 para ítems que SÍ tienen tarifa SOAT
#   (su supuesto es "procedimiento no definido y sin tarifa asignada").
# - NO numerar el Anexo Técnico de la Res. 2284/2023 (es el No. 3 según
#   app/services/normativa.py; se cita la resolución sin número de anexo).
# - Nada de "re-liquidación" ni "no procede el rechazo total" (conceden rebaja).
# Documentación completa: docs/ENTREGA_MODULO_GLOSAS_DISPENSARIO_SIMED.md


def norm(s):
    return " ".join(str(s or "").replace("_x000D_", " ").split())


def money(v):
    try:
        return "$" + f"{int(v):,}".replace(",", ".")
    except Exception:
        return "$0"


# Sólo Dispensario / DSE Ejército (las demás entidades se omiten por indicación del auditor)
disp = lambda e: any(k in e.upper() for k in ("DISPENSARIO", "EJERCITO", "MEBUG"))  # noqa: E731

CIERRE = (
    "Por lo expuesto, se solicita el levantamiento total de la glosa y el pago íntegro de lo facturado. "
    "De persistir diferencias, la ESE HUS manifiesta su disposición a mesa de conciliación de glosas "
    "(art. 20, Decreto 4747 de 2007; Ley 1438 de 2011, art. 57). Comunicaciones: cartera@hus.gov.co, "
    "glosasydevoluciones@hus.gov.co."
)


def clasificar(code, obs):
    g = code.upper()
    o = norm(obs).upper()
    # 1. Estancia definida por código (CL0101/FA0101); si el reparo es el CONTEO del
    # día-cama (ingreso/egreso, solo se reconoce un día), va por causación.
    if g in ("CL0101", "FA0101"):
        if (
            "SOLO SE RECONOCE UN DIA" in o
            or "NO ES POSIBLE ACEPTAR COBRO DE ESTANCIA EL DIA" in o
            or ("FECHA DE INGRESO" in o and "FECHA DE EGRESO" in o)
            or ("INGRESA" in o and "MADRUG" in o)
            or "SOLO ES ATENDIDO EL DIA" in o
            or ("ADMISIONA" in o and "NO SE ACEPTA COBRO DE ESTANCIA" in o)
            or ("INGRESA" in o and "EGRESA" in o and "DIA" in o)
        ):
            return "ESTANCIA_CAUSACION"
        return "CALIDAD_ESTANCIA"
    # 2. Materiales/insumos/medicamentos objetados como incluidos en derechos de sala o estancia.
    if (
        "MATERIALES NO FACTURABLES" in o
        or "ELEMENTOS INCLUIDOS" in o
        or "MATERIALES DE SUJEC" in o
        or "HACE PARTE DE LOS DERECHOS DE SALA" in o
        or "HACEPARTE DE LOS DERECHOS DE SALA" in o
        or "PARTE DE LOS DERECHOS DE SALA" in o
        or "HACE PARTE DE LA ESTANCIA" in o
        or "INCLUIDO EN DERECHO DE SALA" in o
        or "INCLUIDO EN DERECHOS DE SALA" in o
        or "INCLUIDO EN D. SALA" in o
        or "INCLUIDO EN D SALA" in o
        or "INCLUIDO EN D.SALA" in o
        or "MATERIAL DE SUTURA Y CURACION" in o
        or "SUTURA Y CURACION PARA SALA" in o
        or ("INCLUIDO EN EL CODIGO" in o and "INSUMO" in o)
    ):
        return "MATERIALES"
    # 3. Estancia por palabras clave (nivel / pertinencia de internación; no MVC).
    if (
        ("ESTANCIA" in o or " UCI " in o or "UNIDAD DE CUIDADO" in o)
        and (
            "NO PERTINENTE" in o
            or "INOPORTUN" in o
            or "SIN CRITERIOS" in o
            or "SE RECONOCE HABITACION" in o
            or "DIAS DE ESTANCIA" in o
            or "DIA DE ESTANCIA" in o
            or "NIVEL" in o
        )
        and "MAYOR VALOR" not in o
        and "MVC" not in o
    ):
        return "CALIDAD_ESTANCIA"
    # 4. Dispositivo médico / material de osteosíntesis con tarifa (código TA0601).
    if g == "TA0601":
        return "TARIFA_DISPOSITIVO"
    # 5. Pertinencia clínica (remisión con diagnóstico, solicitud de estudios, yeso, no pertinente no-quirúrgico).
    if (
        "REMITIDO A ESTA IPS" in o
        or "OBJETA SOLICITUD DE ESTUDIOS" in o
        or "YESO E INMOVIL" in o
        or "REMITIDA DE PRIMER NIVEL" in o
        or "INGRESA REMITID" in o
        or (
            "NO PERTINENTE" in o
            and "PROCEDIMIENTO QUIRURGICO" not in o
            and "ESTANCIA" not in o
            and "INHERENTE" not in o
        )
    ):
        return "PERTINENCIA"
    # 6. Procedimiento inherente / incluido / subsumido / cubierto en honorarios.
    if (
        "INHERENTE" in o
        or "PROCEDIMIENTO INCLUIDO" in o
        or ("INCLUYE" in o and "PROCEDIMIENTO" in o)
        or "INMERSO EN EL PROCEDIMIENTO" in o
        or "CUBIERTO DENTRO" in o
        or "CUBIERTO EN" in o
        or "YA SE ENCUENTRA CUBIERTO" in o
        or "INCLUIDO EN LOS HONORARIOS" in o
        or "INCLUIDA EN LA ESTANCIA" in o
        or "INCLUIDO EN LA ESTANCIA" in o
        or ("NO FACTURABLE" in o and "HONORARIOS" in o)
        or ("PROCEDIMIENTO QUIRURGICO" in o and "NO PERTINENTE" in o)
    ):
        if "AGOTAMIENTO" in o and ("SALDO" in o or "CUPO" in o) and "DIFERENCIA" in o:
            return "TARIFA_SALDO"
        return "PROC_INDEPENDIENTE"
    # 7. Agotamiento de saldo / cupo.
    if "AGOTAMIENTO" in o and ("SALDO" in o or "CUPO" in o):
        return "TARIFA_SALDO"
    # 8. Medicamento / insumo: justificación de uso o cantidad.
    if "MEDICAMENTO" in o and (
        "NO SE JUSTIFICA" in o
        or "CANTIDAD" in o
        or "NO SE EVIDENCIA" in o
        or "SUMONISTRAD" in o
        or "SUMINISTRAD" in o
    ):
        return "INSUMO_MEDICAMENTO"
    # 9. Mala clasificación / re-encuadre de CUPS.
    if (
        "MALA CLASIFICACION" in o
        or "CLASIFICACION DE CUPS" in o
        or "SE AJUSTA A TARIFA CODIGO" in o
        or "SE AJUSTA A CODIGO" in o
        or "RE-ENCUADRE" in o
    ):
        return "MISCODIFICACION"
    # 9-bis. Valor de insumo/medicamento regido por intermediación, precio promedio o termómetro
    # de precios → defensa por tarifa institucional de dispositivos/insumos.
    if "INTERMEDIACION" in o or "TERMOMETRO DE PRECIOS" in o or "PRECIO PROMEDIO" in o:
        return "TARIFA_DISPOSITIVO"
    # 9-ter. Retención condicionada a lista de precios ("hasta tanto adjunten...").
    if "HASTA TANTO ADJUNTEN LISTA DE PRECIOS" in o or "HASTA TANTO ADJUNTEN" in o:
        return "LISTA_PRECIOS"
    # 9-quater. Componente (derechos de sala/honorarios) del 2do procedimiento "no facturable"
    # por liquidación de múltiples → desagregación.
    if "NO FACTURABLE" in o and "LIQUIDACION DE PROCEDIMIENTOS" in o:
        return "PROC_INDEPENDIENTE"
    # 9-quinquies. La descripción quirúrgica corresponde a OTRO procedimiento → discrepancia de codificación.
    if "DESCRIPCION QUIRURGICA CORRESPONDE A" in o:
        return "MISCODIFICACION"
    # 9-sexies. "Lo realizado se homologa a X que también facturan" → desagregación/no duplicidad.
    if "SE HOMOLOGA A" in o and "FACTURANDO" in o:
        return "PROC_INDEPENDIENTE"
    # 9-septies. Cantidad de pruebas según protocolo de banco de sangre → pertinencia clínica.
    if "BANCO DE SANGRE" in o:
        return "PERTINENCIA"
    # 10. Insumo/dispositivo con soporte de factura de compra/venta (pinza, casa ortopédica).
    if (
        "FACTURA DE VENTA" in o
        or "FACTURA DE COMPRA" in o
        or "CASA ORTOP" in o
        or "SIN SOPORTE DE FACTURA" in o
    ):
        return "INSUMO_FACTURA"
    # 11. Lista / listado de precios (salvo que sea un TA con MVC, que es disputa tarifaria).
    if ("LISTA DE PRECIOS" in o or "LISTADO DE PRECIOS" in o) and not (
        g.startswith("TA")
        and ("MAYOR VALOR" in o or "MVC" in o or "DIFERENCIA" in o or "SOAT" in o)
    ):
        return "LISTA_PRECIOS"
    # 11-bis. Diferencias con las CANTIDADES facturadas → acreditar cada unidad prestada.
    if "CANTIDADES FACTURADAS" in o:
        return "SOPORTE"
    # 12. Soporte / resultados que confirmen la prestación.
    if (
        "SIN RESULTADOS" in o
        or "SIN RESULTADO" in o
        or "RESULTADOS QUE CONFIRMEN" in o
        or "SOPORTE PDX" in o
        or "AYUDA DIAGNOSTICA" in o
        or "SOPORTES DE CUENTA" in o
        or "ANEXO TECNICO" in o
        or "ASPECTOS TECNICOS" in o
        or "NO SE EVIDENCIA RESULTADO" in o
        or "NO SOPORTAD" in o
        or "SIN SOPORTE" in o
        or "SIN JUSTIFICACION" in o
        or "NO SE IDENTIFICA SOPORTE" in o
        or "SIN EVIDENCIA DE REPORTE" in o
        or g.startswith("SO")
    ):
        return "SOPORTE"
    # 13. Tarifa / MVC / SOAT / mayor valor / diferencia / aval del valor.
    if (
        "MVC" in o
        or "SOAT" in o
        or "MAYOR VALOR" in o
        or "DIFERENCIA" in o
        or "NO HAY TARIFA PACTADA" in o
        or "NO SE ENCUENTRA TARIFA" in o
        or "TARIFA" in o
        or "AVAL PARA" in o
        or "AVALADA" in o
        or "AVALE EL VALOR" in o
        or "NO AVAL" in o
        or "PRECIO PROMEDIO" in o
        or "TERMOMETRO DE PRECIOS" in o
        or g.startswith("TA")
    ):
        return "TARIFA"
    # 14. Residual por prefijo.
    if g.startswith("AU"):
        return "AUTORIZACION"
    if g == "CL0601":
        return "MATERIALES"
    if g.startswith("CL"):
        return "PERTINENCIA"
    return "FACTURACION"


def arg(t):
    if t == "TARIFA":
        return (
            "el valor facturado corresponde a la tarifa institucional propia de la ESE Hospital Universitario de "
            "Santander, adoptada mediante el acto administrativo tarifario institucional vigente a la fecha de cada "
            "prestación (Resoluciones HUS 054 y 124 de 2026, o la resolución que corresponda a dicha fecha), tarifa que el Contrato "
            "Interadministrativo No. 440-DIGSA/DMBUG-2025 reconoce "
            "entre las partes en su Cláusula Segunda; por tanto, el valor facturado ES la tarifa pactada y no un "
            "mayor valor cobrado, quedando sin sustento la afirmación de que 'no se anexa acuerdo de tarifas', pues "
            "dicho acuerdo es el propio contrato y su anexo tarifario. La entidad glosadora —Dirección de Sanidad "
            "del Ejército, Dispensario Médico de Bucaramanga— es parte de ese contrato, de modo que alegar 'IPS "
            "sin contrato' contraría sus propios actos (venire contra factum proprium). La tarifa institucional "
            "pactada prevalece sobre la referencia SOAT UVB que el pagador aplica de manera unilateral y sin "
            "acuerdo que la sustituya. Se aporta el listado tarifario institucional que sustenta el cargo, por lo "
            "que no procede el descuento de la diferencia glosada."
        )
    if t == "TARIFA_SALDO":
        return (
            "el procedimiento quirúrgico facturado se liquidó a la tarifa institucional propia de la ESE HUS "
            "(Resoluciones HUS 054 y 124 de 2026), reconocida entre las partes por la Cláusula Segunda del "
            "Contrato Interadministrativo No. 440-DIGSA/DMBUG-2025, del cual la entidad glosadora es parte; por "
            "ello, sustituir unilateralmente dicha tarifa por el esquema SOAT contraría sus propios actos y el "
            "acuerdo vigente. El agotamiento de saldo o cupo es un asunto administrativo y presupuestal de la "
            "entidad contratante —a quien corresponde garantizar la disponibilidad presupuestal— que no está "
            "tipificado como causal admisible de glosa en el Manual Único de Glosas (Resolución 2284 de 2023), por "
            "lo que la causal tarifaria invocada está mal aplicada; además, el procedimiento contó con "
            "autorización previa expedida con antelación a su realización, que ampara el servicio bajo la buena fe "
            "contractual (art. 1603 del Código Civil y 871 del Código de Comercio) y la teoría de los actos "
            "propios. Cuando la entidad pretende adicionalmente subsumir el procedimiento en otro acto quirúrgico "
            "como valor único, se precisa que se trata de un procedimiento autónomo, con identificación y "
            "liquidación separada en la estructura de la tarifa institucional, según consta en la descripción "
            "quirúrgica que se aporta. En consecuencia, no procede el descuento y se solicita el reconocimiento "
            "íntegro del valor facturado, con conciliación de la glosa de contenido tarifario conforme al Decreto "
            "4747 de 2007, arts. 20 y 23."
        )
    if t == "RE_ENCUADRE":
        return (
            "no procede el re-encuadre unilateral del procedimiento facturado a un código distinto. El "
            "procedimiento efectivamente realizado corresponde al código facturado, y la homologación tarifaria "
            "SOAT no autoriza sustituir la identidad del procedimiento practicado ni su grupo. Conforme a la "
            "Cláusula Tercera del Contrato No. 440-DIGSA/DMBUG-2025, las objeciones se tramitan en los términos "
            "del Decreto 4747 de 2007, la Resolución 2284 de 2023 y la Ley 1438 de 2011 (art. 57)."
        )
    if t == "MISCODIFICACION":
        return (
            "el estudio de laboratorio facturado fue realizado por indicación del médico tratante como insumo "
            "indispensable para el diagnóstico y manejo del paciente, en ejercicio de la autonomía profesional "
            "amparada por el Artículo 17 de la Ley Estatutaria 1751 de 2015, y su resultado reposa en la historia "
            "clínica. La glosa se funda exclusivamente en una presunta 'mala clasificación de CUPS', causal que no "
            "está tipificada de forma taxativa en el Manual Único de Glosas (Resolución 2284 de 2023) —el cual ni "
            "siquiera adopta la CUPS—, por lo que la objeción carece de causal válida y es improcedente de origen. "
            "En todo caso, la pertinencia del examen efectivamente practicado prevalece sobre una eventual "
            "discrepancia formal frente al inicialmente autorizado (prevalencia de lo sustancial sobre lo formal), "
            "y el servicio realmente prestado debe reconocerse íntegramente a la tarifa institucional vigente "
            "(Resoluciones HUS 054 y 124 de 2026), sin que el pagador pueda enriquecerse sin causa. Con la "
            "presente respuesta se aportan la orden médica y el resultado que acreditan su realización, por lo que "
            "se solicita el reconocimiento íntegro del cargo."
        )
    if t == "PROC_INDEPENDIENTE":
        return (
            "el procedimiento facturado corresponde a un acto asistencial con CUPS propio y desagregación tarifaria "
            "independiente, no incluido dentro del procedimiento principal en el que la entidad pretende "
            "subsumirlo. Conforme a la estructura tarifaria aplicable, cada línea facturada corresponde a un "
            "componente distinto del acto asistencial con su código y soporte propios, y no constituye duplicidad "
            "ni inclusión: la entidad pagadora no ha aportado prueba documental de una desagregación distinta ni "
            "de que el paquete incluya expresamente el procedimiento objetado, cuya realización efectiva —con "
            "objetivo terapéutico, tiempo, complejidad y recurso propios— consta en la nota operatoria o el registro clínico de la atención. "
            "Su pertinencia y técnica están amparadas por la autonomía profesional del médico tratante (Artículo "
            "17 de la Ley 1751 de 2015), sin que el auditor pueda sustituir retrospectivamente el criterio del "
            "profesional tratante ni encuadrar la objeción fuera de las causales taxativas de la Resolución 2284 de 2023. "
            "Reconocida su autonomía, su valor se liquida a la tarifa institucional propia de la ESE (Resoluciones "
            "HUS 054 y 124 de 2026), cuya estructura liquida estos actos por renglones separados y que fue "
            "reconocida por la Cláusula Segunda del Contrato No. 440-DIGSA/DMBUG-2025 —del cual la entidad "
            "glosadora es parte, por lo que alegar ausencia de contrato o de acuerdo tarifario contraría sus "
            "propios actos—, sin que el agotamiento de saldo, cuando se invoque, constituya fundamento admisible; "
            "se solicita el levantamiento de la glosa "
            "y el pago íntegro de lo facturado (Decreto 4747 de 2007; Ley 1438 de 2011, art. 57)."
        )
    if t == "ESTANCIA_CAUSACION":
        return (
            "el día de estancia objetado se causó efectivamente conforme a la regla de liquidación de estancias "
            "de la tarifa institucional de la ESE HUS: el día-cama se genera con la ocupación efectiva y el "
            "registro de ingreso del paciente al servicio, con los cuidados de enfermería y la disponibilidad "
            "asistencial correspondientes, sin que la norma contractual condicione su cobro a la pernoctación "
            "completa ni al corte de medianoche. Las notas de ingreso y de enfermería que se aportan acreditan la "
            "permanencia y la atención efectivamente prestada durante el día objetado, por lo que el cargo "
            "corresponde a un servicio real y liquidado a la tarifa institucional reconocida por el Contrato No. "
            "440-DIGSA/DMBUG-2025 (Resoluciones HUS 054 y 124 de 2026). En consecuencia, no procede el descuento "
            "del día de estancia facturado."
        )
    if t == "CALIDAD_ESTANCIA":
        return (
            "la estancia hospitalaria objetada obedeció a la evolución clínica del paciente y a los criterios "
            "médicos de permanencia y egreso documentados en las notas de evolución diarias de la historia "
            "clínica, en ejercicio de la autonomía profesional del médico tratante amparada por el Artículo 17 de "
            "la Ley Estatutaria 1751 de 2015. El nivel de cuidado se determina por los criterios clínicos "
            "consignados día a día —monitoreo, soporte y vigilancia—, con independencia de la hora del registro "
            "formal de una orden de traslado, sin que una interconsulta puntual borre la indicación del equipo "
            "tratante; el HUS, como institución de alta complejidad habilitada, está autorizado para prestar el "
            "servicio en el nivel facturado. Mientras el paciente permaneció pendiente de manejo quirúrgico no era "
            "egresable con seguridad y requirió manejo intrahospitalario efectivamente prestado; la "
            "programación del acto quirúrgico dentro del intervalo técnicamente indicado no desvirtúa la "
            "necesidad clínica de la permanencia ni la efectiva prestación del servicio de hospitalización, y toda prolongación "
            "derivada de demora en autorización, "
            "traslado o respuesta de la entidad pagadora tampoco es imputable al HUS (art. 1603 del Código Civil; "
            "art. 871 del Código de Comercio). En consecuencia, se solicita el reconocimiento del nivel de "
            "complejidad facturado y del valor objetado de la estancia, servicio real y efectivamente prestado."
        )
    if t == "INSUMO_MEDICAMENTO":
        return (
            "el medio de contraste facturado fue administrado por indicación del médico tratante para la "
            "realización del estudio radiológico contrastado, en ejercicio de la autonomía profesional (Artículo "
            "17 de la Ley 1751 de 2015), y la cantidad utilizada corresponde a la dosificación propia del "
            "procedimiento según el peso y la condición del paciente y la ficha técnica del producto. La cantidad "
            "administrada se ajusta a lo requerido y autorizado para el estudio; una vez emitida la autorización "
            "del apoyo diagnóstico por la entidad pagadora, no procede objetar las unidades efectivamente "
            "empleadas en su ejecución, en aplicación de la teoría de los actos propios. Con la presente respuesta "
            "se aportan la orden del contraste y el registro de administración que justifican el uso y la cantidad, "
            "por lo que se solicita el levantamiento de la glosa y el pago íntegro de lo facturado."
        )
    if t == "INSUMO_FACTURA":
        return (
            "el insumo médico-quirúrgico facturado fue efectivamente utilizado en la atención, según la "
            "descripción quirúrgica y la hoja de gasto, que constituyen el soporte de uso exigido por la "
            "Resolución 2284 de 2023, sin que sea exigible la factura de compra del proveedor para acreditar la "
            "prestación. Su valor se rige por la tarifa institucional propia de la ESE HUS (Resoluciones HUS 054 y "
            "124 de 2026), reconocida por el Contrato No. 440-DIGSA/DMBUG-2025, y no por el costo de adquisición; "
            "la atención contó con la autorización correspondiente conforme al procedimiento contractual, por lo "
            "que no cabe alegar 'sobrecosto', 'sin contrato' ni 'sin autorización'. El dispositivo es de un solo "
            "uso y no fue reprocesado, de modo que las políticas de reúso no le son aplicables. La retención del "
            "30% 'en espera de conciliación' no corresponde a una causal presente y taxativa de glosa (Resolución "
            "2284 de 2023): la conciliación (Decreto 4747 de 2007, arts. 20 y 23) es una vía posterior que no "
            "autoriza retener el pago, por lo que procede el reconocimiento íntegro del valor facturado."
        )
    if t == "MATERIALES":
        return (
            "el insumo o medicamento facturado fue efectivamente utilizado o administrado en la atención del "
            "paciente y registrado en la hoja de gasto, y su cobro por separado es procedente: no se trata de un "
            "elemento comprendido dentro de los derechos de sala, los materiales de sujeción ni la estancia, pues "
            "no figura en los listados de inclusión que invoca la entidad, correspondiendo a un consumo real, "
            "individualizable e independiente. Además, la tarifa institucional de la ESE HUS (Resoluciones HUS 054 "
            "y 124 de 2026), reconocida por la Cláusula Segunda del Contrato No. 440-DIGSA/DMBUG-2025 del cual la "
            "entidad glosadora es parte, codifica y liquida estos ítems como facturables por separado. Con la "
            "presente respuesta se aportan los soportes de consumo que justifican el cargo (Resolución 2284 de "
            "2023)."
        )
    if t == "SOPORTE":
        return (
            "el servicio, insumo o medicamento facturado fue efectivamente prestado, utilizado o administrado por "
            "indicación médica, y se encuentra soportado en la historia clínica remitida o en los sistemas de "
            "información asistencial del HUS, consultables por el equipo auditor, conforme a la integralidad de la "
            "historia clínica exigida por la Resolución 1995 de 1999. Con la presente respuesta se anexa el "
            "soporte específico que acredita la prestación —reporte de resultado con fecha y responsable para los "
            "estudios; descripción quirúrgica y hoja de gasto para los insumos; hoja de administración con hora y "
            "responsable para los medicamentos—, con lo cual queda sin sustento la objeción por ausencia de "
            "soporte (Resolución 2284 de 2023). Por tratarse de un servicio realmente prestado y soportado, se "
            "solicita el levantamiento de la glosa y el pago íntegro de lo facturado."
        )
    if t == "LISTA_PRECIOS":
        return (
            "la glosa por falta de lista de precios es improcedente, por cuanto el valor del servicio glosado "
            "corresponde a la tarifa institucional propia de la ESE HUS adoptada por acto administrativo "
            "(Resoluciones HUS 054 y 124 de 2026) y reconocida entre las partes por la Cláusula Segunda del "
            "Contrato No. 440-DIGSA/DMBUG-2025. El tarifario institucional es un documento contractual preexistente que reposa en poder de ambas "
            "partes y que en todo caso se aporta nuevamente con la presente respuesta (Resolución 2284 de 2023). Con la presente "
            "respuesta se remite la fila tarifaria del código glosado y el "
            "tarifario institucional aplicable, por lo que, subsistiendo el servicio efectivamente prestado, no "
            "procede la glosa total."
        )
    if t == "TARIFA_DISPOSITIVO":
        return (
            "el valor del dispositivo médico o insumo facturado corresponde a la tarifa institucional propia de la "
            "ESE Hospital Universitario de Santander, adoptada por acto administrativo (Resoluciones HUS 054 y 124 "
            "de 2026 y, tratándose de material de osteosíntesis, la Resolución HUS 194 de 2025), reconocida entre "
            "las partes por la Cláusula Segunda del Contrato No. 440-DIGSA/DMBUG-2025 —del cual la entidad "
            "glosadora es parte—. Dicha tarifa prevalece sobre el esquema SOAT, el 'precio promedio del mercado' o "
            "cualquier homologación que el pagador aplique de manera unilateral. El dispositivo o insumo fue efectivamente "
            "utilizado en la atención, según la descripción quirúrgica y la hoja de gasto en los procedimientos "
            "quirúrgicos, o la orden médica y los registros clínicos de administración en los demás servicios, "
            "soportes de uso conformes con la Resolución 2284 de 2023, sin que sea exigible la factura de compra del "
            "proveedor para acreditar la prestación ni para fijar el valor, que se rige por la tarifa institucional "
            "y no por el costo de adquisición. En consecuencia, la diferencia glosada no es un mayor valor cobrado "
            "y no procede su descuento; se aporta el tarifario institucional que sustenta el cargo."
        )
    if t == "PERTINENCIA":
        return (
            "el servicio fue prestado por indicación del profesional tratante y con plena pertinencia clínica, "
            "conforme a la condición del paciente documentada en la historia clínica (indicación, protocolo asistencial o remisión con "
            "diagnóstico que justifica el estudio, procedimiento o medicamento). La pertinencia de las ayudas "
            "diagnósticas y de los procedimientos es un elemento esencial del ejercicio profesional médico, "
            "amparado por la autonomía del Artículo 17 de la Ley Estatutaria 1751 de 2015, sin que el auditor "
            "pueda sustituir el criterio del tratante. La remisión del usuario a esta IPS no excluye la "
            "procedencia ni el pago de los servicios efectivamente realizados y soportados, por lo que la "
            "objeción de pertinencia no está llamada a prosperar frente a los registros clínicos que se aportan, "
            "y se solicita el levantamiento de la glosa y el pago íntegro de lo facturado (Decreto 4747 de 2007)."
        )
    if t == "AUTORIZACION":
        return (
            "la atención facturada corresponde a la autorización expedida por la oficina de referencia y "
            "contrarreferencia del DMBUG, anexa a la cuenta conforme a la Cláusula Tercera del Contrato No. "
            "440-DIGSA/DMBUG-2025. Una eventual inconsistencia administrativa de la autorización no exonera del "
            "pago de los servicios efectivamente prestados y soportados en la historia clínica (Decreto 4747 de "
            "2007, art. 23)."
        )
    return (
        "el servicio fue efectivamente prestado, facturado conforme a la codificación CUPS y liquidado a la tarifa "
        "del Contrato No. 440-DIGSA/DMBUG-2025 vigente entre las partes, sin inconsistencia que amerite la "
        "objeción. El cobro se encuentra soportado en la historia clínica y en los RIPS anexos."
    )


def redactar(factura, code, cups, serv, valor, obs):
    t = clasificar(code, obs)
    txt = (
        f"ESE HUS no acepta la glosa aplicada a la factura {factura} por la Dirección de Sanidad del Ejército – "
        f"Dispensario Médico de Bucaramanga. Frente al cargo por código {cups} {serv} ({money(valor)}), objetado "
        f"bajo el concepto {code}: {arg(t)} {CIERRE}"
    )
    return " ".join(txt.split()).upper(), t
