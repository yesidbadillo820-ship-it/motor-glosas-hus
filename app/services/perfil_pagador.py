"""Motor Universal: el perfil único de cada pagador.

EL PROBLEMA. Lo que el sistema sabe hacer con un pagador estaba repartido
en tres registros y un catálogo curado: el contrato en la malla, el perfil
de lotes masivos en perfiles_lote, los conversores en el Centro de
Automatización y los datos de defensa (contacto, notas) en el catálogo de
prompts. Para saber «¿qué puede hacer el sistema con COOSALUD?» había que
saberse los cuatro lugares — y agregar un pagador era tocar código en
varios.

Acá se unifica: UN perfil por pagador, armado leyendo los registros que ya
existen (cero duplicación — esto no copia datos, los consulta). Agregar
capacidad para un pagador sigue siendo agregar una ficha en el registro
que corresponde, y este perfil la muestra solo: en la pantalla de
Contratos, en la API y en el chat IA.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging_utils import logger


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip().upper()


def _malla_de(pagador: str) -> dict[str, Any]:
    from datetime import date

    from app.services import malla_contractual as mc

    hoy = date.today()
    vigente = mc.vigente(pagador, hoy)
    todos = mc.contratos_de(pagador)
    return {
        "en_malla": bool(todos),
        "contrato_vigente_hoy": vigente.como_dict() if vigente else None,
        "contratos": [c.como_dict() for c in todos],
    }


def _lotes_de(pagador: str) -> dict[str, Any] | None:
    from app.services import perfiles_lote

    clave = _norm(pagador)
    for p in perfiles_lote.PERFILES:
        if _norm(p.pagador) in clave or clave in _norm(p.pagador):
            return {
                "pagador_del_perfil": p.pagador,
                "bot_que_carga": p.bot,
                "soporta_calidad": p.soporta_calidad,
                "ayuda": p.ayuda,
            }
    return None


def _conversores_de(pagador: str) -> list[dict[str, Any]]:
    from app.services import automatizaciones as autos

    clave = _norm(pagador)
    palabras = {w for w in clave.split() if len(w) >= 4}
    salida = []
    for a in autos.CATALOGO:
        nombre = _norm(a.nombre)
        if any(w in nombre for w in palabras):
            salida.append({"id": a.id, "nombre": a.nombre, "que_hace": a.que_hace})
    return salida


def _defensa_de(pagador: str) -> dict[str, Any] | None:
    """Los datos curados del catálogo de prompts (contacto, notas de
    defensa) que la malla no trae."""
    try:
        from app.services.glosa_ia_prompts import CONTRATOS_HUS, _clave_curada

        clave = _clave_curada(pagador)
        if not clave:
            return None
        ficha = CONTRATOS_HUS.get(clave) or {}
        util = {k: v for k, v in ficha.items() if k in ("contacto", "nit", "nota", "regimen") and v}
        return {"clave_catalogo": clave, **util} if util else {"clave_catalogo": clave}
    except Exception:
        return None


def perfil(pagador: str) -> dict[str, Any]:
    """TODO lo que el sistema sabe hacer con un pagador, en una respuesta."""
    partes: dict[str, Any] = {"pagador": pagador}
    for nombre, fn in (
        ("malla", _malla_de),
        ("lotes_masivos", _lotes_de),
        ("conversores", _conversores_de),
        ("defensa", _defensa_de),
    ):
        try:
            partes[nombre] = fn(pagador)
        except Exception:
            logger.warning(f"[PERFIL-PAGADOR] fuente '{nombre}' falló", exc_info=True)
            partes[nombre] = None

    capacidades = []
    m = partes.get("malla") or {}
    if m.get("contrato_vigente_hoy"):
        capacidades.append("El análisis cita su contrato vigente por fecha del hecho")
    elif m.get("en_malla"):
        capacidades.append("Está en la malla pero HOY sin contrato vigente: defensa a SOAT pleno")
    if partes.get("lotes_masivos"):
        capacidades.append(
            f"Respuesta masiva por lotes (bot: {partes['lotes_masivos']['bot_que_carga']})"
        )
    for c in partes.get("conversores") or []:
        capacidades.append(f"Conversor en Automatización: {c['nombre']}")
    if partes.get("defensa", {}) and (partes["defensa"] or {}).get("contacto"):
        capacidades.append("Contacto de radicación registrado")
    partes["capacidades"] = capacidades
    partes["total_capacidades"] = len(capacidades)
    return partes


def catalogo() -> list[dict[str, Any]]:
    """El mapa completo: cada pagador de la malla con sus capacidades."""
    from app.services import malla_contractual as mc

    return [perfil(p) for p in mc.pagadores()]
