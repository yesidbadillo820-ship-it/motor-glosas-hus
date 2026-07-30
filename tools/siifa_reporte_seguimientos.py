#!/usr/bin/env python3
"""siifa_reporte_seguimientos.py — Informe masivo de todos los seguimientos
(glosas y devoluciones) del HUS registrados en SIIFA.

El portal SIIFA (Seguimiento → Listar seguimientos) pagina de a 25 registros
y no tiene botón de exportar. Este script llama a la API oficial
(GET /api/SeguimientoFactura/List, ver docs/CONTEXTO_SIIFA.md) y trae TODO
paginando solo (hasta 1.500 registros por página), sin importar si son 2.579
o 20.000, y arma un Excel con una fila por seguimiento más una hoja resumen.

CREDENCIALES (variables de entorno, NUNCA en el código):
    setx SIIFA_USER <usuario_sispro>
    setx SIIFA_PASSWORD <password>
    setx SIIFA_AUTH_URL <url del servicio de Auth>   (ver docs/CONTEXTO_SIIFA.md — no confirmada)

USO:
    REM Todo lo que haya (glosas + devoluciones)
    py siifa_reporte_seguimientos.py --salida "D:\\...\\SIIFA\\informe_seguimientos.xlsx"

    REM Solo glosas sin responder (para priorizar el trabajo del día)
    py siifa_reporte_seguimientos.py --tipo GLOSA --sin-respuesta ^
        --salida "D:\\...\\SIIFA\\glosas_pendientes.xlsx"

    REM Solo una factura puntual
    py siifa_reporte_seguimientos.py --factura HUS532426 --salida "D:\\...\\HUS532426.xlsx"

INSTALACIÓN (una vez):
    py -m pip install httpx openpyxl
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from siifa_client import SiifaApiError, SiifaClient, credenciales_desde_env  # noqa: E402

logger = logging.getLogger("siifa_reporte")

COLUMNAS = [
    "id_seguimiento_factura_glosa",
    "tipo_seguimiento",
    "numero_factura",
    "nit_emisor",
    "razon_social_emisor",
    "valor_bruto_factura",
    "valor_glosa",
    "codigo_glosa",
    "descripcion_glosa",
    "observacion_glosa",
    "fecha_formulacion",
    "fecha_reporte",
    "tiene_respuesta",
    "codigo_respuesta",
    "descripcion_respuesta",
    "observacion_respuesta",
    "fecha_respuesta",
    "codigo_reiteracion",
    "descripcion_reiteracion",
    "codigo_reiteracion_respuesta",
    "descripcion_reiteracion_respuesta",
    "anexo",
]


def _get(fila: dict, *claves, default=""):
    for clave in claves:
        if clave in fila and fila[clave] not in (None, ""):
            return fila[clave]
    return default


def _fila_reporte(fila: dict) -> dict:
    factura = fila.get("factura") or {}
    emisor = factura.get("emisor") or {}
    tiene_respuesta = bool(_get(fila, "idSeguimientoTipoCodigoRespuesta"))
    return {
        "id_seguimiento_factura_glosa": _get(
            fila, "idSeguimientoFactura", "idSeguimientoFacturaGlosa"
        ),
        "tipo_seguimiento": _get(fila, "tipoSeguimiento"),
        "numero_factura": _get(factura, "numeroFactura"),
        "nit_emisor": _get(emisor, "nitEmisor"),
        "razon_social_emisor": _get(emisor, "razonSocial"),
        "valor_bruto_factura": _get(factura, "valorBruto", default=None),
        "valor_glosa": _get(fila, "valor", "valorGlosa", default=None),
        "codigo_glosa": _get(fila, "idSeguimientoTipoCodigo", "idSeguimientoTipoCodigoGlosa"),
        "descripcion_glosa": _get(
            fila, "descripcionSeguimientoTipoCodigo", "descripcionSeguimientoTipoCodigoGlosa"
        ),
        "observacion_glosa": _get(fila, "observacion"),
        "fecha_formulacion": _get(fila, "fechaFormulacion"),
        "fecha_reporte": _get(fila, "fechaReporte"),
        "tiene_respuesta": "SI" if tiene_respuesta else "NO",
        "codigo_respuesta": _get(fila, "idSeguimientoTipoCodigoRespuesta"),
        "descripcion_respuesta": _get(fila, "descripcionSeguimientoTipoCodigoRespuesta"),
        "observacion_respuesta": _get(fila, "observacionRespuesta"),
        "fecha_respuesta": _get(fila, "fechaRespuesta"),
        "codigo_reiteracion": _get(
            fila, "idSeguimientoTipoCodigoReiteracion", "idSeguimientoTipoCodigoGlosaReiteracion"
        ),
        "descripcion_reiteracion": _get(
            fila,
            "descripcionSeguimientoTipoCodigoReiteracion",
            "descripcionSeguimientoTipoCodigoGlosaReiteracion",
        ),
        "codigo_reiteracion_respuesta": _get(
            fila,
            "idSeguimientoTipoCodigoReiteracionRespuesta",
            "idSeguimientoTipoCodigoGlosaReiteracionRespuesta",
        ),
        "descripcion_reiteracion_respuesta": _get(
            fila,
            "descripcionSeguimientoTipoCodigoReiteracionRespuesta",
            "descripcionSeguimientoTipoCodigoGlosaReiteracionRespuesta",
        ),
        "anexo": _get(fila, "anexo"),
    }


def _resumen(filas: list[dict]) -> list[tuple]:
    agg: dict[tuple, dict] = defaultdict(lambda: {"cant": 0, "valor": 0.0, "sin_respuesta": 0})
    for f in filas:
        clave = (
            f["razon_social_emisor"] or f["nit_emisor"] or "SIN EMISOR",
            f["tipo_seguimiento"] or "?",
        )
        agg[clave]["cant"] += 1
        try:
            agg[clave]["valor"] += float(f["valor_glosa"] or 0)
        except (TypeError, ValueError):
            pass
        if f["tiene_respuesta"] == "NO":
            agg[clave]["sin_respuesta"] += 1
    return [
        (emisor, tipo, d["cant"], d["sin_respuesta"], d["valor"])
        for (emisor, tipo), d in sorted(agg.items(), key=lambda kv: -kv[1]["valor"])
    ]


def escribir_xlsx(filas: list[dict], ruta: Path) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise SystemExit("ERROR: falta openpyxl. py -m pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = "SEGUIMIENTOS"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for c, h in enumerate(COLUMNAS, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.fill = header_fill
        cell.font = header_font

    sin_respuesta_fill = PatternFill("solid", fgColor="FFC7CE")
    i_tiene_respuesta = COLUMNAS.index("tiene_respuesta")
    for r, fila in enumerate(filas, start=2):
        for c, h in enumerate(COLUMNAS, 1):
            cell = ws.cell(row=r, column=c, value=fila.get(h))
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=h in ("observacion_glosa", "observacion_respuesta", "descripcion_glosa"),
            )
        if fila["tiene_respuesta"] == "NO":
            ws.cell(row=r, column=i_tiene_respuesta + 1).fill = sin_respuesta_fill

    anchos = {
        "razon_social_emisor": 30,
        "descripcion_glosa": 30,
        "observacion_glosa": 45,
        "descripcion_respuesta": 30,
        "observacion_respuesta": 45,
        "numero_factura": 14,
    }
    for c, h in enumerate(COLUMNAS, 1):
        ws.column_dimensions[get_column_letter(c)].width = anchos.get(h, 16)
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("RESUMEN")
    encabezado = ["EPS / Emisor", "Tipo", "Cantidad", "Sin respuesta", "Valor total glosado"]
    ws2.append(encabezado)
    for c in range(1, len(encabezado) + 1):
        ws2.cell(row=1, column=c).fill = header_fill
        ws2.cell(row=1, column=c).font = header_font
    for emisor, tipo, cant, sin_resp, valor in _resumen(filas):
        ws2.append([emisor, tipo, cant, sin_resp, round(valor, 0)])
    for col, ancho in (("A", 34), ("B", 12), ("C", 10), ("D", 14), ("E", 20)):
        ws2.column_dimensions[col].width = ancho

    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(ruta))
    logger.info("Informe XLSX: %s (%d filas)", ruta, len(filas))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--salida", required=True, help="Ruta del Excel de salida.")
    ap.add_argument(
        "--tipo",
        choices=["GLOSA", "DEVOLUCION"],
        help="Filtrar por tipo de seguimiento (default: ambos).",
    )
    ap.add_argument(
        "--sin-respuesta",
        action="store_true",
        help="Solo seguimientos que todavía no tienen respuesta del HUS.",
    )
    ap.add_argument("--factura", help="Filtrar por número de factura (ej. HUS532426).")
    ap.add_argument("--desde", help="Fecha de creación desde (AAAA-MM-DD).")
    ap.add_argument("--hasta", help="Fecha de creación hasta (AAAA-MM-DD).")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    usuario, password = credenciales_desde_env()
    filas: list[dict] = []

    with SiifaClient() as cliente:
        try:
            cliente.login(usuario, password)
        except SiifaApiError as exc:
            raise SystemExit(f"ERROR de autenticación: {exc}")

        try:
            for cruda in cliente.listar_seguimientos(
                tipo_seguimiento=args.tipo,
                tiene_respuesta=False if args.sin_respuesta else None,
                numero_factura=args.factura,
                fecha_creacion_inicio=args.desde,
                fecha_creacion_final=args.hasta,
            ):
                filas.append(_fila_reporte(cruda))
        except SiifaApiError as exc:
            raise SystemExit(f"ERROR consultando SIIFA: {exc}")

    if not filas:
        logger.warning("No se encontró ningún seguimiento con esos filtros.")
        return

    escribir_xlsx(filas, Path(args.salida))
    sin_respuesta = sum(1 for f in filas if f["tiene_respuesta"] == "NO")
    logger.info("Total: %d seguimientos (%d sin respuesta del HUS).", len(filas), sin_respuesta)


if __name__ == "__main__":
    main()
