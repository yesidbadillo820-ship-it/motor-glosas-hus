"""Adapter Quality Gate ↔ GlosaService.

Conecta el `_llamar_ia` del GlosaService con el orchestrator del Quality
Gate, permitiendo activarlo via feature flag QUALITY_GATE_ENABLED.

Filosofía:
  - El flujo legacy sigue funcionando sin cambios cuando el flag está OFF
  - Cuando QUALITY_GATE_ENABLED=1, el dictamen pasa por:
      pre-val → IA (con modelo del router) → post-val → regenerar si falla
  - Adopt incremental: probar con 10% del tráfico, luego 50%, luego 100%

Uso desde glosa_service.py (ejemplo, NO requerido aún):

    from app.services.quality_gate_adapter import (
        es_quality_gate_activo,
        ejecutar_con_quality_gate,
    )

    if es_quality_gate_activo():
        resultado = await ejecutar_con_quality_gate(
            servicio=self,
            data=data,
            modo_resp=modo_resp,
            cod_res=cod_res,
            ...
        )
        if resultado.aprobado:
            arg_ia = resultado.dictamen_final
        else:
            # Escalar o usar borrador con warning
            arg_ia = resultado.dictamen_final or texto_fallback
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.ia_router import enrutar
from app.services.quality_gate import (
    QualityGateResult,
    ejecutar_quality_gate,
)
from app.utils.moneda import parse_valor_cop

logger = logging.getLogger("motor_glosas.quality_gate_adapter")


def es_quality_gate_activo() -> bool:
    """True si la variable de entorno QUALITY_GATE_ENABLED está seteada.

    Por defecto OFF para no afectar producción. Activar con:
      QUALITY_GATE_ENABLED=1

    También permite activación parcial por % (canary):
      QUALITY_GATE_ROLLOUT_PCT=10  → 10% del tráfico usa quality gate
    """
    flag = os.environ.get("QUALITY_GATE_ENABLED", "").lower().strip()
    return flag in ("1", "true", "yes", "on")


def porcentaje_rollout() -> int:
    """0-100. Si está seteado, se usa solo en ese % del tráfico.
    Útil para canary deploy."""
    try:
        return max(0, min(100, int(os.environ.get("QUALITY_GATE_ROLLOUT_PCT", "100"))))
    except ValueError:
        return 100


def debe_usar_quality_gate(*, glosa_id: int | None = None) -> bool:
    """Decide si la glosa actual debe procesarse con Quality Gate.

    Si el flag global está OFF → False siempre.
    Si está ON pero hay rollout < 100% → True solo para el % indicado
    (sticky por glosa_id si está disponible, sino random).
    """
    if not es_quality_gate_activo():
        return False
    pct = porcentaje_rollout()
    if pct >= 100:
        return True
    if pct <= 0:
        return False
    # Sticky por glosa_id para que la misma glosa siempre tome la misma decisión
    if glosa_id is not None:
        return (int(glosa_id) % 100) < pct
    # Random para casos sin id
    import random

    return random.randint(0, 99) < pct


async def ejecutar_con_quality_gate(
    *,
    servicio: Any,  # GlosaService instance
    eps: str,
    codigo_glosa: str,
    valor_objetado: str | int | float | None,
    texto_glosa: str,
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
    system_prompt: str = "",
    user_prompt: str = "",
    glosa_id: int | None = None,
    proveedores_disponibles: set[str] | None = None,
) -> QualityGateResult:
    """Ejecuta el pipeline Quality Gate usando el `_llamar_ia` del servicio.

    Args:
        servicio: instancia de GlosaService (para acceder a _llamar_ia)
        eps, codigo_glosa, valor_objetado, texto_glosa: inputs del caso
        es_ratificacion, es_extemporanea: para post-validación
        system_prompt: prompt del sistema (estructura/reglas)
        user_prompt: prompt del usuario (datos del caso)
        glosa_id: opcional, para sticky canary
        proveedores_disponibles: set de "groq"/"anthropic"/"gemini"

    Returns:
        QualityGateResult — ver app/services/quality_gate/orchestrator.py
    """
    # Decidir orden de modelos según router. parse_valor_cop en vez de
    # float(): los valores llegan como "$ 7.700,00" desde _extraer_valor y
    # float() crudo lanzaba ValueError → el adapter completo caía al path
    # legacy (QG muerto para toda glosa con valor monetario en el texto).
    decision = enrutar(
        eps=eps,
        valor=parse_valor_cop(valor_objetado) if valor_objetado else None,
        texto_glosa=texto_glosa,
        es_ratificacion=es_ratificacion,
        es_extemporanea=es_extemporanea,
        proveedores_disponibles=proveedores_disponibles,
    )
    modelos_orden = [decision.modelo_recomendado] + decision.modelos_fallback
    # Dedup preservando orden
    seen: set[str] = set()
    modelos_orden = [m for m in modelos_orden if not (m in seen or seen.add(m))]

    logger.info(
        f"[QG-Adapter] glosa_id={glosa_id} → router: {decision.complejidad} → "
        f"orden modelos: {modelos_orden} ({decision.razon})"
    )

    # Generador adapta _llamar_ia al contrato del orchestrator.
    #
    # Bug auditoría jun-2026 (P1 #2): la versión anterior ignoraba `modelo`
    # y llamaba _llamar_ia sin bypass_cache. Como la clave de caché es
    # (primary|modelo|eps|codigo|system|user) y los prompts no cambian entre
    # intentos, los intentos 2 y 3 devolvían la MISMA respuesta cacheada que
    # el post-validador acababa de rechazar → la regeneración era un no-op.
    n_llamadas = 0

    async def generador(modelo: str, **contexto: Any) -> tuple[str, str]:
        nonlocal n_llamadas
        n_llamadas += 1
        es_regeneracion = n_llamadas > 1

        # `modelo` es un PROVEEDOR del router ("groq"/"anthropic"/"gemini"/
        # "openrouter"). _llamar_ia solo permite forzar proveedor vía
        # modelo_override (que siempre enruta a Anthropic con ese model id);
        # para el resto respeta primary_ai + su cadena de fallback.
        modelo_override = None
        if modelo == "anthropic" and getattr(servicio, "anthropic_key", None):
            modelo_override = getattr(servicio, "anthropic_model", None)

        texto_resp, modelo_real = await servicio._llamar_ia(
            system=system_prompt,
            user=user_prompt,
            eps=eps,
            codigo=codigo_glosa,
            modelo_override=modelo_override,
            # Intento 1 puede servirse de caché (ahorro). Intentos 2+ existen
            # porque el post-validador rechazó el anterior: servir caché ahí
            # repetiría la respuesta defectuosa.
            bypass_cache=es_regeneracion,
        )
        # Extraer argumento del XML si aplica
        try:
            arg = servicio._xml("argumento", texto_resp, "") or texto_resp
        except Exception:
            arg = texto_resp
        return (arg, modelo_real or modelo)

    return await ejecutar_quality_gate(
        eps=eps,
        codigo_glosa=codigo_glosa,
        valor_objetado=valor_objetado,
        texto_glosa=texto_glosa,
        generador=generador,
        es_ratificacion=es_ratificacion,
        es_extemporanea=es_extemporanea,
        max_intentos=3,
        modelos_fallback=modelos_orden,
    )


def registrar_estadistica_qg(resultado: QualityGateResult) -> None:
    """Loguea estadísticas del Quality Gate para análisis posterior.

    Compatible con el sistema PostHog si está configurado.
    """
    try:
        from app.services.posthog_service import track_event

        track_event(
            "quality_gate_executed",
            properties={
                "estado": resultado.estado,
                "score_final": resultado.score_final,
                "n_intentos": len(resultado.intentos),
                "n_regeneraciones": resultado.n_regeneraciones,
                "modelo_final": resultado.modelo_final,
            },
        )
    except Exception:
        pass  # PostHog opcional

    logger.info(
        f"[QG] {resultado.estado} | score={resultado.score_final} | "
        f"intentos={len(resultado.intentos)} | modelo_final={resultado.modelo_final}"
    )
