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

from typing import List
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
                "keywords": [
                    "urgencia",
                    "urgencias",
                    "autorización previa",
                    "atención inicial",
                    "obligatoria",
                ],
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
            # Agregados el 24-08-2026, transcritos del PDF oficial del
            # Ministerio de Salud. Estaban citados en dictámenes reales y una
            # prueba de mayo de 2026 los daba por "citas inventadas": no lo
            # son, existen. El motor los borraba del documento radicado.
            "1": {
                "titulo": "Objeto de la ley",
                "texto": (
                    "Esta ley tiene como objeto el fortalecimiento del Sistema General de "
                    "Seguridad Social en Salud a través de un modelo de prestación del "
                    "servicio público en salud que en el marco de la estrategia Atención "
                    "Primaria en Salud permita la acción coordinada del Estado, las "
                    "instituciones y la sociedad para el mejoramiento de la salud y la "
                    "creación de un ambiente sano y saludable, que brinde servicios de mayor "
                    "calidad, incluyente y equitativo, donde el centro y objetivo de todos "
                    "los esfuerzos sean los residentes en el país."
                ),
                "aplicacion": "Marco general. Por sí solo no sustenta una defensa tarifaria.",
                "keywords": ["objeto", "fortalecimiento", "atención primaria"],
            },
            "2": {
                "titulo": "Orientación del Sistema General de Seguridad Social en Salud",
                "texto": (
                    "El Sistema General de Seguridad Social en Salud estará orientado a "
                    "generar condiciones que protejan la salud de los colombianos, siendo el "
                    "bienestar del usuario el eje central y núcleo articulador de las "
                    "políticas en salud. Para esto concurrirán acciones de salud pública, "
                    "promoción de la salud, prevención de la enfermedad y demás prestaciones "
                    "que, en el marco de una estrategia de Atención Primaria en Salud, sean "
                    "necesarias para promover de manera constante la salud de la población."
                ),
                "aplicacion": "Marco general. Por sí solo no sustenta una defensa tarifaria.",
                "keywords": ["orientación", "bienestar del usuario", "atención primaria"],
            },
            "56": {
                "titulo": "Trámite de pagos",
                "texto": "Las entidades responsables del pago de los servicios de salud deberán pagar a los prestadores el monto total de las facturas dentro de los treinta (30) días hábiles siguientes a la presentación de la factura. Cuando existan glosas, se aplicará el procedimiento señalado en el artículo siguiente. Sin perjuicio de lo anterior, dentro del mismo término, deberán haber efectuado un pago mínimo del 50% del valor neto facturado no sujeto a glosas, según corresponda. Nota operativa (Manual Único de Glosas Res. 2284/2023 + Manual SIIFA 2026): una vez levantada o aceptada la glosa, el pago al prestador debe efectuarse dentro de los cinco (5) días hábiles siguientes.",
                "aplicacion": "Pago total 30 días hábiles + anticipo 50% no sujeto a glosa + pago 5 días hábiles post-levantamiento",
                "keywords": [
                    "pago",
                    "30 días",
                    "50%",
                    "anticipo",
                    "trámite de pagos",
                    "5 días pago",
                ],
            },
            "57": {
                "titulo": "Trámite de glosas",
                "texto": "Las entidades responsables del pago de servicios de salud formularán y comunicarán a los prestadores de servicios de salud las glosas a cada factura, con base en la codificación y alcance definidos por el Ministerio de Salud y Protección Social. Una vez formuladas las glosas a una factura, no se podrán formular nuevas glosas a la misma factura, salvo las que surjan de hechos nuevos detectados en la respuesta dada a la glosa inicial. El prestador de servicios de salud deberá dar respuesta a las glosas presentadas por las entidades responsables del pago dentro del plazo fijado por la norma. Si los prestadores no contestan en el plazo señalado, se entenderá aceptada la glosa. Si no hay acuerdo entre las partes, la entidad responsable del pago podrá optar por la conciliación, el arbitraje o acudir ante las autoridades judiciales.\n\nPLAZOS OPERATIVOS VIGENTES (Ley 1438/2011 + Manual Único Res. 2284/2023 + Manual SIIFA 2026):\n• FORMULACIÓN (EPS/ERP): 20 días hábiles tras radicación de la factura.\n• RESPUESTA (IPS/Prestador): 15 días hábiles tras recepción de la glosa.\n• SUBSANACIÓN (IPS): 7 días hábiles adicionales si la glosa es subsanable.\n• DECISIÓN FINAL (EPS): 10 días hábiles tras la respuesta de la IPS para levantar o ratificar.\n• PAGO POST-LEVANTAMIENTO: 5 días hábiles siguientes al levantamiento de la glosa.\n\nCRITERIO INSTITUCIONAL HUS: toda glosa formulada después de 20 días hábiles es EXTEMPORÁNEA e improcedente (aceptación tácita).",
                "aplicacion": "PLAZOS: 20 días EPS formular | 15 días IPS responder | 7 días IPS subsanar | 10 días EPS decidir | 5 días EPS pagar tras levantamiento",
                "keywords": [
                    "glosa",
                    "20 días",
                    "15 días",
                    "7 días",
                    "10 días",
                    "5 días",
                    "plazo",
                    "trámite de glosas",
                    "extemporánea",
                    "subsanación",
                    "SIIFA",
                ],
            },
            "126": {
                "titulo": "Supervisión, inspección y vigilancia",
                "texto": "La Superintendencia Nacional de Salud tendrá la función jurisdiccional, sin perjuicio de la competencia de los jueces de la República, para conocer y fallar en derecho con carácter definitivo y con las facultades propias de un juez, los conflictos entre las entidades promotoras de salud y sus afiliados o entre las entidades territoriales y las entidades responsables del pago de los servicios de salud, y los prestadores de servicios de salud, en materia de glosas de facturas.",
                "aplicacion": "Función jurisdiccional SuperSalud para conflictos de glosas",
                "keywords": [
                    "SuperSalud",
                    "superintendencia",
                    "conflicto",
                    "jurisdiccional",
                    "arbitraje",
                ],
            },
            "105": {
                "titulo": "Prohibición de intromisión en el acto médico",
                "texto": "Las entidades responsables del pago de los servicios de salud no podrán interferir en la autonomía profesional del médico tratante, ni sustituir sus decisiones clínicas por consideraciones administrativas o económicas. El criterio del médico tratante prevalece sobre la opinión del auditor médico que no examinó al paciente. La violación de esta prohibición compromete la responsabilidad civil de la entidad pagadora por las consecuencias en la salud del usuario.",
                "aplicacion": "Defensa en glosas de PERTINENCIA CLÍNICA (CL/PE) — proscribe revisión administrativa del criterio médico",
                "keywords": [
                    "intromisión",
                    "acto médico",
                    "autonomía profesional",
                    "pertinencia clínica",
                    "criterio médico tratante",
                    "Art. 105",
                ],
            },
        },
        "keywords": [
            "glosa",
            "plazo",
            "30 días",
            "trámite de glosas",
            "ratificación",
            "intromisión acto médico",
        ],
    },
    "LEY 1751 DE 2015": {
        "nombre": "Ley 1751 de 2015 (Estatutaria de Salud)",
        "titulo": "Por medio de la cual se regula el derecho fundamental a la salud",
        "ambito": "Derecho fundamental a la salud",
        "vigente": True,
        "articulos": {
            # Agregado el 24-08-2026, transcrito del PDF oficial del Ministerio
            # de Salud. Una prueba de mayo de 2026 lo daba por "cita inventada":
            # no lo es, y el motor lo borraba del documento radicado.
            "1": {
                "titulo": "Objeto",
                "texto": (
                    "La presente ley tiene por objeto garantizar el derecho fundamental a la "
                    "salud, regularlo y establecer sus mecanismos de protección."
                ),
                "aplicacion": "Marco general del derecho fundamental a la salud.",
                "keywords": ["objeto", "derecho fundamental", "mecanismos de protección"],
            },
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
                "keywords": [
                    "autonomía médica",
                    "médico tratante",
                    "criterio clínico",
                    "diagnóstico",
                ],
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
    # ─── R52 B: ampliación catálogo legal ──────────────────────────────────
    "LEY 23 DE 1981": {
        "nombre": "Ley 23 de 1981",
        "titulo": "Normas en materia de Ética Médica",
        "ambito": "Ética profesional médica — historia clínica",
        "vigente": True,
        "articulos": {
            "34": {
                "titulo": "Historia clínica",
                "texto": "La historia clínica es el registro obligatorio de las condiciones de salud del paciente. Es un documento privado sometido a reserva que únicamente puede ser conocido por terceros previa autorización del paciente o en los casos previstos por la ley.",
            },
        },
        "keywords": ["ética médica", "historia clínica", "secreto profesional", "reserva"],
    },
    "LEY 715 DE 2001": {
        "nombre": "Ley 715 de 2001",
        "titulo": "Sistema General de Participaciones — recursos para salud",
        "ambito": "Distribución competencias y recursos del SGP en salud",
        "vigente": True,
        "keywords": ["SGP", "participaciones", "recursos", "competencias territoriales"],
    },
    "LEY 80 DE 1993": {
        "nombre": "Ley 80 de 1993 (Estatuto General de Contratación)",
        "titulo": "Estatuto General de la Contratación de la Administración Pública",
        "ambito": "Contratos estatales — aplicable a ESE HUS por ser ESE pública",
        "vigente": True,
        "articulos": {
            "23": {
                "titulo": "Principios de las actuaciones contractuales",
                "texto": "Las actuaciones de quienes intervengan en la contratación estatal se desarrollarán con arreglo a los principios de transparencia, economía y responsabilidad y de conformidad con los postulados que rigen la función administrativa. Igualmente, se aplicarán en las mismas las normas que regulan la conducta de los servidores públicos, las reglas de interpretación de la contratación, los principios generales del derecho y los particulares del derecho administrativo.",
                "aplicacion": "Principios rectores de los contratos estatales",
                "keywords": [
                    "transparencia",
                    "economía",
                    "responsabilidad",
                    "principios contratación estatal",
                    "Art. 23",
                ],
            },
            "27": {
                "titulo": "Ecuación contractual y equilibrio económico",
                "texto": "En los contratos estatales se mantendrá la igualdad o equivalencia entre derechos y obligaciones surgidos al momento de proponer o de contratar, según el caso. Si dicha igualdad o equivalencia se rompe por causas no imputables a quien resulte afectado, las partes adoptarán en el menor tiempo posible las medidas necesarias para su restablecimiento.",
                "aplicacion": "Defensa en glosas que rompen equilibrio económico del contrato (tarifas, descuentos unilaterales)",
                "keywords": [
                    "equilibrio económico",
                    "ecuación contractual",
                    "remuneración pactada",
                    "Art. 27",
                ],
            },
        },
        "keywords": [
            "contratación estatal",
            "Ley 80",
            "contrato interadministrativo",
            "ESE pública",
        ],
    },
    "LEY 1150 DE 2007": {
        "nombre": "Ley 1150 de 2007",
        "titulo": "Medidas para la eficiencia y transparencia en la Ley 80 de 1993",
        "ambito": "Contratación estatal — modalidades de selección y régimen aplicable",
        "vigente": True,
        "keywords": ["contratación estatal", "selección abreviada", "régimen ESE", "Ley 1150"],
    },
    "DECRETO 1082 DE 2015": {
        "nombre": "Decreto 1082 de 2015 (DUR Planeación)",
        "titulo": "Decreto Único Reglamentario del sector Administrativo de Planeación Nacional",
        "ambito": "Contratación estatal — reglamentación operativa",
        "vigente": True,
        "articulos": {
            "2.2.1.2.1.4.4": {
                "titulo": "Contratación de prestadores de servicios de salud",
                "texto": "Las entidades estatales que requieran contratar servicios de salud deberán seguir las reglas establecidas en este decreto, garantizando la libre concurrencia, la igualdad de los oferentes, la selección objetiva y el respeto a los principios de la función administrativa.",
                "aplicacion": "Reglamenta contratación de servicios de salud por ESE públicas",
                "keywords": [
                    "contratación servicios salud",
                    "ESE",
                    "Subsección IV",
                    "Art. 2.2.1.2.1.4.4",
                ],
            },
        },
        "keywords": ["contratación estatal", "DUR", "servicios de salud", "Decreto 1082"],
    },
    "LEY 599 DE 2000": {
        "nombre": "Ley 599 de 2000 (Código Penal)",
        "titulo": "Código Penal — delitos contra la fe pública y el patrimonio",
        "ambito": "Falsedad documental, fraude y peculado en glosas",
        "vigente": True,
        "articulos": {
            "286": {
                "titulo": "Falsedad ideológica en documento público",
                "texto": "El servidor público que en ejercicio de sus funciones, al extender documento público que pueda servir de prueba, consigne una falsedad o calle total o parcialmente la verdad, incurrirá en prisión de cuatro (4) a ocho (8) años e inhabilitación para el ejercicio de derechos y funciones públicas de cinco (5) a diez (10) años.",
            },
            "289": {
                "titulo": "Falsedad en documento privado",
                "texto": "El que falsifique documento privado que pueda servir de prueba, incurrirá, si lo usa, en prisión de uno (1) a seis (6) años.",
            },
        },
        "keywords": ["código penal", "falsedad documental", "fraude", "peculado"],
    },
    "LEY 1474 DE 2011": {
        "nombre": "Ley 1474 de 2011 (Estatuto Anticorrupción)",
        "titulo": "Normas para fortalecer mecanismos de prevención de la corrupción",
        "ambito": "Anticorrupción — recobros y facturación pública",
        "vigente": True,
        "keywords": ["anticorrupción", "estatuto", "transparencia", "recobros"],
    },
    "LEY 1581 DE 2012": {
        "nombre": "Ley 1581 de 2012",
        "titulo": "Régimen general de protección de datos personales (Habeas Data)",
        "ambito": "Datos sensibles del paciente — historia clínica digital",
        "vigente": True,
        "keywords": ["habeas data", "datos personales", "datos sensibles", "tratamiento"],
    },
    "LEY 1755 DE 2015": {
        "nombre": "Ley 1755 de 2015",
        "titulo": "Reglamentación del derecho fundamental de petición",
        "ambito": "Términos para responder peticiones de pacientes y entidades",
        "vigente": True,
        "articulos": {
            "14": {
                "titulo": "Términos para resolver",
                "texto": "Salvo norma legal especial y so pena de sanción disciplinaria, toda petición deberá resolverse dentro de los quince (15) días siguientes a su recepción. Para las peticiones de documentos y de información el término es de diez (10) días, y para consultas de las autoridades, treinta (30) días.",
            },
        },
        "keywords": ["derecho de petición", "términos", "respuesta", "Ley 1755"],
    },
    "LEY 1437 DE 2011 (CPACA)": {
        "nombre": "Ley 1437 de 2011 (CPACA)",
        "titulo": "Código de Procedimiento Administrativo y de lo Contencioso Administrativo",
        "ambito": "Actuaciones administrativas — procedimiento ante la administración",
        "vigente": True,
        "articulos": {
            "14": {
                "titulo": "Términos para resolver peticiones",
                "texto": "Las peticiones de documentos y de información deberán resolverse dentro de los diez (10) días siguientes a su recepción. Las demás peticiones, dentro de los quince (15) días.",
            },
            "164": {
                "titulo": "Caducidad — pretensión por reparación directa",
                "texto": "La caducidad de la pretensión de reparación directa será de dos (2) años contados desde el día siguiente a la ocurrencia del hecho, omisión, operación administrativa o de la ejecutoria del acto.",
            },
        },
        "keywords": ["CPACA", "procedimiento administrativo", "actuación", "caducidad"],
    },
    "LEY 1798 DE 2016": {
        "nombre": "Ley 1798 de 2016",
        "titulo": "Acceso de personas con discapacidad a servicios de salud — pago oportuno",
        "ambito": "Derechos de las personas con discapacidad en salud",
        "vigente": True,
        "keywords": ["discapacidad", "acceso", "pago oportuno", "barreras"],
    },
    "LEY 2294 DE 2023": {
        "nombre": "Ley 2294 de 2023",
        "titulo": "Plan Nacional de Desarrollo 2022–2026 'Colombia Potencia Mundial de la Vida'",
        "ambito": "PND — política pública de salud y giro directo a IPS",
        "vigente": True,
        "keywords": ["PND", "Plan Nacional de Desarrollo", "giro directo", "salud preventiva"],
    },
    # Ronda 15 (25-jun-2026, Bug P v2): leyes reales que el verifier
    # marcaba como inexistentes en producción.
    "LEY 1388 DE 2010": {
        "nombre": "Ley 1388 de 2010 (Cáncer infantil)",
        "titulo": "Derechos del menor con cáncer — acceso pleno a tratamientos oncológicos",
        "ambito": "Pediatría oncológica — protección reforzada del NNA",
        "vigente": True,
        "notas": "Garantiza la cobertura integral del tratamiento oncológico en menores (quimio, radio, cirugía, trasplante, terapias avanzadas) sin barreras administrativas. Reglamentada por Resolución 1383/2013.",
        "keywords": [
            "Ley 1388",
            "cáncer infantil",
            "pediatría oncológica",
            "atención integral menor",
        ],
    },
    "LEY 1392 DE 2010": {
        "nombre": "Ley 1392 de 2010 (Enfermedades huérfanas)",
        "titulo": "Reconocimiento, atención e investigación de enfermedades huérfanas",
        "ambito": "Enfermedades huérfanas (raras) — hemofilia, Gaucher, Pompe, etc.",
        "vigente": True,
        "notas": "Reconoce las enfermedades huérfanas como problema de salud pública con tratamiento prioritario. Las barreras administrativas (CTC vencido, MIPRES extemporáneo) NO son oponibles a la continuidad del tratamiento. Reglamentada por Decreto 1954/2012.",
        "keywords": ["Ley 1392", "enfermedades huérfanas", "raras", "hemofilia", "Gaucher"],
    },
    "LEY 1616 DE 2013": {
        "nombre": "Ley 1616 de 2013 (Salud Mental)",
        "titulo": "Ley de Salud Mental — atención integral en salud mental",
        "ambito": "Salud mental — derechos del paciente psiquiátrico",
        "vigente": True,
        "articulos": {
            "art_11": {
                "titulo": "Consentimiento informado en salud mental",
                "texto": "El consentimiento informado en salud mental se otorga por la propia persona; en su ausencia por incapacidad transitoria de juicio (psicosis aguda, riesgo suicida inminente), se acepta consentimiento sustitutivo del cónyuge o familiar de primer grado documentado en historia clínica.",
                "aplicacion": "Defensa de ECT/internación involuntaria sin firma del paciente",
                "keywords": ["consentimiento informado", "capacidad de juicio", "sustitutivo"],
            },
        },
        "keywords": [
            "Ley 1616",
            "salud mental",
            "psiquiatría",
            "consentimiento",
            "internación involuntaria",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════
#  DECRETOS
# ═══════════════════════════════════════════════════════════════════

DECRETOS = {
    # 11-jun-2026: el texto fijo DMBUG cita el art. 71 del Estatuto
    # Orgánico del Presupuesto (defensa "agotamiento presupuestal es
    # responsabilidad del contratante") y el verifier lo marcaba
    # NORMA_INEXISTENTE ALTA por no estar en el corpus — falso positivo
    # que tumbaba la EVIDENCIA del dictamen a C sobre un texto curado.
    "DECRETO 111 DE 1996": {
        "nombre": "Decreto 111 de 1996",
        "titulo": "Estatuto Orgánico del Presupuesto (compila Leyes 38/1989, 179/1994 y 225/1995)",
        "ambito": "Gestión presupuestal de entidades públicas — defensa contra glosas por 'agotamiento presupuestal'",
        "vigente": True,
        "articulos": {
            "71": {
                "titulo": "Certificado de disponibilidad presupuestal",
                "texto": "Todos los actos administrativos que afecten las apropiaciones presupuestales deberán contar con certificados de disponibilidad previos que garanticen la existencia de apropiación suficiente para atender estos gastos.",
                "aplicacion": "La gestión de apropiaciones presupuestales es obligación del contratante público; el agotamiento del valor comprometido no se traslada al prestador ni extingue las tarifas pactadas",
                "keywords": ["presupuesto", "apropiación", "disponibilidad", "agotamiento", "CDP"],
            },
        },
        "keywords": [
            "estatuto orgánico",
            "presupuesto",
            "apropiaciones",
            "agotamiento presupuestal",
        ],
    },
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
        # El Art. 87 se agregó el 24-08-2026. El dictamen GL-207 (AURORA) lo
        # citó completo para defender una tarifa propia del hospital, y el
        # sistema no lo tenía: no podía respaldar una cita que resultó ser
        # CORRECTA. Transcrito del PDF oficial del Ministerio de Salud ese
        # mismo día (decreto-2423-de-1996.pdf, 149 páginas, 241 artículos).
        # Es el fundamento de la tarifa institucional cuando el procedimiento
        # no está en el manual: sirve seguido en glosas de mayor valor cobrado.
        "articulos": {
            "87": {
                "titulo": "Procedimiento sin tarifa asignada — tarifa de la institución",
                "texto": (
                    "Por las circunstancias de orden tecnológico, cuando alguna Institución "
                    "Prestadora de Servicios de Salud realice un procedimiento que no se "
                    "encuentre definido y por lo tanto no tenga asignada tarifa, éste se "
                    "reconocerá por la tarifa que tenga definida la Institución, previa la "
                    "comprobación del médico tratante, de que dicho procedimiento no se "
                    "encuentra relacionado en el presente Decreto ni siquiera bajo otra "
                    "denominación."
                ),
                "aplicacion": (
                    "Glosas de mayor valor cobrado sobre procedimientos que el manual SOAT "
                    "no tiene tarifados. OJO: el propio artículo exige la comprobación del "
                    "médico tratante de que el procedimiento no está en el decreto ni bajo "
                    "otro nombre — sin esa comprobación el argumento queda cojo."
                ),
                "keywords": [
                    "tarifa institucional",
                    "procedimiento no definido",
                    "sin tarifa asignada",
                    "mayor valor cobrado",
                ],
            },
        },
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
    # ─── R52 B: ampliación catálogo ────────────────────────────────────────
    "DECRETO 1011 DE 2006": {
        "nombre": "Decreto 1011 de 2006",
        "titulo": "Sistema Obligatorio de Garantía de Calidad de la Atención de Salud (SOGCS)",
        "ambito": "Habilitación, auditoría y acreditación de servicios",
        "vigente": True,
        "keywords": ["SOGCS", "habilitación", "calidad", "auditoría servicios salud"],
    },
    "DECRETO 1683 DE 2013": {
        "nombre": "Decreto 1683 de 2013",
        "titulo": "Portabilidad nacional en el SGSSS",
        "ambito": "Garantía de prestación a afiliados fuera de su municipio de afiliación",
        "vigente": True,
        "keywords": ["portabilidad", "afiliación nacional", "atención fuera del domicilio"],
    },
    "DECRETO 2353 DE 2015": {
        "nombre": "Decreto 2353 de 2015",
        "titulo": "Régimen unificado de afiliación al SGSSS",
        "ambito": "Afiliación, traslado, movilidad de regímenes",
        "vigente": True,
        "keywords": [
            "afiliación",
            "traslado",
            "movilidad régimen",
            "régimen contributivo subsidiado",
        ],
    },
    "DECRETO 866 DE 2017": {
        "nombre": "Decreto 866 de 2017",
        "titulo": "Pago de servicios y tecnologías no incluidas en el Plan de Beneficios",
        "ambito": "Recobros — flujo de recursos por servicios NO PBS",
        "vigente": True,
        "keywords": ["recobros", "no PBS", "MIPRES", "ADRES"],
    },
    "DECRETO 538 DE 2020": {
        "nombre": "Decreto 538 de 2020",
        "titulo": "Medidas en el sector salud durante la emergencia COVID-19",
        "ambito": "Excepciones a plazos y procedimientos durante pandemia",
        "vigente": True,
        "notas": "Continúa siendo invocado para casos de auditoría retroactiva sobre atenciones COVID 2020-2022.",
        "keywords": ["COVID-19", "pandemia", "emergencia sanitaria", "excepciones"],
    },
    "DECRETO 064 DE 2020": {
        "nombre": "Decreto 064 de 2020",
        "titulo": "Reglamento del aseguramiento — flujo de recursos del SGSSS",
        "ambito": "Pago a IPS, giro directo, glosas",
        "vigente": True,
        "keywords": ["flujo recursos", "aseguramiento", "giro directo IPS"],
    },
    # Ronda 14 (Bug P): normas reales que el verifier marcaba como
    # inexistentes en producción.
    "DECRETO 2493 DE 2004": {
        "nombre": "Decreto 2493 de 2004 (MinProtección Social)",
        "titulo": "Régimen general de obtención, donación, preservación y trasplante de componentes anatómicos",
        "ambito": "Trasplantes — atención del donante y receptor",
        "vigente": True,
        "articulos": {
            "general": {
                "titulo": "Cobertura integral del proceso de trasplante",
                "texto": "La atención del donante cadavérico (extracción, preservación, transporte del órgano) y la del receptor (pre, intra y postoperatoria, inmunosupresión incluida) son responsabilidad ÍNTEGRA de la entidad pagadora del receptor, independientemente del estatus de afiliación del donante.",
                "aplicacion": "Defensa de glosas de trasplante por 'donante no afiliado'",
                "keywords": ["donante", "trasplante", "extracción", "receptor"],
            },
        },
        "keywords": ["Decreto 2493", "trasplante", "donante", "componente anatómico", "INS"],
    },
    "DECRETO 600 DE 2017": {
        "nombre": "Decreto 600 de 2017 (Min. Justicia + MinSalud)",
        "titulo": "Atención en salud para Población Privada de la Libertad (PPL)",
        "ambito": "PPL — financiamiento vía Fondo Nacional de Salud PPL administrado por Fiduprevisora",
        "vigente": True,
        "notas": "Establece que las atenciones a PPL se cargan al Fondo Nacional, no a la EPS contributiva del núcleo familiar — salvo urgencia vital ya iniciada.",
        "keywords": ["Decreto 600", "PPL", "INPEC", "Fiduprevisora", "fondo PPL"],
    },
    "DECRETO 4725 DE 2005": {
        "nombre": "Decreto 4725 de 2005 (MinProtección Social)",
        "titulo": "Régimen de registros sanitarios INVIMA para dispositivos médicos",
        "ambito": "Dispositivos médicos — registro, vigilancia, renovación",
        "vigente": True,
        "articulos": {
            "art_35": {
                "titulo": "Vigencia y renovación del registro sanitario",
                "texto": "El registro sanitario tiene vigencia de 10 años renovable. Si se radica la solicitud de renovación antes del vencimiento, el registro se entiende vigente hasta el pronunciamiento del INVIMA (extensión automática).",
                "aplicacion": "Defensa de glosas por uso de dispositivo con registro 'vencido' pero en proceso de renovación",
                "keywords": [
                    "registro sanitario",
                    "vencimiento",
                    "renovación",
                    "extensión automática",
                ],
            },
        },
        "keywords": [
            "Decreto 4725",
            "dispositivos médicos",
            "INVIMA",
            "registro sanitario",
            "renovación",
        ],
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
    # Ronda 14 (Bug P): la Resolución 1885 de 2018 es la del MIPRES
    # (Mi Prescripción), distinta a la Resolución 1885 de 2024 que el
    # corpus ya tenía (esa es de cronograma del Manual Único). El verifier
    # marcaba la de 2018 como inexistente porque solo tenía la de 2024.
    "RESOLUCION 1885 DE 2018": {
        "nombre": "Resolución 1885 de 2018 (MinSalud)",
        "titulo": "Procedimiento MIPRES — prescripción de servicios y tecnologías no incluidas en PBS",
        "ambito": "Prescripción NoPBS — vigencia de la prescripción y trámite",
        "vigente": True,
        "articulos": {
            "art_14": {
                "titulo": "Vigencia de la prescripción MIPRES",
                "texto": "La prescripción tiene vigencia equivalente a la duración del tratamiento prescrito por el médico tratante. La continuidad del tratamiento en hospitalización por descompensación clínica no requiere nueva prescripción si el evento clínico es el mismo.",
                "aplicacion": "Defensa de glosas por 'MIPRES vencido' cuando la atención hospitalaria continúa el tratamiento crónico",
                "keywords": ["vigencia MIPRES", "continuidad", "tratamiento crónico"],
            },
            "art_22": {
                "titulo": "MIPRES en eventos especiales — junta médica",
                "texto": "En urgencia vital o tratamiento iniciado prequirúrgicamente (inducción inmunológica en trasplantes), la prescripción MIPRES puede radicarse antes o durante el evento; el rigor administrativo NO impide la cobertura del tratamiento.",
                "aplicacion": "Defensa de inmunosupresión PRE-trasplante prescrita antes de la cirugía",
                "keywords": ["MIPRES contingencia", "trasplante", "urgencia vital"],
            },
        },
        "keywords": ["Resolución 1885", "MIPRES", "no PBS", "prescripción"],
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
            # Estos dos artículos estaban pegados en uno solo (24-08-2026). El
            # texto del Art. 3 traía al final «la historia clínica es un
            # documento privado, obligatorio y sometido a reserva», que no es
            # del Art. 3 sino del literal a) del Art. 1. Los dictámenes copiaban
            # la frase completa entre comillas y se la atribuían al Art. 3, así
            # que media cita quedaba mal atribuida. Lo detectó la segunda
            # auditoría independiente. Ambos textos se transcribieron del PDF
            # oficial del Ministerio de Salud ese mismo día.
            "1": {
                "titulo": "Definiciones",
                "texto": (
                    "La Historia Clínica es un documento privado, obligatorio y sometido a "
                    "reserva, en el cual se registran cronológicamente las condiciones de "
                    "salud del paciente, los actos médicos y los demás procedimientos "
                    "ejecutados por el equipo de salud que interviene en su atención. Dicho "
                    "documento únicamente puede ser conocido por terceros previa autorización "
                    "del paciente o en los casos previstos por la ley."
                ),
                "aplicacion": "Definición legal de la historia clínica y su reserva",
                "keywords": [
                    "historia clínica",
                    "documento privado",
                    "reserva",
                    "definición",
                ],
            },
            "3": {
                "titulo": "Características de la historia clínica",
                "texto": (
                    "Las características básicas son: Integralidad: la historia clínica de un "
                    "usuario debe reunir la información de los aspectos científicos, técnicos "
                    "y administrativos relativos a la atención en salud. Secuencialidad: los "
                    "registros de la prestación de los servicios en salud deben consignarse en "
                    "la secuencia cronológica en que ocurrió la atención. Racionalidad "
                    "científica: es la aplicación de criterios científicos en el "
                    "diligenciamiento y registro de las acciones en salud brindadas a un "
                    "usuario, de modo que evidencie en forma lógica, clara y completa el "
                    "procedimiento que se realizó. Disponibilidad: es la posibilidad de "
                    "utilizar la historia clínica en el momento en que se necesita, con las "
                    "limitaciones que impone la Ley. Oportunidad: es el diligenciamiento de "
                    "los registros de atención de la historia clínica, simultánea o "
                    "inmediatamente después de que ocurre la prestación del servicio."
                ),
                "aplicacion": "Historia clínica = documento médico-legal de plena prueba",
                "keywords": [
                    "historia clínica",
                    "plena prueba",
                    "reserva",
                    "documento médico-legal",
                ],
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
    "CIRCULAR 047 DE 2025": {
        "nombre": "Circular Externa 047 de 2025 (MinSalud)",
        "titulo": "Manual Tarifario SOAT 2026 indexado a UVB",
        "ambito": "Tarifas SOAT 2026 expresadas en UVB. UVB 2026 = $12.110. Fórmula: Tarifa_UVB × $12.110 → centena más próxima.",
        "vigente": True,
        "keywords": ["SOAT", "tarifa 2026", "UVB", "047", "circular externa", "manual tarifario"],
    },
    "RESOLUCION 054 DE 2026": {
        "nombre": "Resolución 054 de enero 30 de 2026 (ESE HUS)",
        "titulo": "Listado unificado de tarifas institucionales propias del HUS",
        "ambito": "Tarifas propias expresadas en FACTOR SMDLV. Aplica cuando el contrato dice 'TIPO TARIFA = PROPIAS'",
        "vigente": True,
        "keywords": [
            "tarifas propias",
            "HUS",
            "054",
            "propia",
            "manual HUS",
            "SMDLV",
            "institucional",
        ],
    },
    "RESOLUCION 124 DE 2026": {
        "nombre": "Resolución 124 de marzo 25 de 2026 (ESE HUS)",
        "titulo": "Nuevas tarifas institucionales HUS + modificaciones Res. 054",
        "ambito": "Laboratorio clínico, quirúrgicos, electrofisiología, patología, gineco-oncológicos. Fórmula: FACTOR × SMDLV 2026 (≈ $58.375)",
        "vigente": True,
        "keywords": [
            "tarifas propias",
            "HUS",
            "124",
            "institucional",
            "SMDLV",
            "laboratorio",
            "quirurgicos",
        ],
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
    # Ronda 48: Resolución 2641 de 2025 — Clasificación CUPS y tabla de
    # homologación oficial entre códigos internos de prestadores y la
    # numeración vigente (CUPS 2025).
    "RESOLUCION 2641 DE 2025": {
        "nombre": "Resolución 2641 de 2025 (MinSalud)",
        "titulo": "Clasificación Única de Procedimientos en Salud (CUPS) versión 2025 — Tabla de homologación oficial",
        "ambito": (
            "Reemplaza la Res. 2341 de 2024 (CUPS 2024) y establece la "
            "TABLA DE HOMOLOGACIÓN entre códigos internos de prestadores "
            "(ej. códigos institucionales HUS con sufijo H, H1, H2, o con "
            "versión -18/-16/-19) y la numeración CUPS oficial vigente. "
            "De OBLIGATORIO CUMPLIMIENTO para RIPS, FEV y todo reporte "
            "de cuentas médicas. En el sistema IA GLOSAS SINAC la "
            "equivalencia se aplica automáticamente cuando la EPS glosa "
            "con el código viejo — ver homologador_cups.py."
        ),
        "vigente": True,
        "articulos": {
            "uso_obligatorio": {
                "titulo": "Uso obligatorio de CUPS 2025",
                "texto": (
                    "Todos los prestadores y entidades responsables del pago "
                    "deberán emplear la numeración CUPS 2025 establecida en "
                    "esta resolución para la facturación, glosa, conciliación "
                    "y reporte al Registro Individual de Prestación de "
                    "Servicios de Salud (RIPS, Res. 202/2021 y 2275/2023 FEV). "
                    "Cuando el Excel del contrato o la factura traiga el "
                    "código interno del prestador (ej. '39147B-18', '890348H', "
                    "'372301H'), se entenderá equivalente al CUPS 2025 oficial "
                    "según la tabla de homologación del Anexo Técnico."
                ),
                "aplicacion": (
                    "Ante glosas con código viejo, aplicar homologación "
                    "Res. 2641/2025 antes de evaluar la tarifa pactada. "
                    "El sistema lo hace automáticamente vía codigo_ips + "
                    "homologador_cups.py."
                ),
                "keywords": [
                    "CUPS 2025",
                    "homologación",
                    "equivalencia",
                    "código interno",
                    "código viejo",
                    "2641",
                    "RIPS",
                    "FEV",
                ],
            },
        },
        "keywords": [
            "CUPS",
            "2641",
            "homologación",
            "clasificación única",
            "procedimientos",
            "código interno",
            "MinSalud 2025",
        ],
    },
    "RESOLUCION 2341 DE 2024": {
        "nombre": "Resolución 2341 de 2024 (MinSalud)",
        "titulo": "Clasificación Única de Procedimientos en Salud (CUPS) versión 2024 (antecedente)",
        "ambito": (
            "Antecesora de la Res. 2641/2025. Vigente hasta la entrada de "
            "CUPS 2025. Los archivos históricos pueden traer referencia a "
            "'CUPS 2341/24'."
        ),
        "vigente": False,
        "keywords": ["CUPS 2024", "2341", "clasificación única"],
    },
    # ─── R52 B: ampliación catálogo ────────────────────────────────────────
    "RESOLUCION 412 DE 2000": {
        "nombre": "Resolución 412 de 2000 (MinSalud)",
        "titulo": "Guías de Atención Integral y normas técnicas obligatorias",
        "ambito": "Pertinencia clínica — actividades, intervenciones y procedimientos POS",
        "vigente": True,
        "keywords": [
            "guías de atención",
            "PAI",
            "promoción y prevención",
            "actividades de detección",
        ],
    },
    "RESOLUCION 5261 DE 1994": {
        "nombre": "Resolución 5261 de 1994 (MAPIPOS)",
        "titulo": "Manual de Actividades, Procedimientos e Intervenciones del POS",
        "ambito": "Histórica — base de tarifas SOAT y referente histórico",
        "vigente": False,
        "notas": "Si bien fue derogada por Res. 5521/2013 y posteriores, sigue siendo referida como histórica para discusión de tarifas SOAT en glosas extemporáneas.",
        "keywords": ["MAPIPOS", "tarifas históricas", "SOAT histórico"],
    },
    "RESOLUCION 5521 DE 2013": {
        "nombre": "Resolución 5521 de 2013 (MinSalud)",
        "titulo": "Plan Obligatorio de Salud (POS) — actualización",
        "ambito": "Cobertura — incluye/excluye procedimientos del POS",
        "vigente": False,
        "notas": "Reemplazada por Res. 5857/2018 y luego Res. 2481/2020 (PBS).",
        "keywords": ["POS", "plan obligatorio", "cobertura POS", "exclusión POS"],
    },
    "RESOLUCION 5857 DE 2018": {
        "nombre": "Resolución 5857 de 2018 (MinSalud)",
        "titulo": "Plan de Beneficios en Salud con cargo a la UPC (PBS)",
        "ambito": "Cobertura — financiación con UPC",
        "vigente": False,
        "notas": "Reemplazada por Res. 2481/2020.",
        "keywords": ["PBS", "UPC", "plan beneficios", "cobertura UPC"],
    },
    "RESOLUCION 2481 DE 2020": {
        "nombre": "Resolución 2481 de 2020 (MinSalud)",
        "titulo": "Listado de tecnologías de salud financiadas con UPC",
        "ambito": "Cobertura PBS vigente",
        "vigente": True,
        "keywords": ["PBS", "UPC", "Res. 2481", "listado financiado"],
    },
    "RESOLUCION 4505 DE 2012": {
        "nombre": "Resolución 4505 de 2012 (MinSalud)",
        "titulo": "Reporte de información a Programas de Atención a Eventos de Interés en Salud Pública",
        "ambito": "PAI, gestación, salud bucal, RCV — reportes obligatorios",
        "vigente": True,
        "keywords": ["PVE", "eventos salud pública", "reporte", "gestación", "PAI"],
    },
    "RESOLUCION 256 DE 2016": {
        "nombre": "Resolución 256 de 2016 (MinSalud)",
        "titulo": "Sistema de Información para la Calidad — indicadores",
        "ambito": "SOGCS — reporte obligatorio de indicadores trazadores",
        "vigente": True,
        "keywords": ["calidad", "indicadores trazadores", "SOGCS", "monitoría"],
    },
    "RESOLUCION 3100 DE 2019": {
        "nombre": "Resolución 3100 de 2019 (MinSalud)",
        "titulo": "Procedimientos y condiciones de inscripción de prestadores y habilitación de servicios",
        "ambito": "Habilitación de servicios — base para auditoría de pertinencia",
        "vigente": True,
        "keywords": ["habilitación", "REPS", "registro especial prestadores", "estándares"],
    },
    "RESOLUCION 202 DE 2021": {
        "nombre": "Resolución 202 de 2021 (MinSalud)",
        "titulo": "Lineamientos del RIPS (Registro Individual de Prestación de Servicios de Salud)",
        "ambito": "RIPS — estructura obligatoria de archivos planos",
        "vigente": True,
        "keywords": ["RIPS", "Res. 202", "registros prestación servicios", "archivos planos"],
    },
    "RESOLUCION 1441 DE 2013": {
        "nombre": "Resolución 1441 de 2013 (MinSalud)",
        "titulo": "Definición de procedimientos y condiciones para inscripción y habilitación",
        "ambito": "Habilitación — antecesora de Res. 3100/2019",
        "vigente": False,
        "keywords": ["habilitación 2013", "Res. 1441"],
    },
    "RESOLUCION 1604 DE 2013": {
        "nombre": "Resolución 1604 de 2013 (MinSalud)",
        "titulo": "Procedimiento de glosas para servicios de salud",
        "ambito": "Glosas — antecesora del Manual Único 2284/2023",
        "vigente": False,
        "notas": "Reemplazada por Res. 2284/2023. Aún se cita en glosas extemporáneas con eventos pre-julio 2023.",
        "keywords": ["Res. 1604", "glosas históricas", "manual glosas 2013"],
    },
    "RESOLUCION 4331 DE 2012": {
        "nombre": "Resolución 4331 de 2012 (MinSalud)",
        "titulo": "Pago de servicios prestados por urgencias a no afiliados",
        "ambito": "Urgencias — flujo de recursos para pacientes no asegurados",
        "vigente": True,
        "keywords": ["urgencias", "no afiliados", "ADRES", "FOSYGA"],
    },
    "RESOLUCION 2003 DE 2014": {
        "nombre": "Resolución 2003 de 2014 (MinSalud)",
        "titulo": "Sistema Único de Habilitación — manual de inscripción",
        "ambito": "Habilitación — manual de criterios",
        "vigente": False,
        "notas": "Antecesora de Res. 3100/2019.",
        "keywords": ["Res. 2003", "habilitación 2014", "manual inscripción"],
    },
    "RESOLUCION 1604 DE 2024": {
        "nombre": "Resolución 1604 de 2024 (MinSalud)",
        "titulo": "Modificaciones al RIPS y FEV — actualizaciones técnicas",
        "ambito": "RIPS y Factura Electrónica de Venta",
        "vigente": True,
        "keywords": ["RIPS 2024", "FEV", "actualización", "Res. 2275"],
    },
    "RESOLUCION 754 DE 2024": {
        "nombre": "Resolución 754 de 2024 (MinSalud)",
        "titulo": "Periodicidad y reportes de PVE",
        "ambito": "Programas de Vigilancia Epidemiológica — periodicidad",
        "vigente": True,
        "keywords": ["PVE", "vigilancia epidemiológica", "periodicidad reporte"],
    },
    "RESOLUCION 042 DE 2020": {
        "nombre": "Resolución 000042 de 2020 (DIAN)",
        "titulo": "Sistema de facturación electrónica de venta",
        "ambito": "Factura Electrónica de Venta (FEV), CUFE, requisitos técnicos DIAN",
        "vigente": True,
        "keywords": [
            "factura electrónica",
            "FEV",
            "CUFE",
            "facturación electrónica",
            "DIAN",
            "Res. 042/2020",
            "Resolución 042 2020",
        ],
        "texto": (
            "La Resolución 000042 de 2020 expedida por la DIAN establece los "
            "requisitos del sistema de facturación electrónica de venta en Colombia, "
            "incluyendo la generación del CUFE (Código Único de Facturación "
            "Electrónica), los formatos XML, los plazos de transmisión y los "
            "requisitos formales de la Factura Electrónica de Venta (FEV)."
        ),
    },
    # Ronda 15 (Bug P v2): resoluciones reales que aparecieron en producción
    # marcadas como inexistentes.
    "RESOLUCION 1652 DE 2021": {
        "nombre": "Resolución 1652 de 2021 (MinSalud)",
        "titulo": "Programa de Atención Integral en Hemofilia y otras coagulopatías congénitas (PAB)",
        "ambito": "Hemofilia — auto-administración domiciliaria, profilaxis",
        "vigente": True,
        "notas": "Reconoce la auto-administración domiciliaria del Factor VIII/IX/VIIa como modalidad estándar en pacientes con hemofilia severa, evitando el riesgo de hemartrosis por desplazamiento. La EPS NO puede exigir asistencia institucional cada 48h.",
        "keywords": ["Resolución 1652", "hemofilia", "PAB", "Factor VIII", "auto-administración"],
    },
    "RESOLUCION 2292 DE 2021": {
        "nombre": "Resolución 2292 de 2021 (MinSalud)",
        "titulo": "Actualización del Plan de Beneficios en Salud (PBS) con cargo a la UPC",
        "ambito": "PBS — listado de tecnologías financiadas con UPC",
        "vigente": True,
        "notas": "Reemplazó parcialmente la Res. 5267/2017. Incluye tecnologías de alto costo (Factor VIII recombinante, Emicizumab para profilaxis en hemofilia con inhibidores) con financiación UPC.",
        "keywords": ["Resolución 2292", "PBS", "UPC", "hemofilia", "Emicizumab"],
    },
    "RESOLUCION 2335 DE 2023": {
        "nombre": "Resolución 2335 de 2023 (MinSalud)",
        "titulo": "Reglamentación atención integral cáncer infantil — Ley 1388/2010",
        "ambito": "Pediatría oncológica — atención integral con red de complejidad",
        "vigente": True,
        "notas": "Define el alcance de la atención integral del cáncer infantil incluyendo terapias avanzadas (trasplante MO, CAR-T cells) cuando las líneas previas han fallado. La EPS no puede excluir terapias génicas argumentando 'fuera de PBS' si son la única alternativa terapéutica.",
        "keywords": [
            "Resolución 2335",
            "cáncer infantil",
            "Ley 1388",
            "atención integral",
            "CAR-T",
        ],
    },
    "RESOLUCION 2358 DE 1998": {
        "nombre": "Resolución 2358 de 1998 (MinSalud)",
        "titulo": "Lineamientos de atención en crisis psiquiátrica e internación involuntaria",
        "ambito": "Salud mental — crisis psiquiátrica, contención mecánica",
        "vigente": True,
        "notas": "Establece protocolo de intervención en crisis psiquiátricas vitales: la contención mecánica intermitente está permitida como ÚLTIMO RECURSO en pacientes con riesgo inminente para sí mismos. Salvar la vida prima sobre la restricción temporal de movilidad.",
        "keywords": [
            "Resolución 2358",
            "crisis psiquiátrica",
            "contención mecánica",
            "salud mental",
        ],
    },
    "RESOLUCION 4886 DE 2018": {
        "nombre": "Resolución 4886 de 2018 (MinSalud)",
        "titulo": "Política Nacional de Salud Mental — internación involuntaria y junta médica",
        "ambito": "Salud mental — internación involuntaria, criterios de prolongación",
        "vigente": True,
        "articulos": {
            "art_25": {
                "titulo": "Junta médica para internación involuntaria prolongada",
                "texto": "La internación involuntaria que supere 14 días requiere pronunciamiento documentado de junta médica interdisciplinaria cada 7 días con criterios clínicos de mantenimiento (riesgo suicida activo, agitación severa, respuesta parcial al tratamiento).",
                "aplicacion": "Defensa de internación prolongada con junta médica documentada",
                "keywords": [
                    "internación involuntaria",
                    "junta médica",
                    "prolongación",
                    "salud mental",
                ],
            },
        },
        "keywords": ["Resolución 4886", "salud mental", "internación involuntaria", "junta médica"],
    },
    # ── Ronda 16 (26-jun-2026 — Bug P v3): normas pre-existentes que la EPS
    #     SURA/NUEVA EPS/COMPENSAR invocaron y que el verifier marcaba como
    #     "NORMA_INEXISTENTE". Las agregamos para que el quality gate las
    #     reconozca como reales y el dictamen pueda usarlas en su defensa.
    "RESOLUCION 13437 DE 1991": {
        "nombre": "Resolución 13437 de 01-11-1991 (MinSalud)",
        "titulo": "Decálogo de Derechos del Paciente — primera carta nacional",
        "ambito": "Derechos del usuario en la atención en salud (preconstitucional, ratificada por Ley Estatutaria 1751/2015)",
        "vigente": True,
        "ratio": "Establece el decálogo de derechos del paciente: trato digno, respeto a creencias, información comprensible, segunda opinión, confidencialidad, autonomía, atención completa, identificación del personal, libre elección, y formulación de quejas. Norma fundacional citada como soporte en glosas que invocan calidad de la atención.",
        "aplica_a": "Glosas que cuestionan calidad o trato — defensa por aplicación del decálogo institucional",
        "keywords": [
            "Resolución 13437/1991",
            "decálogo paciente",
            "derechos del usuario",
            "trato digno",
            "confidencialidad",
        ],
    },
    "RESOLUCION 2338 DE 2013": {
        "nombre": "Resolución 2338 de 11-07-2013 (MinSalud)",
        "titulo": "Lineamientos para la gestión de tecnologías biomédicas e insumos",
        "ambito": "Adquisición, mantenimiento y gestión de equipo biomédico — IPS prestadoras",
        "vigente": True,
        "ratio": "Define los lineamientos para la gestión integral de tecnología biomédica (selección, adquisición, instalación, mantenimiento, baja). Norma técnica de obligatorio cumplimiento para IPS y soporte en glosas de calidad por uso de dispositivos: el HUS acredita procesos institucionales conforme a esta resolución, no admite cuestionamientos al equipo biomédico aprobado por gerencia técnica.",
        "aplica_a": "Glosas que cuestionan dispositivos biomédicos, mantenimiento de equipos o calibración",
        "keywords": [
            "Resolución 2338/2013",
            "tecnología biomédica",
            "gestión de insumos",
            "mantenimiento equipos",
            "calidad",
        ],
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
    "MANUAL SIIFA 2026": {
        "nombre": "Manual SIIFA 2026",
        "titulo": "Sistema Integrado de Información Financiera y Administrativa — Gestión de Cuentas Médicas",
        "ambito": "Manual operativo plazos de cuentas médicas y glosas",
        "vigente": True,
        "notas": "Consolida y operacionaliza los plazos del Art. 57 Ley 1438/2011 y la Res. 2284/2023 (Manual Único). Plazos vigentes: 20 días EPS formular | 15 días IPS responder | 7 días subsanar | 10 días EPS decidir | 5 días pago post-levantamiento.",
        "articulos": {
            "plazos": {
                "titulo": "Cronograma completo del trámite de glosas",
                "texto": "1. FORMULACIÓN: La Entidad Responsable del Pago (EPS/ERP) dispone de 20 días hábiles desde la radicación de la factura para formular glosas. Vencido este plazo, se configura aceptación tácita. 2. RESPUESTA: La IPS dispone de 15 días hábiles desde la recepción de la glosa para presentar respuesta técnica. 3. SUBSANACIÓN: Si la glosa es subsanable, la IPS cuenta con 7 días hábiles adicionales para corregir y reenviar. 4. DECISIÓN FINAL: La EPS dispone de 10 días hábiles tras la respuesta de la IPS para levantar (parcial o total) o ratificar la glosa. 5. PAGO: Una vez levantada o aceptada la glosa, el pago debe efectuarse dentro de los 5 días hábiles siguientes. Nota: Una vez formulada la glosa inicial, no se pueden presentar nuevas glosas sobre la misma factura, salvo hechos nuevos detectados en la respuesta.",
                "aplicacion": "Cronograma operativo completo vigente 2026",
                "keywords": [
                    "plazos",
                    "cronograma",
                    "20 días",
                    "15 días",
                    "7 días",
                    "10 días",
                    "5 días",
                    "formulación",
                    "respuesta",
                    "subsanación",
                    "decisión",
                    "pago",
                ],
            },
        },
        "keywords": [
            "SIIFA",
            "manual SIIFA",
            "cuentas médicas",
            "plazos",
            "cronograma glosas",
            "2026",
        ],
    },
    # ─── R52 B: ampliación catálogo ────────────────────────────────────────
    "CIRCULAR 010 DE 2017": {
        "nombre": "Circular 010 de 2017 (Supersalud)",
        "titulo": "Pago oportuno de servicios — flujo de recursos a IPS",
        "ambito": "Vigilancia y control — sanción por mora en pago",
        "vigente": True,
        "keywords": ["Supersalud", "pago oportuno", "flujo recursos", "mora EPS"],
    },
    "CIRCULAR 015 DE 2014": {
        "nombre": "Circular Externa 015 de 2014 (Supersalud)",
        "titulo": "Reportes obligatorios de IPS y EPS al Sistema de Información de la Supersalud",
        "ambito": "Vigilancia — reportes financieros y de calidad",
        "vigente": True,
        "keywords": ["Supersalud", "reportes", "información financiera", "vigilancia"],
    },
    "CIRCULAR 005 DE 2022": {
        "nombre": "Circular Externa 005 de 2022 (Supersalud)",
        "titulo": "Giro directo a IPS y vigilancia del flujo de recursos",
        "ambito": "Giro directo — control de pagos a prestadores",
        "vigente": True,
        "keywords": ["giro directo", "Supersalud", "flujo recursos", "ADRES IPS"],
    },
    "CIRCULAR 011 DE 2021": {
        "nombre": "Circular Externa 011 de 2021 (Supersalud)",
        "titulo": "Reportes de cartera y cuentas por cobrar de IPS",
        "ambito": "Vigilancia — informe trimestral de cartera",
        "vigente": True,
        "keywords": ["cartera IPS", "cuentas por cobrar", "Supersalud", "reporte trimestral"],
    },
    "CIRCULAR 008 DE 2018": {
        "nombre": "Circular Externa 008 de 2018 (Supersalud)",
        "titulo": "Procedimiento para reportar a la SNS conductas que afectan flujo de recursos",
        "ambito": "Anti-evasión y reporte de conductas EPS contrarias al flujo de recursos",
        "vigente": True,
        "keywords": ["denuncia EPS", "Supersalud", "flujo recursos", "conductas indebidas"],
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
    # ─── R52 B: ampliación ────────────────────────────────────────────────
    "CODIGO CIVIL - ARTICULO 1494": {
        "nombre": "Código Civil — Artículo 1494",
        "titulo": "Fuentes de las obligaciones",
        "texto": "Las obligaciones nacen, ya del concurso real de las voluntades de dos o más personas, como en los contratos o convenciones; ya de un hecho voluntario de la persona que se obliga, como en la aceptación de una herencia o legado y en todos los cuasicontratos; ya a consecuencia de un hecho que ha inferido injuria o daño a otra persona, como en los delitos; ya por disposición de la ley, como entre los padres y los hijos de familia.",
        "aplicacion": "Origen de la obligación de pago contractual EPS-IPS",
        "keywords": ["fuentes obligaciones", "1494", "C.Civil", "contrato"],
    },
    "CODIGO CIVIL - ARTICULO 1626": {
        "nombre": "Código Civil — Artículo 1626",
        "titulo": "Pago efectivo y modos de extinción de obligaciones",
        "texto": "El pago efectivo es la prestación de lo que se debe. Por consiguiente, el deudor de una cosa no puede obligar al acreedor a que reciba otra, aun cuando sea de igual o mayor valor.",
        "aplicacion": "Base del concepto de pago integral por la EPS",
        "keywords": ["pago efectivo", "1626", "modos extinción", "C.Civil"],
    },
    "CODIGO DE COMERCIO - ARTICULO 884": {
        "nombre": "Código de Comercio — Artículo 884",
        "titulo": "Intereses moratorios mercantiles",
        "texto": "Cuando en los negocios mercantiles haya de pagarse réditos de un capital, sin que se especifique por convenio el interés, este será el bancario corriente; si las partes no han estipulado el interés moratorio, será equivalente a una y media veces del bancario corriente.",
        "aplicacion": "Reclamo de intereses moratorios sobre saldos vencidos a favor de la IPS",
        "keywords": ["intereses moratorios", "884", "C.Comercio", "mora EPS"],
    },
    "CODIGO PENAL - ARTICULO 397": {
        "nombre": "Código Penal — Artículo 397 (Peculado)",
        "titulo": "Peculado por apropiación",
        "texto": "El servidor público que se apropie en provecho suyo o de un tercero de bienes del Estado o de empresas o instituciones en que éste tenga parte o de bienes o fondos parafiscales, o de bienes de particulares cuya administración, tenencia o custodia se le haya confiado por razón o con ocasión de sus funciones, incurrirá en prisión.",
        "aplicacion": "Marco penal aplicable a fraude documental en glosas y recobros",
        "keywords": ["peculado", "397", "C.Penal", "servidor público"],
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
        "ratio_literal": "Las EPS no pueden negar la prestación de servicios de salud cuando la condición clínica del paciente los requiera y la historia clínica soporte la indicación médica.",
        "extracto_judicial": (
            "«El acceso efectivo a los servicios de salud es un componente esencial del derecho "
            "fundamental, y su negación injustificada constituye una violación directa de la "
            "dignidad humana y del derecho a la vida en condiciones dignas. Las entidades "
            "promotoras de salud tienen la obligación de garantizar la prestación de los "
            "servicios requeridos por sus afiliados, sin que puedan oponerse obstáculos "
            "administrativos o económicos que impidan el acceso oportuno.»"
        ),
        "aplica_a": "EPS del régimen contributivo/subsidiado (NO aplica a Sanidad Militar, PPL, FOMAG, Policía)",
        "keywords": ["T-760", "derecho salud", "EPS", "negación servicios", "riesgo vital"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-1025 DE 2002": {
        "nombre": "Sentencia T-1025 de 2002",
        "corte": "Corte Constitucional",
        "titulo": "Consentimiento informado en cirugia de asignacion de sexo (menores intersexuales)",
        "ratio": (
            "Consentimiento informado del menor para intervenciones altamente invasivas. La Corte "
            "precisa que estas cirugias NO califican como urgencia. NO trata sobre atencion de "
            "urgencias sin autorizacion previa. "
        ),
        "aplica_a": "No aplicable a glosas de urgencias ni de autorizacion previa",
        "magistrado_ponente": "Rodrigo Escobar Gil",
        "keywords": ["T-1025", "consentimiento informado", "menores intersexuales"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-478 DE 1995": {
        "nombre": "Sentencia T-478 de 1995",
        "corte": "Corte Constitucional",
        "titulo": "Seguridad social y tratamiento asilar de personas con discapacidad psiquica",
        "ratio": (
            "Obligaciones del Estado y de las instituciones de salud frente al acceso a servicios "
            "de personas con enfermedad mental cronica. NO trata sobre autonomia del medico "
            "tratante. "
        ),
        "aplica_a": "No aplicable a glosas de pertinencia ni de autonomia medica",
        "magistrado_ponente": "Alejandro Martinez Caballero",
        "keywords": ["T-478", "discapacidad psiquica", "tratamiento asilar"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-121 DE 2015": {
        "nombre": "Sentencia T-121 de 2015",
        "corte": "Corte Constitucional",
        "titulo": "Autorizacion de procedimientos quirurgicos ordenados al menor (epispadias)",
        "ratio": (
            "La EPS debe autorizar los procedimientos ordenados por el medico tratante cuando el "
            "servicio se requiere con necesidad. NO trata sobre las Guias de Practica Clinica ni "
            "sobre su caracter recomendativo. "
        ),
        "aplica_a": "Autorizacion de servicios ordenados por el tratante",
        "magistrado_ponente": "Luis Guillermo Guerrero Perez",
        "keywords": ["T-121", "autorizacion", "medico tratante", "menor"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-171 DE 2018": {
        "nombre": "Sentencia T-171 de 2018",
        "corte": "Corte Constitucional",
        "ratio_literal": "La auditoría administrativa carece de potestad para negar procedimientos médicamente indicados cuando no aporta contradicción científica con sustento clínico equivalente al del médico tratante.",
        "verificada": "24-08-2026 relatoria Corte Constitucional",
        "titulo": "Atencion integral a adulta mayor tras fractura de cadera",
        "ratio": (
            "La EPS no presto atencion integral a una adulta mayor de 88 anos. La Corte reconoce "
            "la primacia del criterio del medico tratante, pero el eje del fallo es garantizar un "
            "diagnostico efectivo integral, no fijar una regla sobre auditoria de cuentas."
        ),
        "aplica_a": "Atencion integral y valoracion medica",
        "magistrado_ponente": "Cristina Pardo Schlesinger",
        "keywords": ["T-171", "atencion integral", "medico tratante"],
    },
    "SENTENCIA T-134 DE 2022": {
        "nombre": "Sentencia T-134 de 2022",
        "corte": "Corte Constitucional",
        "titulo": "Oportunidad en prestación de servicios de salud",
        "ratio": "Las demoras administrativas en autorizaciones o pagos violan el derecho fundamental a la salud. Las EPS no pueden trasladar su ineficiencia a pacientes o prestadores.",
        "aplica_a": "Glosas administrativas que trasladan cargas indebidas a la IPS",
        "keywords": ["T-134", "oportunidad", "demoras administrativas"],
        "verificada": False,
    },
    "SENTENCIA T-050 DE 2017": {
        "nombre": "Sentencia T-050 de 2017",
        "corte": "Corte Constitucional",
        "titulo": "Atención integral y continuidad del tratamiento",
        "ratio": "Los pacientes tienen derecho a recibir atención continua sin interrupciones por cambios de EPS o trámites administrativos. El prestador que garantizó continuidad debe ser remunerado íntegramente.",
        "aplica_a": "Continuidad de tratamiento, oncología, crónicos",
        "keywords": ["T-050", "continuidad", "atención integral"],
        "verificada": False,
    },
    # ─── Ronda 50 Paso 11: ampliación jurisprudencia ─────────────────────
    "SENTENCIA T-235 DE 1998": {
        "nombre": "Sentencia T-235 de 1998",
        "corte": "Corte Constitucional",
        "titulo": "Participacion politica — exclusion de listas electorales universitarias",
        "ratio": (
            "Derechos de participacion en elecciones internas de una universidad publica. NO trata "
            "de salud, ni de historia clinica, ni de prestacion de servicios. "
        ),
        "aplica_a": "Ninguna glosa de salud — materia ajena",
        "magistrado_ponente": "Fabio Moron Diaz",
        "keywords": ["T-235", "participacion politica"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA SU-480 DE 1997": {
        "nombre": "Sentencia SU-480 de 1997",
        "corte": "Corte Constitucional (Sala Plena)",
        "titulo": "Medicamentos no incluidos en el POS (antirretrovirales, VIH/sida)",
        "ratio": (
            "La EPS debe entregar el medicamento prescrito por el medico tratante aunque no figure "
            "en el listado, cuando esta de por medio la vida del paciente, y puede repetir contra "
            "el Estado. NO trata sobre atencion inicial de urgencias. "
        ),
        "aplica_a": "Cobertura de medicamentos fuera del listado",
        "magistrado_ponente": "Alejandro Martinez Caballero",
        "keywords": ["SU-480", "medicamentos no POS", "antirretrovirales"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-313 DE 2007": {
        "nombre": "Sentencia T-313 de 2007",
        "corte": "Corte Constitucional",
        "titulo": "Autorización tácita por silencio administrativo",
        "ratio": "Si la EPS no responde la solicitud de autorización en el plazo legal, opera el silencio positivo: el servicio queda autorizado y la EPS está obligada al pago íntegro sin glosa por autorización.",
        "aplica_a": "Glosas AU0101, AU0201 cuando hubo solicitud sin respuesta dentro del plazo",
        "keywords": ["T-313", "silencio positivo", "autorización tácita", "plazo respuesta"],
        "verificada": False,
    },
    "SENTENCIA T-642 DE 2008": {
        "nombre": "Sentencia T-642 de 2008",
        "corte": "Corte Constitucional",
        "titulo": "Transporte, alojamiento y manutencion para el tratamiento de un menor",
        "ratio": (
            "La EPS debe sufragar los gastos de desplazamiento y hospedaje del paciente para "
            "acceder al tratamiento. NO trata sobre flujo de recursos ni sobre el pago oportuno de "
            "la EPS a la IPS. "
        ),
        "aplica_a": "Gastos de acceso al tratamiento del paciente",
        "magistrado_ponente": "Nilson Pinilla Pinilla",
        "keywords": ["T-642", "transporte", "alojamiento"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-053 DE 2009": {
        "nombre": "Sentencia T-053 de 2009",
        "corte": "Corte Constitucional",
        "titulo": "Tratamiento integral a persona con paralisis cerebral y epilepsia",
        "ratio": (
            "El tratamiento integral no se agota en el suministro de medicamentos: comprende todos "
            "los servicios e insumos relacionados con la patologia. NO trata sobre glosas de la EPS "
            "a la IPS. "
        ),
        "aplica_a": "Atencion integral al paciente",
        "magistrado_ponente": "Humberto Antonio Sierra Porto",
        "keywords": ["T-053", "tratamiento integral", "paralisis cerebral"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "CONSEJO_ESTADO_2018_00154": {
        "nombre": "Consejo de Estado, Sec. Tercera, Rad. 2018-00154",
        "corte": "Consejo de Estado — Sala Contencioso Administrativa, Sección Tercera",
        "titulo": "Silencio positivo en respuesta a glosa (Art. 57 Ley 1438/2011)",
        "ratio": "Si la EPS no responde la respuesta a glosa del prestador dentro de los 10 días hábiles legales, opera el LEVANTAMIENTO TÁCITO de la objeción. La EPS pierde el derecho a discutir y debe pagar.",
        "ratio_literal": "El silencio de la entidad responsable del pago frente a la respuesta motivada del prestador configura un levantamiento tácito de la glosa, no susceptible de revocatoria posterior.",
        "aplica_a": "Defensa cuando la EPS deja vencer el plazo de 10 días tras la respuesta del HUS",
        "keywords": [
            "Consejo de Estado",
            "silencio positivo",
            "Art. 57",
            "levantamiento tácito",
            "Ley 1438",
        ],
    },
    # ─── R52 B: ampliación catálogo de jurisprudencia ──────────────────────
    "SENTENCIA T-024 DE 2009": {
        "nombre": "Sentencia T-024 de 2009",
        "ambito": "Glosas y mora en pago a IPS — derecho fundamental afectado",
        "vigente": True,
        "titulo": "Custodia de menor y restitucion por via de tutela",
        "ratio": (
            "Derecho de familia: custodia de una nina e interes superior del menor, en tutela "
            "contra el ICBF. NO trata del pago de servicios de salud ni de obligaciones de las "
            "EPS."
        ),
        "aplica_a": "Ninguna glosa de cuentas medicas — materia ajena",
        "magistrado_ponente": "Rodrigo Escobar Gil",
        "keywords": ["T-024", "custodia", "interes superior del menor"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-744 DE 2009": {
        "nombre": "Sentencia T-744 de 2009",
        "ambito": "Pertinencia médica vs. negativa de la EPS",
        "vigente": True,
        "titulo": "Salud de una persona privada de la libertad con enfermedad mental",
        "ratio": (
            "Acceso a los servicios de salud de un interno con enfermedad mental. Toca el acceso "
            "y la autorizacion, pero NO fija una regla general de autonomia profesional frente a "
            "la auditoria de la EPS: no sirve como fundamento de pertinencia clinica."
        ),
        "aplica_a": "Acceso a servicios de personas privadas de la libertad",
        "magistrado_ponente": "Gabriel Eduardo Mendoza Martelo",
        "keywords": ["T-744", "privados de la libertad", "salud mental"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-940 DE 2009": {
        "nombre": "Sentencia T-940 de 2009",
        "ambito": "Glosa parcial — proporcionalidad",
        "vigente": True,
        "titulo": "Hemodialisis sin contrato vigente con la IPS (insuficiencia renal terminal)",
        "ratio": (
            "La EPS-S debe autorizar la hemodialisis en la IPS que la presta aunque no tenga "
            "contrato vigente con ella, y garantizar el tratamiento integral. Es una orden a "
            "favor del PACIENTE. NO trata del pago de facturas a las IPS ni de fragmentacion de "
            "pagos."
        ),
        "aplica_a": "Acceso del paciente a la IPS aunque no haya contrato",
        "magistrado_ponente": "Luis Ernesto Vargas Silva",
        "keywords": ["T-940", "hemodialisis", "sin contrato", "tratamiento integral"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-117 DE 2013": {
        "nombre": "Sentencia T-117 de 2013",
        "ambito": "Cobertura — interrupción de tratamiento por glosa",
        "vigente": True,
        "titulo": "Tutela contra providencia judicial por defecto factico (materia penal)",
        "ratio": (
            "Exclusion de una entrevista forense del juicio oral. Es derecho procesal penal y "
            "probatorio. NO trata de continuidad del tratamiento ni de atencion integral en "
            "salud."
        ),
        "aplica_a": "Ninguna glosa de cuentas medicas — materia ajena",
        "magistrado_ponente": "Alexei Julio Estrada",
        "keywords": ["T-117", "defecto factico", "prueba penal"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-307 DE 2017": {
        "nombre": "Sentencia T-307 de 2017",
        "ambito": "MIPRES y recobros — barreras administrativas",
        "vigente": True,
        "titulo": "Pension de sobrevivientes de la companera permanente (Policia Nacional)",
        "ratio": (
            "Regimen pensional especial. NO trata de recobros NO PBS ni de flujo de recursos del "
            "sistema de salud."
        ),
        "aplica_a": "Ninguna glosa de cuentas medicas — materia ajena",
        "magistrado_ponente": "Gloria Stella Ortiz Delgado",
        "keywords": ["T-307", "pension de sobrevivientes"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-126 DE 2018": {
        "nombre": "Sentencia T-126 de 2018",
        "ambito": "Soportes de glosa — valor probatorio de la HC",
        "vigente": True,
        "titulo": "Tutela contra providencia judicial — violencia sexual en el conflicto armado",
        "ratio": (
            "Acceso a la justicia de una victima de violencia sexual. NO fija ninguna regla sobre "
            "la historia clinica como prueba, ni sobre facturacion o auditoria de cuentas "
            "medicas."
        ),
        "aplica_a": "Ninguna glosa de cuentas medicas — materia ajena",
        "magistrado_ponente": "Cristina Pardo Schlesinger",
        "keywords": ["T-126", "violencia sexual", "acceso a la justicia"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA C-313 DE 2014": {
        "nombre": "Sentencia C-313 de 2014",
        "ambito": "Salud como derecho fundamental autónomo",
        "vigente": True,
        "titulo": "Control previo de constitucionalidad de la Ley Estatutaria de Salud",
        "ratio": (
            "Revision PREVIA y automatica del proyecto que luego fue la Ley 1751 de 2015. El "
            "asunto de fondo si es el derecho fundamental a la salud; el enunciado anterior decia "
            "'Ley Estatutaria 1751 de 2015', que en 2014 aun no existia con ese numero."
        ),
        "aplica_a": "Marco general del derecho fundamental a la salud",
        "magistrado_ponente": "Gabriel Eduardo Mendoza Martelo",
        "keywords": ["C-313", "ley estatutaria", "derecho fundamental a la salud"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    # Ronda 15 (Bug P v2): sentencias específicas que aparecen en producción
    # y el verifier marcaba como inexistentes.
    "SENTENCIA T-705 DE 2017": {
        "nombre": "Sentencia T-705 de 2017",
        "ambito": "Migrantes venezolanos sin afiliación al SGSSS — atención inicial obligatoria",
        "vigente": True,
        "titulo": "Atencion en salud a un menor migrante venezolano",
        "ratio": (
            "Tutela de un menor venezolano contra un instituto departamental de salud. Trata la "
            "atencion del migrante, pero el enunciado anterior la presentaba como regla de "
            "urgencias: revisar el alcance antes de apoyarse en ella."
        ),
        "aplica_a": "Atencion a poblacion migrante",
        "magistrado_ponente": "Jose Fernando Reyes Cuartas",
        "keywords": ["T-705", "migrante", "menor"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-401 DE 1994": {
        "nombre": "Sentencia T-401 de 1994",
        "ambito": "Salud mental — uso proporcional de contención mecánica",
        "vigente": True,
        "titulo": "Consentimiento idoneo del paciente frente al cambio de tratamiento",
        "ratio": (
            "El medico no puede cambiar unilateralmente el tratamiento sin el consentimiento "
            "idoneo del paciente (caso de dialisis peritoneal). NO trata de contencion mecanica "
            "ni de pacientes psiquiatricos."
        ),
        "aplica_a": "Autonomia del paciente y consentimiento informado",
        "magistrado_ponente": "Eduardo Cifuentes Munoz",
        "keywords": ["T-401", "consentimiento informado", "autonomia del paciente"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-1198 DE 2003": {
        "nombre": "Sentencia T-1198 de 2003",
        "ambito": "Glosas dilatorias y bloqueo de cartera",
        "vigente": True,
        "titulo": "Continuidad del servicio e improcedencia de una nueva tutela",
        "ratio": (
            "Continuidad en la prestacion del servicio de salud, y por que no procede una segunda "
            "tutela cuando ya hay fallo que ordeno el tratamiento. NO trata del pago a "
            "prestadores ni de solidaridad financiera del sistema."
        ),
        "aplica_a": "Continuidad del tratamiento ya ordenado",
        "magistrado_ponente": "Eduardo Montealegre Lynett",
        "keywords": ["T-1198", "continuidad", "cosa juzgada"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-076 DE 2008": {
        "nombre": "Sentencia T-076 de 2008",
        "ambito": "Cobertura — afiliación posterior al nacimiento",
        "vigente": True,
        "titulo": "Derecho al diagnostico (complicaciones de un procedimiento estetico)",
        "ratio": (
            "Derecho a la salud, a la seguridad social y AL DIAGNOSTICO de una afiliada con "
            "complicaciones tras un procedimiento estetico voluntario. NO trata de atencion a "
            "recien nacidos ni de cobertura inmediata del neonato."
        ),
        "aplica_a": "Derecho al diagnostico",
        "magistrado_ponente": "Rodrigo Escobar Gil",
        "keywords": ["T-076", "derecho al diagnostico"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA SU-1023 DE 2001": {
        "nombre": "Sentencia SU-1023 de 2001",
        "ambito": "Estructura del SGSSS — UPC y compensación",
        "vigente": True,
        "titulo": "Mesadas pensionales de una empresa en liquidacion obligatoria",
        "ratio": (
            "Cinco tutelas acumuladas de pensionados de una empresa en liquidacion que dejo de "
            "pagar las mesadas. Es materia pensional. NO trata de solidaridad del sistema de "
            "salud ni de financiacion cruzada entre EPS e IPS."
        ),
        "aplica_a": "Ninguna glosa de cuentas medicas — materia ajena",
        "magistrado_ponente": "Jaime Cordoba Trivino",
        "keywords": ["SU-1023", "mesadas pensionales", "liquidacion"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    # ── Ronda 16 (26-jun-2026 — Bug P v3): jurisprudencia que la EPS
    #     SURA/NUEVA EPS/COMPENSAR invocaron y que el verifier marcaba
    #     como inexistente. Las agregamos para que el quality gate las
    #     reconozca y el dictamen pueda responder por nombre.
    "SENTENCIA T-385 DE 2023": {
        "nombre": "Sentencia T-385 de 2023 (Corte Constitucional)",
        "ambito": "Defensa de prestadores frente a EPS — obligaciones bilaterales y continuidad",
        "vigente": True,
        "titulo": "Nacionalidad y personalidad juridica de una nina en riesgo de apatridia",
        "ratio": (
            "Derechos a la nacionalidad y a la personalidad juridica de una nina nacida en "
            "Venezuela, hija de extranjeros residentes en Colombia. NO trata del derecho a la "
            "salud del paciente complejo ni de la relacion EPS-IPS."
        ),
        "aplica_a": "Ninguna glosa de cuentas medicas — materia ajena",
        "magistrado_ponente": "Jorge Enrique Ibanez Najar",
        "keywords": ["T-385", "nacionalidad", "apatridia"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "SENTENCIA T-970 DE 2014": {
        "nombre": "Sentencia T-970 de 2014 (Corte Constitucional)",
        "ambito": "Cuidados paliativos, sedación terminal y voluntad anticipada",
        "vigente": True,
        "titulo": "Derecho a morir dignamente",
        "ratio": (
            "Derecho fundamental a morir dignamente de una paciente con cancer terminal. "
            "Verificada: el enunciado guardado era correcto."
        ),
        "aplica_a": "Muerte digna y autonomia del paciente terminal",
        "magistrado_ponente": "Luis Ernesto Vargas Silva",
        "keywords": ["T-970", "muerte digna", "paciente terminal"],
        "verificada": "24-08-2026 relatoria Corte Constitucional",
    },
    "AUTO 037 DE 2024": {
        # Corregido el 24-08-2026. El sistema lo describía como «seguimiento a
        # la Sentencia T-553/2024» sobre terapia CAR-T. El Auto existe —se leyó
        # su texto oficial completo— pero no dice una palabra de CAR-T (cero
        # menciones), y la sentencia a la que decía darle seguimiento no
        # existe. Lo que trata de verdad es mucho más útil para cartera.
        "nombre": "Auto 037 de 2024 (Corte Constitucional, Sala Plena)",
        "titulo": (
            "Jurisdicción competente para cobrar ejecutivamente facturas de servicios de salud"
        ),
        "ambito": "Cobro judicial de facturas de la IPS a la entidad pagadora",
        "vigente": True,
        "ratio": (
            "Conflicto de jurisdicciones (expediente CJU-4122): un hospital demandó a "
            "una caja de compensación para que se declarara la deuda por la factura de "
            "una atención inicial de urgencias. La Sala Plena resolvió que es la "
            "jurisdicción ORDINARIA LABORAL la competente para los procesos ejecutivos "
            "en que se pretende el pago de obligaciones derivadas de facturas por "
            "prestación de servicios de salud."
        ),
        "aplica_a": (
            "Cobro judicial de cartera a la entidad pagadora: sirve para saber ante qué "
            "juez se demanda, no como argumento dentro de la respuesta a una glosa."
        ),
        "magistrado_ponente": "Antonio José Lizarazo Ocampo (sustanciador)",
        "verificada": "24-08-2026 relatoria Corte Constitucional",
        "keywords": [
            "Auto 037/2024",
            "conflicto de jurisdicciones",
            "proceso ejecutivo",
            "cobro de facturas",
            "jurisdicción laboral",
        ],
    },
    "AUTO 116 DE 2024": {
        # Corregido el 24-08-2026. El sistema lo describía como un auto de
        # «sostenibilidad fiscal del SGSSS y giros directos de ADRES a IPS
        # públicas», y lo ofrecía como «soporte fuerte» para glosas de EPS
        # intervenidas. Se leyó su texto oficial: CERO menciones de ADRES, cero
        # de giro directo, cero de sostenibilidad. Nada de eso está ahí.
        "nombre": "Auto 116 de 2024 (Corte Constitucional, Sala Plena)",
        "titulo": (
            "Jurisdicción competente cuando se demanda un acto administrativo de "
            "una entidad pública"
        ),
        "ambito": "Conflicto de jurisdicciones — nulidad y restablecimiento del derecho",
        "vigente": True,
        "ratio": (
            "Conflicto de jurisdicciones (expediente CJU-4747) entre un juzgado "
            "administrativo y uno laboral. Una EPS demandó las resoluciones con que "
            "Colpensiones le ordenó reintegrar subsidios de incapacidades posteriores "
            "al día 540. La Sala Plena resolvió que corresponde a la jurisdicción "
            "CONTENCIOSO ADMINISTRATIVA conocer de actos sujetos al derecho "
            "administrativo cuando está involucrada una entidad pública."
        ),
        "aplica_a": (
            "Define ante qué juez se demanda un acto administrativo. No es argumento "
            "para responder una glosa."
        ),
        "magistrado_ponente": "Natalia Ángel Cabo",
        "verificada": "24-08-2026 relatoria Corte Constitucional",
        "keywords": [
            "Auto 116/2024",
            "conflicto de jurisdicciones",
            "nulidad y restablecimiento",
            "incapacidades posteriores al día 540",
        ],
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
    # Ronda 14 (25-jun-2026, Bug P): el verifier marcaba como
    # "NORMA_INEXISTENTE" las siguientes normas que SÍ existen en el
    # ordenamiento jurídico colombiano. Las agregamos al corpus para que
    # el quality gate deje de generar falsos positivos en dictámenes
    # legítimos.
    "ACUERDO 256 DE 2001": {
        "nombre": "Acuerdo 256 de 2001 (Consejo Nacional de Seguridad Social en Salud — CNSSS)",
        "titulo": "Mecanismo de actualización de tarifas SOAT (anualidad fiscal)",
        "ambito": "Tarifas SOAT — cambio de manual al inicio de cada vigencia",
        "vigente": True,
        "notas": "Regula el ajuste anual del Manual Tarifario SOAT y la aplicación temporal de los nuevos valores al 1 de enero de cada año.",
        "keywords": ["Acuerdo 256", "SOAT", "anualidad fiscal", "actualización tarifas"],
    },
    "ACUERDO 029 DE 2011": {
        "nombre": "Acuerdo 029 de 2011 (CRES)",
        "titulo": "Plan Obligatorio de Salud — actualización integral",
        "ambito": "Cobertura PBS (derogado parcialmente por Resolución 5267/2017)",
        "vigente": False,
        "reemplazado_por": "Resolución 5267 de 2017 (luego Resolución 2292 de 2021)",
        "notas": "Norma de transición — el contenido fue subrogado pero algunas EPS aún la invocan en glosas. Cuando la EPS la cite, contrarrestar con la norma vigente del PBS.",
        "keywords": ["Acuerdo 029", "POS", "PBS", "CRES", "derogado"],
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
                        resultados_directos.append(
                            {
                                "norma": norma["nombre"],
                                "tipo": norma.get("ambito", ""),
                                "titulo": norma.get("titulo", ""),
                                "texto": norma.get("texto", ""),
                                "match_directo": True,
                            }
                        )
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
        texto_norma = _normalizar(
            " ".join(
                [
                    norma.get("titulo", ""),
                    norma.get("ambito", ""),
                    norma.get("texto", ""),
                ]
            )
        )
        for t in terminos:
            if t in texto_norma:
                score += 1
        # artículos internos
        for art_num, art in norma.get("articulos", {}).items():
            art_text = _normalizar(
                " ".join(
                    [
                        art.get("titulo", ""),
                        art.get("texto", ""),
                        art.get("aplicacion", ""),
                        " ".join(art.get("keywords", [])),
                    ]
                )
            )
            art_score = 0
            for t in terminos:
                if t in art_text:
                    art_score += 2
            if art_score > 0:
                scored.append(
                    (
                        art_score + score,
                        {
                            "norma": norma["nombre"],
                            "articulo": art_num,
                            "titulo": art["titulo"],
                            "texto": art["texto"],
                            "aplicacion": art.get("aplicacion", ""),
                        },
                    )
                )
        if score > 0:
            scored.append(
                (
                    score,
                    {
                        "norma": norma["nombre"],
                        "tipo": norma.get("ambito", ""),
                        "titulo": norma.get("titulo", ""),
                        "texto": norma.get("texto", ""),
                    },
                )
            )

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
        "TA": [
            "LEY 100 DE 1993",
            "CODIGO CIVIL - ARTICULO 1602",
            "CODIGO DE COMERCIO - ARTICULO 871",
            "CIRCULAR 047 DE 2025",
            "RESOLUCION 054 DE 2026",
            "RESOLUCION 124 DE 2026",
        ],
        "SO": [
            "RESOLUCION 1995 DE 1999",
            "RESOLUCION 866 DE 2021",
            "CIRCULAR 030 DE 2013",
            "RESOLUCION 2284 DE 2023",
        ],
        # T-1025/2002 se retiro el 24-08-2026: verificada contra la relatoria de la
        # Corte, trata de consentimiento informado en cirugia de asignacion de sexo,
        # no de urgencias. El anclaje correcto de urgencias es el Art. 168 de la
        # Ley 100 y el Art. 20 del Decreto 4747, que ya estaban aqui.
        "AU": ["LEY 100 DE 1993", "DECRETO 4747 DE 2007"],
        "CO": ["LEY 1751 DE 2015", "RESOLUCION 5269 DE 2017", "SENTENCIA T-760 DE 2008"],
        "CL": [
            "LEY 1751 DE 2015",
            # T-478/1995 se retiro el 24-08-2026: verificada, trata de seguridad
            # social de personas con discapacidad psiquica, no de autonomia medica.
            # El anclaje correcto es el Art. 17 de la Ley 1751, que ya estaba aqui.
            "SENTENCIA T-171 DE 2018",
            "RESOLUCION 1995 DE 1999",
        ],
        "PE": ["LEY 1751 DE 2015", "SENTENCIA T-171 DE 2018", "RESOLUCION 1995 DE 1999"],
        "FA": [
            "LEY 100 DE 1993",
            "RESOLUCION 1995 DE 1999",
            "RESOLUCION 2284 DE 2023",
            "CODIGO DE COMERCIO - ARTICULO 871",
        ],
        "IN": [
            "DECRETO 780 DE 2016",
            "CODIGO DE COMERCIO - ARTICULO 871",
            "RESOLUCION 5269 DE 2017",
        ],
        "ME": ["LEY 1751 DE 2015", "RESOLUCION 5269 DE 2017"],
    }
    return mapping.get(prefijo, ["LEY 100 DE 1993", "RESOLUCION 2284 DE 2023"])
