"""Carga y valida los datos lingüísticos del curso.

Todo el noruego del curso vive en los JSON de ``noruego/lexico/``. Se pueden
abrir y corregir sin saber programar, y el validador avisa cuando algo quedó
mal antes de que llegue a la aplicación.

Regla del proyecto: **no se inventa noruego**. Si una palabra, una forma o una
traducción está en duda, se marca con ``"revisar": true`` en el JSON y el
validador la reporta, en vez de presentarla como un hecho.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .dominio import TEMAS_POR_CLAVE, Genero, GrupoVerbal, Nivel

DIRECTORIO: Path = Path(__file__).parent / "lexico"

#: Qué archivo trae cada tipo de dato y qué campos son obligatorios en él.
ESQUEMA: dict[str, tuple[str, ...]] = {
    "sustantivos": ("id", "no", "genero", "def", "es", "tema", "nivel", "pron"),
    "verbos": ("id", "inf", "pres", "pas", "perf", "grupo", "es", "tema", "nivel", "pron"),
    "adjetivos": ("id", "base", "neutro", "plural", "es", "nivel", "pron"),
    "frases": ("id", "no", "es", "tema", "nivel", "pron"),
    "numeros": ("id", "no", "valor", "es", "nivel", "pron"),
    "sonidos": ("id", "letra", "nombre", "como", "ejemplos", "consejo"),
    "gramatica": ("id", "clave", "titulo", "nivel", "explicacion", "ejemplos", "error"),
    "dialogos": ("id", "titulo", "nivel", "tema", "situacion", "lineas", "huecos"),
}


class LexicoInvalido(Exception):
    """Los datos del curso tienen un problema que impide usarlos."""


@dataclass(frozen=True)
class Lexico:
    """Todos los datos lingüísticos del curso, ya cargados."""

    sustantivos: tuple[dict, ...] = ()
    verbos: tuple[dict, ...] = ()
    adjetivos: tuple[dict, ...] = ()
    frases: tuple[dict, ...] = ()
    numeros: tuple[dict, ...] = ()
    sonidos: tuple[dict, ...] = ()
    gramatica: tuple[dict, ...] = ()
    dialogos: tuple[dict, ...] = ()
    notas: dict[str, str] = field(default_factory=dict)

    @property
    def todo(self) -> dict[str, tuple[dict, ...]]:
        return {
            "sustantivos": self.sustantivos,
            "verbos": self.verbos,
            "adjetivos": self.adjetivos,
            "frases": self.frases,
            "numeros": self.numeros,
            "sonidos": self.sonidos,
            "gramatica": self.gramatica,
            "dialogos": self.dialogos,
        }

    def __len__(self) -> int:
        return sum(len(v) for v in self.todo.values())

    def por_id(self, identificador: str) -> dict | None:
        """Busca cualquier elemento por su id."""
        for grupo in self.todo.values():
            for elemento in grupo:
                if elemento["id"] == identificador:
                    return elemento
        return None

    def gramatica_por_clave(self, clave: str) -> dict | None:
        return next((g for g in self.gramatica if g["clave"] == clave), None)

    def filtrar(
        self,
        tipo: str,
        temas: tuple[str, ...] = (),
        niveles: tuple[str, ...] = (),
        ids: tuple[str, ...] = (),
    ) -> tuple[dict, ...]:
        """Selecciona elementos de un tipo por tema, nivel o lista de ids."""
        grupo = self.todo.get(tipo, ())
        salida = []
        for elemento in grupo:
            if ids and elemento["id"] not in ids:
                continue
            if temas and elemento.get("tema") not in temas:
                continue
            if niveles and elemento.get("nivel") not in niveles:
                continue
            salida.append(elemento)
        return tuple(salida)

    def resumen(self) -> str:
        lineas = [f"Léxico del curso — {len(self)} elementos"]
        for tipo, grupo in self.todo.items():
            lineas.append(f"  {tipo:<14}{len(grupo):>5}")
        return "\n".join(lineas)

    def conteo_por_nivel(self) -> dict[str, int]:
        conteo: Counter[str] = Counter()
        for grupo in self.todo.values():
            for elemento in grupo:
                if "nivel" in elemento:
                    conteo[elemento["nivel"]] += 1
        return dict(conteo)


def cargar(directorio: Path | None = None) -> Lexico:
    """Lee todos los JSON del léxico. Lanza :class:`LexicoInvalido` si algo falla."""
    carpeta = directorio or DIRECTORIO
    if not carpeta.is_dir():
        raise LexicoInvalido(f"No existe la carpeta del léxico: {carpeta}")

    grupos: dict[str, tuple[dict, ...]] = {}
    notas: dict[str, str] = {}
    for tipo, obligatorios in ESQUEMA.items():
        archivo = carpeta / f"{tipo}.json"
        if not archivo.is_file():
            grupos[tipo] = ()
            continue
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LexicoInvalido(f"{archivo.name}: el JSON está mal escrito ({exc})") from exc
        elementos = datos.get("palabras", [])
        for elemento in elementos:
            faltan = [c for c in obligatorios if c not in elemento or elemento[c] == ""]
            # «valor» puede ser 0 y «es» puede ser "0": no cuentan como vacíos.
            faltan = [c for c in faltan if elemento.get(c) not in (0, "0")]
            if elemento.get("soloPlural"):
                # «penger» (dinero) solo existe en plural: no tiene género ni
                # forma definida singular, y eso no es un error del dato.
                faltan = [c for c in faltan if c not in ("genero", "def")]
            if faltan:
                raise LexicoInvalido(
                    f"{archivo.name} · {elemento.get('id', '?')}: faltan {', '.join(faltan)}"
                )
        grupos[tipo] = tuple(elementos)
        notas[tipo] = datos.get("nota", "")

    lexico = Lexico(**grupos, notas=notas)  # type: ignore[arg-type]
    repetidos = [
        i for i, c in Counter(e["id"] for g in lexico.todo.values() for e in g).items() if c > 1
    ]
    if repetidos:
        raise LexicoInvalido(f"Ids repetidos: {', '.join(sorted(repetidos))}")
    return lexico


def revisar(lexico: Lexico) -> list[str]:
    """Problemas de calidad que no impiden usar el curso pero lo empeoran."""
    avisos: list[str] = []
    niveles = {n.value for n in Nivel}

    for s in lexico.sustantivos:
        if not s["genero"] and not s.get("soloPlural"):
            avisos.append(f"{s['id']}: sin género y sin marcar como «soloPlural»")
        if s["genero"] and s["genero"] not in {g.value for g in Genero}:
            avisos.append(f"{s['id']}: género «{s['genero']}» no es en/ei/et")
        if s["genero"] == "et" and s["def"] and not s["def"].endswith(("et", "e")):
            avisos.append(f"{s['id']}: un neutro debería hacer el definido en -et")
    for v in lexico.verbos:
        if v["grupo"] not in {g.value for g in GrupoVerbal}:
            avisos.append(f"{v['id']}: grupo verbal «{v['grupo']}» desconocido")
        if not v["perf"].startswith("har "):
            avisos.append(f"{v['id']}: el perfecto debería empezar por «har»")
    for grupo, elementos in lexico.todo.items():
        for e in elementos:
            if e.get("nivel") and e["nivel"] not in niveles:
                avisos.append(f"{e['id']}: nivel «{e['nivel']}» no existe")
            if e.get("tema") and e["tema"] not in TEMAS_POR_CLAVE:
                avisos.append(f"{e['id']}: tema «{e['tema']}» no existe")
            if e.get("revisar"):
                avisos.append(f"{e['id']} ({grupo}): marcado para revisión lingüística")
            if "pron" in e and not e["pron"].strip():
                avisos.append(f"{e['id']}: sin aproximación de pronunciación")
    for d in lexico.dialogos:
        for indice in d["huecos"]:
            if not 0 <= indice < len(d["lineas"]):
                avisos.append(f"{d['id']}: el hueco {indice} no existe en el diálogo")
        if not d["huecos"]:
            avisos.append(f"{d['id']}: no tiene ninguna línea para completar")
    for g in lexico.gramatica:
        if len(g["ejemplos"]) < 2:
            avisos.append(f"{g['id']}: una regla necesita al menos dos ejemplos")
        if not g.get("error", "").strip():
            avisos.append(f"{g['id']}: no dice cuál es el error típico")
    return avisos
