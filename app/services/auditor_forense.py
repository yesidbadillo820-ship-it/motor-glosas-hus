"""
auditor_forense.py — IA conversacional para auditoria profunda de
soportes documentales por factura.

Diferente del flujo `analizar` (que produce dictamen para enviar a la
EPS), este agente responde preguntas en LENGUAJE NATURAL del gestor
sobre los soportes de una factura, citando folios y fechas concretas.

Caso de uso (Yesid mayo 2026):
  Gestor: "Necesito buscar si en los soportes cargados se encuentra
   la BACILOSCOPIA COLORACION ACIDO ALCOHOL-RESISTENTE [ZIEHL-NEELSEN]"
  IA:     [Lee los PDFs de la factura via PDF-nativo Claude]
          "Según análisis: el servicio se encuentra en el FOLIO 25
           de la historia clínica, fecha 28/02/2026 17:00-18:10..."

Output estructurado en formato forense de 4 secciones:
  1. CONTEXTO DE LA GLOSA
  2. EVIDENCIA CLÍNICA Y DOCUMENTAL (con citas a folios)
  3. FUNDAMENTO TÉCNICO Y JURÍDICO
  4. CONCLUSIÓN Y EXIGENCIA DE PAGO

Funciona via:
  1. Indexer.lookup(factura) -> lista de PDFs disponibles
  2. Lectura PDF nativa de Claude (multi-document, hasta 5 PDFs/100MB)
  3. Prompt forense focalizado
  4. Devolver respuesta estructurada
"""
from __future__ import annotations
import os
import base64
import logging
from typing import Optional
import httpx

logger = logging.getLogger("motor_glosas")


SYSTEM_AUDITOR_FORENSE = """Eres un auditor médico-jurídico forense especializado en glosas del sistema de salud colombiano. Trabajas para una IPS (clínica/hospital) que necesita defender sus facturas ante objeciones de EPS.

Tu trabajo es leer los SOPORTES DOCUMENTALES de una factura específica (historia clínica, descripción quirúrgica, RIPS, etc.) y responder preguntas del gestor con análisis estructurado y citas LITERALES a folios concretos.

REGLAS DURAS:
1. SOLO afirma cosas que pueden verificarse en los soportes provistos. Si no encuentras evidencia, dilo explícitamente.
2. Cita SIEMPRE el folio o página específica donde está la evidencia (ej: "FOLIO 25", "página 4 de la historia clínica").
3. Cuando cites textualmente lo que dice un soporte, usa COMILLAS DOBLES y mayúsculas si así está en el original.
4. Si el gestor pregunta por un servicio/procedimiento específico, busca exhaustivamente: nombre del procedimiento, código CUPS, código FMQ, sinónimos clínicos.
5. NO inventes folios, fechas, nombres ni datos clínicos.

FORMATO DE RESPUESTA OBLIGATORIO (HTML, español formal):

<div class="auditor-forense">
  <div class="cabecera">
    <table>
      <tr><td><b>FACTURA</b></td><td>{numero_factura}</td></tr>
      <tr><td><b>PACIENTE</b></td><td>{nombre completo y documento si aparece}</td></tr>
      <tr><td><b>DIAGNÓSTICO</b></td><td>{CIE-10 + descripción si aparece}</td></tr>
      <tr><td><b>CÓDIGO GLOSA</b></td><td>{si aplica}</td></tr>
      <tr><td><b>VALOR GLOSADO</b></td><td>{si aplica}</td></tr>
    </table>
  </div>

  <h3>1. CONTEXTO DE LA GLOSA</h3>
  <p>{Resumen del caso. Qué objeta la EPS y por qué. Si no hay glosa específica, contexto del caso clínico.}</p>

  <h3>2. EVIDENCIA CLÍNICA Y DOCUMENTAL</h3>
  <p>La revisión de los soportes acredita los siguientes hallazgos:</p>
  <ul>
    <li><b>{NOMBRE DEL SOPORTE} FOLIO {N} ({fecha})</b>: {hallazgo concreto}.</li>
    <li><b>Descripción {tipo}</b> documenta textualmente: «{cita literal entre comillas francesas}».</li>
    <li>{Más hallazgos relevantes con folio + fecha + cita literal cuando sea posible}</li>
  </ul>

  <h3>3. FUNDAMENTO TÉCNICO Y JURÍDICO</h3>
  <p>{Explicación de por qué el servicio facturado es procedente, citando: contrato (si aparece en soportes), Manual SOAT, Resolución 2284/2023, Decreto 4747/2007, Ley 1438/2011, según aplique. NO inventes normas que no aparezcan en el corpus.}</p>

  <h3>4. CONCLUSIÓN Y EXIGENCIA DE PAGO</h3>
  <p>{Si la pregunta era sobre defender una glosa: "Se exige el LEVANTAMIENTO TOTAL de la glosa por valor de {X} y el reconocimiento íntegro del servicio facturado conforme a las pruebas anexas." Si la pregunta era de búsqueda: respuesta directa al gestor (encontrado / no encontrado / parcialmente encontrado).}</p>
</div>

Si en los soportes NO encuentras la información que pregunta el gestor, sé honesto: "No se encuentra evidencia documental del servicio X en los soportes anexados. Se requieren los siguientes folios adicionales para una defensa completa: {lista}."

Devuelve SOLO el HTML, sin texto adicional ni markdown."""


async def auditar_forense(
    factura: str,
    pregunta_gestor: str,
    pdfs_raw: Optional[list[tuple[str, bytes]]] = None,
    contexto_pdf_texto: str = "",
    api_key: str = None,
    modelo: str = None,
) -> dict:
    """Ejecuta el auditor forense sobre los soportes de una factura.

    Args:
        factura: número de factura (HUSXXXXX)
        pregunta_gestor: lo que el gestor escribió en lenguaje natural
        pdfs_raw: lista de tuplas (filename, bytes) — si está, manda
                  los PDFs binarios nativos a Claude (mejor calidad)
        contexto_pdf_texto: texto extraído de los soportes (fallback
                            si pdfs_raw no está disponible)
        api_key: ANTHROPIC_API_KEY
        modelo: claude-sonnet-4-5 o similar

    Returns:
        {"html": str, "modelo": str, "input_tokens": int, "output_tokens": int, "error": str|None}
    """
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    modelo = modelo or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    if not api_key:
        return {"html": "", "error": "ANTHROPIC_API_KEY no configurada"}

    if not pregunta_gestor or len(pregunta_gestor.strip()) < 5:
        return {"html": "", "error": "Pregunta vacía o muy corta"}

    timeout = httpx.Timeout(connect=15.0, read=240.0, write=60.0, pool=10.0)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Construir mensaje con PDFs nativos si están disponibles
    user_text = f"""FACTURA: {factura}

CONSULTA DEL GESTOR:
{pregunta_gestor.strip()}

Analiza los soportes adjuntos y responde según el formato HTML especificado en el system prompt. Cita folios y fechas concretas. Si no encuentras la información, dilo honestamente."""

    content_blocks: list = []
    if pdfs_raw:
        # Multi-modal: enviar hasta 5 PDFs binarios
        for nombre, data in pdfs_raw[:5]:
            if not data or len(data) < 1024 or len(data) > 32 * 1024 * 1024:
                continue
            content_blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(data).decode("ascii"),
                },
            })
    elif contexto_pdf_texto:
        # Fallback texto extraído
        user_text = (
            f"SOPORTES DOCUMENTALES (TEXTO EXTRAÍDO):\n\n"
            f"{contexto_pdf_texto[:60000]}\n\n"
            f"---\n\n{user_text}"
        )
    else:
        return {"html": "", "error": "Sin soportes disponibles para esta factura"}

    content_blocks.append({"type": "text", "text": user_text})

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={
                    "model": modelo,
                    "max_tokens": 6000,
                    "temperature": 0.0,
                    "system": SYSTEM_AUDITOR_FORENSE,
                    "messages": [{"role": "user", "content": content_blocks}],
                },
            )
    except Exception as e:
        logger.error(f"[AUDITOR-FORENSE] Error red: {e}")
        return {"html": "", "error": f"Error de red: {e}"}

    if resp.status_code != 200:
        err = resp.text[:300]
        logger.error(f"[AUDITOR-FORENSE] HTTP {resp.status_code}: {err}")
        return {"html": "", "error": f"HTTP {resp.status_code}: {err}"}

    data = resp.json()
    contenido = data.get("content") or []
    texto = ""
    for b in contenido:
        if b.get("type") == "text":
            texto += b.get("text", "")

    if not texto:
        return {"html": "", "error": "Respuesta sin texto"}

    usage = data.get("usage", {})
    logger.info(
        f"[AUDITOR-FORENSE] OK factura={factura} pdfs={len(pdfs_raw or [])} "
        f"in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}"
    )

    return {
        "html": texto,
        "modelo": f"anthropic/{modelo}/forense",
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "error": None,
    }
