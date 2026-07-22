"""Tests de HOSPIAI — AG001 Servicio de Indexación Permanente.

Cubre: primera indexación con guardado inmediato, indexación INCREMENTAL
(solo lo nuevo/cambiado; lo borrado queda AUSENTE), búsqueda instantánea por
factura en la vista global (varias bases = varios servidores), el agente AG001
sobre el SDK, y el cruce del radicador leyendo del índice permanente
(--soportes-db y autodetección) en vez del txt.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_indexador as idx  # noqa: E402
import radicar_facturacion as rad  # noqa: E402
from hospiai_sdk import Mision  # noqa: E402


def _share(base: Path) -> Path:
    """Share sintético: carpeta de factura con genérico + archivo con token."""
    d = base / "NUEVA EPS" / "LILIANA" / "ENV-1" / "SOPORTES" / "HUS528043"
    d.mkdir(parents=True)
    (d / "HEV_900006037_HUS528043.pdf").write_text("x", encoding="utf-8")
    (d / "EPICRISIS.pdf").write_text("x", encoding="utf-8")
    (base / "NUEVA EPS" / "suelto_sin_factura.pdf").write_text("x", encoding="utf-8")
    return base


class TestIndexacion:
    def test_primera_pasada_guarda_todo(self, tmp_path):
        share = _share(tmp_path / "y")
        r = idx.indexar_raiz(str(share), tmp_path / "indices", progreso=lambda m: None)
        assert r["total"] == 3 and r["nuevos"] == 3 and r["ausentes"] == 0
        con = sqlite3.connect(idx.db_de(str(share), tmp_path / "indices"))
        filas = {
            f[0]: f for f in con.execute("SELECT nombre, factura, tipo, reconocido FROM archivos")
        }
        con.close()
        assert filas["HEV_900006037_HUS528043.pdf"][1] == "528043"
        assert filas["HEV_900006037_HUS528043.pdf"][2] == "HEV"
        # El genérico toma la factura de la CARPETA (mismo criterio del motor).
        assert filas["EPICRISIS.pdf"][1] == "528043" and filas["EPICRISIS.pdf"][3] == 1
        assert filas["suelto_sin_factura.pdf"][1] == ""

    def test_incremental_solo_lo_nuevo_y_marca_ausentes(self, tmp_path):
        share = _share(tmp_path / "y")
        idx.indexar_raiz(str(share), tmp_path / "indices", progreso=lambda m: None)
        # Nada cambió → 0 nuevos, 0 actualizados, rápido.
        r2 = idx.indexar_raiz(str(share), tmp_path / "indices", progreso=lambda m: None)
        assert r2["nuevos"] == 0 and r2["actualizados"] == 0 and r2["ausentes"] == 0
        # Aparece un archivo y desaparece otro → 1 nuevo, 1 ausente.
        d = share / "NUEVA EPS" / "LILIANA" / "ENV-1" / "SOPORTES" / "HUS528043"
        (d / "OPF_900006037_HUS528043.pdf").write_text("x", encoding="utf-8")
        (share / "NUEVA EPS" / "suelto_sin_factura.pdf").unlink()
        r3 = idx.indexar_raiz(str(share), tmp_path / "indices", progreso=lambda m: None)
        assert r3["nuevos"] == 1 and r3["ausentes"] == 1
        con = sqlite3.connect(idx.db_de(str(share), tmp_path / "indices"))
        estado = dict(con.execute("SELECT nombre, estado FROM archivos"))
        con.close()
        assert estado["suelto_sin_factura.pdf"] == "AUSENTE"
        assert estado["OPF_900006037_HUS528043.pdf"] == "ACTIVO"

    def test_modificacion_actualiza(self, tmp_path):
        share = _share(tmp_path / "y")
        idx.indexar_raiz(str(share), tmp_path / "indices", progreso=lambda m: None)
        f = share / "NUEVA EPS" / "LILIANA" / "ENV-1" / "SOPORTES" / "HUS528043" / "EPICRISIS.pdf"
        time.sleep(1.1)  # asegura mtime distinto (resolución de 1s del criterio)
        f.write_text("contenido nuevo más largo", encoding="utf-8")
        r = idx.indexar_raiz(str(share), tmp_path / "indices", progreso=lambda m: None)
        assert r["actualizados"] == 1 and r["nuevos"] == 0


class TestBusquedaGlobal:
    def test_busqueda_instantanea_en_varias_bases(self, tmp_path):
        # Dos "servidores" (bases separadas) → la búsqueda los une (vista global).
        share_y = _share(tmp_path / "y")
        share_z = tmp_path / "z" / "GLOSAS" / "HUS528043"
        share_z.mkdir(parents=True)
        (share_z / "FUR_HUS528043.pdf").write_text("x", encoding="utf-8")
        idx.indexar_raiz(str(share_y), tmp_path / "indices", progreso=lambda m: None)
        idx.indexar_raiz(str(tmp_path / "z"), tmp_path / "indices", progreso=lambda m: None)
        assert len(idx.bases_disponibles(tmp_path / "indices")) == 2  # separadas
        t0 = time.perf_counter()
        filas = idx.buscar("HUS528043", tmp_path / "indices")
        ms = (time.perf_counter() - t0) * 1000
        assert {f["nombre"] for f in filas} == {
            "HEV_900006037_HUS528043.pdf",
            "EPICRISIS.pdf",
            "FUR_HUS528043.pdf",
        }
        assert ms < 500  # instantánea (holgura para máquinas lentas de CI)
        assert idx.buscar("HUS999999", tmp_path / "indices") == []

    def test_estado_reporta_cada_base(self, tmp_path):
        idx.indexar_raiz(str(_share(tmp_path / "y")), tmp_path / "indices", progreso=lambda m: None)
        e = idx.estado(tmp_path / "indices")
        assert len(e) == 1 and e[0]["archivos"] == 3 and e[0]["facturas"] == 1
        assert e[0]["ultima"]["modo"] == "INCREMENTAL"


class TestAgenteAG001:
    def test_mision_buscar_archivo(self, tmp_path):
        idx.indexar_raiz(str(_share(tmp_path / "y")), tmp_path / "indices", progreso=lambda m: None)
        m = Mision(codigo="MISION-000031", tipo="BUSCAR_ARCHIVO", datos={"factura": "HUS528043"})
        res = idx.AgenteIndexador().ejecutar(m, {"dir_indices": tmp_path / "indices"})
        assert res.resultado == "OK"
        assert len(res.salida["coincidencias"]) == 2

    def test_mision_indexar(self, tmp_path):
        share = _share(tmp_path / "y")
        m = Mision(codigo="MISION-000032", tipo="INDEXAR", datos={"raiz": str(share)})
        res = idx.AgenteIndexador().ejecutar(m, {"dir_indices": tmp_path / "indices"})
        assert res.resultado == "OK" and res.salida["resumen"]["total"] == 3


class TestCruceDesdeIndicePermanente:
    def _fe(self, base: Path, fac: str) -> Path:
        import json

        d = base / "COOSALUD" / fac  # carpeta de EPS: resuelve la entidad por ruta
        d.mkdir(parents=True)
        rips = {
            "numFactura": fac,
            "usuarios": [{"servicios": {"procedimientos": [{"vrServicio": 100}]}}],
        }
        (d / f"Rips_{fac}.json").write_text(json.dumps(rips), encoding="utf-8")
        (d / f"FEV_900006037_{fac}.xml").write_text(
            f'<?xml version="1.0"?><Invoice xmlns:cbc="x"><cbc:ID>{fac}</cbc:ID></Invoice>',
            encoding="utf-8",
        )
        (d / f"CUV_900006037_{fac}.json").write_text("{}", encoding="utf-8")
        return d

    def test_radicador_cruza_desde_soportes_db(self, tmp_path):
        # El share clínico está indexado en la base; el radicador NO recorre la
        # red: cruza desde SQLite y la factura queda LISTA.
        idx.indexar_raiz(str(_share(tmp_path / "y")), tmp_path / "indices", progreso=lambda m: None)
        origen = tmp_path / "fe"
        self._fe(origen, "HUS528043")
        reporte = tmp_path / "rep.csv"
        rc = rad.main(
            [
                "--sin-db",
                "--origen", str(origen),
                "--reporte", str(reporte),
                "--soportes-db", str(idx.db_de(str(tmp_path / "y"), tmp_path / "indices")),
            ]
        )  # fmt: skip
        assert rc == 0  # sin problemas: la única factura quedó LISTA
        contenido = reporte.read_text(encoding="utf-8-sig")
        assert "LISTA" in contenido and "HEV" in contenido

    def test_soportes_db_inexistente_avisa_como_armarlo(self, tmp_path, caplog):
        origen = tmp_path / "fe"
        self._fe(origen, "HUS1")
        rc = rad.main(
            [
                "--sin-db",
                "--origen", str(origen),
                "--reporte", str(tmp_path / "r.csv"),
                "--soportes-db", str(tmp_path / "no_existe.db"),
            ]
        )  # fmt: skip
        assert rc == 1
        assert "hospiai_indexador" in caplog.text
