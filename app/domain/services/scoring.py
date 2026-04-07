from dataclasses import dataclass
from app.domain.entities.glosa import Glosa


@dataclass
class Score:
    total: int
    componentes: dict


class ScoringService:
    def __init__(
        self,
        peso_valor: float = 0.4,
        peso_recuperabilidad: float = 0.3,
        peso_urgencia: float = 0.3,
    ):
        self.peso_valor = peso_valor
        self.peso_recuperabilidad = peso_recuperabilidad
        self.peso_urgencia = peso_urgencia

    def calcular(self, glosa: Glosa) -> Score:
        score_valor = self._score_valor(glosa.valor_objetado)
        score_recup = self._score_recuperabilidad(glosa)
        score_urgencia = self._score_urgencia(glosa.dias_restantes)

        total = int(
            score_valor * self.peso_valor
            + score_recup * self.peso_recuperabilidad
            + score_urgencia * self.peso_urgencia
        )

        return Score(
            total=min(100, max(0, total)),
            componentes={
                "valor": score_valor,
                "recuperabilidad": score_recup,
                "urgencia": score_urgencia,
            }
        )

    def _score_valor(self, valor: float) -> int:
        if valor >= 10_000_000:
            return 100
        elif valor >= 5_000_000:
            return 80
        elif valor >= 1_000_000:
            return 60
        elif valor >= 500_000:
            return 40
        elif valor >= 100_000:
            return 20
        return 10

    def _score_recuperabilidad(self, glosa: Glosa) -> int:
        if glosa.valor_objetado == 0:
            return 50
        ratio = glosa.valor_aceptado / glosa.valor_objetado
        return int(ratio * 100)

    def _score_urgencia(self, dias: int) -> int:
        if dias <= 0:
            return 100
        elif dias <= 3:
            return 80
        elif dias <= 7:
            return 60
        elif dias <= 15:
            return 40
        elif dias <= 30:
            return 20
        return 10


SCORING_DEFAULT = ScoringService()