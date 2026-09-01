"""excel_a_pdf.py — pasa muchos Excel a PDF de una sola corrida.

Toma una carpeta (o una lista de archivos) y deja **un PDF por cada Excel**,
con el mismo nombre. Sirve para los detallados de factura que deja
`dividir_detallado_por_factura.py`, pero funciona con cualquier `.xlsx`/`.xls`.

Dos motores, se elige solo:

  - **Excel** (`--motor excel`): usa el Excel instalado en el equipo. Es el que
    respeta exactamente el formato de impresión del hospital. Necesita Windows
    con Office y `py -m pip install pywin32`.
  - **LibreOffice** (`--motor libreoffice`): no necesita Office. Convierte en
    tandas, más rápido, con mínimas diferencias de maquetación.

Por defecto (`--motor auto`) usa Excel si está disponible y si no LibreOffice.

USO (Windows, desde C:\\temp-notas):

    REM Todos los Excel de una carpeta → PDFs en otra carpeta:
    py tools\\excel_a_pdf.py ^
        --origen "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\POR_FACTURA" ^
        --salida "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\PDF"

    REM Cada PDF dentro de su propia carpeta (una por factura):
    py tools\\excel_a_pdf.py ^
        --origen "D:\\...\\POR_FACTURA" ^
        --salida "D:\\...\\PDF" ^
        --carpeta-por-archivo

    REM Ver qué haría, sin convertir nada:
    py tools\\excel_a_pdf.py --origen "D:\\...\\POR_FACTURA" --salida "D:\\...\\PDF" --dry-run

Seguro por defecto: NO toca ni modifica los Excel de origen, solo los abre para
leerlos. Si un PDF ya existe se sobrescribe, salvo `--saltar-existentes`.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("excel_a_pdf")

EXTENSIONES = (".xlsx", ".xlsm", ".xls")

# Nombres con los que se instala LibreOffice en Windows y en Linux.
_CANDIDATOS_LIBREOFFICE = (
    "soffice",
    "soffice.exe",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


@dataclass
class Conversion:
    origen: Path
    destino: Path
    estado: str = ""  # OK | SALTADO | ERROR
    detalle: str = ""


@dataclass
class Resumen:
    hechos: list[Conversion] = field(default_factory=list)

    @property
    def ok(self) -> int:
        return sum(1 for c in self.hechos if c.estado == "OK")

    @property
    def errores(self) -> list[Conversion]:
        return [c for c in self.hechos if c.estado == "ERROR"]

    @property
    def saltados(self) -> int:
        return sum(1 for c in self.hechos if c.estado == "SALTADO")


# ─── Qué convertir y a dónde ─────────────────────────────────────────────────


def _es_temporal(ruta: Path) -> bool:
    """Los archivos que Excel deja abiertos empiezan por '~$'."""
    return ruta.name.startswith("~$")


def listar_excels(
    origenes: list[Path], patron: str = "*.xlsx", recursivo: bool = False
) -> list[Path]:
    """Archivos a convertir: acepta archivos sueltos, carpetas y comodines."""
    encontrados: list[Path] = []
    for origen in origenes:
        if origen.is_dir():
            it = origen.rglob(patron) if recursivo else origen.glob(patron)
            encontrados.extend(sorted(it))
        elif origen.exists():
            encontrados.append(origen)
        else:  # comodín escrito a mano (D:\...\*.xlsx)
            encontrados.extend(sorted(origen.parent.glob(origen.name)))
    return [
        r
        for r in dict.fromkeys(encontrados)
        if r.is_file() and r.suffix.lower() in EXTENSIONES and not _es_temporal(r)
    ]


def planificar(
    archivos: list[Path],
    salida: Path | None,
    *,
    carpeta_por_archivo: bool = False,
    saltar_existentes: bool = False,
) -> list[Conversion]:
    """Arma la lista de (Excel → PDF) respetando la opción de carpetas."""
    plan: list[Conversion] = []
    for archivo in archivos:
        base = salida if salida is not None else archivo.parent
        carpeta = base / archivo.stem if carpeta_por_archivo else base
        destino = carpeta / f"{archivo.stem}.pdf"
        conv = Conversion(origen=archivo, destino=destino)
        if saltar_existentes and destino.exists():
            conv.estado = "SALTADO"
            conv.detalle = "el PDF ya existe"
        plan.append(conv)
    return plan


# ─── Motores ─────────────────────────────────────────────────────────────────


def buscar_libreoffice(ruta: str | None = None) -> str | None:
    for cand in ([ruta] if ruta else []) + list(_CANDIDATOS_LIBREOFFICE):
        if not cand:
            continue
        hallado = shutil.which(cand) or (cand if Path(cand).exists() else None)
        if hallado:
            return hallado
    return None


def hay_excel() -> bool:
    try:
        import win32com.client  # noqa: F401
    except Exception:
        return False
    return True


def convertir_con_libreoffice(
    pendientes: list[Conversion], binario: str, lote: int = 25, tiempo_limite: int = 600
) -> None:
    """Convierte en tandas. LibreOffice solo sabe escribir en una carpeta de
    salida, así que se convierte a una temporal y de ahí se mueve al destino."""
    por_carpeta: dict[Path, list[Conversion]] = {}
    for conv in pendientes:
        por_carpeta.setdefault(conv.destino.parent, []).append(conv)

    with tempfile.TemporaryDirectory(prefix="excel_a_pdf_") as tmp:
        perfil = Path(tmp) / "perfil"
        for carpeta, convs in por_carpeta.items():
            carpeta.mkdir(parents=True, exist_ok=True)
            for i in range(0, len(convs), lote):
                tanda = convs[i : i + lote]
                destino_tmp = Path(tmp) / "salida"
                destino_tmp.mkdir(parents=True, exist_ok=True)
                comando = [
                    binario,
                    "--headless",
                    "--norestore",
                    "--invisible",
                    f"-env:UserInstallation=file://{perfil}",
                    "--convert-to",
                    "pdf:calc_pdf_Export",
                    "--outdir",
                    str(destino_tmp),
                    *[str(c.origen) for c in tanda],
                ]
                try:
                    proc = subprocess.run(
                        comando, capture_output=True, text=True, timeout=tiempo_limite, check=False
                    )
                except subprocess.TimeoutExpired:
                    for c in tanda:
                        c.estado, c.detalle = "ERROR", "LibreOffice se pasó del tiempo límite"
                    continue
                for c in tanda:
                    generado = destino_tmp / f"{c.origen.stem}.pdf"
                    if generado.exists():
                        shutil.move(str(generado), str(c.destino))
                        c.estado = "OK"
                    else:
                        c.estado = "ERROR"
                        c.detalle = (proc.stderr or proc.stdout or "").strip()[:200] or (
                            "LibreOffice no generó el PDF"
                        )
                shutil.rmtree(destino_tmp, ignore_errors=True)


def convertir_con_excel(pendientes: list[Conversion]) -> None:  # pragma: no cover - necesita Office
    """Usa el Excel instalado (Windows). Abre una sola instancia para todo."""
    import pythoncom  # type: ignore[import-not-found]
    import win32com.client  # type: ignore[import-not-found]

    pythoncom.CoInitialize()
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    excel.AskToUpdateLinks = False
    try:
        for conv in pendientes:
            conv.destino.parent.mkdir(parents=True, exist_ok=True)
            libro = None
            try:
                libro = excel.Workbooks.Open(
                    str(conv.origen.resolve()), UpdateLinks=0, ReadOnly=True
                )
                # 0 = xlTypePDF
                libro.ExportAsFixedFormat(0, str(conv.destino.resolve()))
                conv.estado = "OK"
            except Exception as e:
                conv.estado, conv.detalle = "ERROR", str(e)[:200]
            finally:
                if libro is not None:
                    with contextlib.suppress(Exception):
                        libro.Close(False)
    finally:
        with contextlib.suppress(Exception):
            excel.Quit()
        pythoncom.CoUninitialize()


def elegir_motor(pedido: str, ruta_libreoffice: str | None) -> tuple[str, str | None]:
    """(motor, binario de LibreOffice si aplica)."""
    if pedido == "excel":
        if not hay_excel():
            raise SystemExit(
                "No encontré Excel por COM. Instalá pywin32 (py -m pip install pywin32) "
                "o usá --motor libreoffice."
            )
        return "excel", None
    if pedido == "libreoffice":
        binario = buscar_libreoffice(ruta_libreoffice)
        if not binario:
            raise SystemExit(
                "No encontré LibreOffice. Instalalo o indicá la ruta con --ruta-libreoffice."
            )
        return "libreoffice", binario
    if hay_excel():
        return "excel", None
    binario = buscar_libreoffice(ruta_libreoffice)
    if binario:
        return "libreoffice", binario
    raise SystemExit(
        "No hay con qué convertir: instalá pywin32 (para usar el Excel del equipo) o LibreOffice."
    )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convierte muchos Excel a PDF, uno por archivo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--origen", type=Path, nargs="+", required=True, help="Carpeta(s) o archivo(s) Excel."
    )
    p.add_argument(
        "--salida", type=Path, help="Carpeta donde dejar los PDF (por defecto, junto al Excel)."
    )
    p.add_argument(
        "--carpeta-por-archivo",
        action="store_true",
        help="Deja cada PDF en su propia carpeta (salida\\HUS352890\\HUS352890.pdf).",
    )
    p.add_argument("--patron", default="*.xlsx", help="Qué archivos tomar de la carpeta.")
    p.add_argument("--recursivo", action="store_true", help="Entrar también en las subcarpetas.")
    p.add_argument("--motor", choices=("auto", "excel", "libreoffice"), default="auto")
    p.add_argument("--ruta-libreoffice", help="Ruta a soffice.exe si no está en el PATH.")
    p.add_argument("--lote", type=int, default=25, help="Archivos por tanda de LibreOffice.")
    p.add_argument(
        "--saltar-existentes", action="store_true", help="No rehacer los PDF que ya están."
    )
    p.add_argument("--reporte-csv", type=Path, help="Listado de lo convertido y lo que falló.")
    p.add_argument("--dry-run", action="store_true", help="Solo mostrar qué haría.")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    archivos = listar_excels(args.origen, patron=args.patron, recursivo=args.recursivo)
    if not archivos:
        logger.error("No encontré ningún Excel en: %s", ", ".join(str(o) for o in args.origen))
        return 2
    plan = planificar(
        archivos,
        args.salida,
        carpeta_por_archivo=args.carpeta_por_archivo,
        saltar_existentes=args.saltar_existentes,
    )
    pendientes = [c for c in plan if c.estado != "SALTADO"]
    logger.info(
        "%d Excel encontrado(s); %d por convertir, %d ya tenían PDF",
        len(archivos),
        len(pendientes),
        len(plan) - len(pendientes),
    )

    if args.dry_run:
        for c in plan[:20]:
            logger.info(
                "   %s → %s%s", c.origen.name, c.destino, f"  [{c.detalle}]" if c.detalle else ""
            )
        if len(plan) > 20:
            logger.info("   … y %d más", len(plan) - 20)
        return 0

    if pendientes:
        motor, binario = elegir_motor(args.motor, args.ruta_libreoffice)
        logger.info(
            "Motor: %s", "Excel del equipo" if motor == "excel" else f"LibreOffice ({binario})"
        )
        if motor == "excel":
            convertir_con_excel(pendientes)
        else:
            convertir_con_libreoffice(pendientes, binario, lote=args.lote)

    res = Resumen(hechos=plan)
    logger.info("─" * 68)
    logger.info("PDF generados ... %d", res.ok)
    if res.saltados:
        logger.info("Ya existían .... %d", res.saltados)
    if res.errores:
        logger.warning("Con error ...... %d", len(res.errores))
        for c in res.errores[:10]:
            logger.warning("   %s: %s", c.origen.name, c.detalle)

    if args.reporte_csv:
        args.reporte_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.reporte_csv.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["EXCEL", "PDF", "ESTADO", "DETALLE"])
            for c in plan:
                w.writerow([str(c.origen), str(c.destino), c.estado or "OK", c.detalle])
        logger.info("Reporte: %s", args.reporte_csv)
    return 1 if res.errores else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
