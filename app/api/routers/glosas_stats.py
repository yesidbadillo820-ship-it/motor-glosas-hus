"""Estadísticas y analítica del módulo de glosas.

Extraído de glosas.py (Fase 2 — separación de dominios).
Contiene todos los endpoints /stats/* (~225 endpoints).
Se incluye en el router principal via router.include_router(stats_router).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as _f
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin, get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import (
    AuditLogRecord,
    ComentarioGlosaRecord,
    ConciliacionRecord,
    ConceptoGlosaRecord,
    DictamenVersionRecord,
    GlosaRecord,
    TarifaContratadaRecord,
    UsuarioRecord,
)

stats_router = APIRouter(tags=["estadísticas"])


@stats_router.get("/stats/por-gestor")
def stats_por_gestor(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R73 P1: productividad por gestor en la ventana indicada.

    Solo coordinador/admin (datos sensibles de equipo).

    Devuelve por gestor:
      count_glosas      glosas asignadas / creadas en la ventana
      valor_objetado    suma total
      valor_aceptado    suma aceptada
      valor_recuperado  v_obj - v_ac
      tasa_exito_pct    % defendido
      tiempo_promedio_dias_a_decision  (si hay fecha_decision_eps)

    Ordenado DESC por count_glosas.
    """

    from sqlalchemy import func as _f


    desde = ahora_utc() - timedelta(days=int(dias))

    # Agregar por auditor_email (gestor responsable)
    rows = (
        db.query(
            GlosaRecord.auditor_email,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
            _f.sum(GlosaRecord.valor_aceptado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.auditor_email.isnot(None))
        .group_by(GlosaRecord.auditor_email)
        .all()
    )

    items = []
    for email, count, v_obj, v_ac in rows:
        v_obj = float(v_obj or 0)
        v_ac = float(v_ac or 0)
        v_rec = v_obj - v_ac
        tasa = (v_rec / v_obj * 100) if v_obj > 0 else 0
        items.append(
            {
                "auditor_email": email,
                "count_glosas": int(count),
                "valor_objetado": v_obj,
                "valor_aceptado": v_ac,
                "valor_recuperado": v_rec,
                "tasa_exito_pct": round(tasa, 1),
            }
        )
    items.sort(key=lambda x: x["count_glosas"], reverse=True)

    return {
        "ventana_dias": dias,
        "total_gestores_activos": len(items),
        "items": items,
    }


@stats_router.get("/stats/anomalias")
def stats_anomalias(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R114 P1: detecta glosas con valores atípicos (outliers).

    Usa IQR (interquartile range) sobre valor_objetado:
      - Q1 = percentil 25
      - Q3 = percentil 75
      - IQR = Q3 - Q1
      - Outlier alto: valor > Q3 + 1.5 * IQR
      - Outlier bajo: valor < Q1 - 1.5 * IQR

    Útil para identificar:
      - Glosas con valores monstruosos (revisar, ¿typo?)
      - Glosas mini (¿vale la pena pelearlas?)
      - Patrones inusuales

    Devuelve estadísticas + lista de outliers (max 50).
    """
    glosas = db.query(GlosaRecord).all()
    valores = [
        (g, float(g.valor_objetado or 0))
        for g in glosas
        if g.valor_objetado and float(g.valor_objetado) > 0
    ]

    if len(valores) < 4:
        return {
            "total_glosas_evaluadas": len(valores),
            "razon": "Necesitas al menos 4 glosas con valor>0 para calcular cuartiles.",
            "outliers_altos": [],
            "outliers_bajos": [],
        }

    sorted_valores = sorted([v for _, v in valores])
    n = len(sorted_valores)
    q1 = sorted_valores[n // 4]
    q3 = sorted_valores[3 * n // 4]
    iqr = q3 - q1
    upper = q3 + 1.5 * iqr
    lower = max(0, q1 - 1.5 * iqr)

    outliers_altos = []
    outliers_bajos = []
    for g, v in valores:
        if v > upper:
            outliers_altos.append(
                {
                    "glosa_id": g.id,
                    "eps": g.eps,
                    "factura": g.factura,
                    "valor_objetado": int(v),
                    "veces_sobre_q3": round(v / q3, 2) if q3 else 0,
                }
            )
        elif v < lower:
            outliers_bajos.append(
                {
                    "glosa_id": g.id,
                    "eps": g.eps,
                    "factura": g.factura,
                    "valor_objetado": int(v),
                }
            )

    outliers_altos.sort(key=lambda x: x["valor_objetado"], reverse=True)
    outliers_bajos.sort(key=lambda x: x["valor_objetado"])

    return {
        "total_glosas_evaluadas": len(valores),
        "estadisticas": {
            "q1": int(q1),
            "q3": int(q3),
            "iqr": int(iqr),
            "limite_superior_outlier": int(upper),
            "limite_inferior_outlier": int(lower),
        },
        "total_outliers_altos": len(outliers_altos),
        "total_outliers_bajos": len(outliers_bajos),
        "outliers_altos": outliers_altos[:50],
        "outliers_bajos": outliers_bajos[:50],
    }


@stats_router.get("/stats/distribucion-riesgo")
def stats_distribucion_riesgo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R139 P1: perfil de riesgo de la cartera de glosas abiertas.

    Clasifica cada glosa abierta en una matriz 2D:
      eje 1 = urgencia (vencida / crítica / próxima / lejana)
      eje 2 = monto (alto / medio / bajo)

    Devuelve la distribución cruzada para detectar dónde se
    concentra el riesgo:
      "el 70% del valor pendiente está en glosas vencidas de
       alto monto → atención prioritaria"

    Útil para reportes ejecutivos de cartera.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    matriz = {
        "VENCIDA": {"ALTO": [], "MEDIO": [], "BAJO": []},
        "CRITICA": {"ALTO": [], "MEDIO": [], "BAJO": []},
        "PROXIMA": {"ALTO": [], "MEDIO": [], "BAJO": []},
        "LEJANA": {"ALTO": [], "MEDIO": [], "BAJO": []},
    }

    for g in glosas:
        v = float(g.valor_objetado or 0)
        dr = g.dias_restantes if g.dias_restantes is not None else 0

        if dr < 0:
            urg = "VENCIDA"
        elif dr <= 3:
            urg = "CRITICA"
        elif dr <= 7:
            urg = "PROXIMA"
        else:
            urg = "LEJANA"

        if v > 5_000_000:
            monto = "ALTO"
        elif v > 1_000_000:
            monto = "MEDIO"
        else:
            monto = "BAJO"

        matriz[urg][monto].append(v)

    items = []
    total_valor = 0.0
    for urg in ("VENCIDA", "CRITICA", "PROXIMA", "LEJANA"):
        for monto in ("ALTO", "MEDIO", "BAJO"):
            valores = matriz[urg][monto]
            count = len(valores)
            v_sum = sum(valores)
            total_valor += v_sum
            items.append(
                {
                    "urgencia": urg,
                    "monto": monto,
                    "count": count,
                    "valor_total": int(v_sum),
                }
            )

    # Calcular pct relativos
    total_count = sum(it["count"] for it in items)
    for it in items:
        it["pct_count"] = round(100 * it["count"] / total_count, 2) if total_count else 0.0
        it["pct_valor"] = round(100 * it["valor_total"] / total_valor, 2) if total_valor else 0.0

    # Ordenar por valor DESC para resaltar el riesgo concentrado
    items.sort(key=lambda x: x["valor_total"], reverse=True)

    return {
        "total_glosas_abiertas": total_count,
        "valor_pendiente_total": int(total_valor),
        "matriz": items,
    }


@stats_router.get("/stats/concentracion-pareto")
def stats_concentracion_pareto(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R113 P1: análisis Pareto (80/20) sobre EPS y valor.

    Identifica si el valor está concentrado en pocas EPS:
      - ¿Cuántas EPS aportan el 80% del valor objetado?
      - ¿Cuál es el coeficiente de Gini?

    Útil para entender la dependencia HUS-EPS:
      - Alta concentración: foco en pocas EPS clave
      - Baja concentración: gestión más distribuida

    Devuelve:
      - eps_para_80_pct: int (cuántas EPS suman 80% del valor)
      - top_eps_concentracion: serie con cumulative_pct
      - gini_coefficient: 0 (igual) ... 1 (concentración total)
    """
    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, float] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        por_eps[eps] = por_eps.get(eps, 0.0) + float(g.valor_objetado or 0)

    if not por_eps:
        return {
            "total_eps": 0,
            "valor_total": 0,
            "eps_para_80_pct": 0,
            "gini_coefficient": 0.0,
            "top_eps_concentracion": [],
        }

    valores = sorted(por_eps.values(), reverse=True)
    total = sum(valores)

    # Pareto: cuántas EPS para 80%
    acumulado = 0.0
    cuantas_para_80 = 0
    for i, v in enumerate(valores):
        acumulado += v
        if acumulado / total >= 0.80 and cuantas_para_80 == 0:
            cuantas_para_80 = i + 1
            break

    # Gini coefficient (formulación Lorenz)
    n = len(valores)
    valores_asc = sorted(valores)
    suma_pesada = sum((i + 1) * v for i, v in enumerate(valores_asc))
    gini = (2 * suma_pesada) / (n * sum(valores_asc)) - (n + 1) / n
    gini = round(gini, 4)

    # Top concentración (DESC) con cumulative_pct
    items_eps = sorted(por_eps.items(), key=lambda x: x[1], reverse=True)
    cum = 0.0
    top_concentracion = []
    for eps, v in items_eps[:20]:  # Top 20
        cum += v
        top_concentracion.append(
            {
                "eps": eps,
                "valor": int(v),
                "pct_individual": round(100 * v / total, 2),
                "pct_acumulado": round(100 * cum / total, 2),
            }
        )

    return {
        "total_eps": len(por_eps),
        "valor_total": int(total),
        "eps_para_80_pct": cuantas_para_80,
        "gini_coefficient": gini,
        "top_eps_concentracion": top_concentracion,
    }


@stats_router.get("/stats/refinaciones")
def stats_refinaciones(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R129 P2: métricas globales de refinaciones de dictámenes.

    Agregado del versionado de TODOS los dictámenes en la
    ventana. Útil para detectar si los auditores están
    "refinando demasiado" (señal de que el dictamen IA inicial
    no satisface).

    Devuelve:
      - total_acciones
      - por_accion: counts por tipo (CREAR, REFINAR, REGENERAR,
                    RESTAURAR)
      - top_5_autores: usuarios que más refinan
      - glosas_con_refinaciones (DISTINCT glosa_id)
      - promedio_versiones_por_glosa
      - tasa_refinacion_pct (REFINAR / total acciones)
    """


    desde = ahora_utc() - timedelta(days=int(dias))
    versiones = (
        db.query(DictamenVersionRecord).filter(DictamenVersionRecord.creado_en >= desde).all()
    )

    if not versiones:
        return {
            "ventana_dias": int(dias),
            "total_acciones": 0,
            "por_accion": {},
            "top_5_autores": [],
            "glosas_con_refinaciones": 0,
            "promedio_versiones_por_glosa": 0.0,
            "tasa_refinacion_pct": 0.0,
        }

    por_accion: dict[str, int] = {}
    por_autor: dict[str, int] = {}
    glosas_set: set[int] = set()
    for v in versiones:
        if v.accion:
            por_accion[v.accion] = por_accion.get(v.accion, 0) + 1
        if v.autor_email:
            por_autor[v.autor_email] = por_autor.get(v.autor_email, 0) + 1
        if v.glosa_id is not None:
            glosas_set.add(v.glosa_id)

    top_5 = sorted(
        por_autor.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    refinar = por_accion.get("REFINAR", 0)
    tasa = round(100 * refinar / len(versiones), 2)

    return {
        "ventana_dias": int(dias),
        "total_acciones": len(versiones),
        "por_accion": por_accion,
        "top_5_autores": [{"autor": u, "acciones": n} for u, n in top_5],
        "glosas_con_refinaciones": len(glosas_set),
        "promedio_versiones_por_glosa": (
            round(len(versiones) / len(glosas_set), 2) if glosas_set else 0.0
        ),
        "tasa_refinacion_pct": tasa,
    }


@stats_router.get("/stats/conciliaciones")
def stats_conciliaciones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R128 P1: métricas de conciliaciones bilaterales HUS-EPS.

    La conciliación es la última instancia antes del litigio: si
    EPS no levanta y HUS no acepta, hay audiencia bilateral con
    acta firmada.

    Útil para entender:
      - ¿Cuántas glosas terminan en conciliación?
      - ¿Cuál es el valor promedio defendido vs conciliado?
      - ¿Estados bilaterales en pipeline?

    Devuelve:
      - total_conciliaciones
      - por_resultado (mapa)
      - por_estado_bilateral (mapa)
      - valor_total_conciliado
      - valor_total_defendido_hus (valor_ratificado_hus)
      - tasa_recuperacion_conciliacion_pct
      - audiencias_proximas_30d
    """
    from datetime import timezone


    todas = db.query(ConciliacionRecord).all()

    if not todas:
        return {
            "total_conciliaciones": 0,
            "por_resultado": {},
            "por_estado_bilateral": {},
            "valor_total_conciliado": 0,
            "valor_total_defendido_hus": 0,
            "tasa_recuperacion_conciliacion_pct": 0.0,
            "audiencias_proximas_30d": 0,
        }

    por_resultado: dict[str, int] = {}
    por_estado: dict[str, int] = {}
    valor_conc = 0.0
    valor_def = 0.0

    ahora = ahora_utc()
    en_30d = ahora + timedelta(days=30)
    audiencias_proximas = 0

    for c in todas:
        if c.resultado:
            por_resultado[c.resultado] = por_resultado.get(c.resultado, 0) + 1
        eb = c.estado_bilateral or "?"
        por_estado[eb] = por_estado.get(eb, 0) + 1
        valor_conc += float(c.valor_conciliado or 0)
        valor_def += float(c.valor_ratificado_hus or 0)

        fa = c.fecha_audiencia
        if fa and fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        if fa and ahora <= fa <= en_30d:
            audiencias_proximas += 1

    tasa = round(100 * valor_conc / valor_def, 2) if valor_def else 0.0

    return {
        "total_conciliaciones": len(todas),
        "por_resultado": por_resultado,
        "por_estado_bilateral": por_estado,
        "valor_total_conciliado": int(valor_conc),
        "valor_total_defendido_hus": int(valor_def),
        "tasa_recuperacion_conciliacion_pct": tasa,
        "audiencias_proximas_30d": audiencias_proximas,
    }


@stats_router.get("/stats/serie-mensual-cantidad")
def stats_serie_mensual_cantidad(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R124 P2: serie temporal mensual con creadas Y cerradas.

    Diferente a /stats/recuperacion-mensual (solo valor) y
    /stats/cohorte-mensual (% cierre por cohorte de creación):
    aquí se muestra el flujo entrante vs saliente del backlog.

    Útil para gráficos de doble línea:
      - Línea 1: glosas creadas en el mes
      - Línea 2: glosas cerradas en el mes
      - Si línea 1 > línea 2 sostenidamente → backlog crece

    Devuelve serie ascendente:
      [{"mes": "2026-04", "creadas": 50, "cerradas": 35,
        "delta_neto": 15, "ratio_cierre": 0.7}, ...]
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()

    creadas_mes: dict[str, int] = {}
    cerradas_mes: dict[str, int] = {}

    for g in glosas:
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        if creado:
            k = creado.strftime("%Y-%m")
            creadas_mes[k] = creadas_mes.get(k, 0) + 1

        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if dec and (g.estado or "").upper() in ESTADOS_CERRADOS:
            k = dec.strftime("%Y-%m")
            cerradas_mes[k] = cerradas_mes.get(k, 0) + 1

    todos_meses = sorted(set(creadas_mes.keys()) | set(cerradas_mes.keys()))
    meses_recientes = todos_meses[-int(meses) :]

    serie = []
    for k in meses_recientes:
        c = creadas_mes.get(k, 0)
        cer = cerradas_mes.get(k, 0)
        ratio = round(cer / c, 2) if c else None
        serie.append(
            {
                "mes": k,
                "creadas": c,
                "cerradas": cer,
                "delta_neto": c - cer,
                "ratio_cierre": ratio,
            }
        )

    return {
        "meses_solicitados": int(meses),
        "total_meses_disponibles": len(todos_meses),
        "serie": serie,
    }


@stats_router.get("/stats/facturas-hot")
def stats_facturas_hot(
    min_glosas: int = Query(3, ge=2, le=20),
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R124 P1: facturas con múltiples glosas asociadas.

    "Hot facturas" = facturas con N+ glosas distintas. Indican:
      - Servicio/episodio complejo bajo objeción múltiple
      - Posible glosa fraccionada (mala práctica EPS)
      - Caso de litigio prioritario

    Devuelve top N facturas con >= min_glosas:
      - factura, eps
      - count_glosas
      - valor_objetado_total
      - estados (mapa estado→count)
      - codigos_distintos
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "N/A")
        .all()
    )

    por_factura: dict[str, dict] = {}
    for g in glosas:
        f = g.factura
        if f not in por_factura:
            por_factura[f] = {
                "eps": g.eps,
                "count": 0,
                "valor_objetado": 0.0,
                "estados": {},
                "codigos": set(),
            }
        b = por_factura[f]
        b["count"] += 1
        b["valor_objetado"] += float(g.valor_objetado or 0)
        estado = g.estado or "?"
        b["estados"][estado] = b["estados"].get(estado, 0) + 1
        if g.codigo_glosa:
            b["codigos"].add(g.codigo_glosa)

    items = []
    for f, b in por_factura.items():
        if b["count"] < min_glosas:
            continue
        items.append(
            {
                "factura": f,
                "eps": b["eps"],
                "count_glosas": b["count"],
                "valor_objetado_total": int(b["valor_objetado"]),
                "estados": b["estados"],
                "codigos_distintos": sorted(b["codigos"]),
            }
        )
    items.sort(key=lambda x: x["count_glosas"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_facturas_calientes": len(items),
        "items": items[:top],
    }


@stats_router.get("/stats/cobranza-por-eps")
def stats_cobranza_por_eps(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R122 P2: ranking de EPS por valor pendiente de cobro.

    Cruza /stats/cobranza-pendiente (global) con la EPS deudora
    para identificar contra quién hay más plata por defender:
      "$50M pendientes de SANITAS, $30M de NUEVA EPS, ..."

    Devuelve top N EPS ordenadas DESC por valor_pendiente con:
      - count_pendientes
      - valor_pendiente (sum de valor_objetado en abiertas)
      - valor_recuperable_estimado (con tasa histórica de la EPS)
      - tasa_historica_recuperacion_pct
      - antiguedad_promedio_dias
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ahora = ahora_utc()

    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {
                "pendiente_count": 0,
                "pendiente_valor": 0.0,
                "antiguedades": [],
                "cerradas_obj": 0.0,
                "cerradas_rec": 0.0,
            }
        b = por_eps[eps]
        v = float(g.valor_objetado or 0)
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            b["cerradas_obj"] += v
            b["cerradas_rec"] += float(g.valor_recuperado or 0)
        else:
            b["pendiente_count"] += 1
            b["pendiente_valor"] += v
            creado = g.creado_en
            if creado and creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            if creado:
                b["antiguedades"].append((ahora - creado).days)

    items = []
    for eps, b in por_eps.items():
        if b["pendiente_count"] == 0:
            continue
        tasa_hist = (
            round(100 * b["cerradas_rec"] / b["cerradas_obj"], 2) if b["cerradas_obj"] else 0.0
        )
        recuperable = b["pendiente_valor"] * (tasa_hist / 100)
        antig_prom = (
            round(sum(b["antiguedades"]) / len(b["antiguedades"]), 1) if b["antiguedades"] else 0.0
        )
        items.append(
            {
                "eps": eps,
                "count_pendientes": b["pendiente_count"],
                "valor_pendiente": int(b["pendiente_valor"]),
                "tasa_historica_recuperacion_pct": tasa_hist,
                "valor_recuperable_estimado": int(recuperable),
                "antiguedad_promedio_dias": antig_prom,
            }
        )
    items.sort(key=lambda x: x["valor_pendiente"], reverse=True)

    return {
        "top_solicitado": int(top),
        "total_eps_con_pendientes": len(items),
        "valor_pendiente_global": sum(it["valor_pendiente"] for it in items),
        "items": items[:top],
    }


@stats_router.get("/stats/cobranza-pendiente")
def stats_cobranza_pendiente(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R120 P2: valor pendiente de cobro segmentado por antigüedad.

    Complementa /stats/proyeccion-recuperacion (forecast global) con
    desglose por buckets de antigüedad — útil para priorizar
    cobranza:
      - <30d: cobranza temprana, alta probabilidad
      - 30-60d: cobranza estándar
      - 60-90d: cobranza tardía, alerta amarilla
      - >90d: cobranza dudosa, alerta roja

    Solo cuenta glosas no-cerradas con valor_objetado > 0.

    Devuelve por bucket:
      - count, valor_pendiente
      - pct_count y pct_valor
      - tasa_recuperacion_historica_pct (estimada del histórico)
      - valor_recuperable_estimado
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    BUCKETS = [
        ("<30d", 0, 30),
        ("30-60d", 30, 60),
        ("60-90d", 60, 90),
        (">90d", 90, None),
    ]

    ahora = ahora_utc()
    glosas = db.query(GlosaRecord).all()

    # Tasa histórica global para extrapolar
    cerradas_obj = 0.0
    cerradas_rec = 0.0
    pendientes = []
    for g in glosas:
        v = float(g.valor_objetado or 0)
        if v <= 0:
            continue
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            cerradas_obj += v
            cerradas_rec += float(g.valor_recuperado or 0)
        else:
            creado = g.creado_en
            if creado and creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            antig = (ahora - creado).days if creado else 0
            pendientes.append((antig, v))

    tasa_historica = round(100 * cerradas_rec / cerradas_obj, 2) if cerradas_obj else 0.0

    total_count = len(pendientes)
    total_valor = sum(v for _, v in pendientes)

    items = []
    for nombre, lo, hi in BUCKETS:
        en_bucket = [(a, v) for a, v in pendientes if a >= lo and (hi is None or a < hi)]
        n = len(en_bucket)
        v_sum = sum(v for _, v in en_bucket)
        recuperable = v_sum * (tasa_historica / 100)
        items.append(
            {
                "rango_antiguedad": nombre,
                "antiguedad_min_dias": lo,
                "antiguedad_max_dias": hi,
                "count": n,
                "valor_pendiente": int(v_sum),
                "pct_count": round(100 * n / total_count, 2) if total_count else 0.0,
                "pct_valor": round(100 * v_sum / total_valor, 2) if total_valor else 0.0,
                "valor_recuperable_estimado": int(recuperable),
            }
        )

    return {
        "tasa_historica_recuperacion_pct": tasa_historica,
        "total_pendientes": total_count,
        "valor_pendiente_total": int(total_valor),
        "valor_recuperable_estimado_total": int(
            total_valor * (tasa_historica / 100),
        ),
        "buckets": items,
    }


@stats_router.get("/stats/eps-emergentes")
def stats_eps_emergentes(
    dias: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R120 P1: detecta EPS que aparecen como nuevas en el período.

    Una EPS es "emergente" si:
      - Tiene glosas creadas en los últimos N días
      - NO tenía glosas en el histórico previo

    Útil para alertar al coordinador:
      "¡Aparece una nueva EPS en el sistema! Verificar contrato."

    Devuelve:
      - eps_nuevas: lista de EPS emergentes con count y valor
      - eps_continuas: count de EPS que vienen del histórico
    """
    from datetime import timezone

    ahora = ahora_utc()
    corte = ahora - timedelta(days=int(dias))

    eps_recientes: dict[str, dict] = {}
    eps_historicas: set[str] = set()

    for g in db.query(GlosaRecord).all():
        eps = (g.eps or "").strip()
        if not eps:
            continue
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)

        if creado and creado >= corte:
            if eps not in eps_recientes:
                eps_recientes[eps] = {
                    "count": 0,
                    "valor_objetado": 0.0,
                    "primer_visto": None,
                }
            b = eps_recientes[eps]
            b["count"] += 1
            b["valor_objetado"] += float(g.valor_objetado or 0)
            if b["primer_visto"] is None or creado < b["primer_visto"]:
                b["primer_visto"] = creado
        elif creado:
            eps_historicas.add(eps)

    nuevas = []
    continuas = 0
    for eps, b in eps_recientes.items():
        if eps in eps_historicas:
            continuas += 1
            continue
        nuevas.append(
            {
                "eps": eps,
                "glosas_recientes": b["count"],
                "valor_objetado_total": int(b["valor_objetado"]),
                "primer_glosa_en": (b["primer_visto"].isoformat() if b["primer_visto"] else None),
            }
        )

    nuevas.sort(key=lambda x: x["glosas_recientes"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "total_eps_nuevas": len(nuevas),
        "total_eps_continuas": continuas,
        "items": nuevas,
    }


@stats_router.get("/stats/estatus-eps")
def stats_estatus_eps(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R137 P2: estado consolidado por EPS con semáforo.

    Para cada EPS calcula un estatus VERDE/AMARILLO/ROJO basado
    en señales agregadas:
      - ROJO: 15+ vencidas O (tasa_lev<30% con >=5 decididas)
      - AMARILLO: 5+ vencidas O tasa_lev<60% con >=5 decididas
      - VERDE: el resto

    Útil como vista resumen rápida: "¿con qué EPS estamos
    teniendo problemas?"

    Devuelve por EPS: status, razones (lista), + métricas detalladas.
    Items ordenados ROJO → AMARILLO → VERDE.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {
                "total": 0,
                "decididas": 0,
                "levantadas": 0,
                "vencidas": 0,
                "criticas": 0,
            }
        b = por_eps[eps]
        b["total"] += 1
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            if estado in {"LEVANTADA", "ACEPTADA"}:
                b["decididas"] += 1
                if estado == "LEVANTADA":
                    b["levantadas"] += 1
        else:
            dr = g.dias_restantes if g.dias_restantes is not None else 0
            if dr < 0:
                b["vencidas"] += 1
            elif dr <= 3:
                b["criticas"] += 1

    items = []
    for eps, b in por_eps.items():
        tasa = round(100 * b["levantadas"] / b["decididas"], 2) if b["decididas"] else 0.0
        razones = []
        if b["vencidas"] > 15:
            status = "ROJO"
            razones.append(f"{b['vencidas']} glosas vencidas")
        elif tasa < 30 and b["decididas"] >= 5:
            status = "ROJO"
            razones.append(f"tasa_levantamiento_pct={tasa} muy baja")
        elif b["vencidas"] > 5 or (tasa < 60 and b["decididas"] >= 5):
            status = "AMARILLO"
            if b["vencidas"] > 5:
                razones.append(f"{b['vencidas']} vencidas")
            if tasa < 60 and b["decididas"] >= 5:
                razones.append(f"tasa_levantamiento_pct={tasa} bajo target")
        else:
            status = "VERDE"
            razones.append("operación saludable")

        items.append(
            {
                "eps": eps,
                "status": status,
                "razones": razones,
                "total_glosas": b["total"],
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "vencidas": b["vencidas"],
                "criticas": b["criticas"],
                "tasa_levantamiento_pct": tasa,
            }
        )

    orden_status = {"ROJO": 0, "AMARILLO": 1, "VERDE": 2}
    items.sort(key=lambda x: (orden_status[x["status"]], x["eps"]))

    counts = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0}
    for it in items:
        counts[it["status"]] += 1

    return {
        "total_eps": len(items),
        "por_status": counts,
        "items": items,
    }


@stats_router.get("/stats/comparativa-eps")
def stats_comparativa_eps(
    min_glosas: int = Query(5, ge=1, le=100, description="Mínimo de glosas para incluir EPS"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R90 P2: ranking comparativo de EPS por desempeño.

    Desde la perspectiva del HUS (IPS):
      - LEVANTADA = HUS defendió con éxito (HUS recupera el valor)
      - ACEPTADA = HUS aceptó la glosa (EPS no paga)
      - RATIFICADA = EPS sostuvo la glosa
      - CONCILIADA = acuerdo intermedio

    "Mejor EPS" desde HUS = mayor tasa de levantamiento (HUS le gana
    más casos a esa EPS), porque indica que la EPS objeta cosas que
    no debería y HUS las defiende bien.

    Devuelve por EPS (filtradas por min_glosas):
      - total_glosas
      - levantadas / aceptadas / ratificadas / pendientes
      - tasa_levantamiento_pct
      - valor_objetado_total
      - valor_recuperado_total
      - tiempo_promedio_decision_dias
    Ordenado DESC por tasa_levantamiento_pct.
    """
    todas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in todas:
        eps = (g.eps or "SIN_EPS").strip()
        if eps not in por_eps:
            por_eps[eps] = {
                "total": 0,
                "levantadas": 0,
                "aceptadas": 0,
                "ratificadas": 0,
                "pendientes": 0,
                "valor_objetado": 0.0,
                "valor_recuperado": 0.0,
                "tiempos": [],
            }
        b = por_eps[eps]
        b["total"] += 1
        b["valor_objetado"] += float(g.valor_objetado or 0)
        b["valor_recuperado"] += float(g.valor_recuperado or 0)

        estado = (g.estado or "").upper()
        if estado == "LEVANTADA":
            b["levantadas"] += 1
        elif estado == "ACEPTADA":
            b["aceptadas"] += 1
        elif estado == "RATIFICADA":
            b["ratificadas"] += 1
        else:
            b["pendientes"] += 1

        if g.fecha_decision_eps and g.creado_en:
            delta = (g.fecha_decision_eps - g.creado_en).total_seconds() / 86400
            b["tiempos"].append(delta)

    items = []
    for eps, b in por_eps.items():
        if b["total"] < min_glosas:
            continue
        decididas = b["levantadas"] + b["aceptadas"] + b["ratificadas"]
        tasa = round(100 * b["levantadas"] / decididas, 2) if decididas else 0.0
        tiempo_prom = round(sum(b["tiempos"]) / len(b["tiempos"]), 2) if b["tiempos"] else 0.0
        items.append(
            {
                "eps": eps,
                "total_glosas": b["total"],
                "levantadas": b["levantadas"],
                "aceptadas": b["aceptadas"],
                "ratificadas": b["ratificadas"],
                "pendientes": b["pendientes"],
                "tasa_levantamiento_pct": tasa,
                "valor_objetado_total": int(b["valor_objetado"]),
                "valor_recuperado_total": int(b["valor_recuperado"]),
                "tiempo_promedio_decision_dias": tiempo_prom,
            }
        )

    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps_evaluadas": len(items),
        "items": items,
    }


@stats_router.get("/stats/cumplimiento-sla")
def stats_cumplimiento_sla(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R90 P1: cumplimiento de SLA agregado para dashboard ejecutivo.

    Resolución 2284/2023 fija términos máximos para cada etapa del
    ciclo glosa→respuesta→ratificación→conciliación. Este endpoint
    agrega el estado actual de la cartera de glosas frente a esos
    plazos.

    Devuelve:
      {
        "total": int,
        "vencidas": int,           # dias_restantes < 0 y no cerradas
        "criticas": int,           # 0 <= dias_restantes <= 3
        "en_tiempo": int,          # dias_restantes > 3
        "cerradas": int,           # estado in cerrados
        "tasa_cumplimiento_pct": float,  # cerradas a_tiempo / cerradas
        "tiempo_promedio_resolucion_dias": float,
        "valor_en_riesgo": int,    # suma valor_objetado de vencidas+críticas
      }
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas = db.query(GlosaRecord).all()
    total = len(todas)

    vencidas = 0
    criticas = 0
    en_tiempo = 0
    cerradas = 0
    cerradas_a_tiempo = 0
    tiempos_resolucion: list[float] = []
    valor_en_riesgo = 0.0

    for g in todas:
        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            cerradas += 1
            if g.fecha_decision_eps and g.fecha_vencimiento:
                if g.fecha_decision_eps <= g.fecha_vencimiento:
                    cerradas_a_tiempo += 1
            if g.fecha_decision_eps and g.creado_en:
                delta = (g.fecha_decision_eps - g.creado_en).total_seconds() / 86400
                tiempos_resolucion.append(delta)
            continue

        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            vencidas += 1
            valor_en_riesgo += float(g.valor_objetado or 0)
        elif dr <= 3:
            criticas += 1
            valor_en_riesgo += float(g.valor_objetado or 0)
        else:
            en_tiempo += 1

    tasa = round(100 * cerradas_a_tiempo / cerradas, 2) if cerradas else 0.0
    tiempo_promedio = (
        round(sum(tiempos_resolucion) / len(tiempos_resolucion), 2) if tiempos_resolucion else 0.0
    )

    return {
        "total": total,
        "vencidas": vencidas,
        "criticas": criticas,
        "en_tiempo": en_tiempo,
        "cerradas": cerradas,
        "cerradas_a_tiempo": cerradas_a_tiempo,
        "tasa_cumplimiento_pct": tasa,
        "tiempo_promedio_resolucion_dias": tiempo_promedio,
        "valor_en_riesgo": int(valor_en_riesgo),
    }


@stats_router.get("/stats/distribucion-valores")
def stats_distribucion_valores(
    dias: int = Query(180, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R89 P2: histograma del valor_objetado de las glosas.

    Útil para entender la distribución económica de las glosas
    (¿son mayoría < 100k pero pocas > 10M concentran el valor?).

    Buckets en COP, pensados para el rango típico HUS:
      - <100k, 100k-500k, 500k-1M, 1M-5M, 5M-10M, 10M-50M, 50M+

    Devuelve:
      {
        "ventana_dias": 180,
        "total_glosas": int,
        "valor_total": int,           # suma COP
        "valor_promedio": float,
        "valor_mediano": float,
        "buckets": [
          {"rango": "<100k", "min": 0, "max": 100000,
           "count": int, "valor": int, "pct_count": float, "pct_valor": float},
          ...
        ]
      }
    """

    BUCKETS = [
        ("<100k", 0, 100_000),
        ("100k-500k", 100_000, 500_000),
        ("500k-1M", 500_000, 1_000_000),
        ("1M-5M", 1_000_000, 5_000_000),
        ("5M-10M", 5_000_000, 10_000_000),
        ("10M-50M", 10_000_000, 50_000_000),
        ("50M+", 50_000_000, None),
    ]

    corte = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(GlosaRecord.valor_objetado)
        .filter(GlosaRecord.creado_en >= corte)
        .filter(GlosaRecord.valor_objetado.isnot(None))
        .all()
    )

    valores = [float(v[0] or 0) for v in rows]
    total_glosas = len(valores)
    valor_total = sum(valores)

    # Mediana
    if valores:
        ordenado = sorted(valores)
        mid = total_glosas // 2
        if total_glosas % 2 == 0:
            valor_mediano = (ordenado[mid - 1] + ordenado[mid]) / 2
        else:
            valor_mediano = ordenado[mid]
    else:
        valor_mediano = 0.0

    # Distribución por bucket
    buckets_out = []
    for nombre, lo, hi in BUCKETS:
        en_bucket = [v for v in valores if v >= lo and (hi is None or v < hi)]
        n = len(en_bucket)
        v_sum = sum(en_bucket)
        buckets_out.append(
            {
                "rango": nombre,
                "min": lo,
                "max": hi,
                "count": n,
                "valor": int(v_sum),
                "pct_count": round(100 * n / total_glosas, 2) if total_glosas else 0.0,
                "pct_valor": round(100 * v_sum / valor_total, 2) if valor_total else 0.0,
            }
        )

    return {
        "ventana_dias": int(dias),
        "total_glosas": total_glosas,
        "valor_total": int(valor_total),
        "valor_promedio": round(valor_total / total_glosas, 2) if total_glosas else 0.0,
        "valor_mediano": round(valor_mediano, 2),
        "buckets": buckets_out,
    }


@stats_router.get("/stats/comparar-periodos")
def stats_comparar_periodos(
    dias: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R118 P1: compara métricas del período actual vs anterior.

    Útil para reportes "vs mes pasado":
      - "Este mes creamos 50 glosas; el mes pasado fueron 40
        → +25%"
      - "Recuperamos $5M vs $3M → +66%"

    Devuelve métricas de ambos períodos + delta absoluto y %:
      - glosas_creadas
      - glosas_cerradas
      - valor_recuperado
      - tiempo_promedio_resolucion_dias

    Período actual = últimos N días.
    Período previo = los N días anteriores a esos.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    ahora = ahora_utc()
    hoy_inicio = ahora - timedelta(days=int(dias))
    prev_inicio = hoy_inicio - timedelta(days=int(dias))

    todas = db.query(GlosaRecord).all()

    def _stats(desde, hasta):
        creadas = 0
        cerradas = 0
        valor_rec = 0.0
        tiempos = []
        for g in todas:
            creado = g.creado_en
            if creado and creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            dec = g.fecha_decision_eps
            if dec and dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)

            if creado and desde <= creado < hasta:
                creadas += 1

            if dec and desde <= dec < hasta and (g.estado or "").upper() in ESTADOS_CERRADOS:
                cerradas += 1
                valor_rec += float(g.valor_recuperado or 0)
                if creado:
                    tiempos.append((dec - creado).days)

        return {
            "glosas_creadas": creadas,
            "glosas_cerradas": cerradas,
            "valor_recuperado": int(valor_rec),
            "tiempo_promedio_resolucion_dias": (
                round(sum(tiempos) / len(tiempos), 2) if tiempos else 0.0
            ),
        }

    actual = _stats(hoy_inicio, ahora)
    previo = _stats(prev_inicio, hoy_inicio)

    def _delta(a, p):
        diff = a - p
        pct = round(100 * diff / p, 2) if p else None
        return {"absoluto": diff, "pct": pct}

    deltas = {k: _delta(actual[k], previo[k]) for k in actual.keys()}

    return {
        "ventana_dias": int(dias),
        "periodo_actual": {
            "desde": hoy_inicio.isoformat(),
            "hasta": ahora.isoformat(),
            **actual,
        },
        "periodo_previo": {
            "desde": prev_inicio.isoformat(),
            "hasta": hoy_inicio.isoformat(),
            **previo,
        },
        "deltas": deltas,
    }


@stats_router.get("/stats/forecast-cierres")
def stats_forecast_cierres(
    semanas: int = Query(8, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R115 P2: proyección de cierres en las próximas N semanas.

    Basado en velocidad_diaria_promedio_30d (de R115 P1) extrapolado
    a futuro. Modelo simple: lineal, asume velocidad estable.

    Útil para gráficos de proyección "burndown" del backlog:
      - ¿Cuándo terminamos de cerrar las 500 pendientes?
      - ¿La velocidad actual alcanza para el deadline?

    Devuelve serie semanal:
      [{"semana": "2026-W18", "cierres_estimados": 35,
        "pendientes_restantes_estimados": 465}, ...]
    """

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    ahora = ahora_utc()
    desde_30 = ahora - timedelta(days=30)

    cerradas_30d = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .filter(GlosaRecord.fecha_decision_eps >= desde_30)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .count()
    )
    velocidad_diaria = cerradas_30d / 30 if cerradas_30d else 0
    velocidad_semanal = velocidad_diaria * 7

    pendientes_actuales = (
        db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).count()
    )

    serie = []
    pendientes = pendientes_actuales
    for w in range(1, int(semanas) + 1):
        cierres = min(int(velocidad_semanal), pendientes)
        pendientes -= cierres
        fecha = ahora + timedelta(weeks=w)
        serie.append(
            {
                "semana": f"{fecha.year}-W{fecha.isocalendar()[1]:02d}",
                "cierres_estimados": cierres,
                "pendientes_restantes_estimados": max(0, pendientes),
            }
        )
        if pendientes <= 0:
            break

    return {
        "semanas_solicitadas": int(semanas),
        "velocidad_semanal_actual": round(velocidad_semanal, 2),
        "pendientes_inicial": pendientes_actuales,
        "serie": serie,
    }


@stats_router.get("/stats/velocidad-equipo")
def stats_velocidad_equipo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R115 P1: throughput del equipo (glosas cerradas por período).

    Mide la velocidad de cierre del equipo, útil para:
      - Capacity planning ("¿podemos cerrar las 500 pendientes en
        un mes con la velocidad actual?")
      - Detectar caídas de productividad
      - Trends semana-a-semana

    Devuelve:
      - cerradas_ultimos_7d / 30d / 90d (counts)
      - velocidad_diaria_promedio_30d
      - dias_para_cerrar_pendientes (estimado)
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    ahora = ahora_utc()

    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    cerradas_7d = 0
    cerradas_30d = 0
    cerradas_90d = 0
    for g in cerradas:
        dec = g.fecha_decision_eps
        if dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        delta = (ahora - dec).days
        if delta <= 7:
            cerradas_7d += 1
        if delta <= 30:
            cerradas_30d += 1
        if delta <= 90:
            cerradas_90d += 1

    pendientes = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).count()

    velocidad_diaria_30d = round(cerradas_30d / 30, 2)
    dias_para_cerrar = (
        round(pendientes / velocidad_diaria_30d, 1) if velocidad_diaria_30d > 0 else None
    )

    return {
        "ahora": ahora.isoformat(),
        "cerradas_ultimos_7d": cerradas_7d,
        "cerradas_ultimos_30d": cerradas_30d,
        "cerradas_ultimos_90d": cerradas_90d,
        "velocidad_diaria_promedio_30d": velocidad_diaria_30d,
        "pendientes_actuales": pendientes,
        "dias_estimados_cerrar_pendientes": dias_para_cerrar,
    }


@stats_router.get("/stats/desempeno-trimestral")
def stats_desempeno_trimestral(
    trimestres: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R109 P1: evolución del desempeño HUS por trimestre.

    Útil para informe ejecutivo periódico: ¿estamos mejorando?
    Cada trimestre devuelve:
      - total_glosas (creadas en el trimestre)
      - decididas / pendientes
      - tasa_levantamiento_pct
      - valor_objetado_total / valor_recuperado_total
      - tasa_recuperacion_pct

    Útil para gráficos de evolución (línea trimestre-a-trimestre).
    Trimestre se calcula con ((mes-1)//3 + 1) → Q1, Q2, Q3, Q4.
    """
    from datetime import timezone

    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).all()

    por_trim: dict[str, dict] = {}
    for g in glosas:
        if not g.creado_en:
            continue
        creado = g.creado_en
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        anio = creado.year
        trim = (creado.month - 1) // 3 + 1
        key = f"{anio}-Q{trim}"

        if key not in por_trim:
            por_trim[key] = {
                "total": 0,
                "decididas": 0,
                "levantadas": 0,
                "valor_obj": 0.0,
                "valor_rec": 0.0,
            }
        b = por_trim[key]
        b["total"] += 1
        b["valor_obj"] += float(g.valor_objetado or 0)
        b["valor_rec"] += float(g.valor_recuperado or 0)

        estado = (g.estado or "").upper()
        if estado in ESTADOS_DECIDIDOS:
            b["decididas"] += 1
            if estado == "LEVANTADA":
                b["levantadas"] += 1

    # Ordenar por trimestre y limitar a últimos N
    keys_ordenados = sorted(por_trim.keys())
    keys_recientes = keys_ordenados[-int(trimestres) :]

    serie = []
    for key in keys_recientes:
        b = por_trim[key]
        tasa_lev = round(100 * b["levantadas"] / b["decididas"], 2) if b["decididas"] else 0.0
        tasa_rec = round(100 * b["valor_rec"] / b["valor_obj"], 2) if b["valor_obj"] else 0.0
        serie.append(
            {
                "trimestre": key,
                "total_glosas": b["total"],
                "decididas": b["decididas"],
                "pendientes": b["total"] - b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa_lev,
                "valor_objetado_total": int(b["valor_obj"]),
                "valor_recuperado_total": int(b["valor_rec"]),
                "tasa_recuperacion_pct": tasa_rec,
            }
        )

    return {
        "trimestres_solicitados": int(trimestres),
        "total_trimestres_disponibles": len(por_trim),
        "serie": serie,
    }


@stats_router.get("/stats/picos-historicos")
def stats_picos_historicos(
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R104 P2: top N días con más glosas creadas (picos de carga).

    Útil para:
      - Identificar fechas de "embotellamiento" históricas
      - Correlacionar con eventos externos (cargas masivas EPS,
        cambios normativos, fin de mes)
      - Planeación: "los días X-Y de cada mes pico hay alta carga"

    Devuelve top N días ordenados DESC por glosas creadas:
      [{"fecha": "2026-04-15", "glosas": 47, "valor_total": 8500000}, ...]
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).all()

    por_dia: dict[str, dict] = {}
    for g in glosas:
        if not g.creado_en:
            continue
        creado = g.creado_en
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        key = creado.date().isoformat()
        if key not in por_dia:
            por_dia[key] = {"glosas": 0, "valor": 0.0}
        por_dia[key]["glosas"] += 1
        por_dia[key]["valor"] += float(g.valor_objetado or 0)

    items = [
        {
            "fecha": k,
            "glosas": v["glosas"],
            "valor_total": int(v["valor"]),
        }
        for k, v in por_dia.items()
    ]
    items.sort(key=lambda x: x["glosas"], reverse=True)

    return {
        "top_solicitado": int(top),
        "total_dias_con_actividad": len(items),
        "items": items[:top],
    }


@stats_router.get("/stats/valor-eficiencia-anual")
def stats_valor_eficiencia_anual(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r"""R210 P1: serie anual de valor objetado vs recuperado.

    Vista comparativa para reportes anuales:
      "En 2025 se objetaron \$10B y recuperamos \$5B (50%
       efectividad económica)"

    Por año:
      - valor_objetado_total
      - valor_recuperado_total
      - eficiencia_pct (recuperado / objetado)
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).all()

    por_anio: dict[str, dict] = {}
    for g in glosas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = str(cre.year)
        if k not in por_anio:
            por_anio[k] = {"obj": 0.0, "rec": 0.0}
        por_anio[k]["obj"] += float(g.valor_objetado or 0)
        por_anio[k]["rec"] += float(g.valor_recuperado or 0)

    serie = []
    for k in sorted(por_anio.keys()):
        b = por_anio[k]
        eff = round(100 * b["rec"] / b["obj"], 2) if b["obj"] else 0.0
        serie.append(
            {
                "anio": k,
                "valor_objetado": int(b["obj"]),
                "valor_recuperado": int(b["rec"]),
                "eficiencia_pct": eff,
            }
        )

    return {"serie": serie}


@stats_router.get("/stats/criticas-economicas")
def stats_criticas_economicas(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R201 P1: top glosas con MAYOR valor + MENOR dias_restantes.

    Combina urgencia + cuantía con score:
      score = valor_objetado / max(1, dias_restantes + 30)
      (más alto = más prioritaria)

    Útil para que el coordinador atienda primero las glosas
    "donde se queman millones de pesos por hora".

    Solo abiertas, ordenado DESC por score.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    items = []
    for g in abiertas:
        valor = float(g.valor_objetado or 0)
        if valor <= 0:
            continue
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        score = valor / max(1, dr + 30)
        items.append(
            {
                "id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "valor_objetado": valor,
                "dias_restantes": dr,
                "score_urgencia_economica": round(score, 2),
            }
        )
    items.sort(
        key=lambda x: x["score_urgencia_economica"],
        reverse=True,
    )

    return {
        "top_solicitado": int(top),
        "items": items[: int(top)],
    }


@stats_router.get("/stats/proceso-bilateral")
def stats_proceso_bilateral(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R197 P1: estado del proceso bilateral HUS-EPS.

    Muestra el funnel completo del proceso:
      RADICADA → RESPONDIDA → RATIFICADA → CONCILIADA →
      LEVANTADA / ACEPTADA / ARCHIVADA

    Para cada estado: count + valor pendiente.

    Útil para visualizar el embudo y dónde se pierde más valor.
    """
    glosas = db.query(GlosaRecord).all()

    ESTADOS_PIPELINE = [
        "RADICADA",
        "RESPONDIDA",
        "RATIFICADA",
        "CONCILIADA",
        "LEVANTADA",
        "ACEPTADA",
        "ARCHIVADA",
        "EXTEMPORANEA",
    ]
    por_estado: dict[str, dict] = {e: {"count": 0, "valor": 0.0} for e in ESTADOS_PIPELINE}

    for g in glosas:
        e = (g.estado or "").upper().strip() or "(SIN_ESTADO)"
        if e in por_estado:
            por_estado[e]["count"] += 1
            por_estado[e]["valor"] += float(g.valor_objetado or 0)

    items = []
    for e in ESTADOS_PIPELINE:
        b = por_estado[e]
        items.append(
            {
                "estado": e,
                "count": b["count"],
                "valor": int(b["valor"]),
            }
        )

    total = sum(it["count"] for it in items)

    return {
        "total_glosas": total,
        "pipeline": items,
    }


@stats_router.get("/stats/mas-comentadas")
def stats_mas_comentadas(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R196 P1: glosas con más comentarios entre auditores.

    Indicador de glosas "complejas" o "controvertidas" — donde
    el equipo tuvo que discutir mucho.

    Útil para:
      - Identificar casos para training
      - Detectar discusiones interminables que necesitan
        decisión gerencial

    Devuelve top N glosas ordenado DESC por número de
    comentarios.
    """


    rows = (
        db.query(
            ComentarioGlosaRecord.glosa_id,
            _f.count().label("n_coms"),
        )
        .filter(ComentarioGlosaRecord.glosa_id.isnot(None))
        .group_by(ComentarioGlosaRecord.glosa_id)
        .order_by(_f.count().desc())
        .limit(int(top))
        .all()
    )

    items = []
    for glosa_id, n in rows:
        g = (
            db.query(GlosaRecord)
            .filter(
                GlosaRecord.id == glosa_id,
            )
            .first()
        )
        if not g:
            continue
        items.append(
            {
                "glosa_id": glosa_id,
                "n_comentarios": int(n),
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
            }
        )

    return {
        "top_solicitado": int(top),
        "items": items,
    }


@stats_router.get("/stats/eps-no-responde")
def stats_eps_no_responde(
    dias_minimos: int = Query(15, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R195 P1: EPS que no responde tras N días desde respuesta HUS.

    Detecta glosas en estado RESPONDIDA (HUS ya respondió) cuya
    fecha_decision_eps NO está set y cuya creación es >= N días
    atrás.

    Útil para escalar:
      "SANITAS no respondió 25 glosas que llevamos esperando
       30+ días → llamar a su contraparte"

    Agrega por EPS, ordenado DESC por count.
    """

    desde_minimo = ahora_utc() - timedelta(days=int(dias_minimos))

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado == "RESPONDIDA")
        .filter(GlosaRecord.fecha_decision_eps.is_(None))
        .filter(GlosaRecord.creado_en <= desde_minimo)
        .all()
    )

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"count": 0, "valor": 0.0}
        por_eps[eps]["count"] += 1
        por_eps[eps]["valor"] += float(g.valor_objetado or 0)

    items = []
    for eps, b in por_eps.items():
        items.append(
            {
                "eps": eps,
                "count_sin_respuesta": b["count"],
                "valor_pendiente": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["count_sin_respuesta"], reverse=True)

    return {
        "umbral_dias": int(dias_minimos),
        "total_eps_morosas": len(items),
        "items": items,
    }


@stats_router.get("/stats/listas-para-cerrar")
def stats_listas_para_cerrar(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R194 P1: glosas con dictamen completo listas para enviar.

    Filtra glosas con:
      - Estado RADICADA
      - Dictamen presente >= 200 chars
      - codigo_respuesta configurado
      - Gestor asignado

    Útil como cola de "envío masivo": estas ya pasaron auditoría
    interna y solo falta empujarlas a la EPS.

    Devuelve top 50 ordenado por dias_restantes ASC.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado == "RADICADA")
        .filter(GlosaRecord.dictamen.isnot(None))
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    items = []
    for g in glosas:
        if not g.dictamen or len(g.dictamen) < 200:
            continue
        if not g.codigo_respuesta or not g.codigo_respuesta.strip():
            continue
        items.append(
            {
                "id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "codigo_respuesta": g.codigo_respuesta,
                "valor_objetado": float(g.valor_objetado or 0),
                "dias_restantes": g.dias_restantes,
                "gestor": g.gestor_nombre,
            }
        )
    items.sort(
        key=lambda x: x["dias_restantes"] if x["dias_restantes"] is not None else 9999,
    )

    return {
        "total_listas": len(items),
        "items": items[:50],
    }


@stats_router.get("/stats/refinaciones-por-dia")
def stats_refinaciones_por_dia(
    dias: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R193 P1: serie diaria de refinaciones de dictamen.

    Útil para ver el ritmo de trabajo IA del equipo:
      - Picos de refinación (días post-import masivo)
      - Pausas (¿festivos? ¿BD caída?)

    Devuelve serie ASC por fecha YYYY-MM-DD.
    """
    from datetime import timezone


    desde = ahora_utc() - timedelta(days=int(dias))
    versiones = (
        db.query(DictamenVersionRecord).filter(DictamenVersionRecord.creado_en >= desde).all()
    )

    por_dia: dict[str, dict] = {}
    for v in versiones:
        cre = v.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.date().isoformat()
        if k not in por_dia:
            por_dia[k] = {"total": 0, "refinar": 0, "regenerar": 0}
        b = por_dia[k]
        b["total"] += 1
        if v.accion == "REFINAR":
            b["refinar"] += 1
        elif v.accion == "REGENERAR":
            b["regenerar"] += 1

    serie = []
    for k in sorted(por_dia.keys()):
        b = por_dia[k]
        serie.append(
            {
                "fecha": k,
                "total": b["total"],
                "refinar": b["refinar"],
                "regenerar": b["regenerar"],
            }
        )

    return {
        "ventana_dias": int(dias),
        "total_acciones": len(versiones),
        "serie": serie,
    }


@stats_router.get("/stats/tiempo-primer-dictamen")
def stats_tiempo_primer_dictamen(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R226 P1: tiempo promedio entre creación y primer dictamen.

    Mide la velocidad del flujo HUS: ¿cuánto tarda el equipo en
    redactar el primer dictamen tras radicar la glosa?

    Por glosa con DictamenVersionRecord:
      tiempo = MIN(version.creado_en) - glosa.creado_en

    Devuelve:
      - count_glosas_evaluadas
      - tiempo_promedio_horas
      - tiempo_mediano_horas
      - tiempo_max_horas
    """
    from datetime import timezone


    rows = (
        db.query(
            DictamenVersionRecord.glosa_id,
            _f.min(DictamenVersionRecord.creado_en).label("primera"),
        )
        .filter(DictamenVersionRecord.glosa_id.isnot(None))
        .group_by(DictamenVersionRecord.glosa_id)
        .all()
    )

    if not rows:
        return {
            "count_glosas_evaluadas": 0,
            "tiempo_promedio_horas": 0.0,
            "tiempo_mediano_horas": 0.0,
            "tiempo_max_horas": 0.0,
        }

    glosa_ids = [r[0] for r in rows]
    glosas_dict = {
        g.id: g for g in (db.query(GlosaRecord).filter(GlosaRecord.id.in_(glosa_ids)).all())
    }

    horas: list[float] = []
    for glosa_id, primera in rows:
        g = glosas_dict.get(glosa_id)
        if not g or not g.creado_en or not primera:
            continue
        cre = g.creado_en
        if cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        prim = primera
        if prim.tzinfo is None:
            prim = prim.replace(tzinfo=timezone.utc)
        h = (prim - cre).total_seconds() / 3600
        if h < 0:
            continue
        horas.append(h)

    horas.sort()
    n = len(horas)
    if n == 0:
        return {
            "count_glosas_evaluadas": 0,
            "tiempo_promedio_horas": 0.0,
            "tiempo_mediano_horas": 0.0,
            "tiempo_max_horas": 0.0,
        }

    promedio = sum(horas) / n
    if n % 2 == 0:
        mediano = (horas[n // 2 - 1] + horas[n // 2]) / 2
    else:
        mediano = horas[n // 2]

    return {
        "count_glosas_evaluadas": n,
        "tiempo_promedio_horas": round(promedio, 2),
        "tiempo_mediano_horas": round(mediano, 2),
        "tiempo_max_horas": round(max(horas), 2),
    }


@stats_router.get("/stats/tercero-nit-resumen")
def stats_tercero_nit_resumen(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R265 P1: resumen por NIT del tercero (entidad responsable).

    Cuando una EPS tiene varias razones sociales o filiales,
    el campo `tercero_nit` permite agruparlas por entidad
    legal real. Ejemplo: SANITAS y SANITAS COMPLEMENTARIO
    podrían compartir NIT.

    Por NIT:
      - tercero_nombre (uno representativo)
      - count_glosas
      - eps_distintas (cuántas razones sociales)
      - valor_objetado_total
      - valor_recuperado_total

    Ordenado DESC por valor_objetado_total.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.tercero_nit.isnot(None))
        .filter(GlosaRecord.tercero_nit != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        nit = (g.tercero_nit or "").strip()
        if not nit:
            continue
        b = bucket.setdefault(
            nit,
            {
                "nombre": g.tercero_nombre or g.eps or nit,
                "count": 0,
                "eps": set(),
                "obj": 0.0,
                "rec": 0.0,
            },
        )
        b["count"] += 1
        if g.eps:
            b["eps"].add(g.eps.strip())
        b["obj"] += float(g.valor_objetado or 0)
        b["rec"] += float(g.valor_recuperado or 0)

    items = []
    for nit, b in bucket.items():
        items.append(
            {
                "tercero_nit": nit,
                "tercero_nombre": b["nombre"],
                "count_glosas": b["count"],
                "eps_distintas": len(b["eps"]),
                "valor_objetado_total": int(b["obj"]),
                "valor_recuperado_total": int(b["rec"]),
            }
        )
    items.sort(key=lambda x: x["valor_objetado_total"], reverse=True)

    return {
        "limit": int(limit),
        "total_terceros": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/dgh-radicacion-tiempo")
def stats_dgh_radicacion_tiempo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R264 P1: distribución del campo `dias_radicacion_dgh`.

    `dias_radicacion_dgh` mide los días entre la radicación
    de la factura y la objeción de la EPS. Histograma por
    rangos:
      - 0-7, 8-30, 31-60, 61-90, 91+

    Útil para ver patrones temporales: ¿las EPS demoran en
    objetar? ¿hay glosas con radicación atípicamente larga?

    También retorna promedio y mediana globales.
    """
    rows = db.query(GlosaRecord).filter(GlosaRecord.dias_radicacion_dgh.isnot(None)).all()

    buckets = {"0-7": 0, "8-30": 0, "31-60": 0, "61-90": 0, "91+": 0}
    valores: list[int] = []
    for g in rows:
        d = int(g.dias_radicacion_dgh or 0)
        if d < 0:
            continue
        valores.append(d)
        if d <= 7:
            buckets["0-7"] += 1
        elif d <= 30:
            buckets["8-30"] += 1
        elif d <= 60:
            buckets["31-60"] += 1
        elif d <= 90:
            buckets["61-90"] += 1
        else:
            buckets["91+"] += 1

    n = len(valores)
    if n == 0:
        promedio = 0.0
        mediana = 0
        maximo = 0
    else:
        promedio = round(sum(valores) / n, 2)
        ord_v = sorted(valores)
        mediana = ord_v[n // 2]
        maximo = max(valores)

    return {
        "total_glosas": n,
        "promedio_dias": promedio,
        "mediana_dias": mediana,
        "max_dias": maximo,
        "buckets": [{"rango": k, "count": v} for k, v in buckets.items()],
    }


@stats_router.get("/stats/tecnico-recepcion-actividad")
def stats_tecnico_recepcion_actividad(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R263 P1: actividad por técnico que recepcionó glosas.

    El campo `tecnico_recepcion` viene del Excel del DGH y
    es el responsable inicial de la radicación. Útil para
    ver carga de recepciones por técnico (no es el mismo
    rol que gestor o auditor).

    Por técnico:
      - total_glosas
      - eps_distintas (cuántas EPS le tocó manejar)
      - valor_objetado_total
      - count_devoluciones (es_devolucion = '1')

    Ordenado DESC por total_glosas.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.tecnico_recepcion.isnot(None))
        .filter(GlosaRecord.tecnico_recepcion != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        tec = (g.tecnico_recepcion or "").strip()
        if not tec:
            continue
        b = bucket.setdefault(
            tec,
            {
                "total": 0,
                "eps": set(),
                "valor": 0.0,
                "dev": 0,
            },
        )
        b["total"] += 1
        if g.eps:
            b["eps"].add(g.eps.strip())
        b["valor"] += float(g.valor_objetado or 0)
        if (g.es_devolucion or "").strip() in ("1", "S", "Y"):
            b["dev"] += 1

    items = []
    for tec, b in bucket.items():
        items.append(
            {
                "tecnico_recepcion": tec,
                "total_glosas": b["total"],
                "eps_distintas": len(b["eps"]),
                "valor_objetado_total": int(b["valor"]),
                "count_devoluciones": b["dev"],
            }
        )
    items.sort(key=lambda x: x["total_glosas"], reverse=True)

    return {
        "limit": int(limit),
        "total_tecnicos": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/dashboard-mensual-completo")
def stats_dashboard_mensual_completo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R350 P1: dashboard mensual completo (single-call). HITO.

    Mega-snapshot del mes en curso, combinando:
      - kpis_creacion: creadas, valor_objetado_total
      - kpis_decisiones: decididas, levantadas,
        ratificadas, valor_recuperado_total
      - kpis_sla: cerradas a tiempo, % SLA
      - top_3_eps_volumen
      - top_3_gestores_volumen
      - tasa_levantamiento_pct, tasa_recuperacion_monetaria_pct

    Hito R350: dashboard ejecutivo definitivo del mes.
    """

    inicio = ahora_utc().replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    creadas = db.query(GlosaRecord).filter(GlosaRecord.creado_en >= inicio).all()
    decididas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= inicio)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    n_creadas = len(creadas)
    obj_creadas = sum(float(g.valor_objetado or 0) for g in creadas)

    n_dec = len(decididas)
    n_lev = sum(1 for g in decididas if (g.estado or "").upper() == "LEVANTADA")
    n_rat = sum(1 for g in decididas if (g.estado or "").upper() == "RATIFICADA")
    rec_total = sum(float(g.valor_recuperado or 0) for g in decididas)
    obj_dec_total = sum(float(g.valor_objetado or 0) for g in decididas)

    a_tiempo = 0
    for g in decididas:
        venc = g.fecha_vencimiento
        dec = g.fecha_decision_eps
        if venc and dec and dec <= venc:
            a_tiempo += 1

    tasa_lev = round(100 * n_lev / n_dec, 2) if n_dec else 0.0
    tasa_rec = round(100 * rec_total / obj_dec_total, 2) if obj_dec_total else 0.0
    pct_sla = round(100 * a_tiempo / n_dec, 2) if n_dec else 0.0

    eps_vol: dict[str, int] = {}
    gestor_vol: dict[str, int] = {}
    for g in creadas:
        eps = (g.eps or "").strip()
        gest = (g.gestor_nombre or "").strip()
        if eps:
            eps_vol[eps] = eps_vol.get(eps, 0) + 1
        if gest:
            gestor_vol[gest] = gestor_vol.get(gest, 0) + 1

    top3_eps = sorted(
        eps_vol.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:3]
    top3_gestor = sorted(
        gestor_vol.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    return {
        "mes": inicio.strftime("%Y-%m"),
        "kpis_creacion": {
            "creadas": n_creadas,
            "valor_objetado_total": int(obj_creadas),
        },
        "kpis_decisiones": {
            "decididas": n_dec,
            "levantadas": n_lev,
            "ratificadas": n_rat,
            "valor_recuperado_total": int(rec_total),
        },
        "kpis_sla": {
            "cerradas_a_tiempo": a_tiempo,
            "pct_sla": pct_sla,
        },
        "tasa_levantamiento_pct": tasa_lev,
        "tasa_recuperacion_monetaria_pct": tasa_rec,
        "top_3_eps_volumen": [{"eps": e, "count": c} for e, c in top3_eps],
        "top_3_gestores_volumen": [{"gestor": g, "count": c} for g, c in top3_gestor],
    }


@stats_router.get("/stats/ratificadas-recientes")
def stats_ratificadas_recientes(
    dias: int = Query(30, ge=1, le=180),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R347 P1: glosas ratificadas (HUS perdió) recientes.

    Lista glosas que terminaron en RATIFICADA en los
    últimos N días. Útil para retrospective: ¿qué
    perdimos esta semana/mes?

    Ordena DESC por fecha_decision_eps.
    """

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado == "RATIFICADA")
        .filter(GlosaRecord.fecha_decision_eps >= desde)
        .order_by(GlosaRecord.fecha_decision_eps.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for g in rows:
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "valor_aceptado": int(float(g.valor_aceptado or 0)),
                "gestor_nombre": g.gestor_nombre,
                "fecha_decision_eps": (
                    g.fecha_decision_eps.isoformat() if g.fecha_decision_eps else None
                ),
            }
        )

    return {
        "ventana_dias": int(dias),
        "total": len(items),
        "valor_aceptado_total": sum(it["valor_aceptado"] for it in items),
        "items": items,
    }


@stats_router.get("/stats/conciliaciones-acta-firmadas")
def stats_conciliaciones_acta_firmadas(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R366 P1: conciliaciones con acta firmada.

    Lista conciliaciones en estado ACTA_FIRMADA o
    CERRADA con detalle de acta_numero, fecha_acta y
    valor_ratificado_hus. Útil como inventario formal
    de cierres bilaterales.
    """

    rows = (
        db.query(ConciliacionRecord)
        .filter(
            ConciliacionRecord.estado_bilateral.in_(
                ["ACTA_FIRMADA", "CERRADA"],
            )
        )
        .order_by(ConciliacionRecord.fecha_acta.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for c in rows:
        items.append(
            {
                "conciliacion_id": c.id,
                "glosa_id": c.glosa_id,
                "acta_numero": c.acta_numero,
                "fecha_acta": (c.fecha_acta.isoformat() if c.fecha_acta else None),
                "valor_conciliado": int(float(c.valor_conciliado or 0)),
                "valor_ratificado_hus": int(
                    float(c.valor_ratificado_hus or 0),
                ),
                "estado_bilateral": c.estado_bilateral,
            }
        )

    return {
        "total_actas": len(items),
        "items": items,
    }


@stats_router.get("/stats/cobranza-eps-vencidas")
def stats_cobranza_eps_vencidas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R364 P1: por EPS, glosas vencidas con saldo pendiente.

    Combina vencidas (dias_restantes < 0) con saldo
    financiero. Da prioridad de cobranza a EPS que más
    nos deben + más nos ignoran.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < 0)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(
            eps,
            {
                "count": 0,
                "suma_dias": 0,
                "obj": 0.0,
                "saldo": 0.0,
            },
        )
        b["count"] += 1
        b["suma_dias"] += abs(int(g.dias_restantes or 0))
        b["obj"] += float(g.valor_objetado or 0)
        b["saldo"] += float(g.saldo_factura or 0)

    items = []
    for eps, b in bucket.items():
        prom = round(b["suma_dias"] / b["count"], 1) if b["count"] else 0.0
        items.append(
            {
                "eps": eps,
                "count_vencidas": b["count"],
                "dias_promedio_vencido": prom,
                "valor_objetado_total": int(b["obj"]),
                "saldo_total": int(b["saldo"]),
            }
        )
    items.sort(key=lambda x: x["valor_objetado_total"], reverse=True)

    return {
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/conciliaciones-pendientes")
def stats_conciliaciones_pendientes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R363 P1: conciliaciones aún pendientes en el ciclo bilateral.

    Filtra estados pre-cierre: PROGRAMADA, EPS_RESPONDIO,
    AUDIENCIA_REALIZADA. Útil para saber cuánto trabajo
    bilateral está activo.

    Por estado_bilateral: count, valor_conciliado_total.
    """

    PENDIENTES = [
        "PROGRAMADA",
        "EPS_RESPONDIO",
        "AUDIENCIA_REALIZADA",
    ]

    rows = (
        db.query(ConciliacionRecord)
        .filter(ConciliacionRecord.estado_bilateral.in_(PENDIENTES))
        .all()
    )

    bucket: dict[str, dict] = {}
    for c in rows:
        e = (c.estado_bilateral or "?").upper()
        b = bucket.setdefault(e, {"count": 0, "valor": 0.0})
        b["count"] += 1
        b["valor"] += float(c.valor_conciliado or 0)

    items = []
    for e, b in bucket.items():
        items.append(
            {
                "estado_bilateral": e,
                "count": b["count"],
                "valor_conciliado_total": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_pendientes": sum(it["count"] for it in items),
        "valor_total": sum(it["valor_conciliado_total"] for it in items),
        "items": items,
    }


@stats_router.get("/stats/factura-grandes-pendientes")
def stats_factura_grandes_pendientes(
    umbral: float = Query(50_000_000, ge=10_000_000),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R362 P1: facturas grandes con glosas abiertas.

    Lista facturas con valor_factura >= umbral que todavía
    tienen al menos una glosa abierta. Prioridad alta
    para cobranza estratégica.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "N/A")
        .filter(GlosaRecord.valor_factura >= float(umbral))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        f = (g.factura or "").strip()
        if not f:
            continue
        b = bucket.setdefault(
            f,
            {
                "eps": g.eps,
                "valor_factura": float(g.valor_factura or 0),
                "saldo": float(g.saldo_factura or 0),
                "abiertas": 0,
                "obj_abierto": 0.0,
            },
        )
        if (g.estado or "").upper() not in ESTADOS_CERRADOS:
            b["abiertas"] += 1
            b["obj_abierto"] += float(g.valor_objetado or 0)

    items = []
    for f, b in bucket.items():
        if b["abiertas"] == 0:
            continue
        items.append(
            {
                "factura": f,
                "eps": b["eps"],
                "valor_factura": int(b["valor_factura"]),
                "saldo_factura": int(b["saldo"]),
                "count_glosas_abiertas": b["abiertas"],
                "valor_objetado_pendiente": int(b["obj_abierto"]),
            }
        )
    items.sort(key=lambda x: x["valor_factura"], reverse=True)

    return {
        "umbral": int(umbral),
        "total_facturas": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/dictamen-tasa-vs-largo")
def stats_dictamen_tasa_vs_largo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R361 P1: correlación entre largo de dictamen y tasa de
    levantamiento.

    Bucketea dictamen length: 0-49 (sin), 50-199 (corto),
    200-499 (medio), 500+ (largo). Para cada bucket
    calcula la tasa de levantamiento sobre glosas decididas.

    Hipótesis: dictámenes más largos correlacionan con
    mayor tasa de levantamiento (mejor argumentación).
    """
    BUCKETS = [
        ("0-49", 0, 49),
        ("50-199", 50, 199),
        ("200-499", 200, 499),
        ("500+", 500, None),
    ]

    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    bandas = {n: {"dec": 0, "lev": 0} for n, _, _ in BUCKETS}
    for g in glosas:
        dlen = len(g.dictamen or "")
        for n, lo, hi in BUCKETS:
            if dlen >= lo and (hi is None or dlen <= hi):
                bandas[n]["dec"] += 1
                if (g.estado or "").upper() == "LEVANTADA":
                    bandas[n]["lev"] += 1
                break

    items = []
    for n, _, _ in BUCKETS:
        b = bandas[n]
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        items.append(
            {
                "rango_caracteres": n,
                "decididas": b["dec"],
                "levantadas": b["lev"],
                "tasa_levantamiento_pct": tasa,
            }
        )

    return {
        "items": items,
    }


@stats_router.get("/stats/codigo-respuesta-mes-actual")
def stats_codigo_respuesta_mes_actual(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R359 P1: uso de codigo_respuesta en el mes en curso.

    Snapshot de codigos_respuesta usados por HUS este
    mes, con count y tasa de levantamiento.
    """

    inicio = ahora_utc().replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= inicio)
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .filter(GlosaRecord.codigo_respuesta != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        c = (g.codigo_respuesta or "").strip()
        if not c:
            continue
        b = bucket.setdefault(
            c,
            {
                "count": 0,
                "lev": 0,
                "dec": 0,
            },
        )
        b["count"] += 1
        estado = (g.estado or "").upper()
        if estado in ("LEVANTADA", "RATIFICADA", "ACEPTADA"):
            b["dec"] += 1
        if estado == "LEVANTADA":
            b["lev"] += 1

    items = []
    for c, b in bucket.items():
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        items.append(
            {
                "codigo_respuesta": c,
                "count_total": b["count"],
                "decididas": b["dec"],
                "levantadas": b["lev"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["count_total"], reverse=True)

    return {
        "mes": inicio.strftime("%Y-%m"),
        "total_codigos": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-radica-promedio-dia")
def stats_eps_radica_promedio_dia(
    dias: int = Query(30, ge=7, le=180),
    min_glosas: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R357 P1: glosas creadas por día por EPS.

    En los últimos N días, cuántas glosas envía en
    promedio cada EPS por día. Útil para presupuestar
    capacidad operativa.
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        b = bucket.setdefault(
            eps,
            {
                "total": 0,
                "por_dia": {},
            },
        )
        b["total"] += 1
        k = cre.date().isoformat()
        b["por_dia"][k] = b["por_dia"].get(k, 0) + 1

    items = []
    for eps, b in bucket.items():
        if b["total"] < min_glosas:
            continue
        n_dias = len(b["por_dia"])
        max_dia = max(b["por_dia"].values()) if b["por_dia"] else 0
        prom = round(b["total"] / int(dias), 2)
        items.append(
            {
                "eps": eps,
                "count_total": b["total"],
                "dias_con_glosa": n_dias,
                "promedio_diario": prom,
                "max_dia": max_dia,
            }
        )
    items.sort(key=lambda x: x["promedio_diario"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/factura-tasa-cierre")
def stats_factura_tasa_cierre(
    min_glosas: int = Query(2, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R354 P1: tasa de cierre por factura.

    Para cada factura con >= min_glosas, qué % de sus
    glosas están cerradas. Útil para identificar facturas
    "atascadas" (varias glosas, todas abiertas) vs
    "completadas".
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "N/A")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        f = (g.factura or "").strip()
        if not f:
            continue
        b = bucket.setdefault(
            f,
            {
                "total": 0,
                "cerradas": 0,
                "eps": g.eps,
            },
        )
        b["total"] += 1
        if (g.estado or "").upper() in ESTADOS_CERRADOS:
            b["cerradas"] += 1

    items = []
    for f, b in bucket.items():
        if b["total"] < min_glosas:
            continue
        pct = round(100 * b["cerradas"] / b["total"], 2) if b["total"] else 0.0
        items.append(
            {
                "factura": f,
                "eps": b["eps"],
                "total": b["total"],
                "cerradas": b["cerradas"],
                "pct_cerradas": pct,
            }
        )
    items.sort(key=lambda x: x["pct_cerradas"])

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_facturas": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-codigo-rentabilidad")
def stats_eps_codigo_rentabilidad(
    min_decididas: int = Query(3, ge=1, le=50),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R352 P1: rentabilidad por par (eps, codigo_glosa).

    Por combinación EPS-código:
      - count_decididas
      - valor_recuperado_total
      - valor_recuperado_promedio_por_glosa

    Identifica las parejas más rentables. Ordenado DESC
    por valor_recuperado_total.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.eps.isnot(None))
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    bucket: dict[tuple[str, str], dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        codigo = (g.codigo_glosa or "").strip()
        if not eps or not codigo:
            continue
        b = bucket.setdefault(
            (eps, codigo),
            {
                "count": 0,
                "rec": 0.0,
            },
        )
        b["count"] += 1
        b["rec"] += float(g.valor_recuperado or 0)

    items = []
    for (eps, codigo), b in bucket.items():
        if b["count"] < min_decididas:
            continue
        prom = int(b["rec"] / b["count"]) if b["count"] else 0
        items.append(
            {
                "eps": eps,
                "codigo_glosa": codigo,
                "count_decididas": b["count"],
                "valor_recuperado_total": int(b["rec"]),
                "valor_recuperado_promedio": prom,
            }
        )
    items.sort(key=lambda x: x["valor_recuperado_total"], reverse=True)

    return {
        "min_decididas_filtro": int(min_decididas),
        "total_pares": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/conciliaciones-por-eps")
def stats_conciliaciones_por_eps(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R351 P1: conciliaciones agregadas por EPS.

    Para cada EPS, cuántas conciliaciones tiene asociadas
    (a través de glosas) y suma de valores. Útil para
    saber qué EPS llegan más al proceso bilateral.
    """

    rows = db.query(
        ConciliacionRecord.glosa_id,
        ConciliacionRecord.valor_conciliado,
        ConciliacionRecord.valor_ratificado_hus,
    ).all()

    if not rows:
        return {"total_eps": 0, "items": []}

    glosa_ids = {r[0] for r in rows if r[0]}
    glosas_eps = dict(
        db.query(GlosaRecord.id, GlosaRecord.eps).filter(GlosaRecord.id.in_(glosa_ids)).all()
    )

    bucket: dict[str, dict] = {}
    for g_id, val_c, val_r in rows:
        eps = (glosas_eps.get(g_id) or "").strip() if g_id else ""
        if not eps:
            continue
        b = bucket.setdefault(
            eps,
            {
                "count": 0,
                "valor": 0.0,
                "ratificado": 0.0,
            },
        )
        b["count"] += 1
        b["valor"] += float(val_c or 0)
        b["ratificado"] += float(val_r or 0)

    items = []
    for eps, b in bucket.items():
        items.append(
            {
                "eps": eps,
                "count_conciliaciones": b["count"],
                "valor_conciliado_total": int(b["valor"]),
                "valor_ratificado_hus_total": int(b["ratificado"]),
            }
        )
    items.sort(
        key=lambda x: x["count_conciliaciones"],
        reverse=True,
    )

    return {
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/glosas-conciliadas-detalle")
def stats_glosas_conciliadas_detalle(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R344 P1: glosas que tienen al menos una conciliación.

    Lista glosas con conciliacion asociada (pasaron por
    proceso bilateral). Útil para ver el universo de
    casos que llegaron a esa instancia.

    Ordena DESC por valor_conciliado total agregado.
    """

    # Para cada glosa con concil, sumar valor
    rows = (
        db.query(
            ConciliacionRecord.glosa_id,
        )
        .distinct()
        .all()
    )

    glosa_ids = {r[0] for r in rows if r[0]}

    if not glosa_ids:
        return {
            "total": 0,
            "items": [],
        }

    glosas = db.query(GlosaRecord).filter(GlosaRecord.id.in_(glosa_ids)).all()

    # Aggregate valor per glosa
    valores_concil = {}
    valores_ratificado = {}
    for g_id, valor, valor_rat in db.query(
        ConciliacionRecord.glosa_id,
        ConciliacionRecord.valor_conciliado,
        ConciliacionRecord.valor_ratificado_hus,
    ).all():
        if not g_id:
            continue
        valores_concil[g_id] = valores_concil.get(g_id, 0.0) + float(valor or 0)
        valores_ratificado[g_id] = valores_ratificado.get(g_id, 0.0) + float(valor_rat or 0)

    items = []
    for g in glosas:
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "valor_conciliado_total": int(
                    valores_concil.get(g.id, 0.0),
                ),
                "valor_ratificado_hus_total": int(
                    valores_ratificado.get(g.id, 0.0),
                ),
            }
        )
    items.sort(
        key=lambda x: x["valor_conciliado_total"],
        reverse=True,
    )

    return {
        "total": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/vencen-en-dias")
def stats_vencen_en_dias(
    dias: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R342 P1: lista detallada de glosas que vencen en N días.

    Diferente a /stats/proyeccion-vencimiento (histograma):
    aquí lista detallada de glosas con
    0 <= dias_restantes <= N. Útil para acción operativa
    inmediata.

    Ordena ASC por dias_restantes.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes >= 0)
        .filter(GlosaRecord.dias_restantes <= int(dias))
        .order_by(GlosaRecord.dias_restantes.asc())
        .all()
    )

    items = []
    for g in rows:
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "dias_restantes": g.dias_restantes,
                "gestor_nombre": g.gestor_nombre,
            }
        )

    return {
        "ventana_dias": int(dias),
        "total_proximos_a_vencer": len(items),
        "valor_total": sum(it["valor_objetado"] for it in items),
        "items": items,
    }


@stats_router.get("/stats/conciliaciones-top-monto")
def stats_conciliaciones_top_monto(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R340 P1: top N conciliaciones por valor_conciliado.

    Lista las conciliaciones de mayor valor cerrado.
    Útil para review de big-ticket cases.

    Por conciliación:
      - id, glosa_id, valor_conciliado, resultado,
        estado_bilateral, fecha_audiencia
    """

    rows = (
        db.query(ConciliacionRecord)
        .filter(ConciliacionRecord.valor_conciliado > 0)
        .order_by(ConciliacionRecord.valor_conciliado.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for c in rows:
        items.append(
            {
                "conciliacion_id": c.id,
                "glosa_id": c.glosa_id,
                "valor_conciliado": int(float(c.valor_conciliado or 0)),
                "valor_ratificado_hus": int(
                    float(c.valor_ratificado_hus or 0),
                ),
                "resultado": c.resultado,
                "estado_bilateral": c.estado_bilateral,
                "fecha_audiencia": (c.fecha_audiencia.isoformat() if c.fecha_audiencia else None),
            }
        )

    return {
        "limit": int(limit),
        "items": items,
    }


@stats_router.get("/stats/codigos-recuperacion-monetaria")
def stats_codigos_recuperacion_monetaria(
    min_glosas: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R339 P1: ratio recuperado/objetado por codigo_glosa.

    Diferente a /stats/codigos-mejor-tasa (% count) y
    /stats/codigos-mas-recuperados (suma absoluta): aquí
    el ratio monetario.

    Por código:
      - count_decididas
      - valor_objetado_total
      - valor_recuperado_total
      - tasa_recuperacion_monetaria_pct
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        codigo = (g.codigo_glosa or "").strip()
        if not codigo:
            continue
        b = bucket.setdefault(
            codigo,
            {
                "count": 0,
                "obj": 0.0,
                "rec": 0.0,
            },
        )
        b["count"] += 1
        b["obj"] += float(g.valor_objetado or 0)
        b["rec"] += float(g.valor_recuperado or 0)

    items = []
    for codigo, b in bucket.items():
        if b["count"] < min_glosas:
            continue
        tasa = round(100 * b["rec"] / b["obj"], 2) if b["obj"] else 0.0
        items.append(
            {
                "codigo_glosa": codigo,
                "count_decididas": b["count"],
                "valor_objetado_total": int(b["obj"]),
                "valor_recuperado_total": int(b["rec"]),
                "tasa_recuperacion_monetaria_pct": tasa,
            }
        )
    items.sort(
        key=lambda x: x["tasa_recuperacion_monetaria_pct"],
        reverse=True,
    )

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_codigos": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-volumen-mes-anterior")
def stats_eps_volumen_mes_anterior(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R338 P1: volumen por EPS en el mes anterior.

    Snapshot del mes pasado: count_glosas y
    valor_objetado por EPS para las creadas el mes
    anterior. Útil para reportar "cómo cerró el mes" por
    EPS.

    Ordenado DESC por count_glosas.
    """


    ahora = ahora_utc()
    inicio_mes_actual = ahora.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if inicio_mes_actual.month == 1:
        inicio_anterior = inicio_mes_actual.replace(
            year=inicio_mes_actual.year - 1,
            month=12,
        )
    else:
        inicio_anterior = inicio_mes_actual.replace(
            month=inicio_mes_actual.month - 1,
        )

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= inicio_anterior)
        .filter(GlosaRecord.creado_en < inicio_mes_actual)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(eps, {"count": 0, "valor": 0.0})
        b["count"] += 1
        b["valor"] += float(g.valor_objetado or 0)

    items = []
    for eps, b in bucket.items():
        items.append(
            {
                "eps": eps,
                "count_glosas": b["count"],
                "valor_objetado_total": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["count_glosas"], reverse=True)

    return {
        "mes_anterior": inicio_anterior.strftime("%Y-%m"),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/codigo-respuesta-monetaria")
def stats_codigo_respuesta_monetaria(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R336 P1: efectividad monetaria por codigo_respuesta.

    Para cada codigo_respuesta usado por HUS, cuál fue el
    valor recuperado promedio cuando se ganó la glosa
    (LEVANTADA). Diferente a /stats/exito-por-codigo-respuesta
    (tasa por count): aquí enfoque monetario.

    Por código:
      - count_levantadas
      - valor_recuperado_total
      - valor_recuperado_promedio
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado == "LEVANTADA")
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .filter(GlosaRecord.codigo_respuesta != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        c = (g.codigo_respuesta or "").strip()
        if not c:
            continue
        b = bucket.setdefault(c, {"count": 0, "rec": 0.0})
        b["count"] += 1
        b["rec"] += float(g.valor_recuperado or 0)

    items = []
    for c, b in bucket.items():
        prom = int(b["rec"] / b["count"]) if b["count"] else 0
        items.append(
            {
                "codigo_respuesta": c,
                "count_levantadas": b["count"],
                "valor_recuperado_total": int(b["rec"]),
                "valor_recuperado_promedio": prom,
            }
        )
    items.sort(
        key=lambda x: x["valor_recuperado_total"],
        reverse=True,
    )

    return {
        "items": items,
    }


@stats_router.get("/stats/cumplimiento-sla-mensual")
def stats_cumplimiento_sla_mensual(
    meses: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R335 P1: serie mensual de cumplimiento SLA.

    Por mes (basado en fecha_decision_eps), porcentaje de
    glosas cerradas a tiempo (fecha_decision_eps <=
    fecha_vencimiento) vs total cerradas en ese mes.

    Diferente a /stats/cumplimiento-sla (snapshot global):
    aquí evolución temporal.
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= desde)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    por_mes: dict[str, dict] = {}
    for g in glosas:
        dec = g.fecha_decision_eps
        venc = g.fecha_vencimiento
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if venc and venc.tzinfo is None:
            venc = venc.replace(tzinfo=timezone.utc)
        if not dec:
            continue
        k = dec.strftime("%Y-%m")
        b = por_mes.setdefault(k, {"total": 0, "a_tiempo": 0})
        b["total"] += 1
        if venc and dec <= venc:
            b["a_tiempo"] += 1

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        pct = round(100 * b["a_tiempo"] / b["total"], 2) if b["total"] else 0.0
        serie.append(
            {
                "mes": k,
                "total_cerradas": b["total"],
                "cerradas_a_tiempo": b["a_tiempo"],
                "cumplimiento_sla_pct": pct,
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_meses": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/eps-tiempo-radicacion-objecion")
def stats_eps_tiempo_radicacion_objecion(
    min_glosas: int = Query(3, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R333 P1: tiempo entre radicación y objeción por EPS.

    Por EPS, calcula los días promedio entre
    `fecha_radicacion_factura` y `fecha_objecion_eps`.
    Mide qué tan rápido objeta cada EPS desde que se le
    radica la factura.

    Por EPS:
      - count
      - tiempo_promedio_dias
      - tiempo_max_dias
    """
    from datetime import timezone

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_radicacion_factura.isnot(None))
        .filter(GlosaRecord.fecha_objecion_eps.isnot(None))
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, list[int]] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        rad = g.fecha_radicacion_factura
        obj = g.fecha_objecion_eps
        if rad and rad.tzinfo is None:
            rad = rad.replace(tzinfo=timezone.utc)
        if obj and obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        if not rad or not obj:
            continue
        dias = (obj - rad).days
        if dias < 0:
            continue
        bucket.setdefault(eps, []).append(dias)

    items = []
    for eps, vals in bucket.items():
        if len(vals) < min_glosas:
            continue
        prom = round(sum(vals) / len(vals), 2)
        items.append(
            {
                "eps": eps,
                "count": len(vals),
                "tiempo_promedio_dias": prom,
                "tiempo_max_dias": max(vals),
            }
        )
    items.sort(key=lambda x: x["tiempo_promedio_dias"])

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/codigo-eps-cobertura")
def stats_codigo_eps_cobertura(
    min_glosas: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R332 P1: cobertura de EPS por código de glosa.

    Para cada código, cuántas EPS distintas lo usan. Un
    código usado por muchas EPS es "universal", uno usado
    por pocas EPS es "nicho".

    Por código:
      - count_glosas
      - eps_distintas
      - top_3_eps
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        codigo = (g.codigo_glosa or "").strip()
        eps = (g.eps or "").strip()
        if not codigo or not eps:
            continue
        b = bucket.setdefault(
            codigo,
            {
                "count": 0,
                "eps": {},
            },
        )
        b["count"] += 1
        b["eps"][eps] = b["eps"].get(eps, 0) + 1

    items = []
    for codigo, b in bucket.items():
        if b["count"] < min_glosas:
            continue
        top3 = sorted(
            b["eps"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        items.append(
            {
                "codigo_glosa": codigo,
                "count_glosas": b["count"],
                "eps_distintas": len(b["eps"]),
                "top_3_eps": [{"eps": e, "count": c} for e, c in top3],
            }
        )
    items.sort(key=lambda x: x["eps_distintas"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_codigos": len(items),
        "items": items,
    }


@stats_router.get("/stats/codigos-respuesta-mejor-tasa-eps")
def stats_codigos_respuesta_mejor_tasa_eps(
    eps: str = Query(..., min_length=2),
    min_muestras: int = Query(2, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R398 P1: para una EPS, qué código de respuesta de
    HUS tuvo mejor tasa de levantamiento históricamente.

    Útil estratégico: "con esta EPS, RE9501 funciona el
    80% de las veces, RE9701 solo el 30%". Permite al
    gestor elegir el mejor código antes de enviar.

    Devuelve códigos ordenados DESC por tasa
    (con muestras ≥ min_muestras).
    """
    eps_q = (eps or "").strip()
    if not eps_q:
        return {"eps": "", "items": []}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.ilike(eps_q))
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .filter(GlosaRecord.codigo_respuesta != "")
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        cr = (g.codigo_respuesta or "").strip()
        if not cr:
            continue
        b = bucket.setdefault(cr, {"dec": 0, "lev": 0, "rec": 0.0})
        b["dec"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["lev"] += 1
        b["rec"] += float(g.valor_recuperado or 0)

    items = []
    for cr, b in bucket.items():
        if b["dec"] < int(min_muestras):
            continue
        tasa = round(100 * b["lev"] / b["dec"], 2)
        prom_rec = int(b["rec"] / b["dec"]) if b["dec"] else 0
        items.append(
            {
                "codigo_respuesta": cr,
                "decididas": b["dec"],
                "levantadas": b["lev"],
                "tasa_levantamiento_pct": tasa,
                "valor_recuperado_promedio": prom_rec,
            }
        )
    items.sort(
        key=lambda x: (
            x["tasa_levantamiento_pct"],
            x["decididas"],
        ),
        reverse=True,
    )

    return {
        "eps": eps_q,
        "min_muestras": int(min_muestras),
        "total_codigos": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-volumen-tasa-mes")
def stats_eps_volumen_tasa_mes(
    meses: int = Query(6, ge=1, le=24),
    top_eps: int = Query(8, ge=2, le=20),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R393 P1: matriz EPS × mes con volumen y tasa.

    Para las top N EPS por volumen total, devuelve por
    cada mes el count de creadas y la tasa de
    levantamiento. Útil para detectar EPS que están
    cambiando su patrón de tasa (no solo volumen).
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    total_eps: dict[str, int] = {}
    matriz: dict[str, dict[str, dict]] = {}
    meses_set: set = set()

    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.strftime("%Y-%m")
        meses_set.add(k)
        total_eps[eps] = total_eps.get(eps, 0) + 1
        b = matriz.setdefault(eps, {}).setdefault(
            k,
            {
                "count": 0,
                "dec": 0,
                "lev": 0,
            },
        )
        b["count"] += 1
        estado = (g.estado or "").upper()
        if estado in ESTADOS_DECIDIDOS:
            b["dec"] += 1
        if estado == "LEVANTADA":
            b["lev"] += 1

    eps_top = [
        e
        for e, _ in sorted(
            total_eps.items(),
            key=lambda x: x[1],
            reverse=True,
        )[: int(top_eps)]
    ]
    meses_ord = sorted(meses_set)

    items = []
    for eps in eps_top:
        celdas = []
        for m in meses_ord:
            b = matriz.get(eps, {}).get(m, {"count": 0, "dec": 0, "lev": 0})
            tasa = round(100 * b["lev"] / b["dec"], 1) if b["dec"] else None
            celdas.append(
                {
                    "mes": m,
                    "count": b["count"],
                    "tasa_levantamiento_pct": tasa,
                }
            )
        items.append(
            {
                "eps": eps,
                "total": total_eps.get(eps, 0),
                "celdas": celdas,
            }
        )

    return {
        "ventana_meses": int(meses),
        "meses": meses_ord,
        "items": items,
    }


@stats_router.get("/stats/anomalias-recientes")
def stats_anomalias_recientes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R388 P1: anomalías detectadas en últimos 7 días.

    La IA compara la última semana con el promedio
    histórico (12 semanas) para cada EPS y reporta
    anomalías estadísticas:
      - volumen 2x el promedio (PICO)
      - volumen 0.3x el promedio (CAÍDA)
      - código nuevo apareció (NUEVO_CODIGO)

    Útil como vigilancia automática.
    """
    from datetime import timezone

    ahora = ahora_utc()
    inicio_actual = ahora - timedelta(days=7)
    inicio_hist = ahora - timedelta(days=7 * 13)

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= inicio_hist)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    eps_actual: dict[str, int] = {}
    eps_hist_buckets: dict[str, list[int]] = {}
    codigos_actual: dict[tuple, int] = {}
    codigos_hist: set = set()

    # 12 cubos semanales históricos (sin la semana actual)
    semanas = {}
    for g in rows:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        eps = (g.eps or "").strip()
        cod = (g.codigo_glosa or "").strip()
        if cre >= inicio_actual:
            eps_actual[eps] = eps_actual.get(eps, 0) + 1
            if eps and cod:
                codigos_actual[(eps, cod)] = codigos_actual.get((eps, cod), 0) + 1
        else:
            # bucket por semana
            semana_idx = int((ahora - cre).days // 7)
            if 1 <= semana_idx <= 12:
                semanas.setdefault(eps, {}).setdefault(semana_idx, 0)
                semanas[eps][semana_idx] += 1
            if eps and cod:
                codigos_hist.add((eps, cod))

    for eps, by_w in semanas.items():
        # 12 buckets, llenar con 0 si falta
        bk = [by_w.get(i, 0) for i in range(1, 13)]
        eps_hist_buckets[eps] = bk

    items = []

    # PICO / CAÍDA por volumen
    for eps, count in eps_actual.items():
        bk = eps_hist_buckets.get(eps, [])
        if not bk:
            continue
        promedio = sum(bk) / len(bk) if bk else 0
        if promedio < 1:
            continue
        ratio = count / promedio
        if ratio >= 2.0 and count >= 5:
            items.append(
                {
                    "tipo": "PICO",
                    "eps": eps,
                    "actual_semana": count,
                    "promedio_semanal_hist": round(promedio, 1),
                    "ratio": round(ratio, 2),
                    "mensaje": (
                        f"{eps} pasó de ~{promedio:.0f}/sem a {count} esta semana ({ratio:.1f}x)"
                    ),
                }
            )
        elif ratio <= 0.3 and promedio >= 5:
            items.append(
                {
                    "tipo": "CAIDA",
                    "eps": eps,
                    "actual_semana": count,
                    "promedio_semanal_hist": round(promedio, 1),
                    "ratio": round(ratio, 2),
                    "mensaje": (f"{eps} cayó de ~{promedio:.0f}/sem a {count} esta semana"),
                }
            )

    # CODIGO NUEVO por par (eps, codigo) que no estaba en histórico
    for (eps, cod), count in codigos_actual.items():
        if (eps, cod) in codigos_hist:
            continue
        if count < 2:
            continue  # filtra ruido — al menos 2 casos
        items.append(
            {
                "tipo": "NUEVO_CODIGO",
                "eps": eps,
                "codigo_glosa": cod,
                "actual_semana": count,
                "mensaje": (
                    f"Código {cod} aparece en {eps} ({count} casos esta semana, antes nunca)"
                ),
            }
        )

    # Orden: PICO primero, luego CAÍDA, luego NUEVO_CODIGO
    orden_tipo = {"PICO": 1, "CAIDA": 2, "NUEVO_CODIGO": 3}
    items.sort(
        key=lambda x: (
            orden_tipo.get(x["tipo"], 9),
            -(x.get("actual_semana") or 0),
        )
    )

    return {
        "ventana_dias": 7,
        "total_anomalias": len(items),
        "items": items,
    }


@stats_router.get("/stats/comparativa-anio")
def stats_comparativa_anio(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R383 P1: comparativa este año vs año anterior, mes a mes.

    Para cada mes (1..12) devuelve creadas y valor_objetado
    de este año y del anterior, con delta_pct. Útil para
    informe ejecutivo Y-over-Y.
    """
    from datetime import timezone

    ahora = ahora_utc()
    year_actual = ahora.year
    year_anterior = year_actual - 1

    rows = db.query(GlosaRecord).filter(GlosaRecord.creado_en.isnot(None)).all()

    actual: dict[int, dict] = {m: {"count": 0, "valor": 0.0} for m in range(1, 13)}
    anterior: dict[int, dict] = {m: {"count": 0, "valor": 0.0} for m in range(1, 13)}
    for g in rows:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        m = cre.month
        v = float(g.valor_objetado or 0)
        if cre.year == year_actual:
            actual[m]["count"] += 1
            actual[m]["valor"] += v
        elif cre.year == year_anterior:
            anterior[m]["count"] += 1
            anterior[m]["valor"] += v

    serie = []
    for m in range(1, 13):
        a = actual[m]
        p = anterior[m]
        delta_pct = None
        if p["count"]:
            delta_pct = round(100 * (a["count"] - p["count"]) / p["count"], 2)
        elif a["count"] > 0:
            delta_pct = 100.0
        serie.append(
            {
                "mes": m,
                "actual_count": a["count"],
                "actual_valor": int(a["valor"]),
                "anterior_count": p["count"],
                "anterior_valor": int(p["valor"]),
                "delta_count_pct": delta_pct,
            }
        )

    return {
        "year_actual": year_actual,
        "year_anterior": year_anterior,
        "serie": serie,
        "total_actual_count": sum(actual[m]["count"] for m in range(1, 13)),
        "total_anterior_count": sum(anterior[m]["count"] for m in range(1, 13)),
        "total_actual_valor": int(sum(actual[m]["valor"] for m in range(1, 13))),
        "total_anterior_valor": int(sum(anterior[m]["valor"] for m in range(1, 13))),
    }


@stats_router.post("/stats/tasas-pares-batch")
def stats_tasas_pares_batch(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R382 P1: tasas par (eps, codigo_glosa) en batch.

    Recibe `{"glosa_ids": [1, 2, 3, ...]}` y devuelve para
    cada una su tasa histórica del par sin N+1 queries.
    Pensado para que el frontend muestre badges de tasa
    en listas (Mis glosas, Historial, etc.).

    Por glosa devuelve: glosa_id, eps, codigo_glosa,
    tasa_par_pct (null si < 2 muestras), n_par.
    """
    ESTADOS_DECIDIDOS = ["LEVANTADA", "ACEPTADA", "RATIFICADA"]
    ids = payload.get("glosa_ids") or []
    if not isinstance(ids, list) or not ids:
        return {"items": []}
    ids = [int(x) for x in ids if isinstance(x, (int, float, str))][:200]

    glosas = db.query(GlosaRecord).filter(GlosaRecord.id.in_(ids)).all()
    if not glosas:
        return {"items": []}

    # Para cada glosa, encontrar par único; cargar el histórico de cada par
    pares_unicos = {
        ((g.eps or "").strip(), (g.codigo_glosa or "").strip())
        for g in glosas
        if g.eps and g.codigo_glosa
    }

    # Carga única de todo el histórico decidido relevante
    eps_set = {p[0] for p in pares_unicos}
    cod_set = {p[1] for p in pares_unicos}
    historico = (
        (
            db.query(GlosaRecord)
            .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
            .filter(GlosaRecord.eps.in_(eps_set))
            .filter(GlosaRecord.codigo_glosa.in_(cod_set))
            .all()
        )
        if pares_unicos
        else []
    )

    par_idx: dict[tuple, dict] = {}
    for h in historico:
        k = ((h.eps or "").strip(), (h.codigo_glosa or "").strip())
        if k not in pares_unicos:
            continue
        b = par_idx.setdefault(k, {"dec": 0, "lev": 0})
        b["dec"] += 1
        if (h.estado or "").upper() == "LEVANTADA":
            b["lev"] += 1

    items = []
    for g in glosas:
        k = ((g.eps or "").strip(), (g.codigo_glosa or "").strip())
        b = par_idx.get(k)
        if not b or b["dec"] < 2:
            tasa = None
            n = b["dec"] if b else 0
        else:
            tasa = round(100 * b["lev"] / b["dec"], 2)
            n = b["dec"]
        items.append(
            {
                "glosa_id": g.id,
                "eps": k[0],
                "codigo_glosa": k[1],
                "tasa_par_pct": tasa,
                "n_par": n,
            }
        )

    return {"total": len(items), "items": items}


@stats_router.get("/stats/eps-perfil")
def stats_eps_perfil(
    eps: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Perfil estadístico por EPS — qué tan bien le va al HUS contra ella
    históricamente, y qué tono le funciona mejor.

    Si `eps` se pasa, devuelve solo esa entidad. Si no, top 30 por volumen.
    Cada item:
      - eps_norm: nombre normalizado para mostrar
      - n_decididas: total con decision_eps registrada
      - n_levantadas: cuántas le ganamos
      - tasa_pct: levantamiento sobre total decididas
      - tono_recomendado: heurística simple basada en perfil HUS
      - codigos_top: top 5 códigos glosa más frecuentes con tasa par
    """
    from app.services import pagador_normalizer

    q = db.query(GlosaRecord).filter(
        GlosaRecord.estado.in_(["LEVANTADA", "ACEPTADA", "RATIFICADA"])
    )
    if eps:
        q = q.filter(GlosaRecord.eps.ilike(f"%{eps.strip()}%"))
    glosas = q.limit(20000).all()

    perfiles: dict[str, dict] = {}
    for g in glosas:
        clave = pagador_normalizer.nombre_corto(g.eps or "") or (g.eps or "—")
        p = perfiles.setdefault(
            clave,
            {
                "n_decididas": 0,
                "n_levantadas": 0,
                "n_aceptadas": 0,
                "n_ratificadas": 0,
                "valor_total": 0.0,
                "valor_recuperado": 0.0,
                "codigos": {},
            },
        )
        p["n_decididas"] += 1
        e = (g.estado or "").upper()
        if e == "LEVANTADA":
            p["n_levantadas"] += 1
            p["valor_recuperado"] += float(g.valor_recuperado or g.valor_objetado or 0)
        elif e == "ACEPTADA":
            p["n_aceptadas"] += 1
        elif e == "RATIFICADA":
            p["n_ratificadas"] += 1
        p["valor_total"] += float(g.valor_objetado or 0)
        cod = (g.codigo_glosa or "").upper().strip()
        if cod:
            cod_b = p["codigos"].setdefault(cod, {"n": 0, "lev": 0})
            cod_b["n"] += 1
            if e == "LEVANTADA":
                cod_b["lev"] += 1

    def _tono_recomendado(p: dict) -> dict:
        n = p["n_decididas"]
        if n < 5:
            return {
                "tono": "conciliador",
                "razon": "Sin datos suficientes — tono conciliador por defecto.",
                "confianza": "baja",
            }
        tasa = (p["n_levantadas"] / n) * 100
        if tasa >= 65:
            return {
                "tono": "conciliador",
                "razon": f"Esta EPS levanta el {tasa:.0f}% de las glosas — el tono conciliador funciona bien.",
                "confianza": "alta",
            }
        if tasa <= 35:
            return {
                "tono": "firme",
                "razon": f"Esta EPS solo levanta el {tasa:.0f}% — tono firme con citas normativas reforzadas.",
                "confianza": "alta",
            }
        return {
            "tono": "neutral",
            "razon": f"Tasa intermedia ({tasa:.0f}%) — tono neutral con argumento técnico claro.",
            "confianza": "media",
        }

    items = []
    for clave, p in perfiles.items():
        n = p["n_decididas"]
        if n == 0:
            continue
        tasa = round(100 * p["n_levantadas"] / n, 1)
        codigos_top = sorted(p["codigos"].items(), key=lambda kv: kv[1]["n"], reverse=True)[:5]
        items.append(
            {
                "eps": clave,
                "n_decididas": n,
                "n_levantadas": p["n_levantadas"],
                "n_ratificadas": p["n_ratificadas"],
                "n_aceptadas": p["n_aceptadas"],
                "tasa_pct": tasa,
                "valor_total": int(p["valor_total"]),
                "valor_recuperado": int(p["valor_recuperado"]),
                "tono_recomendado": _tono_recomendado(p),
                "codigos_top": [
                    {
                        "codigo": k,
                        "n": v["n"],
                        "tasa_par_pct": round(100 * v["lev"] / v["n"], 1) if v["n"] >= 2 else None,
                    }
                    for k, v in codigos_top
                ],
            }
        )

    items.sort(key=lambda x: x["n_decididas"], reverse=True)
    return {"total": len(items), "items": items[:30]}


@stats_router.get("/stats/eps-totales-snapshot")
def stats_eps_totales_snapshot(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R331 P1: snapshot tabular único por EPS de totales.

    Tabla compacta para vista de referencia rápida.
    Por EPS:
      - count_total, count_abiertas, count_cerradas
      - valor_objetado_total
      - valor_recuperado_total
      - saldo_total
      - tasa_levantamiento_pct (sobre cerradas)

    Útil para grilla de referencia en dashboards
    operacionales.
    """
    rows = db.query(GlosaRecord).filter(GlosaRecord.eps.isnot(None)).all()

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    bucket: dict[str, dict] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(
            eps,
            {
                "total": 0,
                "abiertas": 0,
                "lev": 0,
                "dec": 0,
                "obj": 0.0,
                "rec": 0.0,
                "saldo": 0.0,
            },
        )
        b["total"] += 1
        b["obj"] += float(g.valor_objetado or 0)
        b["rec"] += float(g.valor_recuperado or 0)
        b["saldo"] += float(g.saldo_factura or 0)
        estado = (g.estado or "").upper()
        if estado not in ESTADOS_CERRADOS:
            b["abiertas"] += 1
        if estado in ESTADOS_DECIDIDOS:
            b["dec"] += 1
        if estado == "LEVANTADA":
            b["lev"] += 1

    items = []
    for eps, b in bucket.items():
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        items.append(
            {
                "eps": eps,
                "count_total": b["total"],
                "count_abiertas": b["abiertas"],
                "count_cerradas": b["total"] - b["abiertas"],
                "valor_objetado_total": int(b["obj"]),
                "valor_recuperado_total": int(b["rec"]),
                "saldo_total": int(b["saldo"]),
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["count_total"], reverse=True)

    return {
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/glosas-grandes-perdidas")
def stats_glosas_grandes_perdidas(
    umbral: float = Query(5_000_000, ge=10_000),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R330 P1: glosas de alto valor que terminaron ratificadas.

    Lista las glosas con valor_objetado >= umbral que
    terminaron en RATIFICADA o ACEPTADA (HUS perdió).
    Útil para análisis post-mortem: ¿qué casos grandes
    perdimos? ¿por qué?

    Ordenado DESC por valor_objetado.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(["RATIFICADA", "ACEPTADA"]))
        .filter(GlosaRecord.valor_objetado >= float(umbral))
        .order_by(GlosaRecord.valor_objetado.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for g in rows:
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "estado": g.estado,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "valor_aceptado": int(float(g.valor_aceptado or 0)),
                "gestor_nombre": g.gestor_nombre,
                "fecha_decision_eps": (
                    g.fecha_decision_eps.isoformat() if g.fecha_decision_eps else None
                ),
            }
        )

    return {
        "umbral": int(umbral),
        "total_grandes_perdidas": len(items),
        "valor_total_perdido": sum(it["valor_aceptado"] for it in items),
        "items": items,
    }


@stats_router.get("/stats/auditor-emails-distribucion")
def stats_auditor_emails_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R327 P1: distribución por `auditor_email`.

    Diferente a gestor_nombre (campo libre del Excel):
    auditor_email es el email del usuario asignado en la
    plataforma. Ambos campos pueden coexistir; este
    endpoint usa solo auditor_email.

    Solo coordinador/admin (datos sensibles). Por
    auditor_email: total, abiertas, decididas,
    valor_objetado_total.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.auditor_email.isnot(None))
        .filter(GlosaRecord.auditor_email != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        email = (g.auditor_email or "").strip()
        if not email:
            continue
        b = bucket.setdefault(
            email,
            {
                "total": 0,
                "abiertas": 0,
                "decididas": 0,
                "valor": 0.0,
            },
        )
        b["total"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        estado = (g.estado or "").upper()
        if estado not in ESTADOS_CERRADOS:
            b["abiertas"] += 1
        if estado in ESTADOS_DECIDIDOS:
            b["decididas"] += 1

    items = []
    for email, b in bucket.items():
        items.append(
            {
                "auditor_email": email,
                "total": b["total"],
                "abiertas": b["abiertas"],
                "decididas": b["decididas"],
                "valor_objetado_total": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["total"], reverse=True)

    return {
        "total_auditores": len(items),
        "items": items,
    }


@stats_router.get("/stats/factura-resumen")
def stats_factura_resumen(
    factura: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R325 P1: drill-down de TODAS las glosas de una factura.

    Drill-down operacional: para una factura específica,
    muestra todas las glosas con estado, código, valor.
    Útil al revisar una factura disputada.

    Devuelve resumen y lista detallada.
    """
    factura_q = (factura or "").strip()
    if not factura_q:
        return {"factura": "", "glosas": []}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.factura == factura_q)
        .order_by(GlosaRecord.creado_en.asc())
        .all()
    )

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = sum(1 for g in rows if (g.estado or "").upper() not in ESTADOS_CERRADOS)
    obj_total = sum(float(g.valor_objetado or 0) for g in rows)
    rec_total = sum(float(g.valor_recuperado or 0) for g in rows)

    items = []
    for g in rows:
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "codigo_glosa": g.codigo_glosa,
                "estado": g.estado,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "valor_recuperado": int(float(g.valor_recuperado or 0)),
                "gestor_nombre": g.gestor_nombre,
                "creado_en": (g.creado_en.isoformat() if g.creado_en else None),
            }
        )

    return {
        "factura": factura_q,
        "count_total": len(rows),
        "count_abiertas": abiertas,
        "count_cerradas": len(rows) - abiertas,
        "valor_objetado_total": int(obj_total),
        "valor_recuperado_total": int(rec_total),
        "glosas": items,
    }


@stats_router.get("/stats/edad-promedio-por-estado")
def stats_edad_promedio_por_estado(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R324 P1: edad promedio (días desde creado_en) por estado.

    Para cada valor del campo `estado`, cuál es la edad
    promedio de las glosas que están en él. Distingue
    entre estados normales (corta edad) y "atascos"
    (estados donde glosas envejecen mucho).
    """
    from datetime import timezone

    rows = db.query(GlosaRecord).all()
    ahora = ahora_utc()

    bucket: dict[str, list[int]] = {}
    for g in rows:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        edad = (ahora - cre).days
        estado = (g.estado or "?").upper()
        bucket.setdefault(estado, []).append(edad)

    items = []
    for estado, ages in bucket.items():
        n = len(ages)
        prom = round(sum(ages) / n, 1) if n else 0.0
        ord_a = sorted(ages)
        med = ord_a[n // 2]
        items.append(
            {
                "estado": estado,
                "count": n,
                "edad_promedio_dias": prom,
                "edad_mediana_dias": med,
                "edad_max_dias": max(ages),
            }
        )
    items.sort(key=lambda x: x["edad_promedio_dias"], reverse=True)

    return {
        "items": items,
    }


@stats_router.get("/stats/gestor-vencidas-distribucion")
def stats_gestor_vencidas_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R323 P1: distribución de glosas vencidas por gestor.

    Solo coordinador/admin (datos sensibles del equipo).
    Por gestor: count de vencidas, criticas y total
    abiertas.

    Útil para identificar gestores que necesitan apoyo
    o redistribución de carga.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in abiertas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        b = bucket.setdefault(
            gestor,
            {
                "total": 0,
                "vencidas": 0,
                "criticas": 0,
            },
        )
        b["total"] += 1
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            b["vencidas"] += 1
        elif dr <= 3:
            b["criticas"] += 1

    items = []
    for gestor, b in bucket.items():
        pct = round(100 * b["vencidas"] / b["total"], 2) if b["total"] else 0.0
        items.append(
            {
                "gestor": gestor,
                "total_abiertas": b["total"],
                "vencidas": b["vencidas"],
                "criticas": b["criticas"],
                "pct_vencidas": pct,
            }
        )
    items.sort(key=lambda x: x["vencidas"], reverse=True)

    return {
        "total_gestores": len(items),
        "items": items,
    }


@stats_router.get("/stats/glosas-sin-fecha-decision")
def stats_glosas_sin_fecha_decision(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R322 P1: glosas en estados decididos pero sin
    `fecha_decision_eps` poblada.

    Si una glosa está en LEVANTADA, RATIFICADA o ACEPTADA
    pero su fecha_decision_eps es null, hay un dato
    incompleto. Esto afecta cálculos de tiempo y SLA.

    Útil para campañas de calidad de datos: completar
    fechas históricas.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.fecha_decision_eps.is_(None))
        .all()
    )

    items = []
    for g in rows:
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "creado_en": (g.creado_en.isoformat() if g.creado_en else None),
            }
        )
    items.sort(key=lambda x: x["valor_objetado"], reverse=True)

    return {
        "total_sin_fecha_decision": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/eps-pacientes-distintos")
def stats_eps_pacientes_distintos(
    min_glosas: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R321 P1: cobertura de pacientes por EPS.

    Para cada EPS, cuántos pacientes distintos hay con
    glosas. Útil para detectar EPS que afectan a pocos
    pacientes vs muchas (concentración por paciente).

    Por EPS:
      - count_glosas
      - pacientes_distintos
      - ratio_glosas_paciente (count_glosas/pacientes)
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.isnot(None))
        .filter(GlosaRecord.paciente.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        paciente = (g.paciente or "").strip()
        if not eps or not paciente:
            continue
        b = bucket.setdefault(eps, {"count": 0, "pacientes": set()})
        b["count"] += 1
        b["pacientes"].add(paciente)

    items = []
    for eps, b in bucket.items():
        if b["count"] < min_glosas:
            continue
        n_pac = len(b["pacientes"])
        ratio = round(b["count"] / n_pac, 2) if n_pac else 0.0
        items.append(
            {
                "eps": eps,
                "count_glosas": b["count"],
                "pacientes_distintos": n_pac,
                "ratio_glosas_paciente": ratio,
            }
        )
    items.sort(key=lambda x: x["pacientes_distintos"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/progreso-equipo-mes")
def stats_progreso_equipo_mes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R320 P1: progreso del equipo en el mes en curso.

    Snapshot de balance de mes para todo el equipo:
      - creadas_mes
      - cerradas_mes
      - levantadas_mes
      - balance_neto (cerradas - creadas)
      - tasa_cierre_pct (cerradas / creadas)
      - valor_recuperado_mes

    Útil para landing del dashboard del equipo.
    """

    inicio_mes = ahora_utc().replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    creadas = db.query(GlosaRecord).filter(GlosaRecord.creado_en >= inicio_mes).all()
    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= inicio_mes)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    n_creadas = len(creadas)
    n_cerradas = len(cerradas)
    n_levantadas = sum(1 for g in cerradas if (g.estado or "").upper() == "LEVANTADA")
    rec_total = sum(float(g.valor_recuperado or 0) for g in cerradas)
    obj_creadas = sum(float(g.valor_objetado or 0) for g in creadas)

    balance = n_cerradas - n_creadas
    tasa_cierre = round(100 * n_cerradas / n_creadas, 2) if n_creadas else 0.0

    return {
        "mes": inicio_mes.strftime("%Y-%m"),
        "creadas_mes": n_creadas,
        "cerradas_mes": n_cerradas,
        "levantadas_mes": n_levantadas,
        "balance_neto": balance,
        "tasa_cierre_pct": tasa_cierre,
        "valor_recuperado_mes": int(rec_total),
        "valor_creado_mes": int(obj_creadas),
    }


@stats_router.get("/stats/recientes-decididas")
def stats_recientes_decididas(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R319 P1: últimas N glosas decididas (live feed).

    Lista las decisiones EPS más recientes con todo el
    detalle relevante. Útil como feed operacional en
    tiempo real.

    Ordena DESC por fecha_decision_eps.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .order_by(GlosaRecord.fecha_decision_eps.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for g in rows:
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "estado": g.estado,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "valor_recuperado": int(float(g.valor_recuperado or 0)),
                "gestor_nombre": g.gestor_nombre,
                "fecha_decision_eps": (
                    g.fecha_decision_eps.isoformat() if g.fecha_decision_eps else None
                ),
            }
        )

    return {
        "limit": int(limit),
        "items": items,
    }


@stats_router.get("/stats/devoluciones-resumen")
def stats_devoluciones_resumen(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R317 P1: resumen de glosas marcadas como devolución.

    Una "devolución" (es_devolucion='1' o 'S') es una
    objeción donde la EPS pide que se reradique la
    factura por motivos formales, distinto de una
    glosa propiamente dicha.

    Métricas:
      - count_total_devoluciones
      - count_abiertas, count_cerradas
      - valor_objetado_total
      - top_eps con más devoluciones

    Útil para identificar EPS que abusan de la devolución.
    """
    rows = db.query(GlosaRecord).filter(GlosaRecord.es_devolucion.in_(["1", "S", "Y"])).all()

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    total = len(rows)
    abiertas = sum(1 for g in rows if (g.estado or "").upper() not in ESTADOS_CERRADOS)
    valor = sum(float(g.valor_objetado or 0) for g in rows)

    por_eps: dict[str, int] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if eps:
            por_eps[eps] = por_eps.get(eps, 0) + 1

    top_eps = sorted(
        por_eps.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    return {
        "count_total_devoluciones": total,
        "count_abiertas": abiertas,
        "count_cerradas": total - abiertas,
        "valor_objetado_total": int(valor),
        "top_eps": [{"eps": e, "count": c} for e, c in top_eps],
    }


@stats_router.get("/stats/dictamenes-largos-top")
def stats_dictamenes_largos_top(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R314 P1: top glosas con dictamen más largo.

    Diferente a /stats/dictamenes-cortos: aquí los más
    elaborados. Útil para identificar casos de alta
    complejidad o dictámenes ejemplares (best practice).

    Por glosa:
      - id, eps, codigo_glosa, valor_objetado
      - dictamen_len
      - estado y resultado (si decidida)
    """
    rows = db.query(GlosaRecord).filter(GlosaRecord.dictamen.isnot(None)).all()

    items = []
    for g in rows:
        dlen = len(g.dictamen or "")
        if dlen < 50:
            continue
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "dictamen_len": dlen,
                "estado": g.estado,
                "gestor_nombre": g.gestor_nombre,
            }
        )
    items.sort(key=lambda x: x["dictamen_len"], reverse=True)

    return {
        "limit": int(limit),
        "total_glosas_evaluadas": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/cobertura-asignacion")
def stats_cobertura_asignacion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R313 P1: cobertura de asignación de campos críticos.

    Para campos que indican "quién está manejando esto":
    qué porcentaje de glosas los tienen poblados. Métrica
    de salud de datos del sistema.

    Campos evaluados:
      - gestor_nombre
      - auditor_email
      - profesional_medico
      - codigo_respuesta
      - fecha_decision_eps

    Útil para identificar lagunas: "30% de glosas no
    tiene gestor — ¿por qué?".
    """
    rows = db.query(GlosaRecord).all()
    n = len(rows)

    if n == 0:
        return {
            "total_glosas": 0,
            "items": [],
        }

    counts = {
        "gestor_nombre": 0,
        "auditor_email": 0,
        "profesional_medico": 0,
        "codigo_respuesta": 0,
        "fecha_decision_eps": 0,
    }

    for g in rows:
        if g.gestor_nombre and g.gestor_nombre.strip():
            counts["gestor_nombre"] += 1
        if g.auditor_email and g.auditor_email.strip():
            counts["auditor_email"] += 1
        if g.profesional_medico and g.profesional_medico.strip():
            counts["profesional_medico"] += 1
        if g.codigo_respuesta and g.codigo_respuesta.strip():
            counts["codigo_respuesta"] += 1
        if g.fecha_decision_eps:
            counts["fecha_decision_eps"] += 1

    items = []
    for campo, c in counts.items():
        items.append(
            {
                "campo": campo,
                "count": c,
                "pct_cobertura": round(100 * c / n, 2),
                "faltantes": n - c,
            }
        )

    return {
        "total_glosas": n,
        "items": items,
    }


@stats_router.get("/stats/recuperacion-tasa-mensual")
def stats_recuperacion_tasa_mensual(
    meses: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R311 P1: tasa de recuperación monetaria mes a mes.

    Diferente a /stats/recuperacion-mensual (suma absoluta)
    y /stats/tasa-levantamiento-mensual (sobre count):
    aquí mes a mes el ratio
    valor_recuperado / valor_objetado.

    Útil para ver si HUS está recuperando un % mayor o
    menor de lo objetado con el tiempo.
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= desde)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    por_mes: dict[str, dict] = {}
    for g in glosas:
        f = g.fecha_decision_eps
        if f and f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if not f:
            continue
        k = f.strftime("%Y-%m")
        b = por_mes.setdefault(k, {"obj": 0.0, "rec": 0.0})
        b["obj"] += float(g.valor_objetado or 0)
        b["rec"] += float(g.valor_recuperado or 0)

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        tasa = round(100 * b["rec"] / b["obj"], 2) if b["obj"] else 0.0
        serie.append(
            {
                "mes": k,
                "valor_objetado": int(b["obj"]),
                "valor_recuperado": int(b["rec"]),
                "tasa_recuperacion_pct": tasa,
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_meses": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/fecha-objecion-mensual")
def stats_fecha_objecion_mensual(
    meses: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R309 P1: serie mensual por `fecha_objecion_eps`.

    Diferente a /stats/serie-mensual-cantidad (basado en
    creado_en — fecha de carga al sistema): aquí usamos
    `fecha_objecion_eps`, la fecha real en que la EPS
    emitió la objeción según el documento DGH.

    Permite ver el patrón temporal real de las EPS, no
    el de la operación interna HUS.
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    rows = db.query(GlosaRecord).filter(GlosaRecord.fecha_objecion_eps >= desde).all()

    por_mes: dict[str, dict] = {}
    for g in rows:
        f = g.fecha_objecion_eps
        if f and f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if not f:
            continue
        k = f.strftime("%Y-%m")
        b = por_mes.setdefault(k, {"count": 0, "valor": 0.0})
        b["count"] += 1
        b["valor"] += float(g.valor_objetado or 0)

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        serie.append(
            {
                "mes": k,
                "count_objetadas": b["count"],
                "valor_objetado_total": int(b["valor"]),
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_meses": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/tipo-glosa-tasa")
def stats_tipo_glosa_tasa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R308 P1: tasa de levantamiento por tipo de glosa.

    Por prefijo de codigo_glosa (TA, SO, AU, CO, CL, PE,
    FA, SE, IN, ME, EX), cuál es la tasa histórica de
    levantamiento. Útil para identificar tipos donde HUS
    pierde sistemáticamente.
    """
    PREFIJOS = ["TA", "SO", "AU", "CO", "CL", "PE", "FA", "SE", "IN", "ME", "EX"]

    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        codigo = (g.codigo_glosa or "").strip().upper()
        if len(codigo) < 2:
            continue
        prefijo = codigo[:2]
        b = bucket.setdefault(
            prefijo,
            {
                "dec": 0,
                "lev": 0,
            },
        )
        b["dec"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["lev"] += 1

    items = []
    for p in PREFIJOS:
        b = bucket.get(p, {"dec": 0, "lev": 0})
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        items.append(
            {
                "tipo": p,
                "decididas": b["dec"],
                "levantadas": b["lev"],
                "tasa_levantamiento_pct": tasa,
            }
        )

    return {
        "total_decididas": sum(it["decididas"] for it in items),
        "items": items,
    }


@stats_router.get("/stats/saldo-evolucion-mensual")
def stats_saldo_evolucion_mensual(
    meses: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R307 P1: evolución mensual del saldo pendiente acumulado.

    Para cada mes, cuál era el saldo total pendiente al
    final del mes. Calculado sobre todas las glosas
    creadas hasta ese mes que aún estaban abiertas o
    cuyo cierre fue posterior.

    Métrica para evolución: ¿el saldo pendiente está
    creciendo o disminuyendo?
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(meses) * 31)

    rows = db.query(GlosaRecord).all()

    serie: dict[str, dict] = {}
    for g in rows:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        if cre < desde:
            continue
        k = cre.strftime("%Y-%m")
        b = serie.setdefault(
            k,
            {
                "creadas": 0,
                "saldo": 0.0,
            },
        )
        b["creadas"] += 1
        b["saldo"] += float(g.saldo_factura or 0)

    items = []
    for k in sorted(serie.keys()):
        b = serie[k]
        items.append(
            {
                "mes": k,
                "glosas_creadas": b["creadas"],
                "saldo_creado": int(b["saldo"]),
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_meses": len(items),
        "serie": items,
    }


@stats_router.get("/stats/factura-distribucion-glosas")
def stats_factura_distribucion_glosas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R306 P1: distribución del número de glosas por factura.

    Cuenta cuántas facturas tienen 1, 2, 3, ... 10+ glosas
    asociadas. Útil para entender el patrón:
      - ¿La mayoría de facturas tienen 1 sola glosa?
      - ¿Hay facturas con 5+ glosas (objeción múltiple)?

    Devuelve histograma de buckets.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "N/A")
        .all()
    )

    counts: dict[str, int] = {}
    for g in rows:
        f = (g.factura or "").strip()
        if not f:
            continue
        counts[f] = counts.get(f, 0) + 1

    buckets = {
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 0,
        "5": 0,
        "6-10": 0,
        "10+": 0,
    }
    for n in counts.values():
        if n == 1:
            buckets["1"] += 1
        elif n == 2:
            buckets["2"] += 1
        elif n == 3:
            buckets["3"] += 1
        elif n == 4:
            buckets["4"] += 1
        elif n == 5:
            buckets["5"] += 1
        elif n <= 10:
            buckets["6-10"] += 1
        else:
            buckets["10+"] += 1

    items = [{"glosas_por_factura": k, "count_facturas": v} for k, v in buckets.items()]

    total_facturas = len(counts)
    total_glosas = sum(counts.values())
    promedio = round(total_glosas / total_facturas, 2) if total_facturas else 0.0

    return {
        "total_facturas": total_facturas,
        "total_glosas": total_glosas,
        "promedio_glosas_por_factura": promedio,
        "buckets": items,
    }


@stats_router.get("/stats/codigo-glosa-eps-cruzado")
def stats_codigo_glosa_eps_cruzado(
    codigo: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R305 P1: para un codigo_glosa, qué EPS lo usan más.

    Reverso de /stats/eps-codigo-pareja. Dado un código,
    devuelve la lista de EPS que lo usan, con su frecuencia
    y tasa de levantamiento.

    Útil para: "¿qué EPS golpea más con TA0801?".
    """
    codigo_q = (codigo or "").strip()
    if not codigo_q:
        return {"codigo_glosa": "", "items": []}

    rows = db.query(GlosaRecord).filter(GlosaRecord.codigo_glosa.ilike(codigo_q)).all()

    bucket: dict[str, dict] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(
            eps,
            {
                "count": 0,
                "lev": 0,
                "dec": 0,
                "valor": 0.0,
            },
        )
        b["count"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        estado = (g.estado or "").upper()
        if estado in ("LEVANTADA", "RATIFICADA", "ACEPTADA"):
            b["dec"] += 1
        if estado == "LEVANTADA":
            b["lev"] += 1

    items = []
    for eps, b in bucket.items():
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        items.append(
            {
                "eps": eps,
                "count": b["count"],
                "decididas": b["dec"],
                "levantadas": b["lev"],
                "tasa_levantamiento_pct": tasa,
                "valor_objetado_total": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "codigo_glosa": codigo_q,
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-tiempo-en-pipeline")
def stats_eps_tiempo_en_pipeline(
    min_glosas: int = Query(3, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R304 P1: tiempo promedio de glosas abiertas en pipeline por EPS.

    Para cada EPS, calcula los días que tienen las glosas
    abiertas desde su `creado_en`. Diferente a
    /stats/eps-velocidad-respuesta (mide cierres pasados):
    aquí mide el "envejecimiento" actual del backlog.

    Por EPS:
      - count_abiertas
      - antiguedad_promedio_dias
      - antiguedad_max_dias
      - saldo_pendiente_total

    Ordenado DESC por antiguedad_promedio_dias.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    ahora = ahora_utc()
    bucket: dict[str, dict] = {}
    for g in abiertas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        antig = (ahora - cre).days
        b = bucket.setdefault(
            eps,
            {
                "count": 0,
                "suma": 0,
                "max": 0,
                "saldo": 0.0,
            },
        )
        b["count"] += 1
        b["suma"] += antig
        b["max"] = max(b["max"], antig)
        b["saldo"] += float(g.saldo_factura or 0)

    items = []
    for eps, b in bucket.items():
        if b["count"] < min_glosas:
            continue
        prom = round(b["suma"] / b["count"], 1)
        items.append(
            {
                "eps": eps,
                "count_abiertas": b["count"],
                "antiguedad_promedio_dias": prom,
                "antiguedad_max_dias": b["max"],
                "saldo_pendiente_total": int(b["saldo"]),
            }
        )
    items.sort(key=lambda x: x["antiguedad_promedio_dias"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/prioridad-distribucion")
def stats_prioridad_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R302 P1: distribución por nivel de prioridad.

    Por valor del campo `prioridad`:
      - count, valor_objetado_total, abiertas
      - pct sobre el total

    Útil para ver el balance del backlog por urgencia.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = db.query(GlosaRecord).all()

    bucket: dict[str, dict] = {}
    for g in rows:
        p = (g.prioridad or "NORMAL").upper()
        b = bucket.setdefault(
            p,
            {
                "count": 0,
                "valor": 0.0,
                "abiertas": 0,
            },
        )
        b["count"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        if (g.estado or "").upper() not in ESTADOS_CERRADOS:
            b["abiertas"] += 1

    total = sum(b["count"] for b in bucket.values())

    items = []
    for p, b in bucket.items():
        items.append(
            {
                "prioridad": p,
                "count": b["count"],
                "abiertas": b["abiertas"],
                "valor_objetado_total": int(b["valor"]),
                "pct": (round(100 * b["count"] / total, 2) if total else 0.0),
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_glosas": total,
        "items": items,
    }


@stats_router.get("/stats/workflow-state-distribucion")
def stats_workflow_state_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R301 P1: distribución por workflow_state.

    `workflow_state` es el estado interno del flujo HUS
    (BORRADOR, EN_ANALISIS, EN_REVISION, etc.) distinto
    de `estado` (que sigue el ciclo formal con la EPS).

    Útil para ver el pipeline interno: cuántas glosas
    están en cada paso del proceso.
    """

    rows = (
        db.query(
            GlosaRecord.workflow_state,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
        )
        .group_by(GlosaRecord.workflow_state)
        .all()
    )

    items = []
    for state, count, valor in rows:
        items.append(
            {
                "workflow_state": state or "SIN_ESTADO",
                "count": int(count),
                "valor_objetado_total": int(float(valor or 0)),
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    total = sum(it["count"] for it in items)
    for it in items:
        it["pct"] = round(100 * it["count"] / total, 2) if total else 0.0

    return {
        "total_glosas": total,
        "items": items,
    }


@stats_router.get("/stats/dashboard-cobranza")
def stats_dashboard_cobranza(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R300 P1: dashboard único de cobranza (single-call).

    Combina en una sola respuesta los datos clave para el
    panel de cobranza:
      - kpis: saldo_total, valor_factura_total, count_abiertas
      - aging: distribución por antigüedad
      - top_eps: 5 EPS con mayor saldo
      - top_facturas: 5 facturas con mayor saldo

    Reduce latencia (de ~5 calls a 1) para landing del
    coordinador de cobranza. Hito R300.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    BUCKETS = [
        ("0-30", 0, 30),
        ("31-60", 31, 60),
        ("61-90", 61, 90),
        ("91-180", 91, 180),
        (">180", 181, None),
    ]

    ahora = ahora_utc()
    bandas = {n: {"count": 0, "saldo": 0.0} for n, _, _ in BUCKETS}
    saldo_total = 0.0
    valor_total = 0.0
    por_eps: dict[str, float] = {}
    por_factura: dict[str, dict] = {}

    for g in abiertas:
        saldo = float(g.saldo_factura or 0)
        valor = float(g.valor_factura or 0)
        saldo_total += saldo
        valor_total += valor

        eps = (g.eps or "").strip()
        if eps:
            por_eps[eps] = por_eps.get(eps, 0.0) + saldo

        factura = (g.factura or "").strip()
        if factura and factura != "N/A":
            f = por_factura.setdefault(
                factura,
                {
                    "saldo": 0.0,
                    "eps": eps,
                },
            )
            f["saldo"] += saldo

        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if cre:
            antig = (ahora - cre).days
            for n, lo, hi in BUCKETS:
                if antig >= lo and (hi is None or antig <= hi):
                    bandas[n]["count"] += 1
                    bandas[n]["saldo"] += saldo
                    break

    top_eps = sorted(
        por_eps.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:5]
    top_facturas = sorted(
        por_factura.items(),
        key=lambda x: x[1]["saldo"],
        reverse=True,
    )[:5]

    return {
        "kpis": {
            "count_abiertas": len(abiertas),
            "saldo_total": int(saldo_total),
            "valor_factura_total": int(valor_total),
        },
        "aging": [
            {"rango_dias": n, "count": b["count"], "saldo": int(b["saldo"])}
            for n, b in bandas.items()
        ],
        "top_eps": [{"eps": e, "saldo": int(s)} for e, s in top_eps],
        "top_facturas": [
            {"factura": f, "eps": d["eps"], "saldo": int(d["saldo"])} for f, d in top_facturas
        ],
    }


@stats_router.get("/stats/sin-actividad-reciente")
def stats_sin_actividad_reciente(
    dias: int = Query(30, ge=7, le=180),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R298 P1: glosas abiertas sin actividad audit reciente.

    Una glosa abierta sin ningún evento audit_log en los
    últimos N días es candidata a "estancada". Útil para
    detectar casos olvidados que requieren atención.

    Solo abiertas, ordenado por valor_objetado DESC.
    """


    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    desde = ahora_utc() - timedelta(days=int(dias))
    glosas_con_actividad = {
        row[0]
        for row in db.query(AuditLogRecord.registro_id)
        .filter(AuditLogRecord.tabla == "historial")
        .filter(AuditLogRecord.timestamp >= desde)
        .distinct()
        .all()
        if row[0]
    }

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    items = []
    for g in abiertas:
        if g.id in glosas_con_actividad:
            continue
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "dias_restantes": g.dias_restantes,
            }
        )
    items.sort(key=lambda x: x["valor_objetado"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "total_estancadas": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/decisiones-por-dia")
def stats_decisiones_por_dia(
    dias: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R297 P1: serie diaria de decisiones EPS.

    Para cada día de los últimos N, cuántas glosas fueron
    decididas (LEVANTADA, RATIFICADA, ACEPTADA con
    `fecha_decision_eps`).

    Útil para detectar picos diarios de actividad y
    planear cargas de equipo.
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(dias))
    glosas = db.query(GlosaRecord).filter(GlosaRecord.fecha_decision_eps >= desde).all()

    por_dia: dict[str, dict] = {}
    for g in glosas:
        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not dec:
            continue
        k = dec.strftime("%Y-%m-%d")
        b = por_dia.setdefault(
            k,
            {
                "total": 0,
                "lev": 0,
                "rat": 0,
                "ace": 0,
            },
        )
        b["total"] += 1
        estado = (g.estado or "").upper()
        if estado == "LEVANTADA":
            b["lev"] += 1
        elif estado == "RATIFICADA":
            b["rat"] += 1
        elif estado == "ACEPTADA":
            b["ace"] += 1

    serie = []
    for k in sorted(por_dia.keys()):
        b = por_dia[k]
        serie.append(
            {
                "fecha": k,
                "total": b["total"],
                "levantadas": b["lev"],
                "ratificadas": b["rat"],
                "aceptadas": b["ace"],
            }
        )

    return {
        "ventana_dias": int(dias),
        "total_dias_con_actividad": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/gestor-vs-eps-matriz")
def stats_gestor_vs_eps_matriz(
    top_gestores: int = Query(10, ge=2, le=30),
    top_eps: int = Query(10, ge=2, le=30),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R296 P1: matriz gestor × EPS de decisiones.

    Muestra qué gestor maneja qué EPS y con qué volumen.
    Útil para detectar asignaciones desbalanceadas:
      "Alice maneja toda SANITAS, nadie más sabe."

    Solo coordinador o admin (datos sensibles del equipo).

    Devuelve:
      - gestores: lista de top N gestores por volumen
      - eps: lista de top N EPS por volumen
      - matriz: dict[gestor][eps] = count_decididas
    """
    decididas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    total_g: dict[str, int] = {}
    total_e: dict[str, int] = {}
    matriz: dict[str, dict[str, int]] = {}

    for g in decididas:
        gestor = (g.gestor_nombre or "").strip()
        eps = (g.eps or "").strip()
        if not gestor or not eps:
            continue
        total_g[gestor] = total_g.get(gestor, 0) + 1
        total_e[eps] = total_e.get(eps, 0) + 1
        matriz.setdefault(gestor, {})
        matriz[gestor][eps] = matriz[gestor].get(eps, 0) + 1

    g_top = [
        g
        for g, _ in sorted(
            total_g.items(),
            key=lambda x: x[1],
            reverse=True,
        )[: int(top_gestores)]
    ]
    e_top = [
        e
        for e, _ in sorted(
            total_e.items(),
            key=lambda x: x[1],
            reverse=True,
        )[: int(top_eps)]
    ]

    matriz_filt = {}
    for gestor in g_top:
        matriz_filt[gestor] = {eps: matriz.get(gestor, {}).get(eps, 0) for eps in e_top}

    return {
        "gestores": g_top,
        "eps": e_top,
        "matriz": matriz_filt,
    }


@stats_router.get("/stats/dias-decision-promedio-mes")
def stats_dias_decision_promedio_mes(
    meses: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R295 P1: días promedio a la decisión por mes.

    Serie temporal: para cada mes (basado en
    `fecha_decision_eps`), cuál fue el promedio de días
    desde `creado_en` a la decisión. Útil para detectar
    si las EPS están tardando más o menos con el tiempo.

    Diferente a /stats/eps-velocidad-respuesta (por EPS):
    aquí agregado global por mes.
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    glosas = db.query(GlosaRecord).filter(GlosaRecord.fecha_decision_eps >= desde).all()

    por_mes: dict[str, list[int]] = {}
    for g in glosas:
        cre = g.creado_en
        dec = g.fecha_decision_eps
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not cre or not dec:
            continue
        dias = (dec - cre).days
        if dias < 0:
            continue
        k = dec.strftime("%Y-%m")
        por_mes.setdefault(k, []).append(dias)

    serie = []
    for k in sorted(por_mes.keys()):
        vals = por_mes[k]
        prom = round(sum(vals) / len(vals), 2)
        ord_v = sorted(vals)
        med = ord_v[len(vals) // 2]
        serie.append(
            {
                "mes": k,
                "count": len(vals),
                "promedio_dias": prom,
                "mediana_dias": med,
                "max_dias": max(vals),
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_meses": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/eps-diversidad-codigos")
def stats_eps_diversidad_codigos(
    min_glosas: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R293 P1: diversidad de códigos de glosa por EPS.

    Para cada EPS calcula cuántos códigos distintos
    `codigo_glosa` utiliza. EPS con muy pocos códigos
    distintos suelen ser "especializadas" (golpean
    siempre lo mismo); EPS con muchos códigos son
    "amplias" (atacan en muchos frentes).

    Por EPS:
      - count_glosas
      - codigos_distintos
      - ratio_diversidad (codigos / count_glosas)
      - top_3_codigos: lista de los 3 más usados

    Ordenado DESC por codigos_distintos.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.isnot(None))
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        codigo = (g.codigo_glosa or "").strip()
        if not eps or not codigo:
            continue
        b = bucket.setdefault(
            eps,
            {
                "count": 0,
                "codigos": {},
            },
        )
        b["count"] += 1
        b["codigos"][codigo] = b["codigos"].get(codigo, 0) + 1

    items = []
    for eps, b in bucket.items():
        if b["count"] < min_glosas:
            continue
        diversos = len(b["codigos"])
        ratio = round(diversos / b["count"], 3) if b["count"] else 0.0
        top3 = sorted(
            b["codigos"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        items.append(
            {
                "eps": eps,
                "count_glosas": b["count"],
                "codigos_distintos": diversos,
                "ratio_diversidad": ratio,
                "top_3_codigos": [{"codigo_glosa": c, "count": n} for c, n in top3],
            }
        )
    items.sort(key=lambda x: x["codigos_distintos"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/tipo-glosa-mensual")
def stats_tipo_glosa_mensual(
    meses: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R289 P1: serie mensual por tipo de glosa (prefijo Res. 2284).

    Diferente a /stats/por-tipo (snapshot global): aquí
    serie temporal mes-a-mes por prefijo (TA, SO, AU, CO,
    CL, PE, FA, SE, IN, ME, EX).

    Útil para detectar cuál tipo está creciendo:
      "Las glosas de soportes (SO) crecieron 200% este
       trimestre."
    """
    from datetime import timezone

    PREFIJOS = ["TA", "SO", "AU", "CO", "CL", "PE", "FA", "SE", "IN", "ME", "EX"]

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    por_mes: dict[str, dict] = {}
    for g in rows:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        codigo = (g.codigo_glosa or "").strip().upper()
        prefijo = codigo[:2] if len(codigo) >= 2 else "??"
        k = cre.strftime("%Y-%m")
        b = por_mes.setdefault(k, {p: 0 for p in PREFIJOS})
        b.setdefault(prefijo, 0)
        b[prefijo] += 1

    serie = []
    for k in sorted(por_mes.keys()):
        item = {"mes": k}
        item.update(por_mes[k])
        serie.append(item)

    return {
        "ventana_meses": int(meses),
        "prefijos": PREFIJOS,
        "serie": serie,
    }


@stats_router.get("/stats/glosas-recientes-eps")
def stats_glosas_recientes_eps(
    eps: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R288 P1: últimas N glosas de una EPS específica.

    Drill-down operacional: para una EPS dada, devuelve
    las N glosas más recientes con datos clave. Útil al
    comenzar revisión sectorial de una EPS.
    """
    eps_q = (eps or "").strip()
    if not eps_q:
        return {"eps": "", "items": []}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.ilike(eps_q))
        .order_by(GlosaRecord.creado_en.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for g in rows:
        items.append(
            {
                "glosa_id": g.id,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "estado": g.estado,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "creado_en": (g.creado_en.isoformat() if g.creado_en else None),
                "gestor_nombre": g.gestor_nombre,
            }
        )

    return {
        "eps": eps_q,
        "limit": int(limit),
        "items": items,
    }


@stats_router.get("/stats/codigo-respuesta-tendencia")
def stats_codigo_respuesta_tendencia(
    dias: int = Query(30, ge=7, le=90),
    min_glosas_actual: int = Query(3, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R286 P1: tendencia de uso del codigo_respuesta de HUS.

    Compara dos ventanas consecutivas de N días en el uso
    del campo `codigo_respuesta` (RE9501, RE9701, etc.).
    Útil para ver evolución de la estrategia de respuesta
    de la IPS:
      "Empezamos a usar RE9501 mucho más → ¿está
       funcionando?"

    Por código:
      - count_actual, count_previo
      - delta_abs, delta_pct
    """
    from datetime import timezone

    ahora = ahora_utc()
    corte_actual = ahora - timedelta(days=int(dias))
    corte_previo = ahora - timedelta(days=int(dias) * 2)

    actual: dict[str, int] = {}
    previo: dict[str, int] = {}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .filter(GlosaRecord.codigo_respuesta != "")
        .all()
    )

    for g in rows:
        codigo = (g.codigo_respuesta or "").strip()
        if not codigo:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        if cre >= corte_actual:
            actual[codigo] = actual.get(codigo, 0) + 1
        elif cre >= corte_previo:
            previo[codigo] = previo.get(codigo, 0) + 1

    todos = set(actual) | set(previo)
    items = []
    for codigo in todos:
        a = actual.get(codigo, 0)
        p = previo.get(codigo, 0)
        if a < min_glosas_actual:
            continue
        if p == 0:
            delta_pct = 100.0 if a > 0 else 0.0
        else:
            delta_pct = round(100 * (a - p) / p, 2)
        items.append(
            {
                "codigo_respuesta": codigo,
                "count_actual": a,
                "count_previo": p,
                "delta_abs": a - p,
                "delta_pct": delta_pct,
            }
        )
    items.sort(key=lambda x: x["delta_pct"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "min_glosas_actual": int(min_glosas_actual),
        "total_codigos": len(items),
        "items": items,
    }


@stats_router.get("/stats/decision-eps-tiempo-distribucion")
def stats_decision_eps_tiempo_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R285 P1: distribución del tiempo `creado_en` → `fecha_decision_eps`.

    Histograma de días que tarda la EPS en emitir
    decisión, en buckets de SLA Res. 2284/2023:
      - 0-15 (en plazo formal)
      - 16-30
      - 31-60
      - 61-90
      - >90 (extemporáneo grave)

    Solo glosas con fecha_decision_eps poblada.
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).filter(GlosaRecord.fecha_decision_eps.isnot(None)).all()

    BUCKETS = [
        ("0-15", 0, 15),
        ("16-30", 16, 30),
        ("31-60", 31, 60),
        ("61-90", 61, 90),
        (">90", 91, None),
    ]

    bandas = {nombre: 0 for nombre, _, _ in BUCKETS}
    total = 0
    suma = 0
    valores = []
    for g in glosas:
        cre = g.creado_en
        dec = g.fecha_decision_eps
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not cre or not dec:
            continue
        dias = (dec - cre).days
        if dias < 0:
            continue
        valores.append(dias)
        suma += dias
        total += 1
        for nombre, lo, hi in BUCKETS:
            if dias >= lo and (hi is None or dias <= hi):
                bandas[nombre] += 1
                break

    promedio = round(suma / total, 2) if total else 0.0
    mediana = sorted(valores)[len(valores) // 2] if valores else 0

    items = [{"rango_dias": k, "count": bandas[k]} for k, _, _ in BUCKETS]

    return {
        "total_glosas": total,
        "promedio_dias": promedio,
        "mediana_dias": mediana,
        "buckets": items,
    }


@stats_router.get("/stats/glosas-sin-comentarios")
def stats_glosas_sin_comentarios(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R284 P1: glosas abiertas sin comentarios internos.

    Una glosa abierta sin ningún comentario en el hilo del
    equipo posiblemente está siendo ignorada o no se ha
    discutido. Útil para detectar casos "olvidados".

    Filtro: solo abiertas. Ordena DESC por valor_objetado
    para priorizar las de mayor cuantía.
    """

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    # IDs con al menos 1 comentario
    ids_con_com = {row[0] for row in db.query(ComentarioGlosaRecord.glosa_id).distinct().all()}

    items = []
    for g in abiertas:
        if g.id in ids_con_com:
            continue
        items.append(
            {
                "glosa_id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": int(float(g.valor_objetado or 0)),
                "dias_restantes": g.dias_restantes,
            }
        )
    items.sort(key=lambda x: x["valor_objetado"], reverse=True)

    return {
        "total_sin_comentarios": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/eps-volumen-vs-tasa")
def stats_eps_volumen_vs_tasa(
    min_decididas: int = Query(3, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R283 P1: por EPS, volumen vs tasa de levantamiento.

    Datos para análisis cuadrante (scatter-plot):
      - Volumen alto + tasa alta = "EPS dominada" (gana mucho)
      - Volumen alto + tasa baja = "EPS difícil" (foco)
      - Volumen bajo + tasa alta = "EPS pequeña ganada"
      - Volumen bajo + tasa baja = "EPS irrelevante"

    Por EPS:
      - decididas (volumen)
      - tasa_levantamiento_pct
      - cuadrante: ALTA_VOL_ALTA_TASA, etc.

    Usa medianas para clasificar (evita outliers).
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(eps, {"dec": 0, "lev": 0})
        b["dec"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["lev"] += 1

    raw = []
    for eps, b in bucket.items():
        if b["dec"] < min_decididas:
            continue
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        raw.append(
            {
                "eps": eps,
                "decididas": b["dec"],
                "tasa_levantamiento_pct": tasa,
            }
        )

    if not raw:
        return {
            "min_decididas_filtro": int(min_decididas),
            "mediana_volumen": 0,
            "mediana_tasa": 0.0,
            "items": [],
        }

    vols = sorted(it["decididas"] for it in raw)
    tasas = sorted(it["tasa_levantamiento_pct"] for it in raw)
    med_vol = vols[len(vols) // 2]
    med_tasa = tasas[len(tasas) // 2]

    items = []
    for it in raw:
        alto_vol = it["decididas"] >= med_vol
        alta_tasa = it["tasa_levantamiento_pct"] >= med_tasa
        if alto_vol and alta_tasa:
            cuadrante = "ALTA_VOL_ALTA_TASA"
        elif alto_vol:
            cuadrante = "ALTA_VOL_BAJA_TASA"
        elif alta_tasa:
            cuadrante = "BAJA_VOL_ALTA_TASA"
        else:
            cuadrante = "BAJA_VOL_BAJA_TASA"
        items.append({**it, "cuadrante": cuadrante})

    items.sort(key=lambda x: x["decididas"], reverse=True)

    return {
        "min_decididas_filtro": int(min_decididas),
        "mediana_volumen": int(med_vol),
        "mediana_tasa": float(med_tasa),
        "items": items,
    }


@stats_router.get("/stats/eps-ganancia-perdida")
def stats_eps_ganancia_perdida(
    min_glosas: int = Query(3, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R282 P1: ganancia vs pérdida financiera por EPS.

    Vista neta de cada relación HUS-EPS:
      - ganancia: sum(valor_recuperado) en LEVANTADAS
                  (HUS defendió y EPS pagó)
      - perdida: sum(valor_aceptado) en RATIFICADAS o
                 ACEPTADAS (no se cobró)
      - balance: ganancia - perdida
      - ratio_ganancia_pct: ganancia / (ganancia + perdida)

    Útil para clasificar EPS como "ganadora" o "perdedora"
    desde el punto de vista financiero.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(
            eps,
            {
                "count": 0,
                "ganancia": 0.0,
                "perdida": 0.0,
            },
        )
        b["count"] += 1
        estado = (g.estado or "").upper()
        if estado == "LEVANTADA":
            b["ganancia"] += float(g.valor_recuperado or 0)
        elif estado in ("RATIFICADA", "ACEPTADA"):
            b["perdida"] += float(g.valor_aceptado or 0)

    items = []
    for eps, b in bucket.items():
        if b["count"] < min_glosas:
            continue
        denom = b["ganancia"] + b["perdida"]
        ratio = round(100 * b["ganancia"] / denom, 2) if denom else 0.0
        items.append(
            {
                "eps": eps,
                "count_decididas": b["count"],
                "ganancia": int(b["ganancia"]),
                "perdida": int(b["perdida"]),
                "balance": int(b["ganancia"] - b["perdida"]),
                "ratio_ganancia_pct": ratio,
            }
        )
    items.sort(key=lambda x: x["balance"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/conciliaciones-mensual")
def stats_conciliaciones_mensual(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R277 P1: serie temporal mensual de conciliaciones.

    Diferente a /stats/conciliaciones (snapshot global):
    aquí mes-a-mes count_conciliaciones, valor_conciliado
    y resultado más común.

    Útil para detectar tendencias en la fase pre-litigio.
    """
    from datetime import timezone


    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    rows = db.query(ConciliacionRecord).filter(ConciliacionRecord.creado_en >= desde).all()

    por_mes: dict[str, dict] = {}
    for c in rows:
        cre = c.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.strftime("%Y-%m")
        b = por_mes.setdefault(
            k,
            {
                "count": 0,
                "valor": 0.0,
                "resultados": {},
            },
        )
        b["count"] += 1
        b["valor"] += float(c.valor_conciliado or 0)
        res = c.resultado or "SIN_RESULTADO"
        b["resultados"][res] = b["resultados"].get(res, 0) + 1

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        top_res = max(b["resultados"].items(), key=lambda x: x[1])[0]
        serie.append(
            {
                "mes": k,
                "count_conciliaciones": b["count"],
                "valor_conciliado_total": int(b["valor"]),
                "resultado_dominante": top_res,
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_meses": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/comentarios-actividad-mensual")
def stats_comentarios_actividad_mensual(
    meses: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R276 P1: actividad mensual de comentarios internos.

    Diferente a /stats/comentarios-globales (snapshot
    actual): aquí serie temporal mes-a-mes de los
    comentarios creados.

    Por mes:
      - count_comentarios
      - autores_distintos
      - menciones (con @ a otros)
      - resueltos (porcentaje)

    Útil para medir colaboración del equipo en el tiempo.
    """
    from datetime import timezone


    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    rows = db.query(ComentarioGlosaRecord).filter(ComentarioGlosaRecord.creado_en >= desde).all()

    por_mes: dict[str, dict] = {}
    for c in rows:
        cre = c.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.strftime("%Y-%m")
        b = por_mes.setdefault(
            k,
            {
                "count": 0,
                "autores": set(),
                "menciones": 0,
                "resueltos": 0,
            },
        )
        b["count"] += 1
        if c.autor_email:
            b["autores"].add(c.autor_email)
        if c.mencion:
            b["menciones"] += 1
        if int(c.resuelto or 0) == 1:
            b["resueltos"] += 1

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        pct = round(100 * b["resueltos"] / b["count"], 2) if b["count"] else 0.0
        serie.append(
            {
                "mes": k,
                "count_comentarios": b["count"],
                "autores_distintos": len(b["autores"]),
                "menciones": b["menciones"],
                "resueltos": b["resueltos"],
                "pct_resueltos": pct,
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_meses": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/heatmap-mes-eps")
def stats_heatmap_mes_eps(
    meses: int = Query(6, ge=1, le=24),
    top_eps: int = Query(10, ge=2, le=30),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R275 P1: heatmap (mes × EPS) de count de glosas creadas.

    Datos para visualizar como tabla 2D mes-vs-EPS. Solo
    incluye las top N EPS por volumen total para mantener
    el output enfocado.

    Devuelve:
      - meses: lista de YYYY-MM ordenados
      - eps: lista de top N EPS
      - matriz: dict[eps][mes] = count
    """
    from datetime import timezone

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    total_por_eps: dict[str, int] = {}
    matriz: dict[str, dict[str, int]] = {}
    meses_set: set = set()

    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.strftime("%Y-%m")
        meses_set.add(k)
        total_por_eps[eps] = total_por_eps.get(eps, 0) + 1
        matriz.setdefault(eps, {})
        matriz[eps][k] = matriz[eps].get(k, 0) + 1

    top = sorted(total_por_eps.items(), key=lambda x: x[1], reverse=True)
    eps_top = [e for e, _ in top[: int(top_eps)]]

    meses_ord = sorted(meses_set)

    matriz_filt = {}
    for eps in eps_top:
        matriz_filt[eps] = {m: matriz.get(eps, {}).get(m, 0) for m in meses_ord}

    return {
        "ventana_meses": int(meses),
        "meses": meses_ord,
        "eps": eps_top,
        "matriz": matriz_filt,
    }


@stats_router.get("/stats/eps-respuestas-codigos")
def stats_eps_respuestas_codigos(
    eps: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R274 P1: distribución de codigo_respuesta usado por una EPS.

    Para una EPS dada, lista los `codigo_respuesta` (RE9501,
    RE9701, etc.) que esa EPS ha usado y cuántas veces.
    Útil para preparación de mesa con la EPS:
      "Esta EPS usa principalmente RE9501 (no comparto):
       de las 50 veces que la usó, ratificó 40 → 80%
       lo que indica que sus argumentos son fuertes."

    Por código:
      - count_total
      - levantadas, ratificadas
      - tasa_levantamiento_pct (sobre decididas)
    """
    eps_q = (eps or "").strip()
    if not eps_q:
        return {"eps": "", "items": []}

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.ilike(eps_q))
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .filter(GlosaRecord.codigo_respuesta != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        c = (g.codigo_respuesta or "").strip()
        if not c:
            continue
        b = bucket.setdefault(
            c,
            {
                "count": 0,
                "lev": 0,
                "rat": 0,
                "dec": 0,
            },
        )
        b["count"] += 1
        estado = (g.estado or "").upper()
        if estado in ("LEVANTADA", "RATIFICADA", "ACEPTADA"):
            b["dec"] += 1
        if estado == "LEVANTADA":
            b["lev"] += 1
        elif estado == "RATIFICADA":
            b["rat"] += 1

    items = []
    for c, b in bucket.items():
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        items.append(
            {
                "codigo_respuesta": c,
                "count_total": b["count"],
                "decididas": b["dec"],
                "levantadas": b["lev"],
                "ratificadas": b["rat"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["count_total"], reverse=True)

    return {
        "eps": eps_q,
        "total_codigos": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-tendencia-mensual")
def stats_eps_tendencia_mensual(
    eps: str = Query(..., min_length=2),
    meses: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R273 P1: evolución mensual de UNA EPS específica.

    Drill-down temporal por EPS. Diferente a
    /stats/eps-actividad-mensual (todas las EPS): aquí
    enfocado en una sola, perfecto para revisión de
    relación EPS-IPS.

    Por mes: creadas, decididas, levantadas, valor_objetado,
    valor_recuperado, tasa_levantamiento_pct.
    """
    from datetime import timezone

    eps_q = (eps or "").strip()
    if not eps_q:
        return {"eps": "", "ventana_meses": int(meses), "serie": []}

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps.ilike(eps_q))
        .filter(GlosaRecord.creado_en >= desde)
        .all()
    )

    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    por_mes: dict[str, dict] = {}
    for g in glosas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.strftime("%Y-%m")
        b = por_mes.setdefault(
            k,
            {
                "creadas": 0,
                "decididas": 0,
                "levantadas": 0,
                "obj": 0.0,
                "rec": 0.0,
            },
        )
        b["creadas"] += 1
        b["obj"] += float(g.valor_objetado or 0)
        estado = (g.estado or "").upper()
        if estado in ESTADOS_DECIDIDOS:
            b["decididas"] += 1
            b["rec"] += float(g.valor_recuperado or 0)
            if estado == "LEVANTADA":
                b["levantadas"] += 1

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        tasa = round(100 * b["levantadas"] / b["decididas"], 2) if b["decididas"] else 0.0
        serie.append(
            {
                "mes": k,
                "creadas": b["creadas"],
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "valor_objetado": int(b["obj"]),
                "valor_recuperado": int(b["rec"]),
                "tasa_levantamiento_pct": tasa,
            }
        )

    return {
        "eps": eps_q,
        "ventana_meses": int(meses),
        "total_meses_con_actividad": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/facturas-saldos-pendientes")
def stats_facturas_saldos_pendientes(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R269 P1: top facturas con saldo pendiente más alto.

    Diferente a /stats/facturas-hot (por count_glosas):
    aquí ordenamos por saldo_factura agregado.

    Solo facturas con al menos una glosa abierta. Por
    factura:
      - eps
      - count_glosas, count_abiertas
      - saldo_factura (representativo)
      - valor_factura
      - valor_objetado_total
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.factura.isnot(None))
        .filter(GlosaRecord.factura != "N/A")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        f = (g.factura or "").strip()
        if not f:
            continue
        b = bucket.setdefault(
            f,
            {
                "eps": g.eps,
                "count": 0,
                "abiertas": 0,
                "saldo": float(g.saldo_factura or 0),
                "valor_factura": float(g.valor_factura or 0),
                "obj": 0.0,
            },
        )
        b["count"] += 1
        if (g.estado or "").upper() not in ESTADOS_CERRADOS:
            b["abiertas"] += 1
        b["obj"] += float(g.valor_objetado or 0)

    items = []
    for factura, b in bucket.items():
        if b["abiertas"] == 0:
            continue
        items.append(
            {
                "factura": factura,
                "eps": b["eps"],
                "count_glosas": b["count"],
                "count_abiertas": b["abiertas"],
                "saldo_factura": int(b["saldo"]),
                "valor_factura": int(b["valor_factura"]),
                "valor_objetado_total": int(b["obj"]),
            }
        )
    items.sort(key=lambda x: x["saldo_factura"], reverse=True)

    return {
        "limit": int(limit),
        "total_facturas": len(items),
        "saldo_total": sum(it["saldo_factura"] for it in items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/eps-codigo-pareto")
def stats_eps_codigo_pareto(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R268 P1: Pareto 80/20 sobre parejas (EPS, codigo_glosa).

    Análisis bidimensional: identifica qué combinaciones
    EPS-código concentran el 80% del valor objetado. Útil
    para enfocar esfuerzos: "ataquemos primero estas 5
    parejas (EPS, código) y cubrimos 80% del valor".

    Diferente a /stats/concentracion-pareto (1D EPS) y
    /stats/eps-codigo-pareja (lookup individual).

    Devuelve:
      - valor_total
      - count_parejas_top80, pct_parejas_top80
      - parejas_top80
    """
    rows = db.query(GlosaRecord).all()

    pares: dict[tuple[str, str], float] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        codigo = (g.codigo_glosa or "").strip()
        if not eps or not codigo:
            continue
        valor = float(g.valor_objetado or 0)
        pares[(eps, codigo)] = pares.get((eps, codigo), 0.0) + valor

    valor_total = sum(pares.values())
    if valor_total == 0:
        return {
            "valor_total": 0,
            "count_parejas_top80": 0,
            "pct_parejas_top80": 0.0,
            "parejas_top80": [],
        }

    ord_p = sorted(pares.items(), key=lambda x: x[1], reverse=True)

    acumulado = 0.0
    top80 = []
    for (eps, codigo), valor in ord_p:
        top80.append(
            {
                "eps": eps,
                "codigo_glosa": codigo,
                "valor_objetado": int(valor),
                "pct_individual": round(100 * valor / valor_total, 2),
            }
        )
        acumulado += valor
        if acumulado >= 0.8 * valor_total:
            break

    pct = round(100 * len(top80) / len(ord_p), 2)

    return {
        "valor_total": int(valor_total),
        "total_parejas": len(ord_p),
        "count_parejas_top80": len(top80),
        "pct_parejas_top80": pct,
        "parejas_top80": top80,
    }


@stats_router.get("/stats/aging-cartera-saldo")
def stats_aging_cartera_saldo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R267 P1: aging report basado en `saldo_factura`.

    Diferente a /stats/aging-glosas (basado en valor_objetado):
    aquí usamos `saldo_factura`, el saldo real pendiente
    según el módulo de cartera del DGH.

    Buckets (días desde creado_en):
      0-30, 31-60, 61-90, 91-180, >180

    Solo glosas no-cerradas. Devuelve count y saldo por
    bucket, con totales globales.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    BUCKETS = [
        ("0-30", 0, 30),
        ("31-60", 31, 60),
        ("61-90", 61, 90),
        ("91-180", 91, 180),
        (">180", 181, None),
    ]

    ahora = ahora_utc()
    bandas: dict[str, dict] = {nombre: {"count": 0, "saldo": 0.0} for nombre, _, _ in BUCKETS}

    for g in abiertas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        antig = (ahora - cre).days
        saldo = float(g.saldo_factura or 0)
        for nombre, lo, hi in BUCKETS:
            if antig >= lo and (hi is None or antig <= hi):
                bandas[nombre]["count"] += 1
                bandas[nombre]["saldo"] += saldo
                break

    items = []
    for nombre, _, _ in BUCKETS:
        b = bandas[nombre]
        items.append(
            {
                "rango_dias": nombre,
                "count": b["count"],
                "saldo": int(b["saldo"]),
            }
        )

    return {
        "total_count": sum(it["count"] for it in items),
        "total_saldo": sum(it["saldo"] for it in items),
        "items": items,
    }


@stats_router.get("/stats/cartera-por-eps")
def stats_cartera_por_eps(
    solo_abiertas: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R262 P1: cartera (saldo_factura) consolidada por EPS.

    Diferente a /stats/cobranza-por-eps (basado en
    valor_objetado): aquí usamos `saldo_factura` que viene
    del módulo de cartera del DGH. Es el saldo real
    pendiente en libros, no el monto objetado.

    Por EPS:
      - count_glosas
      - saldo_total (sum saldo_factura)
      - valor_factura_total (sum valor_factura)
      - pct_saldo (saldo_total / valor_factura_total)

    Si `solo_abiertas` (default True), excluye glosas en
    estados terminales.

    Ordenado DESC por saldo_total.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    q = db.query(GlosaRecord).filter(GlosaRecord.eps.isnot(None))
    if solo_abiertas:
        q = q.filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
    rows = q.all()

    por_eps: dict[str, dict] = {}
    for g in rows:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = por_eps.setdefault(
            eps,
            {
                "count": 0,
                "saldo": 0.0,
                "valor": 0.0,
            },
        )
        b["count"] += 1
        b["saldo"] += float(g.saldo_factura or 0)
        b["valor"] += float(g.valor_factura or 0)

    items = []
    for eps, b in por_eps.items():
        pct = round(100 * b["saldo"] / b["valor"], 2) if b["valor"] else 0.0
        items.append(
            {
                "eps": eps,
                "count_glosas": b["count"],
                "saldo_total": int(b["saldo"]),
                "valor_factura_total": int(b["valor"]),
                "pct_saldo": pct,
            }
        )
    items.sort(key=lambda x: x["saldo_total"], reverse=True)

    saldo_global = sum(it["saldo_total"] for it in items)
    valor_global = sum(it["valor_factura_total"] for it in items)
    pct_global = round(100 * saldo_global / valor_global, 2) if valor_global else 0.0

    return {
        "solo_abiertas": bool(solo_abiertas),
        "saldo_total": saldo_global,
        "valor_factura_total": valor_global,
        "pct_saldo_global": pct_global,
        "items": items,
    }


@stats_router.get("/stats/calidad-dictamen-por-gestor")
def stats_calidad_dictamen_por_gestor(
    min_glosas: int = Query(3, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R261 P1: calidad de dictamen por gestor.

    Métricas por gestor sobre el campo `dictamen`:
      - total_glosas
      - len_promedio (caracteres del dictamen)
      - count_cortos (< 50 chars)
      - count_largos (>= 200 chars)
      - pct_completos (>= 50 chars)

    Útil para detectar gestores que escriben dictámenes
    pobres y sugerir entrenamiento.

    Ordenado DESC por len_promedio.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .filter(GlosaRecord.dictamen.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        b = bucket.setdefault(
            gestor,
            {
                "total": 0,
                "suma": 0,
                "cortos": 0,
                "largos": 0,
                "completos": 0,
            },
        )
        dlen = len(g.dictamen or "")
        b["total"] += 1
        b["suma"] += dlen
        if dlen < 50:
            b["cortos"] += 1
        elif dlen >= 200:
            b["largos"] += 1
        if dlen >= 50:
            b["completos"] += 1

    items = []
    for gestor, b in bucket.items():
        if b["total"] < min_glosas:
            continue
        prom = round(b["suma"] / b["total"], 1)
        pct_c = round(100 * b["completos"] / b["total"], 2)
        items.append(
            {
                "gestor": gestor,
                "total_glosas": b["total"],
                "len_promedio": prom,
                "count_cortos": b["cortos"],
                "count_largos": b["largos"],
                "pct_completos": pct_c,
            }
        )
    items.sort(key=lambda x: x["len_promedio"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_gestores": len(items),
        "items": items,
    }


@stats_router.get("/stats/codigo-glosa-tendencia")
def stats_codigo_glosa_tendencia(
    dias: int = Query(30, ge=7, le=90),
    min_glosas_actual: int = Query(3, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R260 P1: tendencia de códigos de glosa (emergentes vs en declive).

    Compara dos ventanas consecutivas de N días:
      - actual: últimos N días
      - previa: N días anteriores a esos

    Por código:
      - count_actual, count_previo
      - delta_abs (actual - previo)
      - delta_pct (variación relativa)

    Útil para alertar sobre nuevos patrones de objeción de las
    EPS antes de que se vuelvan masivos.
    """
    from datetime import timezone

    ahora = ahora_utc()
    corte_actual = ahora - timedelta(days=int(dias))
    corte_previo = ahora - timedelta(days=int(dias) * 2)

    actual: dict[str, int] = {}
    previo: dict[str, int] = {}

    for g in db.query(GlosaRecord).all():
        codigo = (g.codigo_glosa or "").strip()
        if not codigo:
            continue
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        if not creado:
            continue
        if creado >= corte_actual:
            actual[codigo] = actual.get(codigo, 0) + 1
        elif creado >= corte_previo:
            previo[codigo] = previo.get(codigo, 0) + 1

    todos_codigos = set(actual) | set(previo)
    items = []
    for codigo in todos_codigos:
        a = actual.get(codigo, 0)
        p = previo.get(codigo, 0)
        if a < min_glosas_actual:
            continue
        delta_abs = a - p
        if p == 0:
            delta_pct = 100.0 if a > 0 else 0.0
        else:
            delta_pct = round(100 * (a - p) / p, 2)
        items.append(
            {
                "codigo_glosa": codigo,
                "count_actual": a,
                "count_previo": p,
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
            }
        )

    items.sort(key=lambda x: x["delta_pct"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "min_glosas_actual": int(min_glosas_actual),
        "total_codigos": len(items),
        "items": items,
    }


@stats_router.get("/stats/gestores-pareto")
def stats_gestores_pareto(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R259 P1: Pareto 80/20 sobre gestores por glosas decididas.

    Identifica qué gestores concentran el 80% del volumen de
    decisiones. Útil para el coordinador: detectar
    sobrecarga en pocas personas y rebalancear cargas.

    Devuelve:
      - total_decididas
      - count_gestores_top80 / pct_gestores_top80
      - gestores_top80: lista hasta acumular 80%
    """
    decididas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    por_gestor: dict[str, int] = {}
    for g in decididas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        por_gestor[gestor] = por_gestor.get(gestor, 0) + 1

    total = sum(por_gestor.values())
    if total == 0:
        return {
            "total_decididas": 0,
            "count_gestores_top80": 0,
            "pct_gestores_top80": 0.0,
            "gestores_top80": [],
        }

    ord_g = sorted(por_gestor.items(), key=lambda x: x[1], reverse=True)

    acumulado = 0
    top80 = []
    for gestor, count in ord_g:
        top80.append(
            {
                "gestor": gestor,
                "decididas": count,
                "pct_individual": round(100 * count / total, 2),
            }
        )
        acumulado += count
        if acumulado >= 0.8 * total:
            break

    pct_g = round(100 * len(top80) / len(ord_g), 2)

    return {
        "total_decididas": int(total),
        "total_gestores": len(ord_g),
        "count_gestores_top80": len(top80),
        "pct_gestores_top80": pct_g,
        "gestores_top80": top80,
    }


@stats_router.get("/stats/profesional-top")
def stats_profesional_top(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R258 P1: top profesionales médicos por glosas asociadas.

    Útil para identificar prácticas (médicos, especialistas)
    que generan más glosas y abrir conversaciones de calidad
    con auditoría médica. Solo cuenta glosas con
    `profesional_medico` no nulo y no vacío.

    Por profesional:
      - total_glosas
      - levantadas, ratificadas, decididas
      - tasa_levantamiento_pct (sobre decididas)
      - valor_objetado_total

    Ordenado DESC por total_glosas.
    """
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.profesional_medico.isnot(None))
        .filter(GlosaRecord.profesional_medico != "")
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in rows:
        prof = (g.profesional_medico or "").strip()
        if not prof:
            continue
        b = bucket.setdefault(
            prof,
            {
                "total": 0,
                "lev": 0,
                "rat": 0,
                "dec": 0,
                "val": 0.0,
            },
        )
        b["total"] += 1
        estado = (g.estado or "").upper()
        if estado in ("LEVANTADA", "RATIFICADA", "ACEPTADA"):
            b["dec"] += 1
        if estado == "LEVANTADA":
            b["lev"] += 1
        elif estado == "RATIFICADA":
            b["rat"] += 1
        b["val"] += float(g.valor_objetado or 0)

    items = []
    for prof, b in bucket.items():
        tasa = round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        items.append(
            {
                "profesional_medico": prof,
                "total_glosas": b["total"],
                "decididas": b["dec"],
                "levantadas": b["lev"],
                "ratificadas": b["rat"],
                "tasa_levantamiento_pct": tasa,
                "valor_objetado_total": int(b["val"]),
            }
        )
    items.sort(key=lambda x: x["total_glosas"], reverse=True)

    return {
        "limit": int(limit),
        "total_profesionales": len(items),
        "items": items[: int(limit)],
    }


@stats_router.get("/stats/exito-por-gestor")
def stats_exito_por_gestor(
    min_glosas: int = Query(3, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R257 P1: tasa de levantamiento por gestor (público).

    Diferente a /admin/ranking-gestores (con badges, requiere
    SUPER_ADMIN): aquí solo métricas crudas, accesible a
    cualquier auditor para autoevaluación o comparación con
    pares.

    Por gestor:
      - decididas, levantadas
      - tasa_levantamiento_pct
      - valor_recuperado_total

    Ordenado DESC por tasa_levantamiento_pct.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    por_gestor: dict[str, dict] = {}
    for g in glosas:
        gestor = g.gestor_nombre
        if not gestor:
            continue
        if gestor not in por_gestor:
            por_gestor[gestor] = {
                "decididas": 0,
                "levantadas": 0,
                "rec": 0.0,
            }
        por_gestor[gestor]["decididas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_gestor[gestor]["levantadas"] += 1
        por_gestor[gestor]["rec"] += float(g.valor_recuperado or 0)

    items = []
    for gestor, b in por_gestor.items():
        if b["decididas"] < min_glosas:
            continue
        tasa = round(100 * b["levantadas"] / b["decididas"], 2)
        items.append(
            {
                "gestor": gestor,
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
                "valor_recuperado_total": int(b["rec"]),
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "items": items,
    }


@stats_router.get("/stats/cobranza-pareto-eps")
def stats_cobranza_pareto_eps(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R254 P1: Pareto 80/20 sobre EPS pendientes (cobranza).

    Identifica las EPS que concentran el 80% del valor pendiente.
    Útil para el coordinador: "ataquemos primero estas 3 EPS y
    cubrimos el 80% del valor a recuperar".

    Devuelve:
      - valor_total
      - count_eps_top80 / pct_eps_top80
      - eps_top80: lista de EPS hasta acumular 80%
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    por_eps: dict[str, float] = {}
    for g in abiertas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        por_eps[eps] = por_eps.get(eps, 0.0) + float(g.valor_objetado or 0)

    valor_total = sum(por_eps.values())
    if valor_total == 0:
        return {
            "valor_total": 0,
            "count_eps_top80": 0,
            "pct_eps_top80": 0.0,
            "eps_top80": [],
        }

    eps_ord = sorted(por_eps.items(), key=lambda x: x[1], reverse=True)

    acumulado = 0.0
    eps_top80 = []
    for eps, valor in eps_ord:
        eps_top80.append(
            {
                "eps": eps,
                "valor_pendiente": int(valor),
                "pct_individual": round(100 * valor / valor_total, 2),
            }
        )
        acumulado += valor
        if acumulado >= 0.8 * valor_total:
            break

    pct_eps = round(100 * len(eps_top80) / len(eps_ord), 2)

    return {
        "valor_total": int(valor_total),
        "count_eps_top80": len(eps_top80),
        "pct_eps_top80": pct_eps,
        "eps_top80": eps_top80,
    }


@stats_router.get("/stats/glosas-altas-cuantia")
def stats_glosas_altas_cuantia(
    umbral: float = Query(5_000_000, ge=10_000),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r"""R253 P1: glosas con valor objetado superior al umbral.

    Útil para identificar casos de alta cuantía que requieren
    seguimiento ejecutivo:
      "Glosas >\$5M ABIERTAS, ordenadas DESC por valor"

    Solo abiertas. Param `umbral` en COP (default \$5M).
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.valor_objetado > float(umbral))
        .order_by(GlosaRecord.valor_objetado.desc())
        .limit(50)
        .all()
    )

    items = []
    for g in glosas:
        items.append(
            {
                "id": g.id,
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
                "valor_objetado": float(g.valor_objetado or 0),
                "dias_restantes": g.dias_restantes,
            }
        )

    return {
        "umbral": int(umbral),
        "total_altas_cuantia": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-codigo-pareja")
def stats_eps_codigo_pareja(
    eps: str = Query(..., min_length=2),
    codigo_glosa: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R252 P1: tasa histórica para una pareja (eps, codigo_glosa).

    Útil cuando el frontend crea una glosa y quiere mostrar:
      "Histórico SANITAS+TA0201: 5 levantadas, 3 ratificadas
       (tasa 62%)"

    Devuelve {decididas, levantadas, ratificadas, aceptadas,
    tasa_levantamiento_pct}.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .filter(GlosaRecord.codigo_glosa == codigo_glosa)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    levantadas = sum(1 for g in glosas if (g.estado or "").upper() == "LEVANTADA")
    ratificadas = sum(1 for g in glosas if (g.estado or "").upper() == "RATIFICADA")
    aceptadas = sum(1 for g in glosas if (g.estado or "").upper() == "ACEPTADA")

    tasa = round(100 * levantadas / len(glosas), 2) if glosas else 0.0

    return {
        "eps": eps,
        "codigo_glosa": codigo_glosa,
        "decididas": len(glosas),
        "levantadas": levantadas,
        "ratificadas": ratificadas,
        "aceptadas": aceptadas,
        "tasa_levantamiento_pct": tasa,
    }


@stats_router.get("/stats/mes-actual")
def stats_mes_actual(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R248 P1: estadísticas del mes en curso.

    Vista resumida del mes corriente (desde día 1):
      - creadas
      - cerradas
      - levantadas
      - valor_objetado_mes
      - valor_recuperado_mes
      - tasa_levantamiento_pct

    Útil para reportes de avance del mes.
    """

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    ahora = ahora_utc()
    inicio_mes = ahora.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    creadas = (
        db.query(_f.count(GlosaRecord.id)).filter(GlosaRecord.creado_en >= inicio_mes).scalar() or 0
    )
    cerradas_list = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= inicio_mes)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )
    levantadas = sum(1 for g in cerradas_list if (g.estado or "").upper() == "LEVANTADA")
    valor_obj_mes = (
        db.query(_f.coalesce(_f.sum(GlosaRecord.valor_objetado), 0))
        .filter(GlosaRecord.creado_en >= inicio_mes)
        .scalar()
        or 0
    )
    valor_rec_mes = sum(float(g.valor_recuperado or 0) for g in cerradas_list)

    decididas = sum(
        1
        for g in cerradas_list
        if (g.estado or "").upper() in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
    )
    tasa = round(100 * levantadas / decididas, 2) if decididas else 0.0

    return {
        "mes": inicio_mes.strftime("%Y-%m"),
        "creadas": int(creadas),
        "cerradas": len(cerradas_list),
        "levantadas": levantadas,
        "valor_objetado_mes": int(valor_obj_mes),
        "valor_recuperado_mes": int(valor_rec_mes),
        "tasa_levantamiento_pct": tasa,
    }


@stats_router.get("/stats/eps-pacientes-top")
def stats_eps_pacientes_top(
    eps: str = Query(..., min_length=2),
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R246 P1: top pacientes con más glosas para una EPS específica.

    Útil para identificar pacientes "calientes" en una EPS:
      "Pedro tiene 8 glosas con SANITAS, casos relacionados"

    Param `eps`: nombre exacto.

    Devuelve top N ordenado DESC por count.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .filter(GlosaRecord.paciente.isnot(None))
        .all()
    )

    por_pac: dict[str, dict] = {}
    for g in glosas:
        pac = (g.paciente or "").strip()
        if not pac:
            continue
        if pac not in por_pac:
            por_pac[pac] = {"count": 0, "valor": 0.0}
        por_pac[pac]["count"] += 1
        por_pac[pac]["valor"] += float(g.valor_objetado or 0)

    items = []
    for pac, b in por_pac.items():
        items.append(
            {
                "paciente": pac,
                "count": b["count"],
                "valor_objetado_total": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "eps": eps,
        "items": items[: int(top)],
    }


@stats_router.get("/stats/tiempo-cierre-promedio")
def stats_tiempo_cierre_promedio(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R245 P1: tiempo promedio total entre creación y cierre.

    Para todas las glosas cerradas:
      tiempo_cierre = fecha_decision_eps - creado_en

    Devuelve estadísticas agregadas:
      - count_glosas_cerradas
      - tiempo_promedio_dias
      - tiempo_mediano_dias
      - tiempo_max_dias

    KPI top-line de eficiencia operacional.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .all()
    )

    tiempos: list[int] = []
    for g in glosas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not cre or not dec:
            continue
        d = (dec - cre).days
        if d < 0:
            continue
        tiempos.append(d)

    if not tiempos:
        return {
            "count_glosas_cerradas": 0,
            "tiempo_promedio_dias": 0.0,
            "tiempo_mediano_dias": 0.0,
            "tiempo_max_dias": 0,
        }

    tiempos.sort()
    n = len(tiempos)
    promedio = sum(tiempos) / n
    if n % 2 == 0:
        mediano = (tiempos[n // 2 - 1] + tiempos[n // 2]) / 2
    else:
        mediano = tiempos[n // 2]

    return {
        "count_glosas_cerradas": n,
        "tiempo_promedio_dias": round(promedio, 2),
        "tiempo_mediano_dias": round(mediano, 2),
        "tiempo_max_dias": int(max(tiempos)),
    }


@stats_router.get("/stats/codigos-mas-recuperados")
def stats_codigos_mas_recuperados(
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r"""R244 P1: códigos de glosa con más valor TOTAL recuperado.

    Útil para identificar dónde se recauda más:
      "TA0201 nos ha generado \$50M en defensas exitosas"

    Solo glosas con valor_recuperado > 0.

    Por código: count_levantadas + valor_recuperado_total.
    Ordenado DESC por valor_recuperado_total.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.valor_recuperado > 0)
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    por_cod: dict[str, dict] = {}
    for g in glosas:
        cod = g.codigo_glosa
        if not cod:
            continue
        if cod not in por_cod:
            por_cod[cod] = {"count": 0, "valor": 0.0}
        por_cod[cod]["count"] += 1
        por_cod[cod]["valor"] += float(g.valor_recuperado or 0)

    items = []
    for cod, b in por_cod.items():
        items.append(
            {
                "codigo_glosa": cod,
                "count_levantadas": b["count"],
                "valor_recuperado_total": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["valor_recuperado_total"], reverse=True)

    return {
        "items": items[: int(top)],
    }


@stats_router.get("/stats/eps-pendientes-detalle")
def stats_eps_pendientes_detalle(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R243 P1: ranking de EPS por count de glosas pendientes.

    Diferente a /stats/cobranza-por-eps (ordenado por valor) y
    /admin/eps-conteos (todas con todos los counts):
    aquí solo EPS con glosas abiertas, ordenado por count.

    Solo glosas no-cerradas.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    por_eps: dict[str, dict] = {}
    for g in abiertas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"count": 0, "valor": 0.0, "vencidas": 0}
        por_eps[eps]["count"] += 1
        por_eps[eps]["valor"] += float(g.valor_objetado or 0)
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            por_eps[eps]["vencidas"] += 1

    items = []
    for eps, b in por_eps.items():
        items.append(
            {
                "eps": eps,
                "count_pendientes": b["count"],
                "valor_pendiente": int(b["valor"]),
                "vencidas": b["vencidas"],
            }
        )
    items.sort(key=lambda x: x["count_pendientes"], reverse=True)

    return {
        "total_eps_con_pendientes": len(items),
        "items": items,
    }


@stats_router.get("/stats/codigos-respuesta-distribucion")
def stats_codigos_respuesta_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R238 P1: distribución global de códigos de respuesta.

    Muestra qué códigos de respuesta usa más HUS:
      - RE9901: 60% (defensa principal)
      - RE9502: 20% (extemporáneas)
      - RE9801: 10% (parciales)

    Útil para entender el patrón de defensa del equipo.

    Solo glosas con codigo_respuesta no-NULL.
    """
    glosas = db.query(GlosaRecord).filter(GlosaRecord.codigo_respuesta.isnot(None)).all()

    por_codigo: dict[str, int] = {}
    for g in glosas:
        cr = g.codigo_respuesta
        if not cr:
            continue
        por_codigo[cr] = por_codigo.get(cr, 0) + 1

    total = sum(por_codigo.values())
    items = []
    for cod, count in por_codigo.items():
        pct = round(100 * count / total, 2) if total else 0.0
        items.append(
            {
                "codigo_respuesta": cod,
                "count": count,
                "pct": pct,
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_glosas_con_codigo": total,
        "items": items,
    }


@stats_router.get("/stats/aging-glosas")
def stats_aging_glosas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R237 P1: aging report estilo cobranza para glosas abiertas.

    Tradicional aging: cuántas glosas abiertas y por cuánto valor
    en buckets de antigüedad:
      0-30, 31-60, 61-90, 91-180, >180

    Útil para reportes financieros (cobranza tradicional).

    Solo glosas no-cerradas.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    BUCKETS = [
        ("0-30", 0, 30),
        ("31-60", 31, 60),
        ("61-90", 61, 90),
        ("91-180", 91, 180),
        (">180", 181, None),
    ]

    ahora = ahora_utc()
    bandas: dict[str, dict] = {nombre: {"count": 0, "valor": 0.0} for nombre, _, _ in BUCKETS}

    for g in abiertas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        antig = (ahora - cre).days
        for nombre, lo, hi in BUCKETS:
            if antig >= lo and (hi is None or antig <= hi):
                bandas[nombre]["count"] += 1
                bandas[nombre]["valor"] += float(g.valor_objetado or 0)
                break

    items = []
    for nombre, _, _ in BUCKETS:
        b = bandas[nombre]
        items.append(
            {
                "rango_dias": nombre,
                "count": b["count"],
                "valor": int(b["valor"]),
            }
        )

    return {
        "total_abiertas": len(abiertas),
        "items": items,
    }


@stats_router.get("/stats/anomalias-valor")
def stats_anomalias_valor(
    factor_z: float = Query(2.0, ge=1.0, le=5.0),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R233 P1: glosas con valor anómalo dentro de su cohorte.

    Para cada (eps, codigo_glosa), calcula media + desviación
    estándar y detecta glosas cuyo valor está más allá de
    `factor_z` desviaciones (z-score>=factor_z).

    Diferente a /stats/anomalias (IQR global): aquí cohorte y
    z-score paramétricos.

    Útil para detectar:
      - Errores de captura ($1B en lugar de $1M)
      - Casos extraordinarios que requieren review

    Devuelve glosas anómalas con el motivo (z-score).
    """
    glosas = db.query(GlosaRecord).all()

    # Agrupar por (eps, codigo_glosa)
    cohortes: dict[tuple[str, str], list] = {}
    for g in glosas:
        if not g.eps or not g.codigo_glosa:
            continue
        v = float(g.valor_objetado or 0)
        if v <= 0:
            continue
        key = (g.eps, g.codigo_glosa)
        cohortes.setdefault(key, []).append((g, v))

    items = []
    for key, glosas_cohorte in cohortes.items():
        if len(glosas_cohorte) < 5:
            continue
        valores = [v for _, v in glosas_cohorte]
        mean = sum(valores) / len(valores)
        var = sum((v - mean) ** 2 for v in valores) / len(valores)
        std = var**0.5
        if std == 0:
            continue
        for g, v in glosas_cohorte:
            z = (v - mean) / std
            if abs(z) >= factor_z:
                items.append(
                    {
                        "glosa_id": g.id,
                        "eps": g.eps,
                        "codigo_glosa": g.codigo_glosa,
                        "valor_objetado": v,
                        "z_score": round(z, 2),
                        "promedio_cohorte": round(mean, 2),
                    }
                )
    items.sort(key=lambda x: abs(x["z_score"]), reverse=True)

    return {
        "factor_z_filtro": float(factor_z),
        "total_anomalias": len(items),
        "items": items[:50],
    }


@stats_router.get("/stats/tasa-levantamiento-mensual")
def stats_tasa_levantamiento_mensual(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R232 P1: evolución mensual de la tasa de levantamiento global.

    Por mes (basado en fecha_decision_eps):
      tasa_pct = LEVANTADAS / decididas

    Útil para ver si el equipo mejora con el tiempo:
      "En enero 50%, en abril 75% → mejora sostenida"

    Devuelve serie ASC por mes.
    """
    from datetime import timezone

    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .all()
    )

    por_mes: dict[str, dict] = {}
    for g in glosas:
        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not dec:
            continue
        k = dec.strftime("%Y-%m")
        if k not in por_mes:
            por_mes[k] = {"decididas": 0, "levantadas": 0}
        por_mes[k]["decididas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_mes[k]["levantadas"] += 1

    todos = sorted(por_mes.keys())
    recientes = todos[-int(meses) :]
    serie = []
    for k in recientes:
        b = por_mes[k]
        tasa = round(100 * b["levantadas"] / b["decididas"], 2) if b["decididas"] else 0.0
        serie.append(
            {
                "mes": k,
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
            }
        )

    return {
        "meses_solicitados": int(meses),
        "serie": serie,
    }


@stats_router.get("/stats/codigos-mejor-tasa")
def stats_codigos_mejor_tasa(
    min_decididas: int = Query(5, ge=1, le=100),
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R230 P1: códigos de glosa con MEJOR tasa.

    Contraparte de /stats/codigos-peor-tasa. Útil para
    identificar tipos de glosa donde HUS gana fácil:
      "TA0201 levantamos 95% → seguir esa estrategia"

    Filtra por min_decididas (default 5).
    Ordenado DESC por tasa.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    por_codigo: dict[str, dict] = {}
    for g in glosas:
        cod = g.codigo_glosa
        if not cod:
            continue
        if cod not in por_codigo:
            por_codigo[cod] = {"decididas": 0, "levantadas": 0}
        por_codigo[cod]["decididas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_codigo[cod]["levantadas"] += 1

    items = []
    for cod, b in por_codigo.items():
        if b["decididas"] < min_decididas:
            continue
        tasa = round(100 * b["levantadas"] / b["decididas"], 2)
        items.append(
            {
                "codigo_glosa": cod,
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "min_decididas_filtro": int(min_decididas),
        "items": items[: int(top)],
    }


@stats_router.get("/stats/codigos-peor-tasa")
def stats_codigos_peor_tasa(
    min_decididas: int = Query(5, ge=1, le=100),
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R229 P1: códigos de glosa con PEOR tasa de levantamiento.

    Útil para identificar tipos de glosa que HUS pierde mucho:
      "TA0202 levantamos solo 15% → revisar la estrategia"

    Filtra por min_decididas (default 5).
    Ordenado ASC por tasa.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .all()
    )

    por_codigo: dict[str, dict] = {}
    for g in glosas:
        cod = g.codigo_glosa
        if not cod:
            continue
        if cod not in por_codigo:
            por_codigo[cod] = {"decididas": 0, "levantadas": 0}
        por_codigo[cod]["decididas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_codigo[cod]["levantadas"] += 1

    items = []
    for cod, b in por_codigo.items():
        if b["decididas"] < min_decididas:
            continue
        tasa = round(100 * b["levantadas"] / b["decididas"], 2)
        items.append(
            {
                "codigo_glosa": cod,
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"])

    return {
        "min_decididas_filtro": int(min_decididas),
        "items": items[: int(top)],
    }


@stats_router.get("/stats/eps-peor-tasa")
def stats_eps_peor_tasa(
    min_decididas: int = Query(5, ge=1, le=100),
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R228 P1: top EPS donde HUS tiene PEOR tasa.

    Contraparte de /stats/eps-mejor-tasa. Útil para identificar
    EPS con dificultades:
      "Contra X EPS, solo levantamos 10% — ¿qué hacemos
       diferente?"

    Filtra por min_decididas (default 5).
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"decididas": 0, "levantadas": 0}
        por_eps[eps]["decididas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_eps[eps]["levantadas"] += 1

    items = []
    for eps, b in por_eps.items():
        if b["decididas"] < min_decididas:
            continue
        tasa = round(100 * b["levantadas"] / b["decididas"], 2)
        items.append(
            {
                "eps": eps,
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"])

    return {
        "min_decididas_filtro": int(min_decididas),
        "items": items[: int(top)],
    }


@stats_router.get("/stats/eps-mejor-tasa")
def stats_eps_mejor_tasa(
    min_decididas: int = Query(5, ge=1, le=100),
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R227 P1: top EPS donde HUS tiene MEJOR tasa de levantamiento.

    Diferente a /stats/comparativa-eps (todas con métricas) y
    /stats/estatus-eps (semáforo): aquí solo el ranking de las
    EPS donde HUS gana más, ordenado DESC por tasa.

    Útil para reconocer patrones positivos:
      "Contra X EPS, levantamos el 90%"

    Filtra por min_decididas (default 5) para evitar ruido.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"decididas": 0, "levantadas": 0}
        por_eps[eps]["decididas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_eps[eps]["levantadas"] += 1

    items = []
    for eps, b in por_eps.items():
        if b["decididas"] < min_decididas:
            continue
        tasa = round(100 * b["levantadas"] / b["decididas"], 2)
        items.append(
            {
                "eps": eps,
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "min_decididas_filtro": int(min_decididas),
        "items": items[: int(top)],
    }


@stats_router.get("/stats/dashboard-completo")
def stats_dashboard_completo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R225 P1: dashboard mega-completo en single-call.

    Combina TODAS las métricas que un coordinador querría ver
    en una sola pantalla, sin múltiples requests.

    Secciones:
      - kpis_globales (4 KPIs principales)
      - urgencia (4 bandas)
      - top_3_eps_pendientes
      - actividad_hoy (creadas, cerradas)

    Pensado como single-call autosuficiente para mobile/PWA.
    """

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    inicio_hoy = ahora_utc().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    total_glosas = db.query(_f.count(GlosaRecord.id)).scalar() or 0
    abiertas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar()
        or 0
    )
    valor_pendiente = (
        db.query(_f.coalesce(_f.sum(GlosaRecord.valor_objetado), 0))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar()
        or 0
    )
    valor_recuperado_total = (
        db.query(_f.coalesce(_f.sum(GlosaRecord.valor_recuperado), 0)).scalar() or 0
    )

    abiertas_glosas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()
    urgencia = {
        "VENCIDA": 0,
        "CRITICA": 0,
        "PROXIMA": 0,
        "LEJANA": 0,
    }
    for g in abiertas_glosas:
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            urgencia["VENCIDA"] += 1
        elif dr <= 3:
            urgencia["CRITICA"] += 1
        elif dr <= 7:
            urgencia["PROXIMA"] += 1
        else:
            urgencia["LEJANA"] += 1

    por_eps_valor: dict[str, float] = {}
    for g in abiertas_glosas:
        if g.eps:
            por_eps_valor[g.eps] = por_eps_valor.get(g.eps, 0.0) + float(g.valor_objetado or 0)
    top_3 = sorted(
        por_eps_valor.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    creadas_hoy = (
        db.query(_f.count(GlosaRecord.id)).filter(GlosaRecord.creado_en >= inicio_hoy).scalar() or 0
    )
    cerradas_hoy = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_hoy)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar()
        or 0
    )

    return {
        "kpis_globales": {
            "total_glosas": int(total_glosas),
            "abiertas": int(abiertas),
            "valor_pendiente": int(valor_pendiente),
            "valor_recuperado_acumulado": int(valor_recuperado_total),
        },
        "urgencia": urgencia,
        "top_3_eps_pendientes": [{"eps": e, "valor_pendiente": int(v)} for e, v in top_3],
        "actividad_hoy": {
            "creadas": int(creadas_hoy),
            "cerradas": int(cerradas_hoy),
        },
    }


@stats_router.get("/stats/dictamen-vs-tasa-exito")
def stats_dictamen_vs_tasa_exito(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R224 P1: correlación longitud dictamen vs tasa levantamiento.

    ¿Los dictámenes largos ganan más? ¿O los cortos? Este
    endpoint calcula la tasa por banda de longitud.

    Solo glosas decididas (LEVANTADA, ACEPTADA, RATIFICADA).

    Devuelve por banda: count + levantadas + tasa_lev_pct.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            )
        )
        .all()
    )

    bandas = {
        "MUY_CORTO_<100": {"count": 0, "lev": 0},
        "CORTO_100a499": {"count": 0, "lev": 0},
        "MEDIO_500a1999": {"count": 0, "lev": 0},
        "LARGO_>=2000": {"count": 0, "lev": 0},
    }
    for g in glosas:
        if not g.dictamen:
            continue
        n = len(g.dictamen)
        if n < 100:
            k = "MUY_CORTO_<100"
        elif n < 500:
            k = "CORTO_100a499"
        elif n < 2000:
            k = "MEDIO_500a1999"
        else:
            k = "LARGO_>=2000"
        bandas[k]["count"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            bandas[k]["lev"] += 1

    items = []
    for nombre, b in bandas.items():
        tasa = round(100 * b["lev"] / b["count"], 2) if b["count"] else 0.0
        items.append(
            {
                "banda": nombre,
                "count": b["count"],
                "levantadas": b["lev"],
                "tasa_levantamiento_pct": tasa,
            }
        )

    return {"items": items}


@stats_router.get("/stats/cargabilidad-equipo")
def stats_cargabilidad_equipo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R223 P1: cargabilidad agregada del equipo.

    Diferente a /admin/stats-asignacion (counts globales) y
    /admin/usuarios-mas-cargados (top): aquí distribución por
    rangos de carga.

    Categoriza gestores por carga abierta:
      - 1-5: ligera
      - 6-15: media
      - 16-30: alta
      - >30: sobrecarga

    Útil para vista del coordinador: "¿hay sobrecarga?"
    """

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    rows = (
        db.query(
            GlosaRecord.gestor_nombre,
            _f.count().label("n"),
        )
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .group_by(GlosaRecord.gestor_nombre)
        .all()
    )

    bandas = {
        "ligera_1a5": 0,
        "media_6a15": 0,
        "alta_16a30": 0,
        "sobrecarga_mas_30": 0,
    }
    for _, n in rows:
        if n <= 5:
            bandas["ligera_1a5"] += 1
        elif n <= 15:
            bandas["media_6a15"] += 1
        elif n <= 30:
            bandas["alta_16a30"] += 1
        else:
            bandas["sobrecarga_mas_30"] += 1

    return {
        "total_gestores_con_carga": len(rows),
        "bandas": bandas,
    }


@stats_router.get("/stats/dictamen-calidad-distribucion")
def stats_dictamen_calidad_distribucion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R222 P1: distribución de longitud de dictamen.

    Categoriza dictámenes por chars:
      - SIN_DICTAMEN: NULL/vacío
      - MUY_CORTO: <100
      - CORTO: 100-499
      - MEDIO: 500-1999
      - LARGO: >=2000

    Útil para entender la calidad de los dictámenes generados.
    """
    glosas = db.query(GlosaRecord).all()

    bandas = {
        "SIN_DICTAMEN": 0,
        "MUY_CORTO": 0,
        "CORTO": 0,
        "MEDIO": 0,
        "LARGO": 0,
    }
    for g in glosas:
        if not g.dictamen or not g.dictamen.strip():
            bandas["SIN_DICTAMEN"] += 1
            continue
        n = len(g.dictamen)
        if n < 100:
            bandas["MUY_CORTO"] += 1
        elif n < 500:
            bandas["CORTO"] += 1
        elif n < 2000:
            bandas["MEDIO"] += 1
        else:
            bandas["LARGO"] += 1

    total = sum(bandas.values())
    items = []
    for nombre, count in bandas.items():
        pct = round(100 * count / total, 2) if total else 0.0
        items.append(
            {
                "banda": nombre,
                "count": count,
                "pct": pct,
            }
        )

    return {
        "total_glosas": total,
        "items": items,
    }


@stats_router.get("/stats/decisiones-eps-detalle")
def stats_decisiones_eps_detalle(
    eps: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R221 P1: distribución detallada de decisiones de una EPS.

    Para una EPS específica, ver el patrón de decisiones:
      - ¿Cuántas LEVANTÓ?
      - ¿Cuántas RATIFICÓ?
      - ¿Cuántas ACEPTÓ?

    Útil para tailoring de estrategia: "SANITAS levanta 60% pero
    rechaza 30%, vs OTRA que levanta 20% y rechaza 70%".

    Param `eps`: nombre exacto.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .all()
    )

    por_estado: dict[str, int] = {}
    for g in glosas:
        e = (g.estado or "").upper()
        por_estado[e] = por_estado.get(e, 0) + 1

    total = sum(por_estado.values())
    items = []
    for estado, count in sorted(por_estado.items()):
        pct = round(100 * count / total, 2) if total else 0.0
        items.append(
            {
                "estado": estado,
                "count": count,
                "pct": pct,
            }
        )

    return {
        "eps": eps,
        "total_decididas": total,
        "items": items,
    }


@stats_router.get("/stats/distribucion-urgencia")
def stats_distribucion_urgencia(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R219 P1: distribución de glosas abiertas por banda urgencia.

    Útil para una vista rápida del semáforo:
      - VENCIDA (dr<0)
      - CRITICA (0..3)
      - PROXIMA (4..7)
      - LEJANA (>7)

    Devuelve por banda: count + valor_total + pct.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    bandas = {
        "VENCIDA": {"count": 0, "valor": 0.0},
        "CRITICA": {"count": 0, "valor": 0.0},
        "PROXIMA": {"count": 0, "valor": 0.0},
        "LEJANA": {"count": 0, "valor": 0.0},
    }
    for g in abiertas:
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            k = "VENCIDA"
        elif dr <= 3:
            k = "CRITICA"
        elif dr <= 7:
            k = "PROXIMA"
        else:
            k = "LEJANA"
        bandas[k]["count"] += 1
        bandas[k]["valor"] += float(g.valor_objetado or 0)

    total = sum(b["count"] for b in bandas.values())
    items = []
    for nombre, b in bandas.items():
        pct = round(100 * b["count"] / total, 2) if total else 0.0
        items.append(
            {
                "banda": nombre,
                "count": b["count"],
                "valor_total": int(b["valor"]),
                "pct": pct,
            }
        )

    return {
        "total_abiertas": total,
        "items": items,
    }


@stats_router.get("/stats/eps-velocidad-respuesta")
def stats_eps_velocidad_respuesta(
    min_glosas: int = Query(3, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R218 P1: tiempo promedio decision por EPS.

    Mide qué tan rápido decide cada EPS comparando creado_en vs
    fecha_decision_eps. Útil para comparar:
      "SANITAS responde en 30 días, NUEVA EPS en 90"

    Solo EPS con >= min_glosas decididas (con fecha_decision_eps
    set).

    Devuelve por EPS:
      - count
      - tiempo_promedio_dias
      - tiempo_max_dias

    Ordenado ASC por tiempo_promedio (más rápidas primero).
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).filter(GlosaRecord.fecha_decision_eps.isnot(None)).all()

    por_eps: dict[str, list[int]] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not cre or not dec:
            continue
        dias = (dec - cre).days
        if dias < 0:
            continue
        por_eps.setdefault(eps, []).append(dias)

    items = []
    for eps, tiempos in por_eps.items():
        if len(tiempos) < min_glosas:
            continue
        promedio = sum(tiempos) / len(tiempos)
        items.append(
            {
                "eps": eps,
                "count": len(tiempos),
                "tiempo_promedio_dias": round(promedio, 2),
                "tiempo_max_dias": max(tiempos),
            }
        )
    items.sort(key=lambda x: x["tiempo_promedio_dias"])

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/antiguedad-promedio-eps")
def stats_antiguedad_promedio_eps(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R214 P1: antigüedad promedio de glosas abiertas por EPS.

    Útil para detectar EPS donde HUS demora mucho en cerrar
    (problemas de comunicación o casos complejos):
      "SANITAS tiene un promedio de 90d, OTRA solo 20d"

    Solo cuenta glosas no-cerradas. Por EPS:
      - count
      - antiguedad_promedio_dias
      - antiguedad_max_dias

    Ordenado DESC por antiguedad_promedio.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    ahora = ahora_utc()
    por_eps: dict[str, list[int]] = {}
    for g in abiertas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        antig = (ahora - cre).days
        por_eps.setdefault(eps, []).append(antig)

    items = []
    for eps, antiguedades in por_eps.items():
        promedio = sum(antiguedades) / len(antiguedades)
        items.append(
            {
                "eps": eps,
                "count": len(antiguedades),
                "antiguedad_promedio_dias": round(promedio, 2),
                "antiguedad_max_dias": max(antiguedades),
            }
        )
    items.sort(
        key=lambda x: x["antiguedad_promedio_dias"],
        reverse=True,
    )

    return {
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/multi-concepto-ratio")
def stats_multi_concepto_ratio(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R213 P1: ratio de glosas multi-concepto vs simples.

    Mide qué porcentaje de las glosas tienen múltiples
    conceptos (ConceptoGlosaRecord) vs son glosas "simples"
    de un solo ítem.

    Útil para entender la complejidad del trabajo:
      - Multi-concepto = más esfuerzo de IA + auditor
      - Simples = trámite directo

    Devuelve totales + ratio_multi_pct + promedio.
    """


    total_glosas = db.query(_f.count(GlosaRecord.id)).scalar() or 0

    rows = (
        db.query(
            ConceptoGlosaRecord.glosa_id,
            _f.count().label("n"),
        )
        .filter(ConceptoGlosaRecord.glosa_id.isnot(None))
        .group_by(ConceptoGlosaRecord.glosa_id)
        .all()
    )

    glosas_con_conceptos = len(rows)
    glosas_multi = sum(1 for _, n in rows if n > 1)
    promedio_conceptos = sum(n for _, n in rows) / len(rows) if rows else 0

    return {
        "total_glosas": int(total_glosas),
        "glosas_con_conceptos": glosas_con_conceptos,
        "glosas_multi_concepto": glosas_multi,
        "glosas_simples": glosas_con_conceptos - glosas_multi,
        "ratio_multi_pct": (
            round(100 * glosas_multi / glosas_con_conceptos, 2) if glosas_con_conceptos else 0.0
        ),
        "promedio_conceptos_por_glosa": round(promedio_conceptos, 2),
    }


@stats_router.get("/stats/audit-mas-cambiada")
def stats_audit_mas_cambiada(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R211 P1: glosas con más eventos audit (más editadas).

    Diferente a /stats/glosas-mas-refinadas (versiones de
    dictamen): aquí TODOS los eventos audit de la glosa.

    Útil para identificar:
      - Casos de litigio complejo con muchos cambios
      - Posible edición sospechosa (modificaciones repetidas)

    Devuelve top N glosas ordenado DESC por eventos audit.
    """


    rows = (
        db.query(
            AuditLogRecord.registro_id,
            _f.count().label("n"),
        )
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.registro_id.isnot(None))
        .group_by(AuditLogRecord.registro_id)
        .order_by(_f.count().desc())
        .limit(int(top))
        .all()
    )

    items = []
    for glosa_id, n in rows:
        g = (
            db.query(GlosaRecord)
            .filter(
                GlosaRecord.id == glosa_id,
            )
            .first()
        )
        if not g:
            continue
        items.append(
            {
                "glosa_id": glosa_id,
                "n_eventos_audit": int(n),
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
            }
        )

    return {
        "top_solicitado": int(top),
        "items": items,
    }


@stats_router.get("/stats/glosas-mas-refinadas")
def stats_glosas_mas_refinadas(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R192 P1: glosas con más versiones de dictamen.

    Glosas que requirieron más iteraciones humanas. Útil para:
      - Detectar casos complejos que necesitan training
      - Identificar problemas con el primer dictamen IA
      - Estudio de "casos atípicos"

    Devuelve top N ordenado DESC por número de versiones.
    """


    rows = (
        db.query(
            DictamenVersionRecord.glosa_id,
            _f.count().label("n_versiones"),
        )
        .group_by(DictamenVersionRecord.glosa_id)
        .order_by(_f.count().desc())
        .limit(int(top))
        .all()
    )

    items = []
    for glosa_id, n in rows:
        if glosa_id is None:
            continue
        g = (
            db.query(GlosaRecord)
            .filter(
                GlosaRecord.id == glosa_id,
            )
            .first()
        )
        if not g:
            continue
        items.append(
            {
                "glosa_id": glosa_id,
                "n_versiones": int(n),
                "eps": g.eps,
                "factura": g.factura,
                "estado": g.estado,
            }
        )

    return {
        "top_solicitado": int(top),
        "items": items,
    }


@stats_router.get("/stats/concentracion-eps")
def stats_concentracion_eps(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R187 P1: índice de concentración por EPS.

    Mide qué tan concentrada está la cartera entre las EPS:
      - HHI (Herfindahl-Hirschman Index) × 10000:
        · <1500 = poco concentrado (sano)
        · 1500-2500 = moderado
        · >2500 = alto (riesgo de dependencia)
      - top_eps_pct: % del valor que viene de la #1
      - top_3_eps_pct: % del valor de las 3 más grandes

    Útil para riesgo: "¿qué pasa si SANITAS quiebra?"
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    por_eps: dict[str, float] = {}
    for g in abiertas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        por_eps[eps] = por_eps.get(eps, 0.0) + float(g.valor_objetado or 0)

    if not por_eps:
        return {
            "total_eps": 0,
            "valor_pendiente_total": 0,
            "hhi": 0.0,
            "top_eps_pct": 0.0,
            "top_3_eps_pct": 0.0,
            "interpretacion": "(sin datos)",
        }

    valor_total = sum(por_eps.values())
    pcts = sorted(
        [v / valor_total for v in por_eps.values()],
        reverse=True,
    )
    hhi = sum(p * p for p in pcts) * 10000

    if hhi < 1500:
        interpretacion = "POCO_CONCENTRADO"
    elif hhi < 2500:
        interpretacion = "MODERADO"
    else:
        interpretacion = "ALTO_RIESGO"

    return {
        "total_eps": len(por_eps),
        "valor_pendiente_total": int(valor_total),
        "hhi": round(hhi, 2),
        "top_eps_pct": round(100 * pcts[0], 2),
        "top_3_eps_pct": round(100 * sum(pcts[:3]), 2),
        "interpretacion": interpretacion,
    }


@stats_router.get("/stats/recuperacion-promedio-por-eps")
def stats_recuperacion_promedio_por_eps(
    min_glosas: int = Query(3, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R182 P1: valor recuperado promedio por glosa, por EPS.

    Diferente a /stats/comparativa-eps (% tasa) y
    /stats/promedio-por-eps (valor objetado): aquí valor
    recuperado promedio por glosa CERRADA.

    Útil para detectar:
      - EPS donde recuperamos más por glosa (rentables)
      - EPS donde recuperamos poco a pesar de mucho esfuerzo

    Filtra por min_glosas (default 3).
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"count": 0, "rec": 0.0, "obj": 0.0}
        b = por_eps[eps]
        b["count"] += 1
        b["rec"] += float(g.valor_recuperado or 0)
        b["obj"] += float(g.valor_objetado or 0)

    items = []
    for eps, b in por_eps.items():
        if b["count"] < min_glosas:
            continue
        promedio = b["rec"] / b["count"] if b["count"] else 0
        tasa = round(100 * b["rec"] / b["obj"], 2) if b["obj"] else 0.0
        items.append(
            {
                "eps": eps,
                "glosas_cerradas": b["count"],
                "valor_recuperado_total": int(b["rec"]),
                "valor_recuperado_promedio": round(promedio, 2),
                "tasa_recuperacion_pct": tasa,
            }
        )
    items.sort(
        key=lambda x: x["valor_recuperado_promedio"],
        reverse=True,
    )

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/eps-actividad-mensual")
def stats_eps_actividad_mensual(
    eps: str = Query(..., min_length=2),
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R181 P1: serie mensual de actividad para una EPS.

    Para una EPS específica, devuelve la evolución mes a mes:
      - cuántas glosas inició
      - cuánto valor objetó
      - cuánto recuperamos

    Útil para gráficos por EPS individual y detectar
    aceleraciones / desaceleraciones:
      "SANITAS pasó de 50 glosas/mes a 200 → algo cambió"

    Param `eps`: nombre exacto.
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).filter(GlosaRecord.eps == eps).all()

    por_mes: dict[str, dict] = {}
    for g in glosas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.strftime("%Y-%m")
        if k not in por_mes:
            por_mes[k] = {
                "count": 0,
                "valor_obj": 0.0,
                "valor_rec": 0.0,
            }
        b = por_mes[k]
        b["count"] += 1
        b["valor_obj"] += float(g.valor_objetado or 0)
        b["valor_rec"] += float(g.valor_recuperado or 0)

    todos_meses = sorted(por_mes.keys())
    meses_recientes = todos_meses[-int(meses) :]
    serie = []
    for k in meses_recientes:
        b = por_mes[k]
        serie.append(
            {
                "mes": k,
                "glosas_iniciadas": b["count"],
                "valor_objetado": int(b["valor_obj"]),
                "valor_recuperado": int(b["valor_rec"]),
            }
        )

    return {
        "eps": eps,
        "meses_solicitados": int(meses),
        "total_meses_disponibles": len(todos_meses),
        "serie": serie,
    }


@stats_router.get("/stats/dashboard-light")
def stats_dashboard_light(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R180 P1: KPIs livianos optimizados para mobile / PWA.

    Endpoint ultraligero — solo COUNTs y SUMs SQL sin iteración
    de Python. Pensado para refresh frecuente en dispositivos
    con bajo ancho de banda.

    6 cifras agregadas que un coordinador querría ver en la
    pantalla principal de la app móvil:
      - total_abiertas
      - total_criticas (0..3 días)
      - total_vencidas (<0 días)
      - valor_pendiente
      - cerradas_hoy
      - valor_recuperado_hoy
    """

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    inicio_hoy = ahora_utc().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    abiertas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar()
        or 0
    )
    criticas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes >= 0)
        .filter(GlosaRecord.dias_restantes <= 3)
        .scalar()
        or 0
    )
    vencidas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < 0)
        .scalar()
        or 0
    )
    valor_pendiente = (
        db.query(_f.coalesce(_f.sum(GlosaRecord.valor_objetado), 0))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar()
        or 0
    )
    cerradas_hoy = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_hoy)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar()
        or 0
    )
    valor_rec_hoy = (
        db.query(_f.coalesce(_f.sum(GlosaRecord.valor_recuperado), 0))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_hoy)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar()
        or 0
    )

    return {
        "total_abiertas": int(abiertas),
        "total_criticas": int(criticas),
        "total_vencidas": int(vencidas),
        "valor_pendiente": int(valor_pendiente),
        "cerradas_hoy": int(cerradas_hoy),
        "valor_recuperado_hoy": int(valor_rec_hoy),
    }


@stats_router.get("/stats/proyeccion-vencimiento")
def stats_proyeccion_vencimiento(
    dias: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R178 P1: glosas que vencen en los próximos N días.

    Distribución de vencimientos por día restante. Útil para
    planeación semanal:
      "En 1 día vencen 5, en 2 días 12, en 3 días 8..."

    Solo cuenta glosas no-cerradas con 0 <= dias_restantes < N.

    Devuelve serie ASC por dias_restantes.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes >= 0)
        .filter(GlosaRecord.dias_restantes < int(dias))
        .all()
    )

    por_dia: dict[int, dict] = {}
    for g in abiertas:
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr not in por_dia:
            por_dia[dr] = {"count": 0, "valor": 0.0}
        por_dia[dr]["count"] += 1
        por_dia[dr]["valor"] += float(g.valor_objetado or 0)

    serie = []
    for dr in sorted(por_dia.keys()):
        b = por_dia[dr]
        serie.append(
            {
                "dias_restantes": dr,
                "count": b["count"],
                "valor_objetado_total": int(b["valor"]),
            }
        )

    return {
        "ventana_dias": int(dias),
        "total_glosas_proximas": sum(s["count"] for s in serie),
        "valor_total_proximas": sum(s["valor_objetado_total"] for s in serie),
        "serie": serie,
    }


@stats_router.get("/stats/transiciones-recientes")
def stats_transiciones_recientes(
    horas: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R177 P1: transiciones de estado recientes.

    Lista las transiciones de estado en audit_log en las últimas
    N horas, agregadas por par (anterior, nuevo):
      "RADICADA → RESPONDIDA: 12 transiciones"
      "RESPONDIDA → LEVANTADA: 8"

    Útil para entender el flujo del proceso en tiempo real.
    """


    desde = ahora_utc() - timedelta(hours=int(horas))
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.campo == "estado")
        .all()
    )

    por_transicion: dict[str, int] = {}
    for e in eventos:
        anterior = e.valor_anterior or "(NULL)"
        nuevo = e.valor_nuevo or "(NULL)"
        key = f"{anterior}|{nuevo}"
        por_transicion[key] = por_transicion.get(key, 0) + 1

    items = []
    for k, count in por_transicion.items():
        anterior, nuevo = k.split("|", 1)
        items.append(
            {
                "anterior": anterior,
                "nuevo": nuevo,
                "count": count,
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "ventana_horas": int(horas),
        "total_transiciones": len(eventos),
        "items": items,
    }


@stats_router.get("/stats/cerradas-hoy")
def stats_cerradas_hoy(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R176 P1: contador en vivo de glosas cerradas hoy.

    Cuenta glosas con fecha_decision_eps en el día actual y
    estado en cerrados.

    Devuelve:
      - count
      - levantadas / aceptadas
      - valor_recuperado_total
      - tasa_levantamiento_pct
    """
    inicio_hoy = ahora_utc().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= inicio_hoy)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    levantadas = 0
    aceptadas = 0
    valor_rec = 0.0
    for g in glosas:
        e = (g.estado or "").upper()
        if e == "LEVANTADA":
            levantadas += 1
        elif e == "ACEPTADA":
            aceptadas += 1
        valor_rec += float(g.valor_recuperado or 0)

    decididas = levantadas + aceptadas
    tasa = round(100 * levantadas / decididas, 2) if decididas else 0.0

    return {
        "fecha": inicio_hoy.date().isoformat(),
        "count": len(glosas),
        "levantadas": levantadas,
        "aceptadas": aceptadas,
        "valor_recuperado_total": int(valor_rec),
        "tasa_levantamiento_pct": tasa,
    }


@stats_router.get("/stats/creadas-hoy")
def stats_creadas_hoy(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R175 P1: contador en vivo de glosas creadas hoy.

    Endpoint MUY ligero. Devuelve los KPIs del día corriente:
      - count
      - valor_objetado_total
      - epss_distintas
      - facturas_distintas

    Útil para refresh frecuente en pantalla de monitoreo.
    """

    inicio_hoy = ahora_utc().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    glosas_hoy = db.query(GlosaRecord).filter(GlosaRecord.creado_en >= inicio_hoy).all()

    eps_set: set[str] = set()
    fac_set: set[str] = set()
    valor_total = 0.0
    for g in glosas_hoy:
        if g.eps:
            eps_set.add(g.eps)
        if g.factura and g.factura != "N/A":
            fac_set.add(g.factura)
        valor_total += float(g.valor_objetado or 0)

    return {
        "fecha": inicio_hoy.date().isoformat(),
        "count": len(glosas_hoy),
        "valor_objetado_total": int(valor_total),
        "epss_distintas": len(eps_set),
        "facturas_distintas": len(fac_set),
    }


@stats_router.get("/stats/analizadas-hoy")
def stats_analizadas_hoy(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R174 P1: glosas con dictamen creado o actualizado hoy.

    Cuenta glosas con DictamenVersionRecord cuya creado_en es
    hoy (UTC). Útil para ver el ritmo del día:
      "Hoy ya se generaron/refinaron 27 dictámenes"

    Devuelve:
      - dictamenes_hoy
      - glosas_distintas_hoy
      - por_accion (CREAR/REFINAR/REGENERAR/RESTAURAR)
      - por_autor: top 5
    """


    ahora = ahora_utc()
    inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

    versiones = (
        db.query(DictamenVersionRecord).filter(DictamenVersionRecord.creado_en >= inicio_hoy).all()
    )

    glosas_set: set[int] = set()
    por_accion: dict[str, int] = {}
    por_autor: dict[str, int] = {}
    for v in versiones:
        if v.glosa_id:
            glosas_set.add(v.glosa_id)
        if v.accion:
            por_accion[v.accion] = por_accion.get(v.accion, 0) + 1
        if v.autor_email:
            por_autor[v.autor_email] = por_autor.get(v.autor_email, 0) + 1

    top_5 = sorted(
        por_autor.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    return {
        "fecha": inicio_hoy.date().isoformat(),
        "dictamenes_hoy": len(versiones),
        "glosas_distintas_hoy": len(glosas_set),
        "por_accion": por_accion,
        "top_5_autores": [{"autor": u, "acciones": n} for u, n in top_5],
    }


@stats_router.get("/stats/cerradas-por-etapa")
def stats_cerradas_por_etapa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R173 P1: distribución de glosas cerradas por etapa final.

    Diferente a /stats/por-etapa-actual (snapshot pipeline):
    aquí solo glosas en estados cerrados, agrupadas por la etapa
    en la que se cerraron.

    Útil para responder: "¿la mayoría de glosas se resuelven en
    primera respuesta o llegan a ratificación/conciliación?"

    Devuelve por etapa:
      - count
      - valor_recuperado_total
      - tasa_levantamiento_pct (LEVANTADA / cerradas en esa etapa)
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    por_etapa: dict[str, dict] = {}
    for g in glosas:
        etapa = (g.etapa or "(SIN_ETAPA)").strip() or "(SIN_ETAPA)"
        if etapa not in por_etapa:
            por_etapa[etapa] = {
                "count": 0,
                "levantadas": 0,
                "valor_rec": 0.0,
            }
        b = por_etapa[etapa]
        b["count"] += 1
        b["valor_rec"] += float(g.valor_recuperado or 0)
        if (g.estado or "").upper() == "LEVANTADA":
            b["levantadas"] += 1

    items = []
    for etapa, b in por_etapa.items():
        tasa = round(100 * b["levantadas"] / b["count"], 2) if b["count"] else 0.0
        items.append(
            {
                "etapa": etapa,
                "count": b["count"],
                "valor_recuperado_total": int(b["valor_rec"]),
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_glosas_cerradas": sum(it["count"] for it in items),
        "items": items,
    }


@stats_router.get("/stats/valor-objetado-mensual")
def stats_valor_objetado_mensual(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r"""R172 P1: serie mensual del valor objetado (no recuperado).

    Diferente a /stats/recuperacion-mensual (valor RECUPERADO):
    aquí valor OBJETADO en el mes que se creó la glosa, útil
    para visualizar la "presión" mensual sobre HUS:
      - "EPS objetaron \$500M en marzo"
      - "Solo \$50M en abril → menor presión"

    Devuelve serie ASC por mes:
      - mes (YYYY-MM)
      - count_glosas
      - valor_objetado_total
      - valor_promedio
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).all()

    por_mes: dict[str, dict] = {}
    for g in glosas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if not cre:
            continue
        k = cre.strftime("%Y-%m")
        if k not in por_mes:
            por_mes[k] = {"count": 0, "valor": 0.0}
        por_mes[k]["count"] += 1
        por_mes[k]["valor"] += float(g.valor_objetado or 0)

    todos_meses = sorted(por_mes.keys())
    meses_recientes = todos_meses[-int(meses) :]

    serie = []
    for k in meses_recientes:
        b = por_mes[k]
        promedio = b["valor"] / b["count"] if b["count"] else 0
        serie.append(
            {
                "mes": k,
                "count_glosas": b["count"],
                "valor_objetado_total": int(b["valor"]),
                "valor_promedio": round(promedio, 2),
            }
        )

    return {
        "meses_solicitados": int(meses),
        "total_meses_disponibles": len(todos_meses),
        "serie": serie,
    }


@stats_router.get("/stats/cups-sin-tarifa")
def stats_cups_sin_tarifa(
    eps: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R170 P1: CUPS objetados por una EPS pero SIN tarifa cargada.

    Para una EPS específica, lista los CUPS que aparecen en
    glosas TA* pero no tienen entrada en
    TarifaContratadaRecord.

    Útil para priorizar la carga de tarifas:
      "Carguen primero los CUPS que SANITAS más nos objeta"

    Ordenado DESC por frecuencia de aparición en glosas.

    Param `eps`: nombre exacto de la EPS.
    """
    cups_con_tarifa = {
        t.codigo_cups
        for t in (
            db.query(TarifaContratadaRecord)
            .filter(TarifaContratadaRecord.eps == eps)
            .filter(TarifaContratadaRecord.codigo_cups.isnot(None))
            .all()
        )
    }

    # Conceptos TA* de glosas de esta EPS
    glosas_eps = db.query(GlosaRecord.id).filter(GlosaRecord.eps == eps).all()
    glosa_ids = {g[0] for g in glosas_eps}

    if not glosa_ids:
        return {
            "eps": eps,
            "total_cups_sin_tarifa": 0,
            "items": [],
        }

    conceptos = (
        db.query(ConceptoGlosaRecord)
        .filter(ConceptoGlosaRecord.glosa_id.in_(glosa_ids))
        .filter(ConceptoGlosaRecord.codigo_glosa.like("TA%"))
        .filter(ConceptoGlosaRecord.cups_codigo.isnot(None))
        .all()
    )

    por_cups: dict[str, dict] = {}
    for c in conceptos:
        if c.cups_codigo in cups_con_tarifa:
            continue
        cups = c.cups_codigo
        if cups not in por_cups:
            por_cups[cups] = {
                "frecuencia": 0,
                "valor": 0.0,
                "descripcion": c.cups_descripcion or "",
            }
        por_cups[cups]["frecuencia"] += 1
        por_cups[cups]["valor"] += float(c.valor_objetado or 0)

    items = []
    for cups, b in por_cups.items():
        items.append(
            {
                "cups_codigo": cups,
                "cups_descripcion": (b["descripcion"] or "")[:200],
                "frecuencia": b["frecuencia"],
                "valor_total_objetado": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["frecuencia"], reverse=True)

    return {
        "eps": eps,
        "total_cups_sin_tarifa": len(items),
        "items": items[:50],
    }


@stats_router.get("/stats/tarifa-coincidente")
def stats_tarifa_coincidente(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R169 P1: glosas TA* con tarifa pactada en el catálogo.

    Detecta cuántas glosas tipo TARIFA (codigo_glosa empieza
    con "TA") tienen una tarifa correspondiente cargada en
    TarifaContratadaRecord para esa EPS+CUPS.

    Si está cargada → la IA puede comparar valor pactado vs
    facturado automáticamente.
    Si NO está cargada → la IA tiene que improvisar.

    Útil para medir el % de glosas TA con base de comparación
    sólida.
    """
    conceptos_ta = (
        db.query(ConceptoGlosaRecord)
        .filter(ConceptoGlosaRecord.codigo_glosa.like("TA%"))
        .filter(ConceptoGlosaRecord.cups_codigo.isnot(None))
        .all()
    )

    if not conceptos_ta:
        return {
            "total_conceptos_ta": 0,
            "con_tarifa_pactada": 0,
            "sin_tarifa_pactada": 0,
            "cobertura_pct": 0.0,
        }

    # Set de (eps, cups) con tarifa cargada
    tarifas_set: set[tuple[str, str]] = set()
    for t in db.query(TarifaContratadaRecord).all():
        if t.eps and t.codigo_cups:
            tarifas_set.add((t.eps, t.codigo_cups))

    # Para cada concepto, ver si su (eps_de_la_glosa, cups) está
    glosa_ids = {c.glosa_id for c in conceptos_ta if c.glosa_id}
    eps_por_glosa = {}
    if glosa_ids:
        for g in db.query(GlosaRecord).filter(GlosaRecord.id.in_(glosa_ids)).all():
            eps_por_glosa[g.id] = g.eps

    con_tarifa = 0
    sin_tarifa = 0
    for c in conceptos_ta:
        eps = eps_por_glosa.get(c.glosa_id)
        if not eps:
            sin_tarifa += 1
            continue
        if (eps, c.cups_codigo) in tarifas_set:
            con_tarifa += 1
        else:
            sin_tarifa += 1

    total = con_tarifa + sin_tarifa
    cobertura = round(100 * con_tarifa / total, 2) if total else 0.0

    return {
        "total_conceptos_ta": total,
        "con_tarifa_pactada": con_tarifa,
        "sin_tarifa_pactada": sin_tarifa,
        "cobertura_pct": cobertura,
    }


@stats_router.get("/stats/sin-dictamen")
def stats_sin_dictamen(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R167 P1: glosas no-cerradas sin dictamen alguno.

    Diferente a /stats/dictamenes-cortos (dictamen pero pobre):
    aquí dictamen es NULL o vacío. Estas glosas requieren
    pre-análisis IA o trabajo humano antes de poder responder.

    Útil para alimentar cola de pre-análisis automático.

    Devuelve top 50 priorizadas por dias_restantes ASC (las más
    urgentes primero).
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    items = []
    for g in glosas:
        if not g.dictamen or not g.dictamen.strip():
            items.append(
                {
                    "id": g.id,
                    "eps": g.eps,
                    "factura": g.factura,
                    "estado": g.estado,
                    "dias_restantes": g.dias_restantes,
                    "valor_objetado": float(g.valor_objetado or 0),
                }
            )
    items.sort(
        key=lambda x: x["dias_restantes"] if x["dias_restantes"] is not None else 9999,
    )

    return {
        "total_sin_dictamen": len(items),
        "items": items[:50],
    }


@stats_router.get("/stats/dictamenes-cortos")
def stats_dictamenes_cortos(
    umbral_chars: int = Query(200, ge=50, le=2000),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R166 P1: glosas con dictamen muy corto (calidad sospechosa).

    Identifica glosas cuyo dictamen tiene < umbral_chars caracteres,
    señal de:
      - Dictamen IA mal generado (timeout/error)
      - Dictamen sin argumentación suficiente
      - Glosa abandonada con texto placeholder

    Útil como cola de revisión: "estos casos necesitan reanálisis
    o refinamiento humano".

    Solo cuenta glosas no-cerradas (cerradas ya pasaron filtro EPS).

    Devuelve top 50 con menos chars.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    glosas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dictamen.isnot(None))
        .all()
    )

    items = []
    for g in glosas:
        dlen = len(g.dictamen or "")
        if dlen < umbral_chars:
            items.append(
                {
                    "id": g.id,
                    "eps": g.eps,
                    "factura": g.factura,
                    "estado": g.estado,
                    "dictamen_chars": dlen,
                    "valor_objetado": float(g.valor_objetado or 0),
                }
            )
    items.sort(key=lambda x: x["dictamen_chars"])

    return {
        "umbral_chars": int(umbral_chars),
        "total_dictamenes_cortos": len(items),
        "items": items[:50],
    }


@stats_router.get("/stats/comentarios-globales")
def stats_comentarios_globales(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R160 P1: estadísticas globales del hilo de comentarios.

    Mide la actividad colaborativa del equipo (comentarios entre
    auditores en glosas):
      - cuántos comentarios hubo
      - quién comenta más
      - cuántas menciones sin resolver

    Útil para entender el nivel de colaboración:
      - Pocos comentarios → trabajo siloed
      - Muchas menciones sin resolver → comunicación trabada

    Ventana default 30d.
    """


    desde = ahora_utc() - timedelta(days=int(dias))
    coms = db.query(ComentarioGlosaRecord).filter(ComentarioGlosaRecord.creado_en >= desde).all()

    por_autor: dict[str, int] = {}
    glosas_set: set[int] = set()
    menciones_total = 0
    menciones_resueltas = 0
    for c in coms:
        if c.autor_email:
            por_autor[c.autor_email] = por_autor.get(c.autor_email, 0) + 1
        if c.glosa_id is not None:
            glosas_set.add(c.glosa_id)
        if c.mencion:
            menciones_total += 1
            if c.resuelto:
                menciones_resueltas += 1

    top_5 = sorted(
        por_autor.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    return {
        "ventana_dias": int(dias),
        "total_comentarios": len(coms),
        "glosas_con_comentarios": len(glosas_set),
        "menciones_totales": menciones_total,
        "menciones_resueltas": menciones_resueltas,
        "menciones_pendientes": menciones_total - menciones_resueltas,
        "top_5_comentaristas": [{"autor": u, "comentarios": n} for u, n in top_5],
    }


@stats_router.get("/stats/por-anio")
def stats_por_anio(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R157 P2: serie anual de glosas creadas y cerradas.

    Vista de largo plazo de la operación. Útil para reporting
    a JD / gerencia ("evolución últimos 5 años") y comparativos
    año vs año.

    Por año:
      - creadas: glosas con creado_en en el año
      - cerradas: glosas con fecha_decision_eps en el año
      - valor_recuperado_anual

    Devuelve serie ascendente.
    """
    from datetime import timezone

    glosas = db.query(GlosaRecord).all()

    por_anio: dict[str, dict] = {}

    def _ensure(k):
        if k not in por_anio:
            por_anio[k] = {
                "creadas": 0,
                "cerradas": 0,
                "valor_rec": 0.0,
            }
        return por_anio[k]

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    for g in glosas:
        cre = g.creado_en
        if cre and cre.tzinfo is None:
            cre = cre.replace(tzinfo=timezone.utc)
        if cre:
            _ensure(str(cre.year))["creadas"] += 1

        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        estado = (g.estado or "").upper()
        if dec and estado in ESTADOS_CERRADOS:
            b = _ensure(str(dec.year))
            b["cerradas"] += 1
            b["valor_rec"] += float(g.valor_recuperado or 0)

    serie = []
    for k in sorted(por_anio.keys()):
        b = por_anio[k]
        serie.append(
            {
                "anio": k,
                "creadas": b["creadas"],
                "cerradas": b["cerradas"],
                "valor_recuperado": int(b["valor_rec"]),
            }
        )

    return {
        "total_anios_con_actividad": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/por-dia-semana")
def stats_por_dia_semana(
    dias: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R141 P2: distribución de glosas creadas por día de la semana.

    Diferente a /stats/heatmap-actividad (matriz día×hora):
    aquí solo el día sumado, útil para responder "¿se crean más
    glosas los lunes que los viernes?"

    Útil para planeación:
      - Spike los lunes → reforzar capacidad lunes
      - Caída los viernes → ¿hay backlog que limpiar?

    Devuelve por día de semana (Lunes...Domingo):
      - dia (nombre)
      - count, valor_total, pct_del_total
    """
    from datetime import timezone

    DIAS_NOMBRE = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    desde = ahora_utc() - timedelta(days=int(dias))
    glosas = db.query(GlosaRecord).filter(GlosaRecord.creado_en >= desde).all()

    por_dia = [{"dia": DIAS_NOMBRE[i], "count": 0, "valor_total": 0.0} for i in range(7)]

    for g in glosas:
        creado = g.creado_en
        if creado and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        if not creado:
            continue
        idx = creado.weekday()  # Monday=0 ... Sunday=6
        por_dia[idx]["count"] += 1
        por_dia[idx]["valor_total"] += float(g.valor_objetado or 0)

    total_count = sum(d["count"] for d in por_dia)
    for d in por_dia:
        d["pct_del_total"] = round(100 * d["count"] / total_count, 2) if total_count else 0.0
        d["valor_total"] = int(d["valor_total"])

    return {
        "ventana_dias": int(dias),
        "total_glosas": total_count,
        "items": por_dia,
    }


@stats_router.get("/stats/pacientes-frecuentes")
def stats_pacientes_frecuentes(
    top: int = Query(20, ge=1, le=100),
    min_glosas: int = Query(2, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R141 P1: pacientes con más glosas asociadas.

    Útil para detectar:
      - Pacientes complejos con múltiples hospitalizaciones
      - Casos de litigio prioritario (mismo paciente, varias glosas)
      - Posibles patrones clínicos sistémicos

    Devuelve top N pacientes con >= min_glosas (default 2):
      - paciente
      - count_glosas
      - facturas_distintas
      - eps_distintas
      - valor_objetado_total
    """
    glosas = db.query(GlosaRecord).filter(GlosaRecord.paciente.isnot(None)).all()

    por_paciente: dict[str, dict] = {}
    for g in glosas:
        nombre = (g.paciente or "").strip()
        if not nombre:
            continue
        if nombre not in por_paciente:
            por_paciente[nombre] = {
                "count": 0,
                "facturas": set(),
                "epss": set(),
                "valor": 0.0,
            }
        b = por_paciente[nombre]
        b["count"] += 1
        if g.factura and g.factura != "N/A":
            b["facturas"].add(g.factura)
        if g.eps:
            b["epss"].add(g.eps)
        b["valor"] += float(g.valor_objetado or 0)

    items = []
    for paciente, b in por_paciente.items():
        if b["count"] < min_glosas:
            continue
        items.append(
            {
                "paciente": paciente,
                "count_glosas": b["count"],
                "facturas_distintas": len(b["facturas"]),
                "eps_distintas": len(b["epss"]),
                "valor_objetado_total": int(b["valor"]),
            }
        )
    items.sort(key=lambda x: x["count_glosas"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_pacientes_recurrentes": len(items),
        "items": items[:top],
    }


@stats_router.get("/stats/cups-mas-objetados")
def stats_cups_mas_objetados(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R140 P1: ranking de CUPS más objetados por las EPS.

    Cruza ConceptoGlosaRecord por cups_codigo para identificar
    qué servicios/procedimientos son los más objetados.

    Útil para:
      - Capacitación a facturación: "ojo con estos CUPS"
      - Análisis con departamentos clínicos
      - Negociación de tarifas: si CUPS X siempre objetado por
        diferencia de tarifa → revisar contrato

    Devuelve top N CUPS con:
      - cups_codigo + descripcion
      - frecuencia
      - valor_objetado_total
      - facturas_distintas
    """
    conceptos = (
        db.query(ConceptoGlosaRecord).filter(ConceptoGlosaRecord.cups_codigo.isnot(None)).all()
    )

    por_cups: dict[str, dict] = {}
    for c in conceptos:
        cups = c.cups_codigo
        if not cups:
            continue
        if cups not in por_cups:
            por_cups[cups] = {
                "descripcion": c.cups_descripcion or "",
                "frecuencia": 0,
                "valor": 0.0,
                "facturas": set(),
            }
        b = por_cups[cups]
        b["frecuencia"] += 1
        b["valor"] += float(c.valor_objetado or 0)
        if c.factura:
            b["facturas"].add(c.factura)

    items = []
    for cups, b in por_cups.items():
        items.append(
            {
                "cups_codigo": cups,
                "cups_descripcion": (b["descripcion"] or "")[:200],
                "frecuencia": b["frecuencia"],
                "valor_objetado_total": int(b["valor"]),
                "facturas_distintas": len(b["facturas"]),
            }
        )
    items.sort(key=lambda x: x["frecuencia"], reverse=True)

    return {
        "total_cups_unicos": len(items),
        "top_solicitado": int(top),
        "items": items[:top],
    }


@stats_router.get("/stats/correlacion-codigos")
def stats_correlacion_codigos(
    top: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R108 P2: pares de códigos de glosa que aparecen juntos en una factura.

    Cruza ConceptoGlosaRecord (multi-concepto por glosa) para
    detectar patrones de co-ocurrencia: "cuando objetan TA0201,
    también suelen objetar FA0603".

    Útil para:
      - Anticipar argumentación: si veo TA0201, prepararme para
        FA0603 también
      - Detectar bundles típicos de objeción de cada EPS
      - Capacitación: "estos códigos van casi siempre juntos"

    Devuelve top N pares ordenados DESC por co-frecuencia:
      [{"codigo_a": "TA0201", "codigo_b": "FA0603",
        "co_frecuencia": 12, "facturas": ["F001", "F015", ...]}, ...]
    """
    from itertools import combinations

    conceptos = db.query(ConceptoGlosaRecord).all()

    # Agrupar códigos por factura
    por_factura: dict[str, set[str]] = {}
    for c in conceptos:
        if not c.factura or not c.codigo_glosa:
            continue
        por_factura.setdefault(c.factura, set()).add(c.codigo_glosa)

    # Contar pares
    pares: dict[tuple, dict] = {}
    for factura, codigos in por_factura.items():
        if len(codigos) < 2:
            continue
        codigos_lista = sorted(codigos)
        for a, b in combinations(codigos_lista, 2):
            key = (a, b)
            if key not in pares:
                pares[key] = {"co_frecuencia": 0, "facturas": []}
            pares[key]["co_frecuencia"] += 1
            if len(pares[key]["facturas"]) < 5:  # cap muestra
                pares[key]["facturas"].append(factura)

    items = [
        {
            "codigo_a": a,
            "codigo_b": b,
            "co_frecuencia": v["co_frecuencia"],
            "facturas_muestra": v["facturas"],
        }
        for (a, b), v in pares.items()
    ]
    items.sort(key=lambda x: x["co_frecuencia"], reverse=True)

    return {
        "total_pares_unicos": len(items),
        "top_solicitado": int(top),
        "items": items[:top],
    }


@stats_router.get("/stats/cohorte-mensual")
def stats_cohorte_mensual(
    meses: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R103 P1: cohort analysis de glosas por mes de creación.

    Para cada cohorte mensual (mes en que se creó la glosa),
    calcula qué % se cerraron dentro de 30/60/90 días.

    Útil para identificar si el equipo mejora con el tiempo:
      - ¿Cohorte de marzo cierra al 30d más rápido que cohorte de enero?
      - ¿Empeoró tras nuevo proceso/cambio?

    Devuelve serie ordenada por mes con métricas de retención
    (% aún sin cerrar a los 30/60/90 días).

    Estados cerrados: ACEPTADA, LEVANTADA, ARCHIVADA, CONCILIADA.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    corte = ahora_utc() - timedelta(days=int(meses) * 31)
    glosas = db.query(GlosaRecord).filter(GlosaRecord.creado_en >= corte).all()

    cohortes: dict[str, list] = {}
    for g in glosas:
        creado = g.creado_en
        if not creado:
            continue
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        key = creado.strftime("%Y-%m")
        cohortes.setdefault(key, []).append(g)

    serie = []
    for key in sorted(cohortes.keys()):
        cohorte = cohortes[key]
        total = len(cohorte)
        cerradas_30 = 0
        cerradas_60 = 0
        cerradas_90 = 0
        for g in cohorte:
            estado = (g.estado or "").upper()
            if estado not in ESTADOS_CERRADOS:
                continue
            if not (g.fecha_decision_eps and g.creado_en):
                continue
            dec = g.fecha_decision_eps
            cre = g.creado_en
            if dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)
            if cre.tzinfo is None:
                cre = cre.replace(tzinfo=timezone.utc)
            dias = (dec - cre).days
            if dias <= 30:
                cerradas_30 += 1
            if dias <= 60:
                cerradas_60 += 1
            if dias <= 90:
                cerradas_90 += 1

        serie.append(
            {
                "cohorte": key,
                "total_glosas": total,
                "cierre_30d_pct": round(100 * cerradas_30 / total, 2),
                "cierre_60d_pct": round(100 * cerradas_60 / total, 2),
                "cierre_90d_pct": round(100 * cerradas_90 / total, 2),
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_cohortes": len(serie),
        "serie": serie,
    }


@stats_router.get("/stats/proyeccion-recuperacion")
def stats_proyeccion_recuperacion(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R102 P2: forecast simple de recuperación esperada.

    Usa la tasa histórica de recuperación (sobre glosas cerradas)
    aplicada al valor pendiente como predicción gruesa de cuánto
    podría recuperar el HUS si el patrón histórico se mantiene.

    Útil para:
      - Cash flow planning del coordinador
      - Reporte ejecutivo con proyección
      - Detectar cuándo la pendiente excede capacidad histórica

    NO es ML — es una regla simple. Para una proyección más
    sofisticada usar /analitica-predictiva.

    Devuelve:
      - tasa_historica_recuperacion_pct
      - valor_pendiente_total (no cerradas)
      - proyeccion_recuperable
      - intervalo: {"min": ..., "max": ...} con ±20% de margen
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas = db.query(GlosaRecord).all()

    cerradas_obj = 0.0
    cerradas_rec = 0.0
    pendientes_obj = 0.0
    pendientes_count = 0

    for g in todas:
        estado = (g.estado or "").upper()
        v_obj = float(g.valor_objetado or 0)
        if estado in ESTADOS_CERRADOS:
            cerradas_obj += v_obj
            cerradas_rec += float(g.valor_recuperado or 0)
        else:
            pendientes_obj += v_obj
            pendientes_count += 1

    tasa = round(100 * cerradas_rec / cerradas_obj, 2) if cerradas_obj else 0.0

    proyeccion = pendientes_obj * (tasa / 100)

    # Intervalo ±20% como margen de incertidumbre
    margen = proyeccion * 0.20

    return {
        "tasa_historica_recuperacion_pct": tasa,
        "valor_pendiente_total": int(pendientes_obj),
        "glosas_pendientes": pendientes_count,
        "proyeccion_recuperable": int(proyeccion),
        "intervalo": {
            "min": int(max(0, proyeccion - margen)),
            "max": int(proyeccion + margen),
            "margen_pct": 20,
        },
        "basado_en_glosas_cerradas": int(cerradas_obj > 0),
    }


@stats_router.get("/stats/dashboard-snapshot")
def stats_dashboard_snapshot(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R109 P2: snapshot agregado para dashboard ejecutivo (single-call).

    Combina las métricas más usadas del dashboard en un solo
    round-trip. Reduce latencia y simplifica el frontend.

    Devuelve:
      - kpis: counts globales (total, abiertas, cerradas, vencidas,
              criticas, en_tiempo)
      - economico: valor_objetado_total, valor_recuperado_total,
                   tasa_recuperacion_pct
      - resoluciones: tasa_levantamiento_pct
      - sla: % en tiempo, criticas, vencidas

    Si necesitas más detalle, usar endpoints específicos
    (cumplimiento-sla, comparativa-eps, recuperacion-mensual).
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ESTADOS_DECIDIDOS = ESTADOS_CERRADOS | {"RATIFICADA"}

    todas = db.query(GlosaRecord).all()
    total = len(todas)

    abiertas = 0
    cerradas = 0
    vencidas = 0
    criticas = 0
    en_tiempo = 0
    levantadas = 0
    decididas = 0
    valor_obj_total = 0.0
    valor_rec_total = 0.0

    for g in todas:
        estado = (g.estado or "").upper()
        v_obj = float(g.valor_objetado or 0)
        valor_obj_total += v_obj
        valor_rec_total += float(g.valor_recuperado or 0)

        if estado in ESTADOS_CERRADOS:
            cerradas += 1
        else:
            abiertas += 1
            dr = g.dias_restantes if g.dias_restantes is not None else 0
            if dr < 0:
                vencidas += 1
            elif dr <= 3:
                criticas += 1
            else:
                en_tiempo += 1

        if estado in ESTADOS_DECIDIDOS:
            decididas += 1
            if estado == "LEVANTADA":
                levantadas += 1

    return {
        "kpis": {
            "total": total,
            "abiertas": abiertas,
            "cerradas": cerradas,
            "vencidas": vencidas,
            "criticas": criticas,
            "en_tiempo": en_tiempo,
        },
        "economico": {
            "valor_objetado_total": int(valor_obj_total),
            "valor_recuperado_total": int(valor_rec_total),
            "tasa_recuperacion_pct": (
                round(100 * valor_rec_total / valor_obj_total, 2) if valor_obj_total else 0.0
            ),
        },
        "resoluciones": {
            "decididas": decididas,
            "levantadas": levantadas,
            "tasa_levantamiento_pct": (
                round(100 * levantadas / decididas, 2) if decididas else 0.0
            ),
        },
        "sla": {
            "vencidas": vencidas,
            "criticas": criticas,
            "en_tiempo": en_tiempo,
            "pct_en_tiempo": (round(100 * en_tiempo / abiertas, 2) if abiertas else 0.0),
        },
        "generado_en": ahora_utc().isoformat(),
    }


@stats_router.get("/stats/cuellos-botella")
def stats_cuellos_botella(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R135 P1: detecta etapas con tiempo elevado (cuellos de botella).

    Diferente a /stats/abandono-por-etapa (% abiertas): aquí mide
    TIEMPO promedio que las glosas pasan en cada estado antes
    de transicionar al siguiente, usando transiciones del
    audit_log (campo='estado').

    Útil para identificar:
      - Estados que requieren más recursos
      - Procesos lentos que necesitan optimización
      - Comparación HUS vs SLA de la Resolución

    Devuelve por estado:
      - count_glosas_con_transicion
      - tiempo_promedio_dias
      - tiempo_mediano_dias
    Ordenado DESC por tiempo_promedio.
    """
    from datetime import timezone

    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.tabla == "glosas")
        .filter(AuditLogRecord.campo == "estado")
        .filter(AuditLogRecord.timestamp.isnot(None))
        .filter(AuditLogRecord.registro_id.isnot(None))
        .order_by(
            AuditLogRecord.registro_id.asc(),
            AuditLogRecord.timestamp.asc(),
        )
        .all()
    )

    # Agrupar por glosa, ordenadas cronológicamente.
    # Por cada evento guardamos (timestamp, valor_nuevo). El estado en
    # el que está la glosa entre evento[i] y evento[i+1] es valor_nuevo
    # del evento[i] (el "destino" de esa transición).
    por_glosa: dict[int, list] = {}
    for e in eventos:
        ts = e.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        por_glosa.setdefault(e.registro_id, []).append((ts, e.valor_nuevo))

    # Para cada glosa, tiempo entre transiciones consecutivas
    por_estado: dict[str, list[float]] = {}
    for transiciones in por_glosa.values():
        transiciones.sort(key=lambda x: x[0])
        for i in range(1, len(transiciones)):
            ts_prev, estado_durante = transiciones[i - 1]
            ts_act, _ = transiciones[i]
            if not estado_durante or not ts_prev or not ts_act:
                continue
            dias = (ts_act - ts_prev).total_seconds() / 86400
            if dias < 0:
                continue
            por_estado.setdefault(estado_durante, []).append(dias)

    items = []
    for estado, tiempos in por_estado.items():
        tiempos.sort()
        n = len(tiempos)
        promedio = sum(tiempos) / n
        if n % 2 == 0:
            mediano = (tiempos[n // 2 - 1] + tiempos[n // 2]) / 2
        else:
            mediano = tiempos[n // 2]
        items.append(
            {
                "estado": estado,
                "count_glosas_con_transicion": n,
                "tiempo_promedio_dias": round(promedio, 2),
                "tiempo_mediano_dias": round(mediano, 2),
            }
        )
    items.sort(
        key=lambda x: x["tiempo_promedio_dias"],
        reverse=True,
    )

    return {
        "total_estados_con_data": len(items),
        "items": items,
    }


@stats_router.get("/stats/abandono-por-etapa")
def stats_abandono_por_etapa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R106 P1: identifica en qué etapa se "atascan" más las glosas.

    Útil para detectar bottlenecks del proceso:
      - ¿Las glosas mueren en RESPUESTA_PRIMERA?
      - ¿Hay un cuello en RATIFICACION?

    Devuelve por etapa:
      - total_glosas
      - abiertas (no cerradas)
      - tasa_abandono_pct (% que sigue en esta etapa)
      - tiempo_promedio_dias (cuánto llevan en la etapa, basado en
        días desde creación)

    Ordenado DESC por tasa_abandono_pct.
    """
    from datetime import timezone

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas = db.query(GlosaRecord).all()
    ahora = ahora_utc()

    por_etapa: dict[str, dict] = {}
    for g in todas:
        etapa = (g.etapa or "SIN_ETAPA").strip() or "SIN_ETAPA"
        if etapa not in por_etapa:
            por_etapa[etapa] = {
                "total": 0,
                "abiertas": 0,
                "tiempos": [],
            }
        b = por_etapa[etapa]
        b["total"] += 1

        estado = (g.estado or "").upper()
        if estado not in ESTADOS_CERRADOS:
            b["abiertas"] += 1
            if g.creado_en:
                creado = g.creado_en
                if creado.tzinfo is None:
                    creado = creado.replace(tzinfo=timezone.utc)
                b["tiempos"].append((ahora - creado).days)

    items = []
    for etapa, b in por_etapa.items():
        tiempo_prom = round(sum(b["tiempos"]) / len(b["tiempos"]), 2) if b["tiempos"] else 0.0
        tasa = round(100 * b["abiertas"] / b["total"], 2) if b["total"] else 0.0
        items.append(
            {
                "etapa": etapa,
                "total_glosas": b["total"],
                "abiertas": b["abiertas"],
                "tasa_abandono_pct": tasa,
                "tiempo_promedio_dias_abiertas": tiempo_prom,
            }
        )

    items.sort(key=lambda x: x["tasa_abandono_pct"], reverse=True)

    return {
        "total_etapas": len(items),
        "items": items,
    }


@stats_router.get("/stats/codigos-respuesta-por-eps")
def stats_codigos_respuesta_por_eps(
    eps: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R145 P1: efectividad de cada código de respuesta IPS contra
    una EPS específica.

    Diferente a /stats/exito-por-codigo-respuesta (global): aquí
    se filtra a una EPS para descubrir qué argumentos funcionan
    mejor contra esa EPS:
      "Contra SANITAS, RE9502 levanta 80%; contra NUEVA EPS, 30%."

    Útil para tailoring de estrategia por EPS.

    Param `eps`: nombre exacto de la EPS.
    """
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .filter(GlosaRecord.codigo_respuesta.isnot(None))
        .all()
    )

    por_codigo: dict[str, dict] = {}
    for g in glosas:
        cod = g.codigo_respuesta
        if cod not in por_codigo:
            por_codigo[cod] = {
                "total": 0,
                "decididas": 0,
                "levantadas": 0,
            }
        b = por_codigo[cod]
        b["total"] += 1
        estado = (g.estado or "").upper()
        if estado in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}:
            b["decididas"] += 1
            if estado == "LEVANTADA":
                b["levantadas"] += 1

    items = []
    for cod, b in por_codigo.items():
        tasa = round(100 * b["levantadas"] / b["decididas"], 2) if b["decididas"] else 0.0
        items.append(
            {
                "codigo_respuesta": cod,
                "usado": b["total"],
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "eps": eps,
        "total_codigos_respuesta": len(items),
        "items": items,
    }


@stats_router.get("/stats/exito-por-codigo-respuesta")
def stats_exito_por_codigo_respuesta(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R116 P1: efectividad de cada código de respuesta IPS.

    Códigos de respuesta (Resolución 2284/2023):
      - RE9901: Acepta glosa
      - RE9502: Rechaza por concepto técnico
      - RE9801: Rechaza por concepto jurídico
      - RE9702: No procede
      - RE9602: Aclaración

    Útil para entender cuáles argumentos funcionan mejor:
      "Cuando respondemos con RE9502, ¿qué % de glosas se levantan?"

    Devuelve por código_respuesta:
      - total_usado
      - levantadas (HUS ganó)
      - tasa_levantamiento_pct
    """
    glosas = db.query(GlosaRecord).all()

    por_codigo: dict[str, dict] = {}
    for g in glosas:
        cod = g.codigo_respuesta
        if not cod:
            continue
        if cod not in por_codigo:
            por_codigo[cod] = {
                "total": 0,
                "levantadas": 0,
                "decididas": 0,
            }
        b = por_codigo[cod]
        b["total"] += 1
        estado = (g.estado or "").upper()
        if estado in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}:
            b["decididas"] += 1
            if estado == "LEVANTADA":
                b["levantadas"] += 1

    items = []
    for cod, b in por_codigo.items():
        tasa = round(100 * b["levantadas"] / b["decididas"], 2) if b["decididas"] else 0.0
        items.append(
            {
                "codigo_respuesta": cod,
                "total_usado": b["total"],
                "decididas": b["decididas"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa,
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "total_codigos_respuesta_unicos": len(items),
        "items": items,
    }


@stats_router.get("/stats/promedio-por-eps")
def stats_promedio_por_eps(
    min_glosas: int = Query(3, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r"""R152 P1: valor promedio de glosa por EPS.

    Detecta el "perfil económico" de cada EPS:
      - SANITAS: promedio \$5M (glosas grandes, casos complejos)
      - NUEVA EPS: promedio \$50k (glosas chicas, alto volumen)

    Útil para tailoring de estrategia:
      - EPS con promedio alto → atención senior
      - EPS con promedio bajo → flujo automatizado masivo

    Devuelve top N EPS con >= min_glosas (default 3):
      - eps
      - count
      - valor_promedio (mean)
      - valor_mediano (median)
      - valor_max
    """
    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, list[float]] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        por_eps.setdefault(eps, []).append(float(g.valor_objetado or 0))

    items = []
    for eps, valores in por_eps.items():
        if len(valores) < min_glosas:
            continue
        valores_ord = sorted(valores)
        n = len(valores_ord)
        promedio = sum(valores_ord) / n
        if n % 2 == 0:
            mediano = (valores_ord[n // 2 - 1] + valores_ord[n // 2]) / 2
        else:
            mediano = valores_ord[n // 2]
        items.append(
            {
                "eps": eps,
                "count": n,
                "valor_promedio": round(promedio, 2),
                "valor_mediano": round(mediano, 2),
                "valor_max": int(max(valores)),
            }
        )
    items.sort(key=lambda x: x["valor_promedio"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_eps": len(items),
        "items": items,
    }


@stats_router.get("/stats/por-etapa-actual")
def stats_por_etapa_actual(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R147 P1: distribución actual de glosas por etapa.

    Snapshot del pipeline: cuántas glosas hay en cada etapa
    ahora mismo. Útil para visualizar el funnel:
      "RADICADA: 100 → RESPUESTA_PRIMERA: 80 → RATIFICACION: 20"

    Devuelve por etapa:
      - count
      - valor_pendiente_total
      - pct_del_total

    Ordenado DESC por count.
    """
    glosas = db.query(GlosaRecord).all()

    por_etapa: dict[str, dict] = {}
    for g in glosas:
        etapa = (g.etapa or "(SIN_ETAPA)").strip() or "(SIN_ETAPA)"
        if etapa not in por_etapa:
            por_etapa[etapa] = {"count": 0, "valor": 0.0}
        por_etapa[etapa]["count"] += 1
        por_etapa[etapa]["valor"] += float(g.valor_objetado or 0)

    total_count = sum(b["count"] for b in por_etapa.values())
    items = []
    for etapa, b in por_etapa.items():
        pct = round(100 * b["count"] / total_count, 2) if total_count else 0.0
        items.append(
            {
                "etapa": etapa,
                "count": b["count"],
                "valor_pendiente_total": int(b["valor"]),
                "pct_del_total": pct,
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_glosas": total_count,
        "total_etapas_unicas": len(items),
        "items": items,
    }


@stats_router.get("/stats/concentracion-codigo")
def stats_concentracion_codigo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R146 P1: concentración de valor pendiente por código de glosa.

    Útil para responder: "¿qué tipos de glosa generan más cartera
    pendiente?" — distinto a /stats/codigos-mas-objetados (mide
    frecuencia), aquí mide concentración VALOR.

    Solo cuenta glosas no-cerradas. Devuelve los códigos ordenados
    DESC por valor_pendiente con su pct del total.

    Útil para:
      - Priorizar capacitación: ataquemos códigos del 80% valor
      - Comparativo: ¿es el mismo top que el de frecuencia?
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    abiertas = db.query(GlosaRecord).filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS)).all()

    por_codigo: dict[str, dict] = {}
    for g in abiertas:
        cod = g.codigo_glosa or "(SIN_CODIGO)"
        if cod not in por_codigo:
            por_codigo[cod] = {"count": 0, "valor": 0.0}
        por_codigo[cod]["count"] += 1
        por_codigo[cod]["valor"] += float(g.valor_objetado or 0)

    valor_total = sum(b["valor"] for b in por_codigo.values())
    items = []
    for cod, b in por_codigo.items():
        pct = round(100 * b["valor"] / valor_total, 2) if valor_total else 0.0
        items.append(
            {
                "codigo_glosa": cod,
                "count": b["count"],
                "valor_pendiente": int(b["valor"]),
                "pct_del_total": pct,
            }
        )
    items.sort(key=lambda x: x["valor_pendiente"], reverse=True)

    return {
        "total_codigos_unicos": len(items),
        "valor_pendiente_total": int(valor_total),
        "items": items,
    }


@stats_router.get("/stats/codigos-mas-objetados")
def stats_codigos_mas_objetados(
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R102 P1: ranking de códigos de glosa por frecuencia y valor.

    Útil para:
      - Identificar dónde se "pelean" más las EPS
        (¿es siempre TA0201 por insumos?)
      - Decidir capacitación enfocada (top códigos = más impacto)
      - Análisis de cumplimiento Resolución 2284/2023

    Devuelve top N códigos ordenados DESC por frecuencia, con:
      - codigo
      - frecuencia (count de glosas con ese código)
      - valor_objetado_total
      - tasa_levantamiento_pct (LEVANTADAS / decididas)
      - eps_principales (top 3 EPS que más usan ese código)
    """
    todas = db.query(GlosaRecord).all()

    por_codigo: dict[str, dict] = {}
    for g in todas:
        cod = g.codigo_glosa
        if not cod:
            continue
        if cod not in por_codigo:
            por_codigo[cod] = {
                "freq": 0,
                "valor": 0.0,
                "decididas": 0,
                "levantadas": 0,
                "por_eps": {},
            }
        b = por_codigo[cod]
        b["freq"] += 1
        b["valor"] += float(g.valor_objetado or 0)

        estado = (g.estado or "").upper()
        if estado in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}:
            b["decididas"] += 1
            if estado == "LEVANTADA":
                b["levantadas"] += 1

        if g.eps:
            b["por_eps"][g.eps] = b["por_eps"].get(g.eps, 0) + 1

    items = []
    for cod, b in por_codigo.items():
        tasa = round(100 * b["levantadas"] / b["decididas"], 2) if b["decididas"] else 0.0
        eps_top3 = sorted(
            b["por_eps"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        items.append(
            {
                "codigo": cod,
                "frecuencia": b["freq"],
                "valor_objetado_total": int(b["valor"]),
                "tasa_levantamiento_pct": tasa,
                "eps_principales": [{"eps": e, "veces": n} for e, n in eps_top3],
            }
        )
    items.sort(key=lambda x: x["frecuencia"], reverse=True)

    return {
        "total_codigos_unicos": len(items),
        "top_solicitado": int(top),
        "items": items[:top],
    }


@stats_router.get("/stats/eficiencia-gestor")
def stats_eficiencia_gestor(
    min_glosas: int = Query(3, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R98 P1: métricas de eficiencia por gestor.

    Diferente a /admin/distribucion-cargas (que cuenta workload):
    este mide DESEMPEÑO — qué tan bien defiende cada gestor las
    glosas asignadas.

    Para gestores con >= min_glosas cerradas, devuelve:
      - total_cerradas
      - tasa_levantamiento_pct (LEVANTADAS / cerradas, mejor=más alto)
      - valor_recuperado_total
      - valor_objetado_total
      - tasa_recuperacion_pct (recuperado / objetado)
      - tiempo_promedio_resolucion_dias

    Ordenado DESC por tasa_levantamiento_pct.
    Útil para identificar best practices y oportunidades de mentoría.
    """
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    por_gestor: dict[str, dict] = {}
    for g in cerradas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        if gestor not in por_gestor:
            por_gestor[gestor] = {
                "total": 0,
                "levantadas": 0,
                "valor_recuperado": 0.0,
                "valor_objetado": 0.0,
                "tiempos": [],
            }
        b = por_gestor[gestor]
        b["total"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["levantadas"] += 1
        b["valor_recuperado"] += float(g.valor_recuperado or 0)
        b["valor_objetado"] += float(g.valor_objetado or 0)

        if g.fecha_decision_eps and g.creado_en:
            delta = (g.fecha_decision_eps - g.creado_en).total_seconds() / 86400
            b["tiempos"].append(delta)

    items = []
    for gestor, b in por_gestor.items():
        if b["total"] < min_glosas:
            continue
        tasa_lev = round(100 * b["levantadas"] / b["total"], 2)
        tasa_rec = (
            round(100 * b["valor_recuperado"] / b["valor_objetado"], 2)
            if b["valor_objetado"]
            else 0.0
        )
        tiempo_prom = round(sum(b["tiempos"]) / len(b["tiempos"]), 2) if b["tiempos"] else 0.0
        items.append(
            {
                "gestor": gestor,
                "total_cerradas": b["total"],
                "levantadas": b["levantadas"],
                "tasa_levantamiento_pct": tasa_lev,
                "valor_recuperado_total": int(b["valor_recuperado"]),
                "valor_objetado_total": int(b["valor_objetado"]),
                "tasa_recuperacion_pct": tasa_rec,
                "tiempo_promedio_resolucion_dias": tiempo_prom,
            }
        )
    items.sort(key=lambda x: x["tasa_levantamiento_pct"], reverse=True)

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_gestores_evaluados": len(items),
        "items": items,
    }


@stats_router.get("/stats/recuperacion-mensual")
def stats_recuperacion_mensual(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R97 P2: serie temporal mensual de valor recuperado.

    Útil para reporte ejecutivo: ¿cuánto plata le hemos sacado a las
    EPS este año? Tendencia mes-a-mes para detectar mejoras /
    degradaciones del proceso de defensa de glosas.

    Calcula valor_recuperado por mes basado en fecha_decision_eps
    (cuándo se cerró el ciclo). Solo cuenta glosas cerradas con
    valor_recuperado > 0.

    Devuelve serie ordenada ascendentemente:
      [{"mes": "2026-01", "recuperado": 1500000, "glosas_cerradas": 12,
        "valor_objetado_total": 5000000, "tasa_recuperacion_pct": 30.0}, ...]
    """
    from datetime import timezone

    corte = ahora_utc() - timedelta(days=int(meses) * 31)

    cerradas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .filter(GlosaRecord.fecha_decision_eps >= corte)
        .all()
    )

    por_mes: dict[str, dict] = {}
    for g in cerradas:
        fecha = g.fecha_decision_eps
        if fecha and fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        if not fecha:
            continue
        key = fecha.strftime("%Y-%m")
        if key not in por_mes:
            por_mes[key] = {
                "recuperado": 0.0,
                "glosas_cerradas": 0,
                "valor_objetado_total": 0.0,
            }
        b = por_mes[key]
        b["glosas_cerradas"] += 1
        b["recuperado"] += float(g.valor_recuperado or 0)
        b["valor_objetado_total"] += float(g.valor_objetado or 0)

    serie = []
    for key in sorted(por_mes.keys()):
        b = por_mes[key]
        tasa = (
            round(100 * b["recuperado"] / b["valor_objetado_total"], 2)
            if b["valor_objetado_total"]
            else 0.0
        )
        serie.append(
            {
                "mes": key,
                "recuperado": int(b["recuperado"]),
                "glosas_cerradas": b["glosas_cerradas"],
                "valor_objetado_total": int(b["valor_objetado_total"]),
                "tasa_recuperacion_pct": tasa,
            }
        )

    return {
        "ventana_meses": int(meses),
        "total_recuperado": sum(s["recuperado"] for s in serie),
        "serie": serie,
    }


@stats_router.get("/stats/heatmap-actividad")
def stats_heatmap_actividad(
    dias: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R89 P1: heatmap de glosas creadas por día-de-semana × hora-del-día.

    Útil para:
      - Detectar picos de carga (¿se concentran las cargas masivas
        de glosas los lunes a las 9am? ¿hay actividad nocturna sospechosa?)
      - Planeación de capacidad de auditores
      - Identificar anomalías (carga repentina fuera de horario)

    Devuelve matriz 7×24:
      {
        "ventana_dias": 90,
        "total": 1234,
        "matriz": [[lunes_0h, lunes_1h, ...], [martes_0h, ...], ...],
        "dias_semana": ["Lunes", "Martes", ...],
        "horas": [0..23]
      }

    Día-de-semana siguiendo ISO 8601 (Lunes=0, Domingo=6).
    Agregación se hace en Python para portabilidad SQLite/PostgreSQL.
    """

    corte = ahora_utc() - timedelta(days=int(dias))
    rows = db.query(GlosaRecord.creado_en).filter(GlosaRecord.creado_en >= corte).all()

    matriz = [[0 for _ in range(24)] for _ in range(7)]
    total = 0
    for (creado,) in rows:
        if creado is None:
            continue
        dow = creado.weekday()  # Lunes=0, Domingo=6
        hr = creado.hour
        matriz[dow][hr] += 1
        total += 1

    return {
        "ventana_dias": int(dias),
        "total": total,
        "matriz": matriz,
        "dias_semana": [
            "Lunes",
            "Martes",
            "Miércoles",
            "Jueves",
            "Viernes",
            "Sábado",
            "Domingo",
        ],
        "horas": list(range(24)),
    }


@stats_router.get("/stats/tendencia-diaria")
def stats_tendencia_diaria(
    dias: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R72 P1: serie temporal diaria de glosas creadas.

    Útil para gráficos de línea en dashboard:
      - Detectar spikes (días con muchas glosas → carga de trabajo)
      - Tendencia semanal (lunes vs viernes)
      - Comparación mes-a-mes

    GET /glosas/stats/tendencia-diaria?dias=30

    Devuelve serie completa (rellenando días con 0 glosas):
      {
        "ventana_dias": 30,
        "serie": [
          {"fecha": "2026-04-01", "count": 5, "valor_objetado": 250000},
          {"fecha": "2026-04-02", "count": 0, "valor_objetado": 0},
          ...
        ]
      }
    """

    from sqlalchemy import func as _f


    desde = (ahora_utc() - timedelta(days=int(dias))).date()

    # Agregar por fecha (truncando a date)
    rows = (
        db.query(
            _f.date(GlosaRecord.creado_en).label("fecha"),
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .group_by(_f.date(GlosaRecord.creado_en))
        .all()
    )

    # Indexar por fecha
    por_fecha = {}
    for fecha, count, valor in rows:
        # SQLAlchemy puede devolver date o str según el motor
        if isinstance(fecha, str):
            from datetime import datetime

            try:
                fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
            except Exception:
                continue
        por_fecha[fecha.isoformat()] = {
            "count": int(count or 0),
            "valor_objetado": float(valor or 0),
        }

    # Rellenar serie completa
    serie = []
    hoy = ahora_utc().date()
    cursor = desde
    while cursor <= hoy:
        clave = cursor.isoformat()
        info = por_fecha.get(clave, {"count": 0, "valor_objetado": 0.0})
        serie.append(
            {
                "fecha": clave,
                "count": info["count"],
                "valor_objetado": info["valor_objetado"],
            }
        )
        cursor += timedelta(days=1)

    return {
        "ventana_dias": dias,
        "total_glosas": sum(s["count"] for s in serie),
        "valor_total": sum(s["valor_objetado"] for s in serie),
        "serie": serie,
    }


@stats_router.get("/stats/por-tipo")
def stats_por_tipo_glosa(
    dias: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R68 P3: distribución por tipo de glosa (prefijo Res. 2284/2023).

    Resolución 2284 de 2023 (Manual Único de Glosas) clasifica con
    prefijos:
      TA  Tarifas
      SO  Soportes
      AU  Autorización
      CO  Cobertura
      CL  Pertinencia clínica
      PE  Pertinencia
      FA  Facturación
      SE  Servicios
      IN  Insumos
      ME  Medicamentos
      EX  Extemporánea / proceso

    Útil para identificar dónde tenemos brechas:
      - Mucho SO → deficiente entrega de soportes operativos
      - Mucho TA → desfase con tarifas pactadas
      - Mucho AU → fallas en autorización previa
    """

    from sqlalchemy import func as _f


    desde = ahora_utc() - timedelta(days=int(dias))

    descripciones = {
        "TA": "Tarifas",
        "SO": "Soportes",
        "AU": "Autorización",
        "CO": "Cobertura",
        "CL": "Pertinencia clínica",
        "PE": "Pertinencia",
        "FA": "Facturación",
        "SE": "Servicios",
        "IN": "Insumos",
        "ME": "Medicamentos",
        "EX": "Extemporánea / proceso",
    }

    rows = (
        db.query(
            GlosaRecord.codigo_glosa,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .group_by(GlosaRecord.codigo_glosa)
        .all()
    )

    # Agrupar por prefijo
    por_prefijo = {}
    for codigo, count, valor in rows:
        prefijo = (codigo or "??")[:2].upper()
        d = por_prefijo.setdefault(
            prefijo,
            {"count": 0, "valor_objetado": 0.0, "codigos_unicos": set()},
        )
        d["count"] += count
        d["valor_objetado"] += float(valor or 0)
        d["codigos_unicos"].add(codigo)

    items = []
    total_count = sum(d["count"] for d in por_prefijo.values()) or 0
    for prefijo, d in por_prefijo.items():
        items.append(
            {
                "prefijo": prefijo,
                "tipo": descripciones.get(prefijo, "Otro"),
                "count": d["count"],
                "valor_objetado": d["valor_objetado"],
                "codigos_distintos": len(d["codigos_unicos"]),
                "porcentaje": round(d["count"] / total_count * 100, 1) if total_count else 0,
            }
        )
    items.sort(key=lambda x: x["count"], reverse=True)

    return {
        "ventana_dias": dias,
        "total": total_count,
        "items": items,
    }
