import logging
from typing import Optional, List
from datetime import datetime

from app.domain.services import WorkflowEngine, WorkflowTransition
from app.infrastructure.repositories import GlosaRepository
from app.infrastructure.db.models import GlosaRecord

logger = logging.getLogger("gestionar_glosa_use_case")


class GestionarGlosaUseCase:
    def __init__(self, glosa_repo: GlosaRepository):
        self.glosa_repo = glosa_repo

    def cambiar_estado(
        self,
        glosa_id: int,
        nuevo_estado: str,
        usuario_id: Optional[int] = None,
        observacion: Optional[str] = None,
    ) -> Optional[GlosaRecord]:
        glosa = self.glosa_repo.obtener_por_id(glosa_id)
        if not glosa:
            logger.warning(f"Glosa {glosa_id} no encontrada")
            return None
        
        transicion = WorkflowEngine.validar_transicion(glosa.estado, nuevo_estado)
        
        if not transicion.valida:
            logger.warning(f"Transición inválida: {glosa.estado} -> {nuevo_estado}")
            raise ValueError(transicion.mensaje)
        
        glosa = self.glosa_repo.actualizar_estado(
            glosa_id, nuevo_estado, usuario_id, observacion
        )
        
        logger.info(f"Glosa {glosa_id} transitó de {transicion.desde} a {transicion.hacia}")
        return glosa

    def asignar_responsable(
        self,
        glosa_id: int,
        responsable_id: int,
    ) -> Optional[GlosaRecord]:
        return self.glosa_repo.actualizar(glosa_id, responsable_id=responsable_id)

    def listar_por_estado(self, estado: str, limit: int = 50) -> List[GlosaRecord]:
        return self.glosa_repo.listar(estado=estado, limit=limit)

    def listar_por_prioridad(self, prioridad: str, limit: int = 50) -> List[GlosaRecord]:
        return self.glosa_repo.listar(limit=limit)

    def obtener_estadisticas(self, eps: Optional[str] = None) -> dict:
        return self.glosa_repo.estadisticas(eps)