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
    GET /recomendaciones/{factura} → acciones con base y casos (Knowledge Engine)
    GET /simulaciones[/{codigo}]   → motor de hipótesis: ¿qué pasaría si…?
    GET /conocimiento              → memoria institucional VALIDADA (AG019)
    GET /plan/{factura}            → plan de recuperación del expediente (AG024)
    GET /oportunidades             → correcciones masivas propuestas (AG025)
    GET /indicadores               → indicadores de la última corrida (Fase 3)
    GET /fichas[/{pagador}]        → ficha viva por pagador/contrato (AG026)
    GET /gemelo/{eps}              → gemelo digital de la EPS (AG027)
    GET /mejora                    → informe de mejora continua (AG028)
    GET /hos                       → Hospital Operational Score (Fase 4)
    GET /situacion                 → la situación del día (tablero de decisiones)
    GET /iniciar-dia               → el 'buenos días' operativo (AG029)
    GET /carga                     → balance de carga por funcionario (AG030)
    GET /alertas                   → riesgos de devolución tempranos (AG031)
    GET /proyeccion                → proyección de cierre de mes (AG032)
    GET /preguntar?q=...           → copiloto ejecutivo en lenguaje natural (AG033)

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

    # ── Endpoints ejecutivos (Fase 2 · directores) ─────────────────────────

    def informe(self) -> dict:
        """El informe ejecutivo de la última corrida (analítica AG012)."""
        from hospiai_directores import analizar_corrida

        return analizar_corrida(self.db_path)

    def caja(self) -> list[dict]:
        """Las respuestas de dinero (AG014), calculadas al momento."""
        from hospiai_directores import AgenteDirectorGerencial
        from hospiai_sdk import Mision

        res = AgenteDirectorGerencial().ejecutar(
            Mision(codigo="MISION-API", tipo="RESPUESTAS_CAJA"), {"db_path": self.db_path}
        )
        return res.salida.get("respuestas", [])

    def tareas(self) -> list[dict]:
        """Las tareas del día (misiones TAREA_HUMANA pendientes, del AG013)."""
        return self._filas(
            "SELECT codigo, prioridad, datos, creada FROM misiones"
            " WHERE tipo='TAREA_HUMANA' AND estado='PENDIENTE' ORDER BY"
            " CASE prioridad WHEN 'ALTA' THEN 0 ELSE 1 END, id DESC LIMIT 50"
        )

    # ── Endpoints del Knowledge Engine (Fase 2.2) ──────────────────────────

    def recomendaciones(self, factura: str) -> dict:
        """Acciones recomendadas para la factura (AG021: reglas vigentes +
        memoria VALIDADA; cada probabilidad declara su base)."""
        from hospiai_conocimiento import recomendar_expediente

        return recomendar_expediente(self.db_path, factura)

    def simulaciones(self, codigo: str | None = None) -> dict:
        """Motor de hipótesis: escenarios EXACTOS por reglas; las estimaciones
        de comportamiento van etiquetadas como tales."""
        from hospiai_conocimiento import simular

        return simular(self.db_path, codigo=codigo)

    def conocimiento(self) -> list[dict]:
        """La memoria institucional SERVIBLE: solo conocimiento VALIDADO por
        el Knowledge Curator (regla de arquitectura de la Fase 2.2)."""
        from hospiai_conocimiento import MemoriaInstitucional

        campos = ("codigo", "tipo", "enunciado", "confianza", "ocurrencias", "exitos", "version")
        return [
            {k: f[k] for k in campos}
            for f in MemoriaInstitucional(self.db_path).consultar(solo_validado=True)[:30]
        ]

    # ── Endpoints de Operational Intelligence (Fase 3) ─────────────────────

    def plan(self, factura: str) -> dict:
        """Plan de Recuperación del expediente (AG024)."""
        from hospiai_operacion import plan_expediente

        return plan_expediente(self.db_path, factura)

    def oportunidades(self) -> dict:
        """Correcciones masivas propuestas con dinero exacto (AG025)."""
        from hospiai_operacion import oportunidades

        return oportunidades(self.db_path)

    def indicadores(self) -> dict:
        """Los 4 bloques de indicadores de la última corrida (sin persistir)."""
        from hospiai_operacion import calcular_indicadores

        return calcular_indicadores(self.db_path, guardar=False)

    def fichas(self, pagador: str | None = None) -> list[dict]:
        """Ficha viva por pagador/contrato (AG026)."""
        from hospiai_operacion import ficha_pagador

        return ficha_pagador(self.db_path, pagador)

    def gemelo(self, eps: str) -> dict:
        """Gemelo digital de la EPS (AG027)."""
        from hospiai_operacion import gemelo_eps

        return gemelo_eps(self.db_path, eps)

    def mejora(self) -> dict:
        """Informe de mejora continua (AG028)."""
        from hospiai_operacion import mejora_semanal

        return mejora_semanal(self.db_path)

    # ── Endpoints del Hospital Command Center (Fase 4) ─────────────────────

    def hos(self) -> dict:
        """Hospital Operational Score — el indicador que gobierna todo."""
        from hospiai_comando import hospital_operational_score

        return hospital_operational_score(self.db_path)

    def situacion(self) -> dict:
        """La situación del día: HOS + decisiones (lo primero que ve un director)."""
        from hospiai_comando import situacion_del_dia

        return situacion_del_dia(self.db_path)

    def iniciar_dia(self) -> dict:
        """El 'buenos días' operativo (AG029)."""
        from hospiai_comando import iniciar_dia

        return iniciar_dia(self.db_path)

    def carga(self) -> dict:
        """Balance de carga por funcionario con propuesta de redistribución (AG030)."""
        from hospiai_comando import balancear_carga

        return balancear_carga(self.db_path)

    def alertas(self) -> dict:
        """Riesgos de devolución detectados antes de la glosa (AG031)."""
        from hospiai_comando import alertas_tempranas

        return alertas_tempranas(self.db_path)

    def proyeccion(self) -> dict:
        """Proyección de cierre de mes al ritmo actual (AG032)."""
        from hospiai_comando import proyectar_mes

        return proyectar_mes(self.db_path)

    def preguntar(self, q: str) -> dict:
        """Copiloto ejecutivo en lenguaje natural (AG033)."""
        from hospiai_comando import preguntar

        return preguntar(self.db_path, q)


class _Manejador(BaseHTTPRequestHandler):
    servicios: Servicios  # inyectado por servir()

    def do_GET(self):  # noqa: N802 (nombre exigido por http.server)
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        partes = [p for p in parsed.path.split("/") if p]
        consulta = parse_qs(parsed.query)
        try:
            cuerpo = self._enrutar(partes, consulta)
        except Exception as e:
            return self._json({"error": str(e)}, 500)
        if cuerpo is None:
            return self._json({"error": "no encontrado"}, 404)
        return self._json(cuerpo, 200)

    def _enrutar(self, partes: list[str], consulta: dict | None = None):
        s = self.servicios
        consulta = consulta or {}
        if partes == ["salud"]:
            return s.salud()
        if partes == ["agentes"]:
            return s.agentes()
        if partes == ["capacidades"]:
            return s.capacidades()
        if partes == ["misiones"]:
            return s.misiones()
        if partes == ["informe"]:
            return s.informe()
        if partes == ["caja"]:
            return s.caja()
        if partes == ["tareas"]:
            return s.tareas()
        if partes == ["simulaciones"]:
            return s.simulaciones()
        if partes == ["conocimiento"]:
            return s.conocimiento()
        if partes == ["oportunidades"]:
            return s.oportunidades()
        if partes == ["indicadores"]:
            return s.indicadores()
        if partes == ["fichas"]:
            return s.fichas()
        if partes == ["mejora"]:
            return s.mejora()
        if partes == ["hos"]:
            return s.hos()
        if partes == ["situacion"]:
            return s.situacion()
        if partes == ["iniciar-dia"]:
            return s.iniciar_dia()
        if partes == ["carga"]:
            return s.carga()
        if partes == ["alertas"]:
            return s.alertas()
        if partes == ["proyeccion"]:
            return s.proyeccion()
        if partes == ["preguntar"]:
            q = (consulta.get("q") or [""])[0]
            return s.preguntar(q) if q else {"error": "falta el parámetro ?q=<pregunta>"}
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
            if recurso == "recomendaciones":
                return s.recomendaciones(clave)
            if recurso == "simulaciones":
                return s.simulaciones(clave)
            if recurso == "plan":
                return s.plan(clave)
            if recurso == "fichas":
                return s.fichas(clave)
            if recurso == "gemelo":
                return s.gemelo(clave)
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
