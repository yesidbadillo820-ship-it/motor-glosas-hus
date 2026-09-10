"""Catálogo de entidades pagadoras reales, más allá de las que tienen
contrato cargado.

**El defecto que esto corrige (09-09-2026).** El desplegable «EPS / Entidad
Pagadora» del botón Analizar se llenaba SOLO con `GET /contratos/` — o sea,
con las entidades que ya tienen un `ContratoRecord` en la base. SURA, SALUD
TOTAL, EMSSANAR, SAVIA y MUTUAL SER son entidades reales con las que el HUS
glosa a diario —cada una tiene SU PROPIO bot de portal en `bots_hus.py` y su
propia lógica en el motor (`glosa_service.py`, `quality_gate/pre_validator.py`,
`recepcion_service.py`)— pero como nadie les ha subido un PDF de contrato,
JAMÁS aparecían como opción. El auditor solo podía elegir
«OTRA / SIN DEFINIR», así que TODOS los dictámenes de esas EPS salían
genéricos: sin el nombre real en el escrito, con el aviso de «entidad sin
identificar» y sin poder acumular precedente ni historial por EPS.

La ENTIDAD sí se conocía en el resto del sistema; lo único que faltaba era
dejarla ELEGIR. `get_contrato()` (`glosa_ia_prompts.py`) ya sabía degradarse
bien para una EPS con nombre y sin contrato —dice «SIN CONTRATO PACTADO,
SOAT PLENO» y sigue citando el nombre real—, así que esto no le pide nada
nuevo al resto del motor: solo lo deja usarlo.

Trampa que esto evita, y por la que no basta con `/contratos/eps-sin-contrato`
(que ya existía para otro formulario): esa ruta solo lista EPS que YA
aparecen en `GlosaRecord.eps` — pero una EPS que nunca se pudo seleccionar
tampoco pudo quedar guardada con su nombre real. Es un candado que se cierra
solo. Por eso este catálogo es una lista fija, no una consulta a la base.
"""

from __future__ import annotations

import re
import unicodedata

from app.services.pagador_normalizer import nombre_corto as _nombre_corto

# Entidades reales con las que el HUS glosa. Cada una está en uso en OTRA
# parte del motor (bot de portal propio, rama de lógica de negocio propia, o
# detector de texto) — no se agrega ninguna que no esté ya referenciada en
# el sistema; agregar una que no lo esté sería inventar un dato (regla del
# proyecto: "PROHIBIDO inventar... EPS").
EPS_CONOCIDAS: tuple[str, ...] = (
    "FAMISANAR",
    "NUEVA EPS",
    "COOSALUD",
    "COMPENSAR",
    "POSITIVA",
    "FOMAG",
    "SANITAS",
    "SALUD TOTAL",
    "SURA",
    "ECOOPSOS",
    "POLICIA NACIONAL",
    "DISPENSARIO MEDICO",
    "SUMIMEDICAL",
    "AURORA",
    "SALUD MIA",
    "PPL",
    "COMFENALCO",
    "CAJACOPI",
    # 09-09-2026 — tenían bot de portal propio (bots_hus.py) y ramas de
    # lógica en glosa_service.py / recepcion_service.py, pero ningún
    # ContratoRecord: nunca habían aparecido como opción.
    "MUTUAL SER",
    "EMSSANAR",
    "SAVIA",
)


# 10-09-2026 — LA MISMA ENTIDAD, ESCRITA DE DOS MANERAS, SALÍA DOS VECES.
#
# Yesid abrió el desplegable de «EPS / Entidad Pagadora» y contó los pares:
# SALUD TOTAL y SALUD TOTAL EPS, SURA y SURA EPS, ADRES ACCIDENTES DE
# TRANSITO y ADRES-ACCIDENTES DE TRANSITO, DISPENSARIO MEDICO y DIRECCION DE
# SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA. No es un error de esta
# lista: son registros REALES escritos distinto —unos vienen de un contrato
# cargado, otros del historial— y la unión solo descartaba el texto idéntico.
#
# Para el auditor eso es peor que feo: dos renglones que parecen dos
# entidades obligan a adivinar cuál elegir, y elegir mal manda el dictamen
# con el nombre que la EPS no reconoce.
#
# LO QUE ESTA REGLA NO PUEDE HACER, y por eso no basta con «quitar sufijos»:
# hay sufijos que SÍ distinguen y borrarlos costaría plata.
#
#   · UVT / UVB es la unidad con la que se liquida el SOAT (UVB rige desde la
#     reforma de 2023, UVT es la anterior). Fundir «SOAT - UVT» con «SOAT UVB»
#     deja la tarifa mal calculada.
#   · CONTRIBUTIVO / SUBSIDIADO es el régimen, y con él la norma aplicable.
#
# Así que la regla une por IDENTIDAD, no por parecido: dos nombres son la
# misma entidad si uno es el comienzo del otro y lo que sobra NO distingue.
_FORMA_JURIDICA: frozenset[str] = frozenset(
    {"EPS", "SA", "SAS", "S", "A", "LTDA", "ESE", "IPS", "ARS", "CIA"}
)

# Palabras que NO son adorno: si aparecen en la diferencia entre dos nombres,
# son dos entidades distintas y se dejan las dos.
_TOKENS_QUE_DISTINGUEN: frozenset[str] = frozenset(
    {
        "UVT",  # unidad de liquidación del SOAT anterior a la reforma de 2023
        "UVB",  # la que rige desde entonces
        "CONTRIBUTIVO",  # régimen: cambia la norma aplicable
        "SUBSIDIADO",
        # ADRES no es solo accidentes de tránsito: en este hospital tiene
        # además la baja de cartera de la Res. 577/2019, que es otra ruta de
        # pago (`bots_hus.py`, grupo ADRES). Un «ADRES» pelado y un «ADRES
        # ACCIDENTES DE TRANSITO» no son el mismo renglón de cartera. Esto NO
        # rompe la unión de «ADRES ACCIDENTES DE TRANSITO» con
        # «ADRES-ACCIDENTES DE TRANSITO»: ahí la diferencia es un guion y no
        # sobra ninguna palabra.
        "ACCIDENTES",
        "TRANSITO",
    }
)

_RE_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]+")


def _clave_de_entidad(nombre: str) -> tuple[str, ...]:
    """Las palabras que de verdad identifican a la entidad.

    Quita el código EPS y el prefijo «DIRECCION DE SANIDAD <FUERZA> -»
    (eso ya lo sabe hacer `pagador_normalizer`), los acentos, la puntuación
    —«ADRES-ACCIDENTES» y «ADRES ACCIDENTES» son lo mismo— y las siglas de
    forma jurídica, que nunca distinguen a un pagador de otro.
    """
    s = _nombre_corto(nombre).upper()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = _RE_NO_ALFANUMERICO.sub(" ", s)
    return tuple(t for t in s.split() if t not in _FORMA_JURIDICA)


def _misma_clave(ka: tuple[str, ...], kb: tuple[str, ...]) -> bool:
    """La comparación de verdad, sobre claves YA calculadas.

    Separada para que la unión normalice cada nombre UNA vez y no una vez por
    comparación: el historial crece, la lista del desplegable no.
    """
    if not ka or not kb:
        return False
    corta, larga = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    if larga[: len(corta)] != corta:
        return False
    return not (set(larga[len(corta) :]) & _TOKENS_QUE_DISTINGUEN)


def misma_entidad(a: str, b: str) -> bool:
    """True si dos nombres son la MISMA entidad escrita de dos maneras.

    Uno tiene que ser el comienzo del otro, y lo que sobra no puede llevar
    ninguna palabra de `_TOKENS_QUE_DISTINGUEN`:

        «SALUD TOTAL» vs «SALUD TOTAL EPS»          → la misma
        «DISPENSARIO MEDICO» vs «… BUCARAMANGA»     → la misma
        «… SOAT - UVT» vs «… SOAT UVB»              → DISTINTAS (unidad)
        «… CONTRIBUTIVO» vs «… SUBSIDIADO»          → DISTINTAS (régimen)
        «… SOAT» vs «… SOAT UVB»                    → DISTINTAS: el nombre
             pelado no dice qué unidad es, y suponerlo sería inventar la
             tarifa. Se dejan los dos y que el auditor elija.
    """
    return _misma_clave(_clave_de_entidad(a), _clave_de_entidad(b))


def eps_seleccionables(
    *otras_listas: "list[str] | tuple[str, ...]",
    preferidas: "list[str] | tuple[str, ...] | None" = None,
) -> list[str]:
    """La lista completa para un desplegable: el catálogo fijo, unido con
    lo que traigan otras fuentes (contratos reales, EPS ya vistas en el
    historial sin contrato). Sin repetidos, en mayúscula, orden alfabético.

    «Sin repetidos» incluye la misma entidad escrita de dos maneras
    (ver `misma_entidad`): de cada grupo sobrevive UN nombre.

    `preferidas` es el nombre que gana cuando hay empate — el llamador manda
    ahí las entidades CON CONTRATO CARGADO, porque ese es el nombre con el
    que está firmado el contrato y el que debe salir citado en el dictamen.
    Después manda el catálogo curado, y de último lo que venga del historial,
    que es la fuente más sucia.
    """
    salida: list[str] = []
    claves: list[tuple[str, ...]] = []
    for lista in (preferidas or (), EPS_CONOCIDAS, *otras_listas):
        for nombre in sorted(
            {(n or "").strip().upper() for n in (lista or ()) if (n or "").strip()}
        ):
            clave = _clave_de_entidad(nombre)
            if any(_misma_clave(clave, ya) for ya in claves):
                continue
            salida.append(nombre)
            claves.append(clave)
    salida.sort()
    return salida
