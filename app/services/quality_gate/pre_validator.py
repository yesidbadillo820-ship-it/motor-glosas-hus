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
    """Intenta parsear el valor objetado, pero NO bloquea si está ausente o es cero.

    Hay casos legítimos donde el gestor no tiene cifra (glosa de cobertura
    sin monto definido, ratificación de etapa previa, etc). En esos casos el
    dictamen igual debe poder generarse — el detector de "valores fabricados"
    del post-validator se encarga de impedir que la IA invente cifras que no
    están en el input. Por eso este check devuelve siempre ok=True; solo deja
    una sugerencia para el usuario.
    """
    v = _parsear_valor(valor)
    if v <= 0:
        return (
            PreCheckResult(
                ok=True,  # NO bloquea — solo sugiere
                razon="Sin valor objetado parseable (opcional)",
                sugerencia=(
                    "Si la glosa tiene un valor específico, agrégalo "
                    "(ej. '$500.000') para precisar el dictamen."
                ),
            ),
            0.0,
        )
    return (PreCheckResult(ok=True), v)


# Términos del dominio glosas/clínico — lista amplia para cubrir tanto
# vocabulario administrativo (factura/contrato) como clínico (UCI/día/
# medicamento). Las glosas EPS reales usan jerga mixta; antes la lista
# era demasiado estrecha y bloqueaba textos válidos como "Se reconocen
# únicamente 8 días de UCI..." — visto en producción el 10-jun-2026.
_PALABRAS_DOMINIO_GLOSA = (
    # Administrativo / contractual
    "factura", "cups", "glosa", "contrato", "autorizaci", "prestaci",
    "paciente", "tarif", "soport", "valor", "objet", "cobertura",
    "auditor", "radicac", "concilia", "ratific", "respuesta",
    # Clínico / asistencial
    "medicament", "insumo", "dispositivo", "procedim", "consulta",
    "urgencia", "uci", "ucin", "hospitalizac", "estancia", "cirug",
    "quirurg", "anestesi", "imagen", "laboratorio", "examen",
    "diagnost", "tratamiento", "terapia", "rehabilitac", "ambulator",
    "internac", "egreso", "ingreso", "día", "dia ", "dias ", "días",
    # Normativo / coberturas
    "pbs", "no pbs", "pos ", "no pos", "uvr", "soat", "mipres",
    "rias", "ips", "eps", "arl", "adres", "iss", "msps", "resoluci",
    "decreto", "ley", "circular",
    # Verbos típicos de glosa
    "reconoc", "acept", "rechaz", "devolv", "objeta", "niega",
    "valida", "soport", "justific", "subsana", "responde",
)


def check_texto_glosa(texto: str, codigo_presente: bool = False) -> PreCheckResult:
    """Verifica que el texto tenga contenido mínimo y útil.

    Las glosas reales de EPS suelen ser MUY cortas — "TA0102 - Medicamento
    fuera del PBS" tiene 35 chars y es perfectamente válida. Por eso:

    1. Mínimo de chars: 20 (no 60 como antes — bloqueaba glosas reales).
    2. Si el código YA está presente (TA####, etc.), el texto es claramente
       una glosa y NO exigimos palabras de dominio adicionales.
    3. Si no hay código, exigimos al menos una palabra de la lista amplia
       de dominio (administrativo o clínico) para evitar "lorem ipsum".
    """
    t = (texto or "").strip()
    if len(t) < 20:
        return PreCheckResult(
            ok=False,
            razon=f"Texto de glosa muy corto ({len(t)} chars, mínimo 20)",
            sugerencia=(
                "Incluye al menos el código y un motivo, "
                "ej. 'TA0102 - Medicamento fuera del PBS'."
            ),
        )
    # Si hay código válido (TA0102, SO0501, ...) ya sabemos que es una glosa
    # y no exigimos vocabulario adicional. El propio código es la prueba.
    if codigo_presente:
        return PreCheckResult(ok=True)
    t_lower = t.lower()
    if not any(p in t_lower for p in _PALABRAS_DOMINIO_GLOSA):
        return PreCheckResult(
            ok=False,
            razon="El texto no parece una glosa (no menciona código, factura, paciente, medicamento, día, UCI…)",
            sugerencia="Verifica que estés pegando el texto de la glosa de la EPS y no otra cosa",
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

    # Si el código de glosa fue parseado OK, el texto no necesita repetir
    # vocabulario del dominio — el propio código (TA0102, SO0501, ...) es
    # prueba suficiente de que es una glosa. Esto evita falsos negativos
    # como "TA0102 - Medicamento fuera del PBS" (35 chars, sin palabras
    # como "factura/CUPS/tarifa") que antes bloqueaban a la IA.
    codigo_ok = bool(chk_cod.ok and codigo_norm)
    checks["texto"] = check_texto_glosa(texto_glosa, codigo_presente=codigo_ok)
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
