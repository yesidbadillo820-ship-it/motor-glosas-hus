"""Servicio de consulta y evaluación de tarifas pactadas.

Cuando una glosa es tipo TARIFAS (TA*) con CUPS identificado, este servicio:
  1. Busca la tarifa pactada en la tabla `tarifas_contratadas`.
  2. Evalúa si la glosa tiene mérito o no (facturado vs. pactado).
  3. Devuelve una recomendación de acción para el auditor.

No depende de IA — es lógica pura basada en el contrato cargado por el
coordinador. La recomendación es un "cheat sheet" para el auditor.

Uso típico desde `glosa_service.analizar()`:
    from app.services.tarifa_lookup_service import evaluar_glosa_tarifa
    info = evaluar_glosa_tarifa(db, eps="FAMISANAR EPS", cups="890202",
                                 valor_facturado=100_000, valor_objetado=16_200)
    if info["encontrada"]:
        # Inyectar al prompt / mostrar banner
        ...
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.db import TarifaContratadaRecord


def _buscar(db: Session, eps: str, cups: str) -> Optional[TarifaContratadaRecord]:
    """Busca la tarifa activa más reciente para (eps, cups).

    Match case-insensitive en EPS (ilike %X%) porque puede venir
    'FAMISANAR' vs 'FAMISANAR EPS' vs 'U220181 - FAMISANAR EPS'.
    Match exacto en CUPS (tras strip).
    """
    if not eps or not cups:
        return None
    eps = eps.strip()
    cups = cups.strip()
    if not eps or not cups:
        return None
    return (
        db.query(TarifaContratadaRecord)
        .filter(TarifaContratadaRecord.activa == 1)
        .filter(TarifaContratadaRecord.eps.ilike(f"%{eps}%"))
        .filter(TarifaContratadaRecord.codigo_cups == cups)
        .order_by(TarifaContratadaRecord.creado_en.desc())
        .first()
    )


def calcular_valor_pactado(tarifa: TarifaContratadaRecord, valor_soat_base: float = 0.0) -> float:
    """Calcula el valor pactado final según el tipo de tarifa.

    - VALOR_FIJO → devuelve `valor_pactado` directo.
    - SOAT_PORCENTAJE → aplica `factor_ajuste` sobre `valor_soat_base`.
      Ej: factor=-5 y soat=100.000 → 100.000 × 0.95 = 95.000.
      Si `valor_soat_base=0`, no podemos calcular y devolvemos 0.
    """
    if not tarifa:
        return 0.0
    if (tarifa.tipo_tarifa or "VALOR_FIJO") == "VALOR_FIJO":
        return float(tarifa.valor_pactado or 0.0)
    factor = float(tarifa.factor_ajuste or 0.0)
    if valor_soat_base <= 0:
        return 0.0
    return round(valor_soat_base * (1 + factor / 100.0), 2)


def _recomendacion(valor_facturado: float, valor_pactado: float, valor_objetado: float) -> dict:
    """Compara facturado vs pactado y sugiere acción.

    Reglas:
      - Si facturado == pactado (±$1) → glosa INJUSTIFICADA (defender 100%)
      - Si facturado > pactado y la diferencia cabe en valor_objetado →
        aceptar parcial por la diferencia (defender el pactado)
      - Si facturado < pactado → defender (el hospital cobró menos del pactado)
      - Cualquier otro caso → revisar manualmente
    """
    tolerancia = 1.0  # $1 de margen por redondeos
    diferencia_abs = round(valor_facturado - valor_pactado, 2)

    if abs(diferencia_abs) <= tolerancia and valor_pactado > 0:
        return {
            "accion": "DEFENDER_TOTAL",
            "titulo": "✅ Defender 100%",
            "razon": (
                f"El valor facturado (${valor_facturado:,.0f}) coincide con la "
                f"tarifa pactada (${valor_pactado:,.0f}). La glosa es "
                f"INJUSTIFICADA: la EPS no puede glosar lo que ella misma pactó."
            ),
            "valor_a_defender": valor_pactado,
            "valor_a_aceptar": 0.0,
            "diferencia": 0.0,
        }

    if valor_pactado > 0 and valor_facturado < valor_pactado:
        return {
            "accion": "DEFENDER_TOTAL",
            "titulo": "✅ Defender 100% (facturado < pactado)",
            "razon": (
                f"El hospital facturó ${valor_facturado:,.0f}, MENOR al "
                f"pactado (${valor_pactado:,.0f}). La glosa es INJUSTIFICADA: "
                f"lo cobrado está dentro del contrato."
            ),
            "valor_a_defender": valor_facturado,
            "valor_a_aceptar": 0.0,
            "diferencia": 0.0,
        }

    if valor_pactado > 0 and diferencia_abs > tolerancia:
        # Facturado > pactado: lo correcto es defender el pactado y aceptar la diferencia
        valor_a_aceptar = min(diferencia_abs, valor_objetado) if valor_objetado > 0 else diferencia_abs
        valor_a_defender = max(0.0, valor_objetado - valor_a_aceptar) if valor_objetado > 0 else 0.0
        cabe_en_objetado = valor_objetado > 0 and diferencia_abs <= valor_objetado + tolerancia
        if cabe_en_objetado:
            return {
                "accion": "ACEPTAR_PARCIAL",
                "titulo": "⚠️ Aceptar parcial por la diferencia",
                "razon": (
                    f"El hospital facturó ${valor_facturado:,.0f} pero la "
                    f"tarifa pactada es ${valor_pactado:,.0f}. La diferencia "
                    f"${diferencia_abs:,.0f} SÍ procede aceptarla; el resto "
                    f"(${valor_a_defender:,.0f}) se defiende como pactado."
                ),
                "valor_a_defender": valor_a_defender,
                "valor_a_aceptar": valor_a_aceptar,
                "diferencia": diferencia_abs,
            }
        else:
            return {
                "accion": "REVISAR",
                "titulo": "❗ Revisar manualmente",
                "razon": (
                    f"La diferencia facturado-pactado (${diferencia_abs:,.0f}) "
                    f"EXCEDE el valor objetado por la EPS (${valor_objetado:,.0f}). "
                    f"Revisar si hay más CUPS involucrados o si la tarifa "
                    f"cargada es la correcta."
                ),
                "valor_a_defender": valor_objetado,
                "valor_a_aceptar": 0.0,
                "diferencia": diferencia_abs,
            }

    return {
        "accion": "REVISAR",
        "titulo": "❔ Sin comparación posible",
        "razon": (
            "La tarifa pactada es $0 o no se pudo calcular. "
            "Revisar el contrato o subir un catálogo actualizado."
        ),
        "valor_a_defender": valor_objetado,
        "valor_a_aceptar": 0.0,
        "diferencia": 0.0,
    }


def evaluar_glosa_tarifa(
    db: Session,
    eps: str,
    cups: str,
    valor_facturado: float = 0.0,
    valor_objetado: float = 0.0,
    valor_soat_base: float = 0.0,
) -> dict:
    """Evalúa una glosa TA contra la tarifa pactada. Devuelve siempre un dict
    con la clave `encontrada` que indica si hubo match.

    Estructura del dict:
      {
        "encontrada": bool,
        "tarifa": {id, eps, cups, descripcion, contrato_numero,
                   valor_pactado, tipo_tarifa, factor_ajuste, modalidad,
                   fuente_archivo, vigencia_desde, vigencia_hasta},
        "valor_facturado": float,     # lo que el hospital cobró
        "valor_objetado": float,      # lo que la EPS glosa
        "valor_pactado_calc": float,  # tarifa final ya calculada
        "recomendacion": { accion, titulo, razon, valor_a_defender,
                           valor_a_aceptar, diferencia },
      }

    Si `encontrada=False`, solo vienen valor_facturado/valor_objetado.
    """
    tarifa = _buscar(db, eps, cups)
    if tarifa is None:
        return {
            "encontrada": False,
            "tarifa": None,
            "valor_facturado": valor_facturado,
            "valor_objetado": valor_objetado,
            "valor_pactado_calc": 0.0,
            "recomendacion": None,
        }

    valor_pactado_calc = calcular_valor_pactado(tarifa, valor_soat_base=valor_soat_base)
    recomendacion = _recomendacion(valor_facturado, valor_pactado_calc, valor_objetado)

    return {
        "encontrada": True,
        "tarifa": {
            "id": tarifa.id,
            "eps": tarifa.eps,
            "codigo_cups": tarifa.codigo_cups,
            "descripcion": tarifa.descripcion,
            "contrato_numero": tarifa.contrato_numero,
            "valor_pactado": float(tarifa.valor_pactado or 0.0),
            "tipo_tarifa": tarifa.tipo_tarifa or "VALOR_FIJO",
            "factor_ajuste": float(tarifa.factor_ajuste or 0.0),
            "modalidad": tarifa.modalidad,
            "fuente_archivo": tarifa.fuente_archivo,
            "vigencia_desde": tarifa.vigencia_desde.isoformat() if tarifa.vigencia_desde else None,
            "vigencia_hasta": tarifa.vigencia_hasta.isoformat() if tarifa.vigencia_hasta else None,
        },
        "valor_facturado": valor_facturado,
        "valor_objetado": valor_objetado,
        "valor_pactado_calc": valor_pactado_calc,
        "recomendacion": recomendacion,
    }


def formato_texto_banner(info: dict) -> str:
    """Construye un texto plano resumen para inyectar al prompt de la IA.

    Devuelve "" si no hay tarifa encontrada. Se usa como contexto extra
    en el prompt del LLM para que genere un dictamen con datos duros.
    """
    if not info or not info.get("encontrada"):
        return ""
    t = info["tarifa"]
    r = info.get("recomendacion") or {}
    tipo = t.get("tipo_tarifa", "VALOR_FIJO")
    if tipo == "SOAT_PORCENTAJE":
        factor = t.get("factor_ajuste", 0.0)
        signo = "+" if factor > 0 else ""
        pactada_txt = f"SOAT {signo}{factor:.0f}% (factor pactado)"
    else:
        pactada_txt = f"${t.get('valor_pactado', 0):,.0f} (valor fijo)"
    return (
        "\n[TARIFA PACTADA ENCONTRADA EN EL CONTRATO]\n"
        f"CUPS: {t.get('codigo_cups')}\n"
        f"Descripción: {t.get('descripcion') or '—'}\n"
        f"EPS: {t.get('eps')}\n"
        f"Contrato: {t.get('contrato_numero') or '—'}\n"
        f"Modalidad: {t.get('modalidad') or '—'}\n"
        f"Tarifa pactada: {pactada_txt}\n"
        f"Valor facturado por HUS: ${info['valor_facturado']:,.0f}\n"
        f"Valor objetado por EPS: ${info['valor_objetado']:,.0f}\n"
        f"Recomendación: {r.get('titulo', '—')} — {r.get('razon', '')}\n"
        "USA ESTOS DATOS EN TU DICTAMEN. Cita el número de contrato y "
        "el valor pactado exacto. Argumenta que la EPS no puede desconocer "
        "lo que ella misma pactó (Art. 1602 C.Civil; Art. 871 C.Comercio).\n"
    )
