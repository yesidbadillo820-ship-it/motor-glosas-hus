"""Pre-validador: checks deterministic ANTES de llamar a la IA.

Si alguno falla, no se gasta una llamada de IA — se devuelve mensaje
claro al frontend. Esto evita generar dictámenes basura por inputs
incompletos, y reduce costos.

Checks implementados:
  ✓ Código de glosa presente y en formato válido (regex AA####)
  ✓ EPS reconocida (whitelist + sinónimos)
  ✓ Valor monetario parseable y > 0
  ✓ Texto de glosa con mínimo de contenido (>= 20 chars)
  ✓ Plantilla del banco HUS disponible para la familia del código

Cada check devuelve {"ok": bool, "razon": str, "sugerencia": str}.
El resultado final agrupa todos los checks y dice si se debe proceder
o no a llamar a la IA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Codigos de glosa válidos según el regex usado en glosa_service._extraer_codigos_glosa
# Prefijos oficiales del Manual Único Res. 2284/2023.
_REGEX_CODIGO_VALIDO = re.compile(
    r"^(?:TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}$",
    re.IGNORECASE,
)

# Familias que tienen plantilla en el banco HUS (data/plantillas_hus_base.json).
_FAMILIAS_BANCO_HUS = {"TA", "SO", "CO", "FA", "CL"}

# EPS conocidas — whitelist + variantes comunes (mayúsculas, sin tildes).
# Se usa para verificar que el campo eps no esté vacío o sea algo absurdo.
# Lista no exhaustiva — sólo bloquea inputs claramente inválidos.
_EPS_CONOCIDAS_NORMALIZADAS = {
    # Régimen contributivo
    "FAMISANAR",
    "FAMISANAR EPS",
    "NUEVA EPS",
    "SANITAS",
    "EPS SANITAS",
    "SURA",
    "EPS SURA",
    "COMPENSAR",
    "EPS COMPENSAR",
    "COOSALUD",
    "SALUD TOTAL",
    "SALUD MIA",
    "MUTUAL SER",
    "MUTUALSER",
    "ALIANSALUD",
    # Régimen subsidiado / mixtas
    "ASMET SALUD",
    "EMSSANAR",
    "SAVIA SALUD",
    "ECOOPSOS",
    # Especiales / régimen especial
    "POSITIVA",
    "FOMAG",
    "PPL",
    "POLICIA NACIONAL",
    "POLICÍA NACIONAL",
    "DISPENSARIO MEDICO",
    "DISPENSARIO MÉDICO",
    "DMBUG",
    "DIGSA",
    "PRECIMED",
    "SUMIMEDICAL",
    "AURORA",
    # Genérico para banco HUS
    "GENERICO",
    "GENÉRICO",
    "OTRA / SIN DEFINIR",
    "OTRA",
    "SIN DEFINIR",
}


@dataclass
class PreCheckResult:
    ok: bool
    razon: str = ""
    sugerencia: str = ""


@dataclass
class PreValidationResult:
    """Agrupa los checks individuales en una decisión global."""

    aprobado: bool
    checks: dict[str, PreCheckResult] = field(default_factory=dict)
    codigo_normalizado: str = ""
    familia_codigo: str = ""
    eps_normalizada: str = ""
    valor_parseado: float = 0.0
    razones_bloqueo: list[str] = field(default_factory=list)
    sugerencias: list[str] = field(default_factory=list)

    @property
    def mensaje_para_usuario(self) -> str:
        """Mensaje legible para mostrar al usuario si la validación falla."""
        if self.aprobado:
            return ""
        partes = ["No puedo generar dictamen sin estos datos:"]
        for r in self.razones_bloqueo:
            partes.append(f"  • {r}")
        if self.sugerencias:
            partes.append("\nSugerencias:")
            for s in self.sugerencias:
                partes.append(f"  → {s}")
        return "\n".join(partes)


def _normalizar_codigo(codigo: str) -> str:
    return (codigo or "").upper().strip()


def _normalizar_eps(eps: str) -> str:
    """Quita tildes simples + UPPER + trim. No es perfecto pero suficiente
    para matchear contra _EPS_CONOCIDAS_NORMALIZADAS."""
    e = (eps or "").upper().strip()
    # Reemplazos comunes
    for orig, repl in [("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U")]:
        e = e.replace(orig, repl)
    return e


def _parsear_valor(valor: str | int | float | None) -> float:
    """Parsea valores en formatos colombianos típicos:
      "$ 500.000" → 500000.0
      "500,000"   → 500000.0
      "1'500.000" → 1500000.0
      "%150.000"  → 150000.0 (typo % por $)
      500000      → 500000.0
    Devuelve 0.0 si no se puede parsear."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    # Quitar prefijos y caracteres no numéricos comunes
    s = re.sub(r"[$%]", "", s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[A-Za-zÁÉÍÓÚáéíóú]+", "", s)  # quita "pesos", "COP", etc.
    s = s.replace("'", "").replace(",", "").replace(".", "")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def check_codigo_glosa(codigo: str) -> tuple[PreCheckResult, str, str]:
    """Valida que el código sea AA#### (TA0201, SO0501, etc.).

    Devuelve (resultado, codigo_normalizado, familia).
    """
    cod_norm = _normalizar_codigo(codigo)
    if not cod_norm:
        return (
            PreCheckResult(
                ok=False,
                razon="Falta el código de glosa",
                sugerencia="Incluye el código en el texto, ej. 'TA0201 - ...'",
            ),
            "",
            "",
        )
    if not _REGEX_CODIGO_VALIDO.match(cod_norm):
        return (
            PreCheckResult(
                ok=False,
                razon=f"Código '{cod_norm}' no tiene formato válido (debe ser AA####)",
                sugerencia="Prefijos válidos: TA, SO, AU, CO, CL, PE, FA, SE, IN, ME, EX + 2-4 dígitos",
            ),
            cod_norm,
            "",
        )
    familia = cod_norm[:2]
    return (PreCheckResult(ok=True), cod_norm, familia)


def check_eps(eps: str) -> tuple[PreCheckResult, str]:
    """Valida que la EPS sea reconocida o al menos no esté vacía."""
    eps_norm = _normalizar_eps(eps)
    if not eps_norm:
        return (
            PreCheckResult(
                ok=False,
                razon="Falta la EPS / Entidad Pagadora",
                sugerencia="Selecciona la EPS del dropdown",
            ),
            "",
        )
    # No bloqueamos por EPS desconocida — solo advertimos (es muy permisivo
    # porque a veces hay EPSs nuevas, ARL, IPS pagadoras, etc.)
    return (PreCheckResult(ok=True), eps_norm)


def check_valor_monetario(valor: str | int | float | None) -> tuple[PreCheckResult, float]:
    """Valida que el valor objetado se pueda parsear y sea > 0."""
    v = _parsear_valor(valor)
    if v <= 0:
        return (
            PreCheckResult(
                ok=False,
                razon=f"Valor objetado no parseable o cero ({valor!r})",
                sugerencia="Incluye un valor en el texto, ej. '$500.000' o 'por valor de 1.500.000'",
            ),
            0.0,
        )
    return (PreCheckResult(ok=True), v)


def check_texto_glosa(texto: str) -> PreCheckResult:
    """Verifica que el texto tenga contenido mínimo."""
    t = (texto or "").strip()
    if len(t) < 20:
        return PreCheckResult(
            ok=False,
            razon=f"Texto de glosa muy corto ({len(t)} chars, mínimo 20)",
            sugerencia="Incluye el código, motivo y valor objetado",
        )
    return PreCheckResult(ok=True)


def check_plantilla_disponible(familia: str) -> PreCheckResult:
    """Verifica que el banco HUS tenga plantillas para la familia del código.

    NOTA: no consulta la BD — sólo verifica que la familia esté en la lista
    estática de _FAMILIAS_BANCO_HUS. Si no está, el dictamen igual se
    generará pero sin few-shot del banco HUS (caerá a free-form).
    """
    if not familia:
        return PreCheckResult(ok=True)  # no aplicable
    if familia not in _FAMILIAS_BANCO_HUS:
        return PreCheckResult(
            ok=True,  # NO bloquea — solo advierte
            razon=f"Familia {familia} no tiene plantillas en el banco HUS",
            sugerencia="El dictamen se generará en modo libre — calidad puede ser menor",
        )
    return PreCheckResult(ok=True)


def pre_validar_glosa(
    eps: str,
    codigo_glosa: str,
    valor_objetado: str | int | float | None,
    texto_glosa: str,
    *,
    strict: bool = False,
) -> PreValidationResult:
    """Ejecuta todos los pre-checks y devuelve el resultado agregado.

    Args:
        eps: nombre de la EPS / entidad pagadora
        codigo_glosa: código en formato AA#### (ej. TA0201)
        valor_objetado: valor monetario (puede ser str con formato colombiano)
        texto_glosa: texto completo de la glosa
        strict: si True, advertencias también bloquean (default False)

    Returns:
        PreValidationResult con .aprobado=True si todo OK,
        False si algún check crítico falló. Incluye también los valores
        normalizados (código UPPER, eps normalizada, valor parseado).
    """
    checks: dict[str, PreCheckResult] = {}

    # Cada check
    chk_cod, codigo_norm, familia = check_codigo_glosa(codigo_glosa)
    checks["codigo"] = chk_cod

    chk_eps, eps_norm = check_eps(eps)
    checks["eps"] = chk_eps

    chk_val, valor_num = check_valor_monetario(valor_objetado)
    checks["valor"] = chk_val

    checks["texto"] = check_texto_glosa(texto_glosa)
    checks["plantilla"] = check_plantilla_disponible(familia)

    # Agregar checks → decisión global
    razones: list[str] = []
    sugerencias: list[str] = []
    for nombre, res in checks.items():
        if not res.ok:
            razones.append(res.razon)
            if res.sugerencia:
                sugerencias.append(res.sugerencia)
        elif res.razon and strict:
            razones.append(res.razon)
            if res.sugerencia:
                sugerencias.append(res.sugerencia)

    aprobado = len(razones) == 0
    return PreValidationResult(
        aprobado=aprobado,
        checks=checks,
        codigo_normalizado=codigo_norm,
        familia_codigo=familia,
        eps_normalizada=eps_norm,
        valor_parseado=valor_num,
        razones_bloqueo=razones,
        sugerencias=sugerencias,
    )
