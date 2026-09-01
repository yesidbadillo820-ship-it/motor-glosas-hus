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

Con `--comprimir` (requiere pymupdf) el consolidado se recomprime antes de
sacar la copia .cmd: los escaneos con resolución alta se bajan a 150 dpi
(de sobra para leer e imprimir) y se re-encoda como JPEG calidad 80. Solo se
reemplaza si de verdad queda más liviano y conserva todas las páginas; ante
cualquier fallo se mantiene el original tal cual.

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
    py tools\\unir_pdfs_carpetas.py . --comprimir          # reducir el peso del consolidado

Normalmente NO se ejecuta a mano: el archivo `UNIR_PDFS.cmd` lo lanza con doble
clic sobre la carpeta donde esté ubicado.

Requiere PyPDF2 (o pypdf). El repo ya fija PyPDF2==3.0.1.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import logging
import shutil
import time
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


def unir_pdfs(
    pdfs: list[Path],
    destino: Path,
    PdfReader,
    PdfWriter,
    metadatos: dict[str, str] | None = None,
    detalle: list[tuple[Path, int]] | None = None,
) -> tuple[int, list[str]]:
    """Une `pdfs` en `destino`. Devuelve (n_paginas, [archivos_omitidos]).

    `metadatos` deja una firma dentro del PDF resultante. Sirve para que el bot
    que lo escribió pueda reconocerlo después como suyo y no confundirlo con un
    soporte de verdad.

    `detalle`, si se pasa, recibe `(ruta, n_paginas)` de cada archivo que SÍ
    entró. Sirve para saber en qué página empieza cada uno — que es lo que
    necesita una carátula para no mentir.
    """
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
                if detalle is not None:
                    detalle.append((pdf, n))
        except Exception as exc:  # PDF dañado/ilegible: se omite y se sigue
            omitidos.append(f"{pdf.name} ({type(exc).__name__})")
    if paginas == 0:
        return 0, omitidos
    if metadatos:
        escritor.add_metadata(metadatos)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        with open(tmp, "wb") as fh:
            escritor.write(fh)
        reemplazar_con_reintento(tmp, destino)  # atómica: no deja PDFs a medias
    except Exception:
        # No dejar el .tmp huérfano (mismo cuidado que `copiar_como`): en
        # Windows el destino puede estar ABIERTO en un visor de PDF, o
        # bloqueado por el antivirus, y entonces `os.replace` no pasa.
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return paginas, omitidos


# Sobre el share del hospital 3,7 s no alcanzaban: seguía cayendo una factura
# por corrida. Con esto se aguanta medio minuto antes de darse por vencido.
# El bot del folio configura el logging; suelto por el .cmd no estorba.
logger = logging.getLogger(__name__)

ESPERAS_REEMPLAZO = (0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0)


def reemplazar_con_reintento(origen: Path, destino: Path) -> None:
    """Mueve `origen` encima de `destino`, aguantando un bloqueo pasajero.

    Sobre el share del hospital, el antivirus abre el archivo recién escrito
    para mirarlo y, mientras tanto, Windows contesta «Acceso denegado». Dura un
    instante: en el paquete 31068 cada corrida tumbaba UNA factura distinta —en
    una falló la 376521 y pasó la 377385; en la siguiente, al revés—. Se espera
    un momento y se vuelve a intentar; si de verdad está bloqueado (alguien con
    el PDF abierto), después de los intentos el error sube igual.
    """
    esperado = 0.0
    for espera in ESPERAS_REEMPLAZO:
        try:
            os.replace(origen, destino)
            if esperado:
                # Sin esto solo se ven las que fallan, nunca las que se
                # salvaron, y no hay cómo saber si la espera alcanza.
                logger.info(
                    "  %s estaba ocupado; cedió tras esperar %.1f s.", destino.name, esperado
                )
            return
        except PermissionError:
            time.sleep(espera)
            esperado += espera
    os.replace(origen, destino)


def copiar_como(origen: Path, destino: Path) -> None:
    """Copia byte a byte con escritura atómica (mismo patrón que unir_pdfs)."""
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        shutil.copyfile(origen, tmp)
        reemplazar_con_reintento(tmp, destino)
    except Exception:
        # No dejar el .tmp huérfano (p. ej. destino solo-lectura o bloqueado
        # por antivirus/portal en Windows).
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


def comprimir_pdf(destino: Path, dpi: int = 150, calidad: int = 80) -> tuple[int, int, int] | None:
    """Reduce el peso del PDF consolidado sin perder páginas ni legibilidad.

    Recomprime los escaneos: las imágenes con resolución mayor al umbral se
    bajan a `dpi` (150 es de sobra para leer e imprimir un contrato) y todo se
    re-encoda como JPEG calidad `calidad`. Además limpia objetos basura y
    duplicados que quedan al unir varios PDF.

    Red de seguridad: el archivo SOLO se reemplaza si el resultado abre bien,
    conserva el mismo número de páginas y pesa menos. Ante cualquier duda se
    conserva el original intacto. Devuelve (bytes_antes, bytes_despues,
    n_avisos) si comprimió, o None si no hubo ganancia / falta pymupdf / algo
    falló.

    Sobre `n_avisos`: los PDF que generan algunos sistemas traen referencias
    rotas (p. ej. "cannot find Pattern resource") que MuPDF reporta al leerlos.
    Vienen así DESDE EL ORIGEN — esos elementos tampoco se ven al abrir el
    original en cualquier visor — y no afectan la unión. Se capturan para
    mostrarlos como un contador amable en vez de ruido rojo en la consola.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return None
    with contextlib.suppress(Exception):
        fitz.TOOLS.mupdf_display_errors(False)  # sin ruido en stderr
        fitz.TOOLS.mupdf_warnings(reset=True)
    antes = destino.stat().st_size
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        with fitz.open(str(destino)) as doc:
            paginas = doc.page_count
            if hasattr(doc, "rewrite_images"):  # pymupdf >= 1.24.10
                doc.rewrite_images(
                    dpi_threshold=int(dpi * 4 / 3),
                    dpi_target=dpi,
                    quality=calidad,
                    set_to_gray=False,
                )
            doc.save(str(tmp), garbage=4, deflate=True, clean=True)
        with fitz.open(str(tmp)) as chk:  # el comprimido debe abrir y estar completo
            if chk.page_count != paginas:
                raise ValueError("el comprimido no conserva las páginas")
        avisos = 0
        with contextlib.suppress(Exception):
            texto = fitz.TOOLS.mupdf_warnings(reset=True) or ""
            avisos = sum(1 for ln in texto.splitlines() if "cannot find" in ln)
        despues = tmp.stat().st_size
        if despues >= antes:
            tmp.unlink()
            return None
        reemplazar_con_reintento(tmp, destino)
        return antes, despues, avisos
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        return None


def procesar(
    raiz: Path,
    prefijo: str,
    minimo: int,
    recursivo: bool,
    simulacro: bool,
    tambien_cmd: bool,
    comprimir: bool,
) -> int:
    PdfReader, PdfWriter = _cargar_lector_escritor()

    if comprimir and not simulacro:
        try:
            import fitz  # noqa: F401  (pymupdf)
        except ImportError:
            comprimir = False
            print("AVISO: compresión no disponible (falta pymupdf).")
            print("       Instálala con:  py -m pip install pymupdf")
            print("       Se continúa sin comprimir; los archivos salen igual de válidos.")

    carpetas = [Path(dp) for dp, _dn, _fn in os.walk(raiz)] if recursivo else [raiz]
    carpetas.sort(key=lambda p: clave_natural(str(p)))

    generados = 0
    total_paginas = 0
    saltadas = 0
    copias_cmd = 0
    ahorrado = 0
    avisos_origen = 0
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
        if comprimir:
            resultado = comprimir_pdf(destino)
            if resultado:
                antes, despues, avisos = resultado
                ahorrado += antes - despues
                avisos_origen += avisos
                detalle += f"  comprimido {_mb(antes)} → {_mb(despues)}"
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
    if ahorrado:
        print(f"           Compresión: se ahorraron {_mb(ahorrado)} en total sin perder páginas.")
    if avisos_origen:
        print(
            f"           {avisos_origen} aviso(s) técnicos en los PDF de ORIGEN (referencias rotas"
        )
        print("           que ya venían del sistema que los generó; NO afectan el resultado).")
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
        "--comprimir",
        action="store_true",
        help="Reducir el peso del consolidado recomprimiendo los escaneos (150 dpi, "
        "JPEG 80): sigue perfectamente legible e imprimible. Requiere pymupdf; "
        "si falta, se continúa sin comprimir. Solo se aplica si de verdad reduce "
        "el tamaño y nunca pierde páginas.",
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
        comprimir=args.comprimir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
