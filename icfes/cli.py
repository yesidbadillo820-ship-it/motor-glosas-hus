"""El programa de consola: con esto se estudia todos los días.

Se usa así::

    python -m icfes iniciar --examen 2027-08-08 --meta 400 --horas 12
    python -m icfes hoy               # qué toca hoy
    python -m icfes practicar --area mat --n 10
    python -m icfes simulacro --tipo sesion1
    python -m icfes repaso
    python -m icfes progreso
    python -m icfes exportar-web      # la app que funciona sin internet

Todas las funciones interactivas reciben ``entrada``, ``salida`` y ``reloj``
como parámetros. Eso no es un capricho: permite probarlas con ``pytest`` sin
que nadie tenga que escribir en el teclado.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import fechas
from . import progreso as mod_progreso
from .almacen import Almacen, Configuracion
from .banco import Banco, barajar_opciones, cargar_banco, revisar_banco
from .dominio import AREAS, LETRAS_OPCIONES, ORDEN_AREAS, Area, CausaError, Pregunta
from .plan import TipoSesion, generar_plan
from .progreso import Intento
from .puntaje import correctas_para_puntaje, meta_por_area
from .repaso import calidad_desde_respuesta, calificar, pendientes
from .simulacro import TipoSimulacro, armar_simulacro, calificar_simulacro

Salida = Callable[[str], None]
Entrada = Callable[[str], str]
Reloj = Callable[[], float]

#: Nombres cortos para escribir menos en la consola.
ALIAS_AREAS: dict[str, Area] = {
    "lc": Area.LECTURA_CRITICA,
    "lectura": Area.LECTURA_CRITICA,
    "mat": Area.MATEMATICAS,
    "matematicas": Area.MATEMATICAS,
    "soc": Area.SOCIALES_CIUDADANAS,
    "sociales": Area.SOCIALES_CIUDADANAS,
    "cn": Area.CIENCIAS_NATURALES,
    "naturales": Area.CIENCIAS_NATURALES,
    "ing": Area.INGLES,
    "ingles": Area.INGLES,
}

#: Diagnóstico neutro para quien todavía no ha hecho ninguno.
PUNTAJE_NEUTRO: float = 50.0

RAYA = "─" * 72


@dataclass(frozen=True)
class Ronda:
    """Lo que pasó en una tanda de preguntas.

    ``respuestas`` guarda, por cada pregunta, la opción marcada **en el orden
    original de la pregunta**, que es lo que necesita el calificador. Sin esto
    habría que releer la base de datos y una pregunta practicada más temprano
    el mismo día se colaría en el resultado del simulacro.
    """

    respondidas: int
    correctas: int
    respuestas: dict[str, int]


def area_desde_texto(texto: str) -> Area:
    """Convierte «mat» o «matematicas» en el área correspondiente."""
    clave = texto.strip().lower()
    if clave in ALIAS_AREAS:
        return ALIAS_AREAS[clave]
    try:
        return Area(clave)
    except ValueError as exc:
        opciones = ", ".join(sorted(ALIAS_AREAS))
        raise ValueError(f"No existe el área «{texto}». Usa una de: {opciones}") from exc


def _config_o_error(almacen: Almacen) -> Configuracion:
    config = almacen.config()
    if config is None:
        raise SystemExit(
            "Primero hay que configurar el sistema:\n"
            "  python -m icfes iniciar --examen 2027-08-08 --meta 400 --horas 12"
        )
    return config


def _diagnostico(almacen: Almacen, salida: Salida) -> dict[Area, float]:
    """Los puntajes por área del último simulacro completo, o un valor neutro."""
    guardado = almacen.ultimo_diagnostico()
    if guardado and all(a in guardado for a in ORDEN_AREAS):
        return guardado
    salida(
        "Aviso: todavía no hay un simulacro con las cinco áreas, así que el plan\n"
        "       parte de un nivel supuesto de 50 en cada una. Corre\n"
        "       «python -m icfes simulacro --tipo completo» para ajustarlo a tu nivel real."
    )
    return dict.fromkeys(ORDEN_AREAS, PUNTAJE_NEUTRO)


# ---------------------------------------------------------------------------
# La ronda de preguntas: el corazón del programa
# ---------------------------------------------------------------------------


def _mostrar_pregunta(
    pregunta: Pregunta,
    opciones: Sequence[str],
    numero: int,
    total: int,
    salida: Salida,
) -> None:
    salida("")
    salida(RAYA)
    salida(
        f"Pregunta {numero} de {total}   ·   {AREAS[pregunta.area].nombre}   ·   "
        f"dificultad {pregunta.dificultad.etiqueta}"
    )
    salida(RAYA)
    if pregunta.contexto:
        salida(pregunta.contexto)
        salida("")
    salida(pregunta.enunciado)
    salida("")
    for letra, texto in zip(LETRAS_OPCIONES, opciones, strict=False):
        salida(f"   {letra}. {texto}")


def _preguntar_causa(entrada: Entrada, salida: Salida) -> CausaError | None:
    """Pregunta por qué se falló. Es lo que convierte un error en aprendizaje."""
    salida("")
    salida("¿Por qué fallaste? (esto alimenta tu cuaderno de errores)")
    causas = list(CausaError)
    for indice, causa in enumerate(causas, 1):
        salida(f"   {indice}. {causa.descripcion}")
    respuesta = entrada("   Número (Enter para saltar): ").strip()
    if not respuesta.isdigit():
        return None
    indice = int(respuesta)
    return causas[indice - 1] if 1 <= indice <= len(causas) else None


def correr_ronda(
    preguntas: Sequence[Pregunta],
    almacen: Almacen,
    hoy: date,
    fecha_examen: date,
    entrada: Entrada,
    salida: Salida,
    reloj: Reloj = time.monotonic,
    mostrar_explicacion: bool = True,
    semilla: int | None = None,
) -> Ronda:
    """Presenta las preguntas una por una y guarda todo lo que pasó."""
    correctas = 0
    respondidas = 0
    respuestas: dict[str, int] = {}
    for numero, pregunta in enumerate(preguntas, 1):
        opciones, indice_correcto, orden = barajar_opciones(pregunta, semilla)
        _mostrar_pregunta(pregunta, opciones, numero, len(preguntas), salida)

        arranque = reloj()
        cruda = entrada("\n   Tu respuesta (A/B/C/D, Enter para saltar, S para salir): ")
        segundos = max(0.0, reloj() - arranque)
        marcada = cruda.strip().upper()

        if marcada == "S":
            salida("\nSesión terminada. Lo respondido queda guardado.")
            break

        respondidas += 1
        elegida = LETRAS_OPCIONES.index(marcada) if marcada in LETRAS_OPCIONES else None
        acerto = elegida == indice_correcto
        correctas += int(acerto)
        if elegida is not None:
            # Se traduce la letra de pantalla al índice original de la pregunta.
            respuestas[pregunta.id] = orden[elegida]

        if acerto:
            salida(f"\n   ✓ CORRECTA ({segundos:.0f} segundos)")
        elif elegida is None:
            salida(f"\n   — Sin responder. La correcta era la {LETRAS_OPCIONES[indice_correcto]}.")
        else:
            salida(f"\n   ✗ INCORRECTA. La correcta era la {LETRAS_OPCIONES[indice_correcto]}.")

        if mostrar_explicacion:
            salida(f"\n   Por qué: {pregunta.explicacion}")
            if pregunta.trampa:
                salida(f"\n   La trampa: {pregunta.trampa}")

        causa = None
        if not acerto:
            causa = CausaError.ADIVINE if elegida is None else _preguntar_causa(entrada, salida)

        almacen.guardar_intento(
            Intento(
                fecha=hoy,
                pregunta_id=pregunta.id,
                area=pregunta.area,
                competencia=pregunta.competencia,
                tema=pregunta.tema,
                acerto=acerto,
                segundos=segundos,
                causa=causa,
            )
        )
        calidad = calidad_desde_respuesta(acerto, segundos, causa)
        almacen.guardar_tarjeta(calificar(almacen.tarjeta(pregunta.id), calidad, hoy, fecha_examen))

    return Ronda(respondidas=respondidas, correctas=correctas, respuestas=respuestas)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_iniciar(args: argparse.Namespace, almacen: Almacen, salida: Salida) -> int:
    """Guarda la fecha del examen, la meta y las horas disponibles."""
    config = Configuracion(
        nombre=args.nombre,
        fecha_examen=date.fromisoformat(args.examen),
        meta_global=args.meta,
        horas_semana=args.horas,
        dias_por_semana=args.dias,
    )
    if config.fecha_examen <= date.today():
        raise SystemExit("La fecha del examen tiene que estar en el futuro.")
    almacen.guardar_config(config)

    metas = meta_por_area(config.meta_global)
    salida(f"Listo, {config.nombre}.")
    salida(f"Examen: {fechas.largo(config.fecha_examen)}")
    salida(fechas.cuenta_regresiva(date.today(), config.fecha_examen))
    salida(f"Meta: {config.meta_global} de 500 puntos.")
    salida("")
    salida("Para llegar a esa meta necesitas, en cada área:")
    salida(f"  {'Área':<24}{'Puntaje':>9}{'Preguntas a acertar':>22}")
    for area in ORDEN_AREAS:
        ficha = AREAS[area]
        necesarias = correctas_para_puntaje(metas[area], ficha.preguntas)
        salida(f"  {ficha.nombre:<24}{metas[area]:>9}{f'{necesarias} de {ficha.preguntas}':>22}")
    salida("")
    salida(
        "Siguiente paso: «python -m icfes simulacro --tipo completo» para saber de dónde partes."
    )
    return 0


def cmd_hoy(args: argparse.Namespace, almacen: Almacen, banco: Banco, salida: Salida) -> int:
    """Muestra qué toca estudiar hoy."""
    config = _config_o_error(almacen)
    hoy = date.fromisoformat(args.fecha) if args.fecha else date.today()
    diagnostico = _diagnostico(almacen, salida)
    plan = generar_plan(
        diagnostico,
        config.fecha_examen,
        config.meta_global,
        config.horas_semana,
        inicio=args.desde and date.fromisoformat(args.desde) or hoy,
        dias_por_semana=config.dias_por_semana,
    )

    salida("")
    salida(f"HOY — {fechas.largo(hoy)}")
    salida(fechas.cuenta_regresiva(hoy, config.fecha_examen))
    semana = plan.semana_de(hoy)
    if semana:
        salida(f"Semana {semana.numero} de {plan.semanas_disponibles} · fase «{semana.fase}»")
    salida("")

    bloques = plan.bloques_de(hoy)
    if not bloques:
        salida("Hoy es tu día de descanso. Descansar también es parte del plan.")
    else:
        total = sum(b.minutos for b in bloques)
        salida(f"{len(bloques)} bloques · {total} minutos en total")
        for bloque in bloques:
            salida("")
            salida(f"  ▸ {bloque.titulo}  ({bloque.minutos} min)")
            salida(f"     Foco: {bloque.foco}")
            salida(f"     {bloque.tipo.instruccion}")
            if bloque.area and bloque.tipo is TipoSesion.PRACTICA:
                atajo = next(k for k, v in ALIAS_AREAS.items() if v is bloque.area and len(k) <= 3)
                salida(f"     Comando: python -m icfes practicar --area {atajo}")

    vencidas = pendientes(almacen.tarjetas(), hoy)
    if vencidas:
        salida("")
        salida(f"Además tienes {len(vencidas)} preguntas que toca repasar hoy.")
        salida("  Comando: python -m icfes repaso")
    return 0


def cmd_plan(args: argparse.Namespace, almacen: Almacen, salida: Salida) -> int:
    """Muestra el plan completo o una semana."""
    config = _config_o_error(almacen)
    hoy = date.today()
    plan = generar_plan(
        _diagnostico(almacen, salida),
        config.fecha_examen,
        config.meta_global,
        config.horas_semana,
        inicio=hoy,
        dias_por_semana=config.dias_por_semana,
    )
    if args.semana:
        semana = next((s for s in plan.semanas if s.numero == args.semana), None)
        if semana is None:
            raise SystemExit(f"El plan tiene {plan.semanas_disponibles} semanas.")
        salida(f"SEMANA {semana.numero} — fase «{semana.fase}»")
        salida(f"Del {fechas.largo(semana.inicio)} al {fechas.largo(semana.fin)}")
        salida("")
        actual: date | None = None
        for bloque in semana.bloques:
            if bloque.fecha != actual:
                actual = bloque.fecha
                salida(f"  {fechas.corto(bloque.fecha)}")
            salida(f"     · {bloque.titulo} ({bloque.minutos} min) — {bloque.foco}")
        return 0
    salida(plan.resumen())
    return 0


def cmd_practicar(
    args: argparse.Namespace,
    almacen: Almacen,
    banco: Banco,
    entrada: Entrada,
    salida: Salida,
    reloj: Reloj,
) -> int:
    """Práctica libre de un área."""
    config = _config_o_error(almacen)
    hoy = date.fromisoformat(args.fecha) if args.fecha else date.today()
    area = area_desde_texto(args.area) if args.area else None
    excluir = almacen.ids_respondidos() if args.nuevas else None

    preguntas = banco.muestra(args.n, area=area, semilla=args.semilla, excluir=excluir)
    if not preguntas and excluir:
        salida("Ya respondiste todas las preguntas de ese filtro. Repito las que hay.")
        preguntas = banco.muestra(args.n, area=area, semilla=args.semilla)
    if not preguntas:
        raise SystemExit("No hay preguntas para ese filtro.")

    nombre = AREAS[area].nombre if area else "todas las áreas"
    salida(f"PRÁCTICA — {nombre} · {len(preguntas)} preguntas")
    salida("Lee la explicación de todas, también de las que aciertes.")

    ronda = correr_ronda(
        preguntas,
        almacen,
        hoy,
        config.fecha_examen,
        entrada,
        salida,
        reloj,
        semilla=args.semilla,
    )
    salida("")
    salida(RAYA)
    if ronda.respondidas:
        salida(
            f"Resultado: {ronda.correctas} de {ronda.respondidas} correctas "
            f"({ronda.correctas / ronda.respondidas * 100:.0f} %)."
        )
    else:
        salida("No respondiste ninguna pregunta.")
    return 0


def cmd_simulacro(
    args: argparse.Namespace,
    almacen: Almacen,
    banco: Banco,
    entrada: Entrada,
    salida: Salida,
    reloj: Reloj,
) -> int:
    """Simulacro con la estructura y el tiempo del examen real."""
    config = _config_o_error(almacen)
    hoy = date.fromisoformat(args.fecha) if args.fecha else date.today()
    tipos = {
        "sesion1": TipoSimulacro.SESION_1,
        "sesion2": TipoSimulacro.SESION_2,
        "completo": TipoSimulacro.COMPLETO,
        "area": TipoSimulacro.AREA,
    }
    tipo = tipos[args.tipo]
    area = area_desde_texto(args.area) if args.area else None
    if tipo is TipoSimulacro.AREA and area is None:
        raise SystemExit("Un simulacro de área necesita --area (por ejemplo: --area mat)")

    simulacro = armar_simulacro(banco, tipo, area=area, semilla=args.semilla, maximo=args.max)
    salida(f"SIMULACRO — {tipo.etiqueta}")
    salida(simulacro.aviso)
    salida(
        f"{simulacro.total} preguntas · {simulacro.minutos} minutos · "
        f"{simulacro.segundos_por_pregunta():.0f} segundos por pregunta"
    )
    salida("")
    for a, cuantas in simulacro.reparto.items():
        salida(f"   {AREAS[a].nombre:<24}{cuantas:>4} preguntas")

    arranque = reloj()
    ronda = correr_ronda(
        simulacro.preguntas,
        almacen,
        hoy,
        config.fecha_examen,
        entrada,
        salida,
        reloj,
        mostrar_explicacion=False,
        semilla=args.semilla,
    )
    usados = round(reloj() - arranque)
    resultado = calificar_simulacro(simulacro, ronda.respuestas, hoy, segundos_usados=usados)
    almacen.guardar_simulacro(resultado)
    salida("")
    salida(resultado.informe())
    return 0


def cmd_repaso(
    args: argparse.Namespace,
    almacen: Almacen,
    banco: Banco,
    entrada: Entrada,
    salida: Salida,
    reloj: Reloj,
) -> int:
    """Repasa lo que vence hoy según el repaso espaciado."""
    config = _config_o_error(almacen)
    hoy = date.fromisoformat(args.fecha) if args.fecha else date.today()
    vencidas = pendientes(almacen.tarjetas(), hoy, limite=args.n)
    preguntas = [p for p in (banco.por_id(t.clave) for t in vencidas) if p is not None]
    if not preguntas:
        salida("No hay nada que repasar hoy. Practica preguntas nuevas:")
        salida("  python -m icfes practicar --n 10 --nuevas")
        return 0

    salida(f"REPASO — {len(preguntas)} preguntas que ya toca volver a ver")
    ronda = correr_ronda(
        preguntas,
        almacen,
        hoy,
        config.fecha_examen,
        entrada,
        salida,
        reloj,
        semilla=args.semilla,
    )
    salida("")
    if ronda.respondidas:
        salida(f"Repaso terminado: {ronda.correctas} de {ronda.respondidas} correctas.")
    return 0


def cmd_progreso(args: argparse.Namespace, almacen: Almacen, salida: Salida) -> int:
    """Informe de avance, errores y proyección."""
    config = _config_o_error(almacen)
    hoy = date.fromisoformat(args.fecha) if args.fecha else date.today()
    salida(
        mod_progreso.informe(
            almacen.intentos(),
            almacen.historial_simulacros(),
            hoy,
            config.fecha_examen,
            config.meta_global,
        )
    )
    return 0


def cmd_banco(args: argparse.Namespace, banco: Banco, salida: Salida) -> int:
    """Muestra qué hay en el banco y revisa su calidad."""
    salida(banco.resumen())
    salida("")
    salida("COBERTURA POR COMPETENCIA")
    for area, competencias in banco.cobertura().items():
        salida(f"  {area}")
        for competencia, cuantas in competencias.items():
            salida(f"     {cuantas:>3}  {competencia}")
    avisos = revisar_banco(banco)
    salida("")
    if avisos:
        salida(f"REVISIÓN: {len(avisos)} avisos")
        for aviso in avisos:
            salida(f"  · {aviso}")
        return 1
    salida("REVISIÓN: el banco está bien. Sin avisos.")
    return 0


def cmd_exportar_web(
    args: argparse.Namespace, almacen: Almacen, banco: Banco, salida: Salida
) -> int:
    """Genera la aplicación web que funciona sin internet."""
    from .exportar_web import exportar

    config = almacen.config()
    destino = Path(args.salida)
    ruta = exportar(banco, destino, config=config)
    salida(f"Aplicación web generada en: {ruta}")
    salida(f"Tamaño: {ruta.stat().st_size / 1024:.0f} KB")
    salida("")
    salida("Ábrela con doble clic. Funciona sin internet y guarda tu avance en el")
    salida("navegador. Se puede copiar al celular y sigue funcionando igual.")
    return 0


# ---------------------------------------------------------------------------
# Armado de la línea de comandos
# ---------------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    """Arma el analizador de argumentos con todos los comandos."""
    parser = argparse.ArgumentParser(
        prog="icfes",
        description="Sistema de preparación para el examen Saber 11 del ICFES.",
    )
    parser.add_argument("--datos", help="Ruta del archivo de progreso (SQLite).")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("iniciar", help="Configurar fecha del examen, meta y horas.")
    p.add_argument("--examen", required=True, help="Fecha del examen (AAAA-MM-DD).")
    p.add_argument("--meta", type=int, default=350, help="Puntaje global objetivo (0 a 500).")
    p.add_argument("--horas", type=float, default=10, help="Horas de estudio por semana.")
    p.add_argument("--dias", type=int, default=6, help="Días de estudio por semana (1 a 7).")
    p.add_argument("--nombre", default="estudiante", help="Cómo te llamas.")

    p = sub.add_parser("hoy", help="Qué estudiar hoy.")
    p.add_argument("--fecha", help="Simular otro día (AAAA-MM-DD).")
    p.add_argument("--desde", help="Fecha de inicio del plan (AAAA-MM-DD).")

    p = sub.add_parser("plan", help="Ver el plan completo o una semana.")
    p.add_argument("--semana", type=int, help="Ver el detalle de una semana.")

    p = sub.add_parser("practicar", help="Practicar preguntas.")
    p.add_argument("--area", help="lc, mat, soc, cn o ing.")
    p.add_argument("-n", type=int, default=10, help="Cuántas preguntas.")
    p.add_argument("--nuevas", action="store_true", help="Solo preguntas que nunca has visto.")
    p.add_argument("--fecha", help="Simular otro día (AAAA-MM-DD).")
    p.add_argument("--semilla", type=int, help="Repetir la misma selección de preguntas.")

    p = sub.add_parser("simulacro", help="Simulacro con el tiempo del examen real.")
    p.add_argument("--tipo", default="sesion1", choices=["sesion1", "sesion2", "completo", "area"])
    p.add_argument("--area", help="Obligatorio si el tipo es «area».")
    p.add_argument("--max", type=int, help="Tope de preguntas.")
    p.add_argument("--fecha", help="Simular otro día (AAAA-MM-DD).")
    p.add_argument("--semilla", type=int, help="Repetir el mismo simulacro.")

    p = sub.add_parser("repaso", help="Repasar lo que vence hoy.")
    p.add_argument("-n", type=int, default=20, help="Tope de repasos.")
    p.add_argument("--fecha", help="Simular otro día (AAAA-MM-DD).")
    p.add_argument("--semilla", type=int, help="Fijar el barajado de opciones.")

    p = sub.add_parser("progreso", help="Informe de avance y proyección.")
    p.add_argument("--fecha", help="Simular otro día (AAAA-MM-DD).")

    sub.add_parser("banco", help="Ver y revisar el banco de preguntas.")

    p = sub.add_parser("exportar-web", help="Generar la app web que funciona sin internet.")
    p.add_argument("--salida", default="icfes-app.html", help="Dónde guardar el archivo.")

    return parser


def main(
    argv: Sequence[str] | None = None,
    entrada: Entrada = input,
    salida: Salida = print,
    reloj: Reloj = time.monotonic,
) -> int:
    """Punto de entrada del programa."""
    args = construir_parser().parse_args(argv)
    ruta = Path(args.datos) if args.datos else None

    if args.comando == "banco":
        return cmd_banco(args, cargar_banco(), salida)

    with Almacen(ruta) as almacen:
        if args.comando == "iniciar":
            return cmd_iniciar(args, almacen, salida)
        if args.comando == "plan":
            return cmd_plan(args, almacen, salida)
        if args.comando == "progreso":
            return cmd_progreso(args, almacen, salida)

        banco = cargar_banco()
        if args.comando == "hoy":
            return cmd_hoy(args, almacen, banco, salida)
        if args.comando == "practicar":
            return cmd_practicar(args, almacen, banco, entrada, salida, reloj)
        if args.comando == "simulacro":
            return cmd_simulacro(args, almacen, banco, entrada, salida, reloj)
        if args.comando == "repaso":
            return cmd_repaso(args, almacen, banco, entrada, salida, reloj)
        if args.comando == "exportar-web":
            return cmd_exportar_web(args, almacen, banco, salida)
    raise SystemExit(f"Comando desconocido: {args.comando}")
