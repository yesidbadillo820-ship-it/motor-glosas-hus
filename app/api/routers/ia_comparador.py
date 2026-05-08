"""Comparador de IAs lado a lado.

Ejecuta la misma query en los 3 proveedores en paralelo y devuelve
los resultados para que el coordinador compare calidad/velocidad/
estilo. Util para:
- Decidir cual IA poner como primary
- Auditoria de calidad: la IA primary se desvio del estilo deseado?
- Diagnostico: cual IA esta fallando para esta query especifica
"""
from __future__ import annotations
import asyncio
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.database import get_db
from app.models.db import UsuarioRecord


router = APIRouter(prefix="/ia-comparador", tags=["ia-comparador"])


class ComparadorInput(BaseModel):
    system: str = Field(..., min_length=10, max_length=8000)
    user: str = Field(..., min_length=5, max_length=8000)
    proveedores: list[str] = Field(default_factory=lambda: ["anthropic", "gemini", "groq"])


@router.post("/comparar")
async def comparar(
    data: ComparadorInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Ejecuta la misma query en las IAs solicitadas en paralelo."""
    cfg = get_settings()
    proveedores = [p.lower() for p in data.proveedores if p.lower() in ("anthropic", "gemini", "groq")]
    if not proveedores:
        raise HTTPException(400, "Ningun proveedor valido")

    async def _exec_anthropic():
        if not cfg.anthropic_api_key:
            return {"ok": False, "error": "sin API key"}
        import httpx
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": cfg.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": cfg.anthropic_model,
                        "max_tokens": 2000,
                        "system": data.system,
                        "messages": [{"role": "user", "content": data.user}],
                    },
                )
            ms = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}", "latency_ms": ms}
            d = r.json()
            texto = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
            usage = d.get("usage", {})
            return {
                "ok": True, "respuesta": texto,
                "modelo": d.get("model", cfg.anthropic_model),
                "latency_ms": ms,
                "tokens_in": usage.get("input_tokens", 0),
                "tokens_out": usage.get("output_tokens", 0),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def _exec_gemini():
        if not cfg.gemini_api_key:
            return {"ok": False, "error": "sin API key"}
        from app.services.gemini_service import GeminiService
        gs = GeminiService(api_key=cfg.gemini_api_key, default_model=cfg.gemini_model)
        t0 = time.time()
        try:
            texto, modelo = await gs.completar(
                system=data.system, user=data.user,
                temperature=0.2, max_tokens=2000,
            )
            ms = int((time.time() - t0) * 1000)
            return {"ok": True, "respuesta": texto, "modelo": modelo, "latency_ms": ms}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def _exec_groq():
        if not cfg.groq_api_key:
            return {"ok": False, "error": "sin API key"}
        from groq import AsyncGroq
        g = AsyncGroq(api_key=cfg.groq_api_key, timeout=60.0)
        t0 = time.time()
        try:
            r = await g.chat.completions.create(
                model=cfg.groq_model,
                messages=[
                    {"role": "system", "content": data.system},
                    {"role": "user", "content": data.user},
                ],
                temperature=0.2, max_tokens=2000,
            )
            ms = int((time.time() - t0) * 1000)
            content = r.choices[0].message.content
            return {
                "ok": True, "respuesta": content,
                "modelo": f"groq/{cfg.groq_model}",
                "latency_ms": ms,
                "tokens_in": getattr(r.usage, "prompt_tokens", 0),
                "tokens_out": getattr(r.usage, "completion_tokens", 0),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    fns = {"anthropic": _exec_anthropic, "gemini": _exec_gemini, "groq": _exec_groq}
    tareas = [(p, fns[p]()) for p in proveedores]
    resultados_raw = await asyncio.gather(*[t[1] for t in tareas], return_exceptions=True)

    out = {}
    for (p, _), res in zip(tareas, resultados_raw):
        if isinstance(res, Exception):
            out[p] = {"ok": False, "error": str(res)[:200]}
        else:
            out[p] = res

    return {"proveedores_evaluados": proveedores, "resultados": out}
