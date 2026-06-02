"""generar_fur_servicios.py — Genera el Excel FUR SERVICIOS desde el RIPS.

Lee el RIPS de una factura y arma el Excel del **FUR SERVICIOS** (Diccionario
de 13 campos, Resolución 2284/2023), pre-rellenando las columnas que salen
del RIPS y dejando en blanco (resaltadas) las que diligencia el prestador.

Columnas auto-rellenadas desde el RIPS:
    NUM_FACTURA, NIT_PRESTADOR, Codificacion_CUPS, Descripción,
    Cantidad_de_servicios, Valor_unitario_facturado, Valor_total_facturado,
    Codigo_del_servicio (medicamentos/otros), y Tipo_de_servicio (best-effort).

Columnas que quedan para el prestador (resaltadas en naranja):
    Codigo_general_del_procedimiento_quirurgico, Consecutivo_procedimiento_quirurgico,
    Valor_unitario_reclamado, Valor_total_reclamado (se pre-cargan = facturado
    como punto de partida; el prestador los puede bajar).

USO
---

    # Desde la carpeta de la factura (busca el *_RIP.json adentro)
    py generar_fur_servicios.py ^
        --carpeta "C:\\Users\\Usuario\\Downloads\\FACTURAS\\HUS428139" ^
        --salida  "C:\\Users\\Usuario\\Downloads\\FACTURAS\\HUS428139_FURSERVICIOS.xlsx"

    # O apuntando directo al RIPS
    py generar_fur_servicios.py --rips "...\\HUS428139_RIP.json" --salida salida.xlsx

DEPENDENCIA: openpyxl (pip install openpyxl)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factura_lectura import cargar_factura_xml, hallar_factura_xml  # noqa: E402
from rips_lectura import (  # noqa: E402
    cargar_rips,
    datos_generales,
    extraer_lineas_servicios,
    inferir_tipo_por_codigo,
)

logger = logging.getLogger("gen_fur_servicios")

# (encabezado JSON, ¿auto?) en el orden exacto del Diccionario FUR SERVICIOS
COLUMNAS = [
    ("NUM_FACTURA", True),
    ("NIT_PRESTADOR", True),
    ("Tipo_de_servicio", True),  # best-effort (revisar)
    ("Codigo_general_del_procedimiento_quirurgico", False),
    ("Consecutivo_procedimiento_quirurgico", False),
    ("Codigo_del_servicio", True),
    ("Codificacion_CUPS", True),
    ("Descripción_del_servicio_o_elemento_reclamado", True),
    ("Cantidad_de_servicios", True),
    ("Valor_unitario_facturado", True),
    ("Valor_unitario_reclamado", False),
    ("Valor_total_facturado", True),
    ("Valor_total_reclamado", False),
]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _vr_eq(a: str, b: str) -> bool:
    """Compara dos importes que pueden venir como '83400', '83400.00' o ''."""
    try:
        return abs(float(a) - float(b)) < 0.5
    except (TypeError, ValueError):
        return False


def enriquecer_con_factura(linea: dict, items_factura: dict, usadas_por_precio: set) -> dict:
    """Completa descripción y Tipo de servicio desde la factura.

    Estrategia:
      1) Match por código directo (codTecnologiaSalud — funciona para
         medicamentos CUM, insumos FMQ/QX y osteosíntesis FMO).
      2) Si no hay match por código (típico de consultas/procedimientos:
         RIPS trae CUPS, factura trae SOAT), buscar UN solo ítem de la
         factura cuyo vr_total coincida y aún no se haya usado. Si hay
         empate, no se decide (queda para revisión manual).
    """
    cod = (linea.get("cod_servicio") or "").strip()
    enriquecida = dict(linea)

    # 1) Match por código directo
    if cod and cod in items_factura:
        item = items_factura[cod]
        if not enriquecida.get("descripcion") and item.get("descripcion"):
            enriquecida["descripcion"] = item["descripcion"]
        return enriquecida

    # 2) Match por valor (consultas/procedimientos donde RIPS=CUPS ≠ factura=SOAT)
    vr_total_rips = linea.get("vr_total") or ""
    if vr_total_rips:
        candidatos = [
            (k, v)
            for k, v in items_factura.items()
            if k not in usadas_por_precio and _vr_eq(v.get("vr_total", ""), vr_total_rips)
        ]
        if len(candidatos) == 1:
            cod_fact, item = candidatos[0]
            usadas_por_precio.add(cod_fact)
            if not enriquecida.get("descripcion") and item.get("descripcion"):
                enriquecida["descripcion"] = item["descripcion"]
            # Para procedimientos, el código del vendedor de la factura es el SOAT
            if linea.get("tipo_rips") in ("consultas", "procedimientos", "urgencias") and not cod:
                enriquecida["cod_servicio"] = cod_fact
        # Si hay múltiples candidatos o ninguno, dejamos como está (sin adivinar).

    return enriquecida


def fila_desde_linea(ln: dict) -> dict:
    """Mapea una línea normalizada del RIPS a las 13 columnas del FUR SERVICIOS."""
    # Si tipo de servicio sigue vacío, último intento por código (cod_servicio
    # puede haber sido completado desde la factura).
    tipo = ln.get("tipo_servicio_fur") or inferir_tipo_por_codigo(ln.get("cod_servicio", ""))
    return {
        "NUM_FACTURA": ln["num_factura"],
        "NIT_PRESTADOR": ln["nit_prestador"],
        "Tipo_de_servicio": tipo,
        "Codigo_general_del_procedimiento_quirurgico": "",
        "Consecutivo_procedimiento_quirurgico": "",
        "Codigo_del_servicio": ln["cod_servicio"],
        "Codificacion_CUPS": ln["cups"],
        "Descripción_del_servicio_o_elemento_reclamado": ln["descripcion"],
        "Cantidad_de_servicios": ln["cantidad"],
        "Valor_unitario_facturado": ln["vr_unitario"],
        # Punto de partida: reclamado = facturado (el prestador lo puede bajar)
        "Valor_unitario_reclamado": ln["vr_unitario"],
        "Valor_total_facturado": ln["vr_total"],
        "Valor_total_reclamado": ln["vr_total"],
    }


def escribir_excel(filas: list[dict], ruta: Path, meta: dict) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl.\n  Instalalo con:  py -m pip install openpyxl\n")
        sys.exit(2)

    wb = Workbook()
    ws = wb.active
    ws.title = "FUR_SERVICIOS"

    fill_auto = PatternFill("solid", fgColor="DCFCE7")  # verde claro: auto
    fill_manual = PatternFill("solid", fgColor="FFE8CC")  # naranja claro: manual
    header_font = Font(bold=True, size=9, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1E40AF")
    wrap = Alignment(wrap_text=True, vertical="center", horizontal="center")

    # Fila 1: encabezados
    for col_idx, (nombre, _auto) in enumerate(COLUMNAS, 1):
        c = ws.cell(row=1, column=col_idx, value=nombre)
        c.font = header_font
        c.fill = header_fill
        c.alignment = wrap
        ws.column_dimensions[get_column_letter(col_idx)].width = 22

    # Fila 2: leyenda auto/manual
    for col_idx, (_nombre, auto) in enumerate(COLUMNAS, 1):
        etiqueta = "AUTO (RIPS)" if auto else "← completar"
        c = ws.cell(row=2, column=col_idx, value=etiqueta)
        c.fill = fill_auto if auto else fill_manual
        c.font = Font(italic=True, size=8)
        c.alignment = wrap

    # Filas de datos
    for i, fila in enumerate(filas, start=3):
        for col_idx, (nombre, auto) in enumerate(COLUMNAS, 1):
            c = ws.cell(row=i, column=col_idx, value=fila.get(nombre, ""))
            if not auto:
                c.fill = fill_manual

    ws.freeze_panes = "A3"

    # Hoja de resumen / metadatos
    ws2 = wb.create_sheet("INFO")
    ws2["A1"] = "FUR SERVICIOS — generado automáticamente desde el RIPS"
    ws2["A1"].font = Font(bold=True)
    info_rows = [
        ("Número de factura", meta.get("num_factura", "")),
        ("NIT prestador", meta.get("nit_prestador", "")),
        ("Usuarios en RIPS", meta.get("num_usuarios", "")),
        ("Total líneas de servicio", len(filas)),
        ("", ""),
        ("Verde = autollenado desde el RIPS", ""),
        ("Naranja = lo completa el prestador", ""),
        ("", ""),
        ("OJO: 'Tipo_de_servicio' es best-effort:", ""),
        ("  consultas/procedim./urgencias → 2", ""),
        ("  medicamentos → 1", ""),
        ("  otrosServicios → vacío (insumo/dispositivo/osteo: completar)", ""),
        ("'Valor_*_reclamado' viene = facturado; bajalo si reclamás menos.", ""),
        ("'Codigo_del_servicio' para procedimientos requiere código SOAT", ""),
        ("  (el RIPS trae CUPS, no SOAT): revisar esa columna.", ""),
    ]
    for r, (k, v) in enumerate(info_rows, start=3):
        ws2.cell(row=r, column=1, value=k)
        ws2.cell(row=r, column=2, value=v)
    ws2.column_dimensions["A"].width = 55
    ws2.column_dimensions["B"].width = 20

    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)


def hallar_rips(carpeta: Path) -> Path | None:
    candidatos = [
        p
        for p in carpeta.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".json"
        and "RIP" in p.name.upper()
        and "CUV" not in p.name.upper()
    ]
    return candidatos[0] if candidatos else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--carpeta", type=Path, help="Carpeta de la factura (busca el *_RIP.json)")
    grupo.add_argument("--rips", type=Path, help="Ruta directa al RIPS .json")
    parser.add_argument("--salida", type=Path, required=True, help="Excel .xlsx de salida")
    args = parser.parse_args()
    setup_logging()

    if args.carpeta:
        if not args.carpeta.is_dir():
            logger.error(f"No existe la carpeta: {args.carpeta}")
            return 1
        rips_path = hallar_rips(args.carpeta)
        if not rips_path:
            logger.error(f"No encontré un *_RIP.json en {args.carpeta}")
            return 1
    else:
        rips_path = args.rips
        if not rips_path.is_file():
            logger.error(f"No existe el RIPS: {rips_path}")
            return 1

    logger.info(f"RIPS: {rips_path.name}")
    data = cargar_rips(rips_path)
    meta = datos_generales(data)
    lineas = extraer_lineas_servicios(data)

    if not lineas:
        logger.error("El RIPS no trae líneas de servicio (¿estructura distinta?).")
        logger.error(f"Claves raíz del RIPS: {sorted(data.keys())}")
        return 1

    # Enriquecer con la factura DIAN si está disponible (completa descripción
    # de consultas/procedimientos y agrega código SOAT).
    items_factura: dict = {}
    if args.carpeta:
        factura_path = hallar_factura_xml(args.carpeta)
        if factura_path:
            items_factura = cargar_factura_xml(factura_path)
            logger.info(f"FEV: {factura_path.name}  ({len(items_factura)} items)")
        else:
            logger.info("FEV: no encontrada — sin enriquecimiento por factura.")

    usadas_por_precio: set = set()
    if items_factura:
        lineas = [enriquecer_con_factura(ln, items_factura, usadas_por_precio) for ln in lineas]
        enriquecidas = sum(1 for ln in lineas if ln.get("descripcion"))
        logger.info(f"  Líneas con descripción tras enriquecer: {enriquecidas}/{len(lineas)}")

    filas = [fila_desde_linea(ln) for ln in lineas]
    escribir_excel(filas, args.salida, meta)

    logger.info(f"  Factura: {meta['num_factura']}   NIT: {meta['nit_prestador']}")
    logger.info(f"  Líneas de servicio: {len(filas)}")
    logger.info(f"  ✓ Excel generado: {args.salida}")
    logger.info("  Verde=autollenado / Naranja=completar el prestador (ver hoja INFO).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
