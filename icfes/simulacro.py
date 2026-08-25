"""Simulacros con la estructura y el tiempo reales del examen.

Un simulacro sirve para dos cosas que la práctica suelta no da:

1. **Entrenar el reloj.** En la primera sesión hay 2 minutos y 15 segundos por
   pregunta; en la segunda, 2 minutos y 1 segundo. Quien no ha entrenado eso
   se queda sin tiempo aunque sepa el tema.
2. **Entrenar el cansancio.** Cuatro horas y media seguidas cansan, y los
   errores de la última hora no son errores de conocimiento.

**Sobre el tamaño:** una sesión real trae 120 o 134 preguntas. Mientras el
banco no tenga esa cantidad, el simulacro se arma **a escala**: conserva la
proporción exacta de cada área y los mismos segundos por pregunta, pero con
menos preguntas. El resultado dice siempre a qué escala se hizo, para que
nadie confunda un simulacro corto con la jornada completa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .banco import Banco
from .dominio import (
    AREAS,
    ORDEN_AREAS,
    Area,
    Pregunta,
    preguntas_de_sesion,
    segundos_por_pregunta,
)
from .puntaje import (
    describir_estimacion,
    estimar_puntaje_area,
    nivel_ingles,
    puntaje_global,
    semaforo_area,
)


class TipoSimulacro(StrEnum):
    """Qué tan grande es el simulacro."""

    SESION_1 = "sesion_1"
    SESION_2 = "sesion_2"
    COMPLETO = "completo"
    AREA = "area"

    @property
    def etiqueta(self) -> str:
        return {
            "sesion_1": "Sesión 1 (Lectura Crítica completa + las demás áreas)",
            "sesion_2": "Sesión 2 (Inglés completo + las demás áreas)",
            "completo": "Examen completo (las dos sesiones)",
            "area": "Simulacro de una sola área",
        }[self.value]


@dataclass(frozen=True)
class Simulacro:
    """Un simulacro listo para presentar."""

    tipo: TipoSimulacro
    preguntas: tuple[Pregunta, ...]
    reparto: dict[Area, int]
    segundos_totales: int
    escala: float
    reparto_oficial: dict[Area, int]

    @property
    def total(self) -> int:
        return len(self.preguntas)

    @property
    def minutos(self) -> int:
        return round(self.segundos_totales / 60)

    @property
    def es_tamano_real(self) -> bool:
        """¿Tiene todas las preguntas que trae el examen de verdad?"""
        return self.escala >= 0.999

    @property
    def aviso(self) -> str:
        """La advertencia honesta que hay que mostrar antes de empezar."""
        if self.es_tamano_real:
            return "Simulacro de tamaño real. Sin celular y sin pausas largas."
        oficial = sum(self.reparto_oficial.values())
        return (
            f"Simulacro a escala {self.escala * 100:.0f} %: {self.total} preguntas en vez de "
            f"{oficial}, con la misma proporción por área y los mismos segundos por pregunta. "
            "Entrena el ritmo, pero NO entrena el cansancio de la jornada completa."
        )

    def segundos_por_pregunta(self) -> float:
        """El tiempo promedio disponible para cada pregunta."""
        return self.segundos_totales / self.total if self.total else 0.0


def _reparto_oficial(tipo: TipoSimulacro, area: Area | None) -> dict[Area, int]:
    """Cuántas preguntas de cada área trae el examen real en ese formato."""
    if tipo is TipoSimulacro.AREA:
        if area is None:
            raise ValueError("Un simulacro de área necesita saber cuál área")
        return {area: AREAS[area].preguntas}
    if tipo is TipoSimulacro.SESION_1:
        return preguntas_de_sesion(1)
    if tipo is TipoSimulacro.SESION_2:
        return preguntas_de_sesion(2)
    return {a: AREAS[a].preguntas for a in ORDEN_AREAS}


def _segundos_oficiales(tipo: TipoSimulacro, area: Area | None) -> float:
    """Segundos por pregunta según la sesión del examen que se está imitando."""
    if tipo is TipoSimulacro.SESION_1:
        return segundos_por_pregunta(1)
    if tipo is TipoSimulacro.SESION_2:
        return segundos_por_pregunta(2)
    if tipo is TipoSimulacro.COMPLETO:
        return (segundos_por_pregunta(1) + segundos_por_pregunta(2)) / 2
    # Un simulacro de una sola área usa el ritmo de la sesión donde más pesa.
    if area is not None and AREAS[area].preguntas_sesion_1 >= AREAS[area].preguntas_sesion_2:
        return segundos_por_pregunta(1)
    return segundos_por_pregunta(2)


def armar_simulacro(
    banco: Banco,
    tipo: TipoSimulacro = TipoSimulacro.SESION_1,
    area: Area | None = None,
    semilla: int | None = None,
    maximo: int | None = None,
) -> Simulacro:
    """Arma un simulacro con la estructura del examen real.

    Args:
        banco: el banco de preguntas.
        tipo: sesión 1, sesión 2, examen completo o un área sola.
        area: obligatorio si el tipo es ``AREA``.
        semilla: para poder repetir el mismo simulacro (útil en pruebas).
        maximo: tope de preguntas. Si el banco no alcanza para el tamaño real,
            el simulacro se reduce solo, conservando las proporciones.
    """
    oficial = _reparto_oficial(tipo, area)
    disponible = {a: len(banco.por_area(a)) for a in oficial}
    sin_preguntas = [AREAS[a].nombre for a, cuantas in disponible.items() if cuantas == 0]
    if sin_preguntas:
        raise ValueError(f"El banco no tiene preguntas de: {', '.join(sin_preguntas)}")

    # La escala es la del área más limitada: así se mantiene la proporción.
    escala = min(min(disponible[a] / oficial[a], 1.0) for a in oficial)
    if maximo is not None and maximo > 0:
        escala = min(escala, maximo / sum(oficial.values()))

    reparto = {a: max(1, round(oficial[a] * escala)) for a in oficial}
    reparto = {a: min(cuantas, disponible[a]) for a, cuantas in reparto.items()}

    preguntas: list[Pregunta] = []
    for indice, (a, cuantas) in enumerate(reparto.items()):
        semilla_area = None if semilla is None else semilla + indice
        preguntas.extend(banco.muestra(cuantas, area=a, semilla=semilla_area))

    segundos = round(sum(reparto.values()) * _segundos_oficiales(tipo, area))
    escala_real = sum(reparto.values()) / sum(oficial.values())
    return Simulacro(
        tipo=tipo,
        preguntas=tuple(preguntas),
        reparto=reparto,
        segundos_totales=segundos,
        escala=escala_real,
        reparto_oficial=oficial,
    )


@dataclass(frozen=True)
class ResultadoArea:
    """Cómo salió un área dentro de un simulacro."""

    area: Area
    correctas: int
    total: int
    puntaje: int

    @property
    def porcentaje(self) -> float:
        return self.correctas / self.total * 100 if self.total else 0.0


@dataclass(frozen=True)
class ResultadoSimulacro:
    """El resultado de un simulacro, ya calificado."""

    fecha: date
    tipo: TipoSimulacro
    por_area: dict[Area, ResultadoArea]
    por_competencia: dict[str, tuple[int, int]]
    segundos_usados: int | None
    escala: float

    @property
    def correctas(self) -> int:
        return sum(r.correctas for r in self.por_area.values())

    @property
    def total(self) -> int:
        return sum(r.total for r in self.por_area.values())

    @property
    def tiene_todas_las_areas(self) -> bool:
        """Solo con las cinco áreas se puede calcular un puntaje global."""
        return all(a in self.por_area for a in ORDEN_AREAS)

    @property
    def global_estimado(self) -> int | None:
        """El puntaje global estimado, o ``None`` si faltan áreas."""
        if not self.tiene_todas_las_areas:
            return None
        return puntaje_global({a: r.puntaje for a, r in self.por_area.items()})

    def informe(self) -> str:
        """El informe que se le muestra al estudiante al terminar."""
        lineas = [
            f"RESULTADO DEL SIMULACRO — {self.tipo.etiqueta}",
            f"Fecha: {self.fecha:%d/%m/%Y}   ·   {self.correctas} de {self.total} correctas",
        ]
        if self.escala < 0.999:
            lineas.append(
                f"Simulacro a escala {self.escala * 100:.0f} % del examen real: "
                "sirve para comparar contigo mismo, no para anunciar un puntaje."
            )
        if self.segundos_usados:
            por_pregunta = self.segundos_usados / self.total if self.total else 0
            lineas.append(
                f"Tiempo usado: {self.segundos_usados // 60} minutos "
                f"({por_pregunta:.0f} segundos por pregunta)."
            )
        lineas += ["", f"  {'Área':<24}{'Bien':>6}{'De':>5}{'%':>7}{'Puntaje':>9}  Nivel"]
        for area in ORDEN_AREAS:
            r = self.por_area.get(area)
            if r is None:
                continue
            etiqueta, _ = semaforo_area(r.puntaje)
            lineas.append(
                f"  {AREAS[area].nombre:<24}{r.correctas:>6}{r.total:>5}"
                f"{r.porcentaje:>6.0f}%{r.puntaje:>9}  {etiqueta}"
            )
        if Area.INGLES in self.por_area:
            nivel, descripcion = nivel_ingles(self.por_area[Area.INGLES].puntaje)
            lineas.append(f"  Inglés — nivel estimado {nivel}: {descripcion}")

        glob = self.global_estimado
        if glob is not None:
            lineas += ["", f"  PUNTAJE GLOBAL ESTIMADO: {glob} de 500"]
        else:
            faltan = [AREAS[a].nombre for a in ORDEN_AREAS if a not in self.por_area]
            lineas += [
                "",
                "  No se calcula puntaje global: este simulacro no incluye "
                + ", ".join(faltan)
                + ".",
            ]

        flojas = sorted(
            (
                (competencia, bien / total)
                for competencia, (bien, total) in self.por_competencia.items()
                if total >= 2
            ),
            key=lambda par: par[1],
        )[:3]
        if flojas:
            lineas += ["", "  COMPETENCIAS MÁS FLOJAS (por ahí empieza el próximo repaso):"]
            lineas += [f"    · {c} — {p * 100:.0f} % de acierto" for c, p in flojas]
        return "\n".join(lineas)


def calificar_simulacro(
    simulacro: Simulacro,
    respuestas: dict[str, int],
    fecha: date,
    segundos_usados: int | None = None,
) -> ResultadoSimulacro:
    """Califica un simulacro.

    Args:
        simulacro: el simulacro presentado.
        respuestas: por cada id de pregunta, la opción marcada (0 a 3). Las
            preguntas que no estén en el diccionario cuentan como no
            respondidas, que es lo mismo que falladas en el examen real.
        fecha: el día en que se presentó.
        segundos_usados: cuánto se demoró, si se midió.
    """
    aciertos: dict[Area, int] = {}
    totales: dict[Area, int] = {}
    competencias: dict[str, list[int]] = {}

    for pregunta in simulacro.preguntas:
        totales[pregunta.area] = totales.get(pregunta.area, 0) + 1
        marcada = respuestas.get(pregunta.id)
        acerto = marcada is not None and pregunta.es_correcta(marcada)
        aciertos[pregunta.area] = aciertos.get(pregunta.area, 0) + (1 if acerto else 0)
        acumulado = competencias.setdefault(pregunta.competencia, [0, 0])
        acumulado[0] += 1 if acerto else 0
        acumulado[1] += 1

    por_area = {
        area: ResultadoArea(
            area=area,
            correctas=aciertos.get(area, 0),
            total=total,
            puntaje=estimar_puntaje_area(aciertos.get(area, 0), total),
        )
        for area, total in totales.items()
    }
    return ResultadoSimulacro(
        fecha=fecha,
        tipo=simulacro.tipo,
        por_area=por_area,
        por_competencia={c: (bien, total) for c, (bien, total) in competencias.items()},
        segundos_usados=segundos_usados,
        escala=simulacro.escala,
    )


def descripcion_estimacion(resultado: ResultadoSimulacro, area: Area) -> str:
    """La frase honesta sobre el puntaje estimado de un área."""
    r = resultado.por_area[area]
    return describir_estimacion(r.correctas, r.total)
