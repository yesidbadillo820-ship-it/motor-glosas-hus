"""
normativa_completa.py — Biblioteca comprehensiva de normativa colombiana
=========================================================================
Base de conocimiento para consulta de auditores y motor de respuestas a
glosas. Cada norma tiene: descripción, artículos clave con su texto, y
palabras clave para búsqueda semántica.

Cobertura 2026: cuentas médicas, glosas, FEV/RIPS, tarifas SOAT, régimen
especial (PPL/FOMAG/FF.MM./ARL), historia clínica, autonomía médica.

Uso:
    from app.services.normativa_completa import consultar_normativa
    resp = consultar_normativa("¿cuál es el plazo para que una EPS formule glosa?")
"""
from __future__ import annotations

from typing import List, Optional
import re
import unicodedata


# ═══════════════════════════════════════════════════════════════════
#  LEYES
# ═══════════════════════════════════════════════════════════════════

LEYES = {
    "LEY 100 DE 1993": {
        "nombre": "Ley 100 de 1993",
        "titulo": "Por la cual se crea el Sistema de Seguridad Social Integral",
        "ambito": "Sistema General de Seguridad Social en Salud",
        "vigente": True,
        "articulos": {
            "168": {
                "titulo": "Atención inicial de urgencias",
                "texto": "La atención inicial de urgencias debe ser prestada en forma obligatoria por todas las entidades públicas y privadas que presten servicios de salud, a todas las personas, independientemente de la capacidad de pago. Su prestación no requiere contrato ni orden previa. El costo de estos servicios será pagado por el Fondo de Solidaridad y Garantía en los casos previstos en el artículo anterior, o por la Entidad Promotora de Salud al cual esté afiliado, en cualquier otro evento.",
                "aplicacion": "Urgencias obligatorias sin autorización previa",
                "keywords": ["urgencia", "urgencias", "autorización previa", "atención inicial", "obligatoria"],
            },
            "177": {
                "titulo": "Obligaciones de las Entidades Promotoras de Salud",
                "texto": "Las Entidades Promotoras de Salud tendrán las siguientes obligaciones: (...) c) Movilizar los recursos para el otorgamiento del Plan Obligatorio de Salud, a través de patrimonios autónomos o en administración fiduciaria o cualquier otro mecanismo idóneo; d) Definir procedimientos para controlar la atención integral, eficiente, oportuna y de calidad en los servicios prestados por las Instituciones Prestadoras de Servicios de Salud; (...) f) Organizar la forma y mecanismos a través de los cuales los afiliados y sus familias puedan acceder a los servicios de salud en todo el territorio nacional.",
                "aplicacion": "Obligación EPS de reconocer y pagar servicios prestados",
                "keywords": ["obligación EPS", "pago", "reconocimiento", "servicios prestados"],
            },
            "178": {
                "titulo": "Funciones de las EPS",
                "texto": "Las Entidades Promotoras de Salud tendrán como funciones básicas las siguientes: 1. Ser delegatarias del Fondo de Solidaridad y Garantía; 2. Promover la afiliación; 3. Organizar y garantizar la prestación de los servicios del POS; 4. Aceptar a toda persona que solicite afiliación; 5. Definir procedimientos para garantizar el libre acceso a instituciones prestadoras; (...)",
                "aplicacion": "Funciones de las EPS en el sistema",
                "keywords": ["funciones EPS", "POS", "afiliación"],
            },
        },
        "keywords": ["sistema general", "seguridad social", "SGSSS", "salud", "pensiones"],
    },

    "LEY 1122 DE 2007": {
        "nombre": "Ley 1122 de 2007",
        "titulo": "Por la cual se hacen modificaciones al Sistema General de Seguridad Social en Salud",
        "ambito": "Modificaciones al SGSSS",
        "vigente": True,
        "articulos": {
            "13": {
                "titulo": "Flujo y protección de los recursos",
                "texto": "Para efectos de garantizar el flujo oportuno de los recursos, las Entidades Promotoras de Salud contributivas y subsidiadas girarán a los prestadores de servicios de salud, en el régimen contributivo, como mínimo el 50% de los valores facturados dentro de los cinco días posteriores a la presentación de la factura por parte del prestador. En el régimen subsidiado, las Entidades Promotoras de Salud girarán un anticipo equivalente al 50% del valor de la facturación, también dentro de los cinco días posteriores.",
                "aplicacion": "Anticipo del 50% de facturación en 5 días",
                "keywords": ["anticipo", "flujo de recursos", "pago", "5 días", "50%"],
            },
        },
        "keywords": ["flujo recursos", "anticipo", "pagos"],
    },

    "LEY 1438 DE 2011": {
        "nombre": "Ley 1438 de 2011",
        "titulo": "Por medio de la cual se reforma el Sistema General de Seguridad Social en Salud",
        "ambito": "Reforma SGSSS — trámite de glosas y pagos",
        "vigente": True,
        "articulos": {
            "56": {
                "titulo": "Trámite de pagos",
                "texto": "Las entidades responsables del pago de los servicios de salud deberán pagar a los prestadores el monto total de las facturas dentro de los treinta (30) días hábiles siguientes a la presentación de la factura. Cuando existan glosas, se aplicará el procedimiento señalado en el artículo siguiente. Sin perjuicio de lo anterior, dentro del mismo término, deberán haber efectuado un pago mínimo del 50% del valor neto facturado no sujeto a glosas, según corresponda.",
                "aplicacion": "Plazo de pago 30 días hábiles + anticipo 50%",
                "keywords": ["pago", "30 días", "50%", "anticipo", "trámite de pagos"],
            },
            "57": {
                "titulo": "Trámite de glosas",
                "texto": "Las entidades responsables del pago de servicios de salud dentro de los treinta (30) días hábiles siguientes a la presentación de la factura con todos sus soportes, formularán y comunicarán a los prestadores de servicios de salud las glosas a cada factura, con base en la codificación y alcance definidos por el Ministerio de Salud y Protección Social. Una vez formuladas las glosas a una factura, no se podrán formular nuevas glosas a la misma factura, salvo las que surjan de hechos nuevos detectados en la respuesta dada a la glosa inicial. El prestador de servicios de salud deberá dar respuesta a las glosas presentadas por las entidades responsables del pago, dentro de los quince (15) días hábiles siguientes a su recepción. La entidad responsable del pago, dentro de los siete (7) días hábiles siguientes, decidirá si levanta total o parcialmente las glosas o las deja como definitivas. Si los prestadores no contestan en el plazo antes señalado, se entenderá aceptada la glosa. Si no hay acuerdo entre las partes, la entidad responsable del pago podrá optar por la conciliación, el arbitraje o acudir ante las autoridades judiciales.",
                "aplicacion": "PLAZOS DE GLOSAS: 30 días EPS para formular / 15 días IPS para responder / 7 días EPS para decidir",
                "keywords": ["glosa", "30 días", "15 días", "7 días", "plazo", "trámite de glosas", "extemporánea"],
            },
            "126": {
                "titulo": "Supervisión, inspección y vigilancia",
                "texto": "La Superintendencia Nacional de Salud tendrá la función jurisdiccional, sin perjuicio de la competencia de los jueces de la República, para conocer y fallar en derecho con carácter definitivo y con las facultades propias de un juez, los conflictos entre las entidades promotoras de salud y sus afiliados o entre las entidades territoriales y las entidades responsables del pago de los servicios de salud, y los prestadores de servicios de salud, en materia de glosas de facturas.",
                "aplicacion": "Función jurisdiccional SuperSalud para conflictos de glosas",
                "keywords": ["SuperSalud", "superintendencia", "conflicto", "jurisdiccional", "arbitraje"],
            },
        },
        "keywords": ["glosa", "plazo", "30 días", "trámite de glosas", "ratificación"],
    },

    "LEY 1751 DE 2015": {
        "nombre": "Ley 1751 de 2015 (Estatutaria de Salud)",
        "titulo": "Por medio de la cual se regula el derecho fundamental a la salud",
        "ambito": "Derecho fundamental a la salud",
        "vigente": True,
        "articulos": {
            "2": {
                "titulo": "Naturaleza y contenido del derecho fundamental a la salud",
                "texto": "El derecho fundamental a la salud es autónomo e irrenunciable en lo individual y en lo colectivo. Comprende los servicios de salud de manera oportuna, eficaz y con calidad para la preservación, el mejoramiento y la promoción de la salud.",
                "aplicacion": "Salud como derecho fundamental",
                "keywords": ["derecho fundamental", "salud", "autonomía"],
            },
            "15": {
                "titulo": "Prestaciones de salud — exclusiones",
                "texto": "El Sistema garantizará el derecho fundamental a la salud a través de la prestación de servicios y tecnologías, estructurados sobre una concepción integral de la salud, que incluya su promoción, la prevención, la paliación, la atención de la enfermedad y rehabilitación de sus secuelas. En todo caso, los recursos públicos asignados a la salud no podrán destinarse a financiar servicios y tecnologías en los que se advierta alguno de los siguientes criterios: a) Que tengan como finalidad principal un propósito cosmético o suntuario; b) Que no exista evidencia científica sobre su seguridad y eficacia; c) Que no exista evidencia científica sobre su efectividad clínica; d) Que su uso no haya sido autorizado por la autoridad competente; e) Que se encuentren en fase de experimentación; f) Que tengan que ser prestados en el exterior.",
                "aplicacion": "Exclusiones TAXATIVAS del sistema (6 causales)",
                "keywords": ["exclusiones", "PBS", "UPC", "cobertura"],
            },
            "17": {
                "titulo": "Autonomía profesional",
                "texto": "Se garantiza la autonomía de los profesionales de la salud para adoptar decisiones sobre el diagnóstico y tratamiento de los pacientes que tienen a su cargo. Esta autonomía será ejercida en el marco de esquemas de autorregulación, la ética, la racionalidad y la evidencia científica. Se prohíbe todo constreñimiento, presión o restricción del ejercicio profesional que atente contra la autonomía de los profesionales de la salud.",
                "aplicacion": "Autonomía médica = derecho fundamental",
                "keywords": ["autonomía médica", "médico tratante", "criterio clínico", "diagnóstico"],
            },
        },
        "keywords": ["estatutaria", "derecho fundamental", "autonomía"],
    },

    "LEY 1709 DE 2014": {
        "nombre": "Ley 1709 de 2014",
        "titulo": "Reforma Código Penitenciario y Carcelario — atención en salud a PPL",
        "ambito": "Cobertura salud Población Privada de Libertad",
        "vigente": True,
        "articulos": {
            "65": {
                "titulo": "Atención en salud a PPL",
                "texto": "El sistema de salud al interior de los establecimientos penitenciarios y carcelarios será diseñado e implementado por el Gobierno Nacional a través de los Ministerios competentes, con el fin de garantizar el derecho fundamental a la salud de los internos, así como de promover la salud, prevenir y controlar los principales riesgos.",
                "aplicacion": "Cobertura integral en salud para PPL",
                "keywords": ["PPL", "reclusos", "cárcel", "penitenciario"],
            },
        },
        "keywords": ["PPL", "penitenciario", "reclusos"],
    },

    "LEY 1562 DE 2012": {
        "nombre": "Ley 1562 de 2012",
        "titulo": "Modifica el Sistema de Riesgos Laborales",
        "ambito": "ARL — Riesgos Laborales",
        "vigente": True,
        "articulos": {
            "1": {
                "titulo": "Definiciones",
                "texto": "El Sistema General de Riesgos Laborales es el conjunto de entidades públicas y privadas, normas y procedimientos, destinados a prevenir, proteger y atender a los trabajadores de los efectos de las enfermedades y los accidentes que puedan ocurrirles con ocasión o como consecuencia del trabajo que desarrollan.",
                "aplicacion": "Marco general ARL",
                "keywords": ["ARL", "riesgos laborales", "accidente trabajo", "enfermedad laboral"],
            },
        },
        "keywords": ["ARL", "riesgos laborales", "Positiva", "Aurora"],
    },

    "LEY 352 DE 1997": {
        "nombre": "Ley 352 de 1997",
        "titulo": "Régimen de Salud de las Fuerzas Militares y Policía Nacional",
        "ambito": "Subsistema de Salud FF.MM. y Policía",
        "vigente": True,
        "articulos": {
            "7": {
                "titulo": "Subsistema de Salud",
                "texto": "El Subsistema de Salud de las Fuerzas Militares y de la Policía Nacional está integrado por los servicios de sanidad militar, los servicios de sanidad de la Policía Nacional y el sistema de seguridad social en salud para los miembros de las Fuerzas Militares y de la Policía Nacional, de sus beneficiarios y del personal civil del Ministerio de Defensa Nacional.",
                "aplicacion": "Marco normativo FF.MM./Policía",
                "keywords": ["FF.MM.", "policía", "sanidad militar", "subsistema"],
            },
        },
        "keywords": ["FF.MM.", "fuerzas militares", "policía", "sanidad"],
    },

    "LEY 91 DE 1989": {
        "nombre": "Ley 91 de 1989",
        "titulo": "Fondo Nacional de Prestaciones Sociales del Magisterio",
        "ambito": "FOMAG — Docentes oficiales",
        "vigente": True,
        "keywords": ["FOMAG", "magisterio", "docentes"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  DECRETOS
# ═══════════════════════════════════════════════════════════════════

DECRETOS = {
    "DECRETO 4747 DE 2007": {
        "nombre": "Decreto 4747 de 2007",
        "titulo": "Relaciones entre prestadores de servicios de salud y entidades responsables del pago",
        "ambito": "Trámite de glosas, facturación y conciliación",
        "vigente": True,
        "articulos": {
            "11": {
                "titulo": "Atención de urgencias",
                "texto": "La atención de urgencias se prestará con independencia de la existencia o no de un acuerdo de voluntades entre la entidad responsable del pago y el prestador de servicios de salud. Las entidades responsables del pago no podrán condicionar la atención inicial de urgencias a la existencia previa de autorización administrativa para el acceso a la prestación del servicio.",
                "aplicacion": "Urgencias sin autorización previa",
                "keywords": ["urgencia", "autorización", "atención inicial"],
            },
            "20": {
                "titulo": "Trámite de glosas — conciliación",
                "texto": "El trámite de glosas y de solicitudes de aclaraciones o ampliaciones es la instancia de conciliación entre el prestador de servicios de salud y la entidad responsable del pago, con el fin de resolver las discrepancias presentadas frente a los valores facturados. El trámite deberá agotarse dentro de los términos establecidos en el artículo 57 de la Ley 1438 de 2011 y podrá realizarse conforme al procedimiento de conciliación entre las partes.",
                "aplicacion": "Conciliación de auditoría como paso obligatorio antes de ratificación",
                "keywords": ["conciliación", "auditoría", "glosa", "trámite"],
            },
            "21": {
                "titulo": "Pago durante trámite de glosas",
                "texto": "Durante el trámite de las glosas, la entidad responsable del pago no podrá dejar de pagar el valor aceptado ni podrá condicionar el pago a la aceptación total de las glosas.",
                "aplicacion": "Pago parcial del valor aceptado durante glosa",
                "keywords": ["pago parcial", "glosa", "valor aceptado"],
            },
        },
        "keywords": ["glosa", "conciliación", "4747"],
    },

    "DECRETO 780 DE 2016": {
        "nombre": "Decreto 780 de 2016 (Decreto Único Reglamentario Sector Salud)",
        "titulo": "Decreto Único Reglamentario del Sector Salud y Protección Social",
        "ambito": "Marco general reglamentario sector salud",
        "vigente": True,
        "articulos": {
            "2.5.3.4.1.1": {
                "titulo": "Prohibición de auditoría previa como barrera",
                "texto": "No podrá establecerse la auditoría previa como barrera para la radicación de facturas por servicios de salud efectivamente prestados. La auditoría es un mecanismo posterior al pago y no un requisito previo.",
                "aplicacion": "PROHÍBE auditoría previa como barrera de radicación",
                "keywords": ["auditoría previa", "radicación", "barrera"],
            },
        },
        "keywords": ["decreto único", "reglamentario", "780"],
    },

    "DECRETO 441 DE 2022": {
        "nombre": "Decreto 441 de 2022",
        "titulo": "Actualiza acuerdos de voluntades entre prestadores y pagadores",
        "ambito": "Contratación — auditoría concurrente y administrativa",
        "vigente": True,
        "keywords": ["acuerdos voluntades", "auditoría concurrente", "contratación"],
    },

    "DECRETO 1795 DE 2000": {
        "nombre": "Decreto 1795 de 2000",
        "titulo": "Sistema de Salud de las Fuerzas Militares y la Policía Nacional",
        "ambito": "Subsistema FF.MM./Policía",
        "vigente": True,
        "articulos": {
            "6": {
                "titulo": "Cobertura",
                "texto": "El Sistema de Salud de las Fuerzas Militares y de la Policía Nacional garantizará la atención integral en salud a sus afiliados y beneficiarios, incluyendo servicios de baja, mediana y alta complejidad.",
                "aplicacion": "Cobertura integral FF.MM./Policía",
                "keywords": ["FF.MM.", "cobertura", "sanidad"],
            },
        },
        "keywords": ["FF.MM.", "policía", "sanidad militar"],
    },

    "DECRETO 2423 DE 1996": {
        "nombre": "Decreto 2423 de 1996",
        "titulo": "Manual de Tarifas SOAT",
        "ambito": "Tarifas SOAT — marco histórico",
        "vigente": True,
        "keywords": ["SOAT", "tarifa", "manual tarifario"],
    },

    "DECRETO 3752 DE 2003": {
        "nombre": "Decreto 3752 de 2003",
        "titulo": "Plan de Salud del Magisterio",
        "ambito": "FOMAG — Docentes oficiales",
        "vigente": True,
        "keywords": ["FOMAG", "magisterio", "docentes"],
    },

    "DECRETO 1295 DE 1994": {
        "nombre": "Decreto 1295 de 1994",
        "titulo": "Sistema General de Riesgos Profesionales",
        "ambito": "ARL",
        "vigente": True,
        "keywords": ["ARL", "riesgos profesionales"],
    },

    "DECRETO 1072 DE 2015": {
        "nombre": "Decreto 1072 de 2015",
        "titulo": "Decreto Único Reglamentario del Sector Trabajo",
        "ambito": "ARL — Libro 2 Parte 2 Título 4",
        "vigente": True,
        "keywords": ["ARL", "riesgos laborales", "decreto único trabajo"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  RESOLUCIONES
# ═══════════════════════════════════════════════════════════════════

RESOLUCIONES = {
    "RESOLUCION 2284 DE 2023": {
        "nombre": "Resolución 2284 de 2023 (MinSalud)",
        "titulo": "Manual Único de Devoluciones, Glosas y Respuestas",
        "ambito": "Norma maestra vigente — CÓDIGOS TAXATIVOS de glosas",
        "vigente": True,
        "anexos": {
            "Anexo Técnico No. 3": "Listado TAXATIVO de códigos de glosa (6 dígitos). La EPS no puede inventar códigos fuera de este catálogo.",
        },
        "reemplaza": "Resolución 3047/2008 Anexo Técnico 5 (que queda como antecedente procedimental)",
        "keywords": ["manual único", "glosas", "códigos taxativos", "2284", "anexo técnico 3"],
    },

    "RESOLUCION 1885 DE 2024": {
        "nombre": "Resolución 1885 de 2024 (MinSalud)",
        "titulo": "Cronograma gradual implementación Manual Único",
        "ambito": "Implementación Res. 2284/2023 por complejidad",
        "vigente": True,
        "articulos": {
            "cronograma": {
                "titulo": "Cronograma 2025",
                "texto": "Alta complejidad: desde 1-feb-2025. Mediana complejidad: desde 1-abr-2025. Baja complejidad: desde 1-jun-2025.",
                "aplicacion": "Plazos de implementación Manual Único",
                "keywords": ["cronograma", "alta complejidad", "implementación"],
            },
        },
        "keywords": ["cronograma", "implementación", "2025"],
    },

    "RESOLUCION 2275 DE 2023": {
        "nombre": "Resolución 2275 de 2023 (MinSalud)",
        "titulo": "Factura Electrónica de Venta en Salud (FEV) + RIPS",
        "ambito": "Facturación electrónica — validación previa MinSalud",
        "vigente": True,
        "keywords": ["FEV", "RIPS", "factura electrónica", "validación"],
    },

    "RESOLUCION 3047 DE 2008": {
        "nombre": "Resolución 3047 de 2008",
        "titulo": "Procedimiento glosas (antecedente)",
        "ambito": "Antecedente procedimental — desplazada por Res. 2284/2023",
        "vigente": True,
        "notas": "Sigue vigente como referente histórico y para casos en transición. El anexo técnico 5 fue reemplazado por Res. 2284/2023 Anexo 3.",
        "keywords": ["3047", "anexo técnico 5", "glosa", "antecedente"],
    },

    "RESOLUCION 5269 DE 2017": {
        "nombre": "Resolución 5269 de 2017 (MinSalud)",
        "titulo": "Plan de Beneficios en Salud (PBS)",
        "ambito": "Listado de servicios cubiertos por UPC",
        "vigente": True,
        "keywords": ["PBS", "plan beneficios", "UPC", "cobertura"],
    },

    "RESOLUCION 1995 DE 1999": {
        "nombre": "Resolución 1995 de 1999 (MinSalud)",
        "titulo": "Historia Clínica",
        "ambito": "Historia clínica como documento médico-legal",
        "vigente": True,
        "articulos": {
            "3": {
                "titulo": "Características de la historia clínica",
                "texto": "La historia clínica debe cumplir con las siguientes características: INTEGRALIDAD, SECUENCIALIDAD, RACIONALIDAD CIENTÍFICA, DISPONIBILIDAD y OPORTUNIDAD. La historia clínica es un documento privado, obligatorio y sometido a reserva.",
                "aplicacion": "Historia clínica = documento médico-legal de plena prueba",
                "keywords": ["historia clínica", "plena prueba", "reserva", "documento médico-legal"],
            },
        },
        "keywords": ["historia clínica", "1995", "documento médico-legal"],
    },

    "RESOLUCION 866 DE 2021": {
        "nombre": "Resolución 866 de 2021 (MinSalud)",
        "titulo": "Registros Individuales de Prestación de Servicios de Salud (RIPS)",
        "ambito": "RIPS obligatorios — reglamentación y generación",
        "vigente": True,
        "keywords": ["RIPS", "registros individuales", "866"],
    },

    "RESOLUCION 054 DE 2026": {
        "nombre": "Resolución 054 de 2026 (MinSalud)",
        "titulo": "Tarifas SOAT Plenas vigentes 2026",
        "ambito": "Tarifas SOAT expresadas en UVB",
        "vigente": True,
        "keywords": ["SOAT", "tarifa 2026", "UVB", "054"],
    },

    "RESOLUCION 2175 DE 2015": {
        "nombre": "Resolución 2175 de 2015",
        "titulo": "Procedimiento de conciliación de glosas médicas",
        "ambito": "Conciliación de auditoría médica",
        "vigente": True,
        "keywords": ["conciliación", "auditoría médica", "2175"],
    },

    "RESOLUCION 5159 DE 2015": {
        "nombre": "Resolución 5159 de 2015 (MinSalud)",
        "titulo": "Procedimiento atención salud PPL",
        "ambito": "Atención integral PPL",
        "vigente": True,
        "keywords": ["PPL", "reclusos", "5159"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  CIRCULARES
# ═══════════════════════════════════════════════════════════════════

CIRCULARES = {
    "CIRCULAR 025 DE 2024": {
        "nombre": "Circular 025 de 31-dic-2024 (MinSalud)",
        "titulo": "Manual Tarifario SOAT actualizado — UVB",
        "ambito": "Unidad de Valor Básico (UVB) vigente desde 01/01/2025",
        "vigente": True,
        "notas": "Reemplaza el uso de UVT (2023-2024). Todos los valores tarifarios SOAT se expresan ahora en UVB.",
        "keywords": ["UVB", "unidad valor básico", "025/2024", "SOAT"],
    },

    "CIRCULAR 030 DE 2013": {
        "nombre": "Circular 030 de 2013 (MinSalud)",
        "titulo": "Errores formales subsanables en facturación",
        "ambito": "Errores formales — NO causal de glosa",
        "vigente": True,
        "notas": "APLICA solo a errores verdaderamente formales (firma, fecha, código mal digitado). NO aplica a disputas sobre la naturaleza del servicio facturado (ej. FA0202 domiciliaria vs intrahospitalaria).",
        "keywords": ["errores formales", "subsanables", "030/2013", "circular"],
    },

    "CIRCULAR 007 DE 2025": {
        "nombre": "Circular Externa 007 de 2025 (MinSalud)",
        "titulo": "Cronograma implementación Manual Único de Glosas",
        "ambito": "Implementación Res. 2284/2023",
        "vigente": True,
        "keywords": ["cronograma", "implementación", "007/2025"],
    },

    "CIRCULAR 0000022 DE 2023": {
        "nombre": "Circular 0000022 de 2023 (MinSalud + DIAN)",
        "titulo": "Factura Electrónica de Venta en Salud",
        "ambito": "FEV en salud",
        "vigente": True,
        "keywords": ["FEV", "factura electrónica", "DIAN"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  CÓDIGOS
# ═══════════════════════════════════════════════════════════════════

CODIGOS = {
    "CODIGO DE COMERCIO - ARTICULO 871": {
        "nombre": "Código de Comercio Art. 871",
        "titulo": "Principio de buena fe contractual",
        "ambito": "Principio general contractual",
        "vigente": True,
        "texto": "Los contratos deberán celebrarse y ejecutarse de buena fe, y, en consecuencia, obligarán no sólo a lo pactado expresamente en ellos, sino a todo lo que corresponda a la naturaleza de los mismos, según la ley, la costumbre o la equidad natural.",
        "aplicacion": "Buena fe contractual — obliga a respetar tarifas pactadas y ejecutar contrato íntegramente",
        "keywords": ["buena fe", "contrato", "Art. 871", "C.Comercio"],
    },

    "CODIGO CIVIL - ARTICULO 1602": {
        "nombre": "Código Civil Art. 1602",
        "titulo": "Fuerza vinculante del contrato",
        "ambito": "Principio general contractual",
        "vigente": True,
        "texto": "Todo contrato legalmente celebrado es una ley para los contratantes, y no puede ser invalidado sino por su consentimiento mutuo o por causas legales.",
        "aplicacion": "El contrato es ley entre las partes. NO es 1601 — error común.",
        "keywords": ["contrato ley", "1602", "C.Civil", "fuerza vinculante"],
    },

    "CODIGO CIVIL - ARTICULO 1603": {
        "nombre": "Código Civil Art. 1603",
        "titulo": "Ejecución de buena fe",
        "ambito": "Principio general contractual",
        "vigente": True,
        "texto": "Los contratos deben ejecutarse de buena fe, y por consiguiente obligan no solo a lo que en ellos se expresa, sino a todas las cosas que emanan precisamente de la naturaleza de la obligación, o que por ley pertenecen a ella.",
        "aplicacion": "Ejecución contractual de buena fe (complemento Art. 1602)",
        "keywords": ["buena fe", "ejecución", "1603", "C.Civil"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  JURISPRUDENCIA (SENTENCIAS CONSTITUCIONALES)
# ═══════════════════════════════════════════════════════════════════

JURISPRUDENCIA = {
    "SENTENCIA T-760 DE 2008": {
        "nombre": "Sentencia T-760 de 2008",
        "corte": "Corte Constitucional",
        "magistrado_ponente": "Manuel José Cepeda Espinosa",
        "titulo": "Sentencia estructural — protección del derecho a la salud",
        "ratio": "Las EPS no pueden negar servicios cuando hay riesgo vital o documentación clínica que respalda la indicación. Obliga a las EPS a garantizar acceso oportuno.",
        "aplica_a": "EPS del régimen contributivo/subsidiado (NO aplica a Sanidad Militar, PPL, FOMAG, Policía)",
        "keywords": ["T-760", "derecho salud", "EPS", "negación servicios", "riesgo vital"],
    },

    "SENTENCIA T-1025 DE 2002": {
        "nombre": "Sentencia T-1025 de 2002",
        "corte": "Corte Constitucional",
        "titulo": "Urgencias sin autorización previa",
        "ratio": "Las urgencias son de cobertura obligatoria sin requisito de autorización previa. La autorización es administrativa y no puede condicionar la atención vital.",
        "aplica_a": "Urgencias — transversal a todos los regímenes",
        "keywords": ["T-1025", "urgencias", "autorización", "cobertura obligatoria"],
    },

    "SENTENCIA T-478 DE 1995": {
        "nombre": "Sentencia T-478 de 1995",
        "corte": "Corte Constitucional",
        "titulo": "Autonomía médica como derecho fundamental",
        "ratio": "La autonomía del médico tratante es un derecho fundamental protegido. El auditor administrativo no puede invalidar el criterio clínico desde revisión documental.",
        "aplica_a": "Glosas de pertinencia clínica (CL/PE)",
        "keywords": ["T-478", "autonomía médica", "médico tratante", "pertinencia"],
    },

    "SENTENCIA T-171 DE 2018": {
        "nombre": "Sentencia T-171 de 2018",
        "corte": "Corte Constitucional",
        "titulo": "Pertinencia médica y autoridad del tratante",
        "ratio": "El criterio del médico tratante prevalece sobre la auditoría administrativa cuando existe sustento clínico. La EPS no puede negar sin prueba técnica equivalente.",
        "aplica_a": "Defensa de pertinencia clínica y servicios especializados",
        "keywords": ["T-171", "pertinencia", "autoridad médica"],
    },

    "SENTENCIA T-134 DE 2022": {
        "nombre": "Sentencia T-134 de 2022",
        "corte": "Corte Constitucional",
        "titulo": "Oportunidad en prestación de servicios de salud",
        "ratio": "Las demoras administrativas en autorizaciones o pagos violan el derecho fundamental a la salud. Las EPS no pueden trasladar su ineficiencia a pacientes o prestadores.",
        "aplica_a": "Glosas administrativas que trasladan cargas indebidas a la IPS",
        "keywords": ["T-134", "oportunidad", "demoras administrativas"],
    },

    "SENTENCIA T-050 DE 2017": {
        "nombre": "Sentencia T-050 de 2017",
        "corte": "Corte Constitucional",
        "titulo": "Atención integral y continuidad del tratamiento",
        "ratio": "Los pacientes tienen derecho a recibir atención continua sin interrupciones por cambios de EPS o trámites administrativos. El prestador que garantizó continuidad debe ser remunerado íntegramente.",
        "aplica_a": "Continuidad de tratamiento, oncología, crónicos",
        "keywords": ["T-050", "continuidad", "atención integral"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  ACUERDOS ESPECIALES (SANIDAD MILITAR)
# ═══════════════════════════════════════════════════════════════════

ACUERDOS = {
    "ACUERDO 002 DE 2001 CSSFFMM": {
        "nombre": "Acuerdo 002 del 27-04-2001 Consejo Superior de Salud FF.MM.",
        "titulo": "Régimen de atención y remuneración a IPS prestadoras",
        "ambito": "Sanidad Militar — tarifas contractuales",
        "vigente": True,
        "notas": "Establece que la remuneración a las IPS que atienden población FF.MM. se rige íntegramente por las tarifas consignadas en los contratos interadministrativos.",
        "keywords": ["Acuerdo 002", "FF.MM.", "sanidad militar", "tarifas contractuales"],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  ÍNDICE UNIFICADO (para búsquedas)
# ═══════════════════════════════════════════════════════════════════

_TODAS_LAS_NORMAS = {
    **LEYES,
    **DECRETOS,
    **RESOLUCIONES,
    **CIRCULARES,
    **CODIGOS,
    **JURISPRUDENCIA,
    **ACUERDOS,
}


def _normalizar(texto: str) -> str:
    """Elimina acentos, pasa a minúsculas para búsqueda."""
    if not texto:
        return ""
    s = unicodedata.normalize("NFD", texto)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


def consultar_normativa(pregunta: str, limite: int = 5) -> List[dict]:
    """Busca normas que respondan la pregunta del usuario.

    Estrategia:
      1. Detecta si pregunta por norma específica (ej. "Art. 57 Ley 1438") → retorno directo.
      2. Si no, puntúa cada norma por coincidencia de keywords y texto.
      3. Retorna top N normas ordenadas por relevancia.

    Returns: lista de dicts con {norma, articulo, titulo, texto, keywords_match}
    """
    if not pregunta or not pregunta.strip():
        return []

    q = _normalizar(pregunta)

    # 1) Detección de norma específica por número
    # Ej: "ley 1438", "art 57 ley 1438", "resolución 2284", "decreto 4747"
    patrones_directos = [
        (r"(?:art[íi]culo|art\.?)\s*(\d+)\s+(?:de\s+la\s+)?ley\s+(\d+)", "LEY {1} DE {0}", "{0}"),
        (r"ley\s+(\d+)\s+(?:de\s+)?(\d{4})?", "LEY {0} DE {1}", None),
        (r"resoluci[oó]n\s+(\d+)\s+(?:de\s+)?(\d{4})?", "RESOLUCION {0} DE {1}", None),
        (r"decreto\s+(\d+)\s+(?:de\s+)?(\d{4})?", "DECRETO {0} DE {1}", None),
        (r"circular\s+(\d+)\s+(?:de\s+)?(\d{4})?", "CIRCULAR {0} DE {1}", None),
        (r"sentencia\s+t[-\s]?(\d+)\s+(?:de\s+)?(\d{4})?", "SENTENCIA T-{0} DE {1}", None),
    ]

    resultados_directos: List[dict] = []
    for pat, plantilla, articulo_grupo in patrones_directos:
        m = re.search(pat, q)
        if not m:
            continue
        grupos = m.groups()
        try:
            # Intenta match exacto; si falta año, busca por prefijo
            if grupos[-1]:  # hay año
                clave = plantilla.format(*grupos)
                for k in _TODAS_LAS_NORMAS:
                    if _normalizar(k) == _normalizar(clave):
                        norma = _TODAS_LAS_NORMAS[k]
                        resp = {
                            "norma": norma["nombre"],
                            "tipo": norma.get("ambito", ""),
                            "titulo": norma.get("titulo", ""),
                            "texto": norma.get("texto", ""),
                            "match_directo": True,
                        }
                        # Si preguntó por artículo específico
                        if articulo_grupo is not None and "articulos" in norma:
                            art_num = articulo_grupo.format(*grupos)
                            if art_num in norma["articulos"]:
                                art = norma["articulos"][art_num]
                                resp["articulo"] = art_num
                                resp["titulo"] = art["titulo"]
                                resp["texto"] = art["texto"]
                                resp["aplicacion"] = art.get("aplicacion", "")
                        resultados_directos.append(resp)
                        break
            else:  # sin año, match parcial por prefijo
                prefijo = plantilla.split(" ")[0] + " " + grupos[0] + " "
                for k, norma in _TODAS_LAS_NORMAS.items():
                    if _normalizar(k).startswith(_normalizar(prefijo)):
                        resultados_directos.append({
                            "norma": norma["nombre"],
                            "tipo": norma.get("ambito", ""),
                            "titulo": norma.get("titulo", ""),
                            "texto": norma.get("texto", ""),
                            "match_directo": True,
                        })
                        break
        except (IndexError, KeyError):
            continue

    if resultados_directos:
        return resultados_directos[:limite]

    # 2) Búsqueda por keywords (ranking)
    scored: List[tuple] = []
    terminos = [t for t in q.split() if len(t) > 2]

    for clave, norma in _TODAS_LAS_NORMAS.items():
        score = 0
        # keywords de la norma
        keywords_norma = [_normalizar(k) for k in norma.get("keywords", [])]
        for t in terminos:
            for kw in keywords_norma:
                if t in kw or kw in t:
                    score += 3
        # coincidencia en título/texto general
        texto_norma = _normalizar(" ".join([
            norma.get("titulo", ""),
            norma.get("ambito", ""),
            norma.get("texto", ""),
        ]))
        for t in terminos:
            if t in texto_norma:
                score += 1
        # artículos internos
        for art_num, art in norma.get("articulos", {}).items():
            art_text = _normalizar(" ".join([
                art.get("titulo", ""),
                art.get("texto", ""),
                art.get("aplicacion", ""),
                " ".join(art.get("keywords", [])),
            ]))
            art_score = 0
            for t in terminos:
                if t in art_text:
                    art_score += 2
            if art_score > 0:
                scored.append((
                    art_score + score,
                    {
                        "norma": norma["nombre"],
                        "articulo": art_num,
                        "titulo": art["titulo"],
                        "texto": art["texto"],
                        "aplicacion": art.get("aplicacion", ""),
                    },
                ))
        if score > 0:
            scored.append((
                score,
                {
                    "norma": norma["nombre"],
                    "tipo": norma.get("ambito", ""),
                    "titulo": norma.get("titulo", ""),
                    "texto": norma.get("texto", ""),
                },
            ))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in scored[:limite]]


def listar_todas_las_normas() -> List[dict]:
    """Retorna resumen de todas las normas indexadas."""
    return [
        {
            "clave": k,
            "nombre": v["nombre"],
            "tipo": v.get("ambito", ""),
            "titulo": v.get("titulo", ""),
            "vigente": v.get("vigente", True),
            "num_articulos": len(v.get("articulos", {})),
        }
        for k, v in _TODAS_LAS_NORMAS.items()
    ]


def normas_relevantes_para_codigo(codigo_glosa: str) -> List[str]:
    """Para un código de glosa (TA0801, FA0202, etc.), retorna las claves de
    normas más relevantes a citar en el argumento.
    """
    prefijo = (codigo_glosa or "")[:2].upper()
    mapping = {
        "TA": ["LEY 100 DE 1993", "CODIGO CIVIL - ARTICULO 1602", "CODIGO DE COMERCIO - ARTICULO 871", "RESOLUCION 054 DE 2026", "CIRCULAR 025 DE 2024"],
        "SO": ["RESOLUCION 1995 DE 1999", "RESOLUCION 866 DE 2021", "CIRCULAR 030 DE 2013", "RESOLUCION 2284 DE 2023"],
        "AU": ["LEY 100 DE 1993", "SENTENCIA T-1025 DE 2002", "DECRETO 4747 DE 2007"],
        "CO": ["LEY 1751 DE 2015", "RESOLUCION 5269 DE 2017", "SENTENCIA T-760 DE 2008"],
        "CL": ["LEY 1751 DE 2015", "SENTENCIA T-478 DE 1995", "SENTENCIA T-171 DE 2018", "RESOLUCION 1995 DE 1999"],
        "PE": ["LEY 1751 DE 2015", "SENTENCIA T-478 DE 1995", "RESOLUCION 1995 DE 1999"],
        "FA": ["LEY 100 DE 1993", "RESOLUCION 1995 DE 1999", "RESOLUCION 2284 DE 2023", "CODIGO DE COMERCIO - ARTICULO 871"],
        "IN": ["DECRETO 780 DE 2016", "CODIGO DE COMERCIO - ARTICULO 871", "RESOLUCION 5269 DE 2017"],
        "ME": ["LEY 1751 DE 2015", "RESOLUCION 5269 DE 2017", "SENTENCIA T-478 DE 1995"],
    }
    return mapping.get(prefijo, ["LEY 100 DE 1993", "RESOLUCION 2284 DE 2023"])

