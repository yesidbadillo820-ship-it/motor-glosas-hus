"""Servicio OpenRouter — meta-router de modelos IA.

OpenRouter (openrouter.ai) expone una API compatible con OpenAI que
da acceso a 100+ modelos LLM con 1 sola key. Util para:

  • Meter DeepSeek V3 como fallback super-barato (≈ $0.27/M tokens
    input, ~30× mas barato que Claude Sonnet con calidad comparable
    en redaccion legal).
  • Acceder a modelos "free" como meta-llama/llama-3.3-70b-instruct
    sin gestionar cuentas separadas.
  • Resiliencia: cuando un modelo X esta caido, OpenRouter reintenta
    automaticamente con el siguiente del fallback que le pasemos en
    el campo `models[]`.

Endpoint REST OpenAI-compatible: usamos httpx directo (sin SDK extra)
manteniendo la misma estetica que `gemini_service.py` para uniformidad.

Roles funcionales sugeridos en este proyecto:
  - Anthropic Claude: PRIMARIO. Multi-modal nativo (PDFs/imagenes),
    razonamiento legal premium en español.
  - OpenRouter (DeepSeek): FALLBACK #1 cuando Anthropic 429ea o cae.
    Calidad cercana a Sonnet a 5% del costo. Solo texto (no PDFs).
  - Gemini: FALLBACK #2 (1M context). Util cuando hay contexto enorme
    pero su tier gratis se agota rapido bajo carga.
  - Groq Llama: FALLBACK #3 (ultimo recurso). Velocidad bestial pero
    calidad inferior a los demas para argumentacion juridica densa.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("motor_glosas")


# Modelos validos en mayo 2026. Lista completa: openrouter.ai/models
# Precio referenciado por 1M tokens (input / output).
OPENROUTER_MODELS = {
    "deepseek/deepseek-chat":               "$0.27 / $1.10",   # V3, default
    "deepseek/deepseek-r1":                 "$0.55 / $2.19",   # reasoning
    "meta-llama/llama-3.3-70b-instruct":    "$0.07 / $0.25",   # barato
    "meta-llama/llama-3.3-70b-instruct:free": "FREE (50 RPD)",  # gratis
    "qwen/qwen-2.5-72b-instruct":           "$0.13 / $0.39",
    "google/gemma-2-27b-it":                "$0.27 / $0.27",
    "mistralai/mistral-large-2411":         "$2.00 / $6.00",
}

DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-chat"


class OpenRouterService:
    """Cliente para OpenRouter API (compatible OpenAI).

    Uso basico:
        cli = OpenRouterService(api_key="sk-or-v1-...")
        texto, modelo = await cli.completar_con_retry(
            system="Eres un experto auditor...",
            user="Analiza esta glosa: ...",
        )

    Multi-fallback dentro de OpenRouter (su feature `models[]`):
        texto, modelo = await cli.completar(
            system=..., user=...,
            modelo="deepseek/deepseek-chat",
            fallbacks=["meta-llama/llama-3.3-70b-instruct:free"],
        )
    Si DeepSeek falla en su servidor, OpenRouter reintenta solo con
    Llama sin que el caller tenga que manejar el reintento.

    NOTA: este cliente es solo TEXTO. Para multi-modal (PDFs/imagenes
    binarios) seguir usando AnthropicService o GeminiService — solo
    algunos modelos en OpenRouter soportan vision y la API es distinta.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str = "",
        default_model: str = DEFAULT_OPENROUTER_MODEL,
        timeout: float = 90.0,
        app_url: str = "https://motor-glosas-hus.fly.dev",
        app_title: str = "Motor Glosas HUS",
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.default_model = default_model
        self.timeout = httpx.Timeout(
            connect=10.0, read=timeout, write=30.0, pool=5.0,
        )
        # Headers de identificacion que OpenRouter recomienda incluir
        # — ayudan a que el dashboard del proyecto muestre nuestra app.
        self.app_url = app_url
        self.app_title = app_title

    @property
    def disponible(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_title,
        }

    async def completar(
        self,
        system: str,
        user: str,
        modelo: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 3000,
        fallbacks: Optional[list[str]] = None,
    ) -> tuple[str, str]:
        """Genera completion. Retorna (texto, modelo_usado).

        Si el modelo principal falla en el servidor, OpenRouter cae
        automaticamente al siguiente de `fallbacks` sin gastar nuestro
        tiempo en reintentos manuales.
        """
        if not self.disponible:
            raise RuntimeError("OPENROUTER_API_KEY no configurada")
        modelo = modelo or self.default_model
        url = f"{self.BASE_URL}/chat/completions"

        body: dict = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if fallbacks:
            body["models"] = [modelo] + fallbacks

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=body, headers=self._headers())

        if r.status_code != 200:
            err = r.text[:300]
            logger.warning(f"[OPENROUTER] HTTP {r.status_code}: {err}")
            raise RuntimeError(f"OpenRouter HTTP {r.status_code}: {err}")

        data = r.json()
        try:
            choice = data["choices"][0]
            texto = (choice["message"]["content"] or "").strip()
            modelo_usado = data.get("model", modelo)
        except (IndexError, KeyError) as e:
            raise RuntimeError(f"OpenRouter respuesta sin texto: {e}")

        if not texto:
            finish = (data.get("choices", [{}])[0] or {}).get("finish_reason", "")
            raise RuntimeError(f"OpenRouter sin texto (finish={finish})")

        usage = data.get("usage", {}) or {}
        logger.info(
            f"[OPENROUTER] OK modelo={modelo_usado} "
            f"in={usage.get('prompt_tokens', 0)} "
            f"out={usage.get('completion_tokens', 0)}"
        )
        return texto, f"openrouter/{modelo_usado}"

    async def completar_con_retry(
        self,
        system: str,
        user: str,
        modelo: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 3000,
        max_intentos: int = 3,
        fallbacks: Optional[list[str]] = None,
    ) -> tuple[str, str]:
        """Wrapper con retry exponencial para 429/5xx/timeout.

        OpenRouter maneja su propio fallback entre modelos via
        `models[]`; este retry adicional cubre fallos de RED entre
        nuestro servicio y OpenRouter (timeouts, 503 transitorios).
        """
        ultimo_error: Exception = Exception("Sin intentos")
        for intento in range(max_intentos):
            try:
                return await self.completar(
                    system, user,
                    modelo=modelo,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    fallbacks=fallbacks,
                )
            except Exception as e:
                ultimo_error = e
                msg = str(e).lower()
                retriable = any(
                    c in msg for c in
                    ["429", "503", "504", "rate", "overloaded", "timeout", "connection"]
                )
                if retriable and intento < max_intentos - 1:
                    espera = min(2 ** intento, 8)
                    logger.warning(
                        f"OpenRouter retriable: {e}, "
                        f"retry {intento+2}/{max_intentos} en {espera}s"
                    )
                    await asyncio.sleep(espera)
                    continue
                raise
        raise ultimo_error

    async def health_check(self) -> dict:
        """Ping ligero (1 token) para verificar conectividad y key."""
        if not self.disponible:
            return {"ok": False, "error": "sin OPENROUTER_API_KEY"}
        try:
            texto, modelo = await self.completar(
                system="ok",
                user="ping",
                max_tokens=4,
            )
            return {"ok": True, "modelo": modelo, "respuesta": texto[:50]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}
