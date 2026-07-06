"""Tests del backup automático de SQLite + pragmas (migración a volumen Fly).

Importante: NO se recarga app.database (eso rompería la identidad de
Base.metadata y contaminaría el resto de la suite). En su lugar:
  • los PRAGMAs se prueban con la función pública registrar_pragmas_sqlite
    sobre un engine aislado;
  • el backup se prueba monkeypatcheando _ruta_sqlite a una DB temporal.
"""

from __future__ import annotations

import glob
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text


# ── PRAGMAs sobre engine aislado ─────────────────────────────────────
def test_registrar_pragmas_aplica_wal(tmp_path):
    from app.database import registrar_pragmas_sqlite

    ruta = tmp_path / "x.db"
    eng = create_engine(f"sqlite:///{ruta}", connect_args={"check_same_thread": False})
    registrar_pragmas_sqlite(eng)
    with eng.connect() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert c.execute(text("PRAGMA busy_timeout")).scalar() == 30000
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
    eng.dispose()


# ── Backup ───────────────────────────────────────────────────────────
@pytest.fixture
def db_temporal(tmp_path, monkeypatch):
    """Crea una DB SQLite temporal con una tabla y apunta _ruta_sqlite a ella."""
    ruta = tmp_path / "prod.db"
    conn = sqlite3.connect(ruta)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('hola')")
    conn.commit()
    conn.close()
    import app.services.backup_sqlite as bk

    monkeypatch.setattr(bk, "_ruta_sqlite", lambda: str(ruta))
    return bk, ruta


def test_crear_backup_genera_archivo(db_temporal):
    bk, ruta = db_temporal
    r = bk.crear_backup(retener=5)
    assert "ruta" in r, f"backup no se creó: {r}"
    assert os.path.exists(r["ruta"])
    dir_bk = os.path.join(os.path.dirname(str(ruta)), "backups")
    assert len(glob.glob(os.path.join(dir_bk, "*.db"))) == 1
    # El backup es una copia consistente y legible
    c = sqlite3.connect(r["ruta"])
    assert c.execute("SELECT v FROM t").fetchone()[0] == "hola"
    c.close()


def test_rotacion_conserva_solo_n(db_temporal):
    import time

    bk, ruta = db_temporal
    for _ in range(4):
        bk.crear_backup(retener=2)
        time.sleep(1.05)  # timestamps distintos (resolución de 1s)
    dir_bk = os.path.join(os.path.dirname(str(ruta)), "backups")
    assert len(glob.glob(os.path.join(dir_bk, "*.db"))) == 2


def test_backup_noop_si_no_sqlite(monkeypatch):
    """Si la DB no es SQLite de archivo, el backup es no-op (no revienta)."""
    import app.services.backup_sqlite as bk

    monkeypatch.setattr(bk, "_ruta_sqlite", lambda: None)
    r = bk.crear_backup()
    assert "skip" in r
