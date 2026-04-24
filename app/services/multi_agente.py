"""Arquitectura multi-agente para dictámenes jurídicos premium.

Ronda 6 de la visión premium. En lugar de UN prompt genérico, dividimos
la tarea en agentes especializados que colaboran:

  - Agente JURÍDICO: cita normas, artículos, jurisprudencia correcta
  - Agente CLÍNICO: valida pertinencia médica, interpreta HC y CUPS
  - Agente TARIFARIO: calcula UVB/SMDLV/factor SOAT con precisión
  - Agente CONCILIADOR: ajusta tono, estructura, cierres formales

Un ORQUESTADOR combina las salidas en un único dictamen coherente.

Diseño sobrio: NO duplicamos llamadas a IA por cada agente (eso sería
4x el costo). Los "agentes" son funciones Python deterministas que
enriquecen el PROMPT antes de UNA sola llamada al LLM. El LLM recibe
el prompt aumentado con todos los insumos de los agentes.

Beneficios:
  - Mejor calidad sin multiplicar costo
  - Cada agente evoluciona independientemente
  - Debugging más fácil: si falla la cita normativa, revisas SOLO el
    agente jurídico
  - Caché IA se mantiene efectivo (mismo flujo = mismo hash)
"""
from __future__ import annotations

import re


# ─── Agente Jurídico ────────────────────────────────────────────────────────

def agente_juridico(codigo_glosa: str, eps: str, etapa: str) -> dict:
    """Devuelve citas normativas especializadas según tipo de glosa + contexto.

    Output: dict con:
      - normas_primarias: lista de citas CLAVE que la IA DEBE usar
      - normas_secundarias: refuerzos opcionales
      - jurisprudencia: sentencias relevantes
      - evitar: citas prohibidas para este caso (ej. NO T-760 en FF.MM.)
    """
    prefijo = (codigo_glosa or "")[:2].upper()
    eps_up = (eps or "").upper()
    es_ratif = "RATIF" in (etapa or "").upper()

    resultado = {
        "normas_primarias": [],
        "normas_secundarias": [],
        "jurisprudencia": [],
        "evitar": [],
    }

    # Base común para toda glosa: Ley 1438 Art. 56/57 + Manual Único
    resultado["normas_primarias"].append(
        "Ley 1438/2011 Art. 56 y 57 (plazos EPS/IPS para glosas y conciliación)"
    )
    resultado["normas_primarias"].append(
        "Resolución 2284/2023 MinSalud (Manual Único de Glosas — códigos taxativos)"
    )

    # Especializado por tipo
    if prefijo == "TA":  # Tarifas
        resultado["normas_primarias"].append(
            "Art. 871 Código de Comercio (buena fe en la celebración y ejecución del contrato)"
        )
        resultado["normas_primarias"].append(
            "Art. 1602 Código Civil (contrato legalmente celebrado es ley para las partes)"
        )
        resultado["normas_secundarias"].append(
            "Circular Externa 047 de 2025 MinSalud (Manual Tarifario SOAT 2026 indexado a UVB; "
            "UVB 2026 = $12.110)"
        )
        resultado["normas_secundarias"].append(
            "Decreto 780 de 2016 (marco general sector salud)"
        )
        resultado["evitar"].append(
            "T-1025/2002 (pertinencia en urgencias) — NO aplica a controversia tarifaria"
        )
        resultado["evitar"].append(
            "T-478/1995 (autonomía médica) — NO aplica a tarifas"
        )
    elif prefijo == "SO":  # Soportes
        resultado["normas_primarias"].append(
            "Resolución 1995 de 1999 Art. 3 (historia clínica como documento de plena prueba médico-legal)"
        )
        resultado["normas_primarias"].append(
            "Resolución 866 de 2021 (RIPS — soportes electrónicos)"
        )
        resultado["normas_secundarias"].append(
            "Circular 030 de 2013 MinSalud (errores formales subsanables en la facturación)"
        )
    elif prefijo == "AU":  # Autorización
        resultado["normas_primarias"].append(
            "Art. 168 Ley 100 de 1993 (atención inicial de urgencias sin autorización previa)"
        )
        resultado["jurisprudencia"].append(
            "Sentencia T-1025/2002 (autorización posterior en urgencias)"
        )
    elif prefijo in ("CL", "PE"):  # Pertinencia clínica
        resultado["normas_primarias"].append(
            "Art. 17 Ley 1751 de 2015 (autonomía médica)"
        )
        resultado["jurisprudencia"].append(
            "Sentencia T-478/1995 (autonomía profesional en decisiones clínicas)"
        )
    elif prefijo == "CO":  # Cobertura
        resultado["normas_primarias"].append(
            "Resolución 5269 de 2017 (PBS — Plan de Beneficios en Salud)"
        )
        resultado["normas_primarias"].append(
            "Art. 2 Ley 1751/2015 (derecho fundamental a la salud)"
        )
    elif prefijo == "FA":  # Facturación
        resultado["normas_primarias"].append(
            "Resolución 2275 de 2023 (factura electrónica de venta)"
        )
        resultado["normas_secundarias"].append(
            "Circular 030 de 2013 (errores formales subsanables)"
        )

    # Régimenes especiales
    if any(k in eps_up for k in ("FOMAG", "FUERZAS", "PPL", "POLICIA", "SANIDAD", "DISPENSARIO")):
        resultado["normas_primarias"].append(
            "Decreto 1795 de 2000 (Subsistema de Salud de las Fuerzas Militares)"
        )
        resultado["normas_primarias"].append(
            "Acuerdo 002 de 2001 Consejo Superior de Salud de las Fuerzas Militares"
        )
        resultado["evitar"].append(
            "T-760/2008 — Esa sentencia regula el sistema general SGSSS, no aplica a FF.MM."
        )

    # Ratificación: agregar cita de conciliación obligatoria
    if es_ratif:
        resultado["normas_primarias"].append(
            "Art. 20 Decreto 4747 de 2007 (mesa de conciliación de auditoría)"
        )

    return resultado


# ─── Agente Clínico ─────────────────────────────────────────────────────────

def agente_clinico(cups: str, servicio: str, tipo_servicio: str = "") -> dict:
    """Analiza pertinencia clínica: es urgencia, ambulatorio, hospitalario,
    diagnóstico, procedimiento. Informa a la IA qué soportes justificarían
    el servicio.

    Output:
      - categoria: URGENCIA | CONSULTA | APOYO_DX | HOSPITALARIO | CIRUGIA | OTRO
      - soportes_esperados: lista textual
      - justificacion_inherente: bool (si el servicio justifica por sí mismo)
    """
    s = (servicio or "").upper()
    c = (cups or "").upper()

    categoria = "OTRO"
    soportes = ["Historia clínica institucional", "RIPS radicados", "Factura electrónica"]
    inherente = False

    if any(k in s for k in ("URGENCIA", "URGENTE", "EMERGENCIA")):
        categoria = "URGENCIA"
        soportes.append("Epicrisis o resumen de atención de urgencias")
        inherente = True
    elif "CONSULTA" in s:
        categoria = "CONSULTA"
        soportes.append("Nota de consulta médica especializada o general")
    elif any(k in s for k in ("ESTUDIO", "RADIOGRAF", "TOMOGRAF", "RESONAN", "ECOGRAF", "BIOPSIA", "LABORATORIO")):
        categoria = "APOYO_DX"
        soportes.append("Orden médica + resultado del estudio")
    elif any(k in s for k in ("CIRUG", "PROCEDIMIENTO", "ABLACION", "IMPLANT", "RESEC", "ARTROD")):
        categoria = "CIRUGIA"
        soportes.append("Descripción quirúrgica + nota operatoria")
        soportes.append("Consentimiento informado")
    elif any(k in s for k in ("HOSPITALIZ", "INTERNACION", "ESTANCIA")):
        categoria = "HOSPITALARIO"
        soportes.append("Historia de hospitalización + epicrisis de egreso")

    # Sufijo H (tarifa institucional propia) → agregar referencia específica
    if c.endswith("H") or re.search(r"H\d$", c):
        soportes.append("Referencia a Resolución 054/2026 + 124/2026 ESE HUS (código IPS propio)")

    return {
        "categoria": categoria,
        "soportes_esperados": soportes,
        "justificacion_inherente": inherente,
    }


# ─── Agente Tarifario ───────────────────────────────────────────────────────

def agente_tarifario(
    modalidad: str,
    factor_ajuste: float = 0.0,
    valor_pactado: float = 0.0,
    tipo_tarifa: str = "VALOR_FIJO",
    valor_facturado: float = 0.0,
    valor_reconocido: float = 0.0,
) -> dict:
    """Calcula SOAT/SMDLV/factor con precisión matemática. Produce un texto
    listo para inyectar en el prompt de la IA con los números correctos.

    Devuelve:
      - resumen: string técnico para el prompt
      - interpretacion_hus: valor SOAT base implícito según HUS
      - interpretacion_eps: idem EPS
      - diferencia_pesos: |facturado - reconocido|
      - recomendacion: DEFENDER | ACEPTAR_PARCIAL | REVISAR
    """
    from app.services.uvb import UVB_2026, SMDLV_2026

    modalidad_up = (modalidad or "").upper()
    tipo_tarifa = (tipo_tarifa or "VALOR_FIJO").upper()
    diferencia = abs(valor_facturado - valor_reconocido) if valor_facturado and valor_reconocido else 0.0

    resumen = f"MODALIDAD: {modalidad or 'NO ESPECIFICADA'}\n"

    if "SOAT" in modalidad_up or tipo_tarifa == "SOAT_PORCENTAJE":
        mult = 1 + float(factor_ajuste or 0.0) / 100.0
        interp_hus = valor_facturado / mult if (valor_facturado > 0 and mult > 0) else 0.0
        interp_eps = valor_reconocido / mult if (valor_reconocido > 0 and mult > 0) else 0.0
        resumen += (
            f"Marco: Circular 047/2025 MinSalud — Manual SOAT 2026 (UVB = ${UVB_2026:,})\n"
            f"Fórmula pactada: SOAT_vigente × {mult:.3f} (factor {factor_ajuste}%)\n"
        )
        if interp_hus > 0:
            resumen += f"SOAT base implícito HUS: ${interp_hus:,.0f}\n"
        if interp_eps > 0:
            resumen += f"SOAT base implícito EPS: ${interp_eps:,.0f}\n"
            resumen += (
                f"Discrepancia: HUS interpreta SOAT base ${interp_hus:,.0f} vs "
                f"EPS ${interp_eps:,.0f}.\n"
            )
        recomendacion = "DEFENDER" if diferencia > 0 and interp_hus > interp_eps else "REVISAR"
    elif "PROPIA" in modalidad_up or "MANUAL HUS" in modalidad_up or "INSTITUCIONAL" in modalidad_up:
        resumen += (
            f"Marco: Res. 054/2026 ESE HUS (listado unificado) + Res. 124/2026 ESE HUS "
            f"(nuevos códigos). Fórmula: FACTOR × SMDLV 2026 (${SMDLV_2026:,})\n"
            f"Valor pactado fijo: ${valor_pactado:,.0f}\n"
        )
        interp_hus = valor_facturado
        interp_eps = valor_reconocido
        if abs(valor_facturado - valor_pactado) < max(1.0, valor_pactado * 0.005):
            recomendacion = "DEFENDER"
        elif valor_facturado > valor_pactado and diferencia <= valor_facturado:
            recomendacion = "ACEPTAR_PARCIAL"
        else:
            recomendacion = "REVISAR"
    else:
        # Valor fijo desconocido
        interp_hus = valor_facturado
        interp_eps = valor_reconocido
        resumen += f"Valor pactado contractual: ${valor_pactado:,.0f}\n"
        recomendacion = "REVISAR"

    return {
        "resumen": resumen.strip(),
        "interpretacion_hus": round(interp_hus, 2),
        "interpretacion_eps": round(interp_eps, 2),
        "diferencia_pesos": round(diferencia, 2),
        "recomendacion": recomendacion,
    }


# ─── Agente Conciliador ─────────────────────────────────────────────────────

def agente_conciliador(tono: str, etapa: str) -> dict:
    """Ajusta tono y estructura final del dictamen.

    Devuelve lineamientos textuales que la IA debe respetar al generar
    el argumento.
    """
    tono = (tono or "conciliador").lower().strip()
    etapa = (etapa or "").upper()
    es_ratif = "RATIF" in etapa

    resultado = {
        "cierre_sugerido": (
            "Comunicaciones: cartera@hus.gov.co, glosasydevoluciones@hus.gov.co"
        ),
        "lineamientos": [],
    }

    if es_ratif:
        resultado["lineamientos"].append(
            "Tono firme pero institucional. Referenciar la respuesta inicial."
        )
        resultado["lineamientos"].append(
            "Incluir cita explícita al Art. 57 Ley 1438/2011 (plazo conciliación)."
        )
        resultado["lineamientos"].append(
            "Cierre obligatorio: 'De persistir la ratificación sin acuerdo, la ESE HUS "
            "se reserva el derecho de acudir ante las autoridades competentes para "
            "resolver el conflicto en los términos de ley.'"
        )
    elif tono == "firme":
        resultado["lineamientos"].append(
            "Sube intensidad argumentativa sin cruzar a hostil. Usa 'NO SE AJUSTA A "
            "DERECHO', 'CARECE DE RESPALDO NORMATIVO', 'SE INSTA AL PRONUNCIAMIENTO "
            "DEFINITIVO'."
        )
    elif tono == "neutral":
        resultado["lineamientos"].append(
            "Registro técnico-jurídico sin suavizadores ('respetuosamente', "
            "'cordialmente'). Directo pero institucional."
        )
    else:  # conciliador (default)
        resultado["lineamientos"].append(
            "Usa 'SE SOLICITA RESPETUOSAMENTE', 'AMERITA REVISIÓN', 'REQUIERE "
            "MAYOR SUSTENTO'. Evita imperativos duros."
        )

    resultado["lineamientos"].append(
        "Cerrar con el párrafo estándar de plazo Art. 57 Ley 1438 + silencio favorable."
    )
    return resultado


# ─── Orquestador ────────────────────────────────────────────────────────────

def orquestar_dictamen(
    codigo_glosa: str,
    eps: str,
    cups: str = "",
    servicio: str = "",
    etapa: str = "INICIAL",
    tono: str = "conciliador",
    tipo_servicio: str = "",
    modalidad: str = "",
    factor_ajuste: float = 0.0,
    valor_pactado: float = 0.0,
    tipo_tarifa: str = "VALOR_FIJO",
    valor_facturado: float = 0.0,
    valor_reconocido: float = 0.0,
) -> str:
    """Combina la salida de los 4 agentes en un bloque de contexto que se
    inyecta al user_prompt del LLM. El LLM recibe toda esta info curada
    antes de redactar el argumento final.

    Retorna un string listo para concatenar al user_prompt.
    """
    jur = agente_juridico(codigo_glosa, eps, etapa)
    clin = agente_clinico(cups, servicio, tipo_servicio)
    tar = agente_tarifario(
        modalidad=modalidad, factor_ajuste=factor_ajuste,
        valor_pactado=valor_pactado, tipo_tarifa=tipo_tarifa,
        valor_facturado=valor_facturado, valor_reconocido=valor_reconocido,
    )
    conc = agente_conciliador(tono, etapa)

    bloque = ["\n═══ BLOQUE MULTI-AGENTE (usa en este orden) ═══"]

    # Agente Jurídico
    bloque.append("\n[AGENTE JURÍDICO]")
    bloque.append("Normas PRIMARIAS (citar explícitamente):")
    for n in jur["normas_primarias"]:
        bloque.append(f"  • {n}")
    if jur["normas_secundarias"]:
        bloque.append("Normas SECUNDARIAS (refuerzos):")
        for n in jur["normas_secundarias"]:
            bloque.append(f"  • {n}")
    if jur["jurisprudencia"]:
        bloque.append("Jurisprudencia:")
        for j in jur["jurisprudencia"]:
            bloque.append(f"  • {j}")
    if jur["evitar"]:
        bloque.append("NO CITES (no aplica a este caso):")
        for e in jur["evitar"]:
            bloque.append(f"  ✗ {e}")

    # Agente Clínico
    bloque.append(f"\n[AGENTE CLÍNICO] Categoría: {clin['categoria']}")
    if clin["justificacion_inherente"]:
        bloque.append("  → El servicio tiene justificación clínica inherente (no requiere autorización previa)")
    bloque.append("  Soportes esperados en el expediente:")
    for s in clin["soportes_esperados"]:
        bloque.append(f"    - {s}")

    # Agente Tarifario
    if tar.get("resumen"):
        bloque.append("\n[AGENTE TARIFARIO]")
        for linea in tar["resumen"].split("\n"):
            bloque.append(f"  {linea}")
        bloque.append(f"  Recomendación tarifaria: {tar['recomendacion']}")

    # Agente Conciliador
    bloque.append("\n[AGENTE CONCILIADOR]")
    for l in conc["lineamientos"]:
        bloque.append(f"  • {l}")
    bloque.append(f"  Cierre: {conc['cierre_sugerido']}")

    bloque.append("═══════════════════════════════════════════")
    return "\n".join(bloque)
