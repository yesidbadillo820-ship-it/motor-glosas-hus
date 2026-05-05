import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.schemas import ContratoInput
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.audit_repository import AuditRepository
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord, ContratoRecord, ClausulaContrato
from app.core.rate_limit import limiter

logger = logging.getLogger("motor_glosas")

router = APIRouter(prefix="/contratos", tags=["contratos"])

# Carpeta donde se guardan los PDFs de contratos. En Fly se monta el
# volumen persistente en /data; en dev cae a /tmp/contratos.
CONTRATOS_PDF_ROOT = os.getenv("CONTRATOS_PDF_ROOT") or os.path.join(
    os.getenv("SOPORTES_ROOT", "/data"), "contratos"
)

@router.get("/", response_model=List[dict])
def listar_contratos(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Retorna todos los contratos registrados en el HUS."""
    repo = ContratoRepository(db)
    contratos = repo.listar()
    return [{"eps": c.eps, "detalles": c.detalles} for c in contratos]

@router.post("/upsert")
def crear_o_actualizar_contrato(
    data: ContratoInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea un nuevo contrato o actualiza uno existente si la EPS ya existe."""
    repo = ContratoRepository(db)
    return repo.upsert(data)

@router.get("/eps-sin-contrato")
def eps_sin_contrato(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R132 P2: EPS con glosas pero sin contrato firmado.

    Caso opuesto a /sin-glosas. Detecta:
      - Imports masivos con EPS no esperadas (typo/normalización)
      - Contratos pendientes de cargar al sistema
      - Riesgo regulatorio: prestar servicios sin contrato firmado

    Útil para auditoría regulatoria — la falta de contrato puede
    invalidar el cobro de glosas.

    Devuelve EPS con glosas que NO tienen entrada en ContratoRecord.
    """
    from app.models.db import ContratoRecord, GlosaRecord

    eps_contratadas = {
        c.eps for c in db.query(ContratoRecord).all() if c.eps
    }

    # Agrupar glosas por EPS
    por_eps: dict[str, dict] = {}
    for g in db.query(GlosaRecord).all():
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps in eps_contratadas:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"glosas": 0, "valor_objetado": 0.0}
        por_eps[eps]["glosas"] += 1
        por_eps[eps]["valor_objetado"] += float(g.valor_objetado or 0)

    items = [
        {
            "eps": eps,
            "glosas_acumuladas": v["glosas"],
            "valor_objetado_total": int(v["valor_objetado"]),
        }
        for eps, v in por_eps.items()
    ]
    items.sort(key=lambda x: x["valor_objetado_total"], reverse=True)

    return {
        "total_eps_sin_contrato": len(items),
        "items": items,
    }


@router.get("/exportar.csv")
def exportar_contratos_csv(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R163 P1: export de TODOS los contratos a CSV.

    Útil para auditoría externa, copias de seguridad fuera de
    BD y análisis en Excel/Tableau.

    StreamingResponse — no carga todo en memoria.

    Columnas: eps, detalles.
    """
    import csv
    import io
    from datetime import datetime, timezone

    from fastapi.responses import StreamingResponse

    from app.models.db import ContratoRecord

    contratos = (
        db.query(ContratoRecord)
        .order_by(ContratoRecord.eps.asc())
        .all()
    )

    def _generar():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["eps", "detalles"])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        for c in contratos:
            w.writerow([c.eps or "", (c.detalles or "")[:500]])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    fname = (
        f"contratos-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    )
    return StreamingResponse(
        _generar(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/sin-glosas")
def contratos_sin_glosas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R132 P1: contratos firmados sin actividad de glosas.

    Útil para identificar EPS con contrato pero que aún no han
    enviado glosas:
      - Buenas noticias: la EPS está pagando todo bien
      - Mala noticia: el contrato está inactivo (no hay servicios)
      - Por confirmar: nuevo contrato sin operación aún

    Cruza ContratoRecord con GlosaRecord:
      - ContratoRecord.eps no aparece en GlosaRecord.eps

    Devuelve la lista de EPS con contrato pero sin glosas.
    """
    from app.models.db import ContratoRecord, GlosaRecord

    contratos = db.query(ContratoRecord).all()
    eps_con_glosas = {
        e[0] for e in db.query(GlosaRecord.eps).distinct().all()
        if e[0]
    }

    sin_glosas = []
    for c in contratos:
        if c.eps not in eps_con_glosas:
            sin_glosas.append({
                "eps": c.eps,
                "detalles": c.detalles,
            })

    sin_glosas.sort(key=lambda x: x["eps"])

    return {
        "total_contratos": len(contratos),
        "contratos_con_glosas": len(contratos) - len(sin_glosas),
        "contratos_sin_glosas": len(sin_glosas),
        "items": sin_glosas,
    }


@router.get("/ranking")
def ranking_contratos(
    min_glosas: int = 5,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R100 P2: ranking de contratos por valor recuperado total.

    Útil para reporte ejecutivo:
      "¿De qué EPS hemos sacado más plata este año?"

    Filtra contratos con >= min_glosas históricas (default 5)
    para evitar ruido de EPS con poca data.

    Devuelve por contrato:
      - eps
      - total_glosas
      - valor_recuperado_total
      - tasa_recuperacion_pct
      - ranking_position (1=mejor)

    Ordenado DESC por valor_recuperado_total.
    """
    from app.models.db import GlosaRecord

    glosas = db.query(GlosaRecord).all()

    por_eps: dict[str, dict] = {}
    for g in glosas:
        eps = (g.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {
                "total": 0,
                "valor_objetado": 0.0,
                "valor_recuperado": 0.0,
            }
        b = por_eps[eps]
        b["total"] += 1
        b["valor_objetado"] += float(g.valor_objetado or 0)
        b["valor_recuperado"] += float(g.valor_recuperado or 0)

    items = []
    for eps, b in por_eps.items():
        if b["total"] < min_glosas:
            continue
        tasa = (
            round(100 * b["valor_recuperado"] / b["valor_objetado"], 2)
            if b["valor_objetado"] else 0.0
        )
        items.append({
            "eps": eps,
            "total_glosas": b["total"],
            "valor_objetado_total": int(b["valor_objetado"]),
            "valor_recuperado_total": int(b["valor_recuperado"]),
            "tasa_recuperacion_pct": tasa,
        })

    items.sort(
        key=lambda x: x["valor_recuperado_total"],
        reverse=True,
    )
    for idx, it in enumerate(items, start=1):
        it["ranking_position"] = idx

    return {
        "min_glosas_filtro": int(min_glosas),
        "total_contratos_evaluados": len(items),
        "items": items,
    }


@router.get("/{eps}/perfil-detallado")
def perfil_detallado_eps(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R121 P2: perfil 360º de una EPS — toda la info en single-call.

    Combina:
      - Métricas históricas (volumen, valores, tasas)
      - Top códigos glosa que esta EPS objeta
      - Códigos respuesta más exitosos contra esta EPS
      - Tiempo promedio de decisión
      - Glosas pendientes vs cerradas
      - Última actividad

    Útil al abrir el panel de un contrato sin tener que hacer
    múltiples requests.
    """
    from datetime import timezone

    from app.models.db import GlosaRecord

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .all()
    )

    if not glosas:
        return {
            "eps": eps,
            "sin_historial": True,
            "total_glosas": 0,
        }

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    abiertas = [g for g in glosas if (g.estado or "").upper() not in ESTADOS_CERRADOS]
    cerradas = [g for g in glosas if (g.estado or "").upper() in ESTADOS_CERRADOS]
    levantadas = [g for g in cerradas if (g.estado or "").upper() == "LEVANTADA"]
    decididas = [
        g for g in cerradas
        if (g.estado or "").upper() in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
    ]

    valor_obj = sum(float(g.valor_objetado or 0) for g in glosas)
    valor_rec = sum(float(g.valor_recuperado or 0) for g in glosas)
    valor_pendiente = sum(float(g.valor_objetado or 0) for g in abiertas)

    # Top códigos glosa
    por_codigo: dict[str, int] = {}
    for g in glosas:
        if g.codigo_glosa:
            por_codigo[g.codigo_glosa] = por_codigo.get(g.codigo_glosa, 0) + 1
    top_codigos = sorted(por_codigo.items(), key=lambda x: x[1], reverse=True)[:5]

    # Códigos respuesta exitosos
    por_resp: dict[str, dict] = {}
    for g in cerradas:
        cr = g.codigo_respuesta
        if not cr:
            continue
        if cr not in por_resp:
            por_resp[cr] = {"total": 0, "levantadas": 0}
        por_resp[cr]["total"] += 1
        if (g.estado or "").upper() == "LEVANTADA":
            por_resp[cr]["levantadas"] += 1
    resp_efectivos = []
    for cr, b in por_resp.items():
        tasa = round(100 * b["levantadas"] / b["total"], 2) if b["total"] else 0
        resp_efectivos.append({
            "codigo_respuesta": cr,
            "usado": b["total"],
            "tasa_exito_pct": tasa,
        })
    resp_efectivos.sort(key=lambda x: x["tasa_exito_pct"], reverse=True)

    # Tiempo promedio decisión
    tiempos = []
    for g in cerradas:
        if g.fecha_decision_eps and g.creado_en:
            dec = g.fecha_decision_eps
            cre = g.creado_en
            if dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)
            if cre.tzinfo is None:
                cre = cre.replace(tzinfo=timezone.utc)
            tiempos.append((dec - cre).days)

    # Última glosa creada (señal de actividad)
    ultima = max(
        (g.creado_en for g in glosas if g.creado_en),
        default=None,
    )

    return {
        "eps": eps,
        "sin_historial": False,
        "volumen": {
            "total_glosas": len(glosas),
            "abiertas": len(abiertas),
            "cerradas": len(cerradas),
            "decididas": len(decididas),
            "levantadas": len(levantadas),
        },
        "economico": {
            "valor_objetado_total": int(valor_obj),
            "valor_recuperado_total": int(valor_rec),
            "valor_pendiente": int(valor_pendiente),
            "tasa_recuperacion_pct": (
                round(100 * valor_rec / valor_obj, 2) if valor_obj else 0.0
            ),
        },
        "resoluciones": {
            "tasa_levantamiento_pct": (
                round(100 * len(levantadas) / len(decididas), 2)
                if decididas else 0.0
            ),
            "tiempo_promedio_decision_dias": (
                round(sum(tiempos) / len(tiempos), 2) if tiempos else 0.0
            ),
        },
        "top_5_codigos_objetados": [
            {"codigo": c, "veces": n} for c, n in top_codigos
        ],
        "codigos_respuesta_efectivos": resp_efectivos[:5],
        "ultima_actividad": ultima.isoformat() if ultima else None,
    }


@router.get("/{eps}/glosas-historico")
def historial_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R100 P1: resumen del histórico de glosas para un contrato (EPS).

    Útil para entender la "salud" del contrato con esta EPS:
      - ¿Cuántas glosas en total?
      - ¿Tasa de levantamiento?
      - ¿Valor total objetado vs recuperado?
      - ¿Top 5 códigos de glosa más usados por esta EPS?

    Devuelve métricas agregadas + top códigos.
    """
    from app.models.db import GlosaRecord

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.eps == eps)
        .all()
    )

    total = len(glosas)
    if total == 0:
        return {
            "eps": eps,
            "total_glosas": 0,
            "valor_objetado_total": 0,
            "valor_recuperado_total": 0,
            "tasa_recuperacion_pct": 0.0,
            "tasa_levantamiento_pct": 0.0,
            "top_5_codigos": [],
        }

    valor_obj = sum(float(g.valor_objetado or 0) for g in glosas)
    valor_rec = sum(float(g.valor_recuperado or 0) for g in glosas)

    decididas = [g for g in glosas if (g.estado or "").upper()
                 in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}]
    levantadas = sum(1 for g in decididas
                     if (g.estado or "").upper() == "LEVANTADA")

    # Top 5 códigos
    por_codigo: dict[str, int] = {}
    for g in glosas:
        if g.codigo_glosa:
            por_codigo[g.codigo_glosa] = por_codigo.get(g.codigo_glosa, 0) + 1
    top_5 = sorted(por_codigo.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "eps": eps,
        "total_glosas": total,
        "valor_objetado_total": int(valor_obj),
        "valor_recuperado_total": int(valor_rec),
        "tasa_recuperacion_pct": (
            round(100 * valor_rec / valor_obj, 2)
            if valor_obj else 0.0
        ),
        "tasa_levantamiento_pct": (
            round(100 * levantadas / len(decididas), 2)
            if decididas else 0.0
        ),
        "decididas": len(decididas),
        "pendientes": total - len(decididas),
        "top_5_codigos": [
            {"codigo": c, "veces": n} for c, n in top_5
        ],
    }


@router.delete("/{eps}")
def eliminar_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Elimina el contrato de una EPS específica."""
    repo = ContratoRepository(db)
    exito = repo.eliminar(eps)
    if not exito:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return {"message": f"Contrato con {eps} eliminado correctamente"}


# ─── PDF de contrato + extracción automática de cláusulas ─────────────
# Permite subir el PDF del contrato firmado con cada EPS para que el
# motor cite cláusulas reales al objetar glosas. Sólo se guarda el
# vigente: subir uno nuevo reemplaza el anterior y sus cláusulas.

@router.post("/{eps}/pdf")
@limiter.limit("5/minute")
async def subir_pdf_contrato(
    request: Request,
    eps: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Sube el PDF del contrato vigente para la EPS y extrae cláusulas.

    Flow:
      1. Valida que el contrato exista (debe haberse creado antes vía /upsert).
      2. Guarda el PDF en /data/contratos/<eps>.pdf (sobreescribe vigente).
      3. Pasa el PDF binario a Claude (soporte nativo Messages API) para
         extraer cláusulas estructuradas — más robusto que pdfplumber.
      4. Borra cláusulas viejas + inserta las nuevas.
      5. Registra el evento en audit_log (trazabilidad SuperSalud).

    Rate-limit: 5/min por IP (cada subida cuesta ~$0.10-0.15 USD en
    Claude — proteger contra clicks repetidos accidentales o abuso).

    Devuelve cantidad de cláusulas extraídas + ruta donde quedó el PDF.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    contrato = db.query(ContratoRecord).filter(ContratoRecord.eps == eps).first()
    if not contrato:
        raise HTTPException(
            status_code=404,
            detail=f"No existe contrato registrado para EPS '{eps}'. Créalo primero en la pestaña Contratos.",
        )

    contenido = await file.read()
    if len(contenido) < 1024:
        raise HTTPException(status_code=400, detail="Archivo PDF demasiado pequeño / corrupto")
    if len(contenido) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF mayor a 30MB no soportado")

    # Guardar el PDF en disco (sobreescribe el vigente)
    os.makedirs(CONTRATOS_PDF_ROOT, exist_ok=True)
    eps_safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in eps)[:80]
    pdf_path = os.path.join(CONTRATOS_PDF_ROOT, f"{eps_safe}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(contenido)

    # Extraer cláusulas: pasamos el PDF binario directo a Claude (soporte
    # nativo de Anthropic Messages API). Es mucho más robusto que
    # pdfplumber → texto plano: Claude lee todas las páginas incluso si
    # el PDF tiene fonts raros, tablas complejas, o escaneos con OCR
    # incrustado. Famisanar tiene formato que pdfplumber no maneja bien
    # (devolvía solo 7k chars de un PDF de 4MB → 0 cláusulas).
    from app.services.extractor_clausulas_contrato import (
        extraer_clausulas_desde_pdf_bytes,
    )
    try:
        clausulas = await extraer_clausulas_desde_pdf_bytes(contenido, eps)
    except Exception as e:
        logger.error(f"[CONTRATO-PDF] Error extrayendo cláusulas eps={eps}: {e}")
        clausulas = []

    # Reemplazar cláusulas anteriores por las nuevas
    db.query(ClausulaContrato).filter(ClausulaContrato.eps == eps).delete()
    for c in clausulas:
        db.add(ClausulaContrato(
            eps=eps,
            numero_clausula=c["numero"],
            tema=c["tema"],
            titulo=c["titulo"],
            texto_literal=c["texto_literal"],
            pagina=c["pagina"],
        ))

    contrato.pdf_path = pdf_path
    contrato.pdf_subido_en = datetime.now(timezone.utc)
    db.commit()

    # Audit log — quién subió qué PDF, cuándo, cuántas cláusulas
    # extrajo. Sirve para reportes SuperSalud y trazabilidad interna.
    try:
        ip_origen = request.client.host if request.client else None
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol or "AUDITOR",
            accion="UPLOAD_CONTRATO_PDF",
            tabla="contratos",
            registro_id=None,
            campo="pdf_path",
            valor_nuevo=pdf_path,
            detalle=f"EPS={eps}, {len(contenido)//1024}KB, {len(clausulas)} cláusulas extraídas",
            ip=ip_origen,
        )
    except Exception as _e_audit:
        logger.debug(f"[AUDIT] no se pudo registrar UPLOAD_CONTRATO_PDF: {_e_audit}")

    logger.info(
        f"[CONTRATO-PDF] eps={eps} pdf={len(contenido)//1024}KB "
        f"clausulas={len(clausulas)} usuario={current_user.email}"
    )

    return {
        "eps": eps,
        "pdf_kb": len(contenido) // 1024,
        "clausulas_extraidas": len(clausulas),
        "subido_en": contrato.pdf_subido_en.isoformat(),
    }


@router.get("/{eps}/clausulas")
def listar_clausulas_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista cláusulas del contrato de una EPS, agrupadas por tema."""
    contrato = db.query(ContratoRecord).filter(ContratoRecord.eps == eps).first()
    if not contrato:
        raise HTTPException(status_code=404, detail=f"Contrato no encontrado para EPS '{eps}'")

    clausulas = (
        db.query(ClausulaContrato)
        .filter(ClausulaContrato.eps == eps)
        .order_by(ClausulaContrato.tema, ClausulaContrato.id)
        .all()
    )
    items = [
        {
            "id": c.id,
            "numero": c.numero_clausula,
            "tema": c.tema,
            "titulo": c.titulo,
            "texto_literal": c.texto_literal,
            "pagina": c.pagina,
        }
        for c in clausulas
    ]
    return {
        "eps": eps,
        "pdf_subido_en": contrato.pdf_subido_en.isoformat() if contrato.pdf_subido_en else None,
        "tiene_pdf": bool(contrato.pdf_path and os.path.exists(contrato.pdf_path or "")),
        "total_clausulas": len(items),
        "clausulas": items,
    }


@router.delete("/{eps}/clausulas")
def borrar_clausulas_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Borra todas las cláusulas extraídas (no borra el PDF guardado).

    Útil para forzar re-extracción manual sin borrar el PDF de disco.
    """
    n = db.query(ClausulaContrato).filter(ClausulaContrato.eps == eps).delete()
    db.commit()
    return {"eps": eps, "clausulas_borradas": n}
