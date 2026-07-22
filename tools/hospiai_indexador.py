#!/usr/bin/env python3
"""HOSPIAI — AG001 · Servicio de Indexación Permanente.

Reemplaza definitivamente el archivo idx_soportes_2026.txt: el índice de los
shares vive en BASES SQLITE (una por servidor, en data/indices/), se construye
guardando CADA archivo apenas se encuentra (nunca espera al final), muestra
progreso en tiempo real, se actualiza INCREMENTALMENTE (solo lo que cambió →
segundos), responde búsquedas instantáneas por factura y soporta millones de
documentos sin reconstrucciones completas.

Separación por servidor: indice_y.db, indice_z.db, indice_x.db… — si un
servidor falla, los demás siguen sirviendo. La "vista global" es la unión de
todas las bases al consultar.

Sobre el "watcher": en discos de RED (SMB) los eventos de archivos de Windows
no son confiables (el servidor no siempre los emite). El vigilante de
producción correcto es el RESCAN INCREMENTAL: `vigilar --cada 300` re-escanea
solo fechas de modificación en bucle (o se programa con schtasks). Detecta
todo lo nuevo en minutos, sin depender de eventos que pueden no llegar.

Solo lectura sobre los shares; escribe únicamente las bases locales del índice.

Uso:
    py tools\\hospiai_indexador.py indexar "Y:\\" "Z:\\SERVIDOR GLOSAS" "X:\\SERVIDOR RADICACION\\2. SINAC SC SAS - 2026"
    py tools\\hospiai_indexador.py buscar HUS528043
    py tools\\hospiai_indexador.py estado
    py tools\\hospiai_indexador.py vigilar "Y:\\" --cada 300
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radicar_facturacion as rad  # noqa: E402
from hospiai_sdk import Agente, Mision, ResultadoAgente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DIR_INDICES = RAIZ / "data" / "indices"
LOTE = 5000  # archivos por transacción: guardado inmediato sin castigar el disco

ESQUEMA = """
CREATE TABLE IF NOT EXISTS archivos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ruta TEXT UNIQUE NOT NULL,
  nombre TEXT NOT NULL,
  factura TEXT DEFAULT '',
  tipo TEXT DEFAULT '',
  reconocido INTEGER DEFAULT 0,
  tamano INTEGER DEFAULT 0,
  hash TEXT DEFAULT '',
  ultima_modificacion REAL DEFAULT 0,
  visto_primera TEXT NOT NULL,
  visto_ultima TEXT NOT NULL,
  servidor TEXT DEFAULT '',
  estado TEXT DEFAULT 'ACTIVO'
);
CREATE INDEX IF NOT EXISTS ix_archivos_factura ON archivos(factura);
CREATE INDEX IF NOT EXISTS ix_archivos_estado ON archivos(estado);
CREATE TABLE IF NOT EXISTS corridas_indexacion(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  iniciada TEXT NOT NULL,
  terminada TEXT,
  raiz TEXT NOT NULL,
  total INTEGER DEFAULT 0,
  nuevos INTEGER DEFAULT 0,
  actualizados INTEGER DEFAULT 0,
  ausentes INTEGER DEFAULT 0,
  modo TEXT DEFAULT 'INCREMENTAL'
);
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def alias_de(raiz: str) -> str:
    """'Y:\\' → 'y' · 'Z:\\SERVIDOR GLOSAS' → 'z' · otra ruta → nombre + huella
    corta (dos raíces distintas jamás comparten base)."""
    import hashlib

    r = str(raiz).strip().rstrip("\\/")
    m = re.match(r"^([A-Za-z]):", r)
    if m:
        return m.group(1).lower()
    base = re.sub(r"[^a-z0-9]+", "_", (Path(r).name or "raiz").lower()).strip("_")[:14] or "raiz"
    return f"{base}_{hashlib.sha1(r.encode('utf-8')).hexdigest()[:6]}"


def db_de(raiz: str, dir_indices: Path | None = None) -> Path:
    return (dir_indices or DIR_INDICES) / f"indice_{alias_de(raiz)}.db"


def _abrir(ruta_db: Path) -> sqlite3.Connection:
    ruta_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta_db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(ESQUEMA)
    return con


def _clave_y_tipo(nombre: str, carpeta: str, rx) -> tuple[str, str, int]:
    """(factura_norm, tipo, reconocido) — mismo criterio del cruce del motor."""
    clave = rad._clave_factura_en(nombre, rx) or rad._clave_factura_en(carpeta, rx) or ""
    cod, _desc, reconocido = rad.clasificar_soporte(nombre)
    return clave, cod, 1 if reconocido else 0


def indexar_raiz(
    raiz: str,
    dir_indices: Path | None = None,
    completo: bool = False,
    progreso=print,
    patron: str = rad.PATRON_FACTURA_DEFAULT,
) -> dict:
    """Indexa UNA raíz en su base propia. Guarda cada lote apenas se encuentra
    (nunca espera al final) e informa progreso en tiempo real. En modo
    incremental (defecto) solo inserta/actualiza lo nuevo o modificado y marca
    AUSENTE lo que desapareció — en segundos si nada cambió."""
    raiz_p = Path(raiz)
    if not raiz_p.is_dir():
        raise SystemExit(f"No existe o no es carpeta: {raiz}")
    rx = re.compile(patron, re.IGNORECASE)
    con = _abrir(db_de(raiz, dir_indices))
    t0 = time.perf_counter()
    ahora = _ahora()
    servidor = alias_de(raiz)

    previos: dict[str, tuple[float, int]] = {}
    total_previo = 0
    if not completo:
        for f in con.execute("SELECT ruta, ultima_modificacion, tamano FROM archivos"):
            previos[f["ruta"]] = (f["ultima_modificacion"], f["tamano"])
        total_previo = len(previos)

    cur = con.execute(
        "INSERT INTO corridas_indexacion(iniciada, raiz, modo) VALUES(?,?,?)",
        (ahora, str(raiz), "COMPLETO" if completo else "INCREMENTAL"),
    )
    corrida_id = cur.lastrowid
    con.commit()

    vistos: set[str] = set()
    lote: list[tuple] = []
    n = nuevos = actualizados = 0

    def _volcar():
        nonlocal lote
        if not lote:
            return
        with con:
            con.executemany(
                "INSERT INTO archivos(ruta, nombre, factura, tipo, reconocido, tamano,"
                " ultima_modificacion, visto_primera, visto_ultima, servidor, estado)"
                " VALUES(?,?,?,?,?,?,?,?,?,?, 'ACTIVO')"
                " ON CONFLICT(ruta) DO UPDATE SET nombre=excluded.nombre,"
                " factura=excluded.factura, tipo=excluded.tipo,"
                " reconocido=excluded.reconocido, tamano=excluded.tamano,"
                " ultima_modificacion=excluded.ultima_modificacion,"
                " visto_ultima=excluded.visto_ultima, estado='ACTIVO'",
                lote,
            )
        lote = []

    import os

    for dirpath, _dirnames, filenames in os.walk(raiz_p):
        if not filenames:
            continue
        for fn in filenames:
            ruta = str(Path(dirpath) / fn)
            n += 1
            vistos.add(ruta)
            try:
                st = os.stat(ruta)
                mtime, tam = st.st_mtime, st.st_size
            except OSError:
                continue
            previo = previos.get(ruta)
            if previo is not None and abs(previo[0] - mtime) < 1 and previo[1] == tam:
                pass  # sin cambios: no se reescribe
            else:
                clave, tipo, reconocido = _clave_y_tipo(fn, dirpath, rx)
                lote.append((ruta, fn, clave, tipo, reconocido, tam, mtime, ahora, ahora, servidor))
                if previo is None:
                    nuevos += 1
                else:
                    actualizados += 1
                if len(lote) >= LOTE:
                    _volcar()  # guardado INMEDIATO: nunca se espera al final
            if n % 20000 == 0:
                seg = time.perf_counter() - t0
                ritmo = n / seg if seg else 0
                eta = ""
                if total_previo and ritmo:
                    restante = max(0, total_previo - n) / ritmo
                    pct = min(99, 100 * n / total_previo)
                    eta = f" · {pct:.0f}% · restan ~{restante / 60:.0f} min"
                progreso(
                    f"  [{servidor}] {n:,} archivos · {ritmo:,.0f}/s · "
                    f"{seg / 60:.1f} min{eta} · +{nuevos:,} nuevos"
                )
    _volcar()

    ausentes = 0
    if not completo and previos:
        desaparecidos = [r for r in previos if r not in vistos]
        with con:
            for i in range(0, len(desaparecidos), 900):
                trozo = desaparecidos[i : i + 900]
                con.execute(
                    "UPDATE archivos SET estado='AUSENTE', visto_ultima=? WHERE ruta IN (%s)"
                    % ",".join("?" * len(trozo)),
                    [ahora, *trozo],
                )
        ausentes = len(desaparecidos)

    with con:
        con.execute(
            "UPDATE corridas_indexacion SET terminada=?, total=?, nuevos=?, actualizados=?,"
            " ausentes=? WHERE id=?",
            (_ahora(), n, nuevos, actualizados, ausentes, corrida_id),
        )
    con.close()
    seg = time.perf_counter() - t0
    resumen = {
        "raiz": str(raiz),
        "servidor": servidor,
        "total": n,
        "nuevos": nuevos,
        "actualizados": actualizados,
        "ausentes": ausentes,
        "segundos": round(seg, 1),
    }
    progreso(
        f"  [{servidor}] LISTO: {n:,} archivos en {seg / 60:.1f} min — "
        f"{nuevos:,} nuevos · {actualizados:,} actualizados · {ausentes:,} ausentes"
    )
    return resumen


def bases_disponibles(dir_indices: Path | None = None) -> list[Path]:
    d = dir_indices or DIR_INDICES
    return sorted(d.glob("indice_*.db")) if d.is_dir() else []


def buscar(factura: str, dir_indices: Path | None = None) -> list[dict]:
    """Búsqueda instantánea por factura en TODAS las bases (vista global)."""
    clave = rad.normalizar_factura(factura)
    filas: list[dict] = []
    for db in bases_disponibles(dir_indices):
        con = _abrir(db)
        try:
            filas += [
                dict(r)
                for r in con.execute(
                    "SELECT ruta, nombre, tipo, tamano, servidor, estado FROM archivos"
                    " WHERE factura=? ORDER BY nombre",
                    (clave,),
                )
            ]
        finally:
            con.close()
    return filas


def estado(dir_indices: Path | None = None) -> list[dict]:
    salida = []
    for db in bases_disponibles(dir_indices):
        con = _abrir(db)
        try:
            tot = con.execute(
                "SELECT COUNT(*) n, SUM(CASE WHEN estado='ACTIVO' THEN 1 ELSE 0 END) activos,"
                " COUNT(DISTINCT NULLIF(factura,'')) facturas FROM archivos"
            ).fetchone()
            ult = con.execute(
                "SELECT iniciada, terminada, total, nuevos, ausentes, modo"
                " FROM corridas_indexacion ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            con.close()
        salida.append(
            {
                "base": db.name,
                "archivos": tot["n"],
                "activos": tot["activos"] or 0,
                "facturas": tot["facturas"],
                "ultima": dict(ult) if ult else {},
            }
        )
    return salida


# ─── AG001 como agente del SDK ───────────────────────────────────────────────


class AgenteIndexador(Agente):
    """AG001 — El índice permanente como agente: misiones INDEXAR (una raíz)
    y BUSCAR_ARCHIVO (una factura). Solo lectura sobre los shares."""

    id = "AG001"
    nombre = "IndexadorPermanente"
    dominio = "D1"
    version = "2.0"
    entradas = []
    salidas = ["resumen", "coincidencias"]
    herramientas = ["shares-solo-lectura", "data/indices/*.db"]
    capacidades = ["INDEXAR", "BUSCAR_ARCHIVO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        if mision.tipo == "INDEXAR":
            raiz = mision.datos["raiz"]
            resumen = indexar_raiz(
                raiz,
                contexto.get("dir_indices"),
                completo=bool(mision.datos.get("completo")),
                progreso=lambda _m: None,
            )
            res.salida = {"resumen": resumen}
            res.detalle = (
                f"{resumen['total']:,} archivos ({resumen['nuevos']:,} nuevos) "
                f"en {resumen['segundos']}s"
            )
            res.evidencias.append({"tipo": "raiz", "valor": str(raiz)})
        else:  # BUSCAR_ARCHIVO
            factura = mision.datos["factura"]
            filas = buscar(factura, contexto.get("dir_indices"))
            res.salida = {"coincidencias": filas}
            res.confianza = 1.0 if filas else 0.5
            res.detalle = f"{len(filas)} archivo(s) para {factura}"


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AG001 — Servicio de Indexación Permanente (solo lee).")
    p.add_argument(
        "--indices", type=Path, default=None, help="Carpeta de bases (def. data/indices)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    si = sub.add_parser("indexar", help="Indexa una o varias raíces (incremental por defecto).")
    si.add_argument("raices", nargs="+")
    si.add_argument("--completo", action="store_true", help="Reindexa todo (ignora lo previo).")
    sb = sub.add_parser("buscar", help="Búsqueda instantánea por factura en la vista global.")
    sb.add_argument("factura")
    sub.add_parser("estado", help="Estado de cada base del índice.")
    sv = sub.add_parser("vigilar", help="Rescan incremental en bucle (el watcher para SMB).")
    sv.add_argument("raices", nargs="+")
    sv.add_argument("--cada", type=int, default=300, help="Segundos entre pasadas (def. 300).")
    args = p.parse_args(argv)

    if args.cmd == "indexar":
        for raiz in args.raices:
            print(f"Indexando {raiz} …")
            indexar_raiz(raiz, args.indices, completo=args.completo)
        return 0
    if args.cmd == "buscar":
        t0 = time.perf_counter()
        filas = buscar(args.factura, args.indices)
        ms = (time.perf_counter() - t0) * 1000
        print(f"{len(filas)} archivo(s) para {args.factura} en {ms:.0f} ms")
        for f in filas:
            print(f"  [{f['tipo'] or '—'}] ({f['servidor']}) {f['ruta']}  [{f['estado']}]")
        return 0 if filas else 1
    if args.cmd == "estado":
        for e in estado(args.indices):
            u = e["ultima"]
            print(
                f"{e['base']:<18} {e['archivos']:>9,} archivos ({e['activos']:,} activos)"
                f" · {e['facturas']:>7,} facturas · última: {u.get('terminada') or '—'}"
                f" ({u.get('modo', '—')}, +{u.get('nuevos', 0):,} nuevos)"
            )
        if not bases_disponibles(args.indices):
            print("Sin bases todavía: corré primero 'indexar'.")
        return 0
    # vigilar
    print(f"Vigilando {len(args.raices)} raíz(ces) cada {args.cada}s — Ctrl+C para parar.")
    try:
        while True:
            for raiz in args.raices:
                try:
                    indexar_raiz(raiz, args.indices)
                except SystemExit as e:
                    print(f"  ⚠ {e} — sigo con las demás raíces.")
            time.sleep(args.cada)
    except KeyboardInterrupt:
        print("Vigilancia detenida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
