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
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.models.db import GlosaAdresRecord, ItemDetalladoAdresRecord, PaqueteAdresRecord

# Los scripts de tools/ son la fuente única de las reglas: se importan por ruta
# para no tener dos copias del criterio.
_TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from ajustar_detallado_glosas import normalizar_factura  # noqa: E402
from preauditar_glosas_adres import (  # noqa: E402
    DECISIONES,
    TEXTO_EXTEMPORANEA,
    FilaMacro,
    aprender_decisiones,
    armar_texto_respuesta,
    centro_de_costos,
    clasificar,
    codigo_numerico,
    leer_macro,
    leer_reporte,
    preauditar,
    sugerir,
    trabajo_ya_hecho,
)

__all__ = [
    "DECISIONES",
    "TEXTO_EXTEMPORANEA",
    "aprender_decisiones",
    "armar_texto_respuesta",
    "centro_de_costos",
    "clasificar",
    "codigo_numerico",
    "consultar_factura",
    "glosa_dict",
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
    reemplazar: bool = True,
) -> PaqueteAdresRecord:
    """Carga el `ReporteGlosasReclamPAQUETE` y lo deja pre-auditado en la base.

    Si ya había un cargue del mismo paquete, `reemplazar` borra el anterior
    para no duplicar filas — pero **conserva las decisiones ya tomadas**, que
    se vuelven a aplicar sobre las filas nuevas.

    `macro` es el Excel con el que el equipo venía trabajando: de ahí salen el
    reparto gestor/médico, la clasificación afinada y lo que ya habían escrito.
    """
    filas = _leer_temporal(contenido, ".xlsx", lambda p: leer_reporte(p, paquete=paquete))
    if not filas:
        raise ValueError("El reporte no trajo ninguna fila glosada.")

    numero = paquete or (filas[0].paquete or "").strip()

    # Lo que el equipo ya decidió: primero lo que hay en la base, y si mandan el
    # Excel de la macro, también lo que venían llevando ahí.
    decididas = _decisiones_previas(db, numero)
    aprendidas = _aprender_de_la_base(decididas)
    tabla_clasificacion = None
    reparto: dict[str, tuple[str, str]] = {}
    hecho: dict[tuple, list[dict]] = {}
    if macro:
        aprendida_clasif, reparto, _centros, filas_macro = _leer_temporal(
            macro, ".xlsm", leer_macro
        )
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

    if reemplazar:
        _borrar_paquete(db, numero)

    registro = PaqueteAdresRecord(
        numero_paquete=numero,
        archivo=nombre_archivo,
        importado_por=importado_por,
        total_filas=len(resumen.filas),
        total_facturas=resumen.facturas,
        valor_glosado=sum(f.valor_glosado for f in resumen.filas),
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
            centro_costos=f.centro_costos,
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
            rescatadas += 1
        db.add(fila)

    db.commit()
    logger.info(
        "Paquete ADRES %s importado: %d filas, %d facturas, %d decisión(es) conservada(s)",
        numero,
        len(resumen.filas),
        resumen.facturas,
        rescatadas,
    )
    return registro


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
    filas = (
        db.query(GlosaAdresRecord)
        .filter(GlosaAdresRecord.paquete_id.in_(ids))
        .filter(GlosaAdresRecord.decision.isnot(None))
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
        try:
            return float(str(v).replace(",", ".")) if str(v).strip() else 0.0
        except ValueError:
            return 0.0

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


def consultar_factura(db: Session, numero: str, *, paquete_id: int | None = None) -> dict:
    """Todo lo que el sistema sabe de esa factura, listo para la pantalla."""
    clave = normalizar_factura(numero)
    q = db.query(GlosaAdresRecord).filter(GlosaAdresRecord.factura_clave == clave)
    if paquete_id:
        q = q.filter(GlosaAdresRecord.paquete_id == paquete_id)
    glosas = q.order_by(GlosaAdresRecord.id).all()
    if not glosas:
        return {"encontrada": False, "factura": numero, "glosas": [], "items": []}

    q2 = db.query(ItemDetalladoAdresRecord).filter(ItemDetalladoAdresRecord.factura_clave == clave)
    if paquete_id:
        q2 = q2.filter(ItemDetalladoAdresRecord.paquete_id == paquete_id)
    items = q2.order_by(ItemDetalladoAdresRecord.id).all()

    primera = glosas[0]
    paquete = db.get(PaqueteAdresRecord, primera.paquete_id)
    decididas = [g for g in glosas if g.decision]
    sigue_glosado = sum(i.valor_nuevo for i in items if i.accion in ("CONSERVADO", "AJUSTADO"))

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
            "valor_glosado": sum(g.valor_glosado for g in glosas),
            "valor_aceptado": sum(g.valor_aceptado or 0 for g in glosas),
            "valor_reclamado": sum(g.valor_reclamado for g in glosas),
            "items_detallado": len(items),
            "sigue_glosado_detallado": sigue_glosado,
        },
        "glosas": [glosa_dict(g) for g in glosas],
        "items": [_item_dict(i) for i in items],
        "por_clasificacion": _agrupar(glosas),
    }


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
        "valor_aprobado": g.valor_aprobado,
        "valor_glosado": g.valor_glosado,
        "clasificacion": g.clasificacion,
        "centro_costos": g.centro_costos,
        "gestor": g.gestor,
        "medico": g.medico,
        "sugerencia": g.sugerencia,
        "confianza": g.confianza,
        "motivo": g.motivo,
        "estado_detallado": g.estado_detallado,
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
        glosa.centro_costos = centro_costos
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
        glosa.decidido_por = usuario
        glosa.decidido_en = ahora
        n += 1
    db.commit()
    return n
