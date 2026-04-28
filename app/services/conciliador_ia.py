"""Conciliador IA — preparador de audiencias de conciliación.

Cuando una glosa va a mesa de conciliación (Art. 20 Decreto 4747/2007),
el gestor llega a la audiencia con:
  • Posibles contraargumentos de la EPS basados en el histórico contra
    esa misma EPS para el mismo código de glosa.
  • Respuesta sugerida a cada contraargumento (texto listo para usar).
  • Valor mínimo aceptable según margen de defensa.
  • Recomendación táctica: si conviene firme defensa, si conviene
    aceptar parcial, si conviene escalar a SuperSalud.

No reemplaza al abogado — le da contexto + munición lista para que la
audiencia sea más eficiente.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Catálogo de contraargumentos típicos por tipo de glosa, con respuestas
# sugeridas. La IA luego personaliza según el caso concreto.
_CONTRAARGUMENTOS_PLANTILLA = {
    "TA": [
        {
            "titulo": "La EPS dirá: 'el valor cobrado excede la tarifa pactada'",
            "respuesta_sugerida": (
                "Mostrar el contrato vigente (cláusula tarifaria) y la "
                "factura. Si la diferencia es por SOAT base distinto, "
                "citar Circular 047/2025 MinSalud (UVB 2026 = $12.110)."
            ),
        },
        {
            "titulo": "La EPS dirá: 'el descuento contractual no se aplicó'",
            "respuesta_sugerida": (
                "Probar matemáticamente: facturado / tarifa_SOAT_base = "
                "(1 + factor_pactado). Si HUS aplicó correctamente, la "
                "objeción carece de fundamento."
            ),
        },
        {
            "titulo": "La EPS dirá: 'no hay contrato firmado'",
            "respuesta_sugerida": (
                "Aportar minuta o acta de negociación tarifaria firmada "
                "por ambas partes. Art. 871 C.Comercio: la buena fe "
                "contractual rige aún sin formalidades estrictas."
            ),
        },
    ],
    "FA": [
        {
            "titulo": "La EPS dirá: 'falta soporte de la prestación'",
            "respuesta_sugerida": (
                "Aportar historia clínica completa (Res. 1995/1999 — "
                "plena prueba), RIPS radicados (Res. 866/2021), factura "
                "electrónica (Res. 2275/2023)."
            ),
        },
        {
            "titulo": "La EPS dirá: 'errores formales en facturación'",
            "respuesta_sugerida": (
                "Circular 030/2013: los errores formales son subsanables, "
                "no causan glosa válida. La prestación efectiva del "
                "servicio genera obligación de pago."
            ),
        },
    ],
    "SO": [
        {
            "titulo": "La EPS dirá: 'soportes insuficientes'",
            "respuesta_sugerida": (
                "Historia clínica institucional como plena prueba "
                "(Res. 1995/1999). EPS tuvo 20 días hábiles para objetar "
                "(Art. 57 Ley 1438/2011) — no puede solicitar más "
                "soportes en conciliación."
            ),
        },
    ],
    "AU": [
        {
            "titulo": "La EPS dirá: 'no había autorización previa'",
            "respuesta_sugerida": (
                "Atención por urgencia vital — Art. 168 Ley 100/1993 + "
                "Sentencia T-1025/2002: las urgencias no requieren "
                "autorización. Mostrar registro de triage."
            ),
        },
    ],
    "CL": [
        {
            "titulo": "La EPS dirá: 'no hay pertinencia clínica'",
            "respuesta_sugerida": (
                "Autonomía médica protegida por Art. 17 Ley 1751/2015. "
                "El criterio del médico tratante prevalece. La historia "
                "clínica soporta la decisión clínica."
            ),
        },
    ],
}


def preparar_audiencia(
    db,
    glosa_id: int,
) -> dict:
    """Prepara material táctico para la audiencia de conciliación de una
    glosa específica.

    Devuelve:
      {
        "glosa_id": int,
        "codigo_glosa": str,
        "eps": str,
        "valor_objetado": float,
        "estadistica_eps": {
          "n_audiencias_previas": int,
          "tasa_levantamiento_pct": float | None,
          "patron_eps": "agresiva" | "negociadora" | "indecisa" | "sin_datos",
        },
        "contraargumentos": [
          {"titulo": str, "respuesta_sugerida": str, "frecuencia_estimada": "alta"|"media"|"baja"},
          ...
        ],
        "valor_minimo_aceptable": float,    # 0 si conviene defender íntegramente
        "recomendacion_tactica": str,       # texto plano corto
        "normas_clave": [str, ...],         # las 3-5 más relevantes
      }
    """
    from app.models.db import GlosaRecord
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        return {"error": "Glosa no encontrada"}

    codigo = (g.codigo_glosa or "").upper()
    tipo = codigo[:2] if len(codigo) >= 2 else ""
    eps = g.eps or ""
    valor = float(g.valor_objetado or 0)

    # Histórico de la EPS para este tipo de código
    historico = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .filter(GlosaRecord.codigo_glosa.startswith(tipo))
        .filter(GlosaRecord.estado.in_(["LEVANTADA", "ACEPTADA", "RATIFICADA"]))
        .limit(200)
        .all()
    )
    n_prev = len(historico)
    n_lev = sum(1 for h in historico if (h.estado or "").upper() == "LEVANTADA")
    n_rat = sum(1 for h in historico if (h.estado or "").upper() == "RATIFICADA")
    tasa = round(100 * n_lev / n_prev, 1) if n_prev else None

    if n_prev < 3:
        patron = "sin_datos"
    elif tasa >= 65:
        patron = "negociadora"
    elif tasa <= 30:
        patron = "agresiva"
    else:
        patron = "indecisa"

    contras = list(_CONTRAARGUMENTOS_PLANTILLA.get(tipo, []))
    # Marcar frecuencia estimada según patrón
    for c in contras:
        c["frecuencia_estimada"] = (
            "alta" if patron == "agresiva" else
            "media" if patron == "indecisa" else
            "baja"
        )

    # Recomendación táctica
    if patron == "negociadora" or (tasa is not None and tasa >= 65):
        recomendacion = (
            f"Esta EPS levantó el {tasa:.0f}% de glosas {tipo}* en el pasado. "
            "Llegar con tono conciliador y argumentos sólidos. Probabilidad "
            "alta de levantamiento si presentás soportes completos."
        )
        valor_min = 0.0
    elif patron == "agresiva":
        recomendacion = (
            f"Esta EPS solo levantó el {tasa:.0f}% de glosas {tipo}*. "
            "Llegar con tono firme y la batería normativa completa. "
            "Si la EPS ofrece levantar parcial 70%+, considerar aceptar "
            "para evitar escalamiento a SuperSalud."
        )
        valor_min = round(valor * 0.30, 2)
    elif patron == "indecisa":
        recomendacion = (
            f"Esta EPS tiene patrón mixto ({tasa:.0f}% levantamiento). "
            "Tono neutral. Si insiste, valor mínimo aceptable 50%."
        )
        valor_min = round(valor * 0.50, 2)
    else:
        recomendacion = (
            "Sin histórico suficiente con esta EPS para predecir. "
            "Tono conciliador inicial; ajustar según reacción."
        )
        valor_min = 0.0

    # Normas clave por tipo de glosa
    normas_por_tipo = {
        "TA": [
            "Art. 1602 C.Civil (contrato como ley entre partes)",
            "Art. 871 C.Comercio (buena fe contractual)",
            "Circular 047/2025 MinSalud (Manual SOAT 2026 indexado a UVB)",
            "Res. 2284/2023 (Manual Único de Glosas)",
        ],
        "FA": [
            "Circular 030/2013 (errores formales subsanables)",
            "Art. 177 Ley 100/1993 (deber EPS de pagar)",
            "Res. 2275/2023 (factura electrónica)",
        ],
        "SO": [
            "Res. 1995/1999 (historia clínica como plena prueba)",
            "Art. 57 Ley 1438/2011 (plazo 20 días EPS para glosar)",
        ],
        "AU": [
            "Art. 168 Ley 100/1993 (urgencias)",
            "Sentencia T-1025/2002 (urgencias sin autorización previa)",
            "Res. 5269/2017 (PBS)",
        ],
        "CL": [
            "Art. 17 Ley 1751/2015 (autonomía médica)",
            "Sentencia T-760/2008 (obligaciones EPS)",
        ],
    }

    return {
        "glosa_id": g.id,
        "codigo_glosa": codigo,
        "eps": eps,
        "valor_objetado": valor,
        "estadistica_eps": {
            "n_audiencias_previas": n_prev,
            "n_levantadas": n_lev,
            "n_ratificadas": n_rat,
            "tasa_levantamiento_pct": tasa,
            "patron_eps": patron,
        },
        "contraargumentos": contras,
        "valor_minimo_aceptable": valor_min,
        "recomendacion_tactica": recomendacion,
        "normas_clave": normas_por_tipo.get(tipo, [
            "Art. 57 Ley 1438/2011",
            "Art. 20 Decreto 4747/2007",
            "Res. 2284/2023 (Manual Único)",
        ]),
    }
