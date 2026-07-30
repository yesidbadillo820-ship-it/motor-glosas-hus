import os
import json
import logging
import re
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models.schemas import ContratoInput
from app.repositories.contrato_repository import ContratoRepository
from app.repositories.audit_repository import AuditRepository
from app.api.deps import get_usuario_actual, get_auditor_o_superior, get_coordinador_o_admin
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
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Crea un nuevo contrato o actualiza uno existente si la EPS ya existe.

    Acceso: AUDITOR o superior. Subir el contrato firmado es trabajo diario del
    gestor —la propia pantalla se lo pide—, así que el auditor conserva el
    permiso; lo que cambia es que el VIEWER deja de tenerlo. Antes bastaba con
    estar autenticado.

    **Borrar** el contrato o sus cláusulas sí exige COORDINADOR: eso deja sin
    base todos los dictámenes de esa EPS.
    """
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

    eps_contratadas = {c.eps for c in db.query(ContratoRecord).all() if c.eps}

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

    contratos = db.query(ContratoRecord).order_by(ContratoRecord.eps.asc()).all()

    def _generar():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["eps", "detalles"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for c in contratos:
            w.writerow([c.eps or "", (c.detalles or "")[:500]])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    fname = f"contratos-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
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
    eps_con_glosas = {e[0] for e in db.query(GlosaRecord.eps).distinct().all() if e[0]}

    sin_glosas = []
    for c in contratos:
        if c.eps not in eps_con_glosas:
            sin_glosas.append(
                {
                    "eps": c.eps,
                    "detalles": c.detalles,
                }
            )

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
            if b["valor_objetado"]
            else 0.0
        )
        items.append(
            {
                "eps": eps,
                "total_glosas": b["total"],
                "valor_objetado_total": int(b["valor_objetado"]),
                "valor_recuperado_total": int(b["valor_recuperado"]),
                "tasa_recuperacion_pct": tasa,
            }
        )

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

    glosas = db.query(GlosaRecord).filter(GlosaRecord.eps == eps).all()

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
        g for g in cerradas if (g.estado or "").upper() in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
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
        resp_efectivos.append(
            {
                "codigo_respuesta": cr,
                "usado": b["total"],
                "tasa_exito_pct": tasa,
            }
        )
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
            "tasa_recuperacion_pct": (round(100 * valor_rec / valor_obj, 2) if valor_obj else 0.0),
        },
        "resoluciones": {
            "tasa_levantamiento_pct": (
                round(100 * len(levantadas) / len(decididas), 2) if decididas else 0.0
            ),
            "tiempo_promedio_decision_dias": (
                round(sum(tiempos) / len(tiempos), 2) if tiempos else 0.0
            ),
        },
        "top_5_codigos_objetados": [{"codigo": c, "veces": n} for c, n in top_codigos],
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

    glosas = db.query(GlosaRecord).filter(GlosaRecord.eps == eps).all()

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

    decididas = [
        g for g in glosas if (g.estado or "").upper() in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}
    ]
    levantadas = sum(1 for g in decididas if (g.estado or "").upper() == "LEVANTADA")

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
        "tasa_recuperacion_pct": (round(100 * valor_rec / valor_obj, 2) if valor_obj else 0.0),
        "tasa_levantamiento_pct": (
            round(100 * levantadas / len(decididas), 2) if decididas else 0.0
        ),
        "decididas": len(decididas),
        "pendientes": total - len(decididas),
        "top_5_codigos": [{"codigo": c, "veces": n} for c, n in top_5],
    }


@router.delete("/{eps}")
def eliminar_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
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
        clausulas, diagnostico = await extraer_clausulas_desde_pdf_bytes(contenido, eps)
    except Exception as e:
        logger.error(f"[CONTRATO-PDF] Error extrayendo cláusulas eps={eps}: {e}")
        clausulas, diagnostico = [], f"Excepción inesperada: {e}"

    # Normalizar el eps para guardar (upper + strip). Las queries del motor
    # (RAG, citation_verifier) usan .upper() — guardar igual previene
    # mismatch entre "SALUD MIA" guardado y "Salud Mia" buscado.
    eps_norm = (eps or "").upper().strip()

    # CRÍTICO: solo BORRAR cláusulas viejas si la IA devolvió cláusulas nuevas.
    # Antes el código hacía DELETE incondicional → si la IA fallaba (0 cláusulas)
    # se perdían las cláusulas previamente cargadas. Bug reportado por el
    # gestor: "subí SALUD MIA con éxito ayer, hoy no aparecen".
    clausulas_previas = db.query(ClausulaContrato).filter(ClausulaContrato.eps == eps_norm).count()
    if clausulas:
        db.query(ClausulaContrato).filter(ClausulaContrato.eps == eps_norm).delete()
        for c in clausulas:
            db.add(
                ClausulaContrato(
                    eps=eps_norm,
                    numero_clausula=c["numero"],
                    tema=c["tema"],
                    titulo=c["titulo"],
                    texto_literal=c["texto_literal"],
                    pagina=c["pagina"],
                )
            )
        logger.info(
            f"[CONTRATO-PDF] eps={eps_norm} reemplazadas {clausulas_previas} → "
            f"{len(clausulas)} cláusulas"
        )
    else:
        logger.warning(
            f"[CONTRATO-PDF] eps={eps_norm} extracción IA devolvió 0 cláusulas. "
            f"PRESERVANDO {clausulas_previas} cláusulas previas. Diag: {diagnostico}"
        )

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
            detalle=f"EPS={eps}, {len(contenido) // 1024}KB, {len(clausulas)} cláusulas extraídas",
            ip=ip_origen,
        )
    except Exception as _e_audit:
        logger.debug(f"[AUDIT] no se pudo registrar UPLOAD_CONTRATO_PDF: {_e_audit}")

    logger.info(
        f"[CONTRATO-PDF] eps={eps} pdf={len(contenido) // 1024}KB "
        f"clausulas={len(clausulas)} usuario={current_user.email}"
    )

    return {
        "eps": eps,
        "pdf_kb": len(contenido) // 1024,
        "clausulas_extraidas": len(clausulas),
        "diagnostico": diagnostico,
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

    # Buscar con eps normalizado (upper+strip) y también con el raw original
    # para encontrar registros que se guardaron antes del fix (sin normalizar).
    eps_norm = (eps or "").upper().strip()
    clausulas = (
        db.query(ClausulaContrato)
        .filter(ClausulaContrato.eps.in_([eps, eps_norm]))
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
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Borra todas las cláusulas extraídas (no borra el PDF guardado).

    Útil para forzar re-extracción manual sin borrar el PDF de disco.
    """
    eps_norm = (eps or "").upper().strip()
    n = (
        db.query(ClausulaContrato)
        .filter(ClausulaContrato.eps.in_([eps, eps_norm]))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"eps": eps, "clausulas_borradas": n}


# ─── Cargar cláusulas MANUALMENTE (sin gastar tokens IA) ──────────────
# Útil cuando ya tenés el texto del contrato y querés inyectarlo
# directamente, en lugar de subir el PDF y pagar a Claude por extraerlo.
# El gestor copia/pega cada cláusula desde el contrato firmado.


class ClausulaManualInput(BaseModel):
    numero: str
    tema: str  # TA / SO / AU / CO / FA / NN
    titulo: str = ""
    texto_literal: str
    pagina: Optional[int] = None


class ClausulasManualBatch(BaseModel):
    reemplazar: bool = True  # si True, borra las existentes antes de insertar
    clausulas: list[ClausulaManualInput]


@router.post("/{eps}/clausulas-manual")
def cargar_clausulas_manual(
    eps: str,
    batch: ClausulasManualBatch,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Inserta cláusulas escritas a mano (no requiere subir PDF ni gastar
    tokens IA). El gestor copia el texto literal del contrato firmado.

    Si reemplazar=True: borra las cláusulas existentes para esa EPS antes.
    Si reemplazar=False: las agrega a las existentes.

    Devuelve cuántas se insertaron y total después de la operación.
    """
    eps_norm = (eps or "").upper().strip()
    if not eps_norm:
        raise HTTPException(status_code=400, detail="EPS vacía")
    if not batch.clausulas:
        raise HTTPException(status_code=400, detail="batch.clausulas vacío")

    TEMAS_VALIDOS = {"TA", "SO", "AU", "CO", "FA", "NN"}

    if batch.reemplazar:
        db.query(ClausulaContrato).filter(ClausulaContrato.eps.in_([eps, eps_norm])).delete(
            synchronize_session=False
        )

    insertadas = 0
    for c in batch.clausulas:
        texto = (c.texto_literal or "").strip()
        if len(texto) < 30:
            continue
        tema = (c.tema or "NN").upper().strip()
        if tema not in TEMAS_VALIDOS:
            tema = "NN"
        db.add(
            ClausulaContrato(
                eps=eps_norm,
                numero_clausula=(c.numero or "").strip()[:80],
                tema=tema,
                titulo=(c.titulo or "").strip()[:300],
                texto_literal=texto[:5000],
                pagina=c.pagina,
            )
        )
        insertadas += 1

    db.commit()

    total = db.query(ClausulaContrato).filter(ClausulaContrato.eps == eps_norm).count()
    logger.info(
        f"[CONTRATO-MANUAL] eps={eps_norm} insertadas={insertadas} "
        f"reemplazar={batch.reemplazar} total_actual={total}"
    )
    return {
        "eps": eps_norm,
        "insertadas": insertadas,
        "total_actual": total,
        "modo": "reemplazar" if batch.reemplazar else "agregar",
    }


# ─── Metadatos enriquecidos del contrato (editor admin) ───────────────
# El PR #106 creó las 12 columnas y el inyector
# contexto_contractual_enriquecido.py ya las consume para armar el bloque
# [CONTRATO VIGENTE — DATOS AUDITABLES] del prompt. Pero sin editor todo
# quedaba NULL y el dictamen salía genérico (auditoría 10-jun-2026 vs la
# "otra IA" que cita contrato, NITs, SECOP, plazo y anexos). Estos
# endpoints cierran ese hueco.
#
# NOTA: este archivo NO usa `from __future__ import annotations` a
# propósito — slowapi + PEP 563 rompe los body models Pydantic en los
# endpoints decorados (regresión vista en producción jun-2026).

# NIT colombiano laxo: tras quitar espacios solo se aceptan dígitos,
# puntos de miles y guión del dígito de verificación. Se preserva el
# formato con puntos porque el dictamen cita "NIT 900.006.037-4" tal cual.
_NIT_CHARS_VALIDOS = re.compile(r"^[\d.\-]+$")

# Longitudes de columna (ver ContratoRecord) — se trunca defensivamente
# en vez de reventar con 500 en Postgres: el editor manda textos que un
# humano pegó desde el PDF y pueden venir más largos que la columna.
_MAX_CAMPOS_META = {
    "numero_contrato": 120,
    "razon_social_eps": 300,
    "razon_social_ips": 300,
    "numero_proceso_secop": 120,
}

# Anexos estándar de los contratos de prestación de servicios de salud
# del HUS (numeración tipo DIGSA/Famisanar). Sugerencias editables para
# el botón "Cargar anexos comunes" del panel — no se imponen.
ANEXOS_SUGERIDOS_ESTANDAR = [
    {"nombre": "Anexo 1", "descripcion": "Tarifas y servicios pactados"},
    {"nombre": "Anexo 2", "descripcion": "Red de servicios habilitados y sedes"},
    {"nombre": "Anexo 3", "descripcion": "Servicios CUPS con tarifa SOAT ± %"},
    {"nombre": "Anexo 3.1", "descripcion": "Medicamentos a valor fijo (CUM)"},
    {"nombre": "Anexo 3.2", "descripcion": "Suministros e insumos (con IVA)"},
    {"nombre": "Anexo 05", "descripcion": "Dispositivos médicos"},
    {
        "nombre": "Anexo técnico 5 Res. 3047/2008",
        "descripcion": "Soportes de facturación exigibles al prestador",
    },
]


class AnexoContratoInput(BaseModel):
    nombre: str = ""
    descripcion: str = ""


class MetadatosContratoInput(BaseModel):
    """Body del PUT — todos opcionales; el formulario manda el set completo.

    Semántica PUT real: reemplaza los 12 campos enriquecidos. Campo vacío
    o ausente → NULL en BD (el inyector degrada elegantemente).
    """

    numero_contrato: Optional[str] = None
    nit_eps: Optional[str] = None
    nit_ips: Optional[str] = None
    razon_social_eps: Optional[str] = None
    razon_social_ips: Optional[str] = None
    numero_proceso_secop: Optional[str] = None
    secop_url: Optional[str] = None
    fecha_suscripcion: Optional[str] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    objeto_contractual: Optional[str] = None
    anexos_descripcion: Optional[List[AnexoContratoInput]] = None
    modalidades_tarifarias: Optional[List[str]] = None


def _texto_o_none(valor: Optional[str], maximo: int) -> Optional[str]:
    """Strip + truncado a longitud de columna; vacío → None."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio[:maximo] if limpio else None


def _normalizar_nit(valor: Optional[str], campo: str) -> Optional[str]:
    """Normaliza quitando espacios; rechaza solo caracteres claramente inválidos.

    Acepta '900.006.037-4', '900006037-4' y '900006037' (regex laxo
    \\d{6,12} + dígito de verificación opcional). No fuerza un formato:
    el dictamen cita el NIT tal como el gestor lo escribió.
    """
    if valor is None:
        return None
    limpio = valor.replace(" ", "").strip()
    if not limpio:
        return None
    if not _NIT_CHARS_VALIDOS.match(limpio):
        raise HTTPException(
            status_code=400,
            detail=f"{campo} contiene caracteres inválidos: '{valor}'. "
            "Use solo dígitos, puntos y guión (ej: 900.006.037-4).",
        )
    digitos = limpio.replace(".", "").replace("-", "")
    if not digitos.isdigit() or not (6 <= len(digitos) <= 13):
        raise HTTPException(
            status_code=400,
            detail=f"{campo} no parece un NIT colombiano válido: '{valor}' "
            "(se esperan 6-12 dígitos + dígito de verificación opcional).",
        )
    return limpio


def _parsear_fecha_iso(valor: Optional[str], campo: str) -> Optional[datetime]:
    """ISO YYYY-MM-DD → datetime UTC (la columna es DateTime). Vacío → None."""
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio:
        return None
    try:
        d = date.fromisoformat(limpio)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{campo} debe ser fecha ISO YYYY-MM-DD (recibido: '{valor}').",
        )
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _fecha_a_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.date().isoformat() if dt else None


def _parsear_lista_json(texto: Optional[str]) -> list:
    """Text JSON de BD → list. Vacío o corrupto → [] (nunca rompe el GET)."""
    if not texto:
        return []
    try:
        valor = json.loads(texto)
        return valor if isinstance(valor, list) else []
    except (ValueError, TypeError):
        return []


def _buscar_contrato(db: Session, eps: str) -> Optional[ContratoRecord]:
    """Busca por eps crudo y normalizado (upper+strip) — hay registros
    históricos guardados sin normalizar, igual que en /clausulas."""
    eps_norm = (eps or "").upper().strip()
    return db.query(ContratoRecord).filter(ContratoRecord.eps.in_([eps, eps_norm])).first()


def _serializar_metadatos(contrato: ContratoRecord) -> dict:
    """Forma única de respuesta para GET y PUT (el front rellena el form con esto)."""
    return {
        "eps": contrato.eps,
        "detalles": contrato.detalles,
        "pdf_path": contrato.pdf_path,
        "pdf_subido_en": contrato.pdf_subido_en.isoformat() if contrato.pdf_subido_en else None,
        "numero_contrato": contrato.numero_contrato,
        "nit_eps": contrato.nit_eps,
        "nit_ips": contrato.nit_ips,
        "razon_social_eps": contrato.razon_social_eps,
        "razon_social_ips": contrato.razon_social_ips,
        "numero_proceso_secop": contrato.numero_proceso_secop,
        "secop_url": contrato.secop_url,
        "fecha_suscripcion": _fecha_a_iso(contrato.fecha_suscripcion),
        "fecha_inicio": _fecha_a_iso(contrato.fecha_inicio),
        "fecha_fin": _fecha_a_iso(contrato.fecha_fin),
        "objeto_contractual": contrato.objeto_contractual,
        "anexos_descripcion": _parsear_lista_json(contrato.anexos_descripcion),
        "modalidades_tarifarias": _parsear_lista_json(contrato.modalidades_tarifarias),
    }


@router.get("/{eps}/anexos/sugeridos")
def anexos_sugeridos(
    eps: str,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Sugerencias estándar de anexos para auto-llenar el editor.

    Lectura libre (cualquier usuario autenticado): son plantillas, no
    datos del contrato. El front las añade como filas editables.
    """
    return {"eps": eps, "sugeridos": ANEXOS_SUGERIDOS_ESTANDAR}


@router.get("/{eps}/metadatos")
def obtener_metadatos_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Devuelve los metadatos enriquecidos del contrato de la EPS.

    Lectura abierta a AUDITOR+ para que vean los datos auditables
    (contrato, NITs, SECOP, plazo, anexos) al analizar glosas. 404 si la
    EPS no tiene ContratoRecord — el front lo interpreta como "contrato
    nuevo" y muestra el formulario vacío.
    """
    contrato = _buscar_contrato(db, eps)
    if not contrato:
        raise HTTPException(
            status_code=404,
            detail=f"No existe contrato registrado para EPS '{eps}'.",
        )
    logger.info(f"[CONTRATO-META] consulta eps={contrato.eps} usuario={current_user.email}")
    return _serializar_metadatos(contrato)


@router.put("/{eps}/metadatos")
def actualizar_metadatos_contrato(
    eps: str,
    body: MetadatosContratoInput,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Actualiza (o crea) los 12 metadatos enriquecidos en un solo request.

    Validaciones:
      - NITs: laxo colombiano, normaliza quitando espacios (400 solo si
        trae caracteres claramente inválidos).
      - secop_url: https obligatorio si no viene vacía (evita ftp:// y
        javascript: inyectados al prompt/dictamen).
      - fechas ISO YYYY-MM-DD; vacío → NULL; fecha_inicio <= fecha_fin.
      - objeto_contractual máx 5000 chars.
      - anexos [{nombre, descripcion}] y modalidades [str] → Text JSON.

    Si la fila no existe se crea (flujo "EPS con glosas sin contrato").
    Registra el cambio en audit_log con valor_anterior/valor_nuevo.
    """
    eps_norm = (eps or "").upper().strip()
    if not eps_norm:
        raise HTTPException(status_code=400, detail="EPS vacía")

    # ── Validar/normalizar TODO antes de tocar la fila ──
    nit_eps = _normalizar_nit(body.nit_eps, "nit_eps")
    nit_ips = _normalizar_nit(body.nit_ips, "nit_ips")

    secop_url = _texto_o_none(body.secop_url, 500)
    if secop_url and not secop_url.lower().startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="secop_url debe comenzar con https:// "
            f"(recibido: '{secop_url[:80]}'). Copie la URL del proceso desde SECOP II.",
        )

    fecha_suscripcion = _parsear_fecha_iso(body.fecha_suscripcion, "fecha_suscripcion")
    fecha_inicio = _parsear_fecha_iso(body.fecha_inicio, "fecha_inicio")
    fecha_fin = _parsear_fecha_iso(body.fecha_fin, "fecha_fin")
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=400,
            detail=f"fecha_inicio ({body.fecha_inicio}) no puede ser posterior a "
            f"fecha_fin ({body.fecha_fin}).",
        )

    objeto = (body.objeto_contractual or "").strip() or None
    if objeto and len(objeto) > 5000:
        raise HTTPException(
            status_code=400,
            detail=f"objeto_contractual supera el máximo de 5000 caracteres ({len(objeto)}).",
        )

    anexos_json: Optional[str] = None
    if body.anexos_descripcion:
        anexos_limpios = []
        for a in body.anexos_descripcion:
            nombre = (a.nombre or "").strip()[:120]
            descripcion = (a.descripcion or "").strip()[:400]
            if nombre or descripcion:
                anexos_limpios.append({"nombre": nombre, "descripcion": descripcion})
        if anexos_limpios:
            anexos_json = json.dumps(anexos_limpios, ensure_ascii=False)

    modalidades_json: Optional[str] = None
    if body.modalidades_tarifarias:
        modalidades = [m.strip()[:120] for m in body.modalidades_tarifarias if m and m.strip()]
        if modalidades:
            modalidades_json = json.dumps(modalidades, ensure_ascii=False)

    # ── Fila: buscar o crear ──
    contrato = _buscar_contrato(db, eps)
    creado = False
    if not contrato:
        # detalles="" (no None): el grid del panel concatena el campo y
        # mostraría el literal "null" si quedara NULL.
        contrato = ContratoRecord(eps=eps_norm, detalles="")
        db.add(contrato)
        creado = True

    valores_anteriores = {
        "numero_contrato": contrato.numero_contrato,
        "nit_eps": contrato.nit_eps,
        "nit_ips": contrato.nit_ips,
        "razon_social_eps": contrato.razon_social_eps,
        "razon_social_ips": contrato.razon_social_ips,
        "numero_proceso_secop": contrato.numero_proceso_secop,
        "secop_url": contrato.secop_url,
        "fecha_suscripcion": _fecha_a_iso(contrato.fecha_suscripcion),
        "fecha_inicio": _fecha_a_iso(contrato.fecha_inicio),
        "fecha_fin": _fecha_a_iso(contrato.fecha_fin),
        "objeto_contractual": contrato.objeto_contractual,
        "anexos_descripcion": contrato.anexos_descripcion,
        "modalidades_tarifarias": contrato.modalidades_tarifarias,
    }

    contrato.numero_contrato = _texto_o_none(
        body.numero_contrato, _MAX_CAMPOS_META["numero_contrato"]
    )
    contrato.nit_eps = nit_eps
    contrato.nit_ips = nit_ips
    contrato.razon_social_eps = _texto_o_none(
        body.razon_social_eps, _MAX_CAMPOS_META["razon_social_eps"]
    )
    contrato.razon_social_ips = _texto_o_none(
        body.razon_social_ips, _MAX_CAMPOS_META["razon_social_ips"]
    )
    contrato.numero_proceso_secop = _texto_o_none(
        body.numero_proceso_secop, _MAX_CAMPOS_META["numero_proceso_secop"]
    )
    contrato.secop_url = secop_url
    contrato.fecha_suscripcion = fecha_suscripcion
    contrato.fecha_inicio = fecha_inicio
    contrato.fecha_fin = fecha_fin
    contrato.objeto_contractual = objeto
    contrato.anexos_descripcion = anexos_json
    contrato.modalidades_tarifarias = modalidades_json
    db.commit()
    db.refresh(contrato)

    respuesta = _serializar_metadatos(contrato)

    # Audit log — qué cambió, quién y desde dónde (trazabilidad
    # SuperSalud). Best-effort: si falla no revienta el guardado.
    try:
        valores_nuevos = {
            k: v
            for k, v in respuesta.items()
            if k not in ("eps", "detalles", "pdf_path", "pdf_subido_en")
        }
        ip_origen = request.client.host if request.client else None
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol or "AUDITOR",
            accion="UPDATE_CONTRATO_METADATOS",
            tabla="contratos",
            registro_id=None,
            campo="contratos.metadatos",
            valor_anterior=json.dumps(valores_anteriores, ensure_ascii=False),
            valor_nuevo=json.dumps(valores_nuevos, ensure_ascii=False),
            detalle=f"EPS={contrato.eps}, {'creado' if creado else 'actualizado'} desde editor",
            ip=ip_origen,
        )
    except Exception as _e_audit:
        logger.debug(f"[AUDIT] no se pudo registrar UPDATE_CONTRATO_METADATOS: {_e_audit}")

    logger.info(
        f"[CONTRATO-META] eps={contrato.eps} {'creado' if creado else 'actualizado'} "
        f"usuario={current_user.email} contrato={contrato.numero_contrato or '—'}"
    )
    return respuesta
