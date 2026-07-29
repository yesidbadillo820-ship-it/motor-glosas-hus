"""buscar_facturas.py — Recolector de soportes: busca en las carpetas
compartidas TODOS los archivos de una lista de facturas y los copia
organizados en una carpeta por factura. Usado por BUSCAR_FACTURA.cmd.

Para armar el paquete de respuesta de una glosa hoy toca abrir carpeta por
carpeta buscando la factura. Este bot recibe la lista (facturas.txt, una por
línea: sirve HUS0000533470, HUS533470 o 533470) y recorre la carpeta que le
digas (y sus subcarpetas) copiando a DESTINO\\<factura>\\ cada archivo cuyo
nombre traiga ese número. Los originales NO se tocan ni se mueven.

Al final deja un RESUMEN_BUSQUEDA.txt con cuántos archivos halló por factura
y cuáles facturas quedaron SIN soportes.

USO:
    py tools\\buscar_facturas.py CARPETA_DONDE_BUSCAR --lista facturas.txt --destino SOPORTES
    py tools\\buscar_facturas.py \\\\servidor\\soportes --lista facturas.txt --destino D:\\PAQUETE

No requiere componentes adicionales (solo Python).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


def normalizar_factura(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    return digitos.lstrip("0") or digitos


def cargar_lista(ruta: Path) -> list[str]:
    facturas = []
    vistas = set()
    for ln in ruta.read_text(encoding="utf-8-sig").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        norm = normalizar_factura(s)
        if norm and norm not in vistas:
            vistas.add(norm)
            facturas.append(s)
    return facturas


def compilar_patrones(facturas: list[str]) -> dict[str, re.Pattern]:
    """{factura original: patrón} — el número no puede ir pegado a más dígitos."""
    patrones = {}
    for f in facturas:
        norm = normalizar_factura(f)
        if norm:
            patrones[f] = re.compile(rf"(?<!\d)0*{re.escape(norm)}(?!\d)")
    return patrones


def copiar_sin_pisar(origen: Path, carpeta: Path) -> str:
    """Copia conservando fecha; si ya existe uno distinto, numera la copia."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / origen.name
    n = 1
    while destino.exists():
        if destino.stat().st_size == origen.stat().st_size:
            return "ya estaba"
        n += 1
        destino = carpeta / f"{origen.stem}_{n}{origen.suffix}"
    shutil.copy2(str(origen), str(destino))
    return "copiado"


def procesar(raiz: Path, lista: Path, destino: Path) -> int:
    facturas = cargar_lista(lista)
    patrones = compilar_patrones(facturas)

    print("=" * 66)
    print("  BUSCAR FACTURA — recolector de soportes por lista")
    print("=" * 66)
    print(f"  Buscando en: {raiz}")
    print(f"  Facturas en la lista: {len(facturas)}   Destino: {destino}")
    print("-" * 66)

    conteo = dict.fromkeys(facturas, 0)
    revisados = errores = 0
    destino_res = destino.resolve()
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        try:
            if destino_res in p.resolve().parents:
                continue  # no re-copiar lo ya recolectado
        except OSError:
            continue
        revisados += 1
        for f, patron in patrones.items():
            if patron.search(p.name):
                try:
                    copiar_sin_pisar(p, destino / f)
                    conteo[f] += 1
                except OSError as exc:
                    errores += 1
                    print(f"  ✗ {p.name}: no se pudo copiar ({type(exc).__name__})")
                break  # un archivo se guarda con la primera factura que coincida

    con_algo = {f: n for f, n in conteo.items() if n}
    sin_nada = [f for f, n in conteo.items() if not n]
    for f in facturas:
        marca = "✓" if conteo[f] else "·"
        print(f"  {marca} {f:18s} {conteo[f]} archivo(s)")

    resumen = destino / "RESUMEN_BUSQUEDA.txt"
    destino.mkdir(parents=True, exist_ok=True)
    lineas = [
        "RESUMEN DE BUSQUEDA DE SOPORTES",
        f"Carpeta revisada: {raiz}",
        f"Archivos revisados: {revisados}",
        "",
        "FACTURAS CON SOPORTES:",
        *(f"  {f}: {n} archivo(s)" for f, n in con_algo.items()),
        "",
        "FACTURAS SIN NINGUN ARCHIVO (buscar manualmente):",
        *(f"  {f}" for f in sin_nada),
    ]
    resumen.write_text("\r\n".join(lineas), encoding="utf-8")

    print("-" * 66)
    print(f"  Archivos revisados: {revisados}")
    print(
        f"  Facturas con soportes: {len(con_algo)}   Sin soportes: {len(sin_nada)}   Errores: {errores}"
    )
    print(f"  Resumen: {resumen}")
    print("=" * 66)
    return 0 if errores == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Busca y copia los soportes de una lista de facturas."
    )
    parser.add_argument(
        "carpeta", nargs="?", default=".", help="Carpeta donde buscar (incluye subcarpetas)."
    )
    parser.add_argument(
        "--lista", type=Path, required=True, help="Archivo .txt con las facturas (una por línea)."
    )
    parser.add_argument(
        "--destino", type=Path, required=True, help="Carpeta donde dejar lo encontrado."
    )
    args = parser.parse_args(argv)

    raiz = Path(args.carpeta).expanduser()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2
    if not args.lista.is_file():
        sys.stderr.write(f"ERROR: no existe la lista: {args.lista}\n")
        return 2
    return procesar(raiz.resolve(), args.lista, args.destino)


if __name__ == "__main__":
    raise SystemExit(main())
