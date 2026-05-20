"""Biblioteca de plantillas 'gold' — argumentos que ganaron la glosa.

Se guardan respuestas exitosas (glosa levantada por la EPS) y se usan como
few-shot examples al generar respuestas para nuevas glosas del mismo
(EPS, código). Efecto compuesto: cada victoria mejora las próximas.
"""

import csv
import hashlib
import io
import json
from datetime import UTC

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin, get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import GlosaRecord, PlantillaGoldRecord, UsuarioRecord
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/plantillas-gold", tags=["plantillas-gold"])


class PlantillaGoldInput(BaseModel):
    eps: str
    codigo_glosa: str
    titulo: str = Field(..., max_length=200)
    argumento: str
    tipo: str | None = None
    glosa_origen_id: int | None = None
    valor_recuperado: float | None = 0.0
    notas: str | None = None


class PlantillaGoldUpdate(BaseModel):
    titulo: str | None = None
    argumento: str | None = None
    notas: str | None = None
    activa: bool | None = None


@router.get("/")
def listar(
    eps: str | None = None,
    codigo: str | None = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista plantillas gold. Acepta filtros por EPS y código."""
    q = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.activa == 1)
    if eps:
        q = q.filter(PlantillaGoldRecord.eps.ilike(f"%{eps}%"))
    if codigo:
        q = q.filter(PlantillaGoldRecord.codigo_glosa == codigo.upper())
    q = q.order_by(PlantillaGoldRecord.usos.desc(), PlantillaGoldRecord.creado_en.desc())
    return [
        {
            "id": p.id,
            "eps": p.eps,
            "codigo_glosa": p.codigo_glosa,
            "tipo": p.tipo,
            "titulo": p.titulo,
            "argumento": p.argumento,
            "glosa_origen_id": p.glosa_origen_id,
            "valor_recuperado": float(p.valor_recuperado or 0),
            "usos": p.usos or 0,
            "creado_por": p.creado_por,
            "creado_en": p.creado_en.isoformat() if p.creado_en else None,
            "ultima_uso_en": p.ultima_uso_en.isoformat() if p.ultima_uso_en else None,
            "notas": p.notas,
        }
        for p in q.limit(500).all()
    ]


@router.post("/", status_code=201)
def crear(
    data: PlantillaGoldInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Guarda una respuesta exitosa como plantilla gold."""
    if len(data.argumento.strip()) < 50:
        raise HTTPException(400, "El argumento debe tener al menos 50 caracteres")

    rec = PlantillaGoldRecord(
        eps=(data.eps or "").upper().strip(),
        codigo_glosa=(data.codigo_glosa or "").upper().strip(),
        tipo=data.tipo,
        titulo=data.titulo.strip(),
        argumento=data.argumento.strip(),
        glosa_origen_id=data.glosa_origen_id,
        valor_recuperado=data.valor_recuperado or 0.0,
        notas=data.notas,
        creado_por=current_user.email,
        activa=1,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_CREAR",
        tabla="plantillas_gold",
        registro_id=rec.id,
        detalle=f"{rec.eps} · {rec.codigo_glosa} · {rec.titulo}",
    )
    return {"id": rec.id, "message": "Plantilla gold creada"}


@router.post("/desde-glosa/{glosa_id}")
def crear_desde_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea una plantilla gold a partir de una glosa que fue LEVANTADA o
    ACEPTADA por la EPS. Extrae el argumento del dictamen automáticamente."""
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(404, "Glosa no encontrada")
    if not g.dictamen:
        raise HTTPException(400, "La glosa no tiene dictamen generado")

    # Extraer argumento limpio del HTML
    import re as _re
    from html import unescape

    txt = _re.sub(r"<[^>]+>", " ", g.dictamen)
    txt = _re.sub(r"\s+", " ", unescape(txt)).strip()
    for marker in ("ARGUMENTACIÓN JURÍDICA", "RESPUESTA A GLOSA"):
        if marker in txt and len(txt.split(marker, 1)[0]) < 500:
            txt = txt.split(marker, 1)[1].strip()
            break
    for cierre in ("Nota: Generado con asistencia", "RESUMEN DE VALORES"):
        if cierre in txt:
            txt = txt.split(cierre)[0].strip()

    if len(txt) < 80:
        raise HTTPException(400, "No se pudo extraer un argumento suficientemente largo")

    titulo = f"{g.codigo_glosa or '—'} · {g.eps or '—'}"
    valor_recuperado = (g.valor_objetado or 0) - (g.valor_aceptado or 0)

    rec = PlantillaGoldRecord(
        eps=(g.eps or "").upper().strip(),
        codigo_glosa=(g.codigo_glosa or "").upper().strip(),
        tipo=None,
        titulo=titulo[:200],
        argumento=txt,
        glosa_origen_id=g.id,
        valor_recuperado=float(valor_recuperado),
        creado_por=current_user.email,
        activa=1,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_CREAR",
        tabla="plantillas_gold",
        registro_id=rec.id,
        detalle=f"desde glosa #{glosa_id} · ${valor_recuperado:,.0f} recuperados",
    )
    return {"id": rec.id, "message": "Plantilla gold creada desde glosa"}


@router.patch("/{plantilla_id}")
def actualizar(
    plantilla_id: int,
    data: PlantillaGoldUpdate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    p = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.id == plantilla_id).first()
    if not p:
        raise HTTPException(404, "Plantilla no encontrada")

    if data.titulo is not None:
        p.titulo = data.titulo.strip()[:200]
    if data.argumento is not None:
        p.argumento = data.argumento.strip()
    if data.notas is not None:
        p.notas = data.notas
    if data.activa is not None:
        p.activa = 1 if data.activa else 0
    db.commit()

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_UPDATE",
        tabla="plantillas_gold",
        registro_id=plantilla_id,
    )
    return {"id": plantilla_id, "message": "Plantilla actualizada"}


@router.delete("/{plantilla_id}")
def eliminar(
    plantilla_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    p = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.id == plantilla_id).first()
    if not p:
        raise HTTPException(404, "Plantilla no encontrada")
    db.delete(p)
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_DELETE",
        tabla="plantillas_gold",
        registro_id=plantilla_id,
    )
    return {"message": "Plantilla eliminada"}


def obtener_few_shot(
    db: Session, eps: str, codigo_glosa: str, limite: int = 2
) -> list[PlantillaGoldRecord]:
    """Obtiene las mejores plantillas gold para inyectar como ejemplo en el
    prompt.

    Prioridad:
      1. Match exacto (EPS + código).
      2. Mismo código CUPS en cualquier EPS.
      3. Plantillas genéricas del banco HUS (eps=GENERICO) cuyo código
         pertenece al mismo grupo familiar que el código de la glosa:
         prefijo de 2 letras (ej. "TA" de "TA0201") → busca "TA-G*".
    """
    if not codigo_glosa:
        return []
    codigo = codigo_glosa.upper().strip()
    eps_u = (eps or "").upper().strip()

    # 1. Match exacto primero
    exactas = (
        db.query(PlantillaGoldRecord)
        .filter(
            PlantillaGoldRecord.activa == 1,
            PlantillaGoldRecord.codigo_glosa == codigo,
            PlantillaGoldRecord.eps == eps_u,
        )
        .order_by(PlantillaGoldRecord.usos.desc())
        .limit(limite)
        .all()
    )
    if len(exactas) >= limite:
        return exactas

    # 2. Mismo código en otras EPS
    faltan = limite - len(exactas)
    ids_ya = [p.id for p in exactas]
    genericas = (
        db.query(PlantillaGoldRecord)
        .filter(
            PlantillaGoldRecord.activa == 1,
            PlantillaGoldRecord.codigo_glosa == codigo,
            ~PlantillaGoldRecord.id.in_(ids_ya) if ids_ya else True,
        )
        .order_by(PlantillaGoldRecord.usos.desc())
        .limit(faltan)
        .all()
    )
    resultado = exactas + genericas
    if len(resultado) >= limite:
        return resultado

    # 3. Fallback por familia: prefijo 2 letras → GENERICO + "XX-G*"
    faltan = limite - len(resultado)
    ids_ya = [p.id for p in resultado]
    prefijo = codigo[:2]  # "TA" de "TA0201", "SO" de "SO0501", etc.
    patron_familia = f"{prefijo}-G%"
    familia = (
        db.query(PlantillaGoldRecord)
        .filter(
            PlantillaGoldRecord.activa == 1,
            PlantillaGoldRecord.eps == "GENERICO",
            PlantillaGoldRecord.codigo_glosa.like(patron_familia),
            ~PlantillaGoldRecord.id.in_(ids_ya) if ids_ya else True,
        )
        .order_by(PlantillaGoldRecord.usos.desc())
        .limit(faltan)
        .all()
    )
    return resultado + familia


def marcar_usos(db: Session, plantilla_ids: list[int]):
    """Incrementa el contador de usos y actualiza ultima_uso_en."""
    if not plantilla_ids:
        return
    now = ahora_utc()
    db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.id.in_(plantilla_ids)).update(
        {
            PlantillaGoldRecord.usos: PlantillaGoldRecord.usos + 1,
            PlantillaGoldRecord.ultima_uso_en: now,
        },
        synchronize_session=False,
    )
    db.commit()


@router.get("/export.json")
def exportar_plantillas_gold(
    solo_activas: bool = True,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R77 P1: descarga las plantillas Gold como JSON (knowledge base).

    Útil para:
      - Migrar plantillas a otra instancia (ej. otra IPS de la red)
      - Backup específico del trabajo curado del equipo
      - Análisis externo de los argumentos ganadores

    Solo coordinador/admin (las plantillas son IP del equipo legal).
    """
    import json
    from datetime import datetime

    from fastapi.responses import Response

    q = db.query(PlantillaGoldRecord)
    if solo_activas:
        q = q.filter(PlantillaGoldRecord.activa == 1)
    plantillas = q.order_by(PlantillaGoldRecord.usos.desc()).all()

    payload = {
        "metadata": {
            "exportado_en": datetime.now(UTC).isoformat(),
            "exportado_por": current_user.email,
            "total": len(plantillas),
            "solo_activas": solo_activas,
        },
        "plantillas": [
            {
                "id": p.id,
                "eps": p.eps,
                "codigo_glosa": p.codigo_glosa,
                "tipo": p.tipo,
                "titulo": p.titulo,
                "argumento": p.argumento,
                "valor_recuperado": float(p.valor_recuperado or 0),
                "glosa_origen_id": p.glosa_origen_id,
                "creado_por": p.creado_por,
                "notas": p.notas,
                "usos": p.usos or 0,
                "activa": int(p.activa or 0),
                "creado_en": p.creado_en.isoformat() if p.creado_en else None,
            }
            for p in plantillas
        ],
    }
    fname = f"plantillas-gold-{datetime.now(UTC).strftime('%Y%m%d')}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/no-usadas")
def plantillas_no_usadas(
    dias: int = 90,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R127 P2: plantillas gold sin uso reciente (candidatas a archivar).

    Complementa /plantillas-gold/efectividad (top usadas) con la
    contraparte: cuáles NO se han usado en N días o nunca.

    Útil para curación de la biblioteca:
      - Plantillas viejas que ya no aplican
      - Plantillas mal taggeadas (nunca matchean glosas reales)

    Devuelve plantillas activas con:
      - usos = 0 (nunca usada) O ultima_uso_en < hoy - N dias

    Cada plantilla con: dias_sin_uso (None si nunca usada).
    Ordenado DESC por dias_sin_uso (los más obsoletos primero).
    """
    from datetime import timedelta

    plantillas = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.activa == 1).all()

    ahora = ahora_utc()
    corte = ahora - timedelta(days=int(dias))

    items = []
    for p in plantillas:
        ult = p.ultima_uso_en
        if ult is not None and ult.tzinfo is None:
            ult = ult.replace(tzinfo=UTC)

        # Nunca usada O sin actividad en >N días
        if ult is None or ult < corte:
            dias_sin = (ahora - ult).days if ult else None
            items.append(
                {
                    "id": p.id,
                    "titulo": p.titulo,
                    "eps": p.eps,
                    "codigo_glosa": p.codigo_glosa,
                    "usos": p.usos or 0,
                    "ultima_uso_en": ult.isoformat() if ult else None,
                    "dias_sin_uso": dias_sin,
                    "creado_en": (p.creado_en.isoformat() if p.creado_en else None),
                }
            )

    # nulls al final, los más antiguos arriba
    items.sort(
        key=lambda x: (x["dias_sin_uso"] is None, -(x["dias_sin_uso"] or 0)),
    )

    return {
        "umbral_dias": int(dias),
        "total_no_usadas": len(items),
        "nunca_usadas": sum(1 for it in items if it["usos"] == 0),
        "items": items,
    }


@router.get("/efectividad")
def plantillas_efectividad(
    min_usos: int = 1,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R107 P1: ranking de plantillas gold por efectividad real.

    Cruza PlantillaGoldRecord con GlosaRecord (vía glosa_origen_id)
    para mostrar qué plantillas vienen de glosas que efectivamente
    se LEVANTARON, y cuántas veces se han reusado.

    Útil para:
      - Identificar mejores prácticas (plantillas con muchos usos +
        glosa origen LEVANTADA = "gold real")
      - Detectar plantillas obsoletas (creadas pero nunca usadas)
      - Curación de la biblioteca

    Devuelve por plantilla activa (con >= min_usos):
      - id, titulo, eps, codigo_glosa
      - usos
      - glosa_origen_estado (LEVANTADA, ACEPTADA, etc.)
      - valor_recuperado_origen
      - es_gold_real (bool: usos>=3 Y origen=LEVANTADA)

    Ordenado DESC por usos.
    """
    plantillas = db.query(PlantillaGoldRecord).filter(PlantillaGoldRecord.activa == 1).all()

    items = []
    for p in plantillas:
        if (p.usos or 0) < min_usos:
            continue

        origen = None
        origen_estado = None
        valor_orig = 0.0
        if p.glosa_origen_id:
            origen = db.query(GlosaRecord).filter(GlosaRecord.id == p.glosa_origen_id).first()
            if origen:
                origen_estado = origen.estado
                valor_orig = float(origen.valor_recuperado or 0)

        es_gold_real = (p.usos or 0) >= 3 and (origen_estado or "").upper() == "LEVANTADA"

        items.append(
            {
                "id": p.id,
                "titulo": p.titulo,
                "eps": p.eps,
                "codigo_glosa": p.codigo_glosa,
                "usos": p.usos or 0,
                "glosa_origen_id": p.glosa_origen_id,
                "glosa_origen_estado": origen_estado,
                "valor_recuperado_origen": int(valor_orig),
                "ultima_uso_en": (p.ultima_uso_en.isoformat() if p.ultima_uso_en else None),
                "es_gold_real": es_gold_real,
            }
        )

    items.sort(key=lambda x: x["usos"], reverse=True)

    return {
        "total_evaluadas": len(items),
        "gold_reales": sum(1 for it in items if it["es_gold_real"]),
        "items": items,
    }


def _hash_plantilla(eps: str, codigo: str, argumento: str) -> str:
    """Hash determinístico para detectar duplicados en importación masiva.
    Normaliza eps + código + argumento (sin espacios redundantes ni case)."""
    import re as _re

    norm = " ".join((eps or "").upper().split())
    norm += "|" + " ".join((codigo or "").upper().split())
    arg_norm = _re.sub(r"\s+", " ", (argumento or "").strip())[:5000]
    norm += "|" + arg_norm
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


class PlantillaImportRow(BaseModel):
    """Una fila del payload de importación masiva."""

    eps: str
    codigo_glosa: str
    titulo: str = Field(..., max_length=200)
    argumento: str
    tipo: str | None = None
    valor_recuperado: float | None = 0.0
    notas: str | None = None


class PlantillaImportPayload(BaseModel):
    """Payload JSON para POST /plantillas-gold/importar-masivo (modo JSON)."""

    plantillas: list[PlantillaImportRow]


def _procesar_filas_importacion(
    db: Session,
    filas: list[dict],
    autor: str,
) -> dict:
    """Inserta plantillas en lote con detección de duplicados.

    Cada fila debe tener: eps, codigo_glosa, titulo, argumento.
    Opcional: tipo, valor_recuperado, notas.

    Devuelve resumen estructurado:
      {creadas: N, omitidas_duplicado: N, omitidas_error: N,
       errores: [{fila: i, razon: "..."}], ids_creadas: [...]}
    """
    creadas = 0
    duplicadas = 0
    errores: list[dict] = []
    ids: list[int] = []

    # Pre-cargar hashes existentes para detectar duplicados sin N queries
    hashes_existentes: set[str] = set()
    for p in db.query(PlantillaGoldRecord).all():
        hashes_existentes.add(_hash_plantilla(p.eps, p.codigo_glosa, p.argumento))

    for i, fila in enumerate(filas, start=1):
        try:
            eps = (fila.get("eps") or "").upper().strip()
            cod = (fila.get("codigo_glosa") or "").upper().strip()
            tit = (fila.get("titulo") or "").strip()
            arg = (fila.get("argumento") or "").strip()
            if not eps or not cod or not arg:
                errores.append({"fila": i, "razon": "eps/codigo_glosa/argumento requeridos"})
                continue
            if len(arg) < 50:
                errores.append({"fila": i, "razon": "argumento < 50 chars"})
                continue

            h = _hash_plantilla(eps, cod, arg)
            if h in hashes_existentes:
                duplicadas += 1
                continue

            try:
                valor = float(fila.get("valor_recuperado") or 0)
            except (TypeError, ValueError):
                valor = 0.0

            rec = PlantillaGoldRecord(
                eps=eps,
                codigo_glosa=cod,
                tipo=fila.get("tipo") or None,
                titulo=(tit or f"{cod} · {eps}")[:200],
                argumento=arg,
                valor_recuperado=valor,
                notas=fila.get("notas") or None,
                creado_por=autor,
                activa=1,
            )
            db.add(rec)
            db.flush()
            hashes_existentes.add(h)
            ids.append(rec.id)
            creadas += 1
        except Exception as e:
            errores.append({"fila": i, "razon": f"excepcion: {e!s}"[:200]})

    db.commit()
    return {
        "total_recibidas": len(filas),
        "creadas": creadas,
        "omitidas_duplicado": duplicadas,
        "omitidas_error": len(errores),
        "errores": errores[:50],
        "ids_creadas": ids,
    }


def _validar_y_procesar_lote(
    db: Session, filas: list[dict], autor: str, current_user: UsuarioRecord
) -> dict:
    """Helper compartido entre los 2 endpoints de import (JSON y multipart)."""
    if not filas:
        raise HTTPException(400, "El archivo/payload no contiene filas")
    if len(filas) > 5000:
        raise HTTPException(413, f"Máximo 5000 plantillas por lote (recibidas {len(filas)})")

    resumen = _procesar_filas_importacion(db, filas, autor)

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="PLANTILLA_GOLD_IMPORT",
        tabla="plantillas_gold",
        registro_id=None,
        detalle=(
            f"importadas={resumen['creadas']} "
            f"dup={resumen['omitidas_duplicado']} "
            f"err={resumen['omitidas_error']}"
        ),
    )
    return resumen


@router.post("/importar-masivo", status_code=201)
def importar_masivo_json(
    payload: PlantillaImportPayload,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Importa plantillas en lote desde JSON body.

    Body: `{"plantillas": [{"eps": "...", "codigo_glosa": "...",
            "titulo": "...", "argumento": "...", ...}, ...]}`

    Detecta duplicados por hash SHA-256(eps|codigo|argumento_normalizado).
    Reporta errores por fila sin abortar el batch — útil para archivos
    masivos donde algunas filas pueden estar mal formateadas.

    Solo coordinador/admin (las plantillas son IP del equipo legal).

    Para subir CSV/archivo, ver POST /plantillas-gold/importar-masivo/archivo.
    """
    filas = [p.model_dump() for p in payload.plantillas]
    return _validar_y_procesar_lote(db, filas, current_user.email, current_user)


@router.post("/importar-masivo/archivo", status_code=201)
async def importar_masivo_archivo(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Importa plantillas en lote desde un archivo CSV o JSON.

    Acepta:
      - CSV con columnas: eps, codigo_glosa, titulo, argumento
        (opcionales: tipo, valor_recuperado, notas). Encoding UTF-8 con
        BOM o Latin-1 detectado automáticamente.
      - JSON: lista directa `[{...}, {...}]` o `{"plantillas": [...]}`.

    Detecta el formato por extensión del archivo (.json vs .csv).
    Mismo procesamiento que /importar-masivo (dedupe + reporte de errores).
    """
    contenido = await archivo.read()
    nombre = (archivo.filename or "").lower()
    filas: list[dict] = []

    if nombre.endswith(".json"):
        try:
            data = json.loads(contenido.decode("utf-8"))
            if isinstance(data, dict) and "plantillas" in data:
                filas = list(data["plantillas"])
            elif isinstance(data, list):
                filas = data
            else:
                raise HTTPException(400, "JSON debe ser lista o {plantillas: [...]}")
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"JSON inválido: {e}") from e
    else:
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
        reader = csv.DictReader(io.StringIO(texto))
        filas = list(reader)

    return _validar_y_procesar_lote(db, filas, current_user.email, current_user)


@router.get("/cobertura")
def cobertura_plantillas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Mapa de cobertura: qué (EPS × código_glosa) tienen plantillas y cuáles no.

    Cruza PlantillaGoldRecord con GlosaRecord para identificar:
      - combinaciones (EPS, código) frecuentes en glosas reales SIN plantilla
      - combinaciones con plantilla pero pocos usos
      - top-10 huecos por valor objetado (qué falta cargar primero)

    Devuelve:
      {
        eps_codigo_sin_plantilla: [{eps, codigo, n_glosas, valor_total}, ...],
        eps_codigo_con_plantilla: [{eps, codigo, n_plantillas, usos}, ...],
        resumen: {total_combinaciones, con_plantilla, sin_plantilla}
      }
    """
    from sqlalchemy import func

    # Plantillas activas por (eps, codigo)
    plantillas = (
        db.query(
            PlantillaGoldRecord.eps,
            PlantillaGoldRecord.codigo_glosa,
            func.count(PlantillaGoldRecord.id).label("n_plantillas"),
            func.coalesce(func.sum(PlantillaGoldRecord.usos), 0).label("usos_total"),
        )
        .filter(PlantillaGoldRecord.activa == 1)
        .group_by(PlantillaGoldRecord.eps, PlantillaGoldRecord.codigo_glosa)
        .all()
    )
    set_con_plantilla: set[tuple[str, str]] = {
        ((p.eps or "").upper(), (p.codigo_glosa or "").upper()) for p in plantillas
    }

    # Glosas reales por (eps, codigo) — últimos 365 días
    from datetime import datetime, timedelta

    desde = datetime.now(UTC) - timedelta(days=365)
    glosas = (
        db.query(
            GlosaRecord.eps,
            GlosaRecord.codigo_glosa,
            func.count(GlosaRecord.id).label("n_glosas"),
            func.coalesce(func.sum(GlosaRecord.valor_objetado), 0).label("valor_total"),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .group_by(GlosaRecord.eps, GlosaRecord.codigo_glosa)
        .all()
    )

    sin_plantilla = []
    for g in glosas:
        clave = ((g.eps or "").upper(), (g.codigo_glosa or "").upper())
        if not clave[0] or not clave[1]:
            continue
        if clave in set_con_plantilla:
            continue
        sin_plantilla.append(
            {
                "eps": g.eps,
                "codigo_glosa": g.codigo_glosa,
                "n_glosas": int(g.n_glosas),
                "valor_total": float(g.valor_total or 0),
            }
        )
    # Top huecos por valor (los más urgentes de cargar)
    sin_plantilla.sort(key=lambda x: x["valor_total"], reverse=True)

    con_plantilla = [
        {
            "eps": p.eps,
            "codigo_glosa": p.codigo_glosa,
            "n_plantillas": int(p.n_plantillas),
            "usos_total": int(p.usos_total or 0),
        }
        for p in plantillas
    ]
    con_plantilla.sort(key=lambda x: x["usos_total"], reverse=True)

    return {
        "resumen": {
            "combinaciones_con_plantilla": len(con_plantilla),
            "combinaciones_sin_plantilla": len(sin_plantilla),
            "top_huecos_por_valor": sin_plantilla[:10],
        },
        "eps_codigo_sin_plantilla": sin_plantilla,
        "eps_codigo_con_plantilla": con_plantilla,
    }


@router.get("/sugerencias")
def sugerencias_plantillas_gold(
    eps: str | None = None,
    codigo_glosa: str | None = None,
    limite: int = 5,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R75 P1: lista plantillas Gold sugeridas para un (EPS, código).

    Útil para que el gestor vea qué argumentos ganadores ya existen
    antes de generar dictamen, así puede:
      - Reutilizarlas directamente (copiar texto)
      - Pedirle a la IA que las use como base
      - Decidir si crear una nueva variante

    Reusa obtener_few_shot() pero con limite configurable y devuelve
    JSON estructurado.
    """
    if not (eps or codigo_glosa):
        raise HTTPException(400, "Debes pasar al menos eps o codigo_glosa")

    plantillas = obtener_few_shot(
        db,
        eps=eps or "",
        codigo_glosa=codigo_glosa or "",
        limite=max(1, min(int(limite), 20)),
    )
    return {
        "eps": eps,
        "codigo_glosa": codigo_glosa,
        "total": len(plantillas),
        "items": [
            {
                "id": p.id,
                "eps": p.eps,
                "codigo_glosa": p.codigo_glosa,
                "tipo": p.tipo,
                "titulo": p.titulo,
                "argumento_preview": (p.argumento or "")[:300],
                "usos": p.usos or 0,
                "creado_en": p.creado_en.isoformat() if p.creado_en else None,
            }
            for p in plantillas
        ],
    }
