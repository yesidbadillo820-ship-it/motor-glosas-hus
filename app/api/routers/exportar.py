"""Export al formato DGH (Excel de 26 columnas canónicas).

Ronda 29 (jul-2026): el botón "📥 Formato DGH" del Historial llamaba a
GET /exportar/dgh pero el router se perdió en una limpieza anterior — el
servicio completo (app/services/exportar_dgh.py) quedó huérfano y el botón
devolvía 404. Este router lo reconecta reutilizando los filtros de la
vista Historial (eps, estado, desde, hasta, solo_respondidas).
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.repositories.audit_repository import AuditRepository
from app.services.exportar_dgh import generar_excel_dgh

router = APIRouter(prefix="/exportar", tags=["exportar"])

# Estados que cuentan como "respondidas" para el cargue al DGH.
_ESTADOS_RESPONDIDAS = ("RESPONDIDA", "LEVANTADA")


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@router.get("/dgh")
def exportar_formato_dgh(
    eps: Optional[str] = Query(None, description="Filtra por EPS (subcadena)"),
    estado: Optional[str] = Query(None, description="Filtra por estado exacto"),
    desde: Optional[str] = Query(None, description="YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="YYYY-MM-DD"),
    solo_respondidas: bool = Query(True, description="Solo RESPONDIDA/LEVANTADA"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Descarga el Excel con la estructura EXACTA que exige el DGH.

    26 columnas canónicas + dictamen limpio en OBSERVACION (una fila por
    concepto de glosa). Reutiliza los filtros de la vista Historial.
    """
    q = db.query(GlosaRecord)
    if eps:
        q = q.filter(GlosaRecord.eps.ilike(f"%{eps}%"))
    if estado:
        q = q.filter(GlosaRecord.estado == estado)
    elif solo_respondidas:
        q = q.filter(GlosaRecord.estado.in_(_ESTADOS_RESPONDIDAS))
    f_desde = _parse_date(desde)
    f_hasta = _parse_date(hasta)
    if f_desde:
        q = q.filter(GlosaRecord.creado_en >= f_desde)
    if f_hasta:
        # `hasta` es inclusivo (día completo): se compara contra el día
        # siguiente a las 00:00.
        q = q.filter(GlosaRecord.creado_en < f_hasta.replace(hour=23, minute=59, second=59))
    glosas = q.order_by(GlosaRecord.creado_en.asc()).all()

    try:
        buf = generar_excel_dgh(db, glosas)
    except ImportError:
        raise HTTPException(status_code=503, detail="openpyxl no instalado en el servidor")

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="EXPORT_DGH",
        tabla="historial",
        detalle=f"eps={eps or 'todas'} estado={estado or 'auto'} · {len(glosas)} glosas",
    )

    filename = f"glosas_dgh_{ahora_utc().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
