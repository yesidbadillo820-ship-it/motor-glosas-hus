from typing import List
from abc import ABC, abstractmethod
from app.domain.value_objects import ResultadoRegla, ScoringInput, ScoringOutput, InfoTemporal, WorkflowTransition


class ReglaGlosa(ABC):
    @abstractmethod
    def evaluar(self, contexto: dict) -> ResultadoRegla:
        pass

    @property
    @abstractmethod
    def nombre(self) -> str:
        pass


class ReglaExtemporaneidad(ReglaGlosa):
    @property
    def nombre(self) -> str:
        return "ReglaExtemporaneidad"

    def evaluar(self, contexto: dict) -> ResultadoRegla:
        dias_habiles = contexto.get("dias_habiles", 0)
        limite = contexto.get("dias_limite", 20)
        
        if dias_habiles > limite:
            return ResultadoRegla(
                aplico=True,
                codigo="RE9502",
                descripcion="GLOSA EXTEMPORÁNEA",
                gravedad="alta",
                mensaje=f"La glosa fue radicada fuera de los {limite} días hábiles permitidos"
            )
        return ResultadoRegla(aplico=False, codigo="", descripcion="", gravedad="baja")


class ReglaRatificacion(ReglaGlosa):
    @property
    def nombre(self) -> str:
        return "ReglaRatificacion"

    def evaluar(self, contexto: dict) -> ResultadoRegla:
        es_ratificacion = contexto.get("es_ratificacion", False)
        
        if es_ratificacion:
            return ResultadoRegla(
                aplico=True,
                codigo="RE9901",
                descripcion="GLOSA DE RATIFICACIÓN",
                gravedad="media",
                mensaje="Glosa en etapa de ratificación - revisar documentación"
            )
        return ResultadoRegla(aplico=False, codigo="", descripcion="", gravedad="baja")


class ReglaValorMinimo(ReglaGlosa):
    @property
    def nombre(self) -> str:
        return "ReglaValorMinimo"

    def evaluar(self, contexto: dict) -> ResultadoRegla:
        valor = contexto.get("valor_objetado", 0)
        
        if valor < 50000:
            return ResultadoRegla(
                aplico=True,
                codigo="RE9501",
                descripcion="VALOR MÍNIMO",
                gravedad="baja",
                mensaje="Valor menor a $50,000 - evaluar priorización"
            )
        return ResultadoRegla(aplico=False, codigo="", descripcion="", gravedad="baja")


class ReglaCobertura(ReglaGlosa):
    @property
    def nombre(self) -> str:
        return "ReglaCobertura"

    def evaluar(self, contexto: dict) -> ResultadoRegla:
        cobertura_eps = contexto.get("cobertura_eps", True)
        
        if not cobertura_eps:
            return ResultadoRegla(
                aplico=True,
                codigo="RE9603",
                descripcion="SIN COBERTURA CONTRACTUAL",
                gravedad="alta",
                mensaje="La EPS no tiene cobertura para este servicio"
            )
        return ResultadoRegla(aplico=False, codigo="", descripcion="", gravedad="baja")


class MotorReglas:
    def __init__(self, reglas: List[ReglaGlosa] = None):
        self.reglas = reglas or [
            ReglaExtemporaneidad(),
            ReglaRatificacion(),
            ReglaValorMinimo(),
            ReglaCobertura(),
        ]

    def evaluar(self, contexto: dict) -> List[ResultadoRegla]:
        resultados = []
        for regla in self.reglas:
            resultado = regla.evaluar(contexto)
            if resultado.aplico:
                resultados.append(resultado)
        return resultados

    def obtener_codigo_principal(self, resultados: List[ResultadoRegla]) -> str:
        if not resultados:
            return "RE9602"
        
        for r in resultados:
            if r.gravedad == "alta":
                return r.codigo
        return resultados[0].codigo


class ServicioScoring:
    def __init__(self):
        self.peso_valor = 30
        self.peso_probabilidad = 40
        self.peso_urgencia = 30

    def calcular(self, input: ScoringInput) -> ScoringOutput:
        valor_recuperable = input.valor_objetado - input.valor_aceptado
        
        if input.es_extemporanea:
            return ScoringOutput(
                score_total=0,
                prioridad="SIN_ACCION",
                valor_recuperable=0,
                sugerencia_accion="GLOSA EXTEMPORÁNEA - NO PROCEDE"
            )
        
        score_valor = min(100, (valor_recuperable / 1000000)) * self.peso_valor if valor_recuperable > 0 else 0
        score_prob = input.probabilidad_recuperacion * self.peso_probabilidad
        
        dias_vencido = max(0, -input.dias_restantes)
        score_urgencia = max(0, (30 - dias_vencido) / 30) * self.peso_urgencia
        
        score_total = int(score_valor + score_prob + score_urgencia)
        score_total = min(100, max(0, score_total))
        
        if score_total >= 70:
            prioridad = "ALTA"
        elif score_total >= 40:
            prioridad = "MEDIA"
        else:
            prioridad = "BAJA"
        
        return ScoringOutput(
            score_total=score_total,
            prioridad=prioridad,
            valor_recuperable=valor_recuperable,
            sugerencia_accion=f"Prioridad {prioridad} - Score: {score_total}"
        )


class ServicioTemporal:
    FERIADOS_CO = [
        "2025-01-01","2025-01-06","2025-03-24","2025-04-17","2025-04-18",
        "2025-05-01","2025-06-02","2025-06-23","2025-06-30","2025-07-20",
        "2025-08-07","2025-08-18","2025-10-13","2025-11-03","2025-11-17",
        "2025-12-08","2025-12-25",
        "2026-01-01","2026-01-12","2026-03-23","2026-04-02","2026-04-03",
        "2026-05-01","2026-05-18","2026-06-08","2026-06-15","2026-06-29",
        "2026-07-20","2026-08-07","2026-08-17","2026-10-12","2026-11-02",
        "2026-11-16","2026-12-08","2026-12-25",
    ]

    @staticmethod
    def calcular_dias_habiles(fecha_radicacion: str, fecha_recepcion: str, limite: int = 20) -> InfoTemporal:
        from datetime import datetime, timedelta
        
        try:
            d1 = datetime.strptime(fecha_radicacion[:10], "%Y-%m-%d")
            d2 = datetime.strptime(fecha_recepcion[:10], "%Y-%m-%d")
            
            dias, curr = 0, d1
            while curr < d2:
                curr += timedelta(days=1)
                if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in ServicioTemporal.FERIADOS_CO:
                    dias += 1
            
            es_extemporanea = dias > limite
            dias_restantes = max(0, limite - dias)
            esta_vencida = dias > limite
            
            if es_extemporanea:
                mensaje = f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES)"
                color = "bg-red-600"
            else:
                mensaje = f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)"
                color = "bg-emerald-500"
            
            return InfoTemporal(
                dias_habiles=dias,
                es_extemporanea=es_extemporanea,
                dias_restantes=dias_restantes,
                esta_vencida=esta_vencida,
                mensaje_estado=mensaje,
                color_estado=color
            )
        except Exception:
            return InfoTemporal(
                dias_habiles=0,
                es_extemporanea=False,
                dias_restantes=limite,
                esta_vencida=False,
                mensaje_estado="Fechas no ingresadas",
                color_estado="bg-slate-500"
            )


class WorkflowEngine:
    TRANSICIONES = {
        "RADICADA": ["EN_REVISION"],
        "EN_REVISION": ["RESPONDIDA", "RADICADA"],
        "RESPONDIDA": ["ACEPTADA", "RECHAZADA", "EN_REVISION"],
        "ACEPTADA": ["CERRADA"],
        "RECHAZADA": ["CERRADA"],
        "CERRADA": [],
    }

    @classmethod
    def puede_transicionar(cls, desde: str, hacia: str) -> bool:
        return hacia in cls.TRANSICIONES.get(desde, [])

    @classmethod
    def validar_transicion(cls, desde: str, hacia: str) -> WorkflowTransition:
        valida = cls.puede_transicionar(desde, hacia)
        return WorkflowTransition(
            desde=desde,
            hacia=hacia,
            valida=valida,
            mensaje="Transición válida" if valida else f"No se permite {desde} -> {hacia}"
        )