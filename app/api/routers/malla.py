"""Malla contractual: qué contrato rige, hasta cuándo, y qué ya venció.

Facturar contra un contrato vencido es una glosa segura, y renegociar uno toma
semanas. Hasta ahora la malla vivía en un PDF que actualiza contratación y que
el área de glosas miraba cuando se acordaba; el sistema tenía las vigencias
como texto libre y no las leía nunca.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord
from app.services import malla_contractual as malla

router = APIRouter(prefix="/malla", tags=["malla"])


@router.get("")
def estado_de_la_malla(
    dias_aviso: int = Query(
        malla.DIAS_AVISO_VENCIMIENTO,
        ge=1,
        le=365,
        description="Con cuántos días de anticipación se avisa",
    ),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Qué contratos están vencidos, cuáles se acaban pronto y cuáles siguen.

    Es de solo lectura y la ve cualquier usuario autenticado: saber con qué
    contrato se está facturando no es información reservada, y esconderla es
    lo que hace que alguien defienda una glosa citando un contrato muerto.
    """
    return malla.estado_vigencia(date.today(), dias_aviso=dias_aviso)


@router.get("/pagadores")
def mapa_de_pagadores(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """El Motor Universal en una respuesta: cada pagador de la malla con
    TODO lo que el sistema sabe hacer con él (contrato por fecha, lotes
    masivos y su bot, conversores, contacto de radicación)."""
    from app.services import perfil_pagador

    return {"pagadores": perfil_pagador.catalogo()}


@router.get("/perfil")
def perfil_de_pagador(
    pagador: str = Query(..., min_length=2, description="EPS o entidad pagadora"),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """El perfil universal de UN pagador: qué sabe hacer el sistema con él
    y de qué registro sale cada capacidad."""
    from app.services import perfil_pagador

    return perfil_pagador.perfil(pagador)


@router.get("/vigente")
def contrato_vigente(
    pagador: str = Query(..., min_length=2, description="EPS o entidad pagadora"),
    fecha: str | None = Query(None, description="Fecha del hecho (AAAA-MM-DD). Por defecto, hoy."),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """El contrato que regía **el día de la atención**, no el que esté cargado hoy.

    Es la pregunta que hay que hacerse antes de defender una glosa por tarifa:
    una atención de marzo de 2026 no está cubierta por el contrato de FAMISANAR
    que empezó el 15 de abril, y citarlo le da la razón a la EPS.
    """
    if fecha:
        try:
            dia = datetime.strptime(fecha.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "La fecha debe venir como AAAA-MM-DD")
    else:
        dia = date.today()

    contrato = malla.vigente(pagador, dia)
    todos = malla.contratos_de(pagador)

    if contrato is None:
        return {
            "pagador": pagador,
            "fecha": dia.isoformat(),
            "hay_contrato": False,
            # Que no haya contrato ese día no es un fallo de búsqueda: es un
            # hecho que cambia la defensa. Se dice, con lo que sí existe.
            "mensaje": (
                f"Ningún contrato de '{pagador}' regía el {dia.isoformat()}."
                if todos
                else f"'{pagador}' no aparece en la malla contractual."
            ),
            "otros_contratos": [c.como_dict() for c in todos],
        }

    dias = contrato.dias_para_vencer(dia)
    return {
        "pagador": pagador,
        "fecha": dia.isoformat(),
        "hay_contrato": True,
        "contrato": contrato.como_dict(),
        "dias_para_vencer": dias,
        "vencido": dias is not None and dias < 0,
        "otros_contratos": [c.como_dict() for c in todos if c.numero != contrato.numero],
    }
