"""Qué pagadores se pueden encolar, y con qué bot — declarado como dato.

EL PROBLEMA. `lotes_service.PAGADORES_SOPORTADOS` era el conjunto literal
`{"COOSALUD"}`, el parser del Excel estaba llamado por su nombre en el
servicio, y `agente_lotes.BOTS_POR_TIPO` mapeaba a mano un solo tipo de
tarea. Los bots de SIMED, SAVIA, EMSSANAR, VCO, FOMAG y MUTUAL SER ya viven
en `tools/`: funcionan, y ninguno se podía encolar. Habilitar uno exigía
tocar tres archivos distintos y desplegar.

LA FORMA. Cada pagador es una ficha: cómo se llama en la pantalla, qué bot lo
atiende, qué hoja trae su Excel por defecto y cómo se lee ese Excel. Habilitar
el pagador número ocho es agregar una ficha — no tocar el servicio, ni el
agente, ni la pantalla.

LO QUE HAY QUE NORMALIZAR. Cada bot lee su Excel a su manera y devuelve una
forma distinta: COOSALUD entrega `{factura: {grupos, calidad}}` y SIMED
`{factura: [objeciones]}`. La ficha declara cómo pasar de esa forma a la que
el lote necesita — cuántas facturas, cuántas glosas, cuántas de calidad y si
alguna exige soporte—, y el servicio de lotes deja de saber de pagadores.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"


@dataclass(frozen=True)
class FacturaLote:
    """Una factura del lote, ya en la forma que el lote necesita."""

    grupos: int
    glosas: int
    calidad: int
    requiere_soporte: bool


@dataclass(frozen=True)
class PerfilLote:
    """Un pagador que se puede encolar."""

    pagador: str
    nombre: str  # cómo se lee en la pantalla
    bot: str  # archivo de `tools/` que lo atiende
    modulo: str  # módulo que sabe leer su Excel
    hoja_por_defecto: str = ""
    soporta_calidad: bool = False
    # Qué dice la pantalla sobre este pagador, para que el auditor sepa qué
    # archivo tiene que subir sin preguntarle a nadie.
    ayuda: str = ""
    # Cómo se lee su Excel y cómo se normaliza. Recibe (ruta, hoja,
    # incluir_calidad) y devuelve {factura: FacturaLote}.
    leer: Callable[[Path, str, bool], dict[str, FacturaLote]] = None

    @property
    def tarea(self) -> str:
        """El tipo de tarea que consume el agente: `RESPONDER_<PAGADOR>`."""
        return f"RESPONDER_{self.pagador}"

    def como_dict(self) -> dict[str, Any]:
        return {
            "pagador": self.pagador,
            "nombre": self.nombre,
            "hoja_por_defecto": self.hoja_por_defecto,
            "soporta_calidad": self.soporta_calidad,
            "ayuda": self.ayuda,
            "tarea": self.tarea,
        }


def _importar(modulo: str):
    """Importa la herramienta de `tools/` sin dejar `sys.path` sucio."""
    import importlib

    ruta = str(_TOOLS)
    agregado = ruta not in sys.path
    if agregado:
        sys.path.insert(0, ruta)
    try:
        return importlib.import_module(modulo)
    finally:
        if agregado and ruta in sys.path:
            sys.path.remove(ruta)


def _leer_coosalud(ruta: Path, hoja: str, incluir_calidad: bool) -> dict[str, FacturaLote]:
    """`{factura: {"grupos": [...], "calidad": N}}` → forma del lote."""
    mod = _importar("responder_glosas_coosalud")
    crudo = mod.leer_excel(ruta, hoja, incluir_calidad=incluir_calidad)
    return {
        factura: FacturaLote(
            grupos=len(info["grupos"]),
            glosas=sum(len(g["ids"]) for g in info["grupos"]),
            calidad=info.get("calidad", 0),
            requiere_soporte=any(g.get("es_soporte") for g in info["grupos"]),
        )
        for factura, info in crudo.items()
    }


def _leer_simed(ruta: Path, hoja: str, incluir_calidad: bool) -> dict[str, FacturaLote]:
    """`{factura: [objeción, …]}` → forma del lote.

    SIMED no separa glosas de calidad: su Excel es la respuesta ya redactada,
    una fila por objeción. Cada objeción es su propio grupo.
    """
    mod = _importar("responder_glosas_simed")
    crudo = mod.leer_excel_respuestas(ruta)
    return {
        factura: FacturaLote(
            grupos=len(objeciones),
            glosas=len(objeciones),
            calidad=0,
            # El Dispensario carga los soportes en un paso aparte
            # (`cargar_soportes_simed`), así que el lote de respuestas no los
            # exige.
            requiere_soporte=False,
        )
        for factura, objeciones in crudo.items()
    }


# ─── El registro ──────────────────────────────────────────────────────────
# Habilitar un pagador es agregar una ficha acá.

PERFILES: tuple[PerfilLote, ...] = (
    PerfilLote(
        pagador="COOSALUD",
        nombre="COOSALUD",
        bot="responder_glosas_coosalud.py",
        modulo="responder_glosas_coosalud",
        hoja_por_defecto="",
        soporta_calidad=True,
        ayuda=(
            "Subí el Excel consolidado de COOSALUD. Las glosas de CALIDAD "
            "(pertinencia) quedan fuera salvo que marqués la casilla."
        ),
        leer=_leer_coosalud,
    ),
    PerfilLote(
        pagador="SIMED",
        nombre="SIMED · Dispensario Médico",
        bot="responder_glosas_simed.py",
        modulo="responder_glosas_simed",
        hoja_por_defecto="",
        soporta_calidad=False,
        ayuda=(
            "Subí el Excel de respuestas del Dispensario: una fila por objeción, "
            "con la factura, el número y el texto de la respuesta ya redactado."
        ),
        leer=_leer_simed,
    ),
)

_POR_PAGADOR = {p.pagador: p for p in PERFILES}


def pagadores() -> list[str]:
    return sorted(_POR_PAGADOR)


def obtener(pagador: str) -> PerfilLote | None:
    return _POR_PAGADOR.get((pagador or "").strip().upper())


def catalogo() -> list[dict[str, Any]]:
    """Lo que la pantalla necesita para ofrecer los pagadores encolables."""
    return [p.como_dict() for p in PERFILES]


def bots_por_tarea() -> dict[str, str]:
    """`{RESPONDER_SIMED: responder_glosas_simed.py}` — lo que usa el agente.

    Sale del mismo registro que la pantalla, así que un pagador nuevo no puede
    quedar ofrecido en la aplicación y sin bot en el agente.
    """
    return {p.tarea: p.bot for p in PERFILES}
