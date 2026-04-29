"""Liquidador en línea de tarifas SOAT (UVB) y Propias HUS (SMDLV).

Endpoints públicos (autenticados) para que el gestor consulte por código
CUPS o por descripción, vea el factor (UVB / SMDLV), aplique el
porcentaje contractual (ej. SOAT-5%, SOAT+10%) y obtenga el valor en
pesos calculado a la centena más próxima — equivalente local a sitios
como miscuentasmedicas.com pero usando los catálogos del HUS.

Catálogos consultados:
  • TARIFAS_PROPIAS_HUS  — Res. 054/2026 + 124/2026 ESE HUS
  • TARIFAS_SOAT_2026    — Circular 047/2025 MinSalud (UVB $12.110)
  • DESCRIPCIONES_CUPS_2025 — fallback informativo (~150 códigos sin
    factor; cuando aparece acá pero no en los anteriores, se devuelve
    como "sin tarifa local — consulte el Manual SOAT 2026 oficial").

Modalidades soportadas:
  • SOAT_PLENO            (UVB × 12.110)
  • SOAT_PCT              (UVB × 12.110 × (1 + pct/100))
  • PROPIA_HUS            (FACTOR × SMDLV)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord
from app.services.homologador_cups import DESCRIPCIONES_CUPS_2025
from app.services.tarifas_oficiales import (
    TARIFAS_PROPIAS_HUS,
    TARIFAS_SOAT_2026,
    buscar_tarifa_propia_hus,
    buscar_tarifa_soat_2026,
)
from app.services.uvb import (
    UVB_2026,
    SMDLV_2026,
    calcular_soat_con_factor,
    calcular_propia_hus,
    calcular_valor_pesos,
    valor_smdlv_vigente,
    valor_uvb_vigente,
)

router = APIRouter(prefix="/tarifa-liquidador", tags=["Tarifa Liquidador"])


# ─── Helpers ────────────────────────────────────────────────────────────


def _matchea(texto_buscado: str, codigo: str, descripcion: str) -> bool:
    q = (texto_buscado or "").upper().strip()
    if not q:
        return True
    if q in (codigo or "").upper():
        return True
    if q in (descripcion or "").upper():
        return True
    # Match parcial token-a-token (cualquier palabra del query)
    tokens = [t for t in q.split() if len(t) >= 3]
    desc_up = (descripcion or "").upper()
    return all(t in desc_up for t in tokens) if tokens else False


def _liquidar_soat(factor_uvb: float, pct: float, anio: int) -> dict:
    """Aplica fórmula SOAT con porcentaje contractual."""
    valor = calcular_soat_con_factor(factor_uvb, pct, anio)
    return {
        "modalidad": "SOAT_PCT" if pct != 0 else "SOAT_PLENO",
        "factor_uvb": float(factor_uvb),
        "uvb_vigente": valor_uvb_vigente(anio),
        "porcentaje_aplicado": float(pct),
        "valor_pesos": valor,
        "formula": (
            f"{factor_uvb} UVB × ${valor_uvb_vigente(anio):,} × "
            f"(1 + {pct}/100) → centena más próxima = ${valor:,}"
        ).replace(",", "."),
    }


def _liquidar_propia(factor_smdlv: float, anio: int) -> dict:
    valor = calcular_propia_hus(factor_smdlv, anio)
    return {
        "modalidad": "PROPIA_HUS",
        "factor_smdlv": float(factor_smdlv),
        "smdlv_vigente": valor_smdlv_vigente(anio),
        "valor_pesos": valor,
        "formula": (
            f"{factor_smdlv} SMDLV × ${valor_smdlv_vigente(anio):,} → "
            f"centena más próxima = ${valor:,}"
        ).replace(",", "."),
    }


# ─── Endpoints ──────────────────────────────────────────────────────────


@router.get("/buscar")
def buscar_codigo(
    q: str = Query(..., min_length=1, description="Código o descripción"),
    modalidad: str = Query("SOAT", description="SOAT | PROPIA"),
    pct: float = Query(0.0, ge=-100, le=200, description="% contractual"),
    anio: int = Query(2026, ge=2020, le=2030),
    limite: int = Query(20, ge=1, le=100),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Busca códigos en SOAT 2026 + Propias HUS y devuelve el cálculo.

    Ejemplos:
      • /tarifa-liquidador/buscar?q=ecocardiograma&modalidad=PROPIA
      • /tarifa-liquidador/buscar?q=890402&modalidad=SOAT&pct=-5
    """
    mod = (modalidad or "").upper()
    matches = []

    if mod in ("SOAT", "SOAT_PLENO", "SOAT_PCT", "AMBOS", ""):
        for cod, (factor_uvb, valor_pesos, desc, norma) in TARIFAS_SOAT_2026.items():
            if _matchea(q, cod, desc):
                liquidacion = _liquidar_soat(factor_uvb, pct, anio)
                matches.append({
                    "codigo": cod,
                    "descripcion": desc,
                    "norma": norma,
                    "catalogo": "SOAT_2026",
                    **liquidacion,
                })

    if mod in ("PROPIA", "PROPIA_HUS", "AMBOS", ""):
        for cod, (factor_smdlv, valor_pesos, desc, norma) in TARIFAS_PROPIAS_HUS.items():
            if _matchea(q, cod, desc):
                liquidacion = _liquidar_propia(factor_smdlv, anio)
                matches.append({
                    "codigo": cod,
                    "descripcion": desc,
                    "norma": norma,
                    "catalogo": "PROPIA_HUS",
                    **liquidacion,
                })

    # Orden: matches por código exacto primero, luego por descripción
    q_up = q.upper().strip()
    matches.sort(key=lambda x: (
        0 if x["codigo"].upper() == q_up else
        1 if q_up in x["codigo"].upper() else
        2,
        x["descripcion"],
    ))

    # Fallback informativo: si no hay tarifa local pero el código existe
    # en el catálogo CUPS curado, devolverlo como "sin tarifa local". El
    # gestor al menos confirma que el código existe y la descripción.
    fallback_cups = []
    if not matches and q:
        for cod, desc in DESCRIPCIONES_CUPS_2025.items():
            if _matchea(q, cod, desc):
                fallback_cups.append({
                    "codigo": cod,
                    "descripcion": desc,
                    "modalidad": "SIN_TARIFA_LOCAL",
                    "factor_uvb": None,
                    "factor_smdlv": None,
                    "valor_pesos": None,
                    "uvb_vigente": valor_uvb_vigente(anio),
                    "smdlv_vigente": valor_smdlv_vigente(anio),
                    "porcentaje_aplicado": pct,
                    "catalogo": "CUPS_2025_DESCRIPTIVO",
                    "norma": "Catálogo CUPS curado (sin factor tarifario local)",
                    "formula": (
                        "Sin factor en catálogos locales. Consulta el Manual SOAT "
                        "2026 oficial (Circular 047/2025) o el contrato vigente "
                        "para obtener el factor UVB/SMDLV de este código."
                    ),
                })
        # Limitar fallback a 30 para no saturar
        fallback_cups = fallback_cups[:30]

    todos = matches[:limite] + fallback_cups
    return {
        "query": q,
        "modalidad": mod or "AMBOS",
        "porcentaje_aplicado": pct,
        "anio": anio,
        "uvb_vigente": valor_uvb_vigente(anio),
        "smdlv_vigente": valor_smdlv_vigente(anio),
        "total_resultados": len(matches),
        "total_fallback_cups": len(fallback_cups),
        "resultados": todos,
    }


class LiquidarManualInput(BaseModel):
    factor: float = Field(..., gt=0, description="Factor UVB o SMDLV")
    modalidad: str = Field("SOAT", description="SOAT | PROPIA")
    pct: float = Field(0.0, ge=-100, le=200)
    anio: int = Field(2026, ge=2020, le=2030)


@router.post("/liquidar-manual")
def liquidar_manual(
    data: LiquidarManualInput,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Calcula directamente sin código — el usuario digita el factor.

    Útil cuando el código NO está en el catálogo local pero tenés el
    factor del documento físico.
    """
    if data.modalidad.upper().startswith("PROPIA"):
        return _liquidar_propia(data.factor, data.anio)
    return _liquidar_soat(data.factor, data.pct, data.anio)


@router.get("/info-unidades")
def info_unidades(
    anio: int = Query(2026, ge=2020, le=2030),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve la UVB y el SMDLV vigentes + marco normativo."""
    return {
        "anio": anio,
        "uvb": valor_uvb_vigente(anio),
        "smdlv": valor_smdlv_vigente(anio),
        "marco_soat": (
            "Manual Tarifario SOAT — Circular Externa 047 de 2025 MinSalud, "
            "Decreto 780 de 2016 (Anexo Técnico No. 1). "
            f"UVB {anio} = ${valor_uvb_vigente(anio):,}"
        ).replace(",", "."),
        "marco_propias_hus": (
            "Tarifas propias ESE HUS — Resolución 054 de enero 30/2026 "
            "(unificada) y Resolución 124 de marzo 25/2026 (nuevos códigos "
            f"y modificaciones). SMDLV {anio} ≈ ${valor_smdlv_vigente(anio):,}"
        ).replace(",", "."),
        "total_codigos_propios": len(TARIFAS_PROPIAS_HUS),
        "total_codigos_soat": len(TARIFAS_SOAT_2026),
    }
