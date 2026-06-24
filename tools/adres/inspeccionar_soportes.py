"""inspeccionar_soportes.py — Inventario y lectura de soportes de una factura (ADRES).

Lee una carpeta con los soportes de UNA factura (RIPS, CUV, FEV XML, PDFs
clínicos) y reporta:

1. Inventario: clasifica cada archivo según el tipo de soporte ADRES
   (Resolución 2284/2023) y le asigna el nombre destino (FEV_*, RIP_*, etc.).
2. Datos del RIPS: NIT del prestador, número de factura, usuarios y el
   detalle de servicios (consultas, procedimientos, medicamentos, otros) que
   alimentan el FUR SERVICIOS.
3. Peek del FEV XML (DIAN): número de factura y NIT del emisor (best-effort).

NO modifica ni copia nada — sólo lee y reporta. Es la base para los
generadores de FUR / FUR SERVICIOS / JSON / ZIP.

Pensado para correr en cualquier PC: sólo usa la librería estándar de Python
(json, xml, argparse, pathlib). No requiere instalar nada.

USO
---

    # Resumen legible de una carpeta de factura
    py inspeccionar_soportes.py --carpeta "C:\\Users\\Usuario\\Downloads\\FACTURAS\\HUS428139"

    # Volcar TODO lo extraído a un JSON (para revisar la estructura completa)
    py inspeccionar_soportes.py --carpeta "...\\HUS428139" --volcar-json salida.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("inspeccionar_adres")

# ─── Clasificación de soportes según token en el nombre del archivo ──────────
# (HUS nombra así: <codHabilitacion>_<factura>_<TOKEN>.ext)
# Mapea TOKEN encontrado → (codigo ADRES, descripción)
TOKENS_SOPORTE = {
    "RIP": ("RIP", "RIPS - Registro individual de prestación de servicios"),
    "RIPS": ("RIP", "RIPS - Registro individual de prestación de servicios"),
    "CUV": ("CUV", "Resultado de validación RIPS (MSPS)"),
    "FACTURA": ("FEV/FAC", "Factura electrónica DIAN (XML=FEV, PDF=FAC)"),
    "FEV": ("FEV", "Factura electrónica DIAN (XML)"),
    "EPICRIS": ("EPI", "Epicrisis"),
    "EPI": ("EPI", "Epicrisis"),
    "INFOPOL": ("IPO", "Informe policial / aviso a entidad competente"),
    "HEV": ("HEV", "Resumen de atención u hoja de evolución"),
    "HAU": ("HAU", "Hoja de atención de urgencia"),
    "OPF": ("OPF", "Orden o prescripción facultativa"),
    "CRC": ("CRC", "Comprobante de recibido del usuario"),
    "PDX": ("PDX", "Resultado de procedimientos de apoyo diagnóstico"),
    "HAM": ("HAM", "Hoja de administración de medicamentos"),
    "DQX": ("DQX", "Descripción quirúrgica"),
    "RAN": ("RAN", "Registro de anestesia"),
    "TAP": ("TAP", "Traslado asistencial de pacientes"),
    "FMO": ("FMO", "Factura material de osteosíntesis"),
    "FACOSTE": ("?", "Factura/detalle de costos (no es soporte ADRES estándar)"),
}

# Tipos de servicio del RIPS que alimentan el FUR SERVICIOS
SERVICIOS_RIPS = (
    "consultas",
    "procedimientos",
    "medicamentos",
    "otrosServicios",
    "urgencias",
    "hospitalizacion",
    "recienNacidos",
)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def clasificar_archivo(nombre: str) -> tuple[str, str]:
    """Devuelve (codigo_adres, descripcion) según el token del nombre."""
    base = nombre.rsplit(".", 1)[0]
    tokens = base.replace("-", "_").split("_")
    for t in reversed(tokens):  # el token de tipo suele ir al final
        tu = t.upper()
        if tu in TOKENS_SOPORTE:
            return TOKENS_SOPORTE[tu]
    return ("ADM", "Sin clasificar (¿documento administrativo ADM_*?)")


def cargar_json(ruta: Path) -> dict | None:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with ruta.open(encoding=enc) as fh:
                return json.load(fh)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except OSError as e:
            logger.warning(f"  No pude abrir {ruta.name}: {e}")
            return None
    logger.warning(f"  No pude parsear JSON: {ruta.name}")
    return None


def resumir_rips(data: dict) -> dict:
    """Extrae los campos clave del RIPS para el FUR / FUR SERVICIOS."""
    resumen: dict = {
        "numFactura": data.get("numFactura") or data.get("numNota") or "",
        "numDocumentoIdObligado": data.get("numDocumentoIdObligado", ""),
        "tipoNota": data.get("tipoNota"),
        "numNota": data.get("numNota"),
        "usuarios": [],
        "conteo_servicios": {k: 0 for k in SERVICIOS_RIPS},
        "lineas_fur_servicios": [],
    }

    usuarios = data.get("usuarios") or []
    for u in usuarios:
        info_u = {
            "tipoDocumentoIdentificacion": u.get("tipoDocumentoIdentificacion", ""),
            "numDocumentoIdentificacion": u.get("numDocumentoIdentificacion", ""),
            "fechaNacimiento": u.get("fechaNacimiento", ""),
            "codSexo": u.get("codSexo", ""),
            "codMunicipioResidencia": u.get("codMunicipioResidencia", ""),
        }
        resumen["usuarios"].append(info_u)

        servicios = u.get("servicios") or {}
        for tipo in SERVICIOS_RIPS:
            items = servicios.get(tipo) or []
            resumen["conteo_servicios"][tipo] += len(items)
            for it in items:
                # Campos comunes que alimentan el FUR SERVICIOS (best-effort:
                # los nombres varían un poco entre consultas/procedim./medic.)
                linea = {
                    "tipo_rips": tipo,
                    "codTecnologiaSalud": it.get("codTecnologiaSalud", ""),
                    "codProcedimiento": it.get("codProcedimiento", ""),
                    "codConsulta": it.get("codConsulta", ""),
                    "nomTecnologiaSalud": it.get("nomTecnologiaSalud", ""),
                    "cantidad": (
                        it.get("cantidadOS")
                        or it.get("cantidadMedicamento")
                        or it.get("cantidad")
                        or ""
                    ),
                    "vrUnitario": (
                        it.get("vrUnitOS")
                        or it.get("vrUnitMedicamento")
                        or it.get("vrServicio")
                        or ""
                    ),
                    "vrServicio": it.get("vrServicio", ""),
                }
                resumen["lineas_fur_servicios"].append(linea)

    return resumen


def peek_fev_xml(ruta: Path) -> dict:
    """Intenta sacar número de factura y NIT del XML DIAN (best-effort).

    El FEV de la DIAN suele ser un AttachedDocument que envuelve el Invoice
    (a veces escapado dentro de cbc:Description). Hacemos una lectura tolerante.
    """
    info = {"archivo": ruta.name, "num_factura": "", "nit_emisor": "", "nota": ""}
    try:
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        info["nota"] = f"no se pudo leer: {e}"
        return info

    # 1) Si el Invoice viene escapado dentro del AttachedDocument, buscar tags
    # tolerando namespaces. Buscamos cbc:ID (número factura) y los datos del
    # AccountingSupplierParty. Como es best-effort, usamos búsquedas simples.
    # Número de factura: primer cbc:ID dentro de Invoice, o ID del AttachedDocument
    m = re.search(r"<cbc:ID>([^<]+)</cbc:ID>", texto)
    if m:
        info["num_factura"] = m.group(1).strip()

    # NIT del emisor: CompanyID dentro de AccountingSupplierParty
    m = re.search(
        r"AccountingSupplierParty.*?<cbc:CompanyID[^>]*>([^<]+)</cbc:CompanyID>",
        texto,
        re.DOTALL,
    )
    if m:
        info["nit_emisor"] = m.group(1).strip()
    else:
        m = re.search(r"<cbc:CompanyID[^>]*>([^<]+)</cbc:CompanyID>", texto)
        if m:
            info["nit_emisor"] = m.group(1).strip()

    return info


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--carpeta", type=Path, required=True, help="Carpeta con los soportes de UNA factura"
    )
    parser.add_argument(
        "--volcar-json",
        type=Path,
        default=None,
        help="Guarda todo lo extraído en este JSON (para revisar la estructura)",
    )
    args = parser.parse_args()
    setup_logging()

    if not args.carpeta.is_dir():
        logger.error(f"No existe la carpeta: {args.carpeta}")
        return 1

    archivos = sorted(p for p in args.carpeta.iterdir() if p.is_file())
    logger.info("=" * 70)
    logger.info(f"INVENTARIO: {args.carpeta}")
    logger.info("=" * 70)

    rips_path = cuv_path = fev_path = None
    inventario = []
    for p in archivos:
        cod, desc = clasificar_archivo(p.name)
        ext = p.suffix.lower()
        inventario.append({"archivo": p.name, "codigo_adres": cod, "descripcion": desc})
        logger.info(f"  [{cod:7}] {p.name}  ({p.stat().st_size:,} bytes)")
        logger.info(f"            → {desc}")
        nombre_up = p.name.upper()
        if ext == ".json" and ("RIP" in nombre_up):
            rips_path = p
        elif ext == ".json" and "CUV" in nombre_up:
            cuv_path = p
        elif ext == ".xml" and ("FACTURA" in nombre_up or "FEV" in nombre_up):
            fev_path = p

    salida_total: dict = {"carpeta": str(args.carpeta), "inventario": inventario}

    # ── RIPS ──────────────────────────────────────────────────────────────
    if rips_path:
        logger.info("")
        logger.info("-" * 70)
        logger.info(f"RIPS: {rips_path.name}")
        logger.info("-" * 70)
        data = cargar_json(rips_path)
        if data:
            logger.info(f"  Claves de nivel raíz: {sorted(data.keys())}")
            r = resumir_rips(data)
            salida_total["rips"] = r
            logger.info(f"  numFactura ............ {r['numFactura']}")
            logger.info(f"  NIT (numDocIdObligado)  {r['numDocumentoIdObligado']}")
            logger.info(f"  usuarios .............. {len(r['usuarios'])}")
            logger.info("  Servicios por tipo:")
            for tipo, n in r["conteo_servicios"].items():
                if n:
                    logger.info(f"      {tipo}: {n}")
            logger.info(f"  Total líneas FUR SERVICIOS: {len(r['lineas_fur_servicios'])}")
            # Muestra de las primeras 3 líneas
            for i, ln in enumerate(r["lineas_fur_servicios"][:3], 1):
                logger.info(f"      ej[{i}] {ln}")
            # Para verificar la estructura cruda de un servicio:
            u0 = (data.get("usuarios") or [{}])[0]
            serv0 = u0.get("servicios") or {}
            for tipo in SERVICIOS_RIPS:
                items = serv0.get(tipo) or []
                if items:
                    logger.info(f"  Claves crudas de un '{tipo}': {sorted(items[0].keys())}")
                    break
    else:
        logger.warning("\n  ⚠ No encontré el RIPS (.json con 'RIP' en el nombre)")

    # ── CUV ───────────────────────────────────────────────────────────────
    if cuv_path:
        data = cargar_json(cuv_path)
        if data:
            salida_total["cuv_claves"] = sorted(data.keys())
            logger.info("")
            logger.info(f"CUV: {cuv_path.name} — claves raíz: {sorted(data.keys())}")

    # ── FEV XML ───────────────────────────────────────────────────────────
    if fev_path:
        info = peek_fev_xml(fev_path)
        salida_total["fev"] = info
        logger.info("")
        logger.info(f"FEV XML: {fev_path.name}")
        logger.info(f"  num_factura (peek) .... {info['num_factura']}")
        logger.info(f"  nit_emisor (peek) ..... {info['nit_emisor']}")

    if args.volcar_json:
        args.volcar_json.write_text(
            json.dumps(salida_total, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"\n  Volcado completo guardado en: {args.volcar_json}")

    logger.info("")
    logger.info("Listo. Revisá el RIPS arriba: con esos campos armo el FUR SERVICIOS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
