"""Guarda el progreso en un archivo local, sin nube y sin cuentas.

Todo vive en un solo archivo SQLite (por defecto ``~/.icfes/progreso.db``).
Eso tiene tres ventajas para un estudiante: funciona sin internet, se puede
copiar a una memoria USB para cambiar de computador, y nadie más lo ve.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .dominio import Area, CausaError
from .progreso import Intento
from .repaso import Tarjeta
from .simulacro import ResultadoSimulacro

#: Dónde se guarda el progreso si no se dice otra cosa. La variable de entorno
#: ICFES_DATOS permite mover el archivo (por ejemplo, a una memoria USB).
RUTA_POR_DEFECTO: Path = Path(os.environ.get("ICFES_DATOS", Path.home() / ".icfes")) / "progreso.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intentos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha        TEXT NOT NULL,
    pregunta_id  TEXT NOT NULL,
    area         TEXT NOT NULL,
    competencia  TEXT NOT NULL,
    tema         TEXT NOT NULL,
    acerto       INTEGER NOT NULL,
    segundos     REAL,
    causa        TEXT
);
CREATE INDEX IF NOT EXISTS idx_intentos_fecha ON intentos(fecha);
CREATE INDEX IF NOT EXISTS idx_intentos_pregunta ON intentos(pregunta_id);
CREATE TABLE IF NOT EXISTS tarjetas (
    clave          TEXT PRIMARY KEY,
    repeticiones   INTEGER NOT NULL,
    facilidad      REAL NOT NULL,
    intervalo_dias INTEGER NOT NULL,
    proxima_fecha  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tarjetas_proxima ON tarjetas(proxima_fecha);
CREATE TABLE IF NOT EXISTS simulacros (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha            TEXT NOT NULL,
    tipo             TEXT NOT NULL,
    correctas        INTEGER NOT NULL,
    total            INTEGER NOT NULL,
    global_estimado  INTEGER,
    escala           REAL NOT NULL,
    segundos_usados  INTEGER,
    detalle          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_simulacros_fecha ON simulacros(fecha);
"""


@dataclass(frozen=True)
class Configuracion:
    """Los datos que el estudiante fija una sola vez."""

    nombre: str
    fecha_examen: date
    meta_global: int
    horas_semana: float
    dias_por_semana: int = 6


class Almacen:
    """Acceso al archivo de progreso. Se usa como gestor de contexto."""

    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = Path(ruta) if ruta else RUTA_POR_DEFECTO
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.conexion = sqlite3.connect(self.ruta)
        self.conexion.row_factory = sqlite3.Row
        with closing(self.conexion.cursor()) as cur:
            cur.executescript(ESQUEMA)
        self.conexion.commit()

    def __enter__(self) -> Almacen:
        return self

    def __exit__(self, *_: object) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        self.conexion.close()

    # -- configuración ----------------------------------------------------

    def guardar_config(self, config: Configuracion) -> None:
        """Guarda (o reemplaza) la configuración del estudiante."""
        datos = {
            "nombre": config.nombre,
            "fecha_examen": config.fecha_examen.isoformat(),
            "meta_global": str(config.meta_global),
            "horas_semana": str(config.horas_semana),
            "dias_por_semana": str(config.dias_por_semana),
        }
        with closing(self.conexion.cursor()) as cur:
            cur.executemany(
                "INSERT INTO config (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                datos.items(),
            )
        self.conexion.commit()

    def config(self) -> Configuracion | None:
        """La configuración guardada, o ``None`` si todavía no se ha creado."""
        with closing(self.conexion.cursor()) as cur:
            filas = cur.execute("SELECT clave, valor FROM config").fetchall()
        datos = {f["clave"]: f["valor"] for f in filas}
        if "fecha_examen" not in datos:
            return None
        return Configuracion(
            nombre=datos.get("nombre", "estudiante"),
            fecha_examen=date.fromisoformat(datos["fecha_examen"]),
            meta_global=int(datos.get("meta_global", 350)),
            horas_semana=float(datos.get("horas_semana", 10)),
            dias_por_semana=int(datos.get("dias_por_semana", 6)),
        )

    # -- intentos ---------------------------------------------------------

    def guardar_intento(self, intento: Intento) -> None:
        """Registra una pregunta respondida."""
        with closing(self.conexion.cursor()) as cur:
            cur.execute(
                "INSERT INTO intentos (fecha, pregunta_id, area, competencia, tema, "
                "acerto, segundos, causa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intento.fecha.isoformat(),
                    intento.pregunta_id,
                    intento.area.value,
                    intento.competencia,
                    intento.tema,
                    int(intento.acerto),
                    intento.segundos,
                    intento.causa.value if intento.causa else None,
                ),
            )
        self.conexion.commit()

    def intentos(self, desde: date | None = None) -> list[Intento]:
        """Todos los intentos registrados, del más viejo al más nuevo."""
        consulta = "SELECT * FROM intentos"
        parametros: tuple[str, ...] = ()
        if desde:
            consulta += " WHERE fecha >= ?"
            parametros = (desde.isoformat(),)
        consulta += " ORDER BY fecha, id"
        with closing(self.conexion.cursor()) as cur:
            filas = cur.execute(consulta, parametros).fetchall()
        return [
            Intento(
                fecha=date.fromisoformat(f["fecha"]),
                pregunta_id=f["pregunta_id"],
                area=Area(f["area"]),
                competencia=f["competencia"],
                tema=f["tema"],
                acerto=bool(f["acerto"]),
                segundos=f["segundos"],
                causa=CausaError(f["causa"]) if f["causa"] else None,
            )
            for f in filas
        ]

    def ids_respondidos(self) -> set[str]:
        """Los ids de preguntas ya vistas, para no repetirlas de entrada."""
        with closing(self.conexion.cursor()) as cur:
            filas = cur.execute("SELECT DISTINCT pregunta_id FROM intentos").fetchall()
        return {f["pregunta_id"] for f in filas}

    # -- tarjetas de repaso ----------------------------------------------

    def guardar_tarjeta(self, tarjeta: Tarjeta) -> None:
        """Guarda o actualiza una tarjeta del repaso espaciado."""
        with closing(self.conexion.cursor()) as cur:
            cur.execute(
                "INSERT INTO tarjetas (clave, repeticiones, facilidad, intervalo_dias, "
                "proxima_fecha) VALUES (?, ?, ?, ?, ?) ON CONFLICT(clave) DO UPDATE SET "
                "repeticiones = excluded.repeticiones, facilidad = excluded.facilidad, "
                "intervalo_dias = excluded.intervalo_dias, proxima_fecha = excluded.proxima_fecha",
                (
                    tarjeta.clave,
                    tarjeta.repeticiones,
                    tarjeta.facilidad,
                    tarjeta.intervalo_dias,
                    tarjeta.proxima_fecha.isoformat() if tarjeta.proxima_fecha else None,
                ),
            )
        self.conexion.commit()

    def tarjeta(self, clave: str) -> Tarjeta:
        """La tarjeta de una pregunta. Si no existe, devuelve una nueva."""
        with closing(self.conexion.cursor()) as cur:
            fila = cur.execute("SELECT * FROM tarjetas WHERE clave = ?", (clave,)).fetchone()
        if fila is None:
            return Tarjeta(clave=clave)
        return Tarjeta(
            clave=fila["clave"],
            repeticiones=fila["repeticiones"],
            facilidad=fila["facilidad"],
            intervalo_dias=fila["intervalo_dias"],
            proxima_fecha=date.fromisoformat(fila["proxima_fecha"])
            if fila["proxima_fecha"]
            else None,
        )

    def tarjetas(self) -> list[Tarjeta]:
        """Todas las tarjetas del repaso espaciado."""
        with closing(self.conexion.cursor()) as cur:
            filas = cur.execute("SELECT clave FROM tarjetas ORDER BY proxima_fecha").fetchall()
        return [self.tarjeta(f["clave"]) for f in filas]

    # -- simulacros -------------------------------------------------------

    def guardar_simulacro(self, resultado: ResultadoSimulacro) -> None:
        """Guarda el resultado de un simulacro."""
        detalle = {
            "por_area": {
                area.value: {"correctas": r.correctas, "total": r.total, "puntaje": r.puntaje}
                for area, r in resultado.por_area.items()
            },
            "por_competencia": {c: list(v) for c, v in resultado.por_competencia.items()},
        }
        with closing(self.conexion.cursor()) as cur:
            cur.execute(
                "INSERT INTO simulacros (fecha, tipo, correctas, total, global_estimado, "
                "escala, segundos_usados, detalle) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    resultado.fecha.isoformat(),
                    resultado.tipo.value,
                    resultado.correctas,
                    resultado.total,
                    resultado.global_estimado,
                    resultado.escala,
                    resultado.segundos_usados,
                    json.dumps(detalle, ensure_ascii=False),
                ),
            )
        self.conexion.commit()

    def historial_simulacros(self) -> list[tuple[date, int]]:
        """Pares (fecha, puntaje global) de los simulacros con las cinco áreas.

        Solo entran los que tienen puntaje global: un simulacro de una sola
        área no dice nada sobre el puntaje del examen completo.
        """
        with closing(self.conexion.cursor()) as cur:
            filas = cur.execute(
                "SELECT fecha, global_estimado FROM simulacros "
                "WHERE global_estimado IS NOT NULL ORDER BY fecha"
            ).fetchall()
        return [(date.fromisoformat(f["fecha"]), int(f["global_estimado"])) for f in filas]

    def ultimo_diagnostico(self) -> dict[Area, float] | None:
        """Los puntajes por área del simulacro más reciente que las tuvo todas."""
        with closing(self.conexion.cursor()) as cur:
            fila = cur.execute(
                "SELECT detalle FROM simulacros WHERE global_estimado IS NOT NULL "
                "ORDER BY fecha DESC, id DESC LIMIT 1"
            ).fetchone()
        if fila is None:
            return None
        detalle = json.loads(fila["detalle"])
        return {Area(a): float(d["puntaje"]) for a, d in detalle["por_area"].items()}
