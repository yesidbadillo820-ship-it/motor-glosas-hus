#!/usr/bin/env python3
"""HOSPIAI — Los Directores (Fase 2 · Sprint 2A).

Cuatro agentes que NO revisan documentos ni mueven misiones: interpretan la
corrida completa y la convierten en decisiones.

- **AG012 DirectorAuditoria**  → informe ejecutivo de la corrida (resumen,
  riesgo financiero explicado, ranking por responsable, riesgo por entidad con
  causa principal, hallazgos valorizados con su norma, productividad,
  predicción estadística y recomendaciones priorizadas por impacto).
- **AG013 DirectorOperativo**  → convierte el informe en TAREAS del día por
  funcionario (misiones TAREA_HUMANA, retenidas por política hasta que un
  humano las tome).
- **AG014 DirectorGerencial**  → habla solo en dinero: cuánto puedo radicar
  hoy, cuánto está detenido, cuánto recupero si corrijo X, quién genera mayor
  retorno, qué EPS frena la caja.
- **AG015 AprendizajeInstitucional** → registra cada transición REVISAR→LISTA
  entre corridas: qué cambió, por qué, qué aprendimos (eventos APRENDIZAJE).

Todo se calcula del Expediente Digital. Predicción = estadística pura (sin IA):
una factura "sube" con la corrección del código X si X es lo ÚNICO que le falta.

Uso directo (también corren como misiones vía el Supervisor):
    py tools\\hospiai_directores.py informe     [--db …]
    py tools\\hospiai_directores.py tareas
    py tools\\hospiai_directores.py caja
    py tools\\hospiai_directores.py aprendizaje
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402
from hospiai_sdk import Agente, ColaMisiones, Mision, ResultadoAgente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DB_DEFAULT = RAIZ / "data" / "hospiai.db"
DIR_INFORMES = RAIZ / "data" / "informes"


def _pesos(v: float) -> str:
    return f"$ {v:,.0f}"


# ─── Analítica central (una sola fuente para los tres directores) ────────────


def analizar_corrida(db_path: Path) -> dict:
    """Toda la analítica de la última corrida, calculada del Expediente."""
    con = hospiai_db.abrir(db_path)
    try:
        q = lambda s, a=(): [dict(r) for r in con.execute(s, a).fetchall()]  # noqa: E731
        corrida = q("SELECT * FROM corridas ORDER BY id DESC LIMIT 1")
        ultima = corrida[0]["id"] if corrida else 0

        tot = q(
            "SELECT COUNT(*) n, COALESCE(SUM(valor_total),0) v,"
            " SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas,"
            " COALESCE(SUM(CASE WHEN dictamen='LISTA' THEN valor_total END),0) v_listas"
            " FROM expedientes"
        )[0]
        detenido_por_causa = q(
            "SELECT dictamen, COUNT(*) n, COALESCE(SUM(valor_total),0) v FROM expedientes"
            " WHERE dictamen<>'LISTA' GROUP BY dictamen ORDER BY v DESC"
        )
        responsables = q(
            "SELECT responsable, COUNT(*) n,"
            " SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas,"
            " COALESCE(SUM(valor_total),0) v,"
            " COALESCE(SUM(CASE WHEN dictamen='LISTA' THEN valor_total END),0) v_listas,"
            " COALESCE(SUM(CASE WHEN dictamen<>'LISTA' THEN valor_total END),0) v_detenido"
            " FROM expedientes WHERE responsable<>'' GROUP BY responsable ORDER BY n DESC"
        )
        entidades = q(
            "SELECT e.pagador_nombre, COUNT(*) pendientes,"
            " COALESCE(SUM(e.valor_total),0) v_detenido,"
            " (SELECT h.codigo FROM hallazgos h WHERE h.factura_norm IN"
            "   (SELECT factura_norm FROM expedientes e2 WHERE"
            "    e2.pagador_nombre=e.pagador_nombre AND e2.dictamen<>'LISTA')"
            "   AND h.corrida_id=? AND h.codigo<>''"
            "   GROUP BY h.codigo ORDER BY COUNT(*) DESC LIMIT 1) causa_principal"
            " FROM expedientes e WHERE e.dictamen<>'LISTA'"
            " GROUP BY e.pagador_nombre ORDER BY pendientes DESC",
            (ultima,),
        )
        hallazgos = q(
            "SELECT COALESCE(NULLIF(h.codigo,''), h.tipo) causa,"
            " MAX(h.criticidad) criticidad,"
            " COUNT(DISTINCT h.factura_norm) facturas,"
            " (SELECT COALESCE(SUM(e.valor_total),0) FROM expedientes e"
            "   WHERE e.factura_norm IN (SELECT h2.factura_norm FROM hallazgos h2"
            "     WHERE h2.corrida_id=? AND COALESCE(NULLIF(h2.codigo,''), h2.tipo)="
            "       COALESCE(NULLIF(h.codigo,''), h.tipo))) valor,"
            " MAX((SELECT r.fuente FROM reglas r WHERE r.id=h.regla_id)) norma"
            " FROM hallazgos h WHERE h.corrida_id=?"
            " GROUP BY COALESCE(NULLIF(h.codigo,''), h.tipo)"
            " ORDER BY valor DESC",
            (ultima, ultima),
        )
        # Predicción estadística: una factura SUBE con la corrección del código X
        # si X es lo único que le falta (un solo código distinto en sus hallazgos).
        recuperables = q(
            "WITH faltas AS (SELECT factura_norm,"
            "   COUNT(DISTINCT COALESCE(NULLIF(codigo,''), tipo)) distintos,"
            "   MAX(COALESCE(NULLIF(codigo,''), tipo)) unico"
            " FROM hallazgos WHERE corrida_id=? GROUP BY factura_norm)"
            " SELECT f.unico causa, COUNT(*) facturas, COALESCE(SUM(e.valor_total),0) valor"
            " FROM faltas f JOIN expedientes e ON e.factura_norm=f.factura_norm"
            " WHERE f.distintos=1 AND e.dictamen<>'LISTA'"
            " GROUP BY f.unico ORDER BY valor DESC",
            (ultima,),
        )
        reprocesos = q(
            "SELECT COUNT(*) n FROM (SELECT factura_norm FROM eventos"
            " WHERE tipo='AUDITORIA' GROUP BY factura_norm HAVING COUNT(*)>1)"
        )[0]["n"]
    finally:
        con.close()

    no_listas = tot["n"] - tot["listas"]
    detenido = tot["v"] - tot["v_listas"]
    recomendaciones = [
        {
            "prioridad": i + 1,
            "accion": f"Corregir {r['causa']}"
            if r["causa"] not in ("ENTIDAD_NO_RESUELTA", "SIN_TIPIFICAR")
            else (
                "Resolver entidades no identificadas (agregar pagadores al catálogo)"
                if r["causa"] == "ENTIDAD_NO_RESUELTA"
                else "Tipificar correctamente los archivos sin clasificar"
            ),
            "facturas": r["facturas"],
            "impacto": r["valor"],
        }
        for i, r in enumerate(recuperables[:5])
    ]
    return {
        "corrida": corrida[0] if corrida else {},
        "resumen": {
            "facturas": tot["n"],
            "valor_total": tot["v"],
            "listas": tot["listas"],
            "listas_pct": 100 * tot["listas"] / tot["n"] if tot["n"] else 0,
            "valor_listas": tot["v_listas"],
            "no_listas": no_listas,
            "no_listas_pct": 100 * no_listas / tot["n"] if tot["n"] else 0,
        },
        "riesgo_financiero": {"detenido": detenido, "por_causa": detenido_por_causa},
        "responsables": [
            {
                **r,
                "pct_listas": 100 * r["listas"] / r["n"] if r["n"] else 0,
                "pct_observadas": 100 * (r["n"] - r["listas"]) / r["n"] if r["n"] else 0,
            }
            for r in responsables
        ],
        "entidades": entidades,
        "hallazgos": hallazgos,
        "prediccion": recuperables,
        "recomendaciones": recomendaciones,
        "productividad": {"reprocesos": reprocesos},
        "generado": datetime.now().isoformat(timespec="seconds"),
    }


# ─── AG012 · Director de Auditoría ───────────────────────────────────────────


class AgenteDirectorAuditoria(Agente):
    """AG012 — Interpreta la corrida completa y produce el informe ejecutivo."""

    id = "AG012"
    nombre = "DirectorAuditoria"
    dominio = "D6"
    version = "1.0"
    salidas = ["informe", "ruta_informe"]
    depende_de = ["AG008"]
    herramientas = ["expediente"]
    capacidades = ["INFORME_AUDITORIA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        informe = analizar_corrida(db)
        DIR_INFORMES.mkdir(parents=True, exist_ok=True)
        num = informe["corrida"].get("id", 0)
        ruta = DIR_INFORMES / f"informe_corrida_{num:04d}.json"
        ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
        res.salida = {"informe": informe, "ruta_informe": str(ruta)}
        r = informe["resumen"]
        res.detalle = (
            f"{r['facturas']:,} facturas · {r['listas']:,} listas ({r['listas_pct']:.1f}%) · "
            f"detenido {_pesos(informe['riesgo_financiero']['detenido'])}"
        )
        res.evidencias.append({"tipo": "corrida", "valor": str(num)})


# ─── AG013 · Director Operativo ──────────────────────────────────────────────


class AgenteDirectorOperativo(Agente):
    """AG013 — Convierte el informe en las TAREAS del día por funcionario.
    Cada tarea queda como misión TAREA_HUMANA (la política la retiene para
    que la tome una persona, no un robot)."""

    id = "AG013"
    nombre = "DirectorOperativo"
    dominio = "D5"
    version = "1.0"
    salidas = ["tareas"]
    depende_de = ["AG012"]
    capacidades = ["PLAN_OPERATIVO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        a = analizar_corrida(db)
        cola = ColaMisiones(db)
        tareas: list[dict] = []
        top_causa = a["prediccion"][0]["causa"] if a["prediccion"] else ""
        for r in sorted(a["responsables"], key=lambda x: -x["v_detenido"]):
            pendientes = r["n"] - r["listas"]
            if pendientes <= 0:
                continue
            tarea = {
                "responsable": r["responsable"],
                "accion": f"Gestionar {pendientes:,} factura(s) pendientes"
                + (f" — empezar por {top_causa}" if top_causa else ""),
                "pendientes": pendientes,
                "valor": r["v_detenido"],
            }
            tareas.append(tarea)
            m = cola.crear(
                "TAREA_HUMANA",
                prioridad="ALTA" if r["v_detenido"] >= 1_000_000_000 else "NORMAL",
                datos=tarea,
                creada_por=self.id,
            )
            tarea["mision"] = m.codigo
        res.salida = {"tareas": tareas}
        res.detalle = f"{len(tareas)} tarea(s) del día creadas (TAREA_HUMANA, retenidas)"


# ─── AG014 · Director Gerencial ──────────────────────────────────────────────


class AgenteDirectorGerencial(Agente):
    """AG014 — Habla únicamente en dinero. Responde las preguntas de caja."""

    id = "AG014"
    nombre = "DirectorGerencial"
    dominio = "D6"
    version = "1.0"
    salidas = ["respuestas"]
    depende_de = ["AG012"]
    capacidades = ["RESPUESTAS_CAJA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        a = analizar_corrida(db)
        r = a["resumen"]
        mejor = max(a["responsables"], key=lambda x: x["v_listas"], default=None)
        freno = a["entidades"][0] if a["entidades"] else None
        top = a["prediccion"][0] if a["prediccion"] else None
        res.salida = {
            "respuestas": [
                {
                    "pregunta": "¿Cuánto dinero puedo radicar hoy?",
                    "cifra": r["valor_listas"],
                    "respuesta": f"{_pesos(r['valor_listas'])} en {r['listas']:,} facturas LISTAS.",
                },
                {
                    "pregunta": "¿Cuánto dinero está detenido?",
                    "cifra": a["riesgo_financiero"]["detenido"],
                    "respuesta": f"{_pesos(a['riesgo_financiero']['detenido'])} en "
                    f"{r['no_listas']:,} facturas no listas.",
                },
                {
                    "pregunta": "¿Cuánto recupero si soluciono la causa principal?",
                    "cifra": top["valor"] if top else 0,
                    "respuesta": (
                        f"Corrigiendo {top['causa']}: suben {top['facturas']:,} facturas "
                        f"por {_pesos(top['valor'])}."
                        if top
                        else "Sin causas únicas medibles todavía."
                    ),
                },
                {
                    "pregunta": "¿Cuál funcionario genera mayor retorno?",
                    "cifra": mejor["v_listas"] if mejor else 0,
                    "respuesta": (
                        f"{mejor['responsable']}: {_pesos(mejor['v_listas'])} listos "
                        f"({mejor['pct_listas']:.0f}% de efectividad)."
                        if mejor
                        else "Sin responsables identificados en las rutas."
                    ),
                },
                {
                    "pregunta": "¿Cuál EPS está frenando caja?",
                    "cifra": freno["v_detenido"] if freno else 0,
                    "respuesta": (
                        f"{freno['pagador_nombre']}: {freno['pendientes']:,} pendientes por "
                        f"{_pesos(freno['v_detenido'])} (causa principal: "
                        f"{freno['causa_principal'] or '—'})."
                        if freno
                        else "Sin pendientes por entidad."
                    ),
                },
            ]
        }
        res.detalle = "5 respuestas de caja calculadas de la última corrida"


# ─── AG015 · Aprendizaje Institucional ───────────────────────────────────────


class AgenteAprendizaje(Agente):
    """AG015 — Registra cada transición de dictamen entre corridas (p.ej.
    REVISAR→LISTA): qué cambió, por qué, qué aprendimos. Con el tiempo, esta
    es la memoria institucional del hospital."""

    id = "AG015"
    nombre = "AprendizajeInstitucional"
    dominio = "D6"
    version = "1.0"
    salidas = ["aprendizajes"]
    depende_de = ["AG008"]
    capacidades = ["APRENDIZAJE"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        con = hospiai_db.abrir(db)
        try:
            transiciones = [
                dict(r)
                for r in con.execute(
                    "SELECT d1.factura_norm, d1.dictamen antes, d2.dictamen despues,"
                    " d1.corrida_id c1, d2.corrida_id c2"
                    " FROM decisiones d1 JOIN decisiones d2"
                    "   ON d2.factura_norm=d1.factura_norm AND d2.corrida_id>d1.corrida_id"
                    " WHERE d1.dictamen<>d2.dictamen"
                    "   AND d2.corrida_id=(SELECT MAX(corrida_id) FROM decisiones d3"
                    "     WHERE d3.factura_norm=d1.factura_norm)"
                    "   AND d1.corrida_id=(SELECT MAX(corrida_id) FROM decisiones d4"
                    "     WHERE d4.factura_norm=d1.factura_norm"
                    "       AND d4.corrida_id<d2.corrida_id)"
                ).fetchall()
            ]
            aprendizajes = []
            ahora = datetime.now().isoformat(timespec="seconds")
            with con:
                for t in transiciones:
                    ya = con.execute(
                        "SELECT 1 FROM eventos WHERE factura_norm=? AND tipo='APRENDIZAJE'"
                        " AND corrida_id=?",
                        (t["factura_norm"], t["c2"]),
                    ).fetchone()
                    if ya:
                        continue
                    resueltos = [
                        r["cod"]
                        for r in con.execute(
                            "SELECT DISTINCT COALESCE(NULLIF(codigo,''), tipo) cod"
                            " FROM hallazgos WHERE factura_norm=? AND corrida_id=?"
                            " AND COALESCE(NULLIF(codigo,''), tipo) NOT IN"
                            " (SELECT COALESCE(NULLIF(codigo,''), tipo) FROM hallazgos"
                            "  WHERE factura_norm=? AND corrida_id=?)",
                            (t["factura_norm"], t["c1"], t["factura_norm"], t["c2"]),
                        ).fetchall()
                    ]
                    leccion = {
                        "expediente": t["factura_norm"],
                        "cambio": f"{t['antes']} → {t['despues']}",
                        "que_cambio": resueltos,
                        "aprendizaje": (
                            f"Se resolvió {', '.join(resueltos)} y el expediente pasó a "
                            f"{t['despues']}."
                            if resueltos
                            else f"El dictamen pasó de {t['antes']} a {t['despues']}."
                        ),
                    }
                    aprendizajes.append(leccion)
                    con.execute(
                        "INSERT INTO eventos(factura_norm, fecha, agente, tipo, resultado,"
                        " corrida_id, detalle) VALUES(?,?,?,?,?,?,?)",
                        (
                            t["factura_norm"],
                            ahora,
                            f"{self.id} v{self.version}",
                            "APRENDIZAJE",
                            leccion["cambio"],
                            t["c2"],
                            leccion["aprendizaje"][:300],
                        ),
                    )
        finally:
            con.close()
        res.salida = {"aprendizajes": aprendizajes}
        res.detalle = f"{len(aprendizajes)} lección(es) nuevas registradas"


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _correr(agente: Agente, db: Path) -> int:
    m = Mision(codigo="MISION-DIRECTA", tipo=agente.capacidades[0])
    r = agente.ejecutar(m, {"db_path": db})
    print(f"{agente.id} {agente.nombre}: {r.resultado} — {r.detalle}")
    if r.resultado != "OK":
        return 1
    if agente.id == "AG014":
        for resp in r.salida["respuestas"]:
            print(f"  · {resp['pregunta']}\n    → {resp['respuesta']}")
    if agente.id == "AG013":
        for t in r.salida["tareas"]:
            print(
                f"  · {t['responsable']:<14} {t['accion']}  ({_pesos(t['valor'])})  {t['mision']}"
            )
    if agente.id == "AG012":
        print(f"  Informe: {r.salida['ruta_informe']}")
        for rec in r.salida["informe"]["recomendaciones"]:
            print(
                f"  Prioridad {rec['prioridad']}: {rec['accion']} — impacto {_pesos(rec['impacto'])}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Directores HOSPIAI (AG012–AG015).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("informe", "tareas", "caja", "aprendizaje"):
        sub.add_parser(c)
    args = p.parse_args(argv)
    if not args.db.is_file():
        print(f"ERROR: no existe la base {args.db}. Corré primero el radicador.")
        return 1
    agentes = {
        "informe": AgenteDirectorAuditoria,
        "tareas": AgenteDirectorOperativo,
        "caja": AgenteDirectorGerencial,
        "aprendizaje": AgenteAprendizaje,
    }
    return _correr(agentes[args.cmd](), args.db)


if __name__ == "__main__":
    sys.exit(main())
