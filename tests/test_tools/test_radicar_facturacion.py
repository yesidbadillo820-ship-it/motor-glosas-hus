"""Tests del radicador maestro multi-entidad (tools/radicar_facturacion.py).

Cubre: tipificación de soportes (token / alias / prefijo), normalización de
factura, resolución de entidad contra el catálogo real, diagnóstico de
completitud por factura, descubrimiento de lotes (carpeta-factura y lote),
armado del paquete con renombrado ADRES + ZIP, y el CLI end-to-end.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import radicar_facturacion as rad  # noqa: E402

FEV_XML = '<?xml version="1.0"?><Invoice xmlns:cbc="x"><cbc:ID>{fac}</cbc:ID></Invoice>'


def _rips(fac: str, servicios: dict | None = None, nit: str = "900006037") -> str:
    return json.dumps(
        {
            "numFactura": fac,
            "numDocumentoIdObligado": nit,
            "usuarios": [
                {
                    "numDocumentoIdentificacion": "1098765432",
                    "servicios": servicios
                    or {"consultas": [{"codConsulta": "890201", "vrServicio": 52300}]},
                }
            ],
        }
    )


def _factura_folder(
    base: Path,
    fac: str,
    *,
    con_cuv: bool = True,
    extra: dict | None = None,
    servicios: dict | None = None,
) -> Path:
    """Crea una carpeta de factura con RIPS + FEV (+ CUV) y archivos extra."""
    d = base / fac
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Rips_{fac}.json").write_text(_rips(fac, servicios), encoding="utf-8")
    (d / f"FEV_900006037_{fac}.xml").write_text(FEV_XML.format(fac=fac), encoding="utf-8")
    if con_cuv:
        (d / f"CUV_900006037_{fac}.json").write_text("{}", encoding="utf-8")
    for nombre, contenido in (extra or {}).items():
        (d / nombre).write_text(contenido, encoding="utf-8")
    return d


def _factura_desnuda(base: Path, fac: str, *, con_fev: bool = True, con_cuv: bool = True) -> Path:
    """Carpeta de factura al estilo del share real de SINAC: el RIPS es
    <fac>.json (SIN token de tipo), más CUV_<fac>.json y, opcional, el FEV."""
    d = base / fac
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{fac}.json").write_text(_rips(fac), encoding="utf-8")  # RIPS desnudo
    if con_cuv:
        (d / f"CUV_{fac}.json").write_text("{}", encoding="utf-8")
    if con_fev:
        (d / f"FEV_900006037_{fac}.xml").write_text(FEV_XML.format(fac=fac), encoding="utf-8")
    return d


@pytest.fixture
def cfg() -> rad.ConfigRadicacion:
    """Catálogo real de perfiles (data/perfiles_radicacion.json)."""
    return rad.cargar_perfiles(None)


class TestClasificarSoporte:
    def test_token_separado(self):
        cod, _desc, ok = rad.clasificar_soporte("FEV_900006037_HUS487523.xml")
        assert (cod, ok) == ("FEV", True)

    def test_alias_rips(self):
        assert rad.clasificar_soporte("Rips_HUS487523.json")[0] == "RIP"

    def test_alias_resultadosmsps_es_cuv(self):
        assert rad.clasificar_soporte("ResultadosMSPS_HUS487523.json")[0] == "CUV"

    def test_rips_desnudo_solo_factura(self):
        # En el share real el RIPS viene como HUS469401.json (sin token RIP).
        cod, _d, ok = rad.clasificar_soporte("HUS469401.json")
        assert (cod, ok) == ("RIP", True)

    def test_rips_desnudo_numerico(self):
        assert rad.clasificar_soporte("469401.json")[0] == "RIP"

    def test_cuv_desnudo_no_se_confunde_con_rips(self):
        # CUV_HUS469401.json sigue siendo CUV (no RIPS), va junto al RIPS desnudo.
        assert rad.clasificar_soporte("CUV_HUS469401.json")[0] == "CUV"

    def test_json_no_factura_no_es_rips(self):
        # Un .json cuyo nombre NO es una factura no se confunde con RIPS.
        cod, _d, ok = rad.clasificar_soporte("config.json")
        assert (cod, ok) == ("ADM", False)

    def test_dian_fv_xml_es_fev(self):
        # Factura de venta DIAN (fv…) en XML = factura electrónica.
        assert rad.clasificar_soporte("fv09000060370002600526350.xml")[0] == "FEV"

    def test_dian_fv_pdf_es_fac(self):
        # La representación gráfica (pdf) de la fv = factura de venta PDF.
        assert rad.clasificar_soporte("fv09000060370002600526350.pdf")[0] == "FAC"

    def test_dian_ad_es_documento_adjunto(self):
        # AttachedDocument DIAN (ad…) con CUFE.
        cod, _d, ok = rad.clasificar_soporte("ad09000060370002600526350.xml")
        assert (cod, ok) == ("FED", True)

    def test_dian_ar_es_acuse(self):
        # ApplicationResponse (ar…) = acuse de la DIAN.
        assert rad.clasificar_soporte("ar09000060370002600526350.xml")[0] == "ARD"

    def test_zip_desnudo_es_paquete_fe(self):
        # HUS520769.zip = paquete FE comprimido (documento adjunto).
        assert rad.clasificar_soporte("HUS520769.zip")[0] == "FED"

    def test_resultados_doker_es_cuv(self):
        # En el share de FE el CUV viene como ResultadosDoker_<fac>_<id>.json.
        cod, _d, ok = rad.clasificar_soporte("ResultadosDoker_HUS520760_010626002250.json")
        assert (cod, ok) == ("CUV", True)

    def test_envio_doker_es_auxiliar(self):
        # El envío al validador es auxiliar (reconocido, no es soporte ADRES).
        cod, _d, ok = rad.clasificar_soporte("EnvioDoker_HUS520760_010626002250.json")
        assert (cod, ok) == ("VAL", True)

    def test_prefijo_furips_pegado(self):
        # FURIPS viene pegado a dígitos en los lotes reales.
        assert rad.clasificar_soporte("FURIPS168001007920121012026.txt")[0] == "FUR"

    def test_prefijo_no_confunde_furips_con_rip(self):
        cod, _d, ok = rad.clasificar_soporte("FURIPS123.txt")
        assert (cod, ok) == ("FUR", True)

    def test_no_reconocido(self):
        cod, _desc, ok = rad.clasificar_soporte("documento_raro.pdf")
        assert ok is False
        assert cod == "ADM"


class TestNormalizacion:
    def test_normalizar_factura_equivalentes(self):
        assert rad.normalizar_factura("HUS0000487523") == rad.normalizar_factura("487523")
        assert rad.normalizar_factura("HUS487523") == "487523"

    def test_factura_corta(self):
        assert rad.factura_corta("HUS0000409621") == "HUS409621"
        assert rad.factura_corta("487523") == "487523"


class TestResolverEntidad:
    def test_alias_exacto(self, cfg):
        ent = rad.resolver_entidad("COOSALUD EPS", cfg)
        assert ent is not None and ent.id == "COOSALUD"

    def test_codigo_eps_embebido(self, cfg):
        ent = rad.resolver_entidad("U220311 - DISPENSARIO MEDICO BUCARAMANGA", cfg)
        assert ent is not None and ent.id == "DISPENSARIO_MEDICO"

    def test_substring_gana_el_mas_especifico(self, cfg):
        ent = rad.resolver_entidad("SALUD TOTAL", cfg)
        assert ent is not None and ent.id == "SALUD_TOTAL"

    def test_desconocida(self, cfg):
        assert rad.resolver_entidad("ENTIDAD QUE NO EXISTE XYZ", cfg) is None

    def test_none(self, cfg):
        assert rad.resolver_entidad(None, cfg) is None


class TestProcesarFactura:
    def test_lista_consulta_simple(self, tmp_path, cfg):
        d = _factura_folder(tmp_path, "HUS487999")
        res = rad.procesar_factura("HUS487999", rad._archivos_de(d), d, "COOSALUD", cfg)
        assert res.estado == "LISTA"
        assert res.entidad_id == "COOSALUD"
        assert set(res.soportes_presentes) >= {"FEV", "RIP", "CUV"}
        assert res.valor_total == 52300.0

    def test_rips_desnudo_lista(self, tmp_path, cfg):
        # Caso real SINAC: el RIPS es HUS469401.json (sin token). Debe leerse
        # como RIPS y la factura quedar LISTA (no SIN_RIPS).
        d = _factura_desnuda(tmp_path, "HUS469401")
        res = rad.procesar_factura("HUS469401", rad._archivos_de(d), d, "COOSALUD", cfg)
        assert res.estado == "LISTA", res.detalle
        assert "RIP" in res.soportes_presentes
        assert res.valor_total == 52300.0

    def test_rips_desnudo_sin_fev_es_sin_fev(self, tmp_path, cfg):
        # RIPS desnudo + CUV pero sin FEV → debe reportar SIN_FEV (no SIN_RIPS).
        d = _factura_desnuda(tmp_path, "HUS469402", con_fev=False)
        res = rad.procesar_factura("HUS469402", rad._archivos_de(d), d, "COOSALUD", cfg)
        assert res.estado == "SIN_FEV"

    def test_fev_con_nombre_atipico_no_es_sin_fev(self, tmp_path, cfg):
        # XML sin token FEV: el fallback evita el SIN_FEV duro (queda FALTAN_
        # SOPORTES pidiendo renombrarlo), pero el RIPS desnudo sí se detecta.
        d = tmp_path / "HUS469403"
        d.mkdir()
        (d / "HUS469403.json").write_text(_rips("HUS469403"), encoding="utf-8")
        (d / "CUV_HUS469403.json").write_text("{}", encoding="utf-8")
        (d / "comprobante.xml").write_text(FEV_XML.format(fac="HUS469403"), encoding="utf-8")
        res = rad.procesar_factura("HUS469403", rad._archivos_de(d), d, "COOSALUD", cfg)
        assert res.estado != "SIN_FEV"
        assert res.estado != "SIN_RIPS"

    def test_dian_ad_cuenta_como_fev(self, tmp_path, cfg):
        # Documentos DIAN (sin "FEV_…"): el AttachedDocument ad…xml es la
        # factura electrónica → FEV presente → LISTA. El cbc:ID puede ser un
        # CUFE largo y NO debe disparar FACTURA_INCONSISTENTE.
        d = tmp_path / "HUS520769"
        d.mkdir()
        (d / "HUS520769.json").write_text(_rips("HUS520769"), encoding="utf-8")
        (d / "CUV_HUS520769.json").write_text("{}", encoding="utf-8")
        (d / "ad09000060370002600526350.xml").write_text(
            FEV_XML.format(fac="09000060370002600526350"), encoding="utf-8"
        )
        res = rad.procesar_factura("HUS520769", rad._archivos_de(d), d, "COOSALUD", cfg)
        assert res.estado == "LISTA", res.detalle
        assert "FEV" in res.soportes_presentes

    def test_sin_cuv(self, tmp_path, cfg):
        d = _factura_folder(tmp_path, "HUS500001", con_cuv=False)
        res = rad.procesar_factura("HUS500001", rad._archivos_de(d), d, "NUEVA EPS", cfg)
        assert res.estado == "SIN_CUV"
        assert "CUV" in res.soportes_faltantes

    def test_entidad_no_resuelta(self, tmp_path, cfg):
        d = _factura_folder(tmp_path, "HUS600002")
        res = rad.procesar_factura("HUS600002", rad._archivos_de(d), d, None, cfg)
        assert res.estado == "ENTIDAD_NO_RESUELTA"

    def test_revisar_por_archivo_sin_tipificar(self, tmp_path, cfg):
        d = _factura_folder(tmp_path, "HUS487523", extra={"basura.pdf": "x"})
        res = rad.procesar_factura("HUS487523", rad._archivos_de(d), d, "COOSALUD", cfg)
        assert res.estado == "REVISAR_TIPIFICACION"
        assert "basura.pdf" in res.archivos_sin_clasificar

    def test_soat_no_exige_cuv_pero_si_fur(self, tmp_path, cfg):
        # ASEGURADORA SOLIDARIA: cuv_obligatorio=false, soportes_extra=[FUR, SER].
        d = _factura_folder(tmp_path, "HUS800001", con_cuv=False)
        res = rad.procesar_factura(
            "HUS800001", rad._archivos_de(d), d, "ASEGURADORA SOLIDARIA", cfg
        )
        assert res.estado == "FALTAN_SOPORTES"
        assert "FUR" in res.soportes_faltantes and "SER" in res.soportes_faltantes
        assert "CUV" not in res.soportes_faltantes

    def test_factura_inconsistente(self, tmp_path, cfg):
        d = tmp_path / "HUSX"
        d.mkdir()
        (d / "Rips_HUS111.json").write_text(_rips("HUS111"), encoding="utf-8")
        (d / "FEV_900006037_HUS222.xml").write_text(FEV_XML.format(fac="HUS222"), encoding="utf-8")
        (d / "CUV_900006037_HUS111.json").write_text("{}", encoding="utf-8")
        res = rad.procesar_factura("HUS111", rad._archivos_de(d), d, "COOSALUD", cfg)
        assert res.estado == "FACTURA_INCONSISTENTE"


class TestDescubrimiento:
    def test_carpeta_factura_con_eps_padre(self, tmp_path, cfg):
        _factura_folder(tmp_path / "COOSALUD", "HUS1")
        _factura_folder(tmp_path / "NUEVA EPS", "HUS2")
        items = rad.descubrir_carpeta_factura(tmp_path, {}, cfg)
        hints = {fac: ent for fac, _arch, _c, ent in items}
        assert hints["HUS1"] == "COOSALUD"
        assert hints["HUS2"] == "NUEVA EPS"

    def test_lote_agrupa_por_token_y_reparte_compartidos(self, tmp_path, cfg):
        env = tmp_path / "ESCANEO" / "COOSALUD" / "ENV-1"
        env.mkdir(parents=True)
        for fac in ("HUS900001", "HUS900002"):
            (env / f"Rips_{fac}.json").write_text(_rips(fac), encoding="utf-8")
            (env / f"FEV_900006037_{fac}.xml").write_text(FEV_XML.format(fac=fac), encoding="utf-8")
            (env / f"CUV_900006037_{fac}.json").write_text("{}", encoding="utf-8")
        (env / "FURIPS12345.txt").write_text("compartido", encoding="utf-8")
        items = rad.descubrir_lote(tmp_path, {}, cfg, cfg.patron_factura)
        assert len(items) == 2
        for _fac, archivos, _c, ent in items:
            nombres = {p.name for p in archivos}
            assert "FURIPS12345.txt" in nombres  # repartido a ambas
            assert ent == "COOSALUD"  # de la carpeta padre

    def test_carpeta_factura_fusiona_arboles_paralelos(self, tmp_path, cfg):
        # La MISMA factura en …/RIPS/ENV/HUS469401 (RIPS+CUV) y en
        # …/SOPORTES/ENV/HUS469401 (FEV) debe fusionarse en UNA sola.
        base = tmp_path / "ESCANEO" / "COOSALUD"
        rips_dir = base / "RIPS" / "ENV-222467-OK" / "HUS469401"
        rips_dir.mkdir(parents=True)
        (rips_dir / "HUS469401.json").write_text(_rips("HUS469401"), encoding="utf-8")
        (rips_dir / "CUV_HUS469401.json").write_text("{}", encoding="utf-8")
        sop_dir = base / "SOPORTES" / "ENV-222467-OK" / "HUS469401"
        sop_dir.mkdir(parents=True)
        (sop_dir / "FEV_900006037_HUS469401.xml").write_text(
            FEV_XML.format(fac="HUS469401"), encoding="utf-8"
        )
        items = rad.descubrir_carpeta_factura(tmp_path, {}, cfg)
        assert len(items) == 1  # fusionadas, no dos facturas
        fac, archivos, carpeta, ent = items[0]
        nombres = {p.name for p in archivos}
        assert {
            "HUS469401.json",
            "CUV_HUS469401.json",
            "FEV_900006037_HUS469401.xml",
        } <= nombres
        assert ent == "COOSALUD"  # de la carpeta EPS de la ruta
        res = rad.procesar_factura(fac, archivos, carpeta, ent, cfg)
        assert res.estado == "LISTA", res.detalle

    def test_lote_share_real_lee_rips_desnudo(self, tmp_path, cfg):
        # Todo en la carpeta de la factura, anidada bajo ESCANEO/<EPS>/RIPS/ENV.
        leaf = tmp_path / "ESCANEO" / "COOSALUD" / "RIPS" / "ENV-1" / "HUS469401"
        leaf.mkdir(parents=True)
        (leaf / "HUS469401.json").write_text(_rips("HUS469401"), encoding="utf-8")
        (leaf / "CUV_HUS469401.json").write_text("{}", encoding="utf-8")
        (leaf / "FEV_900006037_HUS469401.xml").write_text(
            FEV_XML.format(fac="HUS469401"), encoding="utf-8"
        )
        items = rad.descubrir_lote(tmp_path, {}, cfg, cfg.patron_factura)
        assert len(items) == 1
        fac, archivos, carpeta, ent = items[0]
        assert ent == "COOSALUD"
        res = rad.procesar_factura(fac, archivos, carpeta, ent, cfg)
        assert res.estado == "LISTA", res.detalle

    def test_auto_share_fe_dian_anida_rips(self, tmp_path, cfg):
        # Share factura_electronica: …\FACTURAS_SALUD\HUS520769\ con documentos
        # DIAN y una subcarpeta RIPS\. 'auto' ancla en HUS520769 y recoge AMBOS.
        fac_dir = tmp_path / "FACTURAS_SALUD" / "HUS520769"
        rips_dir = fac_dir / "RIPS"
        rips_dir.mkdir(parents=True)
        (rips_dir / "HUS520769.json").write_text(_rips("HUS520769"), encoding="utf-8")
        (rips_dir / "CUV_HUS520769.json").write_text("{}", encoding="utf-8")
        for nombre in (
            "ad09000060370002600526350.xml",
            "ar09000060370002600526350.xml",
            "fv09000060370002600526350.xml",
            "fv09000060370002600526350.pdf",
            "HUS520769.zip",
        ):
            (fac_dir / nombre).write_text(FEV_XML.format(fac="520769"), encoding="utf-8")
        items = rad.descubrir_auto(tmp_path, {}, cfg, cfg.patron_factura)
        assert len(items) == 1  # una sola factura, no una por subcarpeta
        fac, archivos, carpeta, _ent = items[0]
        nombres = {p.name for p in archivos}
        # Recogió el RIPS de la subcarpeta Y los documentos DIAN de la carpeta.
        assert "HUS520769.json" in nombres
        assert "fv09000060370002600526350.xml" in nombres
        res = rad.procesar_factura(fac, archivos, carpeta, "COOSALUD", cfg)
        assert {"RIP", "FEV", "CUV"} <= set(res.soportes_presentes), res.detalle
        assert res.estado == "LISTA", res.detalle


class TestArmarPaquete:
    def test_arma_renombra_y_zipea(self, tmp_path, cfg):
        origen = tmp_path / "origen"
        d = _factura_folder(origen / "COOSALUD", "HUS487999")
        destino = tmp_path / "destino"
        res = rad.procesar_factura("HUS487999", rad._archivos_de(d), d, "COOSALUD", cfg)
        perfil = rad.resolver_entidad("COOSALUD", cfg)
        uso_zip = rad.armar_paquete(
            res,
            rad._archivos_de(d),
            perfil,
            destino,
            "20260624",
            1,
            mover=False,
            hacer_zip=True,
            forzar=False,
            dry_run=False,
            nit_prestador="900006037",
        )
        assert uso_zip is True
        dir_fac = destino / "COOSALUD" / "HUS487999"
        assert (dir_fac / "RIP_900006037_HUS487999.json").is_file()  # renombrado ADRES
        assert (dir_fac / "_manifiesto_radicacion.json").is_file()
        zip_ruta = destino / "COOSALUD" / "900006037_20260624_0001.zip"
        assert zip_ruta.is_file()
        with zipfile.ZipFile(zip_ruta) as zf:
            nombres = zf.namelist()
        assert "RIP_900006037_HUS487999.json" in nombres
        assert "_manifiesto_radicacion.json" not in nombres  # control interno fuera del ZIP

    def test_no_arma_si_estado_bloqueante(self, tmp_path, cfg):
        d = _factura_folder(tmp_path, "HUS500001", con_cuv=False)
        res = rad.procesar_factura("HUS500001", rad._archivos_de(d), d, "NUEVA EPS", cfg)
        destino = tmp_path / "destino"
        uso_zip = rad.armar_paquete(
            res,
            rad._archivos_de(d),
            rad.resolver_entidad("NUEVA EPS", cfg),
            destino,
            "20260624",
            1,
            mover=False,
            hacer_zip=True,
            forzar=False,
            dry_run=False,
            nit_prestador="900006037",
        )
        assert uso_zip is False
        assert not destino.exists()
        assert any("NO_ARMADO" in a for a in res.acciones)

    def test_dispensario_usa_hus_corto(self, cfg):
        archivo = Path("HEV_900006037_HUS0000487523.pdf")
        nombre = rad.nombre_soporte(archivo, "HUS0000487523", "900006037", "DISPENSARIO_HUS_CORTO")
        assert nombre == "HEV_900006037_HUS487523.pdf"

    def test_archivo_sin_clasificar_conserva_nombre(self):
        nombre = rad.nombre_soporte(Path("cosa.pdf"), "HUS1", "900006037", "ADRES")
        assert nombre == "cosa.pdf"


class TestManifiesto:
    def test_csv(self, tmp_path):
        ruta = tmp_path / "m.csv"
        ruta.write_text(
            "FACTURA,EPS\nHUS700001,SALUD TOTAL\nHUS0000700002,SANITAS\n", encoding="utf-8-sig"
        )
        mapa = rad.cargar_manifiesto(ruta)
        assert mapa[rad.normalizar_factura("HUS700001")] == "SALUD TOTAL"
        assert mapa[rad.normalizar_factura("700002")] == "SANITAS"


class TestCLI:
    def test_main_audita_y_genera_csv(self, tmp_path, cfg):
        origen = tmp_path / "lote"
        _factura_folder(origen / "COOSALUD", "HUS480001")  # LISTA
        _factura_folder(origen / "NUEVA EPS", "HUS480002", con_cuv=False)  # SIN_CUV
        reporte = tmp_path / "rep.csv"
        rc = rad.main(["--origen", str(origen), "--reporte", str(reporte)])
        assert rc == 1  # hay problemas (SIN_CUV)
        assert reporte.is_file()
        contenido = reporte.read_text(encoding="utf-8-sig")
        assert "LISTA" in contenido and "SIN_CUV" in contenido

    def test_main_todo_listo_retorna_0(self, tmp_path):
        origen = tmp_path / "lote"
        _factura_folder(origen / "COOSALUD", "HUS480001")
        _factura_folder(origen / "COOSALUD", "HUS480003")
        reporte = tmp_path / "rep.csv"
        rc = rad.main(["--origen", str(origen), "--reporte", str(reporte)])
        assert rc == 0

    def test_main_origen_inexistente(self, tmp_path):
        rc = rad.main(
            ["--origen", str(tmp_path / "no_existe"), "--reporte", str(tmp_path / "r.csv")]
        )
        assert rc == 1

    def test_main_share_real_queda_lista(self, tmp_path):
        # Reproduce el share real: RIPS+CUV en …/RIPS/ENV/<fac> y FEV en el
        # árbol hermano …/SOPORTES/ENV/<fac>. La fusión + el RIPS desnudo deben
        # dejar la factura LISTA con el layout por defecto (rc 0).
        eps = tmp_path / "ESCANEO" / "COOSALUD"
        rips_dir = eps / "RIPS" / "ENV-222467-OK" / "HUS469401"
        rips_dir.mkdir(parents=True)
        (rips_dir / "HUS469401.json").write_text(_rips("HUS469401"), encoding="utf-8")
        (rips_dir / "CUV_HUS469401.json").write_text("{}", encoding="utf-8")
        sop_dir = eps / "SOPORTES" / "ENV-222467-OK" / "HUS469401"
        sop_dir.mkdir(parents=True)
        (sop_dir / "FEV_900006037_HUS469401.xml").write_text(
            FEV_XML.format(fac="HUS469401"), encoding="utf-8"
        )
        reporte = tmp_path / "rep.csv"
        rc = rad.main(["--origen", str(tmp_path), "--reporte", str(reporte)])
        assert rc == 0, reporte.read_text(encoding="utf-8-sig")
        contenido = reporte.read_text(encoding="utf-8-sig")
        assert "LISTA" in contenido and "COOSALUD" in contenido
        # Una sola fila de datos (no duplicada por los dos árboles).
        assert contenido.count("HUS469401") >= 1
        assert "SIN_RIPS" not in contenido

    def test_main_share_fe_con_manifiesto(self, tmp_path):
        # Share factura_electronica (sin EPS en la ruta): RIPS+CUV en la
        # subcarpeta RIPS\, FEV con nombres DIAN. Con --manifiesto que mapea la
        # factura a su EPS, debe quedar LISTA (rc 0) bajo el layout auto.
        fac_dir = tmp_path / "FACTURAS_SALUD" / "HUS520769"
        rips_dir = fac_dir / "RIPS"
        rips_dir.mkdir(parents=True)
        (rips_dir / "HUS520769.json").write_text(_rips("HUS520769"), encoding="utf-8")
        (rips_dir / "CUV_HUS520769.json").write_text("{}", encoding="utf-8")
        (fac_dir / "fv09000060370002600526350.xml").write_text(
            FEV_XML.format(fac="520769"), encoding="utf-8"
        )
        (fac_dir / "ad09000060370002600526350.xml").write_text(
            FEV_XML.format(fac="520769"), encoding="utf-8"
        )
        manifiesto = tmp_path / "fact.csv"
        manifiesto.write_text("FACTURA,EPS\nHUS520769,COOSALUD\n", encoding="utf-8-sig")
        reporte = tmp_path / "rep.csv"
        rc = rad.main(
            [
                "--origen",
                str(tmp_path),
                "--manifiesto",
                str(manifiesto),
                "--reporte",
                str(reporte),
            ]
        )
        contenido = reporte.read_text(encoding="utf-8-sig")
        assert "LISTA" in contenido and "COOSALUD" in contenido, contenido
        assert rc == 0

    def test_main_share_fe_doker_completo(self, tmp_path):
        # Réplica EXACTA del share de FE (captura real): subcarpeta RIPS\ con
        # Rips_, ResultadosDoker (=CUV) y EnvioDoker (auxiliar), más documentos
        # DIAN en la carpeta de la factura. Con manifiesto → LISTA.
        fac_dir = tmp_path / "FACTURAS_SALUD" / "HUS520760"
        rips_dir = fac_dir / "RIPS"
        rips_dir.mkdir(parents=True)
        (rips_dir / "Rips_HUS520760.json").write_text(_rips("HUS520760"), encoding="utf-8")
        (rips_dir / "ResultadosDoker_HUS520760_010626002250.json").write_text(
            "{}", encoding="utf-8"
        )
        (rips_dir / "EnvioDoker_HUS520760_010626002250.json").write_text("{}", encoding="utf-8")
        (fac_dir / "ad09000060370002600526350.xml").write_text(
            FEV_XML.format(fac="520760"), encoding="utf-8"
        )
        (fac_dir / "fv09000060370002600526350.xml").write_text(
            FEV_XML.format(fac="520760"), encoding="utf-8"
        )
        (fac_dir / "fv09000060370002600526350.pdf").write_text("PDF", encoding="utf-8")
        (fac_dir / "HUS520760.zip").write_text("ZIP", encoding="utf-8")
        manifiesto = tmp_path / "fact.csv"
        manifiesto.write_text("FACTURA,EPS\nHUS520760,COOSALUD\n", encoding="utf-8-sig")
        reporte = tmp_path / "rep.csv"
        rc = rad.main(
            [
                "--origen",
                str(tmp_path),
                "--manifiesto",
                str(manifiesto),
                "--reporte",
                str(reporte),
            ]
        )
        contenido = reporte.read_text(encoding="utf-8-sig")
        assert "LISTA" in contenido, contenido
        assert "SIN_CUV" not in contenido and "SIN_RIPS" not in contenido
        assert rc == 0
