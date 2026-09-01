"""El contrato de salida de la IA: dos campos, y nada más.

01-09-2026 — refactor pedido por el auditor tras el dictamen GL-149:

    «Si el modelo alucina cuentas matemáticas y códigos, es porque le estamos
    dando demasiada libertad de formato. Quítale el control del ensamblaje.»

Tiene razón. Hasta hoy el modelo devolvía un XML con once etiquetas y de ahí
salían cosas que NO son redacción sino datos verificables: qué se facturó
(`<servicio>`), qué contrato rige (`<contrato>`), qué tarifa aplica
(`<tarifa>`). Pedirle esos datos a un modelo generativo y después limpiar lo
que devuelve es hacer el trabajo dos veces y perder una de cada tantas. En
GL-149 se perdió: escribió «EL VALOR FACTURADO DE $18.940.000 ES COMPATIBLE
CON LA UVB VIGENTE», una cuenta que nadie hizo.

Acá el modelo solo entrega lo que sí es su oficio:

  • `justificacion_clinica` — qué dice el expediente y por qué sostiene el
    servicio prestado.
  • `fundamentos_ley` — las normas que amparan esa conducta.

El resto lo arma el motor con f-strings y datos duros: el renglón del servicio
sale del catálogo CUPS, el bloque económico de la malla contractual.

Qué NO resuelve esto, para que quede escrito
────────────────────────────────────────────
El JSON restringe el SOBRE, no el CONTENIDO de un campo de texto. Dentro de
`justificacion_clinica` el modelo puede seguir escribiendo «código CL4506» o
inventar una cifra — en GL-149 lo hizo en el cuerpo del argumento, no solo en
el campo del servicio. Por eso las redes de limpieza y los detectores siguen
en pie: dejaron de ser la primera línea de defensa y pasaron a ser la segunda.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class RespuestaIA(BaseModel):
    """Lo único que el modelo tiene permitido escribir."""

    justificacion_clinica: str = Field(
        default="",
        description=(
            "Por qué el servicio prestado era procedente, según lo que consta "
            "en los documentos aportados. Cita el documento por su título real "
            "y su folio. Sin cifras, sin tarifas, sin códigos de glosa."
        ),
    )
    fundamentos_ley: str = Field(
        default="",
        description=(
            "Las normas y sentencias que amparan la conducta, aplicadas a los "
            "hechos de este caso. Sin normas de relleno."
        ),
    )

    @field_validator("justificacion_clinica", "fundamentos_ley", mode="before")
    @classmethod
    def _a_texto(cls, v: object) -> str:
        """Una lista de párrafos o un número también sirven: se aplanan."""
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x).strip() for x in v if str(x).strip())
        return str(v).strip()

    def argumento(self) -> str:
        """Los dos campos, en el orden en que se leen: primero el hecho."""
        partes = [p for p in (self.justificacion_clinica, self.fundamentos_ley) if p.strip()]
        return " ".join(partes).strip()


# El modelo a veces envuelve el JSON en ```json … ``` o lo precede de un
# «Aquí está la respuesta:». Esto encuentra el objeto igual.
_RE_BLOQUE_JSON = re.compile(r"\{.*\}", re.DOTALL)


def parsear_respuesta_ia(bruto: str) -> Optional[RespuestaIA]:
    """El JSON del modelo, o None si no vino utilizable.

    None NO es un error fatal: el motor sigue con el camino XML de siempre. Un
    modelo que un día devuelva mal el JSON no puede dejar sin dictamen al
    hospital — la salida estructurada es una mejora, no un punto único de
    falla.
    """
    if not bruto or not bruto.strip():
        return None
    candidato = bruto.strip()
    if not candidato.startswith("{"):
        m = _RE_BLOQUE_JSON.search(candidato)
        if not m:
            return None
        candidato = m.group(0)
    try:
        datos = json.loads(candidato)
    except (ValueError, TypeError):
        return None
    if not isinstance(datos, dict):
        return None
    try:
        resp = RespuestaIA.model_validate(datos)
    except Exception:  # noqa: BLE001 — un JSON raro no tumba el dictamen
        return None
    return resp if resp.argumento() else None


def esquema_para_el_prompt() -> str:
    """El esquema tal como se le muestra al modelo, sin ambigüedad."""
    return (
        "Responde ÚNICAMENTE con este objeto JSON, sin texto antes ni después, "
        "sin ```:\n"
        "{\n"
        '  "justificacion_clinica": "<por qué el servicio era procedente, según '
        "los documentos APORTADOS; cita el documento por su título real y su "
        'folio>",\n'
        '  "fundamentos_ley": "<las normas que amparan esa conducta, aplicadas a '
        'los hechos de este caso>"\n'
        "}\n"
        "PROHIBIDO agregar claves. PROHIBIDO escribir cifras, tarifas, factores, "
        "UVB, topes o el código de la glosa dentro de los valores: el renglón "
        "del servicio y el bloque económico los arma el motor con los datos de "
        "la base, y se pegan después."
    )
