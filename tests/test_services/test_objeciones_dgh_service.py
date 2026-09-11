"""Tests del servicio que arma las objeciones para DGH desde la pantalla
(app/services/objeciones_dgh_service.py).

El servicio no reimplementa nada: usa los bots de `tools/`. Lo que se prueba
acá es lo suyo — reconocer de qué entidad es el archivo, normalizar lo que
cada bot devuelve, armar el resumen del cruce y respetar las reglas fijas del
formato (CTNCENCOS vacía, CROTIPOBJ por factura, SLNSERPRO sin inventar y el
100% de los renglones).
"""

from __future__ import annotations

from pathlib import Path

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


def _vco() -> bytes:
    """Consolidado del acta del portal VCO: 10 columnas, el acta en la primera."""
    return _excel(
        "Hoja1",
        [
            "CROOBSERV",
            "NUMERO FACTURA",
            "VALOR GLOSA",
            "CODIGO GLOSA ESPECIFICA",
            "OBSERVACION",
            "CODIGO SERVICIO",
            "DESCRIPCION SERVICIO",
            "CANTIDAD",
            "VALOR UNITARIO SERVICIO",
            "VALOR TOTAL SERVICIO",
        ],
        [
            [
                "ACTA-77",
                "HUS0000548556",
                5800,
                "TA08 01 TARIFAS-MAYOR VALOR COBRADO",
                "SE OBJETA MAYOR VALOR",
                "",
                "CATETER INTRAVENOSO 20",
                1,
                5800,
                5800,
            ],
            [
                "ACTA-77",
                "HUS0000548556",
                4700,
                "CL0101",
                "SE OBJETA PERTINENCIA",
                "903883",
                "GLUCOMETRIA GLUCOSA SEMIAUTOMATIZADA",
                1,
                4700,
                4700,
            ],
        ],
    )


reportlab = pytest.importorskip("reportlab")
pdfplumber = pytest.importorskip("pdfplumber")


def _pdf_emssanar(ruta, factura: str, renglones: list[tuple], valor_obj: int) -> bytes:
    """Un PDF de objeción de ripslink como los que manda EMSSANAR.

    Se arma con las mismas bandas de columna que calibró el bot contra el PDF
    real: Tecnología | Cantidad | Valor Tec. | Cant. Objetada | Valor Objetado |
    Código Objeción | Observación.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(ruta), pagesize=letter)
    c.setFont("Helvetica", 8)
    y = 750
    for linea in (
        f"Objeción a Factura N° {factura}",
        "Tipo objeción: Glosa",
        "Fecha de Objeción: 04-09-2026",
        "Valor Factura: $1.000.000",
        f"Valor Objetado: ${valor_obj:,}".replace(",", "."),
    ):
        c.drawString(50, y, linea)
        y -= 14
    y -= 12
    for x, txt in (
        (60, "Tecnología"),
        (150, "Cantidad"),
        (200, "Valor"),
        (290, "Cantidad"),
        (340, "Valor"),
        (420, "Código"),
        (600, "Observación"),
    ):
        c.drawString(x, y, txt)
    y -= 18
    for tec, valor, cod, obs in renglones:
        c.drawString(60, y, tec)
        c.drawString(150, y, "1")
        c.drawString(200, y, f"${valor:,}".replace(",", "."))
        c.drawString(290, y, "1")
        c.drawString(340, y, f"${valor:,}".replace(",", "."))
        c.drawString(420, y, cod)
        c.drawString(600, y, obs)
        y -= 26
    c.save()
    return Path(ruta).read_bytes()


def _adres() -> bytes:
    """Excel de glosas del ADRES: códigos SOAT y causales de cuatro dígitos."""
    return _excel(
        "GLOSAS",
        [
            "FACTURA",
            "COD ELEMENTO",
            "TIPO ELEMENTO",
            "DESCRIPCION ELEMENTO",
            "CANTIDAD",
            "VALOR RECLAMADO",
            "VALOR GLOSADO",
            "VALOR ACEPTADO",
            "CODIGO NUMERICO",
            "DESCRIPCION GLOSA",
            "CLASIFICACION DE LA GLOSA",
        ],
        [
            [
                "HUS0000548556",
                "21705",
                "Procedimientos",
                "CATETER INTRAVENOSO 20",
                1,
                90000,
                5800,
                84200,
                "3202",
                "21705-Procedimientos-3202- No pertinente",
                "PERTINENCIA",
            ],
            [
                "HUS0000548556",
                "29117",
                "Procedimientos",
                "GLUCOMETRIA GLUCOSA SEMIAUTOMATIZADA",
                1,
                90000,
                4700,
                85300,
                "3106",
                "29117-Procedimientos-3106- Falta soporte",
                "SOPORTES",
            ],
        ],
    )


def _mutual() -> bytes:
    """Consolidado de MUTUAL SER: la columna «SERVICIO» trae el CÓDIGO, y el
    nombre del servicio va escondido dentro de la observación."""
    return _excel(
        "CONSOLIDADO",
        [
            "Número de factura",
            "SERVICIO",
            "Cantidad facturada",
            "Valor glosado",
            "Concepto de glosa",
            "Código de glosa",
            "Observacion",
        ],
        [
            [
                "HUS0000548556",
                "FMQ0113",
                1,
                "$\xa05.800",
                "Dispositivos médicos - TARIFAS",
                "TA0601",
                "La tecnología FMQ0113 - CATETER INTRAVENOSO 20 no se encuentra "
                "dentro del contrato número 20352.",
            ],
            [
                "HUS0000548556",
                "903883",
                1,
                "$\xa04.700",
                "Recargos no pactados - TARIFAS",
                "TA2901",
                "La tarifa facturada 4700 no coincide con la tarifa 3900 definida "
                "en el contrato para la tecnologia 903883 - GLUCOMETRIA GLUCOSA "
                "SEMIAUTOMATIZADA.",
            ],
        ],
    )


def _homologador() -> bytes:
    """Homologador Gold Standard: código SOAT → CUPS."""
    return _excel("CUPS", ["CUPS", "SOAT"], [["903883", "29117"], ["FMQ0113", "21705"]])


def _mutual_corto() -> bytes:
    """El formato de 5 columnas del 8 de septiembre: «Tecnología» en vez de
    «SERVICIO», y sin cantidad ni concepto de glosa."""
    return _excel(
        "Hoja1",
        [
            "Número de factura",
            "Tecnología",
            "Valor glosado",
            "Código de glosa",
            "Observacion",
        ],
        [
            [
                "HUS0000548556",
                "FMQ0113",
                5800,
                "TA0601",
                "La tecnología FMQ0113 - CATETER INTRAVENOSO 20 no se encuentra "
                "dentro del contrato número 20352.",
            ]
        ],
    )


def _capital() -> bytes:
    """Export de CAPITAL SALUD: sin código de servicio y con el código de glosa
    metido dentro de «DescripcionGlosa»."""
    return _excel(
        "Hoja1",
        ["FACTURA", "servicio", "Cantidad", "DescripcionGlosa", "OBSERVACION", "VALOR GLOSA"],
        [
            [
                "HUS0000548556",
                "CATETER-INTRAVENOSO-20",
                1,
                "SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios",
                "no adjuntan factura de compra",
                5800,
            ],
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

    def test_vco(self):
        assert svc.detectar_entidad(_vco()).id == "vco"

    def test_adres(self):
        assert svc.detectar_entidad(_adres()).id == "adres"

    def test_mutual(self):
        assert svc.detectar_entidad(_mutual()).id == "mutual"

    def test_mutual_no_le_roba_el_archivo_a_sanitas(self):
        """Las dos tienen una columna «NUMERO DE FACTURA»: gana la que más señas
        tenga, no la primera del catálogo."""
        assert svc.detectar_entidad(_sanitas()).id == "sanitas"
        assert svc.detectar_entidad(_adres()).id == "adres"

    def test_mutual_en_su_formato_corto(self):
        """Aunque cambie las columnas entre lotes, sigue siendo MUTUAL."""
        assert svc.detectar_entidad(_mutual_corto()).id == "mutual"

    def test_capital(self):
        assert svc.detectar_entidad(_capital()).id == "capital"

    def test_un_pdf_es_de_emssanar(self, tmp_path):
        """Es la única entidad que no manda Excel."""
        datos = _pdf_emssanar(
            tmp_path / "o.pdf",
            "HUS 548556",
            [("FMQ0113 - CATETER 20", 5800, "TA0801 - X", "n")],
            5800,
        )
        assert svc.detectar_entidad(datos).id == "emssanar"
        assert svc.es_pdf(datos) and not svc.es_pdf(_vco())

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
        assert {
            "famisanar",
            "dispensario",
            "savia",
            "saludtotal",
            "sanitas",
            "vco",
            "emssanar",
            "adres",
            "mutual",
        } <= ids


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

    def test_vco_de_punta_a_punta(self):
        """El acta del portal VCO (COOSALUD, FIDUPREVISORA, SAVIA…)."""
        r = svc.procesar(_vco(), _dgh(), fecha="2026-09-04")
        assert r.entidad_id == "vco"
        assert r.objeciones == 2 and r.facturas == 1
        assert r.valor_total == 10500
        assert r.confianza["ALTA"] == 2
        assert r.reglas_ok and not r.fallas_reglas
        assert r.nombre_objeciones == "OBJECIONES_VCO_04092026.xlsx"
        assert r.nombre_cruce == "CRUCE_VCO_04092026.xlsx"

    def test_vco_mezcla_clinica_y_administrativa_es_tipo_2(self):
        r = svc.procesar(_vco(), _dgh(), fecha="2026-09-04")
        assert r.por_factura[0]["tipo"] == 2

    def test_emssanar_de_punta_a_punta(self, tmp_path):
        """EMSSANAR manda PDF, uno por factura: se suben todos de una vez."""
        pdfs = [
            _pdf_emssanar(
                tmp_path / "a.pdf",
                "HUS 548556",
                [("FMQ0113 - CATETER 20", 5800, "TA0801 - EL CARGO", "tarifa")],
                5800,
            ),
            _pdf_emssanar(
                tmp_path / "b.pdf",
                "HUS 548557",
                [("903883 - GLUCOMETRIA", 4700, "CL0801 - NO PERTINENTE", "sin")],
                4700,
            ),
        ]
        dgh = _dgh(
            [
                ["FMQ0113", "CATETER 20", "FMQ0113", "", "", "HUS0000548556", 1, 5800, 90000],
                ["903883H", "GLUCOMETRIA", "903883", "", "", "HUS0000548557", 1, 4700, 90000],
            ]
        )
        r = svc.procesar(pdfs, dgh, fecha="2026-09-04")
        assert r.entidad_id == "emssanar"
        assert r.objeciones == 2 and r.facturas == 2
        assert r.valor_total == 10500
        assert r.reglas_ok and not r.fallas_reglas
        assert r.nombre_objeciones == "OBJECIONES_EMSSANAR_04092026.xlsx"
        # Una factura sólo administrativa (0) y otra sólo clínica (1).
        assert sorted(f["tipo"] for f in r.por_factura) == [0, 1]

    def test_emssanar_no_inventa_el_codigo_con_la_tabla_cups(self, tmp_path):
        """Sin el export, la tabla CUPS_A_DGH escribiría 876802H igual."""
        pdf = _pdf_emssanar(
            tmp_path / "a.pdf",
            "HUS 548556",
            [("876802 - RX TORAX", 20300, "TA0801 - EL CARGO", "tarifa")],
            20300,
        )
        r = svc.procesar([pdf], _dgh(), fecha="2026-09-04")
        assert r.objeciones == 1  # el renglón NO se borra
        assert r.pendientes == 1  # pero queda en REVISAR
        assert r.reglas_ok

    def test_adres_de_punta_a_punta(self):
        """El ADRES tiene motor propio (SOAT↔CUPS, topes, lotes de 300)."""
        r = svc.procesar(_adres(), _dgh(), fecha="2026-09-04")
        assert r.entidad_id == "adres"
        assert r.objeciones == 2 and r.facturas == 1
        assert r.valor_total == 10500
        assert r.reglas_ok and not r.fallas_reglas
        assert r.nombre_objeciones == "OBJECIONES_ADRES_04092026.xlsx"

    def test_adres_es_mixta_por_la_clasificacion_no_por_el_codigo(self):
        """Sus códigos (3202, 3106) no dicen el grupo: lo dice la columna
        CLASIFICACION. Pertinencia + soportes = mixta."""
        r = svc.procesar(_adres(), _dgh(), fecha="2026-09-04")
        assert r.por_factura[0]["tipo"] == 2

    def test_adres_deja_ctncencos_vacia_aunque_el_dgh_sepa_el_centro(self):
        import io

        r = svc.procesar(_adres(), _dgh(), fecha="2026-09-04")
        ws = openpyxl.load_workbook(io.BytesIO(r.objeciones_xlsx)).active
        cols = [c.value for c in ws[1]]
        assert "_grupos" not in cols  # el dato interno no baja al archivo
        for fila in ws.iter_rows(min_row=2, values_only=True):
            assert dict(zip(cols, fila))["CTNCENCOS"] is None

    def test_adres_acepta_el_homologador_como_segundo_archivo(self):
        r = svc.procesar([_adres(), _homologador()], _dgh(), fecha="2026-09-04")
        assert r.objeciones == 2 and r.reglas_ok

    def test_adres_no_acepta_un_tercer_archivo(self):
        with pytest.raises(svc.ErrorObjeciones, match="uno o dos archivos"):
            svc.procesar([_adres(), _homologador(), _adres()], _dgh(), fecha="2026-09-04")

    def test_adres_sin_glosas_avisa_claro(self):
        vacio = _excel(
            "GLOSAS",
            ["COD ELEMENTO", "VALOR GLOSADO", "VALOR ACEPTADO", "CODIGO NUMERICO"],
            [],
        )
        with pytest.raises(svc.ErrorObjeciones, match="ninguna glosa"):
            svc.procesar(vacio, _dgh(), entidad_id="adres", fecha="2026-09-04")

    def test_mutual_de_punta_a_punta(self):
        r = svc.procesar(_mutual(), _dgh(), fecha="2026-09-07")
        assert r.entidad_id == "mutual"
        assert r.objeciones == 2 and r.facturas == 1
        assert r.valor_total == 10500
        assert r.confianza["ALTA"] == 2
        assert r.reglas_ok and not r.fallas_reglas
        assert r.nombre_objeciones == "OBJECIONES_MUTUAL_07092026.xlsx"
        assert r.nombre_cruce == "CRUCE_MUTUAL_07092026.xlsx"

    def test_mutual_no_cuenta_dos_veces_la_misma_glosa(self):
        """La pantalla tiene que dar lo MISMO que la consola.

        MUTUAL lista el mismo servicio bajo dos conceptos (TA0201 y TA0601)
        pero en su total lo cuenta una vez. En el lote del 7-sep, sumar las dos
        filas daba $26.636.056 cuando la entidad reportó $24.462.346.
        """
        doble = _excel(
            "CONSOLIDADO",
            [
                "Número de factura",
                "SERVICIO",
                "Cantidad facturada",
                "Valor glosado",
                "Concepto de glosa",
                "Código de glosa",
                "Observacion",
            ],
            [
                [
                    "HUS0000548556",
                    "FMQ0113",
                    1,
                    "$\xa05.800",
                    "Consultas, interconsultas y atenciones (visitas) domiciliarias - TARIFAS",
                    "TA0201",
                    "La tecnología FMQ0113 - CATETER INTRAVENOSO 20 no se encuentra "
                    "dentro del contrato número 20352.",
                ],
                [
                    "HUS0000548556",
                    "FMQ0113",
                    1,
                    "$\xa05.800",
                    "Dispositivos médicos - TARIFAS",
                    "TA0601",
                    "La tecnología FMQ0113 - CATETER INTRAVENOSO 20 no se encuentra "
                    "dentro del contrato número 20352.",
                ],
            ],
        )
        r = svc.procesar(doble, _dgh(), fecha="2026-09-07")
        assert r.objeciones == 1
        assert r.valor_total == 5800  # no 11.600
        assert r.reglas_ok

    def test_mutual_ubica_el_servicio_por_el_nombre_de_la_observacion(self):
        """El DGH tiene la glucometría como 903883H; MUTUAL manda 903883 y el
        nombre sólo aparece dentro del texto de la observación."""
        import io

        r = svc.procesar(_mutual(), _dgh(), fecha="2026-09-07")
        ws = openpyxl.load_workbook(io.BytesIO(r.objeciones_xlsx))["OBJECIONES"]
        cols = [c.value for c in ws[1]]
        filas = [dict(zip(cols, f)) for f in ws.iter_rows(min_row=2, values_only=True)]
        assert [f["SLNSERPRO"] for f in filas] == ["FMQ0113", "903883H"]
        assert {f["CTNCENCOS"] for f in filas} == {None}
        assert {f["CROTIPOBJ"] for f in filas} == {0}

    def test_mutual_corto_de_punta_a_punta(self):
        """El lote del 8 de septiembre: la pantalla lo rechazaba por el nombre
        de la columna del servicio."""
        r = svc.procesar(_mutual_corto(), _dgh(), fecha="2026-09-08")
        assert r.entidad_id == "mutual"
        assert r.objeciones == 1
        assert r.valor_total == 5800
        assert r.reglas_ok and not r.fallas_reglas
        assert r.nombre_objeciones == "OBJECIONES_MUTUAL_08092026.xlsx"

    def test_capital_de_punta_a_punta(self):
        """CAPITAL no manda código de servicio: se ubica por nombre y valor.
        El nombre viene con guiones y hay que igualarlos a espacios."""
        r = svc.procesar(_capital(), _dgh(), fecha="2026-09-09")
        assert r.entidad_id == "capital"
        assert r.objeciones == 1 and r.facturas == 1
        assert r.valor_total == 5800
        assert r.confianza["ALTA"] == 1
        assert r.reglas_ok and not r.fallas_reglas
        assert r.nombre_objeciones == "OBJECIONES_CAPITAL_SALUD_09092026.xlsx"
        assert r.nombre_cruce == "CRUCE_CAPITAL_SALUD_09092026.xlsx"

    def test_capital_saca_el_codigo_de_glosa_de_la_descripcion(self):
        import io

        r = svc.procesar(_capital(), _dgh(), fecha="2026-09-09")
        ws = openpyxl.load_workbook(io.BytesIO(r.objeciones_xlsx)).active
        cols = [c.value for c in ws[1]]
        fila = dict(zip(cols, [c.value for c in ws[2]], strict=True))
        assert fila["CRNCONOBJ"] == "SO4201"
        assert fila["SLNSERPRO"] == "FMQ0113"
        assert fila["CTNCENCOS"] is None
        assert fila["CROTIPOBJ"] == 0

    def test_un_pdf_que_no_es_una_objecion(self, tmp_path):
        with pytest.raises(svc.ErrorObjeciones, match="PDF"):
            svc.procesar([b"%PDF-1.4 cualquier cosa"], _dgh(), fecha="2026-09-04")

    def test_las_entidades_de_excel_no_aceptan_dos_archivos(self):
        with pytest.raises(svc.ErrorObjeciones, match="un solo Excel"):
            svc.procesar([_famisanar(), _famisanar()], _dgh(), fecha="2026-09-04")

    def test_vco_no_acepta_un_archivo_ya_armado(self):
        """Si suben el OBJECIONES de 16 columnas en vez del acta, se avisa."""
        ya_armado = _excel(
            "OBJECIONES", list(svc._cargar("organizar_objeciones_vco").COLUMNAS_CARGUE), []
        )
        with pytest.raises(svc.ErrorObjeciones):
            svc.procesar(ya_armado, _dgh(), entidad_id="vco", fecha="2026-09-04")

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
