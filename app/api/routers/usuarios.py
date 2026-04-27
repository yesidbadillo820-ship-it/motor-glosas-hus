from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.db import UsuarioRecord, ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR, ROL_VIEWER
from app.auth import get_password_hash
from app.api.deps import get_usuario_actual, get_admin, get_coordinador_o_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


class UsuarioCreate(BaseModel):
    nombre: str
    email: str
    password: str


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None


class PasswordChange(BaseModel):
    nueva_password: str


class RolChange(BaseModel):
    rol: str


ROLES_VALIDOS = {ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR, ROL_VIEWER}


@router.get("/yo")
def info_usuario_actual(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R81 P2: información del usuario autenticado.

    Útil para que el frontend muestre nombre/email/rol en el header
    sin tener que decodificar el JWT en JavaScript ni hacer lookup
    adicional al login.

    NO devuelve password_hash ni totp_secret — solo metadata pública.
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "nombre": current_user.nombre,
        "rol": current_user.rol,
        "activo": bool(current_user.activo),
        "totp_activo": bool(getattr(current_user, "totp_activo", 0)),
        "must_change_password": bool(
            getattr(current_user, "must_change_password", 0)
        ),
        "creado_en": (
            current_user.creado_en.isoformat()
            if getattr(current_user, "creado_en", None) else None
        ),
    }


@router.get("/yo/mis-glosas")
def mis_glosas_paginado(
    estado: Optional[str] = None,
    page: int = 1,
    per_page: int = 25,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R130 P2: listado paginado completo de glosas del usuario.

    Diferente a /yo/worklist (top urgentes priorizadas con score):
    aquí se devuelve la lista COMPLETA paginada, con filtro
    opcional por estado.

    Útil para "Mis Glosas → ver todas":
      - Pestaña "Abiertas"
      - Pestaña "Cerradas"
      - Filtro libre por estado

    Asignación = gestor_nombre == nombre OR auditor_email == email.

    Devuelve {items, total, page, per_page, pages} estándar.
    """
    from sqlalchemy import or_

    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email

    q = (
        db.query(GlosaRecord)
        .filter(or_(
            GlosaRecord.gestor_nombre == nombre,
            GlosaRecord.auditor_email == current_user.email,
        ))
    )
    if estado:
        q = q.filter(GlosaRecord.estado == estado.upper())

    total = q.count()
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    pages = (total + per_page - 1) // per_page

    glosas = (
        q.order_by(GlosaRecord.creado_en.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "usuario_email": current_user.email,
        "filtro_estado": estado,
        "items": [
            {
                "id": g.id,
                "creado_en": (
                    g.creado_en.isoformat() if g.creado_en else None
                ),
                "eps": g.eps,
                "factura": g.factura,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": float(g.valor_objetado or 0),
                "estado": g.estado,
                "etapa": g.etapa,
                "dias_restantes": g.dias_restantes,
            }
            for g in glosas
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/yo/performance-historica")
def performance_historica(
    meses: int = 6,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R145 P2: evolución mensual personal del usuario actual.

    Diferente a /yo/resumen (snapshot último N días): aquí
    serie temporal mes-a-mes de las glosas que el usuario cerró.

    Útil para que el auditor vea su mejora con el tiempo:
      - "En enero levanté 10, en marzo 25 → mejorando"

    Devuelve serie ascendente:
      [{"mes": "2026-04", "glosas_cerradas": 12, "levantadas": 8,
        "valor_recuperado": 5000000}, ...]
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    nombre = current_user.nombre or current_user.email

    desde = ahora_utc() - timedelta(days=int(meses) * 31)
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.fecha_decision_eps >= desde)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
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
            por_mes[k] = {
                "cerradas": 0, "levantadas": 0, "valor_rec": 0.0,
            }
        b = por_mes[k]
        b["cerradas"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["levantadas"] += 1
        b["valor_rec"] += float(g.valor_recuperado or 0)

    serie = []
    for k in sorted(por_mes.keys()):
        b = por_mes[k]
        tasa = (
            round(100 * b["levantadas"] / b["cerradas"], 2)
            if b["cerradas"] else 0.0
        )
        serie.append({
            "mes": k,
            "glosas_cerradas": b["cerradas"],
            "levantadas": b["levantadas"],
            "tasa_levantamiento_pct": tasa,
            "valor_recuperado": int(b["valor_rec"]),
        })

    return {
        "usuario_email": current_user.email,
        "ventana_meses": int(meses),
        "total_meses_con_actividad": len(serie),
        "serie": serie,
    }


@router.get("/yo/resumen")
def resumen_personal(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R123 P2: resumen personal de desempeño.

    "Mis números" en un período: glosas trabajadas, tasa de
    levantamiento, valor recuperado, posición vs equipo.

    Útil para que cada auditor vea su propio progreso sin
    depender del coordinador.

    Devuelve:
      - mis_glosas_asignadas: count abiertas
      - mis_glosas_cerradas_periodo
      - mi_valor_recuperado_periodo
      - mi_tasa_levantamiento_pct
      - mi_tiempo_promedio_resolucion_dias
      - posicion_ranking: rank en equipo por levantamientos
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    nombre = current_user.nombre or current_user.email
    ahora = ahora_utc()
    desde = ahora - timedelta(days=int(dias))

    glosas_asignadas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .all()
    )

    abiertas = sum(
        1 for g in glosas_asignadas
        if (g.estado or "").upper() not in ESTADOS_CERRADOS
    )

    cerradas_periodo = []
    for g in glosas_asignadas:
        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if (dec and dec >= desde and
                (g.estado or "").upper() in ESTADOS_CERRADOS):
            cerradas_periodo.append(g)

    levantadas = [
        g for g in cerradas_periodo
        if (g.estado or "").upper() == "LEVANTADA"
    ]
    decididas = [
        g for g in cerradas_periodo
        if (g.estado or "").upper() in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
    ]

    valor_rec = sum(float(g.valor_recuperado or 0) for g in cerradas_periodo)

    tiempos = []
    for g in cerradas_periodo:
        if g.fecha_decision_eps and g.creado_en:
            dec = g.fecha_decision_eps
            cre = g.creado_en
            if dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)
            if cre.tzinfo is None:
                cre = cre.replace(tzinfo=timezone.utc)
            tiempos.append((dec - cre).days)

    # Ranking: cuántos gestores tienen MÁS levantamientos que yo en período
    todas_periodo = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.fecha_decision_eps >= desde)
        .filter(GlosaRecord.estado == "LEVANTADA")
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )
    levant_por_gestor: dict[str, int] = {}
    for g in todas_periodo:
        levant_por_gestor[g.gestor_nombre] = (
            levant_por_gestor.get(g.gestor_nombre, 0) + 1
        )
    mis_levantamientos = levant_por_gestor.get(nombre, 0)
    posicion = sum(
        1 for n in levant_por_gestor.values()
        if n > mis_levantamientos
    ) + 1

    return {
        "usuario_email": current_user.email,
        "ventana_dias": int(dias),
        "mis_glosas_asignadas": abiertas,
        "mis_glosas_cerradas_periodo": len(cerradas_periodo),
        "mi_valor_recuperado_periodo": int(valor_rec),
        "mi_tasa_levantamiento_pct": (
            round(100 * len(levantadas) / len(decididas), 2)
            if decididas else 0.0
        ),
        "mi_tiempo_promedio_resolucion_dias": (
            round(sum(tiempos) / len(tiempos), 2) if tiempos else 0.0
        ),
        "posicion_ranking": posicion,
        "total_gestores_activos_ranking": len(levant_por_gestor),
    }


@router.get("/yo/worklist")
def worklist_personal(
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R123 P1: worklist personal priorizada del usuario actual.

    Lista las glosas asignadas a este usuario (como gestor o
    auditor) ordenadas por prioridad heurística — qué debería
    atacar primero.

    Score (mismo que /admin/glosas-prioritarias pero filtrado a
    sus propias asignaciones):
      +100 vencida, +50 crítica, +20 próxima
      +30 alto valor, +25 sin dictamen

    Útil al inicio del día: "estas son TUS glosas urgentes".
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    nombre = current_user.nombre or current_user.email
    abiertas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(
            (GlosaRecord.gestor_nombre == nombre) |
            (GlosaRecord.auditor_email == current_user.email)
        )
        .all()
    )

    items = []
    for g in abiertas:
        score = 0
        razones = []

        dr = g.dias_restantes if g.dias_restantes is not None else 0
        if dr < 0:
            score += 100
            razones.append(f"vencida {abs(dr)}d")
        elif dr <= 3:
            score += 50
            razones.append(f"crítica {dr}d")
        elif dr <= 7:
            score += 20

        v = float(g.valor_objetado or 0)
        if v > 10_000_000:
            score += 30
            razones.append("alto valor (>10M)")

        if not g.dictamen or len(g.dictamen) < 50:
            score += 25
            razones.append("sin dictamen")

        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "dias_restantes": dr,
            "valor_objetado": int(v),
            "score": score,
            "razones": razones,
        })

    items.sort(key=lambda x: x["score"], reverse=True)

    return {
        "usuario_email": current_user.email,
        "total_asignadas": len(abiertas),
        "items": items[:limit],
    }


@router.get("/yo/timeline-mes")
def yo_timeline_mes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R389 P1: timeline diaria del mes en curso.

    Para cada día del mes hasta hoy, devuelve count de
    glosas decididas por el usuario y el resultado más
    común (LEVANTADA / RATIFICADA / ACEPTADA). Útil para
    vista de calendario o sparkline en Mi desempeño.
    """
    from calendar import monthrange
    from datetime import timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    ahora = ahora_utc()
    inicio = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    dias_mes = monthrange(ahora.year, ahora.month)[1]

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.fecha_decision_eps >= inicio)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .all()
    )

    por_dia: dict[int, dict] = {}
    for g in rows:
        f = g.fecha_decision_eps
        if f and f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if not f:
            continue
        d = f.day
        b = por_dia.setdefault(d, {
            "count": 0, "lev": 0, "rat": 0, "ace": 0, "rec": 0.0,
        })
        b["count"] += 1
        e = (g.estado or "").upper()
        if e == "LEVANTADA":
            b["lev"] += 1
        elif e == "RATIFICADA":
            b["rat"] += 1
        elif e == "ACEPTADA":
            b["ace"] += 1
        b["rec"] += float(g.valor_recuperado or 0)

    serie = []
    for d in range(1, dias_mes + 1):
        b = por_dia.get(d)
        if d > ahora.day:
            serie.append({
                "dia": d, "count": 0, "futuro": True,
                "lev": 0, "rat": 0, "ace": 0,
                "valor_recuperado": 0,
                "dominante": None,
            })
        elif b:
            dominante = max(
                ("LEVANTADA", "RATIFICADA", "ACEPTADA"),
                key=lambda k: (
                    b["lev"] if k == "LEVANTADA"
                    else b["rat"] if k == "RATIFICADA"
                    else b["ace"]
                ),
            )
            serie.append({
                "dia": d,
                "count": b["count"],
                "lev": b["lev"],
                "rat": b["rat"],
                "ace": b["ace"],
                "valor_recuperado": int(b["rec"]),
                "dominante": dominante,
                "futuro": False,
            })
        else:
            serie.append({
                "dia": d, "count": 0, "futuro": False,
                "lev": 0, "rat": 0, "ace": 0,
                "valor_recuperado": 0,
                "dominante": None,
            })

    total_mes = sum(s["count"] for s in serie)
    max_dia = max(serie, key=lambda s: s["count"]) if serie else None

    return {
        "mes": inicio.strftime("%Y-%m"),
        "dias_mes": dias_mes,
        "dia_actual": ahora.day,
        "total_decididas_mes": total_mes,
        "mejor_dia": (
            {"dia": max_dia["dia"], "count": max_dia["count"]}
            if max_dia and max_dia["count"] > 0 else None
        ),
        "serie": serie,
    }


@router.get("/yo/progreso-mes")
def yo_progreso_mes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R387 P1: progreso del mes vs meta personal.

    Calcula meta automática como el promedio mensual de
    los últimos 6 meses con actividad. Devuelve:
      - decididas_mes_actual
      - meta_mensual (promedio histórico, mín 5)
      - progreso_pct (cap 200 si superó la meta)
      - dias_restantes_del_mes
      - ritmo_diario_actual vs ritmo_diario_necesario
      - mensaje motivacional según el progreso
    """
    from calendar import monthrange
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    ahora = ahora_utc()
    inicio_mes = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    # Mes actual count
    decididas_mes = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_mes)
        .count()
    )

    # Histórico últimos 6 meses con actividad
    desde_hist = inicio_mes - timedelta(days=180)
    hist = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(GlosaRecord.fecha_decision_eps >= desde_hist)
        .filter(GlosaRecord.fecha_decision_eps < inicio_mes)
        .all()
    )
    por_mes: dict[str, int] = {}
    for g in hist:
        f = g.fecha_decision_eps
        if f and f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if not f:
            continue
        k = f.strftime("%Y-%m")
        por_mes[k] = por_mes.get(k, 0) + 1

    if por_mes:
        promedio = sum(por_mes.values()) / len(por_mes)
        meta = max(int(promedio), 5)
    else:
        meta = 5  # arranque mínimo

    progreso_pct = min(round(100 * decididas_mes / meta, 1), 200) if meta else 0

    dias_mes = monthrange(ahora.year, ahora.month)[1]
    dia_actual = ahora.day
    dias_restantes_mes = max(dias_mes - dia_actual, 0)

    ritmo_actual = round(decididas_mes / dia_actual, 2) if dia_actual else 0.0
    faltan = max(meta - decididas_mes, 0)
    ritmo_necesario = (
        round(faltan / max(dias_restantes_mes, 1), 2)
        if dias_restantes_mes else 0.0
    )

    if progreso_pct >= 100:
        mensaje = "🎉 ¡Meta cumplida! Sigue sumando para batir tu récord."
        nivel = "EXCELENTE"
    elif progreso_pct >= 80:
        mensaje = "💪 Casi llegas — solo te faltan unas pocas."
        nivel = "BUENO"
    elif progreso_pct >= 50:
        mensaje = "📊 Vas a buen ritmo, mantén el foco."
        nivel = "OK"
    elif dias_restantes_mes <= 5:
        mensaje = "⚠️ Pocos días restantes — prioriza Quick Wins."
        nivel = "ATENCION"
    else:
        mensaje = "🎯 Aún hay margen — atiende casos críticos primero."
        nivel = "EN_PROGRESO"

    return {
        "usuario_email": current_user.email,
        "mes": inicio_mes.strftime("%Y-%m"),
        "decididas_mes_actual": decididas_mes,
        "meta_mensual": meta,
        "progreso_pct": progreso_pct,
        "dia_actual": dia_actual,
        "dias_mes": dias_mes,
        "dias_restantes_mes": dias_restantes_mes,
        "ritmo_diario_actual": ritmo_actual,
        "ritmo_diario_necesario": ritmo_necesario,
        "nivel": nivel,
        "mensaje": mensaje,
    }


@router.get("/yo/insights")
def yo_insights(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R385 P1: insights personales narrativos.

    La IA convierte tus métricas en frases cortas
    accionables, en lenguaje humano. Devuelve hasta 5
    insights ordenados por relevancia.

    Cada insight: titulo, frase, tipo (POSITIVO,
    NEUTRAL, ATENCION), accion_sugerida.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    ahora = ahora_utc()
    inicio_mes = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    if inicio_mes.month == 1:
        inicio_anterior = inicio_mes.replace(
            year=inicio_mes.year - 1, month=12,
        )
    else:
        inicio_anterior = inicio_mes.replace(
            month=inicio_mes.month - 1,
        )

    # Mes actual y anterior
    decididas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_anterior)
        .all()
    )
    actual_dec = actual_lev = prev_dec = prev_lev = 0
    actual_rec = prev_rec = 0.0
    for g in decididas:
        f = g.fecha_decision_eps
        if f and f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if not f:
            continue
        rec = float(g.valor_recuperado or 0)
        if f >= inicio_mes:
            actual_dec += 1
            actual_rec += rec
            if (g.estado or "").upper() == "LEVANTADA":
                actual_lev += 1
        else:
            prev_dec += 1
            prev_rec += rec
            if (g.estado or "").upper() == "LEVANTADA":
                prev_lev += 1

    tasa_actual = (
        100.0 * actual_lev / actual_dec if actual_dec else 0.0
    )
    tasa_prev = (
        100.0 * prev_lev / prev_dec if prev_dec else 0.0
    )

    # Equipo (para comparativa)
    decididas_eq = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )
    bucket_eq: dict[str, dict] = {}
    for g in decididas_eq:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        b = bucket_eq.setdefault(gestor, {"dec": 0, "lev": 0})
        b["dec"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["lev"] += 1
    if bucket_eq:
        tasas_eq = [
            100.0 * b["lev"] / b["dec"]
            for b in bucket_eq.values() if b["dec"] >= 3
        ]
        tasa_eq_promedio = (
            round(sum(tasas_eq) / len(tasas_eq), 2)
            if tasas_eq else 0.0
        )
    else:
        tasa_eq_promedio = 0.0

    # Backlog
    abiertas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )
    n_abiertas = len(abiertas)
    n_vencidas = sum(
        1 for g in abiertas if (g.dias_restantes or 0) < 0
    )

    insights = []

    # 1) Comparación con mes anterior
    if prev_dec >= 3:
        delta = tasa_actual - tasa_prev
        if delta >= 5:
            insights.append({
                "titulo": "Subiste tu tasa este mes",
                "frase": (
                    f"Pasaste de {tasa_prev:.1f}% a "
                    f"{tasa_actual:.1f}% — sube {delta:.1f} pts."
                ),
                "tipo": "POSITIVO",
                "accion_sugerida": "Mantén el momentum",
                "prioridad": 3,
            })
        elif delta <= -5:
            insights.append({
                "titulo": "Tu tasa cayó vs mes anterior",
                "frase": (
                    f"Bajaste de {tasa_prev:.1f}% a "
                    f"{tasa_actual:.1f}% ({delta:+.1f} pts)."
                ),
                "tipo": "ATENCION",
                "accion_sugerida": (
                    "Revisa /yo/eps-mejor-rendimiento para "
                    "identificar qué cambió"
                ),
                "prioridad": 1,
            })

    # 2) Comparación con equipo
    if actual_dec >= 3 and tasa_eq_promedio > 0:
        diff = tasa_actual - tasa_eq_promedio
        if diff >= 8:
            insights.append({
                "titulo": "Por encima del promedio del equipo",
                "frase": (
                    f"Tu tasa ({tasa_actual:.1f}%) está "
                    f"{diff:.1f} pts arriba del promedio "
                    f"({tasa_eq_promedio:.1f}%)."
                ),
                "tipo": "POSITIVO",
                "accion_sugerida": (
                    "Comparte buenas prácticas con el equipo"
                ),
                "prioridad": 3,
            })
        elif diff <= -8:
            insights.append({
                "titulo": "Por debajo del promedio del equipo",
                "frase": (
                    f"Tu tasa ({tasa_actual:.1f}%) está "
                    f"{abs(diff):.1f} pts abajo del promedio "
                    f"({tasa_eq_promedio:.1f}%)."
                ),
                "tipo": "ATENCION",
                "accion_sugerida": (
                    "Revisa casos similares antes de redactar dictamen"
                ),
                "prioridad": 2,
            })

    # 3) Vencidas
    if n_vencidas > 0:
        insights.append({
            "titulo": f"{n_vencidas} glosa(s) vencidas",
            "frase": (
                "Estas glosas pueden archivarse "
                "automáticamente si no las cierras hoy."
            ),
            "tipo": "ATENCION",
            "accion_sugerida": "Atender en orden de antigüedad",
            "prioridad": 1,
        })

    # 4) Backlog
    if n_abiertas > 30:
        insights.append({
            "titulo": "Backlog alto",
            "frase": (
                f"Tienes {n_abiertas} glosas abiertas — "
                "considera priorizar quick-wins."
            ),
            "tipo": "NEUTRAL",
            "accion_sugerida": "Abre Quick Wins en Mi desempeño",
            "prioridad": 2,
        })

    # 5) Recuperado del mes
    if actual_rec > 0:
        if actual_rec > prev_rec * 1.2 and prev_rec > 0:
            insights.append({
                "titulo": "Recuperación creciente",
                "frase": (
                    f"Recuperaste ${int(actual_rec):,} este mes — "
                    f"{((actual_rec/prev_rec - 1)*100):.0f}% más "
                    "que el mes pasado."
                ),
                "tipo": "POSITIVO",
                "accion_sugerida": "Buen ritmo financiero",
                "prioridad": 3,
            })

    insights.sort(key=lambda x: x["prioridad"])
    return {
        "usuario_email": current_user.email,
        "total_insights": len(insights),
        "items": insights[:5],
    }


@router.get("/yo/checklist-personal")
def yo_checklist_personal(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R381 P1: checklist auto-detectado de cosas pendientes.

    La IA escanea TUS glosas abiertas y detecta lo que
    falta completar. Devuelve checks con título y count
    para mostrar como lista de pendientes claros:

      - sin_dictamen
      - dictamen_corto (< 50 chars)
      - sin_codigo_respuesta (en RESPONDIDA)
      - sin_valor_aceptado (en RATIFICADA)
      - vencidas
      - criticas (≤ 3 días)
      - alto_valor_sin_dictamen (≥ 5M)

    Cada item incluye glosa_ids para acción directa.
    """
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    abiertas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )
    respondidas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado == "RESPONDIDA")
        .all()
    )
    ratificadas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado == "RATIFICADA")
        .all()
    )

    sin_dict = [
        g for g in abiertas
        if not (g.dictamen or "").strip()
    ]
    dict_corto = [
        g for g in abiertas
        if g.dictamen and 0 < len(g.dictamen.strip()) < 50
    ]
    sin_cresp = [
        g for g in respondidas
        if not (g.codigo_respuesta or "").strip()
    ]
    sin_aceptado = [
        g for g in ratificadas
        if not g.valor_aceptado or float(g.valor_aceptado) == 0
    ]
    vencidas = [
        g for g in abiertas
        if (g.dias_restantes or 0) < 0
    ]
    criticas = [
        g for g in abiertas
        if 0 <= (g.dias_restantes or 0) <= 3
    ]
    alto_valor_sin_dict = [
        g for g in sin_dict
        if float(g.valor_objetado or 0) >= 5_000_000
    ]

    def _ids(lst, n=5):
        return [g.id for g in lst[:n]]

    items = [
        {
            "id": "sin_dictamen",
            "titulo": "Glosas abiertas sin dictamen",
            "count": len(sin_dict),
            "prioridad": 2,
            "glosa_ids": _ids(sin_dict),
        },
        {
            "id": "dictamen_corto",
            "titulo": "Dictamen demasiado corto (< 50 chars)",
            "count": len(dict_corto),
            "prioridad": 3,
            "glosa_ids": _ids(dict_corto),
        },
        {
            "id": "sin_codigo_respuesta",
            "titulo": "RESPONDIDAS sin código de respuesta",
            "count": len(sin_cresp),
            "prioridad": 2,
            "glosa_ids": _ids(sin_cresp),
        },
        {
            "id": "sin_valor_aceptado",
            "titulo": "RATIFICADAS sin valor_aceptado",
            "count": len(sin_aceptado),
            "prioridad": 3,
            "glosa_ids": _ids(sin_aceptado),
        },
        {
            "id": "vencidas",
            "titulo": "Glosas vencidas (¡cierra hoy!)",
            "count": len(vencidas),
            "prioridad": 1,
            "glosa_ids": _ids(vencidas),
        },
        {
            "id": "criticas",
            "titulo": "Glosas críticas (≤ 3 días)",
            "count": len(criticas),
            "prioridad": 1,
            "glosa_ids": _ids(criticas),
        },
        {
            "id": "alto_valor_sin_dictamen",
            "titulo": "Alto valor (≥5M) sin dictamen",
            "count": len(alto_valor_sin_dict),
            "prioridad": 1,
            "glosa_ids": _ids(alto_valor_sin_dict),
        },
    ]
    items_no_vacios = [it for it in items if it["count"] > 0]
    items_no_vacios.sort(key=lambda x: (x["prioridad"], -x["count"]))

    return {
        "usuario_email": current_user.email,
        "total_chequeos": len(items),
        "total_pendientes": len(items_no_vacios),
        "items": items_no_vacios,
    }


@router.get("/yo/inicio")
def yo_inicio(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R378 P1: home unificado del usuario (single-call).

    Devuelve TODO lo que el gestor necesita ver al
    iniciar la jornada — sin que pregunte:
      - resumen_dia (count vencidas, críticas, abiertas,
        cerradas_hoy)
      - top_acciones (3 más urgentes del asistente)
      - top_quick_wins (3 fáciles de cerrar HOY)
      - menciones_pendientes (count + 3 más recientes)

    Optimizado: una sola llamada para una pantalla
    completa de bienvenida.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import (
        ComentarioGlosaRecord, GlosaRecord,
    )

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    nombre = current_user.nombre or current_user.email
    ahora = ahora_utc()
    inicio_dia = ahora.replace(
        hour=0, minute=0, second=0, microsecond=0,
    )

    # Resumen del día
    abiertas_q = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )
    n_abiertas = len(abiertas_q)
    n_vencidas = sum(
        1 for g in abiertas_q
        if (g.dias_restantes or 0) < 0
    )
    n_criticas = sum(
        1 for g in abiertas_q
        if 0 <= (g.dias_restantes or 0) <= 3
    )

    cerradas_hoy = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(
            ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
        ))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_dia)
        .count()
    )

    # Top 3 acciones más urgentes
    top_acciones = []
    if n_vencidas:
        peor = next(
            (g for g in sorted(
                abiertas_q,
                key=lambda x: x.dias_restantes or 0,
            )), None,
        )
        top_acciones.append({
            "tipo": "URGENTE",
            "titulo": f"{n_vencidas} vencida(s)",
            "glosa_id": peor.id if peor else None,
        })
    if n_criticas:
        peor_c = next(
            (g for g in sorted(
                abiertas_q,
                key=lambda x: x.dias_restantes or 0,
            ) if 0 <= (g.dias_restantes or 0) <= 3),
            None,
        )
        top_acciones.append({
            "tipo": "IMPORTANTE",
            "titulo": f"{n_criticas} crítica(s)",
            "glosa_id": peor_c.id if peor_c else None,
        })

    # Top 3 quick wins
    tasas_cache: dict[tuple, tuple] = {}

    def _tasa(eps, cod):
        k = (eps, cod)
        if k in tasas_cache:
            return tasas_cache[k]
        rows = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.eps == eps)
            .filter(GlosaRecord.codigo_glosa == cod)
            .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
            .all()
        )
        n = len(rows)
        lev = sum(
            1 for r in rows
            if (r.estado or "").upper() == "LEVANTADA"
        )
        tasas_cache[k] = (n, lev)
        return n, lev

    qw = []
    for g in abiertas_q:
        if not g.eps or not g.codigo_glosa:
            continue
        n, lev = _tasa(g.eps, g.codigo_glosa)
        if n < 3:
            continue
        tasa = 100.0 * lev / n
        if tasa < 60:
            continue
        valor = float(g.valor_objetado or 0)
        qw.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "valor_objetado": int(valor),
            "tasa_pct": round(tasa, 1),
            "score": tasa * valor,
        })
    qw.sort(key=lambda x: x["score"], reverse=True)

    # Menciones pendientes
    menciones_q = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.mencion == current_user.email)
        .filter(
            (ComentarioGlosaRecord.resuelto == 0)
            | (ComentarioGlosaRecord.resuelto.is_(None))
        )
        .order_by(ComentarioGlosaRecord.creado_en.desc())
        .all()
    )
    menciones_top = [
        {
            "glosa_id": m.glosa_id,
            "autor_email": m.autor_email,
            "texto": (m.texto or "")[:140],
            "creado_en": m.creado_en.isoformat() if m.creado_en else None,
        }
        for m in menciones_q[:3]
    ]

    return {
        "usuario_email": current_user.email,
        "saludo_hora": ahora.hour,
        "resumen_dia": {
            "abiertas": n_abiertas,
            "vencidas": n_vencidas,
            "criticas": n_criticas,
            "cerradas_hoy": cerradas_hoy,
        },
        "top_acciones": top_acciones,
        "top_quick_wins": [
            {
                "glosa_id": x["glosa_id"],
                "eps": x["eps"],
                "valor_objetado": x["valor_objetado"],
                "tasa_pct": x["tasa_pct"],
            }
            for x in qw[:3]
        ],
        "menciones_pendientes": {
            "total": len(menciones_q),
            "top_3": menciones_top,
        },
    }


@router.get("/yo/quick-wins")
def yo_quick_wins(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R373 P1: glosas "fáciles de ganar" HOY.

    La IA filtra de tu backlog las que probablemente
    levantes con poco esfuerzo:
      - Abierta
      - Tasa histórica del par (eps, codigo) >= 60%
      - Suficientes muestras (>= 3)
      - Aún no decidida y sin dictamen pesado

    Devuelve top N ordenado por (tasa * valor_objetado)
    para priorizar las más rentables.
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    nombre = current_user.nombre or current_user.email
    abiertas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .all()
    )

    # Pre-cache tasas (eps, codigo) para evitar N queries
    tasas_cache: dict[tuple, tuple[int, int]] = {}

    def _tasa_par(eps, cod):
        k = (eps, cod)
        if k in tasas_cache:
            return tasas_cache[k]
        rows = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.eps == eps)
            .filter(GlosaRecord.codigo_glosa == cod)
            .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
            .all()
        )
        n = len(rows)
        lev = sum(
            1 for r in rows
            if (r.estado or "").upper() == "LEVANTADA"
        )
        tasas_cache[k] = (n, lev)
        return n, lev

    items = []
    for g in abiertas:
        if not g.eps or not g.codigo_glosa:
            continue
        n, lev = _tasa_par(g.eps, g.codigo_glosa)
        if n < 3:
            continue
        tasa = 100.0 * lev / n
        if tasa < 60:
            continue
        valor = float(g.valor_objetado or 0)
        score = tasa * valor
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": int(valor),
            "tasa_par_pct": round(tasa, 2),
            "n_muestras": n,
            "score": round(score, 2),
            "dias_restantes": g.dias_restantes,
            "tiene_dictamen": bool(g.dictamen and len(g.dictamen) > 50),
        })
    items.sort(key=lambda x: x["score"], reverse=True)

    return {
        "usuario_email": current_user.email,
        "total_quick_wins": len(items),
        "valor_potencial": sum(it["valor_objetado"] for it in items),
        "items": items[: int(limit)],
    }


@router.get("/yo/asistente-proactivo")
def yo_asistente_proactivo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R368 P1: asistente proactivo — qué hacer HOY sin pedirlo.

    Combina señales del estado del usuario para devolver
    acciones priorizadas:
      URGENTE:    vencidas (dias_restantes < 0)
      IMPORTANTE: críticas (0-3 días)
      OPORTUNIDAD: alta cuantía sin dictamen
      MENCIONES:  comentarios pendientes que te etiquetan
      MEJORAR:    si tu tasa cayó vs mes anterior
      REVISAR:    glosas en estado RESPONDIDA esperando confirmar

    Cada acción tiene:
      tipo, prioridad (1=más urgente), mensaje,
      count, glosa_ids (top 5), accion_recomendada
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import (
        ComentarioGlosaRecord,
        GlosaRecord,
    )

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    nombre = current_user.nombre or current_user.email
    ahora = ahora_utc()
    inicio_mes = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    if inicio_mes.month == 1:
        inicio_anterior = inicio_mes.replace(
            year=inicio_mes.year - 1, month=12,
        )
    else:
        inicio_anterior = inicio_mes.replace(
            month=inicio_mes.month - 1,
        )

    acciones = []

    # 1. Vencidas (URGENTE)
    vencidas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < 0)
        .order_by(GlosaRecord.dias_restantes.asc())
        .all()
    )
    if vencidas:
        peor = vencidas[0]
        acciones.append({
            "tipo": "URGENTE",
            "prioridad": 1,
            "icono": "🚨",
            "titulo": f"{len(vencidas)} glosa(s) vencidas",
            "mensaje": (
                f"La más antigua lleva "
                f"{abs(int(peor.dias_restantes or 0))} días vencida. "
                "Cerrá hoy o se archivan automáticamente."
            ),
            "count": len(vencidas),
            "glosa_ids": [g.id for g in vencidas[:5]],
            "accion_recomendada": "Abre Mis Glosas y filtra por VENCIDA",
        })

    # 2. Críticas (IMPORTANTE) — solo abiertas con 0..3 dias
    criticas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes >= 0)
        .filter(GlosaRecord.dias_restantes <= 3)
        .order_by(GlosaRecord.dias_restantes.asc())
        .all()
    )
    if criticas:
        acciones.append({
            "tipo": "IMPORTANTE",
            "prioridad": 2,
            "icono": "⏰",
            "titulo": f"{len(criticas)} glosa(s) críticas",
            "mensaje": (
                "Vencen en 3 días o menos. Atendé hoy "
                "para asegurar el cierre dentro de SLA."
            ),
            "count": len(criticas),
            "glosa_ids": [g.id for g in criticas[:5]],
            "accion_recomendada": (
                "Prioriza por valor: las más caras primero"
            ),
        })

    # 3. Oportunidad: alta cuantía abierta sin dictamen
    sin_dict = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.valor_objetado >= 5_000_000)
        .filter(
            (GlosaRecord.dictamen.is_(None))
            | (GlosaRecord.dictamen == "")
        )
        .all()
    )
    if sin_dict:
        valor_total = sum(float(g.valor_objetado or 0) for g in sin_dict)
        acciones.append({
            "tipo": "OPORTUNIDAD",
            "prioridad": 3,
            "icono": "💰",
            "titulo": (
                f"{len(sin_dict)} glosa(s) de alto valor "
                "sin dictamen"
            ),
            "mensaje": (
                f"Valor total en juego: ${int(valor_total):,}. "
                "Un dictamen sólido aquí impacta directamente "
                "el recuperado del mes."
            ),
            "count": len(sin_dict),
            "glosa_ids": [g.id for g in sin_dict[:5]],
            "accion_recomendada": (
                "Pide casos similares con /casos-similares-resueltos"
            ),
        })

    # 4. Menciones pendientes
    menciones = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.mencion == current_user.email)
        .filter(
            (ComentarioGlosaRecord.resuelto == 0)
            | (ComentarioGlosaRecord.resuelto.is_(None))
        )
        .all()
    )
    if menciones:
        glosa_ids = list({m.glosa_id for m in menciones if m.glosa_id})[:5]
        acciones.append({
            "tipo": "MENCIONES",
            "prioridad": 4,
            "icono": "💬",
            "titulo": f"{len(menciones)} mención(es) sin resolver",
            "mensaje": (
                "Tus colegas te pidieron opinión en estas glosas. "
                "Responder construye colaboración."
            ),
            "count": len(menciones),
            "glosa_ids": glosa_ids,
            "accion_recomendada": "Abre cada glosa y responde al hilo",
        })

    # 5. Mejora: tasa actual vs mes anterior
    decididas_q = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(
            ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
        ))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_anterior)
        .all()
    )
    actual_dec = actual_lev = prev_dec = prev_lev = 0
    for g in decididas_q:
        f = g.fecha_decision_eps
        if not f:
            continue
        if f >= inicio_mes:
            actual_dec += 1
            if (g.estado or "").upper() == "LEVANTADA":
                actual_lev += 1
        else:
            prev_dec += 1
            if (g.estado or "").upper() == "LEVANTADA":
                prev_lev += 1
    tasa_actual = (
        (100.0 * actual_lev / actual_dec) if actual_dec else 0.0
    )
    tasa_prev = (
        (100.0 * prev_lev / prev_dec) if prev_dec else 0.0
    )
    if prev_dec >= 3 and tasa_actual + 5 < tasa_prev:
        acciones.append({
            "tipo": "MEJORAR",
            "prioridad": 5,
            "icono": "📉",
            "titulo": "Tu tasa cayó vs mes anterior",
            "mensaje": (
                f"Pasaste de {tasa_prev:.1f}% a {tasa_actual:.1f}%. "
                "Revisa qué cambió: ¿más ratificadas?, "
                "¿códigos nuevos?, ¿EPS distintas?"
            ),
            "count": int(prev_lev - actual_lev),
            "glosa_ids": [],
            "accion_recomendada": (
                "Revisa /yo/eps-mejor-rendimiento y "
                "/yo/comparativa-equipo"
            ),
        })

    # 6. Si no hay nada urgente, dar un mensaje motivador
    if not acciones:
        acciones.append({
            "tipo": "OK",
            "prioridad": 99,
            "icono": "✨",
            "titulo": "Todo bajo control",
            "mensaje": (
                "No tienes vencidas, ni críticas, ni "
                "menciones pendientes. Buen momento para "
                "revisar tu tasa y planear conciliaciones."
            ),
            "count": 0,
            "glosa_ids": [],
            "accion_recomendada": "Abre Resumen del mes",
        })

    return {
        "usuario_email": current_user.email,
        "generado_en": ahora.isoformat(),
        "total_acciones": len(acciones),
        "acciones": acciones,
    }


@router.get("/yo/stats-trimestre")
def yo_stats_trimestre(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R365 P1: stats personales del trimestre en curso.

    Para el usuario actual, métricas del trimestre actual:
      - decididas
      - levantadas
      - tasa_levantamiento_pct
      - valor_recuperado_total
      - dias_activos (días con al menos una decisión)
    """
    from datetime import timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    ahora = ahora_utc()
    trim = (ahora.month - 1) // 3 + 1
    inicio_trim = ahora.replace(
        month=(trim - 1) * 3 + 1, day=1,
        hour=0, minute=0, second=0, microsecond=0,
    )

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_trim)
        .all()
    )

    n_dec = len(rows)
    n_lev = sum(
        1 for g in rows if (g.estado or "").upper() == "LEVANTADA"
    )
    rec = sum(float(g.valor_recuperado or 0) for g in rows)
    dias = set()
    for g in rows:
        f = g.fecha_decision_eps
        if f and f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if f:
            dias.add(f.date())

    tasa = round(100 * n_lev / n_dec, 2) if n_dec else 0.0

    return {
        "usuario_email": current_user.email,
        "trimestre": f"{ahora.year}-Q{trim}",
        "decididas": n_dec,
        "levantadas": n_lev,
        "tasa_levantamiento_pct": tasa,
        "valor_recuperado_total": int(rec),
        "dias_activos": len(dias),
    }


@router.get("/yo/tendencia-personal")
def yo_tendencia_personal(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R356 P1: tendencia personal mes vs mes anterior.

    Para el usuario actual, comparación de cierre de
    glosas mes en curso vs mes anterior. Útil para "vs
    mes pasado, ¿estoy mejorando?".
    """
    from datetime import timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    ahora = ahora_utc()
    inicio_actual = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    if inicio_actual.month == 1:
        inicio_anterior = inicio_actual.replace(
            year=inicio_actual.year - 1, month=12,
        )
    else:
        inicio_anterior = inicio_actual.replace(
            month=inicio_actual.month - 1,
        )

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.fecha_decision_eps >= inicio_anterior)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .all()
    )

    a_count = 0
    a_rec = 0.0
    p_count = 0
    p_rec = 0.0
    for g in rows:
        f = g.fecha_decision_eps
        if f and f.tzinfo is None:
            f = f.replace(tzinfo=timezone.utc)
        if not f:
            continue
        rec = float(g.valor_recuperado or 0)
        if f >= inicio_actual:
            a_count += 1
            a_rec += rec
        else:
            p_count += 1
            p_rec += rec

    def _delta(a, p):
        if p == 0:
            return 100.0 if a > 0 else 0.0
        return round(100 * (a - p) / p, 2)

    return {
        "usuario_email": current_user.email,
        "mes_actual": inicio_actual.strftime("%Y-%m"),
        "mes_anterior": inicio_anterior.strftime("%Y-%m"),
        "actual": {
            "decididas": a_count,
            "valor_recuperado": int(a_rec),
        },
        "anterior": {
            "decididas": p_count,
            "valor_recuperado": int(p_rec),
        },
        "delta_decididas_pct": _delta(a_count, p_count),
        "delta_recuperado_pct": _delta(a_rec, p_rec),
    }


@router.get("/yo/dictamenes-stats")
def yo_dictamenes_stats(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R348 P1: estadística de calidad de TUS dictámenes.

    Para el usuario actual, métricas sobre el campo
    `dictamen` en sus glosas asignadas:
      - count_total
      - count_con_dictamen
      - len_promedio
      - count_cortos (<50 chars)
      - count_largos (>=200 chars)
      - pct_completos

    Útil para auto-evaluación de calidad escrita.
    """
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .all()
    )

    total = len(rows)
    con_dict = 0
    suma = 0
    cortos = 0
    largos = 0
    completos = 0

    for g in rows:
        d = g.dictamen or ""
        dlen = len(d)
        if dlen > 0:
            con_dict += 1
            suma += dlen
        if dlen < 50:
            cortos += 1
        elif dlen >= 200:
            largos += 1
        if dlen >= 50:
            completos += 1

    prom = round(suma / con_dict, 1) if con_dict else 0.0
    pct = round(100 * completos / total, 2) if total else 0.0

    return {
        "usuario_email": current_user.email,
        "count_total": total,
        "count_con_dictamen": con_dict,
        "len_promedio": prom,
        "count_cortos": cortos,
        "count_largos": largos,
        "pct_completos": pct,
    }


@router.get("/yo/eps-mejor-rendimiento")
def yo_eps_mejor_rendimiento(
    min_decididas: int = 3,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R337 P1: TUS EPS con mejor tasa de levantamiento.

    Para el usuario actual, qué EPS tienes con mejor tasa
    histórica de levantamiento. Útil para auto-coaching:
    "soy bueno con SANITAS, ¿qué hago bien?".

    Filtra por min_decididas (default 3) para evitar
    estadísticas con muestras pequeñas.

    Por EPS: count_decididas, levantadas, tasa.
    """
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(
            ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
        ))
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

    items = []
    for eps, b in bucket.items():
        if b["dec"] < min_decididas:
            continue
        tasa = round(100 * b["lev"] / b["dec"], 2)
        items.append({
            "eps": eps,
            "count_decididas": b["dec"],
            "levantadas": b["lev"],
            "tasa_levantamiento_pct": tasa,
        })
    items.sort(
        key=lambda x: x["tasa_levantamiento_pct"], reverse=True,
    )

    return {
        "usuario_email": current_user.email,
        "min_decididas": int(min_decididas),
        "total_eps": len(items),
        "items": items,
    }


@router.get("/yo/glosas-grandes")
def yo_glosas_grandes(
    umbral: float = 5_000_000,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R334 P1: tus glosas abiertas de alto valor.

    Lista glosas asignadas a ti (gestor_nombre) que están
    abiertas y tienen valor_objetado >= umbral. Útil
    para no perder de vista las "grandes" que tienen
    mayor impacto financiero.

    Ordena DESC por valor_objetado.
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    nombre = current_user.nombre or current_user.email
    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.valor_objetado >= float(umbral))
        .order_by(GlosaRecord.valor_objetado.desc())
        .all()
    )

    items = []
    for g in rows:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "dias_restantes": g.dias_restantes,
        })

    return {
        "usuario_email": current_user.email,
        "umbral": int(umbral),
        "total_grandes": len(items),
        "valor_total_pendiente": sum(
            it["valor_objetado"] for it in items
        ),
        "items": items,
    }


@router.get("/yo/glosas-asignadas-recientes")
def yo_glosas_asignadas_recientes(
    dias: int = 7,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R329 P1: glosas asignadas a mí en los últimos N días.

    Lista las glosas creadas en los últimos N días (default
    7) donde tu nombre figura como gestor. Útil como
    "qué llegó nuevo a mi mesa esta semana".
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    nombre = current_user.nombre or current_user.email
    desde = ahora_utc() - timedelta(days=int(dias))

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.creado_en >= desde)
        .order_by(GlosaRecord.creado_en.desc())
        .all()
    )

    items = []
    for g in rows:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "creado_en": (
                g.creado_en.isoformat() if g.creado_en else None
            ),
            "dias_restantes": g.dias_restantes,
        })

    return {
        "usuario_email": current_user.email,
        "ventana_dias": int(dias),
        "total_recientes": len(items),
        "items": items,
    }


@router.get("/yo/glosas-cerradas-mes")
def yo_glosas_cerradas_mes(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R318 P1: lista de TUS glosas cerradas este mes.

    Diferente a /yo/dashboard (solo count): aquí lista
    detallada de las que cerraste este mes con su
    resultado. Útil para ver el trabajo del mes en
    curso.

    Ordena DESC por fecha_decision_eps.
    """
    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    nombre = current_user.nombre or current_user.email
    inicio_mes = ahora_utc().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )

    rows = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.fecha_decision_eps >= inicio_mes)
        .order_by(GlosaRecord.fecha_decision_eps.desc())
        .limit(int(limit))
        .all()
    )

    items = []
    for g in rows:
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": int(float(g.valor_objetado or 0)),
            "valor_recuperado": int(float(g.valor_recuperado or 0)),
            "fecha_decision_eps": (
                g.fecha_decision_eps.isoformat()
                if g.fecha_decision_eps else None
            ),
        })

    levantadas = sum(
        1 for g in rows if (g.estado or "").upper() == "LEVANTADA"
    )

    return {
        "usuario_email": current_user.email,
        "mes": inicio_mes.strftime("%Y-%m"),
        "total_cerradas": len(items),
        "levantadas": levantadas,
        "valor_recuperado_total": sum(
            it["valor_recuperado"] for it in items
        ),
        "items": items,
    }


@router.get("/yo/eps-asignadas")
def yo_eps_asignadas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R310 P1: EPS con las que trabajas (como gestor).

    Lista las EPS donde tienes glosas asignadas, con
    counts. Útil para que un nuevo gestor vea su scope:
    "trabajo con 5 EPS distintas".

    Por EPS:
      - count_total
      - count_abiertas
      - valor_objetado_total
      - tasa_levantamiento_pct (sobre las que ya decidió)
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}

    nombre = current_user.nombre or current_user.email
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.eps.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        b = bucket.setdefault(eps, {
            "total": 0, "abiertas": 0, "valor": 0.0,
            "dec": 0, "lev": 0,
        })
        b["total"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        estado = (g.estado or "").upper()
        if estado not in ESTADOS_CERRADOS:
            b["abiertas"] += 1
        if estado in ESTADOS_DECIDIDOS:
            b["dec"] += 1
        if estado == "LEVANTADA":
            b["lev"] += 1

    items = []
    for eps, b in bucket.items():
        tasa = (
            round(100 * b["lev"] / b["dec"], 2) if b["dec"] else 0.0
        )
        items.append({
            "eps": eps,
            "count_total": b["total"],
            "count_abiertas": b["abiertas"],
            "valor_objetado_total": int(b["valor"]),
            "tasa_levantamiento_pct": tasa,
        })
    items.sort(key=lambda x: x["count_total"], reverse=True)

    return {
        "usuario_email": current_user.email,
        "total_eps": len(items),
        "items": items,
    }


@router.get("/yo/glosas-criticas")
def yo_glosas_criticas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R303 P1: lista de TUS glosas críticas (vencidas o
    a 3 días o menos del vencimiento).

    Diferente a /yo/dashboard (solo counts) y /yo/worklist
    (priorización heurística): aquí lista pura de las
    críticas con datos de identificación. Útil como
    morning briefing personal.

    Ordena ASC por dias_restantes (vencidas primero).
    """
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    nombre = current_user.nombre or current_user.email
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes <= 3)
        .order_by(GlosaRecord.dias_restantes.asc())
        .all()
    )

    items = []
    for g in glosas:
        dr = g.dias_restantes if g.dias_restantes is not None else 0
        items.append({
            "glosa_id": g.id,
            "eps": g.eps,
            "factura": g.factura,
            "estado": g.estado,
            "codigo_glosa": g.codigo_glosa,
            "dias_restantes": dr,
            "es_vencida": dr < 0,
            "valor_objetado": int(float(g.valor_objetado or 0)),
        })

    return {
        "usuario_email": current_user.email,
        "total_criticas": len(items),
        "vencidas": sum(1 for x in items if x["es_vencida"]),
        "items": items,
    }


@router.get("/yo/comentarios-emitidos")
def yo_comentarios_emitidos(
    dias: int = 90,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R291 P1: comentarios que el usuario ha emitido.

    Métricas de colaboración personal:
      - total_emitidos
      - menciones_hechas (con @ a otros)
      - resueltos (count)
      - resueltos_por_mi (count)
      - glosas_distintas

    Útil para auto-reflexión sobre nivel de colaboración.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import ComentarioGlosaRecord

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.autor_email == current_user.email)
        .filter(ComentarioGlosaRecord.creado_en >= desde)
        .all()
    )

    total = len(rows)
    menciones = sum(1 for c in rows if c.mencion)
    resueltos = sum(1 for c in rows if int(c.resuelto or 0) == 1)
    glosas = {c.glosa_id for c in rows}

    resueltos_por_mi = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.resuelto_por == current_user.email)
        .filter(ComentarioGlosaRecord.resuelto_en >= desde)
        .count()
    )

    return {
        "usuario_email": current_user.email,
        "ventana_dias": int(dias),
        "total_emitidos": total,
        "menciones_hechas": menciones,
        "resueltos": resueltos,
        "resueltos_por_mi": int(resueltos_por_mi),
        "glosas_distintas": len(glosas),
    }


@router.get("/yo/comparativa-equipo")
def yo_comparativa_equipo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R279 P1: cómo te comparas con el promedio del equipo.

    Calcula tus métricas y las del equipo (promedio entre
    gestores con al menos 1 decisión):
      - decididas, levantadas, tasa_levantamiento_pct,
        valor_recuperado_total

    Útil para auto-evaluación: "estoy por encima/debajo
    del promedio en tasa de levantamiento".

    No revela nombres de otros, solo agregado.
    """
    from app.models.db import GlosaRecord

    ESTADOS_DECIDIDOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
    nombre = current_user.nombre or current_user.email

    decididas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.in_(ESTADOS_DECIDIDOS))
        .filter(GlosaRecord.gestor_nombre.isnot(None))
        .all()
    )

    bucket: dict[str, dict] = {}
    for g in decididas:
        gestor = (g.gestor_nombre or "").strip()
        if not gestor:
            continue
        b = bucket.setdefault(gestor, {
            "dec": 0, "lev": 0, "rec": 0.0,
        })
        b["dec"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            b["lev"] += 1
        b["rec"] += float(g.valor_recuperado or 0)

    if not bucket:
        return {
            "usuario_email": current_user.email,
            "tu": {
                "decididas": 0, "levantadas": 0,
                "tasa_levantamiento_pct": 0.0,
                "valor_recuperado_total": 0,
            },
            "equipo": {
                "decididas_promedio": 0.0,
                "tasa_levantamiento_promedio_pct": 0.0,
                "valor_recuperado_promedio": 0,
                "total_gestores": 0,
            },
        }

    yo = bucket.get(nombre, {"dec": 0, "lev": 0, "rec": 0.0})
    yo_tasa = (
        round(100 * yo["lev"] / yo["dec"], 2) if yo["dec"] else 0.0
    )

    n = len(bucket)
    sum_dec = sum(b["dec"] for b in bucket.values())
    sum_lev = sum(b["lev"] for b in bucket.values())
    sum_rec = sum(b["rec"] for b in bucket.values())
    tasa_eq = round(100 * sum_lev / sum_dec, 2) if sum_dec else 0.0

    return {
        "usuario_email": current_user.email,
        "tu": {
            "decididas": yo["dec"],
            "levantadas": yo["lev"],
            "tasa_levantamiento_pct": yo_tasa,
            "valor_recuperado_total": int(yo["rec"]),
        },
        "equipo": {
            "decididas_promedio": round(sum_dec / n, 2),
            "tasa_levantamiento_promedio_pct": tasa_eq,
            "valor_recuperado_promedio": int(sum_rec / n),
            "total_gestores": n,
        },
    }


@router.get("/yo/streak")
def yo_streak(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R270 P1: racha (streak) de días consecutivos con
    al menos una glosa cerrada por el usuario.

    Métrica de gamificación para auto-motivación.
    Calcula:
      - streak_actual: días consecutivos hasta hoy
      - mejor_streak: mejor racha histórica
      - dias_con_actividad_total
      - ultima_decision_en

    Una decisión cuenta cuando estado pasó a LEVANTADA,
    ACEPTADA, RATIFICADA o ARCHIVADA y `fecha_decision_eps`
    está poblada.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    nombre = current_user.nombre or current_user.email

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.fecha_decision_eps.isnot(None))
        .all()
    )

    dias_set: set = set()
    ultima = None
    for g in glosas:
        dec = g.fecha_decision_eps
        if dec and dec.tzinfo is None:
            dec = dec.replace(tzinfo=timezone.utc)
        if not dec:
            continue
        dias_set.add(dec.date())
        if ultima is None or dec > ultima:
            ultima = dec

    if not dias_set:
        return {
            "usuario_email": current_user.email,
            "streak_actual": 0,
            "mejor_streak": 0,
            "dias_con_actividad_total": 0,
            "ultima_decision_en": None,
        }

    dias_ordenados = sorted(dias_set)
    hoy = ahora_utc().date()

    streak_actual = 0
    cursor = hoy
    while cursor in dias_set:
        streak_actual += 1
        cursor -= timedelta(days=1)
    if streak_actual == 0 and (hoy - timedelta(days=1)) in dias_set:
        cursor = hoy - timedelta(days=1)
        while cursor in dias_set:
            streak_actual += 1
            cursor -= timedelta(days=1)

    mejor = 1
    actual_run = 1
    for i in range(1, len(dias_ordenados)):
        if (dias_ordenados[i] - dias_ordenados[i - 1]).days == 1:
            actual_run += 1
            mejor = max(mejor, actual_run)
        else:
            actual_run = 1

    return {
        "usuario_email": current_user.email,
        "streak_actual": streak_actual,
        "mejor_streak": mejor,
        "dias_con_actividad_total": len(dias_set),
        "ultima_decision_en": ultima.isoformat() if ultima else None,
    }


@router.get("/yo/dashboard")
def dashboard_personal(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R255 P1: dashboard personal compacto del usuario actual.

    Single-call con los KPIs personales:
      - mis_glosas_abiertas
      - mis_vencidas / mis_criticas
      - mis_menciones_pendientes
      - cerradas_mes (mes corriente)

    Útil como pantalla principal del usuario al login.
    """
    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import ComentarioGlosaRecord, GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]
    nombre = current_user.nombre or current_user.email
    inicio_mes = ahora_utc().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )

    abiertas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar() or 0
    )
    vencidas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < 0)
        .scalar() or 0
    )
    criticas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes >= 0)
        .filter(GlosaRecord.dias_restantes <= 3)
        .scalar() or 0
    )
    menciones = (
        db.query(_f.count(ComentarioGlosaRecord.id))
        .filter(ComentarioGlosaRecord.mencion == current_user.email)
        .filter(
            (ComentarioGlosaRecord.resuelto == 0)
            | (ComentarioGlosaRecord.resuelto.is_(None))
        )
        .scalar() or 0
    )
    cerradas_mes = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.gestor_nombre == nombre)
        .filter(GlosaRecord.fecha_decision_eps >= inicio_mes)
        .filter(GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar() or 0
    )

    return {
        "usuario_email": current_user.email,
        "mis_glosas_abiertas": int(abiertas),
        "mis_vencidas": int(vencidas),
        "mis_criticas": int(criticas),
        "mis_menciones_pendientes": int(menciones),
        "cerradas_mes": int(cerradas_mes),
    }


@router.get("/yo/menciones-pendientes")
def menciones_pendientes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R216 P1: comentarios donde mencionan al usuario actual,
    sin resolver.

    Detecta @usuario en comentarios de glosas. Útil para
    notificaciones de "alguien necesita tu atención":
      "Bob te mencionó en glosa #123"

    Devuelve menciones DESC por creado_en con metadata.
    """
    from app.models.db import ComentarioGlosaRecord

    coms = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.mencion == current_user.email)
        .filter(
            (ComentarioGlosaRecord.resuelto == 0)
            | (ComentarioGlosaRecord.resuelto.is_(None))
        )
        .order_by(ComentarioGlosaRecord.creado_en.desc())
        .all()
    )

    items = []
    for c in coms:
        items.append({
            "id": c.id,
            "glosa_id": c.glosa_id,
            "autor_email": c.autor_email,
            "texto": (c.texto or "")[:300],
            "creado_en": (
                c.creado_en.isoformat() if c.creado_en else None
            ),
        })

    return {
        "usuario_email": current_user.email,
        "total_pendientes": len(items),
        "items": items,
    }


@router.get("/yo/permisos")
def permisos_del_usuario_actual(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R76 P2: capabilities del usuario actual basado en su rol.

    Útil para que el frontend decida qué botones/menus mostrar sin
    hardcodear roles. Si en el futuro se cambia la matriz de
    permisos, solo se actualiza acá.

    NO ejecuta autorización — solo describe. La autorización real
    sigue en cada endpoint con get_admin / get_coordinador_o_admin /
    get_auditor_o_superior.
    """
    rol = (current_user.rol or "").upper().strip()
    es_super = rol == "SUPER_ADMIN"
    es_admin = rol in ("SUPER_ADMIN", "ADMIN")
    es_coord = rol in ("SUPER_ADMIN", "ADMIN", "COORDINADOR")
    es_aud = rol in ("SUPER_ADMIN", "ADMIN", "COORDINADOR", "AUDITOR")

    return {
        "usuario_email": current_user.email,
        "rol": rol or None,
        "permisos": {
            "puede_analizar_glosa": True,
            "puede_refinar_dictamen": es_aud,
            "puede_reanalizar_glosa": es_aud,
            "puede_clonar_glosa": es_aud,
            "puede_eliminar_glosa": es_coord,
            "puede_ver_audit_log": es_coord,
            "puede_exportar_csv_audit": es_coord,
            "puede_ver_metricas_ia": es_coord,
            "puede_ver_dashboard_equipo": es_coord,
            "puede_ver_alertas_criticas": es_coord,
            "puede_ver_resumen_mensual": es_coord,
            "puede_bulk_actualizar_estado": es_aud,
            "puede_bulk_mover_papelera": es_coord,
            "puede_descargar_backup_db": es_super,
            "puede_purgar_mantenimiento": es_super,
            "puede_resetear_datos": es_super,
            "puede_admin_usuarios": es_super,
        },
    }


@router.get("/{usuario_id}/actividad")
def actividad_usuario(
    usuario_id: int,
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R95 P1: actividad de un usuario específico en el sistema.

    Combina:
      - Audit log: eventos generados por el usuario (acciones)
      - Glosas asignadas/auditadas (gestor_nombre o auditor_email)

    Útil para:
      - Coordinador: ¿qué hizo el equipo esta semana?
      - HR/management: medir productividad
      - Investigación: auditar comportamiento sospechoso

    Solo COORDINADOR/ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord, GlosaRecord

    usuario = db.query(UsuarioRecord).filter_by(id=usuario_id).first()
    if not usuario:
        raise HTTPException(404, f"Usuario {usuario_id} no encontrado")

    corte = ahora_utc() - timedelta(days=int(dias))

    # Audit log: eventos del usuario
    eventos = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.usuario_email == usuario.email)
        .filter(AuditLogRecord.timestamp >= corte)
        .all()
    )

    por_accion: dict[str, int] = {}
    por_tabla: dict[str, int] = {}
    for e in eventos:
        if e.accion:
            por_accion[e.accion] = por_accion.get(e.accion, 0) + 1
        if e.tabla:
            por_tabla[e.tabla] = por_tabla.get(e.tabla, 0) + 1

    # Glosas donde es gestor o auditor (en la ventana)
    glosas_asignadas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.gestor_nombre == (usuario.nombre or usuario.email))
        .filter(GlosaRecord.creado_en >= corte)
        .count()
    )
    glosas_auditadas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.auditor_email == usuario.email)
        .filter(GlosaRecord.creado_en >= corte)
        .count()
    )

    return {
        "usuario": {
            "id": usuario.id,
            "email": usuario.email,
            "nombre": usuario.nombre,
            "rol": usuario.rol,
        },
        "ventana_dias": int(dias),
        "audit": {
            "total_eventos": len(eventos),
            "por_accion": por_accion,
            "por_tabla": por_tabla,
        },
        "glosas": {
            "asignadas_como_gestor": glosas_asignadas,
            "auditadas": glosas_auditadas,
        },
    }


@router.get("/")
def listar_usuarios(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista todos los usuarios registrados."""
    usuarios = db.query(UsuarioRecord).order_by(UsuarioRecord.id).all()
    return [
        {"id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol, "activo": u.activo}
        for u in usuarios
    ]


@router.get("/sin-2fa")
def usuarios_sin_2fa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """R191 P1: usuarios activos SIN 2FA configurado.

    Para auditoría de seguridad: identificar cuentas que no
    han habilitado autenticación de dos factores. Riesgo
    Habeas Data.

    Útil para forzar política "todos los AUDITOR/COORDINADOR
    deben tener 2FA en X días".

    Solo SUPER_ADMIN.
    """
    usuarios = (
        db.query(UsuarioRecord)
        .filter(UsuarioRecord.activo == 1)
        .filter(
            (UsuarioRecord.totp_secret.is_(None))
            | (UsuarioRecord.totp_secret == "")
        )
        .all()
    )

    items = []
    for u in usuarios:
        items.append({
            "id": u.id,
            "email": u.email,
            "nombre": u.nombre,
            "rol": u.rol,
        })

    return {
        "total_sin_2fa": len(items),
        "items": items,
    }


@router.get("/stats")
def stats_usuarios(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R164 P1: estadísticas globales de usuarios.

    Cifras agregadas para dashboard de admin:
      - total y activos
      - distribución por rol
      - usuarios con 2FA habilitado
      - usuarios con email único / sin nombre

    Solo COORDINADOR/ADMIN.
    """
    todos = db.query(UsuarioRecord).all()

    activos = sum(1 for u in todos if u.activo == 1)
    por_rol: dict[str, int] = {}
    con_2fa = 0
    sin_nombre = 0
    for u in todos:
        rol = u.rol or "(SIN_ROL)"
        por_rol[rol] = por_rol.get(rol, 0) + 1
        if u.totp_secret:
            con_2fa += 1
        if not u.nombre:
            sin_nombre += 1

    return {
        "total": len(todos),
        "activos": activos,
        "inactivos": len(todos) - activos,
        "con_2fa": con_2fa,
        "sin_nombre": sin_nombre,
        "por_rol": por_rol,
    }


@router.get("/roles/disponibles")
def listar_roles_disponibles(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista los roles disponibles con descripción (requiere autenticación)."""
    return [
        {"rol": ROL_SUPER_ADMIN, "descripcion": "Todo: usuarios, configuración, eliminar"},
        {"rol": ROL_COORDINADOR, "descripcion": "Ver todo, aprobar, exportar"},
        {"rol": ROL_AUDITOR, "descripcion": "Crear/responder glosas propias"},
        {"rol": ROL_VIEWER, "descripcion": "Solo lectura"},
    ]


def _garantizar_al_menos_un_super_admin_activo(db: Session, excluir_id: int = None):
    """Verifica que exista al menos un SUPER_ADMIN activo distinto al excluido.

    Se llama antes de cambiar rol, desactivar o eliminar para no dejar la
    instancia sin administrador alguno.
    """
    q = db.query(UsuarioRecord).filter(
        UsuarioRecord.rol == ROL_SUPER_ADMIN,
        UsuarioRecord.activo == 1,
    )
    if excluir_id is not None:
        q = q.filter(UsuarioRecord.id != excluir_id)
    if q.count() == 0:
        raise HTTPException(
            status_code=400,
            detail="No se puede dejar el sistema sin SUPER_ADMIN activo. "
                   "Asigna este rol a otro usuario antes de proceder.",
        )


@router.post("/", status_code=201)
def crear_usuario(
    data: UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea un nuevo usuario."""
    email = data.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email inválido")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 6 caracteres")
    if not data.nombre.strip():
        raise HTTPException(status_code=400, detail="El nombre es requerido")
    
    existe = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if existe:
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
    
    usuario = UsuarioRecord(
        nombre=data.nombre.strip(),
        email=email,
        password_hash=get_password_hash(data.password),
        rol=ROL_AUDITOR,
        activo=1,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="CREAR",
        tabla="usuarios",
        registro_id=usuario.id,
        detalle=f"Usuario creado: {email} con rol {ROL_AUDITOR}"
    )
    
    return {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "message": "Usuario creado exitosamente"
    }


@router.patch("/{usuario_id}")
def editar_usuario(
    usuario_id: int,
    data: UsuarioUpdate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Edita nombre y/o email de un usuario (solo SUPER_ADMIN).

    Al menos uno de los dos campos debe venir en el body. El email
    se normaliza a minúsculas y se valida unicidad.
    """
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    cambios = []
    if data.nombre is not None:
        nuevo_nombre = data.nombre.strip()
        if not nuevo_nombre:
            raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
        if nuevo_nombre != usuario.nombre:
            cambios.append(("nombre", usuario.nombre, nuevo_nombre))
            usuario.nombre = nuevo_nombre

    if data.email is not None:
        nuevo_email = data.email.strip().lower()
        if not nuevo_email or "@" not in nuevo_email:
            raise HTTPException(status_code=400, detail="Email inválido")
        if nuevo_email != usuario.email:
            ya_existe = db.query(UsuarioRecord).filter(
                UsuarioRecord.email == nuevo_email,
                UsuarioRecord.id != usuario_id,
            ).first()
            if ya_existe:
                raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
            cambios.append(("email", usuario.email, nuevo_email))
            usuario.email = nuevo_email

    if not cambios:
        return {"message": "Sin cambios", "id": usuario.id, "nombre": usuario.nombre, "email": usuario.email}

    db.commit()
    db.refresh(usuario)

    for campo, anterior, nuevo in cambios:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="ACTUALIZAR",
            tabla="usuarios",
            registro_id=usuario_id,
            campo=campo,
            valor_anterior=anterior,
            valor_nuevo=nuevo,
            detalle=f"{campo.capitalize()} cambiado de '{anterior}' a '{nuevo}'",
        )

    return {
        "message": "Usuario actualizado",
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol": usuario.rol,
        "activo": usuario.activo,
    }


@router.patch("/{usuario_id}/password")
def cambiar_password(
    usuario_id: int,
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Cambia la contraseña de un usuario."""
    if len(data.nueva_password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 6 caracteres")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    usuario.password_hash = get_password_hash(data.nueva_password)
    db.commit()
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ACTUALIZAR",
        tabla="usuarios",
        registro_id=usuario_id,
        campo="password",
        detalle=f"Contraseña cambiada para usuario {usuario.email}"
    )
    return {"message": "Contraseña actualizada exitosamente"}


@router.patch("/{usuario_id}/rol")
def cambiar_rol(
    usuario_id: int,
    data: RolChange,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Cambia el rol de un usuario (solo SUPER_ADMIN)."""
    nuevo_rol = data.rol.upper()
    if nuevo_rol not in ROLES_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Use: {', '.join(ROLES_VALIDOS)}")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    anterior = usuario.rol
    # Si estamos degradando a un SUPER_ADMIN, validar que quede al menos otro activo
    if anterior == ROL_SUPER_ADMIN and nuevo_rol != ROL_SUPER_ADMIN:
        _garantizar_al_menos_un_super_admin_activo(db, excluir_id=usuario_id)

    usuario.rol = nuevo_rol
    db.commit()

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ACTUALIZAR",
        tabla="usuarios",
        registro_id=usuario_id,
        campo="rol",
        valor_anterior=anterior,
        valor_nuevo=nuevo_rol,
        detalle=f"Rol cambiado de {anterior} a {nuevo_rol} para {usuario.email}"
    )
    return {"message": "Rol actualizado", "nuevo_rol": nuevo_rol}


@router.patch("/{usuario_id}/activar")
def activar_desactivar(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Activa o desactiva un usuario."""
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    anterior = usuario.activo
    # Si se va a desactivar a un SUPER_ADMIN, validar que quede al menos otro activo
    if anterior == 1 and usuario.rol == ROL_SUPER_ADMIN:
        _garantizar_al_menos_un_super_admin_activo(db, excluir_id=usuario_id)

    usuario.activo = 0 if anterior == 1 else 1
    db.commit()
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ACTUALIZAR",
        tabla="usuarios",
        registro_id=usuario_id,
        campo="activo",
        valor_anterior=str(anterior),
        valor_nuevo=str(usuario.activo),
        detalle=f"Usuario {'activado' if usuario.activo else 'desactivado'}: {usuario.email}"
    )
    return {"message": f"Usuario {'activado' if usuario.activo else 'desactivado'}", "activo": usuario.activo}


@router.delete("/{usuario_id}")
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Elimina un usuario (solo SUPER_ADMIN)."""
    if usuario_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario mientras estás activo")

    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Si es el último SUPER_ADMIN activo, no permitir su eliminación
    if usuario.rol == ROL_SUPER_ADMIN and usuario.activo == 1:
        _garantizar_al_menos_un_super_admin_activo(db, excluir_id=usuario_id)

    email = usuario.email
    db.delete(usuario)
    db.commit()
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ELIMINAR",
        tabla="usuarios",
        registro_id=usuario_id,
        detalle=f"Usuario eliminado: {email}"
    )
    return {"message": f"Usuario {usuario_id} eliminado"}
