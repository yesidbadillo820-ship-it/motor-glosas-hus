"""Carga, valida y consulta el banco de preguntas.

El banco vive en archivos JSON dentro de ``icfes/banco/``, uno por área. Están
en JSON a propósito: se pueden abrir, leer y corregir sin saber programar, y
se pueden ir agregando preguntas de a poco.

**Sobre las preguntas:** son preguntas de práctica escritas para este sistema,
siguiendo la estructura, las competencias y los componentes que evalúa el
Saber 11. **No son preguntas del examen real** (esas son del ICFES y no se
pueden copiar). Para practicar con preguntas oficiales están los cuadernillos
de práctica que el ICFES publica gratis en su página; este banco sirve para el
entrenamiento diario y para el cuaderno de errores.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .dominio import (
    AREAS,
    ORDEN_AREAS,
    Area,
    Dificultad,
    Pregunta,
)

#: Una explicación que diga "la opción B" queda mentirosa apenas se barajan las
#: opciones. Esta expresión detecta esas menciones.
MENCION_DE_LETRA = re.compile(r"opci[oó]n(?:es)?\s+[A-D]\b")

#: Opciones que traen su propia letra escrita ("A) ...") tampoco resisten el barajado.
ETIQUETA_AL_INICIO = re.compile(r"^\s*[A-Da-d][).\-]\s")

#: Carpeta donde viven los archivos JSON del banco.
DIRECTORIO_BANCO: Path = Path(__file__).parent / "banco"


class BancoInvalido(Exception):
    """El banco tiene un problema que impide usarlo con confianza."""


def _pregunta_desde_json(cruda: dict, area: Area, origen: Path) -> Pregunta:
    """Convierte un diccionario del JSON en una :class:`Pregunta` validada."""
    faltan = [
        campo
        for campo in (
            "id",
            "competencia",
            "componente",
            "tema",
            "dificultad",
            "enunciado",
            "opciones",
            "correcta",
            "explicacion",
        )
        if campo not in cruda
    ]
    if faltan:
        raise BancoInvalido(f"{origen.name}: a una pregunta le faltan campos: {', '.join(faltan)}")
    try:
        return Pregunta(
            id=str(cruda["id"]),
            area=area,
            competencia=str(cruda["competencia"]),
            componente=str(cruda["componente"]),
            tema=str(cruda["tema"]),
            dificultad=Dificultad(int(cruda["dificultad"])),
            enunciado=str(cruda["enunciado"]),
            opciones=tuple(str(o) for o in cruda["opciones"]),
            correcta=int(cruda["correcta"]),
            explicacion=str(cruda["explicacion"]),
            trampa=str(cruda.get("trampa", "")),
            contexto=str(cruda.get("contexto", "")),
        )
    except (ValueError, TypeError) as exc:
        raise BancoInvalido(f"{origen.name} · pregunta {cruda.get('id', '?')}: {exc}") from exc


@dataclass(frozen=True)
class Banco:
    """Todas las preguntas disponibles para practicar."""

    preguntas: tuple[Pregunta, ...]

    def __len__(self) -> int:
        return len(self.preguntas)

    def por_area(self, area: Area) -> tuple[Pregunta, ...]:
        """Las preguntas de un área."""
        return tuple(p for p in self.preguntas if p.area is area)

    def por_id(self, id_pregunta: str) -> Pregunta | None:
        """Busca una pregunta por su identificador."""
        return next((p for p in self.preguntas if p.id == id_pregunta), None)

    def filtrar(
        self,
        area: Area | None = None,
        competencia: str | None = None,
        componente: str | None = None,
        tema: str | None = None,
        dificultad_maxima: int | None = None,
        dificultad_minima: int | None = None,
        excluir: set[str] | None = None,
    ) -> tuple[Pregunta, ...]:
        """Filtra el banco por los criterios que se le pasen."""
        excluir = excluir or set()
        seleccion = []
        for p in self.preguntas:
            if area is not None and p.area is not area:
                continue
            if competencia is not None and p.competencia != competencia:
                continue
            if componente is not None and p.componente != componente:
                continue
            if tema is not None and p.tema.lower() != tema.lower():
                continue
            if dificultad_maxima is not None and p.dificultad.value > dificultad_maxima:
                continue
            if dificultad_minima is not None and p.dificultad.value < dificultad_minima:
                continue
            if p.id in excluir:
                continue
            seleccion.append(p)
        return tuple(seleccion)

    def muestra(
        self,
        cantidad: int,
        area: Area | None = None,
        semilla: int | None = None,
        excluir: set[str] | None = None,
        **filtros: object,
    ) -> tuple[Pregunta, ...]:
        """Escoge preguntas al azar, repartidas entre las competencias del área.

        No es un ``random.sample`` a secas: reparte primero entre competencias
        para que una práctica de 12 preguntas no salga toda de la misma
        competencia. Si no alcanzan las preguntas, devuelve las que haya (sin
        repetir) en vez de fallar.
        """
        if cantidad <= 0:
            return ()
        azar = random.Random(semilla)
        disponibles = list(self.filtrar(area=area, excluir=excluir, **filtros))  # type: ignore[arg-type]
        if not disponibles:
            return ()
        if len(disponibles) <= cantidad:
            azar.shuffle(disponibles)
            return tuple(disponibles)

        por_competencia: dict[str, list[Pregunta]] = {}
        for p in disponibles:
            por_competencia.setdefault(p.competencia, []).append(p)
        for grupo in por_competencia.values():
            azar.shuffle(grupo)

        escogidas: list[Pregunta] = []
        grupos = sorted(por_competencia.values(), key=len, reverse=True)
        while len(escogidas) < cantidad:
            movio = False
            for grupo in grupos:
                if grupo and len(escogidas) < cantidad:
                    escogidas.append(grupo.pop())
                    movio = True
            if not movio:
                break
        azar.shuffle(escogidas)
        return tuple(escogidas)

    def temas(self, area: Area | None = None) -> tuple[str, ...]:
        """Los temas que cubre el banco, ordenados alfabéticamente."""
        return tuple(sorted({p.tema for p in self.filtrar(area=area)}))

    def conteo_por_area(self) -> dict[Area, int]:
        """Cuántas preguntas hay de cada área."""
        return {a: len(self.por_area(a)) for a in ORDEN_AREAS}

    def cobertura(self) -> dict[str, dict[str, int]]:
        """Cuántas preguntas hay por competencia, para ver qué falta escribir."""
        salida: dict[str, dict[str, int]] = {}
        for area in ORDEN_AREAS:
            conteo = Counter(p.competencia for p in self.por_area(area))
            salida[area.nombre] = {c: conteo.get(c, 0) for c in AREAS[area].competencias}
        return salida

    def resumen(self) -> str:
        """Un resumen en texto de lo que hay en el banco."""
        lineas = [f"Banco de preguntas — {len(self)} preguntas en total", ""]
        for area, cuantas in self.conteo_por_area().items():
            lineas.append(f"  {AREAS[area].nombre:<24} {cuantas:>4} preguntas")
        return "\n".join(lineas)


def barajar_opciones(
    pregunta: Pregunta,
    semilla: int | None = None,
) -> tuple[tuple[str, ...], int, tuple[int, ...]]:
    """Revuelve las opciones de una pregunta y dice dónde quedó la correcta.

    Se usa SIEMPRE que se muestra una pregunta. Sin esto, quien practica dos
    veces con la misma pregunta termina recordando la posición de la respuesta
    en vez del razonamiento, y el banco deja de medir.

    Returns:
        Las opciones revueltas, el índice (0 a 3) de la correcta **en el orden
        mostrado**, y el orden usado. El orden hace falta para traducir la
        letra que marcó el estudiante al índice original de la pregunta:
        ``original = orden[marcada]``.
    """
    azar = random.Random(f"{pregunta.id}-{semilla}" if semilla is not None else None)
    orden = list(range(len(pregunta.opciones)))
    azar.shuffle(orden)
    opciones = tuple(pregunta.opciones[i] for i in orden)
    return opciones, orden.index(pregunta.correcta), tuple(orden)


def cargar_banco(directorio: Path | None = None) -> Banco:
    """Lee todos los archivos JSON del banco y devuelve las preguntas.

    Args:
        directorio: carpeta con los JSON. Por defecto, ``icfes/banco/``.

    Raises:
        BancoInvalido: si algún archivo está mal armado o hay ids repetidos.
    """
    carpeta = directorio or DIRECTORIO_BANCO
    if not carpeta.is_dir():
        raise BancoInvalido(f"No existe la carpeta del banco: {carpeta}")

    preguntas: list[Pregunta] = []
    vistos: dict[str, str] = {}
    for archivo in sorted(carpeta.glob("*.json")):
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BancoInvalido(f"{archivo.name}: el JSON está mal escrito ({exc})") from exc
        try:
            area = Area(datos["area"])
        except (KeyError, ValueError) as exc:
            raise BancoInvalido(f"{archivo.name}: el campo 'area' falta o no es válido") from exc
        for cruda in datos.get("preguntas", []):
            pregunta = _pregunta_desde_json(cruda, area, archivo)
            if pregunta.id in vistos:
                raise BancoInvalido(
                    f"El id «{pregunta.id}» está repetido ({vistos[pregunta.id]} y {archivo.name})"
                )
            vistos[pregunta.id] = archivo.name
            preguntas.append(pregunta)
    return Banco(preguntas=tuple(preguntas))


def revisar_banco(banco: Banco) -> list[str]:
    """Lista los problemas de calidad del banco, sin lanzar excepciones.

    Estos no impiden usar el banco, pero sí bajan la calidad del estudio:
    opciones repetidas, respuestas siempre en la misma letra, competencias sin
    preguntas, explicaciones demasiado cortas.
    """
    avisos: list[str] = []

    for p in banco.preguntas:
        limpias = [o.strip().lower() for o in p.opciones]
        if len(set(limpias)) != len(limpias):
            avisos.append(f"{p.id}: tiene dos opciones iguales")
        if any(not o for o in limpias):
            avisos.append(f"{p.id}: tiene una opción vacía")
        if len(p.explicacion.strip()) < 40:
            avisos.append(f"{p.id}: la explicación es demasiado corta para enseñar algo")
        if not p.trampa.strip():
            avisos.append(f"{p.id}: no dice cuál es la trampa (el distractor que más atrae)")
        if MENCION_DE_LETRA.search(f"{p.explicacion} {p.trampa}"):
            avisos.append(
                f"{p.id}: la explicación nombra una letra de opción, pero las opciones se "
                "barajan en cada práctica. Hay que nombrar el contenido, no la letra"
            )
        if any(ETIQUETA_AL_INICIO.match(o) for o in p.opciones):
            avisos.append(
                f"{p.id}: alguna opción viene con su letra escrita adentro; eso se rompe al barajar"
            )

    for area in ORDEN_AREAS:
        if not banco.por_area(area):
            avisos.append(f"{AREAS[area].nombre}: no tiene ninguna pregunta")

    for nombre_area, competencias in banco.cobertura().items():
        for competencia, cuantas in competencias.items():
            if cuantas == 0:
                avisos.append(f"{nombre_area}: la competencia «{competencia}» no tiene preguntas")

    return avisos
