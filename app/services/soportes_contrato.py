"""El contrato de lo que el indexador de soportes puede devolver.

**Por qué existe.** El indexador recorre el archivo del hospital y devuelve
diccionarios sueltos. Cada pantalla los leía a su manera y creía lo que
llegara. Eso ya costó un error de verdad: en el cajón de la mesa se leían
con `getattr` unos datos que son diccionarios, y el auditor veía «3
soportes» con tres renglones **en blanco** — que en una audiencia es peor
que ver un error, porque parece que la factura no tiene con qué defenderse.

Acá se valida una sola vez, con Pydantic, y se responde SIEMPRE con un
estado explícito. Una lista vacía y un índice roto no son lo mismo y no se
pueden pintar igual:

* `CON_SOPORTES`  — hay archivos y se pueden mostrar.
* `SIN_SOPORTES`  — se buscó, se terminó de buscar, y no hay.
* `INDEXANDO`     — el buscador todavía está recorriendo el archivo.
  **No es «no hay».** Decir «no hay» mientras se arma el índice manda a
  aceptar una glosa que sí estaba soportada.
* `SIN_INDICE`    — el indexador no responde (ruta caída, error).
* `DATOS_INVALIDOS` — respondió, pero con basura. Antes esto se colaba y
  pintaba filas vacías; ahora la pantalla muestra el error.

Ningún estado devuelve una lista a medias en silencio: si de veinte
archivos tres vienen mal formados, los tres se cuentan en `descartados` y
la pantalla lo dice.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.logging_utils import logger

# Un soporte más grande que esto no es un soporte: es un error de lectura.
_MAX_KB_RAZONABLE = 5 * 1024 * 1024  # 5 GB


class EstadoSoportes(str, Enum):
    CON_SOPORTES = "CON_SOPORTES"
    SIN_SOPORTES = "SIN_SOPORTES"
    INDEXANDO = "INDEXANDO"
    SIN_INDICE = "SIN_INDICE"
    DATOS_INVALIDOS = "DATOS_INVALIDOS"


class SoporteDeFactura(BaseModel):
    """Un archivo de soporte, ya validado.

    `extra="ignore"`: el indexador trae más campos de los que la pantalla
    usa (firmas, fechas internas). No estorban y no vale la pena romper por
    ellos. Lo que NO se tolera es que falte el nombre: un renglón sin nombre
    es exactamente la fila en blanco que se quiere evitar.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=400)
    tipo: str = Field(default="", max_length=80)
    tipo_codigo: str = Field(default="", max_length=20)
    tamano_kb: int = Field(default=0, ge=0, le=_MAX_KB_RAZONABLE)
    ruta: str = Field(default="", max_length=2000)

    @field_validator("nombre")
    @classmethod
    def _nombre_de_verdad(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("un soporte sin nombre no se puede mostrar")
        return v.strip()


class RespuestaSoportes(BaseModel):
    """Lo que la pantalla recibe. Siempre con estado, nunca ambiguo."""

    model_config = ConfigDict(extra="forbid")

    estado: EstadoSoportes
    cuantos: int = Field(default=0, ge=0)
    archivos: list[SoporteDeFactura] = Field(default_factory=list)
    # Cuántos vinieron mal formados y se dejaron fuera. Si esto no es cero,
    # la pantalla tiene que decirlo: la lista que se ve está incompleta.
    descartados: int = Field(default=0, ge=0)
    # Texto en español para el auditor. Nunca un traceback.
    detalle: str = ""

    @property
    def hay_problema(self) -> bool:
        return self.estado in (EstadoSoportes.SIN_INDICE, EstadoSoportes.DATOS_INVALIDOS)


def _normalizar(crudo: Any) -> Optional[dict]:
    """Un registro del indexador, mapeado a los nombres del contrato.

    `lookup()` devuelve diccionarios (`asdict` de `SoporteEntry`), no
    objetos: leerlos con `getattr` da cadenas vacías sin fallar, que es
    justo el error que llenó el cajón de renglones en blanco. Se aceptan
    también objetos por si otro indexador los entrega así, pero el camino
    normal es el diccionario.
    """
    if isinstance(crudo, dict):
        leer = crudo.get
    elif hasattr(crudo, "nombre_archivo") or hasattr(crudo, "ruta"):

        def leer(clave, defecto=None):
            return getattr(crudo, clave, defecto)
    else:
        return None

    nombre = leer("nombre_archivo") or leer("nombre") or ""
    return {
        "nombre": nombre,
        "tipo": leer("tipo") or "",
        "tipo_codigo": leer("tipo_codigo") or "",
        "tamano_kb": leer("tamano_kb") or 0,
        "ruta": leer("ruta") or "",
    }


def validar_lista(crudos: Any, tope: int = 40) -> tuple[list[SoporteDeFactura], int]:
    """Valida lo que devolvió el indexador. Devuelve (buenos, descartados).

    Un registro malo NO tumba los demás: se descarta y se cuenta. Un archivo
    con el nombre corrupto no puede impedir ver los otros diecinueve en
    plena audiencia.
    """
    if crudos is None:
        return [], 0
    if not isinstance(crudos, (list, tuple)):
        logger.warning(f"[SOPORTES] el indexador devolvió {type(crudos).__name__}, no una lista")
        return [], 1

    buenos: list[SoporteDeFactura] = []
    descartados = 0
    for crudo in crudos:
        datos = _normalizar(crudo)
        if datos is None:
            descartados += 1
            continue
        try:
            buenos.append(SoporteDeFactura(**datos))
        except Exception as e:  # noqa: BLE001
            descartados += 1
            logger.warning(f"[SOPORTES] registro descartado por inválido: {str(e)[:200]}")
        if len(buenos) >= tope:
            break
    return buenos, descartados


def leer_soportes(factura: str, tope: int = 40) -> RespuestaSoportes:
    """Los soportes de una factura, validados y con estado explícito.

    Es el ÚNICO camino que deben usar las pantallas. Nunca lanza: un
    indexador caído es un estado que se pinta, no una excepción que tumba
    la mesa entera cuando la EPS está esperando.
    """
    if not (factura or "").strip():
        return RespuestaSoportes(
            estado=EstadoSoportes.SIN_SOPORTES,
            detalle="No se indicó la factura.",
        )

    try:
        from app.services import soportes_autodiscovery_service as sas

        indexador = sas.get_indexer()
        stats = indexador.stats() or {}
        crudos = indexador.lookup(factura, auto_rebuild=False)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[SOPORTES] el indexador no respondió para {factura}: {e}")
        return RespuestaSoportes(
            estado=EstadoSoportes.SIN_INDICE,
            detalle=(
                "No se pudo consultar el archivo de soportes. NO quiere decir "
                "que la factura no tenga: quiere decir que no se pudo mirar."
            ),
        )

    archivos, descartados = validar_lista(crudos, tope=tope)

    if not archivos and descartados:
        return RespuestaSoportes(
            estado=EstadoSoportes.DATOS_INVALIDOS,
            descartados=descartados,
            detalle=(
                f"El archivo de soportes respondió {descartados} registro(s) que no "
                "se pudieron leer. No se muestra nada porque mostrar filas vacías "
                "haría creer que la factura no tiene soportes."
            ),
        )

    if not archivos:
        if stats.get("construyendo"):
            return RespuestaSoportes(
                estado=EstadoSoportes.INDEXANDO,
                detalle=(
                    "El buscador todavía está recorriendo el archivo del hospital. "
                    "Todavía NO se sabe si esta factura tiene soportes."
                ),
            )
        if stats.get("ultimo_error"):
            return RespuestaSoportes(
                estado=EstadoSoportes.SIN_INDICE,
                detalle=f"El buscador de soportes reportó un error: {str(stats['ultimo_error'])[:200]}",
            )
        if not stats.get("construido_en_epoch"):
            return RespuestaSoportes(
                estado=EstadoSoportes.INDEXANDO,
                detalle=(
                    "El archivo de soportes todavía no se ha recorrido ni una vez. "
                    "Todavía NO se sabe si esta factura tiene soportes."
                ),
            )
        return RespuestaSoportes(
            estado=EstadoSoportes.SIN_SOPORTES,
            detalle="Se revisó el archivo del hospital y no hay soportes de esta factura.",
        )

    detalle = ""
    if descartados:
        detalle = (
            f"Ojo: {descartados} archivo(s) vinieron con datos ilegibles y no se "
            "muestran. La lista está incompleta."
        )
    return RespuestaSoportes(
        estado=EstadoSoportes.CON_SOPORTES,
        cuantos=len(archivos),
        archivos=archivos,
        descartados=descartados,
        detalle=detalle,
    )
