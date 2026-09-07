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

from datetime import datetime, timezone
from typing import Any

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
    aprendido = armador.aprender(
        db, a_acta(db, mesa).lineas, numero_acta=mesa.numero_acta or "", usuario=usuario
    )
    mesa.estado = MESA_CERRADA
    mesa.cerrado_en = datetime.now(timezone.utc)
    mesa.cerrado_por = (usuario or "")[:200]
    db.commit()
    logger.info(f"[MESA] cerrada id={mesa_id} por={usuario} aprendido={aprendido}")
    return {"estado": MESA_CERRADA, "resumen": cifras, "aprendido": aprendido}


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
