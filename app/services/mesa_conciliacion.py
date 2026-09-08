"""La mesa de conciliación: el acta vive en el motor mientras se trabaja.

EL CAMBIO. Antes el acta se armaba, se bajaba en Excel y se llenaba por
fuera. Una audiencia con la EPS dura horas: si se cerraba el archivo sin
guardar, o dos personas lo abrían a la vez, el trabajo se perdía o se
pisaba. Ahora el acta se arma y **se queda acá**: se trabaja en pantalla,
cada cambio queda escrito, y el Excel se genera al final con lo conciliado.

EL CICLO COMPLETO:

    abrir()      la lista de facturas + el archivo de la EPS -> una mesa
    guardar()    cada renglón que toca el auditor, mientras negocia
    cerrar()     la mesa se congela y se aprende lo que decidió una persona
    a_excel()    el acta del formato oficial, ya conciliada

TRES DUEÑOS EN CADA RENGLÓN, y conviene no confundirlos:

  · lo que trajo **la EPS** —factura, código, valor objetado— no se toca;
  · lo que decide **la mesa** —cuánto se acepta, cuánto se levanta, cuánto
    se ratifica y con qué texto— se escribe durante la audiencia;
  · lo **contable** —centro de costo, cuenta y concepto de la nota— sale
    del DGH y del catálogo, y se llena solo cuando se puede.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.logging_utils import logger
from app.models.db import (
    MESA_ABIERTA,
    MESA_CERRADA,
    MesaConciliacionRecord,
    MesaLineaRecord,
)
from app.services import acta_conciliacion_armar as armador
from app.services import conceptos_nota_hus as conceptos
from app.services.acta_conciliacion_excel import Acta, LineaActa

# Las columnas que el auditor puede tocar en la pantalla. Todo lo demás
# viene del archivo de la EPS o del catálogo y no se edita a mano: si el
# valor objetado se pudiera cambiar, el acta dejaría de cuadrar con lo que
# la EPS mandó y la mesa se discutiría sobre cifras distintas.
CAMPOS_EDITABLES = (
    "tipo_glosa",
    "acepta_ips",
    "levanta_entidad",
    "ratificado",
    "texto_conciliacion",
    "centro_costo",
    "cuenta_contable",
    "concepto_nota",
)


def _dinero(valor: Any) -> float:
    try:
        return round(max(0.0, float(valor or 0.0)), 2)
    except (TypeError, ValueError):
        return 0.0


# ═══════════════════════════════════════════════════════════════════════
#  Abrir la mesa
# ═══════════════════════════════════════════════════════════════════════


def glosa_del_motor(db: Any, factura_clave: str, cod_glosa: str) -> Optional[int]:
    """El id de la glosa del motor que corresponde a este renglón, si la hay.

    Los renglones de la mesa vienen del archivo de la EPS, no del historial:
    hay facturas que la EPS glosa y que el motor nunca recibió. Cuando el
    enlace existe, el auditor puede abrir en la audiencia el dictamen que ya
    se escribió, los comentarios del equipo y los soportes cargados — que es
    justo lo que hace falta para refutar en la mesa.

    Se busca por factura Y código: una factura tiene varias glosas y traerse
    la primera sería mostrar el historial de otra.
    """
    from app.models.db import GlosaRecord

    if not factura_clave or not cod_glosa:
        return None
    try:
        fila = (
            db.query(GlosaRecord.id)
            .filter(GlosaRecord.factura.like(f"%{factura_clave}%"))
            .filter(GlosaRecord.codigo_glosa == cod_glosa)
            .order_by(GlosaRecord.id.desc())
            .first()
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[MESA] no se pudo enlazar la glosa del motor: {e}")
        return None
    return int(fila[0]) if fila else None


def _contables_de(db: Any, factura_clave: str, cod_glosa: str) -> tuple[str, str, str]:
    """Centro de costo, cuenta y concepto de nota de una glosa.

    El centro de costo sale del DGH, que el motor ya guarda al recibir las
    glosas (`conceptos_glosa.centro_costo`): no hay que pedírselo a nadie.
    De ahí el catálogo de contabilidad da la cuenta y el concepto.

    Una conciliación es SIEMPRE por acta, así que se pide la vía ACTAS. No
    es el mismo concepto que el de glosa inicial —UCI adultos es 004 por
    inicial y 020 por acta— y ponerle el número equivocado a una nota
    crédito es un asiento mal hecho.

    Devuelve vacíos cuando no se puede saber. Ese vacío es una respuesta.
    """
    from app.models.db import ConceptoGlosaRecord

    if not factura_clave or not cod_glosa:
        return "", "", ""
    try:
        fila = (
            db.query(ConceptoGlosaRecord.centro_costo)
            .filter(ConceptoGlosaRecord.factura.like(f"%{factura_clave}%"))
            .filter(ConceptoGlosaRecord.codigo_glosa == cod_glosa)
            .filter(ConceptoGlosaRecord.centro_costo.isnot(None))
            .first()
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[MESA] no se pudo leer el centro de costo del DGH: {e}")
        return "", "", ""
    if fila is None or not fila[0]:
        return "", "", ""

    centro = str(fila[0])
    hallado = conceptos.buscar(centro, tipo=conceptos.TIPO_GLOSA, via=conceptos.VIA_ACTAS)
    if hallado is None:
        # El centro existe en el DGH pero no en el catálogo de contabilidad.
        # Se muestra el centro igual: es el dato que necesita quien arme la
        # nota para resolverlo o para pedir que lo agreguen al catálogo.
        return centro, "", ""
    return centro, hallado.cuenta, hallado.concepto


def abrir(
    db: Any,
    facturas: list[str],
    filas_eps: list[dict],
    encabezado: armador.Encabezado,
    usuario: str = "",
) -> MesaConciliacionRecord:
    """Arma el acta y la deja guardada, lista para trabajar en pantalla."""
    resultado = armador.armar(
        facturas, filas_eps, encabezado, memoria=armador.memoria_de(db, facturas)
    )
    avisos = {}
    for aviso in resultado.avisos:
        avisos.setdefault(aviso.factura, []).append(aviso.motivo)

    mesa = MesaConciliacionRecord(
        nit=encabezado.nit[:30],
        razon_social=encabezado.razon_social[:300],
        numero_acta=encabezado.numero_acta[:60],
        periodo=encabezado.periodo[:60],
        fecha_conciliacion=(
            datetime.combine(encabezado.fecha_conciliacion, datetime.min.time())
            if encabezado.fecha_conciliacion
            else None
        ),
        estado=MESA_ABIERTA,
        creado_por=(usuario or "")[:200],
        facturas_en_lista=len(facturas),
    )
    db.add(mesa)
    db.flush()

    for orden, linea in enumerate(resultado.acta.lineas):
        clave = armador.clave_factura(linea.factura)
        centro, cuenta, concepto = _contables_de(db, clave, linea.cod_glosa)
        db.add(
            MesaLineaRecord(
                mesa_id=mesa.id,
                orden=orden,
                glosa_id=glosa_del_motor(db, clave, linea.cod_glosa),
                item=linea.item,
                radicado=linea.radicado[:60],
                factura=linea.factura[:50],
                factura_clave=clave[:30],
                fecha_factura=linea.fecha_factura[:20],
                cod_glosa=linea.cod_glosa[:12],
                descripcion=linea.descripcion,
                valor_factura=linea.valor_factura,
                glosa_inicial=linea.glosa_inicial,
                tipificacion=linea.tipificacion[:30],
                tipo_glosa=linea.tipo_glosa[:30],
                aviso=" · ".join(avisos.get(linea.factura, []))[:1000] or None,
                centro_costo=centro[:200] or None,
                cuenta_contable=cuenta[:30] or None,
                concepto_nota=concepto[:10] or None,
            )
        )
    db.commit()
    db.refresh(mesa)
    logger.info(
        f"[MESA] abierta id={mesa.id} acta={mesa.numero_acta} "
        f"lineas={len(resultado.acta.lineas)} por={usuario}"
    )
    return mesa


# ═══════════════════════════════════════════════════════════════════════
#  Trabajar la mesa
# ═══════════════════════════════════════════════════════════════════════


def lineas_de(db: Any, mesa_id: int) -> list[MesaLineaRecord]:
    return (
        db.query(MesaLineaRecord)
        .filter(MesaLineaRecord.mesa_id == mesa_id)
        .order_by(MesaLineaRecord.orden.asc())
        .all()
    )


def guardar_linea(db: Any, mesa_id: int, linea_id: int, cambios: dict, usuario: str = "") -> dict:
    """Guarda lo que el auditor escribió en un renglón, mientras negocia.

    Solo se tocan los campos editables: el valor objetado y el código de
    glosa vienen del archivo de la EPS y cambiarlos haría que el acta deje
    de cuadrar con lo que la EPS mandó.

    NO se impide repartir de más. En una mesa se tantea, se corrige y se
    vuelve atrás; bloquear el renglón a mitad de una negociación estorba.
    Lo que sí se devuelve es el pendiente al instante, para que el descuadre
    se vea mientras pasa — y el `revisar()` del acta lo atrapa al cerrar.
    """
    mesa = db.query(MesaConciliacionRecord).filter(MesaConciliacionRecord.id == mesa_id).first()
    if mesa is None:
        return {"estado": "no_existe"}
    if mesa.estado == MESA_CERRADA:
        return {"estado": "cerrada", "detalle": "Esta mesa ya se cerró: no admite cambios."}

    linea = (
        db.query(MesaLineaRecord)
        .filter(MesaLineaRecord.id == linea_id)
        .filter(MesaLineaRecord.mesa_id == mesa_id)
        .first()
    )
    if linea is None:
        return {"estado": "no_existe_linea"}

    for campo in CAMPOS_EDITABLES:
        if campo not in cambios:
            continue
        valor = cambios[campo]
        if campo in ("acepta_ips", "levanta_entidad", "ratificado"):
            setattr(linea, campo, _dinero(valor))
        else:
            texto = str(valor or "").strip()
            setattr(
                linea, campo, texto[:1000] if campo == "texto_conciliacion" else texto[:200] or None
            )

    # Si el auditor resolvió lo que faltaba, el aviso ya no aplica.
    if linea.tipo_glosa and armador._MARCA_FALTA_HUMANO not in (linea.tipo_glosa or ""):
        linea.aviso = None
    linea.actualizado_por = (usuario or "")[:200]
    db.commit()
    return {
        "estado": "guardada",
        "linea_id": linea.id,
        "pendiente": linea.pendiente,
        "repartido": round(
            (linea.acepta_ips or 0) + (linea.levanta_entidad or 0) + (linea.ratificado or 0), 2
        ),
    }


def resumen(db: Any, mesa_id: int) -> dict:
    """Las cifras de la mesa, para el encabezado de la pantalla."""
    lineas = lineas_de(db, mesa_id)
    suma = lambda campo: round(sum(getattr(x, campo) or 0.0 for x in lineas), 2)  # noqa: E731
    return {
        "lineas": len(lineas),
        "facturas": len({x.factura_clave for x in lineas}),
        "glosado": suma("glosa_inicial"),
        "acepta_ips": suma("acepta_ips"),
        "levanta_entidad": suma("levanta_entidad"),
        "ratificado": suma("ratificado"),
        "pendiente": round(sum(x.pendiente for x in lineas), 2),
        "sin_repartir": sum(1 for x in lineas if x.pendiente > 0.009),
        "con_aviso": sum(1 for x in lineas if x.aviso),
        "sin_contables": sum(1 for x in lineas if not x.cuenta_contable),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Cerrar y generar
# ═══════════════════════════════════════════════════════════════════════


def a_acta(db: Any, mesa: MesaConciliacionRecord) -> Acta:
    """La mesa, en las estructuras que ya entiende el resto del módulo."""
    lineas = [
        LineaActa(
            fila_excel=0,
            item=x.item or str(n + 1),
            radicado=x.radicado or "",
            factura=x.factura or "",
            fecha_factura=x.fecha_factura or "",
            tipo_glosa=x.tipo_glosa or "",
            tipificacion=x.tipificacion or "",
            cod_glosa=x.cod_glosa or "",
            descripcion=x.descripcion or "",
            valor_factura=x.valor_factura or 0.0,
            glosa_inicial=x.glosa_inicial or 0.0,
            pendiente=x.pendiente,
            acepta_ips=x.acepta_ips or 0.0,
            levanta_entidad=x.levanta_entidad or 0.0,
            ratificado=x.ratificado or 0.0,
            texto_conciliacion=x.texto_conciliacion or "",
        )
        for n, x in enumerate(lineas_de(db, mesa.id))
    ]
    return Acta(
        nit=mesa.nit or "",
        razon_social=mesa.razon_social or "",
        periodo=mesa.periodo or "",
        cantidad_facturas_declarada=len({x.factura for x in lineas}),
        valor_a_conciliar_declarado=round(sum(x.glosa_inicial for x in lineas), 2),
        lineas=lineas,
    )


def cerrar(db: Any, mesa_id: int, usuario: str = "") -> dict:
    """Congela la mesa y aprende lo que decidió una persona.

    Cerrar no exige que todo esté repartido: hay actas que quedan con
    renglones pendientes a propósito, para una segunda sesión. Lo que sí se
    hace es decir cuántos quedaron, para que nadie cierre sin enterarse.
    """
    mesa = db.query(MesaConciliacionRecord).filter(MesaConciliacionRecord.id == mesa_id).first()
    if mesa is None:
        return {"estado": "no_existe"}
    if mesa.estado == MESA_CERRADA:
        return {"estado": "ya_cerrada"}

    cifras = resumen(db, mesa_id)

    # Aprender es un extra; cerrar es lo que el auditor vino a hacer. Si la
    # memoria falla —una tabla que no está, un choque de llave— la mesa se
    # cierra igual y se dice qué pasó. Al revés, el auditor termina la
    # audiencia y no puede cerrar el acta por un accesorio.
    aprendido: dict = {"nuevas": 0, "actualizadas": 0, "sin_dato": 0}
    error_memoria = ""
    try:
        aprendido = armador.aprender(
            db, a_acta(db, mesa).lineas, numero_acta=mesa.numero_acta or "", usuario=usuario
        )
    except Exception as e:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:
            pass
        error_memoria = f"{type(e).__name__}: {e}"
        logger.error(f"[MESA] no se pudo aprender al cerrar {mesa_id}: {error_memoria}")
        mesa = db.query(MesaConciliacionRecord).filter(MesaConciliacionRecord.id == mesa_id).first()
        if mesa is None:
            return {"estado": "no_existe"}

    mesa.estado = MESA_CERRADA
    mesa.cerrado_en = datetime.now(timezone.utc)
    mesa.cerrado_por = (usuario or "")[:200]
    db.commit()
    logger.info(f"[MESA] cerrada id={mesa_id} por={usuario} aprendido={aprendido}")
    salida = {"estado": MESA_CERRADA, "resumen": cifras, "aprendido": aprendido}
    if error_memoria:
        salida["aviso_memoria"] = (
            "La mesa quedó cerrada, pero no se pudo guardar la tipificación para "
            f"la próxima vez ({error_memoria})."
        )
    return salida


def reabrir(db: Any, mesa_id: int, usuario: str = "") -> dict:
    """Vuelve a abrir una mesa cerrada.

    Existe porque una audiencia se puede reanudar, o porque alguien cerró
    antes de tiempo. No borra lo aprendido: lo que ya se sabe, se sabe.
    """
    mesa = db.query(MesaConciliacionRecord).filter(MesaConciliacionRecord.id == mesa_id).first()
    if mesa is None:
        return {"estado": "no_existe"}
    mesa.estado = MESA_ABIERTA
    mesa.cerrado_en = None
    mesa.cerrado_por = None
    db.commit()
    logger.info(f"[MESA] reabierta id={mesa_id} por={usuario}")
    return {"estado": MESA_ABIERTA}


def a_excel(db: Any, mesa: MesaConciliacionRecord, modelo: bytes) -> bytes:
    """El acta del formato oficial, con lo que se concilió en la mesa."""
    encabezado = armador.Encabezado(
        nit=mesa.nit or "",
        razon_social=mesa.razon_social or "",
        numero_acta=mesa.numero_acta or "",
        periodo=mesa.periodo or "",
        fecha_conciliacion=mesa.fecha_conciliacion.date() if mesa.fecha_conciliacion else None,
    )
    resultado = armador.Resultado(acta=a_acta(db, mesa))
    return armador.escribir_en_modelo(resultado, modelo, encabezado, marcar_pendientes=False)


# ═══════════════════════════════════════════════════════════════════════
#  El detalle de un renglón: lo que hace falta para refutar en la mesa
# ═══════════════════════════════════════════════════════════════════════


def _soportes_de(factura: str) -> dict:
    """Qué soportes tiene esa factura, con su estado explícito.

    La lectura y la validación viven en `soportes_contrato`: ahí los datos
    del indexador pasan por Pydantic una sola vez, en vez de que cada
    pantalla los interprete a su manera. Eso ya costó un error real —el
    cajón mostraba «3 soportes» con tres renglones en blanco— y por eso
    ninguna pantalla vuelve a leer al indexador directo.

    CINCO estados, no dos. «Tiene», «no tiene», «todavía no sé», «no pude
    mirar» y «me contestaron basura» son cinco cosas distintas, y en una
    mesa confundirlas manda a aceptar una glosa que sí estaba soportada.
    """
    from app.services.soportes_contrato import leer_soportes

    return leer_soportes(factura).model_dump(mode="json")


def detalle_linea(db: Any, mesa_id: int, linea_id: int) -> dict:
    """Todo lo que el auditor necesita ver de un renglón sin salir de la mesa.

    En una audiencia, cuando la EPS sostiene una glosa, la pregunta es
    siempre la misma: **¿qué tenemos para refutar esto?** La respuesta está
    repartida en el motor —el dictamen que ya se escribió, los soportes que
    hay en el archivo, lo que anotó un compañero— y hasta ahora había que ir
    a buscarla a otra pantalla, con la EPS esperando.
    """
    from app.models.db import ComentarioGlosaRecord, GlosaRecord

    linea = (
        db.query(MesaLineaRecord)
        .filter(MesaLineaRecord.id == linea_id)
        .filter(MesaLineaRecord.mesa_id == mesa_id)
        .first()
    )
    if linea is None:
        return {"estado": "no_existe"}

    salida: dict = {
        "estado": "ok",
        "linea_id": linea.id,
        "factura": linea.factura or "",
        "cod_glosa": linea.cod_glosa or "",
        "descripcion": linea.descripcion or "",
        "glosa_id": linea.glosa_id,
        "soportes": _soportes_de(linea.factura or ""),
        "glosa": None,
        "comentarios": [],
    }

    if not linea.glosa_id:
        salida["nota"] = (
            "Esta glosa no está en el historial del motor: vino en el archivo de "
            "la EPS y no se recibió por el flujo normal. No hay dictamen ni "
            "comentarios que mostrar."
        )
        return salida

    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == linea.glosa_id).first()
    if glosa is not None:
        salida["glosa"] = {
            "id": glosa.id,
            "eps": glosa.eps or "",
            "factura": glosa.factura or "",
            "codigo_glosa": glosa.codigo_glosa or "",
            "codigo_respuesta": getattr(glosa, "codigo_respuesta", "") or "",
            "etapa": glosa.etapa or "",
            "estado": glosa.estado or "",
            "workflow_state": getattr(glosa, "workflow_state", "") or "",
            "valor_objetado": glosa.valor_objetado or 0.0,
            "valor_aceptado": glosa.valor_aceptado or 0.0,
            # El dictamen es HTML que ya escribió el motor: es LO que se lee
            # en la mesa para sostener la posición del hospital.
            "dictamen": glosa.dictamen or "",
            "dictamen_generado_en": (
                glosa.dictamen_generado_en.isoformat() if glosa.dictamen_generado_en else None
            ),
            "observacion_eps": getattr(glosa, "observacion_eps", "") or "",
        }

    comentarios = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.glosa_id == linea.glosa_id)
        .order_by(ComentarioGlosaRecord.id.desc())
        .limit(50)
        .all()
    )
    salida["comentarios"] = [
        {
            "id": c.id,
            "autor": c.autor_nombre or c.autor_email or "",
            "texto": c.texto or "",
            "resuelto": bool(c.resuelto),
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
        }
        for c in comentarios
    ]
    return salida


def soportes_de_la_mesa(db: Any, mesa_id: int) -> dict:
    """Cuántos soportes tiene cada factura de la mesa, de una sola pasada.

    Se consulta POR FACTURA y no por renglón: una factura con doce glosas
    comparte sus soportes, y preguntarlo doce veces sería recorrer el índice
    doce veces para la misma respuesta.
    """
    facturas = {x.factura for x in lineas_de(db, mesa_id) if x.factura}
    return {f: _soportes_de(f) for f in sorted(facturas)}


# ═══════════════════════════════════════════════════════════════════════
#  Soportes que se suben EN la mesa
# ═══════════════════════════════════════════════════════════════════════
#
# El indexador del hospital solo LEE lo que ya estaba archivado, y reconstruye
# su índice cada tantas horas. Lo que aparece en plena audiencia —el correo
# que manda el médico, la autorización que la EPS pide en el momento— no está
# ahí y no puede esperar a la próxima pasada del indexador.
#
# EL ARCHIVO VA A DISCO Y SE ESCRIBE POR PEDAZOS. Los escaneos de cartera
# pesan entre 25 y 40 MB. La primera versión los leía enteros a memoria y los
# guardaba como base64 en la base: eso los inflaba un 33% y obligaba a
# cargarlos completos para cualquier cosa, hasta para listarlos. El
# contenedor del hospital corre con 640 MB de tope —y su propio
# docker-compose documenta que el OOM killer ya mató procesos antes—, así
# que listar diez soportes lo habría tumbado en plena audiencia.
#
# Ahora se escribe en pedazos de 1 MB y la memoria que se usa no depende del
# tamaño del archivo.

# Un soporte de mesa es un PDF o una foto de un documento. Nada más: aceptar
# ejecutables o comprimidos por este camino sería abrirle la puerta a que
# entre cualquier cosa a la carpeta del motor.
TIPOS_DE_SOPORTE_OK = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/tiff": ".tif",
}

# 50 MB. El tope lo dictaron los archivos de verdad: los escaneos de cartera
# pesan entre 25 y 40 MB, así que 15 MB —el número con el que nació esto— los
# dejaba a todos afuera. Se deja margen para el escaneo grande sin abrir la
# puerta a que alguien suba un video por equivocación.
MAX_BYTES_SOPORTE = 50 * 1024 * 1024

# De a un mega. Es lo que se sostiene en memoria de cada archivo, pese al
# tamaño que tenga.
_PEDAZO = 1024 * 1024

# Las primeras firmas de cada formato. El `content-type` lo manda el
# navegador y se puede poner a mano: un .exe renombrado a .pdf llega
# diciendo «application/pdf». Se comprueba lo que el archivo ES.
_FIRMAS = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/jpg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
}


class SoporteRechazado(ValueError):
    """El archivo no se puede guardar, con el motivo en español."""


def carpeta_de_soportes() -> Path:
    """Dónde viven los archivos subidos en las mesas.

    Va bajo el mismo volumen persistente que la base (`/data` en el
    hospital). Si fuera una ruta del contenedor a secas, los soportes se
    perderían en la próxima actualización —y el motor se actualiza solo cada
    cinco minutos—, o sea que la evidencia de una audiencia duraría minutos.
    """
    raiz = os.environ.get("SOPORTES_MESA_ROOT", "").strip()
    if not raiz:
        soportes = os.environ.get("SOPORTES_ROOT", "").strip()
        raiz = (
            os.path.join(os.path.dirname(soportes), "soportes_mesa")
            if soportes
            else "data/soportes_mesa"
        )
    ruta = Path(raiz)
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _validar_tipo(nombre: str, mime: str) -> str:
    """El tipo declarado. Levanta `SoporteRechazado` si no se acepta."""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime not in TIPOS_DE_SOPORTE_OK:
        raise SoporteRechazado(
            f"«{nombre}» es de tipo «{mime or 'desconocido'}». Acá solo entran "
            "PDF e imágenes (PNG, JPG, WEBP, TIFF). Un Excel o un Word se pasa "
            "primero a PDF."
        )
    return mime


def _validar_firma(nombre: str, mime: str, comienzo: bytes) -> None:
    """Que el archivo SEA lo que dice ser, mirando sus primeros bytes."""
    firmas = _FIRMAS.get(mime, ())
    if firmas and not any(comienzo.startswith(f) for f in firmas):
        raise SoporteRechazado(
            f"«{nombre}» dice ser {mime} pero su contenido no lo es. Puede que le "
            "hayan cambiado la extensión a mano, o que se haya dañado al copiarlo. "
            "No se guarda: un soporte que no abre no sirve de evidencia."
        )


def _mensaje_muy_pesado(nombre: str, bytes_leidos: int) -> str:
    return (
        f"«{nombre}» pasa de {MAX_BYTES_SOPORTE // (1024 * 1024)} MB, que es el "
        f"tope (llevaba {bytes_leidos / (1024 * 1024):.1f} MB). Si es un PDF "
        "escaneado, bájele el peso con la caja de Herramientas PDF antes de "
        "subirlo."
    )


def validar_soporte(nombre: str, mime: str, contenido: bytes) -> str:
    """Comprueba peso, tipo y contenido real de un archivo ya en memoria.

    Se conserva para quien tenga los bytes a mano (una prueba, un bot). El
    camino de la pantalla NO pasa por acá: usa `guardar_soporte_en_disco`,
    que no carga el archivo entero.
    """
    if not contenido:
        raise SoporteRechazado(
            f"«{nombre}» llegó vacío (0 bytes). Vuelva a seleccionarlo; puede que "
            "el archivo esté abierto en otro programa."
        )
    if len(contenido) > MAX_BYTES_SOPORTE:
        raise SoporteRechazado(_mensaje_muy_pesado(nombre, len(contenido)))
    mime_ok = _validar_tipo(nombre, mime)
    _validar_firma(nombre, mime_ok, contenido[:16])
    return mime_ok


async def guardar_soporte_en_disco(
    archivo: Any, nombre: str, mime: str
) -> tuple[str, str, int, str]:
    """Escribe el archivo por pedazos. Devuelve (mime, ruta relativa, bytes, sha256).

    El tope se comprueba MIENTRAS se escribe, no al final: si alguien manda
    500 MB, se corta a los 50 y se borra lo escrito, en vez de sostenerlos en
    memoria para después decir que no. Con 640 MB de contenedor, esa
    diferencia es que el motor siga vivo o no.
    """
    mime_ok = _validar_tipo(nombre, mime)
    carpeta = carpeta_de_soportes()
    # Nombre en disco propio: el que puso el usuario puede traer barras,
    # tildes o `..` y terminar escribiendo fuera de la carpeta.
    relativa = f"{datetime.now(timezone.utc):%Y%m}/{uuid.uuid4().hex}{TIPOS_DE_SOPORTE_OK[mime_ok]}"
    destino = carpeta / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)

    resumen = hashlib.sha256()
    total = 0
    primeros = b""
    try:
        with open(destino, "wb") as f:
            while True:
                pedazo = await archivo.read(_PEDAZO)
                if not pedazo:
                    break
                if not primeros:
                    primeros = pedazo[:16]
                    _validar_firma(nombre, mime_ok, primeros)
                total += len(pedazo)
                if total > MAX_BYTES_SOPORTE:
                    raise SoporteRechazado(_mensaje_muy_pesado(nombre, total))
                resumen.update(pedazo)
                f.write(pedazo)
        if total == 0:
            raise SoporteRechazado(
                f"«{nombre}» llegó vacío (0 bytes). Vuelva a seleccionarlo; puede "
                "que el archivo esté abierto en otro programa."
            )
    except Exception:
        # Un archivo a medio escribir no es evidencia de nada y ocupa disco.
        destino.unlink(missing_ok=True)
        raise
    return mime_ok, relativa, total, resumen.hexdigest()


def registrar_soporte(
    db: Any,
    mesa_id: int,
    factura: str,
    nombre: str,
    mime: str,
    ruta_relativa: str,
    tamano: int,
    sha256: str,
    autor: str,
    nota: str = "",
) -> dict:
    """Anota en la base un soporte que ya quedó escrito en disco."""
    from app.models.db import SoporteMesaRecord

    reg = SoporteMesaRecord(
        mesa_id=mesa_id,
        factura=(factura or "").strip()[:50],
        nombre=(nombre or "archivo")[:300],
        mime_type=mime,
        tamano_bytes=tamano,
        ruta_relativa=ruta_relativa,
        sha256=sha256,
        # La columna nació NOT NULL y SQLite no sabe quitarlo con un ALTER.
        # Los soportes nuevos no la usan: va vacía a propósito.
        contenido_b64="",
        nota=(nota or "")[:500],
        subido_por=(autor or "")[:200],
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    logger.info(
        f"[MESA] soporte en la mesa {mesa_id} / factura {factura}: "
        f"{reg.nombre} ({tamano / 1048576:.1f} MB)"
    )
    return _soporte_a_dict(reg)


def subir_soporte(
    db: Any,
    mesa_id: int,
    factura: str,
    nombre: str,
    mime: str,
    contenido: bytes,
    autor: str,
    nota: str = "",
) -> dict:
    """Guarda un soporte que ya está en memoria (pruebas, bots).

    La pantalla no usa este camino —usa el que escribe por pedazos—, pero
    tener los bytes a mano es cómodo para probar.
    """
    factura = (factura or "").strip()
    if not factura:
        raise SoporteRechazado("No se indicó a qué factura pertenece el soporte.")
    mime_ok = validar_soporte(nombre or "archivo", mime, contenido)

    carpeta = carpeta_de_soportes()
    relativa = f"{datetime.now(timezone.utc):%Y%m}/{uuid.uuid4().hex}{TIPOS_DE_SOPORTE_OK[mime_ok]}"
    destino = carpeta / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)

    return registrar_soporte(
        db,
        mesa_id=mesa_id,
        factura=factura,
        nombre=nombre,
        mime=mime_ok,
        ruta_relativa=relativa,
        tamano=len(contenido),
        sha256=hashlib.sha256(contenido).hexdigest(),
        autor=autor,
        nota=nota,
    )


def _soporte_a_dict(reg: Any) -> dict:
    return {
        "id": reg.id,
        "factura": reg.factura or "",
        "nombre": reg.nombre or "",
        "mime_type": reg.mime_type or "",
        "tamano_bytes": reg.tamano_bytes or 0,
        "nota": reg.nota or "",
        "subido_por": reg.subido_por or "",
        "subido_en": reg.subido_en.isoformat() if reg.subido_en else None,
    }


def soportes_subidos(db: Any, mesa_id: int, factura: str = "") -> list[dict]:
    """Los soportes subidos en esta mesa (opcionalmente, de una factura).

    Se piden SOLO las columnas que se muestran. Traer la fila entera
    arrastraría `contenido_b64` de los soportes viejos —hasta 53 MB de texto
    cada uno— y listar diez tumbaría el contenedor.
    """
    from app.models.db import SoporteMesaRecord

    columnas = (
        SoporteMesaRecord.id,
        SoporteMesaRecord.factura,
        SoporteMesaRecord.nombre,
        SoporteMesaRecord.mime_type,
        SoporteMesaRecord.tamano_bytes,
        SoporteMesaRecord.nota,
        SoporteMesaRecord.subido_por,
        SoporteMesaRecord.subido_en,
    )
    q = db.query(*columnas).filter(SoporteMesaRecord.mesa_id == mesa_id)
    if factura:
        q = q.filter(SoporteMesaRecord.factura == factura.strip()[:50])
    return [_soporte_a_dict(fila) for fila in q.order_by(SoporteMesaRecord.id.desc()).all()]


def ruta_del_soporte(
    db: Any, mesa_id: int, soporte_id: int
) -> Optional[tuple[Any, Optional[Path]]]:
    """El registro y la ruta en disco de un soporte, para bajarlo.

    Se filtra por mesa además de por id: sin eso, cambiar el número en la
    dirección dejaría bajar los soportes de la mesa de otra EPS.

    La ruta viene `None` en los soportes viejos, que están en la base. Para
    esos hay `contenido_del_soporte`.
    """
    from app.models.db import SoporteMesaRecord

    reg = (
        db.query(SoporteMesaRecord)
        .filter(SoporteMesaRecord.id == soporte_id)
        .filter(SoporteMesaRecord.mesa_id == mesa_id)
        .first()
    )
    if reg is None:
        return None
    if not reg.ruta_relativa:
        return reg, None
    ruta = carpeta_de_soportes() / reg.ruta_relativa
    if not ruta.is_file():
        logger.warning(f"[MESA] el soporte {soporte_id} no está en disco: {ruta}")
        return reg, None
    return reg, ruta


def contenido_del_soporte(reg: Any) -> Optional[bytes]:
    """Los bytes de un soporte guardado en la base (los de antes del 08-09)."""
    if not reg.contenido_b64:
        return None
    try:
        return base64.b64decode(reg.contenido_b64)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[MESA] soporte {reg.id} ilegible: {e}")
        return None


def borrar_soporte_subido(db: Any, mesa_id: int, soporte_id: int) -> bool:
    from app.models.db import SoporteMesaRecord

    reg = (
        db.query(SoporteMesaRecord)
        .filter(SoporteMesaRecord.id == soporte_id)
        .filter(SoporteMesaRecord.mesa_id == mesa_id)
        .first()
    )
    if reg is None:
        return False
    relativa = reg.ruta_relativa
    db.delete(reg)
    db.commit()
    # El archivo se borra DESPUÉS de que la base confirmó. Al revés, si la
    # base fallara quedaría un renglón apuntando a un archivo que ya no está.
    if relativa:
        (carpeta_de_soportes() / relativa).unlink(missing_ok=True)
    return True
