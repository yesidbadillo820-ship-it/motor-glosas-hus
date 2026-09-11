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

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

# Referencia colgante: "el Art./Artículo/Ley/Decreto/Resolución" sin número
# después (la IA empieza a citar y pierde el hilo, dejando "EL ART. LA
# AFIRMACIÓN…" o "EL ART. EN ESTE SENTIDO"). Sólo cuenta como problema si
# tras el "Art." NO viene un dígito (con tolerancia de hasta 3 caracteres
# de puntuación/espacio).
_PAT_REFERENCIA_COLGANTE = re.compile(
    r"\b(?:el|la|del|de\s+la)\s+"
    r"(?:Art(?:[íi]culo)?\.?|Ley|Decreto|Resoluci[óo]n|Acuerdo|Circular)"
    r"[\.\,\;:\s]{1,3}(?![0-9])(?:[A-ZÁÉÍÓÚÑa-záéíóúñ]|$)",
    re.IGNORECASE,
)

# Cita literal truncada: «…texto…» con elipsis dentro indica que la IA
# copió una cláusula/norma cortada (el bug "VIGENCIA FISCAL 202…»").
_PAT_CITA_TRUNCADA = re.compile(r"«[^«»]{10,2000}(?:…|\.\.\.)\s*»")

# Detección de "valores fabricados" — el bug visible en producción:
# el LLM rellena con cifras inventadas cuando el input no las trae.
# Captura "$ 1.200.000", "$1.200.000", "$1'200.000", "1.200.000 pesos".
_PAT_VALOR_EN_DICTAMEN = re.compile(
    r"\$\s*([\d]{1,3}(?:[.,'][\d]{3})+(?:[.,][\d]{1,2})?)"
    r"|"
    r"(?<![/\d])(\d{1,3}(?:[.,'][\d]{3})+)\s*(?:pesos|COP|\$)",
    re.IGNORECASE,
)

# Detección de "contratos fabricados": números de contrato tipo
# "S-13-1-03-1-04958" o "440-DIGSA/DMBUG-2025" que la IA inventa.
# Solo aceptamos números de contrato si aparecen tal cual en el input.
_PAT_CONTRATO_EN_DICTAMEN = re.compile(
    r"\b(?:CONTRATO|Contrato|contrato)\s+(?:N[oº°\.]?\s*|No\.?\s*)?"
    r"([A-Z0-9][A-Z0-9./\-]{4,40}[A-Z0-9])",
)

# Placeholders crudos sin rellenar (12-jun-2026, ronda 2): dictamen real
# entregado con "INTERPUESTA POR [ENTIDAD] ... DEL [SERVICIO] FACTURADO POR
# [VALOR REAL] ... LA GLOSA [CODIGO]". El patrón exige MAYÚSCULAS sostenidas
# dentro de los corchetes para NO confundir con corchetes legítimos tipo
# "[sic]" ni con anotaciones del sistema que llevan puntuación interna.
_PAT_PLACEHOLDER_CRUDO = re.compile(r"\[[A-ZÁÉÍÓÚÑ_ ]{3,}\]")


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
    # 27-08-2026 — UNA NORMA QUE NO SE PUDO COMPROBAR NO SE APRUEBA SOLA.
    # Ese día se bajó de ALTA a MEDIA el aviso de «no está en el corpus»,
    # porque decirle al auditor que la Resolución 839 de 2017 «no existe»
    # —cuando existe y es pertinente— le quita credibilidad al sello. Pero el
    # mensaje es una cosa y la puerta es otra: el prompt le dice al modelo qué
    # normas usar, y todas están en el corpus. Citar una de fuera es salirse
    # del guion, y eso merece ojos humanos antes de radicar. Si se dejara pasar
    # como simple aviso, un dictamen con derecho que nadie pudo comprobar
    # saldría aprobado solo — que es exactamente lo que pasó en agosto.
    _sin_comprobar = {"NORMA_SIN_VERIFICAR"}
    issues_graves = [
        i
        for i in reporte.get("issues", [])
        if i.get("severidad") == "ALTA" or i.get("tipo") in _sin_comprobar
    ]
    issues_medias = [
        i
        for i in reporte.get("issues", [])
        if i.get("severidad") == "MEDIA" and i.get("tipo") not in _sin_comprobar
    ]

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


def check_referencias_colgantes(texto: str) -> PostCheckResult:
    """Detecta frases tipo "el Art. EN ESTE SENTIDO..." sin número de norma.

    Aparece cuando la IA empieza a citar ("el Art.") y pierde el hilo,
    dejando una referencia abierta que la EPS usa para ratificar por
    "argumento incompleto". Era el defecto visible en el último dictamen
    real reportado por el usuario.
    """
    if not texto:
        return PostCheckResult(ok=True, severidad="INFO", razon="texto vacío")
    encontrados = _PAT_REFERENCIA_COLGANTE.findall(texto)
    if encontrados:
        muestra = ", ".join(f"«{e.strip()}…»" for e in encontrados[:3])
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=f"{len(encontrados)} referencia(s) colgante(s) sin número: {muestra}",
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="sin referencias colgantes")


def check_citas_no_truncadas(texto: str) -> PostCheckResult:
    """Detecta citas literales «…texto…» que terminan con elipsis.

    Si una cláusula/norma fue truncada al construir el prompt, la IA copia
    el texto entrecomillado con la elipsis adentro («... VIGENCIA FISCAL
    202…»). Indica que la cita no es real, sino un artefacto de truncado.
    """
    if not texto:
        return PostCheckResult(ok=True, severidad="INFO", razon="texto vacío")
    encontrados = _PAT_CITA_TRUNCADA.findall(texto)
    if encontrados:
        muestra = encontrados[0][:80] + "…»"
        return PostCheckResult(
            ok=False,
            severidad="WARN",
            razon=f"{len(encontrados)} cita(s) literal(es) truncadas con elipsis: {muestra!r}",
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="citas literales completas")


def _normalizar_numero(s: str) -> str:
    """Quita separadores de miles y decimales para comparar cifras como
    secuencias de dígitos. "1.200.000" → "1200000", "1'200.000" → "1200000"."""
    return re.sub(r"[^\d]", "", s or "")


def check_valores_no_fabricados(
    texto_dictamen: str,
    texto_glosa_input: str | None,
    valor_objetado_input: str | int | float | None = None,
) -> PostCheckResult:
    """Detecta cifras monetarias en el dictamen que NO aparecen en el input.

    El bug visible en producción: el gestor pegó "Se glosa por falta de
    cobertura" sin valor, y el LLM rellenó con "$ 1.200.000" inventado.
    Lo mismo para valores que no aparecen en el texto que el gestor pegó.

    Estrategia conservadora:
      · Extrae todas las cifras monetarias del dictamen (>= 1000 para
        ignorar números de norma/artículo).
      · Para cada cifra, normaliza dígitos y verifica si aparece en el
        input del gestor O en el valor objetado del formulario.
      · Si alguna cifra del dictamen NO está en el input → ERROR.
    """
    if not texto_dictamen:
        return PostCheckResult(ok=True, severidad="INFO", razon="texto vacío")

    fuente = (texto_glosa_input or "") + " "
    if valor_objetado_input:
        fuente += str(valor_objetado_input)
    fuente_digitos = _normalizar_numero(fuente)

    cifras_en_dictamen: set[str] = set()
    for m in _PAT_VALOR_EN_DICTAMEN.finditer(texto_dictamen):
        bruto = m.group(1) or m.group(2) or ""
        normalizado = _normalizar_numero(bruto)
        if len(normalizado) < 4:  # < 1000 → ignorar (artículos, fechas)
            continue
        cifras_en_dictamen.add(normalizado)

    fabricadas = [c for c in cifras_en_dictamen if c not in fuente_digitos]
    if fabricadas:
        muestra = ", ".join(
            "$" + (f[:-6] + "." + f[-6:-3] + "." + f[-3:] if len(f) >= 7 else f[:-3] + "." + f[-3:])
            for f in fabricadas[:3]
        )
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=(
                f"{len(fabricadas)} cifra(s) monetaria(s) en el dictamen NO "
                f"aparecen en el input del gestor: {muestra}. La IA pudo "
                "haberlas fabricado."
            ),
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="cifras consistentes con input")


def check_contratos_no_fabricados(
    texto_dictamen: str,
    texto_glosa_input: str | None,
    clausulas_contrato: list[dict] | None = None,
) -> PostCheckResult:
    """Detecta números de contrato citados en el dictamen que NO existen
    en el input del gestor ni en las cláusulas reales inyectadas al prompt.

    Bug visible: el LLM citó "CONTRATO S-13-1-03-1-04958" sin que el gestor
    lo hubiera mencionado. Esos números son verificables de inmediato por
    la EPS y delatan al dictamen como fabricado.
    """
    if not texto_dictamen:
        return PostCheckResult(ok=True, severidad="INFO", razon="texto vacío")

    fuente = (texto_glosa_input or "").upper()
    if clausulas_contrato:
        for cl in clausulas_contrato:
            fuente += " " + str(cl.get("texto_literal") or "").upper()
            fuente += " " + str(cl.get("titulo") or "").upper()
            fuente += " " + str(cl.get("numero_contrato") or "").upper()

    contratos_dictamen: set[str] = set()
    for m in _PAT_CONTRATO_EN_DICTAMEN.finditer(texto_dictamen):
        num = m.group(1).upper().strip().rstrip(",.;:")
        # Ronda 10 (17-jun-2026) — un número de contrato REAL siempre tiene
        # al menos un dígito ("S-13-1-03-1-04958", "440-DIGSA/DMBUG-2025",
        # "1388 DE 2024"). Sin esta restricción la regex matchea "CONTRATO
        # VIGENTE", "CONTRATO ESTABLECE", "CONTRATO LEGALMENTE" como número,
        # provocando falsos positivos masivos en producción que tumban el
        # QG y disparan ESCALAR_HUMANO. Captado en logs reales 17-jun.
        if not any(ch.isdigit() for ch in num):
            continue
        if "-" in num or "/" in num or len(num) >= 6:
            contratos_dictamen.add(num)

    fabricados = [c for c in contratos_dictamen if c not in fuente]
    if fabricados:
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=(
                f"{len(fabricados)} número(s) de contrato citado(s) en el "
                f"dictamen no aparecen en el input ni en las cláusulas: "
                f"{', '.join(fabricados[:3])}. Probable fabricación."
            ),
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="contratos consistentes con input")


def check_contrato_de_otra_eps(texto_dictamen: str, eps: str | None) -> PostCheckResult:
    """Detecta números de contrato CONOCIDOS cuya EPS dueña ≠ EPS de la glosa.

    Ronda 2 (12-jun-2026) — el hallazgo más grave del estrés: 3 dictámenes
    citaron contratos de OTRA entidad (glosa DMBUG citó el
    S-13-1-03-1-04958 de FAMISANAR; "OTRA / SIN DEFINIR" citó su Cláusula
    4.2; FOMAG mezcló actas ajenas). check_contratos_no_fabricados NO los
    caza cuando el número llegó por few-shot/histórico (está "en el input"
    del prompt) — este check compara contra el catálogo contrato→dueña
    (CONTRATOS_HUS + ContratoRecord BD) sin importar de dónde vino.
    """
    if not texto_dictamen or not eps:
        return PostCheckResult(ok=True, severidad="INFO", razon="sin texto o sin EPS")
    try:
        from app.services.glosa_ia_prompts import contratos_ajenos_citados

        ajenos = contratos_ajenos_citados(texto_dictamen, eps)
    except Exception:
        return PostCheckResult(ok=True, severidad="INFO", razon="catálogo no disponible")
    if ajenos:
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=(
                f"{len(ajenos)} contrato(s) de OTRA EPS citado(s) en el dictamen: "
                f"{', '.join(ajenos[:3])} (la EPS de la glosa es {eps}). "
                "Citar el contrato de otra entidad invalida el dictamen completo."
            ),
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="sin contratos de otras EPS")


def check_sin_placeholders_crudos(texto_dictamen: str) -> PostCheckResult:
    """Detecta placeholders crudos tipo [ENTIDAD] / [VALOR REAL] / [CODIGO].

    Ronda 2 (12-jun-2026): un dictamen ENTREGADO conservaba los corchetes de
    la plantilla sin rellenar. Es defecto GRAVE — se radica texto roto.
    """
    if not texto_dictamen:
        return PostCheckResult(ok=True, severidad="INFO", razon="texto vacío")
    encontrados = _PAT_PLACEHOLDER_CRUDO.findall(texto_dictamen)
    if encontrados:
        muestra = ", ".join(encontrados[:3])
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=f"{len(encontrados)} placeholder(s) sin rellenar en el dictamen: {muestra}",
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="sin placeholders crudos")


# ── Dosis, cantidades y números de ítem inventados ────────────────────────
#
# 10-09-2026 — El caso que lo pidió. Objeción N° 189801, causal FA0701 sobre
# el IOBITRIDOL. La entidad objetó así, con todas sus letras:
#
#   «SE OBJETA MEDIO DE CONTRASTE UTILIZADO SEGUN NOTA OPERATORIA SE UTILIZA
#    40CC LA HOJA DE GASTOS REGISTRA FRASCO DE 100 ML 50 ML POR LO TANTO NO
#    SE RECONOCE COBRO DE 4 UNIDADES»
#
# y el dictamen que salió a defender el cobro dijo:
#
#   «EL ÍTEM 13 DE LA FACTURA INDICA LA ADQUISICIÓN DE CINCO UNIDADES DE
#    100 ML CADA UNA, TOTALIZANDO 500 ML»
#
# El ítem 13, las cinco unidades y los 500 ML **no están en ninguna parte de
# lo que se le entregó al modelo**. El medicamento es de 50 ML: lo dice la
# propia descripción del renglón, «IOBITRIDOL 300MG/50ML». O sea que el
# dictamen le discute a la entidad con una cuenta que se inventó, y encima
# se la atribuye a un renglón de la factura que nadie leyó. La entidad abre
# la factura, ve que el ítem 13 no dice eso, y el hospital pierde la glosa y
# la credibilidad de las otras siete.
#
# `check_valores_no_fabricados` no lo veía: solo mira cifras de plata con
# separador de miles. «500 ML» y «ÍTEM 13» pasaban de largo.
#
# Palabras que van delante de un número y NO anuncian una medida. Sin esto,
# «ANEXO 3 G» o «NUMERAL 5 L» de una norma se leerían como gramos y litros.
_ANTES_QUE_NO_ES_MEDIDA = (
    "ANEXO",
    "NUMERAL",
    "LITERAL",
    "ART",
    "ARTICULO",
    "ARTÍCULO",
    "PARAGRAFO",
    "PARÁGRAFO",
    "INCISO",
    "CAPITULO",
    "CAPÍTULO",
    "TITULO",
    "TÍTULO",
    "LEY",
    "DECRETO",
    "RESOLUCION",
    "RESOLUCIÓN",
    "CIRCULAR",
    "ACUERDO",
)

# Centímetro cúbico y mililitro son lo mismo, y el gramo se escribe de tres
# formas. Si no se unifican, un dictamen que dice «40 ML» sobre una glosa que
# dice «40CC» quedaría acusado de inventar.
_UNIDAD_CANONICA = {
    "CC": "ML",
    "ML": "ML",
    "CM3": "ML",
    "MG": "MG",
    "MGS": "MG",
    "MCG": "MCG",
    "UG": "MCG",
    "G": "G",
    "GR": "G",
    "GRS": "G",
    "KG": "KG",
    "UI": "UI",
    "MEQ": "MEQ",
    "L": "L",
}
_UNIDADES = "|".join(sorted(_UNIDAD_CANONICA, key=len, reverse=True))

_PAT_MEDIDA = re.compile(
    r"(?:(?P<antes>[A-ZÁÉÍÓÚÑ]+)\s+)?"
    r"(?P<num>\d+(?:[.,]\d+)?)\s?"
    r"(?P<uni>" + _UNIDADES + r")\b",
    re.IGNORECASE,
)

# «ÍTEM 13», «RENGLÓN No. 4», «FOLIO 27»: señalar un renglón concreto de un
# documento es afirmar que se leyó ese renglón.
_PAT_ITEM = re.compile(
    r"\b(?:[ÍI]TEM|RENGL[ÓO]N|FOLIO)\s*(?:N[oº°]?\.?\s*)?(\d{1,4})\b",
    re.IGNORECASE,
)

# «UN FRASCO», «UNA AMPOLLA»: en español eso casi siempre es el artículo, no
# una cuenta. Se dejan por fuera a propósito — acusar de inventada la prosa
# normal costaría una regeneración de IA y una escalada a humano por nada.
_NUMERO_EN_LETRAS = {
    "DOS": "2",
    "TRES": "3",
    "CUATRO": "4",
    "CINCO": "5",
    "SEIS": "6",
    "SIETE": "7",
    "OCHO": "8",
    "NUEVE": "9",
    "DIEZ": "10",
    "ONCE": "11",
    "DOCE": "12",
}
_ENVASES = (
    r"UNIDADES?|FRASCOS?|AMPOLLAS?|VIALES?|TABLETAS?|CAPSULAS?|CÁPSULAS?"
    r"|BOLSAS?|CAJAS?|SOBRES?|JERINGAS?"
)
_PAT_CONTEO = re.compile(
    r"\b(?P<num>\d{1,4}|" + "|".join(_NUMERO_EN_LETRAS) + r")\s+(?P<envase>" + _ENVASES + r")\b",
    re.IGNORECASE,
)


def _numero_normalizado(bruto: str) -> str:
    """«5», «CINCO», «05», «5,0» → «5». Deja el decimal si de verdad lo hay."""
    s = (bruto or "").strip().upper()
    if s in _NUMERO_EN_LETRAS:
        return _NUMERO_EN_LETRAS[s]
    s = s.replace(",", ".")
    try:
        valor = float(s)
    except ValueError:
        return s
    return str(int(valor)) if valor == int(valor) else str(valor)


def _medidas_del_texto(texto: str) -> set[tuple[str, str]]:
    """Todas las cantidades con unidad, ítems y conteos de un texto.

    Se devuelven normalizadas —(«500», «ML»), («13», «ITEM»), («5», «UNIDAD»)—
    para poder comparar dictamen contra fuente sin que la redacción estorbe.
    """
    encontradas: set[tuple[str, str]] = set()
    if not texto:
        return encontradas

    for m in _PAT_MEDIDA.finditer(texto):
        antes = (m.group("antes") or "").upper()
        if antes in _ANTES_QUE_NO_ES_MEDIDA:
            continue
        unidad = _UNIDAD_CANONICA[m.group("uni").upper()]
        encontradas.add((_numero_normalizado(m.group("num")), unidad))

    for m in _PAT_ITEM.finditer(texto):
        encontradas.add((_numero_normalizado(m.group(1)), "ITEM"))

    for m in _PAT_CONTEO.finditer(texto):
        encontradas.add((_numero_normalizado(m.group("num")), "UNIDAD"))

    return encontradas


def check_medidas_no_fabricadas(
    texto_dictamen: str,
    texto_glosa_input: str | None,
    fuentes_adicionales: list[str] | None = None,
) -> PostCheckResult:
    """Dosis, cantidades o números de ítem del dictamen que nadie le dio a la IA.

    Mismo criterio que `check_valores_no_fabricados`, pero para lo que no
    lleva signo de pesos: mililitros, miligramos, unidades, frascos, «ÍTEM 13».
    Si una medida aparece en la glosa o en cualquiera de las fuentes que se le
    pasaron al modelo (el prompt completo, con el texto de los soportes que se
    hayan leído), es legítima. Si no aparece en ninguna, el dictamen la
    fabricó y esto es ERROR: se radica un documento que la entidad desmiente
    abriendo la factura.
    """
    if not texto_dictamen:
        return PostCheckResult(ok=True, severidad="INFO", razon="texto vacío")

    fuente = texto_glosa_input or ""
    for extra in fuentes_adicionales or []:
        if extra:
            fuente += "\n" + extra
    if not fuente.strip():
        return PostCheckResult(ok=True, severidad="INFO", razon="sin input con qué comparar")

    de_la_fuente = _medidas_del_texto(fuente)
    fabricadas = sorted(_medidas_del_texto(texto_dictamen) - de_la_fuente)
    if fabricadas:
        muestra = ", ".join(
            f"ítem {n}" if u == "ITEM" else (f"{n} unidad(es)" if u == "UNIDAD" else f"{n} {u}")
            for n, u in fabricadas[:4]
        )
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=(
                f"{len(fabricadas)} cantidad(es) del dictamen no están en lo que "
                f"se le entregó a la IA: {muestra}. La entidad lo desmiente "
                "abriendo la factura."
            ),
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="cantidades consistentes con el input")


# ── Negarle al papel lo que el papel dice ───────────────────────────────────
#
# 10-09-2026, mismo caso. El dictamen escribió, para defender el cobro:
#
#   «…Y QUE EL MEDICAMENTO IOBITRIDOL NO ES UN MEDIO DE CONTRASTE, SINO UN
#    SOLUCIÓN ANTISEPTICA»
#
# El iobitridol es un medio de contraste yodado — la propia factura lo dice
# («EQUIVALENTE A 30%P/V DE YODO») y la entidad lo objetó llamándolo así
# («SE OBJETA MEDIO DE CONTRASTE UTILIZADO»). El dictamen le está negando al
# papel lo que el papel dice, y del otro lado lo lee un médico auditor: esa
# sola frase desacredita la respuesta entera, incluidos los siete renglones
# de millones que iban bien argumentados.
#
# El check es estrecho a propósito. NO se mete a opinar de medicina: solo
# mira si el dictamen niega, con todas sus letras, una naturaleza que el
# papel de la entidad afirma con esas mismas palabras. Negarle a la entidad
# sus afirmaciones jurídicas o administrativas —que la glosa es
# extemporánea, que no hubo autorización— es el trabajo del dictamen y no
# se toca. Lo que no puede hacer es reclasificar QUÉ ES una cosa sin una
# ficha técnica que lo respalde, porque eso no se discute: se comprueba.
_NATURALEZAS_QUE_NO_SE_REDEFINEN = (
    "MEDIO DE CONTRASTE",
    "MEDIOS DE CONTRASTE",
    "ANTIS[EÉ]PTICO",
    "ANTIBI[OÓ]TICO",
    "ANEST[EÉ]SICO",
    "DISPOSITIVO M[EÉ]DICO",
    "MATERIAL DE OSTEOS[IÍ]NTESIS",
    "MATERIAL QUIR[UÚ]RGICO",
    "INSUMO",
    "MEDICAMENTO",
    "PROCEDIMIENTO QUIR[UÚ]RGICO",
)

_PAT_NEGACION_DE_NATURALEZA = re.compile(
    r"\bNO\s+(?:ES|SON|SE\s+TRATA\s+DE|CORRESPONDE\s+A|CONSTITUYE)\s+"
    r"(?:UN[AO]?S?\s+|EL\s+|LA\s+|LOS\s+|LAS\s+)?"
    r"(?P<que>" + "|".join(_NATURALEZAS_QUE_NO_SE_REDEFINEN) + r")\b",
    re.IGNORECASE,
)


def _sin_tildes(texto: str) -> str:
    """«antiséptico» y «ANTISEPTICO» son la misma palabra. Deja las dos igual."""
    plano = unicodedata.normalize("NFD", (texto or "").upper())
    return " ".join("".join(c for c in plano if not unicodedata.combining(c)).split())


def check_no_contradice_la_naturaleza_del_servicio(
    texto_dictamen: str,
    texto_glosa_input: str | None,
    fuentes_adicionales: list[str] | None = None,
) -> PostCheckResult:
    """El dictamen no puede negar QUÉ ES una cosa cuando el papel lo dice.

    Solo salta cuando las dos condiciones se dan a la vez: el dictamen niega
    una naturaleza de la lista corta de arriba, y esa misma naturaleza está
    escrita en lo que la entidad mandó. No opina de medicina y no toca las
    negaciones jurídicas —«no es extemporánea», «no procede la glosa»—, que
    son el trabajo del dictamen.
    """
    if not texto_dictamen:
        return PostCheckResult(ok=True, severidad="INFO", razon="texto vacío")

    fuente = " ".join([texto_glosa_input or "", *(f for f in (fuentes_adicionales or []) if f)])
    if not fuente.strip():
        return PostCheckResult(ok=True, severidad="INFO", razon="sin input con qué comparar")

    # Sin tildes de los dos lados: en estos papeles «ANTISEPTICO» y
    # «antiséptico» son la misma palabra, y en mayúscula sostenida casi nadie
    # las pone. Comparar tal cual dejaría pasar justo el caso que se busca.
    fuente_norm = _sin_tildes(fuente)
    contradichas: list[str] = []
    for m in _PAT_NEGACION_DE_NATURALEZA.finditer(texto_dictamen):
        dicho = _sin_tildes(m.group("que"))
        if dicho in fuente_norm and dicho not in contradichas:
            contradichas.append(dicho)

    if contradichas:
        return PostCheckResult(
            ok=False,
            severidad="ERROR",
            razon=(
                "el dictamen niega lo que el papel de la entidad afirma: "
                + ", ".join(f"«no es {c.lower()}»" for c in contradichas[:3])
                + ". Del otro lado lo lee un auditor médico y desacredita "
                "toda la respuesta."
            ),
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="no contradice la naturaleza del cobro")


def check_datos_clinicos_usados(
    texto_dictamen: str,
    texto_glosa_input: str | None,
) -> PostCheckResult:
    """Check SUAVE (WARN): la glosa traía ≥2 datos clínicos y el dictamen no
    usa NINGUNO → "dictamen ignora los datos clínicos del caso".

    Ronda 2 (12-jun-2026): "NYHA III, FE 25%, lista de trasplante" / "47
    días UCI por TCE severo" / "Kellgren IV" — ningún dictamen los mencionó.
    Cuenta para el score (-10) pero NO bloquea por sí solo.
    """
    if not texto_dictamen or not texto_glosa_input:
        return PostCheckResult(ok=True, severidad="INFO", razon="sin texto o sin input")
    try:
        from app.services.contexto_contractual_enriquecido import extraer_datos_clinicos

        datos = extraer_datos_clinicos(texto_glosa_input)
    except Exception:
        return PostCheckResult(ok=True, severidad="INFO", razon="extractor no disponible")
    if len(datos) < 2:
        return PostCheckResult(
            ok=True, severidad="INFO", razon=f"{len(datos)} dato(s) clínico(s) en la glosa"
        )

    dictamen_norm = re.sub(r"\s+", " ", texto_dictamen.upper())

    def _presente(dato: str) -> bool:
        if dato in dictamen_norm:
            return True
        # Tolerancia de redacción: todos los tokens del dato presentes
        # ("47 DÍAS UCI" → "47", "DÍAS", "UCI" — la IA pudo reordenar).
        tokens = [t for t in re.split(r"\s+", dato) if t]
        return bool(tokens) and all(t in dictamen_norm for t in tokens)

    if not any(_presente(d) for d in datos):
        return PostCheckResult(
            ok=False,
            severidad="WARN",
            razon=(
                "dictamen ignora los datos clínicos del caso "
                f"({', '.join(datos[:4])}) — argumentación de plantilla."
            ),
        )
    return PostCheckResult(ok=True, severidad="INFO", razon="datos clínicos incorporados")


def post_validar_dictamen(
    texto: str,
    *,
    eps: str | None = None,
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
    texto_glosa_input: str | None = None,
    valor_objetado_input: str | int | float | None = None,
    clausulas_contrato: list[dict] | None = None,
    fuentes_adicionales: list[str] | None = None,
) -> PostValidationResult:
    """Ejecuta todos los post-checks del dictamen ya generado por la IA.

    Args:
        texto: dictamen completo
        eps: nombre de la EPS (para context en verificador de citas)
        es_ratificacion: si True, acepta coda procesal
        es_extemporanea: si True, acepta coda procesal
        fuentes_adicionales: todo lo demás que la IA sí vio (el prompt
            completo con el texto de los soportes leídos). Sirve para no
            acusar de inventadas las cantidades que vienen de un soporte.

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

    # 5. Referencias colgantes ("EL ART. EN ESTE SENTIDO" sin número)
    checks["referencias_colgantes"] = check_referencias_colgantes(texto)

    # 6. Citas literales no truncadas («… VIGENCIA FISCAL 202…»)
    checks["citas_truncadas"] = check_citas_no_truncadas(texto)

    # 7. Valores monetarios no fabricados (cifras solo si vienen del input).
    #    Solo se ejecuta si el caller pasó texto_glosa_input — para flujos
    #    que no lo proveen, se omite el check (legacy compat).
    if texto_glosa_input is not None:
        checks["valores_fabricados"] = check_valores_no_fabricados(
            texto,
            texto_glosa_input=texto_glosa_input,
            valor_objetado_input=valor_objetado_input,
        )

        # 8. Contratos no fabricados (números solo si vienen del input o
        #    de las cláusulas reales del contrato vigente).
        checks["contratos_fabricados"] = check_contratos_no_fabricados(
            texto,
            texto_glosa_input=texto_glosa_input,
            clausulas_contrato=clausulas_contrato,
        )

        # 9-11. Checks nuevos de la ronda 2 (12-jun-2026). Van dentro del
        #   gate `texto_glosa_input is not None` por compatibilidad con
        #   callers/tests legacy que validan el set exacto de checks sin
        #   pasar el input (el QG y multi_codigo SIEMPRE lo pasan).
        # 9. Contrato de OTRA EPS (catálogo contrato→dueña) — el más grave.
        checks["contrato_otra_eps"] = check_contrato_de_otra_eps(texto, eps)

        # 10. Placeholders crudos [ENTIDAD]/[VALOR REAL]/[CODIGO] → GRAVE.
        checks["placeholders_crudos"] = check_sin_placeholders_crudos(texto)

        # 11. Datos clínicos del caso ignorados → WARN (score, no bloquea).
        checks["datos_clinicos"] = check_datos_clinicos_usados(
            texto, texto_glosa_input=texto_glosa_input
        )

        # 12. Dosis, cantidades y números de ítem inventados (10-09-2026:
        #     «CINCO UNIDADES DE 100 ML… TOTALIZANDO 500 ML» sobre un
        #     medicamento de 50 ML que nadie contó). Igual de grave que una
        #     cifra de plata fabricada, y hasta hoy no lo miraba nadie.
        checks["medidas_fabricadas"] = check_medidas_no_fabricadas(
            texto,
            texto_glosa_input=texto_glosa_input,
            fuentes_adicionales=fuentes_adicionales,
        )

        # 13. Reclasificar qué ES una cosa contra lo que dice el papel
        #     (10-09-2026: «el IOBITRIDOL no es un medio de contraste, sino
        #     una solución antiséptica», sobre una glosa que lo objeta
        #     llamándolo medio de contraste).
        checks["naturaleza_contradicha"] = check_no_contradice_la_naturaleza_del_servicio(
            texto,
            texto_glosa_input=texto_glosa_input,
            fuentes_adicionales=fuentes_adicionales,
        )

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
