from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class RespuestaGlosa:
    id: Optional[int] = None
    glosa_id: int = 0
    resumen: str = ""
    dictamen: str = ""
    tipo: str = ""
    codigo_glosa: str = ""
    valor_objetado: str = ""
    paciente: str = ""
    modelo_ia: Optional[str] = None
    creado_en: Optional[datetime] = None