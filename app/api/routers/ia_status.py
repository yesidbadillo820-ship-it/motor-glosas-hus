"""Status y roles de los 3 proveedores IA del motor.

GET /ia-status/proveedores
    Devuelve estado, modelo configurado, rol, y disponibilidad de cada
    uno de los 3 proveedores (Anthropic, Gemini, Groq).

GET /ia-status/health-check
    Ping ligero a cada proveedor (1 token c/u) para verificar que
    realmente responden, no solo que la key existe.
"""
from __future__ import annotations
import os
import asyncio
from typing import Optional

import httpx
from fastapi import APIRouter, Depends

from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.models.db import UsuarioRecord


router = APIRouter(prefix="/ia-status", tags=["ia-status"])


PROVEEDORES_INFO = {
    "anthropic": {
        "nombre": "Anthropic Claude",
        "tipo": "premium",
        "rol": "PDF nativo, dictamenes complejos, multi-modal",
        "fortaleza": "Razonamiento juridico fino, citas precisas, redaccion legal en español",
        "tier": "Pago (creditos USD)",
        "modelos_disponibles": [
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-opus-4-7",
        ],
        "rate_limit": "Variable (Tier 1: 50K ITPM, Tier 2+: ilimitado)",
        "console_url": "https://console.anthropic.com/settings/billing",
    },
    "openrouter": {
        "nombre": "OpenRouter (DeepSeek/Llama/etc)",
        "tipo": "meta-router-cheap",
        "rol": "Fallback #1 cuando Anthropic 429ea — ofrece DeepSeek V3 a 5% del costo de Sonnet con calidad similar, ademas de fallback gratis a Llama 3.3 70B",
        "fortaleza": "1 sola key da acceso a 100+ modelos. DeepSeek V3 ~$0.27/M tokens (30x mas barato que Sonnet). Si DeepSeek cae, OpenRouter prueba solo con Llama 70B gratis sin retry manual.",
        "tier": "Pay-as-you-go (~$5 te dan miles de queries) + modelos :free",
        "modelos_disponibles": [
            "deepseek/deepseek-chat",
            "deepseek/deepseek-r1",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct",
            "google/gemma-2-27b-it",
        ],
        "rate_limit": "Pago: practicamente sin limite. :free models: 50 RPD aprox",
        "console_url": "https://openrouter.ai/keys",
    },
    "gemini": {
        "nombre": "Google Gemini",
        "tipo": "free-tier",
        "rol": "Fallback #2 cuando hay contexto enorme (1M tokens). Tier free se agota rapido bajo carga (15 RPM / 1500 RPD).",
        "fortaleza": "1M+ tokens contexto, gratis 15 RPM, multi-modal nativo",
        "tier": "Free tier muy generoso",
        "modelos_disponibles": [
            "gemini-2.0-flash-exp",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
        "rate_limit": "Flash: 15 RPM / 1500 RPD · Pro: 2 RPM / 50 RPD",
        "console_url": "https://aistudio.google.com/apikey",
    },
    "groq": {
        "nombre": "Groq Llama",
        "tipo": "free-fast",
        "rol": "Ultimo fallback. Respuestas rapidas, dictamenes simples cuando todo lo demas cae.",
        "fortaleza": "Velocidad bestial (LPU dedicado): 200-400 tokens/s",
        "tier": "Free con rate limits",
        "modelos_disponibles": [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "openai/gpt-oss-120b",
            "mixtral-8x7b-32768",
        ],
        "rate_limit": "30 RPM en tier gratis",
        "console_url": "https://console.groq.com/keys",
    },
}


@router.get("/proveedores")
def listar_proveedores(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista los 3 proveedores con su configuracion y disponibilidad
    actual (solo basado en env vars, no hace ping)."""
    cfg = get_settings()
    primary = (cfg.primary_ai or "anthropic").lower()

    estado: list[dict] = []
    for clave in ["anthropic", "openrouter", "gemini", "groq"]:
        info = dict(PROVEEDORES_INFO[clave])
        if clave == "anthropic":
            info["api_key_configurada"] = bool(cfg.anthropic_api_key)
            info["modelo_actual"] = cfg.anthropic_model
            info["api_key_prefix"] = cfg.anthropic_api_key[:10] if cfg.anthropic_api_key else ""
        elif clave == "openrouter":
            info["api_key_configurada"] = bool(cfg.openrouter_api_key)
            info["modelo_actual"] = cfg.openrouter_model
            info["api_key_prefix"] = cfg.openrouter_api_key[:10] if cfg.openrouter_api_key else ""
        elif clave == "gemini":
            info["api_key_configurada"] = bool(cfg.gemini_api_key)
            info["modelo_actual"] = cfg.gemini_model
            info["api_key_prefix"] = cfg.gemini_api_key[:10] if cfg.gemini_api_key else ""
        else:  # groq
            info["api_key_configurada"] = bool(cfg.groq_api_key)
            info["modelo_actual"] = cfg.groq_model
            info["api_key_prefix"] = cfg.groq_api_key[:10] if cfg.groq_api_key else ""
        info["es_primary"] = clave == primary
        info["clave"] = clave
        estado.append(info)

    return {
        "primary_ai": primary,
        "proveedores": estado,
        "fallback_chain": _calcular_fallback_chain(cfg, primary),
    }


def _calcular_fallback_chain(cfg, primary: str) -> list[str]:
    """Construye la cadena real de fallback que usa GlosaService.

    Espejo de la logica en glosa_service.py `_llamar_ia_con_fallback`.
    OpenRouter (DeepSeek) entra como #1 en cadenas no-OpenRouter porque
    es 30x mas barato que Anthropic con calidad similar.
    """
    chain = []
    disponibles = []
    if cfg.openrouter_api_key: disponibles.append("openrouter")
    if cfg.anthropic_api_key: disponibles.append("anthropic")
    if cfg.gemini_api_key: disponibles.append("gemini")
    if cfg.groq_api_key: disponibles.append("groq")

    if primary in disponibles:
        chain.append(primary)
    # Orden de preferencia para fallbacks: OpenRouter > Anthropic > Gemini > Groq
    for prov in ("openrouter", "anthropic", "gemini", "groq"):
        if prov in disponibles and prov not in chain:
            chain.append(prov)
    return chain


@router.get("/health-check")
async def health_check(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Ping ligero a cada proveedor (~1 token c/u) para verificar
    conectividad real. Mide latencia. Usa asyncio.gather para hacerlos
    en paralelo."""
    cfg = get_settings()
    resultados = {}

    async def _ping_anthropic():
        if not cfg.anthropic_api_key:
            return {"ok": False, "error": "sin API key"}
        import time
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": cfg.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5",
                        "max_tokens": 3,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                return {"ok": True, "latency_ms": ms, "modelo": "claude-haiku-4-5"}
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:150]}", "latency_ms": ms}
        except Exception as e:
            return {"ok": False, "error": str(e)[:150]}

    async def _ping_gemini():
        if not cfg.gemini_api_key:
            return {"ok": False, "error": "sin API key"}
        from app.services.gemini_service import GeminiService
        gs = GeminiService(api_key=cfg.gemini_api_key, default_model=cfg.gemini_model)
        import time
        t0 = time.time()
        try:
            res = await gs.health_check()
            ms = int((time.time() - t0) * 1000)
            res["latency_ms"] = ms
            return res
        except Exception as e:
            return {"ok": False, "error": str(e)[:150]}

    async def _ping_groq():
        if not cfg.groq_api_key:
            return {"ok": False, "error": "sin API key"}
        import time
        t0 = time.time()
        try:
            from groq import AsyncGroq
            g = AsyncGroq(api_key=cfg.groq_api_key, timeout=10.0)
            r = await g.chat.completions.create(
                model=cfg.groq_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=3,
                temperature=0,
            )
            ms = int((time.time() - t0) * 1000)
            return {
                "ok": True,
                "latency_ms": ms,
                "modelo": cfg.groq_model,
                "respuesta": (r.choices[0].message.content or "")[:50],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def _ping_openrouter():
        if not cfg.openrouter_api_key:
            return {"ok": False, "error": "sin API key"}
        from app.services.openrouter_service import OpenRouterService
        ors = OpenRouterService(
            api_key=cfg.openrouter_api_key,
            default_model=cfg.openrouter_model,
        )
        import time
        t0 = time.time()
        try:
            res = await ors.health_check()
            ms = int((time.time() - t0) * 1000)
            res["latency_ms"] = ms
            return res
        except Exception as e:
            return {"ok": False, "error": str(e)[:150]}

    pings = await asyncio.gather(
        _ping_anthropic(), _ping_openrouter(), _ping_gemini(), _ping_groq(),
        return_exceptions=True,
    )
    resultados["anthropic"] = pings[0] if not isinstance(pings[0], Exception) else {"ok": False, "error": str(pings[0])}
    resultados["openrouter"] = pings[1] if not isinstance(pings[1], Exception) else {"ok": False, "error": str(pings[1])}
    resultados["gemini"] = pings[2] if not isinstance(pings[2], Exception) else {"ok": False, "error": str(pings[2])}
    resultados["groq"] = pings[3] if not isinstance(pings[3], Exception) else {"ok": False, "error": str(pings[3])}

    todos_ok = all(r.get("ok") for r in resultados.values())
    alguno_ok = any(r.get("ok") for r in resultados.values())

    return {
        "todos_ok": todos_ok,
        "alguno_ok": alguno_ok,
        "primary_ai": cfg.primary_ai,
        "proveedores": resultados,
    }
