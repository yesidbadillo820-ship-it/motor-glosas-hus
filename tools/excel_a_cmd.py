"""excel_a_cmd.py — Deja cada Excel de las carpetas como archivo .cmd.

Para el flujo de auditoría que exige subir archivos con extensión .cmd:
recorre una carpeta raíz y, por CADA Excel que encuentre (.xlsx, .xlsm,
.xlsb, .xls), deja al lado una copia idéntica con extensión .cmd:

    INFORME.xlsx  →  INFORME.cmd   (mismo contenido byte a byte)

El Excel original NUNCA se toca. La copia .cmd NO es ejecutable ni hay que
darle doble clic — quien la reciba la renombra de vuelta a .xlsx (o la
extensión original) y la abre en Excel normalmente.

Es idempotente: si la copia .cmd ya existe se refresca en cada corrida,
para que nunca quede una versión vieja del Excel. Seguridad: si en el
destino ya existe un .cmd con ese nombre que NO es un Excel (por ejemplo un
script real, o este mismo bot), se salta con un aviso — jamás lo pisa. Los
temporales de Office (``~$...``) se ignoran.

USO:
    py tools\\excel_a_cmd.py "D:\\USUARIO CARTERA\\Documents\\SOPORTES"
    py tools\\excel_a_cmd.py .                    # carpeta actual
    py tools\\excel_a_cmd.py . --simulacro        # solo mostrar, sin escribir
    py tools\\excel_a_cmd.py . --sin-recursion    # solo la carpeta raíz

Normalmente NO se ejecuta a mano: el archivo `EXCEL_A_CMD.cmd` lo lanza con
doble clic sobre la carpeta donde esté ubicado. No requiere instalar ningún
componente extra (solo Python; el lanzador lo instala si falta).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import sys
from pathlib import Path

EXTENSIONES = (".xlsx", ".xlsm", ".xlsb", ".xls")

# Firmas de archivo: ZIP (xlsx/xlsm/xlsb) y OLE2 (xls clásico).
_FIRMA_ZIP = b"PK\x03\x04"
_FIRMA_OLE = b"\xd0\xcf\x11\xe0"


def clave_natural(nombre: str) -> list:
    """Orden natural: 'a2' antes que 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def es_contenido_excel(ruta: Path) -> bool:
    """True si los primeros bytes corresponden a un archivo de Excel."""
    try:
        with open(ruta, "rb") as fh:
            inicio = fh.read(4)
    except OSError:
        return False
    return inicio.startswith(_FIRMA_ZIP) or inicio.startswith(_FIRMA_OLE)


def listar_excels(carpeta: Path) -> list[Path]:
    """Excels sueltos en `carpeta` (no recursivo), sin temporales de Office."""
    excels = []
    for entrada in os.scandir(carpeta):
        if not entrada.is_file():
            continue
        nombre = entrada.name
        if nombre.startswith("~$"):
            continue  # archivo de bloqueo temporal de Office
        if nombre.lower().endswith(EXTENSIONES):
            excels.append(Path(entrada.path))
    return sorted(excels, key=lambda p: clave_natural(p.name))


def copiar_como(origen: Path, destino: Path) -> None:
    """Copia byte a byte con escritura atómica."""
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        shutil.copyfile(origen, tmp)
        os.replace(tmp, destino)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def procesar(raiz: Path, recursivo: bool, simulacro: bool) -> int:
    carpetas = [Path(dp) for dp, _dn, _fn in os.walk(raiz)] if recursivo else [raiz]
    carpetas.sort(key=lambda p: clave_natural(str(p)))

    convertidos = 0
    saltados: list[str] = []
    con_error: list[str] = []

    print("=" * 64)
    print("  EXCEL A CMD — una copia .cmd por cada Excel")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO (no escribe nada)' if simulacro else 'real'}"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
    )
    print("-" * 64)

    for carpeta in carpetas:
        excels = listar_excels(carpeta)
        if not excels:
            continue
        rel = carpeta.name if carpeta != raiz else "(carpeta raíz)"
        destinos_vistos: set[str] = set()
        for excel in excels:
            destino = excel.with_suffix(".cmd")
            # Dos Excels distintos que producirían el mismo .cmd
            # (p. ej. INFORME.xlsx e INFORME.xls en la misma carpeta).
            if destino.name.lower() in destinos_vistos:
                saltados.append(f"{excel.name} (chocaría con otro {destino.name})")
                print(f"  ·  {rel}: {excel.name} se omite — ya se generó {destino.name}")
                continue
            destinos_vistos.add(destino.name.lower())
            # Jamás pisar un .cmd que no sea un Excel (un script real, este bot…).
            if destino.exists() and not es_contenido_excel(destino):
                saltados.append(f"{excel.name} (ya existe {destino.name} y no es un Excel)")
                print(f"  ·  {rel}: {excel.name} se omite — {destino.name} no es un Excel")
                continue

            if simulacro:
                print(f"  →  {rel}: {excel.name}  →  {destino.name}")
                convertidos += 1
                continue
            try:
                copiar_como(excel, destino)
                convertidos += 1
                print(f"  ✓  {rel}: {excel.name}  →  {destino.name}")
            except Exception as exc:  # archivo bloqueado/solo-lectura: seguir
                con_error.append(f"{excel.name} ({type(exc).__name__})")
                print(f"  ✗  {rel}: {excel.name} falló ({type(exc).__name__}), se sigue")

    print("-" * 64)
    verbo = "se convertirían" if simulacro else "convertidos"
    print(f"  Resumen: {convertidos} Excel {verbo} a .cmd.")
    if convertidos and not simulacro:
        print("           Los Excel originales quedaron intactos.")
        print("           OJO: a los .cmd generados NO les des doble clic — no son programas.")
        print("           Para abrir uno en Excel, renómbralo de vuelta a .xlsx.")
    if saltados:
        print(f"           {len(saltados)} archivo(s) omitidos por seguridad (ver arriba).")
    if con_error:
        print(f"           {len(con_error)} archivo(s) con error: {', '.join(con_error)}")
    if convertidos == 0 and not saltados:
        print("           No se encontraron archivos de Excel en esta carpeta ni en")
        print("           sus subcarpetas (busca .xlsx, .xlsm, .xlsb y .xls).")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deja cada Excel de las carpetas como archivo .cmd (copia idéntica).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "raiz", nargs="?", default=".", help="Carpeta a procesar (por defecto, la actual)."
    )
    parser.add_argument(
        "--sin-recursion",
        action="store_true",
        help="Procesar solo la carpeta raíz, sin subcarpetas.",
    )
    parser.add_argument(
        "--simulacro",
        "--dry-run",
        action="store_true",
        help="Mostrar qué haría, sin escribir ningún archivo.",
    )
    args = parser.parse_args(argv)

    raiz = Path(args.raiz).expanduser().resolve()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2

    return procesar(raiz=raiz, recursivo=not args.sin_recursion, simulacro=args.simulacro)


if __name__ == "__main__":
    raise SystemExit(main())
