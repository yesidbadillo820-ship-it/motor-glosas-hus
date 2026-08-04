"""Glosas ADRES — el paquete de glosas dentro del sistema.

Reemplaza el Excel con macro que el equipo llenaba a mano. El coordinador carga
una vez el `ReporteGlosasReclamPAQUETE` (y, si la tiene, la bitácora del
ajustador de detallados) y a partir de ahí **el gestor solo escribe el número
de factura**: la pantalla le trae las glosas ya clasificadas, el centro de
costos, la sugerencia de respuesta con su motivo, el detallado cruzado y el
texto consolidado para el ADRES.

Rutas:
    POST /glosas-adres/importar            carga el reporte (coordinador/admin)
    POST /glosas-adres/importar-bitacora   agrega el detallado cruzado
    GET  /glosas-adres/paquetes            qué paquetes hay cargados
    GET  /glosas-adres/buscar              autocompletado de facturas
    GET  /glosas-adres/factura/{numero}    TODO lo de esa factura
    GET  /glosas-adres/factura/{n}/respuesta  el texto consolidado
    POST /glosas-adres/glosa/{id}          guarda la decisión del gestor
    POST /glosas-adres/aplicar-sugerencias aplica las sugerencias en bloque
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin, get_usuario_actual
from app.core.logging_utils import logger
from app.database import get_db
from app.models.db import GlosaAdresRecord, PaqueteAdresRecord, UsuarioRecord
from app.services import preauditoria_adres as svc

router = APIRouter(prefix="/glosas-adres", tags=["Glosas ADRES"])

MAX_BYTES = 40_000_000  # el reporte del 31068 pesa ~2 MB; damos margen de sobra


# ─── Cargue ──────────────────────────────────────────────────────────────────


@router.post("/importar")
async def importar(
    archivo: UploadFile = File(..., description="ReporteGlosasReclamPAQUETE NNNNN.xlsx"),
    paquete: str | None = Form(None, description="Número de paquete, si el reporte trae varios"),
    macro: UploadFile | None = File(
        None, description="Excel de la macro con la que venía trabajando el equipo (opcional)"
    ),
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Carga el reporte del ADRES y lo deja pre-auditado.

    Volver a cargar el mismo paquete lo reemplaza, pero **las decisiones que el
    equipo ya tomó se conservan** y se vuelven a aplicar sobre las filas nuevas.
    """
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo supera el tamaño máximo permitido.")
    contenido_macro = await macro.read() if macro is not None else None
    if contenido_macro and len(contenido_macro) > MAX_BYTES:
        raise HTTPException(413, "El Excel de la macro supera el tamaño máximo permitido.")
    try:
        registro = svc.importar_reporte(
            db,
            contenido,
            nombre_archivo=archivo.filename or "reporte.xlsx",
            importado_por=usuario.email,
            paquete=paquete,
            macro=contenido_macro,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001 - el detalle va al log
        logger.exception("Fallo importando el paquete ADRES")
        raise HTTPException(500, f"No se pudo leer el reporte: {e}") from e
    return {
        "ok": True,
        "paquete_id": registro.id,
        "numero_paquete": registro.numero_paquete,
        "filas": registro.total_filas,
        "facturas": registro.total_facturas,
        "valor_glosado": registro.valor_glosado,
    }


@router.post("/importar-bitacora")
async def importar_bitacora(
    paquete_id: int = Form(...),
    archivo: UploadFile = File(..., description="Bitácora CSV del ajustador de detallados"),
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Agrega el detallado ya cruzado: qué pagó el ADRES y qué sigue glosado."""
    if db.get(PaqueteAdresRecord, paquete_id) is None:
        raise HTTPException(404, f"No existe el paquete {paquete_id}")
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo supera el tamaño máximo permitido.")
    n = svc.importar_bitacora(db, contenido, paquete_id=paquete_id)
    return {"ok": True, "items": n}


@router.get("/paquetes")
def paquetes(
    db: Session = Depends(get_db),
    _usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    """Los paquetes cargados, del más nuevo al más viejo."""
    filas = db.query(PaqueteAdresRecord).order_by(PaqueteAdresRecord.id.desc()).limit(50).all()
    return [
        {
            "id": p.id,
            "numero": p.numero_paquete,
            "archivo": p.archivo,
            "importado_en": p.importado_en.isoformat() if p.importado_en else None,
            "importado_por": p.importado_por,
            "filas": p.total_filas,
            "facturas": p.total_facturas,
            "valor_glosado": p.valor_glosado,
        }
        for p in filas
    ]


# ─── Consulta ────────────────────────────────────────────────────────────────


@router.get("/buscar")
def buscar(
    q: str = Query("", description="Parte del número de factura"),
    paquete_id: int | None = None,
    limite: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    _usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    """Autocompletado: facturas del paquete que contienen ese texto."""
    consulta = db.query(GlosaAdresRecord.factura).distinct()
    if paquete_id:
        consulta = consulta.filter(GlosaAdresRecord.paquete_id == paquete_id)
    texto = (q or "").strip()
    if texto:
        consulta = consulta.filter(GlosaAdresRecord.factura.ilike(f"%{texto}%"))
    return [f[0] for f in consulta.order_by(GlosaAdresRecord.factura).limit(limite).all()]


@router.get("/factura/{numero}")
def factura(
    numero: str,
    paquete_id: int | None = None,
    db: Session = Depends(get_db),
    _usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    """Todo lo que el sistema sabe de esa factura, en una sola llamada."""
    datos = svc.consultar_factura(db, numero, paquete_id=paquete_id)
    if not datos["encontrada"]:
        raise HTTPException(404, f"La factura {numero} no está en ningún paquete cargado.")
    return datos


@router.get("/factura/{numero}/respuesta")
def respuesta(
    numero: str,
    paquete_id: int | None = None,
    db: Session = Depends(get_db),
    _usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    """El texto de respuesta consolidado, igual al que armaba la macro."""
    texto = svc.texto_respuesta_factura(db, numero, paquete_id=paquete_id)
    return {"factura": numero, "texto": texto}


# ─── Decisión del gestor ─────────────────────────────────────────────────────


class DecisionIn(BaseModel):
    decision: str | None = None  # SE ACEPTA | SE OBJETA | SE SUBSANA | "" para limpiar
    observacion_tecnico: str | None = None
    cantidad_aceptada: str | None = None
    valor_aceptado: float | None = None
    centro_costos: str | None = None
    medico: str | None = None


@router.post("/glosa/{glosa_id}")
def decidir(
    glosa_id: int,
    cuerpo: DecisionIn,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    """Guarda lo que el gestor decidió para una glosa."""
    try:
        glosa = svc.guardar_decision(
            db,
            glosa_id,
            decision=cuerpo.decision,
            observacion_tecnico=cuerpo.observacion_tecnico,
            cantidad_aceptada=cuerpo.cantidad_aceptada,
            valor_aceptado=cuerpo.valor_aceptado,
            centro_costos=cuerpo.centro_costos,
            medico=cuerpo.medico,
            usuario=usuario.email,
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.glosa_dict(glosa)


class AplicarIn(BaseModel):
    paquete_id: int
    factura: str | None = None
    solo_confianza: str | None = None  # APRENDIDA para aplicar solo el criterio del equipo


@router.post("/aplicar-sugerencias")
def aplicar(
    cuerpo: AplicarIn,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    """Copia las sugerencias del bot a la decisión, sin pisar lo ya decidido."""
    n = svc.aplicar_sugerencias(
        db,
        paquete_id=cuerpo.paquete_id,
        factura=cuerpo.factura,
        usuario=usuario.email,
        solo_confianza=cuerpo.solo_confianza,
    )
    return {"ok": True, "aplicadas": n}
