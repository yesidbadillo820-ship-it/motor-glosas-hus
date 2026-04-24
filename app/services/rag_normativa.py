"""RAG de normativa colombiana de salud.

Ronda 7. Indexa el cuerpo normativo que ya está en normativa_completa.py +
citas frecuentes y ofrece búsqueda semántica liviana (TF-IDF-like) para:

  1. Sugerir citas normativas exactas al gestor mientras edita un dictamen
  2. Validar que las citas usadas por la IA existen realmente (anti-
     alucinación: si la IA cita 'Sentencia T-999/2099', el validador la
     flagea como dudosa porque no está en nuestro índice)

Implementación SIN dependencias pesadas: TF-IDF sobre las claves de
_TODAS_LAS_NORMAS (~40 entradas). Suficiente para nuestro dominio y
ejecuta en <10 ms sin cargar modelos de embedding.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Optional


def _normalizar(texto: str) -> str:
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def _tokenizar(texto: str) -> list[str]:
    norm = _normalizar(texto)
    STOP = {
        "de", "la", "el", "los", "las", "en", "un", "una", "que", "por", "para",
        "con", "sin", "del", "al", "se", "es", "como", "este", "esta", "estos",
    }
    return [t for t in norm.split() if t not in STOP and len(t) >= 3]


# Ronda 50 Paso 5: sinónimos del dominio. Se expande el query antes de
# tokenizar para que "plazo" matchee normas que solo usan "término", etc.
# Todos minúsculas sin tildes (post _normalizar).
_SINONIMOS_DOMINIO: dict[str, list[str]] = {
    "plazo": ["termino", "tiempo"],
    "termino": ["plazo", "tiempo"],
    "ips": ["prestador", "hospital", "clinica"],
    "prestador": ["ips", "hospital", "clinica"],
    "eps": ["pagador", "entidad", "asegurador"],
    "pagador": ["eps", "entidad", "asegurador"],
    "glosa": ["objecion", "reparo"],
    "objecion": ["glosa", "reparo"],
    "glosas": ["objeciones", "reparos"],
    "factura": ["cobro", "facturacion"],
    "factura": ["cobro", "facturacion"],
    "soporte": ["documento", "anexo"],
    "historia": ["clinica", "epicrisis", "registro"],
    "tarifa": ["valor", "precio", "pactado"],
    "tarifas": ["valores", "precios", "pactados"],
    "consulta": ["atencion", "visita"],
    "cups": ["procedimiento", "codigo"],
    "ratificada": ["mantenida", "reiterada"],
    "extemporanea": ["tardia", "vencida"],
    "conciliacion": ["acuerdo", "negociacion"],
    "levantamiento": ["aceptacion", "desistimiento"],
    "respuesta": ["replica", "contestacion"],
    "autorizacion": ["aval", "orden"],
    "rips": ["registro", "reporte"],
    "fev": ["factura", "electronica"],
}


def _expandir_con_sinonimos(tokens: list[str]) -> list[str]:
    """Expande la lista de tokens con sus sinónimos conocidos del dominio.

    No duplica: si 'plazo' ya está y se expande 'termino', se agrega una
    sola vez. Los sinónimos tienen peso 0.5 del original (se duplican con
    ese factor — el caller puede leer las frecuencias para ponderar).
    """
    expandidos = list(tokens)  # copia
    vistos = set(tokens)
    for t in tokens:
        for sin in _SINONIMOS_DOMINIO.get(t, []):
            if sin not in vistos:
                expandidos.append(sin)
                vistos.add(sin)
    return expandidos


# Patrones para detectar citas literales en la consulta — boost cuando
# matchean exactamente con el documento.
_CITA_LITERAL_RE = re.compile(
    r"(art[íi]culo|art\.|ley|resoluci[oó]n|res\.|decreto|dec\.|circular|sentencia|acuerdo)\s*"
    r"([tcsu]?-?\s*\d+(?:[/\-]\d+)?)",
    re.IGNORECASE,
)


def _extraer_citas_literales(consulta: str) -> list[str]:
    """Encuentra citas normativas formales en la consulta ('Art. 57',
    'Ley 1438', 'Res. 2284'). Útil para boost en scoring."""
    if not consulta:
        return []
    citas = []
    for m in _CITA_LITERAL_RE.finditer(consulta):
        tipo = _normalizar(m.group(1))
        numero = _normalizar(m.group(2))
        citas.append(f"{tipo}_{numero}".replace(" ", ""))
    return citas


def _cargar_indice() -> dict:
    """Construye índice TF-IDF sobre _TODAS_LAS_NORMAS.

    Retorna:
      {
        "docs": {clave: {tokens, tokens_set, tf, texto_completo, metadata}},
        "idf": {token: idf_score},
        "N": cantidad de docs
      }
    """
    try:
        from app.services.normativa_completa import _TODAS_LAS_NORMAS
    except Exception:
        return {"docs": {}, "idf": {}, "N": 0}

    docs: dict[str, dict] = {}
    for clave, n in _TODAS_LAS_NORMAS.items():
        bloques = [
            n.get("nombre", ""),
            n.get("titulo", ""),
            n.get("ambito", ""),
            " ".join(n.get("keywords", [])),
        ]
        texto = " ".join(str(b) for b in bloques if b)
        tokens = _tokenizar(texto)
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        # Normalizar TF por longitud del doc
        longi = sum(tf.values()) or 1
        tf = {k: v / longi for k, v in tf.items()}
        docs[clave] = {
            "tokens": tokens,
            "tokens_set": set(tokens),
            "tf": tf,
            "texto": texto,
            "metadata": n,
        }
    # IDF
    N = len(docs)
    df: dict[str, int] = {}
    for d in docs.values():
        for tok in d["tokens_set"]:
            df[tok] = df.get(tok, 0) + 1
    idf = {tok: math.log(1 + N / (1 + cnt)) for tok, cnt in df.items()}
    return {"docs": docs, "idf": idf, "N": N}


# Cache lazy del índice — se construye en primer uso
_INDICE: Optional[dict] = None


def _get_indice() -> dict:
    global _INDICE
    if _INDICE is None:
        _INDICE = _cargar_indice()
    return _INDICE


def buscar_normas(consulta: str, top_k: int = 5, min_score: float = 0.05) -> list[dict]:
    """Busca normas relevantes para una consulta libre.

    Ej: 'tarifa soat diferencia contrato' → [Circular 047/2025, Art. 871, ...]

    Ronda 50 Paso 5: agrega sinónimos del dominio (plazo↔término, IPS↔
    prestador, glosa↔objeción...) y boost por citas literales ('Art. 57',
    'Res. 2284').
    """
    idx = _get_indice()
    if not idx.get("docs"):
        return []
    q_tokens_originales = _tokenizar(consulta)
    if not q_tokens_originales:
        return []

    # Expandir con sinónimos: sinónimos pesan 0.5 del original.
    q_tokens_expandidos = _expandir_con_sinonimos(q_tokens_originales)
    q_tf: dict[str, float] = {}
    peso_sinonimo = 0.5
    set_originales = set(q_tokens_originales)
    for t in q_tokens_expandidos:
        peso = 1.0 if t in set_originales else peso_sinonimo
        q_tf[t] = q_tf.get(t, 0) + peso
    longi = sum(q_tf.values()) or 1
    q_tf = {k: v / longi for k, v in q_tf.items()}

    # Citas literales en la consulta — para boost
    citas_query = set(_extraer_citas_literales(consulta))

    scores = []
    idf = idx["idf"]
    for clave, d in idx["docs"].items():
        score = 0.0
        for tok, w_q in q_tf.items():
            if tok in d["tf"]:
                score += w_q * d["tf"][tok] * (idf.get(tok, 1.0) ** 2)
        # Boost ×2 si el nombre de la norma contiene una cita literal del query
        # (ej. query '¿qué dice Art. 57 Ley 1438?' boostea Ley 1438).
        if citas_query:
            clave_norm = _normalizar(clave)
            for cita in citas_query:
                # Cita ya viene normalizada ('ley_1438', 'resolucion_2284')
                numero = cita.split("_", 1)[-1] if "_" in cita else cita
                if numero and numero in clave_norm:
                    score *= 2.0
                    break
        if score > min_score:
            scores.append((clave, score, d["metadata"]))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [
        {
            "clave": clave,
            "score": round(score, 4),
            "nombre": meta.get("nombre", clave),
            "titulo": meta.get("titulo", ""),
            "ambito": meta.get("ambito", ""),
            "vigente": bool(meta.get("vigente", True)),
        }
        for clave, score, meta in scores[:top_k]
    ]


def validar_citas_en_dictamen(dictamen: str) -> dict:
    """Extrae citas del dictamen (Ley 100, Art. 871, Res. 2284/2023, etc.)
    y valida cuáles existen en nuestro índice vs. cuáles son dudosas
    (posiblemente alucinadas por la IA).

    Patrones detectados:
      - Ley XXXX de YYYY / Ley XXXX/YYYY
      - Resolución XXXX de YYYY / Res. XXXX/YYYY
      - Decreto XXXX de YYYY / Dec. XXXX/YYYY
      - Circular XXX de YYYY
      - Sentencia T-XXX/YYYY / C-XXX/YYYY / SU-XXX/YYYY
      - Art. XXX (del cuerpo normativo mencionado cerca)
    """
    if not dictamen:
        return {"citas_detectadas": [], "no_verificadas": [], "total": 0}

    patrones = [
        (r"LEY\s+(\d{1,4})\s+(?:DE\s+)?(\d{4})", "Ley"),
        (r"RESOLUCI[ÓO]N\s+(\d{1,4})\s+(?:DE\s+)?(\d{4})", "Res."),
        (r"DECRETO\s+(\d{1,4})\s+(?:DE\s+)?(\d{4})", "Dec."),
        (r"CIRCULAR\s+(?:EXTERNA\s+)?(\d{1,4})\s+(?:DE\s+)?(\d{4})", "Cir."),
        (r"SENTENCIA\s+(T|C|SU)-(\d{1,4})(?:[/\s]+DE\s+)?[/\s]+(\d{4})", "Sent."),
        (r"ACUERDO\s+(\d{1,4})\s+(?:DE\s+)?(\d{4})", "Acuerdo"),
    ]
    texto = dictamen.upper()
    citas = []
    for pat, tipo in patrones:
        for m in re.finditer(pat, texto):
            if tipo == "Sent.":
                citas.append(f"{tipo} {m.group(1)}-{m.group(2)}/{m.group(3)}")
            else:
                citas.append(f"{tipo} {m.group(1)}/{m.group(2)}")

    citas = list(dict.fromkeys(citas))  # dedupe preservando orden
    idx = _get_indice()
    # Validar: si alguna parte del número aparece en los nombres/claves del
    # índice, se considera verificada.
    claves_texto = " ".join([
        d["texto"] for d in idx.get("docs", {}).values()
    ]).upper()
    no_verificadas = []
    verificadas = []
    for c in citas:
        # Extraer número para buscar
        m = re.search(r"(\d{1,4})", c)
        if not m:
            no_verificadas.append(c)
            continue
        numero = m.group(1)
        if numero in claves_texto:
            verificadas.append(c)
        else:
            no_verificadas.append(c)

    return {
        "citas_detectadas": citas,
        "verificadas": verificadas,
        "no_verificadas": no_verificadas,
        "total": len(citas),
        "tasa_verificacion": round(
            len(verificadas) / len(citas), 2
        ) if citas else 1.0,
    }
