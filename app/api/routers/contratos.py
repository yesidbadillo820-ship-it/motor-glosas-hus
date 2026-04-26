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
