"""Detector de copia textual entre el dictamen IA y los ejemplos Gold
inyectados (R-cerebro mejora #7).

Cuando se inyectan ejemplos Gold como few-shot, el LLM puede caer en
la tentación de copiarlos casi tal cual. Eso es PELIGROSO porque:
  - el dictamen ya no se adapta a los datos reales (CUPS, EPS, valor)
  - la EPS detecta el patrón y ratifica más fácil
  - viola el contrato de "no inventes datos" si el ejemplo tenía
    cifras distintas

Aquí calculamos similitud sobre 5-gramas (jaccard) entre el argumento
generado y cada ejemplo. Si alguna pasa de un umbral (0.55 = 55%
solapamiento), forzamos retry con instrucción de adaptar.
"""
from __future__ import annotations

import re
from typing import Optional


def _normalizar(texto: str) -> str:
    """Pasa a mayúsculas, colapsa espacios y elimina puntuación leve."""
    if not texto:
        return ""
    t = texto.upper()
    t = re.sub(r"[^A-ZÁÉÍÓÚÜÑ0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _ngramas(texto: str, n: int = 5) -> set:
    """Conjunto de n-gramas de palabras."""
    palabras = _normalizar(texto).split()
    if len(palabras) < n:
        return set()
    return {
        " ".join(palabras[i:i + n])
        for i in range(len(palabras) - n + 1)
    }


def similitud_jaccard(
    texto1: str, texto2: str, n: int = 5,
) -> float:
    """Jaccard similarity sobre n-gramas. 0..1."""
    a = _ngramas(texto1, n)
    b = _ngramas(texto2, n)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def detectar_copia_gold(
    dictamen: str,
    ejemplos: list[dict],
    *,
    umbral: float = 0.55,
    n: int = 5,
) -> Optional[dict]:
    """Si el dictamen es >=umbral parecido a algún ejemplo Gold,
    retorna {"similitud": x, "ejemplo_id": id, "fuente": ...}.
    Si no, None.
    """
    if not dictamen or not ejemplos:
        return None
    peor: Optional[dict] = None
    for ej in ejemplos:
        arg_ej = ej.get("argumento") or ""
        s = similitud_jaccard(dictamen, arg_ej, n=n)
        if s >= umbral and (peor is None or s > peor["similitud"]):
            peor = {
                "similitud": round(s, 3),
                "ejemplo_id": ej.get("id"),
                "fuente": ej.get("fuente", "?"),
            }
    return peor


def instruccion_anti_copia(deteccion: dict) -> str:
    """Bloque a anexar al prompt para forzar adaptación."""
    if not deteccion:
        return ""
    return (
        "\n\n═══ DETECCIÓN DE COPIA TEXTUAL ═══\n"
        f"Tu respuesta anterior es {deteccion['similitud']*100:.0f}% "
        f"idéntica al EJEMPLO de fuente {deteccion['fuente']} "
        f"(id={deteccion['ejemplo_id']}). Esto es INACEPTABLE: el "
        "ejemplo es solo REFERENCIA, no debe copiarse textualmente.\n"
        "REGENERA el dictamen completo:\n"
        "  • Usando los datos REALES del BLOQUE 1 (CUPS, valor, EPS).\n"
        "  • Con ESTRUCTURA similar al ejemplo pero PALABRAS distintas.\n"
        "  • Reformula cada oración con vocabulario propio.\n"
        "  • Cita las MISMAS normas pero con frases distintas a las "
        "    del ejemplo.\n"
        "Responde de nuevo en el formato XML completo.\n"
    )
