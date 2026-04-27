"""Generador de dictamen DIRECTO sin LLM (R-cerebro #10).

Cuando el auditor pre-IA detecta inconsistencias contundentes y
tenemos TODOS los datos del caso (valor objetado, contrato, cups,
hallazgos con score >= 80), podemos emitir un dictamen completo
SIN llamar a Claude — usando una plantilla curada que cumple las
mismas reglas estructurales que el system prompt:

  • Apertura "ESE HUS NO ACEPTA..." obligatoria.
  • 4 párrafos con la estructura del system prompt.
  • Refutación punto a punto de los hallazgos del auditor.
  • Cita literal de norma (Art. 1602 C.C. + Art. 871 C.Com.).
  • Régimen especial (Sanidad Militar) cuando aplica.
  • Cierre con escalera procesal + emails institucionales.

Filosofía:
  • SOLO se activa con criterios ESTRICTOS — si hay duda, ir al LLM.
  • La calidad del dictamen no debe ser inferior a la del LLM.
  • Si la plantilla no produce dictamen válido (datos faltantes,
    error de formato), retorna None y se cae al LLM normal.
"""
from __future__ import annotations

import re
from typing import Optional


_NOMBRE_TIPO = {
    "TA": "TARIFAS", "SO": "SOPORTES", "AU": "AUTORIZACIÓN",
    "CO": "COBERTURA", "CL": "PERTINENCIA CLÍNICA",
    "PE": "PERTINENCIA CLÍNICA", "FA": "FACTURACIÓN",
    "IN": "INSUMOS", "ME": "MEDICAMENTOS",
}


def puede_emitir_directo(
    auditoria: dict,
    *,
    codigo: str,
    eps: str,
    cups: Optional[str],
    valor_objetado: float,
    valor_facturado: float,
    valor_pactado: float,
    tiene_contrato: bool,
    numero_contrato: Optional[str],
    accion_excedente: Optional[str] = None,
) -> bool:
    """¿Tenemos todo para emitir dictamen sin LLM con calidad equivalente?

    Criterios estrictos (TODOS deben cumplirse):

      1. Auditor: score >= 70 + acción DEFENDER_FUERTE.
      2. Caso es DEFENDER_TOTAL puro (no excedente, no aceptar):
            facturado <= pactado AND no hay accion_excedente.
      3. Hay contrato y número de contrato.
      4. Hay valor objetado conocido (>0 con dígitos).
      5. Hay CUPS válido.
      6. Código tiene prefijo conocido (TA/SO/AU/CO/CL/FA).
      7. Hay AL MENOS UN hallazgo de severidad ALTA.

    Si falla alguno, retornamos False y se va al LLM.
    """
    if not auditoria:
        return False
    score = int(auditoria.get("score_evidencia", 0))
    n_alta = int(auditoria.get("n_hallazgos_alta", 0) or 0)
    accion = (auditoria.get("accion_sugerida") or "").upper()
    # Combinación: score alto O 2+ hallazgos de severidad ALTA. La
    # acción debe ser DEFENDER_FUERTE o DEFENDER en cualquier caso.
    contundente = (score >= 70) or (n_alta >= 2)
    if not contundente:
        return False
    if accion not in ("DEFENDER_FUERTE", "DEFENDER"):
        return False
    if n_alta < 1:
        return False
    # No emitir directo si hay caso excedente — el LLM redacta mejor
    # respuestas mixtas con tono conciliador adaptado.
    if accion_excedente in ("ACEPTAR_PARCIAL", "ACEPTAR_TOTAL"):
        return False
    if valor_facturado > 0 and valor_pactado > 0 and valor_facturado > valor_pactado:
        return False
    # Datos mínimos
    if not tiene_contrato or not numero_contrato:
        return False
    if not cups or not str(cups).strip() or "INDICADO" in str(cups).upper():
        return False
    if valor_objetado <= 0:
        return False
    if not codigo or len(codigo) < 4:
        return False
    pref = codigo[:2].upper()
    if pref not in _NOMBRE_TIPO:
        return False
    return True


def _formato_pesos(v: float) -> str:
    if not v or v <= 0:
        return "EL VALOR INDICADO EN EL EXPEDIENTE"
    return f"${int(v):,}".replace(",", ".")


def _es_sanidad_militar(eps: str) -> bool:
    e = (eps or "").upper()
    return any(k in e for k in (
        "DISPENSARIO MEDICO", "DIGSA", "FORMA",
        "SANIDAD MILITAR", "FUERZAS MILITARES",
        "DMBUG", "BSALUD", "CERMI",
    ))


def _refutaciones_de_hallazgos(hallazgos: list, max_n: int = 3) -> list:
    """Convierte hallazgos en frases conectadas para el párrafo 2."""
    frases = []
    contrato_hecho = False
    for h in (hallazgos or [])[:max_n]:
        hid = h.get("id", "")
        sev = h.get("severidad", "MEDIA")
        if sev not in ("ALTA", "MEDIA"):
            continue
        if hid == "afirmacion_sin_contrato_falsa" and not contrato_hecho:
            frases.append(
                "LA AFIRMACIÓN DE QUE NO EXISTE CONTRATO ENTRE LAS "
                "PARTES NO SE AJUSTA A LA REALIDAD DOCUMENTAL: "
                "EL CONTRATO SUSCRITO ENTRE LAS PARTES SE ENCUENTRA "
                "VIGENTE Y LA TARIFA APLICABLE OBRA EN EL TARIFARIO "
                "INSTITUCIONAL INCORPORADO AL ACUERDO"
            )
            contrato_hecho = True
        elif hid == "soat_sustituto_indebido":
            frases.append(
                "LA SUSTITUCIÓN UNILATERAL DE LA TARIFA PACTADA POR "
                "SOAT VIGENTE CARECE DE RESPALDO CONTRACTUAL — EL "
                "SOAT OPERA EN AUSENCIA DE PACTO Y NO COMO CRITERIO "
                "ALTERNATIVO CUANDO EL CONTRATO YA FIJÓ TARIFA"
            )
        elif hid == "afirmacion_sin_tarifa_falsa":
            frases.append(
                "LA AFIRMACIÓN DE QUE NO EXISTE TARIFA PACTADA TAMPOCO "
                "SE AJUSTA A LA REALIDAD: EL VALOR PACTADO PARA EL "
                "SERVICIO FACTURADO OBRA EN EL TARIFARIO INSTITUCIONAL "
                "DEL CONTRATO Y ES VERIFICABLE EN AUTOS"
            )
        elif hid == "diferencia_sin_referente":
            frases.append(
                "LA OBJECIÓN POR \"DIFERENCIA\" SIN ACREDITAR EL "
                "REFERENTE TARIFARIO APLICADO INCUMPLE EL DEBER DE "
                "MOTIVACIÓN ESTABLECIDO EN LA RESOLUCIÓN 2284 DE 2023, "
                "QUE EXIGE PRECISIÓN EN LA OBJECIÓN"
            )
        elif hid == "historia_aportada_objetada":
            frases.append(
                "LA HISTORIA CLÍNICA OBRA EN AUTOS Y CONSTITUYE PLENA "
                "PRUEBA MÉDICO-LEGAL CONFORME A LA RESOLUCIÓN 1995 DE "
                "1999, POR LO QUE LA AFIRMACIÓN DE \"FALTA\" CARECE DE "
                "FUNDAMENTO FÁCTICO"
            )
    return frases


def generar_dictamen_directo(
    auditoria: dict,
    *,
    codigo: str,
    eps: str,
    cups: str,
    servicio: str,
    valor_objetado: float,
    valor_facturado: float,
    valor_pactado: float,
    numero_contrato: str,
    paciente: str = "PACIENTE IDENTIFICADO EN EXPEDIENTE",
) -> Optional[str]:
    """Genera XML completo siguiendo el contrato del system prompt.

    Devuelve None si por algún motivo no se puede armar (datos
    faltantes, hallazgos sin frases mapeables, etc.) — el caller
    debe caer al LLM normal.
    """
    pref = (codigo[:2] or "").upper()
    nombre_tipo = _NOMBRE_TIPO.get(pref, "FACTURACIÓN")
    eps_clean = (eps or "").strip().upper()
    cups_clean = (cups or "").strip().upper()
    servicio_clean = (servicio or "").strip().upper() or "EL SERVICIO IDENTIFICADO"
    if len(servicio_clean) > 160:
        servicio_clean = servicio_clean[:160].rsplit(" ", 1)[0]
    obj_str = _formato_pesos(valor_objetado)
    fact_str = _formato_pesos(valor_facturado) if valor_facturado > 0 else None

    # Refutaciones del párrafo 2. Limitamos a 2 para que el dictamen
    # quede dentro del rango de longitud (con cita literal Art. 1602
    # + bloque Sanidad Militar el P3 ya pesa ~120 palabras).
    refutaciones = _refutaciones_de_hallazgos(
        auditoria.get("hallazgos") or [], max_n=2,
    )
    if not refutaciones:
        return None

    # ── PÁRRAFO 1 — IDENTIFICACIÓN
    if fact_str and fact_str != "EL VALOR INDICADO EN EL EXPEDIENTE":
        valor_p1 = (
            f"FACTURADO POR {fact_str}, RESPECTO DEL CUAL LA "
            f"ENTIDAD PAGADORA OBJETA {obj_str}"
        )
    else:
        valor_p1 = f"RESPECTO DEL CUAL LA ENTIDAD PAGADORA OBJETA {obj_str}"

    p1 = (
        f"ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE "
        f"{nombre_tipo} SOBRE EL CÓDIGO {codigo.upper()}, INTERPUESTA "
        f"POR {eps_clean}, RESPECTO DEL SERVICIO IDENTIFICADO CON "
        f"CUPS {cups_clean}, {valor_p1}."
    )

    # ── PÁRRAFO 2 — REFUTACIÓN FÁCTICA ENUMERADA
    conectores = ["EN PRIMER LUGAR", "EN SEGUNDO LUGAR", "EN TERCER LUGAR"]
    razones = []
    for i, frase in enumerate(refutaciones[:2]):
        razones.append(f"{conectores[i]}, {frase}")
    p2 = (
        "LA AFIRMACIÓN DE LA AUDITORÍA NO SE AJUSTA AL MARCO "
        "CONTRACTUAL POR LAS SIGUIENTES RAZONES: "
        + "; ".join(razones)
        + "."
    )

    # ── PÁRRAFO 3 — FUNDAMENTO NORMATIVO
    pacto_pesos = (
        _formato_pesos(valor_pactado)
        if valor_pactado > 0
        else "LO PACTADO EN EL CONTRATO"
    )
    norma_extra = ""
    if _es_sanidad_militar(eps_clean):
        norma_extra = (
            " TRATÁNDOSE DE POBLACIÓN DEL SUBSISTEMA DE SALUD DE LAS "
            "FUERZAS MILITARES, EL DECRETO 1795 DE 2000 Y EL ACUERDO "
            "002 DE 2001 DEL CONSEJO SUPERIOR DE SALUD DE LAS FUERZAS "
            "MILITARES REAFIRMAN QUE LA REMUNERACIÓN A LAS IPS SE RIGE "
            "POR LAS TARIFAS DEL CONTRATO INTERADMINISTRATIVO SUSCRITO."
        )
    p3 = (
        f"DE CONFORMIDAD CON EL ARTÍCULO 1602 DEL CÓDIGO CIVIL, "
        f"«TODO CONTRATO LEGALMENTE CELEBRADO ES UNA LEY PARA LOS "
        f"CONTRATANTES, Y NO PUEDE SER INVALIDADO SINO POR SU "
        f"CONSENTIMIENTO MUTUO O POR CAUSAS LEGALES», DE MODO QUE LA "
        f"TARIFA APLICABLE AL SERVICIO ES LA PACTADA EN EL CONTRATO "
        f"No. {numero_contrato} ({pacto_pesos}), SIN QUE SEA "
        f"ADMISIBLE MODIFICARLA UNILATERALMENTE EN VÍA DE GLOSA. "
        f"EL ARTÍCULO 871 DEL CÓDIGO DE COMERCIO REAFIRMA EL DEBER DE "
        f"EJECUCIÓN DE BUENA FE.{norma_extra}"
    )

    # ── PÁRRAFO 4 — PETICIÓN + ESCALERA + CONTACTO
    p4 = (
        f"EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE A LA "
        f"ENTIDAD PAGADORA EL LEVANTAMIENTO ÍNTEGRO DE LA GLOSA "
        f"{codigo.upper()} Y EL RECONOCIMIENTO DEL VALOR OBJETADO. "
        f"LA ENTIDAD PAGADORA CUENTA CON 10 DÍAS HÁBILES PARA "
        f"PRONUNCIARSE CONFORME AL ARTÍCULO 57 DE LA LEY 1438 DE "
        f"2011; DE NO HACERLO, OPERARÁ EL SILENCIO A FAVOR DEL "
        f"PRESTADOR. EN SUBSIDIO, SE INVITA A MESA DE CONCILIACIÓN "
        f"DE AUDITORÍA CONFORME AL ARTÍCULO 20 DEL DECRETO 4747 DE "
        f"2007. COMUNICACIONES: CARTERA@HUS.GOV.CO, "
        f"GLOSASYDEVOLUCIONES@HUS.GOV.CO."
    )

    argumento = "\n\n".join([p1, p2, p3, p4])
    n_palabras = len(argumento.split())
    # Salvaguarda: si la plantilla terminó muy corta o muy larga,
    # mejor caer al LLM (que tiene más libertad para ajustar).
    if n_palabras < 130 or n_palabras > 340:
        return None

    normas_clave = (
        "Art. 1602 Código Civil | Art. 871 Código de Comercio"
        + (" | Decreto 1795/2000 + Acuerdo 002/2001 FF.MM."
           if _es_sanidad_militar(eps_clean) else
           " | Resolución 2284/2023")
    )

    xml = (
        f"<paciente>{paciente}</paciente>"
        f"<servicio>{servicio_clean} — CUPS {cups_clean}</servicio>"
        f"<contrato>CONTRATO No. {numero_contrato}</contrato>"
        f"<tarifa>TARIFA PACTADA EN CONTRATO — "
        f"{_formato_pesos(valor_pactado) if valor_pactado > 0 else 'según tarifario institucional'}"
        f"</tarifa>"
        f"<accion>DEFENDER_TOTAL</accion>"
        f"<valor_aceptar>0</valor_aceptar>"
        f"<valor_defender>{int(valor_objetado)}</valor_defender>"
        f"<normas_clave>{normas_clave}</normas_clave>"
        f"<argumento>{argumento}</argumento>"
    )
    return xml
