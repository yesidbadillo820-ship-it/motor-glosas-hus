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


# Modelos validos en v1beta de Generative Language API (mayo 2026).
# El experimental 2.0-flash-exp fue deprecado al pasar 2.0-flash a GA.
# 2.5 Flash/Pro son los newest. 1.5 sigue activo como fallback.
GEMINI_MODELS = {
    "2.0-flash": "gemini-2.0-flash",         # GA, default. 15 RPM/1500 RPD free
    "2.0-flash-lite": "gemini-2.0-flash-lite",  # mas barato, mismo tier
    "2.5-flash": "gemini-2.5-flash",         # newer, 15 RPM/1500 RPD free
    "2.5-pro": "gemini-2.5-pro",             # mejor calidad, 5 RPM/25 RPD free
    "1.5-flash": "gemini-1.5-flash",         # legacy estable, 1M ctx
    "1.5-pro": "gemini-1.5-pro",             # legacy mejor calidad, 2M ctx
}

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


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
        pdfs_raw: Optional[list[tuple[str, bytes]]] = None,
        imagenes_raw: Optional[list[tuple[str, bytes]]] = None,
    ) -> tuple[str, str]:
        """Genera completion con Gemini. Retorna (texto, modelo_usado).

        Si Gemini falla, levanta excepcion para que el caller pruebe
        otro proveedor (es responsabilidad del fallback chain).

        Args:
            pdfs_raw: lista opcional de (filename, bytes) para enviar
                como inputs binarios via inlineData. Gemini procesa
                PDFs nativamente igual que Claude. Limites: 50MB por
                request total, max ~1000 paginas.
            imagenes_raw: lista opcional de (filename, bytes) en formato
                PNG/JPEG. Si pdfs_raw no funciona o se prefiere
                vision sobre OCR-like, convertir el PDF a imagenes
                primero (ver pdf_to_images.py) y pasarlas aqui.
        """
        import base64
        if not self.disponible:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        modelo = modelo or self.default_model
        url = f"{self.BASE_URL}/models/{modelo}:generateContent?key={self.api_key}"

        # Construir parts: PDFs + imagenes + texto del user
        parts: list[dict] = []
        if pdfs_raw:
            for nombre, data in pdfs_raw[:5]:
                if not data or len(data) < 1024:
                    continue
                if len(data) > 30 * 1024 * 1024:
                    logger.warning(f"[GEMINI] PDF {nombre} >30MB, saltado")
                    continue
                parts.append({
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": base64.standard_b64encode(data).decode("ascii"),
                    },
                })
        if imagenes_raw:
            # Cap a 30 imagenes total (ya hay buen razonamiento con eso)
            for nombre, data in imagenes_raw[:30]:
                if not data or len(data) < 200:
                    continue
                if len(data) > 7 * 1024 * 1024:  # 7MB por imagen
                    continue
                # Detectar mime type por extension; default png
                ext = (nombre.rsplit(".", 1)[-1] or "").lower()
                mime = {
                    "png": "image/png", "jpg": "image/jpeg",
                    "jpeg": "image/jpeg", "webp": "image/webp",
                    "heic": "image/heic", "heif": "image/heif",
                }.get(ext, "image/png")
                parts.append({
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64.standard_b64encode(data).decode("ascii"),
                    },
                })
        parts.append({"text": user})

        body = {
            "contents": [{"role": "user", "parts": parts}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
                # Desactivar "extended thinking" en modelos 2.5 (Flash/Pro)
                # que por default queman 500-2000 tokens pensando antes
                # de responder, dejando poco budget para la salida real.
                # Para argumentacion juridica directa NO necesitamos
                # razonamiento extendido — queremos respuesta completa.
                # thinkingBudget=0 desactiva el modo. Modelos 2.0/lite
                # ignoran este campo (no afecta).
                "thinkingConfig": {"thinkingBudget": 0},
            },
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
        try:
            cand = data.get("candidates", [{}])[0]
            parts_resp = cand.get("content", {}).get("parts", [])
            texto = "".join(p.get("text", "") for p in parts_resp).strip()
        except (IndexError, KeyError) as e:
            raise RuntimeError(f"Gemini respuesta sin texto: {e}")
        if not texto:
            block = cand.get("finishReason", "")
            raise RuntimeError(f"Gemini sin texto (finish={block})")
        usage = data.get("usageMetadata", {}) or {}
        n_pdfs = len(pdfs_raw or [])
        n_imgs = len(imagenes_raw or [])
        logger.info(
            f"[GEMINI] OK modelo={modelo} pdfs={n_pdfs} imgs={n_imgs} "
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
        pdfs_raw: Optional[list[tuple[str, bytes]]] = None,
        imagenes_raw: Optional[list[tuple[str, bytes]]] = None,
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
                    pdfs_raw=pdfs_raw,
                    imagenes_raw=imagenes_raw,
                )
            except Exception as e:
                ultimo_error = e
                msg = str(e).lower()
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
