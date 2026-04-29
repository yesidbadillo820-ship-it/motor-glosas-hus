"""Tests para app.services.soportes_autodiscovery_service."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.soportes_autodiscovery_service import (
    SoportesIndexer,
    normalizar_factura,
    _clasificar_archivo,
)


class TestNormalizarFactura:
    def test_hus_con_ceros(self):
        assert normalizar_factura("HUS0000495050") == "495050"

    def test_hus_sin_ceros(self):
        assert normalizar_factura("HUS487523") == "487523"

    def test_solo_numeros(self):
        assert normalizar_factura("0000495050") == "495050"

    def test_minusculas(self):
        assert normalizar_factura("hus487523") == "487523"

    def test_vacio(self):
        assert normalizar_factura("") == ""
        assert normalizar_factura(None) == ""  # type: ignore[arg-type]

    def test_sin_numeros(self):
        assert normalizar_factura("HUS") == ""

    def test_solo_ceros(self):
        # No debe colapsar a vacío — preservar al menos un "0"
        assert normalizar_factura("HUS0000") == "0"


class TestClasificarArchivo:
    def test_fev(self):
        assert _clasificar_archivo("FEV_900006037_HUS487523.pdf")[0] == "FEV"

    def test_hev(self):
        assert _clasificar_archivo("HEV_900006037_HUS487523.pdf")[0] == "HEV"

    def test_rips_no_confunde_con_furips(self):
        # FURIPS empieza con FU — no debe matchear RIPS
        assert _clasificar_archivo("FURIPS168001007.txt")[0] == "FURIPS"
        assert _clasificar_archivo("Rips_HUS487523.json")[0] == "RIPS"

    def test_xml_cufe(self):
        assert _clasificar_archivo("ad09000060370002600484921.xml")[0] == "AD"

    def test_resultados_msps(self):
        assert (
            _clasificar_archivo("ResultadosMSPS_HUS487523_ID39685.json")[0]
            == "RESULTADOSMSPS"
        )

    def test_archivo_no_clasificado(self):
        assert _clasificar_archivo("notas_random.pdf") is None


class TestSoportesIndexer:
    def _construir_arbol(self, raiz: Path):
        """Crea un mini-share fake con la estructura real."""
        env1 = (
            raiz / "ABRIL 2026 - SOPORTES RADICACION" / "1. DD FACTURACION"
            / "ESCANEO" / "ASEGURADORA SOLIDARIA" / "ENV-225060-OK"
        )
        env1.mkdir(parents=True)
        for f in [
            "FEV_900006037_HUS487523.pdf",
            "HEV_900006037_HUS487523.pdf",
            "CRC_900006037_HUS487523.PDF",
            "Rips_HUS487523.json",
            "FURIPS168001007920121012026.txt",
            "ad09000060370002600484921.xml",
            "leeme.txt",  # debe ignorarse: sin factura
        ]:
            (env1 / f).write_text("dummy")

        env2 = (
            raiz / "FEBRERO 2026 - SOPORTES RADICACION CARPETA 2" / "1. DD FACTURACION"
            / "ESCANEO" / "FAMISANAR" / "ENV-200001"
        )
        env2.mkdir(parents=True)
        (env2 / "FEV_900006037_HUS0000495050.pdf").write_text("x")
        (env2 / "HEV_900006037_HUS0000495050.pdf").write_text("x")

    def test_indexa_y_encuentra_factura_corta(self, tmp_path: Path):
        self._construir_arbol(tmp_path)
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        soportes = idx.lookup("HUS487523")
        assert len(soportes) == 6  # 7 archivos - 1 sin factura
        tipos = {s["tipo_codigo"] for s in soportes}
        assert {"FEV", "HEV", "CRC", "RIPS", "FURIPS", "AD"} <= tipos

    def test_factura_normalizacion_cruza_formatos(self, tmp_path: Path):
        self._construir_arbol(tmp_path)
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        # `HUS495050` en query debe matchear archivos con `HUS0000495050`
        a = idx.lookup("HUS495050")
        b = idx.lookup("HUS0000495050")
        c = idx.lookup("495050")
        assert len(a) == len(b) == len(c) == 2

    def test_metadata_eps_y_env(self, tmp_path: Path):
        self._construir_arbol(tmp_path)
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        soportes = idx.lookup("HUS487523")
        assert all(s["eps"] == "ASEGURADORA SOLIDARIA" for s in soportes)
        assert all(s["env"] == "ENV-225060-OK" for s in soportes)
        assert all(s["mes"] == "ABRIL" and s["anio"] == 2026 for s in soportes)

    def test_orden_prioriza_factura_e_historia(self, tmp_path: Path):
        self._construir_arbol(tmp_path)
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        soportes = idx.lookup("HUS487523")
        # FEV (factura electrónica) debe ir primero, HEV segundo
        assert soportes[0]["tipo_codigo"] == "FEV"
        assert soportes[1]["tipo_codigo"] == "HEV"

    def test_lookup_factura_inexistente(self, tmp_path: Path):
        self._construir_arbol(tmp_path)
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        assert idx.lookup("HUS999999") == []

    def test_raiz_inexistente_no_crashea(self, tmp_path: Path):
        idx = SoportesIndexer(raiz=str(tmp_path / "no_existe"))
        s = idx.rebuild()
        assert s["facturas_indexadas"] == 0
        assert s["ultimo_error"]
        assert idx.lookup("HUS487523") == []

    def test_stats_reportan_estado(self, tmp_path: Path):
        self._construir_arbol(tmp_path)
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        s = idx.stats()
        assert s["facturas_indexadas"] == 2  # HUS487523 y HUS0000495050
        assert s["archivos_indexados"] >= 8
        assert s["construido_en_epoch"] > 0
