"""Backup automático de la base SQLite al volumen persistente de Fly.

Contexto (17-jun-2026): tras migrar de Neon Postgres a SQLite en el disco
/data de Fly, la DB es un solo archivo. Un archivo es fácil de respaldar
pero también fácil de perder (corrupción, borrado accidental, error en una
migración manual). Este módulo copia la DB a /data/backups/ con timestamp
y rota los más viejos.

Usa la API oficial de backup de SQLite (`sqlite3.Connection.backup`), que
hace una copia consistente incluso con la DB en uso (no copia el archivo
"a lo bruto", que podría quedar a medias si hay una escritura en curso).

No-op si la DB no es SQLite (en Postgres el backup lo hace el proveedor).
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime

from app.core.logging_utils import logger


def _ruta_sqlite() -> str | None:
    """Devuelve la ruta del archivo SQLite, o None si la DB no es SQLite
    de archivo (Postgres o :memory:)."""
    try:
        from app.database import db_url
    except Exception:
        return None
    if not db_url.startswith("sqlite:///") or ":memory:" in db_url:
        return None
    return db_url.replace("sqlite:///", "", 1)


def crear_backup(retener: int = 14) -> dict:
    """Crea un backup consistente de la DB SQLite y rota los antiguos.

    Args:
        retener: cuántos backups conservar (default 14 = ~2 semanas si
            corre diario). Los más viejos se borran.

    Returns:
        dict con el resultado (ruta, tamaño, borrados) o {"skip": motivo}.
    """
    ruta = _ruta_sqlite()
    if not ruta:
        return {"skip": "no es SQLite de archivo"}
    if not os.path.exists(ruta):
        return {"skip": f"archivo no existe aún: {ruta}"}

    dir_backups = os.path.join(os.path.dirname(ruta) or ".", "backups")
    os.makedirs(dir_backups, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = os.path.join(dir_backups, f"motorglosas-{stamp}.db")

    t0 = time.time()
    origen = sqlite3.connect(ruta)
    try:
        dest = sqlite3.connect(destino)
        try:
            origen.backup(dest)  # copia consistente (API oficial)
        finally:
            dest.close()
    finally:
        origen.close()

    tam_mb = round(os.path.getsize(destino) / (1024 * 1024), 2)

    # Rotación: conservar los `retener` más recientes
    backups = sorted(
        (
            os.path.join(dir_backups, f)
            for f in os.listdir(dir_backups)
            if f.startswith("motorglosas-") and f.endswith(".db")
        ),
        reverse=True,
    )
    borrados = 0
    for viejo in backups[retener:]:
        try:
            os.remove(viejo)
            borrados += 1
        except OSError:
            pass

    dur = round(time.time() - t0, 2)
    logger.info(
        f"[BACKUP-SQLITE] OK: {destino} ({tam_mb} MB, {dur}s) · "
        f"conservados={min(len(backups), retener)} borrados={borrados}"
    )
    return {
        "ruta": destino,
        "tamano_mb": tam_mb,
        "duracion_s": dur,
        "conservados": min(len(backups), retener),
        "borrados": borrados,
    }
