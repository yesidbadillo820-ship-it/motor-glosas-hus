#!/usr/bin/env python3
"""HOSPIAI — Hospital Command Center (Fase 4).

El sistema deja de esperar preguntas: cada mañana LLEGA con las decisiones.
El éxito ya no se mide por agentes o tablas, sino por impacto operativo — más
facturas LISTAS, menos tiempo, menos devoluciones, más recuperación.

Ciclo objetivo: observa → detecta → prioriza → recomienda → aprende → mide.

- **Hospital Operational Score (HOS)** — el indicador que gobierna la plataforma.
  Combina lo que SÍ se puede medir (calidad, productividad, aprendizaje y, cuando
  haya historial, tiempo/devoluciones/recuperación). Los componentes sin datos se
  EXCLUYEN con su razón y se re-pondera — nunca se inventa un número para rellenar.
- **AG029 DailyOrchestrator** (`hospiai.py iniciar-dia`) — el "buenos días": las
  acciones del día ordenadas por retorno, el objetivo en pesos, riesgos y cuello.
- **AG030 WorkloadBalancer** — no solo mide carga: propone mover expedientes para
  equilibrarla (aritmética exacta; la ganancia de throughput va etiquetada).
- **AG031 EarlyWarning** — detecta riesgo de devolución ANTES de la glosa, con
  señales verificables del Document Profile + lecciones VALIDADAS (nunca inventa
  probabilidad: la cita de la memoria o la deja cualitativa).
- **AG032 KpiForecaster** — proyecta el cierre de mes al ritmo actual (supuesto
  declarado); lo que no tiene historia lo dice, no lo estima.
- **AG033 ExecutiveCopilot** (`hospiai.py preguntar`) — responde preguntas
  ejecutivas en lenguaje natural con evidencia, indicadores, confianza y
  recomendaciones. Nunca opiniones.

Uso directo:
    py tools\\hospiai_comando.py hos | situacion | carga | alertas | proyeccion
    (iniciar-dia y preguntar viven en hospiai.py — criterio de aceptación Fase 4)
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402
from hospiai_sdk import Agente, Mision, ResultadoAgente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DB_DEFAULT = RAIZ / "data" / "hospiai.db"

# Escala oficial del HOS (directiva Fase 4).
_ESCALA_HOS = ((92, "Excelente"), (80, "Bueno"), (60, "Aceptable"), (0, "Crítico"))
# Pesos de los 6 componentes; se re-normaliza sobre los DISPONIBLES.
_PESOS_HOS = {
    "calidad_listas": 0.30,
    "tiempo_radicacion": 0.15,
    "devoluciones": 0.15,
    "recuperacion": 0.15,
    "productividad": 0.15,
    "aprendizaje": 0.10,
}


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pesos(v: float) -> str:
    return f"$ {v:,.0f}"


def _clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, x))


def nivel_hos(puntaje: float) -> str:
    for corte, etiqueta in _ESCALA_HOS:
        if puntaje >= corte:
            return etiqueta
    return "Crítico"


# ─── Balance de carga (base de la productividad y del AG030) ─────────────────


def _balance(responsables: list[dict]) -> dict:
    """Carga por responsable = pendientes / carga equilibrada. 100% = parejo."""
    activos = [
        {"responsable": r["responsable"], "pendientes": r["n"] - r["listas"], "n": r["n"]}
        for r in responsables
        if (r["n"] - r["listas"]) > 0
    ]
    total = sum(a["pendientes"] for a in activos)
    if not activos or total == 0:
        return {"cargas": [], "equilibrada": 0, "max_carga_pct": 100, "total_pendientes": 0}
    equilibrada = total / len(activos)
    for a in activos:
        a["carga_pct"] = round(100 * a["pendientes"] / equilibrada, 1)
    activos.sort(key=lambda a: -a["carga_pct"])
    return {
        "cargas": activos,
        "equilibrada": equilibrada,
        "max_carga_pct": activos[0]["carga_pct"],
        "total_pendientes": total,
    }


# ─── Hospital Operational Score ──────────────────────────────────────────────


def hospital_operational_score(db_path: Path) -> dict:
    """El HOS: 0–100, combinando SOLO los componentes con datos. Cada uno
    declara su fórmula; los que no se pueden medir aún quedan excluidos con su
    razón y el puntaje se re-pondera sobre los disponibles (no se inventa)."""
    from hospiai_directores import analizar_corrida

    a = analizar_corrida(db_path)
    resumen = a["resumen"]
    con = hospiai_db.abrir(db_path)
    try:
        n_corridas = con.execute("SELECT COUNT(*) n FROM corridas").fetchone()["n"]
        rad = con.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(e.valor_total),0) v FROM radicaciones r"
            " JOIN expedientes e ON e.factura_norm=r.factura_norm WHERE r.fecha<>''"
        ).fetchone()
        gl = con.execute("SELECT COUNT(*) n, COALESCE(SUM(valor),0) v FROM glosas").fetchone()
        pg = con.execute("SELECT COALESCE(SUM(valor),0) v FROM pagos").fetchone()
        validados = con.execute(
            "SELECT COUNT(*) n FROM conocimiento WHERE estado='VALIDADO'"
        ).fetchone()["n"]
        dias_rad = con.execute(
            "SELECT AVG(julianday(r.fecha)-julianday(d.fecha)) d FROM radicaciones r"
            " JOIN decisiones d ON d.factura_norm=r.factura_norm AND d.dictamen='LISTA'"
            " WHERE r.fecha<>''"
        ).fetchone()["d"]
    finally:
        con.close()

    bal = _balance(a["responsables"])
    componentes = []

    def _add(nombre, disponible, score, detalle, razon=""):
        componentes.append(
            {
                "nombre": nombre,
                "peso": _PESOS_HOS[nombre],
                "disponible": bool(disponible),
                "score": round(_clamp(score), 1) if disponible else None,
                "detalle": detalle if disponible else razon,
            }
        )

    _add(
        "calidad_listas",
        resumen["facturas"] > 0,
        resumen["listas_pct"],
        f"{resumen['listas_pct']:.1f}% de las facturas están LISTAS",
        "sin expedientes todavía",
    )
    _add(
        "tiempo_radicacion",
        rad["n"] > 0 and dias_rad is not None,
        100 - (dias_rad or 0),
        f"{dias_rad:.1f} días promedio de LISTA a radicado" if dias_rad is not None else "",
        "sin radicaciones con fecha (se mide cuando se registre el radicado)",
    )
    _add(
        "devoluciones",
        rad["v"] > 0,
        100 * (1 - (gl["v"] / rad["v"] if rad["v"] else 0)),
        f"{_pesos(gl['v'])} glosados de {_pesos(rad['v'])} radicados" if rad["v"] else "",
        "sin historial de radicación/glosas cargado",
    )
    _add(
        "recuperacion",
        rad["v"] > 0,
        100 * (pg["v"] / rad["v"] if rad["v"] else 0),
        f"{_pesos(pg['v'])} recuperados de {_pesos(rad['v'])} radicados" if rad["v"] else "",
        "sin historial de pagos cargado",
    )
    _add(
        "productividad",
        bool(bal["cargas"]),
        100 - max(0, bal["max_carga_pct"] - 100),
        f"carga máxima {bal['max_carga_pct']:.0f}% del equilibrio (100% = parejo)"
        if bal["cargas"]
        else "",
        "sin responsables con carga pendiente en las rutas",
    )
    apr_disp = validados > 0 or n_corridas >= 2
    _add(
        "aprendizaje",
        apr_disp,
        min(100, 50 + validados * 10) if validados else 50,
        f"{validados} conocimiento(s) VALIDADO(s) alimentando las recomendaciones"
        if validados
        else "ciclo activo, aún sin conocimiento validado",
        "aún sin ciclo de aprendizaje (se necesita ≥2 corridas o memoria validada)",
    )

    disp = [c for c in componentes if c["disponible"]]
    peso_total = sum(c["peso"] for c in disp)
    hos = round(sum(c["peso"] * c["score"] for c in disp) / peso_total) if peso_total else 0
    excluidos = [c["nombre"] for c in componentes if not c["disponible"]]
    return {
        "hos": hos,
        "nivel": nivel_hos(hos),
        "componentes": componentes,
        "componentes_usados": len(disp),
        "excluidos": excluidos,
        "nota": (
            "HOS calculado sobre los componentes con datos; "
            f"excluidos por falta de historial: {', '.join(excluidos)}."
            if excluidos
            else "HOS calculado con los seis componentes."
        ),
        "generado": _ahora(),
    }


# ─── Situación del día (el tablero que abre con decisiones) ──────────────────


def situacion_del_dia(db_path: Path, dir_indices: Path | None = None) -> dict:
    """Lo que un director debe entender en menos de un minuto: HOS, cuánto se
    puede recuperar hoy, prioridad máxima, riesgo principal, cuello de botella
    y la acción inmediata. Todo calculado, cada dato con su fuente."""
    from hospiai_directores import analizar_corrida
    from hospiai_operacion import oportunidades

    hos = hospital_operational_score(db_path)
    a = analizar_corrida(db_path)
    op = oportunidades(db_path, dir_indices)
    top = op["oportunidades"][0] if op["oportunidades"] else None
    # "Riesgo principal" = la entidad que más CAJA congela (no la de más folios).
    entidades = sorted(a["entidades"], key=lambda e: -e["v_detenido"])
    entidad = entidades[0] if entidades else None
    bal = _balance(a["responsables"])
    cuello = _cuello_de_botella(db_path, a)
    accion = None
    if bal["cargas"] and bal["max_carga_pct"] > 110:
        sobre = bal["cargas"][0]
        accion = (
            f"Asignar apoyo a {sobre['responsable']}"
            f" (carga {sobre['carga_pct']:.0f}%, {sobre['pendientes']:,} pendientes)"
        )
    elif top:
        accion = top["oportunidad"]
    return {
        "hos": hos["hos"],
        "nivel": hos["nivel"],
        "recuperable_hoy": op["total_recuperable"],
        "facturas_recuperables": op["facturas_potenciales"],
        "prioridad_maxima": top["oportunidad"] if top else "Sin oportunidades pendientes",
        "prioridad_valor": top["valor_liberado"] if top else 0,
        "riesgo_principal": (
            f"{entidad['pagador_nombre']}: {entidad['pendientes']:,} pendientes por"
            f" {_pesos(entidad['v_detenido'])}"
            if entidad
            else "Sin entidad con pendientes"
        ),
        "cuello_de_botella": cuello,
        "accion_inmediata": accion or "Sin acción crítica: operación al día",
        "generado": _ahora(),
    }


def _cuello_de_botella(db_path: Path, analitica: dict) -> str:
    """El cuello: el área con la causa que más concentra pendientes (AG022) o,
    si hay tiempos, la etapa más lenta (AG023)."""
    try:
        from hospiai_conocimiento import AgenteRootCause

        res = AgenteRootCause().ejecutar(
            Mision(codigo="CC", tipo="CAUSA_RAIZ"), {"db_path": db_path}
        )
        causas = res.salida.get("causas", [])
        if causas:
            c = max(causas, key=lambda x: x["casos"])
            return f"{c['area_responsable']} (por {c['hallazgo']}: {c['concentrado_en']})"
    except Exception:
        pass
    hall = analitica.get("hallazgos") or []
    if hall:
        return f"Causa principal: {hall[0]['causa']} ({hall[0]['facturas']:,} facturas)"
    return "Sin cuello identificable todavía"


# ─── AG029 · Daily Orchestrator ──────────────────────────────────────────────


def iniciar_dia(db_path: Path, dir_indices: Path | None = None, tope: int = 15) -> dict:
    """El 'buenos días': las acciones del día ordenadas por retorno económico,
    el objetivo en pesos, tareas por funcionario, riesgos y cuello de botella."""
    from hospiai_directores import analizar_corrida
    from hospiai_operacion import oportunidades

    sit = situacion_del_dia(db_path, dir_indices)
    op = oportunidades(db_path, dir_indices)
    a = analizar_corrida(db_path)
    acciones = [
        {
            "orden": i + 1,
            "accion": o["oportunidad"],
            "impacto": o["valor_liberado"],
            "facturas": o["facturas_liberadas"],
            "base": o["base"],
        }
        for i, o in enumerate(o for o in op["oportunidades"] if o["valor_liberado"])
    ][:tope]
    objetivo = sum(x["impacto"] for x in acciones)
    bal = _balance(a["responsables"])
    tareas = [
        {
            "responsable": c["responsable"],
            "pendientes": c["pendientes"],
            "carga_pct": c["carga_pct"],
        }
        for c in bal["cargas"][:10]
    ]
    return {
        "saludo": "BUENOS DÍAS",
        "hos": sit["hos"],
        "nivel": sit["nivel"],
        "acciones": acciones,
        "objetivo_del_dia": objetivo,
        "tareas_por_funcionario": tareas,
        "riesgo_principal": sit["riesgo_principal"],
        "cuello_de_botella": sit["cuello_de_botella"],
        "accion_inmediata": sit["accion_inmediata"],
        "generado": _ahora(),
    }


class AgenteDailyOrchestrator(Agente):
    """AG029 — El copiloto de la mañana: llega con las decisiones del día."""

    id = "AG029"
    nombre = "DailyOrchestrator"
    dominio = "COMANDO"
    version = "1.0"
    salidas = ["dia"]
    depende_de = ["AG025", "AG012"]
    capacidades = ["INICIAR_DIA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        dia = iniciar_dia(db, contexto.get("dir_indices"))
        res.salida = {"dia": dia}
        res.detalle = (
            f"HOS {dia['hos']} ({dia['nivel']}) · {len(dia['acciones'])} acción(es) ·"
            f" objetivo {_pesos(dia['objetivo_del_dia'])}"
        )


# ─── AG030 · Workload Balancer ───────────────────────────────────────────────


def balancear_carga(db_path: Path) -> dict:
    """No solo mide: PROPONE mover expedientes del más cargado al más libre. Las
    cargas antes/después son aritmética exacta; el efecto en throughput se
    etiqueta como estimación (depende de capacidad real, no medida)."""
    from hospiai_directores import analizar_corrida

    a = analizar_corrida(db_path)
    bal = _balance(a["responsables"])
    if len(bal["cargas"]) < 2:
        return {"cargas": bal["cargas"], "movimientos": [],
                "nota": "se necesitan 2+ funcionarios con carga para redistribuir"}  # fmt: skip
    movimientos = []
    cargas = [dict(c) for c in bal["cargas"]]
    equil = bal["equilibrada"]
    i, j = 0, len(cargas) - 1
    while i < j:
        sobre, sub = cargas[i], cargas[j]
        exceso = sobre["pendientes"] - equil
        hueco = equil - sub["pendientes"]
        mover = int(min(exceso, hueco))
        if mover <= 0:
            break
        movimientos.append(
            {
                "de": sobre["responsable"],
                "a": sub["responsable"],
                "expedientes": mover,
                "de_carga": f"{sobre['carga_pct']:.0f}% → "
                f"{100 * (sobre['pendientes'] - mover) / equil:.0f}%",
                "a_carga": f"{sub['carga_pct']:.0f}% → "
                f"{100 * (sub['pendientes'] + mover) / equil:.0f}%",
            }
        )
        sobre["pendientes"] -= mover
        sub["pendientes"] += mover
        if sobre["pendientes"] <= equil:
            i += 1
        if sub["pendientes"] >= equil:
            j -= 1
    return {
        "cargas": bal["cargas"],
        "max_carga_pct": bal["max_carga_pct"],
        "movimientos": movimientos,
        "efecto": (
            "Equilibrar la carga libera al funcionario saturado; el aumento de"
            " facturas radicadas es una ESTIMACIÓN (depende de la capacidad real,"
            " no medida). El reparto de expedientes sí es exacto."
        ),
        "generado": _ahora(),
    }


class AgenteWorkloadBalancer(Agente):
    """AG030 — Reparte el trabajo, no solo lo mide."""

    id = "AG030"
    nombre = "WorkloadBalancer"
    dominio = "COMANDO"
    version = "1.0"
    salidas = ["balance"]
    depende_de = ["AG012"]
    capacidades = ["BALANCEAR_CARGA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        b = balancear_carga(db)
        res.salida = {"balance": b}
        res.detalle = f"{len(b['movimientos'])} movimiento(s) propuesto(s) para equilibrar"


# ─── AG031 · Early Warning Engine ────────────────────────────────────────────


def alertas_tempranas(db_path: Path, dir_indices: Path | None = None) -> dict:
    """Riesgo de devolución ANTES de la glosa. Señales verificables del Document
    Profile (firma ausente, calidad D/X, sin texto) + lecciones VALIDADAS por
    EPS. No inventa probabilidad: si la memoria la respalda la cita; si no, deja
    el riesgo cualitativo con su motivo concreto."""
    import hospiai_indexador as idx

    from hospiai_conocimiento import MemoriaInstitucional

    # Señales documentales por factura, leídas del índice (DIS).
    señales: dict[str, list[str]] = {}
    for base in idx.bases_disponibles(dir_indices):
        con = idx._abrir(base)
        try:
            filas = con.execute(
                "SELECT ar.factura, dp.codigo, dp.calidad, dp.firma, dp.texto, dp.problema"
                " FROM document_profile dp JOIN archivos ar ON ar.ruta=dp.ruta"
                " WHERE ar.factura<>'' AND ar.estado='ACTIVO'"
            ).fetchall()
        except Exception:
            filas = []
        finally:
            con.close()
        for f in filas:
            motivos = []
            if f["codigo"] in ("DQX", "RAN") and not f["firma"]:
                motivos.append(f"{f['codigo']} sin firma")
            if f["calidad"] in ("D", "X"):
                motivos.append(f"documento calidad {f['calidad']}")
            if f["problema"]:
                motivos.append(f["problema"].split(":")[0].lower())
            if motivos:
                señales.setdefault(f["factura"], []).extend(motivos)

    con = hospiai_db.abrir(db_path)
    try:
        expedientes = {
            r["factura_norm"]: dict(r)
            for r in con.execute(
                "SELECT factura_norm, factura, pagador_nombre, valor_total, dictamen"
                " FROM expedientes"
            )
        }
    finally:
        con.close()
    memoria = MemoriaInstitucional(db_path)

    alertas = []
    for clave, motivos in señales.items():
        exp = expedientes.get(clave)
        if not exp:
            continue
        nivel = "ALTO" if len(set(motivos)) >= 2 or exp["dictamen"] == "LISTA" else "MEDIO"
        respaldo = None
        for m in motivos:
            lec = memoria.consultar("LECCION", {"eps": exp["pagador_nombre"]})
            if lec:
                respaldo = {
                    "probabilidad": lec[0]["confianza"],
                    "casos": lec[0]["ocurrencias"],
                    "fuente": lec[0]["codigo"],
                }
                break
        alertas.append(
            {
                "factura": exp["factura"],
                "pagador": exp["pagador_nombre"],
                "valor": exp["valor_total"],
                "nivel": nivel,
                "motivos": sorted(set(motivos)),
                "respaldo_historico": respaldo,
                "base": (
                    "probabilidad de la memoria VALIDADA"
                    if respaldo
                    else "riesgo cualitativo por señal documental (sin historial que lo cuantifique)"
                ),
            }
        )
    alertas.sort(key=lambda x: (x["nivel"] != "ALTO", -(x["valor"] or 0)))
    return {
        "alertas": alertas[:30],
        "total": len(alertas),
        "sin_base": not idx.bases_disponibles(dir_indices),
        "nota": (
            "Sin base documental perfilada todavía: corré el Document Intelligence"
            " Service (perfilar) para activar la detección temprana."
            if not idx.bases_disponibles(dir_indices)
            else "Riesgo detectado por señales verificables; la probabilidad solo"
            " se muestra cuando la memoria la respalda."
        ),
        "generado": _ahora(),
    }


class AgenteEarlyWarning(Agente):
    """AG031 — Detecta el riesgo de devolución antes de que llegue la glosa."""

    id = "AG031"
    nombre = "EarlyWarning"
    dominio = "COMANDO"
    version = "1.0"
    salidas = ["alertas"]
    depende_de = ["AG016", "AG019"]
    capacidades = ["ALERTA_TEMPRANA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        al = alertas_tempranas(db, contexto.get("dir_indices"))
        res.salida = {"alertas": al}
        res.detalle = f"{al['total']} alerta(s) de riesgo de devolución"


# ─── AG032 · KPI Forecaster ──────────────────────────────────────────────────


def proyectar_mes(db_path: Path) -> dict:
    """¿Cómo termina el mes si seguimos así? Proyección lineal al ritmo de las
    últimas corridas (supuesto declarado). Sin ≥2 corridas medibles, lo dice —
    no proyecta al aire. Lo que exige historial de glosas/recaudo lo declara."""
    con = hospiai_db.abrir(db_path)
    try:
        corridas = [
            dict(r)
            for r in con.execute(
                "SELECT c.id, c.iniciada,"
                " (SELECT COUNT(*) FROM decisiones d WHERE d.corrida_id=c.id) total,"
                " (SELECT COUNT(*) FROM decisiones d WHERE d.corrida_id=c.id"
                "   AND d.dictamen='LISTA') listas"
                " FROM corridas c ORDER BY c.id DESC LIMIT 4"
            )
        ]
    finally:
        con.close()
    medibles = [c for c in corridas if c["total"]]
    if len(medibles) < 2:
        return {
            "disponible": False,
            "nota": "Historial insuficiente para proyectar: se necesitan ≥2 corridas"
            " con decisiones registradas. Con una sola corrida solo hay foto, no tendencia.",
            "pendiente_historial": ["dinero radicado", "glosas", "recaudo"],
            "generado": _ahora(),
        }
    medibles.sort(key=lambda c: c["id"])
    reciente, anterior = medibles[-1], medibles[-2]
    try:
        d0 = datetime.fromisoformat(anterior["iniciada"])
        d1 = datetime.fromisoformat(reciente["iniciada"])
        dias = max(1, (d1 - d0).days)
    except ValueError:
        dias = 1
    p0 = 100 * anterior["listas"] / anterior["total"] if anterior["total"] else 0
    p1 = 100 * reciente["listas"] / reciente["total"] if reciente["total"] else 0
    ritmo_diario = (p1 - p0) / dias
    dia_actual = datetime.fromisoformat(reciente["iniciada"]).day
    dias_restantes = max(0, 30 - dia_actual)
    proyeccion = round(_clamp(p1 + ritmo_diario * dias_restantes), 1)
    return {
        "disponible": True,
        "pct_listas_actual": round(p1, 1),
        "ritmo_diario_puntos": round(ritmo_diario, 2),
        "proyeccion_fin_mes_pct": proyeccion,
        "tendencia": "mejora"
        if ritmo_diario > 0
        else ("estable" if ritmo_diario == 0 else "empeora"),
        "base": (
            f"proyección lineal al ritmo actual ({p0:.1f}%→{p1:.1f}% en {dias} día(s));"
            " supuesto: el ritmo se mantiene. No es un pronóstico garantizado."
        ),
        "pendiente_historial": ["glosas", "recaudo", "productividad por tiempo"],
        "nota_pendiente": "facturas y % LISTAS se proyectan; dinero/glosas/recaudo"
        " requieren historial de radicación y pagos (aún sin cargar).",
        "generado": _ahora(),
    }


class AgenteKpiForecaster(Agente):
    """AG032 — Proyecta el cierre de mes al ritmo actual."""

    id = "AG032"
    nombre = "KpiForecaster"
    dominio = "COMANDO"
    version = "1.0"
    salidas = ["proyeccion"]
    depende_de = ["AG008"]
    capacidades = ["PROYECTAR_KPI"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        pr = proyectar_mes(db)
        res.salida = {"proyeccion": pr}
        res.detalle = (
            f"proyección fin de mes: {pr['proyeccion_fin_mes_pct']}% LISTAS ({pr['tendencia']})"
            if pr["disponible"]
            else "historial insuficiente para proyectar"
        )


# ─── AG033 · Executive Copilot (lenguaje natural) ────────────────────────────


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _resp(pregunta, respuesta, evidencia, indicadores, confianza, motivo_conf, recomendaciones):
    return {
        "pregunta": pregunta,
        "respuesta": respuesta,
        "evidencia": evidencia,
        "indicadores": indicadores,
        "confianza": confianza,
        "confianza_motivo": motivo_conf,
        "recomendaciones": recomendaciones,
    }


def preguntar(db_path: Path, pregunta: str, dir_indices: Path | None = None) -> dict:
    """El copiloto ejecutivo: interpreta la pregunta y responde con evidencia,
    indicadores, confianza y recomendaciones — nunca opiniones. Todo sale de la
    evidencia, las reglas, la memoria institucional y los indicadores."""
    from hospiai_directores import analizar_corrida
    from hospiai_operacion import mejora_semanal, oportunidades

    q = _norm(pregunta)
    hos = hospital_operational_score(db_path)
    ind = {"HOS": f"{hos['hos']} ({hos['nivel']})"}

    def tiene(*claves) -> bool:
        return any(k in q for k in claves)

    # ¿Dónde está detenido el dinero?
    if tiene("detenido", "detiene", "frena", "parado", "estancado", "atascado"):
        a = analizar_corrida(db_path)
        det = a["riesgo_financiero"]
        top = det["por_causa"][0] if det["por_causa"] else None
        ent = a["entidades"][0] if a["entidades"] else None
        return _resp(
            pregunta,
            f"Hay {_pesos(det['detenido'])} detenidos."
            + (
                f" El grueso está en '{top['dictamen']}' ({top['n']:,} facturas,"
                f" {_pesos(top['v'])})."
                if top
                else ""
            ),
            [
                f"{c['dictamen']}: {c['n']:,} facturas · {_pesos(c['v'])}"
                for c in det["por_causa"][:5]
            ],
            {**ind, "Valor detenido": _pesos(det["detenido"])},
            "ALTA",
            "cálculo directo del Expediente Digital (dictámenes vigentes)",
            (
                [f"Empezar por {ent['pagador_nombre']}: {_pesos(ent['v_detenido'])} detenidos"]
                if ent
                else []
            ),
        )

    # ¿Qué EPS debo llamar primero?
    if tiene("eps", "entidad", "pagador") and tiene("llamar", "primero", "gestionar", "priorizar"):
        a = analizar_corrida(db_path)
        ents = sorted(a["entidades"], key=lambda e: -e["v_detenido"])
        ent = ents[0] if ents else None
        return _resp(
            pregunta,
            (
                f"{ent['pagador_nombre']}: es la que más caja frena"
                f" ({ent['pendientes']:,} pendientes, {_pesos(ent['v_detenido'])};"
                f" causa principal {ent['causa_principal'] or '—'})."
                if ent
                else "No hay entidades con pendientes en la última corrida."
            ),
            [
                f"{e['pagador_nombre']}: {e['pendientes']:,} pend. · {_pesos(e['v_detenido'])}"
                for e in ents[:5]
            ],
            ind,
            "ALTA",
            "ranking por valor detenido del Expediente Digital",
            [f"Preparar el paquete de {ent['pagador_nombre']} con su gemelo digital (AG027)"]
            if ent
            else [],
        )

    # ¿Qué funcionario necesita apoyo?
    if tiene("funcionario", "apoyo", "carga", "sobrecarg", "ayuda", "quien necesita"):
        b = balancear_carga(db_path)
        if not b["cargas"]:
            return _resp(pregunta, "Sin responsables con carga pendiente identificados.",
                         [], ind, "MEDIA", "no hay responsables en las rutas", [])  # fmt: skip
        peor = b["cargas"][0]
        mov = b["movimientos"][0] if b["movimientos"] else None
        return _resp(
            pregunta,
            f"{peor['responsable']}: carga {peor['carga_pct']:.0f}% del equilibrio"
            f" ({peor['pendientes']:,} pendientes).",
            [
                f"{c['responsable']}: {c['pendientes']:,} pend. ({c['carga_pct']:.0f}%)"
                for c in b["cargas"][:6]
            ],
            ind,
            "ALTA",
            "carga = pendientes vs. reparto equilibrado (aritmética exacta)",
            (
                [f"Mover {mov['expedientes']:,} expedientes de {mov['de']} a {mov['a']}"]
                if mov
                else []
            ),
        )

    # ¿Qué contrato debo renegociar?
    if tiene("contrato", "renegociar", "negociar"):
        from hospiai_operacion import ficha_pagador

        fichas = sorted(ficha_pagador(db_path), key=lambda f: -f["valor_detenido"])
        peor = fichas[0] if fichas else None
        return _resp(
            pregunta,
            (
                f"{peor['pagador']}: {peor['pct_listas']}% listas y"
                f" {_pesos(peor['valor_detenido'])} detenidos — el de peor desempeño en caja."
                if peor
                else "Sin datos de contratos todavía."
            ),
            [
                f"{f['pagador']}: {f['pct_listas']}% listas · detenido {_pesos(f['valor_detenido'])}"
                for f in fichas[:5]
            ],
            ind,
            "MEDIA",
            "ficha por pagador; el historial de glosas afina el diagnóstico cuando se cargue",
            ([f"Revisar soportes obligatorios y plazos con {peor['pagador']}"] if peor else []),
        )

    # ¿Qué pasó / mejoró / empeoró esta semana / desde ayer?
    if tiene("paso esta semana", "mejoro", "empeoro", "desde ayer", "esta semana", "que cambio"):
        m = mejora_semanal(db_path, dir_indices)
        return _resp(
            pregunta,
            "Balance del período: "
            + "; ".join(m["que_mejoro"][:2])
            + (". Alertas: " + "; ".join(m["que_empeoro"][:2]) if m["que_empeoro"] else ""),
            m["que_aprendimos"],
            ind,
            "ALTA" if "se necesitan" not in m["que_mejoro"][0] else "BAJA",
            "comparación de las dos últimas corridas (Decision Records)",
            m["cambiar_el_lunes"],
        )

    # ¿Qué debo hacer hoy para liberar más dinero? / ¿Qué decisión da más impacto?
    if tiene("liberar", "hoy", "hacer", "mayor impacto", "mas dinero", "decision", "impacto"):
        op = oportunidades(db_path, dir_indices)
        top = op["oportunidades"][:3]
        return _resp(
            pregunta,
            (
                f"La decisión de mayor impacto: {top[0]['oportunidad']}"
                f" → libera {_pesos(top[0]['valor_liberado'])}."
                if top
                else "Sin oportunidades pendientes en la última corrida."
            ),
            [
                f"{o['oportunidad']}: {_pesos(o['valor_liberado'])} ({o['facturas_liberadas']:,} facturas)"
                for o in top
                if o["valor_liberado"]
            ],
            {**ind, "Recuperable total": _pesos(op["total_recuperable"])},
            "ALTA",
            "impacto EXACTO por reglas vigentes (facturas que quedan LISTAS)",
            [o["accion"] for o in top],
        )

    # ¿Qué riesgo debo atender primero?
    if tiene("riesgo", "atender", "devolucion", "glosa"):
        al = alertas_tempranas(db_path, dir_indices)
        top = al["alertas"][0] if al["alertas"] else None
        return _resp(
            pregunta,
            (
                f"Riesgo {top['nivel']} en {top['factura']} ({top['pagador']}):"
                f" {', '.join(top['motivos'])}."
                if top
                else al["nota"]
            ),
            [
                f"{a['factura']} [{a['nivel']}]: {', '.join(a['motivos'])}"
                for a in al["alertas"][:5]
            ],
            ind,
            "MEDIA" if top else "BAJA",
            "señales verificables del Document Profile" if top else "sin base documental perfilada",
            (
                ["Corregir la señal antes de radicar para evitar la devolución"]
                if top
                else ["Correr el Document Intelligence Service para activar la alerta temprana"]
            ),
        )

    # Sin intención reconocida: la situación del día.
    sit = situacion_del_dia(db_path, dir_indices)
    return _resp(
        pregunta,
        f"HOS {sit['hos']} ({sit['nivel']}). Hoy pueden recuperarse"
        f" {_pesos(sit['recuperable_hoy'])}. Prioridad: {sit['prioridad_maxima']}.",
        [f"Riesgo: {sit['riesgo_principal']}", f"Cuello: {sit['cuello_de_botella']}"],
        ind,
        "MEDIA",
        "resumen de la situación del día (no se reconoció una pregunta específica)",
        [sit["accion_inmediata"]],
    )


class AgenteExecutiveCopilot(Agente):
    """AG033 — Responde preguntas ejecutivas con evidencia, nunca opiniones."""

    id = "AG033"
    nombre = "ExecutiveCopilot"
    dominio = "COMANDO"
    version = "1.0"
    entradas = ["pregunta"]
    salidas = ["respuesta"]
    depende_de = ["AG012", "AG025", "AG019"]
    capacidades = ["PREGUNTAR"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        r = preguntar(db, mision.datos["pregunta"], contexto.get("dir_indices"))
        res.salida = {"respuesta": r}
        res.confianza = {"ALTA": 0.9, "MEDIA": 0.6, "BAJA": 0.3}.get(r["confianza"], 0.5)
        res.detalle = r["respuesta"][:120]


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _imprimir_situacion(sit: dict) -> None:
    print("=" * 60)
    print("  SITUACIÓN DEL DÍA")
    print(f"  Hospital Operational Score : {sit['hos']}  ·  {sit['nivel'].upper()}")
    print(f"  Hoy pueden recuperarse     : {_pesos(sit['recuperable_hoy'])}")
    print(f"  Prioridad máxima           : {sit['prioridad_maxima']}")
    print(f"  Riesgo principal           : {sit['riesgo_principal']}")
    print(f"  Cuello de botella          : {sit['cuello_de_botella']}")
    print(f"  Acción inmediata           : {sit['accion_inmediata']}")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Hospital Command Center HOSPIAI (AG029–AG033).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT)
    p.add_argument("--indices", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("hos", "situacion", "carga", "alertas", "proyeccion"):
        sub.add_parser(c)
    args = p.parse_args(argv)
    if not args.db.is_file():
        print(f"ERROR: no existe la base {args.db}. Corré primero el radicador.")
        return 1
    if args.cmd == "hos":
        h = hospital_operational_score(args.db)
        print("=" * 60)
        print(f"  HOSPITAL OPERATIONAL SCORE : {h['hos']}  ·  {h['nivel'].upper()}")
        print("-" * 60)
        for c in h["componentes"]:
            marca = "✓" if c["disponible"] else "·"
            val = f"{c['score']:>5.1f}" if c["disponible"] else "  —  "
            print(f"  {marca} {c['nombre']:<20} {val}  {c['detalle']}")
        print("-" * 60)
        print(f"  {h['nota']}")
        print("=" * 60)
        return 0
    if args.cmd == "situacion":
        _imprimir_situacion(situacion_del_dia(args.db, args.indices))
        return 0
    if args.cmd == "carga":
        b = balancear_carga(args.db)
        for c in b["cargas"]:
            print(
                f"  {c['responsable']:<16} {c['pendientes']:>5,} pendientes  ({c['carga_pct']:.0f}%)"
            )
        for m in b["movimientos"]:
            print(
                f"  → Mover {m['expedientes']:,} de {m['de']} a {m['a']}  ({m['de_carga']} | {m['a_carga']})"
            )
        if b.get("efecto"):
            print(f"  {b['efecto']}")
        return 0
    if args.cmd == "alertas":
        al = alertas_tempranas(args.db, args.indices)
        print(f"  {al['total']} alerta(s) de riesgo de devolución. {al['nota']}")
        for a in al["alertas"][:15]:
            resp = (
                f" · historia {a['respaldo_historico']['probabilidad']:.0%}"
                f" ({a['respaldo_historico']['casos']} casos)"
                if a["respaldo_historico"]
                else ""
            )
            print(
                f"  [{a['nivel']}] {a['factura']} ({a['pagador']}): {', '.join(a['motivos'])}{resp}"
            )
        return 0
    pr = proyectar_mes(args.db)
    if not pr["disponible"]:
        print(f"  {pr['nota']}")
    else:
        print(f"  % LISTAS actual: {pr['pct_listas_actual']}%  ·  tendencia: {pr['tendencia']}")
        print(f"  Proyección fin de mes: {pr['proyeccion_fin_mes_pct']}% LISTAS")
        print(f"  Base: {pr['base']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
