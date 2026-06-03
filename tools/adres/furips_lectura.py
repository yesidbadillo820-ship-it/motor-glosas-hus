"""furips_lectura.py — Parser de los archivos FURIPS planos del HUS.

El HUS genera, por radicación ADRES, dos archivos de texto plano separados
por comas que consolidan TODAS las facturas del período:

    FURIPS2*.txt → detalle de servicios (una línea por servicio facturado)
    FURIPS1*.txt → encabezado de la reclamación (datos del paciente,
                   accidente, vehículo, diagnósticos, valores totales)

El FURIPS2 trae la información lista para el FUR SERVICIOS (Resolución
2284/2023): código SOAT del manual tarifario, descripción, cantidad y
valores; además marca la descomposición quirúrgica con una línea "padre"
(cantidad=0, valores=0) y 5 sub-renglones cuya descripción inicia con
"NNNNN-" donde NNNNN es el código del procedimiento padre. Esto evita el
parseo frágil del PDF.

Estructura FURIPS2 (9 columnas, sin header):
    [0] HUS<factura>      e.g. "HUS428139"
    [1] radicado          número interno de radicación
    [2] tipo              1=medicamentos  2=procedimientos / consultas / cirugía
                          5=insumos pre-llenados (jeringas con SSN, etc.)
                          6=dispositivos médicos / insumos consumibles
                          7=material de osteosíntesis
                          8=otros (artículo 87, laboratorios)
    [3] codigo            SOAT (tipo=2), CUM/IUM (tipo=1), INVIMA (tipo=6/7) o vacío
    [4] descripcion       nombre del servicio. Vacío para tipo=2 simple;
                          inicia con "NNNNN-" en sub-renglones quirúrgicos.
    [5] cantidad
    [6] vr_unitario
    [7] vr_total
    [8] vr_total_2        duplicado del vr_total

Sólo librería estándar (csv, re).
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

# Mapeo tipo FURIPS2 → Tipo_de_servicio del FUR SERVICIOS (Resolución 2284/2023)
_TIPO_FURIPS_A_FUR = {
    "1": "1",  # Medicamentos
    "2": "2",  # Procedimientos
    "5": "5",  # Insumos
    "6": "6",  # Dispositivos médicos
    "7": "7",  # Material de osteosíntesis
    "8": "8",  # Otros (artículo 87, laboratorios)
}

# Sub-renglón quirúrgico: descripción inicia con "NNNN-" o "NNNNN-".
# El parent code es 4-5 dígitos (CUPS/SOAT del procedimiento padre).
_RE_PREFIJO_QUIRURGICO = re.compile(r"^(\d{4,5})-")


def _leer_texto(ruta: Path) -> str:
    """Lee el archivo probando varias codificaciones, en orden.

    Los FURIPS del HUS suelen venir en Windows-1252 / latin-1 (acentos como
    0xC9='É'), NO en UTF-8. Hay que leer los bytes y decodificar de verdad:
    `open(encoding=...)` no sirve para detectar, porque el error de
    decodificación sólo se lanza al leer, no al abrir el handle.
    """
    raw = ruta.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # latin-1 mapea cualquier byte 0..255; este fallback no debería alcanzarse.
    return raw.decode("latin-1", errors="replace")


def _entero(s: str) -> str:
    """Devuelve `s` sin decimales finales tipo '.0'. Vacío si no aplica."""
    s = (s or "").strip()
    if not s:
        return ""
    if "." in s:
        s = s.split(".", 1)[0]
    return s


def iter_filas_furips2(ruta: Path):
    """Itera las filas crudas del FURIPS2 como dict con columnas nombradas."""
    for row in csv.reader(_leer_texto(ruta).splitlines()):
        if len(row) < 9:
            continue
        yield {
            "factura_hus": row[0].strip(),
            "radicado": row[1].strip(),
            "tipo": row[2].strip(),
            "codigo": row[3].strip(),
            "descripcion": row[4].strip(),
            "cantidad": row[5].strip(),
            "vr_unitario": row[6].strip(),
            "vr_total": row[7].strip(),
        }


def facturas_en_furips2(ruta: Path) -> list[str]:
    """Devuelve la lista ordenada de facturas (HUS...) presentes en el FURIPS2."""
    vistas: set[str] = set()
    for fila in iter_filas_furips2(ruta):
        if fila["factura_hus"]:
            vistas.add(fila["factura_hus"])
    return sorted(vistas)


def cargar_furips2(
    ruta: Path,
    factura_id: str,
    nit_prestador: str = "",
) -> list[dict]:
    """Lee el FURIPS2 y devuelve líneas normalizadas para UNA factura.

    `factura_id` se compara contra la columna factura_hus. Acepta tanto
    "HUS428139" como "428139" (se prefija "HUS" automáticamente).

    Las líneas "padre" de cirugía (tipo=2, cantidad=0, valor=0, código
    numérico 4-5 dígitos, descripción con el nombre del procedimiento) se
    DESCARTAN — sólo sirven para identificar el grupo quirúrgico, no son
    una línea facturable. Sus sub-renglones sí entran al FUR llevando el
    código del padre en `cod_general_quirurgico` y el consecutivo en
    `consecutivo_quirurgico`.

    Cada línea devuelta es compatible con el `fila_desde_linea` del
    generador FUR SERVICIOS — tiene los mismos campos que produce
    `_linea_desde_pdf`.
    """
    factura_id = factura_id.strip().upper()
    if not factura_id.startswith("HUS"):
        factura_id = "HUS" + factura_id

    consecutivo = 0
    parent_code_actual = ""  # último código de cirugía padre abierto
    lineas: list[dict] = []

    for fila in iter_filas_furips2(ruta):
        if fila["factura_hus"].upper() != factura_id:
            continue

        tipo_furips = fila["tipo"]
        codigo = fila["codigo"]
        descripcion = fila["descripcion"]
        cant = _entero(fila["cantidad"])
        vr_u = _entero(fila["vr_unitario"])
        vr_t = _entero(fila["vr_total"])

        # ¿Línea "padre" de cirugía descompuesta?
        es_padre = (
            tipo_furips == "2"
            and cant in ("0", "")
            and vr_u in ("0", "")
            and vr_t in ("0", "")
            and codigo.isdigit()
            and 3 <= len(codigo) <= 5
            and bool(descripcion)
        )
        if es_padre:
            consecutivo += 1
            parent_code_actual = codigo
            continue  # la padre NO se incluye en el FUR

        # ¿Sub-renglón quirúrgico? Descripción inicia con "NNNN-..."
        cgq = ""
        cons = ""
        desc_limpia = descripcion
        m = _RE_PREFIJO_QUIRURGICO.match(descripcion)
        if m and tipo_furips == "2":
            cod_padre = m.group(1)
            desc_limpia = descripcion[m.end():].lstrip()
            if cod_padre == parent_code_actual:
                cgq = parent_code_actual
                cons = str(consecutivo)
            else:
                # Sub-renglón sin padre abierto (línea suelta o fuera de orden).
                # Confiamos en el prefijo de la descripción para el código padre,
                # pero dejamos el consecutivo vacío para revisión manual.
                cgq = cod_padre

        tipo_fur = _TIPO_FURIPS_A_FUR.get(tipo_furips, "")

        lineas.append(
            {
                "num_factura": fila["factura_hus"],
                "nit_prestador": nit_prestador,
                "tipo_servicio_fur": tipo_fur,
                "cod_servicio": codigo,
                "cups": "",  # FURIPS no trae CUPS; se enlaza luego desde RIPS por valor
                "descripcion": desc_limpia,
                "cantidad": cant,
                "vr_unitario": vr_u,
                "vr_total": vr_t,
                "cod_general_quirurgico": cgq,
                "consecutivo_quirurgico": cons,
                "_seccion": "furips",
            }
        )

    return lineas


def hallar_furips2(carpeta: Path) -> Path | None:
    """Busca el FURIPS2*.txt en la carpeta y, si no, en la carpeta padre.

    HUS suele guardar el FURIPS2 a nivel del período (la carpeta padre de
    cada factura), por eso se mira un nivel arriba si en la carpeta de la
    factura no aparece.
    """
    for base in (carpeta, carpeta.parent):
        if not base or not base.exists() or not base.is_dir():
            continue
        for p in sorted(base.iterdir()):
            if (
                p.is_file()
                and p.suffix.lower() == ".txt"
                and p.name.upper().startswith("FURIPS2")
            ):
                return p
    return None


def hallar_furips1(carpeta: Path) -> Path | None:
    """Busca el FURIPS1*.txt en la carpeta y, si no, en la carpeta padre."""
    for base in (carpeta, carpeta.parent):
        if not base or not base.exists() or not base.is_dir():
            continue
        for p in sorted(base.iterdir()):
            if (
                p.is_file()
                and p.suffix.lower() == ".txt"
                and p.name.upper().startswith("FURIPS1")
            ):
                return p
    return None


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Smoke test del lector FURIPS2.")
    parser.add_argument("furips2", type=Path, help="Ruta al FURIPS2*.txt")
    parser.add_argument(
        "--factura",
        required=True,
        help="Identificador de factura, e.g. HUS428139 o 428139.",
    )
    parser.add_argument(
        "--nit", default="680010079201", help="NIT del prestador (HUS por defecto)"
    )
    parser.add_argument(
        "--listar", action="store_true", help="Lista las facturas presentes y sale."
    )
    args = parser.parse_args()

    if not args.furips2.is_file():
        sys.stderr.write(f"No existe: {args.furips2}\n")
        return 1

    if args.listar:
        for f in facturas_en_furips2(args.furips2):
            print(f)
        return 0

    lineas = cargar_furips2(args.furips2, args.factura, args.nit)
    print(f"Líneas para {args.factura}: {len(lineas)}")
    for ln in lineas[:80]:
        cgq = (
            f"[cgq={ln['cod_general_quirurgico']} cons={ln['consecutivo_quirurgico']}]"
            if ln["cod_general_quirurgico"]
            else ""
        )
        print(
            f"  T{ln['tipo_servicio_fur'] or '?':<1} {ln['cod_servicio']:<16} "
            f"{ln['descripcion'][:55]:<55} x{ln['cantidad']:<4} "
            f"${ln['vr_unitario']:>10} = ${ln['vr_total']:>12} {cgq}"
        )
    if len(lineas) > 80:
        print(f"  ... ({len(lineas) - 80} líneas más)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
