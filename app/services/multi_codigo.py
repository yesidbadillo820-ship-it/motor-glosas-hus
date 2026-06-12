"""Un dictamen por código para glosas multi-código (jun-2026).

Las glosas de EPS a veces agrupan VARIOS códigos en una misma fila/texto
("SO0601 + TA0201 + TA0701" — casos reales de producción). Antes el motor
procesaba SOLO el primero y el dictamen mezclaba argumentos de las otras
familias sin declararlas: un encabezado "SO0601 SOPORTES" con párrafos de
tarifas adentro confundía a la EPS y facilitaba la ratificación.

Decisión de diseño (jun-2026, opción elegida por el usuario): UN dictamen
por código, CONCATENADOS en el mismo registro de glosa. Sin tocar esquema
de BD (el campo `codigo` sigue siendo el principal), sin dividir en
sub-glosas, sin cambios en dashboard/radicación.

Ensamblado del dictamen final:
  encabezado declarando TODOS los códigos
  + sección del código principal (flujo existente, intacto)
  + "═══ RESPUESTA AL CÓDIGO XX#### — FAMILIA ═══" por cada adicional.

Cada sección adicional sale de una llamada IA propia que SIEMPRE pasa por
el Quality Gate (`ejecutar_con_quality_gate`) con el codigo_glosa del
código adicional — así el pre/post-validator (valores fabricados,
contratos fabricados, citas inválidas) protege cada bloque aunque
QUALITY_GATE_ENABLED esté OFF para el flujo principal. Si el QG escala a
humano, se incluye el mejor intento con nota visible de revisión.

Flag: MULTI_CODIGO_DICTAMENES (default ON="1"). En "0" se vuelve al
comportamiento anterior (solo el primero + warning de pérdida).

Cap de seguridad: máximo MAX_CODIGOS_DICTAMEN códigos por glosa
(principal + 2 adicionales). Los restantes se declaran en el encabezado
como "requieren respuesta separada". Un fallo en un código adicional
NUNCA rompe el dictamen principal: se anota el código como no procesado.
"""

import logging
import os

from app.services.quality_gate_adapter import (
    ejecutar_con_quality_gate,
    registrar_estadistica_qg,
)

logger = logging.getLogger("motor_glosas.multi_codigo")

# Principal + 2 adicionales. Cada adicional cuesta 1-3 llamadas IA (el QG
# puede regenerar), por eso el cap es bajo: una glosa con 4+ códigos es
# rarísima y amerita respuesta manual para los excedentes.
MAX_CODIGOS_DICTAMEN = 3

# Nombre legible de cada familia de código — espejo de _ABREV_A_NOMBRE /
# _NOMBRE_TIPO (glosa_service / glosa_ia_prompts). Se duplica aquí para no
# importar privados de otros módulos a nivel de módulo.
_NOMBRE_FAMILIA = {
    "TA": "TARIFAS",
    "SO": "SOPORTES",
    "AU": "AUTORIZACIÓN",
    "CO": "COBERTURA",
    "CL": "PERTINENCIA CLÍNICA",
    "PE": "PERTINENCIA CLÍNICA",
    "FA": "FACTURACIÓN",
    "IN": "INSUMOS",
    "ME": "MEDICAMENTOS",
    "SE": "SIN ESPECIFICACIÓN",
    "EX": "EXTEMPORANEIDAD",
}

# Colores por familia — espejo del dict `colores` de
# GlosaService._generar_dictamen_html para que las secciones adicionales
# se vean consistentes con el bloque del código principal.
_COLOR_FAMILIA = {
    "TA": "#1e40af",
    "SO": "#7c3aed",
    "AU": "#059669",
    "CO": "#dc2626",
    "CL": "#d97706",
    "PE": "#d97706",
    "FA": "#0891b2",
    "IN": "#e11d48",
    "ME": "#4f46e5",
    "EX": "#991b1b",
}
_COLOR_DEFAULT = "#1e3a8a"


def multi_codigo_habilitado() -> bool:
    """True salvo que MULTI_CODIGO_DICTAMENES esté explícitamente en OFF.

    Default ON: el problema que resuelve (dictámenes que mezclan familias
    sin declararlas) está activo en producción hoy; el flag existe como
    kill-switch si el costo de las llamadas IA adicionales se dispara.
    """
    flag = os.environ.get("MULTI_CODIGO_DICTAMENES", "1").lower().strip()
    return flag not in ("0", "false", "no", "off")


def _nombre_familia(codigo: str) -> str:
    return _NOMBRE_FAMILIA.get((codigo or "")[:2].upper(), "CONCEPTO")


def _color_familia(codigo: str) -> str:
    return _COLOR_FAMILIA.get((codigo or "")[:2].upper(), _COLOR_DEFAULT)


def construir_encabezado_html(
    codigos: list[str],
    no_procesados: list[str] | None = None,
) -> str:
    """Bloque que declara TODOS los códigos detectados al inicio del
    dictamen. La EPS debe ver de entrada que la respuesta cubre varios
    códigos — el reclamo original era justamente que el dictamen los
    mezclaba "sin declararlas"."""
    lista = ", ".join(codigos)
    extra = ""
    if no_procesados:
        extra = (
            "<div style='margin-top:6px;color:#92400e;'>"
            f"⚠ Los códigos {', '.join(no_procesados)} exceden el límite de "
            f"procesamiento automático ({MAX_CODIGOS_DICTAMEN} códigos por glosa) "
            "y requieren respuesta separada.</div>"
        )
    return (
        '<div style="background:#eef2ff;border:2px solid #6366f1;border-radius:8px;'
        'padding:10px 14px;margin-bottom:12px;font-size:12px;color:#312e81;">'
        f"<b>CÓDIGOS GLOSA: {lista}</b> — La glosa agrupa varios códigos; este "
        "documento contiene una respuesta por cada código."
        f"{extra}</div>"
    )


def construir_nota_fallidos_html(codigos_fallidos: list[str]) -> str:
    """Nota visible cuando uno o más códigos adicionales no pudieron
    procesarse (excepción, QG sin dictamen). El gestor debe responderlos
    manualmente — nunca silenciamos la pérdida."""
    if not codigos_fallidos:
        return ""
    lista = ", ".join(codigos_fallidos)
    return (
        '<div style="margin-top:12px;padding:12px;background:#fef3c7;'
        'border:2px solid #f59e0b;border-radius:8px;font-size:11px;color:#78350f;">'
        f"⚠ <b>ATENCIÓN:</b> Los códigos {lista} no pudieron procesarse "
        "automáticamente — responder manualmente.</div>"
    )


def _nota_revision_qg_html(score: int) -> str:
    """Banner cuando el QG escaló a humano: se entrega el mejor intento
    pero el gestor DEBE revisarlo antes de radicar."""
    return (
        '<div style="margin-bottom:10px;padding:8px 10px;background:#fef2f2;'
        "border:1px solid #dc2626;border-radius:6px;font-size:11px;"
        'color:#991b1b;font-weight:700;">'
        f"⚠ REVISAR ESTE BLOQUE — escalado por Quality Gate (score={score})</div>"
    )


def _wrap_seccion_html(codigo: str, argumento_html: str, nota_qg_html: str = "") -> str:
    """Sección visual de un código adicional, consistente con el bloque
    "ARGUMENTACIÓN JURÍDICA" del dictamen principal. El título usa "═══"
    como texto para que sobreviva legible en Excel-respuesta
    (dictamen_a_texto_plano) y en el PDF radicable."""
    color = _color_familia(codigo)
    titulo = f"═══ RESPUESTA AL CÓDIGO {codigo} — {_nombre_familia(codigo)} ═══"
    return (
        f'<div style="margin:18px 0 6px 0;text-align:center;font-size:12px;'
        f'font-weight:700;letter-spacing:1px;color:{color};">{titulo}</div>'
        f'<div style="background:#f8fafc;border-radius:12px;padding:20px;'
        f'border-left:4px solid {color};margin-top:8px;">'
        f"{nota_qg_html}"
        f'<h4 style="color:#0f172a;margin:0 0 10px 0;font-size:14px;">'
        f"ARGUMENTACIÓN JURÍDICA — CÓDIGO {codigo}</h4>"
        f'<div style="font-size:12px;line-height:1.9;color:#334155;'
        f'white-space:pre-wrap;">{argumento_html}</div></div>'
    )


def construir_bloque_instruccion_adicional(
    codigo: str,
    codigo_principal: str,
    todos_los_codigos: list[str],
    valor_objetado: str,
) -> str:
    """Instrucción que se anexa al user prompt estándar (build_user_prompt
    del código adicional) para acotar la respuesta a UNA familia.

    Crítico: el valor objetado de la glosa es GLOBAL — si la IA lo
    atribuye a un solo código o inventa desgloses, la EPS lo usa para
    ratificar por inconsistencia aritmética.
    """
    familia = (codigo or "")[:2].upper()
    otros = [c for c in todos_los_codigos if c != codigo]
    hay_valor = bool(valor_objetado) and valor_objetado.strip() not in ("$ 0.00", "$0.00", "$ 0")
    if hay_valor:
        regla_valor = (
            f"El valor objetado ({valor_objetado}) corresponde a la GLOSA COMPLETA, "
            "no a este código individual — referéncialo como 'valor total objetado' "
            "si lo necesitas, NUNCA lo atribuyas solo a este código ni inventes "
            "desgloses por código.\n"
        )
    else:
        regla_valor = (
            "La glosa no trae valor desglosado por código — NO menciones cifras "
            "monetarias ni inventes desgloses.\n"
        )
    return (
        "\n\n═══ INSTRUCCIÓN MULTI-CÓDIGO (PRIORITARIA — anula cualquier "
        "instrucción en conflicto) ═══\n"
        f"La glosa agrupa VARIOS códigos en el mismo texto: {', '.join(todos_los_codigos)}.\n"
        f"El código {codigo_principal} ya tiene su propia respuesta en otra sección "
        "del documento.\n"
        f"Genera SOLO la argumentación para el código {codigo} "
        f"(familia {familia} — {_nombre_familia(codigo)}). "
        "El texto de la glosa completo está en el BLOQUE 3.\n"
        f"NO repitas la argumentación de los otros códigos ({', '.join(otros)}); "
        "limítate a los hechos y normas de SU familia.\n"
        f"{regla_valor}"
        "LONGITUD: máximo 2 párrafos (120-200 palabras) — es una sección "
        "complementaria del documento, no un dictamen completo. Conserva el "
        "cierre 'SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA…' referido a este código.\n"
    )


def _sanitizar_argumento(
    texto: str,
    eps: str,
    es_ratificacion: bool,
    es_extemporanea: bool,
    codigo: str = "",
    valor_objetado: str = "",
) -> str:
    """Aplica a la sección adicional los mismos sanitizers deterministas
    (sin IA) del flujo principal: tono institucional, palabra prohibida
    "injustific*", coda procesal indebida, citas inventadas/inválidas,
    placeholders crudos (ronda 2, 12-jun-2026), coda post-levantamiento,
    runaway y MAYÚSCULAS. Cualquier fallo de un sanitizer degrada al texto
    previo — el QG ya validó lo esencial.

    Imports locales: glosa_service importa este módulo dentro de
    analizar(), así que importar glosa_service arriba crearía un ciclo.
    """
    try:
        from app.services.dictamen_postprocesor import (
            quitar_citas_invalidas_dinamico,
            quitar_parrafos_con_citas_inventadas,
            truncar_despues_de_levantamiento,
        )
        from app.services.glosa_service import (
            _expandir_abreviaturas_tipo,
            _rellenar_placeholders,
            _suavizar_tono,
            _truncar_runaway,
            limpiar_cierre_extemporanea_indebido,
            limpiar_palabra_injustificado,
        )

        t = _suavizar_tono(texto)
        t = limpiar_palabra_injustificado(t)
        t = limpiar_cierre_extemporanea_indebido(
            t,
            es_ratificacion=es_ratificacion,
            es_extemporanea=es_extemporanea,
        )
        t = quitar_parrafos_con_citas_inventadas(t)
        t = quitar_citas_invalidas_dinamico(t, eps=eps)
        # Placeholders crudos [ENTIDAD]/[VALOR REAL]/[CODIGO] — mismo
        # sanitizer del flujo principal (ronda 2, 12-jun-2026, fix #6).
        t = _rellenar_placeholders(t, eps=eps, codigo=codigo, valor=valor_objetado)
        t = truncar_despues_de_levantamiento(t)
        t = _truncar_runaway(t)
        t = _expandir_abreviaturas_tipo(t)
        # Estándar institucional: respuestas en MAYÚSCULAS (mismo umbral
        # del flujo principal, paso 15 de analizar()).
        letras = [c for c in t if c.isalpha()]
        if letras and (sum(1 for c in letras if c.isupper()) / len(letras)) < 0.80:
            t = t.upper()
        return t or texto
    except Exception as e:
        logger.debug(f"[MULTI-CODIGO] sanitizers no aplicados: {e}")
        return texto


async def _generar_seccion_codigo(
    *,
    servicio,
    codigo: str,
    codigo_principal: str,
    todos_los_codigos: list[str],
    texto_glosa: str,
    eps: str,
    valor_objetado: str,
    contexto_pdf: str,
    numero_factura: str | None,
    numero_radicado: str | None,
    dias_habiles: int,
    es_extemporanea: bool,
    es_ratificacion: bool,
    tono: str,
    proveedores_disponibles: set[str],
) -> str | None:
    """Genera el HTML de la sección de UN código adicional.

    Devuelve None si el bloque no pudo producirse (QG sin dictamen) —
    el caller lo anota como fallido. Las excepciones suben al caller,
    que también las trata como fallo del bloque (nunca del principal).
    """
    # Mismo seam del flujo principal: si existe plantilla curada para el
    # código, se usa directa (0 tokens) en vez de llamar a la IA.
    from app.services.glosa_service import _suavizar_tono, obtener_plantilla_por_codigo

    plantilla = obtener_plantilla_por_codigo(codigo)
    if plantilla:
        texto = _suavizar_tono(plantilla["plantilla"])
        texto = texto.replace("\n", "<br/>").replace("*", "")
        logger.info(f"[MULTI-CODIGO] {codigo}: plantilla curada usada (0 tokens)")
        return _wrap_seccion_html(codigo, texto)

    from app.services.glosa_ia_prompts import build_user_prompt, get_system_prompt

    prefijo = codigo[:2].upper()
    system_prompt = get_system_prompt(prefijo=prefijo, eps=eps)

    # Cláusulas literales del contrato filtradas por la familia del código
    # ADICIONAL (no la del principal) — el QG también las necesita para no
    # marcar como "fabricado" un contrato real citado.
    clausulas: list[dict] = []
    try:
        from app.services.glosa_ia_prompts import get_clausulas_para_glosa

        clausulas = get_clausulas_para_glosa(eps=eps, codigo_glosa=codigo, max_clausulas=5)
    except Exception as e:
        logger.debug(f"[MULTI-CODIGO] clausulas no disponibles para {codigo}: {e}")

    # contexto_pdf recortado a presupuesto "simple" (2000 chars, mismo tope
    # de build_user_prompt para casos de baja complejidad): la sección
    # adicional es complementaria — mandarle 40K chars de PDF a cada código
    # extra triplicaría el costo del análisis sin mejorar el bloque.
    user_prompt = build_user_prompt(
        texto_glosa=texto_glosa,
        contexto_pdf=(contexto_pdf or "")[:2000],
        codigo=codigo,
        eps=eps,
        numero_factura=numero_factura,
        numero_radicado=numero_radicado,
        dias_habiles=dias_habiles,
        es_extemporanea=es_extemporanea,
        valor_objetado=valor_objetado,
        tono=tono,
        clausulas_contrato=clausulas,
    ) + construir_bloque_instruccion_adicional(
        codigo=codigo,
        codigo_principal=codigo_principal,
        todos_los_codigos=todos_los_codigos,
        valor_objetado=valor_objetado,
    )

    # SIEMPRE vía Quality Gate (no gateado por QUALITY_GATE_ENABLED): cada
    # bloque adicional es una llamada IA nueva sin el resto de guard-rails
    # del flujo principal (R-CEREBRO, auto-crítica), así que el pre/post-
    # validator es su única defensa contra valores/contratos fabricados.
    resultado = await ejecutar_con_quality_gate(
        servicio=servicio,
        eps=eps,
        codigo_glosa=codigo,
        valor_objetado=valor_objetado,
        texto_glosa=texto_glosa,
        es_ratificacion=es_ratificacion,
        es_extemporanea=es_extemporanea,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        glosa_id=None,
        proveedores_disponibles=proveedores_disponibles,
        clausulas_contrato=clausulas,
    )
    try:
        registrar_estadistica_qg(resultado)
    except Exception:
        pass

    if resultado.estado == "RECHAZADO_PRE" or not (resultado.dictamen_final or "").strip():
        logger.warning(
            f"[MULTI-CODIGO] {codigo}: QG sin dictamen utilizable "
            f"(estado={resultado.estado}) — bloque marcado para respuesta manual."
        )
        return None

    texto = _sanitizar_argumento(
        resultado.dictamen_final,
        eps=eps,
        es_ratificacion=es_ratificacion,
        es_extemporanea=es_extemporanea,
        codigo=codigo,
        valor_objetado=valor_objetado,
    )
    texto = texto.replace("\n", "<br/>").replace("*", "")

    nota_qg = ""
    if resultado.estado != "APROBADO":
        # Mejor intento del QG (ESCALAR_HUMANO): se entrega con banner de
        # revisión — preferible a perder el bloque, pero el gestor decide.
        nota_qg = _nota_revision_qg_html(resultado.score_final)

    logger.info(
        f"[MULTI-CODIGO] {codigo}: sección generada "
        f"(estado={resultado.estado}, score={resultado.score_final}, "
        f"modelo={resultado.modelo_final})"
    )
    return _wrap_seccion_html(codigo, texto, nota_qg)


async def generar_secciones_adicionales(
    *,
    servicio,
    codigos: list[str],
    codigo_principal: str,
    todos_los_codigos: list[str],
    texto_glosa: str,
    eps: str,
    valor_objetado: str,
    contexto_pdf: str = "",
    numero_factura: str | None = None,
    numero_radicado: str | None = None,
    dias_habiles: int = 0,
    es_extemporanea: bool = False,
    es_ratificacion: bool = False,
    tono: str = "conciliador",
    proveedores_disponibles: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Genera las secciones HTML de todos los códigos adicionales.

    Returns:
        (html_concatenado_de_secciones, codigos_fallidos). Un fallo en un
        código NO aborta los demás ni propaga al caller — el contrato con
        analizar() es que el dictamen principal jamás se pierde por culpa
        de un bloque adicional.
    """
    secciones: list[str] = []
    fallidos: list[str] = []
    for codigo in codigos:
        try:
            seccion = await _generar_seccion_codigo(
                servicio=servicio,
                codigo=codigo,
                codigo_principal=codigo_principal,
                todos_los_codigos=todos_los_codigos,
                texto_glosa=texto_glosa,
                eps=eps,
                valor_objetado=valor_objetado,
                contexto_pdf=contexto_pdf,
                numero_factura=numero_factura,
                numero_radicado=numero_radicado,
                dias_habiles=dias_habiles,
                es_extemporanea=es_extemporanea,
                es_ratificacion=es_ratificacion,
                tono=tono,
                proveedores_disponibles=proveedores_disponibles or set(),
            )
        except Exception as e:
            logger.warning(f"[MULTI-CODIGO] {codigo}: falló la sección adicional: {e}")
            seccion = None
        if seccion:
            secciones.append(seccion)
        else:
            fallidos.append(codigo)
    return "".join(secciones), fallidos
