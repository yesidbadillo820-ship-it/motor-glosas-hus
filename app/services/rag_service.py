import re
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from app.models.db import GlosaRecord


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
    STOPWORDS = {"para", "como", "esta", "este", "pero", "donde", "cuando", "tiene",
                 "valor", "glosa", "segun", "articulo", "dicho", "dicha", "sobre"}
    palabras = re.findall(r"[a-záéíóúñ]{5,}", _normalizar(texto))
    return {p for p in palabras if p not in STOPWORDS}


class RAGService:
    def buscar_casos_similares(self, texto_glosa, eps, codigo_glosa, db: Session,
                                top_k=3, solo_exitosos=True):
        prefijo = codigo_glosa[:2] if codigo_glosa and codigo_glosa != "N/A" else ""
        q = db.query(GlosaRecord).filter(GlosaRecord.dictamen.isnot(None))
        if solo_exitosos:
            q = q.filter(GlosaRecord.decision_eps == "LEVANTADA")
        candidatos = q.order_by(GlosaRecord.creado_en.desc()).limit(200).all()
        if not candidatos:
            return []

        kw_nueva = _palabras_clave(texto_glosa)
        scored = []
        for g in candidatos:
            if not g.dictamen:
                continue
            sim_texto = _similitud(texto_glosa, g.codigo_glosa or "")
            kw_dict = _palabras_clave(g.dictamen)
            kw_overlap = len(kw_nueva & kw_dict) / max(len(kw_nueva), 1) if kw_nueva and kw_dict else 0.0
            bonus_eps = 0.25 if g.eps and g.eps.upper() == eps.upper() else 0.0
            bonus_codigo = 0.35 if prefijo and g.codigo_glosa and g.codigo_glosa.startswith(prefijo) else 0.0
            score_total = (sim_texto * 0.15) + (kw_overlap * 0.25) + bonus_eps + bonus_codigo
            if score_total > 0.2:
                scored.append((score_total, g))

        scored.sort(key=lambda x: x[0], reverse=True)
        resultados = []
        for score, g in scored[:top_k]:
            extracto = re.sub(r"<[^>]+>", " ", g.dictamen[:600] or "")
            extracto = re.sub(r"\s+", " ", extracto).strip()
            resultados.append({
                "codigo_glosa": g.codigo_glosa, "eps": g.eps, "etapa": g.etapa,
                "decision_eps": g.decision_eps or "N/A",
                "score_similitud": round(score, 3), "extracto_dictamen": extracto, "id": g.id,
            })
        return resultados

    def construir_contexto_rag(self, casos):
        if not casos:
            return ""
        lineas = ["=== PRECEDENTES EXITOSOS DEL PROPIO HUS ===",
                  f"Se encontraron {len(casos)} caso(s) similar(es):\n"]
        for i, c in enumerate(casos, 1):
            lineas.append(
                f"PRECEDENTE #{i} — Código: {c['codigo_glosa']} | EPS: {c['eps']}\n"
                f"Extracto: {c['extracto_dictamen']}\n{'─' * 60}")
        return "\n".join(lineas)
