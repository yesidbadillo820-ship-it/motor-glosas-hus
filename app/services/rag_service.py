"""
rag_service.py — Recuperación de glosas históricas similares (precedentes
internos) usando BM25 nativo (sin dependencias externas).

UPGRADE 2026-05: reemplaza el matching basado en SequenceMatcher
(similitud de strings carácter-a-carácter) por **BM25 Okapi**, el
algoritmo estándar de IR. Para textos legales en español con
vocabulario técnico repetitivo, BM25:

  - Pondera términos raros (IDF) → "manual tarifario" pesa más que "el"
  - Maneja saturación de frecuencia (no premia repeticiones excesivas)
  - Normaliza por longitud → no favorece artificialmente docs largos

Resultado esperado: precedentes mejor rankeados → defensa apoyada en
glosas que realmente comparten el patrón argumental, no solo palabras
sueltas. Sin dependencias nuevas (~70 líneas de matemática pura).
"""
import re
import math
import logging
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from app.models.db import GlosaRecord

logger = logging.getLogger("motor_glosas")


# ─── Helpers legacy (compat con tests + uso externo) ─────────────────
def _normalizar(texto):
    if not texto:
        return ""
    t = re.sub(r"[^\w\s]", " ", texto.lower())
    return re.sub(r"\s+", " ", t).strip()


def _similitud(a, b):
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _palabras_clave(texto):
    STOPWORDS_LEGACY = {"para", "como", "esta", "este", "pero", "donde", "cuando", "tiene",
                        "valor", "glosa", "segun", "articulo", "dicho", "dicha", "sobre"}
    palabras = re.findall(r"[a-záéíóúñ]{5,}", _normalizar(texto))
    return {p for p in palabras if p not in STOPWORDS_LEGACY}


# ─── BM25 nativo (núcleo del nuevo ranker) ───────────────────────────

# Stopwords español + jerga genérica del dominio glosas (no aportan info)
_STOPWORDS = frozenset({
    "para", "como", "esta", "este", "pero", "donde", "cuando", "tiene",
    "valor", "glosa", "segun", "según", "articulo", "artículo", "dicho",
    "dicha", "sobre", "entre", "porque", "puede", "debe", "deben", "hace",
    "hacer", "tambien", "también", "muy", "mas", "más", "menos", "ante",
    "bajo", "con", "contra", "desde", "durante", "hasta", "mediante",
    "para", "por", "sin", "sobre", "tras", "que", "los", "las", "del",
    "una", "uno", "unos", "unas", "ese", "esa", "esos", "esas", "ello",
    "todo", "toda", "todos", "todas", "otro", "otra", "otros", "otras",
})

# Parámetros BM25 estándar — funcionan bien out-of-the-box
BM25_K1 = 1.5
BM25_B = 0.75


def _tokenizar(texto: str) -> list[str]:
    """Tokeniza a lista de términos: minúsculas, sin acentos, sin
    stopwords, mínimo 4 chars (descarta nº/cup/conectores)."""
    if not texto:
        return []
    repl = str.maketrans("áéíóúñ", "aeioun")
    norm = texto.translate(repl).lower()
    tokens = re.findall(r"[a-z]{4,}", norm)
    return [t for t in tokens if t not in _STOPWORDS]


def _bm25_score(
    query_terms: list[str],
    doc_terms: list[str],
    avg_doc_len: float,
    idf: dict[str, float],
) -> float:
    """Score BM25 Okapi: suma sobre términos de query del IDF * TF saturado."""
    if not query_terms or not doc_terms:
        return 0.0
    doc_len = len(doc_terms)
    if doc_len == 0:
        return 0.0
    tf: dict[str, int] = {}
    for t in doc_terms:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for q in query_terms:
        if q not in tf:
            continue
        f = tf[q]
        idf_q = idf.get(q, 0.0)
        if idf_q <= 0:
            continue
        norm_factor = 1.0 - BM25_B + BM25_B * (doc_len / max(avg_doc_len, 1.0))
        score += idf_q * (f * (BM25_K1 + 1)) / (f + BM25_K1 * norm_factor)
    return score


class RAGService:
    def buscar_casos_similares(
        self,
        texto_glosa: str,
        eps: str,
        codigo_glosa: str,
        db: Session,
        top_k: int = 3,
        solo_exitosos: bool = True,
    ) -> list[dict]:
        """Busca top-K glosas históricas similares con BM25 + boosts EPS/código.

        Pipeline:
          1. Carga candidatas de BD (filtro por dictamen no nulo + LEVANTADA si solo_exitosos)
          2. Tokeniza cada candidata + la nueva glosa
          3. Calcula IDF sobre el corpus de candidatas
          4. BM25 score por candidata
          5. Boost: +EPS exacto, +mismo prefijo código (TA, SO, AU, etc.)
          6. Top-K ordenado descendente
        """
        prefijo = codigo_glosa[:2] if codigo_glosa and codigo_glosa != "N/A" else ""

        q = db.query(GlosaRecord).filter(GlosaRecord.dictamen.isnot(None))
        if solo_exitosos:
            q = q.filter(GlosaRecord.decision_eps == "LEVANTADA")
        candidatas = q.order_by(GlosaRecord.creado_en.desc()).limit(300).all()
        if not candidatas:
            return []

        # Construir corpus tokenizado: doc = texto del codigo_glosa + dictamen
        # (priorizamos dictamen porque concentra los argumentos jurídicos)
        docs_terms: list[list[str]] = []
        for g in candidatas:
            txt = (g.codigo_glosa or "") + " " + (g.dictamen or "")
            # Limpiar HTML del dictamen (puede haber tags)
            txt = re.sub(r"<[^>]+>", " ", txt)
            docs_terms.append(_tokenizar(txt))

        # IDF sobre el corpus (incluye query)
        N = len(docs_terms)
        df: dict[str, int] = {}
        for terms in docs_terms:
            for t in set(terms):
                df[t] = df.get(t, 0) + 1
        idf = {
            t: math.log(1 + (N - n + 0.5) / (n + 0.5))
            for t, n in df.items()
        }
        avg_doc_len = sum(len(d) for d in docs_terms) / max(N, 1)

        # Tokenizar query
        query_terms = _tokenizar(texto_glosa)
        if not query_terms:
            return []

        # Score BM25 + boosts por candidata
        scored = []
        for i, g in enumerate(candidatas):
            base_score = _bm25_score(query_terms, docs_terms[i], avg_doc_len, idf)
            # Boosts dominio-específicos (proporcionales para no dominar BM25)
            boost = 0.0
            if g.eps and eps and g.eps.upper() == eps.upper():
                boost += 2.5  # mismo EPS = mismo contexto contractual
            if prefijo and g.codigo_glosa and g.codigo_glosa.startswith(prefijo):
                boost += 3.5  # mismo tipo de glosa = mismo argumento jurídico aplica
            score_total = base_score + boost
            if score_total > 1.0:  # umbral mínimo para evitar resultados ruidosos
                scored.append((score_total, g))

        scored.sort(key=lambda x: x[0], reverse=True)

        resultados = []
        for score, g in scored[:top_k]:
            extracto = re.sub(r"<[^>]+>", " ", (g.dictamen or "")[:600])
            extracto = re.sub(r"\s+", " ", extracto).strip()
            resultados.append({
                "codigo_glosa": g.codigo_glosa,
                "eps": g.eps,
                "etapa": g.etapa,
                "decision_eps": g.decision_eps or "N/A",
                "score_similitud": round(score, 3),
                "extracto_dictamen": extracto,
                "id": g.id,
            })

        if resultados:
            logger.debug(
                f"[RAG-BM25] {len(resultados)} precedentes para eps={eps} "
                f"codigo={codigo_glosa} top_score={resultados[0]['score_similitud']:.2f}"
            )
        return resultados

    def construir_contexto_rag(self, casos: list[dict]) -> str:
        if not casos:
            return ""
        lineas = ["=== PRECEDENTES EXITOSOS DEL PROPIO HUS ===",
                  f"Se encontraron {len(casos)} caso(s) similar(es):\n"]
        for i, c in enumerate(casos, 1):
            lineas.append(
                f"PRECEDENTE #{i} — Código: {c['codigo_glosa']} | EPS: {c['eps']}\n"
                f"Extracto: {c['extracto_dictamen']}\n{'─' * 60}"
            )
        return "\n".join(lineas)
