"""BOT RPA del lote de glosas del Dispensario — flujo completo por paquete GI.

Uso (en el equipo de cartera, desde C:\\motor-glosas\\repo):

    py tools\\glosas_dispensario\\bot_lote_dispensario.py --excel "D:\\...\\GLOSAS_X.xlsx"

Qué hace, en orden:
  1. Pide el código GI (o recíbelo con --gi) y crea la carpeta del paquete
     con su subcarpeta `soportes`: <base>\\<GI>\\soportes.
  2. Genera el Excel de respuestas con gen_lote.py — hereda la DIRECTRIZ CL:
     las objeciones CL de glosas Médica/Mixta NO se responden (van a la hoja
     "PARA GESTION MEDICA" y quedan intactas para la nota crédito del equipo
     médico).
  3. Busca el PDF de cada factura del lote en las carpetas de soportes de
     radicación de la unidad Y: y lo copia a `soportes`.
  4. Lee cada PDF con la cascada pdfplumber → PyPDF2 → OCR
     (extraer_factura_pdf.py) y, SOLO con los datos que de verdad se leyeron
     (paciente y valor total), enriquece la respuesta de esa factura con una
     frase de anclaje al soporte. Nada leído = nada agregado (no se inventa).
  5. Si no se pasa --sin-cargue, corre el robot del portal
     (responder_glosas_simed.py) con el Excel del paquete.
  6. Convierte las evidencias de la corrida (los .png del robot) en el PDF
     del paquete <GI>_EVIDENCIAS.pdf y deja todo dentro de la carpeta GI.

Reglas: piloto antes de masivo (use --piloto HUS...), credenciales del portal
solo por variables de entorno (SIMED_USER / SIMED_PASSWORD), y español claro.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[1]

RUTAS_SOPORTES_DEFECTO = [
    r"Y:\2. FEBRERO 2026 - SOPORTES RADICACION CARPETA 2",
    r"Y:\3. MARZO 2026 - SOPORTES RADICACION",
    r"Y:\4. ABRIL 2026 - SOPORTES RADICACION",
    r"Y:\5. MAYO 2026 - SOPORTES RADICACION",
    r"Y:\6. JUNIO 2026 - SOPORTES RADICACION",
    r"Y:\7. JULIO 2026 - SOPORTES RADICACION",
    r"Y:\8. AGOSTO 2026 - SOPORTES RADICACION",
    r"Y:\9.SEPTIEMBRE - SOPORTES RADICACION",
]
BASE_DEFECTO = r"D:\USUARIO CARTERA\Documents"


def asegurar_dependencias() -> None:
    """Autoinstala lo que falte (patrón de los bots del repo)."""
    for paquete, modulo in [
        ("openpyxl", "openpyxl"),
        ("pdfplumber", "pdfplumber"),
        ("PyPDF2", "PyPDF2"),
        ("pymupdf", "pymupdf"),
        ("pillow", "PIL"),
    ]:
        try:
            __import__(modulo)
        except ImportError:
            print(f"Instalando {paquete}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", paquete])


def factura_corta(fac: str) -> str:
    return str(fac).replace("HUS", "").lstrip("0") or "0"


def buscar_pdf_factura(fac: str, rutas: list[str]) -> Path | None:
    """Busca el PDF de la factura en las carpetas de radicación (la más
    reciente primero). Acepta nombres que contengan HUS0000123456 o el
    número corto; carpetas caídas o sin permiso se saltan con aviso."""
    corta = factura_corta(fac)
    patrones = [f"*{fac}*.pdf", f"*HUS*{corta}*.pdf", f"*{corta}*.pdf"]
    for raiz in reversed(rutas):  # el mes más reciente primero
        base = Path(raiz)
        if not base.is_dir():
            continue
        for patron in patrones:
            try:
                hallado = next(base.rglob(patron), None)
            except OSError as e:
                print(f"    (no pude recorrer {raiz}: {e})")
                break
            if hallado:
                return hallado
    return None


def frase_anclaje(fac: str, datos: dict) -> str | None:
    """SOLO con datos extraídos del PDF. Sin paciente ni total no hay frase."""
    partes = [f"LA FACTURA {fac}"]
    if datos.get("paciente"):
        partes.append(f"EXPEDIDA A NOMBRE DEL PACIENTE {datos['paciente']}")
    if datos.get("total"):
        partes.append(f"POR VALOR TOTAL DE ${datos['total']:,.0f}".replace(",", "."))
    if len(partes) == 1:
        return None
    return (
        ", ".join(partes) + ", SE ANEXA COMO SOPORTE DE LA PRESENTE RESPUESTA "
        "JUNTO CON SUS ANEXOS DE RADICACION."
    )


def enriquecer_excel(
    ruta_excel: Path,
    por_factura: dict[str, str] | None = None,
    por_linea: dict[tuple[str, int], str] | None = None,
) -> int:
    """Inserta las frases dinámicas antes del cierre institucional: la
    tarifaria de cada línea (cruce con el contrato 440) y el anclaje al
    soporte de la factura. No toca la hoja PARA GESTION MEDICA."""
    from openpyxl import load_workbook

    MARCA = "POR LO EXPUESTO, SE SOLICITA EL LEVANTAMIENTO"  # arranque del cierre del motor
    por_factura = por_factura or {}
    por_linea = por_linea or {}
    wb = load_workbook(ruta_excel)
    ws = wb["Respuestas Glosa"]
    tocadas = 0
    for fila in ws.iter_rows(min_row=2):
        fac = str(fila[0].value or "").strip()
        num = int(fila[1].value or 0)
        frases = [f for f in (por_linea.get((fac, num)), por_factura.get(fac)) if f]
        detalle = str(fila[7].value or "")
        frases = [f for f in frases if f not in detalle]
        if not frases:
            continue
        agregado = " ".join(frases)
        k = detalle.find(MARCA)
        fila[7].value = (
            detalle[:k].rstrip() + " " + agregado + " " + detalle[k:]
            if k > 0
            else detalle + " " + agregado
        )
        tocadas += 1
    wb.save(ruta_excel)
    return tocadas


def evidencias_a_pdf(gi: str, facturas: list[str], carpeta_gi: Path) -> Path | None:
    """Junta los pantallazos de la corrida de HOY (evidencias_glosa/) en el
    PDF del paquete, copiando además los .png a la carpeta GI."""
    from PIL import Image

    origen = REPO / "evidencias_glosa"
    hoy = time.strftime("%Y%m%d")
    elegidos = []
    for fac in sorted(facturas):
        cands = sorted(origen.glob(f"HUS{factura_corta(fac)}_{hoy}_*.png"))
        if cands:
            destino = carpeta_gi / cands[-1].name
            shutil.copy2(cands[-1], destino)
            elegidos.append(destino)
    if not elegidos:
        return None
    pdf = carpeta_gi / f"{gi}_EVIDENCIAS.pdf"
    for i, png in enumerate(elegidos):
        with Image.open(png) as im:
            im.convert("RGB").save(pdf, "PDF", append=(i > 0))
    return pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--excel", type=Path, required=True, help="Export DGH del lote (GLOSAS_X.xlsx)"
    )
    parser.add_argument(
        "--gi", type=str, default=None, help="Código GI (si se omite, se pide en pantalla)"
    )
    parser.add_argument(
        "--base", type=Path, default=Path(BASE_DEFECTO), help="Dónde crear la carpeta GI"
    )
    parser.add_argument("--rutas-soportes", nargs="*", default=RUTAS_SOPORTES_DEFECTO)
    parser.add_argument(
        "--piloto", type=str, default=None, help="Cargar SOLO esta factura (piloto)"
    )
    parser.add_argument(
        "--sin-cargue", action="store_true", help="Preparar todo sin subir al portal"
    )
    parser.add_argument(
        "--con-cabeza", action="store_true", help="Mostrar el navegador en el cargue"
    )
    parser.add_argument(
        "--tarifario-servicios",
        type=Path,
        default=Path(BASE_DEFECTO) / "TARIFARIO_440" / "6.2 PRECIOS DE REFERENCIA.xlsx",
        help="Anexo 6.2 del contrato 440 (CUPS/servicios)",
    )
    parser.add_argument(
        "--tarifario-medicamentos",
        type=Path,
        default=Path(BASE_DEFECTO) / "TARIFARIO_440" / "TARIFAS DEL CONTRATO.xlsx",
        help="Anexos de medicamentos y dispositivos del contrato 440 (CUM)",
    )
    args = parser.parse_args()

    asegurar_dependencias()
    from extraer_factura_pdf import extraer_datos_factura
    from tarifario_440 import cargar_tarifario, frase_tarifaria, tarifa_de

    gi = (args.gi or input("Código GI del paquete (ej. GI-33-5400-2026): ")).strip()
    if not gi:
        print("Sin código GI no hay paquete.")
        return 1
    carpeta_gi = args.base / gi
    soportes = carpeta_gi / "soportes"
    soportes.mkdir(parents=True, exist_ok=True)
    print(f"[1/6] Carpeta del paquete: {carpeta_gi}")

    # 2. Generar respuestas (gen_lote hereda la exclusión CL médica/mixta)
    excel_resp = carpeta_gi / f"respuestas_glosa_{gi}.xlsx"
    dump = carpeta_gi / f"dump_{gi}.json"
    print("[2/6] Generando respuestas con gen_lote.py (directriz CL incluida)...")
    r = subprocess.run(
        [sys.executable, str(AQUI / "gen_lote.py"), str(args.excel), str(excel_resp), str(dump)],
        cwd=AQUI,
    )
    if r.returncode != 0 or not excel_resp.is_file():
        print("gen_lote.py falló — revise el export.")
        return 1
    lineas = json.load(open(dump, encoding="utf-8"))
    facturas = sorted({d["factura"] for d in lineas})
    print(f"      Facturas a responder: {len(facturas)}")

    # 2b. Cruce con el tarifario del contrato 440 (solo glosas de tarifas y
    # solo códigos que SÍ estén pactados — sin coincidencia no se cita nada)
    indice = cargar_tarifario(args.tarifario_servicios, args.tarifario_medicamentos)
    frases_linea: dict[tuple[str, int], str] = {}
    if indice:
        for d in lineas:
            if not str(d.get("tipo", "")).startswith(("TARIFA", "LISTA_PRECIOS")):
                continue
            t = tarifa_de(indice, d.get("cups"))
            if t:
                frases_linea[(d["factura"], d["num"])] = frase_tarifaria(d["cups"], t)
        print(
            f"      Tarifario cargado ({len(indice):,} códigos): "
            f"{len(frases_linea)} respuestas citarán su tarifa pactada".replace(",", ".")
        )
    else:
        print(
            "      Sin tarifario a mano (revise --tarifario-servicios/--tarifario-medicamentos): "
            "las respuestas van sin la fila tarifaria citada."
        )

    # 3. Soportes de radicación desde la unidad Y:
    print("[3/6] Buscando el PDF de cada factura en las carpetas de radicación...")
    extraidos, sin_pdf, anclajes = {}, [], {}
    for fac in facturas:
        pdf = buscar_pdf_factura(fac, args.rutas_soportes)
        if pdf is None:
            sin_pdf.append(fac)
            continue
        destino = soportes / f"{fac}{pdf.suffix.lower()}"
        try:
            shutil.copy2(pdf, destino)
        except OSError as e:
            print(f"    {fac}: no pude copiar {pdf} ({e})")
            sin_pdf.append(fac)
            continue
        # 4. Lectura en cascada + frase de anclaje SOLO con lo leído
        datos = extraer_datos_factura(destino)
        extraidos[fac] = datos
        frase = frase_anclaje(fac, datos)
        if frase:
            anclajes[fac] = frase
        print(
            f"    {fac}: soporte OK | lectura: {datos['metodo']}"
            + (" | anclada a la respuesta" if frase else " | sin datos legibles para anclar")
        )
    json.dump(
        extraidos,
        open(carpeta_gi / f"lectura_facturas_{gi}.json", "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    if anclajes or frases_linea:
        n = enriquecer_excel(excel_resp, anclajes, frases_linea)
        print(f"[4/6] Respuestas enriquecidas (tarifa pactada y/o datos del soporte): {n} líneas")
    else:
        print(
            "[4/6] Sin tarifas ni datos de PDF que citar: las respuestas van con el texto del motor."
        )
    if sin_pdf:
        print(
            f"      SIN SOPORTE EN Y: ({len(sin_pdf)}): {', '.join(sin_pdf[:12])}"
            + ("..." if len(sin_pdf) > 12 else "")
        )

    # 5. Cargue al portal
    if args.sin_cargue:
        print("[5/6] --sin-cargue: el Excel queda listo; corra el robot cuando quiera.")
    else:
        reporte = carpeta_gi / f"reporte_{gi}.csv"
        cmd = [
            sys.executable,
            str(REPO / "tools" / "responder_glosas_simed.py"),
            "--excel",
            str(excel_resp),
            "--sin-soportes",
            "--reporte",
            str(reporte),
        ]
        cmd += ["--solo", args.piloto] if args.piloto else ["--todas"]
        if args.con_cabeza:
            cmd.append("--con-cabeza")
        print(
            f"[5/6] Corriendo el robot del portal ({'piloto ' + args.piloto if args.piloto else 'todas'})..."
        )
        subprocess.run(cmd, cwd=REPO)

        # 6. Evidencias del paquete
        pdf_ev = evidencias_a_pdf(gi, [args.piloto] if args.piloto else facturas, carpeta_gi)
        print(
            f"[6/6] Evidencias del paquete: {pdf_ev if pdf_ev else 'sin pantallazos de hoy (¿corrió el robot?)'}"
        )

    print(f"\nPaquete {gi} listo en {carpeta_gi}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
