from dataclasses import dataclass
from typing import Optional, Dict
from app.domain.entities.glosa import Glosa
from app.domain.entities.respuesta import RespuestaGlosa
from app.domain.services.motor_reglas import MotorReglas


@dataclass
class ResultadoRespuesta:
    respuesta: RespuestaGlosa
    pdf_bytes: Optional[bytes]
    exito: bool
    mensaje: str


class GeneracionRespuestaUseCase:
    def __init__(
        self,
        repositorio=None,
        motor_reglas: Optional[MotorReglas] = None,
    ):
        self.repositorio = repositorio
        self.motor_reglas = motor_reglas

    async def ejecutar(
        self,
        glosa: Glosa,
        generar_pdf: bool = True,
    ) -> ResultadoRespuesta:
        from app.services.pdf_service import PDFService
        from app.application.use_cases.registro_glosa import RegistroGlosaUseCase
        
        regs = RegistroGlosaUseCase()
        resultado = regs.ejecutar(glosa)
        
        respuesta = RespuestaGlosa(
            glosa_id=resultado.glosa_id,
            resumen=glosa.resumen or "DEFENSA: glosa justificada",
            dictamen=glosa.dictamen,
            tipo="RESPUESTA",
            codigo_glosa=glosa.codigo_glosa,
            valor_objetado=str(glosa.valor_objetado),
            paciente=glosa.paciente,
            modelo_ia=glosa.modelo_ia,
        )
        
        pdf_bytes = None
        if generar_pdf:
            try:
                pdf_service = PDFService()
                pdf_bytes = pdf_service.generar(
                    eps=glosa.eps,
                    resumen=respuesta.resumen,
                    dictamen=respuesta.dictamen,
                    codigo=glosa.codigo_glosa,
                    valor=str(glosa.valor_objetado),
                )
            except Exception as e:
                return ResultadoRespuesta(
                    respuesta=respuesta,
                    pdf_bytes=None,
                    exito=False,
                    mensaje=f"Error generando PDF: {str(e)}",
                )
        
        return ResultadoRespuesta(
            respuesta=respuesta,
            pdf_bytes=pdf_bytes,
            exito=True,
            mensaje="Respuesta generada exitosamente",
        )

    def _obtener_plantilla(self, eps: str) -> str:
        plantillas = {
            "COOSALUD": "plantilla_coosalud.txt",
            "COMPENSAR": "plantilla_compensar.txt",
            "NUEVA EPS": "plantilla_nueva_eps.txt",
        }
        return plantillas.get(eps.upper(), "plantilla_default.txt")