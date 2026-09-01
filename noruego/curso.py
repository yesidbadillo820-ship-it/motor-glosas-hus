"""La ruta de aprendizaje: módulos y lecciones, de cero a nivel avanzado.

Una lección no lista sus palabras una por una: declara **de dónde salen**
(qué temas, qué niveles, qué reglas de gramática). Así, cuando el léxico
crece, las lecciones crecen solas y nadie tiene que tocar este archivo.

El orden importa: cada lección se apoya en lo anterior. Por eso las lecciones
se desbloquean en orden y no se puede saltar a la mitad del curso sin haber
pasado por lo de antes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dominio import Nivel, TipoEjercicio

T = TipoEjercicio

#: Mezclas de tipos de ejercicio, según lo que enseña la lección.
MEZCLA_SONIDOS = (T.PRONUNCIAR, T.ESCUCHAR_OPCION, T.OPCION, T.PAREJAS)
MEZCLA_VOCABULARIO = (T.PAREJAS, T.TRADUCIR_NO_ES, T.TRADUCIR_ES_NO, T.ESCUCHAR_OPCION, T.OPCION)
MEZCLA_FRASES = (T.TRADUCIR_ES_NO, T.ORDENAR, T.COMPLETAR, T.ESCUCHAR_ESCRIBIR, T.TRADUCIR_NO_ES)
MEZCLA_GRAMATICA = (T.COMPLETAR, T.ORDENAR, T.ERROR, T.OPCION, T.TRADUCIR_ES_NO)
MEZCLA_SUSTANTIVOS = (T.GENERO, T.FORMA_NOMINAL, T.PAREJAS, T.TRADUCIR_ES_NO, T.OPCION)
MEZCLA_VERBOS = (T.CONJUGAR, T.COMPLETAR, T.TRADUCIR_ES_NO, T.ORDENAR, T.ERROR)
MEZCLA_CONVERSACION = (T.DIALOGO, T.ORDENAR, T.TRADUCIR_ES_NO, T.ESCUCHAR_OPCION)


@dataclass(frozen=True)
class Leccion:
    """Una lección: lo que se aprende y de dónde sale el material."""

    clave: str
    titulo: str
    objetivo: str
    tipos: tuple[TipoEjercicio, ...] = MEZCLA_VOCABULARIO
    temas: tuple[str, ...] = ()
    niveles: tuple[str, ...] = ()
    ids: tuple[str, ...] = ()
    gramatica: tuple[str, ...] = ()
    sonidos: tuple[str, ...] = ()
    dialogo: str = ""
    fuentes: tuple[str, ...] = ("frases", "sustantivos", "verbos", "adjetivos")
    ejercicios: int = 12


@dataclass(frozen=True)
class Modulo:
    """Un bloque de lecciones sobre un mismo asunto."""

    clave: str
    titulo: str
    icono: str
    nivel: Nivel
    descripcion: str
    lecciones: tuple[Leccion, ...] = field(default_factory=tuple)


def _l(clave, titulo, objetivo, **kw) -> Leccion:
    return Leccion(clave=clave, titulo=titulo, objetivo=objetivo, **kw)


MODULOS: tuple[Modulo, ...] = (
    Modulo(
        "sonidos",
        "Primer contacto",
        "🔤",
        Nivel.CERO,
        "Antes de la primera palabra: los sonidos que el español no tiene.",
        (
            _l(
                "s1",
                "Las tres letras nuevas",
                "Reconocer y pronunciar æ, ø y å.",
                tipos=MEZCLA_SONIDOS,
                sonidos=("p-Æ æ", "p-Ø ø", "p-Å å"),
                fuentes=("sonidos",),
                ejercicios=9,
            ),
            _l(
                "s2",
                "La u y la y noruegas",
                "Distinguir la u y la y, que no suenan como en español.",
                tipos=MEZCLA_SONIDOS,
                sonidos=("p-U u", "p-Y y"),
                fuentes=("sonidos",),
                ejercicios=8,
            ),
            _l(
                "s3",
                "Letras que engañan",
                "La j suena «y», la h es un soplido y la o suena «u».",
                tipos=MEZCLA_SONIDOS,
                sonidos=("p-J j", "p-H h", "p-O o"),
                fuentes=("sonidos",),
                ejercicios=9,
            ),
            _l(
                "s4",
                "Los sonidos sh y kj",
                "Los dos sonidos que más cuestan: kj/tj y sj/skj.",
                tipos=MEZCLA_SONIDOS,
                sonidos=("p-Kj _ Tj", "p-Sj _ Skj _ Sk", "p-Rs"),
                fuentes=("sonidos",),
                ejercicios=9,
            ),
            _l(
                "s5",
                "Letras que no se pronuncian",
                "La d final, la h de hv-, la g de -eg y la t de «huset».",
                tipos=MEZCLA_SONIDOS,
                sonidos=("p-Letras mudas",),
                fuentes=("sonidos",),
                ejercicios=8,
            ),
        ),
    ),
    Modulo(
        "saludos",
        "Saludos y presentaciones",
        "👋",
        Nivel.CERO,
        "Lo primero que vas a decir y a oír.",
        (
            _l(
                "g1",
                "Hola y adiós",
                "Saludar y despedirse a cualquier hora del día.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("saludos",),
                niveles=("cero",),
                fuentes=("frases",),
            ),
            _l(
                "g2",
                "Gracias y perdón",
                "La cortesía básica noruega.",
                tipos=MEZCLA_FRASES,
                temas=("saludos",),
                niveles=("cero", "A1"),
                fuentes=("frases",),
            ),
            _l(
                "g3",
                "¿Cómo te llamas?",
                "Preguntar y decir el nombre con el verbo «hete».",
                tipos=MEZCLA_FRASES,
                temas=("saludos",),
                niveles=("cero", "A1"),
                gramatica=("pregunta", "interrogativos"),
                fuentes=("frases",),
            ),
            _l(
                "g4",
                "¿De dónde eres?",
                "Decir de dónde vienes y dónde vives.",
                tipos=MEZCLA_FRASES,
                temas=("saludos", "casa"),
                niveles=("cero", "A1"),
                gramatica=("pregunta",),
                fuentes=("frases",),
            ),
            _l(
                "g5",
                "Tu primera conversación",
                "Juntar todo en un diálogo real de presentación.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-presentacion",
                temas=("saludos",),
                niveles=("cero", "A1"),
                fuentes=("frases",),
                ejercicios=10,
            ),
        ),
    ),
    Modulo(
        "pronombres",
        "Personas y el verbo ser",
        "🧑",
        Nivel.CERO,
        "Los pronombres y el verbo más usado del idioma.",
        (
            _l(
                "p1",
                "Yo, tú, él, ella",
                "Los pronombres personales.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("pronombres",),
                temas=("personas",),
                niveles=("cero", "A1"),
                fuentes=("frases", "sustantivos"),
            ),
            _l(
                "p2",
                "El verbo «være»",
                "Un solo verbo para «ser» y «estar», igual en todas las personas.",
                tipos=MEZCLA_VERBOS,
                gramatica=("verbo-persona",),
                ids=("v-være", "v-ha"),
                fuentes=("verbos", "frases"),
                temas=("saludos", "personas"),
                niveles=("cero", "A1"),
            ),
            _l(
                "p3",
                "Decir que no",
                "La negación con «ikke», que va DESPUÉS del verbo.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("negacion",),
                temas=("saludos", "estudio"),
                niveles=("cero", "A1"),
                fuentes=("frases",),
            ),
            _l(
                "p4",
                "Preguntar",
                "Poner el verbo de primero y usar hva, hvor, hvordan.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("pregunta", "interrogativos"),
                temas=("saludos", "estudio", "ciudad"),
                niveles=("cero", "A1"),
                fuentes=("frases",),
            ),
        ),
    ),
    Modulo(
        "sustantivos",
        "Los sustantivos y sus géneros",
        "🧩",
        Nivel.A1,
        "El artículo pegado al final: lo que más diferencia al noruego del español.",
        (
            _l(
                "n1",
                "en, ei, et",
                "Los tres géneros y por qué hay que aprenderlos con la palabra.",
                tipos=MEZCLA_SUSTANTIVOS,
                gramatica=("generos",),
                temas=("casa", "ciudad", "personas"),
                niveles=("A1",),
                fuentes=("sustantivos",),
            ),
            _l(
                "n2",
                "El artículo va al final",
                "De «en bil» a «bilen» sin traducir palabra por palabra.",
                tipos=MEZCLA_SUSTANTIVOS,
                gramatica=("articulo",),
                temas=("casa", "ciudad", "comida"),
                niveles=("A1",),
                fuentes=("sustantivos",),
            ),
            _l(
                "n3",
                "El plural",
                "Formar «biler» y «bilene», y los plurales irregulares.",
                tipos=MEZCLA_SUSTANTIVOS,
                gramatica=("plural",),
                temas=("casa", "familia", "personas"),
                niveles=("A1",),
                fuentes=("sustantivos",),
            ),
            _l(
                "n4",
                "Práctica de formas",
                "Las cuatro formas de un sustantivo, de corrido.",
                tipos=(T.FORMA_NOMINAL, T.GENERO, T.TRADUCIR_ES_NO, T.OPCION),
                gramatica=("articulo", "plural", "generos"),
                temas=("casa", "ciudad", "comida", "estudio"),
                niveles=("A1",),
                fuentes=("sustantivos",),
                ejercicios=14,
            ),
        ),
    ),
    Modulo(
        "numeros",
        "Números y hora",
        "🔢",
        Nivel.A1,
        "Contar, decir la hora y entender precios.",
        (
            _l(
                "num1",
                "Del 0 al 20",
                "Los números que más se oyen.",
                tipos=(T.PAREJAS, T.ESCUCHAR_OPCION, T.TRADUCIR_ES_NO, T.OPCION),
                temas=("numeros",),
                niveles=("cero",),
                fuentes=("numeros",),
            ),
            _l(
                "num2",
                "Del 21 en adelante",
                "Cómo se arman las decenas y los cientos.",
                tipos=(T.TRADUCIR_ES_NO, T.OPCION, T.ESCUCHAR_ESCRIBIR, T.PAREJAS),
                temas=("numeros",),
                niveles=("A1",),
                fuentes=("numeros",),
            ),
            _l(
                "num3",
                "La hora",
                "Preguntar y decir qué hora es.",
                tipos=MEZCLA_FRASES,
                temas=("tiempo",),
                niveles=("A1", "A2"),
                fuentes=("frases", "sustantivos"),
            ),
            _l(
                "num4",
                "Días y fechas",
                "Los días de la semana, los meses y los ordinales.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("ordinales",),
                temas=("tiempo",),
                niveles=("A1", "A2"),
                fuentes=("frases", "sustantivos"),
            ),
        ),
    ),
    Modulo(
        "familia",
        "Familia y personas",
        "👨‍👩‍👧",
        Nivel.A1,
        "Hablar de los tuyos y describir a la gente.",
        (
            _l(
                "f1",
                "La familia",
                "Los nombres de los parientes, con sus plurales irregulares.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("familia",),
                niveles=("A1", "A2"),
                fuentes=("sustantivos",),
            ),
            _l(
                "f2",
                "Mi, tu, su",
                "Los posesivos, que en noruego van DETRÁS del sustantivo.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("posesivos",),
                temas=("familia", "casa"),
                niveles=("A1", "A2"),
                fuentes=("frases", "sustantivos"),
            ),
            _l(
                "f3",
                "Adjetivos",
                "Cómo cambia el adjetivo según el género y el número.",
                tipos=(T.COMPLETAR, T.OPCION, T.ERROR, T.TRADUCIR_ES_NO, T.PAREJAS),
                gramatica=("adjetivo",),
                niveles=("A1",),
                fuentes=("adjetivos",),
            ),
            _l(
                "f4",
                "Describir personas",
                "Juntar sustantivo, adjetivo y verbo en una frase.",
                tipos=MEZCLA_FRASES,
                gramatica=("adjetivo", "doble-definido"),
                temas=("personas", "familia", "sentimientos"),
                niveles=("A1", "A2"),
                fuentes=("frases", "adjetivos"),
            ),
        ),
    ),
    Modulo(
        "verbos",
        "Verbos y el orden de la frase",
        "⚙️",
        Nivel.A1,
        "El verbo en segundo lugar: la regla que más delata a un extranjero.",
        (
            _l(
                "v1",
                "Verbos del día a día",
                "Los veinte verbos que más vas a usar.",
                tipos=MEZCLA_VERBOS,
                temas=("gramatica", "casa", "estudio", "trabajo"),
                niveles=("A1",),
                fuentes=("verbos",),
            ),
            _l(
                "v2",
                "El verbo va segundo",
                "La regla V2, con ejemplos que empiezan por tiempo o lugar.",
                tipos=(T.ORDENAR, T.ERROR, T.COMPLETAR, T.TRADUCIR_ES_NO),
                gramatica=("v2",),
                temas=("tiempo", "casa", "trabajo"),
                niveles=("A1", "A2"),
                fuentes=("frases",),
                ejercicios=14,
            ),
            _l(
                "v3",
                "Å + infinitivo",
                "Cuándo lleva «å» y cuándo no.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("infinitivo",),
                temas=("sentimientos", "estudio"),
                niveles=("A1", "A2"),
                fuentes=("frases", "verbos"),
            ),
            _l(
                "v4",
                "Los verbos modales",
                "kan, vil, skal, må, bør y el infinitivo sin «å».",
                tipos=MEZCLA_VERBOS,
                gramatica=("modales",),
                ids=("v-kunne", "v-ville", "v-skulle", "v-måtte", "v-burde"),
                fuentes=("verbos", "frases"),
                temas=("comida", "estudio", "sociedad"),
                niveles=("A1", "A2"),
            ),
        ),
    ),
    Modulo(
        "comida",
        "Comida y restaurante",
        "🍞",
        Nivel.A1,
        "Comprar, pedir y hablar de lo que te gusta.",
        (
            _l(
                "c1",
                "Comida y bebida",
                "El vocabulario del supermercado y la cocina.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("comida",),
                niveles=("A1", "A2"),
                fuentes=("sustantivos",),
            ),
            _l(
                "c2",
                "En la cafetería",
                "Pedir algo de tomar y pagar.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-cafe",
                temas=("comida", "compras"),
                niveles=("A1", "A2"),
                fuentes=("frases",),
            ),
            _l(
                "c3",
                "En el restaurante",
                "Reservar, pedir y pedir la cuenta.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-restaurante",
                temas=("comida",),
                niveles=("A2",),
                fuentes=("frases",),
            ),
            _l(
                "c4",
                "Lo que me gusta",
                "Expresar gustos y opiniones sencillas.",
                tipos=MEZCLA_FRASES,
                gramatica=("infinitivo", "negacion"),
                temas=("sentimientos", "comida"),
                niveles=("A1", "A2"),
                fuentes=("frases",),
            ),
        ),
    ),
    Modulo(
        "casa",
        "La casa",
        "🏠",
        Nivel.A2,
        "Tu vivienda, y las preposiciones que más cuestan.",
        (
            _l(
                "h1",
                "Cuartos y muebles",
                "El vocabulario de la casa.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("casa",),
                niveles=("A1", "A2"),
                fuentes=("sustantivos",),
            ),
            _l(
                "h2",
                "i, på, til",
                "Las tres preposiciones que el español junta en una sola.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("preposiciones",),
                temas=("casa", "ciudad", "trabajo"),
                niveles=("A1", "A2"),
                fuentes=("frases",),
                ejercicios=14,
            ),
            _l(
                "h3",
                "Aquí y allá",
                "hjem o hjemme, ut o ute: movimiento contra lugar.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("hjemme",),
                temas=("casa",),
                niveles=("A2", "B1"),
                fuentes=("frases",),
            ),
            _l(
                "h4",
                "Buscar apartamento",
                "Llamar por un anuncio y preguntar por el arriendo.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-arriendo",
                temas=("casa", "compras"),
                niveles=("A2", "B1"),
                fuentes=("frases", "sustantivos"),
            ),
        ),
    ),
    Modulo(
        "ciudad",
        "Ciudad y transporte",
        "🚌",
        Nivel.A2,
        "Moverte por la ciudad y viajar.",
        (
            _l(
                "t1",
                "En la ciudad",
                "Lugares, calles y direcciones.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("ciudad",),
                niveles=("A1", "A2"),
                fuentes=("sustantivos",),
            ),
            _l(
                "t2",
                "Transporte",
                "Bus, tren, carro y bicicleta.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("ciudad", "viaje"),
                niveles=("A1", "A2"),
                fuentes=("sustantivos", "frases"),
            ),
            _l(
                "t3",
                "Comprar un pasaje",
                "Preguntar horarios y comprar el tiquete.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-transporte",
                temas=("viaje",),
                niveles=("A2",),
                fuentes=("frases",),
            ),
            _l(
                "t4",
                "En el aeropuerto",
                "El check-in y el equipaje.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-aeropuerto",
                temas=("viaje",),
                niveles=("A2",),
                fuentes=("frases", "sustantivos"),
            ),
        ),
    ),
    Modulo(
        "compras",
        "Compras y dinero",
        "🛒",
        Nivel.A2,
        "Precios, pagos y el supermercado.",
        (
            _l(
                "k1",
                "Dinero y precios",
                "Coronas, precios y formas de pago.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("compras",),
                niveles=("A1", "A2"),
                fuentes=("sustantivos", "frases", "numeros"),
            ),
            _l(
                "k2",
                "En el supermercado",
                "Preguntar dónde está algo y pedir ayuda.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-supermercado",
                temas=("compras", "comida"),
                niveles=("A1", "A2"),
                fuentes=("frases",),
            ),
            _l(
                "k3",
                "Comparar",
                "Más grande, más barato: el comparativo.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("comparativo",),
                niveles=("A2", "B1"),
                fuentes=("adjetivos", "frases"),
            ),
            _l(
                "k4",
                "Palabras pegadas",
                "Las palabras compuestas y por qué no se separan.",
                tipos=(T.OPCION, T.PAREJAS, T.ERROR, T.TRADUCIR_ES_NO),
                gramatica=("compuestas",),
                niveles=("A2",),
                fuentes=("sustantivos",),
            ),
        ),
    ),
    Modulo(
        "pasado",
        "Hablar del pasado",
        "⏪",
        Nivel.A2,
        "Los cuatro grupos de verbos y el perfecto.",
        (
            _l(
                "pa1",
                "Los grupos 1 y 2",
                "Los verbos en -et y en -te.",
                tipos=MEZCLA_VERBOS,
                gramatica=("pasado",),
                niveles=("A1", "A2"),
                fuentes=("verbos",),
                ejercicios=14,
            ),
            _l(
                "pa2",
                "Los grupos 3 y 4",
                "Los verbos en -de y en -dde.",
                tipos=MEZCLA_VERBOS,
                gramatica=("pasado",),
                niveles=("A1", "A2", "B1"),
                fuentes=("verbos",),
            ),
            _l(
                "pa3",
                "Los irregulares",
                "Los que hay que aprender de memoria, uno por uno.",
                tipos=MEZCLA_VERBOS,
                gramatica=("pasado",),
                niveles=("A1", "A2"),
                fuentes=("verbos",),
                ejercicios=14,
            ),
            _l(
                "pa4",
                "He hecho, he estado",
                "El perfecto con «har» y cuándo usarlo.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("perfecto", "futuro"),
                temas=("tiempo", "viaje"),
                niveles=("A2", "B1"),
                fuentes=("frases", "verbos"),
            ),
        ),
    ),
    Modulo(
        "trabajo",
        "Trabajo",
        "💼",
        Nivel.A2,
        "Buscar empleo y desenvolverte en la oficina.",
        (
            _l(
                "w1",
                "El mundo laboral",
                "Vocabulario de trabajo, oficina y salario.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("trabajo",),
                niveles=("A1", "A2", "B1"),
                fuentes=("sustantivos",),
            ),
            _l(
                "w2",
                "¿En qué trabajas?",
                "Contar a qué te dedicas.",
                tipos=MEZCLA_FRASES,
                temas=("trabajo",),
                niveles=("A1", "A2", "B1"),
                fuentes=("frases",),
            ),
            _l(
                "w3",
                "Entrevista de trabajo",
                "Responder las preguntas típicas de una entrevista.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-trabajo",
                temas=("trabajo",),
                niveles=("A2", "B1"),
                fuentes=("frases",),
            ),
            _l(
                "w4",
                "Charla de pasillo",
                "La conversación corta con vecinos y colegas.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-vecino",
                temas=("personas", "clima"),
                niveles=("A1", "A2"),
                fuentes=("frases",),
            ),
        ),
    ),
    Modulo(
        "salud",
        "Salud y cuerpo",
        "🩺",
        Nivel.A2,
        "Explicar qué te pasa y entender al médico.",
        (
            _l(
                "sa1",
                "El cuerpo",
                "Las partes del cuerpo, con sus plurales irregulares.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("salud",),
                niveles=("A1", "A2"),
                fuentes=("sustantivos",),
            ),
            _l(
                "sa2",
                "Me duele",
                "La estructura «ha vondt i» y cómo describir un síntoma.",
                tipos=MEZCLA_FRASES,
                temas=("salud",),
                niveles=("A1", "A2", "B1"),
                fuentes=("frases",),
            ),
            _l(
                "sa3",
                "En el consultorio",
                "La consulta médica completa.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-medico",
                temas=("salud",),
                niveles=("A2", "B1"),
                fuentes=("frases",),
            ),
            _l(
                "sa4",
                "Pedir una cita",
                "«Time» significa hora y también cita.",
                tipos=MEZCLA_FRASES,
                temas=("salud", "tiempo", "sociedad"),
                niveles=("A2", "B1"),
                fuentes=("frases",),
            ),
        ),
    ),
    Modulo(
        "clima",
        "Clima y naturaleza",
        "🌦️",
        Nivel.A2,
        "El tema de conversación favorito de Noruega.",
        (
            _l(
                "cl1",
                "El tiempo que hace",
                "Frío, lluvia, nieve y sol.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("clima",),
                niveles=("A1", "A2"),
                fuentes=("sustantivos", "frases"),
            ),
            _l(
                "cl2",
                "Frases impersonales",
                "Por qué el clima siempre empieza con «det».",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("den-det",),
                temas=("clima",),
                niveles=("A1", "A2"),
                fuentes=("frases",),
            ),
            _l(
                "cl3",
                "Naturaleza",
                "Montaña, bosque y mar.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("clima", "viaje"),
                niveles=("A2", "B1"),
                fuentes=("sustantivos",),
            ),
        ),
    ),
    Modulo(
        "opiniones",
        "Opiniones y frases largas",
        "💬",
        Nivel.B1,
        "Decir lo que piensas y encadenar ideas.",
        (
            _l(
                "o1",
                "Creo que, me parece",
                "La diferencia entre «tror», «synes» y «mener».",
                tipos=MEZCLA_FRASES,
                temas=("sentimientos",),
                niveles=("A2", "B1", "B2"),
                fuentes=("frases",),
            ),
            _l(
                "o2",
                "Frases subordinadas",
                "Después de «at» y «fordi», el «ikke» se adelanta.",
                tipos=(T.ORDENAR, T.ERROR, T.COMPLETAR, T.TRADUCIR_ES_NO),
                gramatica=("subordinada",),
                temas=("sentimientos", "estudio"),
                niveles=("A2", "B1"),
                fuentes=("frases",),
                ejercicios=14,
            ),
            _l(
                "o3",
                "Som: el que, la que",
                "Unir dos frases con «som».",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("som",),
                niveles=("B1",),
                fuentes=("frases", "sustantivos"),
            ),
            _l(
                "o4",
                "Su propio o de otro",
                "sin, si, sitt, sine contra hans y hennes.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("sin",),
                temas=("familia", "casa"),
                niveles=("A2", "B1"),
                fuentes=("frases", "sustantivos"),
            ),
        ),
    ),
    Modulo(
        "sociedad",
        "Trámites y vida en Noruega",
        "🏛️",
        Nivel.B1,
        "Papeles, oficinas públicas y derechos.",
        (
            _l(
                "so1",
                "Trámites",
                "El vocabulario de formularios, contratos e impuestos.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("sociedad",),
                niveles=("A2", "B1", "B2"),
                fuentes=("sustantivos", "frases"),
            ),
            _l(
                "so2",
                "Llamar a una oficina",
                "Explicar tu caso por teléfono.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-telefono",
                temas=("sociedad",),
                niveles=("B1", "B2"),
                fuentes=("frases",),
            ),
            _l(
                "so3",
                "El impersonal",
                "«Man» y la voz pasiva con -s.",
                tipos=MEZCLA_GRAMATICA,
                gramatica=("man", "pasiva"),
                niveles=("B1", "B2"),
                fuentes=("frases",),
            ),
            _l(
                "so4",
                "Pedir que te expliquen",
                "Cómo hacer que te repitan sin pena.",
                tipos=MEZCLA_CONVERSACION,
                dialogo="d-escuela",
                temas=("estudio", "sociedad"),
                niveles=("A2", "B1"),
                fuentes=("frases",),
            ),
        ),
    ),
    Modulo(
        "avanzado",
        "Noruego profesional",
        "🎓",
        Nivel.B2,
        "Precisión, matiz y lenguaje de trabajo.",
        (
            _l(
                "ad1",
                "Repaso general de gramática",
                "Todas las reglas del curso, mezcladas.",
                tipos=(T.ERROR, T.ORDENAR, T.COMPLETAR, T.TRADUCIR_ES_NO, T.OPCION),
                niveles=("A2", "B1", "B2"),
                fuentes=("frases",),
                ejercicios=16,
            ),
            _l(
                "ad2",
                "Vocabulario profesional",
                "Las palabras del trabajo cualificado.",
                tipos=MEZCLA_VOCABULARIO,
                temas=("trabajo", "sociedad", "salud"),
                niveles=("B1", "B2"),
                fuentes=("sustantivos",),
            ),
            _l(
                "ad3",
                "Escuchar y escribir",
                "Dictados para afinar el oído.",
                tipos=(T.ESCUCHAR_ESCRIBIR, T.ESCUCHAR_OPCION),
                niveles=("A2", "B1", "B2"),
                fuentes=("frases",),
                ejercicios=10,
            ),
            _l(
                "ad4",
                "Todo junto",
                "Prueba mixta con todo lo del curso.",
                tipos=(T.TRADUCIR_ES_NO, T.ORDENAR, T.ERROR, T.ESCUCHAR_ESCRIBIR, T.COMPLETAR),
                niveles=("A1", "A2", "B1", "B2"),
                fuentes=("frases",),
                ejercicios=16,
            ),
        ),
    ),
)


def todas_las_lecciones() -> list[tuple[Modulo, Leccion, int]]:
    """Cada lección con su módulo y su posición global en el curso."""
    salida = []
    indice = 0
    for modulo in MODULOS:
        for leccion in modulo.lecciones:
            salida.append((modulo, leccion, indice))
            indice += 1
    return salida


def buscar_leccion(clave: str) -> tuple[Modulo, Leccion] | None:
    for modulo, leccion, _ in todas_las_lecciones():
        if leccion.clave == clave:
            return modulo, leccion
    return None


def total_lecciones() -> int:
    return len(todas_las_lecciones())
