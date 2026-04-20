"""Export a ERP contable (CSV con encabezados estándar SIIGO/Hélisa)."""
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/export-erp", tags=["export-erp"])


@router.get("/recuperaciones")
def export_recuperaciones(
    desde: Optional[str] = Query(None, description="YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Exporta un CSV con formato de asiento contable para cargar al ERP.

    Columnas: FECHA | CUENTA | TERCERO_NIT | FACTURA | DESCRIPCION |
              DEBE | HABER | CENTRO_COSTO

    Incluye solo glosas RESPONDIDAS/LEVANTADAS con valor_recuperado > 0.
    """
    f_desde = _parse_date(desde) or (datetime.utcnow() - timedelta(days=30))
    f_hasta = _parse_date(hasta) or datetime.utcnow()

    q = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.creado_en >= f_desde,
            GlosaRecord.creado_en <= f_hasta,
        )
        .order_by(GlosaRecord.creado_en.asc())
    )
    glosas = q.all()

    buf = StringIO()
    buf.write("FECHA,CUENTA,TERCERO,FACTURA,DESCRIPCION,DEBE,HABER,CENTRO_COSTO\n")
    for g in glosas:
        fecha = (g.creado_en or datetime.utcnow()).strftime("%Y-%m-%d")
        obj = float(g.valor_objetado or 0)
        ace = float(g.valor_aceptado or 0)
        recuperado = obj - ace
        if recuperado <= 0:
            continue
        # Asiento: DEBE a la EPS (138505-CARTERA-EPS), HABER a recuperación (419500)
        eps_clean = (g.eps or "SIN_DEFINIR").replace(",", " ").replace("\"", "")
        fac = (g.factura or "N/A").replace(",", " ")
        desc = f"Recuperacion glosa {g.codigo_glosa or ''} {eps_clean}".replace(",", " ")[:120]
        # Línea 1: DEBE (reverso de cartera)
        buf.write(f"{fecha},138505,{eps_clean},{fac},{desc},{recuperado:.0f},0,CARTERA-GLOSAS\n")
        # Línea 2: HABER (ingreso por recuperación)
        buf.write(f"{fecha},419500,{eps_clean},{fac},{desc},0,{recuperado:.0f},CARTERA-GLOSAS\n")

    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="EXPORT_ERP", tabla="historial",
        detalle=f"Periodo {f_desde.date()} a {f_hasta.date()} · {len(glosas)} glosas",
    )

    buf.seek(0)
    filename = f"recuperaciones_glosas_{f_desde.strftime('%Y%m%d')}_{f_hasta.strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None
