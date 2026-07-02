"""unir_pdfs_carpetas.py — Une (combina) todos los PDF de cada carpeta en uno solo.

Pensado para consolidar los soportes de glosas/notas de crédito: cada carpeta
(por factura / NE) suele tener varios PDF sueltos (factura, epicrisis, notas,
autorizaciones…). Este script recorre una carpeta raíz y, para CADA carpeta que
contenga varios PDF, los une en un único PDF consolidado llamado
`_UNIDO_<nombre-de-la-carpeta>.pdf` dentro de esa misma carpeta.

Con `--tambien-cmd` deja además una copia idéntica con extensión `.cmd`
(`_UNIDO_<carpeta>.cmd`): mismo contenido PDF, solo cambia la extensión. Es lo
que exige el flujo de auditoría para subir el consolidado donde piden ".cmd".
Esa copia NO es ejecutable ni hay que darle doble clic — para verla como
documento, se renombra de vuelta a `.pdf`.

Si una carpeta ya tiene su copia `_UNIDO_*.cmd` de una corrida previa, se
refresca SIEMPRE al regenerar el consolidado, aunque no se pase
`--tambien-cmd`: el .cmd es lo que se sube al portal y no puede quedar
divergente del .pdf.

Es idempotente: en cada corrida vuelve a generar los `_UNIDO_*.pdf` y NUNCA los
toma como entrada (se excluyen por el prefijo), así que puedes correrlo las veces
que quieras sin que se aniden.

Orden de las páginas: los PDF de cada carpeta se ordenan por nombre de archivo
de forma "natural" (2 antes que 10). Si necesitas un orden exacto, antepón un
número al nombre: `01_factura.pdf`, `02_epicrisis.pdf`, `03_autorizacion.pdf`.

USO:
    py tools\\unir_pdfs_carpetas.py "D:\\USUARIO CARTERA\\Documents\\SOPORTES"
    py tools\\unir_pdfs_carpetas.py .                      # carpeta actual
    py tools\\unir_pdfs_carpetas.py . --simulacro          # solo mostrar, sin escribir
    py tools\\unir_pdfs_carpetas.py . --minimo 1           # unir aunque haya 1 solo PDF
    py tools\\unir_pdfs_carpetas.py . --sin-recursion      # solo la carpeta raíz
    py tools\\unir_pdfs_carpetas.py . --tambien-cmd        # dejar copia .cmd del consolidado

Normalmente NO se ejecuta a mano: el archivo `UNIR_PDFS.cmd` lo lanza con doble
clic sobre la carpeta donde esté ubicado.

Requiere PyPDF2 (o pypdf). El repo ya fija PyPDF2==3.0.1.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import sys
from pathlib import Path


def _cargar_lector_escritor():
    """Devuelve (PdfReader, PdfWriter) desde pypdf o PyPDF2, lo que haya."""
    try:
        from pypdf import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        sys.stderr.write(
            "\nERROR: falta el componente para leer PDF (PyPDF2 / pypdf).\n"
            "       Instálalo con:  py -m pip install PyPDF2\n\n"
        )
        sys.exit(2)


def clave_natural(nombre: str) -> list:
    """Orden natural: 'a2' antes que 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def listar_pdfs(carpeta: Path, prefijo: str) -> list[Path]:
    """PDF sueltos en `carpeta` (no recursivo), excluyendo los ya unidos."""
    pref = prefijo.upper()
    pdfs = []
    for entrada in os.scandir(carpeta):
        if not entrada.is_file():
            continue
        nombre = entrada.name
        if not nombre.lower().endswith(".pdf"):
            continue
        if nombre.upper().startswith(pref):
            continue  # es un _UNIDO_ de una corrida previa
        pdfs.append(Path(entrada.path))
    return sorted(pdfs, key=lambda p: clave_natural(p.name))


def unir_pdfs(pdfs: list[Path], destino: Path, PdfReader, PdfWriter) -> tuple[int, list[str]]:
    """Une `pdfs` en `destino`. Devuelve (n_paginas, [archivos_omitidos])."""
    escritor = PdfWriter()
    paginas = 0
    omitidos: list[str] = []
    for pdf in pdfs:
        try:
            lector = PdfReader(str(pdf))
            if lector.is_encrypted:
                # PDFs "protegidos" sin contraseña real: se intenta abrir vacío.
                with contextlib.suppress(Exception):
                    lector.decrypt("")
            n = 0
            for pagina in lector.pages:
                escritor.add_page(pagina)
                n += 1
            if n == 0:
                omitidos.append(f"{pdf.name} (sin páginas legibles)")
            else:
                paginas += n
        except Exception as exc:  # PDF dañado/ilegible: se omite y se sigue
            omitidos.append(f"{pdf.name} ({type(exc).__name__})")
    if paginas == 0:
        return 0, omitidos
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        escritor.write(fh)
    os.replace(tmp, destino)  # escritura atómica: no deja PDFs a medias
    return paginas, omitidos


def copiar_como(origen: Path, destino: Path) -> None:
    """Copia byte a byte con escritura atómica (mismo patrón que unir_pdfs)."""
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        shutil.copyfile(origen, tmp)
        os.replace(tmp, destino)
    except Exception:
        # No dejar el .tmp huérfano (p. ej. destino solo-lectura o bloqueado
        # por antivirus/portal en Windows).
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def procesar(
    raiz: Path, prefijo: str, minimo: int, recursivo: bool, simulacro: bool, tambien_cmd: bool
) -> int:
    PdfReader, PdfWriter = _cargar_lector_escritor()

    carpetas = [Path(dp) for dp, _dn, _fn in os.walk(raiz)] if recursivo else [raiz]
    carpetas.sort(key=lambda p: clave_natural(str(p)))

    generados = 0
    total_paginas = 0
    saltadas = 0
    copias_cmd = 0
    con_error: list[str] = []

    print("=" * 64)
    print("  UNIR PDFS — un PDF consolidado por carpeta")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO (no escribe nada)' if simulacro else 'real'}"
        f" | mínimo {minimo} PDF por carpeta"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
    )
    print("-" * 64)

    for carpeta in carpetas:
        pdfs = listar_pdfs(carpeta, prefijo)
        rel = carpeta.name if carpeta != raiz else "(carpeta raíz)"
        if len(pdfs) < minimo:
            if pdfs:  # había algo pero no alcanza el mínimo
                saltadas += 1
                print(f"  ·  {rel}: {len(pdfs)} PDF (menos de {minimo}, se omite)")
            continue

        base = carpeta.name or "SALIDA"
        destino = carpeta / f"{prefijo}{base}.pdf"

        destino_cmd = destino.with_suffix(".cmd")
        # Si ya existe una copia .cmd de una corrida previa, se refresca SIEMPRE
        # (aunque no venga --tambien-cmd): el .cmd es lo que se sube al portal y
        # no puede quedar divergente del .pdf recién regenerado.
        escribir_cmd = tambien_cmd or destino_cmd.exists()

        if simulacro:
            extra = f"  (+ {destino_cmd.name})" if escribir_cmd else ""
            print(f"  →  {rel}: uniría {len(pdfs)} PDF  →  {destino.name}{extra}")
            generados += 1
            continue

        paginas, omitidos = unir_pdfs(pdfs, destino, PdfReader, PdfWriter)
        if paginas == 0:
            print(f"  ✗  {rel}: no se pudo leer ningún PDF, se omite")
            con_error.append(str(carpeta))
            continue
        generados += 1
        total_paginas += paginas
        detalle = f"({len(pdfs)} PDF, {paginas} págs.)"
        if escribir_cmd:
            try:
                copiar_como(destino, destino_cmd)
                copias_cmd += 1
                detalle += f"  + {destino_cmd.name}"
            except Exception as exc:  # p. ej. .cmd solo-lectura: seguir con el resto
                detalle += f"  [copia .cmd falló: {type(exc).__name__}]"
                con_error.append(str(carpeta))
        if omitidos:
            detalle += f"  [omitidos: {', '.join(omitidos)}]"
            con_error.append(str(carpeta))
        print(f"  ✓  {rel}: {destino.name} {detalle}")

    print("-" * 64)
    verbo = "se unirían" if simulacro else "generados"
    print(
        f"  Resumen: {generados} PDF consolidados {verbo}"
        f"{'' if simulacro else f', {total_paginas} páginas en total'}."
    )
    if copias_cmd:
        print(
            f"           {copias_cmd} consolidado(s) quedaron también como .cmd (mismo PDF, otra extensión)."
        )
        print("           OJO: a los _UNIDO_*.cmd NO les des doble clic — no son programas.")
        print("           Para ver uno como documento, renómbralo de vuelta a .pdf.")
    if saltadas:
        print(f"           {saltadas} carpeta(s) con menos de {minimo} PDF, omitidas.")
    if con_error:
        print(f"           {len(con_error)} carpeta(s) con algún PDF ilegible (revisa arriba).")
    if generados == 0 and saltadas == 0:
        print("           No se encontraron PDF para unir en esta carpeta ni en sus subcarpetas.")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Une los PDF de cada carpeta en un solo PDF consolidado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "raiz", nargs="?", default=".", help="Carpeta a procesar (por defecto, la actual)."
    )
    parser.add_argument(
        "--minimo",
        type=int,
        default=2,
        help="Mínimo de PDF en una carpeta para unirla (por defecto 2).",
    )
    parser.add_argument(
        "--prefijo", default="_UNIDO_", help="Prefijo del PDF resultante (por defecto _UNIDO_)."
    )
    parser.add_argument(
        "--sin-recursion",
        action="store_true",
        help="Procesar solo la carpeta raíz, sin subcarpetas.",
    )
    parser.add_argument(
        "--tambien-cmd",
        action="store_true",
        help="Dejar además una copia idéntica del consolidado con extensión .cmd "
        "(mismo contenido PDF, solo cambia la extensión).",
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
    if args.minimo < 1:
        sys.stderr.write("ERROR: --minimo debe ser 1 o más.\n")
        return 2

    return procesar(
        raiz=raiz,
        prefijo=args.prefijo,
        minimo=args.minimo,
        recursivo=not args.sin_recursion,
        simulacro=args.simulacro,
        tambien_cmd=args.tambien_cmd,
    )


if __name__ == "__main__":
    raise SystemExit(main())
