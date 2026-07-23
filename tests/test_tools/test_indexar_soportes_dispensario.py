"""Tests del indexador de soportes del Dispensario
(tools/indexar_soportes_dispensario.py) y del consumo del indice por el
asistente (docs_desde_indice).

Cubre: extraccion de facturas del nombre/ruta, metadatos livianos del RIPS,
construccion del indice sobre una carpeta que imita la estructura real,
actualizacion incremental (reusa lo ya indexado), busqueda por factura, y el
flujo del asistente leyendo SOLO los documentos del indice (sin recorrer Y:\\).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import asistente_conciliacion_dispensario as asis  # noqa: E402
import indexar_soportes_dispensario as idxr  # noqa: E402


def _rips(fac, doc):
    return {
        "numDocumentoIdObligado": "900006037",
        "numFactura": f"HUS{fac}",
        "usuarios": [{"numDocumentoIdentificacion": doc, "servicios": {}}],
    }


def _carpeta(base: Path):
    d = base / "DISPENSARIO" / "LILIANA" / "ENV-229912-OKDGH" / "HUS436483"
    d.mkdir(parents=True)
    (d / "RIPS_900006037_HUS436483.json").write_text(
        json.dumps(_rips("436483", "1029407046")), encoding="utf-8"
    )
    (d / "XML_900006037_HUS436483.xml").write_text("<Invoice/>", encoding="utf-8")
    (d / "HEV_900006037_HUS436483.pdf").write_text("hc", encoding="utf-8")
    return base


def test_facturas_en_nombre_y_ruta():
    assert idxr.facturas_en("RIPS_900006037_HUS436483.json", "x") == {"436483"}
    assert idxr.facturas_en("otro.pdf", "Y:\\...\\HUS0000436483") == {"436483"}
    assert idxr.facturas_en("sinfactura.pdf", "Y:\\x") == set()


def test_meta_liviana_rips(tmp_path):
    p = tmp_path / "RIPS_900006037_HUS436483.json"
    p.write_text(json.dumps(_rips("436483", "1029407046")), encoding="utf-8")
    meta = idxr.meta_liviana(p)
    assert meta["num_factura"] == "HUS436483"
    assert meta["paciente"] == "1029407046"
    # Un XML no da metadatos
    x = tmp_path / "x.xml"
    x.write_text("<a/>", encoding="utf-8")
    assert idxr.meta_liviana(x) == {}


def test_construir_indice_y_resumen(tmp_path):
    _carpeta(tmp_path)
    docs = idxr.construir_indice([tmp_path], previos={}, con_meta=True)
    assert len(docs) == 3
    r = idxr.resumen(docs)
    assert r["facturas"] == 1
    assert r["por_tipo"]["RIPS"] == 1
    rips = next(d for d in docs if d["tipo"] == "RIPS")
    assert rips["paciente"] == "1029407046"
    assert rips["factura"] == "436483"


def test_incremental_reusa(tmp_path):
    _carpeta(tmp_path)
    docs1 = idxr.construir_indice([tmp_path], previos={}, con_meta=False)
    previos = {d["ruta"]: d for d in docs1}
    # Sin cambios: todo se reusa (registros identicos por objeto)
    docs2 = idxr.construir_indice([tmp_path], previos=previos, con_meta=False)
    assert len(docs2) == len(docs1)
    assert all(d in docs1 for d in docs2)


def test_guardar_cargar_y_buscar(tmp_path):
    _carpeta(tmp_path)
    salida = tmp_path / "indice.json"
    docs = idxr.construir_indice([tmp_path], previos={}, con_meta=True)
    idxr.guardar_indice(docs, [tmp_path], salida)
    indice = idxr.cargar_indice(salida)
    assert indice["documentos"]
    hits = idxr.buscar(indice, "HUS436483")
    assert len(hits) == 3
    hits_pac = idxr.buscar(indice, "1029407046")
    assert len(hits_pac) >= 1  # el RIPS trae el paciente


def test_asistente_docs_desde_indice(tmp_path):
    _carpeta(tmp_path)
    salida = tmp_path / "indice.json"
    docs = idxr.construir_indice([tmp_path], previos={}, con_meta=True)
    idxr.guardar_indice(docs, [tmp_path], salida)

    idx = asis.docs_desde_indice(salida, {"436483"}, ocr=False)
    assert len(idx["436483"]) == 3
    tipos = {d.tipo for d in idx["436483"]}
    assert "RIPS" in tipos and "Historia clinica / Evolucion" in tipos
