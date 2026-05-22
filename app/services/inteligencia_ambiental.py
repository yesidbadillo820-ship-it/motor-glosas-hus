"""Inteligencia Ambiental — la app anticipa lo que el usuario necesita.

Ola 4 del Plan de Transformación 2026.

Filosofía: hoy el gestor llena 8 campos para empezar a analizar.
Mañana la app sugiere 6 de esos campos antes de que escriba nada.

Capacidades:
  1. Auto-contexto desde número de factura
  2. Predicción de plantilla óptima ANTES del click Analizar
  3. Sugerencias contextuales (casos similares previos)
  4. Avisos proactivos para la topbar
  5. Detección rápida de código + valor en texto pegado
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PrediccionPlantilla:
    """Predicción de qué plantilla del banco HUS se usará."""

    codigo_familia: str  # "TA", "SO", "CO", "FA", "CL"
    plantilla_id: str  # "TA-G01", "TA-G02", etc.
    titulo: str
    confianza: float  # 0.0 - 1.0
    razon: str


@dataclass
class SugerenciaContextual:
    """Una sugerencia mostrada al gestor en tiempo real."""

    tipo: str  # "caso_similar", "patron_eps", "victoria_previa", "warning"
    titulo: str
    descripcion: str
    accion_label: str = ""  # texto del botón si hay acción
    accion_url: str = ""  # link de la acción
    relevancia: int = 50  # 0-100, para ordenar


@dataclass
class AnalisisRapidoTexto:
    """Lo que el sistema detecta en el texto pegado por el gestor."""

    codigos_detectados: list[str] = field(default_factory=list)
    valores_detectados: list[float] = field(default_factory=list)
    fecha_detectada: Optional[str] = None
    numero_factura: Optional[str] = None
    es_ratificacion: bool = False
    es_extemporanea: bool = False
    complejidad_estimada: str = "MEDIA"  # SIMPLE | MEDIA | COMPLEJA
    plantilla_predicha: Optional[PrediccionPlantilla] = None


# Patrones de extracción rápida
_REGEX_CODIGO = re.compile(r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b", re.IGNORECASE)
_REGEX_VALOR = re.compile(
    r"(?:\$|valor\s+(?:de|objetado)|por\s+valor\s+de)\s*([\d.',]+)",
    re.IGNORECASE,
)
_REGEX_VALOR_SIMPLE = re.compile(r"\$\s*([\d.',]+)")
_REGEX_FACTURA = re.compile(
    r"(?:factura|fact\.?|FE)\s*[#:]?\s*([A-Z]{0,4}\s*-?\s*\d{1,12})",
    re.IGNORECASE,
)
_REGEX_FECHA = re.compile(
    r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b|\b(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b"
)
_REGEX_RATIFICACION = re.compile(
    r"(ratific\w*|reiter\w+|insist\w+|persist\w+|mantien\w+\s+la\s+glosa)",
    re.IGNORECASE,
)
_REGEX_EXTEMPORANEA = re.compile(
    r"\b(extempor[áa]nea|despu[ée]s\s+del\s+plazo|tard[íi]a)\b", re.IGNORECASE
)


# Mapeo de familia → plantilla más usada para each familia + título descriptivo
# (Esto debería venir del banco HUS real; aquí están las defaults razonables)
_DEFAULT_PLANTILLA_POR_FAMILIA = {
    "TA": ("TA-G01", "Mayor valor cobrado — Tarifa institucional HUS por resolución"),
    "SO": ("SO-G01", "Historia clínica integral aportada — Res. 1995/1999"),
    "CO": ("CO-G02", "Atención inicial de urgencias sin autorización"),
    "FA": ("FA-G05", "Términos de glosa — Art. 57 Ley 1438/2011"),
    "CL": ("CL-G01", "Autonomía médica — Ley 1751/2015 Art. 17"),
}


def _parsear_valor_str(s: str) -> Optional[float]:
    if not s:
        return None
    limpio = re.sub(r"[^\d.,'']", "", s).replace("'", "").replace(",", "").replace(".", "")
    try:
        v = float(limpio)
        return v if v > 0 else None
    except ValueError:
        return None


def analisis_rapido(texto: str) -> AnalisisRapidoTexto:
    """Hace un análisis instantáneo del texto pegado.

    Útil para mostrar predicciones al gestor MIENTRAS escribe, antes
    siquiera de que haga click en Analizar.
    """
    resultado = AnalisisRapidoTexto()
    if not texto:
        return resultado

    # Códigos
    codigos = list({m.group(0).upper() for m in _REGEX_CODIGO.finditer(texto)})
    resultado.codigos_detectados = codigos

    # Valores monetarios
    valores: list[float] = []
    for m in _REGEX_VALOR.finditer(texto):
        v = _parsear_valor_str(m.group(1))
        if v:
            valores.append(v)
    for m in _REGEX_VALOR_SIMPLE.finditer(texto):
        v = _parsear_valor_str(m.group(1))
        if v and v not in valores:
            valores.append(v)
    resultado.valores_detectados = valores

    # Fechas
    fecha_m = _REGEX_FECHA.search(texto)
    if fecha_m:
        resultado.fecha_detectada = fecha_m.group(0)

    # Factura
    factura_m = _REGEX_FACTURA.search(texto)
    if factura_m:
        resultado.numero_factura = factura_m.group(1).strip()

    # Ratificación / extemporánea
    resultado.es_ratificacion = bool(_REGEX_RATIFICACION.search(texto))
    resultado.es_extemporanea = bool(_REGEX_EXTEMPORANEA.search(texto))

    # Predicción de plantilla
    if codigos:
        familia = codigos[0][:2]
        plantilla = _DEFAULT_PLANTILLA_POR_FAMILIA.get(familia)
        if plantilla:
            resultado.plantilla_predicha = PrediccionPlantilla(
                codigo_familia=familia,
                plantilla_id=plantilla[0],
                titulo=plantilla[1],
                confianza=0.85 if len(codigos) == 1 else 0.55,
                razon=f"Código {codigos[0]} → familia {familia} → plantilla {plantilla[0]}",
            )

    # Complejidad
    if resultado.es_ratificacion or resultado.es_extemporanea:
        resultado.complejidad_estimada = "COMPLEJA"
    elif valores and max(valores) >= 1_000_000:
        resultado.complejidad_estimada = "COMPLEJA"
    elif len(codigos) >= 2:
        resultado.complejidad_estimada = "COMPLEJA"
    elif valores and max(valores) < 100_000:
        resultado.complejidad_estimada = "SIMPLE"

    return resultado


def generar_sugerencias_contextuales(
    *,
    eps: str = "",
    codigo: str = "",
    valor: float | None = None,
    historico_glosas: list[dict] | None = None,
) -> list[SugerenciaContextual]:
    """Genera sugerencias contextuales basadas en el caso actual.

    Args:
        eps, codigo, valor: contexto del caso actual
        historico_glosas: lista de glosas previas con
            {eps, codigo, estado, valor, dictamen_id}

    Returns:
        lista de SugerenciaContextual ordenada por relevancia desc.
    """
    sugerencias: list[SugerenciaContextual] = []

    # Sugerencia de alto valor → independiente de histórico
    if valor and valor >= 1_000_000:
        sugerencias.append(
            SugerenciaContextual(
                tipo="patron_eps",
                titulo="🧠 Caso alto valor — usando razonamiento avanzado",
                descripcion=(
                    f"Valor ${valor:,.0f} ≥ $1M → la IA usará Claude Sonnet 4.5 "
                    "(razonamiento jurídico profundo)."
                ),
                relevancia=60,
            )
        )

    if not historico_glosas:
        sugerencias.sort(key=lambda s: s.relevancia, reverse=True)
        return sugerencias

    # 1. Casos similares previos (mismo eps + código)
    similares = [
        g
        for g in historico_glosas
        if g.get("eps", "").upper() == eps.upper() and g.get("codigo", "").upper() == codigo.upper()
    ]
    if similares:
        levantadas = [g for g in similares if g.get("estado", "").upper() == "LEVANTADA"]
        if levantadas:
            ult = levantadas[0]
            sugerencias.append(
                SugerenciaContextual(
                    tipo="victoria_previa",
                    titulo=f"💪 Ya ganaste {len(levantadas)} caso(s) similar(es)",
                    descripcion=(
                        f"Mismo par {eps} × {codigo}. "
                        f"Último: glosa #{ult.get('dictamen_id', '?')} "
                        f"por ${ult.get('valor', 0):,.0f}."
                    ),
                    accion_label="Ver dictamen ganador",
                    accion_url=f"/glosas/{ult.get('dictamen_id')}",
                    relevancia=90,
                )
            )

    # 2. Patrón EPS: si EPS rechaza con frecuencia este código
    mismo_codigo = [g for g in historico_glosas if g.get("codigo", "").upper() == codigo.upper()]
    if mismo_codigo:
        ratificadas = [g for g in mismo_codigo if g.get("estado", "").upper() == "RATIFICADA"]
        if len(ratificadas) >= 3:
            sugerencias.append(
                SugerenciaContextual(
                    tipo="warning",
                    titulo=f"⚠ {len(ratificadas)} ratificaciones previas con {codigo}",
                    descripcion="Refuerza el argumento con cláusula contractual literal.",
                    relevancia=75,
                )
            )

    sugerencias.sort(key=lambda s: s.relevancia, reverse=True)
    return sugerencias
