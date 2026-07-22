#!/usr/bin/env python3
"""HOSPIAI — Expediente Digital (Fase 1 · Fundación).

Base de datos única de la plataforma (`data/hospiai.db`, SQLite): una fila por
factura (expediente) que acumula su historia completa — documentos, hallazgos,
eventos, radicaciones, glosas y pagos — aunque los archivos sigan viviendo en
el servidor. Los agentes no se hablan por archivos sueltos: leen y escriben
aquí (docs/ARQUITECTURA_HOSPIAI.md §4).

Este módulo NO recorre la red ni toca los shares: solo escribe en la base de
datos local. Diseño v1: las atenciones (usuarios/servicios/valor) viven como
columnas del expediente; si el detalle clínico crece (Fase 3, OCR), se separa
en su propia tabla sin cambiar a los agentes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path, PureWindowsPath

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS corridas(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  iniciada TEXT NOT NULL,
  terminada TEXT,
  origen TEXT DEFAULT '',
  version_reglas TEXT DEFAULT '',
  version_motor TEXT DEFAULT '',
  parametros TEXT DEFAULT '',
  total_expedientes INTEGER DEFAULT 0,
  total_documentos INTEGER DEFAULT 0,
  total_hallazgos INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pagadores(
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  nit TEXT DEFAULT '',
  regimen TEXT DEFAULT '',
  canal TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS contratos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pagador_id TEXT NOT NULL REFERENCES pagadores(id),
  nombre TEXT DEFAULT '',
  modalidad TEXT DEFAULT '',
  manual_tarifario TEXT DEFAULT '',
  plazo_dias INTEGER,
  periodicidad TEXT DEFAULT '',
  vigencia_desde TEXT,
  vigencia_hasta TEXT,
  nota TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reglas(
  id TEXT PRIMARY KEY,
  ambito TEXT DEFAULT '',
  exige TEXT DEFAULT '',
  criticidad TEXT DEFAULT '',
  accion TEXT DEFAULT '',
  fuente TEXT DEFAULT '',
  nota TEXT DEFAULT '',
  version TEXT DEFAULT '',
  actualizada TEXT DEFAULT '',
  vigencia_desde TEXT DEFAULT '',
  vigencia_hasta TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS expedientes(
  factura_norm TEXT PRIMARY KEY,
  factura TEXT NOT NULL,
  pagador_id TEXT DEFAULT '',
  pagador_nombre TEXT DEFAULT '',
  responsable TEXT DEFAULT '',
  lote TEXT DEFAULT '',
  anio INTEGER,
  mes INTEGER,
  carpeta TEXT DEFAULT '',
  valor_total REAL DEFAULT 0,
  usuarios INTEGER DEFAULT 0,
  servicios TEXT DEFAULT '',
  estado TEXT DEFAULT 'AUDITADA',
  dictamen TEXT DEFAULT '',
  creado TEXT NOT NULL,
  actualizado TEXT NOT NULL,
  ultima_corrida INTEGER
);
CREATE TABLE IF NOT EXISTS documentos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  factura_norm TEXT NOT NULL,
  nombre TEXT NOT NULL,
  ruta TEXT NOT NULL,
  codigo TEXT DEFAULT '',
  origen TEXT DEFAULT 'FE',
  visto_primera TEXT NOT NULL,
  visto_ultima TEXT NOT NULL,
  corrida_id INTEGER,
  UNIQUE(factura_norm, ruta)
);
CREATE TABLE IF NOT EXISTS hallazgos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  factura_norm TEXT NOT NULL,
  corrida_id INTEGER NOT NULL,
  agente TEXT NOT NULL,
  tipo TEXT NOT NULL,
  codigo TEXT DEFAULT '',
  criticidad TEXT NOT NULL,
  detalle TEXT DEFAULT '',
  regla_id TEXT DEFAULT '',
  evidencia TEXT DEFAULT '',
  confianza REAL DEFAULT 1.0,
  fecha TEXT NOT NULL,
  resuelto INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS eventos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  factura_norm TEXT NOT NULL,
  fecha TEXT NOT NULL,
  agente TEXT NOT NULL,
  tipo TEXT NOT NULL,
  resultado TEXT DEFAULT '',
  version_reglas TEXT DEFAULT '',
  corrida_id INTEGER,
  detalle TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS radicaciones(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  factura_norm TEXT NOT NULL,
  fecha TEXT,
  plataforma TEXT DEFAULT '',
  numero_radicado TEXT DEFAULT '',
  comprobante TEXT DEFAULT '',
  estado TEXT DEFAULT 'PENDIENTE',
  detalle TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS glosas(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  factura_norm TEXT NOT NULL,
  fecha TEXT,
  causa TEXT DEFAULT '',
  codigo_glosa TEXT DEFAULT '',
  valor REAL DEFAULT 0,
  estado TEXT DEFAULT 'ABIERTA',
  detalle TEXT DEFAULT '',
  solucion TEXT DEFAULT '',
  aprendizaje TEXT DEFAULT '',
  tiempo_dias INTEGER
);
CREATE TABLE IF NOT EXISTS pagos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  factura_norm TEXT NOT NULL,
  fecha TEXT,
  valor REAL DEFAULT 0,
  fuente TEXT DEFAULT '',
  detalle TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_documentos_fac ON documentos(factura_norm);
CREATE INDEX IF NOT EXISTS ix_hallazgos_fac ON hallazgos(factura_norm);
CREATE INDEX IF NOT EXISTS ix_hallazgos_corrida ON hallazgos(corrida_id);
CREATE INDEX IF NOT EXISTS ix_eventos_fac ON eventos(factura_norm);
CREATE INDEX IF NOT EXISTS ix_exped_dictamen ON expedientes(dictamen);
CREATE INDEX IF NOT EXISTS ix_exped_responsable ON expedientes(responsable);
CREATE INDEX IF NOT EXISTS ix_exped_pagador ON expedientes(pagador_id);
"""

# Dictámenes que bloquean la radicación (hallazgo crítico a nivel de expediente).
_DICTAMENES_BLOQUEANTES = {
    "SIN_RIPS",
    "SIN_FEV",
    "SIN_CUV",
    "FALTAN_SOPORTES",
    "FACTURA_INCONSISTENTE",
    "ENTIDAD_NO_RESUELTA",
}


# Columnas agregadas por fases posteriores a la creación de la base: si la base
# existe de una fase anterior, se le agregan sin perder datos (migración suave).
_MIGRACIONES: dict[str, dict[str, str]] = {
    "hallazgos": {"evidencia": "TEXT DEFAULT ''", "confianza": "REAL DEFAULT 1.0"},
    "glosas": {
        "solucion": "TEXT DEFAULT ''",
        "aprendizaje": "TEXT DEFAULT ''",
        "tiempo_dias": "INTEGER",
    },
    "reglas": {"vigencia_desde": "TEXT DEFAULT ''", "vigencia_hasta": "TEXT DEFAULT ''"},
}

# Vistas: el GRAFO DE CONOCIMIENTO consultable. No son otra base — son el mismo
# expediente leído por sus relaciones (docs/ARQUITECTURA_HOSPIAI.md §7).
VISTAS_SQL = """
CREATE VIEW IF NOT EXISTS vw_evidencias AS
  SELECT h.id, h.factura_norm, e.factura, e.pagador_nombre, e.responsable,
         h.tipo, h.codigo, h.criticidad, h.detalle, h.evidencia, h.confianza,
         h.regla_id, r.fuente AS fuente_normativa, r.nota AS regla_nota,
         h.fecha, c.version_reglas, h.resuelto
  FROM hallazgos h
  LEFT JOIN reglas r ON r.id = h.regla_id
  LEFT JOIN expedientes e ON e.factura_norm = h.factura_norm
  LEFT JOIN corridas c ON c.id = h.corrida_id;
CREATE VIEW IF NOT EXISTS vw_productividad AS
  SELECT responsable, COUNT(*) AS facturas,
         SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) AS listas,
         SUM(valor_total) AS valor
  FROM expedientes WHERE responsable <> '' GROUP BY responsable;
CREATE VIEW IF NOT EXISTS vw_memoria_glosas AS
  SELECT g.*, e.pagador_nombre, e.responsable, e.lote
  FROM glosas g LEFT JOIN expedientes e ON e.factura_norm = g.factura_norm;
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _migrar(con: sqlite3.Connection) -> None:
    """Agrega a una base existente las columnas de fases nuevas (sin tocar datos)."""
    for tabla, columnas in _MIGRACIONES.items():
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabla})")}
        for col, tipo in columnas.items():
            if col not in existentes:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")


def abrir(ruta: Path) -> sqlite3.Connection:
    """Abre (creando si no existe) la base del Expediente Digital con su esquema,
    aplica migraciones suaves y crea las vistas del grafo."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(ESQUEMA_SQL)
    _migrar(con)
    con.executescript(VISTAS_SQL)
    return con


def sincronizar_reglas(con: sqlite3.Connection, registro: list[dict], version: str) -> None:
    """Refleja las reglas del JSON declarativo en la tabla `reglas` (para que los
    hallazgos puedan cruzarse con su regla por consulta). El JSON manda."""
    ahora = _ahora()
    for rg in registro:
        con.execute(
            "INSERT INTO reglas(id, ambito, exige, criticidad, accion, fuente, nota, version,"
            " actualizada, vigencia_desde, vigencia_hasta) VALUES(?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " ambito=excluded.ambito, exige=excluded.exige, criticidad=excluded.criticidad,"
            " accion=excluded.accion, fuente=excluded.fuente, nota=excluded.nota,"
            " version=excluded.version, actualizada=excluded.actualizada,"
            " vigencia_desde=excluded.vigencia_desde, vigencia_hasta=excluded.vigencia_hasta",
            (
                rg.get("id", ""),
                json.dumps(rg.get("ambito", {}), ensure_ascii=False),
                json.dumps(rg.get("exige", []), ensure_ascii=False),
                rg.get("criticidad", ""),
                rg.get("accion", ""),
                rg.get("fuente", ""),
                rg.get("nota", ""),
                version,
                ahora,
                str(rg.get("vigencia_desde") or ""),
                str(rg.get("vigencia_hasta") or ""),
            ),
        )


def sincronizar_catalogo(con: sqlite3.Connection, catalogo: list[dict]) -> None:
    """Refleja el catálogo institucional (perfiles por entidad) en las tablas
    `pagadores` y `contratos`: NIT, régimen, plataforma, plazo de radicación y
    periodicidad quedan consultables junto al expediente."""
    for ent in catalogo:
        con.execute(
            "INSERT INTO pagadores(id, nombre, nit, regimen, canal) VALUES(?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, nit=excluded.nit,"
            " regimen=excluded.regimen, canal=excluded.canal",
            (
                ent.get("id", ""),
                ent.get("nombre", ""),
                ent.get("nit", ""),
                ent.get("regimen", ""),
                ent.get("canal", ""),
            ),
        )
        plazo = int(ent.get("plazo_radicacion_dias", 0) or 0)
        periodicidad = ent.get("periodicidad", "")
        if not plazo and not periodicidad:
            continue  # sin ficha contractual todavía: nada que registrar
        existe = con.execute(
            "SELECT id FROM contratos WHERE pagador_id=? AND nombre='FICHA-CATALOGO'",
            (ent.get("id", ""),),
        ).fetchone()
        if existe:
            con.execute(
                "UPDATE contratos SET plazo_dias=?, periodicidad=?, modalidad=? WHERE id=?",
                (plazo or None, periodicidad, ent.get("tipo_radicacion", ""), existe[0]),
            )
        else:
            con.execute(
                "INSERT INTO contratos(pagador_id, nombre, modalidad, plazo_dias, periodicidad)"
                " VALUES(?,?,?,?,?)",
                (
                    ent.get("id", ""),
                    "FICHA-CATALOGO",
                    ent.get("tipo_radicacion", ""),
                    plazo or None,
                    periodicidad,
                ),
            )


def _hallazgos_de(res, regla_id_por_codigo: dict[str, str]) -> list[tuple]:
    """(tipo, codigo, criticidad, detalle, regla_id, evidencia, confianza) por
    resultado del radicador. Motor de Evidencias v1: cada hallazgo es trazable a
    la regla que lo sustenta Y a la evidencia observada. La confianza es 1.0
    porque estas validaciones son determinísticas (inventario de archivos);
    los agentes de lectura de contenido (OCR, Fase 3) reportarán < 1.0."""
    filas: list[tuple] = []
    inventario = f"Inventario de {res.carpeta}: {' '.join(res.soportes_presentes) or 'vacío'}"
    servicios = json.dumps(res.servicios, ensure_ascii=False) if res.servicios else "{}"
    for cod in res.soportes_faltantes:
        filas.append(
            (
                "SOPORTE_FALTANTE",
                cod,
                "BLOQUEA_RADICACION",
                f"Falta el soporte obligatorio {cod}.",
                regla_id_por_codigo.get(cod, "R-BASE-001"),
                inventario,
                1.0,
            )
        )
    for cod in res.soportes_esperados_faltantes:
        filas.append(
            (
                "SOPORTE_ESPERADO_FALTANTE",
                cod,
                "REVISAR",
                f"Falta el soporte clínico {cod} esperado según los servicios facturados.",
                regla_id_por_codigo.get(cod, ""),
                f"Servicios del RIPS que lo exigen: {servicios}. {inventario}",
                1.0,
            )
        )
    for nombre in res.archivos_sin_clasificar:
        filas.append(
            (
                "SIN_TIPIFICAR",
                "",
                "ADVERTENCIA",
                f"Archivo sin tipificar: {nombre}",
                "",
                f"Archivo observado en {res.carpeta}",
                1.0,
            )
        )
    if res.estado in ("SIN_RIPS", "SIN_FEV", "SIN_CUV", "FACTURA_INCONSISTENTE"):
        filas.append(
            (
                res.estado,
                "",
                "BLOQUEA_RADICACION",
                " ".join(res.detalle),
                "R-BASE-001",
                inventario,
                1.0,
            )
        )
    elif res.estado == "ENTIDAD_NO_RESUELTA":
        filas.append(
            (res.estado, "", "BLOQUEA_RADICACION", " ".join(res.detalle), "", inventario, 1.0)
        )
    return filas


def persistir_corrida(
    db_path: Path,
    resultados: list,
    documentos_por_factura: dict[str, list],
    *,
    version_reglas: str,
    version_motor: str,
    regla_id_por_codigo: dict[str, str] | None = None,
    reglas_registro: list[dict] | None = None,
    catalogo: list[dict] | None = None,
    origen: str = "",
    parametros: str = "",
    clasificar=None,
    agente: str = "auditor-completitud",
) -> dict:
    """Guarda una corrida completa del radicador en el Expediente Digital.

    No reemplaza el CSV/XLSX: es memoria ADICIONAL y persistente. Idempotente a
    nivel de expediente/documento (re-correr actualiza, no duplica); los
    hallazgos y eventos sí se registran POR CORRIDA: son la historia auditable.
    """
    regla_id_por_codigo = regla_id_por_codigo or {}
    clasificar = clasificar or (lambda _n: "")
    ahora = _ahora()
    con = abrir(db_path)
    try:
        with con:
            cur = con.execute(
                "INSERT INTO corridas(iniciada, origen, version_reglas, version_motor, parametros)"
                " VALUES(?,?,?,?,?)",
                (ahora, origen, version_reglas, version_motor, parametros),
            )
            corrida_id = cur.lastrowid
            if reglas_registro:
                sincronizar_reglas(con, reglas_registro, version_reglas)
            if catalogo:
                sincronizar_catalogo(con, catalogo)

            n_docs = n_hall = 0
            for res in resultados:
                norm = res.factura_norm or res.factura
                if res.entidad_id or res.entidad_nombre:
                    con.execute(
                        "INSERT INTO pagadores(id, nombre, canal) VALUES(?,?,?)"
                        " ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre,"
                        " canal=excluded.canal",
                        (res.entidad_id or "SIN_PERFIL", res.entidad_nombre, res.canal),
                    )
                servicios = json.dumps(res.servicios, ensure_ascii=False) if res.servicios else ""
                con.execute(
                    "INSERT INTO expedientes(factura_norm, factura, pagador_id, pagador_nombre,"
                    " responsable, lote, anio, mes, carpeta, valor_total, usuarios, servicios,"
                    " estado, dictamen, creado, actualizado, ultima_corrida)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(factura_norm) DO UPDATE SET factura=excluded.factura,"
                    " pagador_id=excluded.pagador_id, pagador_nombre=excluded.pagador_nombre,"
                    " responsable=CASE WHEN excluded.responsable<>'' THEN excluded.responsable"
                    "   ELSE expedientes.responsable END,"
                    " lote=CASE WHEN excluded.lote<>'' THEN excluded.lote"
                    "   ELSE expedientes.lote END,"
                    " anio=COALESCE(excluded.anio, expedientes.anio),"
                    " mes=COALESCE(excluded.mes, expedientes.mes),"
                    " carpeta=excluded.carpeta, valor_total=excluded.valor_total,"
                    " usuarios=excluded.usuarios, servicios=excluded.servicios,"
                    " estado=excluded.estado, dictamen=excluded.dictamen,"
                    " actualizado=excluded.actualizado, ultima_corrida=excluded.ultima_corrida",
                    (
                        norm,
                        res.factura,
                        res.entidad_id or "SIN_PERFIL",
                        res.entidad_nombre,
                        getattr(res, "responsable", ""),
                        getattr(res, "lote", ""),
                        getattr(res, "anio", 0) or None,
                        getattr(res, "mes", 0) or None,
                        res.carpeta,
                        res.valor_total,
                        res.num_usuarios,
                        servicios,
                        "AUDITADA",
                        res.estado,
                        ahora,
                        ahora,
                        corrida_id,
                    ),
                )

                docs: list[tuple[str, str, str]] = []  # (nombre, ruta, origen)
                for p in documentos_por_factura.get(norm, []):
                    docs.append((Path(p).name, str(p), "FE"))
                for ruta in getattr(res, "soportes_clinicos", []):
                    docs.append((PureWindowsPath(ruta).name, str(ruta), "SOPORTES"))
                for nombre, ruta, orig in docs:
                    con.execute(
                        "INSERT INTO documentos(factura_norm, nombre, ruta, codigo, origen,"
                        " visto_primera, visto_ultima, corrida_id) VALUES(?,?,?,?,?,?,?,?)"
                        " ON CONFLICT(factura_norm, ruta) DO UPDATE SET"
                        " visto_ultima=excluded.visto_ultima, corrida_id=excluded.corrida_id",
                        (norm, nombre, ruta, clasificar(nombre), orig, ahora, ahora, corrida_id),
                    )
                n_docs += len(docs)

                hallazgos = _hallazgos_de(res, regla_id_por_codigo)
                con.executemany(
                    "INSERT INTO hallazgos(factura_norm, corrida_id, agente, tipo, codigo,"
                    " criticidad, detalle, regla_id, evidencia, confianza, fecha)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (norm, corrida_id, agente, t, c, crit, det, rid, evid, conf, ahora)
                        for t, c, crit, det, rid, evid, conf in hallazgos
                    ],
                )
                n_hall += len(hallazgos)

                con.execute(
                    "INSERT INTO eventos(factura_norm, fecha, agente, tipo, resultado,"
                    " version_reglas, corrida_id, detalle) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        norm,
                        ahora,
                        agente,
                        "AUDITORIA",
                        res.estado,
                        version_reglas,
                        corrida_id,
                        f"{len(hallazgos)} hallazgo(s)",
                    ),
                )

            con.execute(
                "UPDATE corridas SET terminada=?, total_expedientes=?, total_documentos=?,"
                " total_hallazgos=? WHERE id=?",
                (_ahora(), len(resultados), n_docs, n_hall, corrida_id),
            )
        return {
            "corrida_id": corrida_id,
            "expedientes": len(resultados),
            "documentos": n_docs,
            "hallazgos": n_hall,
        }
    finally:
        con.close()
