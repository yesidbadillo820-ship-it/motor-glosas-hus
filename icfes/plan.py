"""El plan de estudio: qué hacer cada día hasta el día del examen.

Un plan sirve si cumple tres cosas:

1. **Reparte el tiempo donde rinde.** Una hora en Matemáticas vale tres veces
   una hora en Inglés en el puntaje global, pero además hay que mirar dónde
   está la brecha real de cada quien. El reparto combina las dos cosas.
2. **Cambia con el tiempo.** No se estudia igual a doce meses del examen que a
   dos semanas. El plan avanza por cuatro fases y en cada una cambia la mezcla
   entre teoría, práctica, repaso y simulacros.
3. **Se puede cumplir.** Deja un día de descanso a la semana y afloja la
   última semana. Un plan que nadie aguanta no es un plan: es una lista de
   culpas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from .dominio import AREAS, ORDEN_AREAS, Area
from .puntaje import aporte_al_global, meta_por_area, puntaje_global

#: Un bloque de estudio dura 45 minutos: lo que aguanta la concentración
#: seguida de una persona antes de necesitar una pausa.
MINUTOS_POR_BLOQUE: int = 45

#: Ninguna área baja de esta parte del tiempo, ni siquiera Inglés con su peso
#: de 1. Abandonar un área por completo cuesta más de lo que ahorra.
PISO_POR_AREA: float = 0.08

#: Una sesión del examen real dura 4 horas y 30 minutos.
MINUTOS_SIMULACRO_COMPLETO: int = 270


class TipoSesion(StrEnum):
    """Qué se hace en un bloque de estudio."""

    TEORIA = "teoria"
    PRACTICA = "practica"
    REPASO = "repaso"
    SIMULACRO_AREA = "simulacro_area"
    SIMULACRO_COMPLETO = "simulacro_completo"
    CUADERNO_ERRORES = "cuaderno_errores"

    @property
    def etiqueta(self) -> str:
        return {
            "teoria": "Teoría",
            "practica": "Práctica",
            "repaso": "Repaso espaciado",
            "simulacro_area": "Simulacro de área",
            "simulacro_completo": "Simulacro completo",
            "cuaderno_errores": "Cuaderno de errores",
        }[self.value]

    @property
    def instruccion(self) -> str:
        return {
            "teoria": "Estudiar el tema y resolver 3 ejemplos explicados en voz alta.",
            "practica": "Resolver preguntas nuevas y leer la explicación de TODAS, incluso de las que acertaste.",
            "repaso": "Volver a lo que el sistema marcó para hoy, sin mirar la respuesta primero.",
            "simulacro_area": "Un bloque de preguntas con cronómetro, como en el examen.",
            "simulacro_completo": "Una sesión completa de 4 h 30, sin celular y sin pausas largas.",
            "cuaderno_errores": "Rehacer los errores marcados y escribir por qué se falló.",
        }[self.value]


@dataclass(frozen=True)
class Fase:
    """Una etapa de la preparación, con su mezcla propia de actividades."""

    nombre: str
    objetivo: str
    proporcion: float
    mezcla: dict[TipoSesion, float]


#: Las cuatro fases, de más lejos a más cerca del examen. Las proporciones se
#: reparten sobre el calendario disponible, sea de doce meses o de tres.
FASES: tuple[Fase, ...] = (
    Fase(
        nombre="Fundamentos",
        objetivo="Cerrar los vacíos de base. Aquí se estudia, todavía no se compite.",
        proporcion=0.35,
        mezcla={TipoSesion.TEORIA: 0.45, TipoSesion.PRACTICA: 0.40, TipoSesion.REPASO: 0.15},
    ),
    Fase(
        nombre="Competencias",
        objetivo="Practicar por competencia, que es como el ICFES pregunta de verdad.",
        proporcion=0.30,
        mezcla={
            TipoSesion.TEORIA: 0.20,
            TipoSesion.PRACTICA: 0.50,
            TipoSesion.REPASO: 0.20,
            TipoSesion.SIMULACRO_AREA: 0.10,
        },
    ),
    Fase(
        nombre="Entrenamiento de examen",
        objetivo="Entrenar contra el reloj y aprender a administrar el tiempo.",
        proporcion=0.23,
        mezcla={
            TipoSesion.PRACTICA: 0.40,
            TipoSesion.REPASO: 0.20,
            TipoSesion.SIMULACRO_AREA: 0.25,
            TipoSesion.CUADERNO_ERRORES: 0.15,
        },
    ),
    Fase(
        nombre="Afinamiento",
        objetivo="Sostener lo ganado y llegar descansado. Nada de temas nuevos.",
        proporcion=0.12,
        mezcla={
            TipoSesion.REPASO: 0.45,
            TipoSesion.CUADERNO_ERRORES: 0.25,
            TipoSesion.PRACTICA: 0.20,
            TipoSesion.SIMULACRO_AREA: 0.10,
        },
    ),
)


@dataclass(frozen=True)
class Bloque:
    """Un bloque concreto de estudio, con fecha, área y qué hacer."""

    fecha: date
    tipo: TipoSesion
    minutos: int
    area: Area | None = None
    foco: str = ""

    @property
    def titulo(self) -> str:
        nombre_area = self.area.nombre if self.area else "Todo el examen"
        return f"{nombre_area} · {self.tipo.etiqueta}"


@dataclass(frozen=True)
class Semana:
    """Una semana del plan."""

    numero: int
    inicio: date
    fin: date
    fase: str
    bloques: tuple[Bloque, ...]

    @property
    def minutos(self) -> int:
        return sum(b.minutos for b in self.bloques)


@dataclass(frozen=True)
class Plan:
    """El plan completo, de hoy hasta el examen."""

    inicio: date
    fecha_examen: date
    horas_semana: float
    meta_global: int
    diagnostico: dict[Area, float]
    reparto: dict[Area, float]
    semanas: tuple[Semana, ...]

    @property
    def semanas_disponibles(self) -> int:
        return len(self.semanas)

    @property
    def horas_totales(self) -> float:
        return sum(s.minutos for s in self.semanas) / 60

    def bloques_de(self, dia: date) -> tuple[Bloque, ...]:
        """Los bloques de un día concreto."""
        for semana in self.semanas:
            if semana.inicio <= dia <= semana.fin:
                return tuple(b for b in semana.bloques if b.fecha == dia)
        return ()

    def semana_de(self, dia: date) -> Semana | None:
        """La semana del plan en la que cae una fecha."""
        return next((s for s in self.semanas if s.inicio <= dia <= s.fin), None)

    def simulacros_completos(self) -> tuple[date, ...]:
        """Las fechas de los simulacros de examen completo."""
        return tuple(
            b.fecha
            for s in self.semanas
            for b in s.bloques
            if b.tipo is TipoSesion.SIMULACRO_COMPLETO
        )

    def resumen(self) -> str:
        """Resumen del plan en texto, para leerlo de una."""
        metas = meta_por_area(self.meta_global, self.diagnostico)
        actual = puntaje_global(self.diagnostico)
        lineas = [
            f"PLAN DE ESTUDIO — del {self.inicio:%d/%m/%Y} al {self.fecha_examen:%d/%m/%Y}",
            f"{self.semanas_disponibles} semanas · {self.horas_semana:.0f} horas por semana "
            f"· {self.horas_totales:.0f} horas en total",
            "",
            f"Punto de partida: {actual} puntos    →    Meta: {self.meta_global} puntos "
            f"(faltan {max(0, self.meta_global - actual)})",
            "",
            "REPARTO DEL TIEMPO POR ÁREA",
            f"  {'Área':<24}{'Hoy':>6}{'Meta':>7}{'Falta':>7}{'Horas/sem':>11}{'Vale':>8}",
        ]
        for area in ORDEN_AREAS:
            horas = self.reparto[area] * self.horas_semana
            hoy = self.diagnostico[area]
            lineas.append(
                f"  {AREAS[area].nombre:<24}{hoy:>6.0f}{metas[area]:>7}"
                f"{max(0, metas[area] - hoy):>7.0f}{horas:>10.1f}h"
                f"{aporte_al_global(area):>7.2f}"
            )
        lineas += [
            "",
            "  «Vale» = cuántos puntos del global (0-500) gana subir un punto en esa área.",
            "",
            "FASES",
        ]
        vistas: list[str] = []
        for semana in self.semanas:
            if semana.fase not in vistas:
                vistas.append(semana.fase)
                fase = next(f for f in FASES if f.nombre == semana.fase)
                ultimas = [s for s in self.semanas if s.fase == semana.fase]
                lineas.append(
                    f"  {semana.fase} — semanas {semana.numero} a {ultimas[-1].numero} "
                    f"({ultimas[-1].fin:%d/%m/%Y})"
                )
                lineas.append(f"      {fase.objetivo}")
        simulacros = self.simulacros_completos()
        if simulacros:
            lineas += [
                "",
                f"SIMULACROS COMPLETOS: {len(simulacros)}. "
                f"El primero el {simulacros[0]:%d/%m/%Y} y el último el {simulacros[-1]:%d/%m/%Y}.",
            ]
        return "\n".join(lineas)


def repartir_horas(
    diagnostico: dict[Area, float],
    meta_global: int,
) -> dict[Area, float]:
    """Qué parte del tiempo semanal se lleva cada área (suma 1).

    Combina dos criterios:

    - **Cuánto vale el área** en el puntaje global (su peso oficial).
    - **Cuánto le falta** para la meta (la brecha del diagnóstico).

    Un área donde ya se está bien recibe menos tiempo aunque pese 3; un área
    donde se está muy mal recibe más aunque pese 1. Ninguna baja del piso.
    """
    metas = meta_por_area(meta_global, diagnostico)
    prioridades: dict[Area, float] = {}
    for area in ORDEN_AREAS:
        brecha = max(0.0, metas[area] - diagnostico[area]) / 100
        # El +0,15 evita que un área ya lograda quede en cero: siempre hay que
        # sostenerla, o se pierde antes del examen.
        prioridades[area] = AREAS[area].peso * (0.15 + brecha)

    total = sum(prioridades.values())
    if total <= 0:
        return {area: 1 / len(ORDEN_AREAS) for area in ORDEN_AREAS}

    reparto = {area: valor / total for area, valor in prioridades.items()}

    # Se aplica el piso y se reescala el resto para que siga sumando 1.
    bajos = {a: p for a, p in reparto.items() if p < PISO_POR_AREA}
    if bajos:
        sobrante = 1 - PISO_POR_AREA * len(bajos)
        resto = sum(p for a, p in reparto.items() if a not in bajos)
        reparto = {
            a: PISO_POR_AREA if a in bajos else (p / resto) * sobrante for a, p in reparto.items()
        }
    return reparto


def _reparto_entero(pesos: dict, total: int) -> dict:
    """Reparte ``total`` unidades entre las claves según sus pesos.

    Usa el método del resto mayor, para que la suma dé exactamente ``total``
    y no queden bloques perdidos por el redondeo.
    """
    if total <= 0 or not pesos:
        return dict.fromkeys(pesos, 0)
    suma = sum(pesos.values())
    if suma <= 0:
        return dict.fromkeys(pesos, 0)
    exactos = {clave: peso / suma * total for clave, peso in pesos.items()}
    enteros = {clave: int(valor) for clave, valor in exactos.items()}
    faltan = total - sum(enteros.values())
    orden = sorted(pesos, key=lambda c: (exactos[c] - enteros[c], str(c)), reverse=True)
    for i in range(faltan):
        enteros[orden[i % len(orden)]] += 1
    return enteros


def _fase_de_semana(numero: int, total_semanas: int) -> Fase:
    """A qué fase pertenece la semana ``numero`` (empezando en 1)."""
    acumulado = 0.0
    limites: list[tuple[int, Fase]] = []
    for fase in FASES:
        acumulado += fase.proporcion
        limites.append((max(1, round(acumulado * total_semanas)), fase))
    for tope, fase in limites:
        if numero <= tope:
            return fase
    return FASES[-1]


def generar_plan(
    diagnostico: dict[Area, float],
    fecha_examen: date,
    meta_global: int,
    horas_semana: float,
    inicio: date | None = None,
    dias_por_semana: int = 6,
) -> Plan:
    """Arma el plan completo desde ``inicio`` hasta el día antes del examen.

    Args:
        diagnostico: puntaje estimado de cada área hoy (0 a 100).
        fecha_examen: el día de la primera sesión del examen.
        meta_global: el puntaje global (0 a 500) al que se le apunta.
        horas_semana: horas de estudio que se pueden sostener por semana.
        inicio: desde cuándo arranca el plan (por defecto, la fecha dada).
        dias_por_semana: cuántos días se estudia; el resto se descansa.
    """
    if inicio is None:
        raise ValueError("Hay que decir desde qué día arranca el plan")
    if fecha_examen <= inicio:
        raise ValueError("El examen tiene que ser posterior al inicio del plan")
    if horas_semana <= 0:
        raise ValueError("El plan necesita al menos una hora a la semana")
    if not 1 <= dias_por_semana <= 7:
        raise ValueError("Se estudia entre 1 y 7 días por semana")
    faltantes = [a.nombre for a in ORDEN_AREAS if a not in diagnostico]
    if faltantes:
        raise ValueError(f"El diagnóstico no tiene: {', '.join(faltantes)}")

    reparto = repartir_horas(diagnostico, meta_global)
    dias_totales = (fecha_examen - inicio).days
    total_semanas = max(1, dias_totales // 7)
    bloques_por_semana = max(dias_por_semana, round(horas_semana * 60 / MINUTOS_POR_BLOQUE))

    semanas: list[Semana] = []
    for numero in range(1, total_semanas + 1):
        arranque = inicio + timedelta(days=(numero - 1) * 7)
        cierre = min(arranque + timedelta(days=6), fecha_examen - timedelta(days=1))
        fase = _fase_de_semana(numero, total_semanas)
        ultima = numero == total_semanas

        # La última semana afloja: menos carga y nada de temas nuevos.
        cupo = round(bloques_por_semana * 0.6) if ultima else bloques_por_semana
        mezcla = (
            {TipoSesion.REPASO: 0.6, TipoSesion.CUADERNO_ERRORES: 0.4} if ultima else fase.mezcla
        )

        por_area = _reparto_entero(reparto, cupo)
        por_tipo = _reparto_entero(mezcla, cupo)

        # Se emparejan áreas y tipos en una lista y se reparten por días.
        tipos: list[TipoSesion] = []
        for tipo, cuantos in por_tipo.items():
            tipos.extend([tipo] * cuantos)
        areas: list[Area] = []
        for area, cuantos in por_area.items():
            areas.extend([area] * cuantos)
        # Se intercalan para que un mismo día no caiga todo de la misma área.
        areas.sort(key=lambda a: (-por_area[a], ORDEN_AREAS.index(a)))
        intercaladas: list[Area] = []
        pendiente = dict(por_area)
        while len(intercaladas) < cupo:
            movio = False
            for area in ORDEN_AREAS:
                if pendiente.get(area, 0) > 0 and len(intercaladas) < cupo:
                    intercaladas.append(area)
                    pendiente[area] -= 1
                    movio = True
            if not movio:
                break

        bloques: list[Bloque] = []
        for indice, (area, tipo) in enumerate(zip(intercaladas, tipos, strict=False)):
            dia = arranque + timedelta(days=indice % dias_por_semana)
            if dia > cierre:
                dia = cierre
            bloques.append(
                Bloque(
                    fecha=dia,
                    tipo=tipo,
                    minutos=MINUTOS_POR_BLOQUE,
                    area=area,
                    foco=_foco(area, tipo, indice + numero),
                )
            )

        # Simulacro completo: cada 2 semanas en Entrenamiento y todas las
        # semanas en Afinamiento, siempre el día de descanso y nunca en la
        # última semana. Para una meta alta hacen falta muchas repeticiones
        # de la jornada real: el cansancio de 4 h 30 también se entrena.
        cada = {"Entrenamiento de examen": 2, "Afinamiento": 1}.get(fase.nombre)
        if cada and numero % cada == 0 and not ultima:
            dia_libre = min(arranque + timedelta(days=dias_por_semana), cierre)
            bloques.append(
                Bloque(
                    fecha=dia_libre,
                    tipo=TipoSesion.SIMULACRO_COMPLETO,
                    minutos=MINUTOS_SIMULACRO_COMPLETO,
                    area=None,
                    foco="Sesión 1" if (numero // cada) % 2 == 1 else "Sesión 2",
                )
            )

        bloques.sort(key=lambda b: (b.fecha, b.tipo.value))
        semanas.append(
            Semana(
                numero=numero,
                inicio=arranque,
                fin=cierre,
                fase=fase.nombre,
                bloques=tuple(bloques),
            )
        )

    return Plan(
        inicio=inicio,
        fecha_examen=fecha_examen,
        horas_semana=horas_semana,
        meta_global=meta_global,
        diagnostico=dict(diagnostico),
        reparto=reparto,
        semanas=tuple(semanas),
    )


def _foco(area: Area, tipo: TipoSesion, semilla: int) -> str:
    """Sobre qué se trabaja el bloque: una competencia o un componente."""
    ficha = AREAS[area]
    if tipo in (TipoSesion.PRACTICA, TipoSesion.SIMULACRO_AREA):
        return ficha.competencias[semilla % len(ficha.competencias)]
    if tipo is TipoSesion.TEORIA:
        return ficha.componentes[semilla % len(ficha.componentes)]
    if tipo is TipoSesion.REPASO:
        return "Lo que venza hoy en el repaso espaciado"
    if tipo is TipoSesion.CUADERNO_ERRORES:
        return "Errores marcados sin resolver"
    return "Examen completo"
