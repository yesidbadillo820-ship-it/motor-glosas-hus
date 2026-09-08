"""Objeciones para DGH — armar el archivo de cargue desde la pantalla.

El auditor sube dos Excel —las glosas que mandó la entidad y el export de
servicios facturados del DGH— y recibe los dos archivos de siempre: el que se
sube al DGH y el respaldo con la hoja REVISAR. Antes de descargar nada ve el
resumen del cruce, para decidir con datos y no a ciegas.

El trabajo lo hacen los bots de `tools/` a través de
`app/services/objeciones_dgh_service.py`: acá no hay reglas de negocio, solo
recibir, validar y responder.

Rutas:
    GET  /objeciones-dgh/entidades          las entidades que sabe leer
    POST /objeciones-dgh/procesar           sube los dos Excel y devuelve el resumen
    GET  /objeciones-dgh/{id}/objeciones.xlsx   el archivo que se sube al DGH
    GET  /objeciones-dgh/{id}/cruce.xlsx        el respaldo con la hoja REVISAR
    GET  /objeciones-dgh/{id}/paquete.zip       los dos, juntos

Acceso: AUDITOR o superior. Armar el cargue es trabajo de gestión.
"""

from __future__ import annotations

import io
import uuid
import zipfile

from cachetools import TTLCache
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_auditor_o_superior
from app.core.logging_utils import logger
from app.models.db import UsuarioRecord
from app.services import objeciones_dgh_service as svc

router = APIRouter(prefix="/objeciones-dgh", tags=["Objeciones DGH"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Los archivos armados esperan acá a que el auditor los descargue. Media hora
# alcanza de sobra para mirar el resumen y bajarlos; después se sueltan solos
# para no dejar datos de pacientes en memoria más de lo necesario.
_RESULTADOS: TTLCache = TTLCache(maxsize=32, ttl=30 * 60)


class EntidadFicha(BaseModel):
    """Una entidad del catálogo, para el selector de la pantalla."""

    id: str
    nombre: str
    corto: str
    columnas: int
    ayuda: str


class RespuestaProceso(BaseModel):
    """El resumen del cruce y las llaves para descargar los archivos."""

    id: str = Field(..., description="Con esto se descargan los archivos")
    entidad: str
    entidad_id: str
    fecha: str
    facturas: int
    objeciones: int
    valor_total: int
    confianza: dict[str, int]
    ubicadas: int
    pendientes: int
    revisar: list[dict]
    por_factura: list[dict]
    reglas_ok: bool
    fallas_reglas: list[str]
    avisos: list[str]
    nombre_objeciones: str
    nombre_cruce: str


@router.get("/entidades", response_model=list[EntidadFicha])
def listar_entidades(current_user: UsuarioRecord = Depends(get_auditor_o_superior)):
    """Las entidades cuyo formato de glosas sabe leer el motor."""
    return svc.catalogo_entidades()


async def _leer(archivo: UploadFile | None, cual: str) -> bytes:
    if archivo is None:
        raise HTTPException(400, f"Falta el archivo {cual}.")
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, f"El archivo {cual} debe ser un Excel (.xlsx).")
    datos = await archivo.read()
    if not datos:
        raise HTTPException(400, f"El archivo {cual} llegó vacío.")
    if len(datos) > svc.MAX_BYTES:
        raise HTTPException(
            413, f"El archivo {cual} pesa más de {svc.MAX_BYTES // (1024 * 1024)} MB."
        )
    return datos


@router.post("/procesar", response_model=RespuestaProceso)
async def procesar(
    archivo_entidad: UploadFile = File(..., description="Excel de glosas de la entidad"),
    archivo_dgh: UploadFile = File(..., description="Export de servicios facturados del DGH"),
    entidad: str = Form("", description="id de la entidad; vacío = detectarla sola"),
    fecha: str = Form("", description="Fecha de la objeción (AAAA-MM-DD); vacío = hoy"),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Cruza los dos archivos y deja listos los dos Excel para descargar."""
    datos_entidad = await _leer(archivo_entidad, "de la entidad")
    datos_dgh = await _leer(archivo_dgh, "del DGH")

    try:
        resultado = svc.procesar(
            datos_entidad,
            datos_dgh,
            entidad_id=entidad.strip() or None,
            fecha=fecha.strip() or None,
        )
    except svc.ErrorObjeciones as e:
        raise HTTPException(400, str(e)) from e
    except Exception:
        logger.exception("Objeciones DGH: falló el armado del cargue")
        raise HTTPException(500, "No se pudo armar el archivo. Revisá el log del servidor.")

    identificador = uuid.uuid4().hex
    _RESULTADOS[identificador] = (current_user.id, resultado)
    logger.info(
        "Objeciones DGH: %s armó %s objeciones de %s (%s), %s por revisar",
        current_user.email,
        resultado.objeciones,
        resultado.entidad,
        resultado.fecha,
        resultado.pendientes,
    )
    return {"id": identificador, **resultado.resumen()}


def _recuperar(identificador: str, usuario: UsuarioRecord) -> svc.Resultado:
    guardado = _RESULTADOS.get(identificador)
    if not guardado:
        raise HTTPException(404, "El resultado ya no está disponible: volvé a subir los archivos.")
    dueno, resultado = guardado
    if dueno != usuario.id:
        raise HTTPException(403, "Ese resultado es de otro usuario.")
    return resultado


def _descarga(contenido: bytes, nombre: str, tipo: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/{identificador}/objeciones.xlsx")
def descargar_objeciones(
    identificador: str, current_user: UsuarioRecord = Depends(get_auditor_o_superior)
):
    """El archivo que se sube al DGH."""
    r = _recuperar(identificador, current_user)
    return _descarga(r.objeciones_xlsx, r.nombre_objeciones, XLSX)


@router.get("/{identificador}/cruce.xlsx")
def descargar_cruce(
    identificador: str, current_user: UsuarioRecord = Depends(get_auditor_o_superior)
):
    """El respaldo del auditor, con las hojas CRUCE, REVISAR y RESUMEN."""
    r = _recuperar(identificador, current_user)
    return _descarga(r.cruce_xlsx, r.nombre_cruce, XLSX)


@router.get("/{identificador}/paquete.zip")
def descargar_paquete(
    identificador: str, current_user: UsuarioRecord = Depends(get_auditor_o_superior)
):
    """Los dos archivos juntos, para guardarlos de una."""
    r = _recuperar(identificador, current_user)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(r.nombre_objeciones, r.objeciones_xlsx)
        z.writestr(r.nombre_cruce, r.cruce_xlsx)
    buffer.seek(0)
    nombre = r.nombre_objeciones.replace("OBJECIONES_", "OBJECIONES_DGH_").replace(".xlsx", ".zip")
    return _descarga(buffer.getvalue(), nombre, "application/zip")
