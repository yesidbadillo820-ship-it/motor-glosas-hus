"""Programa de consola del análisis de velas japonesas.

python -m mercados patrones                    # la lista de los 28
python -m mercados ficha martillo              # qué dice el libro de uno
python -m mercados revisar                     # valida el catálogo
python -m mercados detectar historico.csv      # qué patrones hay ahí
python -m mercados medir historico.csv         # ¿cumplen lo que prometen?
python -m mercados exportar historico.csv      # genera la app del celular
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from . import catalogo
from .datos import ArchivoIlegible, decimales, formato, leer_csv, resumen
from .dibujo import en_texto, medidas

from .medicion import CASOS_MINIMOS, HORIZONTES, medir_todo
from .patrones import PATRONES, POR_CLAVE, buscar

Salida = Callable[[str], None]

DESTINO_POR_DEFECTO = Path("static/mercados")

#: Se repite en todas las salidas que hablan de resultados. No es un adorno
#: legal: es la conclusión honesta de lo que este programa puede y no puede
#: decir, y el libro que le dio origen no la trae.
ADVERTENCIA = (
    "Esto mide lo que YA pasó; no predice lo que va a pasar. Un porcentaje\n"
    "alto sobre pocos casos no significa nada, y ningún patrón por sí solo\n"
    "es una razón para comprar o vender."
)


def _cargar(args, salida: Salida):
    try:
        velas = leer_csv(args.archivo)
    except (ArchivoIlegible, OSError) as error:
        raise SystemExit(f"\n{error}\n") from error
    salida(resumen(velas))
    return velas


def cmd_patrones(args, salida: Salida) -> int:
    fichas = catalogo.cargar()
    familia_actual = None
    for p in PATRONES:
        if p.familia is not familia_actual:
            familia_actual = p.familia
            salida(f"\n{familia_actual.etiqueta.upper()}")
        ficha = fichas[p.clave]
        salida(
            f"  {p.clave:<26} {p.nombre:<28} {p.velas} vela(s) · "
            f"{p.sentimiento.etiqueta:<8} · el libro dice fiabilidad "
            f"{p.fiabilidad_declarada.etiqueta} (pág. {ficha.pagina})"
        )
    salida(f"\n{len(PATRONES)} patrones. Fuente: {catalogo.fuente()['titulo']}")
    return 0


def cmd_ficha(args, salida: Salida) -> int:
    patron = POR_CLAVE.get(args.clave)
    if patron is None:
        raise SystemExit(
            f"No existe «{args.clave}». Mire la lista con «python -m mercados patrones»."
        )
    ficha = catalogo.cargar()[patron.clave]
    salida(f"{patron.nombre}  ({patron.clave})")
    salida(
        f"{patron.familia.etiqueta} · {patron.sentimiento.etiqueta} · "
        f"{patron.velas} vela(s) · libro pág. {ficha.pagina}"
    )
    salida("\nCÓMO IDENTIFICARLO")
    for linea in ficha.identificar:
        salida(f"  · {linea}")
    salida(f"\nSIGNIFICADO\n  {ficha.significado}")
    salida(f"\nFIABILIDAD SEGÚN EL LIBRO: {patron.fiabilidad_declarada.etiqueta}")
    salida("  (afirmación del autor, sin medición que la respalde —")
    salida("   compruébela con «python -m mercados medir su_historico.csv»)")
    if ficha.revisar:
        salida(f"\n⚠ PARA REVISAR\n  {ficha.revisar}")
    return 0


def cmd_revisar(args, salida: Salida) -> int:
    avisos = catalogo.revisar()
    salida(f"Detectores: {len(PATRONES)} · Fichas: {len(catalogo.cargar())}")
    dudosas = [f for f in catalogo.cargar().values() if f.revisar]
    if avisos:
        salida(f"\nAVISOS DEL CATÁLOGO: {len(avisos)}")
        for a in avisos:
            salida(f"  · {a}")
    else:
        salida("\nAVISOS DEL CATÁLOGO: ninguno.")
    if dudosas:
        salida(f"\nMARCADOS PARA REVISIÓN: {len(dudosas)}")
        for f in dudosas:
            salida(f"  · {f.clave}: {f.revisar}")
    return 1 if avisos else 0


def cmd_vela(args, salida: Salida) -> int:
    """Dibuja una sesión: sirve para ver que el CSV YA es la vela.

    La duda que responde es razonable: «esos son solo datos, no dicen nada de
    velas». Sí lo dicen — el cuerpo va de la apertura al cierre, y las mechas
    hasta el máximo y el mínimo. TradingView pinta exactamente eso.
    """
    velas = _cargar(args, salida)
    # Se guarda el ÍNDICE, no solo la vela: dos sesiones con los mismos cuatro
    # precios son iguales entre sí, y buscarlas por valor devolvería la
    # primera, no la que se pidió.
    if args.fecha:
        elegidas = [(i, v) for i, v in enumerate(velas) if v.fecha.isoformat() == args.fecha]
        if not elegidas:
            raise SystemExit(
                f"No hay sesión del {args.fecha} en este archivo. "
                f"Van del {velas[0].fecha} al {velas[-1].fecha}."
            )
    else:
        desde = max(0, len(velas) - args.cuantas)
        elegidas = list(enumerate(velas))[desde:]

    dec = decimales(velas[-1].cierre)
    apariciones = buscar(velas)
    for indice, v in elegidas:
        salida(f"\n{'=' * 46}\n  Sesión del {v.fecha}\n{'=' * 46}")
        salida(en_texto(v, decimales=dec))
        salida("")
        for linea in medidas(v, decimales=dec):
            salida(f"  {linea}")
        encontrados = [a.patron for a in apariciones if a.indice == indice]
        if encontrados:
            salida("\n  PATRONES QUE ENCAJAN AQUÍ")
            for p in encontrados:
                salida(f"    · {p.nombre} ({p.sentimiento.etiqueta})")
        else:
            salida("\n  Ningún patrón del libro encaja en esta sesión.")
    return 0


def cmd_detectar(args, salida: Salida) -> int:
    velas = _cargar(args, salida)
    claves = [args.patron] if args.patron else None
    if args.patron and args.patron not in POR_CLAVE:
        raise SystemExit(f"No existe el patrón «{args.patron}».")
    apariciones = buscar(velas, claves)
    if not apariciones:
        salida("\nNo se encontró ningún patrón en este histórico.")
        return 0
    salida(f"\n{len(apariciones)} apariciones\n")
    for a in apariciones[-args.ultimas :]:
        v = a.velas[-1]
        salida(
            f"  {a.fecha}  {a.patron.nombre:<28} {a.patron.sentimiento.etiqueta:<8}"
            f"  cierre {formato(v.cierre):>14}"
        )
    if len(apariciones) > args.ultimas:
        salida(f"\n  (se muestran las últimas {args.ultimas} de {len(apariciones)})")
    return 0


def cmd_medir(args, salida: Salida) -> int:
    velas = _cargar(args, salida)
    if len(velas) < 60:
        salida("\n⚠ Con menos de 60 sesiones no se puede medir nada serio.")
    resultados = medir_todo(velas, [args.sesiones])
    medibles = [r for r in resultados if r.medible]
    salida(f"\nQué pasó {args.sesiones} sesión(es) después de cada patrón\n")
    salida(f"  {'patrón':<28}{'casos':>7}{'acierta':>9}{'base':>8}{'ventaja':>9}   veredicto")
    for r in sorted(medibles, key=lambda r: (-r.casos, r.patron.clave)):
        if r.casos == 0 and not args.todos:
            continue
        salida(
            f"  {r.patron.nombre:<28}{r.casos:>7}{r.tasa:>9.0%}"
            f"{r.tasa_base:>8.0%}{r.ventaja:>+9.0%}   {r.veredicto}"
        )
    contradicen = [r for r in medibles if r.contradice_al_libro]
    if contradicen:
        salida(
            f"\n{len(contradicen)} patrones que el libro vende como fiables y "
            "el histórico NO respalda:"
        )
        for r in contradicen:
            salida(
                f"  · {r.patron.nombre}: el libro dice «{r.patron.fiabilidad_declarada.etiqueta}»,"
                f" acierta {r.tasa:.0%} contra una base de {r.tasa_base:.0%} ({r.casos} casos)"
            )
    salida(f"\nMuestra mínima para concluir algo: {CASOS_MINIMOS} casos.")
    salida(f"\n{ADVERTENCIA}")
    return 0


def cmd_exportar(args, salida: Salida) -> int:
    from .exportar_web import exportar

    velas = _cargar(args, salida)
    destino = Path(args.salida)
    indice = exportar(destino, velas, titulo=args.titulo or Path(args.archivo).stem)
    peso = sum(f.stat().st_size for f in destino.iterdir() if f.is_file()) / 1024
    salida(f"\nAplicación generada en: {destino}/  ({peso:.0f} KB)")
    salida(f"Doble clic en {indice} para abrirla en este computador.")
    salida("\nPara el celular, con el servidor del motor levantado:")
    salida("  <la dirección con la que entra al Motor de Glosas>/static/mercados/index.html")
    salida(f"\n{ADVERTENCIA}")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mercados",
        description="Patrones de velas japonesas: detectarlos y medir si cumplen.",
        epilog=ADVERTENCIA.replace("\n", " "),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("patrones", help="Listar los 28 patrones.")

    p = sub.add_parser("ficha", help="Qué dice el libro de un patrón.")
    p.add_argument("clave", help="Por ejemplo: martillo, toro_180, doji.")

    sub.add_parser("revisar", help="Validar el catálogo contra los detectores.")

    p = sub.add_parser("vela", help="Ver una sesión dibujada, con sus medidas.")
    p.add_argument("archivo", help="CSV exportado del bróker o de TradingView.")
    p.add_argument("--fecha", help="Una sesión concreta (AAAA-MM-DD).")
    p.add_argument("--cuantas", type=int, default=1, help="Cuántas de las últimas.")

    p = sub.add_parser("detectar", help="Buscar patrones en un CSV de precios.")
    p.add_argument("archivo", help="CSV exportado del bróker o de TradingView.")
    p.add_argument("--patron", help="Buscar solo uno.")
    p.add_argument("--ultimas", type=int, default=40, help="Cuántas mostrar.")

    p = sub.add_parser("medir", help="¿Los patrones cumplen lo que el libro promete?")
    p.add_argument("archivo", help="CSV exportado del bróker o de TradingView.")
    p.add_argument(
        "--sesiones",
        type=int,
        default=HORIZONTES[0],
        help="A cuántas sesiones vista medir (por defecto 1).",
    )
    p.add_argument("--todos", action="store_true", help="Incluir los que no aparecieron.")

    p = sub.add_parser("exportar", help="Generar la aplicación web del celular.")
    p.add_argument("archivo", help="CSV exportado del bróker o de TradingView.")
    p.add_argument("--salida", default=str(DESTINO_POR_DEFECTO), help="Carpeta de destino.")
    p.add_argument("--titulo", help="Nombre del activo, para la pantalla.")
    return parser


def main(argv: Sequence[str] | None = None, salida: Salida = print) -> int:
    args = construir_parser().parse_args(argv)
    return {
        "patrones": cmd_patrones,
        "ficha": cmd_ficha,
        "revisar": cmd_revisar,
        "vela": cmd_vela,
        "detectar": cmd_detectar,
        "medir": cmd_medir,
        "exportar": cmd_exportar,
    }[args.comando](args, salida)
