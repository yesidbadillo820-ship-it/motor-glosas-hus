#!/usr/bin/env python3
"""HOSPIAI — Operational Intelligence (Fase 3).

La prioridad deja de ser construir plataforma: es AUMENTAR las facturas LISTAS
y BAJAR los tiempos. Cada agente de este módulo existe porque respondió las 5
preguntas de la regla de oro (problema, dinero, horas, indicador, medición) —
la justificación viva está en su ficha del Registro (data/agentes.json).

- **AG024 PlanRecuperacion** — convierte hallazgos en un PLAN por expediente:
  qué hacer, quién (área curada), cuánto tarda (estimación del área en
  `data/esfuerzos.json` — nunca inventada), con qué probabilidad (por regla
  vigente o historia VALIDADA) y qué impacto. Si el soporte YA existe en un
  servidor indexado, la acción es ASOCIAR (la próxima corrida lo anexa sola).
- **AG025 CorreccionMasiva** — encuentra soluciones MASIVAS: expedientes cuyo
  soporte faltante ya existe en los índices, pendientes de conseguir, archivos
  sin tipificar, entidades sin catálogo. Solo PROPONE — jamás ejecuta.
- **AG026 InteligenciaContratos** — la ficha viva de cada pagador/contrato:
  % listas, valor detenido, causa frecuente, plazo, historial (si está cargado).
- **AG027 GemeloEPS** — el gemelo digital de cada EPS, calculado de los datos:
  exigencia observada, faltante típico, lecciones validadas; los campos que
  requieren historial de glosas/pagos lo declaran (no se inventan).
- **AG028 MejoraContinua** — cada viernes: ¿qué mejoró?, ¿qué empeoró?,
  ¿qué aprendimos?, ¿qué cambiamos el lunes?
- **Indicadores por corrida** (tabla `indicadores`): financieros, operativos,
  de calidad y de aprendizaje — los que no se pueden medir aún quedan NULL con
  su razón, no con un número inventado.

Uso directo:
    py tools\\hospiai_operacion.py indicadores | ficha | gemelo NUEVA | mejora
    (plan y oportunidades viven en hospiai.py — criterio de aceptación Fase 3)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402
from hospiai_sdk import Agente, Mision, ResultadoAgente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DB_DEFAULT = RAIZ / "data" / "hospiai.db"
RUTA_ESFUERZOS = RAIZ / "data" / "esfuerzos.json"

_ETIQUETAS = {
    "ENTIDAD_NO_RESUELTA": "Completar el catálogo de entidades (agregar el pagador)",
    "SIN_TIPIFICAR": "Tipificar/renombrar los archivos sin clasificar",
}


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _esfuerzos() -> dict:
    if RUTA_ESFUERZOS.is_file():
        return json.loads(RUTA_ESFUERZOS.read_text(encoding="utf-8-sig"))
    return {}


def _equivalentes(causa: str) -> list[str]:
    """Códigos que satisfacen la causa (p.ej. un HEV presente cubre EPI/HAU)."""
    import radicar_facturacion as rad

    return list(rad.EQUIVALENCIAS_SOPORTE_DEFAULT.get(causa, [causa]))


# ─── Lectura del índice documental (DIS) ─────────────────────────────────────


def indice_global(dir_indices: Path | None = None) -> tuple[dict, dict]:
    """Del índice permanente: {factura: {tipo: servidor}} de soportes ACTIVOS
    reconocidos, y {factura: n} de archivos con factura pero SIN tipificar."""
    import hospiai_indexador as idx

    tiene: dict[str, dict[str, str]] = {}
    sin_tipificar: dict[str, int] = {}
    for db in idx.bases_disponibles(dir_indices):
        con = idx._abrir(db)
        try:
            for f in con.execute(
                "SELECT factura, tipo, servidor, reconocido FROM archivos"
                " WHERE factura<>'' AND estado='ACTIVO'"
            ):
                if f["reconocido"]:
                    tiene.setdefault(f["factura"], {}).setdefault(f["tipo"], f["servidor"])
                else:
                    sin_tipificar[f["factura"]] = sin_tipificar.get(f["factura"], 0) + 1
        finally:
            con.close()
    return tiene, sin_tipificar


def _existe_en_indice(clave: str, causa: str, tiene: dict) -> str:
    """Servidor donde YA existe un soporte que satisface la causa ('' si no)."""
    tipos = tiene.get(clave, {})
    for cod in _equivalentes(causa):
        if cod in tipos:
            return tipos[cod]
    return ""


# ─── AG024 · Plan de Recuperación por expediente ─────────────────────────────


def plan_expediente(db_path: Path, factura: str, dir_indices: Path | None = None) -> dict:
    """El Plan de Recuperación: cada hallazgo convertido en una acción con
    responsable, tiempo estimado (curado por el área), probabilidad calculada
    e impacto. Nada se inventa: cada dato cita su fuente."""
    from hospiai_conocimiento import recomendar_expediente

    base = recomendar_expediente(db_path, factura)
    if base.get("error") or not base.get("acciones"):
        return {**base, "pasos": [], "total_minutos": 0}
    import radicar_facturacion as rad

    clave = rad.normalizar_factura(factura)
    tiene, _sin_tip = indice_global(dir_indices)
    esf = _esfuerzos()
    pasos = []
    for a in base["acciones"]:
        causa = a["causa"]
        servidor = _existe_en_indice(clave, causa, tiene)
        modo = "ASOCIAR" if servidor else "CONSEGUIR"
        info_esf = esf.get("ASOCIAR" if servidor else causa, {})
        paso = {
            "causa": causa,
            "modo": modo,
            "accion": (
                f"Asociar {causa}: YA existe en el servidor '{servidor}' — la próxima"
                " corrida con el índice lo anexa sola"
                if servidor
                else _ETIQUETAS.get(causa, f"Conseguir/corregir {causa}")
            ),
            "responsable": info_esf.get("area")
            or esf.get(causa, {}).get("area")
            or "por definir (curar data/esfuerzos.json)",
            "tiempo_min": info_esf.get("minutos"),
            "fuente_tiempo": (
                "estimación del área (data/esfuerzos.json)"
                if info_esf.get("minutos") is not None
                else "por estimar (curar data/esfuerzos.json)"
            ),
            "probabilidad": a["probabilidad"] if a["base"] == "POR REGLA VIGENTE" else None,
            "base_probabilidad": a["base"] + (f" (regla {a['regla']})" if a.get("regla") else ""),
            "impacto": (
                f"Pasa inmediatamente a LISTA (libera $ {base.get('valor') or 0:,.0f})"
                if not a["restantes_despues"]
                else "Necesaria; quedarían pendientes: " + ", ".join(a["restantes_despues"])
            ),
        }
        if a.get("historico"):
            h = a["historico"]
            paso["probabilidad"] = h["probabilidad"]
            paso["base_probabilidad"] += (
                f" · historia validada: {h['probabilidad']:.0%} en {h['casos']} caso(s)"
            )
        pasos.append(paso)
    pasos.sort(key=lambda p: (p["modo"] != "ASOCIAR", p["probabilidad"] is None, p["causa"]))
    conocidos = [p["tiempo_min"] for p in pasos if p["tiempo_min"] is not None]
    return {
        **base,
        "pasos": pasos,
        "total_minutos": sum(conocidos),
        "tiempos_completos": len(conocidos) == len(pasos),
    }


class AgentePlanRecuperacion(Agente):
    """AG024 — Radication Readiness Engine: del hallazgo a la acción."""

    id = "AG024"
    nombre = "PlanRecuperacion"
    dominio = "OPERACION"
    version = "1.0"
    entradas = ["factura"]
    salidas = ["plan"]
    depende_de = ["AG021"]
    capacidades = ["PLAN_RECUPERACION"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        plan = plan_expediente(db, mision.datos["factura"], contexto.get("dir_indices"))
        res.salida = {"plan": plan}
        res.detalle = f"{len(plan['pasos'])} paso(s) para {mision.datos['factura']}" + (
            f" · ~{plan['total_minutos']} min" if plan.get("tiempos_completos") else ""
        )


# ─── AG025 · Corrección Masiva (solo propone) ────────────────────────────────


def oportunidades(db_path: Path, dir_indices: Path | None = None) -> dict:
    """Oportunidades de ALTO impacto sobre todos los pendientes. El dinero es
    EXACTO por reglas (facturas que quedan LISTAS al resolver esa causa); la
    existencia del soporte se verifica contra el índice. Solo PROPONE."""
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
    finally:
        con.close()
    tiene, sin_tipificar = indice_global(dir_indices)

    def _valor(facs) -> float:
        return sum(valores.get(f, 0) or 0 for f in facs)

    filas = []
    causas = sorted({c for s in exp_hallazgos.values() for c in s})
    for c in causas:
        faltan = [f for f, s in exp_hallazgos.items() if c in s]
        liberables = [f for f in faltan if exp_hallazgos[f] <= {c}]
        asociables = [f for f in faltan if _existe_en_indice(f, c, tiene)]
        lib_asoc = [f for f in liberables if f in set(asociables)]
        lib_resto = [f for f in liberables if f not in set(asociables)]
        if asociables:
            filas.append(
                {
                    "oportunidad": f"Asociar {c}: ya existe en los servidores"
                    f" ({len(asociables):,} expedientes lo tienen indexado)",
                    "accion": "Correr el radicador con el índice (data\\indices):"
                    " el cruce los anexa solo — nadie mueve archivos",
                    "expedientes": len(asociables),
                    "facturas_liberadas": len(lib_asoc),
                    "valor_liberado": _valor(lib_asoc),
                    "base": "EXACTO por reglas vigentes; existencia verificada en el índice",
                }
            )
        if lib_resto:
            filas.append(
                {
                    "oportunidad": _ETIQUETAS.get(c, f"Conseguir/corregir {c}"),
                    "accion": _ETIQUETAS.get(c, f"Gestionar el soporte {c} con el área")
                    + f" ({len(lib_resto):,} facturas donde es lo único que falta)",
                    "expedientes": len(lib_resto),
                    "facturas_liberadas": len(lib_resto),
                    "valor_liberado": _valor(lib_resto),
                    "base": "EXACTO por reglas vigentes (es lo único que les falta)",
                }
            )
    filas.sort(key=lambda x: -x["valor_liberado"])
    pendientes_sin_tip = {f: n for f, n in sin_tipificar.items() if f in exp_hallazgos}
    todas = {f for f, s in exp_hallazgos.items() if s}
    extra = None
    if pendientes_sin_tip:
        extra = {
            "oportunidad": f"Revisar {sum(pendientes_sin_tip.values()):,} archivo(s) sin"
            f" tipificar de {len(pendientes_sin_tip):,} expedientes pendientes",
            "accion": "Renombrar con el código del soporte: pueden ser soportes ya escaneados",
            "expedientes": len(pendientes_sin_tip),
            "facturas_liberadas": None,
            "valor_liberado": None,
            "base": "POTENCIAL (el impacto se confirma al tipificar — no se estima dinero)",
        }
    return {
        "corrida": ultima,
        "oportunidades": filas[:10],
        "sin_tipificar": extra,
        "total_recuperable": _valor(todas),
        "facturas_potenciales": len(todas),
        "nota": "Total recuperable = todos los pendientes con hallazgos resolubles;"
        " cada oportunidad muestra su tajada exacta. Nada se ejecuta: solo se propone.",
        "generado": _ahora(),
    }


class AgenteCorreccionMasiva(Agente):
    """AG025 — Mass Correction Engine: soluciones por miles, nunca ejecuta."""

    id = "AG025"
    nombre = "CorreccionMasiva"
    dominio = "OPERACION"
    version = "1.0"
    salidas = ["oportunidades"]
    depende_de = ["AG008", "AG001"]
    capacidades = ["CORRECCION_MASIVA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        op = oportunidades(db, contexto.get("dir_indices"))
        res.salida = {"oportunidades": op}
        res.detalle = (
            f"{len(op['oportunidades'])} oportunidad(es) · recuperable"
            f" $ {op['total_recuperable']:,.0f} en {op['facturas_potenciales']:,} facturas"
        )


# ─── AG026 · Inteligencia de Contratos ───────────────────────────────────────


def ficha_pagador(db_path: Path, pagador: str | None = None) -> list[dict]:
    """La ficha viva de cada pagador/contrato. Lo que no tiene historial
    cargado lo dice ('sin historial'), no lo inventa."""
    con = hospiai_db.abrir(db_path)
    try:
        ultima = con.execute("SELECT MAX(id) m FROM corridas").fetchone()["m"] or 0
        filtro, args = "", []
        if pagador:
            filtro = " WHERE e.pagador_nombre LIKE ?"
            args = [f"%{pagador}%"]
        base = [
            dict(r)
            for r in con.execute(
                "SELECT e.pagador_nombre, COUNT(*) n,"
                " SUM(CASE WHEN e.dictamen='LISTA' THEN 1 ELSE 0 END) listas,"
                " COALESCE(SUM(e.valor_total),0) valor,"
                " COALESCE(SUM(CASE WHEN e.dictamen<>'LISTA' THEN e.valor_total END),0)"
                "   v_detenido"
                f" FROM expedientes e{filtro} GROUP BY e.pagador_nombre ORDER BY n DESC",
                args,
            )
        ]
        fichas = []
        for b in base:
            causa = con.execute(
                "SELECT COALESCE(NULLIF(h.codigo,''), h.tipo) c, COUNT(*) n FROM hallazgos h"
                " JOIN expedientes e ON e.factura_norm=h.factura_norm"
                " WHERE h.corrida_id=? AND e.pagador_nombre=?"
                " GROUP BY c ORDER BY n DESC LIMIT 3",
                (ultima, b["pagador_nombre"]),
            ).fetchall()
            contrato = con.execute(
                "SELECT c.plazo_dias, c.periodicidad FROM contratos c"
                " JOIN pagadores p ON p.id=c.pagador_id"
                " WHERE p.nombre=? AND c.nombre='FICHA-CATALOGO'",
                (b["pagador_nombre"],),
            ).fetchone()
            glosas = con.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(g.valor),0) v FROM glosas g"
                " JOIN expedientes e ON e.factura_norm=g.factura_norm"
                " WHERE e.pagador_nombre=?",
                (b["pagador_nombre"],),
            ).fetchone()
            exigidos = [f"{c['c']} ({c['n']:,})" for c in causa]
            fichas.append(
                {
                    "pagador": b["pagador_nombre"] or "—",
                    "expedientes": b["n"],
                    "pct_listas": round(100 * b["listas"] / b["n"], 1) if b["n"] else 0,
                    "valor": b["valor"],
                    "valor_detenido": b["v_detenido"],
                    "causas_frecuentes": exigidos,
                    "plazo_dias": contrato["plazo_dias"] if contrato else None,
                    "periodicidad": (contrato["periodicidad"] or "") if contrato else "",
                    "glosas": glosas["n"],
                    "valor_glosado": glosas["v"],
                    "tiempo_promedio_pago": None,
                    "nota_historial": (
                        ""
                        if glosas["n"]
                        else "sin historial de glosas/pagos cargado (se llena con la operación)"
                    ),
                    "recomendacion": (
                        f"Atacar {causa[0]['c']}: es la causa #1 de sus pendientes"
                        if causa
                        else "Sin pendientes con hallazgos en la última corrida"
                    ),
                }
            )
    finally:
        con.close()
    return fichas


class AgenteContratos(Agente):
    """AG026 — Contract Intelligence: cada contrato, un objeto inteligente."""

    id = "AG026"
    nombre = "InteligenciaContratos"
    dominio = "OPERACION"
    version = "1.0"
    salidas = ["fichas"]
    depende_de = ["AG008"]
    capacidades = ["FICHA_CONTRATO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        fichas = ficha_pagador(db, (mision.datos or {}).get("pagador"))
        res.salida = {"fichas": fichas}
        res.detalle = f"{len(fichas)} ficha(s) de pagador/contrato generadas"


# ─── AG027 · Gemelo digital de EPS ───────────────────────────────────────────


def gemelo_eps(db_path: Path, eps: str) -> dict:
    """El gemelo digital: cómo se comporta ESA EPS, calculado de los datos.
    Cada campo declara su fuente; lo que exige historial externo queda NULL."""
    from hospiai_conocimiento import MemoriaInstitucional

    con = hospiai_db.abrir(db_path)
    try:
        exp = con.execute(
            "SELECT pagador_nombre, COUNT(*) n,"
            " SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas,"
            " COALESCE(SUM(valor_total),0) v FROM expedientes"
            " WHERE pagador_nombre LIKE ? GROUP BY pagador_nombre ORDER BY n DESC LIMIT 1",
            (f"%{eps}%",),
        ).fetchone()
        if exp is None:
            return {"eps": eps, "error": "sin expedientes de esa EPS"}
        nombre = exp["pagador_nombre"]
        ultima = con.execute("SELECT MAX(id) m FROM corridas").fetchone()["m"] or 0
        con_hallazgo = con.execute(
            "SELECT COUNT(DISTINCT h.factura_norm) n FROM hallazgos h"
            " JOIN expedientes e ON e.factura_norm=h.factura_norm"
            " WHERE h.corrida_id=? AND e.pagador_nombre=?",
            (ultima, nombre),
        ).fetchone()["n"]
        faltantes = [
            f"{r['c']} ({r['n']:,})"
            for r in con.execute(
                "SELECT COALESCE(NULLIF(h.codigo,''), h.tipo) c, COUNT(*) n FROM hallazgos h"
                " JOIN expedientes e ON e.factura_norm=h.factura_norm"
                " WHERE h.corrida_id=? AND e.pagador_nombre=?"
                " GROUP BY c ORDER BY n DESC LIMIT 5",
                (ultima, nombre),
            )
        ]
        glosas = con.execute(
            "SELECT causa, COUNT(*) n FROM glosas g JOIN expedientes e"
            " ON e.factura_norm=g.factura_norm WHERE e.pagador_nombre=? AND causa<>''"
            " GROUP BY causa ORDER BY n DESC LIMIT 5",
            (nombre,),
        ).fetchall()
    finally:
        con.close()
    lecciones = MemoriaInstitucional(db_path).consultar("LECCION", {"eps": nombre})
    return {
        "eps": nombre,
        "expedientes": exp["n"],
        "valor": exp["v"],
        "pct_listas": round(100 * exp["listas"] / exp["n"], 1) if exp["n"] else 0,
        "exigencia_observada_pct": round(100 * con_hallazgo / exp["n"], 1) if exp["n"] else 0,
        "fuente_exigencia": "interna: % de sus expedientes con hallazgos en la última corrida",
        "faltantes_tipicos": faltantes,
        "lo_que_funciona": [
            f"{k['enunciado']} ({k['confianza']:.0%}, {k['ocurrencias']} casos)"
            for k in lecciones[:5]
        ]
        or ["aún sin lecciones VALIDADAS para esta EPS (se llenan con las corridas)"],
        "devuelve_frecuentemente": [f"{g['causa']} ({g['n']:,})" for g in glosas]
        or ["sin historial de glosas cargado"],
        "demora_promedio_dias": None,
        "nota_demora": "requiere historial de radicaciones/pagos (aún no cargado)",
        "generado": _ahora(),
    }


class AgenteGemeloEPS(Agente):
    """AG027 — EPS Digital Twin: preparar cada factura PARA esa EPS."""

    id = "AG027"
    nombre = "GemeloEPS"
    dominio = "OPERACION"
    version = "1.0"
    entradas = ["eps"]
    salidas = ["gemelo"]
    depende_de = ["AG008", "AG019"]
    capacidades = ["GEMELO_EPS"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        g = gemelo_eps(db, mision.datos["eps"])
        res.salida = {"gemelo": g}
        res.detalle = f"gemelo de {g.get('eps', mision.datos['eps'])}"


# ─── Indicadores obligatorios por corrida ────────────────────────────────────


def calcular_indicadores(db_path: Path, guardar: bool = True) -> dict:
    """Los 4 bloques de indicadores de la Fase 3, calculados de la última
    corrida y persistidos en la tabla `indicadores` (histórico comparable).
    Lo que no se puede medir aún queda en None con su razón."""
    con = hospiai_db.abrir(db_path)
    try:
        ultima_f = con.execute(
            "SELECT id, iniciada, terminada FROM corridas ORDER BY id DESC LIMIT 1"
        ).fetchone()
        ultima = ultima_f["id"] if ultima_f else 0
        previa = con.execute(
            "SELECT id, iniciada FROM corridas WHERE id<? ORDER BY id DESC LIMIT 1", (ultima,)
        ).fetchone()
        tot = con.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(valor_total),0) v,"
            " SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas,"
            " COALESCE(SUM(CASE WHEN dictamen='LISTA' THEN valor_total END),0) v_listo"
            " FROM expedientes"
        ).fetchone()
        dictamenes = {
            r["dictamen"]: r["n"]
            for r in con.execute("SELECT dictamen, COUNT(*) n FROM expedientes GROUP BY dictamen")
        }
        recuperable = con.execute(
            "SELECT COALESCE(SUM(e.valor_total),0) v, COUNT(DISTINCT e.factura_norm) n"
            " FROM expedientes e WHERE e.dictamen<>'LISTA' AND EXISTS"
            " (SELECT 1 FROM hallazgos h WHERE h.factura_norm=e.factura_norm"
            "  AND h.corrida_id=?)",
            (ultima,),
        ).fetchone()
        transiciones = con.execute(
            "SELECT COUNT(*) n, AVG(julianday(d2.fecha)-julianday(d1.fecha)) dias"
            " FROM decisiones d1 JOIN decisiones d2 ON d2.factura_norm=d1.factura_norm"
            " AND d2.corrida_id>d1.corrida_id AND d2.dictamen='LISTA'"
            " AND d1.dictamen<>'LISTA'",
        ).fetchone()
        desde = previa["iniciada"] if previa else ""
        aprendizaje = con.execute(
            "SELECT SUM(CASE WHEN tipo='LECCION' THEN 1 ELSE 0 END) lecciones,"
            " SUM(CASE WHEN tipo='PATRON' THEN 1 ELSE 0 END) patrones"
            " FROM conocimiento WHERE actualizado>=?",
            (desde,),
        ).fetchone()
        tareas = con.execute(
            "SELECT COUNT(*) n FROM misiones WHERE tipo='TAREA_HUMANA'"
            " AND estado IN ('FINALIZADA','EJECUTANDO','ASIGNADA')"
        ).fetchone()["n"]
    finally:
        con.close()

    n = tot["n"] or 0
    seg_auditoria = None
    if ultima_f and ultima_f["terminada"] and n:
        try:
            d1 = datetime.fromisoformat(ultima_f["iniciada"])
            d2 = datetime.fromisoformat(ultima_f["terminada"])
            seg_auditoria = round((d2 - d1).total_seconds() / n, 3)
        except ValueError:
            pass
    faltan_sop = sum(v for k, v in dictamenes.items() if k.startswith(("SIN_", "FALTA")))

    def _pct(x) -> float:
        return round(100 * x / n, 1) if n else 0.0

    ind = {
        "corrida": ultima,
        "financieros": {
            "valor_listo": tot["v_listo"],
            "valor_detenido": tot["v"] - tot["v_listo"],
            "valor_recuperable": recuperable["v"],
            "valor_perdido": None,
            "nota_perdido": "requiere plazos por contrato en el catálogo (aún sin cargar)",
        },
        "operativos": {
            "seg_auditoria_por_factura": seg_auditoria,
            "dias_hasta_lista": round(transiciones["dias"], 1) if transiciones["dias"] else None,
            "casos_hasta_lista": transiciones["n"],
            "dias_hasta_radicacion": None,
            "dias_hasta_pago": None,
            "nota_pendientes": "radicación/pago se medirán con el historial cargado",
        },
        "calidad": {
            "pct_listas": _pct(tot["listas"]),
            "pct_revisar": _pct(dictamenes.get("REVISAR_TIPIFICACION", 0)),
            "pct_faltan_soportes": _pct(faltan_sop),
            "pct_entidad_no_resuelta": _pct(dictamenes.get("ENTIDAD_NO_RESUELTA", 0)),
        },
        "aprendizaje": {
            "lecciones_nuevas": aprendizaje["lecciones"] or 0,
            "patrones_nuevos": aprendizaje["patrones"] or 0,
            "recomendaciones_aceptadas": tareas,
            "recomendaciones_exitosas": None,
            "nota_exitosas": "se mide al cerrar el ciclo recomendación→corrida siguiente",
        },
        "generado": _ahora(),
    }
    if guardar and ultima:
        con = hospiai_db.abrir(db_path)
        try:
            with con:
                for cat, valores in ind.items():
                    if not isinstance(valores, dict):
                        continue
                    for nombre, valor in valores.items():
                        if nombre.startswith("nota_"):
                            continue
                        con.execute(
                            "INSERT INTO indicadores(corrida_id, categoria, nombre, valor,"
                            " texto, calculado) VALUES(?,?,?,?,?,?)"
                            " ON CONFLICT(corrida_id, nombre) DO UPDATE SET"
                            " valor=excluded.valor, calculado=excluded.calculado",
                            (
                                ultima,
                                cat,
                                nombre,
                                valor,
                                "" if valor is not None else "sin datos para medirlo aún",
                                ind["generado"],
                            ),
                        )
        finally:
            con.close()
    return ind


# ─── AG028 · Mejora Continua (cada viernes) ──────────────────────────────────


def mejora_semanal(db_path: Path, dir_indices: Path | None = None) -> dict:
    """¿Qué mejoró? ¿Qué empeoró? ¿Qué aprendimos? ¿Qué cambiamos el lunes?
    Compara las dos últimas corridas usando los Decision Records."""
    con = hospiai_db.abrir(db_path)
    try:
        corridas = [
            dict(r)
            for r in con.execute(
                "SELECT DISTINCT corrida_id FROM decisiones ORDER BY corrida_id DESC LIMIT 2"
            )
        ]
        series = {}
        for c in corridas:
            cid = c["corrida_id"]
            fila = con.execute(
                "SELECT COUNT(*) n, SUM(CASE WHEN dictamen='LISTA' THEN 1 ELSE 0 END) listas"
                " FROM decisiones WHERE corrida_id=?",
                (cid,),
            ).fetchone()
            causas = {
                r["c"]: r["n"]
                for r in con.execute(
                    "SELECT COALESCE(NULLIF(codigo,''), tipo) c, COUNT(*) n FROM hallazgos"
                    " WHERE corrida_id=? GROUP BY c",
                    (cid,),
                )
            }
            series[cid] = {"n": fila["n"], "listas": fila["listas"] or 0, "causas": causas}
        lecciones = con.execute(
            "SELECT COUNT(*) n FROM eventos WHERE tipo='APRENDIZAJE'"
        ).fetchone()["n"]
    finally:
        con.close()

    mejoro, empeoro = [], []
    if len(corridas) == 2:
        c2, c1 = corridas[0]["corrida_id"], corridas[1]["corrida_id"]
        s2, s1 = series[c2], series[c1]
        p2 = 100 * s2["listas"] / s2["n"] if s2["n"] else 0
        p1 = 100 * s1["listas"] / s1["n"] if s1["n"] else 0
        delta = round(p2 - p1, 1)
        (mejoro if delta >= 0 else empeoro).append(
            f"% LISTAS: {p1:.1f}% → {p2:.1f}% ({delta:+.1f} puntos)"
        )
        for causa in sorted(set(s1["causas"]) | set(s2["causas"])):
            d = s2["causas"].get(causa, 0) - s1["causas"].get(causa, 0)
            if d < 0:
                mejoro.append(f"{causa}: {-d:,} hallazgo(s) menos")
            elif d > 0:
                empeoro.append(f"{causa}: {d:,} hallazgo(s) más")
    nota = "" if len(corridas) == 2 else "se necesitan 2+ corridas para comparar semanas"

    from hospiai_conocimiento import MemoriaInstitucional

    memoria = MemoriaInstitucional(db_path)
    validadas = memoria.consultar()
    op = oportunidades(db_path, dir_indices)
    lunes = [
        f"{o['oportunidad']} → libera $ {o['valor_liberado']:,.0f}"
        f" ({o['facturas_liberadas']:,} facturas)"
        for o in op["oportunidades"][:3]
        if o["valor_liberado"]
    ]
    return {
        "que_mejoro": mejoro or ["sin mejoras medibles esta semana" if not nota else nota],
        "que_empeoro": empeoro or ["nada empeoró en lo medible"],
        "que_aprendimos": [
            f"{lecciones} transición(es) de dictamen registradas como aprendizaje",
            f"{len(validadas)} conocimiento(s) VALIDADO(s) disponibles para recomendar",
        ],
        "cambiar_el_lunes": lunes or ["correr la primera corrida con el índice para medir"],
        "generado": _ahora(),
    }


class AgenteMejoraContinua(Agente):
    """AG028 — Continuous Improvement Engine: el ritual del viernes."""

    id = "AG028"
    nombre = "MejoraContinua"
    dominio = "OPERACION"
    version = "1.0"
    salidas = ["mejora"]
    depende_de = ["AG008"]
    capacidades = ["MEJORA_CONTINUA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        db = Path(contexto.get("db_path") or DB_DEFAULT)
        m = mejora_semanal(db, contexto.get("dir_indices"))
        res.salida = {"mejora": m}
        res.detalle = (
            f"{len(m['que_mejoro'])} mejora(s), {len(m['que_empeoro'])} alerta(s),"
            f" {len(m['cambiar_el_lunes'])} cambio(s) para el lunes"
        )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Operational Intelligence HOSPIAI (AG024–AG028).")
    p.add_argument("--db", type=Path, default=DB_DEFAULT)
    p.add_argument("--indices", type=Path, default=None, help="Carpeta data\\indices alterna.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("indicadores", help="Calcula y guarda los indicadores de la última corrida.")
    sf = sub.add_parser("ficha", help="Ficha viva por pagador/contrato (AG026).")
    sf.add_argument("pagador", nargs="?", help="Filtro por nombre (opcional).")
    sg = sub.add_parser("gemelo", help="Gemelo digital de una EPS (AG027).")
    sg.add_argument("eps")
    sub.add_parser("mejora", help="Informe de mejora continua del viernes (AG028).")
    args = p.parse_args(argv)
    if not args.db.is_file():
        print(f"ERROR: no existe la base {args.db}. Corré primero el radicador.")
        return 1
    if args.cmd == "indicadores":
        ind = calcular_indicadores(args.db)
        print("=" * 70)
        print(f"INDICADORES · corrida #{ind['corrida']}")
        for cat in ("financieros", "operativos", "calidad", "aprendizaje"):
            print(f"  [{cat.upper()}]")
            for k, v in ind[cat].items():
                if k.startswith("nota_"):
                    continue
                if v is None:
                    print(f"    {k:<28} — (sin datos para medirlo aún)")
                elif isinstance(v, float) and k.startswith(("valor_", "seg_")):
                    print(f"    {k:<28} {v:,.1f}")
                else:
                    print(f"    {k:<28} {v:,}" if isinstance(v, int) else f"    {k:<28} {v}")
        print("=" * 70)
        return 0
    if args.cmd == "ficha":
        for f in ficha_pagador(args.db, args.pagador):
            print("-" * 70)
            print(f"  {f['pagador']}  ·  {f['expedientes']:,} exp.  ·  {f['pct_listas']}% listas")
            print(f"    valor $ {f['valor']:,.0f}   detenido $ {f['valor_detenido']:,.0f}")
            print(f"    causas frecuentes: {', '.join(f['causas_frecuentes']) or '—'}")
            print(f"    plazo: {f['plazo_dias'] or '—'} días   glosas: {f['glosas']}")
            if f["nota_historial"]:
                print(f"    ({f['nota_historial']})")
            print(f"    → {f['recomendacion']}")
        return 0
    if args.cmd == "gemelo":
        g = gemelo_eps(args.db, args.eps)
        print(json.dumps(g, ensure_ascii=False, indent=1))
        return 0
    m = mejora_semanal(args.db, args.indices)
    print("=" * 70)
    print("MEJORA CONTINUA · informe del viernes")
    for titulo, clave in (
        ("¿Qué mejoró?", "que_mejoro"),
        ("¿Qué empeoró?", "que_empeoro"),
        ("¿Qué aprendimos?", "que_aprendimos"),
        ("¿Qué cambiamos el lunes?", "cambiar_el_lunes"),
    ):
        print(f"  {titulo}")
        for linea in m[clave]:
            print(f"    · {linea}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
