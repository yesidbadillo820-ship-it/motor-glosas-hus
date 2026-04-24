"""Detector central de casos con texto fijo (Ronda 21).

Unifica la lógica de clasificación de RATIFICADA y EXTEMPORÁNEA que hoy
vive duplicada en recepcion_service.py (al importar Excel) y en
glosa_service.py (al analizar manualmente).

Este módulo expone UNA función autoritativa:

  clasificar_texto_fijo(glosa) → dict | None

Que implementa la **regla de prioridad dura** pedida por el coordinador:

  1º RATIFICADA gana siempre. Si la glosa cumple los criterios de
     ratificación (estado='RATIFICADA', workflow_state='RATIFICADA',
     la palabra 'RATIFICADA' en radicado_info/referencia/nota_workflow),
     devolvemos el texto de ratificada y NUNCA mencionamos extemporaneidad
     aunque también aplicara.

  2º EXTEMPORÁNEA aplica solo si NO es ratificada y:
     - dias_radicacion_dgh > 20 (días hábiles), O bien
     - el cálculo _dias_habiles(fecha_rad, fecha_dgh) > 20 si el campo
       precalculado no está.
     Respeta el flag 'NO APLICAR EXTEMPORANEIDAD' de observacion_tecnico.

  3º En cualquier otro caso devuelve None → la glosa sigue el flujo IA
     normal.

Uso desde otros módulos:

  from app.services.texto_fijo_detector import clasificar_texto_fijo

  clase = clasificar_texto_fijo(glosa_record)
  if clase:
      glosa_record.dictamen = clase["dictamen_html"]
      glosa_record.modelo_ia = f"pre-analisis/texto_fijo/{clase['tipo']}"
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


RATIFICADA_KEYWORDS = ("RATIFICADA", "RATIFICADO", "RATIF.")
DIAS_HABILES_LIMITE = 20


def _es_ratificada(glosa) -> bool:
    """True si la glosa está marcada como ratificada por cualquier vía."""
    # Estado / workflow_state explícitos
    est = (getattr(glosa, "estado", "") or "").upper()
    ws = (getattr(glosa, "workflow_state", "") or "").upper()
    if "RATIF" in est or "RATIF" in ws:
        return True
    # Campos de texto que podrían contenerlo
    campos = (
        getattr(glosa, "radicado_info", "") or "",
        getattr(glosa, "referencia", "") or "",
        getattr(glosa, "nota_workflow", "") or "",
        getattr(glosa, "tipo_glosa_excel", "") or "",
    )
    for c in campos:
        txt = str(c).upper()
        for kw in RATIFICADA_KEYWORDS:
            if kw in txt:
                return True
    return False


def _no_aplicar_extemporaneidad(glosa) -> bool:
    """Respeta el flag del técnico si pidió saltar extemporaneidad."""
    obs = (getattr(glosa, "observacion_tecnico", "") or "").upper()
    if not obs:
        return False
    return (
        "NO APLICAR EXTEMPORANEIDAD" in obs
        or "NO APLICA EXTEMPORANEIDAD" in obs
        or "NO APLICAR EXTEMPORANEA" in obs
    )


def _dias_habiles(desde: datetime, hasta: datetime) -> int:
    """Días hábiles entre dos fechas (lun-vie, sin festivos)."""
    if not desde or not hasta or hasta <= desde:
        return 0
    dias = 0
    cur = desde.date() if hasattr(desde, "date") else desde
    fin = hasta.date() if hasattr(hasta, "date") else hasta
    from datetime import timedelta as _td
    while cur < fin:
        cur = cur + _td(days=1)
        if cur.weekday() < 5:  # 0-4 = lun-vie
            dias += 1
    return dias


def _dias_extemporaneidad(glosa) -> int:
    """Devuelve los días hábiles transcurridos entre radicación y DGH.

    Prefiere el campo precalculado `dias_radicacion_dgh`. Si no está,
    calcula a partir de fecha_radicacion_factura + fecha_documento_dgh.
    """
    d = getattr(glosa, "dias_radicacion_dgh", None)
    if d is not None and int(d or 0) > 0:
        return int(d)
    fr = getattr(glosa, "fecha_radicacion_factura", None)
    fd = getattr(glosa, "fecha_documento_dgh", None)
    if fr and fd:
        return _dias_habiles(fr, fd)
    return 0


def _es_extemporanea(glosa) -> tuple[bool, int]:
    """Regresa (es_extemporanea, dias). No aplica si el técnico pidió salto."""
    if _no_aplicar_extemporaneidad(glosa):
        return False, 0
    dias = _dias_extemporaneidad(glosa)
    return dias > DIAS_HABILES_LIMITE, dias


# ─── Formateadores de dictamen ─────────────────────────────────────────────

def _dictamen_html_ratificada(eps: str, factura: str, info: str = "") -> str:
    """HTML envuelto del TEXTO_RATIFICADA de glosa_service (import-local
    para evitar import circular en tiempo de módulo)."""
    from app.services.glosa_service import TEXTO_RATIFICADA
    eps_s = (eps or "—").strip()
    fac_s = (factura or "—").strip()
    info_s = (info or "").strip() or "—"
    return f"""
    <div style="background:#ede9fe;border-left:4px solid #7c3aed;padding:20px;margin:15px 0;border-radius:8px;">
        <h4 style="color:#5b21b6;margin:0 0 10px 0;">RESPUESTA A GLOSA RATIFICADA</h4>
        <p style="font-size:12px;color:#6d28d9;margin:0 0 10px 0;">
            <b>EPS:</b> {eps_s} | <b>Factura:</b> {fac_s} | <b>Observación:</b> {info_s}
        </p>
        <p style="font-size:13px;line-height:1.8;color:#4c1d95;white-space:pre-wrap;">{TEXTO_RATIFICADA}</p>
    </div>
    """.strip()


def _dictamen_html_extemporanea(eps: str, factura: str, dias: int) -> str:
    """HTML envuelto del generar_texto_extemporanea(dias)."""
    from app.services.glosa_service import generar_texto_extemporanea
    eps_s = (eps or "—").strip()
    fac_s = (factura or "—").strip()
    texto = generar_texto_extemporanea(dias)
    return f"""
    <div style="background:#fef3c7;border-left:4px solid #d97706;padding:20px;margin:15px 0;border-radius:8px;">
        <h4 style="color:#92400e;margin:0 0 10px 0;">GLOSA EXTEMPORÁNEA — {dias} DÍAS HÁBILES</h4>
        <p style="font-size:12px;color:#b45309;margin:0 0 10px 0;">
            <b>EPS:</b> {eps_s} | <b>Factura:</b> {fac_s} | <b>Límite legal:</b> {DIAS_HABILES_LIMITE} días
        </p>
        <p style="font-size:13px;line-height:1.8;color:#78350f;white-space:pre-wrap;">{texto}</p>
    </div>
    """.strip()


# ─── API principal ─────────────────────────────────────────────────────────

def clasificar_texto_fijo(glosa) -> Optional[dict]:
    """Aplica la regla de prioridad y devuelve el dictamen fijo si aplica.

    Regla dura:
      1. RATIFICADA gana siempre — NUNCA mencionamos extemporaneidad.
      2. EXTEMPORÁNEA solo si NO es ratificada.
      3. None si nada aplica (sigue el flujo IA).

    Retorna:
      {
        "tipo": "RATIFICADA" | "EXTEMPORANEA",
        "dictamen_html": str,
        "estado_sugerido": "RATIFICADA" | "EXTEMPORANEA",
        "modelo_ia": "pre-analisis/texto_fijo/RATIFICADA" | ...,
        "razon": str,
        "dias_extemporaneidad": int | None,
      }
    """
    if glosa is None:
        return None

    eps = getattr(glosa, "eps", "") or ""
    factura = getattr(glosa, "factura", "") or ""

    # 1) RATIFICADA — prioridad absoluta
    if _es_ratificada(glosa):
        info = (
            getattr(glosa, "radicado_info", "")
            or getattr(glosa, "referencia", "")
            or getattr(glosa, "nota_workflow", "")
            or ""
        )
        return {
            "tipo": "RATIFICADA",
            "dictamen_html": _dictamen_html_ratificada(eps, factura, str(info)),
            "estado_sugerido": "RATIFICADA",
            "modelo_ia": "pre-analisis/texto_fijo/RATIFICADA",
            "razon": "Glosa marcada como RATIFICADA — prioridad sobre extemporaneidad.",
            "dias_extemporaneidad": None,
        }

    # 2) EXTEMPORÁNEA — solo si NO es ratificada
    es_ext, dias = _es_extemporanea(glosa)
    if es_ext:
        return {
            "tipo": "EXTEMPORANEA",
            "dictamen_html": _dictamen_html_extemporanea(eps, factura, dias),
            "estado_sugerido": "EXTEMPORANEA",
            "modelo_ia": "pre-analisis/texto_fijo/EXTEMPORANEA",
            "razon": f"Glosa radicada {dias} días hábiles después de DGH (límite {DIAS_HABILES_LIMITE}).",
            "dias_extemporaneidad": dias,
        }

    return None


def aplicar_texto_fijo_si_corresponde(glosa) -> Optional[dict]:
    """Mutador: si la glosa califica, asigna dictamen + modelo_ia + estado y
    retorna la clasificación aplicada. Si no, retorna None sin tocar nada.

    Es idempotente: si ya hay un dictamen no vacío, NO lo sobreescribe (salvo
    que el marcador modelo_ia indique que viene de un texto fijo anterior y
    ahora el caso cambió — p. ej. antes era EXTEMPORANEA y la EPS ratificó,
    ahora debe volverse RATIFICADA).
    """
    clase = clasificar_texto_fijo(glosa)
    if clase is None:
        return None

    dictamen_actual = (getattr(glosa, "dictamen", "") or "").strip()
    modelo_actual = (getattr(glosa, "modelo_ia", "") or "").lower()

    # Si ya tiene dictamen y NO es un texto fijo previo, respetamos lo existente.
    if dictamen_actual and "texto_fijo" not in modelo_actual:
        return None

    # Si el texto fijo previo era del mismo tipo, idempotente — no reescribir.
    if (
        dictamen_actual
        and "texto_fijo" in modelo_actual
        and clase["tipo"].lower() in modelo_actual
    ):
        return None

    # Aplicar
    try:
        from datetime import datetime, timezone as _tz
        glosa.dictamen = clase["dictamen_html"]
        glosa.modelo_ia = clase["modelo_ia"]
        # Ronda 38: grabar también codigo_respuesta para el export DGH.
        # RE9901 = no acepta ratificación; RE9501 = rechaza por extemporaneidad.
        try:
            codigo_resp_existente = (getattr(glosa, "codigo_respuesta", "") or "").strip()
            if not codigo_resp_existente:
                if clase["tipo"] == "RATIFICADA":
                    glosa.codigo_respuesta = "RE9901"
                elif clase["tipo"] == "EXTEMPORANEA":
                    glosa.codigo_respuesta = "RE9501"
        except Exception:
            pass
        # Solo actualizamos estado si está vacío o si es una transición válida
        estado_actual = (getattr(glosa, "estado", "") or "").upper()
        if not estado_actual or estado_actual in ("PENDIENTE", "RADICADA", "EN_REVISION", "BORRADOR"):
            glosa.estado = clase["estado_sugerido"]
        # ⚡ Ronda 21+34 (fix): marcar workflow_state como RESPONDIDA para que
        # salga de la bandeja de pendientes. Las RATIFICADAS y EXTEMPORÁNEAS
        # no necesitan que el auditor haga click en "Responder" — el texto
        # canónico ya está aplicado y es un caso mecánico.
        wf_actual = (getattr(glosa, "workflow_state", "") or "").upper()
        if wf_actual not in ("RESPONDIDA", "CONCILIADA", "LEVANTADA"):
            try:
                glosa.workflow_state = "RESPONDIDA"
            except Exception:
                pass
        # Timestamp de decisión si aún no está
        try:
            if getattr(glosa, "fecha_decision_eps", None) is None:
                glosa.fecha_decision_eps = datetime.now(_tz.utc)
        except Exception:
            pass
        # Nota trazable para auditoría
        try:
            if not (getattr(glosa, "nota_workflow", "") or "").strip():
                glosa.nota_workflow = f"Respondida automáticamente: texto fijo {clase['tipo']}"
        except Exception:
            pass
    except Exception:
        # No bloqueamos flujos — si el objeto no permite asignación, devolvemos
        # la clasificación igual para que el llamador decida.
        pass
    return clase
