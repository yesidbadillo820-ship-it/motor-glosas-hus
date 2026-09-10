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


def eps_seleccionables(*otras_listas: "list[str] | tuple[str, ...]") -> list[str]:
    """La lista completa para un desplegable: el catálogo fijo, unido con
    lo que traigan otras fuentes (contratos reales, EPS ya vistas en el
    historial sin contrato). Sin repetidos, en mayúscula, orden alfabético.

    Se acepta cualquier número de listas adicionales para que cada llamador
    sume sus propias fuentes sin que este módulo tenga que conocerlas.
    """
    vistas: set[str] = set()
    salida: list[str] = []
    for lista in (EPS_CONOCIDAS, *otras_listas):
        for nombre in lista or ():
            n = (nombre or "").strip().upper()
            if not n or n in vistas:
                continue
            vistas.add(n)
            salida.append(n)
    salida.sort()
    return salida
