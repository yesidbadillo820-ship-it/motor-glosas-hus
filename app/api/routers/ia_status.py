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
    "gemini": {
        "nombre": "Google Gemini",
        "tipo": "free-tier",
        "rol": "Tareas medianas, contexto largo, fallback gratis cuando Anthropic out",
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
        "rol": "Respuestas rapidas, dictamenes simples, ultimo fallback",
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
    for clave in ["anthropic", "gemini", "groq"]:
        info = dict(PROVEEDORES_INFO[clave])
        if clave == "anthropic":
            info["api_key_configurada"] = bool(cfg.anthropic_api_key)
            info["modelo_actual"] = cfg.anthropic_model
            info["api_key_prefix"] = cfg.anthropic_api_key[:10] if cfg.anthropic_api_key else ""
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
    """Construye la cadena real de fallback que usa GlosaService."""
    chain = []
    if primary == "anthropic" and cfg.anthropic_api_key:
        chain.append("anthropic")
        if cfg.gemini_api_key: chain.append("gemini")
        if cfg.groq_api_key: chain.append("groq")
    elif primary == "gemini" and cfg.gemini_api_key:
        chain.append("gemini")
        if cfg.anthropic_api_key: chain.append("anthropic")
        if cfg.groq_api_key: chain.append("groq")
    else:
        if cfg.groq_api_key: chain.append("groq")
        if cfg.gemini_api_key: chain.append("gemini")
        if cfg.anthropic_api_key: chain.append("anthropic")
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

    pings = await asyncio.gather(
        _ping_anthropic(), _ping_gemini(), _ping_groq(),
        return_exceptions=True,
    )
    resultados["anthropic"] = pings[0] if not isinstance(pings[0], Exception) else {"ok": False, "error": str(pings[0])}
    resultados["gemini"] = pings[1] if not isinstance(pings[1], Exception) else {"ok": False, "error": str(pings[1])}
    resultados["groq"] = pings[2] if not isinstance(pings[2], Exception) else {"ok": False, "error": str(pings[2])}

    todos_ok = all(r.get("ok") for r in resultados.values())
    alguno_ok = any(r.get("ok") for r in resultados.values())

    return {
        "todos_ok": todos_ok,
        "alguno_ok": alguno_ok,
        "primary_ai": cfg.primary_ai,
        "proveedores": resultados,
    }
