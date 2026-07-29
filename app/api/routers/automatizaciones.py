"""Centro de Automatización — correr las herramientas desde el navegador.

Hasta ahora las 34 herramientas de `tools/` solo se podían usar copiando el
guion a un PC con Python y abriendo una consola. Con estas dos rutas el
auditor sube el archivo, elige la herramienta y descarga el resultado.

Acceso: AUDITOR o superior. Convertir el archivo de un pagador al formato del
ERP es trabajo de gestión, no de consulta.
"""

from __future__ import annotations

import io
import json
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_auditor_o_superior
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services import automatizaciones as svc

router = APIRouter(prefix="/automatizaciones", tags=["automatizaciones"])


def _opciones(crudo: str) -> dict[str, str]:
    """Los parámetros que eligió el auditor, validados."""
    try:
        opts = json.loads(crudo or "{}")
        if not isinstance(opts, dict):
            raise ValueError
        return {str(k): str(v) for k, v in opts.items()}
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "Las opciones deben ser un objeto JSON")


@router.get("")
def listar_automatizaciones(
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """El catálogo de lo que se puede correr, agrupado para la pantalla.

    Sale del registro (`services/automatizaciones.CATALOGO`), así que agregar
    una herramienta no obliga a tocar esta ruta.
    """
    fichas = svc.catalogo()
    grupos: dict[str, list] = {}
    for f in fichas:
        grupos.setdefault(f["grupo"], []).append(f)
    return {
        "total": len(fichas),
        "grupos": [{"nombre": g, "automatizaciones": items} for g, items in grupos.items()],
        "limite_mb": svc.MAX_BYTES // 1048576,
    }


@router.post("/{id_automatizacion}/previsualizar")
async def previsualizar_automatizacion(
    id_automatizacion: str,
    archivo: UploadFile = File(...),
    opciones: str = Form("{}"),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Corre la automatización y devuelve **qué salió**, sin el archivo.

    La regla del área es no hacer un cargue masivo sin mirar antes lo que se
    va a cargar, y hasta ahora "mirar" era abrir el Excel a mano. Acá el
    auditor ve cuántas facturas, cuántas objeciones y cuánta plata trae el
    resultado; si el total no se parece al del archivo que mandó la EPS, hay
    algo mal y se ve **antes** de cargarlo al ERP.

    No se guarda nada: la corrida vuelve a hacerse al descargar.
    """
    opts = _opciones(opciones)
    contenido = await archivo.read()
    try:
        resultado = svc.ejecutar(id_automatizacion, contenido, archivo.filename or "", opts)
    except svc.ErrorAutomatizacion as e:
        raise HTTPException(400, str(e))

    return {
        "ok": True,
        "segundos": round(resultado.segundos, 2),
        "archivos": resultado.nombres,
        "resumen": svc.resumir(resultado.archivos),
        "salida_texto": resultado.salida_texto[-800:],
    }


@router.post("/{id_automatizacion}/ejecutar")
async def ejecutar_automatizacion(
    id_automatizacion: str,
    archivo: UploadFile = File(...),
    opciones: str = Form("{}"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Corre la automatización sobre el archivo y devuelve el resultado.

    Un solo archivo se devuelve tal cual; varios van en un ZIP —el conversor
    de SAVIA, por ejemplo, produce un Excel por factura—.

    Queda en el registro de auditoría: quién corrió qué, sobre qué archivo y
    cuánto tardó. El contenido no se guarda en ningún lado: el directorio de
    trabajo se borra al terminar.
    """
    auto = svc.obtener(id_automatizacion)
    if auto is None:
        raise HTTPException(404, f"No existe la automatización '{id_automatizacion}'")

    opts = _opciones(opciones)
    contenido = await archivo.read()
    try:
        resultado = svc.ejecutar(id_automatizacion, contenido, archivo.filename or "", opts)
    except svc.ErrorAutomatizacion as e:
        raise HTTPException(400, str(e))

    try:
        from app.repositories.audit_repository import AuditRepository

        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="EJECUTAR_AUTOMATIZACION",
            tabla="automatizacion",
            campo=id_automatizacion,
            valor_nuevo=", ".join(resultado.nombres)[:500],
            detalle=json.dumps(
                {
                    "automatizacion": id_automatizacion,
                    "archivo": archivo.filename,
                    "bytes_entrada": len(contenido),
                    "archivos_generados": resultado.nombres,
                    "segundos": round(resultado.segundos, 2),
                },
                ensure_ascii=False,
            ),
        )
        db.commit()
    except Exception:  # la auditoría no puede tumbar una corrida ya hecha
        pass

    if len(resultado.archivos) == 1:
        nombre, datos = resultado.archivos[0]
        return StreamingResponse(
            io.BytesIO(datos),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{nombre}"',
                "X-Archivos-Generados": "1",
                "X-Segundos": f"{resultado.segundos:.2f}",
            },
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, datos in resultado.archivos:
            z.writestr(nombre, datos)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{id_automatizacion}.zip"',
            "X-Archivos-Generados": str(len(resultado.archivos)),
            "X-Segundos": f"{resultado.segundos:.2f}",
        },
    )
