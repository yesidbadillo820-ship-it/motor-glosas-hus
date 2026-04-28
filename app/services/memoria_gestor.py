"""Memoria del gestor — la IA aprende el estilo de cada auditor.

Analiza el histórico de refinamientos (DictamenVersionRecord donde
accion=REFINAR) por gestor, extrae patrones recurrentes y los inyecta
como hint al prompt del LLM cuando el mismo gestor analiza una glosa
similar (mismo código_glosa o misma EPS).

Ejemplo: si Yesid suele refinar glosas TA0201 contra FAMISANAR pidiendo
"agrega Sentencia T-760/2008 y baja el tono a conciliador", la próxima
vez que Yesid analice una TA0201 contra FAMISANAR el sistema:
  • Sugiere preview "💭 Tu estilo: sueles agregar T-760 + tono conciliador".
  • Inyecta al system prompt: "PATRÓN DEL GESTOR: en glosas similares
    suele agregar [...]; aplícalo si encaja con el caso."

No reemplaza el dictamen base; lo afina al gusto del gestor sin que
tenga que pedirlo cada vez.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Patrones legales/estilísticos comunes que detectamos en los mensajes
# de refinamiento para clasificarlos. Cada patrón → un "hint" canónico
# que se inyecta al prompt en lenguaje claro.
_PATRONES = (
    # (regex case-insensitive, hint canónico, etiqueta corta)
    (r"\bT-?760(/?2008)?\b|sentencia\s+t-?760", "Cita Sentencia T-760/2008 cuando aplique al PBS y obligaciones EPS.", "T-760"),
    (r"\bt-?1025\b", "Cita Sentencia T-1025/2002 (urgencias sin autorización previa).", "T-1025"),
    (r"\bart[íi]?culo\s+177\b|art\.?\s*177\b", "Cita Art. 177 Ley 100/1993 (deber EPS de pagar lo facturado).", "Art. 177"),
    (r"\bart[íi]?culo\s+871\b|art\.?\s*871\b", "Cita Art. 871 Código de Comercio (buena fe contractual).", "Art. 871"),
    (r"\bart[íi]?culo\s+1602\b|art\.?\s*1602\b", "Cita Art. 1602 Código Civil (contrato como ley entre partes).", "Art. 1602"),
    (r"\b(circular|res\.?)\s*047\b", "Cita Circular Externa 047/2025 MinSalud (Manual SOAT 2026 indexado a UVB).", "Circular 047"),
    (r"\bres\.?\s*2284\b|2284\s*/?\s*2023", "Cita Res. 2284/2023 (Manual Único de Glosas).", "Res. 2284"),
    (r"\bres\.?\s*1995\b|1995\s*/?\s*1999", "Cita Res. 1995/1999 (historia clínica como plena prueba).", "Res. 1995"),
    (r"\bres\.?\s*2641\b|2641\s*/?\s*2025", "Cita Res. 2641/2025 MinSalud (homologación CUPS).", "Res. 2641"),
    (r"baj[áa]?(r)?\s+(el\s+)?tono|m[áa]s\s+conciliador|ton[oa]\s+conciliador", "Usa tono conciliador (sin verbos imperativos).", "tono conciliador"),
    (r"sub[ií]r?\s+(el\s+)?tono|m[áa]s\s+firme|ton[oa]\s+firme", "Usa tono firme con verbos enfáticos.", "tono firme"),
    (r"acort(a|ar|á)|m[áa]s\s+corto|reduc[ií]r?", "Mantén el dictamen corto y directo.", "corto"),
    (r"detall|m[áa]s\s+(largo|completo|extenso)|amplia[rd]?", "Amplía el detalle técnico y normativo.", "detallado"),
    (r"silenci[oa]\s+(administrativo|positivo|favorable)", "Menciona el silencio favorable al prestador (Art. 57 Ley 1438/2011).", "silencio favorable"),
    (r"supersalud|sns|art[íi]?culo\s+126", "Menciona escalamiento a SuperSalud (Art. 126 Ley 1438/2011).", "SuperSalud"),
    (r"conciliaci[óo]n|art[íi]?culo\s+20\s+dec(reto)?\s*4747", "Menciona la mesa de conciliación (Art. 20 Decreto 4747/2007).", "conciliación"),
)


def _clasificar_mensaje(mensaje: str) -> list[str]:
    """Devuelve etiquetas del catálogo que matchean el mensaje del gestor."""
    if not mensaje:
        return []
    txt = mensaje.lower()
    return [etiqueta for (rex, _hint, etiqueta) in _PATRONES if re.search(rex, txt)]


def _hint_de_etiqueta(etiqueta: str) -> str:
    for (_rex, hint, etq) in _PATRONES:
        if etq == etiqueta:
            return hint
    return ""


def patron_gestor(
    db,
    autor_email: str,
    codigo_glosa: str = "",
    eps: str = "",
    limite_meses: int = 6,
    min_repeticiones: int = 2,
) -> dict:
    """Analiza refinamientos del gestor y devuelve sus patrones recurrentes.

    Si pasas codigo_glosa o eps, filtra el contexto al subgrupo similar.
    Solo devuelve patrones con ≥ min_repeticiones para evitar ruido.

    Retorna:
      {
        "autor": str,
        "n_refinamientos": int,
        "patrones_globales": [{"etiqueta": str, "hint": str, "veces": int}, ...],
        "patrones_contexto": [...],   # filtrados por codigo_glosa/eps
        "hint_para_prompt": str,       # texto plano listo para inyectar
      }
    """
    if not autor_email:
        return {"autor": "", "n_refinamientos": 0, "patrones_globales": [],
                "patrones_contexto": [], "hint_para_prompt": ""}

    from datetime import datetime, timedelta, timezone
    from app.models.db import DictamenVersionRecord, GlosaRecord
    desde = datetime.now(timezone.utc) - timedelta(days=30 * limite_meses)

    # Cargar refinamientos del gestor en el período
    q = (
        db.query(DictamenVersionRecord, GlosaRecord)
        .join(GlosaRecord, DictamenVersionRecord.glosa_id == GlosaRecord.id)
        .filter(DictamenVersionRecord.autor_email == autor_email)
        .filter(DictamenVersionRecord.accion == "REFINAR")
        .filter(DictamenVersionRecord.creado_en >= desde)
        .order_by(DictamenVersionRecord.creado_en.desc())
        .limit(500)
    )
    rows = q.all()
    n_total = len(rows)
    if n_total == 0:
        return {"autor": autor_email, "n_refinamientos": 0,
                "patrones_globales": [], "patrones_contexto": [],
                "hint_para_prompt": ""}

    # Contar patrones globales y por contexto
    from collections import Counter
    c_global: Counter = Counter()
    c_ctx: Counter = Counter()
    cod_norm = (codigo_glosa or "").upper().strip()
    eps_norm = (eps or "").upper().strip()
    for ver, g in rows:
        etiquetas = _clasificar_mensaje(ver.mensaje_refinar or "")
        for e in etiquetas:
            c_global[e] += 1
        # Match contextual: mismo código_glosa exacto, mismo prefijo
        # (ej. TA0201 ≈ TA*) o misma EPS (substring laxo).
        g_cod = (g.codigo_glosa or "").upper().strip()
        g_eps = (g.eps or "").upper().strip()
        match_ctx = False
        if cod_norm and g_cod:
            if cod_norm == g_cod or g_cod.startswith(cod_norm[:4]):
                match_ctx = True
        if not match_ctx and eps_norm and g_eps:
            if eps_norm in g_eps or g_eps in eps_norm:
                match_ctx = True
        if match_ctx:
            for e in etiquetas:
                c_ctx[e] += 1

    def _to_list(counter: Counter) -> list[dict]:
        return [
            {"etiqueta": e, "hint": _hint_de_etiqueta(e), "veces": v}
            for e, v in counter.most_common(10) if v >= min_repeticiones
        ]

    glob = _to_list(c_global)
    ctx = _to_list(c_ctx)
    # Hint para inyectar al prompt: priorizar contexto, luego global
    hint_lista: list[str] = []
    vistas: set[str] = set()
    for src in (ctx, glob):
        for it in src:
            if it["etiqueta"] in vistas:
                continue
            vistas.add(it["etiqueta"])
            hint_lista.append(f"• {it['hint']}")
            if len(hint_lista) >= 4:
                break
    hint_prompt = ""
    if hint_lista:
        hint_prompt = (
            "\n[ESTILO DEL GESTOR — patrones de refinamiento aprendidos]\n"
            "Este auditor suele afinar dictámenes así. Aplícalos si encajan "
            "con el caso (no fuerces si no aplica):\n"
            + "\n".join(hint_lista) + "\n"
        )

    return {
        "autor": autor_email,
        "n_refinamientos": n_total,
        "patrones_globales": glob,
        "patrones_contexto": ctx,
        "hint_para_prompt": hint_prompt,
    }
