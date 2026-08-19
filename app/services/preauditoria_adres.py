"""Pre-auditoría de paquetes de glosas del ADRES.

Trae al sistema lo que hasta ahora vivía en un Excel con macro: el reporte de
glosas del ADRES ítem por ítem, ya clasificado, con el centro de costos
propuesto y con una sugerencia de respuesta para cada glosa. Así el gestor
escribe un número de factura y tiene todo al frente, sin abrir un solo Excel.

Las reglas (clasificación por causal, centro de costos, sugerencia, texto de
respuesta) **no se reescriben acá**: son las mismas de
`tools/preauditar_glosas_adres.py`, ya verificadas contra las 4.619 filas que
el equipo había llenado a mano. Este módulo solo las conecta con la base.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.utils.moneda import parse_valor_cop
from app.models.db import (
    FacturaAdresRecord,
    GlosaAdresRecord,
    ItemDetalladoAdresRecord,
    PaqueteAdresRecord,
)

# Los scripts de tools/ son la fuente única de las reglas: se importan por ruta
# para no tener dos copias del criterio.
_TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from ajustar_detallado_glosas import normalizar_factura  # noqa: E402
from glosas_adres_por_factura import (  # noqa: E402
    aceptado_sin_duplicar,
    leer_oficiales,
    marcar_conteo,
)
from preauditar_glosas_adres import (  # noqa: E402
    CATALOGO_CENTROS_COSTOS,
    CAUSALES_DE_DOS_AREAS,
    DECISIONES,
    TEXTO_EXTEMPORANEA,
    FilaMacro,
    aprender_decisiones,
    armar_texto_respuesta,
    centro_de_costos,
    centro_oficial,
    clasificar,
    codigo_numerico,
    leer_macro,
    leer_reporte,
    necesita_asignacion,
    preauditar,
    reparto_de_area,
    sugerir,
    trabajo_ya_hecho,
)

__all__ = [
    "CATALOGO_CENTROS_COSTOS",
    "CAUSALES_DE_DOS_AREAS",
    "DECISIONES",
    "TEXTO_EXTEMPORANEA",
    "aprender_decisiones",
    "armar_texto_respuesta",
    "asignar_area",
    "catalogo_centros",
    "centro_de_costos",
    "centro_oficial",
    "clasificar",
    "codigo_numerico",
    "cambiar_estado_factura",
    "consultar_factura",
    "glosa_dict",
    "listar_facturas",
    "guardar_decision",
    "importar_bitacora",
    "importar_reporte",
    "sugerir",
    "texto_respuesta_factura",
]


# ─── Importar ────────────────────────────────────────────────────────────────


def importar_reporte(
    db: Session,
    contenido: bytes,
    *,
    nombre_archivo: str,
    importado_por: str,
    paquete: str | None = None,
    macro: bytes | None = None,
    facturas: bytes | None = None,
    reemplazar: bool = True,
) -> PaqueteAdresRecord:
    """Carga el `ReporteGlosasReclamPAQUETE` y lo deja pre-auditado en la base.

    Si ya había un cargue del mismo paquete, `reemplazar` borra el anterior
    para no duplicar filas — pero **conserva las decisiones ya tomadas**, que
    se vuelven a aplicar sobre las filas nuevas.

    `macro` es el Excel con el que el equipo venía trabajando: de ahí salen el
    reparto gestor/médico, la clasificación afinada y lo que ya habían escrito.

    `facturas` es el archivo `FACTURAS PAQUETE NNNNN_NN FACTURAS.xlsx`. Conviene
    mandarlo: trae la **cifra oficial** de glosa por factura, que es la única
    buena — el reporte por ítem repite renglones y suma de más.
    """
    filas = _leer_temporal(contenido, ".xlsx", lambda p: leer_reporte(p, paquete=paquete))
    if not filas:
        raise ValueError("El reporte no trajo ninguna fila glosada.")

    numero = paquete or (filas[0].paquete or "").strip()

    # Lo que el equipo ya decidió: primero lo que hay en la base, y si mandan el
    # Excel de la macro, también lo que venían llevando ahí.
    decididas = _decisiones_previas(db, numero)
    # También antes de borrar: qué facturas ya estaban cerradas.
    estados = _estados_previos(db, numero)
    aprendidas = _aprender_de_la_base(decididas)
    tabla_clasificacion = None
    reparto: dict[str, tuple[str, str]] = {}
    hecho: dict[tuple, list[dict]] = {}
    catalogo: list[str] = list(CATALOGO_CENTROS_COSTOS)
    if macro:
        aprendida_clasif, reparto, centros, filas_macro = _leer_temporal(macro, ".xlsm", leer_macro)
        # El catálogo de la macro manda: puede haber cambiado el plan de cuentas.
        if centros:
            catalogo = centros
        tabla_clasificacion = aprendida_clasif or None
        hecho = trabajo_ya_hecho(filas_macro)
        de_la_macro = aprender_decisiones(filas_macro)
        aprendidas = {**de_la_macro, **aprendidas}  # la base manda sobre el Excel

    resumen = preauditar(
        filas,
        tabla_clasificacion=tabla_clasificacion,
        reparto=reparto,
        aprendidas=aprendidas,
        hecho=hecho,
    )

    # El reporte abre una fila por causal del mismo ítem. Se conservan todas
    # (el gestor decide causal por causal) pero solo una cuenta para la plata.
    por_factura_filas: dict[str, list] = {}
    for f in resumen.filas:
        por_factura_filas.setdefault(normalizar_factura(f.factura), []).append(f)
    cuenta: dict[int, bool] = {}
    for grupo in por_factura_filas.values():
        for f, marca in zip(grupo, marcar_conteo(grupo), strict=True):
            cuenta[id(f)] = marca

    # La cifra oficial por factura, si mandaron el archivo de facturas.
    oficiales: dict[str, float] = {}
    if facturas:
        try:
            oficiales = _leer_temporal(facturas, ".xlsx", leer_oficiales)
        except Exception as e:  # noqa: BLE001 - sin esto se sigue, solo sin verificar
            logger.warning("No se pudo leer el archivo de facturas del paquete: %s", e)

    if reemplazar:
        _borrar_paquete(db, numero)

    registro = PaqueteAdresRecord(
        numero_paquete=numero,
        archivo=nombre_archivo,
        importado_por=importado_por,
        total_filas=len(resumen.filas),
        total_facturas=resumen.facturas,
        # La plata del paquete: sin contar dos veces el mismo ítem, y si vino
        # el archivo oficial, la de ese archivo, que es la que manda.
        valor_glosado=(
            round(sum(oficiales.values()), 2)
            if oficiales
            else sum(f.valor_glosado for f in resumen.filas if cuenta.get(id(f), True))
        ),
        catalogo_centros=json.dumps(catalogo, ensure_ascii=False),
    )
    db.add(registro)
    db.flush()

    rescatadas = 0
    consumidas: dict[tuple, int] = {}
    for f in resumen.filas:
        clave_factura = normalizar_factura(f.factura)
        fila = GlosaAdresRecord(
            paquete_id=registro.id,
            factura_clave=clave_factura,
            factura=f.factura,
            radicacion=f.radicacion,
            cod_habilitacion=f.cod_habilitacion,
            doc_victima=f.doc_victima,
            consecutivo=f.consecutivo,
            tipo_elemento=f.tipo_elemento,
            codigo=f.codigo,
            descripcion=f.descripcion,
            causal_codigo=f.codigo_numerico,
            causal_texto=f.descripcion_glosa,
            anotacion=f.anotacion,
            cant_reclamada=f.cant_reclamada,
            valor_reclamado=f.valor_reclamado,
            cant_aprobada=f.cant_aprobada,
            valor_aprobado=f.valor_aprobado,
            valor_glosado=f.valor_glosado,
            clasificacion=f.clasificacion,
            centro_costos=centro_oficial(f.centro_costos, catalogo),
            gestor=f.gestor,
            medico=f.medico,
            sugerencia=f.sugerencia,
            confianza=f.confianza,
            motivo=f.motivo,
            decision=(f.observacion or "").strip() or None,
            observacion_tecnico=f.observacion_tecnico or None,
            cantidad_aceptada=f.cantidad_aceptada or None,
            valor_aceptado=f.valor_aceptado or 0,
        )
        # Sin causal propia, esta fila es el desglose de una GLOSA TOTAL: el
        # ADRES glosó la reclamación entera por el FURIPS. No se responde ítem
        # por ítem, así que la pantalla no la muestra.
        fila.glosa_total = not f.codigo_numerico
        fila.cuenta_valor = cuenta.get(id(f), True)
        # Causales que trabajan dos áreas (la 4506): el bot no las clasifica
        # solo, las marca para que un SUPER ADMIN las reparta.
        if necesita_asignacion(f.codigo_numerico):
            area, motivo_area = reparto_de_area(f.codigo_numerico, f.tipo_elemento, f.descripcion)
            fila.requiere_asignacion = True
            fila.area_sugerida = area
            fila.motivo_area = motivo_area
        if fila.decision:
            fila.decidido_por = "(venía en la macro)"
            rescatadas += 1
        # Devolverle al equipo lo que ya había decidido para esa misma glosa.
        clave = (clave_factura, (f.codigo or "").strip().upper(), round(f.valor_glosado, 2))
        previas = decididas.get(clave)
        if previas:
            n = consumidas.get(clave, 0)
            consumidas[clave] = n + 1
            previa = previas[n] if n < len(previas) else previas[-1]
            if previa["decision"]:
                fila.decision = previa["decision"]
                fila.observacion_tecnico = previa["observacion_tecnico"]
                fila.cantidad_aceptada = previa["cantidad_aceptada"]
                fila.valor_aceptado = previa["valor_aceptado"]
                fila.decidido_por = previa["decidido_por"]
                fila.decidido_en = previa["decidido_en"]
            if previa["gestor"]:
                fila.gestor = previa["gestor"]
            if previa["medico"]:
                fila.medico = previa["medico"]
            # El área que repartió el super admin queda firme.
            if previa["area_asignada_por"]:
                fila.clasificacion = previa["clasificacion"]
                fila.area_asignada_por = previa["area_asignada_por"]
                fila.area_asignada_en = previa["area_asignada_en"]
                fila.requiere_asignacion = False
            # El centro de costos escrito a mano también.
            if previa["centro_costos_por"]:
                fila.centro_costos = previa["centro_costos"]
                fila.centro_costos_por = previa["centro_costos_por"]
            rescatadas += 1
        db.add(fila)

    # La lista de facturas a auditar, que es lo primero que ve el gestor.
    # Si una factura ya estaba cerrada en un cargue anterior, sigue cerrada.
    vistas: set[str] = set()
    for f in resumen.filas:
        clave = normalizar_factura(f.factura)
        if clave in vistas:
            continue
        vistas.add(clave)
        antes = estados.get(clave, {})
        db.add(
            FacturaAdresRecord(
                paquete_id=registro.id,
                factura_clave=clave,
                factura=f.factura,
                radicacion=f.radicacion,
                doc_victima=f.doc_victima,
                gestor=f.gestor,
                medico=f.medico,
                valor_glosado_oficial=oficiales.get(clave),
                estado=antes.get("estado") or "PENDIENTE",
                cerrada_por=antes.get("cerrada_por"),
                cerrada_en=antes.get("cerrada_en"),
                reabierta_por=antes.get("reabierta_por"),
                reabierta_en=antes.get("reabierta_en"),
                nota=antes.get("nota"),
            )
        )

    db.commit()
    logger.info(
        "Paquete ADRES %s importado: %d filas, %d facturas, %d decisión(es) conservada(s)",
        numero,
        len(resumen.filas),
        resumen.facturas,
        rescatadas,
    )
    return registro


def _estados_previos(db: Session, numero_paquete: str) -> dict[str, dict]:
    """Cómo iba cada factura antes de recargar el paquete."""
    if not numero_paquete:
        return {}
    ids = [
        p[0]
        for p in db.query(PaqueteAdresRecord.id)
        .filter(PaqueteAdresRecord.numero_paquete == numero_paquete)
        .all()
    ]
    if not ids:
        return {}
    salida: dict[str, dict] = {}
    for f in db.query(FacturaAdresRecord).filter(FacturaAdresRecord.paquete_id.in_(ids)).all():
        salida[f.factura_clave] = {
            "estado": f.estado,
            "cerrada_por": f.cerrada_por,
            "cerrada_en": f.cerrada_en,
            "reabierta_por": f.reabierta_por,
            "reabierta_en": f.reabierta_en,
            "nota": f.nota,
        }
    return salida


def _leer_temporal(contenido: bytes, sufijo: str, leer):
    """Los lectores de tools/ trabajan sobre rutas; el web recibe bytes."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=sufijo, delete=False) as fh:
        fh.write(contenido)
        tmp = Path(fh.name)
    try:
        return leer(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def _decisiones_previas(db: Session, numero_paquete: str) -> dict[tuple, list[dict]]:
    """Decisiones ya tomadas para ese paquete, indexadas por glosa."""
    if not numero_paquete:
        return {}
    paquetes = (
        db.query(PaqueteAdresRecord.id)
        .filter(PaqueteAdresRecord.numero_paquete == numero_paquete)
        .all()
    )
    ids = [p[0] for p in paquetes]
    if not ids:
        return {}
    salida: dict[tuple, list[dict]] = {}
    # Se rescata todo lo que tenga trabajo humano encima: la decisión del
    # gestor, el área que repartió el super admin o el centro de costos que
    # alguien corrigió a mano. Nada de eso se puede perder al recargar.
    filas = (
        db.query(GlosaAdresRecord)
        .filter(GlosaAdresRecord.paquete_id.in_(ids))
        .filter(
            GlosaAdresRecord.decision.isnot(None)
            | GlosaAdresRecord.area_asignada_por.isnot(None)
            | GlosaAdresRecord.centro_costos_por.isnot(None)
        )
        .all()
    )
    for f in filas:
        clave = (f.factura_clave, (f.codigo or "").strip().upper(), round(f.valor_glosado or 0, 2))
        salida.setdefault(clave, []).append(
            {
                "decision": f.decision,
                "observacion_tecnico": f.observacion_tecnico,
                "cantidad_aceptada": f.cantidad_aceptada,
                "valor_aceptado": f.valor_aceptado,
                "decidido_por": f.decidido_por,
                "decidido_en": f.decidido_en,
                "gestor": f.gestor,
                "medico": f.medico,
                "causal": f.causal_codigo,
                "clasificacion": f.clasificacion,
                "area_asignada_por": f.area_asignada_por,
                "area_asignada_en": f.area_asignada_en,
                "centro_costos": f.centro_costos,
                "centro_costos_por": f.centro_costos_por,
            }
        )
    return salida


def _aprender_de_la_base(decididas: dict[tuple, list[dict]]) -> dict[str, tuple[str, int, int]]:
    """El criterio del equipo por causal, sacado de lo que ya decidió."""
    plano = [
        {
            "Descripción Glosa": (p["causal"] or "") + "-",
            "OBSERVACION (SE ACEPTA - SE OBJETA -  SE SUBSANA )": p["decision"],
        }
        for previas in decididas.values()
        for p in previas
    ]
    return aprender_decisiones(plano)


def _borrar_paquete(db: Session, numero_paquete: str) -> None:
    if not numero_paquete:
        return
    ids = [
        p[0]
        for p in db.query(PaqueteAdresRecord.id)
        .filter(PaqueteAdresRecord.numero_paquete == numero_paquete)
        .all()
    ]
    if not ids:
        return
    db.query(GlosaAdresRecord).filter(GlosaAdresRecord.paquete_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(ItemDetalladoAdresRecord).filter(ItemDetalladoAdresRecord.paquete_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(FacturaAdresRecord).filter(FacturaAdresRecord.paquete_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(PaqueteAdresRecord).filter(PaqueteAdresRecord.id.in_(ids)).delete(
        synchronize_session=False
    )
    db.flush()


def importar_bitacora(db: Session, contenido: bytes, *, paquete_id: int) -> int:
    """Carga la bitácora del ajustador de detallados (el CSV ítem por ítem)."""
    texto = contenido.decode("utf-8-sig", errors="replace")
    db.query(ItemDetalladoAdresRecord).filter(
        ItemDetalladoAdresRecord.paquete_id == paquete_id
    ).delete(synchronize_session=False)

    def num(v):
        """Lee un valor en pesos de la bitácora con el lector único del repo.

        19-08-2026. Antes hacía `float(str(v).replace(",", "."))`. Eso sirve
        para el CSV tal como lo escribe el ajustador (93340.00), pero si el
        auditor abre esa bitácora en Excel y la guarda, Excel la reescribe al
        formato colombiano y entonces:
            "93.340"       ->    93.34   (mil veces menos)
            "1.589.100,00" ->     0.0    (¡en silencio!, por el except)
        Y esos valores son el glosado/reclamado/aprobado de cada ítem del
        detallado. `parse_valor_cop` entiende los dos formatos y deja igual el
        que ya funcionaba."""
        return parse_valor_cop(v)

    n = 0
    for fila in csv.DictReader(io.StringIO(texto), delimiter=";"):
        factura = (fila.get("FACTURA") or "").strip()
        accion = (fila.get("ACCION") or "").strip()
        if not factura or accion in ("ELIMINADA", ""):
            continue
        db.add(
            ItemDetalladoAdresRecord(
                paquete_id=paquete_id,
                factura_clave=normalizar_factura(factura),
                factura=factura,
                grupo=(fila.get("GRUPO") or "").strip(),
                codigo=(fila.get("CODIGO") or "").strip(),
                nombre=(fila.get("NOMBRE") or "").strip(),
                cantidad=num(fila.get("CANT_ORIGINAL")),
                valor_facturado=num(fila.get("VR_ENT_ORIGINAL")),
                valor_reclamado=num(fila.get("VALOR_RECLAMADO")),
                valor_aprobado=num(fila.get("VALOR_APROBADO")),
                valor_glosado=num(fila.get("VALOR_GLOSADO")),
                accion=accion,
                cantidad_nueva=num(fila.get("CANT_NUEVA")),
                valor_nuevo=num(fila.get("VR_ENT_NUEVO")),
                cruce_por=(fila.get("CRUCE_POR") or "").strip(),
                tipo_renglon=(fila.get("TIPO_RENGLON") or "").strip(),
                causales=(fila.get("CAUSALES_GLOSA") or "").strip(),
                observacion=(fila.get("OBSERVACION") or "").strip(),
            )
        )
        n += 1
    db.commit()
    logger.info("Bitácora del paquete %s: %d ítem(s) del detallado", paquete_id, n)
    return n


# ─── Consultar ───────────────────────────────────────────────────────────────


def consultar_factura(
    db: Session,
    numero: str,
    *,
    paquete_id: int | None = None,
    incluir_totales: bool = False,
) -> dict:
    """Todo lo que el sistema sabe de esa factura, listo para la pantalla.

    Por defecto **no se muestran las glosas totales**: son el desglose de una
    reclamación glosada entera por el FURIPS, no traen causal propia y no se
    responden ítem por ítem. Se cuentan aparte para que nada desaparezca en
    silencio, y con `incluir_totales` se pueden ver.
    """
    clave = normalizar_factura(numero)
    q = db.query(GlosaAdresRecord).filter(GlosaAdresRecord.factura_clave == clave)
    if paquete_id:
        q = q.filter(GlosaAdresRecord.paquete_id == paquete_id)
    todas = q.order_by(GlosaAdresRecord.id).all()
    if not todas:
        return {"encontrada": False, "factura": numero, "glosas": [], "items": []}
    totales = [g for g in todas if g.glosa_total]
    glosas = todas if incluir_totales else [g for g in todas if not g.glosa_total]

    q2 = db.query(ItemDetalladoAdresRecord).filter(ItemDetalladoAdresRecord.factura_clave == clave)
    if paquete_id:
        q2 = q2.filter(ItemDetalladoAdresRecord.paquete_id == paquete_id)
    items = q2.order_by(ItemDetalladoAdresRecord.id).all()

    primera = todas[0]
    paquete = db.get(PaqueteAdresRecord, primera.paquete_id)
    ficha = (
        db.query(FacturaAdresRecord)
        .filter(FacturaAdresRecord.paquete_id == primera.paquete_id)
        .filter(FacturaAdresRecord.factura_clave == clave)
        .first()
    )
    decididas = [g for g in glosas if g.decision]
    sigue_glosado = sum(
        (i.valor_nuevo or 0) for i in items if i.accion in ("CONSERVADO", "AJUSTADO")
    )

    return {
        "encontrada": True,
        "factura": primera.factura,
        "factura_clave": clave,
        "paquete": {
            "id": paquete.id if paquete else None,
            "numero": paquete.numero_paquete if paquete else "",
            "importado_en": paquete.importado_en.isoformat()
            if paquete and paquete.importado_en
            else None,
        },
        "radicacion": primera.radicacion,
        "documento_paciente": primera.doc_victima,
        "gestor": primera.gestor,
        "medico": primera.medico,
        "resumen": {
            "glosas": len(glosas),
            "decididas": len(decididas),
            "pendientes": len(glosas) - len(decididas),
            # Solo los renglones que cuentan: el mismo ítem con varias causales
            # sale varias veces y su plata es una sola.
            "valor_glosado": sum((g.valor_glosado or 0) for g in glosas if g.cuenta_valor),
            "valor_aceptado": aceptado_consolidado(glosas),
            "valor_reclamado": sum((g.valor_reclamado or 0) for g in glosas if g.cuenta_valor),
            "items_detallado": len(items),
            "sigue_glosado_detallado": sigue_glosado,
            "por_asignar": sum(1 for g in glosas if g.requiere_asignacion),
            "sin_centro_costos": sum(1 for g in glosas if not (g.centro_costos or "").strip()),
            # Las glosas totales no se muestran, pero se dicen: nada desaparece
            # en silencio.
            "glosas_totales_ocultas": len(totales),
            "valor_glosas_totales": sum((g.valor_glosado or 0) for g in totales if g.cuenta_valor),
        },
        "valor_glosado_oficial": ficha.valor_glosado_oficial if ficha else None,
        "aviso_descuadre": _aviso_descuadre(ficha, todas),
        "estado": ficha.estado if ficha else "PENDIENTE",
        "cerrada_por": ficha.cerrada_por if ficha else None,
        "cerrada_en": ficha.cerrada_en.isoformat() if ficha and ficha.cerrada_en else None,
        "reabierta_por": ficha.reabierta_por if ficha else None,
        "nota": ficha.nota if ficha else None,
        "aviso_glosas_totales": (
            (
                f"{len(totales)} renglón(es) de esta factura no se muestran porque "
                f"corresponden a una GLOSA TOTAL: el ADRES glosó la reclamación entera por el "
                f"FURIPS y esos renglones no traen causal propia, así que no se responden uno "
                f"por uno ("
                f"{_pesos(sum((g.valor_glosado or 0) for g in totales if g.cuenta_valor))})."
            )
            if totales
            else ""
        ),
        # Si no hay detallado, se dice por qué y se sigue mostrando todo lo que
        # sí se tiene del reporte del ADRES. No se deja al gestor sin nada.
        "aviso_detallado": (
            ""
            if items
            else (
                "Esta factura no tiene detallado cargado. Puede ser que no viniera en los "
                "lotes que se importaron, o que aún no se haya subido la bitácora del "
                "ajustador de detallados. Abajo está todo lo que sí trae el reporte del ADRES."
            )
        ),
        "catalogo_centros": catalogo_centros(db, primera.paquete_id),
        "glosas": [glosa_dict(g) for g in glosas],
        "items": [_item_dict(i) for i in items],
        "por_clasificacion": _agrupar(glosas),
    }


def _pesos(valor) -> str:
    """`$297.117.350` — con punto de miles, como se escribe en Colombia."""
    return "$" + f"{int(round(valor or 0)):,}".replace(",", ".")


def _aviso_descuadre(ficha, todas) -> str:
    """Si el detalle no cuadra con lo que dice el ADRES, se dice.

    En el paquete 31078 pasó en 27 de las 81 facturas: el reporte repite
    renglones sin que haya causales distintas que lo expliquen, y son justo las
    de más plata. Responder con esas cifras es responder con valores dobles o
    triples, que el ADRES puede rechazar por inconsistente.
    """
    if ficha is None or ficha.valor_glosado_oficial is None:
        return ""
    detalle = round(sum((g.valor_glosado or 0) for g in todas if g.cuenta_valor), 2)
    oficial = round(ficha.valor_glosado_oficial, 2)
    if abs(detalle - oficial) < 1:
        return ""
    return (
        f"El ADRES dice que esta factura tiene glosado {_pesos(oficial)}, pero el detalle del "
        f"reporte suma {_pesos(detalle)}. El reporte del ADRES repite renglones. Antes de "
        f"responder esta factura, baje el detalle del portal (Reclamaciones → Reportes Lupa "
        f"al giro)."
    )


def _cantidad_texto(cant: float) -> str:
    """`3` y no `3.0`: la cantidad que se le declara al ADRES es de ítems."""
    return str(int(cant)) if abs(cant - round(cant)) < 0.0001 else str(cant)


def _clave_item(factura_clave: str, codigo: str | None, valor_glosado: float | None) -> tuple:
    """Los renglones del MISMO ítem: misma factura, mismo código, mismo glosado.

    Es la misma clave con la que el importador devuelve las decisiones previas
    (línea 239), y agrupa los renglones que el reporte del ADRES abre por
    causal sobre un solo servicio.
    """
    return (factura_clave, (codigo or "").strip().upper(), round(valor_glosado or 0, 2))


def aceptado_consolidado(glosas) -> float:
    """La plata aceptada de una factura, sin declararla dos veces al ADRES.

    19-08-2026. El reporte del ADRES abre un renglón por cada causal del mismo
    ítem, y la pantalla pide una decisión por renglón —así trabaja el gestor—.
    El GLOSADO ya sabía no contar dos veces (`cuenta_valor`); el ACEPTADO no:
    se sumaban todos los renglones.

    Pasaba de verdad. Factura HUS311371, TAC DE CRÁNEO SIMPLE glosado $700.000
    con dos causales (3209 y 3106): aceptando en las dos, el hospital le
    declaraba al ADRES **$1.400.000 aceptados sobre un ítem glosado $700.000**,
    y el KPI de la factura quedaba con el aceptado por encima del glosado.

    El arreglo NO es copiar el filtro `cuenta_valor`: si el gestor objeta el
    renglón que cuenta y acepta el que no cuenta, el aceptado saldría cero —
    otro dictamen falso, al revés. Se consolida por ítem y se pone tope en lo
    glosado, que da bien en los cuatro casos:

      · acepta todo en las dos causales   → el valor del ítem, una vez;
      · reparte 300 y 400 entre causales  → 700, la suma;
      · acepta solo en la que no cuenta   → 700, no cero;
      · dos ítems iguales de verdad       → 1.400, no 700.
    """
    return aceptado_sin_duplicar(
        (
            _clave_item(g.factura_clave, g.codigo, g.valor_glosado),
            g.valor_glosado or 0,
            g.valor_aceptado or 0,
            bool(g.cuenta_valor),
        )
        for g in glosas
    )


def cantidad_glosada(cant_reclamada: float | None, cant_aprobada: float | None) -> float:
    """Cuántos ítems del renglón quedaron glosados: reclamados menos aprobados.

    19-08-2026. El gestor decide sobre CANTIDADES, no solo sobre plata: en el
    paquete 31068 hay 277 renglones donde el ADRES reclamó 3 ítems, aprobó 1 y
    glosó 2 (ej. HUS353885, dispositivo 2022DM-0008875-R1: 3 reclamados, 1
    aprobado, $9.200 glosados). Sin este número el gestor no sabe cuántos
    aceptar y termina declarando la cantidad completa.

    Puede dar CERO con valor glosado mayor que cero: ahí no le glosaron
    cantidad sino tarifa (ej. HUS354131, CUPS 21706: 1 reclamado, 1 aprobado,
    $100 glosados). Cero es la respuesta correcta y la pantalla lo explica.
    """
    return max(0.0, round((cant_reclamada or 0) - (cant_aprobada or 0), 4))


def glosa_dict(g: GlosaAdresRecord) -> dict:
    return {
        "id": g.id,
        "codigo": g.codigo,
        "descripcion": g.descripcion,
        "tipo_elemento": g.tipo_elemento,
        "causal_codigo": g.causal_codigo,
        "causal_texto": g.causal_texto,
        "anotacion": g.anotacion,
        "cant_reclamada": g.cant_reclamada,
        "valor_reclamado": g.valor_reclamado,
        "cant_aprobada": g.cant_aprobada,
        "valor_aprobado": g.valor_aprobado,
        "cant_glosada": cantidad_glosada(g.cant_reclamada, g.cant_aprobada),
        "valor_glosado": g.valor_glosado,
        "clasificacion": g.clasificacion,
        "centro_costos": g.centro_costos,
        "centro_costos_por": g.centro_costos_por,
        "requiere_asignacion": bool(g.requiere_asignacion),
        "area_sugerida": g.area_sugerida,
        "motivo_area": g.motivo_area,
        "areas_posibles": list(CAUSALES_DE_DOS_AREAS.get(g.causal_codigo or "", ())),
        "area_asignada_por": g.area_asignada_por,
        "gestor": g.gestor,
        "medico": g.medico,
        "sugerencia": g.sugerencia,
        "confianza": g.confianza,
        "motivo": g.motivo,
        "estado_detallado": g.estado_detallado,
        "glosa_total": bool(g.glosa_total),
        "cuenta_valor": bool(g.cuenta_valor),
        "decision": g.decision,
        "observacion_tecnico": g.observacion_tecnico,
        "cantidad_aceptada": g.cantidad_aceptada,
        "valor_aceptado": g.valor_aceptado,
        "decidido_por": g.decidido_por,
        "decidido_en": g.decidido_en.isoformat() if g.decidido_en else None,
        "respuesta": _fila_macro(g).rta_glosa_completa,
    }


def _item_dict(i: ItemDetalladoAdresRecord) -> dict:
    return {
        "id": i.id,
        "grupo": i.grupo,
        "codigo": i.codigo,
        "nombre": i.nombre,
        "cantidad": i.cantidad,
        "valor_facturado": i.valor_facturado,
        "valor_glosado": i.valor_glosado,
        "accion": i.accion,
        "cantidad_nueva": i.cantidad_nueva,
        "valor_nuevo": i.valor_nuevo,
        "cruce_por": i.cruce_por,
        "tipo_renglon": i.tipo_renglon,
        "causales": i.causales,
        "observacion": i.observacion,
    }


def _agrupar(glosas: list[GlosaAdresRecord]) -> list[dict]:
    grupos: dict[str, dict] = {}
    for g in glosas:
        clave = g.clasificacion or "SIN CLASIFICAR"
        d = grupos.setdefault(
            clave, {"clasificacion": clave, "glosas": 0, "valor": 0.0, "pendientes": 0}
        )
        d["glosas"] += 1
        d["valor"] += g.valor_glosado or 0
        if not g.decision:
            d["pendientes"] += 1
    return sorted(grupos.values(), key=lambda d: -d["valor"])


def _fila_macro(g: GlosaAdresRecord) -> FilaMacro:
    """Convierte la fila de la base al modelo que arma el texto de respuesta."""
    return FilaMacro(
        factura=g.factura,
        descripcion=g.descripcion or "",
        descripcion_glosa=g.causal_texto or "",
        valor_glosado=g.valor_glosado or 0,
        codigo_numerico=g.causal_codigo or "",
        observacion=g.decision or "",
        observacion_tecnico=g.observacion_tecnico or "",
        cantidad_aceptada=g.cantidad_aceptada or "",
        valor_aceptado=g.valor_aceptado or 0,
    )


def texto_respuesta_factura(db: Session, numero: str, *, paquete_id: int | None = None) -> str:
    """El texto de respuesta consolidado, igual que el que arma la macro."""
    clave = normalizar_factura(numero)
    q = db.query(GlosaAdresRecord).filter(GlosaAdresRecord.factura_clave == clave)
    if paquete_id:
        q = q.filter(GlosaAdresRecord.paquete_id == paquete_id)
    glosas = q.order_by(GlosaAdresRecord.id).all()
    return armar_texto_respuesta([_fila_macro(g) for g in glosas])


# ─── Decidir ─────────────────────────────────────────────────────────────────


def guardar_decision(
    db: Session,
    glosa_id: int,
    *,
    decision: str | None,
    observacion_tecnico: str | None = None,
    cantidad_aceptada: str | None = None,
    valor_aceptado: float | None = None,
    centro_costos: str | None = None,
    medico: str | None = None,
    usuario: str = "",
) -> GlosaAdresRecord:
    """Guarda lo que el gestor decidió para una glosa."""
    glosa = db.get(GlosaAdresRecord, glosa_id)
    if glosa is None:
        raise LookupError(f"No existe la glosa {glosa_id}")
    if decision is not None:
        limpia = decision.strip().upper()
        if limpia and limpia not in DECISIONES:
            raise ValueError(f"Decisión no válida: {decision!r}. Use una de {DECISIONES}.")
        glosa.decision = limpia or None
        glosa.decidido_por = usuario
        glosa.decidido_en = datetime.now(UTC)
    if observacion_tecnico is not None:
        glosa.observacion_tecnico = observacion_tecnico
    if cantidad_aceptada is not None:
        glosa.cantidad_aceptada = cantidad_aceptada
    if valor_aceptado is not None:
        glosa.valor_aceptado = valor_aceptado
    if centro_costos is not None:
        glosa.centro_costos = centro_oficial(centro_costos, catalogo_centros(db, glosa.paquete_id))
        glosa.centro_costos_por = usuario
    if medico is not None:
        glosa.medico = medico
    # Apenas alguien toca una glosa, la factura deja de estar pendiente. Una
    # factura ya cerrada NO se reabre sola: eso lo decide el gestor.
    _marcar_en_proceso(db, glosa)
    db.commit()
    db.refresh(glosa)
    return glosa


def _marcar_en_proceso(db: Session, glosa: GlosaAdresRecord) -> None:
    ficha = (
        db.query(FacturaAdresRecord)
        .filter(FacturaAdresRecord.paquete_id == glosa.paquete_id)
        .filter(FacturaAdresRecord.factura_clave == glosa.factura_clave)
        .first()
    )
    if ficha is not None and ficha.estado == "PENDIENTE":
        ficha.estado = "EN PROCESO"


# ─── La lista de facturas a auditar ──────────────────────────────────────────


def listar_facturas(
    db: Session,
    *,
    paquete_id: int | None = None,
    estado: str | None = None,
    gestor: str | None = None,
    buscar: str = "",
    limite: int = 400,
) -> list[dict]:
    """Las facturas del paquete con su avance, para la lista de trabajo.

    Es lo primero que ve el gestor al entrar: qué facturas hay, cuántas glosas
    tiene cada una, cuánto le falta y cuáles ya cerró.
    """
    q = db.query(FacturaAdresRecord)
    if paquete_id:
        q = q.filter(FacturaAdresRecord.paquete_id == paquete_id)
    else:
        ultimo = db.query(PaqueteAdresRecord).order_by(PaqueteAdresRecord.id.desc()).first()
        if ultimo is None:
            return []
        q = q.filter(FacturaAdresRecord.paquete_id == ultimo.id)
        paquete_id = ultimo.id
    if estado:
        q = q.filter(FacturaAdresRecord.estado == estado.strip().upper())
    if gestor:
        q = q.filter(FacturaAdresRecord.gestor == gestor)
    texto = (buscar or "").strip()
    if texto:
        q = q.filter(FacturaAdresRecord.factura.ilike(f"%{texto}%"))
    fichas = q.order_by(FacturaAdresRecord.factura).limit(limite).all()
    if not fichas:
        return []

    # Un solo recorrido por las glosas del paquete: la pantalla pide 324
    # facturas de una vez y no puede hacer 324 consultas.
    avance: dict[str, dict] = {}
    filas = (
        db.query(
            GlosaAdresRecord.factura_clave,
            GlosaAdresRecord.glosa_total,
            GlosaAdresRecord.decision,
            GlosaAdresRecord.valor_glosado,
            GlosaAdresRecord.valor_aceptado,
            GlosaAdresRecord.requiere_asignacion,
            GlosaAdresRecord.cuenta_valor,
            GlosaAdresRecord.codigo,
        )
        .filter(GlosaAdresRecord.paquete_id == paquete_id)
        .all()
    )
    # Los renglones aceptados se guardan agrupados por ítem para consolidarlos
    # después: el mismo servicio sale una vez por causal y su plata es una sola.
    aceptados_por_item: dict[str, list] = {}
    for clave, total, decision, glosado, aceptado, por_asignar, cuenta, codigo in filas:
        a = avance.setdefault(
            clave,
            {
                "glosas": 0,
                "decididas": 0,
                "valor_glosado": 0.0,
                "valor_aceptado": 0.0,
                "por_asignar": 0,
                "ocultas": 0,
            },
        )
        # La plata es TODA la que el ADRES glosó en la factura, incluidas las
        # glosas totales: es la cifra que hay que defender y la que se compara
        # con la oficial. Lo que cambia con las totales es que no se responden
        # renglón por renglón, así que no cuentan como glosas a trabajar.
        if cuenta:  # el mismo ítem con varias causales cuenta una sola vez
            a["valor_glosado"] += glosado or 0
        if total:
            a["ocultas"] += 1
            continue
        a["glosas"] += 1
        aceptados_por_item.setdefault(clave, []).append(
            (_clave_item(clave, codigo, glosado), glosado or 0, aceptado or 0, bool(cuenta))
        )
        if decision:
            a["decididas"] += 1
        if por_asignar:
            a["por_asignar"] += 1

    for clave, renglones in aceptados_por_item.items():
        avance[clave]["valor_aceptado"] = aceptado_sin_duplicar(renglones)

    salida = []
    for f in fichas:
        a = avance.get(f.factura_clave, {})
        glosas = a.get("glosas", 0)
        decididas = a.get("decididas", 0)
        salida.append(
            {
                "factura": f.factura,
                "factura_clave": f.factura_clave,
                "radicacion": f.radicacion,
                "documento_paciente": f.doc_victima,
                "gestor": f.gestor,
                "medico": f.medico,
                "estado": f.estado,
                "cerrada_por": f.cerrada_por,
                "cerrada_en": f.cerrada_en.isoformat() if f.cerrada_en else None,
                "glosas": glosas,
                "decididas": decididas,
                "pendientes": glosas - decididas,
                "por_asignar": a.get("por_asignar", 0),
                "glosas_totales_ocultas": a.get("ocultas", 0),
                "valor_glosado": a.get("valor_glosado", 0.0),
                "valor_glosado_oficial": f.valor_glosado_oficial,
                "cuadra": (
                    None
                    if f.valor_glosado_oficial is None
                    else abs(a.get("valor_glosado", 0.0) - f.valor_glosado_oficial) < 1
                ),
                "valor_aceptado": a.get("valor_aceptado", 0.0),
                "avance": round(decididas / glosas * 100) if glosas else 100,
            }
        )
    return salida


ESTADOS_FACTURA = ("PENDIENTE", "EN PROCESO", "CERRADA")


def cambiar_estado_factura(
    db: Session,
    factura: str,
    *,
    estado: str,
    paquete_id: int | None = None,
    usuario: str = "",
    nota: str | None = None,
) -> dict:
    """Cierra una factura cuando el gestor termina, o la vuelve a abrir.

    Cerrar **no bloquea nada**: es una marca para saber qué falta. Reabrir deja
    constancia de quién lo hizo, porque encima ya se generó la evidencia.
    """
    limpia = (estado or "").strip().upper()
    if limpia not in ESTADOS_FACTURA:
        raise ValueError(f"Estado no válido: {estado!r}. Use uno de {list(ESTADOS_FACTURA)}.")
    clave = normalizar_factura(factura)
    q = db.query(FacturaAdresRecord).filter(FacturaAdresRecord.factura_clave == clave)
    if paquete_id:
        q = q.filter(FacturaAdresRecord.paquete_id == paquete_id)
    ficha = q.order_by(FacturaAdresRecord.id.desc()).first()
    if ficha is None:
        raise LookupError(f"La factura {factura} no está en ningún paquete cargado.")

    ahora = datetime.now(UTC)
    if limpia == "CERRADA":
        ficha.cerrada_por = usuario
        ficha.cerrada_en = ahora
    elif ficha.estado == "CERRADA":  # la estaban reabriendo
        ficha.reabierta_por = usuario
        ficha.reabierta_en = ahora
    ficha.estado = limpia
    if nota is not None:
        ficha.nota = nota
    db.commit()
    db.refresh(ficha)
    return {
        "factura": ficha.factura,
        "estado": ficha.estado,
        "cerrada_por": ficha.cerrada_por,
        "cerrada_en": ficha.cerrada_en.isoformat() if ficha.cerrada_en else None,
        "reabierta_por": ficha.reabierta_por,
        "reabierta_en": ficha.reabierta_en.isoformat() if ficha.reabierta_en else None,
        "nota": ficha.nota,
    }


# ─── Reparto de las causales que trabajan dos áreas (la 4506) ────────────────


def catalogo_centros(db: Session, paquete_id: int | None = None) -> list[str]:
    """El catálogo oficial de centros de costos, para el desplegable."""
    if paquete_id:
        paquete = db.get(PaqueteAdresRecord, paquete_id)
        if paquete and paquete.catalogo_centros:
            try:
                guardado = json.loads(paquete.catalogo_centros)
                if guardado:
                    return list(guardado)
            except (TypeError, ValueError):
                logger.warning("Catálogo de centros ilegible en el paquete %s", paquete_id)
    return list(CATALOGO_CENTROS_COSTOS)


def pendientes_de_asignar(
    db: Session, *, paquete_id: int | None = None, limite: int = 500
) -> list[dict]:
    """Las glosas que esperan a que un super admin les reparta el área."""
    q = db.query(GlosaAdresRecord).filter(GlosaAdresRecord.requiere_asignacion.is_(True))
    if paquete_id:
        q = q.filter(GlosaAdresRecord.paquete_id == paquete_id)
    return [glosa_dict(g) for g in q.order_by(GlosaAdresRecord.id).limit(limite).all()]


def asignar_area(
    db: Session,
    glosa_id: int,
    *,
    area: str,
    usuario: str = "",
    centro_costos: str | None = None,
    medico: str | None = None,
) -> GlosaAdresRecord:
    """Un SUPER ADMIN decide qué área trabaja esta glosa.

    Hoy aplica a la causal 4506: la misma causal la ven los gestores por
    FACTURACION y las médicas por PERTINENCIA, y quién la toma depende del
    procedimiento y de lo que se glosó.
    """
    glosa = db.get(GlosaAdresRecord, glosa_id)
    if glosa is None:
        raise LookupError(f"No existe la glosa {glosa_id}")
    opciones = CAUSALES_DE_DOS_AREAS.get(glosa.causal_codigo or "")
    if not opciones:
        raise ValueError(
            f"La causal {glosa.causal_codigo or '(sin causal)'} no se reparte entre áreas."
        )
    limpia = (area or "").strip().upper()
    if limpia not in opciones:
        raise ValueError(f"Área no válida: {area!r}. Use una de {list(opciones)}.")
    glosa.clasificacion = limpia
    glosa.requiere_asignacion = False
    glosa.area_asignada_por = usuario
    glosa.area_asignada_en = datetime.now(UTC)
    # Al cambiar de área cambia lo que se propone: se recalcula la sugerencia.
    glosa.sugerencia, glosa.confianza, glosa.motivo = sugerir(limpia, glosa.causal_codigo or "")
    if centro_costos is not None:
        glosa.centro_costos = centro_oficial(centro_costos, catalogo_centros(db, glosa.paquete_id))
        glosa.centro_costos_por = usuario
    if medico is not None:
        glosa.medico = medico
    db.commit()
    db.refresh(glosa)
    return glosa


def aplicar_sugerencias(
    db: Session,
    *,
    paquete_id: int,
    factura: str | None = None,
    usuario: str = "",
    solo_confianza: str | None = None,
) -> int:
    """Copia las sugerencias del bot a la decisión, sin pisar lo ya decidido."""
    q = db.query(GlosaAdresRecord).filter(GlosaAdresRecord.paquete_id == paquete_id)
    if factura:
        q = q.filter(GlosaAdresRecord.factura_clave == normalizar_factura(factura))
    q = q.filter(GlosaAdresRecord.decision.is_(None))
    q = q.filter(GlosaAdresRecord.sugerencia.isnot(None), GlosaAdresRecord.sugerencia != "")
    if solo_confianza:
        q = q.filter(GlosaAdresRecord.confianza == solo_confianza)
    n = 0
    ahora = datetime.now(UTC)
    for glosa in q.all():
        glosa.decision = glosa.sugerencia
        # Aceptar es reconocer plata: hay que decir CUÁNTA. Este camino solo
        # copiaba la decisión y dejaba el valor en cero, así que la carta al
        # ADRES salía «GLOSA ACEPTADA PARCIAL POR VALOR DE $0» mientras el
        # cuerpo enumeraba las glosas aceptadas por su valor completo. Se llena
        # igual que cuando el gestor acepta de a una desde la pantalla: todo lo
        # glosado del renglón, y la cantidad glosada (no la reclamada).
        if glosa.decision == "SE ACEPTA" and not (glosa.valor_aceptado or 0):
            glosa.valor_aceptado = glosa.valor_glosado or 0
            if not (glosa.cantidad_aceptada or "").strip():
                cant = cantidad_glosada(glosa.cant_reclamada, glosa.cant_aprobada)
                if cant <= 0:  # glosa de tarifa: la cantidad en discusión es la reclamada
                    cant = glosa.cant_reclamada or 0
                glosa.cantidad_aceptada = _cantidad_texto(cant or 1)
        glosa.decidido_por = usuario
        glosa.decidido_en = ahora
        n += 1
    db.commit()
    return n
