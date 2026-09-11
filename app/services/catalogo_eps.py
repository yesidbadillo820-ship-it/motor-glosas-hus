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
    {
        "EPS",
        "SA",
        "SAS",
        "S",
        "A",
        "LTDA",
        "ESE",
        "IPS",
        "ARS",
        "CIA",
        # 10-09-2026 — «FUNDACION» va DELANTE del nombre y por eso rompía la
        # comparación: «SALUD MIA» y «FUNDACION SALUD MIA EPS CONTRIBUTIVO»
        # salían como dos entidades. Es una forma jurídica, igual que S.A.S.,
        # y la malla contractual conoce a esa entidad como «SALUD MIA».
        "FUNDACION",
    }
)

# 10-09-2026 — AQUÍ ESTUVO UN ERROR MÍO, Y ESTÁ ESCRITO A PROPÓSITO.
#
# Yesid pidió desde el principio «un único nombre consolidado por entidad», y
# su regla decía expresamente «o separaciones por UVT/UVB». Yo las dejé
# separadas de todos modos, razonando que la unidad del SOAT cambiaba la
# tarifa. Miré el motor y esa razón era falsa:
#
#   · El motor liquida SOLO en UVB (`uvb.py`: UVB 2026 = $12.110). No existe
#     ni una tarifa en UVT en todo el código.
#   · Su propia normativa lo dice: «Reemplaza el uso de UVT (2023-2024). Todos
#     los valores tarifarios SOAT se expresan ahora en UVB».
#   · Las bases de tarifa de la malla son SOAT, SOAT_UVB, SOAT_SMLV, PROPIA,
#     PACTADA y MIXTA. No hay SOAT_UVT.
#
# Y del régimen: AXA COLPATRIA, ALIANZA MEDELLÍN y PROTEGER **no están en la
# malla contractual**, así que su nombre no elige ningún contrato. FUNDACION
# SALUD MIA EPS sí, y la malla la conoce como «SALUD MIA»: unirlas la mejora.
#
# COOSALUD sí tiene dos contratos (subsidiado y contributivo, números
# distintos), pero eso NO se resuelve por el desplegable —que ya muestra un
# solo «COOSALUD»— sino por los alias de la malla contra el texto de la
# glosa. Ese mecanismo no se toca.
#
# La lista no desaparece: SE INVIERTE. Antes decía «estas palabras separan dos
# entidades»; ahora dice «estas palabras son solo una variante de la MISMA».
#
# Hacía falta porque «… SOAT UVT» y «… SOAT UVB» no son uno el comienzo del
# otro: se separan en la última palabra. Sin esta lista quedaban como dos
# entidades aunque nada las distinga de verdad.
_VARIANTES_DE_LA_MISMA_ENTIDAD: frozenset[str] = frozenset(
    {"UVT", "UVB", "CONTRIBUTIVO", "SUBSIDIADO"}
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

    Son la misma entidad en dos casos:

    1. **Una es el comienzo de la otra.** «SALUD TOTAL» y «SALUD TOTAL EPS»;
       «DISPENSARIO MEDICO» y «… BUCARAMANGA».
    2. **Se separan al final y lo que las separa es solo una variante.**
       «… SOAT UVT» y «… SOAT UVB»; «… CONTRIBUTIVO» y «… SUBSIDIADO».

    Lo que NO las une: separarse al final en cualquier otra palabra. «SALUD
    TOTAL» y «SALUD MIA» comparten «SALUD» y ahí se acaba el parecido.
    """
    if not ka or not kb:
        return False
    corta, larga = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    if larga[: len(corta)] == corta:
        return True
    # Se separaron antes del final: solo son la misma si TODO lo que difiere
    # es una variante conocida (la unidad del SOAT, el régimen).
    comun = 0
    while comun < len(corta) and corta[comun] == larga[comun]:
        comun += 1
    if comun == 0:
        return False
    diferencia = set(corta[comun:]) | set(larga[comun:])
    return bool(diferencia) and diferencia <= _VARIANTES_DE_LA_MISMA_ENTIDAD


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


# «OTRA / SIN DEFINIR» es el marcador del desplegable, no una entidad.
#
# 10-09-2026 — en la captura de Yesid salía DOS veces: arriba como marcador y
# otra vez dentro de la lista. La ruta lo filtraba del historial pero no de
# los contratos cargados, así que un contrato guardado con ese nombre se
# colaba. Se filtra acá adentro, donde ningún llamador puede olvidarlo.
_MARCADORES_QUE_NO_SON_ENTIDAD: frozenset[str] = frozenset(
    {"", "OTRA", "SIN DEFINIR", "OTRA / SIN DEFINIR", "OTRA/SIN DEFINIR", "OTRA - SIN DEFINIR"}
)


def _limpios(lista) -> list[str]:
    """Los nombres de una fuente, en mayúscula, sin vacíos ni el marcador.

    Conserva el ORDEN en que vienen: la ruta manda el historial ordenado por
    cuántas glosas tiene cada grafía, y así gana la que de verdad se usa.
    """
    vistos: set[str] = set()
    salida: list[str] = []
    for nombre in lista or ():
        n = (nombre or "").strip().upper()
        if not n or n in _MARCADORES_QUE_NO_SON_ENTIDAD or n in vistos:
            continue
        vistos.add(n)
        salida.append(n)
    return salida


def eps_seleccionables(
    *otras_listas: "list[str] | tuple[str, ...]",
    preferidas: "list[str] | tuple[str, ...] | None" = None,
) -> list[str]:
    """La lista completa para un desplegable: el catálogo fijo, unido con
    lo que traigan otras fuentes (contratos reales, EPS ya vistas en el
    historial sin contrato). Sin repetidos, en mayúscula, orden alfabético.

    «Sin repetidos» incluye la misma entidad escrita de dos maneras
    (ver `misma_entidad`): de cada grupo sobrevive UN nombre.

    **Cuál de los nombres sobrevive.** Gana el primero que entra:

    1. `preferidas` — las entidades CON CONTRATO CARGADO. Ese es el nombre con
       el que está FIRMADO el contrato y el que debe salir citado.
    2. Las demás listas, en el orden en que las manda el llamador. La ruta
       manda el historial ordenado por cuántas glosas tiene cada grafía, así
       que gana el nombre con el que de verdad están escritas las glosas.
    3. El catálogo curado, de último y solo para completar: nunca agrega un
       renglón si los datos reales ya nombran a esa entidad.
    """
    salida: list[str] = []
    claves: list[tuple[str, ...]] = []

    def _agregar(nombre: str, del_catalogo: bool) -> None:
        clave = _clave_de_entidad(nombre)
        if not clave:
            return
        for ya in claves:
            if _misma_clave(clave, ya):
                return
            # El catálogo curado NO agrega renglones. En el desplegable real
            # salía «SALUD MIA» (de esta lista fija, sin una glosa detrás)
            # junto a «FUNDACION SALUD MIA EPS CONTRIBUTIVO»: dos renglones
            # para una entidad. El nombre corto existe solo para que la
            # entidad se pueda ELEGIR cuando no hay ningún dato suyo; si los
            # datos reales ya la nombran, estorba.
            if del_catalogo and ya[: len(clave)] == clave:
                return
        salida.append(nombre)
        claves.append(clave)

    # El orden manda: lo primero que entra es el nombre que sobrevive.
    for nombre in _limpios(preferidas):
        _agregar(nombre, del_catalogo=False)
    for lista in otras_listas:
        for nombre in _limpios(lista):
            _agregar(nombre, del_catalogo=False)
    for nombre in sorted(_limpios(EPS_CONOCIDAS)):
        _agregar(nombre, del_catalogo=True)

    salida.sort()
    return salida
