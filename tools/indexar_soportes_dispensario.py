"""indexar_soportes_dispensario.py — Indexador de soportes (Modulo 1 + 2).

Recorre UNA SOLA VEZ las carpetas de soportes (p. ej. la unidad de red
`Y:\\...`) y construye un INDICE (JSON) con una fila por documento: factura,
tipo, ruta, tamano, fecha y — para RIPS — paciente y numFactura. Despues, el
asistente de conciliacion consulta el indice y abre SOLO los archivos de la
factura que se esta trabajando, sin volver a recorrer `Y:\\` (que es lento).

Soporta actualizacion incremental (`--actualizar`): reusa lo ya indexado y solo
escanea archivos nuevos o modificados.

Tambien sirve de BUSCADOR (`--buscar HUS436483` o un documento/paciente).

CORRE EN LA MAQUINA DONDE ESTA MONTADA LA CARPETA DE SOPORTES (Windows, `Y:\\`).

USO
---
    # 1) Indexar (una sola vez; puede tardar, pero es una sola pasada)
    py tools\\indexar_soportes_dispensario.py ^
        --raiz "Y:\\7. JULIO 2026 - SOPORTES RADICACION" ^
        --raiz "Y:\\6. JUNIO 2026 - SOPORTES RADICACION" ^
        --salida "D:\\...\\indice_soportes.json" --con-meta

    # 2) Actualizar el indice mas tarde (rapido: solo lo nuevo)
    py tools\\indexar_soportes_dispensario.py --raiz "Y:\\..." ^
        --salida "D:\\...\\indice_soportes.json" --actualizar

    # 3) Buscar una factura en el indice (sin tocar Y:\\)
    py tools\\indexar_soportes_dispensario.py --salida "D:\\...\\indice_soportes.json" ^
        --buscar HUS436483

DEPENDENCIAS: solo openpyxl/pdfplumber no son necesarias aqui; usa stdlib +
el clasificador del asistente.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

# Reutiliza el clasificador y la normalizacion del asistente (misma fuente).
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from asistente_conciliacion_dispensario import clasificar, factura_corta  # noqa: E402

logger = logging.getLogger("indexar_soportes")

RE_FACTURA = re.compile(r"HUS0*([0-9]{4,10})")


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def facturas_en(nombre: str, carpeta: str) -> set[str]:
    """Facturas (cortas) mencionadas en el nombre del archivo o su carpeta."""
    texto = (nombre + " " + carpeta).upper()
    return {m.lstrip("0") for m in RE_FACTURA.findall(texto)}


def meta_liviana(ruta: Path) -> dict:
    """Metadatos baratos: para RIPS json, numFactura + primer paciente."""
    if ruta.suffix.lower() != ".json":
        return {}
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            data = json.loads(ruta.read_text(encoding=enc))
            break
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            data = None
        except Exception:  # noqa: BLE001
            data = None
    if not isinstance(data, dict):
        return {}
    usuarios = data.get("usuarios") or []
    paciente = ""
    if usuarios and isinstance(usuarios[0], dict):
        paciente = str(usuarios[0].get("numDocumentoIdentificacion", ""))
    return {
        "num_factura": str(data.get("numFactura") or data.get("numNota") or ""),
        "paciente": paciente,
    }


def construir_indice(raices: list[Path], previos: dict[str, dict], con_meta: bool) -> list[dict]:
    """Escanea las raices y devuelve la lista de registros del indice.

    previos: dict ruta -> registro (para actualizacion incremental).
    """
    documentos: list[dict] = []
    nuevos = reusados = 0
    for raiz in raices:
        if not raiz.exists():
            logger.warning("Raiz inexistente (¿unidad montada?): %s", raiz)
            continue
        for ruta in raiz.rglob("*"):
            if not ruta.is_file():
                continue
            facturas = facturas_en(ruta.name, str(ruta.parent))
            if not facturas:
                continue
            try:
                st = ruta.stat()
                mtime = st.st_mtime
                tamano = st.st_size
            except OSError:
                continue
            clave = str(ruta)
            prev = previos.get(clave)
            if prev and abs(prev.get("mtime_epoch", -1) - mtime) < 1e-6:
                documentos.append(prev)
                reusados += 1
                continue
            tipo = clasificar(ruta.name)
            meta = meta_liviana(ruta) if con_meta else {}
            for corta in facturas:
                documentos.append(
                    {
                        "factura": corta,
                        "tipo": tipo,
                        "nombre": ruta.name,
                        "ruta": clave,
                        "tamano": tamano,
                        "mtime_epoch": mtime,
                        "mtime": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
                        "paciente": meta.get("paciente", ""),
                        "num_factura": meta.get("num_factura", ""),
                    }
                )
                nuevos += 1
    logger.info("Indice: %d registros nuevos, %d reusados", nuevos, reusados)
    return documentos


def guardar_indice(documentos: list[dict], raices: list[Path], salida: Path) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "raices": [str(r) for r in raices],
        "documentos": documentos,
    }
    salida.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def cargar_indice(salida: Path) -> dict:
    if salida and salida.exists():
        try:
            return json.loads(salida.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def buscar(indice: dict, termino: str) -> list[dict]:
    """Busca por factura / paciente / nombre / ruta (subcadena, sin distinguir may/min)."""
    t = termino.strip().upper()
    tcorta = factura_corta(t)
    res = []
    for d in indice.get("documentos", []):
        if (
            (tcorta and d["factura"] == tcorta)
            or t in d["nombre"].upper()
            or t in d["ruta"].upper()
            or (d.get("paciente") and t in d["paciente"].upper())
        ):
            res.append(d)
    return res


def resumen(documentos: list[dict]) -> dict:
    facturas = {d["factura"] for d in documentos}
    por_tipo: dict[str, int] = {}
    for d in documentos:
        por_tipo[d["tipo"]] = por_tipo.get(d["tipo"], 0) + 1
    return {"documentos": len(documentos), "facturas": len(facturas), "por_tipo": por_tipo}


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(description="Indexador/buscador de soportes del Dispensario.")
    ap.add_argument(
        "--raiz",
        type=Path,
        action="append",
        default=[],
        help="Carpeta raiz de soportes (se puede repetir para varios meses)",
    )
    ap.add_argument("--salida", type=Path, required=True, help="Archivo JSON del indice")
    ap.add_argument("--actualizar", action="store_true", help="Incremental: reusa lo ya indexado")
    ap.add_argument("--con-meta", action="store_true", help="Leer RIPS para paciente/numFactura")
    ap.add_argument("--buscar", default=None, help="Solo buscar en el indice (no reindexar)")
    args = ap.parse_args(argv)

    if args.buscar:
        indice = cargar_indice(args.salida)
        if not indice:
            logger.error("No hay indice en %s. Corre primero la indexacion.", args.salida)
            return 1
        hits = buscar(indice, args.buscar)
        logger.info("'%s': %d documentos", args.buscar, len(hits))
        for d in hits:
            print(f"  [{d['tipo']}] {d['nombre']}  ->  {d['ruta']}")
        return 0

    if not args.raiz:
        logger.error("Indica al menos una --raiz para indexar.")
        return 2
    previo = cargar_indice(args.salida) if args.actualizar else {}
    previos = {d["ruta"]: d for d in previo.get("documentos", [])} if previo else {}
    documentos = construir_indice(args.raiz, previos, args.con_meta)
    guardar_indice(documentos, args.raiz, args.salida)
    r = resumen(documentos)
    logger.info("Indice guardado en %s", args.salida)
    logger.info("  %d documentos de %d facturas", r["documentos"], r["facturas"])
    for tipo, n in sorted(r["por_tipo"].items(), key=lambda x: -x[1]):
        logger.info("    %-40s %d", tipo, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
