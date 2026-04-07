from fastapi import BackgroundTasks, APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import asyncio

from app.api.deps import get_usuario_actual, get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.services.pdf_service import PdfService
from app.core.observability import observability, metrics

router = APIRouter(prefix="/async", tags=["async"])


TASKS_STORAGE = {}


async def generar_pdf_async(
    glosa_id: int,
    eps: str,
    resumen: str,
    dictamen: str,
    codigo: str,
    valor: str,
    db_session
):
    task_id = str(uuid.uuid4())
    
    TASKS_STORAGE[task_id] = {"status": "processing", "progress": 0}
    
    try:
        TASKS_STORAGE[task_id]["progress"] = 20
        observability.log_info(f"Iniciando generación PDF async glosa {glosa_id}", glosa_id=glosa_id)
        
        pdf_service = PdfService()
        
        TASKS_STORAGE[task_id]["progress"] = 50
        pdf_path = await pdf_service.generar(
            eps=eps,
            resumen=resumen,
            dictamen=dictamen,
            codigo=codigo,
            valor=valor
        )
        
        TASKS_STORAGE[task_id]["progress"] = 90
        TASKS_STORAGE[task_id] = {
            "status": "completed",
            "progress": 100,
            "file_path": pdf_path,
            "glosa_id": glosa_id
        }
        
        metrics.increment("pdfs_generados")
        observability.log_info(f"PDF generado async glosa {glosa_id}", glosa_id=glosa_id, task_id=task_id)
        
    except Exception as e:
        TASKS_STORAGE[task_id] = {
            "status": "failed",
            "progress": 0,
            "error": str(e)
        }
        observability.log_error(f"Error generando PDF async glosa {glosa_id}", exception=e, glosa_id=glosa_id)
        metrics.increment("pdfs_fallidos")


async def analizar_masivo_async(
    lista_glosas: list,
    db_session,
    usuario_id: int
):
    task_id = str(uuid.uuid4())
    
    TASKS_STORAGE[task_id] = {
        "status": "processing",
        "progress": 0,
        "total": len(lista_glosas),
        "actual": 0
    }
    
    try:
        from app.services.glosa_service import GlosaService
        from app.core.config import get_settings
        
        settings = get_settings()
        service = GlosaService(
            groq_api_key=settings.groq_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )
        
        results = []
        
        for idx, glosa_data in enumerate(lista_glosas):
            TASKS_STORAGE[task_id]["actual"] = idx + 1
            TASKS_STORAGE[task_id]["progress"] = int((idx + 1) / len(lista_glosas) * 100)
            
            try:
                from app.models.schemas import GlosaInput
                
                data = GlosaInput(
                    eps=glosa_data["eps"],
                    etapa=glosa_data["etapa"],
                    fecha_radicacion=glosa_data.get("fecha_radicacion"),
                    fecha_recepcion=glosa_data.get("fecha_recepcion"),
                    valor_aceptado=glosa_data.get("valor_aceptado", "0"),
                    tabla_excel=glosa_data["tabla_excel"],
                )
                
                resultado = await service.analizar(data, "", {})
                results.append({"glosa_idx": idx, "result": resultado.dict(), "success": True})
                
            except Exception as e:
                results.append({"glosa_idx": idx, "error": str(e), "success": False})
        
        TASKS_STORAGE[task_id] = {
            "status": "completed",
            "progress": 100,
            "results": results,
            "total_procesados": len(results),
            "exitosos": sum(1 for r in results if r.get("success"))
        }
        
        metrics.increment("analisis_masivos_completados")
        
    except Exception as e:
        TASKS_STORAGE[task_id] = {
            "status": "failed",
            "error": str(e)
        }
        observability.log_error("Error en análisis masivo", exception=e)


@router.post("/generar-pdf/{glosa_id}")
async def generar_pdf(
    glosa_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    background_tasks.add_task(
        generar_pdf_async,
        glosa_id=glosa_id,
        eps=glosa.eps,
        resumen=glosa.paciente,
        dictamen=glosa.dictamen or "",
        codigo=glosa.codigo_glosa or "N/A",
        valor=str(glosa.valor_objetado),
        db_session=db
    )
    
    observability.log_info(f"Solicitado PDF async para glosa {glosa_id}", glosa_id=glosa_id)
    
    return {"task_id": glosa_id, "status": "queued", "message": "PDF se generará en segundo plano"}


@router.get("/tarea/{task_id}")
def estado_tarea(task_id: str):
    task = TASKS_STORAGE.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    return {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", 0),
        "result": task.get("file_path") or task.get("results"),
        "error": task.get("error")
    }


@router.post("/analisis-masivo")
async def analisis_masivo(
    glosas: list,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    if not glosas:
        raise HTTPException(status_code=400, detail="Lista de glosas vacía")
    
    if len(glosas) > 100:
        raise HTTPException(status_code=400, detail="Máximo 100 glosas por lote")
    
    task_id = str(uuid.uuid4())
    
    background_tasks.add_task(
        analizar_masivo_async,
        lista_glosas=glosas,
        db_session=db,
        usuario_id=usuario.id
    )
    
    observability.log_info(f"Iniciado análisis masivo de {len(glosas)} glosas", usuario_id=usuario.id)
    
    return {
        "task_id": task_id,
        "status": "queued",
        "total": len(glosas),
        "message": "Análisis masivo en segundo plano"
    }


@router.get("/metricas")
def obtener_metricas():
    return metrics.get_all()