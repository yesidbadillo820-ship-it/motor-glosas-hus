"""Diagnóstico de calidad del dictamen, servido por HTTP.

09-09-2026. El auditor preguntó por qué la confianza no sube y qué hay que
cambiar. Buena parte de la respuesta solo se puede dar mirando la base de
datos REAL del hospital, que no se ve desde el entorno de desarrollo. La
alternativa era pedirle que corriera un script por consola en el servidor:
trabajo manual, y él no tiene tiempo para eso.

Esto lo vuelve un enlace. Entra a la pantalla, copia el JSON, y listo.

Solo lee. No escribe nada. Solo SUPER_ADMIN.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_admin
from app.database import get_db
from app.models.db import (
    AICallRecord,
    ClausulaContrato,
    ContratoRecord,
    GlosaRecord,
    TarifaContratadaRecord,
    UsuarioRecord,
)

router = APIRouter(prefix="/admin/diagnostico-calidad", tags=["diagnostico"])

# El marcador del desplegable, que no es una entidad pagadora.
_EPS_GENERICAS = ("OTRA / SIN DEFINIR", "OTRA", "SIN DEFINIR", "")

# Estados que significan que la EPS ya dio su veredicto final. De aquí se
# alimentan el «precedente interno» del puntaje de confianza Y el banco de
# argumentos ganadores que la IA recibe como ejemplo (few_shot_gold).
_ESTADOS_CERRADOS = ("LEVANTADA", "RATIFICADA", "ACEPTADA", "CONCILIADA")


@router.get("")
def diagnostico_calidad(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Los números reales detrás de la confianza baja."""
    total = db.query(GlosaRecord).count()
    out: dict = {"glosas_analizadas": total}
    if not total:
        out["nota"] = "No hay glosas registradas: el resto no se puede calcular."
        return out

    # ── EPS: cuántas quedaron sin entidad identificada ──────────────────
    por_eps = db.query(GlosaRecord.eps, func.count(GlosaRecord.id)).group_by(GlosaRecord.eps).all()
    genericas = sum(n for eps, n in por_eps if (eps or "").strip().upper() in _EPS_GENERICAS)
    out["eps"] = {
        "genericas": genericas,
        "pct_genericas": round(100 * genericas / total, 1),
        "con_nombre_real": sorted(
            (
                {"eps": eps, "glosas": n}
                for eps, n in por_eps
                if (eps or "").strip().upper() not in _EPS_GENERICAS
            ),
            key=lambda x: -x["glosas"],
        )[:20],
    }

    # ── Tarifa pactada por CUPS: el dato que falta en las glosas TA* ────
    n_tarifas = db.query(TarifaContratadaRecord).count()
    out["tarifas_pactadas_por_cups"] = {
        "filas": n_tarifas,
        "diagnostico": (
            "VACÍA — en una glosa de TARIFAS el motor no puede comparar cifra "
            "contra cifra por ítem; solo tiene el texto general del contrato."
            if n_tarifas == 0
            else "Con datos."
        ),
    }

    # ── Cláusulas de contrato ───────────────────────────────────────────
    out["contratos"] = {
        "eps_con_clausulas": db.query(ClausulaContrato.eps).distinct().count(),
        "eps_con_registro_de_contrato": db.query(ContratoRecord).count(),
    }

    # ── Veredicto final: combustible del precedente y de los ejemplos ───
    por_estado = (
        db.query(GlosaRecord.estado, func.count(GlosaRecord.id)).group_by(GlosaRecord.estado).all()
    )
    cerrados = sum(n for e, n in por_estado if (e or "").upper() in _ESTADOS_CERRADOS)
    out["veredicto_final_eps"] = {
        "con_veredicto": cerrados,
        "pct": round(100 * cerrados / total, 1),
        "por_estado": sorted(
            ({"estado": e or "SIN ESTADO", "glosas": n} for e, n in por_estado),
            key=lambda x: -x["glosas"],
        ),
        "diagnostico": (
            "Menos del 30%: el precedente interno y el banco de argumentos "
            "ganadores se quedan sin combustible aunque entren más glosas."
            if total and cerrados / total < 0.30
            else "Suficiente para alimentar precedente y ejemplos."
        ),
    }

    # ── LA COMPARACIÓN QUE DECIDE EL CAMBIO DE MODELO ───────────────────
    # 09-09-2026, corrección. Esto devolvía el promedio de `GlosaRecord.score`
    # con el rótulo «confianza_promedio», y NO es la Confianza: `score` es la
    # fórmula vieja de probabilidad de éxito (99 extemporánea / 92 ratificación
    # / 90 urgencia / 75 tarifa / 85 el resto, +5 con PDF). Daba 77% de
    # promedio mientras el auditor veía 51% en pantalla, y con eso se habría
    # concluido «el modelo está bien» sobre un número que no medía el modelo.
    #
    # Las dos van, cada una con su nombre. La Confianza empieza a guardarse
    # HOY: las glosas anteriores la tienen en NULL —de ellas no se guardó— y
    # eso se dice en vez de disimularlo con un cero.
    por_modelo = (
        db.query(
            GlosaRecord.modelo_ia,
            func.count(GlosaRecord.id),
            func.avg(GlosaRecord.score),
        )
        .filter(GlosaRecord.score > 0)
        .group_by(GlosaRecord.modelo_ia)
        .all()
    )
    out["probabilidad_exito_por_modelo"] = sorted(
        (
            {"modelo": m or "sin registrar", "glosas": n, "promedio": round(avg or 0, 1)}
            for m, n, avg in por_modelo
        ),
        key=lambda x: -x["glosas"],
    )

    conf_por_modelo = (
        db.query(
            GlosaRecord.modelo_ia,
            func.count(GlosaRecord.id),
            func.avg(GlosaRecord.confianza_score),
            func.min(GlosaRecord.confianza_score),
            func.max(GlosaRecord.confianza_score),
        )
        .filter(GlosaRecord.confianza_score.isnot(None))
        .group_by(GlosaRecord.modelo_ia)
        .all()
    )
    con_confianza = db.query(GlosaRecord).filter(GlosaRecord.confianza_score.isnot(None)).count()
    out["confianza_por_modelo"] = {
        "glosas_con_confianza_guardada": con_confianza,
        "de_un_total_de": total,
        "detalle": sorted(
            (
                {
                    "modelo": m or "sin registrar",
                    "glosas": n,
                    "confianza_promedio": round(avg or 0, 1),
                    "peor": round(mn or 0, 1),
                    "mejor": round(mx or 0, 1),
                }
                for m, n, avg, mn, mx in conf_por_modelo
            ),
            key=lambda x: -x["glosas"],
        ),
        "diagnostico": (
            "Todavía no hay ninguna glosa con la Confianza guardada. Se empezó "
            "a guardar el 09-09-2026; las anteriores no la tienen y no se puede "
            "reconstruir hacia atrás. Con unas cuantas glosas nuevas ya se puede "
            "comparar un modelo contra otro."
            if con_confianza == 0
            else "Esta es la comparación buena: la misma Confianza que sale en "
            "pantalla al pie de cada dictamen."
        ),
    }

    # ── Costo real por proveedor: ya está calculado, solo se lee ────────
    por_proveedor = (
        db.query(
            AICallRecord.proveedor,
            func.count(AICallRecord.id),
            func.sum(AICallRecord.cost_usd),
            func.avg(AICallRecord.cost_usd),
            func.avg(AICallRecord.latency_ms),
        )
        .group_by(AICallRecord.proveedor)
        .all()
    )
    out["costo_ia"] = [
        {
            "proveedor": p,
            "llamadas": n,
            "costo_total_usd": round(tot or 0, 4),
            "costo_promedio_usd": round(avg or 0, 4),
            "latencia_promedio_ms": int(lat or 0),
            "proyeccion_mensual_usd_a_este_volumen": round((avg or 0) * total, 2),
        }
        for p, n, tot, avg, lat in por_proveedor
    ]
    return out
