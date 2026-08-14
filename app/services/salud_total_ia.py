"""«Analizar con IA» de Salud Total: cada glosa pasa por el motor de verdad.

OT-045 · 13-08-2026. El botón «Analizar con IA (Análisis completo)» de la
pantalla de Salud Total existía desde antes, pero **no llamaba a la IA**:
caía en las mismas plantillas por código de glosa que las otras dos
opciones. Un botón que promete una cosa y hace otra es de lo peor que puede
tener un sistema: el auditor confía en algo que no ocurrió.

Yesid pidió que hiciera lo que dice, no que le cambiáramos el nombre.

**Qué hace ahora.** Convierte cada fila de la notificación en una glosa como
las que el motor ya sabe analizar, y la manda por el MISMO camino que usa el
portal: `GlosaService.analizar`. Con eso hereda todo lo que el motor tiene —
las cláusulas del contrato firmado, las tarifas pactadas, la homologación
CUPS → SOAT, las 18 redes que revisan lo que el dictamen afirma y el
verificador de citas. No se inventó un prompt nuevo ni un camino paralelo:
eso habría significado dos motores que con el tiempo dicen cosas distintas
sobre la misma factura.

**El detalle que manda sobre todo lo demás:** la casilla «Observación IPS»
del archivo que recibe Salud Total admite **500 caracteres**, y un dictamen
del motor tiene miles. Por eso el dictamen completo NO se recorta a lo bruto:
se corta en el último punto que quepa, para que el texto cierre. Y si por lo
que sea la IA no responde, la fila NO se queda vacía ni con una excusa: cae
en la respuesta por plantilla, que es la que hoy funciona. Un archivo con
filas en blanco es peor que uno con plantilla.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("motor_glosas")

# Lo que cabe en la casilla de la entidad. Está en el otro módulo, se importa
# de allá para que no queden dos números que puedan separarse.
from app.services.salud_total_service import (  # noqa: E402
    OBS_MAX_CARACTERES,
    CONCEPTOS,
    GlosaSaludTotal,
)

# Cuántas glosas se analizan a la vez. Una notificación trae 44 y cada
# análisis tarda; en fila india serían minutos largos. Más de tres en
# paralelo satura al proveedor de IA y empiezan los rechazos por cuota.
MAX_EN_PARALELO = 3

# Cuánto se espera por una glosa antes de darla por perdida y pasar a la
# plantilla. Sin esto, una llamada colgada deja la pantalla girando para
# siempre.
SEGUNDOS_LIMITE_POR_GLOSA = 120


def _pesos(valor) -> str:
    """Escribe un valor de peso como se escribe en Colombia.

    13-08-2026. La primera versión le pasaba a la IA el número tal cual salía
    del archivo —`93340.0`— y la IA lo copiaba al dictamen: en el documento
    que se radica quedaba «FACTURADA POR $ 93340.0». Un decimal en un valor
    en pesos, en un documento legal, se lee como descuido.
    """
    try:
        n = float(valor or 0)
    except (TypeError, ValueError):
        return str(valor or "0")
    return f"${n:,.0f}".replace(",", ".")


def _texto_de_la_glosa(fila: dict) -> str:
    """Arma el texto que lee el motor, con lo que la entidad mandó.

    Solo se escribe lo que viene en la notificación. Nada de rellenar lo que
    falte: si la entidad no mandó el código específico, no se inventa.
    """
    partes = [
        "GLOSA NOTIFICADA POR SALUD TOTAL EPS",
        f"FACTURA: {fila.get('PrefijoFac') or ''}{fila.get('NumeroFac') or ''}",
        f"RADICADO DE LA GLOSA: {fila.get('NumeroRad') or ''}",
        f"REGISTRO: {fila.get('NUMREG') or ''}",
        f"SERVICIO: {fila.get('NombreServicio') or ''}",
        f"VALOR FACTURADO DEL SERVICIO: {_pesos(fila.get('ValorTotalServ'))}",
        f"VALOR OBJETADO POR LA ENTIDAD: {_pesos(fila.get('ValorGlosaTotalxServ'))}",
    ]
    # Los dos códigos van SEPARADOS. Pegados daban «TATA23», que no es
    # ningún código y confunde al motor: el general es TA y el específico
    # TA23, y el específico ya lleva el general adentro.
    general = (fila.get("CodMotvGlosaGeneral") or "").strip()
    especifico = (fila.get("CodMotvGlosaEspc") or "").strip()
    if especifico:
        partes.append(f"CODIGO DE GLOSA: {especifico}")
    elif general:
        partes.append(f"CODIGO DE GLOSA: {general}")
    if general and especifico and not especifico.startswith(general):
        partes.append(f"CODIGO GENERAL: {general}")
    for etiqueta, llave in (
        ("MOTIVO GENERAL", "MotvGlosaGeneral"),
        ("MOTIVO ESPECIFICO", "MotvGlosaEspc"),
        ("DESCRIPCION DEL MOTIVO", "DescripcionMotivo"),
    ):
        valor = (fila.get(llave) or "").strip()
        if valor:
            partes.append(f"{etiqueta}: {valor}")
    return "\n".join(partes)


def _a_texto_plano(html: str) -> str:
    """Saca el argumento en texto plano del dictamen.

    13-08-2026, corrección en caliente. El dictamen del motor viene en HTML
    —está hecho para verse en pantalla y en el PDF— y la primera versión de
    esto lo recortaba sin quitarle las etiquetas. El archivo que se generó
    traía en la casilla de la entidad esto:

        <table border="1" style="width:100%;border-collapse:collapse;…

    cortado a mitad de un atributo de estilo. Ilegible, y con el argumento
    en ninguna parte.

    Se reutiliza el extractor que ya existe en el motor
    (`_extraer_argumento_del_dictamen`), que busca la «ARGUMENTACIÓN
    JURÍDICA» y descarta las tablas de encabezado y el pie de página. Si no
    encuentra ese marcador, se limpian las etiquetas a mano antes que
    devolver HTML.
    """
    if not html:
        return ""
    try:
        from app.services.aprendizaje_feedback import _extraer_argumento_del_dictamen

        texto = _extraer_argumento_del_dictamen(html)
        if texto and len(texto) > 40:
            return texto
    except Exception:  # pragma: no cover - el respaldo de abajo siempre sirve
        pass

    import re

    t = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (
        t.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return " ".join(t.split())


def _condensar(dictamen: str, limite: int = OBS_MAX_CARACTERES) -> str:
    """Deja el argumento dentro de lo que admite la casilla de la entidad.

    Corta en el último punto que quepa para que el texto cierre. Recortar a
    la brava dejaría la defensa a mitad de frase — y esa frase la lee un
    auditor de la EPS que busca cualquier motivo para ratificar.
    """
    texto = _a_texto_plano(dictamen or "")
    if not texto:
        return ""
    if len(texto) <= limite:
        return texto
    recorte = texto[:limite]
    corte = max(recorte.rfind(". "), recorte.rfind("; "))
    # Solo se usa el punto si deja un texto que valga la pena; si el último
    # punto está muy al principio, se prefiere cortar y cerrar con punto.
    if corte > limite * 0.6:
        return recorte[: corte + 1].strip()
    return recorte.rstrip().rstrip(",;:") + "."


async def _analizar_una(servicio, fila: dict, eps: str = "SALUD TOTAL") -> dict | None:
    """Manda UNA glosa por el motor. Devuelve None si no se pudo."""
    from app.models.schemas import GlosaInput

    try:
        entrada = GlosaInput(
            eps=eps,
            etapa="RESPUESTA GLOSA",
            tabla_excel=_texto_de_la_glosa(fila),
            numero_factura=(fila.get("NumeroFac") or None),
            numero_radicado=(fila.get("NumeroRad") or None),
            valor_aceptado="0",
        )
    except Exception as e:  # una fila rota no puede tumbar el lote entero
        logger.warning(f"[SALUD-TOTAL-IA] fila {fila.get('NUMREG')} no se pudo armar: {e}")
        return None

    try:
        resultado = await asyncio.wait_for(
            servicio.analizar(entrada), timeout=SEGUNDOS_LIMITE_POR_GLOSA
        )
    except asyncio.TimeoutError:
        logger.warning(f"[SALUD-TOTAL-IA] fila {fila.get('NUMREG')}: la IA no respondió a tiempo")
        return None
    except Exception as e:
        logger.warning(f"[SALUD-TOTAL-IA] fila {fila.get('NUMREG')}: {type(e).__name__}: {e}")
        return None

    dictamen = getattr(resultado, "dictamen", "") or ""
    if not dictamen.strip():
        return None

    observacion = _condensar(dictamen)

    # Guarda dura. Lo que va a la casilla de la entidad tiene que ser texto
    # y nada más: si se cuela una etiqueta, el archivo llega ilegible y la
    # glosa queda sin argumento. Antes que mandar eso, se prefiere la
    # plantilla, que es texto probado.
    if not observacion or "<" in observacion or ">" in observacion:
        logger.warning(
            f"[SALUD-TOTAL-IA] fila {fila.get('NUMREG')}: el dictamen no dejó texto "
            f"limpio; esa glosa sale por plantilla"
        )
        return None
    if len(observacion) < 60:
        logger.warning(
            f"[SALUD-TOTAL-IA] fila {fila.get('NUMREG')}: el argumento quedó en "
            f"{len(observacion)} caracteres, muy corto para defender; sale por plantilla"
        )
        return None

    return {
        "dictamen": dictamen,
        "observacion": observacion,
        "modelo_ia": getattr(resultado, "modelo_ia", None),
        "score": getattr(resultado, "score", 0.0),
    }


async def analizar_notificacion(
    filas: list[dict],
    servicio=None,
    fecha_recepcion=None,
) -> tuple[list[dict], dict]:
    """Analiza con IA todas las filas de la notificación.

    Devuelve (respuestas, resumen). Cada respuesta trae la misma forma que la
    del camino por plantilla, para que el archivo se arme igual y la pantalla
    no tenga que saber por dónde vino.

    Las que la IA no logre responder caen a la plantilla. El archivo sale
    completo siempre: una fila vacía en el archivo que se radica es una glosa
    sin responder, y una glosa sin responder se da por aceptada.
    """
    if servicio is None:
        from app.services.glosa_service import GlosaService

        servicio = GlosaService()

    semaforo = asyncio.Semaphore(MAX_EN_PARALELO)

    async def _con_turno(fila: dict):
        async with semaforo:
            return await _analizar_una(servicio, fila)

    analisis = await asyncio.gather(*[_con_turno(f) for f in filas], return_exceptions=True)

    respuestas: list[dict] = []
    con_ia = 0
    for fila, salida in zip(filas, analisis):
        if isinstance(salida, Exception):
            salida = None

        # La base de la fila SIEMPRE sale del camino por plantilla: así los
        # valores, los códigos y el radicado son exactamente los mismos que
        # se comprobaron en OT-033, venga o no venga la IA.
        base = GlosaSaludTotal(
            _campos_desde(fila), tipo_respuesta="ia", fecha_recepcion=fecha_recepcion
        ).generar_respuesta()

        if salida:
            con_ia += 1
            base["Observacion_IPS"] = salida["observacion"]
            base["DictamenIA"] = salida["dictamen"]
            base["ModeloIA"] = salida["modelo_ia"]
            base["AnalizadaPorIA"] = True
            base["ConceptoRespuesta"] = CONCEPTOS.get(
                base.get("Codigo_Respuesta_a_glosas", ""), base.get("ConceptoRespuesta", "")
            )
        else:
            base["AnalizadaPorIA"] = False
        respuestas.append(base)

    resumen = {
        "total": len(filas),
        "analizadas_con_ia": con_ia,
        "por_plantilla": len(filas) - con_ia,
    }
    logger.info(
        f"[SALUD-TOTAL-IA] {con_ia} de {len(filas)} respondidas por la IA; "
        f"{resumen['por_plantilla']} por plantilla"
    )
    return respuestas, resumen


def _campos_desde(fila: dict) -> list[str]:
    """Rehace la fila en el orden de columnas de la notificación.

    `GlosaSaludTotal` lee por posición, que es como llega el archivo de la
    entidad. Esto la reconstruye desde el diccionario que ya se leyó, para no
    tener que volver a abrir el TXT.
    """
    return [
        fila.get("FechaRad") or "",
        fila.get("NumeroRad") or "",
        fila.get("PrefijoFac") or "",
        fila.get("NumeroFac") or "",
        fila.get("NUMREG") or "",
        fila.get("NumeroDocAfl") or "",
        "",  # nombre del paciente: no se necesita para responder
        "",  # Nap
        fila.get("NombreServicio") or "",
        str(fila.get("ValorTotalServ") or 0),
        "",  # cantidad
        "",  # valor unitario
        "",  # valor glosa final
        str(fila.get("ValorGlosaTotalxServ") or 0),
        fila.get("DescripcionMotivo") or "",
        "",  # observaciones
        fila.get("CodMotvGlosaGeneral") or "",
        fila.get("MotvGlosaGeneral") or "",
        fila.get("CodMotvGlosaEspc") or "",
        fila.get("MotvGlosaEspc") or "",
        "",
        "",
        "",
        str(fila.get("ValorBrutoFactura") or 0),
    ]
