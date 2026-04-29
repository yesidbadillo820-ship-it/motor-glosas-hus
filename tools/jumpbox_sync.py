"""Jump-box agent: sincroniza el share Y:\\ al motor de glosas vía HTTP.

USO TÍPICO (en una PC Windows que ya tiene Y:\\ mapeado):

    pip install requests
    set MOTOR_URL=https://motor.hus.gov.co
    set MOTOR_TOKEN=eyJhbGciOi...
    set SHARE_ROOT=Y:\\
    python jumpbox_sync.py --once

Para correrlo en bucle (recomendado en producción):

    python jumpbox_sync.py --loop --interval-min 30

QUÉ HACE
    1. Pide a `/soportes-auto/manifest` el inventario de archivos que
       el motor ya tiene.
    2. Recorre `Y:\\` filtrando por extensión (.pdf, .json, .xml, .txt, .csv).
    3. Para cada archivo, compara tamaño contra el manifest. Si difiere
       o no está, lo encola para subir.
    4. Sube en lotes de 20 archivos / 100 MB vía POST /soportes-auto/upload-bulk.
    5. Cuando termina la pasada completa, llama a POST /soportes-auto/reindex.
    6. Guarda estado en `%APPDATA%\\motor-glosas\\jumpbox_state.json` para
       diagnóstico (último run, errores, conteos).

CAVEATS
    - La PC tiene que estar prendida. Recomendado: desactivar suspensión.
    - Si rotás tu password de Windows, Y:\\ se desautentica. El script
       se cae con error de I/O hasta que vuelvas a abrir el share.
    - Es Plan B. Reemplazalo por mount CIFS apenas Infra te dé la
       cuenta de servicio.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

try:
    import requests
except ImportError:
    sys.stderr.write("ERROR: pip install requests\n")
    sys.exit(2)

# ─── Configuración ─────────────────────────────────────────────────
MOTOR_URL = os.getenv("MOTOR_URL", "").rstrip("/")
MOTOR_TOKEN = os.getenv("MOTOR_TOKEN", "")
SHARE_ROOT = Path(os.getenv("SHARE_ROOT", r"Y:\\"))

# Filtros: solo subimos archivos relevantes para soportes
EXT_PERMITIDAS = {".pdf", ".json", ".xml", ".txt", ".csv"}
# Tope por archivo individual (acorde con el endpoint del motor)
MAX_BYTES_POR_ARCHIVO = 50 * 1024 * 1024
# Tope por batch HTTP — debe ser <= límite del motor (200 MB)
MAX_BYTES_POR_BATCH = 100 * 1024 * 1024
MAX_ARCHIVOS_POR_BATCH = 20
# Reintentos por batch en caso de error transitorio
REINTENTOS = 3
PAUSA_REINTENTO_S = 10

# Estado persistente — diagnóstico, no caché
APPDATA = Path(os.getenv("APPDATA") or Path.home() / ".motor-glosas")
STATE_DIR = APPDATA / "motor-glosas"
STATE_FILE = STATE_DIR / "jumpbox_state.json"
LOG_FILE = STATE_DIR / "jumpbox.log"

logger = logging.getLogger("jumpbox")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


# ─── HTTP helpers ──────────────────────────────────────────────────
def _headers() -> dict:
    return {"Authorization": f"Bearer {MOTOR_TOKEN}"}


def fetch_manifest() -> dict:
    """Pide el inventario actual del motor."""
    url = f"{MOTOR_URL}/soportes-auto/manifest"
    r = requests.get(url, headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()


def post_batch(archivos_batch: list[tuple[Path, str]]) -> dict:
    """Sube un batch via multipart. Devuelve el resumen del motor."""
    url = f"{MOTOR_URL}/soportes-auto/upload-bulk"
    files = []
    rel_paths = []
    file_handles: list = []
    try:
        for ruta_local, rel in archivos_batch:
            fh = open(ruta_local, "rb")
            file_handles.append(fh)
            files.append(("files", (ruta_local.name, fh, "application/octet-stream")))
            rel_paths.append(("rel_paths", rel))
        ultimo_error: Optional[Exception] = None
        for intento in range(1, REINTENTOS + 1):
            try:
                # Reposicionar handles si fue reintento (después de un envío parcial)
                for fh in file_handles:
                    fh.seek(0)
                r = requests.post(
                    url,
                    headers=_headers(),
                    files=files + rel_paths,
                    timeout=300,
                )
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                ultimo_error = e
                logger.warning(
                    f"Batch falló intento {intento}/{REINTENTOS}: {e}"
                )
                if intento < REINTENTOS:
                    time.sleep(PAUSA_REINTENTO_S * intento)
        raise RuntimeError(f"Batch falló tras {REINTENTOS} reintentos: {ultimo_error}")
    finally:
        for fh in file_handles:
            try:
                fh.close()
            except Exception:
                pass


def post_reindex() -> dict:
    """Dispara rebuild del índice cuando termina la pasada."""
    url = f"{MOTOR_URL}/soportes-auto/reindex"
    r = requests.post(url, headers=_headers(), timeout=600)
    r.raise_for_status()
    return r.json()


# ─── Walker / filtros ──────────────────────────────────────────────
def iter_archivos(raiz: Path) -> Iterator[Path]:
    """Recorre el share, filtra por extensión y tamaño."""
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in EXT_PERMITIDAS:
            continue
        try:
            if p.stat().st_size > MAX_BYTES_POR_ARCHIVO:
                logger.warning(f"Saltado por tamaño: {p}")
                continue
        except OSError as e:
            logger.warning(f"Stat falló en {p}: {e}")
            continue
        yield p


def _to_rel(local: Path, raiz: Path) -> str:
    """Convierte ruta local a rel-path normalizado (slashes POSIX)."""
    return str(local.relative_to(raiz)).replace("\\", "/")


# ─── State persistente ─────────────────────────────────────────────
def cargar_estado() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def guardar_estado(estado: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(estado, indent=2, default=str), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"No pude guardar estado: {e}")


# ─── Sync principal ────────────────────────────────────────────────
def calcular_pendientes(raiz: Path, manifest: dict) -> list[tuple[Path, str]]:
    """Compara local vs manifest del motor. Devuelve lista de a subir."""
    remoto = manifest.get("archivos", {})
    pendientes: list[tuple[Path, str]] = []
    total_local = 0
    for archivo in iter_archivos(raiz):
        total_local += 1
        rel = _to_rel(archivo, raiz)
        try:
            tam_local = archivo.stat().st_size
        except OSError:
            continue
        info_remota = remoto.get(rel)
        if info_remota and info_remota.get("size") == tam_local:
            # Mismo tamaño = asumimos igual. No comparamos hash por costo.
            continue
        pendientes.append((archivo, rel))
    logger.info(
        f"Local: {total_local} archivos | Remoto: {len(remoto)} | A subir: {len(pendientes)}"
    )
    return pendientes


def subir_pendientes(pendientes: list[tuple[Path, str]]) -> dict:
    """Sube en batches de tamaño limitado. Devuelve resumen agregado."""
    agregado = {
        "guardados": 0,
        "ignorados_iguales": 0,
        "rechazados": [],
        "bytes_escritos": 0,
        "batches": 0,
        "fallidos": 0,
    }
    batch: list[tuple[Path, str]] = []
    bytes_batch = 0
    for ruta, rel in pendientes:
        try:
            tam = ruta.stat().st_size
        except OSError:
            continue
        # Si agregar este archivo excede el batch, primero envío el actual
        if batch and (
            len(batch) >= MAX_ARCHIVOS_POR_BATCH or bytes_batch + tam > MAX_BYTES_POR_BATCH
        ):
            try:
                resp = post_batch(batch)
                _acumular(agregado, resp)
            except Exception as e:
                logger.error(f"Batch perdido: {e}")
                agregado["fallidos"] += len(batch)
            batch = []
            bytes_batch = 0
        batch.append((ruta, rel))
        bytes_batch += tam
    if batch:
        try:
            resp = post_batch(batch)
            _acumular(agregado, resp)
        except Exception as e:
            logger.error(f"Batch final perdido: {e}")
            agregado["fallidos"] += len(batch)
    return agregado


def _acumular(agregado: dict, resp: dict) -> None:
    agregado["batches"] += 1
    agregado["guardados"] += int(resp.get("guardados", 0))
    agregado["ignorados_iguales"] += int(resp.get("ignorados_iguales", 0))
    agregado["bytes_escritos"] += int(resp.get("bytes_escritos", 0))
    if resp.get("rechazados"):
        agregado["rechazados"].extend(resp["rechazados"])


def run_once() -> dict:
    """Una pasada completa: manifest → diff → upload → reindex."""
    inicio = time.time()
    if not MOTOR_URL or not MOTOR_TOKEN:
        raise RuntimeError("Faltan MOTOR_URL o MOTOR_TOKEN")
    if not SHARE_ROOT.exists():
        raise RuntimeError(f"SHARE_ROOT no existe: {SHARE_ROOT}")

    logger.info(f"Iniciando sync. SHARE_ROOT={SHARE_ROOT} → {MOTOR_URL}")
    manifest = fetch_manifest()
    pendientes = calcular_pendientes(SHARE_ROOT, manifest)
    if not pendientes:
        logger.info("Nada que subir — todo está sincronizado.")
        return {
            "duracion_s": round(time.time() - inicio, 1),
            "subidos": 0,
            "reindexado": False,
        }

    resumen = subir_pendientes(pendientes)
    logger.info(f"Sync hecho: {resumen}")

    # Reindex final solo si efectivamente subimos algo
    reindex_resp = None
    if resumen["guardados"] > 0:
        try:
            reindex_resp = post_reindex()
            logger.info(
                f"Reindex OK: {reindex_resp.get('archivos_indexados')} archivos / "
                f"{reindex_resp.get('facturas_indexadas')} facturas"
            )
        except Exception as e:
            logger.error(f"Reindex falló (subida OK igual): {e}")

    estado = cargar_estado()
    estado["ultimo_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    estado["ultimo_resumen"] = resumen
    estado["ultimo_reindex"] = reindex_resp
    guardar_estado(estado)
    return {
        "duracion_s": round(time.time() - inicio, 1),
        "subidos": resumen["guardados"],
        "fallidos": resumen["fallidos"],
        "reindexado": reindex_resp is not None,
    }


def run_loop(interval_min: int) -> None:
    while True:
        try:
            r = run_once()
            logger.info(f"Pasada terminada: {r}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Pasada falló: {e}")
        logger.info(f"Durmiendo {interval_min} min hasta próxima pasada")
        time.sleep(interval_min * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Una sola pasada y salir")
    parser.add_argument("--loop", action="store_true", help="Pasada cada --interval-min minutos")
    parser.add_argument("--interval-min", type=int, default=30, help="Intervalo entre pasadas en modo loop")
    args = parser.parse_args()

    setup_logging()

    if not args.once and not args.loop:
        parser.error("Especificá --once o --loop")
    if args.once:
        sys.exit(0 if run_once().get("fallidos", 0) == 0 else 1)
    else:
        run_loop(args.interval_min)


if __name__ == "__main__":
    main()
