"""Cuánto tiempo lleva una cuenta desde el egreso, y si ya se pasó del plazo.

POR QUÉ EXISTE (08-09-2026, pedido de Yesid). Las cuentas que van al ADRES
tienen un plazo para radicarse contado **desde el egreso del paciente**. Si
se pasa, la cuenta se pierde: el ADRES la rechaza y el hospital deja de
cobrar lo que ya gastó. Hasta ahora eso se vigilaba a ojo, factura por
factura. Este módulo lo calcula.

CÓMO SE CUENTAN LOS MESES — y por qué NO se cuentan en días hábiles.

El plazo está expresado en MESES. Un plazo en meses se cuenta por el
calendario común, completo, sin descontar sábados, domingos ni festivos;
los días hábiles solo entran cuando el plazo está expresado en días. Por eso
la fecha de corte de los 18 meses **no se mueve** por los festivos: si el
egreso fue el 15 de marzo, el corte es el 15 de septiembre del año
siguiente, así ese día sea domingo o Semana Santa.

La regla fina, que es donde se equivocan las cuentas hechas a mano: cuando
el mes de destino tiene menos días que el de origen, el plazo vence el
ÚLTIMO día del mes de destino. Un egreso del 31 de agosto vence el 28 (o 29)
de febrero, no el 3 de marzo. Es la regla común de cómputo de plazos del
Código Civil (art. 67) y es la que aplica `sumar_meses`.

DÓNDE SÍ ENTRAN LOS FESTIVOS. En dos cosas, y las dos importan:

  · Si la fecha de corte cae en sábado, domingo o festivo, ese día **no se
    puede radicar**. El último día útil real es el siguiente hábil, y eso es
    lo que el sistema muestra como fecha límite para trabajar.
  · Para saber cuántos días de trabajo quedan de verdad: «faltan 40 días»
    puede ser «faltan 26 días hábiles». Es el número con el que el auditor
    prioriza.

EL PLAZO ES UN PARÁMETRO, NO UNA VERDAD DE ESTE MÓDULO. Aquí no se cita
ninguna norma: el hospital fija en cuántos meses vence (hoy 18) y el módulo
cuenta. La norma que sustente el término va en la respuesta que escribe el
gestor, no inventada por el sistema.

No toca la red ni la base de datos: fechas entran, dictamen sale.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Optional

from app.services.festivos_colombia import dias_habiles_entre, es_habil, siguiente_habil

# Meses de plazo para radicar ante el ADRES contados desde el egreso.
# Lo fija el hospital; el módulo solo cuenta. 08-09-2026: 18 meses.
MESES_PLAZO_ADRES = 18

# A partir de cuántos días para el vencimiento la cuenta se considera «en
# riesgo». Un mes de anticipación es lo que alcanza para pedir soportes,
# corregir y volver a radicar.
DIAS_ALERTA_TEMPRANA = 30

# Los tres estados posibles. No hay más.
VIGENTE = "VIGENTE"
POR_VENCER = "POR_VENCER"
PRESCRITA = "PRESCRITA"


def sumar_meses(f: date, meses: int) -> date:
    """Suma meses de calendario respetando los meses cortos.

    31 de agosto + 6 meses = 28 (o 29) de febrero, nunca el 3 de marzo.
    """
    total = f.month - 1 + meses
    anio = f.year + total // 12
    mes = total % 12 + 1
    return date(anio, mes, min(f.day, calendar.monthrange(anio, mes)[1]))


def meses_completos_entre(desde: date, hasta: date) -> int:
    """Meses enteros transcurridos entre las dos fechas (0 si va al revés)."""
    if hasta <= desde:
        return 0
    meses = (hasta.year - desde.year) * 12 + (hasta.month - desde.month)
    if hasta.day < min(desde.day, calendar.monthrange(hasta.year, hasta.month)[1]):
        meses -= 1
    return max(0, meses)


@dataclass(frozen=True)
class Prescripcion:
    """El dictamen de tiempo de una cuenta. Todo en fechas, sin ambigüedad."""

    fecha_egreso: date
    fecha_corte: date  # el día que vence el plazo, por calendario
    fecha_limite_habil: date  # el último día en que de verdad se puede radicar
    estado: str  # VIGENTE | POR_VENCER | PRESCRITA
    prescrita: bool
    meses_plazo: int
    meses_transcurridos: int
    dias_restantes: int  # negativo si ya venció
    dias_habiles_restantes: int  # 0 si ya venció
    dias_vencida: int  # 0 si no ha vencido
    evaluada_el: date

    @property
    def resumen(self) -> str:
        """Una línea en cristiano para la pantalla y el oficio."""
        if self.prescrita:
            return (
                f"Prescrita: el egreso fue el {_dmy(self.fecha_egreso)} y el plazo de "
                f"{self.meses_plazo} meses venció el {_dmy(self.fecha_corte)}, "
                f"hace {self.dias_vencida} días."
            )
        if self.estado == POR_VENCER:
            return (
                f"Por vencer: quedan {self.dias_restantes} días "
                f"({self.dias_habiles_restantes} hábiles). Último día para radicar: "
                f"{_dmy(self.fecha_limite_habil)}."
            )
        return (
            f"Vigente: vence el {_dmy(self.fecha_corte)}; quedan {self.dias_restantes} "
            f"días ({self.dias_habiles_restantes} hábiles)."
        )

    def a_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, date):
                d[k] = v.isoformat()
        d["resumen"] = self.resumen
        return d


def _dmy(f: date) -> str:
    return f.strftime("%d/%m/%Y")


def _a_fecha(valor: Any) -> Optional[date]:
    """Acepta date, datetime o texto ISO. Lo que no entienda, lo devuelve None."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    texto = texto.replace("T", " ").split(" ")[0]
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def evaluar(
    fecha_egreso: Any,
    hoy: Optional[date] = None,
    meses_plazo: int = MESES_PLAZO_ADRES,
    dias_alerta: int = DIAS_ALERTA_TEMPRANA,
) -> Optional[Prescripcion]:
    """El dictamen de tiempo de una cuenta, o None si no hay con qué contar.

    `hoy` es obligatorio en la práctica (se pasa siempre desde el servicio,
    para que la prueba pueda fijar el día); si no viene, se toma la fecha
    del sistema.

    Devuelve None cuando la fecha de egreso no se entiende o es futura: sin
    egreso cierto no se dictamina, no se supone. Es la regla de la casa —
    antes que marcar una prescripción falsa, callarse.
    """
    egreso = _a_fecha(fecha_egreso)
    if egreso is None:
        return None
    dia = hoy or date.today()
    if egreso > dia:
        # Un egreso en el futuro es un dato malo, no una cuenta vigente.
        return None
    if meses_plazo <= 0:
        raise ValueError("el plazo en meses tiene que ser mayor que cero")

    corte = sumar_meses(egreso, meses_plazo)
    limite_habil = corte if es_habil(corte) else siguiente_habil(corte)

    dias_restantes = (corte - dia).days
    vencida = dia > limite_habil

    if vencida:
        estado = PRESCRITA
    elif dias_restantes <= dias_alerta:
        estado = POR_VENCER
    else:
        estado = VIGENTE

    return Prescripcion(
        fecha_egreso=egreso,
        fecha_corte=corte,
        fecha_limite_habil=limite_habil,
        estado=estado,
        prescrita=vencida,
        meses_plazo=meses_plazo,
        meses_transcurridos=meses_completos_entre(egreso, dia),
        dias_restantes=dias_restantes,
        dias_habiles_restantes=0 if vencida else dias_habiles_entre(dia, limite_habil),
        dias_vencida=max(0, (dia - limite_habil).days) if vencida else 0,
        evaluada_el=dia,
    )
