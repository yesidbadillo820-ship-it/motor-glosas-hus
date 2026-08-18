"""Tests para app.services.soportes_autodiscovery_service."""

from __future__ import annotations

from pathlib import Path


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
        assert _clasificar_archivo("ResultadosMSPS_HUS487523_ID39685.json")[0] == "RESULTADOSMSPS"

    def test_archivo_no_clasificado(self):
        assert _clasificar_archivo("notas_random.pdf") is None


class TestSoportesIndexer:
    def _construir_arbol(self, raiz: Path):
        """Crea un mini-share fake con la estructura real."""
        env1 = (
            raiz
            / "ABRIL 2026 - SOPORTES RADICACION"
            / "1. DD FACTURACION"
            / "ESCANEO"
            / "ASEGURADORA SOLIDARIA"
            / "ENV-225060-OK"
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
            raiz
            / "FEBRERO 2026 - SOPORTES RADICACION CARPETA 2"
            / "1. DD FACTURACION"
            / "ESCANEO"
            / "FAMISANAR"
            / "ENV-200001"
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

    def test_raiz_inexistente_se_crea_y_no_crashea(self, tmp_path: Path):
        # Cambio de comportamiento (fix abr 2026): el indexer ahora crea
        # la raíz on-demand para que el upload-bulk del jump-box agent
        # pueda escribir desde el primer batch sin FileNotFoundError.
        ruta = tmp_path / "no_existe_aun"
        idx = SoportesIndexer(raiz=str(ruta))
        # Se crea automáticamente
        assert ruta.exists()
        # Sigue indexando sin error (raíz vacía → 0 archivos, sin error)
        s = idx.rebuild()
        assert s["facturas_indexadas"] == 0
        assert s["archivos_indexados"] == 0
        assert s["ultimo_error"] is None
        assert idx.lookup("HUS487523") == []

    def test_stats_reportan_estado(self, tmp_path: Path):
        self._construir_arbol(tmp_path)
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        s = idx.stats()
        assert s["facturas_indexadas"] == 2  # HUS487523 y HUS0000495050
        assert s["archivos_indexados"] >= 8
        assert s["construido_en_epoch"] > 0


class TestFVSSeReconoce:
    """FVS = Factura de Venta en Salud (código ADRES) — 18-08-2026.

    El servidor de radicación del HUS nombra la factura FVS_900006037_HUSxxx.pdf
    (así lo documenta la propia pantalla). Antes esos PDF se indexaban por
    número pero quedaban etiquetados «otro» en vez de la factura.
    """

    def test_fvs_es_la_factura_electronica(self):
        from app.services.soportes_autodiscovery_service import _clasificar_archivo

        for nombre in (
            "FVS_900006037_HUS0000487175.pdf",
            "FVS 900006037 HUS487175.pdf",
        ):
            tipo = _clasificar_archivo(nombre)
            assert tipo is not None
            assert tipo[0] == "FVS"
            assert tipo[1] == "factura_electronica"

    def test_no_se_confunde_con_otros(self):
        from app.services.soportes_autodiscovery_service import _clasificar_archivo

        # No es que ahora cualquier cosa con 'FV' pase: exige el delimitador.
        assert _clasificar_archivo("FVSABC.pdf") is None
        assert _clasificar_archivo("HEV_900006037_HUS487175.pdf")[0] == "HEV"


class TestEstructuraRealDeRadicacion2026:
    """Con los nombres y carpetas REALES del servidor (18-08-2026).

    Yesid mandó rutas reales de \\\\Prime\\radicacion_2026. Traían dos cosas
    que el indexador no manejaba: la carpeta del mes lleva un ordinal delante
    ("8. AGOSTO 2026 - SOPORTES RADICACION") y la factura siempre viene con el
    prefijo HUS en el nombre (FEV_900006037_HUS548170.pdf). Por el ordinal, la
    EPS, el mes y el año salían vacíos.
    """

    def _armar(self, tmp_path, eps, factura, tipo="FEV"):
        carpeta = (
            tmp_path
            / "8. AGOSTO 2026 - SOPORTES RADICACION"
            / eps
            / "SOFIA"
            / "ENV-232984-okdgh"
            / "SOPORTES"
            / f"HUS{factura}"
        )
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = carpeta / f"{tipo}_900006037_HUS{factura}.pdf"
        archivo.write_bytes(b"%PDF-1.4 test")
        return archivo

    def test_encuentra_la_factura_y_sabe_la_eps(self, tmp_path):
        from app.services.soportes_autodiscovery_service import SoportesIndexer

        self._armar(tmp_path, "NUEVA EPS", "548170", "FEV")
        self._armar(tmp_path, "SANITAS", "545510", "HEV")
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()

        r = idx.lookup("HUS0000548170")
        assert r, "no encontró la factura por su número"
        assert r[0]["eps"] == "NUEVA EPS"
        assert r[0]["tipo_codigo"] == "FEV"
        assert r[0]["factura_norm"] == "548170"

    def test_el_ordinal_del_mes_no_esconde_la_eps(self, tmp_path):
        from app.services.soportes_autodiscovery_service import SoportesIndexer

        self._armar(tmp_path, "PPL", "546938", "FEV")
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        r = idx.lookup("546938")
        assert r and r[0]["eps"] == "PPL"
        assert r[0]["mes"] and "AGOSTO" in r[0]["mes"]

    def test_el_nit_con_cero_de_mas_no_rompe_la_factura(self, tmp_path):
        """Un nombre real venía con el NIT mal escrito (9000006037): igual
        tiene que sacar bien la factura por el prefijo HUS."""
        from app.services.soportes_autodiscovery_service import SoportesIndexer

        carpeta = tmp_path / "8. AGOSTO 2026 - SOPORTES RADICACION" / "PPL" / "HUS548740"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "HEV_9000006037_HUS548740.pdf").write_bytes(b"%PDF-1.4")
        idx = SoportesIndexer(raiz=str(tmp_path))
        idx.rebuild()
        assert idx.lookup("548740")
