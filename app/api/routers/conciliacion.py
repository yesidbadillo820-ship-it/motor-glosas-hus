from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.db import UsuarioRecord, GlosaRecord
from app.repositories.conciliacion_repository import ConciliacionRepository
from app.repositories.audit_repository import AuditRepository
from app.api.deps import get_usuario_actual, get_auditor_o_superior

router = APIRouter(prefix="/conciliaciones", tags=["conciliacion"])


class ConciliacionCreate(BaseModel):
    glosa_id: int
    fecha_audiencia: str
    lugar: Optional[str] = ""
    participantes_hus: Optional[str] = ""
    participantes_eps: Optional[str] = ""
    observaciones: Optional[str] = ""
    acta_numero: Optional[str] = ""


class ResultadoUpdate(BaseModel):
    resultado: str
    valor_conciliado: float = 0.0
    observaciones: Optional[str] = ""
    siguiente_paso: Optional[str] = ""
    acta_numero: Optional[str] = ""


class ContraRespuestaEPSInput(BaseModel):
    texto: str
    fecha: Optional[str] = None  # ISO; default = now


class PosturaHUSInput(BaseModel):
    texto: str
    valor_ratificado: Optional[float] = None


class CerrarActaInput(BaseModel):
    acta_numero: str
    fecha_acta: str  # ISO date
    valor_conciliado: float = 0.0
    resultado: str   # ACUERDO_TOTAL | ACUERDO_PARCIAL | SIN_ACUERDO
    observaciones: Optional[str] = ""


@router.post("/", status_code=201)
def crear_conciliacion(data: ConciliacionCreate, db: Session = Depends(get_db),
                       current_user: UsuarioRecord = Depends(get_auditor_o_superior)):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == data.glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    try:
        fecha = datetime.fromisoformat(data.fecha_audiencia)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use ISO: 2026-05-10T10:00:00")
    c = ConciliacionRepository(db).crear(
        glosa_id=data.glosa_id, creado_por=current_user.email, fecha_audiencia=fecha,
        lugar=data.lugar or "", participantes_hus=data.participantes_hus or "",
        participantes_eps=data.participantes_eps or "",
        observaciones=data.observaciones or "", acta_numero=data.acta_numero or "",
    )
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="CREAR", tabla="conciliaciones", registro_id=c.id,
        detalle=f"Conciliación programada para glosa #{data.glosa_id} — fecha: {fecha.date()}")
    return {"message": "Conciliación programada correctamente", "id": c.id,
            "glosa_id": c.glosa_id,
            "fecha_audiencia": c.fecha_audiencia.isoformat() if c.fecha_audiencia else None}


@router.get("/")
def listar_conciliaciones(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100),
                          resultado: Optional[str] = None, db: Session = Depends(get_db),
                          current_user: UsuarioRecord = Depends(get_usuario_actual)):
    res = ConciliacionRepository(db).listar(page=page, per_page=per_page, resultado=resultado)
    return {"items": [_serializar(c) for c in res["items"]], "total": res["total"],
            "page": res["page"], "per_page": res["per_page"], "pages": res["pages"]}


@router.get("/estadisticas")
def estadisticas_conciliaciones(db: Session = Depends(get_db),
                                current_user: UsuarioRecord = Depends(get_usuario_actual)):
    return ConciliacionRepository(db).estadisticas()


@router.get("/glosa/{glosa_id}")
def conciliaciones_por_glosa(glosa_id: int, db: Session = Depends(get_db),
                              current_user: UsuarioRecord = Depends(get_usuario_actual)):
    return [_serializar(c) for c in ConciliacionRepository(db).listar_por_glosa(glosa_id)]


@router.patch("/{conciliacion_id}/resultado")
def registrar_resultado(conciliacion_id: int, data: ResultadoUpdate,
                        db: Session = Depends(get_db),
                        current_user: UsuarioRecord = Depends(get_auditor_o_superior)):
    RESULTADOS_VALIDOS = {"ACUERDO_TOTAL", "ACUERDO_PARCIAL", "SIN_ACUERDO"}
    if data.resultado.upper() not in RESULTADOS_VALIDOS:
        raise HTTPException(status_code=400,
                            detail=f"Resultado inválido. Use: {', '.join(RESULTADOS_VALIDOS)}")
    c = ConciliacionRepository(db).actualizar_resultado(
        conciliacion_id=conciliacion_id, resultado=data.resultado.upper(),
        valor_conciliado=data.valor_conciliado, observaciones=data.observaciones or "",
        siguiente_paso=data.siguiente_paso or "", acta_numero=data.acta_numero or "")
    if not c:
        raise HTTPException(status_code=404, detail="Conciliación no encontrada")
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="ACTUALIZAR", tabla="conciliaciones", registro_id=conciliacion_id,
        campo="resultado", valor_nuevo=data.resultado,
        detalle=f"Resultado conciliación #{conciliacion_id}: {data.resultado} — valor: ${data.valor_conciliado:,.0f}")
    return {"message": "Resultado registrado", "conciliacion": _serializar(c)}


def _serializar(c) -> dict:
    return {
        "id": c.id, "glosa_id": c.glosa_id, "creado_por": c.creado_por,
        "creado_en": c.creado_en.isoformat() if c.creado_en else None,
        "fecha_audiencia": c.fecha_audiencia.isoformat() if c.fecha_audiencia else None,
        "lugar": c.lugar, "participantes_hus": c.participantes_hus,
        "participantes_eps": c.participantes_eps, "resultado": c.resultado,
        "valor_conciliado": c.valor_conciliado, "observaciones": c.observaciones,
        "siguiente_paso": c.siguiente_paso, "acta_numero": c.acta_numero,
        # bilateral
        "contra_respuesta_eps": getattr(c, "contra_respuesta_eps", None),
        "fecha_contra_respuesta_eps": c.fecha_contra_respuesta_eps.isoformat() if getattr(c, "fecha_contra_respuesta_eps", None) else None,
        "postura_hus": getattr(c, "postura_hus", None),
        "fecha_acta": c.fecha_acta.isoformat() if getattr(c, "fecha_acta", None) else None,
        "valor_ratificado_hus": float(getattr(c, "valor_ratificado_hus", 0) or 0),
        "estado_bilateral": getattr(c, "estado_bilateral", None) or "PROGRAMADA",
    }


def _obtener_o_404(db: Session, conciliacion_id: int):
    from app.models.db import ConciliacionRecord
    c = db.query(ConciliacionRecord).filter(ConciliacionRecord.id == conciliacion_id).first()
    if not c:
        raise HTTPException(404, "Conciliación no encontrada")
    return c


@router.patch("/{conciliacion_id}/contra-respuesta-eps")
def registrar_contra_respuesta(
    conciliacion_id: int,
    data: ContraRespuestaEPSInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Registra la respuesta que la EPS dio tras la radicación inicial y
    antes de la audiencia de conciliación."""
    if not data.texto or len(data.texto.strip()) < 20:
        raise HTTPException(400, "La contra-respuesta debe tener al menos 20 caracteres")
    c = _obtener_o_404(db, conciliacion_id)
    fecha = datetime.utcnow()
    if data.fecha:
        try:
            fecha = datetime.fromisoformat(data.fecha)
        except ValueError:
            raise HTTPException(400, "Fecha inválida, use ISO")
    c.contra_respuesta_eps = data.texto.strip()
    c.fecha_contra_respuesta_eps = fecha
    if (c.estado_bilateral or "PROGRAMADA") == "PROGRAMADA":
        c.estado_bilateral = "EPS_RESPONDIO"
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="CONCILIACION_CONTRA_EPS", tabla="conciliaciones",
        registro_id=conciliacion_id,
        detalle=f"EPS respondió {fecha.date()} — {len(data.texto)} chars")
    return {"message": "Contra-respuesta registrada", "conciliacion": _serializar(c)}


@router.patch("/{conciliacion_id}/postura-hus")
def registrar_postura_hus(
    conciliacion_id: int,
    data: PosturaHUSInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Registra la postura final de HUS para llevar a la audiencia."""
    if not data.texto or len(data.texto.strip()) < 20:
        raise HTTPException(400, "La postura debe tener al menos 20 caracteres")
    c = _obtener_o_404(db, conciliacion_id)
    c.postura_hus = data.texto.strip()
    if data.valor_ratificado is not None:
        c.valor_ratificado_hus = float(data.valor_ratificado)
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="CONCILIACION_POSTURA_HUS", tabla="conciliaciones",
        registro_id=conciliacion_id,
        detalle=f"Postura HUS registrada · ${c.valor_ratificado_hus or 0:,.0f}")
    return {"message": "Postura HUS registrada", "conciliacion": _serializar(c)}


@router.patch("/{conciliacion_id}/cerrar-acta")
def cerrar_acta(
    conciliacion_id: int,
    data: CerrarActaInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Cierra la conciliación firmando el acta final."""
    RES_VALIDOS = {"ACUERDO_TOTAL", "ACUERDO_PARCIAL", "SIN_ACUERDO"}
    if data.resultado.upper() not in RES_VALIDOS:
        raise HTTPException(400, f"Resultado inválido. Use: {', '.join(RES_VALIDOS)}")
    try:
        fecha_acta = datetime.fromisoformat(data.fecha_acta)
    except ValueError:
        raise HTTPException(400, "fecha_acta inválida, use ISO")
    c = _obtener_o_404(db, conciliacion_id)
    c.acta_numero = data.acta_numero.strip()
    c.fecha_acta = fecha_acta
    c.valor_conciliado = float(data.valor_conciliado)
    c.resultado = data.resultado.upper()
    if data.observaciones:
        c.observaciones = (c.observaciones or "") + "\n\n[ACTA] " + data.observaciones
    c.estado_bilateral = "ACTA_FIRMADA"
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="CONCILIACION_ACTA", tabla="conciliaciones",
        registro_id=conciliacion_id, campo="acta_numero", valor_nuevo=c.acta_numero,
        detalle=f"Acta {c.acta_numero} · {c.resultado} · ${c.valor_conciliado:,.0f}")
    return {"message": "Acta firmada", "conciliacion": _serializar(c)}


@router.get("/{conciliacion_id}/pdf")
def pdf_acta(
    conciliacion_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Genera un HTML imprimible del acta de conciliación (servido como
    text/html; el navegador puede imprimirlo como PDF con Ctrl+P → Guardar
    como PDF). Evita dependencias de wkhtmltopdf/weasyprint."""
    from fastapi.responses import HTMLResponse
    c = _obtener_o_404(db, conciliacion_id)
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == c.glosa_id).first()

    def _fmt_dt(d):
        return d.strftime("%d/%m/%Y %H:%M") if d else "—"

    def _fmt_d(d):
        return d.strftime("%d/%m/%Y") if d else "—"

    def _cop(v):
        try:
            return "$" + f"{float(v or 0):,.0f}".replace(",", ".")
        except Exception:
            return str(v or "—")

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Acta Conciliación {c.acta_numero or c.id}</title>
<style>
  @page {{ size: Letter; margin: 2cm 2cm 2cm 2cm; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #1f2937; font-size: 11pt; line-height: 1.55; }}
  .hdr {{ text-align: center; border-bottom: 3px double #0b5d8a; padding-bottom: 14px; margin-bottom: 22px; }}
  .hdr h1 {{ margin: 4px 0; color: #0b5d8a; font-size: 15pt; letter-spacing: .3px; }}
  .hdr .meta {{ font-size: 9.5pt; color: #475569; }}
  h2 {{ font-size: 12pt; color: #0b5d8a; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-top: 22px; }}
  .row {{ display: flex; gap: 18px; margin: 6px 0; }}
  .row b {{ min-width: 160px; display: inline-block; color: #334155; }}
  .box {{ border: 1px solid #cbd5e1; background: #f8fafc; padding: 10px 14px; border-radius: 5px; margin: 6px 0 10px; white-space: pre-wrap; }}
  .firmas {{ display: flex; gap: 40px; margin-top: 60px; }}
  .firma {{ flex: 1; text-align: center; border-top: 1px solid #334155; padding-top: 6px; font-size: 10pt; }}
  .watermark {{ position: fixed; bottom: 1cm; right: 1cm; font-size: 8pt; color: #94a3b8; }}
  .resumen {{ border: 2px solid #0b5d8a; background: #ecfeff; padding: 12px 16px; border-radius: 6px; margin: 14px 0; }}
  .resumen .row b {{ color: #0b5d8a; }}
  button.noprint {{ position: fixed; top: 10px; right: 10px; padding: 8px 14px; background: #0b5d8a; color: white; border: 0; border-radius: 6px; cursor: pointer; z-index: 10; }}
  @media print {{ button.noprint {{ display: none; }} }}
</style>
</head><body>
<button class="noprint" onclick="window.print()">Imprimir / Guardar PDF</button>
<div class="hdr">
  <div style="font-size:9pt;color:#64748b">ESE HOSPITAL UNIVERSITARIO DE SANTANDER — NIT 900.006.037-4</div>
  <h1>ACTA DE CONCILIACIÓN DE GLOSAS</h1>
  <div class="meta">Acta N° <b>{c.acta_numero or '—'}</b> · Expediente Glosa #{c.glosa_id}</div>
</div>

<h2>1. Partes intervinientes</h2>
<div class="row"><b>Por la IPS:</b> <span>{(c.participantes_hus or 'ESE HUS — Cartera / Glosas').strip()}</span></div>
<div class="row"><b>Por la EPS:</b> <span>{(c.participantes_eps or (glosa.eps if glosa else '—')).strip()}</span></div>
<div class="row"><b>Lugar de audiencia:</b> <span>{c.lugar or '—'}</span></div>
<div class="row"><b>Fecha audiencia:</b> <span>{_fmt_dt(c.fecha_audiencia)}</span></div>

<h2>2. Glosa objeto de conciliación</h2>
<div class="row"><b>EPS:</b> <span>{glosa.eps if glosa else '—'}</span></div>
<div class="row"><b>Paciente:</b> <span>{glosa.paciente if glosa else '—'}</span></div>
<div class="row"><b>Factura:</b> <span>{glosa.factura if glosa else '—'}</span></div>
<div class="row"><b>Código glosa:</b> <span>{glosa.codigo_glosa if glosa else '—'}</span></div>
<div class="row"><b>Valor objetado:</b> <span>{_cop(glosa.valor_objetado if glosa else 0)}</span></div>

<h2>3. Contra-respuesta de la EPS</h2>
<div class="box">{(c.contra_respuesta_eps or 'No registrada').strip()}</div>
<div class="row"><b>Fecha contra-respuesta:</b> <span>{_fmt_d(c.fecha_contra_respuesta_eps)}</span></div>

<h2>4. Postura de la IPS</h2>
<div class="box">{(c.postura_hus or 'No registrada').strip()}</div>
<div class="row"><b>Valor ratificado por la IPS:</b> <span>{_cop(c.valor_ratificado_hus)}</span></div>

<h2>5. Resolución de la conciliación</h2>
<div class="resumen">
  <div class="row"><b>Resultado:</b> <span><b>{(c.resultado or 'PENDIENTE').replace('_',' ')}</b></span></div>
  <div class="row"><b>Valor conciliado final:</b> <span><b>{_cop(c.valor_conciliado)}</b></span></div>
  <div class="row"><b>Siguiente paso:</b> <span>{c.siguiente_paso or '—'}</span></div>
  <div class="row"><b>Fecha firma del acta:</b> <span>{_fmt_d(c.fecha_acta)}</span></div>
</div>

<h2>6. Observaciones y acuerdos</h2>
<div class="box">{(c.observaciones or '—').strip()}</div>

<p style="margin-top:30px;font-size:10pt;color:#475569">
El presente documento se suscribe en cumplimiento del artículo 56 de la Ley 1438 de 2011,
el Decreto 4747 de 2007 (artículo 20) y la Resolución 2175 de 2015. De no lograrse acuerdo,
las partes podrán elevar el conflicto ante la Superintendencia Nacional de Salud según el
artículo 126 de la Ley 1438 de 2011.
</p>

<div class="firmas">
  <div class="firma">
    <div><b>Representante ESE HUS</b></div>
    <div>{(c.participantes_hus or '—').split(',')[0].strip()[:60]}</div>
  </div>
  <div class="firma">
    <div><b>Representante EPS</b></div>
    <div>{(c.participantes_eps or '—').split(',')[0].strip()[:60]}</div>
  </div>
</div>

<div class="watermark">Generado {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · {current_user.email}</div>
</body></html>"""
    return HTMLResponse(content=html)
