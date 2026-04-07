from dataclasses import dataclass
from typing import Optional, List
from app.domain.entities.glosa import Glosa, EstadoGlosa
from app.domain.services.workflow import WorkflowService, WORKFLOW_SERVICE_DEFAULT, Estado, Transicion


@dataclass
class ResultadoWorkflow:
    glosa_id: int
    estado_anterior: str
    estado_nuevo: str
    transicion: Transicion
    valida: bool
    mensaje: str


class GestionWorkflowUseCase:
    def __init__(self, workflow: Optional[WorkflowService] = None):
        self.workflow = workflow or WORKFLOW_SERVICE_DEFAULT

    def obtener_estados(self) -> List[Estado]:
        return list(Estado)

    def obtener_transiciones(self, estado_actual: str) -> List[Transicion]:
        try:
            estado = Estado(estado_actual.upper())
            return self.workflow.obtener_transiciones(estado)
        except ValueError:
            return []

    def cambiar_estado(
        self,
        glosa_id: int,
        estado_actual: str,
        estado_nuevo: str,
        usuario_id: Optional[int] = None,
    ) -> ResultadoWorkflow:
        try:
            desde = Estado(estado_actual.upper())
            hacia = Estado(estado_nuevo.upper())
        except ValueError as e:
            return ResultadoWorkflow(
                glosa_id=glosa_id,
                estado_anterior=estado_actual,
                estado_nuevo=estado_nuevo,
                transicion=None,
                valida=False,
                mensaje=f"Estado inválido: {e}",
            )

        validacion = self.workflow.puede_transicionar(desde, hacia)
        
        if not validacion.valida:
            return ResultadoWorkflow(
                glosa_id=glosa_id,
                estado_anterior=estado_actual,
                estado_nuevo=estado_nuevo,
                transicion=None,
                valida=False,
                mensaje=validacion.mensaje,
            )

        transiciones = self.workflow.obtener_transiciones(desde)
        transicion_encontrada = next(
            (t for t in transiciones if t.hacia == hacia), None
        )

        if transicion_encontrada and transicion_encontrada.requiere_usuario and not usuario_id:
            return ResultadoWorkflow(
                glosa_id=glosa_id,
                estado_anterior=estado_actual,
                estado_nuevo=estado_nuevo,
                transicion=transicion_encontrada,
                valida=False,
                mensaje="Esta transición requiere un usuario responsable",
            )

        self._actualizar_estado_db(glosa_id, estado_nuevo)

        return ResultadoWorkflow(
            glosa_id=glosa_id,
            estado_anterior=estado_actual,
            estado_nuevo=estado_nuevo,
            transicion=transicion_encontrada,
            valida=True,
            mensaje=validacion.mensaje,
        )

    def _actualizar_estado_db(self, glosa_id: int, nuevo_estado: str):
        from app.database import SessionLocal
        from app.models.db import GlosaRecord
        from sqlalchemy import update

        db = SessionLocal()
        try:
            stmt = update(GlosaRecord).where(GlosaRecord.id == glosa_id).values(estado=nuevo_estado)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    def obtener_sla(self, desde: str, hacia: str) -> Optional[int]:
        try:
            return self.workflow.obtener_sla(Estado(desde.upper()), Estado(hacia.upper()))
        except ValueError:
            return None