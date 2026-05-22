"""Quality Gate Orchestrator — orquesta el pipeline completo.

Filosofía: "ningún dictamen defectuoso llega al usuario silenciosamente".

Pipeline:
  1. PRE-VALIDADOR (deterministic, sin IA)
     ↓ si falla → return mensaje claro al usuario, NO se llama IA
  2. GENERACIÓN con IA (modelo primario)
  3. POST-VALIDADOR (deterministic)
     ↓ si aprobado → return dictamen
     ↓ si debe_regenerar → REGENERAR con OTRO modelo
  4. Max 3 intentos (modelo 1 → 2 → 3)
  5. Si tras 3 intentos sigue fallando → escalar a humano con razón

API principal:
    await ejecutar_quality_gate(
        eps, codigo, valor, texto,
        callable_generar_ia,  # función async que genera dictamen
        es_ratificacion=False,
    ) → QualityGateResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from app.services.quality_gate.post_validator import (
    PostValidationResult,
    post_validar_dictamen,
)
from app.services.quality_gate.pre_validator import (
    PreValidationResult,
    pre_validar_glosa,
)

logger = logging.getLogger("motor_glosas.quality_gate")

# Tipo de la función generadora: recibe contexto, devuelve (texto_dictamen, modelo_usado)
GeneradorIA = Callable[..., Awaitable[tuple[str, str]]]


@dataclass
class IntentoGeneracion:
    """Registro de un intento individual de generación."""

    numero: int  # 1, 2, 3
    modelo_solicitado: str  # "groq", "anthropic", "gemini"
    modelo_usado: str  # el que respondió (puede ser distinto si hubo fallback interno)
    texto: str = ""
    post_validation: Optional[PostValidationResult] = None
    error: str = ""

    @property
    def aprobado(self) -> bool:
        return self.post_validation is not None and self.post_validation.aprobado


@dataclass
class QualityGateResult:
    """Resultado completo del pipeline Quality Gate."""

    estado: str  # "APROBADO" | "RECHAZADO_PRE" | "RECHAZADO_POST" | "ESCALAR_HUMANO"
    dictamen_final: str = ""
    modelo_final: str = ""
    score_final: int = 0
    pre_validation: Optional[PreValidationResult] = None
    intentos: list[IntentoGeneracion] = field(default_factory=list)
    mensaje_usuario: str = ""

    @property
    def aprobado(self) -> bool:
        return self.estado == "APROBADO"

    @property
    def n_regeneraciones(self) -> int:
        return max(0, len(self.intentos) - 1)


# Orden de modelos para regeneración. Si el primer modelo falla post-validation,
# se prueba con el siguiente. Configurable via env en producción.
MODELOS_FALLBACK_ORDEN = ["groq", "anthropic", "gemini"]
MAX_INTENTOS = 3


async def ejecutar_quality_gate(
    *,
    eps: str,
    codigo_glosa: str,
    valor_objetado: str | int | float | None,
    texto_glosa: str,
    generador: GeneradorIA,
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
    max_intentos: int = MAX_INTENTOS,
    modelos_fallback: Optional[list[str]] = None,
) -> QualityGateResult:
    """Ejecuta el pipeline completo de Quality Gate.

    Args:
        eps: nombre de la EPS
        codigo_glosa: código formato AA####
        valor_objetado: valor monetario (flexible)
        texto_glosa: texto completo de la glosa
        generador: función async que genera el dictamen.
            Firma: `async def gen(modelo: str, contexto: dict) → (texto, modelo_real)`
        es_ratificacion: si True, post-val acepta coda procesal
        es_extemporanea: si True, post-val acepta coda procesal
        max_intentos: máximo de regeneraciones (default 3)
        modelos_fallback: orden de modelos a probar (default groq → anthropic → gemini)

    Returns:
        QualityGateResult con .estado y .dictamen_final si aprobado.
    """
    modelos = modelos_fallback or MODELOS_FALLBACK_ORDEN
    resultado = QualityGateResult(estado="PENDIENTE")

    # ─── PASO 1: PRE-VALIDADOR ────────────────────────────────────────
    pre = pre_validar_glosa(
        eps=eps,
        codigo_glosa=codigo_glosa,
        valor_objetado=valor_objetado,
        texto_glosa=texto_glosa,
    )
    resultado.pre_validation = pre

    if not pre.aprobado:
        resultado.estado = "RECHAZADO_PRE"
        resultado.mensaje_usuario = pre.mensaje_para_usuario
        logger.warning(
            f"[QG] Pre-validación rechazada: {pre.razones_bloqueo}. No se gasta call de IA."
        )
        return resultado

    logger.info(
        f"[QG] Pre-OK: eps={pre.eps_normalizada} codigo={pre.codigo_normalizado} "
        f"familia={pre.familia_codigo} valor={pre.valor_parseado}"
    )

    # ─── PASO 2+3: GENERAR + POST-VALIDAR (con regeneración) ──────────
    contexto = {
        "eps": pre.eps_normalizada,
        "codigo_glosa": pre.codigo_normalizado,
        "familia": pre.familia_codigo,
        "valor": pre.valor_parseado,
        "texto_glosa": texto_glosa,
        "es_ratificacion": es_ratificacion,
        "es_extemporanea": es_extemporanea,
    }

    for n in range(1, max_intentos + 1):
        modelo_solicitado = modelos[(n - 1) % len(modelos)]
        intento = IntentoGeneracion(
            numero=n,
            modelo_solicitado=modelo_solicitado,
            modelo_usado="",
        )

        # Llamar al generador
        try:
            texto, modelo_real = await generador(modelo=modelo_solicitado, **contexto)
            intento.texto = texto or ""
            intento.modelo_usado = modelo_real or modelo_solicitado
        except Exception as e:
            intento.error = f"{type(e).__name__}: {e}"
            logger.warning(f"[QG] Intento {n} con {modelo_solicitado} falló: {intento.error}")
            resultado.intentos.append(intento)
            continue

        # Post-validar
        post = post_validar_dictamen(
            intento.texto,
            eps=pre.eps_normalizada,
            es_ratificacion=es_ratificacion,
            es_extemporanea=es_extemporanea,
        )
        intento.post_validation = post
        resultado.intentos.append(intento)

        if post.aprobado and not post.debe_regenerar:
            # ¡APROBADO!
            resultado.estado = "APROBADO"
            resultado.dictamen_final = intento.texto
            resultado.modelo_final = intento.modelo_usado
            resultado.score_final = post.score
            logger.info(
                f"[QG] Aprobado en intento {n} con {intento.modelo_usado}. Score: {post.score}"
            )
            return resultado

        logger.warning(
            f"[QG] Intento {n} con {intento.modelo_usado} no aprobó "
            f"(score={post.score}, aprobado={post.aprobado}). "
            f"Razones: {post.razones_rechazo[:2]}"
        )

    # ─── Si llegamos aquí, todos los intentos fallaron ─────────────────
    # Tomamos el mejor intento (mayor score) como dictamen final + escalamos
    mejores = sorted(
        [i for i in resultado.intentos if i.post_validation],
        key=lambda i: i.post_validation.score,  # type: ignore[union-attr]
        reverse=True,
    )
    if mejores:
        mejor = mejores[0]
        resultado.dictamen_final = mejor.texto
        resultado.modelo_final = mejor.modelo_usado
        resultado.score_final = mejor.post_validation.score if mejor.post_validation else 0
        razones = mejor.post_validation.razones_rechazo if mejor.post_validation else []
        resultado.mensaje_usuario = (
            f"Tras {len(resultado.intentos)} intentos con distintos modelos, "
            f"no se logró aprobar todos los checks (mejor score: {resultado.score_final}/100). "
            f"Problemas detectados:\n"
            + "\n".join(f"  • {r}" for r in razones[:3])
            + "\n\nEl dictamen se entrega como borrador para revisión manual."
        )

    resultado.estado = "ESCALAR_HUMANO"
    logger.error(
        f"[QG] Escalando a humano tras {len(resultado.intentos)} intentos. "
        f"Mejor score: {resultado.score_final}"
    )
    return resultado
