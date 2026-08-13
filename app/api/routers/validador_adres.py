"""El validador ADRES/FURIPS y el buscador de autorizaciones, en el portal.

Hasta el 13-08-2026 estas dos herramientas vivían fuera de la página: el
validador como una aplicación aparte en el puerto 8010 que hay que levantar
con un doble clic, y el buscador de autorizaciones como un bot de escritorio.
Yesid pidió que las dos vivan DENTRO del portal, que es donde el equipo ya
está trabajando y donde ya hay sesión, roles y registro de auditoría.

  POST /validador-adres/validar              sube soportes → arranca el trabajo
  GET  /validador-adres/estado/{id}          cómo va (el navegador consulta)
  GET  /validador-adres/excel/{id}           descarga el informe
  POST /validador-adres/autorizaciones       RIPS JSON → informe de autorizaciones

La validación tarda minutos con un paquete grande, así que corre en segundo
plano y el navegador pregunta por su identificador. La lógica es la MISMA que
usa la aplicación aparte (`app/services/validador_adres_service.py`): un solo
código, para que una corrección no haya que hacerla dos veces.

Roles: auditor o superior. Por acá entran soportes con historia clínica.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import get_auditor_o_superior
from app.models.db import UsuarioRecord
from app.services import validador_adres_service as vas

logger = logging.getLogger("motor_glosas")

router = APIRouter(prefix="/validador-adres", tags=["Validador ADRES"])


def _guardar(archivo: UploadFile, destino: Path) -> Path:
    """Escribe la subida en disco respetando el tope de tamaño.

    El nombre lo pone el cliente: se usa SOLO el último tramo para que un
    "../../algo" no escriba fuera de la carpeta del trabajo.
    """
    nombre = Path(archivo.filename or "archivo").name
    ruta = destino / nombre
    limite = vas.MAX_MB_ARCHIVO * 1024 * 1024
    escrito = 0
    with open(ruta, "wb") as fh:
        while trozo := archivo.file.read(1024 * 1024):
            escrito += len(trozo)
            if escrito > limite:
                fh.close()
                ruta.unlink(missing_ok=True)
                raise HTTPException(
                    413,
                    f"«{nombre}» supera los {vas.MAX_MB_ARCHIVO} MB permitidos por archivo.",
                )
            fh.write(trozo)
    return ruta


@router.post("/validar")
async def validar_soportes(
    tareas: BackgroundTasks,
    archivos: list[UploadFile] = File(...),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Recibe los soportes del ADRES y arranca la validación.

    Acepta los TXT del FURIPS sueltos o todo dentro de un ZIP, que es como
    llegan del servidor de facturación.
    """
    if not archivos:
        raise HTTPException(400, "No se subió ningún archivo.")

    trabajo_id, carpeta = vas.crear_trabajo()
    guardados = 0
    for archivo in archivos:
        if not vas.extension_permitida(archivo.filename or ""):
            continue
        ruta = _guardar(archivo, carpeta)
        if ruta.suffix.lower() == ".zip":
            try:
                guardados += vas.extraer_zip_seguro(ruta, carpeta)
            except Exception as e:
                raise HTTPException(400, f"El ZIP «{ruta.name}» no se pudo abrir: {e}") from e
        else:
            guardados += 1

    if not guardados:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise HTTPException(
            400,
            "Ninguno de los archivos sirve para validar. Se aceptan "
            + ", ".join(sorted(vas.EXT_PERMITIDAS)),
        )

    logger.info(
        f"[VALIDADOR-ADRES] trabajo {trabajo_id} creado por {current_user.email} "
        f"con {guardados} archivo(s)"
    )
    tareas.add_task(vas.correr_validacion, trabajo_id, carpeta)
    return {"trabajo_id": trabajo_id, "archivos": guardados, "estado": "EN_COLA"}


@router.get("/estado/{trabajo_id}")
def estado_validacion(
    trabajo_id: str,
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Cómo va el trabajo. El navegador consulta cada pocos segundos."""
    tr = vas.estado(trabajo_id)
    if not tr:
        raise HTTPException(404, "Esa validación ya no está disponible.")
    return {
        "estado": tr["estado"],
        "mensaje": tr["mensaje"],
        "progreso": tr["progreso"],
        "total": tr["total"],
        "facturas": len(tr.get("resultados") or []),
    }


@router.get("/excel/{trabajo_id}")
def descargar_informe(
    trabajo_id: str,
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Descarga el informe de la validación en Excel."""
    tr = vas.estado(trabajo_id)
    if not tr:
        raise HTTPException(404, "Esa validación ya no está disponible.")
    if tr["estado"] != "LISTO":
        raise HTTPException(409, f"La validación todavía no termina ({tr['estado']}).")
    salida = vas.generar_informe(trabajo_id)
    if not salida:
        raise HTTPException(500, "El informe no se pudo generar.")
    fecha = datetime.now().strftime("%Y%m%d")
    return FileResponse(
        salida,
        filename=f"INFORME_VALIDACION_FURIPS_{fecha}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/autorizaciones")
async def buscar_autorizaciones(
    archivos: list[UploadFile] = File(...),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Busca los números de autorización en los RIPS JSON y devuelve el Excel.

    Acepta los JSON sueltos o el ZIP de la carpeta de facturación completa —
    el buscador recorre todas las subcarpetas que vengan adentro.

    A diferencia de la validación FURIPS, esto es rápido: se responde con el
    archivo en la misma petición, sin trabajo en segundo plano.
    """
    if not archivos:
        raise HTTPException(400, "No se subió ningún archivo.")

    from tools.autorizaciones_rips import procesar

    carpeta = Path(tempfile.mkdtemp(prefix="autoriz_rips_"))
    try:
        entradas = 0
        for archivo in archivos:
            nombre = Path(archivo.filename or "archivo").name
            if Path(nombre).suffix.lower() not in {".json", ".zip"}:
                continue
            ruta = _guardar(archivo, carpeta)
            entradas += 1
            if ruta.suffix.lower() == ".zip":
                vas.extraer_zip_seguro(ruta, carpeta)
                ruta.unlink(missing_ok=True)

        if not entradas:
            raise HTTPException(400, "Suba los RIPS en .json o el .zip de la carpeta.")

        salida = carpeta / "INFORME_AUTORIZACIONES_RIPS.xlsx"
        procesar([str(carpeta)], str(salida), log=lambda *_a, **_k: None)
        if not salida.exists():
            raise HTTPException(
                400, "No se encontró ningún RIPS en JSON dentro de lo que se subió."
            )
        logger.info(
            f"[AUTORIZACIONES-RIPS] informe generado por {current_user.email} "
            f"desde {entradas} entrada(s)"
        )
        fecha = datetime.now().strftime("%Y%m%d")
        # El archivo vive en una carpeta temporal; FileResponse lo lee antes
        # de que se limpie en el siguiente arranque del sistema.
        return FileResponse(
            salida,
            filename=f"INFORME_AUTORIZACIONES_RIPS_{fecha}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except HTTPException:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(carpeta, ignore_errors=True)
        logger.exception("[AUTORIZACIONES-RIPS] falló la búsqueda")
        raise HTTPException(500, f"No se pudo generar el informe: {e}") from e
