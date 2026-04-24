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

    Orden de matching (Ronda 45 — Res. 2641/2025):
      1. Match directo por codigo_cups
      2. Match por codigo_ips (código interno del prestador cargado
         desde el Excel del contrato, ej. '39147B-18' del HUS)
      3. Homologación Res. 2641/2025 → rebusca por CUPS oficial
    """
    if not eps or not cups:
        return None
    eps = eps.strip()
    cups = cups.strip()
    if not eps or not cups:
        return None

    # 1) Match directo por CUPS oficial
    fila = (
        db.query(TarifaContratadaRecord)
        .filter(TarifaContratadaRecord.activa == 1)
        .filter(TarifaContratadaRecord.eps.ilike(f"%{eps}%"))
        .filter(TarifaContratadaRecord.codigo_cups == cups)
        .order_by(TarifaContratadaRecord.creado_en.desc())
        .first()
    )
    if fila:
        return fila

    # 2) Match por codigo_ips (cargado desde columna 'CODIGO IPS' del Excel)
    fila = (
        db.query(TarifaContratadaRecord)
        .filter(TarifaContratadaRecord.activa == 1)
        .filter(TarifaContratadaRecord.eps.ilike(f"%{eps}%"))
        .filter(TarifaContratadaRecord.codigo_ips == cups)
        .order_by(TarifaContratadaRecord.creado_en.desc())
        .first()
    )
    if fila:
        return fila

    # 3) Homologación Res. 2641/2025 — si el código entrada es viejo, lo
    # traducimos al CUPS oficial y reintentamos.
    try:
        from app.services.homologador_cups import homologar_cups
        homo = homologar_cups(cups, db=db, eps=eps)
        if homo and homo.get("cups_oficial") and homo["cups_oficial"] != cups:
            fila = (
                db.query(TarifaContratadaRecord)
                .filter(TarifaContratadaRecord.activa == 1)
                .filter(TarifaContratadaRecord.eps.ilike(f"%{eps}%"))
                .filter(TarifaContratadaRecord.codigo_cups == homo["cups_oficial"])
                .order_by(TarifaContratadaRecord.creado_en.desc())
                .first()
            )
            if fila:
                return fila
    except Exception:
        pass

    return None


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


def _recomendacion(
    valor_facturado: float,
    valor_pactado: float,
    valor_objetado: float,
    *,
    es_soat_pct: bool = False,
    factor_pct: float = 0.0,
    valor_reconocido: float = 0.0,
) -> dict:
    """Compara facturado vs pactado y sugiere acción.

    Reglas VALOR_FIJO:
      - facturado == pactado (±$1) → glosa INJUSTIFICADA (defender 100%)
      - facturado > pactado, diferencia cabe en objetado → aceptar parcial
      - facturado < pactado → defender (cobró menos del pactado)
      - diferencia excede objetado → revisar manualmente

    Reglas SOAT_PORCENTAJE:
      - Si no conocemos valor SOAT base, no podemos calcular el pactado
        absoluto; pero si tenemos `valor_facturado` y `valor_reconocido`
        podemos comparar las **interpretaciones** de SOAT base de cada parte
        y recomendar DEFENDER (ambas aplican el mismo factor; la
        discrepancia es sobre la tarifa SOAT oficial del CUPS).
    """
    tolerancia = 1.0

    # Rama SOAT_PORCENTAJE: siempre inferir SOAT base implícito de HUS y EPS
    # desde los valores facturado/reconocido, y explicar la discrepancia.
    if es_soat_pct:
        multiplicador = 1 + factor_pct / 100.0
        soat_base_hus = (valor_facturado / multiplicador) if (valor_facturado > 0 and multiplicador > 0) else 0.0
        soat_base_eps = (valor_reconocido / multiplicador) if (valor_reconocido > 0 and multiplicador > 0) else 0.0
        signo = "+" if factor_pct > 0 else ""
        if valor_facturado > 0 and valor_reconocido > 0:
            return {
                "accion": "DEFENDER_TOTAL",
                "titulo": "✅ Defender (discrepancia sobre SOAT base, no sobre descuento)",
                "razon": (
                    f"Contrato pactado: SOAT {signo}{factor_pct:.0f}%. HUS facturó "
                    f"${valor_facturado:,.0f}, lo que implica valor SOAT base "
                    f"${soat_base_hus:,.0f} para el CUPS. La EPS reconoce "
                    f"${valor_reconocido:,.0f} (implica SOAT base ${soat_base_eps:,.0f}). "
                    "Ambas partes aplican el mismo descuento pactado — el conflicto "
                    "es sobre la tarifa SOAT oficial del CUPS. Verificar Circular "
                    "Externa 047/2025 MinSalud (Manual SOAT 2026 indexado a UVB — "
                    "UVB 2026 = $12.110) y el Decreto 780/2016; si HUS aplicó el "
                    f"SOAT correcto, defender íntegramente los ${valor_facturado:,.0f}."
                ),
                "valor_a_defender": valor_objetado,
                "valor_a_aceptar": 0.0,
                "diferencia": valor_objetado,
                "soat_base_hus": soat_base_hus,
                "soat_base_eps": soat_base_eps,
            }
        return {
            "accion": "REVISAR",
            "titulo": "❔ SOAT base no identificado",
            "razon": (
                f"Contrato pactado: SOAT {signo}{factor_pct:.0f}%. No se extrajo "
                "facturado/reconocido del texto y el valor SOAT base del CUPS no "
                "está cargado. Revisar manualmente la Circular 047/2025 MinSalud "
                "(Manual SOAT 2026 indexado a UVB — UVB 2026 = $12.110) y "
                f"calcular tarifa pactada = Tarifa_UVB × $12.110 × {multiplicador:.3f}."
            ),
            "valor_a_defender": valor_objetado,
            "valor_a_aceptar": 0.0,
            "diferencia": 0.0,
            "soat_base_hus": soat_base_hus,
            "soat_base_eps": soat_base_eps,
        }

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
    valor_reconocido: float = 0.0,
) -> dict:
    """Evalúa una glosa TA contra la tarifa pactada.

    Cuando el tipo es SOAT_PORCENTAJE y no conocemos el SOAT base, pero sí
    tenemos valor_facturado (lo que HUS cobró), asumimos que HUS aplicó
    correctamente el manual SOAT y calculamos pactado implícito.
    """
    tarifa = _buscar(db, eps, cups)
    if tarifa is None:
        return {
            "encontrada": False,
            "tarifa": None,
            "valor_facturado": valor_facturado,
            "valor_objetado": valor_objetado,
            "valor_reconocido": valor_reconocido,
            "valor_pactado_calc": 0.0,
            "recomendacion": None,
        }

    # Ronda 47 fix: si la glosa solo trae valor_objetado (lo que la EPS
    # reconoció de menos) y no el facturado, asumimos facturado = objetado
    # porque lo típico es que la EPS objete el monto completo. Esto corrige
    # el mensaje engañoso "El hospital facturó $0".
    if valor_facturado <= 0 and valor_objetado > 0:
        valor_facturado = valor_objetado

    tipo = tarifa.tipo_tarifa or "VALOR_FIJO"
    factor_pct = float(tarifa.factor_ajuste or 0.0)
    es_soat_pct = tipo == "SOAT_PORCENTAJE"

    # Para SOAT%, si no pasaron SOAT base pero sí tenemos facturado,
    # asumir facturado = SOAT_base × (1+factor/100) → pactado = facturado
    # (porque HUS ya aplicó el descuento al facturar).
    if es_soat_pct and valor_soat_base <= 0 and valor_facturado > 0:
        valor_soat_base = valor_facturado / (1 + factor_pct / 100.0)

    valor_pactado_calc = calcular_valor_pactado(tarifa, valor_soat_base=valor_soat_base)

    recomendacion = _recomendacion(
        valor_facturado,
        valor_pactado_calc,
        valor_objetado,
        es_soat_pct=es_soat_pct,
        factor_pct=factor_pct,
        valor_reconocido=valor_reconocido,
    )

    # Ronda 45: detectar si el match fue por homologación (el cups del auditor
    # no coincide con codigo_cups de la tarifa encontrada → sí es homologación).
    homologado = False
    cups_entrada = (cups or "").strip().upper()
    cups_encontrado = (tarifa.codigo_cups or "").upper()
    cod_ips_encontrado = (getattr(tarifa, "codigo_ips", None) or "").upper()
    if cups_entrada and cups_entrada != cups_encontrado:
        homologado = True

    return {
        "encontrada": True,
        "tarifa": {
            "id": tarifa.id,
            "eps": tarifa.eps,
            "codigo_cups": tarifa.codigo_cups,
            "codigo_ips": getattr(tarifa, "codigo_ips", None),
            "descripcion": tarifa.descripcion,
            "contrato_numero": tarifa.contrato_numero,
            "valor_pactado": float(tarifa.valor_pactado or 0.0),
            "tipo_tarifa": tipo,
            "factor_ajuste": factor_pct,
            "modalidad": tarifa.modalidad,
            "fuente_archivo": tarifa.fuente_archivo,
            "vigencia_desde": tarifa.vigencia_desde.isoformat() if tarifa.vigencia_desde else None,
            "vigencia_hasta": tarifa.vigencia_hasta.isoformat() if tarifa.vigencia_hasta else None,
        },
        "valor_facturado": valor_facturado,
        "valor_objetado": valor_objetado,
        "valor_reconocido": valor_reconocido,
        "valor_pactado_calc": valor_pactado_calc,
        "recomendacion": recomendacion,
        "homologacion_2641": {
            "aplicada": homologado,
            "codigo_entrada": cups_entrada,
            "codigo_ips_contrato": cod_ips_encontrado,
            "cups_oficial": cups_encontrado,
            "norma": "Res. 2641/2025 MinSalud — CUPS 2025",
        } if homologado else None,
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
