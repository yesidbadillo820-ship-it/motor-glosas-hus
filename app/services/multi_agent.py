"""
multi_agent.py — Foundation del pipeline multi-agente.

ARQUITECTURA (v1, foundation):

  Glosa + Soportes + Contratos
              │
              ▼
       ┌──────────────┐
       │   AUDITOR    │  Identifica hallazgos: qué está
       │   AGENT      │  documentado, qué falta, qué es
       └──────┬───────┘  débil. Output: hallazgos.json
              │
              ▼ (en futuras sesiones se agregan)
       ┌──────────────┐
       │  ESTRATEGA   │  Diseña tesis defensiva, elige
       │  AGENT       │  normas + cláusulas a citar.
       └──────┬───────┘  Output: strategy.json
              │
              ▼
       ┌──────────────┐
       │  REDACTOR    │  Redacta dictamen profesional
       │  AGENT       │  en formato HTML 4-párrafos.
       └──────────────┘  Output: dictamen.html

Por qué multi-agente vs prompt monolítico:
  1. Cada agente con system prompt focalizado = mejor calidad
  2. Salidas estructuradas (JSON) = fácil debugging y observability
  3. Permite iterar/A/B testear cada agente por separado
  4. Cada agente puede usar las mismas TOOLS del módulo ia_tools

Trade-off: 3 llamadas a Claude vs 1 = ~3x costo por análisis. Solo
vale la pena cuando el caso es complejo. Por eso es OPT-IN vía env
var MULTI_AGENT_HABILITADO=1.

ESTADO ACTUAL (foundation):
  - ✅ Clase Agent base
  - ✅ Auditor agent funcional con prompt de extracción de hallazgos
  - ⏳ Estratega: pendiente sesión futura
  - ⏳ Redactor: pendiente sesión futura
  - ✅ Orquestador con fallback a flujo clásico si algo falla

Cuando se sumen Estratega y Redactor, este módulo reemplazará al
prompt monolítico actual para casos complejos. Mientras tanto, el
Auditor aporta hallazgos estructurados que se pueden inyectar como
contexto adicional en el flujo clásico.
"""
from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass
from typing import Optional
import httpx

logger = logging.getLogger("motor_glosas")


def multi_agent_habilitado() -> bool:
    return os.getenv("MULTI_AGENT_HABILITADO", "0").strip() in ("1", "true", "TRUE", "yes")


@dataclass
class Agent:
    """Clase base de un agente. Cada agente tiene un nombre, un system
    prompt focalizado, y opcionalmente un set de tools que puede llamar.

    El método `run` ejecuta una llamada single-turn (sin tool use) o
    multi-turn (con tool use), según `tools` esté vacío o no.
    """
    name: str
    system_prompt: str
    tools: Optional[list[dict]] = None
    max_tokens: int = 3000
    temperature: float = 0.0

    async def run(
        self,
        user_prompt: str,
        api_key: str,
        modelo: str,
        max_turns: int = 3,
    ) -> dict:
        """Ejecuta el agente y devuelve {"texto": str, "json": dict | None,
        "uso": dict, "error": str | None}.

        Si `tools` no es None, hace multi-turn loop ejecutando tools como
        en _llamar_anthropic_con_tools de glosa_service.
        Si `tools` es None, hace single-turn simple.
        """
        if not api_key:
            return {"texto": "", "json": None, "uso": {}, "error": "ANTHROPIC_API_KEY no configurada"}

        timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=10.0)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        messages = [{"role": "user", "content": user_prompt}]
        usage_acumulado: dict = {"input_tokens": 0, "output_tokens": 0}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if not self.tools:
                    # Single-turn
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json={
                            "model": modelo,
                            "max_tokens": self.max_tokens,
                            "temperature": self.temperature,
                            "system": self.system_prompt,
                            "messages": messages,
                        },
                    )
                    if resp.status_code != 200:
                        return {
                            "texto": "", "json": None, "uso": usage_acumulado,
                            "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                        }
                    data = resp.json()
                    texto = ""
                    for b in (data.get("content") or []):
                        if b.get("type") == "text":
                            texto += b.get("text", "")
                    usage = data.get("usage", {})
                    usage_acumulado["input_tokens"] = usage.get("input_tokens", 0)
                    usage_acumulado["output_tokens"] = usage.get("output_tokens", 0)
                    parsed = _intentar_parse_json(texto)
                    logger.info(
                        f"[AGENT:{self.name}] OK | "
                        f"in={usage_acumulado['input_tokens']} out={usage_acumulado['output_tokens']}"
                    )
                    return {"texto": texto, "json": parsed, "uso": usage_acumulado, "error": None}

                # Multi-turn con tools
                from app.services.ia_tools import execute_tool
                for turno in range(max_turns):
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json={
                            "model": modelo,
                            "max_tokens": self.max_tokens,
                            "temperature": self.temperature,
                            "system": self.system_prompt,
                            "tools": self.tools,
                            "messages": messages,
                        },
                    )
                    if resp.status_code != 200:
                        return {
                            "texto": "", "json": None, "uso": usage_acumulado,
                            "error": f"Agent {self.name} HTTP {resp.status_code}",
                        }
                    data = resp.json()
                    contenido = data.get("content") or []
                    usage = data.get("usage", {})
                    usage_acumulado["input_tokens"] += usage.get("input_tokens", 0)
                    usage_acumulado["output_tokens"] += usage.get("output_tokens", 0)
                    messages.append({"role": "assistant", "content": contenido})
                    tool_uses = [b for b in contenido if b.get("type") == "tool_use"]
                    if tool_uses and data.get("stop_reason") == "tool_use":
                        results = []
                        for tu in tool_uses:
                            r = execute_tool(tu.get("name"), tu.get("input", {}))
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.get("id"),
                                "content": r,
                            })
                        messages.append({"role": "user", "content": results})
                        continue
                    # Final
                    texto = ""
                    for b in contenido:
                        if b.get("type") == "text":
                            texto += b.get("text", "")
                    parsed = _intentar_parse_json(texto)
                    logger.info(
                        f"[AGENT:{self.name}] OK tras {turno+1} turnos | "
                        f"in={usage_acumulado['input_tokens']} out={usage_acumulado['output_tokens']}"
                    )
                    return {"texto": texto, "json": parsed, "uso": usage_acumulado, "error": None}
                return {
                    "texto": "", "json": None, "uso": usage_acumulado,
                    "error": f"Agent {self.name} no convergió en {max_turns} turnos",
                }
        except Exception as e:
            logger.error(f"[AGENT:{self.name}] Excepción: {e}")
            return {"texto": "", "json": None, "uso": usage_acumulado, "error": str(e)}


def _intentar_parse_json(texto: str) -> Optional[dict]:
    """Intenta parsear como JSON. Acepta envoltorios ```json ...```."""
    if not texto:
        return None
    t = texto.strip()
    if t.startswith("```"):
        import re as _re
        t = _re.sub(r"^```(?:json)?\s*", "", t)
        t = _re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        return None


# ─── Auditor Agent — primera instancia funcional ─────────────────────

AUDITOR_SYSTEM = """Eres un auditor médico-jurídico especializado en glosas de salud en Colombia (Res. 2284/2023, Decreto 4747/2007, Ley 1438/2011). Tu trabajo es identificar HALLAZGOS objetivos al revisar una glosa contra los soportes documentales.

Devuelve EXCLUSIVAMENTE un JSON válido con esta estructura:

{
  "hallazgos": [
    {
      "tipo": "fortaleza" | "debilidad" | "afirmacion_eps_falsa" | "soporte_faltante" | "calculo_erroneo",
      "severidad": "ALTA" | "MEDIA" | "BAJA",
      "descripcion": "<qué encontraste, en español, máximo 200 chars>",
      "evidencia": "<dónde está la evidencia: 'soporte X, página Y' o 'tabla glosa fila Z'>",
      "implicacion": "<qué significa para la defensa, máximo 200 chars>"
    }
  ],
  "fortalezas_principales": ["<3-5 puntos cortos a favor del prestador>"],
  "debilidades_principales": ["<3-5 puntos cortos en contra>"],
  "recomendacion_estrategia": "<1 línea: defender_total | defender_parcial | aceptar_parcial | aceptar_total>",
  "razon_recomendacion": "<máximo 300 chars explicando por qué>"
}

REGLAS:
1. SOLO hallazgos verificables en los datos provistos. Si no hay evidencia, NO lo afirmes.
2. Identifica al menos 3 hallazgos (más si hay material).
3. Si la EPS afirma algo (ej: "sin contrato", "valor incorrecto"), revisa contra los datos del sistema.
4. Si los soportes son insuficientes, márcalo como soporte_faltante con severidad ALTA.
5. NO redactes el dictamen — eso es trabajo del Redactor. Solo identifica hallazgos.
6. Devuelve SOLO el JSON, sin texto adicional ni markdown."""


def crear_agente_auditor() -> Agent:
    """Factory del Auditor Agent. Sin tools en v1 — solo análisis directo
    sobre la glosa + contexto provisto."""
    return Agent(
        name="auditor",
        system_prompt=AUDITOR_SYSTEM,
        tools=None,
        max_tokens=2500,
        temperature=0.0,
    )


async def ejecutar_auditor(
    texto_glosa: str,
    eps: str,
    codigo: str,
    contexto_pdf: str = "",
    valor_objetado: str = "",
    valor_facturado: str = "",
    valor_pactado: str = "",
    api_key: str = None,
    modelo: str = None,
) -> dict:
    """Ejecuta el Auditor Agent con los datos del caso. Devuelve el dict
    completo del agente: {texto, json, uso, error}."""
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    modelo = modelo or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    user_prompt = f"""DATOS DEL CASO:

EPS: {eps}
Código de glosa: {codigo}
Valor objetado: {valor_objetado or '—'}
Valor facturado: {valor_facturado or '—'}
Valor pactado: {valor_pactado or '—'}

═══ TEXTO DE LA GLOSA ═══
{texto_glosa[:8000]}

═══ SOPORTES DOCUMENTALES ═══
{(contexto_pdf or '(sin soportes adjuntos)')[:30000]}

Identifica los hallazgos y devuelve el JSON especificado."""

    auditor = crear_agente_auditor()
    return await auditor.run(user_prompt, api_key, modelo)
