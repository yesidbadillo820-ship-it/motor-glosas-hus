"""
ia_tools.py — Definición de herramientas (tool use / function calling)
que Claude puede invocar durante el análisis de una glosa.

En vez de inyectar TODO el contexto en el prompt (cláusulas, tarifas,
precedentes, normas, perfil EPS), se le ofrece a Claude un set de
herramientas para que las llame solo cuando las necesita. Esto:

  - Reduce tokens: solo se trae lo relevante al caso específico
  - Reduce alucinaciones: Claude trabaja con data verificada de BD
  - Mejora consistencia: cada llamada devuelve datos canónicos

Activación: env var TOOL_USE_HABILITADO=1. Si no está, el motor usa el
flujo clásico de prompt monolítico. Esto permite probar tool use en
producción sin riesgo de romper el flujo principal.

Spec Anthropic Tool Use:
  https://docs.anthropic.com/en/docs/build-with-claude/tool-use
"""
import os
import logging
from typing import Optional

logger = logging.getLogger("motor_glosas")


def tool_use_habilitado() -> bool:
    return os.getenv("TOOL_USE_HABILITADO", "0").strip() in ("1", "true", "TRUE", "yes")


# ─── Schemas de herramientas (formato Anthropic) ──────────────────────

TOOLS_DISPONIBLES = [
    {
        "name": "buscar_clausula_contrato",
        "description": (
            "Busca cláusulas literales del contrato vigente firmado entre la "
            "IPS (HUS) y la EPS, filtradas por tema (TA=tarifas, SO=soportes, "
            "AU=autorizaciones, CO=cobertura, FA=facturación, NN=generales). "
            "Las cláusulas son extractos textuales del PDF del contrato — citarlas "
            "literalmente blinda el dictamen porque la EPS firmó ese mismo "
            "documento. Usa esta herramienta SIEMPRE que el caso involucre "
            "una EPS con contrato cargado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eps": {
                    "type": "string",
                    "description": "Nombre de la EPS exacto (ej: 'FAMISANAR EPS', 'NUEVA EPS').",
                },
                "tema": {
                    "type": "string",
                    "enum": ["TA", "SO", "AU", "CO", "FA", "NN"],
                    "description": (
                        "Tema de las cláusulas a recuperar. Debe coincidir con las "
                        "primeras 2 letras del código de glosa (TA0801 → tema=TA)."
                    ),
                },
            },
            "required": ["eps", "tema"],
        },
    },
    {
        "name": "buscar_glosa_similar_levantada",
        "description": (
            "Busca glosas históricas LEVANTADAS (defendidas con éxito) similares "
            "al caso actual. Devuelve los dictámenes que YA funcionaron para "
            "que la nueva respuesta se apoye en argumentos probados. Filtra por "
            "EPS y prefijo de código de glosa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eps": {
                    "type": "string",
                    "description": "EPS de la glosa actual.",
                },
                "codigo_glosa": {
                    "type": "string",
                    "description": "Código completo (ej: 'TA0801'). Se usa el prefijo de 2 letras para matching.",
                },
                "limite": {
                    "type": "integer",
                    "description": "Máximo de precedentes a devolver. Default 3.",
                    "default": 3,
                },
            },
            "required": ["eps", "codigo_glosa"],
        },
    },
    {
        "name": "lookup_tarifa_pactada",
        "description": (
            "Consulta la tarifa pactada específica para un código CUPS según "
            "el contrato con esta EPS. Devuelve valor pactado, modalidad "
            "(SOAT_PORCENTAJE o VALOR_FIJO) y vigencia. Úsala cuando la glosa "
            "objete tarifas (códigos TA*) y necesites citar el valor exacto "
            "pactado vs el facturado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "eps": {"type": "string"},
                "codigo_cups": {"type": "string", "description": "Ej: '890201', '992001'."},
            },
            "required": ["eps", "codigo_cups"],
        },
    },
    {
        "name": "lookup_norma",
        "description": (
            "Recupera el texto literal de una norma del corpus normativo "
            "colombiano (Leyes, Decretos, Resoluciones, Sentencias). Úsala "
            "ANTES de citar una norma en el dictamen para asegurarte que "
            "exista y poder copiar el fragmento exacto entre comillas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["resolucion", "decreto", "ley", "sentencia"],
                },
                "numero": {"type": "string"},
                "anio": {"type": "string", "description": "4 dígitos (ej: '2023')."},
            },
            "required": ["tipo", "numero", "anio"],
        },
    },
]


# ─── Implementación de cada herramienta ──────────────────────────────

def execute_tool(name: str, arguments: dict) -> str:
    """Ejecuta una llamada a herramienta y devuelve el resultado como
    string (JSON o texto). Devuelve un mensaje de error legible si la
    herramienta falla — Claude maneja errores de tool si vienen como
    texto en el resultado."""
    try:
        if name == "buscar_clausula_contrato":
            return _exec_buscar_clausula_contrato(arguments)
        if name == "buscar_glosa_similar_levantada":
            return _exec_buscar_glosa_similar(arguments)
        if name == "lookup_tarifa_pactada":
            return _exec_lookup_tarifa(arguments)
        if name == "lookup_norma":
            return _exec_lookup_norma(arguments)
        return f"ERROR: herramienta desconocida '{name}'"
    except Exception as e:
        logger.warning(f"[IA-TOOLS] Error ejecutando '{name}': {e}")
        return f"ERROR ejecutando {name}: {e}"


def _exec_buscar_clausula_contrato(args: dict) -> str:
    import json
    eps = (args.get("eps") or "").strip().upper()
    tema = (args.get("tema") or "").strip().upper()
    if not eps or not tema:
        return json.dumps({"clausulas": [], "error": "Faltan eps o tema"})
    from app.database import SessionLocal
    from app.models.db import ClausulaContrato
    db = SessionLocal()
    try:
        rows = (
            db.query(ClausulaContrato)
            .filter(ClausulaContrato.eps == eps, ClausulaContrato.tema.in_([tema, "NN"]))
            .order_by(ClausulaContrato.id)
            .limit(5)
            .all()
        )
        if not rows:
            return json.dumps({
                "clausulas": [],
                "info": f"No hay cláusulas extraídas del contrato vigente para EPS={eps} tema={tema}. Si necesitás citar el contrato, indicá al gestor que suba el PDF en Tarifas → Subir PDF del contrato.",
            })
        return json.dumps({
            "clausulas": [
                {
                    "numero": c.numero_clausula,
                    "tema": c.tema,
                    "titulo": c.titulo,
                    "texto_literal": c.texto_literal,
                }
                for c in rows
            ]
        }, ensure_ascii=False)
    finally:
        db.close()


def _exec_buscar_glosa_similar(args: dict) -> str:
    import json
    eps = (args.get("eps") or "").strip().upper()
    codigo = (args.get("codigo_glosa") or "").strip().upper()
    limite = int(args.get("limite") or 3)
    if not eps or not codigo:
        return json.dumps({"precedentes": [], "error": "Faltan eps o codigo_glosa"})
    prefijo = codigo[:2]
    from app.database import SessionLocal
    from app.models.db import GlosaRecord
    db = SessionLocal()
    try:
        rows = (
            db.query(GlosaRecord)
            .filter(
                GlosaRecord.eps == eps,
                GlosaRecord.estado == "LEVANTADA",
                GlosaRecord.codigo_glosa.like(f"{prefijo}%"),
                GlosaRecord.dictamen.isnot(None),
            )
            .order_by(GlosaRecord.creado_en.desc())
            .limit(limite)
            .all()
        )
        if not rows:
            return json.dumps({
                "precedentes": [],
                "info": f"No hay glosas levantadas previas con EPS={eps} prefijo={prefijo}. Construí el dictamen sin precedente interno (solo normativa + cláusulas).",
            })
        import re as _re
        return json.dumps({
            "precedentes": [
                {
                    "codigo_glosa": g.codigo_glosa,
                    "valor_recuperado": float(g.valor_recuperado or 0),
                    "extracto_dictamen": _re.sub(r"<[^>]+>", " ", (g.dictamen or "")[:500]),
                }
                for g in rows
            ]
        }, ensure_ascii=False)
    finally:
        db.close()


def _exec_lookup_tarifa(args: dict) -> str:
    import json
    eps = (args.get("eps") or "").strip().upper()
    cups = (args.get("codigo_cups") or "").strip()
    if not eps or not cups:
        return json.dumps({"tarifa": None, "error": "Faltan eps o codigo_cups"})
    from app.database import SessionLocal
    try:
        from app.models.db import TarifaContratada
    except Exception:
        return json.dumps({"tarifa": None, "error": "Modelo TarifaContratada no disponible"})
    db = SessionLocal()
    try:
        row = (
            db.query(TarifaContratada)
            .filter(TarifaContratada.eps == eps, TarifaContratada.codigo_cups == cups)
            .first()
        )
        if not row:
            return json.dumps({
                "tarifa": None,
                "info": f"No hay tarifa pactada cargada para EPS={eps} CUPS={cups}. Verifica el manual tarifario del contrato.",
            })
        return json.dumps({
            "tarifa": {
                "eps": row.eps,
                "codigo_cups": row.codigo_cups,
                "descripcion": getattr(row, "descripcion", None),
                "valor_pactado": float(getattr(row, "valor_pactado", 0) or 0),
                "tipo_tarifa": getattr(row, "tipo_tarifa", None),
                "factor_ajuste": getattr(row, "factor_ajuste", None),
                "modalidad": getattr(row, "modalidad", None),
            }
        }, ensure_ascii=False)
    finally:
        db.close()


def _exec_lookup_norma(args: dict) -> str:
    import json
    tipo = (args.get("tipo") or "").strip().lower()
    numero = (args.get("numero") or "").strip()
    anio = (args.get("anio") or "").strip()
    if not (tipo and numero and anio):
        return json.dumps({"norma": None, "error": "Faltan tipo, numero o anio"})
    try:
        from app.services.normativa_completa import _TODAS_LAS_NORMAS as normas
    except Exception:
        return json.dumps({"norma": None, "error": "Corpus normativo no disponible"})

    from app.services.citation_verifier import _buscar_clave_norma
    clave = _buscar_clave_norma(tipo[:3], numero, anio, normas)
    if not clave:
        return json.dumps({
            "norma": None,
            "info": f"No se encontró {tipo.title()} {numero} de {anio} en el corpus. NO la cites en el dictamen.",
        })
    n = normas[clave]

    # Knowledge graph: incluir relaciones y sustentos heredados
    relaciones = []
    sustentos = []
    try:
        from app.services.normativa_grafo import obtener_relaciones, normas_que_sustentan
        # La clave del grafo usa formato "ley_100_1993" / "res_2284_2023";
        # construimos la clave canónica desde tipo + numero + anio
        tipo_short = {"resolucion": "res", "decreto": "decreto", "ley": "ley", "sentencia": "sentencia"}.get(
            tipo, tipo[:3]
        )
        clave_grafo = f"{tipo_short}_{numero.lstrip('0') or numero}_{anio}"
        relaciones = obtener_relaciones(clave_grafo)
        sustentos = normas_que_sustentan(clave_grafo, max_profundidad=2)
    except Exception:
        pass

    out = {
        "norma": {
            "nombre": n.get("nombre"),
            "texto": (n.get("texto") or "")[:1500],
            "ratio_literal": (n.get("ratio_literal") or "")[:600],
            "extracto_judicial": (n.get("extracto_judicial") or "")[:600],
            "articulos": {
                str(k): {"texto": (v.get("texto") or "")[:800]}
                for k, v in list((n.get("articulos") or {}).items())[:5]
            },
        }
    }
    if relaciones:
        out["relaciones_grafo"] = relaciones[:8]
    if sustentos:
        out["sustentos_heredados"] = sustentos[:5]
    return json.dumps(out, ensure_ascii=False)
