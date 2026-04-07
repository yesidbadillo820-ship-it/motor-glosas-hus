from dataclasses import dataclass
from enum import Enum


class CausaGlosa(str, Enum):
    TARIFA_INCORRECTA = "tarifa_incorrecta"
    SERVICIO_NO_AUTORIZADO = "servicio_no_autorizado"
    COBERTURA_NO_CONTRATADA = "cobertura_no_contratada"
    DEMASIA_POSICIONES = "demasia_posiciones"
    INCUMPLIMIENTO_TECNICO = "incumplimiento_tecnico"
    DUPLICIDAD = "duplicidad"
    EXTEMPORANEA = "extemporanea"
    CODIGO_NO_CUBIERTO = "codigo_no_cubierto"
    PRESENTACION_INADECUADA = "presentacion_inadecuada"
    OTRA = "otra"

    @property
    def recuperable(self) -> bool:
        return self not in [
            CausaGlosa.EXTEMPORANEA,
            CausaGlosa.DUPLICIDAD,
            CausaGlosa.COBERTURA_NO_CONTRATADA,
        ]

    @property
    def necesita_justificacion(self) -> bool:
        return self in [
            CausaGlosa.TARIFA_INCORRECTA,
            CausaGlosa.SERVICIO_NO_AUTORIZADO,
            CausaGlosa.INCUMPLIMIENTO_TECNICO,
        ]