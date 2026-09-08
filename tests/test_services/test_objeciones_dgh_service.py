"""Tests del servicio que arma las objeciones para DGH desde la pantalla
(app/services/objeciones_dgh_service.py).

El servicio no reimplementa nada: usa los bots de `tools/`. Lo que se prueba
acá es lo suyo — reconocer de qué entidad es el archivo, normalizar lo que
cada bot devuelve, armar el resumen del cruce y respetar las reglas fijas del
formato (CTNCENCOS vacía, CROTIPOBJ por factura, SLNSERPRO sin inventar y el
100% de los renglones).
"""

from __future__ import annotations

import pytest

from app.services import objeciones_dgh_service as svc

openpyxl = pytest.importorskip("openpyxl")


# ─── Archivos de prueba, con el formato real de cada entidad ────────────────


def _excel(hoja: str, headers: list, filas: list[list]) -> bytes:
    import io

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(headers)
    for f in filas:
        ws.append(f)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


_HEADERS_DGH = [
    "SERVICIOS DGH",
    "DESCRIPCION INSTITUCIONAL",
    "SLNSERPRO_CUPS",
    "DESCRIPCION CUPS",
    "CODIGO_MEDICAMENTO",
    "FACTURA",
    "CAT_SERVICIOS",
    "Vr_SERVICIO",
    "SALDO_FACT",
]


def _dgh(filas=None) -> bytes:
    return _excel(
        "DGDATATABLE",
        _HEADERS_DGH,
        filas
        or [
            ["FMQ0113", "CATETER INTRAVENOSO 20", "FMQ0113", "", "", "HUS0000548556", 1, 5800, 90000],
            ["903883H", "GLUCOMETRIA GLUCOSA SEMIAUTOMATIZADA", "903883", "", "", "HUS0000548556", 1, 4700, 90000],
        ],
    )  # fmt: skip


OBS_FAMISANAR = (
    "Los dispositivos médicos que vienen relacionados o justificados en los "
    "soportes de cobro no están incluidos en la respectiva cobertura  SERVICIO "
    "SIN COBERTURA    FMQ0113 CATETER INTRAVENOSO 20   CÓDIGO    VALOR UNITARIO "
    "FACTURADO POR IPS     $      5,800"
)


def _famisanar() -> bytes:
    return _excel(
        "CONSOLIDADO",
        ["NRO_FACTURA", "CODIGO_DEVOLUCION", "VALOR DEVOLUCION", "OBSERVACION"],
        [["HUS0000548556", "CO0601", 5800, OBS_FAMISANAR]],
    )


def _dispensario() -> bytes:
    return _excel(
        "Hoja1",
        [
            "FACTURA",
            "VALOR GLOSA INICIAL",
            "SERVICIO OBJETADO",
            "CODIGO GLOSA INICIAL",
            "DESCRIPCION GLOSA INICIAL",
        ],
        [
            [
                "HUS0000548556",
                4700,
                "GLUCOMETRIA GLUCOSA SEMIAUTOMATIZADA",
                "TA08 01 TARIFAS-APOYO DIAGNÓSTICO - LOS CARGOS…",
                "SE GLOSA MVC",
            ]
        ],
    )


def _savia() -> bytes:
    return _excel(
        "Hoja1",
        [
            "Numero_factura",
            "Cod_Servicio",
            "Servicio",
            "Cantidad_Servicio",
            "Valor_Unitario",
            "Valor_Glosa",
            "Motivo_Esp_Glosa_Valor_A",
            "Observacion_Glosa_A",
        ],
        [["HUS0000548556", "FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800, 5800, "TA0801", "No pactado"]],
    )  # fmt: skip


def _saludtotal() -> bytes:
    return _excel(
        "Hoja1",
        [
            "NumeroFac_",
            "NombreServicio",
            "CantidadFac",
            "ValorGlosaTotalxServ",
            "Observaciones",
            "CodMotvGlosaEspc",
        ],
        [[548556, "CATETER INTRAVENOSO 20", 1, 5800, "sin cobertura", "CO0601"]],
    )


def _sanitas() -> bytes:
    return _excel(
        "Glosa",
        [
            "NUMERO DE FACTURA",
            "NUMERO DE FACTURA",
            "VALOR REAL GLOSA",
            "CODIGO PROCEDIMIENTO",
            "NOMBRE PROCEDIMIENTO",
            "CANTIDAD PROCEDIMIENTO",
            "OBSERVACIONES",
        ],
        [
            [
                "HUS0000548556",
                "CO2301",
                4700,
                "903883",
                "GLUCOMETRIA GLUCOSA SEMIAUTOMATIZADA",
                "1",
                "Glosa Calculada Afiliado",
            ]
        ],
    )


# ─── De quién es el archivo ─────────────────────────────────────────────────


class TestDetectarEntidad:
    def test_famisanar(self):
        assert svc.detectar_entidad(_famisanar()).id == "famisanar"

    def test_dispensario(self):
        assert svc.detectar_entidad(_dispensario()).id == "dispensario"

    def test_savia(self):
        assert svc.detectar_entidad(_savia()).id == "savia"

    def test_saludtotal(self):
        assert svc.detectar_entidad(_saludtotal()).id == "saludtotal"

    def test_sanitas(self):
        assert svc.detectar_entidad(_sanitas()).id == "sanitas"

    def test_archivo_desconocido_no_se_procesa_a_ciegas(self):
        otro = _excel("Hoja1", ["COSA", "OTRA COSA"], [["a", "b"]])
        with pytest.raises(svc.ErrorObjeciones, match="No reconozco"):
            svc.detectar_entidad(otro)

    def test_archivo_que_no_es_excel(self):
        with pytest.raises(svc.ErrorObjeciones, match="Excel"):
            svc.detectar_entidad(b"esto no es un xlsx")

    def test_entidad_por_id(self):
        assert svc.entidad_por_id("sanitas").nombre == "SANITAS"
        with pytest.raises(svc.ErrorObjeciones):
            svc.entidad_por_id("no-existe")

    def test_catalogo(self):
        ids = {e["id"] for e in svc.catalogo_entidades()}
        assert {"famisanar", "dispensario", "savia", "saludtotal", "sanitas"} <= ids


# ─── El armado ──────────────────────────────────────────────────────────────


class TestProcesar:
    def test_famisanar_de_punta_a_punta(self):
        r = svc.procesar(_famisanar(), _dgh(), fecha="2026-09-04")
        assert r.entidad_id == "famisanar"
        assert r.objeciones == 1 and r.facturas == 1
        assert r.valor_total == 5800
        assert r.confianza["ALTA"] == 1
        assert r.reglas_ok and not r.fallas_reglas
        assert r.nombre_objeciones == "OBJECIONES_FAMISANAR_04092026.xlsx"
        assert r.nombre_cruce == "CRUCE_FAMISANAR_04092026.xlsx"
        assert r.objeciones_xlsx[:2] == b"PK" and r.cruce_xlsx[:2] == b"PK"

    def test_dispensario_de_punta_a_punta(self):
        r = svc.procesar(_dispensario(), _dgh(), fecha="2026-09-04")
        assert r.entidad_id == "dispensario"
        assert r.objeciones == 1
        assert r.nombre_objeciones == "OBJECIONES_DISPENSARIO_04092026.xlsx"

    def test_savia_de_punta_a_punta(self):
        r = svc.procesar(_savia(), _dgh(), fecha="2026-09-04")
        assert r.entidad_id == "savia"
        assert r.objeciones == 1
        assert r.confianza["ALTA"] == 1
        assert r.reglas_ok
        # El nombre del archivo usa la primera palabra: SAVIA SALUD → SAVIA.
        assert r.nombre_objeciones == "OBJECIONES_SAVIA_04092026.xlsx"

    def test_saludtotal_de_punta_a_punta(self):
        """SALUD TOTAL no manda código: el servicio se ubica por nombre y valor."""
        r = svc.procesar(_saludtotal(), _dgh(), fecha="2026-09-04")
        assert r.entidad_id == "saludtotal"
        assert r.objeciones == 1
        assert r.confianza["ALTA"] == 1
        assert r.reglas_ok
        # La factura viene pelada (548556) y se completa a HUS0000548556.
        assert r.por_factura[0]["factura"] == "HUS0000548556"
        assert r.nombre_objeciones == "OBJECIONES_SALUDTOTAL_04092026.xlsx"

    def test_cada_entidad_nombra_sus_archivos_como_su_bot(self):
        """El nombre corto es el del bot, no la primera palabra del nombre."""
        cortos = {e["id"]: e["corto"] for e in svc.catalogo_entidades()}
        assert cortos["saludtotal"] == "SALUDTOTAL"  # no "SALUD"
        assert cortos["savia"] == "SAVIA"

    def test_sanitas_de_punta_a_punta(self):
        r = svc.procesar(_sanitas(), _dgh(), fecha="2026-09-04")
        assert r.entidad_id == "sanitas"
        assert r.objeciones == 1
        assert r.nombre_objeciones == "OBJECIONES_SANITAS_04092026.xlsx"

    def test_el_excel_sale_con_las_16_columnas_y_las_reglas(self):
        import io

        r = svc.procesar(_famisanar(), _dgh(), fecha="2026-09-04")
        ws = openpyxl.load_workbook(io.BytesIO(r.objeciones_xlsx))["OBJECIONES"]
        headers = [c.value for c in ws[1]]
        assert len(headers) == 16 and headers[0] == "CDCONSEC"
        fila = dict(zip(headers, [c.value for c in ws[2]], strict=True))
        assert fila["CTNCENCOS"] is None  # regla fija
        assert fila["CRNCONOBJ"] == "CO0601"
        assert fila["SLNSERPRO"] == "FMQ0113"
        assert fila["CROTIPOBJ"] == 0

    def test_el_cruce_trae_la_hoja_revisar(self):
        import io

        r = svc.procesar(_famisanar(), _dgh(), fecha="2026-09-04")
        wb = openpyxl.load_workbook(io.BytesIO(r.cruce_xlsx))
        assert wb.sheetnames == ["CRUCE", "REVISAR", "RESUMEN"]

    def test_entidad_forzada_a_mano(self):
        r = svc.procesar(_sanitas(), _dgh(), entidad_id="sanitas", fecha="2026-09-04")
        assert r.entidad_id == "sanitas"

    def test_lo_que_no_cruza_va_a_revisar_pero_no_se_borra(self):
        """Regla fija: el archivo lleva el 100% de los renglones."""
        entidad = _excel(
            "CONSOLIDADO",
            ["NRO_FACTURA", "CODIGO_DEVOLUCION", "VALOR DEVOLUCION", "OBSERVACION"],
            [
                ["HUS0000548556", "CO0601", 5800, OBS_FAMISANAR],
                ["HUS0000548556", "SO0101", 999999, "Existe ausencia total en la epicrisis"],
            ],
        )
        r = svc.procesar(entidad, _dgh(), fecha="2026-09-04")
        assert r.objeciones == 2  # no se pierde ninguna
        assert r.confianza["SIN CRUCE"] == 1
        assert r.pendientes == 1
        assert r.revisar[0]["codigo_glosa"] == "SO0101"
        assert r.revisar[0]["codigo_dgh"] == ""

    def test_resumen_por_factura(self):
        r = svc.procesar(_famisanar(), _dgh(), fecha="2026-09-04")
        assert r.por_factura[0]["factura"] == "HUS0000548556"
        assert r.por_factura[0]["objeciones"] == 1
        assert r.por_factura[0]["valor"] == 5800
        assert r.por_factura[0]["revisar"] == 0

    def test_resumen_no_lleva_los_archivos(self):
        r = svc.procesar(_famisanar(), _dgh(), fecha="2026-09-04")
        assert "objeciones_xlsx" not in r.resumen()
        assert r.resumen()["objeciones"] == 1


# ─── Casos borde ────────────────────────────────────────────────────────────


class TestCasosBorde:
    def test_sin_archivo_de_la_entidad(self):
        with pytest.raises(svc.ErrorObjeciones, match="Falta el archivo"):
            svc.procesar(b"", _dgh())

    def test_sin_export_del_dgh(self):
        with pytest.raises(svc.ErrorObjeciones, match="export de servicios"):
            svc.procesar(_famisanar(), b"")

    def test_export_del_dgh_que_no_lo_es(self):
        malo = _excel("Hoja1", ["COSA"], [["x"]])
        with pytest.raises(svc.ErrorObjeciones, match="export de servicios del DGH"):
            svc.procesar(_famisanar(), malo)

    def test_archivo_de_la_entidad_sin_renglones(self):
        vacio = _excel(
            "CONSOLIDADO",
            ["NRO_FACTURA", "CODIGO_DEVOLUCION", "VALOR DEVOLUCION", "OBSERVACION"],
            [],
        )
        with pytest.raises(svc.ErrorObjeciones, match="ninguna objeción"):
            svc.procesar(vacio, _dgh())

    def test_archivo_demasiado_grande(self):
        with pytest.raises(svc.ErrorObjeciones, match="pesa más"):
            svc.procesar(b"x" * (svc.MAX_BYTES + 1), _dgh())

    def test_fecha_al_reves(self):
        with pytest.raises(svc.ErrorObjeciones, match="Fecha inválida"):
            svc.procesar(_famisanar(), _dgh(), fecha="04-09-2026")

    def test_sin_fecha_usa_hoy(self):
        from datetime import date

        r = svc.procesar(_famisanar(), _dgh())
        assert r.fecha == date.today().strftime("%Y-%m-%d")

    def test_factura_glosada_que_no_esta_en_el_dgh(self):
        """No se inventa el código: el renglón sale igual, con la celda vacía."""
        entidad = _excel(
            "CONSOLIDADO",
            ["NRO_FACTURA", "CODIGO_DEVOLUCION", "VALOR DEVOLUCION", "OBSERVACION"],
            [["HUS0000999999", "CO0601", 5800, OBS_FAMISANAR]],
        )
        r = svc.procesar(entidad, _dgh(), fecha="2026-09-04")
        assert r.objeciones == 1
        assert r.confianza["SIN CRUCE"] == 1
        assert "no está en el export del DGH" in r.revisar[0]["aviso"]
