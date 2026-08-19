"""El informe de uso del Constructor de Agentes lee las tablas que existen.

19-08-2026. Yesid preguntó qué hace el panel de Agentes y **cuánto se ha usado
desde que está**. Lo segundo no se podía responder mirando la pantalla: la
ficha del agente guarda quién la creó y cuándo, pero no cuántas veces se ha
corrido ni cuándo fue la última.

La primera versión de este informe preguntaba por una tabla `auditoria` que no
existe —se llama `audit_log`— y por una columna `fecha` que se llama
`timestamp`. Reventó en la máquina de Yesid con:

    sqlite3.OperationalError: no such table: auditoria

De ahí esta prueba: los nombres de tabla y de columna del informe se comparan
contra los modelos de verdad, no contra lo que uno se acuerde.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
GUION = RAIZ / "tools" / "uso_agentes.py"


def _base(tmp_path: Path, con_datos: bool) -> Path:
    """Una base con el MISMO esquema que usa el motor."""
    from app.models.db import AgenteRecord, AuditLogRecord

    ruta = tmp_path / "t.db"
    con = sqlite3.connect(ruta)
    cols_ag = ", ".join(c.name for c in AgenteRecord.__table__.columns)
    cols_au = ", ".join(c.name for c in AuditLogRecord.__table__.columns)
    con.execute(f"CREATE TABLE {AgenteRecord.__tablename__} ({cols_ag})")
    con.execute(f"CREATE TABLE {AuditLogRecord.__tablename__} ({cols_au})")
    if con_datos:
        con.execute(
            "INSERT INTO agentes (id, nombre, creado_por, creado_en, activo) "
            "VALUES (1, 'Vigilante de vencimientos', 'yesid@hus', '2026-08-19', 1)"
        )
        for accion in ("AGENTE_CREADO", "AGENTE_CORRIDO", "AGENTE_CORRIDO"):
            con.execute(
                "INSERT INTO audit_log (accion, usuario_email, timestamp) VALUES (?,?,?)",
                (accion, "yesid@hus", "2026-08-19 11:00"),
            )
    con.commit()
    con.close()
    return ruta


def _correr(ruta: Path) -> str:
    r = subprocess.run(
        [sys.executable, str(GUION), str(ruta)],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, f"el informe reventó:\n{r.stderr[-800:]}"
    assert "Traceback" not in r.stderr, r.stderr[-800:]
    return r.stdout


class TestPreguntaPorLasTablasQueExisten:
    def test_no_revienta_con_el_esquema_real(self, tmp_path):
        _correr(_base(tmp_path, con_datos=False))

    def test_usa_audit_log_y_no_auditoria(self):
        """El error concreto que le salió a Yesid."""
        fuente = GUION.read_text(encoding="utf-8")
        assert "FROM auditoria" not in fuente
        assert "audit_log" in fuente

    def test_los_nombres_coinciden_con_los_modelos(self):
        from app.models.db import AgenteRecord, AuditLogRecord

        fuente = GUION.read_text(encoding="utf-8")
        assert AgenteRecord.__tablename__ in fuente
        assert AuditLogRecord.__tablename__ in fuente
        # Las columnas que el informe consulta tienen que existir.
        cols = {c.name for c in AuditLogRecord.__table__.columns}
        assert "timestamp" in cols and "accion" in cols and "usuario_email" in cols
        assert "MIN(timestamp)" in fuente


class TestLoQueResponde:
    def test_con_uso_dice_cuantas_veces_y_quien(self, tmp_path):
        salida = _correr(_base(tmp_path, con_datos=True))
        assert "Vigilante de vencimientos" in salida
        assert "AGENTE_CORRIDO" in salida
        assert "yesid@hus" in salida

    def test_sin_uso_lo_dice_en_castellano(self, tmp_path):
        salida = _correr(_base(tmp_path, con_datos=False))
        assert "Nadie ha creado un agente todavía" in salida
        assert "El panel no se ha usado nunca" in salida


class TestNoPuedeDanarNada:
    def test_abre_la_base_en_modo_lectura(self):
        """Un informe que solo mira no puede tener permiso de escribir."""
        assert "mode=ro" in GUION.read_text(encoding="utf-8")

    def test_no_escribe_en_la_base(self, tmp_path):
        ruta = _base(tmp_path, con_datos=True)
        antes = ruta.read_bytes()
        _correr(ruta)
        assert ruta.read_bytes() == antes
