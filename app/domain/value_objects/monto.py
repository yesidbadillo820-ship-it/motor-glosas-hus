from dataclasses import dataclass
from decimal import Decimal
import re


@dataclass(frozen=True)
class Monto:
    valor: Decimal

    @classmethod
    def desde_string(cls, valor_str: str) -> "Monto":
        cleaned = re.sub(r"[^\d]", "", valor_str or "")
        return cls(Decimal(cleaned or "0"))

    @property
    def es_cero(self) -> bool:
        return self.valor == 0

    @property
    def es_alto(self) -> bool:
        return self.valor >= 1_000_000

    @property
    def es_bajo(self) -> bool:
        return self.valor <= 100_000

    def __str__(self) -> str:
        return f"${self.valor:,.0f}".replace(",", ".")

    def __float__(self) -> float:
        return float(self.valor)