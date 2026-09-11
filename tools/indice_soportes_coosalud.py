"""indice_soportes_coosalud.py — Arma y revisa el índice de soportes que usa
el bot del portal de COOSALUD (`responder_glosas_coosalud.py --indice`).

EL PROBLEMA QUE RESUELVE
El bot sabe adjuntar el PDF de soporte, pero necesita que alguien le diga en
qué carpeta del share está cada factura. Ese índice se venía armando a mano.
Cuando quedaba viejo, el bot no hallaba el soporte, dejaba la factura en
PENDIENTE_PDX y nadie sabía por qué.

DOS MODOS
  armar      Recorre las carpetas de Y: y escribe el índice (una línea por
             factura). Con --actualizar conserva lo que ya estaba y solo
             agrega lo nuevo, que es lo normal cuando llega un mes más.
  revisar    Antes de correr el portal: para una lista de facturas dice cuáles
             están en el índice, si la carpeta se alcanza, qué PDF se va a
             adjuntar y cuánto pesa. Avisa de las que pasan del límite del
             portal. No toca nada: solo mira.

USO:
    py tools\\indice_soportes_coosalud.py armar ^
        --raiz "Y:\\8. AGOSTO 2026 - SOPORTES RADICACION" ^
        --salida "D:\\USUARIO CARTERA\\Desktop\\BUSCADOR_HUS\\indice_facturas_HUS.txt" ^
        --actualizar

    py tools\\indice_soportes_coosalud.py revisar ^
        --indice "D:\\USUARIO CARTERA\\Desktop\\BUSCADOR_HUS\\indice_facturas_HUS.txt" ^
        --lista "D:\\...\\FACTURAS_SOPORTES.txt"

No necesita nada aparte de Python.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Se reutiliza la lógica del propio bot para que el índice y la revisión digan
# exactamente lo que el bot va a hacer. Si mañana cambia el límite del portal o
# la lista de prefijos, cambia en un solo lado.
from responder_glosas_coosalud import (  # noqa: E402
    MAX_PDF_MB,
    PREFIJOS_SOPORTE,
    _archivos_con_prefijo,
)

RE_FACTURA = re.compile(r"^HUS\d+$", re.IGNORECASE)


def normalizar(factura: str) -> str:
    """HUS0000541781 y HUS541781 son la misma factura."""
    s = str(factura or "").strip().upper()
    m = re.match(r"^HUS0*(\d+)$", s)
    return "HUS" + m.group(1) if m else s


def carpetas_de_facturas(raiz: Path) -> dict[str, Path]:
    """Todas las carpetas que se llaman HUS<numero> colgando de `raiz`.

    Si aparece la misma factura en dos sitios se queda con la primera en orden
    alfabético, que es estable entre corridas — así el índice no cambia solo
    porque el sistema de archivos devolvió las carpetas en otro orden.

    CÓMO RECORRE, Y POR QUÉ ASÍ. El share está al otro lado de la red y ahí lo
    caro es cada ida y vuelta (la lección del 11-09: se le pedían al servidor
    seis veces más viajes de los necesarios). Entonces:

      * se lista cada carpeta UNA vez con `os.scandir`, y el propio listado ya
        dice qué es carpeta — nada de preguntar de nuevo por cada entrada;
      * al dar con una carpeta de factura NO se entra en ella. Adentro están
        los PDF y los RIPS, que acá no interesan: lo que se quiere es la ruta.
        Sobre el árbol del hospital eso es no visitar cientos de miles de
        archivos para no usar ninguno.
    """
    encontradas: dict[str, Path] = {}
    pendientes = [raiz]
    while pendientes:
        carpeta = pendientes.pop()
        try:
            with os.scandir(carpeta) as it:
                entradas = list(it)
        except OSError:
            # Carpeta que desapareció, sin permiso o unidad caída: se salta.
            # El faltante se ve después en `revisar`, factura por factura.
            continue
        for entrada in entradas:
            try:
                if not entrada.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if RE_FACTURA.match(entrada.name):
                encontradas.setdefault(normalizar(entrada.name), Path(entrada.path))
                continue
            pendientes.append(Path(entrada.path))
    return encontradas


def leer_lista(ruta: Path) -> list[str]:
    facturas: list[str] = []
    vistas: set[str] = set()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = ruta.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"No pude leer la lista: {ruta}")
    for trozo in re.findall(r"HUS\d+", texto, re.IGNORECASE):
        f = normalizar(trozo)
        if f not in vistas:
            vistas.add(f)
            facturas.append(f)
    return facturas


def leer_indice(ruta: Path) -> dict[str, Path]:
    """Lee el índice tolerando la barra de Windows y la de Linux.

    El bot solo corre en Windows y su lector exige `\\`, pero acá se acepta
    también `/` para que la herramienta se pueda probar fuera de Windows.
    """
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = ruta.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"No pude leer el índice: {ruta}")
    mapa: dict[str, Path] = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        m = re.search(r"[\\/](HUS\d+)\s*$", linea, re.IGNORECASE)
        if m:
            mapa[normalizar(m.group(1))] = Path(linea)
    return mapa


def escribir_indice(mapa: dict[str, Path], salida: Path) -> None:
    """Escribe UNA RUTA PELADA POR LÍNEA.

    Es el único formato que el bot lee bien: su `cargar_indice` hace
    `Path(linea)` sobre la línea completa, así que cualquier prefijo (por
    ejemplo `HUS541781<tab>`) le arma una ruta relativa que no existe y la
    factura termina en PENDIENTE_PDX sin explicación.
    """
    salida.parent.mkdir(parents=True, exist_ok=True)
    lineas = [str(ruta) for _, ruta in sorted(mapa.items())]
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def cmd_armar(args: argparse.Namespace) -> int:
    salida = Path(args.salida)
    mapa: dict[str, Path] = {}
    previas = 0
    if args.actualizar and salida.exists():
        mapa = leer_indice(salida)
        previas = len(mapa)
        print(f"Índice actual: {previas:,} facturas.")

    nuevas = 0
    for r in args.raiz:
        raiz = Path(r)
        if not raiz.is_dir():
            print(f"  ⚠ no se alcanza (¿está conectada la unidad?): {raiz}")
            continue
        print(f"  recorriendo {raiz} ...", flush=True)
        halladas = carpetas_de_facturas(raiz)
        antes = len(mapa)
        # Lo nuevo pisa a lo viejo: si la factura se reindexó, vale la ruta de
        # ahora, que es la que existe.
        mapa.update(halladas)
        nuevas += len(halladas)
        print(f"     {len(halladas):,} carpetas de factura ({len(mapa) - antes:,} que no estaban)")

    if not mapa:
        print("\nNo se encontró ninguna carpeta HUS<numero>. El índice NO se escribió.")
        return 1

    escribir_indice(mapa, salida)
    print(f"\nÍndice escrito: {salida}")
    print(
        f"  {len(mapa):,} facturas en total ({len(mapa) - previas:,} agregadas, {nuevas:,} vistas)."
    )
    return 0


def cmd_revisar(args: argparse.Namespace) -> int:
    indice = leer_indice(Path(args.indice))
    print(f"Índice: {len(indice):,} facturas.\n")
    facturas = leer_lista(Path(args.lista))
    print(f"Se revisan {len(facturas)} facturas.\n")

    listas: list[str] = []
    problemas: list[tuple[str, str]] = []
    for f in facturas:
        carpeta = indice.get(f)
        if carpeta is None:
            problemas.append((f, "NO está en el índice — hay que volver a armarlo"))
            continue
        if not carpeta.is_dir():
            problemas.append((f, f"no se alcanza la carpeta: {carpeta}"))
            continue
        candidatos = _archivos_con_prefijo(carpeta, PREFIJOS_SOPORTE)
        if not candidatos:
            problemas.append((f, f"sin {'/'.join(PREFIJOS_SOPORTE)}*.pdf en {carpeta}"))
            continue
        prefijo, pdf = candidatos[0]
        mb = pdf.stat().st_size / (1024 * 1024)
        if mb > MAX_PDF_MB:
            problemas.append(
                (f, f"{pdf.name} pesa {mb:.1f}MB — el portal solo acepta {MAX_PDF_MB}MB")
            )
            continue
        aviso = "" if prefijo == "PDX" else f"  (no había PDX, va {prefijo})"
        listas.append(f"  {f:<14} {pdf.name:<38} {mb:5.1f}MB{aviso}")

    if listas:
        print(f"LISTAS PARA SUBIR ({len(listas)}):")
        print("\n".join(listas))
    if problemas:
        print(f"\nLE FALTA ALGO ({len(problemas)}):")
        for f, motivo in problemas:
            print(f"  {f:<14} {motivo}")
        print("\nEl bot dejaría estas en PENDIENTE_PDX. No prometa un soporte que no adjuntó.")
    else:
        print("\nTodas tienen su soporte. Puede correr el portal.")
    return 1 if problemas else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("armar", help="recorre Y: y escribe el índice")
    a.add_argument(
        "--raiz", action="append", required=True, help="carpeta de soportes (se puede repetir)"
    )
    a.add_argument("--salida", required=True, help="TXT del índice")
    a.add_argument(
        "--actualizar", action="store_true", help="conservar lo ya indexado y solo agregar"
    )
    a.set_defaults(func=cmd_armar)

    r = sub.add_parser("revisar", help="dice qué soporte se va a adjuntar y cuál falta")
    r.add_argument("--indice", required=True)
    r.add_argument("--lista", required=True, help="TXT con las facturas a revisar")
    r.set_defaults(func=cmd_revisar)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
