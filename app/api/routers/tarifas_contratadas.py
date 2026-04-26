"""Tarifas contratadas por EPS: endpoints admin para cargar/consultar
el catálogo de tarifas pactadas por contrato.

Flujo típico:
  1. COORDINADOR/SUPER_ADMIN sube CSV en /tarifas-contratadas/import-csv.
  2. El sistema parsea las filas y upsert-ea en tarifas_contratadas.
  3. Al analizar una glosa TA, el motor consulta buscar_tarifa(eps, cups)
     y decide si el valor facturado coincide con el pactado.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin, get_usuario_actual
from app.core.logging_utils import logger
from app.database import get_db
from app.models.db import TarifaContratadaRecord, UsuarioRecord
from app.repositories.audit_repository import AuditRepository
from app.services.tarifas_excel_parser import parsear_excel_tarifas

router = APIRouter(prefix="/tarifas-contratadas", tags=["Tarifas Contratadas"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _normalizar_valor(v: str) -> float:
    """Parsea un string con formato COP (puntos/comas/signo peso) a float."""
    if not v:
        return 0.0
    s = str(v).strip().replace("$", "").replace(" ", "")
    # Excel exporta "1.500.000" o "1,500,000" — normalizar a int
    # Si trae "," y "." → el último es decimal (formato europeo o US)
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # formato europeo: 1.500,00 → 1500.00
            s = s.replace(".", "").replace(",", ".")
        else:
            # formato US: 1,500.00 → 1500.00
            s = s.replace(",", "")
    else:
        # Solo puntos o solo comas: pueden ser miles o decimal.
        # Si hay UN solo punto/coma seguido de 1-2 digitos al final → decimal.
        # Caso contrario (múltiples o más de 2 dígitos tras) → miles.
        import re as _rex
        match_dec = _rex.match(r"^(\d+)[\.,](\d{1,2})$", s)
        if match_dec:
            s = f"{match_dec.group(1)}.{match_dec.group(2)}"
        else:
            s = s.replace(".", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parsear_fecha_opcional(v: str) -> Optional[datetime]:
    if not v or not v.strip():
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v.strip(), fmt)
        except ValueError:
            continue
    return None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
def listar_tarifas(
    eps: Optional[str] = Query(None, description="Filtrar por EPS (contains, case-insensitive)"),
    cups: Optional[str] = Query(None, description="Filtrar por código CUPS exacto"),
    solo_activas: bool = Query(True),
    limite: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista tarifas contratadas con filtros."""
    q = db.query(TarifaContratadaRecord)
    if solo_activas:
        q = q.filter(TarifaContratadaRecord.activa == 1)
    if eps:
        q = q.filter(TarifaContratadaRecord.eps.ilike(f"%{eps.strip()}%"))
    if cups:
        q = q.filter(TarifaContratadaRecord.codigo_cups == cups.strip())
    registros = q.order_by(TarifaContratadaRecord.eps, TarifaContratadaRecord.codigo_cups).limit(limite).all()
    return [
        {
            "id": r.id,
            "eps": r.eps,
            "contrato_numero": r.contrato_numero,
            "codigo_cups": r.codigo_cups,
            "descripcion": r.descripcion,
            "valor_pactado": r.valor_pactado,
            "modalidad": r.modalidad,
            "tipo_tarifa": r.tipo_tarifa or "VALOR_FIJO",
            "factor_ajuste": r.factor_ajuste or 0.0,
            "fuente_archivo": r.fuente_archivo,
            "vigencia_desde": r.vigencia_desde.isoformat() if r.vigencia_desde else None,
            "vigencia_hasta": r.vigencia_hasta.isoformat() if r.vigencia_hasta else None,
            "creado_en": r.creado_en.isoformat() if r.creado_en else None,
            "creado_por": r.creado_por,
            "activa": bool(r.activa),
        }
        for r in registros
    ]


@router.get("/buscar")
def buscar_tarifa(
    eps: str = Query(..., min_length=2),
    cups: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Busca una tarifa específica por EPS + CUPS. Usado por el motor de glosas.

    Retorna la tarifa activa más reciente si hay múltiples. Si no encuentra,
    retorna 404 para que el caller sepa que no hay dato pactado y caiga al
    flujo por defecto (tarifa IA / SOAT pleno).
    """
    q = (
        db.query(TarifaContratadaRecord)
        .filter(TarifaContratadaRecord.activa == 1)
        .filter(TarifaContratadaRecord.eps.ilike(f"%{eps.strip()}%"))
        .filter(TarifaContratadaRecord.codigo_cups == cups.strip())
        .order_by(TarifaContratadaRecord.creado_en.desc())
    )
    r = q.first()
    if not r:
        raise HTTPException(status_code=404, detail="Sin tarifa pactada para esa combinación EPS + CUPS")
    return {
        "id": r.id,
        "eps": r.eps,
        "contrato_numero": r.contrato_numero,
        "codigo_cups": r.codigo_cups,
        "descripcion": r.descripcion,
        "valor_pactado": r.valor_pactado,
        "modalidad": r.modalidad,
        "tipo_tarifa": r.tipo_tarifa or "VALOR_FIJO",
        "factor_ajuste": r.factor_ajuste or 0.0,
        "fuente_archivo": r.fuente_archivo,
    }


@router.post("/import-csv")
async def importar_csv(
    archivo: UploadFile = File(...),
    eps_default: Optional[str] = Query(None, description="EPS a asignar si la columna EPS no viene en el CSV"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Importa un CSV con tarifas pactadas. Columnas esperadas (case-insensitive,
    en cualquier orden):
        eps, contrato, cups, descripcion, valor, modalidad,
        vigencia_desde, vigencia_hasta

    Mínimo obligatorio: cups + valor (+ eps si no viene eps_default).
    Upsert: si ya existe (eps + cups + contrato) → actualiza; si no → crea.
    """
    if not archivo.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(400, "Solo se aceptan archivos .csv o .txt")
    contenido = await archivo.read()
    if len(contenido) > 5_000_000:
        raise HTTPException(413, "Archivo demasiado grande (>5 MB)")

    # Auto-detectar encoding: utf-8-sig (con BOM), utf-8, latin-1
    texto = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = contenido.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        texto = contenido.decode("utf-8", errors="ignore")

    # Auto-detectar separador: coma, punto y coma, tab
    primera = texto.split("\n", 1)[0] if texto else ""
    sep = ";" if primera.count(";") > primera.count(",") else ","
    if "\t" in primera and primera.count("\t") > primera.count(sep):
        sep = "\t"

    reader = csv.DictReader(io.StringIO(texto), delimiter=sep)
    if not reader.fieldnames:
        raise HTTPException(400, "CSV vacío o sin encabezados")

    # Mapa de nombres de columna → campo interno (case-insensitive)
    alias_map = {
        "eps": ["eps", "entidad", "pagador"],
        "contrato": ["contrato", "contrato_numero", "numero_contrato", "no. contrato"],
        "cups": ["cups", "codigo_cups", "codigo cups", "cups_cum", "cum"],
        "descripcion": ["descripcion", "descripción", "servicio", "nombre_servicio"],
        "valor": ["valor", "valor_pactado", "valor pactado", "precio", "tarifa"],
        "modalidad": ["modalidad", "tipo_tarifa", "metodo", "observacion", "observación"],
        "vigencia_desde": ["vigencia_desde", "desde", "fecha_desde", "inicio"],
        "vigencia_hasta": ["vigencia_hasta", "hasta", "fecha_hasta", "fin"],
    }
    # Normalizar headers del CSV
    headers_norm = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}
    col_map = {}
    for campo, aliases in alias_map.items():
        for a in aliases:
            if a in headers_norm:
                col_map[campo] = headers_norm[a]
                break

    # Validar que tengamos al menos cups + valor
    if "cups" not in col_map or "valor" not in col_map:
        raise HTTPException(
            400,
            f"El CSV debe tener al menos las columnas 'cups' y 'valor'. "
            f"Encabezados detectados: {list(headers_norm.keys())}"
        )
    if "eps" not in col_map and not eps_default:
        raise HTTPException(
            400,
            "El CSV no trae columna 'eps'. Pase eps_default=NOMBRE como query param."
        )

    fuente = archivo.filename[:300]
    creadas = 0
    actualizadas = 0
    errores: list[str] = []
    for idx, fila in enumerate(reader, start=2):  # start=2 porque fila 1 = encabezados
        try:
            cups_val = (fila.get(col_map["cups"]) or "").strip()
            if not cups_val:
                continue
            valor_raw = fila.get(col_map["valor"]) or ""
            valor = _normalizar_valor(valor_raw)
            if valor <= 0:
                errores.append(f"Fila {idx}: valor inválido '{valor_raw}' para CUPS {cups_val}")
                continue

            eps_val = ((fila.get(col_map["eps"]) if "eps" in col_map else "") or eps_default or "").strip()
            if not eps_val:
                errores.append(f"Fila {idx}: EPS vacía y sin eps_default")
                continue

            contrato_val = (fila.get(col_map.get("contrato", "")) or "").strip() if "contrato" in col_map else ""
            descripcion = (fila.get(col_map.get("descripcion", "")) or "").strip() if "descripcion" in col_map else ""
            modalidad = (fila.get(col_map.get("modalidad", "")) or "").strip() if "modalidad" in col_map else ""
            vig_desde = _parsear_fecha_opcional(fila.get(col_map.get("vigencia_desde", "")) or "") if "vigencia_desde" in col_map else None
            vig_hasta = _parsear_fecha_opcional(fila.get(col_map.get("vigencia_hasta", "")) or "") if "vigencia_hasta" in col_map else None

            # Upsert: buscar tarifa existente con (eps, cups, contrato)
            existente = (
                db.query(TarifaContratadaRecord)
                .filter(TarifaContratadaRecord.eps == eps_val)
                .filter(TarifaContratadaRecord.codigo_cups == cups_val)
                .filter(TarifaContratadaRecord.contrato_numero == (contrato_val or None))
                .first()
            )
            campos = dict(
                eps=eps_val,
                contrato_numero=contrato_val or None,
                codigo_cups=cups_val,
                descripcion=descripcion or None,
                valor_pactado=valor,
                modalidad=modalidad or None,
                tipo_tarifa="VALOR_FIJO",
                factor_ajuste=0.0,
                fuente_archivo=fuente,
                vigencia_desde=vig_desde,
                vigencia_hasta=vig_hasta,
                creado_por=current_user.email,
                activa=1,
            )
            if existente:
                for k, v in campos.items():
                    setattr(existente, k, v)
                actualizadas += 1
            else:
                db.add(TarifaContratadaRecord(**campos))
                creadas += 1
        except Exception as e:
            errores.append(f"Fila {idx}: {type(e).__name__}: {e}")
            continue

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error al guardar: {e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="IMPORTAR_TARIFAS",
        tabla="tarifas_contratadas",
        detalle=f"archivo={fuente} creadas={creadas} actualizadas={actualizadas} errores={len(errores)}",
    )

    logger.info(
        f"[TARIFAS] Import CSV '{fuente}' por {current_user.email}: "
        f"creadas={creadas} actualizadas={actualizadas} errores={len(errores)}"
    )
    return {
        "archivo": fuente,
        "creadas": creadas,
        "actualizadas": actualizadas,
        "errores": errores[:30],  # primeras 30 filas con error
        "total_errores": len(errores),
    }


@router.post("/import-excel")
async def importar_excel(
    archivo: UploadFile = File(...),
    eps_override: Optional[str] = Query(None, description="Nombre EPS (si Excel no lo trae claro)"),
    reemplazar: bool = Query(
        False,
        description=(
            "Si es true, elimina TODAS las tarifas activas existentes de la "
            "EPS antes de insertar las nuevas. Útil para renovaciones anuales "
            "de contrato o cuando el Excel anterior quedó mal."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Importa un Excel de tarifas contratadas (tipo Famisanar) con hasta 3 hojas:

    - **Anexo 3** — Servicios CUPS con fórmula SOAT ± % (tipo_tarifa=SOAT_PORCENTAJE)
    - **Anexo 3.1** — Medicamentos, valor fijo (tipo_tarifa=VALOR_FIJO)
    - **Anexo 3.2** — Suministros, valor fijo, con IVA opcional (tipo_tarifa=VALOR_FIJO)

    Auto-detecta EPS, nº de contrato y vigencia desde el encabezado de cada hoja.
    Upsert por (eps + cups + contrato). Si `reemplazar=true`, hace hard-delete
    de las existentes para la EPS antes de insertar.
    """
    if not archivo.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Solo se aceptan archivos .xlsx")
    contenido = await archivo.read()
    if len(contenido) > 20_000_000:
        raise HTTPException(413, "Archivo demasiado grande (>20 MB)")

    resultado = parsear_excel_tarifas(contenido, archivo.filename or "")
    if not resultado["filas"]:
        hojas_info = ", ".join(resultado.get("hojas_detectadas", [])) or "ninguna"
        err_info = ""
        if resultado["errores"]:
            err_info = f" Errores: {'; '.join(resultado['errores'][:2])}"
        raise HTTPException(
            400,
            f"No se detectaron tarifas en el Excel. Hojas reconocidas: {hojas_info}. "
            f"Verifica que las columnas incluyan CUPS y un campo de valor "
            f"(PRECIO DE REFERENCIA, TARIFA UNITARIA, CODIGO DEL PRESTADOR, etc.).{err_info}"
        )

    eps_val = eps_override or resultado.get("eps") or ""
    eps_val = eps_val.strip()
    if not eps_val:
        raise HTTPException(
            400,
            "No se pudo identificar la EPS en el Excel. Pase eps_override=NOMBRE como query param."
        )

    contrato_val = resultado.get("contrato") or None
    vig_desde = resultado.get("vigencia_desde")
    vig_hasta = resultado.get("vigencia_hasta")
    fuente = (archivo.filename or "famisanar.xlsx")[:300]

    # Reemplazar: hard-delete de todas las tarifas de la EPS antes de insertar.
    # Usa la misma comparación case-insensitive que la búsqueda del motor.
    eliminadas = 0
    if reemplazar:
        try:
            eliminadas = (
                db.query(TarifaContratadaRecord)
                .filter(TarifaContratadaRecord.eps.ilike(eps_val))
                .delete(synchronize_session=False)
            )
            db.commit()
            logger.warning(
                f"[TARIFAS] Reemplazar=true · eliminadas {eliminadas} tarifas "
                f"de eps='{eps_val}' por {current_user.email}"
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(500, f"Error al borrar tarifas previas: {e}")

    creadas = 0
    actualizadas = 0
    errores: list[str] = list(resultado.get("errores", []))

    for fila in resultado["filas"]:
        try:
            cups_val = (fila.get("codigo_cups") or "").strip()
            if not cups_val:
                continue
            existente = (
                db.query(TarifaContratadaRecord)
                .filter(TarifaContratadaRecord.eps == eps_val)
                .filter(TarifaContratadaRecord.codigo_cups == cups_val)
                .filter(TarifaContratadaRecord.contrato_numero == (contrato_val or None))
                .first()
            )
            campos = dict(
                eps=eps_val,
                contrato_numero=contrato_val,
                codigo_cups=cups_val,
                codigo_ips=(fila.get("codigo_ips") or None),
                descripcion=fila.get("descripcion"),
                valor_pactado=float(fila.get("valor_pactado") or 0.0),
                modalidad=fila.get("modalidad"),
                tipo_tarifa=fila.get("tipo_tarifa") or "VALOR_FIJO",
                factor_ajuste=float(fila.get("factor_ajuste") or 0.0),
                fuente_archivo=fuente,
                vigencia_desde=vig_desde,
                vigencia_hasta=vig_hasta,
                creado_por=current_user.email,
                activa=1,
            )
            if existente:
                for k, v in campos.items():
                    setattr(existente, k, v)
                actualizadas += 1
            else:
                db.add(TarifaContratadaRecord(**campos))
                creadas += 1
        except Exception as e:
            errores.append(f"CUPS {fila.get('codigo_cups')}: {type(e).__name__}: {e}")
            continue

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error al guardar: {e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="IMPORTAR_TARIFAS_EXCEL",
        tabla="tarifas_contratadas",
        detalle=(
            f"archivo={fuente} eps={eps_val} contrato={contrato_val} "
            f"hojas={','.join(resultado.get('hojas_detectadas', []))} "
            f"reemplazar={reemplazar} eliminadas={eliminadas} "
            f"creadas={creadas} actualizadas={actualizadas} errores={len(errores)}"
        ),
    )

    logger.info(
        f"[TARIFAS] Import Excel '{fuente}' eps={eps_val} por {current_user.email}: "
        f"reemplazar={reemplazar} eliminadas={eliminadas} hojas={resultado.get('hojas_detectadas')} "
        f"creadas={creadas} actualizadas={actualizadas} errores={len(errores)}"
    )
    return {
        "archivo": fuente,
        "eps_detectada": resultado.get("eps"),
        "eps_usada": eps_val,
        "contrato": contrato_val,
        "vigencia_desde": vig_desde.isoformat() if vig_desde else None,
        "vigencia_hasta": vig_hasta.isoformat() if vig_hasta else None,
        "hojas_detectadas": resultado.get("hojas_detectadas", []),
        "total_filas_leidas": len(resultado["filas"]),
        "reemplazar": reemplazar,
        "eliminadas": eliminadas,
        "creadas": creadas,
        "actualizadas": actualizadas,
        "errores": errores[:30],
        "total_errores": len(errores),
    }


@router.delete("/{tarifa_id}")
def eliminar_tarifa(
    tarifa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Soft-delete: marca tarifa como activa=0 (no borra el registro)."""
    r = db.query(TarifaContratadaRecord).filter(TarifaContratadaRecord.id == tarifa_id).first()
    if not r:
        raise HTTPException(404, "Tarifa no encontrada")
    r.activa = 0
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ELIMINAR_TARIFA",
        tabla="tarifas_contratadas",
        registro_id=tarifa_id,
        detalle=f"eps={r.eps} cups={r.codigo_cups} valor={r.valor_pactado}",
    )
    return {"message": "Tarifa archivada", "id": tarifa_id}


@router.get("/cobertura-eps")
def cobertura_eps(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R168 P1: cobertura del catálogo de tarifas por EPS.

    Diferente a /tarifas/stats (totales globales): aquí cuenta
    cuántas tarifas hay cargadas por cada EPS, ordenadas DESC.

    Útil para detectar:
      - EPS con catálogo robusto (>500 entradas)
      - EPS con catálogo magro
      - EPS sin tarifas cargadas (pero con contrato)

    Devuelve por EPS:
      - eps
      - tarifas_count
      - contratos_distintos (DISTINCT contrato_numero)
    """
    from app.models.db import TarifaContratadaRecord

    tarifas = db.query(TarifaContratadaRecord).all()

    por_eps: dict[str, dict] = {}
    for t in tarifas:
        eps = (t.eps or "").strip()
        if not eps:
            continue
        if eps not in por_eps:
            por_eps[eps] = {"count": 0, "contratos": set()}
        por_eps[eps]["count"] += 1
        if t.contrato_numero:
            por_eps[eps]["contratos"].add(t.contrato_numero)

    items = []
    for eps, b in por_eps.items():
        items.append({
            "eps": eps,
            "tarifas_count": b["count"],
            "contratos_distintos": len(b["contratos"]),
        })
    items.sort(key=lambda x: x["tarifas_count"], reverse=True)

    return {
        "total_eps_con_tarifas": len(items),
        "total_tarifas_cargadas": len(tarifas),
        "items": items,
    }


@router.get("/stats")
def stats_tarifas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Resumen: total activas, por EPS."""
    from sqlalchemy import func as _func
    total = db.query(TarifaContratadaRecord).filter(TarifaContratadaRecord.activa == 1).count()
    por_eps = (
        db.query(TarifaContratadaRecord.eps, _func.count(TarifaContratadaRecord.id).label("n"))
        .filter(TarifaContratadaRecord.activa == 1)
        .group_by(TarifaContratadaRecord.eps)
        .order_by(_func.count(TarifaContratadaRecord.id).desc())
        .all()
    )
    return {
        "total_activas": total,
        "por_eps": [{"eps": e, "cantidad": n} for e, n in por_eps],
    }
