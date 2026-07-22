#!/usr/bin/env python3
"""HOSPIAI — Enterprise Knowledge Engine (Fase 2.2).

El cerebro del sistema: agentes que PIENSAN con el conocimiento acumulado.

**Regla de arquitectura (obligatoria):** ningún agente aprende por su cuenta ni
crea reglas directamente. Todo aprendizaje entra como CANDIDATO a la
**Memoria Institucional** (tabla `conocimiento`), el **AG019 Knowledge Curator**
lo consolida (deduplica, versiona, mide confianza, exige evidencia) y solo el
conocimiento **VALIDADO** puede ser usado por los demás agentes. Trazable,
auditable, explicable.

**Integridad estadística (innegociable):** toda probabilidad se CALCULA:
- *Por regla vigente* (determinística): "al agregar HEV el expediente queda
  LISTA" cuando HEV es lo único que falta según las reglas — cita la regla.
- *Histórica*: frecuencia real de la memoria (éxitos/ocurrencias con suavizado
  de Laplace) — cita cuántos casos la respaldan. Con 3 casos NO se reporta un
  94%: la confianza refleja el tamaño de la muestra.

Agentes:
- **AG019 KnowledgeCurator** — consolida, deduplica, versiona, mide confianza.
- **AG020 PatternDiscovery** — descubre patrones (EPS, servicio, funcionario,
  documental, temporal) desde la evidencia y los propone a la memoria.
- **AG021 RecommendationEngine** — acciones por expediente con probabilidad y
  casos que la respaldan.
- **AG022 RootCauseEngine** — ¿por qué ocurrió?: análisis de concentración
  (lote/responsable/entidad/mes) + mapa curado causa→área (data/causas_raiz.json).
- **AG023 ProcessMiner** — reconstruye el flujo real desde los eventos y mide
  dónde se pierde tiempo.
- **MotorHipotesis** — ¿qué pasaría si…? (escenarios exactos por reglas y
  estimaciones etiquetadas como tales).

Uso directo:
    py tools\\hospiai_conocimiento.py curar | patrones | causas | flujo
    (recomendar y simular viven en hospiai.py — criterio de aceptación)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402
from hospiai_sdk import Agente, Mision, ResultadoAgente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DB_DEFAULT = RAIZ / "data" / "hospiai.db"
RUTA_CAUSAS = RAIZ / "data" / "causas_raiz.json"

UMBRAL_VALIDACION_N = 3  # mínimo de ocurrencias para promover a VALIDADO
UMBRAL_VALIDACION_CONF = 0.6


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _confianza_laplace(exitos: int, ocurrencias: int) -> float:
    """Frecuencia suavizada: con pocas muestras la confianza se acerca a 0.5
    en vez de inflarse — no se reporta 100% con 1 caso."""
    return round((exitos + 1) / (ocurrencias + 2), 3)


# ─── Memoria Institucional ───────────────────────────────────────────────────


class MemoriaInstitucional:
    """La ÚNICA puerta de entrada y salida del aprendizaje. Los agentes
    registran CANDIDATOS con evidencia; solo lo VALIDADO por el Curator se
    sirve a los demás."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @staticmethod
    def _clave(tipo: str, contexto: dict) -> str:
        base = tipo + "|" + json.dumps(contexto, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def registrar(
        self,
        tipo: str,
        enunciado: str,
        contexto: dict,
        evidencia: str,
        exito: bool = True,
        fuente_agente: str = "",
        ocurrencias: int = 1,
        exitos: int | None = None,
    ) -> str:
        """Registra o refuerza un conocimiento CANDIDATO (mismo tipo+contexto →
        se acumulan ocurrencias, no se duplica). Devuelve la clave."""
        clave = self._clave(tipo, contexto)
        exitos = (ocurrencias if exito else 0) if exitos is None else exitos
        ahora = _ahora()
        con = hospiai_db.abrir(self.db_path)
        try:
            with con:
                con.execute(
                    "INSERT INTO conocimiento(codigo, clave, tipo, enunciado, contexto,"
                    " evidencia, ocurrencias, exitos, confianza, vigente_desde, fuente_agente,"
                    " actualizado) VALUES('', ?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(clave) DO UPDATE SET"
                    " ocurrencias=conocimiento.ocurrencias+excluded.ocurrencias,"
                    " exitos=conocimiento.exitos+excluded.exitos,"
                    " enunciado=excluded.enunciado, evidencia=excluded.evidencia,"
                    " actualizado=excluded.actualizado",
                    (
                        clave, tipo, enunciado,
                        json.dumps(contexto, ensure_ascii=False), evidencia[:500],
                        ocurrencias, exitos,
                        _confianza_laplace(exitos, ocurrencias), ahora, fuente_agente, ahora,
                    ),
                )  # fmt: skip
                fila = con.execute(
                    "SELECT id, codigo FROM conocimiento WHERE clave=?", (clave,)
                ).fetchone()
                if not fila["codigo"]:
                    con.execute(
                        "UPDATE conocimiento SET codigo=? WHERE id=?",
                        (f"CON-{fila['id']:06d}", fila["id"]),
                    )
        finally:
            con.close()
        return clave

    def consultar(
        self, tipo: str | None = None, contexto_como: dict | None = None,
        solo_validado: bool = True,
    ) -> list[dict]:  # fmt: skip
        """El conocimiento servible. Por la regla de arquitectura, los agentes
        consumidores SOLO reciben VALIDADO (salvo pedido explícito del Curator)."""
        con = hospiai_db.abrir(self.db_path)
        try:
            sql = "SELECT * FROM conocimiento WHERE 1=1"
            args: list = []
            if solo_validado:
                sql += " AND estado='VALIDADO'"
            if tipo:
                sql += " AND tipo=?"
                args.append(tipo)
            filas = [dict(r) for r in con.execute(sql + " ORDER BY confianza DESC", args)]
        finally:
            con.close()
        if contexto_como:
            filtradas = []
            for f in filas:
                ctx = json.loads(f["contexto"] or "{}")
                if all(ctx.get(k) == v for k, v in contexto_como.items()):
                    filtradas.append(f)
            return filtradas
        return filas


# ─── AG019 · Knowledge Curator ───────────────────────────────────────────────


class AgenteKnowledgeCurator(Agente):
    """AG019 — Consolida la memoria: recalcula confianza (Laplace), promueve a
    VALIDADO lo que tiene muestra y evidencia suficientes (n≥3, conf≥0.6),
    retira lo que perdió sustento y versiona cada cambio de estado."""

    id = "AG019"
    nombre = "KnowledgeCurator"
    dominio = "KNOWLEDGE"
    version = "1.0"
    salidas = ["curado"]
    depende_de = []
    capacidades = ["CURAR_CONOCIMIENTO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        con = hospiai_db.abrir(db)
        promovidos = retirados = recalculados = 0
        try:
            with con:
                for f in con.execute("SELECT * FROM conocimiento").fetchall():
                    conf = _confianza_laplace(f["exitos"], f["ocurrencias"])
                    estado = f["estado"]
                    nuevo = estado
                    if (
                        estado == "CANDIDATO"
                        and f["ocurrencias"] >= UMBRAL_VALIDACION_N
                        and conf >= UMBRAL_VALIDACION_CONF
                        and f["evidencia"]
                    ):
                        nuevo = "VALIDADO"
                        promovidos += 1
                    elif estado == "VALIDADO" and conf < 0.4:
                        nuevo = "RETIRADO"
                        retirados += 1
                    if conf != f["confianza"] or nuevo != estado:
                        recalculados += 1
                        con.execute(
                            "UPDATE conocimiento SET confianza=?, estado=?,"
                            " version=version + CASE WHEN ?<>estado THEN 1 ELSE 0 END,"
                            " actualizado=? WHERE id=?",
                            (conf, nuevo, nuevo, _ahora(), f["id"]),
                        )
        finally:
            con.close()
        res.salida = {
            "curado": {
                "promovidos": promovidos,
                "retirados": retirados,
                "recalculados": recalculados,
            }
        }
        res.detalle = (
            f"{promovidos} promovido(s) a VALIDADO, {retirados} retirado(s), "
            f"{recalculados} recalculado(s)"
        )


# ─── AG020 · Pattern Discovery ───────────────────────────────────────────────


class AgentePatternDiscovery(Agente):
    """AG020 — Descubre patrones desde la EVIDENCIA de la base (por EPS,
    servicio implicado, funcionario, tipo documental, mes) y los propone a la
    memoria como CANDIDATOS — nunca crea reglas directamente."""

    id = "AG020"
    nombre = "PatternDiscovery"
    dominio = "KNOWLEDGE"
    version = "1.0"
    salidas = ["patrones"]
    depende_de = ["AG008"]
    capacidades = ["DESCUBRIR_PATRONES"]

    _DIMENSIONES = (
        ("eps", "e.pagador_nombre"),
        ("responsable", "e.responsable"),
        ("mes", "COALESCE(e.mes,'')"),
    )

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        memoria = MemoriaInstitucional(db)
        con = hospiai_db.abrir(db)
        patrones: list[dict] = []
        try:
            ultima = con.execute("SELECT MAX(id) m FROM corridas").fetchone()["m"] or 0
            for nombre_dim, columna in self._DIMENSIONES:
                filas = con.execute(
                    f"SELECT {columna} dim, h.codigo, COUNT(DISTINCT h.factura_norm) n,"
                    f" (SELECT COUNT(*) FROM expedientes e2 WHERE"
                    f"  {columna.replace('e.', 'e2.')}={columna} AND e2.dictamen<>'LISTA') total_dim"
                    f" FROM hallazgos h JOIN expedientes e ON e.factura_norm=h.factura_norm"
                    f" WHERE h.corrida_id=? AND h.codigo<>'' AND {columna}<>''"
                    f" GROUP BY dim, h.codigo HAVING n >= 2 ORDER BY n DESC LIMIT 20",
                    (ultima,),
                ).fetchall()
                for f in filas:
                    ctx = {"dimension": nombre_dim, "valor": str(f["dim"]), "codigo": f["codigo"]}
                    enunciado = (
                        f"En {nombre_dim} '{f['dim']}', el faltante más frecuente es "
                        f"{f['codigo']} ({f['n']} de {f['total_dim']} expedientes no listos)."
                    )
                    memoria.registrar(
                        "PATRON", enunciado, ctx,
                        evidencia=f"corrida #{ultima}: {f['n']}/{f['total_dim']} expedientes",
                        fuente_agente=self.id, ocurrencias=f["n"], exitos=f["n"],
                    )  # fmt: skip
                    patrones.append({**ctx, "casos": f["n"], "enunciado": enunciado})
        finally:
            con.close()
        res.salida = {"patrones": patrones}
        res.detalle = f"{len(patrones)} patrón(es) propuestos a la memoria (CANDIDATOS)"


# ─── AG021 · Recommendation Engine ───────────────────────────────────────────


def recomendar_expediente(db_path: Path, factura: str) -> dict:
    """Acciones recomendadas para UNA factura. Dos vías, siempre trazables:
    - POR REGLA: si al conseguir el código X no queda ningún otro hallazgo, el
      dictamen pasa a LISTA por las reglas vigentes (determinístico, cita regla).
    - HISTÓRICA: lecciones VALIDADAS de la memoria (frecuencia + casos)."""
    import radicar_facturacion as rad

    clave = rad.normalizar_factura(factura)
    con = hospiai_db.abrir(db_path)
    try:
        exp = con.execute("SELECT * FROM expedientes WHERE factura_norm=?", (clave,)).fetchone()
        if exp is None:
            return {"factura": factura, "error": "sin expediente (¿corrió el radicador?)"}
        ultima = con.execute(
            "SELECT MAX(corrida_id) m FROM hallazgos WHERE factura_norm=?", (clave,)
        ).fetchone()["m"]
        hallazgos = [
            dict(r)
            for r in con.execute(
                "SELECT DISTINCT COALESCE(NULLIF(codigo,''), tipo) causa, regla_id"
                " FROM hallazgos WHERE factura_norm=? AND corrida_id=?",
                (clave, ultima or 0),
            )
        ]
    finally:
        con.close()
    if exp["dictamen"] == "LISTA":
        return {"factura": factura, "dictamen": "LISTA", "acciones": [],
                "nota": "El expediente ya está LISTO para radicar."}  # fmt: skip
    if not hallazgos:
        return {"factura": factura, "dictamen": exp["dictamen"], "valor": exp["valor_total"],
                "pagador": exp["pagador_nombre"], "acciones": [],
                "nota": "Sin hallazgos registrados en la última corrida: nada que recomendar."}  # fmt: skip

    memoria = MemoriaInstitucional(db_path)
    causas = [h["causa"] for h in hallazgos]
    acciones = []
    for h in hallazgos:
        causa = h["causa"]
        restantes = [c for c in causas if c != causa]
        accion = {
            "accion": f"Conseguir/corregir {causa}",
            "causa": causa,
            "regla": h["regla_id"] or "",
            "restantes_despues": restantes,
        }
        if not restantes:
            accion["base"] = "POR REGLA VIGENTE"
            accion["probabilidad"] = 1.0
            accion["explicacion"] = (
                "Es lo ÚNICO que falta: al conseguirlo, el dictamen pasa a LISTA"
                + (f" (regla {h['regla_id']})" if h["regla_id"] else "")
                + ". Depende solo de obtener el soporte."
            )
        else:
            accion["base"] = "PARCIAL"
            accion["probabilidad"] = 0.0
            accion["explicacion"] = (
                f"Necesario pero no suficiente: quedarían pendientes {', '.join(restantes)}."
            )
        lecciones = memoria.consultar("LECCION", {"codigo": causa})
        lecciones += [
            x
            for x in memoria.consultar("LECCION", {"codigo": causa, "eps": exp["pagador_nombre"]})
            if x not in lecciones
        ]
        if lecciones:
            top = lecciones[0]
            accion["historico"] = {
                "probabilidad": top["confianza"],
                "casos": top["ocurrencias"],
                "conocimiento": top["codigo"],
                "enunciado": top["enunciado"],
            }
        acciones.append(accion)
    acciones.sort(key=lambda a: (-a["probabilidad"], a["accion"]))
    return {
        "factura": factura,
        "dictamen": exp["dictamen"],
        "valor": exp["valor_total"],
        "pagador": exp["pagador_nombre"],
        "acciones": acciones,
    }


class AgenteRecommendation(Agente):
    """AG021 — Recomendaciones por expediente (usa SOLO reglas vigentes +
    conocimiento VALIDADO de la memoria)."""

    id = "AG021"
    nombre = "RecommendationEngine"
    dominio = "KNOWLEDGE"
    version = "1.0"
    entradas = ["factura"]
    salidas = ["recomendacion"]
    depende_de = ["AG019"]
    capacidades = ["RECOMENDAR"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        r = recomendar_expediente(db, mision.datos["factura"])
        res.salida = {"recomendacion": r}
        res.detalle = f"{len(r.get('acciones', []))} acción(es) para {mision.datos['factura']}"


# ─── AG022 · Root Cause Engine ───────────────────────────────────────────────


class AgenteRootCause(Agente):
    """AG022 — ¿Por qué ocurrió? Análisis de CONCENTRACIÓN: si un tipo de
    hallazgo se concentra (>60%) en un lote/responsable/entidad, la causa
    probable está aguas arriba en esa dimensión — con evidencia numérica.
    El mapa causa→área (data/causas_raiz.json) lo cura el área; si no existe
    la entrada, se dice 'área por determinar', no se inventa."""

    id = "AG022"
    nombre = "RootCauseEngine"
    dominio = "KNOWLEDGE"
    version = "1.0"
    salidas = ["causas"]
    depende_de = ["AG008"]
    capacidades = ["CAUSA_RAIZ"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        mapa = (
            json.loads(RUTA_CAUSAS.read_text(encoding="utf-8-sig")) if RUTA_CAUSAS.is_file() else {}
        )
        memoria = MemoriaInstitucional(db)
        con = hospiai_db.abrir(db)
        causas: list[dict] = []
        try:
            ultima = con.execute("SELECT MAX(id) m FROM corridas").fetchone()["m"] or 0
            tipos = [
                r["t"]
                for r in con.execute(
                    "SELECT DISTINCT COALESCE(NULLIF(codigo,''), tipo) t FROM hallazgos"
                    " WHERE corrida_id=?",
                    (ultima,),
                )
            ]
            for t in tipos:
                for dim, col in (("lote", "e.lote"), ("responsable", "e.responsable"),
                                 ("entidad", "e.pagador_nombre")):  # fmt: skip
                    filas = con.execute(
                        f"SELECT {col} v, COUNT(*) n FROM hallazgos h"
                        f" JOIN expedientes e ON e.factura_norm=h.factura_norm"
                        f" WHERE h.corrida_id=? AND COALESCE(NULLIF(h.codigo,''), h.tipo)=?"
                        f" AND {col}<>'' GROUP BY v ORDER BY n DESC",
                        (ultima, t),
                    ).fetchall()
                    total = sum(f["n"] for f in filas)
                    if total >= 3 and filas and filas[0]["n"] / total >= 0.6:
                        info_mapa = mapa.get(t, {})
                        causa = {
                            "hallazgo": t,
                            "concentrado_en": f"{dim} '{filas[0]['v']}'",
                            "proporcion": round(filas[0]["n"] / total, 2),
                            "casos": filas[0]["n"],
                            "total": total,
                            "causa_probable": info_mapa.get(
                                "causa", f"origen común aguas arriba en ese {dim}"
                            ),
                            "area_responsable": info_mapa.get("area", "por determinar (curar data/causas_raiz.json)"),
                        }  # fmt: skip
                        causas.append(causa)
                        memoria.registrar(
                            "CAUSA_RAIZ",
                            f"{t} se concentra {causa['proporcion']:.0%} en {causa['concentrado_en']}"
                            f" → {causa['causa_probable']}",
                            {"hallazgo": t, "dimension": dim, "valor": str(filas[0]["v"])},
                            evidencia=f"corrida #{ultima}: {filas[0]['n']}/{total} casos",
                            fuente_agente=self.id,
                            ocurrencias=filas[0]["n"],
                            exitos=filas[0]["n"],
                        )
        finally:
            con.close()
        res.salida = {"causas": causas}
        res.detalle = f"{len(causas)} concentración(es) con causa probable identificada"


# ─── AG023 · Process Miner ───────────────────────────────────────────────────


class AgenteProcessMiner(Agente):
    """AG023 — Reconstruye el flujo real desde los EVENTOS del expediente y
    mide el tiempo promedio entre etapas: dónde pierde tiempo el hospital."""

    id = "AG023"
    nombre = "ProcessMiner"
    dominio = "KNOWLEDGE"
    version = "1.0"
    salidas = ["flujo", "cuello_de_botella"]
    depende_de = ["AG008"]
    capacidades = ["MINAR_PROCESO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        con = hospiai_db.abrir(db)
        transiciones: dict[tuple[str, str], list[float]] = {}
        try:
            filas = con.execute(
                "SELECT factura_norm, tipo, fecha FROM eventos ORDER BY factura_norm, fecha, id"
            ).fetchall()
        finally:
            con.close()
        por_exp: dict[str, list] = {}
        for f in filas:
            por_exp.setdefault(f["factura_norm"], []).append((f["tipo"], f["fecha"]))
        for pasos in por_exp.values():
            for (t1, f1), (t2, f2) in zip(pasos, pasos[1:]):
                try:
                    d1 = datetime.fromisoformat(f1)
                    d2 = datetime.fromisoformat(f2)
                except ValueError:
                    continue
                horas = (d2 - d1).total_seconds() / 3600
                if t1 != t2:
                    transiciones.setdefault((t1, t2), []).append(horas)
        flujo = [
            {
                "de": a,
                "a": b,
                "casos": len(hs),
                "horas_promedio": round(sum(hs) / len(hs), 2),
            }
            for (a, b), hs in sorted(transiciones.items(), key=lambda kv: -len(kv[1]))
        ]
        cuello = max(flujo, key=lambda x: x["horas_promedio"], default=None)
        res.salida = {"flujo": flujo, "cuello_de_botella": cuello}
        res.detalle = (
            f"{len(flujo)} transición(es); cuello: {cuello['de']}→{cuello['a']}"
            f" ({cuello['horas_promedio']} h prom.)"
            if cuello
            else "sin transiciones suficientes todavía"
        )


# ─── Motor de Hipótesis (simulador) ──────────────────────────────────────────


def simular(db_path: Path, escenario: str = "top", codigo: str | None = None) -> dict:
    """¿Qué pasaría si…? Cálculo EXACTO por reglas: una factura se libera si,
    quitada la causa del escenario, no le queda ningún otro hallazgo. Las
    estimaciones de comportamiento (redistribución) se etiquetan como tales."""
    con = hospiai_db.abrir(db_path)
    try:
        ultima = con.execute("SELECT MAX(id) m FROM corridas").fetchone()["m"] or 0
        exp_hallazgos: dict[str, set] = {}
        for f in con.execute(
            "SELECT h.factura_norm, COALESCE(NULLIF(h.codigo,''), h.tipo) c FROM hallazgos h"
            " JOIN expedientes e ON e.factura_norm=h.factura_norm"
            " WHERE h.corrida_id=? AND e.dictamen<>'LISTA'",
            (ultima,),
        ):
            exp_hallazgos.setdefault(f["factura_norm"], set()).add(f["c"])
        valores = dict(con.execute("SELECT factura_norm, valor_total FROM expedientes"))
        responsables = [
            dict(r)
            for r in con.execute(
                "SELECT responsable, COUNT(*) n,"
                " SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas"
                " FROM expedientes WHERE responsable<>'' GROUP BY responsable"
            )
        ]
    finally:
        con.close()

    def _liberadas_si(cods: set[str]) -> tuple[int, float]:
        n = v = 0
        for fac, faltas in exp_hallazgos.items():
            if faltas and faltas <= cods:
                n += 1
                v += valores.get(fac, 0) or 0
        return n, v

    escenarios = []
    todas_causas = sorted({c for s in exp_hallazgos.values() for c in s})
    objetivo = [codigo.upper()] if codigo else todas_causas
    for c in objetivo:
        n, v = _liberadas_si({c})
        if n or codigo:
            escenarios.append(
                {
                    "causa": c,
                    "escenario": f"Corregir {c} en todos los expedientes",
                    "facturas_liberadas": n,
                    "valor_liberado": v,
                    "base": "EXACTO por reglas vigentes (se libera lo que solo espera ese soporte)",
                }
            )
    escenarios.sort(key=lambda e: -e["valor_liberado"])
    n3, v3 = _liberadas_si({x["causa"] for x in escenarios[:3]}) if escenarios else (0, 0)
    combo = {
        "escenario": "Corregir las 3 causas principales a la vez",
        "facturas_liberadas": n3,
        "valor_liberado": v3,
        "base": "EXACTO por reglas vigentes",
    }
    redistribucion = None
    if len(responsables) >= 2:
        tasas = [{**r, "tasa": r["listas"] / r["n"] if r["n"] else 0} for r in responsables]
        mejor = max(tasas, key=lambda x: x["tasa"])
        peor = min(tasas, key=lambda x: x["tasa"])
        if mejor["responsable"] != peor["responsable"]:
            pendientes_peor = peor["n"] - peor["listas"]
            adicionales = int(pendientes_peor * max(0.0, mejor["tasa"] - peor["tasa"]))
            redistribucion = {
                "escenario": f"Si {mejor['responsable']} apoyara a {peor['responsable']}",
                "facturas_adicionales_estimadas": adicionales,
                "base": (
                    "ESTIMACIÓN (supuesto: los pendientes rendirían a la tasa del mejor; "
                    f"{mejor['responsable']} {mejor['tasa']:.0%} vs {peor['responsable']} "
                    f"{peor['tasa']:.0%}). No es un cálculo exacto."
                ),
            }
    return {
        "corrida": ultima,
        "escenarios": escenarios[:8],
        "combinado_top3": combo,
        "redistribucion": redistribucion,
        "generado": _ahora(),
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Knowledge Engine HOSPIAI (AG019–AG023).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("curar", "patrones", "causas", "flujo", "memoria"):
        sub.add_parser(c)
    args = p.parse_args(argv)
    if not args.db.is_file():
        print(f"ERROR: no existe la base {args.db}.")
        return 1
    ctx = {"db_path": args.db}
    if args.cmd == "memoria":
        memoria = MemoriaInstitucional(args.db)
        for k in memoria.consultar(solo_validado=False):
            print(
                f"  [{k['estado']:<9}] {k['codigo']} v{k['version']} conf {k['confianza']:.0%}"
                f" ({k['exitos']}/{k['ocurrencias']}) — {k['enunciado'][:90]}"
            )
        return 0
    agentes = {
        "curar": AgenteKnowledgeCurator,
        "patrones": AgentePatternDiscovery,
        "causas": AgenteRootCause,
        "flujo": AgenteProcessMiner,
    }
    ag = agentes[args.cmd]()
    r = ag.ejecutar(Mision(codigo="M", tipo=ag.capacidades[0]), ctx)
    print(f"{ag.id} {ag.nombre}: {r.resultado} — {r.detalle}")
    return 0 if r.resultado == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
