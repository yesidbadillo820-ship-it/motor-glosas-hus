"""Detección de dictámenes obsoletos (stale) tras carga de tarifas/contratos.

Un dictamen se considera stale cuando ya no refleja la realidad contractual:

  • Cargamos un tarifario para esa EPS DESPUÉS de generar el dictamen, o
  • El argumento jurídico contradice un contrato/tarifa que sí existe ahora
    (p.ej. el dictamen dice "NO EXISTE CONTRATO PACTADO" y la EPS sí tiene
    tarifas activas en el catálogo).

La detección por texto es importante porque dictámenes generados antes de
introducir el campo `dictamen_generado_en` no tienen timestamp, y el campo
queda NULL hasta que se re-analicen. Sin la detección por texto esos
dictámenes se quedarían silenciosamente obsoletos.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models.db import GlosaRecord, TarifaContratadaRecord


# Frases que delatan un dictamen generado SIN saber del contrato/tarifario
# (caso típico: TA0xxx defendido con argumento SOAT pleno por "no existe
# contrato pactado" cuando en realidad sí hay un contrato cargado en BD).
_FRASES_NO_CONTRATO = (
    "NO EXISTE CONTRATO PACTADO",
    "NO EXISTE CONTRATO ENTRE LAS PARTES",
    "NO EXISTE CONTRATO VIGENTE",
    "AUSENCIA DE CONTRATO",
    "CARECE DE CONTRATO",
    "SIN CONTRATO PACTADO",
    "SIN CONTRATO ENTRE LAS PARTES",
)

# Frases canónicas que DEBEN aparecer en dictámenes mecánicos. Si la glosa
# califica como extemporánea o ratificada pero el texto del dictamen no
# contiene la frase canónica, el dictamen quedó mal generado por el LLM
# (caso glosa #2484: texto suavizado 'RESPETUOSAMENTE NO ACEPTA' cuando
# debería ser el canónico 'NO ACEPTA GLOSA EXTEMPORÁNEA').
_CANONICA_EXTEMPORANEA = "NO ACEPTA GLOSA EXTEMPORANEA"
_CANONICA_RATIFICADA = "NO ACEPTA GLOSA RATIFICADA"

# Indicadores en el texto de la glosa o etapa que delatan ratificación.
_INDICADORES_RATIFICACION = (
    "RATIFIC",   # RATIFICACION / RATIFICADA / RATIFICACIÓN
    "RESPUESTA A RATIFICACION",
    "RESPUESTA RATIFICACION",
)


def es_stale(glosa, db) -> bool:
    """True si el dictamen quedó desactualizado por carga de tarifas o
    porque su texto contradice el catálogo actual."""
    return motivo_stale(glosa, db) is not None


_STOPWORDS_EPS = {
    "DE", "DEL", "LA", "EL", "Y", "EPS", "ERP", "ARS", "CAJA",
    "ENTIDAD", "PROMOTORA", "SALUD", "SAS", "S.A.S", "S.A", "LTDA",
    "DIRECCION", "DIRECCIÓN", "SANIDAD", "SUBSISTEMA",
}


def _tokens_significativos(s: str) -> set[str]:
    """Devuelve las palabras significativas (≥4 chars, sin stopwords) del nombre."""
    if not s:
        return set()
    palabras = re.split(r"[\s\-·:/]+", s.upper())
    return {p for p in palabras if len(p) >= 4 and p not in _STOPWORDS_EPS}


def _matchea_eps(eps_glosa: str, eps_tarifa: str) -> bool:
    """Match permisivo de EPS por tokens significativos.

    Reglas (en orden):
      1. Equivalencia exacta del normalizador (caso ideal).
      2. ≥2 tokens significativos compartidos (≥4 chars, sin stopwords).
         Ej: "DISPENSARIO MEDICO BUCARAMANGA" ~ "DISPENSARIO MEDICO DMBUG"
             → {DISPENSARIO, MEDICO} → match.
      3. Si uno de los dos tiene un solo token significativo (siglas como
         FOMAG, DMBUG, ISS), basta con que ese token aparezca como
         subcadena del otro. Ej: "DMBUG" matchea
         "U220311 - ... - DMBUG" si encontramos el token "DMBUG".
    """
    if not eps_glosa or not eps_tarifa:
        return False
    from app.services import pagador_normalizer
    if pagador_normalizer.son_equivalentes(eps_glosa, eps_tarifa):
        return True
    a = _tokens_significativos(pagador_normalizer.nombre_corto(eps_glosa))
    b = _tokens_significativos(pagador_normalizer.nombre_corto(eps_tarifa))
    if len(a & b) >= 2:
        return True
    # Sigla única (DMBUG, FOMAG, ISS, etc.) — buscar como subcadena en el otro
    if len(a) == 1 and a:
        sigla = next(iter(a))
        if sigla in pagador_normalizer.nombre_corto(eps_tarifa).upper():
            return True
    if len(b) == 1 and b:
        sigla = next(iter(b))
        if sigla in pagador_normalizer.nombre_corto(eps_glosa).upper():
            return True
    return False


def _eps_tiene_tarifas(db, eps: str, tercero_nombre: str = ""):
    """Devuelve la primera tarifa activa que matchea la EPS o None.

    Prueba contra `eps` (plan EPS oficial) y `tercero_nombre` (nombre
    comercial corto del Tercero) usando matching por tokens permisivo.
    """
    nombres_a_probar = [n for n in (eps, tercero_nombre) if n and n.strip()]
    if not nombres_a_probar:
        return None
    from app.models.db import TarifaContratadaRecord
    candidatos = (
        db.query(TarifaContratadaRecord)
        .filter(TarifaContratadaRecord.activa == 1)
        .limit(200)
        .all()
    )
    for t in candidatos:
        t_eps = (t.eps or "").strip()
        if not t_eps:
            continue
        for n in nombres_a_probar:
            if _matchea_eps(n, t_eps):
                return t
    return None


def _texto_dictamen_normalizado(html: str) -> str:
    """Quita tags HTML, diacríticos y normaliza para búsqueda case-insensitive.

    Sin quitar tildes la búsqueda se rompe: la frase de origen es 'PUNCIÓN'
    pero la lista de patrones se compara contra 'PUNCION'.
    """
    sin_tags = re.sub(r"<[^>]+>", " ", html or "")
    nfkd = unicodedata.normalize("NFKD", sin_tags)
    sin_dia = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_dia).strip().upper()


def motivo_stale(glosa, db) -> Optional[str]:
    """Retorna un mensaje legible si el dictamen está stale, o None si vigente."""
    if not glosa or not glosa.dictamen:
        return None
    eps = (glosa.eps or "").strip()
    if not eps:
        return None

    texto = _texto_dictamen_normalizado(glosa.dictamen)
    contradice_contrato = any(f in texto for f in _FRASES_NO_CONTRATO)

    generado: Optional[datetime] = getattr(glosa, "dictamen_generado_en", None)

    tercero = (getattr(glosa, "tercero_nombre", "") or "").strip()
    codigo_respuesta = (getattr(glosa, "codigo_respuesta", "") or "").strip().upper()
    codigo_glosa = (getattr(glosa, "codigo_glosa", "") or "").strip().upper()
    etapa = (getattr(glosa, "etapa", "") or "").upper()
    dias_radicacion = int(getattr(glosa, "dias_radicacion_dgh", 0) or 0)

    # 0a) Extemporánea (>20 días) sin texto canónico aplicado.
    if dias_radicacion > 20 and _CANONICA_EXTEMPORANEA not in texto:
        return (
            f"Glosa extemporánea ({dias_radicacion} días) pero el dictamen "
            f"no usa el texto canónico HUS para extemporáneas. "
            f"Re-analizar para aplicar el texto fijo correcto."
        )

    # 0b) Ratificación sin texto canónico aplicado.
    if any(ind in etapa for ind in _INDICADORES_RATIFICACION) and _CANONICA_RATIFICADA not in texto:
        return (
            "Glosa en etapa de ratificación pero el dictamen no usa el "
            "texto canónico HUS para ratificadas. Re-analizar para "
            "aplicar el texto fijo correcto."
        )

    # 1) Texto-based: dictamen niega contrato pero la EPS sí tiene tarifas
    #    activas. Se aplica también a dictámenes sin timestamp (legados).
    if contradice_contrato:
        tarifa = _eps_tiene_tarifas(db, eps, tercero)
        if tarifa is not None:
            return (
                "El dictamen argumenta que NO existe contrato, pero el "
                "catálogo ya tiene tarifas activas para esta EPS. "
                "Re-analizar para usar el contrato vigente."
            )

    # 2) Código RE incorrecto: glosa por TARIFAS con código RE9602 (defensa
    #    "injustificada por SOAT pleno"), pero el catálogo SÍ tiene
    #    contrato pactado para esta EPS. El código correcto sería RE9901
    #    ("subsanada con referencia contractual"). Caso típico: dictámenes
    #    generados cuando aún no se cargaba el contrato y quedaron mal
    #    etiquetados aunque ya se respondieron.
    if codigo_respuesta == "RE9602" and codigo_glosa.startswith("TA"):
        tarifa = _eps_tiene_tarifas(db, eps, tercero)
        if tarifa is not None:
            return (
                "Código RE9602 incorrecto: hay contrato pactado para esta "
                "EPS, así que la defensa estándar es RE9901. Re-analizar "
                "para que el dictamen cite la tarifa contractual."
            )

    # 3) Timestamp-based: tarifas para la EPS cargadas después del dictamen.
    if generado:
        from app.models.db import TarifaContratadaRecord
        candidatos = (
            db.query(TarifaContratadaRecord)
            .filter(TarifaContratadaRecord.activa == 1)
            .filter(TarifaContratadaRecord.creado_en > generado)
            .limit(80)
            .all()
        )
        for t in candidatos:
            t_eps = (t.eps or "").strip()
            if not t_eps:
                continue
            if _matchea_eps(eps, t_eps) or (tercero and _matchea_eps(tercero, t_eps)):
                fecha_str = t.creado_en.strftime("%d/%m/%Y") if t.creado_en else "?"
                return (
                    f"Hay tarifas nuevas cargadas el {fecha_str} para esta EPS. "
                    f"El dictamen puede estar desactualizado — re-analizar es recomendable."
                )
    return None
