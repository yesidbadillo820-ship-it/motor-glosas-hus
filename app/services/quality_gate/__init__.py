"""Quality Gate — calidad determinística end-to-end del dictamen.

Filosofía (Plan de Transformación, mayo 2026):
  Hoy: la IA genera, mostramos lo que sale, postprocessors arreglan
       fallas a posteriori, y el gestor recibe dictámenes con bugs
       conocidos (citas inventadas, codas procesales, encabezados no
       verbatim, etc.).
  Mañana: la IA pasa por un Quality Gate que GARANTIZA calidad ANTES
       de mostrar. Si no pasa los checks, se regenera con otro modelo.
       Si tras N intentos no pasa, se marca para revisión humana con
       razón específica — pero nunca llega un dictamen defectuoso al
       usuario sin que él lo pida explícitamente.

Estructura del módulo:
  pre_validator.py   — checks BEFORE calling IA (input sanity)
  post_validator.py  — checks AFTER IA response (output quality)
  orchestrator.py    — Quality Gate central: pre → IA → post → decide
                       si aprobar / regenerar / escalar a humano

Mantra: "ningún dictamen defectuoso llega al usuario silenciosamente.
Si algo falla, lo decimos con claridad."
"""

from app.services.quality_gate.orchestrator import (
    IntentoGeneracion,
    QualityGateResult,
    ejecutar_quality_gate,
)
from app.services.quality_gate.post_validator import (
    PostValidationResult,
    post_validar_dictamen,
)
from app.services.quality_gate.pre_validator import (
    PreValidationResult,
    pre_validar_glosa,
)

__all__ = [
    "IntentoGeneracion",
    "PostValidationResult",
    "PreValidationResult",
    "QualityGateResult",
    "ejecutar_quality_gate",
    "post_validar_dictamen",
    "pre_validar_glosa",
]
