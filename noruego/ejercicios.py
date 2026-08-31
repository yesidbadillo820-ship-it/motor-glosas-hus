"""El motor de ejercicios: convierte los datos del léxico en práctica.

La idea de fondo: **no se escriben ejercicios a mano**. Se escriben los datos
del idioma una sola vez (que «bil» es masculino, que su definido es «bilen»)
y de ahí salen solos el ejercicio de género, el de forma, el de traducción y
el de escucha. Agregar una palabra al léxico agrega ejercicios a todo el curso.

Los distractores no son al azar: salen del mismo tipo de elemento y del mismo
nivel, para que la pregunta mida si sabes y no si adivinas.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field

from .curso import Leccion
from .dominio import TipoEjercicio as T
from .lexico import Lexico

#: Cuántas opciones tiene un ejercicio de selección.
OPCIONES: int = 4


@dataclass(frozen=True)
class Ejercicio:
    """Un ejercicio listo para mostrar y calificar."""

    id: str
    tipo: T
    enunciado: str
    fuente: str
    opciones: tuple[str, ...] = ()
    correcta: int = 0
    respuesta: str = ""
    alternativas: tuple[str, ...] = ()
    orden: tuple[str, ...] = ()
    contexto: str = ""
    audio: str = ""
    pista: str = ""
    explicacion: str = ""
    datos: dict = field(default_factory=dict)

    @property
    def escrita(self) -> bool:
        """¿Se responde escribiendo en vez de tocando una opción?"""
        return self.tipo in (T.TRADUCIR_ES_NO, T.TRADUCIR_NO_ES, T.ESCUCHAR_ESCRIBIR, T.CONJUGAR)


def normalizar(texto: str) -> str:
    """Deja un texto listo para comparar respuestas escritas.

    Perdona lo que no es un error de idioma: mayúsculas, tildes de más, signos
    de puntuación, espacios dobles y el «aa» que algunos teclados escriben en
    vez de «å». No perdona escribir mal la palabra.
    """
    texto = texto.strip().lower().replace("aa", "å")
    texto = "".join(c for c in texto if c.isalnum() or c.isspace() or c in "æøå'-")
    # Se quitan las tildes que el español pone y el noruego no usa, pero se
    # conservan æ, ø y å, que en noruego SÍ son letras distintas.
    salida = []
    for caracter in unicodedata.normalize("NFD", texto):
        if caracter in "æøå" or unicodedata.category(caracter) != "Mn":
            salida.append(caracter)
    return " ".join("".join(salida).split())


def acierta(ejercicio: Ejercicio, respuesta: str | int) -> bool:
    """¿La respuesta del estudiante es correcta?"""
    if ejercicio.tipo is T.ORDENAR:
        dada = respuesta if isinstance(respuesta, str) else ""
        return normalizar(dada) == normalizar(" ".join(ejercicio.orden))
    if ejercicio.escrita:
        dada = normalizar(str(respuesta))
        validas = {normalizar(ejercicio.respuesta)} | {
            normalizar(a) for a in ejercicio.alternativas
        }
        return dada in validas
    try:
        return int(respuesta) == ejercicio.correcta
    except (TypeError, ValueError):
        return False


def _mezclar_opciones(
    azar: random.Random, correcta: str, distractores: list[str]
) -> tuple[tuple[str, ...], int]:
    """Arma las opciones con la correcta en una posición al azar."""
    limpias = []
    for d in distractores:
        if d and normalizar(d) != normalizar(correcta) and d not in limpias:
            limpias.append(d)
    opciones = [correcta] + limpias[: OPCIONES - 1]
    azar.shuffle(opciones)
    return tuple(opciones), opciones.index(correcta)


def _no(elemento: dict) -> str:
    """El texto noruego de cualquier elemento del léxico."""
    return elemento.get("no") or elemento.get("inf") or elemento.get("base") or ""


def _con_articulo(s: dict) -> str:
    return f"{s['genero']} {s['no']}".strip() if s.get("genero") else s["no"]


# ---------------------------------------------------------------------------
# Generadores por tipo
# ---------------------------------------------------------------------------


def _gen_parejas(azar, elementos, pool, indice) -> Ejercicio | None:
    grupo = azar.sample(elementos, min(4, len(elementos)))
    if len(grupo) < 3:
        return None
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.PAREJAS,
        enunciado="Une cada palabra con su significado.",
        fuente=grupo[0]["id"],
        datos={
            "parejas": [{"no": _no(e), "es": e["es"], "pron": e.get("pron", "")} for e in grupo]
        },
        audio=_no(grupo[0]),
        explicacion="Fíjate en las palabras que se parecen entre sí: son las que más se confunden.",
    )


def _gen_traducir(azar, elementos, pool, indice, hacia_no: bool) -> Ejercicio | None:
    e = azar.choice(elementos)
    texto_no, texto_es = _no(e), e["es"]
    if not texto_no or not texto_es:
        return None
    alternativas = tuple(p.strip() for p in texto_es.split("/")) if not hacia_no else ()
    if hacia_no:
        return Ejercicio(
            id=f"e{indice}",
            tipo=T.TRADUCIR_ES_NO,
            enunciado="Escribe en noruego:",
            contexto=texto_es,
            fuente=e["id"],
            respuesta=texto_no,
            audio=texto_no,
            pista=e.get("pron", ""),
            explicacion=e.get("nota")
            or f"«{texto_no}» se pronuncia aproximadamente «{e.get('pron', '')}».",
        )
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.TRADUCIR_NO_ES,
        enunciado="Escribe en español:",
        contexto=texto_no,
        fuente=e["id"],
        respuesta=texto_es.split("/")[0].strip(),
        alternativas=alternativas,
        audio=texto_no,
        pista=e.get("pron", ""),
        explicacion=e.get("nota", ""),
    )


def _gen_opcion(azar, elementos, pool, indice) -> Ejercicio | None:
    e = azar.choice(elementos)
    otros = [o for o in pool if o["id"] != e["id"] and o.get("es")]
    if len(otros) < 3:
        return None
    opciones, correcta = _mezclar_opciones(
        azar, e["es"], [o["es"] for o in azar.sample(otros, min(8, len(otros)))]
    )
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.OPCION,
        enunciado=f"¿Qué significa «{_no(e)}»?",
        fuente=e["id"],
        opciones=opciones,
        correcta=correcta,
        audio=_no(e),
        pista=e.get("pron", ""),
        explicacion=e.get("nota", ""),
    )


def _gen_escuchar_opcion(azar, elementos, pool, indice) -> Ejercicio | None:
    e = azar.choice(elementos)
    otros = [o for o in pool if o["id"] != e["id"] and _no(o)]
    if len(otros) < 3:
        return None
    opciones, correcta = _mezclar_opciones(
        azar, _no(e), [_no(o) for o in azar.sample(otros, min(8, len(otros)))]
    )
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.ESCUCHAR_OPCION,
        enunciado="Escucha y elige lo que oíste.",
        fuente=e["id"],
        opciones=opciones,
        correcta=correcta,
        audio=_no(e),
        explicacion=f"«{_no(e)}» = {e['es']}. Aproximación: «{e.get('pron', '')}».",
    )


def _gen_escuchar_escribir(azar, elementos, pool, indice) -> Ejercicio | None:
    candidatos = [e for e in elementos if len(_no(e).split()) <= 8]
    if not candidatos:
        return None
    e = azar.choice(candidatos)
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.ESCUCHAR_ESCRIBIR,
        enunciado="Escucha y escribe lo que oíste.",
        fuente=e["id"],
        respuesta=_no(e),
        audio=_no(e),
        pista=e.get("pron", ""),
        explicacion=f"«{_no(e)}» = {e['es']}.",
    )


def _gen_ordenar(azar, elementos, pool, indice) -> Ejercicio | None:
    candidatos = [e for e in elementos if 3 <= len(_no(e).replace("?", "").split()) <= 9]
    if not candidatos:
        return None
    e = azar.choice(candidatos)
    palabras = _no(e).split()
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.ORDENAR,
        enunciado="Ordena las palabras para formar la frase.",
        contexto=e["es"],
        fuente=e["id"],
        orden=tuple(palabras),
        datos={"revueltas": _revolver(azar, palabras)},
        audio=_no(e),
        pista=e.get("pron", ""),
        explicacion=e.get("nota") or "Recuerda: el verbo va siempre en segundo lugar.",
    )


def _revolver(azar: random.Random, palabras: list[str]) -> list[str]:
    """Revuelve de verdad: si sale el mismo orden, el ejercicio no mide nada."""
    revueltas = palabras[:]
    for _ in range(12):
        azar.shuffle(revueltas)
        if revueltas != palabras:
            break
    return revueltas


def _gen_completar(azar, elementos, pool, indice) -> Ejercicio | None:
    candidatos = [e for e in elementos if len(_no(e).split()) >= 3]
    if not candidatos:
        return None
    e = azar.choice(candidatos)
    palabras = _no(e).split()
    # Se quita una palabra del medio: la primera y la última dan demasiada pista.
    posicion = azar.randrange(1, len(palabras) - 1) if len(palabras) > 2 else 0
    quitada = palabras[posicion].strip(".,!?")
    hueco = palabras[:]
    hueco[posicion] = "_____"
    otros = {
        p.strip(".,!?")
        for o in pool
        for p in _no(o).split()
        if p.strip(".,!?").lower() != quitada.lower() and len(p) > 1
    }
    if len(otros) < 3:
        return None
    muestra = azar.sample(sorted(otros), min(8, len(otros)))
    opciones, correcta = _mezclar_opciones(azar, quitada, muestra)
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.COMPLETAR,
        enunciado="Completa la frase.",
        contexto=" ".join(hueco),
        fuente=e["id"],
        opciones=opciones,
        correcta=correcta,
        audio=_no(e),
        pista=e["es"],
        explicacion=f"La frase completa es: «{_no(e)}» — {e['es']}.",
    )


def _gen_error(azar, elementos, pool, indice) -> Ejercicio | None:
    """Presenta la frase correcta junto a versiones estropeadas a propósito."""
    candidatos = [e for e in elementos if len(_no(e).split()) >= 3]
    if not candidatos:
        return None
    e = azar.choice(candidatos)
    correcta_txt = _no(e)
    malas = _estropear(azar, correcta_txt)
    if len(malas) < 2:
        return None
    opciones, correcta = _mezclar_opciones(azar, correcta_txt, malas)
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.ERROR,
        enunciado="¿Cuál está bien escrita?",
        contexto=e["es"],
        fuente=e["id"],
        opciones=opciones,
        correcta=correcta,
        audio=correcta_txt,
        explicacion=e.get("nota") or f"La correcta es «{correcta_txt}».",
    )


def _estropear(azar: random.Random, frase: str) -> list[str]:
    """Versiones incorrectas de una frase, con los errores típicos de verdad."""
    palabras = frase.split()
    malas: list[str] = []
    if "ikke" in [p.lower() for p in palabras]:
        # Error clásico: poner «ikke» antes del verbo, como el «no» español.
        i = [p.lower() for p in palabras].index("ikke")
        if i >= 2:
            movida = palabras[:]
            movida.insert(1, movida.pop(i))
            malas.append(" ".join(movida))
    if len(palabras) >= 3:
        # Error clásico: romper la regla del verbo en segundo lugar.
        volteada = palabras[:]
        volteada[1], volteada[2] = volteada[2], volteada[1]
        malas.append(" ".join(volteada))
    sin_a = frase.replace(" å ", " ")
    if sin_a != frase:
        malas.append(sin_a)
    con_a = frase.replace(" kan ", " kan å ").replace(" vil ", " vil å ")
    if con_a != frase:
        malas.append(con_a)
    return [m for m in dict.fromkeys(malas) if m != frase][:3]


def _gen_genero(azar, elementos, pool, indice) -> Ejercicio | None:
    candidatos = [e for e in elementos if e.get("genero")]
    if not candidatos:
        return None
    e = azar.choice(candidatos)
    opciones = ("en", "ei", "et")
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.GENERO,
        enunciado=f"¿Qué artículo lleva «{e['no']}» ({e['es']})?",
        fuente=e["id"],
        opciones=opciones,
        correcta=opciones.index(e["genero"]),
        audio=_con_articulo(e),
        explicacion=(
            f"Es «{_con_articulo(e)}». El género no se adivina: se aprende con la palabra. "
            + (e.get("nota") or "")
        ).strip(),
    )


def _gen_forma_nominal(azar, elementos, pool, indice) -> Ejercicio | None:
    candidatos = [e for e in elementos if e.get("def") and e.get("plural")]
    if not candidatos:
        return None
    e = azar.choice(candidatos)
    forma, etiqueta = azar.choice(
        [
            (e["def"].split(" / ")[0], "la forma definida singular"),
            (e["plural"], "el plural indefinido"),
            (e.get("defPl") or e["plural"], "el plural definido"),
        ]
    )
    otros = [o for o in pool if o["id"] != e["id"]]
    distractores = []
    for o in azar.sample(otros, min(8, len(otros))):
        for campo in ("def", "plural", "defPl"):
            valor = (o.get(campo) or "").split(" / ")[0]
            if valor:
                distractores.append(valor)
    # También un distractor "hecho a mano" con la terminación equivocada.
    distractores.insert(0, e["no"] + "er" if forma != e["no"] + "er" else e["no"] + "en")
    opciones, correcta = _mezclar_opciones(azar, forma, distractores)
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.FORMA_NOMINAL,
        enunciado=f"¿Cuál es {etiqueta} de «{_con_articulo(e)}» ({e['es']})?",
        fuente=e["id"],
        opciones=opciones,
        correcta=correcta,
        audio=forma,
        explicacion=(
            f"{_con_articulo(e)} · {e['def']} · {e['plural']} · {e.get('defPl', '')}"
        ).strip(" ·"),
    )


def _gen_conjugar(azar, elementos, pool, indice) -> Ejercicio | None:
    candidatos = [e for e in elementos if e.get("inf")]
    if not candidatos:
        return None
    e = azar.choice(candidatos)
    forma, etiqueta = azar.choice(
        [
            (e["pres"], "presente"),
            (e["pas"], "pretérito (pasado)"),
            (e["perf"], "perfecto (con har)"),
        ]
    )
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.CONJUGAR,
        enunciado=f"Escribe el {etiqueta} de «å {e['inf']}» ({e['es']}).",
        fuente=e["id"],
        respuesta=forma,
        audio=forma,
        pista=f"Grupo {e['grupo']}",
        explicacion=(
            f"å {e['inf']} · {e['pres']} · {e['pas']} · {e['perf']}. " + (e.get("nota") or "")
        ).strip(),
    )


def _gen_pronunciar(azar, sonidos, indice) -> Ejercicio | None:
    if not sonidos:
        return None
    s = azar.choice(sonidos)
    ejemplo = azar.choice(s["ejemplos"])
    return Ejercicio(
        id=f"e{indice}",
        tipo=T.PRONUNCIAR,
        enunciado=f"Escucha y repite. Letra: {s['letra']}",
        contexto=ejemplo["no"],
        fuente=s["id"],
        audio=ejemplo["no"],
        pista=ejemplo["pron"],
        explicacion=f"{s['como']} {s['consejo']}",
        datos={"letra": s["letra"], "es": ejemplo["es"]},
    )


def _gen_dialogo(azar, dialogo, indice, pool) -> list[Ejercicio]:
    """Un ejercicio por cada línea que el usuario tiene que completar."""
    salida = []
    for numero, hueco in enumerate(dialogo["huecos"]):
        linea = dialogo["lineas"][hueco]
        otras = [other["no"] for d in pool for other in d["lineas"] if other["no"] != linea["no"]]
        azar.shuffle(otras)
        opciones, correcta = _mezclar_opciones(azar, linea["no"], otras[:8])
        previa = dialogo["lineas"][hueco - 1] if hueco > 0 else None
        salida.append(
            Ejercicio(
                id=f"e{indice}-{numero}",
                tipo=T.DIALOGO,
                enunciado=f"{dialogo['titulo']}: ¿qué dices ahora?",
                contexto=(
                    f"{previa['quien']}: {previa['no']}\n({previa['es']})"
                    if previa
                    else dialogo["situacion"]
                ),
                fuente=dialogo["id"],
                opciones=opciones,
                correcta=correcta,
                audio=linea["no"],
                pista=linea["es"],
                explicacion=f"«{linea['no']}» = {linea['es']}. Aproximación: «{linea['pron']}».",
                datos={"situacion": dialogo["situacion"], "titulo": dialogo["titulo"]},
            )
        )
    return salida


GENERADORES = {
    T.PAREJAS: _gen_parejas,
    T.OPCION: _gen_opcion,
    T.ESCUCHAR_OPCION: _gen_escuchar_opcion,
    T.ESCUCHAR_ESCRIBIR: _gen_escuchar_escribir,
    T.ORDENAR: _gen_ordenar,
    T.COMPLETAR: _gen_completar,
    T.ERROR: _gen_error,
    T.GENERO: _gen_genero,
    T.FORMA_NOMINAL: _gen_forma_nominal,
    T.CONJUGAR: _gen_conjugar,
}


def ejemplos_de_gramatica(lexico: Lexico, claves: tuple[str, ...]) -> list[dict]:
    """Convierte los ejemplos de una regla en material practicable.

    Cada regla de `gramatica.json` trae dos o más ejemplos con su traducción y
    su pronunciación. Son frases reales, así que sirven igual que las del
    vocabulario para traducir, ordenar o completar.
    """
    salida = []
    for clave in claves:
        regla = lexico.gramatica_por_clave(clave)
        if not regla:
            continue
        for numero, ejemplo in enumerate(regla["ejemplos"]):
            if "→" in ejemplo["no"] or not ejemplo.get("es"):
                continue
            salida.append(
                {
                    "id": f"{regla['id']}-{numero}",
                    "no": ejemplo["no"],
                    "es": ejemplo["es"],
                    "pron": ejemplo.get("pron", ""),
                    "tema": "gramatica",
                    "nivel": regla["nivel"],
                    "nota": regla["regla"] or regla["explicacion"],
                }
            )
    return salida


def ejemplos_de_sonidos(lexico: Lexico, ids: tuple[str, ...]) -> list[dict]:
    """Convierte los ejemplos de cada sonido en palabras practicables."""
    salida = []
    for sonido in lexico.sonidos:
        if ids and sonido["id"] not in ids:
            continue
        for numero, ejemplo in enumerate(sonido["ejemplos"]):
            salida.append(
                {
                    "id": f"{sonido['id']}-{numero}",
                    "no": ejemplo["no"],
                    "es": ejemplo["es"],
                    "pron": ejemplo.get("pron", ""),
                    "tema": "sonidos",
                    "nivel": sonido.get("nivel", "cero"),
                    "nota": f"{sonido['letra']}: {sonido['como']}",
                }
            )
    return salida


def lineas_de_dialogo(lexico: Lexico, id_dialogo: str) -> list[dict]:
    """Cada línea de un diálogo también es material practicable."""
    dialogo = next((d for d in lexico.dialogos if d["id"] == id_dialogo), None)
    if not dialogo:
        return []
    return [
        {
            "id": f"{dialogo['id']}-l{numero}",
            "no": linea["no"],
            "es": linea["es"],
            "pron": linea.get("pron", ""),
            "tema": dialogo["tema"],
            "nivel": dialogo["nivel"],
            "nota": f"De la conversación «{dialogo['titulo']}».",
        }
        for numero, linea in enumerate(dialogo["lineas"])
    ]


def material(lexico: Lexico, leccion: Leccion) -> list[dict]:
    """Los elementos del léxico que le tocan a esta lección.

    Los `ids` explícitos se SUMAN a la selección por tema y nivel, no la
    reemplazan: una lección que se centra en dos verbos concretos igual
    necesita frases donde esos verbos aparezcan.
    """
    salida: list[dict] = []
    for fuente in leccion.fuentes:
        if fuente == "sonidos":
            salida.extend(ejemplos_de_sonidos(lexico, leccion.sonidos))
            continue
        salida.extend(lexico.filtrar(fuente, temas=leccion.temas, niveles=leccion.niveles))
        if leccion.ids:
            salida.extend(lexico.filtrar(fuente, ids=leccion.ids))
    # Las reglas de gramática y el diálogo de la lección también aportan.
    salida.extend(ejemplos_de_gramatica(lexico, leccion.gramatica))
    if leccion.dialogo:
        salida.extend(lineas_de_dialogo(lexico, leccion.dialogo))
    if not salida and leccion.ids:
        salida = [e for e in (lexico.por_id(i) for i in leccion.ids) if e]
    vistos, unicos = set(), []
    for e in salida:
        if e["id"] not in vistos:
            vistos.add(e["id"])
            unicos.append(e)
    return unicos


def generar(lexico: Lexico, leccion: Leccion, semilla: int | None = None) -> list[Ejercicio]:
    """Arma los ejercicios de una lección.

    Reparte los tipos declarados en la lección y salta los que no puedan
    construirse con el material disponible, en vez de inventar contenido.
    """
    azar = random.Random(f"{leccion.clave}-{semilla}" if semilla is not None else None)
    elementos = material(lexico, leccion)
    sonidos = [s for s in lexico.sonidos if not leccion.sonidos or s["id"] in leccion.sonidos]
    dialogo = next((d for d in lexico.dialogos if d["id"] == leccion.dialogo), None)

    ejercicios: list[Ejercicio] = []
    if dialogo and T.DIALOGO in leccion.tipos:
        ejercicios.extend(_gen_dialogo(azar, dialogo, len(ejercicios), lexico.dialogos))

    tipos = [t for t in leccion.tipos if t is not T.DIALOGO]
    intentos = 0
    while len(ejercicios) < leccion.ejercicios and intentos < leccion.ejercicios * 20:
        # El tipo rota con los INTENTOS, no con los ejercicios ya hechos. Si
        # rotara con los hechos, un tipo que no se puede construir con este
        # material (por ejemplo «ordenar» cuando solo hay palabras sueltas)
        # bloquearía el ciclo entero y la lección se quedaría casi vacía.
        tipo = tipos[intentos % len(tipos)] if tipos else None
        intentos += 1
        if tipo is None:
            break
        nuevo = None
        if tipo is T.PRONUNCIAR:
            nuevo = _gen_pronunciar(azar, sonidos, len(ejercicios))
        elif tipo in (T.TRADUCIR_ES_NO, T.TRADUCIR_NO_ES) and elementos:
            nuevo = _gen_traducir(
                azar, elementos, elementos, len(ejercicios), tipo is T.TRADUCIR_ES_NO
            )
        elif tipo in GENERADORES and elementos:
            nuevo = GENERADORES[tipo](azar, elementos, elementos, len(ejercicios))
        if nuevo is not None and not _repetido(ejercicios, nuevo):
            ejercicios.append(nuevo)
    return ejercicios


def _repetido(previos: list[Ejercicio], nuevo: Ejercicio) -> bool:
    """Evita preguntar dos veces lo MISMO dentro de la misma lección.

    Compara también el enunciado: preguntar el presente y luego el pretérito
    del mismo verbo son dos ejercicios distintos, no una repetición.
    """
    firma = (nuevo.tipo, nuevo.fuente, nuevo.enunciado, nuevo.contexto)
    return any((p.tipo, p.fuente, p.enunciado, p.contexto) == firma for p in previos)
