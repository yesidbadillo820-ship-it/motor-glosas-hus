#!/usr/bin/env python3
"""HOSPIAI — API interna estable (Fase 1.7 · Governance).

El contrato con el que otros sistemas (HIS, ERP, BI, portales) consumirán a
HOSPIAI. Se diseña HOY, aunque todo corra local, para que las integraciones de
mañana no obliguen a rediseñar: la capa de servicios (`Servicios`) es la única
puerta a la plataforma y el servidor HTTP la expone tal cual.

Rutas estables (v1 — SOLO LECTURA; las de escritura llegarán con el Supervisor
y siempre con aprobación humana):

    GET /salud                     → métricas operativas
    GET /agentes                   → Registro Central de Agentes
    GET /capacidades               → capacidades → agentes que las atienden
    GET /misiones                  → estado de la cola
    GET /expedientes/{factura}     → el expediente completo
    GET /decisiones/{factura}      → Decision Records de la factura
    GET /evidencias/{factura}      → cadena hallazgo→regla→norma→evidencia
    GET /ontologia/{codigo}        → explicación semántica del código

Uso local:
    py tools\\hospiai_api.py servir --puerto 8765
    (queda en http://127.0.0.1:8765/salud — SOLO en este equipo)
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402

DB_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "hospiai.db"


def _norm(fac: str) -> str:
    f = (fac or "").strip().upper()
    f = f[3:] if f.startswith("HUS") else f
    return f.lstrip("0") or "0"


class Servicios:
    """La única puerta de entrada a la plataforma. Cada método es un endpoint
    estable: devuelve dicts serializables, sin exponer el esquema interno."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_DEFAULT

    def _filas(self, sql: str, args: tuple = ()) -> list[dict]:
        con = hospiai_db.abrir(self.db_path)
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()

    def salud(self) -> dict:
        from hospiai_gobernanza import salud

        return salud(self.db_path)

    def agentes(self) -> list[dict]:
        from hospiai_agentes import registro_con_implementaciones

        return registro_con_implementaciones().listar()

    def capacidades(self) -> dict[str, list[str]]:
        capa: dict[str, list[str]] = {}
        for a in self.agentes():
            for c in a.get("capacidades") or []:
                capa.setdefault(c, []).append(a["id"])
        return dict(sorted(capa.items()))

    def misiones(self) -> list[dict]:
        return self._filas(
            "SELECT codigo, tipo, expediente, prioridad, estado, agente_asignado,"
            " intentos, creada, actualizada FROM misiones ORDER BY id DESC LIMIT 100"
        )

    def expediente(self, factura: str) -> dict | None:
        filas = self._filas("SELECT * FROM expedientes WHERE factura_norm=?", (_norm(factura),))
        if not filas:
            return None
        exp = filas[0]
        exp["documentos"] = self._filas(
            "SELECT nombre, codigo, origen, ruta FROM documentos WHERE factura_norm=?",
            (exp["factura_norm"],),
        )
        return exp

    def decisiones(self, factura: str) -> list[dict]:
        return self._filas(
            "SELECT codigo, dictamen, motivo, regla_id, agente, version_motor,"
            " version_reglas, confianza, fecha FROM decisiones WHERE factura_norm=?"
            " ORDER BY id DESC",
            (_norm(factura),),
        )

    def evidencias(self, factura: str) -> list[dict]:
        return self._filas(
            "SELECT tipo, codigo, criticidad, detalle, evidencia, confianza, regla_id,"
            " fuente_normativa, fecha, version_reglas FROM vw_evidencias"
            " WHERE factura_norm=? ORDER BY id DESC",
            (_norm(factura),),
        )

    def ontologia(self, codigo: str) -> dict:
        from hospiai_semantica import MotorSemantico

        motor = MotorSemantico()
        hallado = motor.concepto(codigo)
        return {
            "codigo": codigo.upper(),
            "hallado": hallado is not None,
            "ontologia": hallado[0] if hallado else "",
            "cadena": motor.explicar(codigo),
        }


class _Manejador(BaseHTTPRequestHandler):
    servicios: Servicios  # inyectado por servir()

    def do_GET(self):  # noqa: N802 (nombre exigido por http.server)
        partes = [p for p in self.path.split("?", 1)[0].split("/") if p]
        try:
            cuerpo = self._enrutar(partes)
        except Exception as e:
            return self._json({"error": str(e)}, 500)
        if cuerpo is None:
            return self._json({"error": "no encontrado"}, 404)
        return self._json(cuerpo, 200)

    def _enrutar(self, partes: list[str]):
        s = self.servicios
        if partes == ["salud"]:
            return s.salud()
        if partes == ["agentes"]:
            return s.agentes()
        if partes == ["capacidades"]:
            return s.capacidades()
        if partes == ["misiones"]:
            return s.misiones()
        if len(partes) == 2:
            recurso, clave = partes
            if recurso == "expedientes":
                return s.expediente(clave)
            if recurso == "decisiones":
                return {"factura": clave, "decisiones": s.decisiones(clave)}
            if recurso == "evidencias":
                return {"factura": clave, "evidencias": s.evidencias(clave)}
            if recurso == "ontologia":
                return s.ontologia(clave)
        return None

    def _json(self, cuerpo, codigo: int) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, fmt, *args):  # silencioso: el log real vive en la BD
        pass


def servir(db_path: Path, puerto: int) -> None:
    _Manejador.servicios = Servicios(db_path)
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), _Manejador)
    print(f"API HOSPIAI (solo lectura) en http://127.0.0.1:{puerto}/salud — Ctrl+C para parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="API interna de HOSPIAI (v1, solo lectura, local).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)
    ss = sub.add_parser("servir", help="Levanta la API en 127.0.0.1 (solo este equipo).")
    ss.add_argument("--puerto", type=int, default=8765)
    args = p.parse_args(argv)
    if not args.db.is_file():
        print(f"ERROR: no existe la base {args.db}. Corré primero el radicador.")
        return 1
    servir(args.db, args.puerto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
