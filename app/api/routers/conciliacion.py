from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.tz import a_utc, ahora_utc
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
    resultado: str  # ACUERDO_TOTAL | ACUERDO_PARCIAL | SIN_ACUERDO
    observaciones: Optional[str] = ""


class ActaSinacFilaInput(BaseModel):
    glosa_id: Optional[int] = None
    radicado_acta_entidad: Optional[str] = "-"
    numero_factura: str
    fecha_factura: Optional[str] = None  # ISO o "DD/MM/YYYY"
    tipo_glosa: str = "ADMINISTRATIVA"  # ADM | MIX | MED
    tipificacion: Optional[str] = ""  # SOPORTES / TARIFAS / COBERTURA / ...
    cod_glosa: Optional[str] = ""
    descripcion_glosa: Optional[str] = ""
    valor_factura: float = 0.0
    valor_glosa_inicial: float = 0.0
    valor_pendiente_conciliar: float = 0.0
    valor_acepta_ips: float = 0.0


class ActaSinacInput(BaseModel):
    acta_numero: str
    nit: str
    razon_social: str
    periodo: str  # "2026-06" o "JUNIO 2026"
    filas: list[ActaSinacFilaInput]
    observaciones: Optional[str] = ""
    firmante_eps_nombre: Optional[str] = ""
    firmante_eps_cargo: Optional[str] = ""
    firmante_eps_correo: Optional[str] = ""
    firmante_hus_nombre: Optional[str] = ""
    firmante_hus_cargo: Optional[str] = ""
    firmante_hus_correo: Optional[str] = ""
    fecha_acta: Optional[str] = None  # ISO; default = now


@router.post("/", status_code=201)
def crear_conciliacion(
    data: ConciliacionCreate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == data.glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    try:
        fecha = a_utc(datetime.fromisoformat(data.fecha_audiencia))
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Formato de fecha inválido. Use ISO: 2026-05-10T10:00:00"
        )
    c = ConciliacionRepository(db).crear(
        glosa_id=data.glosa_id,
        creado_por=current_user.email,
        fecha_audiencia=fecha,
        lugar=data.lugar or "",
        participantes_hus=data.participantes_hus or "",
        participantes_eps=data.participantes_eps or "",
        observaciones=data.observaciones or "",
        acta_numero=data.acta_numero or "",
    )
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="CREAR",
        tabla="conciliaciones",
        registro_id=c.id,
        detalle=f"Conciliación programada para glosa #{data.glosa_id} — fecha: {fecha.date()}",
    )
    return {
        "message": "Conciliación programada correctamente",
        "id": c.id,
        "glosa_id": c.glosa_id,
        "fecha_audiencia": c.fecha_audiencia.isoformat() if c.fecha_audiencia else None,
    }


@router.get("/")
def listar_conciliaciones(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    resultado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    res = ConciliacionRepository(db).listar(page=page, per_page=per_page, resultado=resultado)
    return {
        "items": [_serializar(c) for c in res["items"]],
        "total": res["total"],
        "page": res["page"],
        "per_page": res["per_page"],
        "pages": res["pages"],
    }


@router.get("/estadisticas")
def estadisticas_conciliaciones(
    db: Session = Depends(get_db), current_user: UsuarioRecord = Depends(get_usuario_actual)
):
    return ConciliacionRepository(db).estadisticas()


@router.get("/glosa/{glosa_id}")
def conciliaciones_por_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    return [_serializar(c) for c in ConciliacionRepository(db).listar_por_glosa(glosa_id)]


@router.patch("/{conciliacion_id}/resultado")
def registrar_resultado(
    conciliacion_id: int,
    data: ResultadoUpdate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    RESULTADOS_VALIDOS = {"ACUERDO_TOTAL", "ACUERDO_PARCIAL", "SIN_ACUERDO"}
    if data.resultado.upper() not in RESULTADOS_VALIDOS:
        raise HTTPException(
            status_code=400, detail=f"Resultado inválido. Use: {', '.join(RESULTADOS_VALIDOS)}"
        )
    c = ConciliacionRepository(db).actualizar_resultado(
        conciliacion_id=conciliacion_id,
        resultado=data.resultado.upper(),
        valor_conciliado=data.valor_conciliado,
        observaciones=data.observaciones or "",
        siguiente_paso=data.siguiente_paso or "",
        acta_numero=data.acta_numero or "",
    )
    if not c:
        raise HTTPException(status_code=404, detail="Conciliación no encontrada")
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ACTUALIZAR",
        tabla="conciliaciones",
        registro_id=conciliacion_id,
        campo="resultado",
        valor_nuevo=data.resultado,
        detalle=f"Resultado conciliación #{conciliacion_id}: {data.resultado} — valor: ${data.valor_conciliado:,.0f}",
    )
    return {"message": "Resultado registrado", "conciliacion": _serializar(c)}


def _serializar(c) -> dict:
    return {
        "id": c.id,
        "glosa_id": c.glosa_id,
        "creado_por": c.creado_por,
        "creado_en": c.creado_en.isoformat() if c.creado_en else None,
        "fecha_audiencia": c.fecha_audiencia.isoformat() if c.fecha_audiencia else None,
        "lugar": c.lugar,
        "participantes_hus": c.participantes_hus,
        "participantes_eps": c.participantes_eps,
        "resultado": c.resultado,
        "valor_conciliado": c.valor_conciliado,
        "observaciones": c.observaciones,
        "siguiente_paso": c.siguiente_paso,
        "acta_numero": c.acta_numero,
        # bilateral
        "contra_respuesta_eps": getattr(c, "contra_respuesta_eps", None),
        "fecha_contra_respuesta_eps": c.fecha_contra_respuesta_eps.isoformat()
        if getattr(c, "fecha_contra_respuesta_eps", None)
        else None,
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
    fecha = ahora_utc()
    if data.fecha:
        try:
            fecha = a_utc(datetime.fromisoformat(data.fecha))
        except ValueError:
            raise HTTPException(400, "Fecha inválida, use ISO")
    c.contra_respuesta_eps = data.texto.strip()
    c.fecha_contra_respuesta_eps = fecha
    if (c.estado_bilateral or "PROGRAMADA") == "PROGRAMADA":
        c.estado_bilateral = "EPS_RESPONDIO"
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="CONCILIACION_CONTRA_EPS",
        tabla="conciliaciones",
        registro_id=conciliacion_id,
        detalle=f"EPS respondió {fecha.date()} — {len(data.texto)} chars",
    )
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
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="CONCILIACION_POSTURA_HUS",
        tabla="conciliaciones",
        registro_id=conciliacion_id,
        detalle=f"Postura HUS registrada · ${c.valor_ratificado_hus or 0:,.0f}",
    )
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
        fecha_acta = a_utc(datetime.fromisoformat(data.fecha_acta))
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
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="CONCILIACION_ACTA",
        tabla="conciliaciones",
        registro_id=conciliacion_id,
        campo="acta_numero",
        valor_nuevo=c.acta_numero,
        detalle=f"Acta {c.acta_numero} · {c.resultado} · ${c.valor_conciliado:,.0f}",
    )
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
  <div class="meta">Acta N° <b>{c.acta_numero or "—"}</b> · Expediente Glosa #{c.glosa_id}</div>
</div>

<h2>1. Partes intervinientes</h2>
<div class="row"><b>Por la IPS:</b> <span>{(c.participantes_hus or "ESE HUS — Cartera / Glosas").strip()}</span></div>
<div class="row"><b>Por la EPS:</b> <span>{(c.participantes_eps or (glosa.eps if glosa else "—")).strip()}</span></div>
<div class="row"><b>Lugar de audiencia:</b> <span>{c.lugar or "—"}</span></div>
<div class="row"><b>Fecha audiencia:</b> <span>{_fmt_dt(c.fecha_audiencia)}</span></div>

<h2>2. Glosa objeto de conciliación</h2>
<div class="row"><b>EPS:</b> <span>{glosa.eps if glosa else "—"}</span></div>
<div class="row"><b>Paciente:</b> <span>{glosa.paciente if glosa else "—"}</span></div>
<div class="row"><b>Factura:</b> <span>{glosa.factura if glosa else "—"}</span></div>
<div class="row"><b>Código glosa:</b> <span>{glosa.codigo_glosa if glosa else "—"}</span></div>
<div class="row"><b>Valor objetado:</b> <span>{_cop(glosa.valor_objetado if glosa else 0)}</span></div>

<h2>3. Contra-respuesta de la EPS</h2>
<div class="box">{(c.contra_respuesta_eps or "No registrada").strip()}</div>
<div class="row"><b>Fecha contra-respuesta:</b> <span>{_fmt_d(c.fecha_contra_respuesta_eps)}</span></div>

<h2>4. Postura de la IPS</h2>
<div class="box">{(c.postura_hus or "No registrada").strip()}</div>
<div class="row"><b>Valor ratificado por la IPS:</b> <span>{_cop(c.valor_ratificado_hus)}</span></div>

<h2>5. Resolución de la conciliación</h2>
<div class="resumen">
  <div class="row"><b>Resultado:</b> <span><b>{(c.resultado or "PENDIENTE").replace("_", " ")}</b></span></div>
  <div class="row"><b>Valor conciliado final:</b> <span><b>{_cop(c.valor_conciliado)}</b></span></div>
  <div class="row"><b>Siguiente paso:</b> <span>{c.siguiente_paso or "—"}</span></div>
  <div class="row"><b>Fecha firma del acta:</b> <span>{_fmt_d(c.fecha_acta)}</span></div>
</div>

<h2>6. Observaciones y acuerdos</h2>
<div class="box">{(c.observaciones or "—").strip()}</div>

<p style="margin-top:30px;font-size:10pt;color:#475569">
El presente documento se suscribe en cumplimiento del artículo 56 de la Ley 1438 de 2011,
el Decreto 4747 de 2007 (artículo 20) y la Resolución 2175 de 2015. De no lograrse acuerdo,
las partes podrán elevar el conflicto ante la Superintendencia Nacional de Salud según el
artículo 126 de la Ley 1438 de 2011.
</p>

<div class="firmas">
  <div class="firma">
    <div><b>Representante ESE HUS</b></div>
    <div>{(c.participantes_hus or "—").split(",")[0].strip()[:60]}</div>
  </div>
  <div class="firma">
    <div><b>Representante EPS</b></div>
    <div>{(c.participantes_eps or "—").split(",")[0].strip()[:60]}</div>
  </div>
</div>

<div class="watermark">Generado {ahora_utc().strftime("%Y-%m-%d %H:%M UTC")} · {current_user.email}</div>
</body></html>"""
    return HTMLResponse(content=html)


@router.post("/acta-sinac/pdf")
def pdf_acta_sinac(
    payload: ActaSinacInput,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Genera el acta de conciliación en formato SINAC (multi-glosa) como
    HTML imprimible. Replica la estructura del Excel ACTA_SINAC_N_XXX que
    el equipo de cartera diligencia en cada audiencia: encabezado NIT +
    Razón Social, tabla de N glosas con tipo/tipificación/cod/descripción/
    valores y firmas HUS-EPS al pie. El navegador puede imprimirlo a PDF
    con Ctrl+P.
    """
    from fastapi.responses import HTMLResponse

    def _cop(v: float) -> str:
        try:
            return "$" + f"{float(v or 0):,.0f}".replace(",", ".")
        except Exception:
            return "$0"

    def _fmt_fecha(s: Optional[str]) -> str:
        if not s:
            return "—"
        try:
            d = datetime.fromisoformat(s.replace("Z", ""))
            return d.strftime("%d/%m/%Y")
        except Exception:
            return str(s)

    fecha_acta_str = (
        _fmt_fecha(payload.fecha_acta) if payload.fecha_acta else ahora_utc().strftime("%d/%m/%Y")
    )

    total_factura = sum((f.valor_factura or 0.0) for f in payload.filas)
    total_glosa_inicial = sum((f.valor_glosa_inicial or 0.0) for f in payload.filas)
    total_pendiente = sum((f.valor_pendiente_conciliar or 0.0) for f in payload.filas)
    total_acepta_ips = sum((f.valor_acepta_ips or 0.0) for f in payload.filas)

    filas_html = ""
    for i, f in enumerate(payload.filas, start=1):
        desc = (f.descripcion_glosa or "").replace("\n", " ").strip()
        filas_html += (
            "<tr>"
            f"<td class='c'>{i}</td>"
            f"<td>{(f.radicado_acta_entidad or '-')}</td>"
            f"<td>{f.numero_factura or '—'}</td>"
            f"<td>{_fmt_fecha(f.fecha_factura)}</td>"
            f"<td>{f.tipo_glosa or 'ADMINISTRATIVA'}</td>"
            f"<td>{f.tipificacion or '—'}</td>"
            f"<td>{f.cod_glosa or '—'}</td>"
            f"<td class='desc'>{desc}</td>"
            f"<td class='r'>{_cop(f.valor_factura)}</td>"
            f"<td class='r'>{_cop(f.valor_glosa_inicial)}</td>"
            f"<td class='r'>{_cop(f.valor_pendiente_conciliar)}</td>"
            f"<td class='r'>{_cop(f.valor_acepta_ips)}</td>"
            "</tr>"
        )

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Acta SINAC N° {payload.acta_numero}</title>
<style>
  @page {{ size: Letter landscape; margin: 1.2cm 1cm 1.2cm 1cm; }}
  body {{ font-family: Arial, sans-serif; color: #0f172a; font-size: 9pt; line-height: 1.35; }}
  .hdr {{ text-align: center; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 2px solid #0b5d8a; }}
  .hdr .marca {{ color: #64748b; font-size: 8pt; letter-spacing: .4px; }}
  .hdr h1 {{ margin: 6px 0 2px; font-size: 13pt; color: #0b5d8a; }}
  .hdr .acta {{ font-weight: 700; color: #b91c1c; font-size: 10pt; margin-top: 2px; }}
  .info {{ width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 9pt; }}
  .info td {{ padding: 4px 8px; border: 1px solid #cbd5e1; }}
  .info .lbl {{ background: #f1f5f9; font-weight: 700; color: #334155; width: 14%; }}
  .info .resumen {{ background: #ecfeff; }}
  .tabla {{ width: 100%; border-collapse: collapse; font-size: 8pt; margin: 4px 0 12px; }}
  .tabla th {{ background: #0b5d8a; color: white; padding: 5px 4px; border: 1px solid #0b5d8a; font-size: 7.5pt; text-transform: uppercase; }}
  .tabla td {{ padding: 4px 5px; border: 1px solid #cbd5e1; vertical-align: top; }}
  .tabla td.c {{ text-align: center; font-weight: 700; }}
  .tabla td.r {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .tabla td.desc {{ font-size: 7.5pt; max-width: 280px; }}
  .total {{ background: #fef3c7; font-weight: 700; }}
  .obs {{ border: 1px solid #cbd5e1; padding: 10px 12px; min-height: 60px; margin: 6px 0 14px; background: #f8fafc; white-space: pre-wrap; }}
  .clausula {{ font-size: 8pt; color: #475569; margin: 14px 0 20px; text-align: justify; padding: 8px 12px; background: #fef2f2; border-left: 3px solid #b91c1c; }}
  .firmas {{ display: flex; gap: 30px; margin-top: 30px; }}
  .firma {{ flex: 1; }}
  .firma .titulo {{ background: #0b5d8a; color: white; padding: 5px 8px; font-weight: 700; font-size: 9pt; text-align: center; }}
  .firma .campo {{ border: 1px solid #cbd5e1; padding: 5px 8px; font-size: 9pt; }}
  .firma .lbl {{ font-weight: 700; color: #334155; display: inline-block; min-width: 70px; }}
  button.noprint {{ position: fixed; top: 10px; right: 10px; padding: 8px 14px; background: #0b5d8a; color: white; border: 0; border-radius: 6px; cursor: pointer; z-index: 10; }}
  @media print {{ button.noprint {{ display: none; }} }}
</style>
</head><body>
<button class="noprint" onclick="window.print()">Imprimir / Guardar PDF</button>

<div class="hdr">
  <div class="marca">SINAC S.C — ESE HOSPITAL UNIVERSITARIO DE SANTANDER · NIT 900.006.037-4</div>
  <h1>FORMATO DE ACTA DE CONCILIACIÓN DE CUENTAS MÉDICAS</h1>
  <div class="acta">ACTA SINAC N° {payload.acta_numero} · Fecha: {fecha_acta_str}</div>
</div>

<table class="info">
  <tr>
    <td class="lbl">NIT:</td><td>{payload.nit}</td>
    <td class="lbl">Razón Social:</td><td colspan="3">{payload.razon_social}</td>
  </tr>
  <tr>
    <td class="lbl">Período:</td><td>{payload.periodo}</td>
    <td class="lbl">Cantidad facturas:</td><td>{len(payload.filas)}</td>
    <td class="lbl resumen">Valor a conciliar:</td><td class="resumen"><b>{_cop(total_pendiente)}</b></td>
  </tr>
  <tr>
    <td class="lbl resumen">Valor acepta IPS:</td><td class="resumen"><b>{_cop(total_acepta_ips)}</b></td>
    <td class="lbl">Valor facturas:</td><td>{_cop(total_factura)}</td>
    <td class="lbl">Valor glosado inicial:</td><td>{_cop(total_glosa_inicial)}</td>
  </tr>
</table>

<table class="tabla">
  <thead>
    <tr>
      <th>Ítem</th>
      <th>Radicado/Acta entidad</th>
      <th>N° Factura</th>
      <th>Fecha factura</th>
      <th>Tipo glosa</th>
      <th>Tipificación</th>
      <th>Cód. glosa</th>
      <th>Descripción glosa</th>
      <th>Valor factura</th>
      <th>Valor glosa inicial</th>
      <th>Valor pendiente conciliar</th>
      <th>Valor acepta IPS</th>
    </tr>
  </thead>
  <tbody>
    {filas_html}
    <tr class="total">
      <td colspan="8" class="r">TOTAL</td>
      <td class="r">{_cop(total_factura)}</td>
      <td class="r">{_cop(total_glosa_inicial)}</td>
      <td class="r">{_cop(total_pendiente)}</td>
      <td class="r">{_cop(total_acepta_ips)}</td>
    </tr>
  </tbody>
</table>

<div><b>Observaciones:</b></div>
<div class="obs">{(payload.observaciones or "—").strip()}</div>

<div class="clausula">
  Esta acta presta mérito ejecutivo para todos los efectos civiles, en el sentido del Art. 422 del Código General del
  Proceso (Ley 1564 de 2012) y el Art. 56 de la Ley 1438 de 2011. Las partes reconocen el contenido aquí consignado
  como una expresión consensuada y definitiva sobre los conceptos conciliados. De no lograrse acuerdo en alguno de los
  ítems, las partes podrán elevar el conflicto ante la Superintendencia Nacional de Salud (Art. 126 Ley 1438/2011).
</div>

<div class="firmas">
  <div class="firma">
    <div class="titulo">POR LA ENTIDAD PAGADORA (EPS)</div>
    <div class="campo"><span class="lbl">Nombre:</span> {payload.firmante_eps_nombre or "____________________"}</div>
    <div class="campo"><span class="lbl">Cargo:</span> {payload.firmante_eps_cargo or "____________________"}</div>
    <div class="campo"><span class="lbl">Correo:</span> {payload.firmante_eps_correo or "____________________"}</div>
    <div class="campo" style="margin-top:30px;text-align:center;border-top:1px solid #334155;padding-top:6px"><b>FIRMA</b></div>
  </div>
  <div class="firma">
    <div class="titulo">POR LA IPS (SINAC S.C — ESE HUS)</div>
    <div class="campo"><span class="lbl">Nombre:</span> {payload.firmante_hus_nombre or current_user.nombre or "____________________"}</div>
    <div class="campo"><span class="lbl">Cargo:</span> {payload.firmante_hus_cargo or "TÉCNICO DE GLOSAS Y DEVOLUCIONES"}</div>
    <div class="campo"><span class="lbl">Correo:</span> {payload.firmante_hus_correo or current_user.email or "____________________"}</div>
    <div class="campo" style="margin-top:30px;text-align:center;border-top:1px solid #334155;padding-top:6px"><b>FIRMA</b></div>
  </div>
</div>

</body></html>"""
    return HTMLResponse(content=html)


# ─── El acta que se trabaja en Excel: revisar, optimizar e imprimir ──────
# La mesa diligencia un Excel (formato ACTA SINAC). Estos tres endpoints lo
# reciben tal cual: «revisar» dice qué no cuadra, «optimizar» devuelve el
# mismo libro con resultado por línea + hoja REVISION + indicadores, y
# «pdf» arma el acta firmable. Lo escrito por el auditor nunca se toca.

_MAX_BYTES_ACTA = 30_000_000


async def _leer_upload_acta(archivo: UploadFile) -> tuple[bytes, bool]:
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".xlsm", ".xlsx")):
        raise HTTPException(400, "El acta debe ser el Excel de la mesa (.xlsm o .xlsx)")
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío")
    if len(contenido) > _MAX_BYTES_ACTA:
        raise HTTPException(413, "El archivo supera los 30 MB")
    return contenido, nombre.endswith(".xlsm")


def _acta_o_400(contenido: bytes):
    from app.services import acta_conciliacion_excel as acta_x

    try:
        return acta_x.leer_acta(contenido)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "No se pudo leer el Excel: ¿es el formato del acta de la mesa?")


@router.post("/acta-excel/revisar")
async def acta_excel_revisar(
    archivo: UploadFile = File(...),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Cuadra el acta sin producir archivos: qué reparte de más, qué
    pendiente no coincide, qué línea quedó conciliada sin texto. Es el
    «ver qué sale» antes de descargar nada."""
    from app.services import acta_conciliacion_excel as acta_x

    contenido, _ = await _leer_upload_acta(archivo)
    acta = _acta_o_400(contenido)
    resumen = acta_x.revisar(acta)
    return {
        "entidad": acta.razon_social,
        "nit": acta.nit,
        "periodo": acta.periodo,
        **resumen,
        # Los primeros hallazgos alcanzan para saber por dónde empezar;
        # el detalle completo va en la hoja REVISION del Excel optimizado.
        "hallazgos": resumen["hallazgos"][:60],
    }


@router.post("/acta-excel/optimizar")
async def acta_excel_optimizar(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Devuelve el MISMO libro (macros, logos y hojas intactas) con el
    resultado de cada línea, la hoja REVISION con los hallazgos y los
    indicadores recalculados."""
    import io as _io
    import json as _json

    from fastapi.responses import StreamingResponse

    from app.services import acta_conciliacion_excel as acta_x

    contenido, es_xlsm = await _leer_upload_acta(archivo)
    _acta_o_400(contenido)  # valida formato antes de trabajar
    try:
        salida, resumen = acta_x.optimizar(contenido, es_xlsm=es_xlsm)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "No se pudo optimizar el acta: revisar el formato del libro.")

    # Expediente: queda constancia de quién pasó el acta y cómo cuadró.
    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="ACTA_EXCEL_OPTIMIZADA",
            tabla="conciliaciones",
            campo="LISTA" if resumen["lista_para_firmar"] else "CON_HALLAZGOS",
            valor_nuevo=(archivo.filename or "acta")[:200],
            detalle=_json.dumps(
                {
                    "resumen": {
                        "facturas": resumen["facturas"],
                        "lineas": resumen["lineas"],
                        "glosado": resumen["glosado"],
                        "levanta_entidad": resumen["levanta_entidad"],
                        "ratificado": resumen["ratificado"],
                        "pendiente": resumen["pendiente_calculado"],
                        "hallazgos": len(resumen["hallazgos"]),
                    }
                },
                ensure_ascii=False,
            )[:1900],
        )
        db.commit()
    except Exception:
        pass

    ext = "xlsm" if es_xlsm else "xlsx"
    media = (
        "application/vnd.ms-excel.sheet.macroEnabled.12"
        if es_xlsm
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    from app.api.routers.automatizaciones import _nombre_para_header

    base = _nombre_para_header((archivo.filename or "acta").rsplit(".", 1)[0][:80])
    return StreamingResponse(
        _io.BytesIO(salida),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{base}_OPTIMIZADA.{ext}"',
            "X-Hallazgos": str(len(resumen["hallazgos"])),
            "X-Lista-Para-Firmar": "1" if resumen["lista_para_firmar"] else "0",
        },
    )


@router.post("/acta-excel/pdf")
async def acta_excel_pdf(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """El acta firmable, armada desde el Excel de la mesa: encabezado de la
    entidad, las líneas con su resultado, totales, cláusula de mérito
    ejecutivo y las firmas leídas del propio libro. El navegador la imprime
    a PDF con Ctrl+P."""
    import json as _json

    from fastapi.responses import HTMLResponse

    from app.services import acta_conciliacion_excel as acta_x

    contenido, _ = await _leer_upload_acta(archivo)
    acta = _acta_o_400(contenido)
    resumen = acta_x.revisar(acta)
    html_impreso = acta_x.html_acta(acta, resumen)

    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="ACTA_EXCEL_PDF",
            tabla="conciliaciones",
            campo="LISTA" if resumen["lista_para_firmar"] else "CON_HALLAZGOS",
            valor_nuevo=(archivo.filename or "acta")[:200],
            detalle=_json.dumps(
                {
                    "entidad": acta.razon_social,
                    "facturas": resumen["facturas"],
                    "glosado": resumen["glosado"],
                    "hallazgos": len(resumen["hallazgos"]),
                },
                ensure_ascii=False,
            )[:1900],
        )
        db.commit()
    except Exception:
        pass

    return HTMLResponse(content=html_impreso)
