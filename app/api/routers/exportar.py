from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.glosa_repository import GlosaRepository
from app.services.excel_service import ExcelExporter, EXCEL_DISPONIBLE
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/exportar", tags=["exportar"])


@router.get("/glosas")
def exportar_glosas(
    eps: str = Query(None, description="Filtrar por EPS"),
    estado: str = Query(None, description="Filtrar por estado"),
    limit: int = Query(1000, ge=1, le=5000, description="Máximo de registros"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Exporta glosas a archivo Excel con formato institucional HUS.
    
    Requiere autenticación JWT.
    """
    if not EXCEL_DISPONIBLE:
        return {"error": " openpyxl no instalado. Ejecute: pip install openpyxl"}
    
    repo = GlosaRepository(db)
    glosas = repo.listar(limit=limit, eps=eps)
    
    if estado:
        glosas = [g for g in glosas if g.estado == estado.upper()]
    
    exportador = ExcelExporter()
    
    fecha_texto = ""
    if eps:
        fecha_texto = f"EPS: {eps}"
    
    output = exportador.generar_reporte_glosas(
        glosas=glosas,
        titulo="Reporte de Glosas",
        fecha_inicio=None,
        fecha_fin=None,
    )
    
    filename = f"glosas_hus_{eps or 'todos'}_{estado or 'todos'}_{exportador._formato_fecha(None)}.xlsx"
    filename = filename.replace(" ", "_").replace("/", "-")
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/resumen-mensual")
def exportar_resumen_mensual(
    meses: int = Query(6, ge=1, le=24, description="Número de meses"),
    eps: str = Query(None, description="Filtrar por EPS"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Exporta resumen de tendencias mensuales a Excel.
    
    Requiere autenticación JWT.
    """
    if not EXCEL_DISPONIBLE:
        return {"error": " openpyxl no instalado. Ejecute: pip install openpyxl"}
    
    repo = GlosaRepository(db)
    tendencias = repo.tendencias_mensuales(meses=meses)
    
    exportador = ExcelExporter()
    output = exportador.generar_resumen_mensual(
        tendencias=tendencias,
        eps=eps or "TODAS",
    )
    
    filename = f"resumen_mensual_hus_{eps or 'todos'}.xlsx"
    filename = filename.replace(" ", "_")
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
