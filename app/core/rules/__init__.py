from datetime import datetime, date
from typing import Optional
from app.domain.value_objects import ResultadoRegla, CodigoRespuesta


class ReglaExtemporaneidad:
    """Evalúa si la glosa es extemporánea (más de 20 días hábiles)"""
    
    DIAS_LIMITE = 20
    SEVERIDAD = "critica"
    
    @property
    def nombre(self) -> str:
        return "Extemporaneidad"
    
    @property
    def descripcion(self) -> str:
        return "Verifica si la glosa fue radicada fuera de los términos legales (20 días)"
    
    def evaluar(self, glosa_data: dict) -> ResultadoRegla:
        dias = glosa_data.get("dias_radicacion", 0)
        es_extemporanea = dias > self.DIAS_LIMITE
        
        if es_extemporanea:
            return ResultadoRegla(
                nombre=self.nombre,
                cumple=False,
                mensaje=f"La glosa es EXTEMPORÁNEA ({dias} días hábiles). No procedió en término.",
                severidad=self.SEVERIDAD
            )
        
        return ResultadoRegla(
            nombre=self.nombre,
            cumple=True,
            mensaje=f"La glosa está DENTRO DE TÉRMINOS ({dias} días hábiles).",
            severidad="info"
        )


class ReglaCobertura:
    """Evalúa la cobertura del contrato con la EPS"""
    
    SEVERIDAD = "alta"
    
    @property
    def nombre(self) -> str:
        return "Cobertura Contractual"
    
    @property
    def descripcion(self) -> str:
        return "Verifica que el servicio glosado tenga cobertura contractual"
    
    def evaluar(self, glosa_data: dict) -> ResultadoRegla:
        eps = glosa_data.get("eps", "").upper()
        contrato = glosa_data.get("contrato", "")
        
        eps_excluyentes = ["FAMISANAR", "COMPENSAR", "PRECIMED"]
        
        if eps in eps_excluyentes and "oncolog" in contrato.lower():
            return ResultadoRegla(
                nombre=self.nombre,
                cumple=False,
                mensaje=f"La EPS {eps} excluye servicios oncológicos según contrato.",
                severidad=self.SEVERIDAD
            )
        
        return ResultadoRegla(
            nombre=self.nombre,
            cumple=True,
            mensaje=f"El servicio tiene cobertura con {eps}.",
            severidad="info"
        )


class ReglaValorMinimo:
    """Evalúa si el valor glosado justifica respuesta"""
    
    VALOR_MINIMO = 50000
    SEVERIDAD = "baja"
    
    @property
    def nombre(self) -> str:
        return "Valor Mínimo"
    
    @property
    def descripcion(self) -> str:
        return f"Verifica que el valor glosado sea mayor a ${VALOR_MINIMO:,}"
    
    def evaluar(self, glosa_data: dict) -> ResultadoRegla:
        valor = glosa_data.get("valor_objetado", 0)
        
        if valor < self.VALOR_MINIMO:
            return ResultadoRegla(
                nombre=self.nombre,
                cumple=False,
                mensaje=f"Valor glosado (${valor:,.0f}) menor al mínimo (${self.VALOR_MINIMO:,}). Considere aceptar.",
                severidad=self.SEVERIDAD
            )
        
        return ResultadoRegla(
            nombre=self.nombre,
            cumple=True,
            mensaje=f"Valor glosado justificado: ${valor:,.0f}",
            severidad="info"
        )


class ReglaEtapa:
    """Evalúa la etapa de la glosa (INICIAL, RATIFICACIÓN, RESPUESTA)"""
    
    SEVERIDAD = "media"
    
    @property
    def nombre(self) -> str:
        return "Etapa Válida"
    
    @property
    def descripcion(self) -> str:
        return "Verifica que la etapa corresponda a un flujo válido"
    
    def evaluar(self, glosa_data: dict) -> ResultadoRegla:
        etapa = glosa_data.get("etapa", "").upper()
        etapas_validas = ["INICIAL", "RATIF", "RATIFICACION", "RESPUESTA"]
        
        if etapa not in etapas_validas:
            return ResultadoRegla(
                nombre=self.nombre,
                cumple=False,
                mensaje=f"Etapa '{etapa}' no válida. Debe ser: INICIAL, RATIF o RESPUESTA.",
                severidad=self.SEVERIDAD
            )
        
        return ResultadoRegla(
            nombre=self.nombre,
            cumple=True,
            mensaje=f"Etapa '{etapa}' correcta.",
            severidad="info"
        )


class ReglaVencimiento:
    """Evalúa si la glosa está próxima a vencer"""
    
    DIAS_ALERTA = 5
    SEVERIDAD = "critica"
    
    @property
    def nombre(self) -> str:
        return "Vencimiento Próximo"
    
    @property
    def descripcion(self) -> str:
        return f"Alerta cuando quedan menos de {DIAS_ALERTA} días"
    
    def evaluar(self, glosa_data: dict) -> ResultadoRegla:
        dias = glosa_data.get("dias_restantes", 0)
        
        if dias <= self.DIAS_ALERTA:
            return ResultadoRegla(
                nombre=self.nombre,
                cumple=False,
                mensaje=f"URGENTE: Quedan {dias} días para responder. Priorizar.",
                severidad=self.SEVERIDAD
            )
        
        return ResultadoRegla(
            nombre=self.nombre,
            cumple=True,
            mensaje=f"Tiempo disponible: {dias} días.",
            severidad="info"
        )


def get_motor_reglas() -> list:
    """Retorna lista de reglas padrão del sistema"""
    return [
        ReglaExtemporaneidad(),
        ReglaCobertura(),
        ReglaValorMinimo(),
        ReglaEtapa(),
        ReglaVencimiento(),
    ]