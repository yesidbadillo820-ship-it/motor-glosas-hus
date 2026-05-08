"""Servicio Google Gemini API (tercer proveedor IA gratis).

Tier gratis muy generoso:
- gemini-2.0-flash-exp: 15 RPM, 1500 RPD, 1M context
- gemini-1.5-flash: 15 RPM, 1500 RPD, 1M context
- gemini-1.5-pro: 2 RPM, 50 RPD, 2M context (mas calidad, menos rate)

Endpoint REST: usamos httpx directo (sin SDK extra) para mantener
deps minimas y compatibilidad con la arquitectura existente.

Roles funcionales propuestos:
- Anthropic Claude: PDF nativo (auditor forense), dictamenes premium,
  multi-modal con imagenes/PDFs binarios.
- Gemini Flash: tareas medianas con contexto largo (parsing de
  importacion masiva, extraccion estructurada de Excel/CSV con muchas
  filas), coaching IA, predicciones.
- Groq Llama: respuestas rapidas, dictamenes simples, fallback.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from typing import Optional

import httpx


logger = logging.getLogger("motor_glosas")


GEMINI_MODELS = {
    "flash": "gemini-2.0-flash-exp",        # mas rapido, 1M ctx
    "flash-1.5": "gemini-1.5-flash",         # estable, 1M ctx
    "pro": "gemini-1.5-pro",                 # mejor calidad, 2M ctx, 2 RPM free
}

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-exp"


class GeminiService:
    """Cliente para Google Gemini API.

    No depende del SDK oficial (google-generativeai) para evitar otra
    dependencia: usa httpx directo contra el endpoint REST.

    Uso:
        gem = GeminiService(api_key=...)
        respuesta, modelo = await gem.completar(
            system="Eres un experto auditor...",
            user="Analiza esta glosa: ...",
        )
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str = "", default_model: str = DEFAULT_GEMINI_MODEL, timeout: float = 90.0):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.default_model = default_model
        self.timeout = httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=5.0)

    @property
    def disponible(self) -> bool:
        return bool(self.api_key)

    async def completar(
        self,
        system: str,
        user: str,
        modelo: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 3000,
    ) -> tuple[str, str]:
        """Genera completion con Gemini. Retorna (texto, modelo_usado).

        Si Gemini falla, levanta excepcion para que el caller pruebe
        otro proveedor (es responsabilidad del fallback chain).
        """
        if not self.disponible:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        modelo = modelo or self.default_model
        url = f"{self.BASE_URL}/models/{modelo}:generateContent?key={self.api_key}"
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": user}]}
            ],
            # Gemini soporta system_instruction como campo separado en
            # v1beta (no como mensaje de rol "system" como Anthropic/Groq).
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
            },
            # Safety settings: BLOCK_NONE para no bloquear contenido
            # medico/jurídico que la IA podria considerar sensible
            # (procedimientos quirurgicos, medicamentos, etc).
            "safetySettings": [
                {"category": c, "threshold": "BLOCK_NONE"}
                for c in [
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                ]
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=body, headers={"Content-Type": "application/json"})
        if r.status_code != 200:
            err = r.text[:300]
            logger.warning(f"[GEMINI] HTTP {r.status_code}: {err}")
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {err}")
        data = r.json()
        # Estructura de respuesta:
        # {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}
        try:
            cand = data.get("candidates", [{}])[0]
            parts = cand.get("content", {}).get("parts", [])
            texto = "".join(p.get("text", "") for p in parts).strip()
        except (IndexError, KeyError) as e:
            raise RuntimeError(f"Gemini respuesta sin texto: {e}")
        if not texto:
            # blocking reason o filtro
            block = cand.get("finishReason", "")
            raise RuntimeError(f"Gemini sin texto (finish={block})")
        usage = data.get("usageMetadata", {}) or {}
        logger.info(
            f"[GEMINI] OK modelo={modelo} "
            f"in={usage.get('promptTokenCount', 0)} out={usage.get('candidatesTokenCount', 0)}"
        )
        return texto, f"gemini/{modelo}"

    async def completar_con_retry(
        self,
        system: str,
        user: str,
        modelo: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 3000,
        max_intentos: int = 3,
    ) -> tuple[str, str]:
        """Wrapper con retry exponencial para rate-limits del free tier."""
        ultimo_error: Exception = Exception("Sin intentos")
        for intento in range(max_intentos):
            try:
                return await self.completar(
                    system, user,
                    modelo=modelo,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                ultimo_error = e
                msg = str(e).lower()
                # 429 (rate limit), 503 (overloaded), 504 (timeout) son retriables
                retriable = any(c in msg for c in ["429", "503", "504", "rate", "overloaded", "timeout"])
                if retriable and intento < max_intentos - 1:
                    espera = min(2 ** intento, 8)
                    logger.warning(f"Gemini retriable: {e}, retry {intento+2}/{max_intentos} en {espera}s")
                    await asyncio.sleep(espera)
                    continue
                raise
        raise ultimo_error

    async def health_check(self) -> dict:
        """Ping ligero (1 token) para verificar conectividad y key."""
        if not self.disponible:
            return {"ok": False, "error": "sin GEMINI_API_KEY"}
        try:
            texto, modelo = await self.completar(
                system="ok",
                user="ping",
                max_tokens=4,
            )
            return {"ok": True, "modelo": modelo, "respuesta": texto[:50]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}
