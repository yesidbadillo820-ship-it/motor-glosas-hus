from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_db
from app.models.db import GlosaRecord, UsuarioRecord, ContratoRecord
from app.models.schemas import ReglasResponse, ReglaEvaluacion
from app.core.rules import get_motor_reglas, MotorReglas
from app.core.observability import observability, metrics

router = APIRouter(prefix="/reglas", tags=["reglas"])


@router.get("/evaluar/{glosa_id}", response_model=ReglasResponse)
def evaluar_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    contrato_repo = ContratoRecord(db) if hasattr(db, 'query') else None
    contrato = ""
    if glosa.eps:
        tmp = db.query(ContratoRecord).filter(ContratoRecord.eps == glosa.eps).first()
        if tmp:
            contrato = tmp.detalles
    
    glosa_data = {
        "eps": glosa.eps,
        "valor_objetado": glosa.valor_objetado,
        "dias_radicacion": 0,
        "dias_restantes": glosa.dias_restantes,
        "etapa": glosa.etapa,
        "contrato": contrato,
    }
    
    reglas = get_motor_reglas()
    motor = MotorReglas()
    motor.agregar_reglas(reglas)
    
    resultados = motor.evaluar_todas(glosa_data)
    
    tiene_criticas = motor.tiene_infracciones_criticas(glosa_data)
    
    reglas_respuesta = [
        ReglaEvaluacion(
            nombre=r.nombre,
            cumple=r.cumple,
            mensaje=r.mensaje,
            severidad=r.severidad
        )
        for r in resultados
    ]
    
    observability.log_info(
        f"Evaluadas {len(resultados)} reglas para glosa {glosa_id}",
        glosa_id=glosa_id,
        tiene_criticas=tiene_criticas
    )
    
    return ReglasResponse(
        glosa_id=glosa_id,
        reglas=reglas_respuesta,
        tiene_infracciones_criticas=tiene_criticas
    )


@router.get("/definiciones")
def obtener_definiciones():
    reglas = get_motor_reglas()
    return [
        {
            "nombre": r.nombre,
            "descripcion": r.descripcion,
        }
        for r in reglas
    ]


@router.get("/metricas-reglas")
def metricas_por_regla(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    reglas = get_motor_reglas()
    metricas = {}
    
    for regla in reglas:
        nombre = regla.nombre
        glosas = db.query(GlosaRecord).all()
        
        aplicables = 0
        incumplimientos = 0
        
        for glosa in glosas:
            glosa_data = {
                "eps": glosa.eps,
                "valor_objetado": glosa.valor_objetado,
                "dias_radicacion": 0,
                "dias_restantes": glosa.dias_restantes,
                "etapa": glosa.etapa,
                "contrato": "",
            }
            resultado = regla.evaluar(glosa_data)
            aplicables += 1
            if not resultado.cumple:
                incumplimientos += 1
        
        metricas[nombre] = {
            "aplicables": aplicables,
            "incumplimientos": incumplimientos,
            "tasa_incumplimiento": round(incumplimientos / aplicables * 100, 2) if aplicables > 0 else 0
        }
    
    return metricas