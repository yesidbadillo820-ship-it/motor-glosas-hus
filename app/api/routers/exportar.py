from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.glosa_repository import GlosaRepository
from app.services.excel_service import ExcelExporter, EXCEL_DISPONIBLE
from app.services.exportar_gerencial import generar_reporte_gerencial
from app.services.exportar_dgh import generar_excel_dgh
from app.api.deps import get_usuario_actual, get_coordinador_o_admin
from app.models.db import UsuarioRecord, GlosaRecord

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


@router.get("/gerencial")
def exportar_reporte_gerencial(
    periodo: str = Query("semana", pattern="^(dia|semana|mes)$"),
    ventana_anomalias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Export Excel gerencial multi-hoja (Ronda 24).

    Hojas: Resumen · Top EPS · Autopilot · Anomalías.
    Solo coordinador / super_admin. Diseñado para Comité de Cartera.
    """
    if not EXCEL_DISPONIBLE:
        return {"error": "openpyxl no instalado. Ejecute: pip install openpyxl"}
    output = generar_reporte_gerencial(db, periodo=periodo, ventana_anomalias_dias=ventana_anomalias)
    filename = f"reporte_gerencial_hus_{periodo}_{__import__('datetime').date.today().isoformat()}.xlsx"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dgh")
def exportar_formato_dgh(
    eps: str = Query(None, description="Filtrar por EPS (substring match)"),
    estado: str = Query(None, description="Filtrar por estado (RESPONDIDA, RATIFICADA, etc.)"),
    desde: str = Query(None, description="Fecha desde YYYY-MM-DD (creado_en)"),
    hasta: str = Query(None, description="Fecha hasta YYYY-MM-DD"),
    solo_respondidas: bool = Query(True, description="Solo glosas ya respondidas"),
    limit: int = Query(5000, ge=1, le=20000),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Export Excel en formato DGH listo para recargar al sistema (Ronda 35).

    Estructura EXACTA de 26 columnas con encabezados canónicos DGH:
      EstadoCxCObjecion · TipoObjecionTramite · FacturaCartera.Factura · ...
      + 4 columnas HUS: FECHA DE CARGUE · CODIGO RESPUESTA · VALOR ACEPTADO · OBSERVACION

    Una fila por CONCEPTO (si la glosa tiene múltiples CUPS, una fila cada una).
    La columna OBSERVACION contiene el dictamen LIMPIO: sin emojis, sin headers
    de debug, respetando el texto canónico de RATIFICADA / EXTEMPORÁNEA.
    """
    if not EXCEL_DISPONIBLE:
        return {"error": "openpyxl no instalado. Ejecute: pip install openpyxl"}

    from datetime import datetime as _dt
    q = db.query(GlosaRecord)
    if eps:
        q = q.filter(GlosaRecord.eps.ilike(f"%{eps}%"))
    if estado:
        q = q.filter(GlosaRecord.estado == estado.upper())
    if solo_respondidas:
        # Respondidas vía workflow o estado
        from sqlalchemy import or_
        q = q.filter(
            or_(
                GlosaRecord.workflow_state == "RESPONDIDA",
                GlosaRecord.estado == "RESPONDIDA",
                GlosaRecord.dictamen.isnot(None),
            )
        )
    if desde:
        try:
            dd = _dt.fromisoformat(desde)
            q = q.filter(GlosaRecord.creado_en >= dd)
        except Exception:
            pass
    if hasta:
        try:
            dh = _dt.fromisoformat(hasta)
            q = q.filter(GlosaRecord.creado_en <= dh)
        except Exception:
            pass

    glosas = q.order_by(GlosaRecord.id.desc()).limit(limit).all()
    output = generar_excel_dgh(db, glosas)
    fecha = _dt.now().strftime("%Y%m%d")
    filename = f"glosas_dgh_{fecha}.xlsx"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
