"""Centro Documental: todos los documentos de un expediente, organizados solos.

EL PROBLEMA. Los documentos de una glosa viven regados: los soportes de la
factura en el share del hospital, el dictamen y sus versiones en el
sistema, el PDF radicable en un botón, las actas de conciliación en otra
pantalla y el paquete de evidencia legal en un endpoint que casi nadie
recuerda. Encontrar «todo lo de esta factura» era una búsqueda manual.

Acá el expediente arma su carpeta solo: cada documento con su tipo, de
dónde sale, y CÓMO obtenerlo — un enlace del sistema cuando se descarga
desde acá, o la ruta del share cuando vive en el disco del hospital (esos
no se sirven por la web: son historia clínica, y se abren desde el equipo
del hospital como siempre).

Sin tablas nuevas: el catálogo se arma leyendo lo que ya existe. Agregar
una fuente documental nueva es agregar una función acá.
"""

from __future__ import annotations

from typing import Any

from app.core.logging_utils import logger


def _doc(
    tipo: str,
    nombre: str,
    origen: str,
    url: str | None = None,
    ruta: str | None = None,
    fecha: str | None = None,
    nota: str | None = None,
) -> dict[str, Any]:
    return {
        "tipo": tipo,
        "nombre": nombre,
        "origen": origen,  # sistema | share
        "url": url,  # descargable desde la aplicación
        "ruta": ruta,  # vive en el share del hospital
        "fecha": fecha,
        "nota": nota,
    }


def documentos_de(glosa, db) -> dict[str, Any]:
    """La carpeta del expediente: agrupada, con enlaces o rutas reales."""
    from app.models.db import DictamenVersionRecord

    gid = glosa.id
    grupos: list[dict[str, Any]] = []

    # ── 1. La respuesta del hospital ──
    docs: list[dict] = []
    if glosa.dictamen:
        docs.append(
            _doc(
                "RESPUESTA RADICABLE",
                f"dictamen-glosa-{gid}.pdf",
                "sistema",
                url=f"/glosas/{gid}/dictamen.pdf",
                nota="El PDF formal que se radica ante la entidad.",
            )
        )
        docs.append(
            _doc(
                "DICTAMEN EN TEXTO",
                f"dictamen-glosa-{gid}.md",
                "sistema",
                url=f"/glosas/{gid}/dictamen.md",
                nota="Para pegar en portales que piden texto.",
            )
        )
    try:
        versiones = (
            db.query(DictamenVersionRecord).filter(DictamenVersionRecord.glosa_id == gid).count()
        )
    except Exception:
        versiones = 0
    if versiones:
        docs.append(
            _doc(
                "HISTORIAL DE VERSIONES",
                f"{versiones} versión(es) del dictamen",
                "sistema",
                nota="Cada refinamiento quedó guardado; se consultan en la glosa.",
            )
        )
    if docs:
        grupos.append({"nombre": "Respuesta del hospital", "documentos": docs})

    # ── 2. Actas de conciliación ──
    try:
        from app.repositories.conciliacion_repository import ConciliacionRepository

        actas = []
        for c in ConciliacionRepository(db).listar_por_glosa(gid):
            actas.append(
                _doc(
                    "ACTA DE CONCILIACIÓN",
                    f"Acta {c.acta_numero or ('conciliación #' + str(c.id))}",
                    "sistema",
                    url=f"/conciliaciones/{c.id}/pdf",
                    fecha=c.fecha_audiencia.isoformat() if c.fecha_audiencia else None,
                    nota=(c.resultado or "sin resultado registrado"),
                )
            )
        if actas:
            grupos.append({"nombre": "Conciliación", "documentos": actas})
    except Exception:
        logger.warning("[DOCUMENTAL] actas no disponibles", exc_info=True)

    # ── 3. Evidencia legal ──
    grupos.append(
        {
            "nombre": "Evidencia legal",
            "documentos": [
                _doc(
                    "PAQUETE DE EVIDENCIA",
                    f"paquete-evidencia-glosa-{gid}.json",
                    "sistema",
                    url=f"/glosas/{gid}/paquete-evidencia.json",
                    nota=(
                        "Dictamen con su huella digital, versiones, auditoría y "
                        "línea de tiempo: lo que se entrega a jurídica o a la "
                        "contraparte en una disputa."
                    ),
                )
            ],
        }
    )

    # ── 4. Soportes de la factura (share del hospital) ──
    try:
        if glosa.factura:
            from app.services.soportes_autodiscovery_service import get_indexer

            soportes = []
            for s in (get_indexer().lookup(glosa.factura, auto_rebuild=False) or [])[:40]:
                soportes.append(
                    _doc(
                        s.get("tipo_codigo") or "SOPORTE",
                        s.get("nombre_archivo") or "",
                        "share",
                        ruta=s.get("ruta"),
                        nota="Vive en el share del hospital: se abre desde el equipo del HUS.",
                    )
                )
            if soportes:
                grupos.append(
                    {
                        "nombre": f"Soportes de la factura {glosa.factura}",
                        "documentos": soportes,
                    }
                )
    except Exception:
        logger.warning("[DOCUMENTAL] indexer de soportes no disponible", exc_info=True)

    total = sum(len(g["documentos"]) for g in grupos)
    return {
        "glosa_id": gid,
        "factura": glosa.factura,
        "total_documentos": total,
        "grupos": grupos,
    }
