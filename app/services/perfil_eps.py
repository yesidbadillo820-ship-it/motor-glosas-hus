"""
perfil_eps.py — Perfil de estilo argumental por entidad pagadora
===================================================================
Cada EPS tiene patrones característicos de auditoría: qué citan,
qué argumentos funcionan mejor, qué nivel de formalismo esperan.
Este módulo inyecta perfil específico al prompt IA para adaptar
el tono y el enfoque argumental.

Uso:
    from app.services.perfil_eps import perfil_para_eps
    perfil = perfil_para_eps("NUEVA EPS")
"""
from __future__ import annotations


# Perfiles por EPS/pagador — observaciones institucionales del área de
# cartera HUS sobre qué funciona mejor con cada entidad.
PERFILES_EPS: dict[str, dict] = {
    "NUEVA EPS": {
        "estilo": "formal-normativo",
        "caracteristicas": (
            "Auditoría enfocada en revisión normativa (Res. 2284/2023). "
            "Responden bien a argumentos con cita textual de la norma y "
            "respaldo de historia clínica. Sensibles a argumentos sobre "
            "autonomía médica cuando hay soporte clínico documentado."
        ),
        "tactica_recomendada": (
            "Cita textual de artículos + referencia explícita a Res. 2284/2023 "
            "para desvirtuar la causal de glosa + anclaje en historia clínica."
        ),
        "evitar": (
            "Evitar tono confrontacional en respuesta inicial — ratifican "
            "cuando perciben hostilidad. Preferir 'se sustenta técnicamente' "
            "sobre 'la EPS se equivoca'."
        ),
        "cierre_preferido": "invitación a conciliación técnica",
    },

    "COOSALUD": {
        "estilo": "administrativo",
        "caracteristicas": (
            "Auditoría con alto volumen — revisan plantillas rápido. "
            "Responden bien a argumentos concretos con cifras exactas y "
            "cálculos tarifarios visibles. Aprecian estructura clara."
        ),
        "tactica_recomendada": (
            "Estructura muy clara (encabezados implícitos), cifras exactas, "
            "referencia directa al contrato vigente y tarifario pactado."
        ),
        "evitar": "Argumentación muy extensa sin cifras concretas.",
        "cierre_preferido": "solicitud directa de reconocimiento con monto específico",
    },

    "COMPENSAR": {
        "estilo": "técnico-clínico",
        "caracteristicas": (
            "Auditoría con fuerte componente clínico. Piden justificación "
            "médica detallada. Responden bien a citación de historia clínica "
            "con datos específicos."
        ),
        "tactica_recomendada": (
            "Cita de historia clínica con folios, médico tratante, diagnóstico "
            "CIE-10 y procedimiento CUPS específico."
        ),
        "evitar": "Argumentos exclusivamente contractuales sin soporte clínico.",
        "cierre_preferido": "invitación a mesa de auditoría médica conjunta",
    },

    "DISPENSARIO MEDICO": {
        "estilo": "institucional-militar",
        "caracteristicas": (
            "Entidad del Subsistema de Salud FF.MM. Auditoría rigurosa con "
            "base contractual. El Dec. 1795/2000 y Acuerdo 002/2001 son "
            "pilares argumentales. No aplica T-760/2008."
        ),
        "tactica_recomendada": (
            "Referencia explícita al contrato interadministrativo 440-DIGSA/"
            "DMBUG-2025, Dec. 1795/2000, Acuerdo 002/2001 FF.MM. Tono formal "
            "institucional entre entidades estatales."
        ),
        "evitar": "Citar jurisprudencia de EPS (T-760/2008) — no aplica.",
        "cierre_preferido": "solicitud de conciliación interadministrativa",
    },

    "POLICIA NACIONAL": {
        "estilo": "institucional-militar",
        "caracteristicas": (
            "Subsistema de Salud Policía Nacional. Similar a FF.MM. pero con "
            "particularidades: UVB y Resoluciones específicas (00011/2025)."
        ),
        "tactica_recomendada": (
            "Referencia al contrato 068-5-200004-26, Res. 00011/2025, Ley "
            "352/1997. Tono formal institucional."
        ),
        "evitar": "Confundir con normativa de EPS regulares.",
        "cierre_preferido": "solicitud conciliación interadministrativa",
    },

    "PPL": {
        "estilo": "régimen-especial",
        "caracteristicas": (
            "Población Privada de Libertad. Fondo administrado por "
            "Fiduprevisora. Cobertura integral por Ley 1709/2014 + "
            "Res. 5159/2015."
        ),
        "tactica_recomendada": (
            "Usar 'ENTIDAD PAGADORA' o 'FONDO' en vez de 'EPS'. Citar "
            "Ley 1709/2014 y Res. 5159/2015."
        ),
        "evitar": "Decir 'EPS' o citar T-760/2008.",
        "cierre_preferido": "invitación a conciliación con el Fondo",
    },

    "FOMAG": {
        "estilo": "régimen-especial",
        "caracteristicas": (
            "Fondo Nacional de Prestaciones Sociales del Magisterio "
            "administrado por Fiduprevisora. Docentes oficiales."
        ),
        "tactica_recomendada": (
            "Citar Ley 91/1989 y Dec. 3752/2003. Referir al Patrimonio "
            "Autónomo FOMAG."
        ),
        "evitar": "Normativa de EPS regulares, tono confrontativo.",
        "cierre_preferido": "conciliación con el Patrimonio Autónomo",
    },

    "SALUD TOTAL": {
        "estilo": "administrativo-automatizado",
        "caracteristicas": (
            "Procesamiento automatizado de glosas (TXT pipe-separated). "
            "Observación IPS limitada a 500 caracteres. Revisión en volumen."
        ),
        "tactica_recomendada": (
            "Respuesta MUY concisa (≤500 chars), directa, cita 2-3 normas "
            "clave sin extenderse. Usar flujo Salud Total dedicado."
        ),
        "evitar": "Respuestas extensas, exceden límite y pueden ser rechazadas.",
        "cierre_preferido": "reconocimiento íntegro sin extenderse",
    },

    "SANITAS": {
        "estilo": "formal-regulatorio",
        "caracteristicas": (
            "Auditoría muy estricta con base normativa. Frecuentemente "
            "ratifican si no encuentran argumentación sólida."
        ),
        "tactica_recomendada": (
            "Múltiples normas citadas con texto literal, jurisprudencia "
            "aplicable, estructura impecable."
        ),
        "evitar": "Argumentos débiles o genéricos — suelen ratificar.",
        "cierre_preferido": "invitación formal a conciliación + reserva de derechos",
    },
}


def perfil_para_eps(eps: str) -> dict | None:
    """Retorna el perfil de una EPS/pagador, o None si no hay."""
    if not eps:
        return None
    eps_up = eps.upper().strip()
    for clave, perfil in PERFILES_EPS.items():
        if clave in eps_up:
            return {"nombre": clave, **perfil}
    return None


def bloque_perfil_para_prompt(eps: str) -> str:
    """Retorna bloque formateado para inyectar al user prompt de la IA."""
    p = perfil_para_eps(eps)
    if not p:
        return ""
    return (
        f"\n[PERFIL DE ESTILO DE LA ENTIDAD PAGADORA — {p['nombre']}]\n"
        f"  • Estilo: {p['estilo']}\n"
        f"  • Características: {p['caracteristicas']}\n"
        f"  • Táctica recomendada: {p['tactica_recomendada']}\n"
        f"  • EVITAR: {p['evitar']}\n"
        f"  • Cierre preferido: {p['cierre_preferido']}\n"
        f"⚠ Adapta la respuesta al estilo de auditoría de esta entidad.\n"
    )
