"""
asistente_maestro.py — IA conversacional unificada con tools que cubre
TODAS las capacidades del sistema en una sola interfaz.

Visión Yesid (mayo 2026):
  "La idea es que la IA sea el complemento de todo de muchas cosas
  estructuradas en una sola mente maestra capaz de auditar, predecir,
  buscar soportes, conciliar, verificar y argumentar sin que haga
  falta entrar a muchos botones."

Esta es la implementación: un agente Claude con acceso a herramientas
que son los servicios ya construidos del motor.

CAPACIDADES (vía tools que el agente decide cuándo llamar):
  - buscar_soportes(query): busca facturas + archivos en el indexer
  - auditar_factura(factura, pregunta): auditor forense
  - buscar_glosa(query): busca glosas en BD por código/factura/EPS
  - lookup_norma(tipo, numero, año): consulta corpus normativo
  - buscar_clausula_contrato(eps, tema): cláusulas del contrato
  - lookup_tarifa(eps, cups): tarifa pactada
  - buscar_glosa_similar_levantada(eps, codigo, limite): precedentes
  - estadisticas_sistema(): KPIs globales (total glosas, valor, tasa)
  - estado_lote_importacion(lote_id): progreso de un lote
  - revisar_dictamen(glosa_id): obtener dictamen de una glosa específica

El usuario escribe en lenguaje natural. La IA decide qué tools llamar,
combina resultados y responde con análisis estructurado.

NO duplica los paneles existentes — es UNA sola conversación que
puede invocar cualquier capacidad. El usuario puede hacer:
  "¿Cuál es la última glosa de FAMISANAR? Busca sus soportes y
   auditá si tiene la baciloscopia"

Y la IA encadena: buscar_glosa → buscar_soportes → auditar_factura.
"""
from __future__ import annotations
import os
import json
import logging
from typing import Optional
import httpx

logger = logging.getLogger("motor_glosas")


SYSTEM_ASISTENTE_MAESTRO = """Eres el asistente maestro del motor IA GLOSAS SINAC SC, sistema de gestión de glosas médicas del Hospital Universitario de Santander (HUS) en Colombia.

Tu rol: ayudar al gestor de cartera (Yesid) y a su equipo a:
  • Auditar facturas y soportes documentales
  • Predecir levantamiento / ratificación de glosas
  • Buscar evidencia clínica en historias clínicas / RIPS / facturas
  • Conciliar valores facturados vs pactados
  • Verificar cumplimiento normativo
  • Argumentar técnico-jurídicamente

Tenés acceso a TODAS las capacidades del sistema vía las herramientas listadas. Decidí cuáles llamar según la pregunta del usuario.

REGLAS DURAS:
1. NUNCA inventes datos. Si no encontrás algo en las tools, dilo.
2. Cuando cites soportes, da folio y fecha exacta.
3. Si el usuario pregunta algo que requiere múltiples pasos (ej: "buscá la glosa X y auditá sus soportes"), encadená herramientas: primero buscar_glosa → después buscar_soportes → después auditar_factura.
4. Respondé en español formal pero claro.
5. Para análisis forenses largos, usá el formato de 4 secciones (Contexto / Evidencia con folios / Fundamento / Conclusión).
6. Si el usuario pide "audita esta factura" sin más, asumí que quiere el auditor_forense con pregunta genérica.
7. Cuando devuelvas valores monetarios, formatealos en pesos colombianos: "$1.234.567 COP".
8. Para fechas, usá formato dd/mm/aaaa.

Comunicate con calidez profesional — sos parte del equipo del HUS, no un bot externo."""


# Schemas de las tools disponibles para Claude
TOOLS_ASISTENTE = [
    {
        "name": "buscar_soportes_por_factura",
        "description": "Busca todos los archivos PDF indexados (factura, RIPS, historia clínica, etc.) para un número de factura específico. Devuelve lista de soportes con tipo, ruta y metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "factura": {"type": "string", "description": "Número de factura (HUSXXXXX o solo dígitos)"},
            },
            "required": ["factura"],
        },
    },
    {
        "name": "buscar_facturas_por_query",
        "description": "Busca facturas en el indexer por texto libre — puede ser nombre EPS, número ENV, número parcial de factura. Útil cuando el usuario dice 'buscá facturas de Famisanar' o 'envío 189840'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limite": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "auditar_factura_forense",
        "description": "Audita los soportes de una factura con análisis forense profundo. Lee los PDFs nativos con Claude, devuelve análisis estructurado en 4 secciones (Contexto/Evidencia/Fundamento/Conclusión). Usa esto cuando el usuario pide buscar algo específico en los soportes o validar evidencia.",
        "input_schema": {
            "type": "object",
            "properties": {
                "factura": {"type": "string"},
                "pregunta_especifica": {"type": "string", "description": "Qué busca el gestor — ej: 'verificar si está la baciloscopia' o 'audita esta factura'"},
            },
            "required": ["factura", "pregunta_especifica"],
        },
    },
    {
        "name": "buscar_glosa_en_bd",
        "description": "Busca glosas en la BD por código, EPS, factura, valor, estado. Devuelve metadata de cada glosa.",
        "input_schema": {
            "type": "object",
            "properties": {
                "factura": {"type": "string"},
                "eps": {"type": "string"},
                "codigo_glosa": {"type": "string"},
                "estado": {"type": "string", "description": "RADICADA, RESPONDIDA, LEVANTADA, RATIFICADA, ACEPTADA, CONCILIADA"},
                "limite": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "lookup_norma_legal",
        "description": "Recupera el texto literal de una norma del corpus colombiano (Ley/Decreto/Resolución/Sentencia). Úsalo ANTES de citar para verificar que existe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["resolucion", "decreto", "ley", "sentencia"]},
                "numero": {"type": "string"},
                "anio": {"type": "string"},
            },
            "required": ["tipo", "numero", "anio"],
        },
    },
    {
        "name": "buscar_clausulas_contrato",
        "description": "Busca cláusulas del contrato vigente de una EPS (extraídas del PDF subido). Filtra por tema (TA, SO, AU, CO, FA, NN).",
        "input_schema": {
            "type": "object",
            "properties": {
                "eps": {"type": "string"},
                "tema": {"type": "string", "enum": ["TA", "SO", "AU", "CO", "FA", "NN"]},
            },
            "required": ["eps", "tema"],
        },
    },
    {
        "name": "lookup_tarifa_pactada",
        "description": "Consulta tarifa pactada de un CUPS específico para una EPS según contrato.",
        "input_schema": {
            "type": "object",
            "properties": {
                "eps": {"type": "string"},
                "codigo_cups": {"type": "string"},
            },
            "required": ["eps", "codigo_cups"],
        },
    },
    {
        "name": "buscar_glosa_similar_levantada",
        "description": "Busca glosas históricas LEVANTADAS (defendidas con éxito) similares al caso. Útil para encontrar precedentes internos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "eps": {"type": "string"},
                "codigo_glosa": {"type": "string"},
                "limite": {"type": "integer", "default": 3},
            },
            "required": ["eps", "codigo_glosa"],
        },
    },
    {
        "name": "estadisticas_sistema",
        "description": "Devuelve KPIs globales: total glosas, valor objetado mes, valor recuperado, tasa éxito, EPS top, glosas vencidas, etc.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


async def execute_tool_asistente(name: str, args: dict, db, current_user) -> str:
    """Ejecuta una tool y devuelve el resultado como string JSON.
    Cada tool envuelve servicios existentes del motor."""
    try:
        if name == "buscar_soportes_por_factura":
            from app.services.soportes_autodiscovery_service import get_indexer
            soportes = get_indexer().lookup(args.get("factura", ""))
            return json.dumps({"soportes": soportes[:10], "total": len(soportes)}, ensure_ascii=False)

        if name == "buscar_facturas_por_query":
            from app.services.soportes_autodiscovery_service import get_indexer
            grupos = get_indexer().buscar(args.get("query", ""), limite=args.get("limite", 10))
            return json.dumps({"resultados": grupos, "total": len(grupos)}, ensure_ascii=False)

        if name == "auditar_factura_forense":
            from app.services.soportes_autodiscovery_service import get_indexer
            from app.services.auditor_forense import auditar_forense
            factura = args.get("factura", "").strip().upper()
            pregunta = args.get("pregunta_especifica", "audita esta factura")
            soportes = get_indexer().lookup(factura)
            if not soportes:
                return json.dumps({
                    "error": f"No hay soportes indexados para {factura}",
                    "sugerencia": "Verificar que el jump-box haya subido los archivos",
                })
            pdfs_raw = []
            for s in soportes[:5]:
                ruta = s.get("ruta")
                if ruta and os.path.exists(ruta):
                    try:
                        with open(ruta, "rb") as f:
                            pdfs_raw.append((s.get("nombre_archivo", "doc.pdf"), f.read()))
                    except Exception:
                        pass
            if not pdfs_raw:
                return json.dumps({"error": "No se pudieron leer los PDFs"})
            res = await auditar_forense(factura, pregunta, pdfs_raw=pdfs_raw)
            return json.dumps({
                "html": res.get("html", "")[:8000],
                "tokens": res.get("input_tokens", 0) + res.get("output_tokens", 0),
                "soportes_usados": len(pdfs_raw),
            }, ensure_ascii=False)

        if name == "buscar_glosa_en_bd":
            from app.models.db import GlosaRecord
            q = db.query(GlosaRecord)
            if args.get("factura"):
                q = q.filter(GlosaRecord.factura.ilike(f"%{args['factura']}%"))
            if args.get("eps"):
                q = q.filter(GlosaRecord.eps.ilike(f"%{args['eps']}%"))
            if args.get("codigo_glosa"):
                q = q.filter(GlosaRecord.codigo_glosa == args["codigo_glosa"].upper())
            if args.get("estado"):
                q = q.filter(GlosaRecord.estado == args["estado"].upper())
            rows = q.order_by(GlosaRecord.creado_en.desc()).limit(args.get("limite", 10)).all()
            return json.dumps({
                "glosas": [
                    {
                        "id": g.id,
                        "factura": g.factura,
                        "eps": g.eps,
                        "codigo_glosa": g.codigo_glosa,
                        "valor_objetado": float(g.valor_objetado or 0),
                        "estado": g.estado,
                        "creado_en": g.creado_en.isoformat() if g.creado_en else None,
                    }
                    for g in rows
                ],
                "total": len(rows),
            }, ensure_ascii=False)

        if name == "lookup_norma_legal":
            from app.services.ia_tools import _exec_lookup_norma
            return _exec_lookup_norma({
                "tipo": args.get("tipo"),
                "numero": args.get("numero"),
                "anio": args.get("anio"),
            })

        if name == "buscar_clausulas_contrato":
            from app.services.ia_tools import _exec_buscar_clausula_contrato
            return _exec_buscar_clausula_contrato({
                "eps": args.get("eps"),
                "tema": args.get("tema"),
            })

        if name == "lookup_tarifa_pactada":
            from app.services.ia_tools import _exec_lookup_tarifa
            return _exec_lookup_tarifa({
                "eps": args.get("eps"),
                "codigo_cups": args.get("codigo_cups"),
            })

        if name == "buscar_glosa_similar_levantada":
            from app.services.ia_tools import _exec_buscar_glosa_similar
            return _exec_buscar_glosa_similar({
                "eps": args.get("eps"),
                "codigo_glosa": args.get("codigo_glosa"),
                "limite": args.get("limite", 3),
            })

        if name == "estadisticas_sistema":
            from app.models.db import GlosaRecord
            from sqlalchemy import func
            from datetime import datetime, timedelta, timezone
            ahora = datetime.now(timezone.utc)
            inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            n_total = db.query(func.count(GlosaRecord.id)).scalar() or 0
            n_mes = db.query(func.count(GlosaRecord.id)).filter(GlosaRecord.creado_en >= inicio_mes).scalar() or 0
            valor_obj_mes = db.query(func.sum(GlosaRecord.valor_objetado)).filter(GlosaRecord.creado_en >= inicio_mes).scalar() or 0
            valor_rec_mes = db.query(func.sum(GlosaRecord.valor_recuperado)).filter(GlosaRecord.creado_en >= inicio_mes).scalar() or 0
            n_levantadas = db.query(func.count(GlosaRecord.id)).filter(GlosaRecord.estado == "LEVANTADA").scalar() or 0
            return json.dumps({
                "glosas_total": n_total,
                "glosas_mes": n_mes,
                "valor_objetado_mes": float(valor_obj_mes),
                "valor_recuperado_mes": float(valor_rec_mes),
                "glosas_levantadas_total": n_levantadas,
                "tasa_levantamiento_pct": round(100.0 * n_levantadas / max(n_total, 1), 2),
            }, ensure_ascii=False)

        return json.dumps({"error": f"Tool desconocida: {name}"})
    except Exception as e:
        logger.warning(f"[ASISTENTE] Tool {name} falló: {e}")
        return json.dumps({"error": str(e)[:200]})


def _sanear_content(content):
    """Sanea el `content` de un mensaje para Anthropic.

    Devuelve un content válido (str no vacío o list de bloques no vacía)
    o None si el mensaje quedaría sin contenido y debe descartarse.

    Anthropic devuelve 400 ("text content blocks must be non-empty") si
    se envía un bloque text con texto vacío/whitespace, un content string
    vacío, o un tool_result sin contenido.
    """
    if isinstance(content, str):
        return content if content.strip() else None

    if isinstance(content, list):
        bloques = []
        for b in content:
            if not isinstance(b, dict):
                if str(b).strip():
                    bloques.append({"type": "text", "text": str(b)})
                continue
            tipo = b.get("type")
            if tipo == "text":
                if (b.get("text") or "").strip():
                    bloques.append(b)
                # texto vacío → se descarta el bloque
            elif tipo == "tool_result":
                cont = b.get("content")
                if isinstance(cont, str) and not cont.strip():
                    b = {**b, "content": "(sin resultado)"}
                elif cont in (None, [], ""):
                    b = {**b, "content": "(sin resultado)"}
                bloques.append(b)
            else:
                # tool_use, image, etc. se conservan tal cual
                bloques.append(b)
        return bloques or None

    if content is None:
        return None
    # Cualquier otro tipo: convertir a texto si no es vacío
    return str(content) if str(content).strip() else None


async def chat_con_asistente(
    mensajes: list[dict],
    db,
    current_user,
    api_key: str = None,
    modelo: str = None,
    max_turns: int = 6,
) -> dict:
    """Loop multi-turn del asistente. Recibe historial de mensajes,
    devuelve la respuesta final + tools que usó.

    mensajes: [{"role": "user|assistant", "content": "..."}]

    Devuelve:
      {
        "respuesta": str (texto final del asistente),
        "tools_llamadas": list[{"name": str, "args": dict, "result_summary": str}],
        "modelo": str,
        "tokens": dict,
      }
    """
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    modelo = modelo or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    if not api_key:
        return {"respuesta": "", "error": "Anthropic API key no configurada"}
    if not mensajes:
        return {"respuesta": "", "error": "Sin mensajes"}

    timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=10.0)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Convertir historial a formato Anthropic, saneando bloques vacíos.
    # Anthropic rechaza con 400 "messages: text content blocks must be
    # non-empty" cualquier bloque de texto vacío/whitespace o un content
    # string vacío. Esto pasa típicamente al reenviar la respuesta del
    # modelo (que puede traer un bloque text vacío junto a un tool_use).
    msgs_anthropic = []
    for m in mensajes:
        if m.get("role") not in ("user", "assistant"):
            continue
        contenido_limpio = _sanear_content(m.get("content"))
        if contenido_limpio is None:
            continue
        msgs_anthropic.append({"role": m["role"], "content": contenido_limpio})

    tools_usadas = []
    tokens_total = {"input": 0, "output": 0}

    async with httpx.AsyncClient(timeout=timeout) as client:
        for turno in range(max_turns):
            try:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json={
                        "model": modelo,
                        "max_tokens": 4000,
                        "temperature": 0.2,
                        "system": SYSTEM_ASISTENTE_MAESTRO,
                        "tools": TOOLS_ASISTENTE,
                        "messages": msgs_anthropic,
                    },
                )
            except Exception as e:
                return {"respuesta": "", "error": f"Error red: {e}", "tools_llamadas": tools_usadas}

            if resp.status_code != 200:
                # Detectar específicamente errores de billing de Anthropic
                # y devolver mensaje útil al usuario en lugar de raw HTTP.
                error_body = resp.text[:500]
                error_user = ""
                try:
                    err_json = resp.json()
                    msg = err_json.get("error", {}).get("message", "")
                    if "credit balance is too low" in msg.lower() or "credits" in msg.lower():
                        error_user = (
                            "🚨 **Anthropic se quedó sin créditos**\n\n"
                            "Tu cuenta Anthropic no tiene créditos suficientes para responder. "
                            "Para resolver:\n\n"
                            "1. Recargá créditos en https://console.anthropic.com/settings/billing\n"
                            "2. Verificá que la API key activa esté en el workspace donde recargaste\n"
                            "3. Mientras tanto, podés usar los paneles directos del menú lateral "
                            "(Auditor Forense, Importación Masiva, etc.) que tienen fallback automático a Groq.\n\n"
                            "El sistema sigue funcionando — solo el chat unificado del asistente requiere Anthropic "
                            "específicamente porque usa tool calling avanzado."
                        )
                    elif resp.status_code == 429:
                        error_user = (
                            "⏳ **Rate limit Anthropic alcanzado**\n\n"
                            "Demasiadas requests en poco tiempo (Tier 1: 30K tokens/min Sonnet). "
                            "Esperá 30-60 segundos y reintentá. Si pasa seguido, considera subir a Tier 2 "
                            "(automático tras gastar $40 acumulado) o desactivar Multi-agent para reducir tokens."
                        )
                    elif resp.status_code == 529:
                        error_user = (
                            "⚠️ **Anthropic API sobrecargada**\n\n"
                            "Servidor Anthropic devuelve 529 (overloaded). Es un problema temporal de su lado. "
                            "Reintentá en 30-60 segundos."
                        )
                except Exception:
                    pass
                if not error_user:
                    error_user = f"Error HTTP {resp.status_code}: {error_body[:200]}"
                return {
                    "respuesta": error_user,
                    "error": None,  # NO marcamos error — devolvemos mensaje al usuario
                    "tools_llamadas": tools_usadas,
                    "modelo": "fallback-error",
                    "tokens": tokens_total,
                }

            data = resp.json()
            usage = data.get("usage", {})
            tokens_total["input"] += usage.get("input_tokens", 0)
            tokens_total["output"] += usage.get("output_tokens", 0)
            contenido = data.get("content") or []
            stop_reason = data.get("stop_reason")
            # Saneamos la respuesta del modelo ANTES de reinyectarla: puede
            # traer un bloque text vacío junto al tool_use, lo que rompería
            # el siguiente turno con 400 "text content blocks must be
            # non-empty".
            contenido_asistente = _sanear_content(contenido)
            if contenido_asistente is not None:
                msgs_anthropic.append(
                    {"role": "assistant", "content": contenido_asistente}
                )

            tool_uses = [
                b for b in contenido
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            if tool_uses and stop_reason == "tool_use":
                # Ejecutar cada tool
                tool_results_content = []
                for tu in tool_uses:
                    tool_id = tu.get("id")
                    tool_name = tu.get("name")
                    tool_input = tu.get("input", {})
                    logger.info(f"[ASISTENTE] turno={turno} tool={tool_name}")
                    result_str = await execute_tool_asistente(tool_name, tool_input, db, current_user)
                    if not (result_str or "").strip():
                        result_str = "(sin resultado)"
                    tools_usadas.append({
                        "name": tool_name,
                        "args": tool_input,
                        "result_preview": result_str[:200],
                    })
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_str,
                    })
                msgs_anthropic.append({"role": "user", "content": tool_results_content})
                continue

            # Stop final — extraer texto
            texto_final = ""
            for b in contenido:
                if isinstance(b, dict) and b.get("type") == "text":
                    texto_final += b.get("text", "")
            return {
                "respuesta": texto_final,
                "tools_llamadas": tools_usadas,
                "modelo": f"anthropic/{modelo}/asistente-maestro",
                "tokens": tokens_total,
                "turnos": turno + 1,
            }

    return {
        "respuesta": "",
        "error": f"Asistente no convergió en {max_turns} turnos",
        "tools_llamadas": tools_usadas,
    }
