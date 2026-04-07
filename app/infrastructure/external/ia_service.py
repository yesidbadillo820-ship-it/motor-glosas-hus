import os
import io
import asyncio
import logging
from typing import Optional, Tuple

import httpx
from groq import AsyncGroq

logger = logging.getLogger("ia_service")


class IAService:
    def __init__(self, groq_api_key: Optional[str] = None, anthropic_api_key: Optional[str] = None):
        self.groq = AsyncGroq(api_key=groq_api_key) if groq_api_key else None
        self.anthropic_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")

    async def analizar(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_model: str = "llama-3.3-70b-versatile",
    ) -> Tuple[str, str]:
        if self.groq:
            try:
                resp = await self.groq.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=fallback_model,
                    temperature=0.1,
                )
                logger.info("IA: Groq responded successfully")
                return resp.choices[0].message.content, f"groq/{fallback_model}"
            except Exception as e:
                logger.warning(f"Groq failed: {e}, trying Anthropic...")

        if self.anthropic_key:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": self.anthropic_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": "claude-3-5-sonnet-20240620",
                            "max_tokens": 1500,
                            "system": system_prompt,
                            "messages": [{"role": "user", "content": user_prompt}],
                        },
                    )
                    result = resp.json()
                    logger.info("IA: Anthropic responded successfully")
                    return result["content"][0]["text"], "anthropic/claude-3.5"
            except Exception as e:
                logger.error(f"Anthropic failed: {e}")

        logger.error("IA: All providers failed, using fallback")
        return "<paciente>ERROR DE CONEXIÓN IA</paciente><argumento>REVISIÓN MANUAL REQUERIDA</argumento>", "fallback"