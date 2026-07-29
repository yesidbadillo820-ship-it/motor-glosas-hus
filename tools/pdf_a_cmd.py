"""pdf_a_cmd.py — Deja cada PDF de las carpetas como archivo .cmd (individual).

Hermano de excel_a_cmd.py, para el flujo de auditoría que exige subir archivos
con extensión .cmd: recorre una carpeta raíz y, por CADA PDF que encuentre,
deja al lado una copia idéntica con extensión .cmd — SIN unir nada:

    FACTURA.pdf  →  FACTURA.cmd   (mismo contenido byte a byte)

Es el complemento del bot UNIR_PDFS (que une los PDF de cada carpeta): este
convierte de a UNO. Si una carpeta tiene un solo PDF, ese solo se convierte.

El PDF original NUNCA se toca. La copia .cmd NO es ejecutable ni hay que
darle doble clic — quien la reciba la renombra de vuelta a .pdf y la abre
normalmente.

Es idempotente: si la copia .cmd ya existe se refresca en cada corrida, para
que nunca quede una versión vieja del PDF. Seguridad: si en el destino ya
existe un .cmd con ese nombre que NO es un PDF (por ejemplo un script real,
este mismo bot, o la copia .cmd de un Excel), se salta con un aviso — jamás
lo pisa.

USO:
    py tools\\pdf_a_cmd.py "D:\\USUARIO CARTERA\\Documents\\SOPORTES"
    py tools\\pdf_a_cmd.py .                    # carpeta actual
    py tools\\pdf_a_cmd.py . --simulacro        # solo mostrar, sin escribir
    py tools\\pdf_a_cmd.py . --sin-recursion    # solo la carpeta raíz

Normalmente NO se ejecuta a mano: el archivo `PDF_A_CMD.cmd` lo lanza con
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


def clave_natural(nombre: str) -> list:
    """Orden natural: 'a2' antes que 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def es_contenido_pdf(ruta: Path) -> bool:
    """True si el archivo es un PDF (la firma %PDF- va en los primeros bytes)."""
    try:
        with open(ruta, "rb") as fh:
            inicio = fh.read(1024)
    except OSError:
        return False
    return b"%PDF-" in inicio


def listar_pdfs(carpeta: Path) -> list[Path]:
    """PDFs sueltos en `carpeta` (no recursivo)."""
    pdfs = []
    for entrada in os.scandir(carpeta):
        if not entrada.is_file():
            continue
        if entrada.name.lower().endswith(".pdf"):
            pdfs.append(Path(entrada.path))
    return sorted(pdfs, key=lambda p: clave_natural(p.name))


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
    print("  PDF A CMD — una copia .cmd por cada PDF (sin unir)")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO (no escribe nada)' if simulacro else 'real'}"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
    )
    print("-" * 64)

    for carpeta in carpetas:
        pdfs = listar_pdfs(carpeta)
        if not pdfs:
            continue
        rel = carpeta.name if carpeta != raiz else "(carpeta raíz)"
        for pdf in pdfs:
            destino = pdf.with_suffix(".cmd")
            # Jamás pisar un .cmd que no sea un PDF (un script real, este bot,
            # o la copia .cmd de un Excel con el mismo nombre).
            if destino.exists() and not es_contenido_pdf(destino):
                saltados.append(f"{pdf.name} (ya existe {destino.name} y no es un PDF)")
                print(f"  ·  {rel}: {pdf.name} se omite — {destino.name} no es un PDF")
                continue

            if simulacro:
                print(f"  →  {rel}: {pdf.name}  →  {destino.name}")
                convertidos += 1
                continue
            try:
                copiar_como(pdf, destino)
                convertidos += 1
                print(f"  ✓  {rel}: {pdf.name}  →  {destino.name}")
            except Exception as exc:  # archivo bloqueado/solo-lectura: seguir
                con_error.append(f"{pdf.name} ({type(exc).__name__})")
                print(f"  ✗  {rel}: {pdf.name} falló ({type(exc).__name__}), se sigue")

    print("-" * 64)
    verbo = "se convertirían" if simulacro else "convertidos"
    print(f"  Resumen: {convertidos} PDF {verbo} a .cmd.")
    if convertidos and not simulacro:
        print("           Los PDF originales quedaron intactos.")
        print("           OJO: a los .cmd generados NO les des doble clic — no son programas.")
        print("           Para ver uno como documento, renómbralo de vuelta a .pdf.")
    if saltados:
        print(f"           {len(saltados)} archivo(s) omitidos por seguridad (ver arriba).")
    if con_error:
        print(f"           {len(con_error)} archivo(s) con error: {', '.join(con_error)}")
    if convertidos == 0 and not saltados:
        print("           No se encontraron PDF en esta carpeta ni en sus subcarpetas.")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deja cada PDF de las carpetas como archivo .cmd (copia idéntica, sin unir).",
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
