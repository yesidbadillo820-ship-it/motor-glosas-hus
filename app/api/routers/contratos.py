from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.schemas import ContratoInput
from app.repositories.contrato_repository import ContratoRepository
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/contratos", tags=["contratos"])

@router.get("/", response_model=List[dict])
def listar_contratos(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Retorna todos los contratos registrados en el HUS."""
    repo = ContratoRepository(db)
    contratos = repo.listar()
    return [{"eps": c.eps, "detalles": c.detalles} for c in contratos]

@router.post("/upsert")
def crear_o_actualizar_contrato(
    data: ContratoInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea un nuevo contrato o actualiza uno existente si la EPS ya existe."""
    repo = ContratoRepository(db)
    return repo.upsert(data)

@router.get("/ranking")
def ranking_contratos(
    min_glosas: int = 5,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R100 P2: ranking de contratos por valor recuperado total.

    Útil para reporte ejecutivo:
      "¿De qué EPS hemos sacado más plata este año?"

    Filtra contratos con >= min_glosas históricas (default 5)
    para evitar ruido de EPS con poca data.

    Devuelve por contrato:
      - eps
      - total_glosas
      - valor_recuperado_total
      - tasa_recuperacion_pct
      - ranking_position (1=mejor)

    Ordenado DESC por valor_recuperado_total.
    """
    from app.models.db import GlosaRecord

    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {
                "total": 0,
                "valor_objetado": 0.0,
                "valor_recuperado": 0.0,
            }
        b = por_eps[eps]
        b["total"] += 1
        b["valor_objetado"] += float(g.valor_objetado or 0)
        b["valor_recuperado"] += float(g.valor_recuperado or 0)

    items = []
    for eps, b in por_eps.items():
        if b["total"] < min_glosas:
            continue
        tasa = (
            round(100 * b["valor_recuperado"] / b["valor_objetado"], 2)
            if b["valor_objetado"] else 0.0
        )
        items.append({
            "eps": eps,
            "total_glosas": b["total"],
            "valor_objetado_total": int(b["valor_objetado"]),
            "valor_recuperado_total": int(b["valor_recuperado"]),
            "tasa_recuperacion_pct": tasa,
        })

    items.sort(
        key=lambda x: x["valor_recuperado_total"],
        reverse=True,
    )
    for idx, it in enumerate(items, start=1):
        it["ranking_position"] = idx

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_contratos_evaluados": len(items),
        "items": items,
    }


@router.get("/{eps}/perfil-detallado")
def perfil_detallado_eps(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R121 P2: perfil 360º de una EPS — toda la info en single-call.

    Combina:
      - Métricas históricas (volumen, valores, tasas)
      - Top códigos glosa que esta EPS objeta
      - Códigos respuesta más exitosos contra esta EPS
      - Tiempo promedio de decisión
      - Glosas pendientes vs cerradas
      - Última actividad

    Útil al abrir el panel de un contrato sin tener que hacer
    múltiples requests.
    """
    from datetime import timezone

    from app.models.db import GlosaRecord

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .all()
    )

    if not glosas:
        return {
            "eps": eps,
            "sin_historial": True,
            "total_glosas": 0,
        }

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    abiertas = [g for g in glosas if (g.estado or "").upper() not in ESTADOS_CERRADOS]
    cerradas = [g for g in glosas if (g.estado or "").upper() in ESTADOS_CERRADOS]
    levantadas = [g for g in cerradas if (g.estado or "").upper() == "LEVANTADA"]
    decididas = [
        g for g in cerradas
        if (g.estado or "").upper() in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
    ]

    valor_obj = sum(float(g.valor_objetado or 0) for g in glosas)
    valor_rec = sum(float(g.valor_recuperado or 0) for g in glosas)
    valor_pendiente = sum(float(g.valor_objetado or 0) for g in abiertas)

    # Top códigos glosa
    por_codigo: dict[str, int] = {}
    for g in glosas:
        if g.codigo_glosa:
            por_codigo[g.codigo_glosa] = por_codigo.get(g.codigo_glosa, 0) + 1
    top_codigos = sorted(por_codigo.items(), key=lambda x: x[1], reverse=True)[:5]

    # Códigos respuesta exitosos
    por_resp: dict[str, dict] = {}
    for g in cerradas:
        cr = g.codigo_respuesta
        if not cr:
            continue
        if cr not in por_resp:
            por_resp[cr] = {"total": 0, "levantadas": 0}
        por_resp[cr]["total"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_resp[cr]["levantadas"] += 1
    resp_efectivos = []
    for cr, b in por_resp.items():
        tasa = round(100 * b["levantadas"] / b["total"], 2) if b["total"] else 0
        resp_efectivos.append({
            "codigo_respuesta": cr,
            "usado": b["total"],
            "tasa_exito_pct": tasa,
        })
    resp_efectivos.sort(key=lambda x: x["tasa_exito_pct"], reverse=True)

    # Tiempo promedio decisión
    tiempos = []
    for g in cerradas:
        if g.fecha_decision_eps and g.creado_en:
            dec = g.fecha_decision_eps
            cre = g.creado_en
            if dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)
            if cre.tzinfo is None:
                cre = cre.replace(tzinfo=timezone.utc)
            tiempos.append((dec - cre).days)

    # Última glosa creada (señal de actividad)
    ultima = max(
        (g.creado_en for g in glosas if g.creado_en),
        default=None,
    )

    return {
        "eps": eps,
        "sin_historial": False,
        "volumen": {
            "total_glosas": len(glosas),
            "abiertas": len(abiertas),
            "cerradas": len(cerradas),
            "decididas": len(decididas),
            "levantadas": len(levantadas),
        },
        "economico": {
            "valor_objetado_total": int(valor_obj),
            "valor_recuperado_total": int(valor_rec),
            "valor_pendiente": int(valor_pendiente),
            "tasa_recuperacion_pct": (
                round(100 * valor_rec / valor_obj, 2) if valor_obj else 0.0
            ),
        },
        "resoluciones": {
            "tasa_levantamiento_pct": (
                round(100 * len(levantadas) / len(decididas), 2)
                if decididas else 0.0
            ),
            "tiempo_promedio_decision_dias": (
                round(sum(tiempos) / len(tiempos), 2) if tiempos else 0.0
            ),
        },
        "top_5_codigos_objetados": [
            {"codigo": c, "veces": n} for c, n in top_codigos
        ],
        "codigos_respuesta_efectivos": resp_efectivos[:5],
        "ultima_actividad": ultima.isoformat() if ultima else None,
    }


@router.get("/{eps}/glosas-historico")
def historial_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R100 P1: resumen del histórico de glosas para un contrato (EPS).

    Útil para entender la "salud" del contrato con esta EPS:
      - ¿Cuántas glosas en total?
      - ¿Tasa de levantamiento?
      - ¿Valor total objetado vs recuperado?
      - ¿Top 5 códigos de glosa más usados por esta EPS?

    Devuelve métricas agregadas + top códigos.
    """
    from app.models.db import GlosaRecord

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .all()
    )

    total = len(glosas)
    if total == 0:
        return {
            "eps": eps,
            "total_glosas": 0,
            "valor_objetado_total": 0,
            "valor_recuperado_total": 0,
            "tasa_recuperacion_pct": 0.0,
            "tasa_levantamiento_pct": 0.0,
            "top_5_codigos": [],
        }

    valor_obj = sum(float(g.valor_objetado or 0) for g in glosas)
    valor_rec = sum(float(g.valor_recuperado or 0) for g in glosas)

    decididas = [g for g in glosas if (g.estado or "").upper()
                 in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}]
    levantadas = sum(1 for g in decididas
                     if (g.estado or "").upper() == "LEVANTADA")

    # Top 5 códigos
    por_codigo: dict[str, int] = {}
    for g in glosas:
        if g.codigo_glosa:
            por_codigo[g.codigo_glosa] = por_codigo.get(g.codigo_glosa, 0) + 1
    top_5 = sorted(por_codigo.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "eps": eps,
        "total_glosas": total,
        "valor_objetado_total": int(valor_obj),
        "valor_recuperado_total": int(valor_rec),
        "tasa_recuperacion_pct": (
            round(100 * valor_rec / valor_obj, 2)
            if valor_obj else 0.0
        ),
        "tasa_levantamiento_pct": (
            round(100 * levantadas / len(decididas), 2)
            if decididas else 0.0
        ),
        "decididas": len(decididas),
        "pendientes": total - len(decididas),
        "top_5_codigos": [
            {"codigo": c, "veces": n} for c, n in top_5
        ],
    }


@router.delete("/{eps}")
def eliminar_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Elimina el contrato de una EPS específica."""
    repo = ContratoRepository(db)
    exito = repo.eliminar(eps)
    if not exito:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return {"message": f"Contrato con {eps} eliminado correctamente"}
