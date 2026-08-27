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
    # ── Cargadas el 25-08-2026 ──────────────────────────────────────────
    # Los prompts del motor ya le ofrecian estas normas a la IA, pero no
    # estaban en el corpus con que se revisan las citas. Resultado: la IA las
    # citaba (porque se lo pedimos) y el revisor las marcaba en rojo como
    # "norma inexistente" sobre un dictamen que podia estar bien. Verificadas
    # una por una contra fuente oficial antes de cargarlas.
    "LEY 1564 DE 2012": {
        "nombre": "Ley 1564 de 2012 (Congreso de la Republica)",
        "titulo": "Codigo General del Proceso",
        "ambito": "Cobro judicial de la cartera y valor probatorio de la factura",
        "vigente": True,
        "notas": (
            "Sirve para sostener que la factura y el acta de conciliacion prestan merito "
            "ejecutivo (Art. 422). Se usa al preparar el cobro, no como argumento de fondo de la "
            "glosa."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["codigo general del proceso", "merito ejecutivo", "factura", "cobro judicial"],
    },
    "LEY 1618 DE 2013": {
        "nombre": "Ley Estatutaria 1618 de 2013 (Congreso de la Republica)",
        "titulo": "Derechos de las personas con discapacidad",
        "ambito": "Atencion integral y sin barreras al paciente con discapacidad",
        "vigente": True,
        "notas": (
            "Respalda la habilitacion y rehabilitacion integral cuando la EPS glosa servicios de "
            "un paciente con discapacidad alegando que no estan cubiertos."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["discapacidad", "atencion integral", "rehabilitacion", "ley estatutaria"],
    },
    "LEY 2277 DE 2022": {
        "nombre": "Ley 2277 de 2022 (Congreso de Colombia)",
        "titulo": "Reforma tributaria para la igualdad y la justicia social",
        "ambito": "Solo para asuntos tributarios de la factura",
        "vigente": True,
        "notas": (
            "El motor la cita por su articulo 89 para la UVB del manual tarifario SOAT. OJO: es "
            "una reforma TRIBUTARIA; en una glosa solo sirve para IVA, retenciones y la unidad de "
            "valor, no como fundamento clinico ni contractual."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["reforma tributaria", "UVB", "unidad de valor basico", "articulo 89"],
    },
    "LEY 776 DE 2002": {
        "nombre": "Ley 776 de 2002 (Congreso de la Republica)",
        "titulo": "Prestaciones del Sistema General de Riesgos Profesionales",
        "ambito": "De quien es la cuenta cuando el evento es de origen laboral",
        "vigente": True,
        "notas": (
            "Sirve cuando la EPS glosa una atencion alegando que el origen es laboral (o al "
            "reves): define las prestaciones que cubre el sistema de riesgos y quien responde por "
            "ellas."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["riesgos laborales", "origen laboral", "ARL", "prestaciones"],
    },
    "LEY 789 DE 2002": {
        "nombre": "Ley 789 de 2002 (Congreso de la Republica)",
        "titulo": "Apoyo al empleo y ampliacion de la proteccion social",
        "ambito": "Acreditacion del pago de aportes al sistema (Art. 50)",
        "vigente": True,
        "notas": (
            "Su articulo 50 exige acreditar el pago de aportes a salud, pensiones, riesgos "
            "laborales y cajas de compensacion. Se invoca cuando la entidad condiciona el pago a "
            "requisitos de aportes."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["aportes al sistema", "articulo 50", "proteccion social"],
    },
    # 25-08-2026: artículos 168, 177 y 178 contrastados contra el texto
    # oficial (normograma SuperSalud). El 177 estaba mal de nombre y de
    # texto; el 178 tenía un resumen donde debía ir la cita.
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
            # 25-08-2026 — CORREGIDO. Decía «Obligaciones de las Entidades
            # Promotoras de Salud» y le atribuía un texto sobre «movilizar los
            # recursos para el otorgamiento del POS a través de patrimonios
            # autónomos». Esa frase NO APARECE en la Ley 100: se buscó en el
            # texto completo. El artículo 177 es la DEFINICIÓN de qué es una EPS.
            "177": {
                "titulo": "Definición",
                "texto": (
                    "Las Entidades Promotoras de Salud son las entidades responsables de "
                    "la afiliación, y el registro de los afiliados y del recaudo de sus "
                    "cotizaciones, por delegación del Fondo de Solidaridad y Garantía. Su "
                    "función básica será organizar y garantizar, directa o indirectamente, "
                    "la prestación del Plan de Salud Obligatorio a los afiliados y girar, "
                    "dentro de los términos previstos en la presente Ley, la diferencia "
                    "entre los ingresos por cotizaciones de sus afiliados y el valor de "
                    "las correspondientes Unidades de Pago por Capitación al Fondo de "
                    "Solidaridad y Garantía."
                ),
                "aplicacion": (
                    "Sirve para recordarle a la EPS que garantizar la prestación es su "
                    "función básica, no un favor. NO le atribuya el deber de «movilizar "
                    "recursos al POS»: esa frase no está en la ley. Las funciones "
                    "detalladas están en el artículo 178."
                ),
                "keywords": ["EPS", "definición", "afiliación", "UPC"],
            },
            "178": {
                "titulo": "Funciones de las EPS",
                "texto": (
                    "Las Entidades Promotoras de Salud tendrán las siguientes funciones: "
                    "1. Ser delegatarias del Fondo de Solidaridad y Garantía para la "
                    "captación de los aportes de los afiliados al Sistema General de "
                    "Seguridad Social en Salud. 2. Promover la afiliación de grupos de "
                    "población no cubiertos actualmente por la Seguridad Social. "
                    "3. Organizar la forma y mecanismos a través de los cuales los "
                    "afiliados y sus familias puedan acceder a los servicios de salud en "
                    "todo el territorio nacional. (…) 4. Definir procedimientos para "
                    "garantizar el libre acceso de los afiliados y sus familias, a las "
                    "Instituciones Prestadoras (…)"
                ),
                "aplicacion": "Funciones de las EPS en el sistema",
                "keywords": ["funciones EPS", "POS", "afiliación"],
            },
        },
        "verificada": "25-08-2026 arts. 168, 177 y 178 contra el texto oficial (normograma SuperSalud)",
        "keywords": ["sistema general", "seguridad social", "SGSSS", "salud", "pensiones"],
    },
    "LEY 1122 DE 2007": {
        "nombre": "Ley 1122 de 2007",
        "titulo": "Por la cual se hacen modificaciones al Sistema General de Seguridad Social en Salud",
        "ambito": "Modificaciones al SGSSS",
        "vigente": True,
        "articulos": {
            # 25-08-2026 — CORREGIDO. El texto guardado decía, en plano, que las
            # EPS «girarán como mínimo el 50% de los valores facturados dentro de
            # los cinco días». El literal d) real lo condiciona a la MODALIDAD de
            # pago: 100% mes anticipado si el contrato es por capitación, y el 50%
            # anticipado solo «si fuesen por otra modalidad». Afirmar la regla sin
            # su condición es darle a la entidad la forma de tumbarla en un
            # contrato capitado.
            "13": {
                "titulo": "Flujo y protección de los recursos (literal d)",
                "texto": (
                    "Las Entidades Promotoras de Salud EPS de ambos regímenes pagarán "
                    "los servicios a los Prestadores de Servicios de salud habilitados, "
                    "mes anticipado en un 100% si los contratos son por capitación. Si "
                    "fuesen por otra modalidad, como pago por evento, global prospectivo "
                    "o grupo diagnóstico se hará como mínimo un pago anticipado del 50% "
                    "del valor de la factura, dentro de los cinco días posteriores a su "
                    "presentación. En caso de no presentarse objeción o glosa alguna, el "
                    "saldo se pagará dentro de los treinta (30) días siguientes a la "
                    "presentación de la factura."
                ),
                "aplicacion": (
                    "Los plazos de pago. OJO CON LA CONDICIÓN: el anticipo del 50% en "
                    "cinco días es para pago por evento, global prospectivo o grupo "
                    "diagnóstico. Si el contrato es por CAPITACIÓN la regla es otra: "
                    "100% mes anticipado. Y los 30 días del saldo corren solo «en caso "
                    "de no presentarse objeción o glosa alguna» — con glosa de por medio "
                    "el que manda es el Art. 57 de la Ley 1438."
                ),
                "keywords": [
                    "flujo de recursos",
                    "plazos de pago",
                    "anticipo 50%",
                    "capitación",
                    "treinta días",
                ],
            },
        },
        "verificada": "25-08-2026 art. 13 literal d) contra el texto oficial — se corrigió: faltaba la condición de modalidad",
        "keywords": ["flujo recursos", "anticipo", "pagos"],
    },
    # 25-08-2026: artículos 56, 105 y 126 verificados y corregidos contra el
    # texto oficial (normograma de la SuperSalud). Los tres tenían mal el
    # epígrafe y dos de ellos, además, texto que no está en la ley.
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
            # 25-08-2026 — CORREGIDO. Decía «Trámite de pagos» con un texto que
            # hablaba de pagar «el monto total dentro de los treinta (30) días».
            # El artículo real se llama «Pagos a los prestadores de servicios de
            # salud» y remite los plazos a lo que fije el Gobierno según la Ley
            # 1122. Y trae algo que el motor no estaba usando: la prohibición de
            # exigir auditoría previa para recibir la factura — que el corpus le
            # atribuía, con texto inventado, a un artículo del Decreto 780.
            "56": {
                "titulo": "Pagos a los prestadores de servicios de salud",
                "texto": (
                    "Las Entidades Promotoras de Salud pagarán los servicios a los "
                    "prestadores de servicios de salud dentro de los plazos, condiciones, "
                    "términos y porcentajes que establezca el Gobierno Nacional según el "
                    "mecanismo de pago, de acuerdo con lo establecido en la Ley 1122 de "
                    "2007. El no pago dentro de los plazos causará intereses moratorios a "
                    "la tasa establecida para los impuestos administrados por la Dirección "
                    "de Impuestos y Aduanas Nacionales (DIAN). Se prohíbe el "
                    "establecimiento de la obligatoriedad de procesos de auditoría previa "
                    "a la presentación de las facturas por prestación de servicios o "
                    "cualquier práctica tendiente a impedir la recepción."
                ),
                "aplicacion": (
                    "Dos argumentos fuertes en un solo artículo: (1) el no pago a tiempo "
                    "causa intereses moratorios a la tasa DIAN; (2) está PROHIBIDO exigir "
                    "auditoría previa para recibir la factura, o cualquier práctica que "
                    "impida la recepción. Es de rango de LEY, más fuerte que la "
                    "Resolución 2284. NO afirmar «treinta días»: el artículo remite los "
                    "plazos al Gobierno Nacional y a la Ley 1122 de 2007."
                ),
                "keywords": [
                    "pagos",
                    "intereses moratorios",
                    "auditoría previa",
                    "recepción de facturas",
                    "DIAN",
                ],
            },
            # 25-08-2026 (noche) — CORREGIDO CONTRA DOS FUENTES OFICIALES
            # (normograma de la SuperSalud y Senado de la República).
            #
            # El "texto" guardado era una PARÁFRASIS con dos frases que NO están
            # en el artículo:
            #   · «Si los prestadores no contestan en el plazo señalado, se
            #     entenderá aceptada la glosa» — la consecuencia es real, pero
            #     su fuente es el código RE2202 del Manual Único (Res. 2284 de
            #     2023), no este artículo.
            #   · «podrá optar por la conciliación, el ARBITRAJE o acudir ante
            #     las autoridades judiciales» — el artículo no menciona
            #     arbitraje; manda a la Superintendencia Nacional de Salud.
            #
            # Y le faltaban los números dentro del texto: los plazos estaban
            # solo en la lista de abajo, desconectados de la cita. De ahí salió
            # el dictamen GL-131, que escribió «el artículo 57 fija DIEZ (10)
            # días hábiles para responder» — son QUINCE. Decirle a la entidad
            # que nuestro plazo es más corto de lo que es le regala el
            # argumento de extemporaneidad contra el propio hospital.
            "57": {
                "titulo": "Trámite de glosas",
                "texto": (
                    "Las entidades responsables del pago de servicios de salud dentro de "
                    "los veinte (20) días hábiles siguientes a la presentación de la "
                    "factura con todos sus soportes, formularán y comunicarán a los "
                    "prestadores de servicios de salud las glosas a cada factura, con base "
                    "en la codificación y alcance definidos en la normatividad vigente. "
                    "Una vez formuladas las glosas a una factura no se podrán formular "
                    "nuevas glosas a la misma factura, salvo las que surjan de hechos "
                    "nuevos detectados en la respuesta dada a la glosa inicial. El "
                    "prestador de servicios de salud deberá dar respuesta a las glosas "
                    "presentadas por las entidades responsables del pago de servicios de "
                    "salud, dentro de los quince (15) días hábiles siguientes a su "
                    "recepción, indicando su aceptación o justificando la no aceptación. "
                    "La entidad responsable del pago, dentro de los diez (10) días hábiles "
                    "siguientes a la recepción de la respuesta, decidirá si levanta total "
                    "o parcialmente las glosas o las deja como definitivas. Si cumplidos "
                    "los quince (15) días hábiles, el prestador de servicios de salud "
                    "considera que la glosa es subsanable, tendrá un plazo máximo de siete "
                    "(7) días hábiles para subsanar la causa de las glosas no levantadas "
                    "(…). Una vez vencidos los términos, y en el caso de que persista el "
                    "desacuerdo se acudirá a la Superintendencia Nacional de Salud, bien "
                    "sea en uso de la facultad de conciliación o jurisdiccional a elección "
                    "del prestador."
                ),
                "aplicacion": (
                    "El artículo que más usa el motor. TRES AVISOS al citarlo:\n"
                    "(1) NO le atribuya la carga de la prueba: el artículo no la menciona "
                    "(dictamen GL-127 lo hizo y es refutable de una).\n"
                    "(2) NO le atribuya la aceptación tácita por silencio del prestador: "
                    "esa consecuencia es real pero viene del código RE2202 del Manual "
                    "Único (Res. 2284 de 2023) — cítela por su nombre.\n"
                    "(3) Los plazos, sin cambiarlos: 20 hábiles para que la entidad "
                    "glose · 15 para que el prestador responda · 10 para que la entidad "
                    "decida · 7 de subsanación · 5 para pagar lo levantado.\n"
                    "Lo mejor del artículo para el hospital: prohíbe glosas nuevas sobre "
                    "la misma factura salvo por hechos nuevos, y deja a ELECCIÓN DEL "
                    "PRESTADOR la vía ante la SuperSalud."
                ),
                "keywords": [
                    "trámite de glosas",
                    "20 días",
                    "15 días",
                    "10 días",
                    "hechos nuevos",
                    "extemporánea",
                    "superintendencia",
                ],
            },
            # 25-08-2026: el título decía «Supervisión, inspección y vigilancia».
            # El real es «Función jurisdiccional de la Superintendencia Nacional
            # de Salud», y lo que hace es adicionarle literales al Art. 41 de la
            # Ley 1122 — entre ellos el f), que es justo el de las glosas.
            "126": {
                "titulo": "Función jurisdiccional de la Superintendencia Nacional de Salud",
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
            # 25-08-2026 — CORREGIDO. Decía «Prohibición de intromisión en el
            # acto médico» con un texto que no está en la ley. El artículo real
            # se llama «Autonomía profesional» y DEFINE qué es esa autonomía;
            # sirve igual para la defensa, pero hay que citarlo por lo que dice.
            "105": {
                "titulo": "Autonomía profesional",
                "texto": (
                    "Entiéndase por autonomía de los profesionales de la salud, la "
                    "garantía que el profesional de la salud pueda emitir con toda "
                    "libertad su opinión profesional con respecto a la atención y "
                    "tratamiento de sus pacientes con calidad, aplicando las normas, "
                    "principios y valores que regulan el ejercicio de su profesión."
                ),
                "aplicacion": (
                    "Para las glosas de pertinencia: la ley garantiza que el médico opine "
                    "con libertad sobre la atención de su paciente. Acompaña al Art. 17 de "
                    "la Ley 1751 de 2015 y al Art. 26 de la Ley 1164 de 2007. NO le "
                    "atribuya la frase «las entidades no podrán interferir»: eso no está "
                    "en el artículo."
                ),
                "keywords": ["autonomía profesional", "acto médico", "pertinencia"],
            },
        },
        "verificada": "25-08-2026 arts. 56, 105 y 126 contra el texto oficial (normograma SuperSalud)",
        "keywords": [
            "glosa",
            "plazo",
            "30 días",
            "trámite de glosas",
            "ratificación",
            "intromisión acto médico",
        ],
    },
    # 25-08-2026: artículos 15 y 17 contrastados contra el texto oficial.
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
                # 25-08-2026: el epígrafe real es solo «Prestaciones de salud».
                "titulo": "Prestaciones de salud",
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
        "verificada": "25-08-2026 arts. 15 y 17 contra el texto oficial (normograma SuperSalud)",
        "keywords": ["estatutaria", "derecho fundamental", "autonomía"],
    },
    "LEY 1709 DE 2014": {
        "nombre": "Ley 1709 de 2014",
        "titulo": "Reforma Código Penitenciario y Carcelario — atención en salud a PPL",
        "ambito": "Cobertura salud Población Privada de Libertad",
        "vigente": True,
        "articulos": {
            "65": {
                "titulo": "Modifícase el artículo 104 de la Ley 65 de 1993 — «Artículo 104. Acceso a la salud»",
                "texto": (
                    "Acceso a la salud. Las personas privadas de la libertad tendrán acceso a "
                    "todos los servicios del sistema general de salud de conformidad con lo "
                    "establecido en la ley sin discriminación por su condición jurídica. Se "
                    "garantizarán la prevención, diagnóstico temprano y tratamiento adecuado de "
                    "todas las patologías físicos o mentales. Cualquier tratamiento médico, "
                    "quirúrgico o psiquiátrico que se determine como necesario para el "
                    "cumplimiento de este fin será aplicado sin necesidad de resolución judicial "
                    "que lo ordene. En todo caso el tratamiento médico o la intervención "
                    "quirúrgica deberán realizarse garantizando el respeto a la dignidad humana "
                    "de las personas privadas de la libertad. En todos los centros de reclusión "
                    "se garantizará la existencia de una Unidad de Atención Primaria y de "
                    "Atención Inicial de Urgencias en Salud Penitenciaria y Carcelaria. Se "
                    "garantizará el tratamiento médico a la población en condición de "
                    "discapacidad que observe el derecho a la rehabilitación requerida, "
                    "atendiendo un enfoque diferencial de acuerdo a la necesidad específica.» "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: el otro revisor tiene razón en las "
                    "dos cosas. (a) El artículo 65 SÍ existe. (b) El epígrafe guardado, "
                    "«Atención en salud a PPL», es inventado: el artículo 65 de la Ley 1709 no "
                    "tiene epígrafe propio, es una norma modificatoria que empieza «Modifícase "
                    "el artículo 104 de la Ley 65 de 1993, el cual quedará así:» y el título del "
                    "artículo que introduce es «Acceso a "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
                "texto": (
                    "Sistema General de Riesgos Laborales: Es el conjunto de entidades públicas "
                    "y privadas, normas y procedimientos, destinados a prevenir, proteger y "
                    "atender a los trabajadores de los efectos de las enfermedades y los "
                    "accidentes que puedan ocurrirles con ocasión o como consecuencia del "
                    "trabajo que desarrollan. Las disposiciones vigentes de salud ocupacional "
                    "relacionadas con la prevención de los accidentes de trabajo y enfermedades "
                    "laborales y el mejoramiento de las condiciones de trabajo, hacen parte "
                    "integrante del Sistema General de Riesgos Laborales. Salud Ocupacional: Se "
                    "entenderá en adelante como Seguridad y Salud en el Trabajo, definida como "
                    "aquella disciplina que trata de la prevención de las lesiones y "
                    "enfermedades causadas por las condiciones de trabajo, y de la protección y "
                    "promoción de la salud de los trabajadores. Tiene por objeto mejorar las "
                    "condiciones y el medio ambiente de trabajo, así como la salud en el "
                    "trabajo, que conlleva la promoción y el mantenimiento del bienestar físico, "
                    "mental y social de los trabajadores en todas las ocupaciones. Programa de "
                    "Salud Ocupacional: en lo sucesivo se entenderá como el Sistema de Gestión "
                    "de la Seguridad y Salud en el Trabajo SG-SST. Este Sistema consiste en el "
                    "desarrollo de un proceso lógico y por etapas, basado en la mejora continua "
                    "y que incluye la política, la organización, la planificación, la "
                    "aplicación, la evaluación, la auditoría y las acciones de mejora con el "
                    "objetivo de anticipar, reconocer, evaluar y controlar los riesgos que "
                    "puedan afectar la seguridad y salud en el trabajo. PARÁGRAFO. El uso de las "
                    "anteriores definiciones no obsta para que no se mantengan los derechos ya "
                    "existentes con las definiciones anteriores. "
                ),
                "aplicacion": (
                    "Fui yo mismo a la fuente oficial y no pude refutar el hallazgo: el otro "
                    "revisor tiene razón. En el Normograma de la Supersalud y en la Secretaría "
                    "del Senado el artículo 1 de la Ley 1562 de 2012 aparece rotulado «ARTÍCULO "
                    "1o. Definiciones», de modo que el epígrafe guardado («Definiciones») es "
                    "correcto y no hay invención en el título. El problema está en el texto, por "
                    "dos razones. (1) Está retocado "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
        "keywords": ["ARL", "riesgos laborales", "Positiva", "Aurora"],
    },
    "LEY 352 DE 1997": {
        "nombre": "Ley 352 de 1997",
        "titulo": "Régimen de Salud de las Fuerzas Militares y Policía Nacional",
        "ambito": "Subsistema de Salud FF.MM. y Policía",
        "vigente": True,
        "articulos": {
            "7": {
                "titulo": "FUNCIONES",
                "texto": (
                    "Son funciones del CSSMP: a) Adoptar las políticas, planes, programas y "
                    "prioridades generales del SSMP; b) Señalar los lineamientos generales de "
                    "organización, orientación y funcionamiento de los subsistemas; c) Aprobar "
                    "el anteproyecto de presupuesto general de los subsistemas de salud de las "
                    "Fuerzas Militares y de la Policía Nacional, presentado por los respectivos "
                    "directores; d) Aprobar el Plan de Servicios de Sanidad Militar y Policial y "
                    "los planes complementarios de salud, con sujeción a los recursos "
                    "disponibles para la prestación del servicio de salud en cada uno de los "
                    "subsistemas; e) Determinar y reglamentar el funcionamiento de los fondos "
                    "cuenta que se crean por la presente Ley; f) Aprobar los parámetros de "
                    "administración, transferencia interna y aplicación de recursos para cada "
                    "uno de los subsistemas con base en los presupuestos disponibles; g) "
                    "<Literal INEXEQUIBLE>; h) Aprobar el monto de los pagos compartidos y "
                    "cuotas moderadoras para cada uno de los subsistemas a fin de racionalizar "
                    "el servicio de salud; i) Autorizar a las entidades y a las unidades que "
                    "conforman el SSMP la prestación de servicios de salud a terceros o a "
                    "entidades promotoras de salud y determinar los parámetros que aseguren la "
                    "atención preferencial de las necesidades de los afiliados y beneficiarios "
                    "del sistema; j) Adoptar los regímenes de referencia y contrarreferencia "
                    "para cada uno de los subsistemas; k) <Literal INEXEQUIBLE>; l) Dictar su "
                    "propio reglamento; m) Expedir los actos administrativos para el "
                    "cumplimiento de sus funciones; n) Las demás que le señale la ley. "
                ),
                "aplicacion": (
                    "El hallazgo del otro revisor es correcto y no pude refutarlo. (a) El "
                    "artículo 7o. SÍ existe en la Ley 352 de 1997. (b) El epígrafe guardado "
                    "«Subsistema de Salud» es falso: el epígrafe real es «FUNCIONES», y el "
                    "artículo enumera las funciones del Consejo Superior de Salud de las Fuerzas "
                    "Militares y de la Policía Nacional (CSSMP) en literales a) a n). (c) El "
                    "texto guardado no es literal ni siquiera u "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
    # 25-08-2026: el lote de recepcion cito 3 veces la Ley 1164 de 2007 para
    # sostener la autonomia del medico tratante y el revisor la marco como
    # NORMA_INEXISTENTE — no porque no exista, sino porque el corpus no la
    # tenia. La ley es real (Diario Oficial, 3 de octubre de 2007) y su
    # articulo 26 dice justo lo que el dictamen le atribuye.
    "LEY 1164 DE 2007": {
        "nombre": "Ley 1164 de 2007 (Congreso de Colombia, 3 de octubre de 2007)",
        "titulo": "Disposiciones en materia del Talento Humano en Salud",
        "ambito": "Ejercicio profesional, autonomia y etica del personal de salud",
        "vigente": True,
        "articulos": {
            "26": {
                "titulo": "Acto propio de los profesionales de la salud",
                "texto": (
                    "Entendido como el conjunto de acciones orientadas a la atencion integral "
                    "del usuario, aplicadas por el profesional autorizado legalmente para "
                    "ejercerlas dentro del perfil que le otorga el respectivo titulo, el acto "
                    "profesional se caracteriza por la autonomia profesional y la relacion "
                    "entre el profesional de la salud y el usuario. Esta relacion de asistencia "
                    "en salud genera una obligacion de medios, basada en la competencia "
                    "profesional."
                ),
            },
            "35": {
                "titulo": "De los principios Eticos y Bioeticos",
                "texto": (
                    "Ademas de los principios rectores consagrados en la Constitucion Politica, "
                    "son requisitos de quien ejerce una profesion u ocupacion en salud, la "
                    "veracidad, la igualdad, la autonomia, la beneficencia, el mal menor, la no "
                    "maleficencia, la totalidad y la causa de doble efecto. De autonomia: el "
                    "personal de salud debe ejercer su capacidad para deliberar, decidir y "
                    "actuar."
                ),
            },
        },
        "notas": (
            "Es el respaldo legal de la autonomia del medico tratante frente a una glosa de "
            "pertinencia: el articulo 26 define el acto profesional como caracterizado por la "
            "autonomia. Acompana al articulo 17 de la Ley 1751 de 2015, no lo reemplaza."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": [
            "talento humano en salud",
            "autonomia profesional",
            "acto propio",
            "medico tratante",
            "pertinencia",
            "etica",
        ],
    },
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
        "verificada": "25-08-2026 art. 34 contra el texto oficial — coincide literalmente",
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
                "titulo": "DE LOS PRINCIPIOS EN LAS ACTUACIONES CONTRACTUALES DE LAS ENTIDADES ESTATALES",
                "texto": (
                    "Las actuaciones de quienes intervengan en la contratación estatal se "
                    "desarrollarán con arreglo a los principios de transparencia, economía y "
                    "responsabilidad y de conformidad con los postulados que rigen la función "
                    "administrativa. Igualmente, se aplicarán en las mismas las normas que "
                    "regulan la conducta de los servidores públicos, las reglas de "
                    "interpretación de la contratación, los principios generales del derecho y "
                    "los particulares del derecho administrativo. "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: el otro revisor tiene razón. (a) El "
                    "artículo 23 SÍ existe en la Ley 80 de 1993 y abre el Capítulo II «DE LOS "
                    "PRINCIPIOS DE LA CONTRATACIÓN ESTATAL». (b) El epígrafe guardado está MAL: "
                    "el real, idéntico en las dos fuentes oficiales consultadas, es «DE LOS "
                    "PRINCIPIOS EN LAS ACTUACIONES CONTRACTUALES DE LAS ENTIDADES ESTATALES», "
                    "mientras el corpus guarda «Princi "
                ),
                "keywords": [],
            },
            "27": {
                "titulo": "DE LA ECUACIÓN CONTRACTUAL",
                "texto": (
                    "En los contratos estatales se mantendrá la igualdad o equivalencia entre "
                    "derechos y obligaciones surgidos al momento de proponer o de contratar, "
                    "según el caso. Si dicha igualdad o equivalencia se rompe por causas no "
                    "imputables a quien resulte afectado, las partes adoptarán en el menor "
                    "tiempo posible las medidas necesarias para su restablecimiento. // Para "
                    "tales efectos, las partes suscribirán los acuerdos y pactos necesarios "
                    "sobre cuantía, condiciones y forma de pago de gastos adicionales, "
                    "reconocimiento de costos financieros e intereses, si a ello hubiere lugar, "
                    "ajustando la cancelación a las disponibilidades de la apropiación de que "
                    "trata el numeral 14 del artículo 25. En todo caso, las entidades deberán "
                    "adoptar las medidas necesarias que aseguren la efectividad de estos pagos y "
                    "reconocimientos al contratista en la misma o en la siguiente vigencia de "
                    "que se trate. "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: el revisor tiene razón en los dos "
                    "puntos. (a) El artículo 27 SÍ existe y está vigente, sin notas de "
                    "derogatoria ni de modificación (solo aparecen anotaciones de "
                    "«Jurisprudencia Vigencia» y «Concordancias»). (b) El EPÍGRAFE guardado está "
                    "mal: en el texto oficial dice exactamente «ARTÍCULO 27. DE LA ECUACIÓN "
                    "CONTRACTUAL.», sin el añadido «y equilibrio económico "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
                "titulo": "Convenios o contratos interadministrativos",
                "texto": (
                    "La modalidad de selección para la contratación entre Entidades Estatales es "
                    "la contratación directa; y en consecuencia, le es aplicable lo establecido "
                    "en el artículo 2.2.1.2.1.4.1 del presente decreto. Cuando la totalidad del "
                    "presupuesto de una Entidad Estatal hace parte del presupuesto de otra con "
                    "ocasión de un convenio o contrato interadministrativo, el monto del "
                    "presupuesto de la primera deberá deducirse del presupuesto de la segunda "
                    "para determinar la capacidad contractual de las Entidades Estatales. "
                    "(Decreto 1510 de 2013, artículo 76) "
                ),
                "aplicacion": (
                    "Verifiqué yo mismo el texto oficial del Decreto 1082 de 2015 y el hallazgo "
                    "del otro revisor se confirma en los tres puntos. (a) El artículo "
                    "2.2.1.2.1.4.4 SÍ existe: está en el Libro 2, Parte 2, Título 1, Capítulo 2, "
                    "Sección 1, Subsección 4 «CONTRATACIÓN DIRECTA». (b) El epígrafe guardado "
                    "(«Contratación de prestadores de servicios de salud») es FALSO; el epígrafe "
                    "real es «CONVENIOS O CONTRATOS INTE "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
        "keywords": ["contratación estatal", "DUR", "servicios de salud", "Decreto 1082"],
    },
    "LEY 599 DE 2000": {
        "nombre": "Ley 599 de 2000 (Código Penal)",
        "titulo": "Código Penal — delitos contra la fe pública y el patrimonio",
        "ambito": "Falsedad documental, fraude y peculado en glosas",
        "vigente": True,
        "articulos": {
            "286": {
                "titulo": "FALSEDAD IDEOLOGICA EN DOCUMENTO PÚBLICO",
                "texto": (
                    "El servidor público que en ejercicio de sus funciones, al extender "
                    "documento público que pueda servir de prueba, consigne una falsedad o calle "
                    "total o parcialmente la verdad, incurrirá en prisión de sesenta y cuatro "
                    "(64) a ciento cuarenta y cuatro (144) meses e inhabilitación para el "
                    "ejercicio de derechos y funciones públicas de ochenta (80) a ciento ochenta "
                    "(180) meses. (Penas aumentadas por el artículo 14 de la Ley 890 de 2004, a "
                    "partir del 1o. de enero de 2005.) "
                ),
                "aplicacion": (
                    "Fui a la fuente oficial y el hallazgo del otro revisor queda confirmado. El "
                    "artículo 286 SÍ existe en la Ley 599 de 2000 y el epígrafe guardado es "
                    "correcto en sustancia (la norma lo imprime en mayúsculas y sin tilde: "
                    "«FALSEDAD IDEOLOGICA EN DOCUMENTO PÚBLICO»), así que el título no está "
                    "inventado, solo con otra ortografía. El problema es el TEXTO: el corpus "
                    "guarda la redacción ORIGINAL de 2000, de "
                ),
                "keywords": [],
            },
            "289": {
                "titulo": "Falsedad en documento privado",
                "texto": (
                    "El que falsifique documento privado que pueda servir de prueba, incurrirá, "
                    "si lo usa, en prisión de dieciséis (16) a ciento ocho (108) meses. "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: la fuente oficial le da la razón. "
                    "(a) EXISTENCIA — El artículo 289 SÍ existe en la Ley 599 de 2000 (Código "
                    "Penal), Título IX «De los delitos contra la fe pública», Capítulo III «De "
                    "la falsedad en documentos». (b) EPÍGRAFE — El epígrafe guardado, «Falsedad "
                    "en documento privado», es el REAL. En el texto de la Secretaría del Senado "
                    "aparece como «ARTÍCULO 289. "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
                "titulo": "Términos para resolver las distintas modalidades de peticiones",
                "texto": (
                    "Artículo 14. Términos para resolver las distintas modalidades de "
                    "peticiones. Salvo norma legal especial y so pena de sanción disciplinaria, "
                    "toda petición deberá resolverse dentro de los quince (15) días siguientes a "
                    "su recepción. Estará sometida a término especial la resolución de las "
                    "siguientes peticiones: 1. Las peticiones de documentos y de información "
                    "deberán resolverse dentro de los diez (10) días siguientes a su recepción. "
                    "Si en ese lapso no se ha dado respuesta al peticionario, se entenderá, para "
                    "todos los efectos legales, que la respectiva solicitud ha sido aceptada y, "
                    "por consiguiente, la administración ya no podrá negar la entrega de dichos "
                    "documentos al peticionario, y como consecuencia las copias se entregarán "
                    "dentro de los tres (3) días siguientes. 2. Las peticiones mediante las "
                    "cuales se eleva una consulta a las autoridades en relación con las materias "
                    "a su cargo deberán resolverse dentro de los treinta (30) días siguientes a "
                    "su recepción. PARÁGRAFO. Cuando excepcionalmente no fuere posible resolver "
                    "la petición en los plazos aquí señalados, la autoridad debe informar esta "
                    "circunstancia al interesado, antes del vencimiento del término señalado en "
                    "la ley expresando los motivos de la demora y señalando a la vez el plazo "
                    "razonable en que se resolverá o dará respuesta, que no podrá exceder del "
                    "doble del inicialmente previsto. "
                ),
                "aplicacion": (
                    "INTENTÉ REFUTARLO Y NO PUDE: el otro revisor tiene razón en los tres "
                    "puntos. Descargué la norma yo mismo de dos fuentes oficiales y el texto "
                    "coincide palabra por palabra entre ellas. 1) EPÍGRAFE: el guardado dice "
                    "«Términos para resolver». El real, idéntico en Senado y en Normograma "
                    "SuperSalud, es «Términos para resolver las distintas modalidades de "
                    "peticiones». Confirmado: el epígrafe guardado es "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
        "keywords": ["derecho de petición", "términos", "respuesta", "Ley 1755"],
    },
    "LEY 1437 DE 2011 (CPACA)": {
        "nombre": "Ley 1437 de 2011 (CPACA)",
        "titulo": "Código de Procedimiento Administrativo y de lo Contencioso Administrativo",
        "ambito": "Actuaciones administrativas — procedimiento ante la administración",
        "vigente": True,
        "articulos": {
            "14": {
                "titulo": "Términos para resolver las distintas modalidades de peticiones",
                "texto": (
                    "Salvo norma legal especial y so pena de sanción disciplinaria, toda "
                    "petición deberá resolverse dentro de los quince (15) días siguientes a su "
                    "recepción. Estará sometida a término especial la resolución de las "
                    "siguientes peticiones: 1. Las peticiones de documentos y de información "
                    "deberán resolverse dentro de los diez (10) días siguientes a su recepción. "
                    "Si en ese lapso no se ha dado respuesta al peticionario, se entenderá, para "
                    "todos los efectos legales, que la respectiva solicitud ha sido aceptada y, "
                    "por consiguiente, la administración ya no podrá negar la entrega de dichos "
                    "documentos al peticionario, y como consecuencia las copias se entregarán "
                    "dentro de los tres (3) días siguientes. 2. Las peticiones mediante las "
                    "cuales se eleva una consulta a las autoridades en relación con las materias "
                    "a su cargo deberán resolverse dentro de los treinta (30) días siguientes a "
                    "su recepción. PARÁGRAFO. Cuando excepcionalmente no fuere posible resolver "
                    "la petición en los plazos aquí señalados, la autoridad debe informar esta "
                    "circunstancia al interesado, antes del vencimiento del término señalado en "
                    "la ley expresando los motivos de la demora y señalando a la vez el plazo "
                    "razonable en que se resolverá o dará respuesta, que no podrá exceder del "
                    "doble del inicialmente previsto. [Nota de vigencia obligatoria en la cita: "
                    "artículo modificado por el artículo 1 de la Ley 1755 de 2015.] "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: el otro revisor tiene razón en los "
                    "dos puntos. (a) El artículo 14 SÍ existe. (b) El epígrafe real es «TÉRMINOS "
                    "PARA RESOLVER LAS DISTINTAS MODALIDADES DE PETICIONES»; el corpus lo tenía "
                    "truncado como «Términos para resolver peticiones». (c) El texto guardado NO "
                    "es literal: es un resumen. Le falta el encabezado, que es la regla general "
                    "y va PRIMERO («Salvo nor "
                ),
                "keywords": [],
            },
            "164": {
                "titulo": "OPORTUNIDAD PARA PRESENTAR LA DEMANDA",
                "texto": (
                    "La demanda deberá ser presentada: 1. En cualquier tiempo, cuando: a) Se "
                    "pretenda la nulidad en los términos del artículo 137 de este Código; (…) f) "
                    "En los demás casos expresamente establecidos en la ley. 2. En los "
                    "siguientes términos, so pena de que opere la caducidad: (…) d) Cuando se "
                    "pretenda la nulidad y restablecimiento del derecho, la demanda deberá "
                    "presentarse dentro del término de cuatro (4) meses contados a partir del "
                    "día siguiente al de la comunicación, notificación, ejecución o publicación "
                    "del acto administrativo, según el caso, salvo las excepciones establecidas "
                    "en otras disposiciones legales; (…) i) Cuando se pretenda la reparación "
                    "directa, la demanda deberá presentarse dentro del término de dos (2) años, "
                    "contados a partir del día siguiente al de la ocurrencia de la acción u "
                    "omisión causante del daño, o de cuando el demandante tuvo o debió tener "
                    "conocimiento del mismo si fue en fecha posterior y siempre que pruebe la "
                    "imposibilidad de haberlo conocido en la fecha de su ocurrencia. Sin "
                    "embargo, el término para formular la pretensión de reparación directa "
                    "derivada del delito de desaparición forzada, se contará a partir de la "
                    "fecha en que aparezca la víctima o en su defecto desde la ejecutoria del "
                    "fallo definitivo adoptado en el proceso penal, sin perjuicio de que la "
                    "demanda con tal pretensión pueda intentarse desde el momento en que "
                    "ocurrieron los hechos que dieron lugar a la desaparición; j) En las "
                    "relativas a contratos el término para demandar será de dos (2) años que se "
                    "contarán a partir del día siguiente a la ocurrencia de los motivos de hecho "
                    "o de derecho que les sirvan de fundamento. Cuando se pretenda la nulidad "
                    "absoluta o relativa del contrato, el término para demandar será de dos (2) "
                    "años que se empezarán a contar desde el día siguiente al de su "
                    "perfeccionamiento. En todo caso, podrá demandarse la nulidad absoluta del "
                    "contrato mientras este se encuentre vigente. En los siguientes contratos, "
                    "el término de dos (2) años se contará así: i) En los de ejecución "
                    "instantánea desde el día siguiente a cuando se cumplió o debió cumplirse el "
                    "objeto del contrato; ii) En los que no requieran de liquidación, desde el "
                    "día siguiente al de la terminación del contrato por cualquier causa; iii) "
                    "En los que requieran de liquidación y esta sea efectuada de común acuerdo "
                    "por las partes, desde el día siguiente al de la firma del acta; iv) En los "
                    "que requieran de liquidación y esta sea efectuada unilateralmente por la "
                    "administración, desde el día siguiente al de la ejecutoria del acto "
                    "administrativo que la apruebe; v) En los que requieran de liquidación y "
                    "esta no se logre por mutuo acuerdo o no se practique por la administración "
                    "unilateralmente, una vez cumplido el término de dos (2) meses contados a "
                    "partir del vencimiento del plazo convenido para hacerlo bilateralmente o, "
                    "en su defecto, del término de los cuatro (4) meses siguientes a la "
                    "terminación del contrato o la expedición del acto que lo ordene o del "
                    "acuerdo que la disponga; k) Cuando se pretenda la ejecución con títulos "
                    "derivados del contrato, de decisiones judiciales proferidas por la "
                    "Jurisdicción de lo Contencioso Administrativo en cualquier materia y de "
                    "laudos arbitrales contractuales estatales, el término para solicitar su "
                    "ejecución será de cinco (5) años contados a partir de la exigibilidad de la "
                    "obligación en ellos contenida; l) <Literal modificado por el artículo 43 de "
                    "la Ley 2195 de 2022, corregido por el artículo 1 del Decreto 1463 de 2022. "
                    "El nuevo texto es el siguiente:> Cuando se pretenda repetir para recuperar "
                    "lo pagado como consecuencia de una condena, conciliación u otra forma de "
                    "terminación de un conflicto, el termino será de cinco (5) años, contados a "
                    "partir del día siguiente de la fecha del pago, o, a más tardar desde el "
                    "vencimiento del plazo con que cuenta la administración para el pago de "
                    "condenas de conformidad con lo previsto en este Código. "
                ),
                "aplicacion": (
                    "NO logré refutar al otro revisor: tiene razón en los dos puntos, y lo "
                    "comprobé yo mismo bajando la Ley 1437 de 2011 del normograma oficial de la "
                    "Superintendencia Nacional de Salud (HTTP 200, 720 KB, descarga propia, no "
                    "reutilicé archivos de otra sesión). (a) EXISTENCIA: el artículo 164 SÍ "
                    "existe en la Ley 1437 de 2011, y está vigente. (b) EPÍGRAFE: el guardado "
                    "(«Caducidad — pretensión por repara "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
                "titulo": "ACCIONES COMPLEMENTARIAS PARA LA ATENCIÓN INTEGRAL",
                "texto": (
                    "TEXTO VIGENTE (modificado por el artículo 12 de la Ley 2460 de 2025): "
                    "«ARTÍCULO 11. ACCIONES COMPLEMENTARIAS PARA LA ATENCIÓN INTEGRAL. <Artículo "
                    "modificado por el artículo 12 de la Ley 2460 de 2025. El nuevo texto es el "
                    "siguiente:> La atención integral en salud mental no se reducirá a un "
                    "tratamiento médico, psicológico o psiquiátrico, y se llevará a cabo con un "
                    "enfoque biopsicosocial y comunitario e incluirá acciones complementarias al "
                    "tratamiento tales como la integración familiar, social, laboral, educativa "
                    "y en actividades culturales, físicas, deportivas y/o recreativas. Para tal "
                    "efecto, el Ministerio de Salud y Protección en coordinación con el "
                    "Ministerio de Educación garantizará la incorporación del enfoque "
                    "promocional de la Calidad de Vida y la acción transectorial e "
                    "intersectorial necesaria como elementos fundamentales en el diseño, "
                    "implementación y evaluación de las acciones complementarias para la "
                    "atención integral en salud mental, y deberá incluir la educación emocional, "
                    "sensibilización y prevención de todo tipo de violencia. Para promover los "
                    "entornos protectores pana [sic] la salud mental, los entes territoriales y "
                    "las autoridades en temas de salud y educación de los niveles nacional, "
                    "departamental, distrital y municipal, armonizarán y articularán sus "
                    "campañas de prevención, sensibilización, orientación y capacitación, y "
                    "convocarán a participar a organizaciones sociales, étnicas y comunitarias, "
                    "a familias, a cuidadores y a otros actores interesados. Estas "
                    "capacitaciones deberán considerar las rutas de atención en salud mental, "
                    "educación emocional, sensibilización y prevención de todo tipo de violencia "
                    "y promover elementos básicos de autocuidado, incluyendo la promoción de "
                    "factores protectores, la atención en situaciones de crisis y los primeros "
                    "auxilios psicológicos, sin perjuicio de los demás ternos [sic] que se "
                    "definan en el marco de su autonomía.» TEXTO ORIGINAL DE LA LEY 1616 DE 2013 "
                    "(aplicable a servicios anteriores a la reforma de 2025): «ARTÍCULO 11. "
                    "ACCIONES COMPLEMENTARIAS PARA LA ATENCIÓN INTEGRAL. La atención integral en "
                    "salud mental incluirá acciones complementarias al tratamiento tales como la "
                    "integración familiar, social, laboral y educativa. Para tal efecto, el "
                    "Ministerio de Salud y Protección Social, garantizará la incorporación del "
                    "enfoque promocional de la Calidad de Vida y la acción transectorial e "
                    "intersectorial necesaria como elementos fundamentales en el diseño, "
                    "implementación y evaluación de las acciones complementarias para la "
                    "atención integral en salud mental.» CITA CORRECTA SI SE NECESITA "
                    "CONSENTIMIENTO INFORMADO EN SALUD MENTAL (artículo 6, Derechos de las "
                    "personas): «13. Derecho a exigir que sea tenido en cuenta el consentimiento "
                    "informado para recibir el tratamiento. 14. Derecho a no ser sometido a "
                    "ensayos clínicos ni tratamientos experimentales sin su consentimiento "
                    "informado.» "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: es correcto en todo. Descargué y "
                    "verifiqué yo mismo DOS fuentes oficiales independientes: 1) Ley 1616 de "
                    "2013 original firmada, publicada por el Ministerio de Salud (PDF de 17 "
                    "páginas, ley-1616-del-21-de-enero-2013.pdf). 2) Compilación vigente de la "
                    "Secretaría del Senado (ley_1616_2013.html, última actualización 15 de "
                    "agosto de 2026), que ya incorpora la Ley "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
    # ── Cargadas el 25-08-2026 ──────────────────────────────────────────
    # Los prompts del motor ya le ofrecian estas normas a la IA, pero no
    # estaban en el corpus con que se revisan las citas. Resultado: la IA las
    # citaba (porque se lo pedimos) y el revisor las marcaba en rojo como
    # "norma inexistente" sobre un dictamen que podia estar bien. Verificadas
    # una por una contra fuente oficial antes de cargarlas.
    "DECRETO 1477 DE 2014": {
        "nombre": "Decreto 1477 de 2014 (Ministerio del Trabajo)",
        "titulo": "Tabla de Enfermedades Laborales",
        "ambito": "Discusion de origen: laboral o comun",
        "vigente": True,
        "notas": (
            "Sirve para sustentar de quien es la cuenta cuando la EPS glosa una atencion alegando "
            "origen laboral: la tabla dice que enfermedades se presumen laborales."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["tabla de enfermedades laborales", "origen", "ARL"],
    },
    "DECRETO 1352 DE 2013": {
        "nombre": "Decreto 1352 de 2013 (Ministerio del Trabajo)",
        "titulo": "Juntas de Calificacion de Invalidez",
        "ambito": "Quien decide la controversia de origen",
        "vigente": True,
        "notas": (
            "Sirve en glosas de ARL: si la aseguradora alega que el evento no fue laboral sino "
            "comun, esa discusion la resuelven las Juntas de Calificacion, no la auditoria de "
            "cuentas."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["juntas de calificacion", "origen", "invalidez", "ARL"],
    },
    "DECRETO 1142 DE 2016": {
        "nombre": "Decreto 1142 de 2016 (Presidencia — sector Justicia)",
        "titulo": "Atencion en salud de la poblacion privada de la libertad",
        "ambito": "PPL — servicios a cargo del fondo de atencion en salud",
        "vigente": True,
        "notas": (
            "Sustenta que los servicios de salud de las personas privadas de la libertad se "
            "prestan y se pagan por el esquema especial del INPEC/USPEC, no por el PBS regular."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["PPL", "privados de la libertad", "INPEC", "modelo de atencion"],
    },
    "DECRETO 2462 DE 2013": {
        "nombre": "Decreto 2462 de 2013 (Presidencia — sector Salud)",
        "titulo": "Estructura de la Superintendencia Nacional de Salud",
        "ambito": "Inspeccion y vigilancia sobre EPS e IPS",
        "vigente": False,
        "derogada_por": (
            "figura como no vigente; verificar la norma que reestructuro la Supersalud antes de "
            "citarlo"
        ),
        "notas": (
            "Servia para senalar que dependencia de la Supersalud ejerce la inspeccion y "
            "vigilancia. Revisar la norma que lo reemplazo antes de citarlo."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["Supersalud", "inspeccion y vigilancia", "estructura"],
    },
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
        "verificada": "25-08-2026 art. 71 contra el texto oficial — coincide literalmente",
        "keywords": [
            "estatuto orgánico",
            "presupuesto",
            "apropiaciones",
            "agotamiento presupuestal",
        ],
    },
    # 25-08-2026 — CORREGIDO CONTRA LA FUENTE OFICIAL.
    # La segunda auditoría del lote del día encontró que el motor citaba el
    # «Artículo 20 del Decreto 4747 de 2007» como si regulara el trámite de
    # glosas — en las 28 respuestas de ratificación, el 100 %. Se contrastó
    # con el texto del decreto publicado por MinSalud y los TRES artículos que
    # tenía cargados este corpus estaban mal, con encabezado y texto
    # inventados:
    #
    #   Art. 11 decía «Atención de urgencias»            → es «Verificación de
    #                                                       derechos de los usuarios»
    #   Art. 20 decía «Trámite de glosas — conciliación» → es «RIPS»
    #   Art. 21 decía «Pago durante trámite de glosas»   → es «Soportes de las facturas»
    #
    # El trámite de glosas está en el Art. 23, y el Manual Único en el 22.
    # Como el revisor de citas contrasta contra ESTE corpus, la cita inventada
    # se certificaba sola: el dictamen salía «verificado» con una norma que
    # dice otra cosa. Es la misma lección de la jurisprudencia del 24-08.
    #
    # Los textos de abajo son literales del decreto. No se resumen ni se
    # reescriben: si el hospital los pone entre comillas, la entidad los
    # compara contra el original.
    "DECRETO 4747 DE 2007": {
        "nombre": "Decreto 4747 de 2007 (Ministerio de la Protección Social, 7 de diciembre)",
        "titulo": "Relaciones entre prestadores de servicios de salud y entidades responsables del pago",
        "ambito": "Trámite de glosas, soportes de factura y manual único",
        "vigente": True,
        "articulos": {
            "11": {
                "titulo": "Verificación de derechos de los usuarios",
                "texto": (
                    "La verificación de derechos de los usuarios es el procedimiento por medio "
                    "del cual se identifica la entidad responsable del pago de los servicios de "
                    "salud que demanda el usuario y el derecho del mismo a ser cubierto por "
                    "dicha entidad. (…) Parágrafo 1. El procedimiento de verificación de "
                    "derechos será posterior a la selección y clasificación del paciente, "
                    "«triage», y no podrá ser causa bajo ninguna circunstancia para negar la "
                    "atención de urgencias."
                ),
                "aplicacion": (
                    "Sirve cuando la glosa dice que el usuario no estaba afiliado o que el "
                    "responsable era otro: la verificación no puede negar la urgencia. NO es "
                    "el artículo de «urgencias sin autorización previa» — ese argumento se "
                    "sostiene en el Art. 67 de la Ley 1438 de 2011 y el Art. 168 de la Ley 100."
                ),
                "keywords": ["verificación de derechos", "afiliación", "triage", "urgencias"],
            },
            "20": {
                "titulo": "Registro Individual de Prestaciones de Salud - RIPS",
                "texto": (
                    "El Ministerio de la Protección Social revisará y ajustará el formato, "
                    "codificaciones, procedimientos y malla de validación de obligatoria "
                    "adopción por todas las entidades del Sistema General de Seguridad Social "
                    "en Salud, para el reporte del Registro Individual de Prestaciones de "
                    "Salud - RIPS."
                ),
                "aplicacion": (
                    "RIPS. NO regula el trámite de glosas: para eso es el Art. 23 de este "
                    "mismo decreto."
                ),
                "keywords": ["RIPS", "registro individual", "malla de validación"],
            },
            "21": {
                "titulo": "Soportes de las facturas de prestación de servicios",
                "texto": (
                    "Los prestadores de servicios de salud deberán presentar a las entidades "
                    "responsables de pago, las facturas con los soportes que, de acuerdo con el "
                    "mecanismo de pago, establezca el Ministerio de la Protección Social. La "
                    "entidad responsable del pago no podrá exigir soportes adicionales a los "
                    "definidos para el efecto por el Ministerio de la Protección Social."
                ),
                "aplicacion": (
                    "Es el artículo para las glosas SO: la entidad NO puede exigir un soporte "
                    "que el Ministerio no haya definido."
                ),
                "keywords": ["soportes", "factura", "soportes adicionales", "SO"],
            },
            "22": {
                "titulo": "Manual único de glosas, devoluciones y respuestas",
                "texto": (
                    "El Ministerio de la Protección Social expedirá el Manual Único de Glosas, "
                    "devoluciones y respuestas, en el que se establecerán la denominación, "
                    "codificación de las causas de glosa y de devolución de facturas, el cual "
                    "es de obligatoria adopción por todas las entidades del Sistema General de "
                    "Seguridad Social en Salud."
                ),
                "aplicacion": (
                    "Fundamenta que la entidad debe glosar con los códigos del manual vigente "
                    "(hoy la Resolución 2284 de 2023) y no con causales de su propia cosecha."
                ),
                "keywords": ["manual único de glosas", "codificación", "causales"],
            },
            "23": {
                "titulo": "Trámite de glosas",
                "texto": (
                    "Las entidades responsables del pago de servicios de salud dentro de los "
                    "treinta (30) días hábiles siguientes a la presentación de la factura con "
                    "todos sus soportes, formularán y comunicarán a los prestadores de "
                    "servicios de salud las glosas a cada factura, con base en la codificación "
                    "y alcance definidos en el manual único de glosas, devoluciones y "
                    "respuestas. Una vez formuladas las glosas a una factura, no se podrán "
                    "formular nuevas glosas a la misma factura, salvo las que surjan de hechos "
                    "nuevos detectados en la respuesta dada a la glosa inicial. El prestador de "
                    "servicios de salud deberá dar respuesta a las glosas presentadas por las "
                    "entidades responsables del pago de servicios de salud, dentro de los "
                    "quince (15) días hábiles siguientes a su recepción. (…) La entidad "
                    "responsable del pago, dentro de los diez (10) días hábiles siguientes, "
                    "decidirá si levanta total o parcialmente las glosas o las deja como "
                    "definitivas. Los valores por las glosas levantadas deberán ser cancelados "
                    "dentro de los cinco (5) días hábiles siguientes, informando de este hecho "
                    "al prestador de servicios de salud. (…) Vencidos los términos y en el caso "
                    "de que persista el desacuerdo se acudirá a la Superintendencia Nacional de "
                    "Salud, en los términos establecidos por la ley."
                ),
                "aplicacion": (
                    "ESTE es el artículo del trámite de glosas — el que hay que citar, no el "
                    "20. Dos avisos al usarlo: (1) el plazo de 30 días hábiles para formular "
                    "la glosa lo redujo a VEINTE el Art. 57 de la Ley 1438 de 2011, que es "
                    "posterior y prevalece; los 15 de respuesta y los 10 de decisión coinciden "
                    "en las dos normas. (2) Aquí está la prohibición de glosar dos veces la "
                    "misma factura salvo por hechos nuevos, que es la defensa contra una "
                    "ratificación que estrena causal."
                ),
                "keywords": [
                    "trámite de glosas",
                    "términos",
                    "20 días",
                    "15 días",
                    "10 días",
                    "hechos nuevos",
                    "ratificación",
                    "superintendencia",
                ],
            },
        },
        "articulos_completos": False,
        "verificada": "25-08-2026 contra el texto oficial de MinSalud",
        "keywords": ["glosa", "trámite de glosas", "soportes", "manual único", "4747"],
    },
    "DECRETO 780 DE 2016": {
        "nombre": "Decreto 780 de 2016 (Decreto Único Reglamentario Sector Salud)",
        "titulo": "Decreto Único Reglamentario del Sector Salud y Protección Social",
        "ambito": "Marco general reglamentario sector salud",
        "vigente": True,
        # 25-08-2026 — CORREGIDO CONTRA LA FUENTE. Este corpus tenía cargado un
        # artículo 2.5.3.4.1.1 titulado «Prohibición de auditoría previa como
        # barrera», con un texto que no existe. Verificado contra el Decreto
        # 441 de 2022 (que es el que agregó este capítulo al Decreto 780):
        # el 2.5.3.4.1.1 es el «Objeto» del capítulo.
        #
        # La prohibición SÍ es real, pero vive en otra parte: en el artículo 5
        # de la Resolución 2284 de 2023, que está más abajo en este archivo con
        # su texto literal. Es la que hay que citar.
        "articulos": {
            "2.5.3.4.1.1": {
                "titulo": "Objeto",
                "texto": (
                    "El presente capítulo tiene por objeto regular algunos aspectos "
                    "generales de los acuerdos de voluntades entre las entidades "
                    "responsables de pago y los prestadores de servicios de salud o "
                    "proveedores de tecnologías en salud, celebrados entre dos o más "
                    "personas naturales o jurídicas para la prestación o provisión de "
                    "servicios y tecnologías en salud, en sus etapas precontractual, "
                    "contractual y post contractual, y establecer mecanismos de "
                    "protección a los usuarios."
                ),
                "aplicacion": (
                    "Es el artículo de encabezado del capítulo. NO prohíbe la auditoría "
                    "previa: para eso es el artículo 5 de la Resolución 2284 de 2023."
                ),
                "keywords": ["acuerdos de voluntades", "objeto", "capítulo"],
            },
            "2.5.3.4.3.3": {
                "titulo": "Auditoría de cuentas médicas",
                "texto": (
                    "La auditoría de las cuentas médicas se realizará con base en los "
                    "soportes definidos en el artículo 2.5.3.4.4.1 del presente decreto, "
                    "con sujeción a los estándares establecidos en el Manual Único de "
                    "Devoluciones, Glosas y Respuestas expedido por el Ministerio de "
                    "Salud y Protección Social, conforme a los términos señalados en el "
                    "trámite de glosas establecido en el artículo 57 de la Ley 1438 de "
                    "2011, y de acuerdo con la información reportada y validada en el "
                    "Registro Individual de Prestaciones de Salud."
                ),
                "aplicacion": (
                    "Ata la auditoría de la entidad a TRES cosas: los soportes definidos "
                    "por norma, las causales del Manual Único y los plazos del Art. 57. "
                    "Sirve contra la entidad que glosa por fuera del manual, que exige "
                    "un soporte que la norma no pide, o que se pasa del término."
                ),
                "keywords": [
                    "auditoría de cuentas médicas",
                    "soportes",
                    "manual único",
                    "plazos",
                ],
            },
        },
        "articulos_completos": False,
        "verificada": "25-08-2026 contra el Decreto 441 de 2022 (norma que lo adicionó)",
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
                "titulo": "PRINCIPIOS Y CARACTERISTICAS",
                "texto": (
                    "Serán principios orientadores para la prestación del servicio de salud del "
                    "SSMP los siguientes: a) CALIDAD. Los servicios que presta el Sistema se "
                    "fundamentan en valores orientados a satisfacer las necesidades y "
                    "expectativas razonables de los usuarios de tal forma que los servicios se "
                    "presten de manera integral. b) ETICA. Es el conjunto de reglas encaminadas "
                    "a brindar servicios de salud integrales en un marco de respeto por la vida "
                    "y la dignidad humana sin ningún distingo. c) EFICIENCIA. Es la mejor "
                    "utilización social y económica de los recursos administrativos y "
                    "financieros disponibles para que los beneficios a que da derecho el Sistema "
                    "sean prestados en forma adecuada, oportuna y suficiente. d) UNIVERSALIDAD. "
                    "Es la garantía de la protección para todas las personas, sin ninguna "
                    "discriminación, en todas las etapas de la vida. e) SOLIDARIDAD. Es la "
                    "práctica de la mutua ayuda entre los Establecimientos de Sanidad de las "
                    "Fuerzas Militares y Policía Nacional bajo el principio del más fuerte hacia "
                    "el más débil. f) PROTECCION INTEGRAL. El SSMP brindará atención en salud "
                    "integral a sus afiliados y beneficiarios en sus fases de educación, "
                    "información y fomento de la salud, así como en los aspectos de prevención, "
                    "protección, diagnóstico, recuperación, rehabilitación, en los términos y "
                    "condiciones que se establezcan en el plan de Servicios de Sanidad Militar y "
                    "Policial, y atenderá todas las actividades que en materia de salud "
                    "operacional requieran las Fuerzas Militares y la Policía Nacional para el "
                    "cumplimiento de su misión. En el SSMP no existirán restricciones a los "
                    "servicios prestados a los afiliados y beneficiarios por concepto de "
                    "preexistencias. g) <Literal INEXEQUIBLE> h) EQUIDAD. El SSMP garantizará "
                    "servicios de salud de igual calidad a todos sus afiliados y beneficiarios, "
                    "independientemente de su ubicación geográfica, grado o condición de "
                    "uniformado o no uniformado, activo, retirado o pensionado. Serán "
                    "características propias del Sistema: a) AUTONOMIA. <Aparte tachado "
                    "INEXEQUIBLE> El SSMP es autónomo y se regirá de conformidad con lo "
                    "establecido en el presente Decreto. b) DESCENTRALIZACION Y "
                    "DESCONCENTRACION. El SSMP se administrará en forma descentralizada y "
                    "desconcentrada, con el fin de optimizar la utilización de los recursos, "
                    "obtener economías de escala y facilitar el acceso y la oportunidad de los "
                    "servicios de salud en las Fuerzas Militares y en la Policía Nacional. Esto "
                    "con sujeción a las políticas, reglas, directrices y orientaciones trazadas "
                    "por el Consejo Superior de Salud de las Fuerzas Militares y de la Policía "
                    "Nacional. c) INTEGRACION FUNCIONAL. La Dirección General de Sanidad "
                    "Militar, la Dirección de Sanidad de la Policía Nacional, las Direcciones de "
                    "Sanidad de las Fuerzas, los Establecimientos de Sanidad Militar y Policial, "
                    "y el Hospital Militar Central, concurrirán armónicamente a la prestación de "
                    "los servicios de salud, mediante la integración en sus funciones, acciones "
                    "y recursos, de acuerdo con la regulación que para el efecto adopte el "
                    "Consejo Superior de Salud de las Fuerzas Militares y de la Policía "
                    "Nacional. d) INDEPENDENCIA DE LOS RECURSOS. Los recursos que reciban las "
                    "Fuerzas Militares y la Policía Nacional para la salud, deberán manejarse en "
                    "fondos cuenta separados e independientes del resto de su presupuesto y sólo "
                    "podrán destinarse a la ejecución de dichas funciones. e) ATENCION "
                    "EQUITATIVA Y PREFERENCIAL. <Aparte tachado INEXEQUIBLE> En todos los "
                    "niveles del SSMP se deberán atender equitativa y prioritariamente a los "
                    "afiliados y beneficiarios del mismo. Por consiguiente, solamente podrán "
                    "ofrecer servicios a terceros o a entidades promotoras de salud, una vez "
                    "hayan sido satisfechas debidamente las necesidades de tales usuarios. f) "
                    "RACIONALIDAD. El SSMP utilizará los recursos de manera racional a fin de "
                    "que los servicios sean eficaces, eficientes y equitativos. g) UNIDAD. El "
                    "SSMP tendrá unidad de gestión, de tal forma que aunque la prestación de "
                    "servicios se realice en forma desconcentrada o contratada, siempre que "
                    "exista unidad de dirección y políticas así como la debida coordinación "
                    "entre los Subsistemas y entre las entidades y Establecimientos de Sanidad "
                    "de cada uno de ellos. "
                ),
                "aplicacion": (
                    "Verifiqué yo mismo el Decreto 1795 de 2000 en el normograma de la "
                    "Supersalud (HTTP 200, 148 KB; encabezado «DECRETO 1795 DE 2000 (septiembre "
                    "14) — Diario Oficial 44.161 — MINISTERIO DE DEFENSA NACIONAL») y NO pude "
                    "refutar al otro revisor: tiene razón en todo. (a) El artículo 6 sí existe. "
                    "(b) Su epígrafe real es «PRINCIPIOS Y CARACTERISTICAS»; el título guardado "
                    "«Cobertura» no corresponde — la pala "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
        "keywords": ["FF.MM.", "policía", "sanidad militar"],
    },
    "DECRETO 2423 DE 1996": {
        "nombre": "Decreto 2423 de 1996",
        "titulo": "Manual de Tarifas SOAT",
        "ambito": "Tarifas SOAT — marco histórico",
        "vigente": True,
        "verificada": "24-08-2026 art. 87 (ver la entrada de ese día)",
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
        # Corregido el 25-08-2026. El sistema lo daba como "reglamento del
        # aseguramiento — flujo de recursos del SGSSS". La primera mitad es
        # cierta (si es norma de aseguramiento), la segunda no: no trata del
        # flujo de recursos, y citarlo asi ante una EPS es peligroso.
        "nombre": "Decreto 064 del 20 de enero de 2020",
        "titulo": "Afiliacion al regimen subsidiado y afiliacion de oficio",
        "ambito": "Afiliacion — modifica y adiciona articulos del Decreto 780 de 2016",
        "vigente": True,
        "notas": (
            "Modifica los articulos 2.1.3.11, 2.1.3.13, 2.1.5.1, 2.1.7.7, 2.1.7.8 y "
            "2.1.3.17 y adiciona los 2.1.5.4 y 2.1.5.5 del Decreto 780 de 2016, sobre "
            "afiliados al regimen subsidiado y afiliacion de oficio. NO es norma de flujo "
            "de recursos."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["afiliacion de oficio", "regimen subsidiado", "Decreto 780 de 2016"],
    },
    # Ronda 14 (Bug P): normas reales que el verifier marcaba como
    # inexistentes en producción.
    "DECRETO 2493 DE 2004": {
        "nombre": "Decreto 2493 de 2004 (MinProtección Social)",
        "titulo": "Régimen general de obtención, donación, preservación y trasplante de componentes anatómicos",
        "ambito": "Trasplantes — atención del donante y receptor",
        "vigente": True,
        "articulos": {},
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
                "titulo": "REQUERIMIENTOS GENERALES PARA LOS EQUIPOS BIOMÉDICOS DE TECNOLOGÍA CONTROLADA",
                "texto": (
                    "Sin perjuicio de lo dispuesto en los artículos precedentes, cuando se trate "
                    "de equipos biomédicos de tecnología controlada, se deberán tener en cuenta "
                    "los siguientes requisitos: a) Las personas naturales o jurídicas que "
                    "adquieran equipos biomédicos deberán contar en todo momento, con los "
                    "manuales de operación, funcionamiento y mantenimiento, los cuales serán "
                    "provistos en forma obligatoria por el distribuidor en el momento de la "
                    "entrega del equipo; b) El titular o importador del equipo biomédico deberá "
                    "garantizar, la capacidad de ofrecer servicio de soporte técnico permanente "
                    "durante la vida útil del mismo, así como los repuestos y herramientas "
                    "necesarias para el mantenimiento y calibración que permita conservar los "
                    "equipos en los rangos de seguridad establecidos inicialmente por el "
                    "fabricante; c) Las empresas productoras de equipos biomédicos, sus "
                    "representantes en el país y titulares de permiso de comercialización, "
                    "deberán contar con responsables técnicos, con título universitario y/o "
                    "especialización en el área específica para los procesos de adquisición, "
                    "instalación y mantenimiento de este tipo de tecnología; d) Los productos "
                    "deberán diseñarse, fabricarse y acondicionarse de forma tal, que sus "
                    "características y funciones según la utilización prevista, no se vean "
                    "alteradas durante el almacenamiento y transporte, teniendo en cuenta las "
                    "instrucciones y datos facilitados por el fabricante. --- Artículos que el "
                    "corpus confundió con el 35 (texto literal, para guardarlos aparte) --- "
                    "ARTÍCULO 31. VIGENCIA DE LOS REGISTROS SANITARIOS Y PERMISOS DE "
                    "COMERCIALIZACIÓN. Los registros sanitarios y permisos de comercialización, "
                    "tendrán una vigencia de diez (10) años contados a partir de la expedición "
                    "del acto administrativo correspondiente. El titular de dichos registros o "
                    "permisos podrá solicitar su cancelación en cualquier momento. ARTÍCULO 32. "
                    "DE LAS RENOVACIONES DE LOS REGISTROS SANITARIOS Y PERMISOS DE "
                    "COMERCIALIZACIÓN. Las renovaciones de los registros sanitarios y permisos "
                    "de comercialización se realizarán siguiendo el mismo procedimiento de su "
                    "expedición en lo que hace referencia a las evaluaciones técnica y legal. "
                    "Para las mismas, se podrá realizar análisis de control de calidad y "
                    "evaluación del proceso de elaboración, cuando sea del caso y del "
                    "cumplimiento de Buenas Prácticas de Manufactura para Dispositivos Médicos, "
                    "BPM, vigentes. Los registros sanitarios y permisos de comercialización de "
                    "que trata el presente decreto se renovarán bajo el mismo número que tenía "
                    "inicialmente pero seguida de la letra R, adicionada con el número 1, 2 y "
                    "así sucesivamente. La solicitud de renovación deberá radicarse ante el "
                    "Instituto Nacional de Vigilancia de Medicamentos y Alimentos, Invima, con "
                    "tres (3) meses de anterioridad al vencimiento del respectivo registro "
                    "sanitario o permiso de comercialización. Toda solicitud de renovación de un "
                    "registro sanitario o permiso de comercialización que no sea presentada en "
                    "el término previsto, se tramitará como nueva solicitud. PARÁGRAFO 1o. Si se "
                    "hubiere vencido el respectivo registro sanitario o permiso de "
                    "comercialización sin que se presente la solicitud de renovación, se "
                    "abandone la solicitud o se desista de ella o no se hubiere presentado la "
                    "solicitud en el término aquí previsto, el correspondiente producto no podrá "
                    "importarse al país, ni fabricarse, según el caso. Si hay existencias en el "
                    "mercado, el Instituto Nacional de Vigilancia de Medicamentos y Alimentos, "
                    "Invima, dará a los interesados un plazo para disponer de ellas, el cual no "
                    "podrá ser superior a seis (6) meses. Si transcurrido este plazo, existen "
                    "productos en el mercado, el Instituto Nacional de Vigilancia de "
                    "Medicamentos y Alimentos, Invima, ordenará su decomiso conforme a lo "
                    "dispuesto en el presente decreto. PARÁGRAFO 2o. Si la información "
                    "científica que reposa en el expediente no ha cambiado y continúa vigente en "
                    "el momento de solicitar la renovación, no se deberá anexar nuevamente, y en "
                    "su lugar, el titular allegará una declaración en tal sentido. "
                ),
                "aplicacion": (
                    "Descargué y verifiqué el texto oficial compilado del Decreto 4725 de 2005 "
                    "en el Normograma de la Superintendencia Nacional de Salud (fuente de primer "
                    "orden). El otro revisor tiene razón; no pude refutarlo: (a) EXISTE el "
                    "artículo 35, dentro del CAPÍTULO VII «DISPOSICIONES COMUNES A LOS CAPÍTULOS "
                    "ANTERIORES». (b) El EPÍGRAFE guardado («Vigencia y renovación del registro "
                    "sanitario») es FALSO. El epí "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
    "RESOLUCION 506 DE 2021": {
        # Cargada el 25-08-2026. El motor la ofrecia en el prompt como
        # "Resolucion 506/2021 DIAN" y no estaba en el corpus, asi que citarla
        # producia una alarma roja de "norma inexistente". Verificada contra
        # fuente oficial: NO es de la DIAN, la expidio el Ministerio de Salud
        # el 19 de abril de 2021, y ya no rige.
        "nombre": "Resolucion 506 de 2021 (MinSalud)",
        "titulo": "Campos de datos adicionales del sector salud en la factura electronica",
        "ambito": "Factura electronica en salud — campos adicionales del sector",
        "vigente": False,
        "derogada_por": (
            "figura como no vigente; para la factura electronica en salud rige hoy la "
            "Res. 948 de 2026"
        ),
        "notas": (
            "Adopto el anexo tecnico de campos de datos adicionales del sector salud en "
            "la factura electronica de venta. Solo aplica a servicios facturados mientras "
            "estuvo vigente."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["factura electronica", "FEV", "campos del sector salud", "MinSalud"],
    },
    # ── Cargadas el 25-08-2026 ──────────────────────────────────────────
    # Los prompts del motor ya le ofrecian estas normas a la IA, pero no
    # estaban en el corpus con que se revisan las citas. Resultado: la IA las
    # citaba (porque se lo pedimos) y el revisor las marcaba en rojo como
    # "norma inexistente" sobre un dictamen que podia estar bien. Verificadas
    # una por una contra fuente oficial antes de cargarlas.
    "RESOLUCION 1403 DE 2007": {
        "nombre": "Resolucion 1403 de 2007 (Ministerio de la Proteccion Social)",
        "titulo": "Modelo de Gestion del Servicio Farmaceutico",
        "ambito": "Glosas de medicamentos y dispositivos medicos",
        "vigente": True,
        "notas": (
            "Fija como debe hacerse la prescripcion, la dispensacion y el registro de "
            "medicamentos. Sirve para defender glosas de medicamentos por supuestos defectos de "
            "formula o de entrega."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["servicio farmaceutico", "medicamentos", "prescripcion", "dispensacion"],
    },
    "RESOLUCION 3539 DE 2019": {
        "nombre": "Resolucion 3539 de 2019 (MinSalud)",
        "titulo": "Reporte de servicios negados por las EPS",
        "ambito": "Solo para el tema de negacion de servicios",
        "vigente": False,
        "derogada_por": (
            "figura como no vigente; verificar la norma que la reemplazo antes de citarla"
        ),
        "notas": (
            "Obliga a la EPS a registrar y reportar al Ministerio los servicios que niega. NO es "
            "una norma de habilitacion, como decia el catalogo del motor."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["servicios negados", "reporte", "EPS"],
    },
    "RESOLUCION 2284 DE 2023": {
        "nombre": "Resolución 2284 de 2023 (MinSalud)",
        "titulo": "Manual Único de Devoluciones, Glosas y Respuestas",
        "ambito": "Norma maestra vigente — CÓDIGOS TAXATIVOS de glosas",
        "vigente": True,
        # 25-08-2026: se carga el artículo 5 con su texto literal. Es el que de
        # verdad prohíbe exigir auditoría previa para radicar — el corpus se lo
        # atribuía al Decreto 780, con un texto inventado.
        "articulos": {
            "5": {
                "titulo": "Auditoría de cuentas médicas",
                "texto": (
                    "De conformidad con lo establecido en el artículo 2.5.3.4.3.3 del "
                    "Decreto número 780 de 2016, las entidades responsables de pago no "
                    "podrán exigir que, para radicar las facturas de venta en salud, se "
                    "haya surtido un proceso de auditoría previo o paso por mallas "
                    "validadoras propias ni el envío previo de la factura, actuaciones "
                    "que se consideran prácticas dilatorias no autorizadas. Corresponde "
                    "a las entidades responsables de pago adelantar la auditoría de las "
                    "cuentas médicas."
                ),
                "aplicacion": (
                    "ESTE es el artículo contra la entidad que condiciona la radicación "
                    "a pasar antes por su malla o su auditoría: la norma llama a eso "
                    "«práctica dilatoria no autorizada». Se cita por su nombre —Art. 5 "
                    "de la Res. 2284 de 2023—, no como artículo del Decreto 780."
                ),
                "keywords": [
                    "auditoría previa",
                    "radicación",
                    "mallas validadoras",
                    "prácticas dilatorias",
                ],
            },
        },
        "articulos_completos": False,
        "verificada": "25-08-2026 contra el texto oficial (normograma SuperSalud)",
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
                "titulo": "DE LAS PRESCRIPCIONES EN EL ÁMBITO DE ATENCIÓN HOSPITALARIA",
                "texto": (
                    "Cuando el profesional de la salud se encuentre prescribiendo tecnologías en "
                    "salud no financiadas con recursos de la UPC o servicios complementarios, en "
                    "el ámbito hospitalario de atención, ya sea internación, domiciliario o "
                    "urgencias deberá tener en cuenta lo siguiente: 1. En casos de urgencia "
                    "vital, la prescripción de tecnologías no financiadas con recursos de la UPC "
                    "o servicios complementarios podrá efectuarse en la herramienta tecnológica "
                    "dispuesta por este Ministerio de forma posterior a la prestación de los "
                    "servicios durante las doce (12) horas siguientes a la atención y hasta el "
                    "momento del egreso del paciente. 2. En caso de servicios hospitalarios con "
                    "internación en institución o domiciliaria, la prescripción se podrá "
                    "registrar en la herramienta tecnológica, durante la internación y hasta la "
                    "fecha del egreso. En caso de que se presenten excedentes en cuanto a las "
                    "cantidades prescritas por el profesional de la salud, la evidencia de "
                    "entrega para efectos del recobro/cobro ante la ADRES, se realizará contra "
                    "lo efectivamente suministrado y facturado. 3. Sin perjuicio de lo "
                    "establecido en el numeral anterior del presente artículo, el profesional de "
                    "la salud deberá conforme a la normatividad vigente registrar en la historia "
                    "clínica, el plan de tratamiento de forma habitual, y prescribirá en el "
                    "ordenamiento médico diario el manejo que se requiera realizar. 4. Cuando se "
                    "trate de prescripciones para el egreso hospitalario, se debe tener en "
                    "cuenta lo siguiente: i) si corresponde a prescripciones necesarias para "
                    "garantizar la continuidad del tratamiento posterior al egreso hospitalario, "
                    "el profesional de la salud deberá seleccionar el ámbito ambulatorio "
                    "priorizado en la herramienta tecnológica de que trata la presente "
                    "Resolución, y podrá generar la solicitud hasta por un mes de tratamiento; "
                    "ii) si un usuario requiere continuar tratamiento en hospitalización "
                    "domiciliaria, el profesional de la salud tratante de la IPS que efectúa el "
                    "egreso deberá seleccionar el ámbito de atención hospitalario - domiciliario "
                    "para generar el plan de manejo de las tecnologías no financiadas con "
                    "recursos de la UPC o servicios complementarios, en la herramienta "
                    "tecnológica dispuesta para tal fin; iii) Cuando se requiera ajustar o "
                    "cambiar el plan de manejo en el ámbito de atención domiciliaria, "
                    "corresponderá a los profesionales de la salud de la IPS domiciliaria, la "
                    "prescripción en la herramienta tecnológica. 5. Cuando la IPS no haga parte "
                    "de la red de prestadores de la EPS o EOC y se requiera atención de "
                    "urgencias e incluso posterior a ello, se defina la hospitalización del "
                    "usuario, se podrá utilizar el ámbito de atención de urgencias desde el "
                    "ingreso hasta el egreso hospitalario, siempre y cuando se informe y sea "
                    "autorizado por la EPS o EOC tal condición, en los términos estipulados para "
                    "dicho reporte, so pena de incurrir en omisión a la obligación de reportar "
                    "la información. [NOTA DE VIGENCIA: Resolución derogada por el artículo 53 "
                    "de la Resolución 740 de 2024] "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: el otro revisor tiene razón "
                    "(AMBOS_MAL). Descargué el texto oficial completo de la Resolución 1885 de "
                    "2018 del Normograma de la SuperSalud y lo verifiqué línea por línea. (a) "
                    "EXISTE: el artículo 14 sí existe en la Resolución 1885 de 2018. (b) "
                    "EPÍGRAFE GUARDADO: FALSO. El corpus dice «Vigencia de la prescripción "
                    "MIPRES». El epígrafe real, literal, es «DE LAS "
                ),
                "keywords": [],
            },
            "art_22": {
                "titulo": "RESPONSABILIDAD DE LA IPS",
                "texto": (
                    "<Resolución derogada por el artículo 53 de la Resolución 740 de 2024> Las "
                    "IPS deben conformar la Junta de Profesionales de la Salud de acuerdo con la "
                    "obligatoriedad establecida en la presente Resolución, les corresponderá: 1. "
                    "Disponer de los mecanismos necesarios para garantizar el funcionamiento de "
                    "la Junta de Profesiones de la Salud, de conformidad con los integrantes "
                    "establecidos en la presente Resolución, para dar la respuesta, en cada "
                    "caso, en los tiempos previstos en la garantía del suministro establecida en "
                    "esta resolución. 2. Reportar oportunamente la decisión adoptada por la "
                    "Junta de Profesionales de la Salud en la herramienta tecnológica que el "
                    "Ministerio de Salud y Protección dispone para ello, en los tiempos "
                    "previstos en el presente acto administrativo so pena de las sanciones a que "
                    "haya lugar por no realizarlo. 3. Garantizar que bajo ninguna circunstancia "
                    "el personal administrativo de las Instituciones Prestadoras de Salud (IPS), "
                    "hagan parte de Juntas, así sean profesionales de la salud. 4. Instaurar "
                    "mecanismos para evitar que los miembros de las Juntas de Profesionales de "
                    "la Salud reciban reconocimientos en especie o económicos de compañías "
                    "productoras y distribuidoras de tecnologías en salud. "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y NO pude: la fuente oficial le da la razón al "
                    "otro revisor. Descargué la compilación oficial de la Resolución 1885 de "
                    "2018 MSPS del Normograma de la Superintendencia Nacional de Salud (281 KB "
                    "de HTML, texto completo con notas de vigencia) y busqué el artículo 22. (a) "
                    "El artículo 22 EXISTE. (b) Su epígrafe real es «RESPONSABILIDAD DE LA IPS», "
                    "no «MIPRES en eventos espec "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
        "keywords": ["Resolución 1885", "MIPRES", "no PBS", "prescripción"],
    },
    "RESOLUCION 1885 DE 2024": {
        "nombre": "Resolución 1885 de 2024 (MinSalud)",
        "titulo": "Cronograma gradual implementación Manual Único",
        "ambito": "Implementación Res. 2284/2023 por complejidad",
        "vigente": True,
        "articulos": {
            "cronograma": {
                "titulo": "(modifica el artículo 12 «Transitoriedad» de la Resolución 2284 de 2023)",
                "texto": (
                    "ARTÍCULO 1o. Modifíquese el artículo 12 de la Resolución número 2284 de "
                    "2023, modificado por el artículo 1o de la Resolución número 627 de 2024, el "
                    "cual quedará así: 'Artículo 12. Transitoriedad. Las entidades responsables "
                    "de pago, los prestadores de servicios de salud y los proveedores de "
                    "tecnologías en salud, deberán implementar las disposiciones establecidas en "
                    "la presente resolución, de acuerdo con el siguiente cronograma y "
                    "clasificación de las entidades, así: Tipo de entidad / Fecha de inicio "
                    "Grupo 1: Prestadores de Servicios de Salud con servicios de alta "
                    "complejidad habilitados y activos en REPS al 2 de septiembre de 2024 según "
                    "el listado dispuesto por el Ministerio en el micrositio de FEV-RIPS en el "
                    "siguiente enlace "
                    "https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/OT/listado-pss-reps-2024.zip "
                    "y las Entidades Responsables de Pago — 1o de febrero de 2025 Grupo 2: "
                    "Prestadores de Servicios de Salud con servicios de mediana complejidad "
                    "habilitados y activos en REPS al 2 de septiembre de 2024 según el listado "
                    "dispuesto por el Ministerio en el micrositio de FEV-RIPS en el siguiente "
                    "enlace "
                    "https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/OT/listado-pss-reps-2024.zip "
                    "— 1o de abril de 2025 Grupo 3: Prestadores de Servicios de Salud con "
                    "servicios de baja complejidad, profesionales independientes no obligados a "
                    "FEV en salud y entidades con objeto social diferente habilitados y activos "
                    "en REPS al 2 de septiembre de 2024 según el listado dispuesto por el "
                    "Ministerio en el micrositio de FEV-RIPS en el siguiente enlace "
                    "https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/OT/listado-pss-reps-2024.zip "
                    "y los Proveedores de Tecnologías en Salud en el marco del Decreto número "
                    "441 de 2022 incorporado en el Decreto número 780 de 2016 — 1o de junio de "
                    "2025 Los servicios y tecnologías en salud, prestados o suministrados antes "
                    "de la fecha de inicio establecida para cada uno de los grupos definidos en "
                    "el presente artículo, dispondrán hasta el 31 de diciembre de 2025 para "
                    "atender las disposiciones contenidas en la Resolución 3047 de 2008 y sus "
                    "modificatorias, la Resolución 416 de 2009 y la Resolución 4331 de 2012, así "
                    "como la Resolución 3253 de 2009, y para los procesos de auditoría deberán "
                    "aplacarse [sic, en el texto publicado] los términos del artículo 57 de la "
                    "Ley 1438 de 2011.' "
                ),
                "aplicacion": (
                    "Fui yo mismo a la fuente oficial y NO pude refutar el hallazgo: el corpus "
                    "está mal en los tres puntos señalados. (1) «cronograma» no es un artículo. "
                    "La Resolución 00001885 de 2024 (30 de septiembre de 2024, Diario Oficial "
                    "No. 52.896 del 1 de octubre de 2024) tiene únicamente tres artículos: 1o, "
                    "2o y 3o. El cronograma está dentro del ARTÍCULO 1o, que sustituye el "
                    "artículo 12 de la Resolución 2284 "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
        "keywords": ["cronograma", "implementación", "2025"],
    },
    "RESOLUCION 2275 DE 2023": {
        "nombre": "Resolución 2275 de 2023 (MinSalud)",
        "titulo": "Factura Electrónica de Venta en Salud (FEV) + RIPS",
        "ambito": "Facturación electrónica — validación previa MinSalud",
        # DEROGADA (verificado el 24-08-2026 en el PDF oficial del Ministerio).
        # El sistema la daba por vigente y la citaba en seis sitios distintos
        # como fundamento de facturación electrónica. La derogó la Resolución
        # 948 del 14 de mayo de 2026, que rige desde su expedición. Un dictamen
        # radicado hoy que se apoye en ella le entrega a la EPS la forma de
        # desmontar el argumento: basta con mostrar la derogatoria.
        #
        # NO se borra del corpus: para servicios prestados antes del 14-05-2026
        # sigue siendo la norma aplicable, y hay que poder citarla bien.
        "vigente": False,
        "derogada_por": (
            "la derogó la Resolución 948 del 14 de mayo de 2026, que rige desde su "
            "expedición (junto con las Resoluciones 558 y 1884 de 2024)"
        ),
        "keywords": ["FEV", "RIPS", "factura electrónica", "validación", "derogada"],
    },
    "RESOLUCION 948 DE 2026": {
        # Agregada el 24-08-2026, transcrita del PDF oficial del Ministerio de
        # Salud (resolucion-0948-de-2026.pdf, 17 páginas). Es la que rige hoy
        # para RIPS y factura electrónica; el sistema no la tenía y seguía
        # citando la derogada.
        "nombre": "Resolución 948 del 14 de mayo de 2026 (MinSalud)",
        "titulo": "RIPS como soporte de la Factura Electrónica de Venta en salud",
        "ambito": "Facturación electrónica y RIPS — norma vigente desde el 14-05-2026",
        "vigente": True,
        "notas": (
            "Artículo 1: reglamenta el Registro Individual de Prestación de Servicios "
            "de Salud (RIPS) como soporte de la Factura Electrónica de Venta (FEV) en "
            "salud y adopta los documentos técnicos. Su artículo de vigencia dice que "
            "rige a partir de su expedición y deroga las Resoluciones 2275 de 2023 y "
            "558 y 1884 de 2024. OJO CON LA FECHA DEL SERVICIO: para lo prestado antes "
            "del 14 de mayo de 2026 la norma aplicable sigue siendo la Res. 2275/2023."
        ),
        "verificada": "24-08-2026 PDF oficial MinSalud",
        "keywords": [
            "RIPS",
            "FEV",
            "factura electrónica",
            "soporte de cobro",
            "948 de 2026",
        ],
    },
    "RESOLUCION 3047 DE 2008": {
        # DEROGADA — corregido el 27-08-2026 contra el texto oficial.
        #
        # El corpus la daba como «vigente: True» con la nota «sigue vigente
        # como referente histórico y para casos en transición». Eso hacía que
        # el revisor de citas la aprobara, y un dictamen real del 27-08 fundó
        # TODA su defensa de soportes en su Anexo Técnico 5, citándola seis
        # veces. Ese dictamen es tumbable de entrada.
        #
        # La derogatoria es expresa y está fechada. Texto literal del Art. 20
        # de la Resolución 2335 de 2023, tal como quedó tras su modificación:
        #
        #   «ARTÍCULO 20. DEROGATORIAS. <Artículo modificado por el artículo 2
        #    de la Resolución 1886 de 2024. El nuevo texto es el siguiente:>
        #    El presente acto administrativo deroga la Resolución número 3047
        #    de 2008 y sus modificatorias, la Resolución número 416 de 2009 y
        #    la Resolución número 4331 de 2012, así como la Resolución número
        #    3253 de 2009; a partir del 1 de abril de 2026.»
        #
        # Se descargó del normograma de la Superintendencia Nacional de Salud
        # (resolucion_minsaludps_2335_2023.htm) el 27-08-2026.
        #
        # OJO CON LAS FECHAS, que aquí es donde se decide: para un servicio
        # prestado ANTES del 1 de abril de 2026 la 3047 sí era la norma
        # aplicable y citarla es correcto. Para uno posterior, no. Por eso no
        # se borra del corpus: se marca, con la fecha desde la que dejó de
        # regir, y el motor escoge según la fecha de la atención.
        "nombre": "Resolución 3047 de 2008",
        "titulo": "Formatos y procedimientos entre prestadores y pagadores (DEROGADA)",
        "ambito": "Aplicable solo a servicios prestados antes del 1 de abril de 2026",
        "vigente": False,
        "derogada_por": (
            "Resolución 2335 de 2023, artículo 20 (modificado por el artículo 2 de la "
            "Resolución 1886 de 2024), que la deroga expresamente A PARTIR DEL 1 DE "
            "ABRIL DE 2026 junto con la Res. 416 de 2009, la Res. 4331 de 2012 y la "
            "Res. 3253 de 2009. Para los soportes de cobro rige hoy el Anexo Técnico 1 "
            "de la Res. 2284 de 2023, sustituido por el Anexo 1 de la Res. 1885 de 2024; "
            "para las causales de glosa, el Anexo Técnico 3 de la Res. 2284 de 2023"
        ),
        "notas": (
            "Definía los formatos, mecanismos de envío, procedimientos y términos entre "
            "prestadores y entidades responsables de pago. NO citarla para servicios "
            "prestados desde el 1 de abril de 2026: la entidad tumba el escrito sin "
            "discutir el fondo. Su Anexo Técnico 5 (soportes) y su Anexo Técnico 6 "
            "(catálogo de glosas) ya no son la fuente aplicable."
        ),
        "verificada": "27-08-2026 fuente oficial (normograma Supersalud, Res. 2335/2023 art. 20)",
        "keywords": ["3047", "anexo técnico 5", "anexo técnico 6", "glosa", "derogada"],
    },
    # 27-08-2026 — CARGADA PORQUE EL MOTOR LA DABA POR INVENTADA.
    # El dictamen GL-135 la citó y el revisor la marcó NORMA_INEXISTENTE en
    # severidad ALTA. Existe: se descargó del normograma oficial de la
    # Supersalud y es conjunta de MinSalud y MinCultura. Y es pertinente —
    # modifica justamente la Res. 1995 de 1999, que es la que el motor usa
    # para la historia clínica. Los textos de abajo son literales de esa
    # descarga.
    # FUENTE VERIFICADA: normograma.supersalud.gov.co, resolucion_minsaludps_0839_2017
    "RESOLUCION 839 DE 2017": {
        "nombre": "Resolución 839 de 2017 (MinSalud y MinCultura)",
        "titulo": "Manejo, custodia y conservación de la historia clínica",
        "ambito": (
            "Modifica la Resolución 1995 de 1999. Fija cuánto tiempo debe "
            "guardarse la historia clínica y qué pasa con ella si la entidad se "
            "liquida."
        ),
        "vigente": True,
        "verificada": (
            "normograma.supersalud.gov.co — resolucion_minsaludps_0839_2017 "
            "(descargado y transcrito el 27-08-2026)"
        ),
        "articulos": {
            "1": {
                "titulo": "Objeto",
                "texto": (
                    "La presente resolución tiene por objeto establecer el manejo, "
                    "custodia, tiempo de retención, conservación y disposición final "
                    "de los expedientes de las historias clínicas, así como "
                    "reglamentar el procedimiento que deben adelantar las entidades "
                    "del SGSSS, para el manejo de estas en caso de liquidación."
                ),
            },
            "3": {
                "titulo": (
                    "Retención y tiempos de conservación documental del expediente "
                    "de la historia clínica"
                ),
                "texto": (
                    "La historia clínica debe retenerse y conservarse por el "
                    "responsable de su custodia, por un periodo mínimo de quince (15) "
                    "años, contados a partir de la fecha de la última atención. Los "
                    "cinco (5) primeros años dicha retención y conservación se hará en "
                    "el archivo de gestión y los diez (10) años siguientes en el "
                    "archivo central."
                ),
                "aplicacion": (
                    "Sirve para responder a la entidad que pide un soporte de una "
                    "atención antigua: si está dentro de los 15 años, el hospital debe "
                    "tenerlo y puede aportarlo; si la entidad exige uno de antes, esa "
                    "exigencia no tiene respaldo normativo."
                ),
            },
        },
        "keywords": [
            "839",
            "historia clínica",
            "custodia",
            "retención",
            "conservación",
            "liquidación",
            "archivo",
        ],
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
        # 25-08-2026: arts. 1 y 3 contrastados contra el PDF oficial de
        # MinSalud. Los dos coinciden literalmente. Esta norma estaba bien.
        "verificada": "25-08-2026 arts. 1 y 3 contra el PDF oficial de MinSalud — sin hallazgos",
        "keywords": ["historia clínica", "1995", "documento médico-legal"],
    },
    "RESOLUCION 866 DE 2021": {
        # Corregida el 25-08-2026. El sistema la daba como "los RIPS" y la
        # ofrecia para refutar glosas de soportes. No es eso: reglamenta los
        # datos clinicos para la INTEROPERABILIDAD DE LA HISTORIA CLINICA
        # (desarrolla la Ley 2015 de 2020). Citarla como norma de RIPS ante una
        # EPS es entregarle el argumento de que el prestador no sabe que cita.
        "nombre": "Resolucion 866 de 2021 (MinSalud)",
        "titulo": "Datos clinicos para la interoperabilidad de la historia clinica",
        "ambito": "Historia clinica electronica interoperable — Ley 2015 de 2020",
        "vigente": True,
        "notas": (
            "Define el conjunto de elementos de datos clinicos relevantes que deben "
            "poder intercambiarse entre prestadores. NO es la norma de RIPS: la de RIPS "
            "como soporte de la factura electronica es hoy la Res. 948 de 2026."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": [
            "interoperabilidad",
            "historia clinica electronica",
            "datos clinicos",
            "Ley 2015 de 2020",
        ],
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
        # DEROGADA (verificado el 25-08-2026 en el PDF oficial del Ministerio).
        # La derogó el artículo 12 de la Resolución 1099 de 2026: «rige a partir
        # de la fecha de su expedición y deroga las Resoluciones 5159 de 2015 y
        # 3595 de 2016». El motor la tenía como vigente en dos sitios y el
        # prompt ordenaba «citar SIEMPRE Res. 5159/2015» al defender PPL, que es
        # uno de los pagadores reales del hospital.
        #
        # NO se borra: para atenciones prestadas antes de junio de 2026 sigue
        # siendo la norma aplicable, y hay que poder citarla bien.
        "nombre": "Resolución 5159 del 30 de noviembre de 2015 (MinSalud)",
        "titulo": "Modelo de atención en salud para la población privada de la libertad",
        "ambito": "PPL — atenciones prestadas antes de junio de 2026",
        "vigente": False,
        "derogada_por": (
            "la derogó el artículo 12 de la Resolución 1099 de 2026, que rige desde su "
            "expedición (junto con la Resolución 3595 de 2016)"
        ),
        "verificada": "25-08-2026 PDF oficial MinSalud",
        "keywords": ["PPL", "reclusos", "INPEC", "5159"],
    },
    "RESOLUCION 1099 DE 2026": {
        # Cargada el 25-08-2026, transcrita del PDF oficial del Ministerio
        # (9 páginas). Es la que rige hoy para la atención en salud de la
        # población privada de la libertad, y el sistema no la tenía.
        "nombre": "Resolución 1099 de 2026 (MinSalud)",
        "titulo": "Modelo de atención en salud para la población privada de la libertad",
        "ambito": "PPL — norma vigente desde junio de 2026",
        "vigente": True,
        "notas": (
            "Adopta el modelo de atención en salud para la población privada de la "
            "libertad bajo custodia, inspección y vigilancia del INPEC. Su artículo 12 "
            "dice que rige desde su expedición y deroga las Resoluciones 5159 de 2015 y "
            "3595 de 2016. OJO CON LA FECHA DE LA ATENCIÓN: para lo prestado antes de "
            "junio de 2026 la norma aplicable sigue siendo la Res. 5159 de 2015. La "
            "Ley 1709 de 2014 es el respaldo legal de fondo en los dos casos."
        ),
        "verificada": "25-08-2026 PDF oficial MinSalud",
        "keywords": ["PPL", "INPEC", "modelo de atención", "1099 de 2026"],
    },
    # Ronda 48: Resolución 2641 de 2025 — Clasificación CUPS y tabla de
    # homologación oficial entre códigos internos de prestadores y la
    # numeración vigente (CUPS 2025).
    "RESOLUCION 2641 DE 2024": {
        # Corregida el 25-08-2026, DOBLE ERROR. El sistema la guardaba como
        # "Resolucion 2641 de 2025 — CUPS version vigente", y ni el ano ni la
        # vigencia eran ciertos:
        #   · No existe una "Resolucion 2641 de 2025". La real es de 2024,
        #     expedida el 23 de diciembre de 2024 (al sector se le dice "CUPS
        #     2025" porque rigio desde el 1 de enero de 2025).
        #   · Y ya no rige: la derogo la Resolucion 2706 de 2025 desde el
        #     1 de enero de 2026.
        #
        # Peor todavia: el motor tenia un limpiador que BORRABA del dictamen la
        # cita "Resolucion 2641 de 2024" por considerarla inventada, y la
        # cambiaba por la frase vaga "la normativa vigente del Ministerio de
        # Salud". O sea que borraba la cita CORRECTA y dejaba una pseudo-norma.
        # Ese limpiador se retiro en el mismo cambio.
        "nombre": "Resolucion 2641 del 23 de diciembre de 2024 (MinSalud)",
        "titulo": "Clasificacion Unica de Procedimientos en Salud (CUPS) — vigencia 2025",
        "ambito": "CUPS aplicable a servicios prestados durante 2025",
        "vigente": False,
        "derogada_por": (
            "la derogo la Resolucion 2706 de 2025 (23 de diciembre de 2025) a partir del "
            "1 de enero de 2026, junto con las Resoluciones 2689 de 2024 y 756 de 2025"
        ),
        "notas": (
            "Reemplazo a la Resolucion 2336 de 2023. OJO CON LA FECHA DEL SERVICIO: para "
            "lo prestado durante 2025 esta es la CUPS aplicable; para 2026 en adelante, "
            "la Res. 2706 de 2025."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["CUPS", "procedimientos en salud", "2641 de 2024", "vigencia 2025"],
    },
    "RESOLUCION 2706 DE 2025": {
        # Agregada el 25-08-2026, transcrita del PDF oficial del Ministerio
        # (395 paginas, firmada el 23 de diciembre de 2025). Es la CUPS que
        # rige hoy y el sistema no la tenia.
        "nombre": "Resolucion 2706 del 23 de diciembre de 2025 (MinSalud)",
        "titulo": "Clasificacion Unica de Procedimientos en Salud (CUPS) vigente",
        "ambito": "CUPS aplicable a los servicios prestados desde el 1 de enero de 2026",
        "vigente": True,
        "notas": (
            "Su Articulo 5 dice: 'La presente resolucion rige a partir del 1 de enero de "
            "2026 y deroga, a partir de esa fecha, las Resoluciones 2641 de 2024, 2689 de "
            "2024 y 756 de 2025'. Es la norma con que se comprueba la descripcion de un "
            "CUPS facturado en 2026."
        ),
        "verificada": "25-08-2026 PDF oficial MinSalud",
        "keywords": ["CUPS", "procedimientos en salud", "2706 de 2025", "vigente"],
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
        # 25-08-2026: dos dictámenes del lote la citaron como «Resolución 3100
        # de 2020». El número es correcto, el año no. Con el año cambiado la
        # entidad no la encuentra y trata la cita como inventada.
        "notas": (
            "OJO CON EL AÑO: es de 2019 (25 de noviembre), no de 2020. "
            "Sirve para acreditar que el servicio facturado estaba habilitado."
        ),
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
        # Corregida el 25-08-2026. El sistema la daba como "modificaciones al
        # RIPS y a la factura electronica". No tiene NADA que ver: es un acto
        # del Ministerio del INTERIOR que le reconoce personeria juridica a una
        # iglesia. Ni siquiera es del sector salud. Se conserva con su
        # contenido real para que, si alguien la cita, el sistema sepa que es.
        #
        # La norma de RIPS que probablemente se queria referenciar es la
        # Resolucion 1884 de 2024 (plazos de RIPS), hoy derogada por la
        # Res. 948 de 2026 junto con la 2275 de 2023 y la 558 de 2024.
        "nombre": "Resolucion 1604 de 2024 (Ministerio del Interior)",
        "titulo": "Personeria juridica especial a una entidad religiosa",
        "ambito": "Asuntos religiosos — ajena por completo a las cuentas medicas",
        "vigente": True,
        "notas": (
            "NO USAR EN NINGUNA RESPUESTA DE GLOSA: no es una norma de salud. Si lo que "
            "se busca es la reglamentacion de RIPS y factura electronica, hoy rige la "
            "Res. 948 de 2026."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["personeria juridica", "entidad religiosa", "Ministerio del Interior"],
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
        # Verificada el 25-08-2026 contra fuente oficial.
        "vigente": False,
        "derogada_por": (
            "la derogo expresamente la Resolucion DIAN 000165 del 1 de noviembre de 2023, cuyo "
            "articulo 70 dice que rige desde su publicacion y deroga la Res. 000042 de 2020"
        ),
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
        # 25-08-2026: no se pudo confirmar si sigue vigente (las
        # fuentes oficiales no respondieron). Verificar antes de citarla.
        "vigencia_sin_confirmar": True,
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
        # Corregida el 25-08-2026. El sistema la daba como "reglamentacion de
        # la atencion integral del cancer infantil (Ley 1388/2010)", y un
        # dictamen la cito ademas "en materia de RIPS": ninguna de las dos.
        # Lo que trata resulto MAS util para cartera de lo que decia el rotulo.
        "nombre": "Resolucion 2335 del 29 de diciembre de 2023 (MinSalud)",
        "titulo": "Ejecucion, seguimiento y ajuste de los acuerdos de voluntades",
        "ambito": "Relacion contractual entre prestadores y entidades responsables de pago",
        "vigente": True,
        "notas": (
            "21 articulos y 2 anexos tecnicos. Fija los procedimientos y aspectos "
            "tecnicos para ejecutar, hacer seguimiento y ajustar los acuerdos de "
            "voluntades entre la IPS y la entidad pagadora. Sirve para discutir la "
            "ejecucion del contrato, no para cancer infantil ni para RIPS."
        ),
        # 27-08-2026: se carga el articulo 20 con su texto literal. Es el que
        # deroga la Resolucion 3047 de 2008, y el corpus no lo tenia — por eso
        # el revisor de citas aprobaba dictamenes fundados en una norma muerta.
        # Descargado del normograma de la Superintendencia Nacional de Salud
        # (resolucion_minsaludps_2335_2023.htm).
        "articulos": {
            "20": {
                "titulo": "Derogatorias",
                "texto": (
                    "El presente acto administrativo deroga la Resolucion numero 3047 de "
                    "2008 y sus modificatorias, la Resolucion numero 416 de 2009 y la "
                    "Resolucion numero 4331 de 2012, asi como la Resolucion numero 3253 "
                    "de 2009; a partir del 1 de abril de 2026."
                ),
                "aplicacion": (
                    "Texto vigente tras la modificacion del articulo 2 de la Resolucion "
                    "1886 de 2024. Es la prueba de que la Res. 3047 de 2008 ya no rige "
                    "para servicios prestados desde el 1 de abril de 2026. Para los "
                    "anteriores a esa fecha la 3047 SI era aplicable."
                ),
            },
        },
        "verificada": (
            "25-08-2026 PDF oficial MinSalud (objeto de la resolución) · "
            "27-08-2026 normograma Supersalud (artículo 20, derogatorias)"
        ),
        "keywords": [
            "acuerdos de voluntades",
            "ejecucion del contrato",
            "seguimiento",
            "prestador y pagador",
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
        "articulos": {},
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
    # Agregadas el 24-08-2026. Estaban en la pantalla de Consulta Normativa
    # pero NO en el corpus con que se revisan las citas, así que un dictamen
    # que las citara —y hay glosas de medicamentos que obligan a citarlas—
    # salía marcado con «NORMA_INEXISTENTE» en rojo. Son las dos normas con
    # que se responde una glosa de «precio superior al regulado».
    "CIRCULAR 19 DE 2024": {
        "nombre": "Circular 19 de 2024 (CNPMDM — MinSalud/MinCIT)",
        "titulo": "Precio máximo de venta de medicamentos en control directo",
        "ambito": "Medicamentos con control directo de precios — por mercado relevante",
        "vigente": True,
        "notas": (
            "Rige desde el 30 de julio de 2024 y deroga la Circular 13 de 2022. "
            "Fija el precio máximo POR MERCADO RELEVANTE (mg/unidad). CLAVE PARA LA "
            "DEFENSA: el Parágrafo 2 del Art. 1 permite a la IPS ADICIONAR al precio "
            "máximo el margen del Art. 11 de la Circular 18 de 2024, así que facturar "
            "por encima del precio máximo NO es por sí solo un sobrecosto."
        ),
        "keywords": [
            "precio máximo de venta",
            "control directo de precios",
            "medicamentos regulados",
            "mercado relevante",
            "CNPMDM",
            "CUM",
        ],
    },
    "CIRCULAR 18 DE 2024": {
        # Corregida el 25-08-2026. Esta entrada se habia agregado ese mismo dia
        # describiendola como "margenes de comercializacion", y al verificarla
        # contra la fuente oficial el enunciado resulto incompleto: su objeto es
        # la METODOLOGIA del regimen de control directo de precios.
        "nombre": "Circular 18 de 2024 (CNPMDM — MinSalud/MinCIT)",
        "titulo": "Metodologia del regimen de control directo de precios de medicamentos",
        "ambito": "Como se fija el precio maximo de un medicamento regulado",
        "vigente": True,
        "notas": (
            "Define la metodologia con que la Comision Nacional de Precios identifica los "
            "medicamentos que entran al control directo y como se les fija el precio. Su "
            "Articulo 11 es el margen al que remite el Paragrafo 2 del Articulo 1 de la "
            "Circular 19 de 2024, y por eso las dos se citan juntas al responder una glosa "
            "por 'precio superior al regulado'."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": [
            "control directo de precios",
            "metodologia",
            "precio maximo",
            "CNPMDM",
            "margen Art. 11",
        ],
    },
    "CIRCULAR 025 DE 2024": {
        "nombre": "Circular 025 de 31-dic-2024 (MinSalud)",
        "titulo": "Manual Tarifario SOAT actualizado — UVB",
        "ambito": "Unidad de Valor Básico (UVB) vigente desde 01/01/2025",
        # Verificada el 25-08-2026 contra fuente oficial.
        "vigente": False,
        "derogada_por": (
            "fijo las tarifas SOLO para la vigencia 2025 (asi lo dice su propio asunto). Para s"
            "ervicios prestados desde el 1 de enero de 2026 rige la Circular Externa 047 del 30"
            " de diciembre de 2025"
        ),
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
        # Corregida el 25-08-2026. El sistema la daba como "cronograma de
        # implementacion del Manual Unico de Glosas". No es eso, y lo que si es
        # resulto mucho mas util para defender al hospital.
        "nombre": "Circular Externa Conjunta 007 del 3 de marzo de 2025",
        "titulo": ("Prohibicion de barreras y de exigencias no normadas a los prestadores"),
        "ambito": "Exigencias de la entidad pagadora que no estan en ninguna norma",
        "vigente": True,
        "notas": (
            "Circular CONJUNTA del Ministerio de Salud y la Superintendencia Nacional de "
            "Salud (no solo del Ministerio). Su asunto textual es el cumplimiento de la "
            "normativa legal y la PROHIBICION de medidas no normadas, de imponer barreras "
            "y de hacer solicitudes no permitidas a los prestadores de servicios de salud. "
            "Util cuando la EPS exige un requisito que ninguna norma le impone al hospital."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": [
            "barreras al prestador",
            "exigencias no normadas",
            "SuperSalud",
            "circular conjunta",
        ],
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
                "titulo": "Manual Funcional de Seguimiento a Facturas – SIIFA, Ministerio de Salud y Protección Social, versión 1.0.0 …",
                "texto": (
                    "6.3 Registro de Glosa — «Se recuerda que en virtud del artículo 57 de la "
                    "Ley 1438 de 2011, todas las glosas deben formularse y comunicarse en un "
                    "mismo momento y sólo es posible formular nuevas glosas que resulten de la "
                    "respuesta inicial dada por el prestador. El sistema registrará "
                    "automáticamente la fecha del registro.» «Tiempos del registro en SIIFA de "
                    "la glosa. Los tiempos para el registro de las glosa y la respuestas en el "
                    "SIIFA, están determinados en la Resolución 1962 de 2025, y debe ser "
                    "preferiblemente por interoperabilidad o a mas tardar durante las siguientes "
                    "48 horas hábiles posteriores a la formulación y comunicación de las "
                    "mismas.» «Tiempos del trámite de la glosa. Los tiempos para la formulación "
                    "y comunicación de las glosas están establecidos en el artículo 57 de la Ley "
                    "1438 de 2011. (…) Una vez registrada la glosa que previamente ha sido "
                    "formulada y comunicada por el pagador; esta queda disponible para que el "
                    "prestador/proveedor consulte y registre la respuesta dentro de los tiempos "
                    "definidos por la normativa vigente.» Tabla «Tiempos para la formulación y "
                    "comunicación de glosa» (Etapa | Responsable | Tiempo máximo | Descripción): "
                    "1) «Formulación y comunicación de todas las glosas asociadas a la factura» "
                    "| ERP | «20 días hábiles desde la radicación» | «La entidad pagadora revisa "
                    "la factura radicada, si encuentra alguna inconformidad que sea causal de "
                    "glosa, debe comunicarla al prestador/proveedor durante los primeros 20 dias "
                    "hábiles posteriores a la radicación de la factura. Preferiblemente por "
                    "interoperabilidad o máximo durante las siguientes 48 horas hábiles, deberá "
                    "registrar dicha información en SIIFA.» 2) «Respuesta a glosa» | "
                    "Prestador/Proveedor | «15 días hábiles después de la formulación y "
                    "comunicación» | «(…) El prestador/proveedor debe corregir las "
                    "inconsistencias señaladas y responder a la ERP, justificando o sustentando "
                    "su respuesta, dentro del plazo estipulado.» 3) «ERP levanta total o, "
                    "parcialmente la glosa o, la reitera» | ERP | «10 días hábiles posteriores a "
                    "la respuesta del PSS o PTS» | «La entidad pagadora analiza la respuesta "
                    "presentada y decide levantar o reiterar total o parcialmente la glosa, con "
                    "el debido argumento que justifique la decisión. Preferiblemente por "
                    "interoperabilidad o máximo durante las siguientes 48 horas hábiles, deberá "
                    "registrar dicha información en SIIFA. Si la glosa es reiterada, y el "
                    "prestador/proveedor considera que es correcta la aplicación deberá realizar "
                    "una nota crédito afectando la factura por el valor de la glosa, y validar "
                    "dicha nota crétido por el mecanismo único de validación de FEV-RIPS.» 4) "
                    "«Subsanación de glosa no levantada» | Prestador/Proveedor | «7 días hábiles "
                    "después de la respuesta inicial de la ERP» | «Sobre las glosas no "
                    "levantadas, si el prestador/provedor considera que es subsanable, debe "
                    "corregir la inconsistencia señalada y responder a la ERP, justificando o "
                    "sustentando su subsanación, dentro del plazo estipulado. Preferiblemente "
                    "por interoperabilidad o máximo durante las siguientes 48 horas hábiles, "
                    "deberá registrar dicha información en SIIFA.» 5) «Respuesta final y Pago de "
                    "valores aceptados» | ERP | «5 días hábiles» | «La entidad responsable de "
                    "pago debe responder durante los 5 dias hábiles posteriores a la subsanación "
                    "recibida del prestador/proveedor, sobre las glosas no levantadas, con el "
                    "debido argumento que justifique la decisión. Preferiblemente por "
                    "interoperabilidad o máximo durante las siguientes 48 horas hábiles, el "
                    "pagador deberá registrar la decisión final en SIIFA. Si la glosa es "
                    "reiterada, y el prestador/proveedor considera que es correcta la aplicación "
                    "deberá realizar una nota crédito parcial afectando la factura por el valor "
                    "de la glosa, y validarla ante la DIAN y por el mecanismo único de "
                    "validación de FEV-RIPS. De modo contrario, si considera que la glosa no "
                    "levantada es injustificada, podrá acudir ante la Superintendencia Nacional "
                    "de Salud, para que en el ejercicio de sus funciones conciliatorias o "
                    "jurisdiccionales resuelva la controversia.» «Normativa: Artículo 57, Ley "
                    "1438 de 2011.» Numeral 6.3.5 «Decisión Final»: «Posterior a la subsananción "
                    "de glosas no levantadas realizada por el prestador/proveedor, la ERP deberá "
                    "revisar y tomar una decisión final, la cual posterior a la comunicación al "
                    "prestador/proveedor deberá ser registrada en el SIIFA dentro de los 48 "
                    "horas hábiles posteriores.» "
                ),
                "aplicacion": (
                    "Intenté refutar el hallazgo y no pude: los tres defectos son ciertos y se "
                    "comprueban en la fuente oficial. (0) EPÍGRAFE INEXISTENTE: el «Manual SIIFA "
                    "2026» no es una norma con artículos; el documento real es el «Manual "
                    "Funcional de Seguimiento a Facturas – SIIFA» v1.0.0 de febrero de 2026, y "
                    "en sus 61 páginas no existe ningún título «Cronograma completo del trámite "
                    "de glosas». Los plazos están en "
                ),
                "keywords": [],
            },
        },
        "verificada": "26-08-2026 contra fuente oficial (normograma SuperSalud / Senado) — se corrigió",
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
    # ── Cargadas el 25-08-2026 ──────────────────────────────────────────
    # Los prompts del motor ya le ofrecian estas normas a la IA, pero no
    # estaban en el corpus con que se revisan las citas. Resultado: la IA las
    # citaba (porque se lo pedimos) y el revisor las marcaba en rojo como
    # "norma inexistente" sobre un dictamen que podia estar bien. Verificadas
    # una por una contra fuente oficial antes de cargarlas.
    "ACUERDO 080 DE 2022 CSSMP": {
        "nombre": "Acuerdo 080 de 2022 (Consejo Superior de Salud de las FF.MM. y de Policia)",
        "titulo": "Gestion farmaceutica del Subsistema de Salud de las Fuerzas Militares",
        "ambito": "Sanidad Militar y de Policia — medicamentos cubiertos",
        "vigente": True,
        "notas": (
            "Es la lista oficial de medicamentos cubiertos del subsistema (el MUMT) y las reglas "
            "de dispensacion. Se cita en glosas de medicamentos de Dispensario y Sanidad Militar."
        ),
        "verificada": "25-08-2026 fuente oficial",
        "keywords": ["sanidad militar", "MUMT", "gestion farmaceutica", "CSSMP"],
    },
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
        (r"ley\s+(\d+)\s*(?:de\s+)?(\d{4})?", "LEY {0} DE {1}", None),
        (r"resoluci[oó]n\s+(\d+)\s*(?:de\s+)?(\d{4})?", "RESOLUCION {0} DE {1}", None),
        (r"decreto\s+(\d+)\s*(?:de\s+)?(\d{4})?", "DECRETO {0} DE {1}", None),
        (r"circular\s+(\d+)\s*(?:de\s+)?(\d{4})?", "CIRCULAR {0} DE {1}", None),
        (r"sentencia\s+t[-\s]?(\d+)\s*(?:de\s+)?(\d{4})?", "SENTENCIA T-{0} DE {1}", None),
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
        # Ley 100 («su prestacion no requiere contrato ni orden previa»).
        # 25-08-2026: este comentario decia ademas «y el Art. 20 del Decreto
        # 4747» — el Art. 20 es el del RIPS. Corregido contra la fuente.
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
