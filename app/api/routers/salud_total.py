"""Pantalla «Salud Total»: notificación de glosas → archivo de respuesta.

OT-033 · 13-08-2026. La pantalla existe en el menú del portal y su
JavaScript llama a `/api/salud-total/preview` y `/api/salud-total/procesar`,
pero el router se había borrado en la limpieza de mayo de 2026 (commit
«cleanup: salud_total»). Solo se borró el router: el servicio
`salud_total_service` siguió en su sitio, completo y con sus pruebas. Por
eso la pantalla respondía «Not Found» — no le faltaba el motor, le faltaba
la puerta.

Se repone la puerta tal como estaba, con dos cambios mínimos:

  · pide rol AUDITOR o superior en vez de cualquier sesión, porque por acá
    salen documentos que se radican ante la entidad;
  · avisa cuando la respuesta se calcula sin fecha de recepción de la
    factura (ver `sin_fecha_recepcion` en el servicio).
"""

import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_auditor_o_superior
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.salud_total_service import (
    generar_nombre_archivo,
    generar_txt_respuesta,
    procesar_glosas_salud_total,
)

router = APIRouter(prefix="/api/salud-total", tags=["Salud Total"])

# Cuántas filas se devuelven a la pantalla de vista previa. El archivo se
# genera completo; esto solo evita mandarle 3.000 filas al navegador.
MAX_FILAS_PREVIEW = 50


def _decodificar_contenido(contenido: bytes) -> str:
    """Decodifica UTF-8 y cae a Latin-1, que es como llegan los archivos.

    Las notificaciones de Salud Total vienen en latin-1: leerlas como UTF-8
    parte las tildes de los nombres de los pacientes y de los motivos.
    """
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return contenido.decode(enc)
        except UnicodeDecodeError:
            continue
    return contenido.decode("utf-8", errors="ignore")


def _fecha_recepcion(valor: str | None) -> datetime | None:
    """Lee la fecha que digitó el auditor. None si no la puso o es inválida.

    None NO significa cero días: significa que no hay con qué contar el
    plazo, y el servicio se encarga de no afirmar un número inventado.
    """
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def _respuestas(contenido: bytes, tipo: str, fecha: datetime | None) -> list[dict]:
    texto = _decodificar_contenido(contenido)
    try:
        respuestas = procesar_glosas_salud_total(texto, tipo, fecha)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not respuestas:
        raise HTTPException(
            status_code=400,
            detail=(
                "No se encontraron glosas en el archivo. Verifique que sea la "
                "notificación de Salud Total y que traiga filas bajo el encabezado."
            ),
        )
    return respuestas


@router.post("/preview")
async def preview_glosas(
    file: UploadFile = File(...),
    tipo_respuesta: str = Form("extemporanea"),
    fecha_recepcion: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Muestra en pantalla lo que va a salir, antes de descargarlo.

    Recibe la misma fecha de recepción que `procesar`: si la vista previa
    calculara sin ella, mostraría un código de respuesta y el archivo
    descargado traería otro.
    """
    if not (file.filename or "").lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .txt")

    respuestas = _respuestas(await file.read(), tipo_respuesta, _fecha_recepcion(fecha_recepcion))

    total_glosado = sum(r.get("ValorGlosaTotalxServ", 0) for r in respuestas)
    total_aceptado = sum(r.get("ValorAceptadoIPS", 0) for r in respuestas)

    return {
        "total_registros": len(respuestas),
        "total_glosado": total_glosado,
        "total_aceptado": total_aceptado,
        "total_rechazado": total_glosado - total_aceptado,
        # Si alguna respuesta se armó sin fecha de recepción, la pantalla lo
        # tiene que decir: el plazo no se puede contar de memoria.
        "sin_fecha_recepcion": any(r.get("SinFechaRecepcion") for r in respuestas),
        "glosas": respuestas[:MAX_FILAS_PREVIEW],
    }


@router.post("/procesar")
async def procesar_glosas(
    file: UploadFile = File(None),
    tipo_respuesta: str = Form("extemporanea"),
    fecha_recepcion: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Genera el archivo de respuesta que se carga en el portal de la entidad."""
    if not file or not (file.filename or "").lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Debe subir el archivo TXT de la notificación")

    respuestas = _respuestas(await file.read(), tipo_respuesta, _fecha_recepcion(fecha_recepcion))

    txt = generar_txt_respuesta(respuestas)
    nombre = generar_nombre_archivo(tipo_respuesta)

    return StreamingResponse(
        io.BytesIO(txt.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
