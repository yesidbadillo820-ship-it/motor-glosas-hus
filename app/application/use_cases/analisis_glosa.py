from dataclasses import dataclass
from typing import Optional, Dict
from app.domain.entities.glosa import Glosa
from app.domain.services.motor_reglas import MotorReglas, MOTOR_DEFAULT
from app.domain.services.scoring import ScoringService, SCORING_DEFAULT
from app.models.schemas import GlosaInput, GlosaResult


@dataclass
class ResultadoAnalisis:
    glosa: Glosa
    resultado_ia: GlosaResult
    reglas_aplicadas: list


class AnalisisGlosaUseCase:
    def __init__(
        self,
        motor_reglas: Optional[MotorReglas] = None,
        scoring: Optional[ScoringService] = None,
    ):
        self.motor_reglas = motor_reglas or MOTOR_DEFAULT
        self.scoring = scoring or SCORING_DEFAULT

    async def ejecutar(
        self,
        entrada: GlosaInput,
        contexto_pdf: str = "",
        contratos: Dict[str, str] = None,
    ) -> ResultadoAnalisis:
        from app.services.glosa_service import GlosaService
        from app.core.config import get_settings
        
        cfg = get_settings()
        servicio = GlosaService(
            groq_api_key=cfg.groq_api_key,
            anthropic_api_key=cfg.anthropic_api_key,
        )
        
        resultado_ia = await servicio.analizar(entrada, contexto_pdf, contratos)
        
        glosa = Glosa(
            eps=entrada.eps,
            codigo_glosa=resultado_ia.codigo_glosa,
            paciente=resultado_ia.paciente,
            valor_objetado=resultado_ia.valor_objetado,
            etapa=entrada.etapa,
            dictamen=resultado_ia.dictamen,
            dias_restantes=resultado_ia.dias_restantes,
            modelo_ia=resultado_ia.modelo_ia,
            fecha_radicacion=entrada.fecha_radicacion,
            fecha_recepcion=entrada.fecha_recepcion,
        )
        
        glosa.score = self.scoring.calcular(glosa).total
        
        reglas = self.motor_reglas.evaluar(glosa)
        
        return ResultadoAnalisis(
            glosa=glosa,
            resultado_ia=resultado_ia,
            reglas_aplicadas=reglas,
        )