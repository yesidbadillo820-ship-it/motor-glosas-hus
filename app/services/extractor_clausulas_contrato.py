"""
extractor_clausulas_contrato.py — Lee el PDF de un contrato y extrae las
cláusulas contractuales relevantes al proceso de glosas, usando Claude.

Salida: lista estructurada de cláusulas con número, tema, título y texto
literal. El motor de glosas las inyecta como contexto al generar dictamen
de manera que cite literalmente la cláusula contractual aplicable.

Mapeo de temas a códigos de glosa (primeras 2 letras):
    TA = Tarifas
    SO = Soportes / documentación
    AU = Autorizaciones
    CO = Cobertura / pertinencia
    FA = Facturación / pagos
    NN = Notas / generales
"""
import os
import json
import logging
import re
import httpx

logger = logging.getLogger("motor_glosas")


SYSTEM_EXTRACCION = """Eres un abogado especializado en contratos del sistema de salud colombiano (Ley 100/1993, Decreto 4747/2007, Resolución 2284/2023). Tu tarea es leer el texto de un contrato firmado entre una IPS (clínica/hospital) y una EPS, y extraer las cláusulas que pueden ser citadas como defensa contractual ante glosas.

Devuelve EXCLUSIVAMENTE un JSON válido con esta forma:

{
  "clausulas": [
    {
      "numero": "<número o identificador de la cláusula, ej: '7.3', 'PARÁGRAFO 2', 'Anexo II'>",
      "tema": "<TA|SO|AU|CO|FA|NN>",
      "titulo": "<resumen corto de la cláusula, máx 100 chars>",
      "texto_literal": "<texto exacto de la cláusula, sin parafrasear, preservando comillas y mayúsculas>",
      "pagina": <número de página si aparece, o null>
    }
  ]
}

Reglas estrictas:
1. EXTRAE solo cláusulas útiles para responder glosas: tarifas pactadas, manual tarifario aplicable, soportes exigibles, autorizaciones requeridas, exclusiones de cobertura, modos de facturación, vigencia, modificaciones, mecanismos de glosa.
2. NO inventes ni resumas. El texto_literal debe ser COPIA EXACTA del contrato.
3. Si una cláusula es muy larga (>800 chars) córtala al fragmento más relevante y agrega "...".
4. Mapea cada cláusula al tema correcto:
   - TA: tarifas, valor servicios, manual SOAT/ISS, anexos tarifarios, IPC
   - SO: soportes, anexos documentales, RIPS, factura, historia clínica
   - AU: autorizaciones, prior, urgencias, red contratada
   - CO: cobertura PBS, exclusiones, pertinencia, paquetes
   - FA: facturación, plazos pago, intereses mora, conciliación
   - NN: vigencia, modificaciones, terminación, jurisdicción, otros generales
5. Si no encuentras NINGUNA cláusula extraíble, devuelve {"clausulas": []}.
6. Devuelve SOLO el JSON, sin texto adicional ni markdown."""


def _limpiar_json_respuesta(texto: str) -> str:
    """Claude a veces envuelve el JSON en ```json ... ```. Lo desenvolvemos."""
    t = texto.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


async def extraer_clausulas_desde_texto(
    texto_contrato: str,
    eps: str,
    api_key: str = None,
    modelo: str = None,
) -> list[dict]:
    """Llama a Claude con el texto extraído del PDF y retorna lista de
    dicts con: numero, tema, titulo, texto_literal, pagina.

    Si la API falla o devuelve JSON inválido, retorna [] y loggea warning
    (el endpoint marcará la subida como "PDF guardado, extracción pendiente").
    """
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    modelo = modelo or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    if not api_key:
        logger.warning("[CLAUSULAS] ANTHROPIC_API_KEY no configurada — saltando extracción")
        return []

    if not texto_contrato or len(texto_contrato.strip()) < 200:
        logger.warning(f"[CLAUSULAS] Texto del contrato muy corto ({len(texto_contrato or '')} chars) — saltando")
        return []

    # Truncar para no explotar tokens. Contratos típicos 30-50 páginas
    # caben en ~80k chars (~25k tokens). Cap a 100k chars (~33k tokens).
    texto_truncado = texto_contrato[:100_000]
    truncado = len(texto_contrato) > 100_000

    user_prompt = (
        f"Contrato de la EPS: {eps}\n"
        f"{'(Texto truncado a primeros 100k chars de un contrato más largo)' if truncado else ''}\n\n"
        f"--- INICIO TEXTO CONTRATO ---\n"
        f"{texto_truncado}\n"
        f"--- FIN TEXTO CONTRATO ---"
    )

    timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=10.0)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={
                    "model": modelo,
                    "max_tokens": 8000,
                    "temperature": 0.0,
                    "system": SYSTEM_EXTRACCION,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
    except Exception as e:
        logger.error(f"[CLAUSULAS] Error llamando a Anthropic: {e}")
        return []

    if resp.status_code != 200:
        logger.error(f"[CLAUSULAS] Anthropic HTTP {resp.status_code}: {resp.text[:300]}")
        return []

    data = resp.json()
    if not data.get("content"):
        logger.error(f"[CLAUSULAS] Respuesta sin content: {str(data)[:300]}")
        return []

    texto_resp = data["content"][0].get("text", "")
    json_text = _limpiar_json_respuesta(texto_resp)

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.error(f"[CLAUSULAS] JSON inválido de Claude: {e} — texto: {json_text[:300]}")
        return []

    clausulas = parsed.get("clausulas", [])
    if not isinstance(clausulas, list):
        logger.error(f"[CLAUSULAS] 'clausulas' no es lista: {type(clausulas)}")
        return []

    # Sanitizar y filtrar entradas válidas
    TEMAS_VALIDOS = {"TA", "SO", "AU", "CO", "FA", "NN"}
    sanas = []
    for c in clausulas:
        if not isinstance(c, dict):
            continue
        texto = (c.get("texto_literal") or "").strip()
        if len(texto) < 30:
            continue
        tema = (c.get("tema") or "NN").upper().strip()
        if tema not in TEMAS_VALIDOS:
            tema = "NN"
        sanas.append({
            "numero": (c.get("numero") or "").strip()[:80],
            "tema": tema,
            "titulo": (c.get("titulo") or "").strip()[:300],
            "texto_literal": texto[:5000],
            "pagina": c.get("pagina") if isinstance(c.get("pagina"), int) else None,
        })

    logger.info(f"[CLAUSULAS] Extraídas {len(sanas)} cláusulas válidas para EPS={eps}")
    return sanas


# ─── Helper para inyectar cláusulas relevantes al prompt IA ────────────
# Lo invoca `glosa_ia_prompts.build_user_prompt` para que el dictamen
# pueda citar literalmente la cláusula contractual aplicable al código
# de glosa que se está respondiendo.

def bloque_clausulas_contrato_para_prompt(eps: str, codigo: str, max_clausulas: int = 3) -> str:
    """Devuelve el bloque de cláusulas del contrato vigente, formateado
    para el user prompt. Filtra por EPS + tema (matchea con `codigo[:2]`).

    Si no hay cláusulas almacenadas para esa EPS, devuelve "" — el resto
    del prompt sigue funcionando normalmente con la lógica anterior
    (clausulas_anti_rebatimiento + normativa).

    Abre su propia sesión BD (SessionLocal) para no requerir cambios en
    la firma de `build_user_prompt`. Cierra la sesión siempre.
    """
    if not eps or not codigo:
        return ""
    tema = (codigo[:2] or "").upper().strip()
    if not tema:
        return ""

    try:
        from app.database import SessionLocal
        from app.models.db import ClausulaContrato
    except Exception as e:
        logger.debug(f"[CLAUSULAS] No se pudieron importar deps: {e}")
        return ""

    db = SessionLocal()
    try:
        # Prioridad 1: cláusulas del tema exacto (TA, SO, AU, etc.)
        # Prioridad 2: cláusulas NN (generales) como respaldo si hay <3
        clausulas_tema = (
            db.query(ClausulaContrato)
            .filter(ClausulaContrato.eps == eps, ClausulaContrato.tema == tema)
            .order_by(ClausulaContrato.id)
            .limit(max_clausulas)
            .all()
        )
        seleccionadas = list(clausulas_tema)
        if len(seleccionadas) < max_clausulas:
            faltan = max_clausulas - len(seleccionadas)
            ids_existentes = {c.id for c in seleccionadas}
            clausulas_nn = (
                db.query(ClausulaContrato)
                .filter(
                    ClausulaContrato.eps == eps,
                    ClausulaContrato.tema == "NN",
                )
                .order_by(ClausulaContrato.id)
                .limit(faltan)
                .all()
            )
            for c in clausulas_nn:
                if c.id not in ids_existentes:
                    seleccionadas.append(c)
                if len(seleccionadas) >= max_clausulas:
                    break

        if not seleccionadas:
            return ""

        lineas = []
        for c in seleccionadas:
            num = c.numero_clausula or "(s/n)"
            txt = (c.texto_literal or "").strip()
            if len(txt) > 600:
                txt = txt[:600] + "…"
            lineas.append(f"  • Cláusula {num}: «{txt}»")

        return (
            "\n[CLÁUSULAS LITERALES DEL CONTRATO VIGENTE CON ESTA EPS — cita textualmente al menos UNA en el dictamen]\n"
            + "\n".join(lineas)
            + "\n"
        )
    except Exception as e:
        logger.warning(f"[CLAUSULAS] Error consultando cláusulas eps={eps} codigo={codigo}: {e}")
        return ""
    finally:
        try:
            db.close()
        except Exception:
            pass
