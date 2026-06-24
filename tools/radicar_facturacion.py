"""radicar_facturacion.py — Radicador maestro multi-entidad de la ESE HUS.

Es el paso AGUAS ARRIBA de los bots de glosas: toma el lote de facturas que
entrega el área de FACTURACIÓN y lo deja listo para radicar ante cada entidad
(EPS, regímenes especiales, SOAT/ADRES). En una sola corrida:

  1. INVENTARÍA y TIPIFICA cada soporte de cada factura según el catálogo
     ADRES (Resolución 2284/2023): FEV, RIP, CUV, HEV, EPI, HAU, PDX, OPF,
     DQX, RAN, CRC, HAM, TAP, FMO, FUR, SER, IPO, … Detecta los que están
     mal nombrados o sin reconocer.
  2. LEE el RIPS y la factura electrónica (FEV) — reutiliza tools/adres/ —
     para sacar número de factura, NIT del prestador, usuarios, servicios y
     el valor total facturado.
  3. RESUELVE la ENTIDAD/pagador de cada factura (desde el manifiesto de
     facturación, desde la carpeta padre o desde el nombre) y la cruza con su
     PERFIL de radicación (data/perfiles_radicacion.json): soportes
     obligatorios, canal/portal, si exige CUV, nomenclatura y formato de
     paquete.
  4. VALIDA la completitud: soportes base (FEV+RIP+CUV), soportes esperados
     según los servicios del RIPS, consistencia del número de factura entre
     RIPS / FEV / carpeta, y CUV cuando la entidad lo exige.
  5. ARMA el paquete (con --armar): crea <destino>/<ENTIDAD>/<factura>/,
     renombra los soportes a la nomenclatura de la entidad, escribe un
     manifiesto por factura y, con --zip, genera el ZIP
     <NIT>_<AAAAMMDD>_<consecutivo>.zip.
  6. REPORTA: CSV por factura, resumen por entidad y resumen global, con
     estados claros (LISTA / FALTAN_SOPORTES / SIN_CUV / SIN_RIPS / SIN_FEV /
     ENTIDAD_NO_RESUELTA / REVISAR_TIPIFICACION).

Por defecto NO toca archivos: solo diagnostica y reporta (modo auditoría).
Pasá --armar para construir los paquetes y --zip para comprimirlos.

USO RÁPIDO
----------

    # Solo auditar el lote (no arma nada): tipificación + completitud + reporte
    py radicar_facturacion.py --origen "D:\\LOTE_FACTURACION_2026-06" \\
        --reporte "D:\\salida\\radicacion_2026-06.csv" --xlsx "D:\\salida\\radicacion_2026-06.xlsx"

    # Armar los paquetes por entidad (carpetas + renombrado ADRES)
    py radicar_facturacion.py --origen "D:\\LOTE" --destino "D:\\RADICAR" --armar

    # Armar y comprimir en ZIP por factura, solo una entidad
    py radicar_facturacion.py --origen "D:\\LOTE" --destino "D:\\RADICAR" \\
        --armar --zip --entidad COOSALUD

    # El lote viene de un share anidado (ESCANEO o factura_electronica): el
    # layout 'auto' (por defecto) ancla en las carpetas HUS<factura>.
    py radicar_facturacion.py --origen "/mnt/radicacion_2026/.../ESCANEO"

    # Mapear factura → entidad con un Excel/CSV de facturación
    py radicar_facturacion.py --origen "D:\\LOTE" --manifiesto "D:\\facturacion.xlsx"

LAYOUTS DE ENTRADA
------------------

    auto (def.)             Ancla en carpetas cuyo nombre es una factura
                            (HUS520769) y les asigna TODO lo que cuelga debajo
                            (incluye subcarpetas como RIPS/ y los documentos DIAN
                            fv…/ad…/ar…/.zip). Lo no anclado se agrupa por el
                            token del nombre. Fusiona por número de factura. Es
                            el más robusto: cubre todos los shares reales.
    carpeta-factura         Cada subcarpeta es UNA factura; todos sus archivos
                            le pertenecen. Fusiona árboles paralelos con el mismo
                            nombre de carpeta.
    lote                    Una carpeta con archivos de MUCHAS facturas: se
                            agrupan por el token _<factura>_ del nombre. Los
                            compartidos (FURIPS) se reparten a su carpeta.

LOS SHARES REALES
-----------------

    1) ESCANEO (RIPS + CUV, organizado por EPS):

        …\\ESCANEO\\<EPS>\\RIPS\\ENV-<lote>\\HUS<factura>\\
            HUS<factura>.json        ← RIPS (¡nombrado SOLO con la factura!)
            CUV_HUS<factura>.json    ← validación MSPS

       El RIPS viene SIN token (es solo <factura>.json) y la EPS sale de la
       carpeta <EPS> de la ruta.

    2) factura_electronica (FEV DIAN, organizado por factura):

        …\\FACTURAS_SALUD\\HUS<factura>\\
            RIPS\\                    ← subcarpeta con el RIPS (y CUV)
            ad09…xml                 ← AttachedDocument DIAN (CUFE) = la FEV
            ar09…xml                 ← ApplicationResponse (acuse DIAN)
            fv09…xml / fv09…pdf      ← factura de venta (XML + representación)
            HUS<factura>.zip         ← paquete FE comprimido

       Los nombres DIAN (fv…/ad…/ar…) se tipifican solos. Como la ruta NO trae
       la EPS, el radicador la lee del adquiriente (AccountingCustomerParty) de
       la propia factura electrónica — no necesitás --manifiesto (aunque podés
       usarlo para forzar/corregir el mapeo). 'auto' recoge el RIPS de la
       subcarpeta y los documentos DIAN en una sola factura.

DEPENDENCIAS
------------

    Núcleo: solo librería estándar (corre en cualquier PC).
    --xlsx y manifiesto .xlsx: openpyxl (py -m pip install openpyxl).
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import os
import re
import shutil
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("radicar")

# Reutilizamos los parsers ADRES (stdlib) que ya están vetados por el HUS.
_ADRES_DIR = Path(__file__).resolve().parent / "adres"
sys.path.insert(0, str(_ADRES_DIR))
try:
    from rips_lectura import (  # noqa: E402
        SERVICIOS_RIPS,
        cargar_rips,
        datos_generales,
        extraer_lineas_servicios,
    )

    _ADRES_OK = True
except ImportError:  # pragma: no cover - el módulo adres siempre acompaña al script
    _ADRES_OK = False
    SERVICIOS_RIPS = (
        "consultas",
        "procedimientos",
        "medicamentos",
        "otrosServicios",
        "urgencias",
        "hospitalizacion",
        "recienNacidos",
    )


# ─── Catálogo de soportes ADRES (Resolución 2284/2023) ───────────────────────
# TOKEN reconocido en el nombre del archivo → descripción del soporte.
# Mantiene los mismos códigos que tools/adres/inspeccionar_soportes.py y
# app/services/soportes_autodiscovery_service.py.
CODIGOS_SOPORTE: dict[str, str] = {
    "FEV": "Factura electrónica de venta (XML DIAN)",
    "FAC": "Factura de venta (PDF)",
    "FAT": "Factura / detalle de cobro",
    "FED": "Factura electrónica DIAN — documento adjunto (AttachedDocument/CUFE)",
    "ARD": "Acuse de la DIAN (ApplicationResponse)",
    "RIP": "RIPS — registro individual de prestación de servicios",
    "CUV": "Resultado de validación RIPS (MSPS / FEVRIPS)",
    "EPI": "Epicrisis",
    "HEV": "Resumen de atención u hoja de evolución (historia clínica)",
    "HAU": "Hoja de atención de urgencias",
    "HAO": "Hoja de atención odontológica",
    "HAM": "Hoja de administración de medicamentos",
    "OPF": "Orden o prescripción facultativa",
    "PDX": "Resultado de procedimientos de apoyo diagnóstico",
    "PDE": "Resultado de procedimientos / evolución",
    "DQX": "Descripción quirúrgica",
    "RAN": "Registro de anestesia",
    "CRC": "Comprobante de recibido del usuario / a cobro",
    "TAP": "Hoja de traslado asistencial de pacientes",
    "FMO": "Factura de material de osteosíntesis e insumos",
    "LDP": "Lista de precios",
    "FUR": "Formato Único de Reclamación (SOAT / ADRES)",
    "SER": "FUR Servicios (detalle de servicios reclamados)",
    "IPO": "Informe policial de accidente / aviso a autoridad",
    "CRA": "Constancia de atención / certificación",
    "VAL": "Validación RIPS — envío al validador (Doker), auxiliar",
    "ADM": "Documento administrativo / otros soportes",
}

# Tokens equivalentes que aparecen en los nombres reales del HUS → código ADRES.
_ALIAS_TOKEN: dict[str, str] = {
    "RIPS": "RIP",
    "FACTURA": "FEV",
    "EPICRIS": "EPI",
    "EPICRISIS": "EPI",
    "INFOPOL": "IPO",
    "FURIPS": "FUR",
    "RESULTADOSMSPS": "CUV",
    "RESULTADOSDOKER": "CUV",  # resultado de validación vía Doker (= CUV)
    "ENVIODOKER": "VAL",  # envío al validador Doker (auxiliar, no es soporte)
    "AD": "FEV",  # XML CUFE de la DIAN (ad0900...xml)
    "FACOSTE": "FAT",
}

# Soportes esperados por tipo de servicio del RIPS (Res. 2284/2023). Defaults;
# el JSON de perfiles los puede sobrescribir.
SOPORTES_BASE_DEFAULT = ["FEV", "RIP", "CUV"]
SOPORTES_POR_SERVICIO_DEFAULT: dict[str, list[str]] = {
    "consultas": [],
    "procedimientos": ["HEV"],
    "urgencias": ["HAU"],
    "hospitalizacion": ["EPI"],
    "medicamentos": ["OPF"],
    "otrosServicios": ["OPF"],
    "recienNacidos": ["EPI"],
}

PRESTADOR_NIT_DEFAULT = "900006037"
PATRON_FACTURA_DEFAULT = r"HUS\d{4,12}"

# Estados de salida (ordenados de peor a mejor para el resumen).
ESTADOS_PROBLEMA = (
    "ENTIDAD_NO_RESUELTA",
    "SIN_RIPS",
    "SIN_FEV",
    "SIN_CUV",
    "FALTAN_SOPORTES",
    "FACTURA_INCONSISTENTE",
    "REVISAR_TIPIFICACION",
)
ESTADOS_OK = ("LISTA",)


# ─── Normalización ───────────────────────────────────────────────────────────


def _norm(s: str | None) -> str:
    """Mayúsculas, sin tildes, espacios colapsados."""
    s = (s or "").strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return " ".join(s.split())


_RE_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitizar(nombre: str) -> str:
    return _RE_INVALIDOS.sub("_", nombre).strip()


_RE_HUS_CORTO = re.compile(r"^(HUS)0*(\d+)$", re.IGNORECASE)


def factura_corta(fac: str) -> str:
    """HUS0000409621 → HUS409621 (quita ceros de relleno). Algunos portales,
    como SIMED del Dispensario, rechazan el formato largo."""
    m = _RE_HUS_CORTO.match((fac or "").strip())
    return (m.group(1).upper() + m.group(2)) if m else fac


def normalizar_factura(fac: str) -> str:
    """Clave canónica para comparar facturas: HUS0000487523, HUS487523 y
    487523 colapsan a 487523 (mismo criterio que soportes_autodiscovery)."""
    f = (fac or "").strip().upper()
    f = re.sub(r"^HUS", "", f)
    f = f.lstrip("0")
    return f or "0"


# ─── Tipificación de soportes ────────────────────────────────────────────────


# Prefijos que en la realidad vienen pegados a dígitos (sin separador), típicos
# de los archivos compartidos por lote: FURIPS168001..., ResultadosMSPS_123,
# EPICRISIS123. Se evalúan por prefijo del nombre, del más largo al más corto
# para no confundir FURIPS con FUR ni RESULTADOSMSPS con RIPS.
_PREFIJOS_SOPORTE: tuple[tuple[str, str], ...] = (
    ("RESULTADOSMSPS", "CUV"),
    ("RESULTADOSDOKER", "CUV"),
    ("ENVIODOKER", "VAL"),
    ("FURIPS", "FUR"),
    ("EPICRISIS", "EPI"),
    ("EPICRIS", "EPI"),
    ("INFOPOL", "IPO"),
    ("FACOSTE", "FAT"),
    ("FACTURA", "FEV"),
)

# El RIPS "desnudo" del share real viene nombrado SOLO con el número de factura
# (HUS469401.json), sin token de soporte. Reconocemos ese patrón para no perder
# el RIPS ni reportarlo como SIN_RIPS. CUV_HUS469401.json no entra aquí porque
# se resuelve antes por el token CUV.
_RE_FACTURA_DESNUDA = re.compile(r"^(?:HUS)?\d{4,12}$", re.IGNORECASE)

# Factura electrónica DIAN: prefijo de 2 letras pegado al CUFE/consecutivo, como
# los del share factura_electronica_net22:
#   fv… = factura de venta (xml = FEV, pdf = representación gráfica)
#   ad… = AttachedDocument firmado con CUFE (la factura electrónica a radicar)
#   ar… = ApplicationResponse (acuse de la DIAN)
_RE_DIAN = re.compile(r"^(fv|ad|ar)\d{6,}", re.IGNORECASE)


def clasificar_soporte(nombre: str) -> tuple[str, str, bool]:
    """Devuelve (codigo_adres, descripcion, reconocido) según el TOKEN del
    nombre del archivo. Recorre los tokens de atrás hacia adelante porque el
    tipo suele ir al final (FEV_900006037_HUS487523.pdf → FEV). Si no hay token
    separado, intenta por prefijo (FURIPS168...txt → FUR), por nombre DIAN
    (fv…/ad…/ar…) y, en último lugar, reconoce el RIPS desnudo (HUS469401.json)
    o el paquete FE comprimido (HUS520769.zip)."""
    base = nombre.rsplit(".", 1)[0]
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    tokens = re.split(r"[ _\-.]+", base)
    for t in reversed(tokens):
        tu = t.upper()
        if tu in CODIGOS_SOPORTE:
            return tu, CODIGOS_SOPORTE[tu], True
        if tu in _ALIAS_TOKEN:
            cod = _ALIAS_TOKEN[tu]
            return cod, CODIGOS_SOPORTE[cod], True
    base_up = base.upper()
    for pref, cod in _PREFIJOS_SOPORTE:
        if base_up.startswith(pref):
            return cod, CODIGOS_SOPORTE[cod], True
    # Factura electrónica DIAN nombrada por CUFE (fv…/ad…/ar… + dígitos).
    m = _RE_DIAN.match(base.lower())
    if m:
        pref = m.group(1).lower()
        if pref == "fv":
            cod = "FEV" if ext == "xml" else "FAC"
        elif pref == "ad":
            cod = "FED"
        else:  # ar
            cod = "ARD"
        return cod, CODIGOS_SOPORTE[cod], True
    # Nombres "desnudos" (solo la factura): .json = RIPS, .zip = paquete FE.
    if _RE_FACTURA_DESNUDA.match(base):
        if ext == "json":
            return "RIP", CODIGOS_SOPORTE["RIP"], True
        if ext == "zip":
            return "FED", CODIGOS_SOPORTE["FED"], True
    return "ADM", "Sin clasificar (¿documento administrativo o nombre no ADRES?)", False


# ─── Perfiles de entidad ─────────────────────────────────────────────────────


@dataclass
class PerfilEntidad:
    id: str
    nombre: str
    alias: list[str] = field(default_factory=list)
    nit: str = ""
    eps_codigo: str = ""
    regimen: str = ""
    canal: str = ""
    portal: str = ""
    nomenclatura: str = "ADRES"
    cuv_obligatorio: bool = True
    soportes_extra: list[str] = field(default_factory=list)
    formato_paquete: str = "CARPETA"
    bot: str = ""
    observaciones: str = ""


@dataclass
class ConfigRadicacion:
    prestador_nombre: str = "ESE HOSPITAL UNIVERSITARIO DE SANTANDER"
    prestador_nit: str = PRESTADOR_NIT_DEFAULT
    patron_factura: str = PATRON_FACTURA_DEFAULT
    soportes_base: list[str] = field(default_factory=lambda: list(SOPORTES_BASE_DEFAULT))
    soportes_por_servicio: dict[str, list[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in SOPORTES_POR_SERVICIO_DEFAULT.items()}
    )
    entidades: list[PerfilEntidad] = field(default_factory=list)


def cargar_perfiles(ruta: Path | None) -> ConfigRadicacion:
    """Carga el JSON de perfiles. Si no se pasa ruta, busca
    data/perfiles_radicacion.json relativo al repo. Si no existe, usa los
    defaults embebidos (sin entidades → todo cae a SIN_PERFIL)."""
    if ruta is None:
        candidato = Path(__file__).resolve().parent.parent / "data" / "perfiles_radicacion.json"
        ruta = candidato if candidato.is_file() else None
    if ruta is None:
        logger.warning(
            "No se encontró data/perfiles_radicacion.json — uso defaults sin catálogo de entidades."
        )
        return ConfigRadicacion()
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo de perfiles: {ruta}")

    data = json.loads(ruta.read_text(encoding="utf-8"))
    prest = data.get("prestador") or {}
    sop = data.get("soportes") or {}
    cfg = ConfigRadicacion(
        prestador_nombre=prest.get("nombre", "ESE HOSPITAL UNIVERSITARIO DE SANTANDER"),
        prestador_nit=str(prest.get("nit", PRESTADOR_NIT_DEFAULT)),
        patron_factura=prest.get("patron_factura", PATRON_FACTURA_DEFAULT),
        soportes_base=list(sop.get("base_obligatorios", SOPORTES_BASE_DEFAULT)),
        soportes_por_servicio={
            k: list(v)
            for k, v in (sop.get("por_servicio") or SOPORTES_POR_SERVICIO_DEFAULT).items()
        },
    )
    for e in data.get("entidades", []):
        cfg.entidades.append(
            PerfilEntidad(
                id=e.get("id") or _norm(e.get("nombre", "")).replace(" ", "_"),
                nombre=e.get("nombre", ""),
                alias=list(e.get("alias", [])),
                nit=str(e.get("nit", "")),
                eps_codigo=str(e.get("eps_codigo", "")),
                regimen=e.get("regimen", ""),
                canal=e.get("canal", ""),
                portal=e.get("portal", ""),
                nomenclatura=e.get("nomenclatura", "ADRES"),
                cuv_obligatorio=bool(e.get("cuv_obligatorio", True)),
                soportes_extra=list(e.get("soportes_extra", [])),
                formato_paquete=e.get("formato_paquete", "CARPETA"),
                bot=e.get("bot", ""),
                observaciones=e.get("observaciones", ""),
            )
        )
    logger.info(f"Perfiles cargados: {len(cfg.entidades)} entidades desde {ruta.name}")
    return cfg


def resolver_entidad(hint: str | None, cfg: ConfigRadicacion) -> PerfilEntidad | None:
    """Resuelve un nombre/código de entidad contra el catálogo. Tolera código
    EPS embebido ('U220311 - DISPENSARIO ...'), tildes y truncamientos."""
    if not hint:
        return None
    h = hint.strip()
    # Quitar prefijo de código EPS estilo DGH: "U220311 - NOMBRE".
    m = re.match(r"^\s*([A-Za-z]\d{5,})\s*[-–:·]\s*(.+)$", h)
    cod = m.group(1).upper() if m else ""
    if m:
        h = m.group(2)
    hn = _norm(h)
    if not hn:
        return None

    mejor: PerfilEntidad | None = None
    mejor_len = -1
    for ent in cfg.entidades:
        # Match por código EPS.
        if cod and ent.eps_codigo and cod == ent.eps_codigo.upper():
            return ent
        for a in [ent.nombre, *ent.alias]:
            an = _norm(a)
            if not an:
                continue
            if an == hn:
                return ent
            # Contención en cualquier dirección, gana el alias más largo (más
            # específico) para no confundir 'SALUD TOTAL' con 'SALUD'.
            if (an in hn or hn in an) and len(an) > mejor_len:
                mejor, mejor_len = ent, len(an)
    return mejor


# ─── Lectura de RIPS / FEV ───────────────────────────────────────────────────

_RE_CBC_ID = re.compile(r"<cbc:ID>([^<]+)</cbc:ID>")


def peek_num_factura_fev(ruta: Path) -> str:
    """Número de factura del FEV XML (best-effort, tolera el wrapping DIAN)."""
    try:
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    m = _RE_CBC_ID.search(texto)
    return m.group(1).strip() if m else ""


# Adquiriente (EPS) del AccountingCustomerParty del FEV. Permite resolver la
# entidad cuando la ruta no la trae (share de factura electrónica). Funciona con
# el Invoice directo y con el Invoice embebido (CDATA o escapado) de un
# AttachedDocument DIAN.
_RE_CLIENTE_REG = re.compile(
    r"AccountingCustomerParty.*?RegistrationName[^>]*>\s*([^<]+?)\s*<",
    re.IGNORECASE | re.DOTALL,
)
_RE_CLIENTE_NOM = re.compile(
    r"AccountingCustomerParty.*?PartyName.*?:Name[^>]*>\s*([^<]+?)\s*<",
    re.IGNORECASE | re.DOTALL,
)


def peek_eps_fev(ruta: Path) -> str:
    """Nombre del adquiriente (EPS) leído de la factura electrónica."""
    try:
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    for _ in range(2):
        m = _RE_CLIENTE_REG.search(texto) or _RE_CLIENTE_NOM.search(texto)
        if m:
            return m.group(1).strip()
        if "&lt;" not in texto:
            break
        texto = html.unescape(texto)  # Invoice embebido y escapado en un AD.
    return ""


def _leer_rips(ruta: Path) -> dict | None:
    if not _ADRES_OK:
        try:
            return json.loads(ruta.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return None
    try:
        return cargar_rips(ruta)
    except (ValueError, OSError):
        return None


# ─── Inventario de una factura ───────────────────────────────────────────────


@dataclass
class ResultadoFactura:
    factura: str = ""
    factura_norm: str = ""
    carpeta: str = ""
    entidad_hint: str = ""
    entidad_id: str = ""
    entidad_nombre: str = "SIN_PERFIL"
    canal: str = ""
    nit_prestador: str = ""
    num_usuarios: int = 0
    valor_total: float = 0.0
    servicios: dict[str, int] = field(default_factory=dict)
    soportes_presentes: list[str] = field(default_factory=list)
    soportes_faltantes: list[str] = field(default_factory=list)
    soportes_esperados_faltantes: list[str] = field(default_factory=list)
    archivos_sin_clasificar: list[str] = field(default_factory=list)
    n_archivos: int = 0
    estado: str = ""
    detalle: list[str] = field(default_factory=list)
    ruta_paquete: str = ""
    acciones: list[str] = field(default_factory=list)


def _archivos_de(carpeta: Path) -> list[Path]:
    return sorted(p for p in carpeta.iterdir() if p.is_file()) if carpeta.is_dir() else []


def procesar_factura(
    factura_hint: str,
    archivos: list[Path],
    carpeta: Path,
    entidad_hint: str | None,
    cfg: ConfigRadicacion,
) -> ResultadoFactura:
    """Diagnóstico de UNA factura: tipifica soportes, lee RIPS/FEV, resuelve
    entidad y valida completitud. NO toca archivos."""
    res = ResultadoFactura(carpeta=str(carpeta), entidad_hint=entidad_hint or "")
    res.n_archivos = len(archivos)

    # ── Tipificación de soportes ───────────────────────────────────────────
    presentes: set[str] = set()
    por_codigo: dict[str, list[Path]] = defaultdict(list)
    rips_path: Path | None = None
    fev_path: Path | None = None
    fed_path: Path | None = None
    for p in archivos:
        cod, _desc, reconocido = clasificar_soporte(p.name)
        por_codigo[cod].append(p)
        if reconocido:
            presentes.add(cod)
        else:
            res.archivos_sin_clasificar.append(p.name)
        sfx = p.suffix.lower()
        # El RIPS es el .json tipificado como RIP (incluye el desnudo
        # HUS469401.json). El CUV es otro .json y NO debe tomarse como RIPS.
        if sfx == ".json" and cod == "RIP" and rips_path is None:
            rips_path = p
        elif sfx == ".xml" and cod == "FEV" and fev_path is None:
            fev_path = p
        elif sfx == ".xml" and cod == "FED" and fed_path is None:
            fed_path = p
    # Preferir el Invoice (fv…, FEV) sobre el AttachedDocument (ad…, FED): el AD
    # lleva su PROPIO cbc:ID (no el número de la factura), lo que provocaba
    # falsos FACTURA_INCONSISTENTE. El AD sólo se usa si no hay Invoice.
    fev_es_invoice = fev_path is not None
    if fev_path is None:
        fev_path = fed_path
    # El documento adjunto DIAN (FED, ad…xml o el .zip) ES la factura
    # electrónica: cuenta como FEV para la completitud.
    if "FED" in presentes:
        presentes.add("FEV")
    # Fallback FEV: si ningún XML quedó tipificado como FEV/FED (nombre atípico),
    # tomar el primer XML que no sea la factura de costo (FACOSTE/FAT) ni un
    # acuse de la DIAN (ApplicationResponse).
    if fev_path is None:
        for p in archivos:
            if (
                p.suffix.lower() == ".xml"
                and p not in por_codigo["FAT"]
                and p not in por_codigo["ARD"]
            ):
                fev_path = p
                break
    res.soportes_presentes = sorted(presentes)

    # ── Datos del RIPS ──────────────────────────────────────────────────────
    num_rips = ""
    if rips_path is not None:
        data = _leer_rips(rips_path)
        if data is not None:
            gen = datos_generales(data) if _ADRES_OK else {}
            num_rips = (gen.get("num_factura") if _ADRES_OK else data.get("numFactura")) or ""
            res.nit_prestador = (
                gen.get("nit_prestador") if _ADRES_OK else data.get("numDocumentoIdObligado")
            ) or ""
            res.num_usuarios = (
                gen.get("num_usuarios") if _ADRES_OK else len(data.get("usuarios") or [])
            )
            res.servicios = _contar_servicios(data)
            res.valor_total = _valor_total(data)
    res.nit_prestador = res.nit_prestador or cfg.prestador_nit

    num_fev = peek_num_factura_fev(fev_path) if fev_path is not None else ""

    # ── Número de factura definitivo ────────────────────────────────────────
    res.factura = num_rips or factura_hint or num_fev or carpeta.name
    res.factura_norm = normalizar_factura(res.factura)

    # ── Resolución de entidad ───────────────────────────────────────────────
    perfil = resolver_entidad(entidad_hint, cfg)
    if perfil is None:
        # Sin pista por ruta/manifiesto (típico del share de factura
        # electrónica): leer el adquiriente (EPS) de la propia FEV. Se prueba
        # primero el Invoice (fv…) y luego el AttachedDocument (ad…).
        eps_detectada = ""
        for cand in (*por_codigo.get("FEV", []), *por_codigo.get("FED", [])):
            if cand.suffix.lower() != ".xml":
                continue
            eps_fev = peek_eps_fev(cand)
            if eps_fev and not eps_detectada:
                eps_detectada = eps_fev
            perfil = resolver_entidad(eps_fev, cfg)
            if perfil is not None:
                eps_detectada = eps_fev
                break
        # Guardar el nombre leído del FEV (aunque NO matchee el catálogo) para
        # diagnóstico: aparece en el detalle de las ENTIDAD_NO_RESUELTA.
        if eps_detectada and not res.entidad_hint:
            res.entidad_hint = eps_detectada
    if perfil is not None:
        res.entidad_id = perfil.id
        res.entidad_nombre = perfil.nombre
        res.canal = perfil.canal

    # ── Completitud ─────────────────────────────────────────────────────────
    base = set(cfg.soportes_base)
    if perfil is not None and not perfil.cuv_obligatorio:
        base.discard("CUV")
    if perfil is not None:
        base |= set(perfil.soportes_extra)
    res.soportes_faltantes = sorted(base - presentes)

    esperados: set[str] = set()
    for serv, n in res.servicios.items():
        if n:
            esperados |= set(cfg.soportes_por_servicio.get(serv, []))
    res.soportes_esperados_faltantes = sorted(esperados - presentes - base)

    res.estado, res.detalle = _evaluar_estado(
        res, perfil, num_rips, num_fev, rips_path, fev_path, fev_es_invoice
    )
    return res


def _contar_servicios(data: dict) -> dict[str, int]:
    conteo: dict[str, int] = dict.fromkeys(SERVICIOS_RIPS, 0)
    for u in data.get("usuarios") or []:
        servicios = u.get("servicios") or {}
        for tipo in SERVICIOS_RIPS:
            conteo[tipo] += len(servicios.get(tipo) or [])
    return {k: v for k, v in conteo.items() if v}


def _valor_total(data: dict) -> float:
    if _ADRES_OK:
        total = 0.0
        for ln in extraer_lineas_servicios(data):
            try:
                total += float(ln.get("vr_total") or 0)
            except (TypeError, ValueError):
                continue
        return round(total, 2)
    total = 0.0
    for u in data.get("usuarios") or []:
        for items in (u.get("servicios") or {}).values():
            for it in items or []:
                try:
                    total += float(it.get("vrServicio") or 0)
                except (TypeError, ValueError):
                    continue
    return round(total, 2)


def _evaluar_estado(
    res: ResultadoFactura,
    perfil: PerfilEntidad | None,
    num_rips: str,
    num_fev: str,
    rips_path: Path | None,
    fev_path: Path | None,
    fev_es_invoice: bool = True,
) -> tuple[str, list[str]]:
    detalle: list[str] = []

    if perfil is None:
        detalle.append(
            f"No se pudo resolver la entidad (pista: '{res.entidad_hint or '—'}'). "
            "Usá --manifiesto o organizá el lote en carpetas por EPS."
        )

    if rips_path is None:
        detalle.append("Falta el RIPS (.json).")
    if fev_path is None:
        detalle.append("Falta la factura electrónica (FEV .xml).")

    # Nota (NO bloqueante) sobre el número de factura entre RIPS y FEV. La
    # factura electrónica DIAN suele numerarse con otra serie que el RIPS, así
    # que una diferencia es esperable y NO debe impedir radicar; la identidad de
    # la factura la da el RIPS / la carpeta. Solo se compara con un Invoice real
    # (el AttachedDocument lleva su propio cbc:ID) y con números plausibles.
    fuentes = {
        n
        for n in (normalizar_factura(num_rips), normalizar_factura(num_fev))
        if n != "0" and n.isdigit() and len(n) <= 12
    }
    if fev_es_invoice and len(fuentes) > 1:
        detalle.append(
            f"Nota: el número del FEV ({num_fev or '—'}) difiere del RIPS "
            f"({num_rips or '—'}); normal si la FE usa otra numeración."
        )

    if res.soportes_faltantes:
        detalle.append("Faltan soportes obligatorios: " + ", ".join(res.soportes_faltantes) + ".")
    if res.soportes_esperados_faltantes:
        detalle.append(
            "Soportes esperados según los servicios (revisar): "
            + ", ".join(res.soportes_esperados_faltantes)
            + "."
        )
    if res.archivos_sin_clasificar:
        detalle.append(
            f"{len(res.archivos_sin_clasificar)} archivo(s) sin tipificar (renombrar a la "
            "nomenclatura ADRES <TOKEN>_<NIT>_<factura>): "
            + ", ".join(res.archivos_sin_clasificar[:5])
            + ("…" if len(res.archivos_sin_clasificar) > 5 else "")
        )

    # Estado: el primer problema bloqueante manda.
    if perfil is None:
        return "ENTIDAD_NO_RESUELTA", detalle
    if rips_path is None:
        return "SIN_RIPS", detalle
    if fev_path is None:
        return "SIN_FEV", detalle
    if "CUV" in res.soportes_faltantes:
        return "SIN_CUV", detalle
    if res.soportes_faltantes:
        return "FALTAN_SOPORTES", detalle
    if res.archivos_sin_clasificar or res.soportes_esperados_faltantes:
        return "REVISAR_TIPIFICACION", detalle
    detalle.append("Lista para radicar.")
    return "LISTA", detalle


def _debe_armar(estado: str, forzar: bool) -> bool:
    if estado == "LISTA":
        return True
    return estado == "REVISAR_TIPIFICACION" and forzar


# ─── Descubrimiento del lote ─────────────────────────────────────────────────


def _entidad_desde_ruta(carpeta: Path, origen: Path, cfg: ConfigRadicacion) -> str | None:
    """Busca, de la carpeta hacia arriba hasta origen, un componente de ruta
    que resuelva a una entidad conocida (la carpeta EPS del share)."""
    try:
        rel = carpeta.relative_to(origen)
    except ValueError:
        rel = Path(carpeta.name)
    for parte in reversed(rel.parts):
        # Saltar carpetas contenedoras del share (no son entidades): ENV-…,
        # ESCANEO, RIPS, SOPORTES, FE/FACTURA…, y prefijos numéricos
        # tipo "1. DD FACTURACION".
        if re.match(
            r"(?i)^(env[-_].*|escaneo|soportes.*|rips|fe|factura.*|xml|pdf|\d+\..*)$", parte
        ):
            continue
        if resolver_entidad(parte, cfg) is not None:
            return parte
    return None


def descubrir_carpeta_factura(
    origen: Path, manifiesto: dict[str, str], cfg: ConfigRadicacion
) -> list[tuple[str, list[Path], Path, str | None]]:
    """Layout carpeta-factura: cada carpeta con archivos directos es una
    factura. Devuelve [(factura_hint, archivos, carpeta, entidad_hint)].

    En el share real una misma factura aparece en árboles PARALELOS (p.ej.
    …/RIPS/ENV-…/HUS469401/ con el RIPS+CUV y …/SOPORTES/ENV-…/HUS469401/ con
    el FEV y los PDFs): dos carpetas con el MISMO nombre de factura. Se FUSIONAN
    por número de factura para no reportar la misma dos veces ni dejarla
    incompleta."""
    carpetas: list[Path] = []
    raiz_archivos = _archivos_de(origen)
    if raiz_archivos:
        carpetas.append(origen)
    for d in sorted(p for p in origen.rglob("*") if p.is_dir()):
        if _archivos_de(d):
            carpetas.append(d)

    fusion: dict[str, list] = {}
    orden: list[str] = []
    for c in carpetas:
        archivos = _archivos_de(c)
        fac_hint = c.name
        ent = manifiesto.get(normalizar_factura(fac_hint)) or _entidad_desde_ruta(c, origen, cfg)
        # Fusionar solo cuando el nombre de la carpeta ES una factura
        # (HUS469401); si no, cada carpeta es única (clave = su ruta).
        clave = (
            "F:" + normalizar_factura(fac_hint)
            if _RE_FACTURA_DESNUDA.match(fac_hint)
            else "D:" + str(c)
        )
        if clave in fusion:
            slot = fusion[clave]
            ya = {p.name for p in slot[1]}
            slot[1].extend(p for p in archivos if p.name not in ya)
            if not slot[3] and ent:
                slot[3] = ent
        else:
            fusion[clave] = [fac_hint, list(archivos), c, ent]
            orden.append(clave)
    return [tuple(fusion[k]) for k in orden]


def descubrir_lote(
    origen: Path, manifiesto: dict[str, str], cfg: ConfigRadicacion, patron: str
) -> list[tuple[str, list[Path], Path, str | None]]:
    """Layout lote: muchos archivos por carpeta, agrupados por el token
    _<factura>_ del nombre. Los compartidos (sin factura en el nombre, ej.
    FURIPS) se asocian a todas las facturas de su carpeta."""
    rx = re.compile(patron, re.IGNORECASE)
    grupos: dict[str, list[Path]] = defaultdict(list)
    carpeta_de: dict[str, Path] = {}
    compartidos_por_dir: dict[Path, list[Path]] = defaultdict(list)
    facturas_por_dir: dict[Path, set[str]] = defaultdict(set)

    for p in sorted(x for x in origen.rglob("*") if x.is_file()):
        m = rx.search(p.name)
        if m:
            clave = normalizar_factura(m.group(0))
            grupos[clave].append(p)
            carpeta_de.setdefault(clave, p.parent)
            facturas_por_dir[p.parent].add(clave)
        else:
            compartidos_por_dir[p.parent].append(p)

    # Repartir compartidos a cada factura de su carpeta.
    for d, comps in compartidos_por_dir.items():
        for clave in facturas_por_dir.get(d, set()):
            grupos[clave].extend(comps)

    salida = []
    for clave, archivos in grupos.items():
        carpeta = carpeta_de.get(clave, origen)
        # Nombre crudo de factura: el token tal como aparece en un archivo.
        fac_raw = clave
        for p in archivos:
            m = rx.search(p.name)
            if m:
                fac_raw = m.group(0)
                break
        ent = manifiesto.get(clave) or _entidad_desde_ruta(carpeta, origen, cfg)
        salida.append((fac_raw, sorted(set(archivos)), carpeta, ent))
    return salida


def descubrir_auto(
    origen: Path, manifiesto: dict[str, str], cfg: ConfigRadicacion, patron: str
) -> list[tuple[str, list[Path], Path, str | None]]:
    """Layout auto (def.): ancla en carpetas cuyo nombre ES una factura
    (HUS520769) y les asigna TODOS los archivos que cuelgan debajo,
    recursivamente — así recoge subcarpetas como RIPS/ y los documentos DIAN
    (fv…/ad…/ar…/.zip) que viven en la carpeta de la factura. Lo que no cae bajo
    ninguna carpeta-factura se agrupa por el token _<factura>_ del nombre
    (estilo lote). Fusiona por número de factura, así la misma factura repartida
    en árboles distintos queda UNA sola. Es el más robusto: cubre el share de FE
    (FACTURAS_SALUD\\HUS…\\), el de ESCANEO y los lotes sueltos."""
    rx = re.compile(patron, re.IGNORECASE)
    # Un solo recorrido del árbol con os.walk (no hace stat por entrada → mucho
    # más rápido en shares de red con miles de facturas que rglob + is_dir).
    anclas: set[Path] = set()
    archivos: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(origen):
        d = Path(dirpath)
        if d != origen and _RE_FACTURA_DESNUDA.match(d.name):
            anclas.add(d)
        archivos.extend(d / fn for fn in filenames)
    archivos.sort()

    grupos: dict[str, list[Path]] = defaultdict(list)
    carpeta_de: dict[str, Path] = {}
    fac_raw_de: dict[str, str] = {}
    sueltos: list[Path] = []

    for p in archivos:
        ancla: Path | None = None
        for parent in p.parents:
            if parent in anclas:
                ancla = parent
                break
            if parent == origen:
                break
        if ancla is not None:
            clave = normalizar_factura(ancla.name)
            grupos[clave].append(p)
            carpeta_de.setdefault(clave, ancla)
            fac_raw_de.setdefault(clave, ancla.name)
        else:
            sueltos.append(p)

    # Lo no anclado: agrupar por el token del nombre y repartir los compartidos
    # (sin token) a las facturas de su misma carpeta — igual que el layout lote.
    compartidos_por_dir: dict[Path, list[Path]] = defaultdict(list)
    facturas_por_dir: dict[Path, set[str]] = defaultdict(set)
    for p in sueltos:
        m = rx.search(p.name)
        if m:
            clave = normalizar_factura(m.group(0))
            grupos[clave].append(p)
            carpeta_de.setdefault(clave, p.parent)
            fac_raw_de.setdefault(clave, m.group(0))
            facturas_por_dir[p.parent].add(clave)
        else:
            compartidos_por_dir[p.parent].append(p)
    for d, comps in compartidos_por_dir.items():
        for clave in facturas_por_dir.get(d, set()):
            grupos[clave].extend(comps)

    salida = []
    for clave, archivos in grupos.items():
        carpeta = carpeta_de.get(clave, origen)
        ent = manifiesto.get(clave) or _entidad_desde_ruta(carpeta, origen, cfg)
        salida.append((fac_raw_de.get(clave, clave), sorted(set(archivos)), carpeta, ent))
    return salida


# ─── Manifiesto factura → entidad ────────────────────────────────────────────


def cargar_manifiesto(ruta: Path) -> dict[str, str]:
    """CSV/XLSX con columnas de factura y entidad. Devuelve {factura_norm:
    entidad}. Reconoce encabezados flexibles (FACTURA, EPS, ENTIDAD, …)."""
    alias_fac = {"FACTURA", "FACTURA HUS", "NUMERO FACTURA", "NRO FACTURA", "NO FACTURA"}
    alias_ent = {"ENTIDAD", "EPS", "PAGADOR", "TERCERO", "ASEGURADORA", "RESPONSABLE"}
    filas = _leer_tabla(ruta)
    if not filas:
        return {}
    headers = [_norm(h) for h in filas[0]]
    i_fac = next((i for i, h in enumerate(headers) if h in alias_fac), None)
    i_ent = next((i for i, h in enumerate(headers) if h in alias_ent), None)
    if i_fac is None or i_ent is None:
        raise ValueError(
            f"--manifiesto: no encontré columnas de factura y entidad en {ruta.name} "
            f"(encabezados: {filas[0]})"
        )
    mapa: dict[str, str] = {}
    for fila in filas[1:]:
        if len(fila) <= max(i_fac, i_ent):
            continue
        fac = normalizar_factura(str(fila[i_fac] or ""))
        ent = str(fila[i_ent] or "").strip()
        if fac != "0" and ent:
            mapa[fac] = ent
    return mapa


def _leer_tabla(ruta: Path) -> list[list]:
    if ruta.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError as e:
            raise SystemExit(
                "ERROR: para leer un manifiesto .xlsx falta openpyxl (py -m pip install openpyxl)."
            ) from e
        wb = load_workbook(filename=str(ruta), data_only=True, read_only=True)
        ws = wb[wb.sheetnames[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    with ruta.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


# ─── Armado del paquete ──────────────────────────────────────────────────────


def _nombre_unico(nombre: str, usados: set[str]) -> str:
    """Evita pisar archivos cuando dos soportes mapean al mismo nombre destino
    (p.ej. fv…xml y ad…xml de un mismo paquete DIAN): agrega _2, _3, …"""
    if nombre not in usados:
        return nombre
    raiz, punto, ext = nombre.rpartition(".")
    base = raiz if punto else nombre
    sufijo = ("." + ext) if punto else ""
    i = 2
    while f"{base}_{i}{sufijo}" in usados:
        i += 1
    return f"{base}_{i}{sufijo}"


def nombre_soporte(archivo: Path, factura: str, nit_prestador: str, nomenclatura: str) -> str:
    """Nombre destino del soporte según la nomenclatura de la entidad.
    ADRES: <TOKEN>_<NIT>_<factura>.<ext>.  DISPENSARIO_HUS_CORTO: igual pero
    con la factura en formato corto (HUS487523). Archivos ya bien nombrados o
    sin clasificar se dejan con su nombre original."""
    cod, _desc, reconocido = clasificar_soporte(archivo.name)
    ext = archivo.suffix.lower().lstrip(".") or "dat"
    fac = factura_corta(factura) if nomenclatura == "DISPENSARIO_HUS_CORTO" else factura
    if not reconocido:
        return sanitizar(archivo.name)
    return sanitizar(f"{cod}_{nit_prestador}_{fac}.{ext}")


def armar_paquete(
    res: ResultadoFactura,
    archivos: list[Path],
    perfil: PerfilEntidad | None,
    destino: Path,
    fecha: str,
    consecutivo: int,
    mover: bool,
    hacer_zip: bool,
    forzar: bool,
    dry_run: bool,
    nit_prestador: str,
) -> bool:
    """Construye <destino>/<ENTIDAD>/<factura>/ con los soportes renombrados.
    Solo arma estados LISTA o REVISAR_TIPIFICACION (este último requiere
    --forzar). Registra acciones y la ruta del paquete en `res`. Devuelve True
    si se generó (o se generaría) un ZIP, para avanzar el consecutivo."""
    if not _debe_armar(res.estado, forzar):
        res.acciones.append(f"NO_ARMADO ({res.estado})")
        return False

    nomen = perfil.nomenclatura if perfil else "ADRES"
    formato = perfil.formato_paquete if perfil else "CARPETA"
    ent_id = res.entidad_id or "SIN_PERFIL"
    fac = factura_corta(res.factura) if nomen == "DISPENSARIO_HUS_CORTO" else res.factura
    dir_factura = destino / sanitizar(ent_id) / sanitizar(fac)
    res.ruta_paquete = str(dir_factura)

    if not dry_run:
        dir_factura.mkdir(parents=True, exist_ok=True)

    copiados = 0
    usados: set[str] = set()
    for p in archivos:
        nuevo = _nombre_unico(nombre_soporte(p, res.factura, nit_prestador, nomen), usados)
        usados.add(nuevo)
        destino_final = dir_factura / nuevo
        if dry_run:
            copiados += 1
            continue
        try:
            if mover:
                shutil.move(str(p), str(destino_final))
            else:
                shutil.copy2(str(p), str(destino_final))
            copiados += 1
        except OSError as e:
            res.acciones.append(f"ERROR_COPIA {p.name}: {e}")
    res.acciones.append(f"{'movería' if dry_run else 'copió'} {copiados} soporte(s)")

    if not dry_run:
        _escribir_manifiesto_factura(res, dir_factura, perfil, nit_prestador)

    if hacer_zip and formato.startswith("ZIP"):
        zip_nombre = f"{nit_prestador}_{fecha}_{consecutivo:04d}.zip"
        zip_ruta = destino / sanitizar(ent_id) / zip_nombre
        res.acciones.append(f"ZIP → {zip_nombre}")
        if not dry_run:
            _comprimir(dir_factura, zip_ruta)
            res.ruta_paquete = str(zip_ruta)
        return True
    return False


def _escribir_manifiesto_factura(
    res: ResultadoFactura, dir_factura: Path, perfil: PerfilEntidad | None, nit: str
) -> None:
    manifiesto = {
        "factura": res.factura,
        "entidad": res.entidad_nombre,
        "entidad_id": res.entidad_id,
        "canal": perfil.canal if perfil else "",
        "portal": perfil.portal if perfil else "",
        "nit_prestador": nit,
        "valor_total": res.valor_total,
        "usuarios": res.num_usuarios,
        "servicios": res.servicios,
        "soportes_presentes": res.soportes_presentes,
        "estado": res.estado,
        "generado": datetime.now().isoformat(timespec="seconds"),
    }
    (dir_factura / "_manifiesto_radicacion.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _comprimir(carpeta: Path, zip_ruta: Path) -> None:
    """Comprime los soportes de la carpeta. Excluye los archivos de control
    internos (prefijo '_', como _manifiesto_radicacion.json) que no deben
    viajar a la entidad."""
    zip_ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(carpeta.iterdir()):
            if p.is_file() and not p.name.startswith("_"):
                zf.write(p, arcname=p.name)


# ─── Reportes ────────────────────────────────────────────────────────────────

CAMPOS_REPORTE = [
    "factura",
    "entidad",
    "entidad_id",
    "canal",
    "valor_total",
    "usuarios",
    "servicios",
    "n_archivos",
    "soportes_presentes",
    "soportes_faltantes",
    "soportes_esperados_faltantes",
    "archivos_sin_clasificar",
    "estado",
    "detalle",
    "ruta_paquete",
    "acciones",
    "carpeta",
]


def _fila_reporte(res: ResultadoFactura) -> dict:
    serv = ", ".join(f"{k}:{v}" for k, v in res.servicios.items())
    return {
        "factura": res.factura,
        "entidad": res.entidad_nombre,
        "entidad_id": res.entidad_id,
        "canal": res.canal,
        "valor_total": f"{res.valor_total:.0f}",
        "usuarios": res.num_usuarios,
        "servicios": serv,
        "n_archivos": res.n_archivos,
        "soportes_presentes": " ".join(res.soportes_presentes),
        "soportes_faltantes": " ".join(res.soportes_faltantes),
        "soportes_esperados_faltantes": " ".join(res.soportes_esperados_faltantes),
        "archivos_sin_clasificar": "; ".join(res.archivos_sin_clasificar),
        "estado": res.estado,
        "detalle": " ".join(res.detalle),
        "ruta_paquete": res.ruta_paquete,
        "acciones": "; ".join(res.acciones),
        "carpeta": res.carpeta,
    }


def escribir_reporte_csv(resultados: list[ResultadoFactura], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CAMPOS_REPORTE)
        writer.writeheader()
        for r in resultados:
            writer.writerow(_fila_reporte(r))
    logger.info(f"Reporte CSV: {ruta}")


def escribir_reporte_xlsx(resultados: list[ResultadoFactura], ruta: Path) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        logger.warning("openpyxl no está instalado — omito el XLSX (el CSV sí se generó).")
        return

    colores = {
        "LISTA": "C6EFCE",
        "REVISAR_TIPIFICACION": "FFEB9C",
        "FACTURA_INCONSISTENTE": "FFEB9C",
        "FALTAN_SOPORTES": "FFC7CE",
        "SIN_CUV": "FFC7CE",
        "SIN_FEV": "FFC7CE",
        "SIN_RIPS": "FFC7CE",
        "ENTIDAD_NO_RESUELTA": "F4B084",
    }
    wb = Workbook()
    ws = wb.active
    ws.title = "RADICACION"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for c, h in enumerate(CAMPOS_REPORTE, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.fill = header_fill
        cell.font = header_font
    anchos = {
        "detalle": 60,
        "soportes_presentes": 22,
        "carpeta": 40,
        "acciones": 30,
        "servicios": 24,
    }
    for c, h in enumerate(CAMPOS_REPORTE, 1):
        ws.column_dimensions[get_column_letter(c)].width = anchos.get(h, 16)

    i_estado = CAMPOS_REPORTE.index("estado")
    for r, res in enumerate(resultados, start=2):
        fila = _fila_reporte(res)
        for c, h in enumerate(CAMPOS_REPORTE, 1):
            cell = ws.cell(row=r, column=c, value=fila[h])
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        color = colores.get(res.estado)
        if color:
            ws.cell(row=r, column=i_estado + 1).fill = PatternFill("solid", fgColor=color)
    ws.freeze_panes = "A2"

    # Hoja resumen por entidad.
    ws2 = wb.create_sheet("RESUMEN")
    ws2.append(["Entidad", "Facturas", "Listas", "Con problemas", "Valor total"])
    for c in range(1, 6):
        ws2.cell(row=1, column=c).fill = header_fill
        ws2.cell(row=1, column=c).font = header_font
    for ent, datos in _resumen_por_entidad(resultados).items():
        ws2.append(
            [ent, datos["total"], datos["listas"], datos["problemas"], f"{datos['valor']:.0f}"]
        )
    for col, ancho in (("A", 38), ("B", 10), ("C", 8), ("D", 14), ("E", 16)):
        ws2.column_dimensions[col].width = ancho

    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(ruta))
    logger.info(f"Reporte XLSX: {ruta}")


def _resumen_por_entidad(resultados: list[ResultadoFactura]) -> dict[str, dict]:
    agg: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "listas": 0, "problemas": 0, "valor": 0.0}
    )
    for r in resultados:
        d = agg[r.entidad_nombre]
        d["total"] += 1
        d["valor"] += r.valor_total
        if r.estado in ESTADOS_OK:
            d["listas"] += 1
        else:
            d["problemas"] += 1
    return dict(sorted(agg.items(), key=lambda kv: -kv[1]["total"]))


def imprimir_resumen(resultados: list[ResultadoFactura]) -> None:
    por_estado = Counter(r.estado for r in resultados)
    total = len(resultados)
    valor_total = sum(r.valor_total for r in resultados)
    logger.info("=" * 64)
    logger.info("RESUMEN DE RADICACIÓN")
    logger.info(f"  Facturas procesadas: {total:,}")
    logger.info(f"  Valor total facturado: $ {valor_total:,.0f}")
    logger.info("  Por estado:")
    orden = [*ESTADOS_OK, *ESTADOS_PROBLEMA]
    for estado in orden + [e for e in por_estado if e not in orden]:
        n = por_estado.get(estado, 0)
        if n:
            pct = 100 * n / max(1, total)
            logger.info(f"    {estado:<22} {n:>4} ({pct:.0f}%)")
    logger.info("  Por entidad:")
    for ent, d in _resumen_por_entidad(resultados).items():
        logger.info(
            f"    {ent[:34]:<34} {d['total']:>3} facturas | "
            f"{d['listas']:>3} listas | $ {d['valor']:,.0f}"
        )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _coincide_entidad(filtro_norm: str, res: ResultadoFactura) -> bool:
    return filtro_norm in _norm(res.entidad_nombre) or filtro_norm in _norm(res.entidad_hint)


def setup_logging(log_file: Path | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--origen", type=Path, required=True, help="Carpeta raíz del lote de facturación."
    )
    p.add_argument(
        "--destino", type=Path, default=None, help="Carpeta donde armar los paquetes (con --armar)."
    )
    p.add_argument(
        "--perfiles",
        type=Path,
        default=None,
        help="JSON de perfiles (def.: data/perfiles_radicacion.json).",
    )
    p.add_argument(
        "--manifiesto",
        type=Path,
        default=None,
        help="CSV/XLSX que mapea factura → entidad (cuando el lote no está por carpetas de EPS).",
    )
    p.add_argument(
        "--layout",
        choices=["auto", "carpeta-factura", "lote"],
        default="auto",
        help="auto (def.): ancla en carpetas HUS<factura> y agrupa lo demás por token "
        "(cubre los shares anidados). carpeta-factura: una carpeta por factura. "
        "lote: muchos archivos por carpeta.",
    )
    p.add_argument(
        "--entidad", type=str, default=None, help="Filtrar solo esta entidad (substring)."
    )
    p.add_argument(
        "--reporte",
        type=Path,
        default=Path("radicacion_reporte.csv"),
        help="CSV de salida con el estado de cada factura.",
    )
    p.add_argument("--xlsx", type=Path, default=None, help="XLSX con formato y hoja de resumen.")
    p.add_argument(
        "--armar", action="store_true", help="Construir los paquetes (carpetas + renombrado)."
    )
    p.add_argument(
        "--zip", action="store_true", dest="hacer_zip", help="Comprimir cada paquete a ZIP."
    )
    p.add_argument(
        "--mover", action="store_true", help="Mover archivos en vez de copiar (con --armar)."
    )
    p.add_argument(
        "--forzar",
        action="store_true",
        help="Armar también las facturas en estado REVISAR_TIPIFICACION.",
    )
    p.add_argument("--fecha", type=str, default=None, help="Fecha AAAAMMDD para el nombre del ZIP.")
    p.add_argument(
        "--consecutivo-inicial",
        type=int,
        default=1,
        dest="consecutivo",
        help="Consecutivo inicial para los ZIP (def. 1).",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="No toca archivos; solo reporta qué haría."
    )
    p.add_argument("--log", type=Path, default=None, help="Archivo de log opcional.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log)

    if not args.origen.is_dir():
        logger.error(f"--origen no existe o no es carpeta: {args.origen}")
        return 1
    if args.armar and args.destino is None:
        logger.error("--armar requiere --destino.")
        return 1
    if not _ADRES_OK:
        logger.warning(
            "No pude importar tools/adres/ (rips_lectura, factura_lectura): los valores y "
            "servicios del RIPS saldrán limitados. Verificá que el script esté en tools/."
        )

    cfg = cargar_perfiles(args.perfiles)
    cfg.prestador_nit = cfg.prestador_nit or PRESTADOR_NIT_DEFAULT

    manifiesto: dict[str, str] = {}
    if args.manifiesto is not None:
        if not args.manifiesto.is_file():
            logger.error(f"--manifiesto no existe: {args.manifiesto}")
            return 1
        manifiesto = cargar_manifiesto(args.manifiesto)
        logger.info(f"Manifiesto: {len(manifiesto)} facturas mapeadas a entidad.")

    if args.layout == "lote":
        items = descubrir_lote(args.origen, manifiesto, cfg, cfg.patron_factura)
    elif args.layout == "carpeta-factura":
        items = descubrir_carpeta_factura(args.origen, manifiesto, cfg)
    else:
        items = descubrir_auto(args.origen, manifiesto, cfg, cfg.patron_factura)

    if not items:
        logger.error(
            f"No encontré facturas en {args.origen} (layout={args.layout}). "
            "¿El lote tiene subcarpetas con soportes? Probá el otro --layout."
        )
        return 1

    filtro_ent = _norm(args.entidad or "")
    fecha = args.fecha or datetime.now().strftime("%Y%m%d")
    logger.info(
        f"Lote: {len(items)} factura(s) en {args.origen} (layout={args.layout})"
        + (f" | filtro entidad: '{args.entidad}'" if args.entidad else "")
        + ("  [MODO AUDITORÍA — no se arma nada]" if not args.armar else "")
        + ("  (DRY-RUN)" if args.dry_run else "")
    )

    resultados: list[ResultadoFactura] = []
    consecutivo = args.consecutivo
    for i, (fac_hint, archivos, carpeta, ent_hint) in enumerate(items, 1):
        res = procesar_factura(fac_hint, archivos, carpeta, ent_hint, cfg)
        if filtro_ent and not _coincide_entidad(filtro_ent, res):
            continue
        logger.info(f"[{i}/{len(items)}] {res.factura} → {res.entidad_nombre}  [{res.estado}]")
        if args.armar:
            perfil = resolver_entidad(ent_hint, cfg)
            uso_zip = armar_paquete(
                res,
                archivos,
                perfil,
                args.destino,
                fecha,
                consecutivo,
                mover=args.mover,
                hacer_zip=args.hacer_zip,
                forzar=args.forzar,
                dry_run=args.dry_run,
                nit_prestador=cfg.prestador_nit,
            )
            if uso_zip:
                consecutivo += 1
        resultados.append(res)

    if not resultados:
        logger.warning("Ninguna factura pasó el filtro de entidad.")
        return 0

    escribir_reporte_csv(resultados, args.reporte)
    if args.xlsx is not None:
        escribir_reporte_xlsx(resultados, args.xlsx)
    imprimir_resumen(resultados)

    listas = sum(1 for r in resultados if r.estado in ESTADOS_OK)
    logger.info(
        f"\n{listas}/{len(resultados)} factura(s) LISTAS para radicar. "
        "Revisá el reporte para las demás."
    )
    problemas = len(resultados) - listas
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
