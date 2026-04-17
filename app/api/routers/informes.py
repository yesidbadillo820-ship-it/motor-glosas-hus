"""Informes ejecutivos PDF para Gerencia y Junta Directiva."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord, ConciliacionRecord
from app.api.deps import get_usuario_actual
from app.repositories.glosa_repository import GlosaRepository
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/informes", tags=["informes"])


def _cop(v) -> str:
    try:
        return "$" + f"{float(v or 0):,.0f}".replace(",", ".")
    except Exception:
        return str(v or "—")


@router.get("/ejecutivo-mensual")
def ejecutivo_mensual(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Genera HTML imprimible (guardar como PDF desde el navegador) con el
    informe ejecutivo del mes indicado. Por defecto el mes actual."""
    now = datetime.utcnow()
    year = year or now.year
    month = month or now.month
    inicio = datetime(year, month, 1)
    # Fin = primer día del mes siguiente
    if month == 12:
        fin = datetime(year + 1, 1, 1)
    else:
        fin = datetime(year, month + 1, 1)

    # Totales del mes
    base_q = db.query(GlosaRecord).filter(
        GlosaRecord.creado_en >= inicio, GlosaRecord.creado_en < fin
    )
    total = base_q.count()
    valores = db.query(
        func.sum(GlosaRecord.valor_objetado),
        func.sum(GlosaRecord.valor_aceptado),
    ).filter(
        GlosaRecord.creado_en >= inicio, GlosaRecord.creado_en < fin
    ).first()
    v_obj = float(valores[0] or 0)
    v_ac = float(valores[1] or 0)
    v_rec = v_obj - v_ac
    tasa = round((v_rec / v_obj * 100) if v_obj > 0 else 0, 1)

    # Top 5 EPS
    top_eps = (
        db.query(
            GlosaRecord.eps,
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        )
        .filter(GlosaRecord.creado_en >= inicio, GlosaRecord.creado_en < fin)
        .group_by(GlosaRecord.eps)
        .order_by(func.sum(GlosaRecord.valor_objetado).desc())
        .limit(5)
        .all()
    )

    # Top 5 causales (prefijo código)
    from sqlalchemy import case
    tipo_case = case(
        (GlosaRecord.codigo_glosa.like('TA%'), 'TARIFAS'),
        (GlosaRecord.codigo_glosa.like('SO%'), 'SOPORTES'),
        (GlosaRecord.codigo_glosa.like('AU%'), 'AUTORIZACIÓN'),
        (GlosaRecord.codigo_glosa.like('CO%'), 'COBERTURA'),
        (GlosaRecord.codigo_glosa.like('PE%'), 'PERTINENCIA'),
        (GlosaRecord.codigo_glosa.like('CL%'), 'PERTINENCIA'),
        (GlosaRecord.codigo_glosa.like('FA%'), 'FACTURACIÓN'),
        (GlosaRecord.codigo_glosa.like('IN%'), 'INSUMOS'),
        (GlosaRecord.codigo_glosa.like('ME%'), 'MEDICAMENTOS'),
        else_='OTROS',
    )
    top_causales = (
        db.query(
            tipo_case.label("tipo"),
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
        )
        .filter(GlosaRecord.creado_en >= inicio, GlosaRecord.creado_en < fin)
        .group_by(tipo_case)
        .order_by(func.sum(GlosaRecord.valor_objetado).desc())
        .limit(5)
        .all()
    )

    # Tendencia 6 meses (incluyendo el actual)
    meses_atras = 5
    inicio_tendencia = datetime(year, month, 1) - timedelta(days=meses_atras * 32)
    tendencia = (
        db.query(
            func.extract('year', GlosaRecord.creado_en).label('y'),
            func.extract('month', GlosaRecord.creado_en).label('m'),
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        )
        .filter(GlosaRecord.creado_en >= inicio_tendencia, GlosaRecord.creado_en < fin)
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )

    # Conciliaciones del mes
    conc_total = db.query(ConciliacionRecord).filter(
        ConciliacionRecord.creado_en >= inicio, ConciliacionRecord.creado_en < fin
    ).count()
    conc_acuerdo = db.query(ConciliacionRecord).filter(
        ConciliacionRecord.creado_en >= inicio, ConciliacionRecord.creado_en < fin,
        ConciliacionRecord.resultado == "ACUERDO_TOTAL"
    ).count()

    # Recomendaciones automáticas básicas
    recomendaciones = []
    if top_eps:
        peor = None
        for r in top_eps:
            obj = float(r[2] or 0)
            ace = float(r[3] or 0)
            if obj > 0:
                exito = (obj - ace) / obj * 100
                if peor is None or exito < peor[1]:
                    peor = (r[0], exito, int(r[1] or 0))
        if peor and peor[1] < 50 and peor[2] >= 3:
            recomendaciones.append(
                f"Baja tasa de éxito con {peor[0]} ({peor[1]:.0f}%). Revisar contrato y plantillas."
            )
    if tasa < 40 and total >= 5:
        recomendaciones.append(
            f"Tasa global del mes ({tasa}%) por debajo del objetivo 60%. "
            "Reforzar revisión por coordinador antes de radicar."
        )
    if tasa > 75:
        recomendaciones.append(
            f"Tasa global excelente ({tasa}%). Documentar mejores prácticas del mes."
        )
    if not recomendaciones:
        recomendaciones.append("Desempeño operativo dentro de parámetros normales.")

    meses_esp = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                 "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
    titulo_mes = f"{meses_esp[month-1]} {year}"

    # Registrar auditoría
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="INFORME_EJECUTIVO",
        tabla="historial",
        detalle=f"Informe {titulo_mes}",
    )

    # Render HTML
    def _tr_eps(r):
        obj = float(r[2] or 0)
        ace = float(r[3] or 0)
        rec = obj - ace
        ex = (rec / obj * 100) if obj > 0 else 0
        return (
            f"<tr><td>{r[0] or '—'}</td><td class='num'>{int(r[1] or 0)}</td>"
            f"<td class='num'>{_cop(obj)}</td><td class='num'>{_cop(rec)}</td>"
            f"<td class='num'>{ex:.1f}%</td></tr>"
        )

    def _tr_causal(r):
        return (
            f"<tr><td>{r[0]}</td><td class='num'>{int(r[1] or 0)}</td>"
            f"<td class='num'>{_cop(float(r[2] or 0))}</td></tr>"
        )

    def _tr_mes(r):
        y = int(r[0])
        m = int(r[1])
        obj = float(r[3] or 0)
        ace = float(r[4] or 0)
        rec = obj - ace
        return (
            f"<tr><td>{meses_esp[m-1][:3]} {y}</td><td class='num'>{int(r[2] or 0)}</td>"
            f"<td class='num'>{_cop(obj)}</td><td class='num'>{_cop(rec)}</td></tr>"
        )

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Informe Ejecutivo {titulo_mes}</title>
<style>
  @page {{ size: Letter; margin: 2cm 1.8cm; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; font-size: 10.5pt; line-height: 1.55; }}
  h1, h2, h3 {{ color: #0b5d8a; }}
  .hdr {{ text-align: center; border-bottom: 3px double #0b5d8a; padding-bottom: 14px; margin-bottom: 24px; }}
  .hdr h1 {{ margin: 4px 0 6px; font-size: 17pt; letter-spacing: .3px; }}
  .hdr .inst {{ font-size: 9pt; color: #64748b; letter-spacing: .5px; }}
  .hdr .mes {{ font-size: 13pt; color: #047857; font-weight: 700; margin-top: 4px; }}
  h2 {{ font-size: 13pt; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-top: 22px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0 4px; }}
  .kpi {{ background: linear-gradient(135deg,#ecfeff,#f0fdf4); border: 1px solid #bae6fd; border-radius: 8px; padding: 10px 14px; }}
  .kpi .l {{ font-size: 8.5pt; color: #64748b; text-transform: uppercase; letter-spacing: .4px; font-weight: 600; }}
  .kpi .n {{ font-size: 15pt; font-weight: 700; color: #0b5d8a; margin-top: 4px; }}
  .kpi .s {{ font-size: 8.5pt; color: #047857; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 4px; font-size: 10pt; }}
  th, td {{ padding: 7px 9px; border-bottom: 1px solid #e2e8f0; text-align: left; }}
  th {{ background: #0b5d8a; color: white; font-size: 9pt; font-weight: 600; letter-spacing: .3px; text-transform: uppercase; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .recos {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 6px; margin: 12px 0; }}
  .recos h3 {{ margin: 0 0 8px; font-size: 11pt; color: #92400e; }}
  .recos li {{ margin: 4px 0; font-size: 10pt; }}
  .foot {{ margin-top: 30px; font-size: 9pt; color: #64748b; border-top: 1px solid #cbd5e1; padding-top: 10px; display: flex; justify-content: space-between; }}
  button.noprint {{ position: fixed; top: 12px; right: 12px; padding: 8px 14px; background: #0b5d8a; color: white; border: 0; border-radius: 6px; cursor: pointer; z-index: 10; box-shadow: 0 2px 4px rgba(0,0,0,.15); }}
  @media print {{ button.noprint {{ display: none; }} }}
</style></head>
<body>
<button class="noprint" onclick="window.print()">🖨️ Imprimir / Guardar PDF</button>

<div class="hdr">
  <div class="inst">ESE HOSPITAL UNIVERSITARIO DE SANTANDER — NIT 900.006.037-4</div>
  <h1>Informe Ejecutivo de Glosas</h1>
  <div class="mes">{titulo_mes}</div>
  <div style="font-size:9pt;color:#64748b;margin-top:4px">Generado {now.strftime('%Y-%m-%d %H:%M UTC')} · {current_user.email}</div>
</div>

<h2>1. Resumen del mes</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="l">Glosas procesadas</div><div class="n">{total:,}</div></div>
  <div class="kpi"><div class="l">Valor objetado</div><div class="n">{_cop(v_obj)}</div></div>
  <div class="kpi"><div class="l">Valor recuperado</div><div class="n">{_cop(v_rec)}</div><div class="s">defendido con éxito</div></div>
  <div class="kpi"><div class="l">Tasa de éxito</div><div class="n">{tasa}%</div></div>
</div>

<h2>2. Top 5 EPS por valor objetado</h2>
<table>
  <thead><tr><th>EPS / Entidad</th><th class="num">Glosas</th><th class="num">Objetado</th><th class="num">Recuperado</th><th class="num">Tasa éxito</th></tr></thead>
  <tbody>{''.join(_tr_eps(r) for r in top_eps) or '<tr><td colspan="5">Sin datos</td></tr>'}</tbody>
</table>

<h2>3. Top 5 causales</h2>
<table>
  <thead><tr><th>Causal</th><th class="num">Glosas</th><th class="num">Valor objetado</th></tr></thead>
  <tbody>{''.join(_tr_causal(r) for r in top_causales) or '<tr><td colspan="3">Sin datos</td></tr>'}</tbody>
</table>

<h2>4. Tendencia últimos 6 meses</h2>
<table>
  <thead><tr><th>Mes</th><th class="num">Glosas</th><th class="num">Objetado</th><th class="num">Recuperado</th></tr></thead>
  <tbody>{''.join(_tr_mes(r) for r in tendencia) or '<tr><td colspan="4">Sin datos</td></tr>'}</tbody>
</table>

<h2>5. Conciliaciones</h2>
<div class="kpi-grid" style="grid-template-columns:repeat(2,1fr)">
  <div class="kpi"><div class="l">Audiencias programadas</div><div class="n">{conc_total}</div></div>
  <div class="kpi"><div class="l">Acuerdos totales</div><div class="n">{conc_acuerdo}</div></div>
</div>

<h2>6. Recomendaciones</h2>
<div class="recos">
  <h3>⚡ Acciones sugeridas</h3>
  <ul>{''.join('<li>' + r + '</li>' for r in recomendaciones)}</ul>
</div>

<div class="foot">
  <span>Informe generado automáticamente · Motor Glosas HUS</span>
  <span>Página <span class="pageno"></span></span>
</div>
</body></html>"""

    return HTMLResponse(content=html)
