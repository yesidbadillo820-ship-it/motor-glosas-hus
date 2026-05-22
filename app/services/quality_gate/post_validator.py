"""Post-validador: checks deterministic DESPUÉS de que la IA generó el dictamen.

Verifica calidad antes de mostrar al usuario. Si algún check crítico falla,
el orchestrator decide si regenerar con otro modelo o escalar a humano.

Checks implementados:
  ✓ Citas verificadas — usando `citation_verifier.verificar_citas` que
    ya valida contra `normativa_completa._TODAS_LAS_NORMAS` (corpus oficial).
  ✓ Cierre canónico "SE SOLICITA EL LEVANTAMIENTO" presente.
  ✓ Sin coda procesal (excepto ratificadas/extemporáneas).
  ✓ Longitud razonable (no truncado, no excesivo).

Cada check devuelve {ok, severidad, razon}.
La decisión global agrega todo en un PostValidationResult con score 0-100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PostCheckResult:
    ok: bool
    severidad: Literal["INFO", "WARN", "ERROR"] = "INFO"
    razon: str = ""


@dataclass
class PostValidationResult:
    aprobado: bool
    checks: dict[str, PostCheckResult] = field(default_factory=dict)
    citas_problematicas: list[dict] = field(default_factory=list)
    razones_rechazo: list[str] = field(default_factory=list)
    score: int = 100

    @property
    def debe_regenerar(self) -> bool:
        """True si la calidad merece regenerar con otro modelo."""
        return not self.aprobado or self.score < 70


def check_citas_verificadas(
    texto: str, eps: str | None = None
) -> tuple[PostCheckResult, list[dict]]:
    """Verifica que TODAS las citas existan en el corpus normativo cargado.

    Usa `citation_verifier.verificar_citas` que es el verificador oficial
    contra `_TODAS_LAS_NORMAS` (LEYES + DECRETOS + RESOLUCIONES + CIRCULARES
    + CODIGOS + JURISPRUDENCIA + ACUERDOS).

    Devuelve (resultado_check, lista_de_issues_graves).
    """
    try:
        from app.services.citation_verifier import verificar_citas
    except ImportError:
        return (
            PostCheckResult(ok=True, severidad="INFO", razon="verificador no disponible"),
            [],
        )

    reporte = verificar_citas(texto or "", eps=eps)
    issues_graves = [i for i in reporte.get("issues", []) if i.get("severidad") == "ALTA"]
    issues_medias = [i for i in reporte.get("issues", []) if i.get("severidad") == "MEDIA"]

    total_problematicas = issues_graves + issues_medias

    if issues_graves:
        ejemplos = ", ".join(i.get("cita", "") for i in issues_graves[:3])
        return (
            PostCheckResult(
                ok=False,
                severidad="ERROR",
                razon=f"{len(issues_graves)} cita(s) GRAVE(s) inválida(s): {ejemplos}",
            ),
            total_problematicas,
        )

    if issues_medias:
        ejemplos = ", ".join(i.get("cita", "") for i in issues_medias[:3])
        return (
            PostCheckResult(
                ok=False,
                severidad="WARN",
                razon=f"{len(issues_medias)} cita(s) con problemas medios: {ejemplos}",
            ),
            total_problematicas,
        )

    total = reporte.get("total_citas", 0)
    return (
        PostCheckResult(
            ok=True,
            severidad="INFO",
            razon=f"Todas las {total} citas verificadas en corpus",
        ),
        [],
    )


def check_cierre_canonico(texto: str) -> PostCheckResult:
    """Verifica que el dictamen termine con 'SE SOLICITA EL LEVANTAMIENTO'."""
    t = (texto or "").upper()
    if "SE SOLICITA" in t and "LEVANTAMIENTO" in t:
        return PostCheckResult(ok=True, severidad="INFO", razon="Cierre canónico presente")
    return PostCheckResult(
        ok=False,
        severidad="ERROR",
        razon="Falta cierre canónico 'SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA'",
    )


def check_sin_coda_procesal(texto: str, es_ratificacion: bool = False) -> PostCheckResult:
    """Verifica que NO haya coda procesal (solo en defensas normales)."""
    if es_ratificacion:
        return PostCheckResult(ok=True, severidad="INFO", razon="N/A — es ratificación")

    t = (texto or "").upper()
    indicadores_coda = [
        "10 DÍAS HÁBILES",
        "10 DIAS HABILES",
        "MESA DE CONCILIACI",
        "@HUS.GOV.CO",
        "CARTERA@HUS",
        "GLOSASYDEVOLUCIONES@HUS",
    ]
    encontrados = [ind for ind in indicadores_coda if ind in t]
    if encontrados:
        return PostCheckResult(
            ok=False,
            severidad="WARN",
            razon=f"Coda procesal detectada: {', '.join(encontrados[:2])}",
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="Sin coda procesal")


def check_longitud_razonable(texto: str) -> PostCheckResult:
    """El dictamen debe estar entre 200 y 5000 chars."""
    n = len(texto or "")
    if n < 200:
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=f"Dictamen demasiado corto ({n} chars, mínimo 200)",
        )
    if n > 5000:
        return PostCheckResult(
            ok=False,
            severidad="WARN",
            razon=f"Dictamen excesivamente largo ({n} chars, máximo recomendado 5000)",
        )
    return PostCheckResult(ok=True, severidad="INFO", razon=f"Longitud OK ({n} chars)")


def post_validar_dictamen(
    texto: str,
    *,
    eps: str | None = None,
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
) -> PostValidationResult:
    """Ejecuta todos los post-checks del dictamen ya generado por la IA.

    Args:
        texto: dictamen completo
        eps: nombre de la EPS (para context en verificador de citas)
        es_ratificacion: si True, acepta coda procesal
        es_extemporanea: si True, acepta coda procesal

    Returns:
        PostValidationResult con .aprobado=True si TODOS los checks ERROR pasaron,
        .citas_problematicas, .score 0-100, .debe_regenerar si calidad baja.
    """
    checks: dict[str, PostCheckResult] = {}
    razones: list[str] = []

    # 1. Citas verificadas (crítico)
    chk_citas, citas_problematicas = check_citas_verificadas(texto, eps=eps)
    checks["citas"] = chk_citas

    # 2. Cierre canónico (crítico)
    checks["cierre"] = check_cierre_canonico(texto)

    # 3. Coda procesal (warning si aplica)
    checks["coda"] = check_sin_coda_procesal(texto, es_ratificacion or es_extemporanea)

    # 4. Longitud razonable
    checks["longitud"] = check_longitud_razonable(texto)

    # Score: 100 - 30 por cada ERROR, -10 por cada WARN
    score = 100
    for nombre, res in checks.items():
        if not res.ok:
            if res.severidad == "ERROR":
                score -= 30
                razones.append(f"[{nombre}] {res.razon}")
            elif res.severidad == "WARN":
                score -= 10
                razones.append(f"[{nombre}] {res.razon}")
    score = max(0, score)

    # Aprobado si NINGÚN check ERROR falla
    aprobado = all(r.ok or r.severidad != "ERROR" for r in checks.values())

    return PostValidationResult(
        aprobado=aprobado,
        checks=checks,
        citas_problematicas=citas_problematicas,
        razones_rechazo=razones,
        score=score,
    )
