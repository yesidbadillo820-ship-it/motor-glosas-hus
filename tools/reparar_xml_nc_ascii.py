"""reparar_xml_nc_ascii.py — Repara los XML de notas crédito que el portal de
SAVIA (Conexiones, conexiones.saviasaludeps.com) rechaza con:

    "Error al procesar el tag Numero en asignarNumeroFacturaDeXml :
     Invalid byte 2 of 4-byte UTF-8 sequence"

QUÉ PASA: el XML de la nota (AttachedDocument de la DIAN) es UTF-8 válido,
pero trae letras acentuadas («ó», «ñ», «Ó»…). El portal, al extraer el
documento embebido para leer el número de factura, re-codifica mal esos
acentos (latin-1) y su lector UTF-8 explota — una «ó» en latin-1 es el byte
0xF3, que UTF-8 interpreta como inicio de secuencia de 4 bytes.

QUÉ HACE ESTE BOT: convierte cada carácter acentuado a su entidad XML
numérica («ó» → «&#243;»), dejando el archivo 100 % ASCII. Al parsearlo, las
entidades resuelven EXACTAMENTE a las mismas letras: el contenido y las
firmas DIAN de los documentos embebidos (CreditNote y ApplicationResponse)
quedan canónicamente idénticos — el bot lo VERIFICA antes de escribir y no
escribe si algo no cuadra.

USO:
    py reparar_xml_nc_ascii.py --entrada "NC332660.xml"          # un archivo
    py reparar_xml_nc_ascii.py --entrada "CARPETA_DE_NOTAS"      # todos los .xml

    La salida queda en una subcarpeta ARREGLADOS con el MISMO nombre de
    archivo (listo para subir al portal). Con --salida se cambia el destino.

INSTALACIÓN: no necesita nada (solo Python).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger("reparar_xml_nc")

_RE_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def a_ascii_con_entidades(texto: str) -> str:
    """Cada carácter no-ASCII → entidad XML numérica (&#NNN;)."""
    return "".join(ch if ord(ch) < 128 else f"&#{ord(ch)};" for ch in texto)


def verificar_equivalencia(original: str, arreglado: str) -> list[str]:
    """Comprueba que el arreglo NO cambió el contenido: el documento exterior
    parsea y cada documento embebido (CDATA) queda canónicamente idéntico al
    original. Devuelve la lista de problemas (vacía = todo bien)."""
    problemas: list[str] = []
    if any(ord(c) >= 128 for c in arreglado):
        problemas.append("el resultado no quedó 100% ASCII")
    try:
        ET.fromstring(arreglado)
    except ET.ParseError as e:
        problemas.append(f"el documento exterior no parsea tras el arreglo: {e}")
        return problemas
    cd_orig = _RE_CDATA.findall(original)
    cd_fix = _RE_CDATA.findall(arreglado)
    if len(cd_orig) != len(cd_fix):
        problemas.append(f"cambió el número de documentos embebidos ({len(cd_orig)}→{len(cd_fix)})")
        return problemas
    for j, (a, b) in enumerate(zip(cd_orig, cd_fix, strict=True)):
        try:
            if ET.canonicalize(a) != ET.canonicalize(b):
                problemas.append(f"el documento embebido {j} cambió tras el arreglo")
        except ET.ParseError as e:
            problemas.append(f"el documento embebido {j} no parsea: {e}")
    return problemas


def reparar_archivo(ruta: Path, destino: Path) -> tuple[bool, str]:
    """Repara UN xml. Devuelve (se_escribio, mensaje)."""
    crudo = ruta.read_bytes()
    try:
        texto = crudo.decode("utf-8")
        codificacion = "utf-8"
    except UnicodeDecodeError:
        # Archivo ya dañado de origen (bytes latin-1 sueltos): rescatarlo.
        texto = crudo.decode("latin-1")
        codificacion = "latin-1 (¡el archivo ya venía dañado y se rescató!)"

    acentos = sum(1 for c in texto if ord(c) >= 128)
    if acentos == 0:
        return False, "ya era 100% ASCII — no necesita arreglo"

    arreglado = a_ascii_con_entidades(texto)
    problemas = verificar_equivalencia(texto, arreglado)
    if problemas:
        return False, "NO se escribió (verificación falló): " + "; ".join(problemas)

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(arreglado.encode("ascii"))
    return True, f"{acentos} acentos convertidos (leído como {codificacion})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        required=True,
        help="Un .xml de nota crédito, o una carpeta con varios.",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=None,
        help="Carpeta destino. Default: subcarpeta ARREGLADOS junto a la entrada.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.entrada.is_file():
        archivos = [args.entrada]
        base = args.entrada.parent
    elif args.entrada.is_dir():
        archivos = sorted(args.entrada.glob("*.xml"))
        base = args.entrada
    else:
        logger.error(f"No existe: {args.entrada}")
        return 1
    if not archivos:
        logger.error("No hay archivos .xml en la entrada.")
        return 1

    destino_dir = args.salida if args.salida is not None else base / "ARREGLADOS"
    ok = saltados = fallidos = 0
    for ruta in archivos:
        escrito, msg = reparar_archivo(ruta, destino_dir / ruta.name)
        if escrito:
            ok += 1
            logger.info(f"  ✔ {ruta.name}: {msg}")
        elif msg.startswith("NO"):
            fallidos += 1
            logger.error(f"  ✖ {ruta.name}: {msg}")
        else:
            saltados += 1
            logger.info(f"  – {ruta.name}: {msg}")

    logger.info(
        f"\n{ok} arreglado(s) en {destino_dir}  |  {saltados} sin necesidad  |  {fallidos} con problema"
    )
    return 0 if fallidos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
