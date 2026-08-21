"""El bot que pasa las glosas del ADRES al formato OBJECIONES de DGH.

Lo que se cuida aquí es lo que le costaría plata al hospital: que no se pierda
ni un renglón, que el código de servicio de DGH salga del cruce y no de una
suposición, que la objeción no supere el tope de DGH y que el archivo se parta
en lotes de 300 facturas.
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import organizar_objeciones_adres as org  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")


HOY = _dt.datetime(2026, 8, 21)


# ─── Ayudas para armar los libros de prueba ──────────────────────────────────

CAB_GLOSAS = [
    "Número Factura",
    "FECHA DE FACTURA",
    "FECHA DE RADICACION",
    "Número Paquete",
    "Cantidad Reclamado",
    "Valor Reclamado",
    "Valor Aprobado",
    "Valor Glosado",
    "Cod Elemento",
    "Descripción Glosa",
    "CODIGO NUMERICO",
    "CLASIFICACION DE LA GLOSA",
    "CANTIDAD ACEPTADA",
    "VALOR ACEPTADO",
]
CAB_REPORTE = [
    "Número Factura",
    "Número Paquete",
    "Cantidad Reclamado",
    "Valor Reclamado",
    "Cantidad Aprobada",
    "Valor Aprobado",
    "Valor Glosado",
    "Tipo Elemento",
    "Cod Elemento",
    "Descripción Elemento",
    "Descripción Glosa",
]
CAB_DGH = [
    "NIT",
    "CONS_ORDER",
    "SLNSERPRO_SERVICIO",
    "DESCRIPCION INSTITUCIONAL",
    "SLNSERPRO_CUPS",
    "DESCRIPCION CUPS",
    "CODIGO_MEDICAMENTO",
    "COD_MED_FACTURA",
    "NOMBRE_MEDICAMENTO",
    "CENTRO_COSTO",
    "NOM_CENTRO_COSTO",
    "FACTURA",
    "FECHA_FACTURA",
    "FECHA_INGRESO",
    "FECHA_EGRESO",
    "CAT_SERVICIOS",
    "Vr_SERVICIO",
    "SALDO_FACT",
]


def _libro(tmp_path: Path, nombre: str, hojas: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, filas in hojas.items():
        ws = wb.create_sheet(titulo)
        for fila in filas:
            ws.append(fila)
    ruta = tmp_path / nombre
    wb.save(str(ruta))
    return ruta


def glosa(
    factura, cod, vglos, codnum, clasif, texto="", vrecl=None, cant=1, vacep=None, paquete="31068"
):
    return [
        factura,
        "2024-09-26",
        "2025-12-03",
        paquete,
        cant,
        vglos if vrecl is None else vrecl,
        0,
        vglos,
        cod,
        texto or f"{cod}-Procedimientos-{codnum}- causal de prueba",
        codnum,
        clasif,
        None,
        vacep,
    ]


def linea_dgh(factura, servicio="", desc="", cups="", medicamento="", nombre="", valor=0, saldo=0):
    return [
        "901037916",
        1,
        servicio or None,
        desc or None,
        cups or None,
        desc or None,
        medicamento or None,
        medicamento or None,
        nombre or None,
        "730102",
        "URGENCIAS",
        factura,
        None,
        None,
        None,
        1,
        valor,
        saldo,
    ]


# ─── Piezas sueltas ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("HUS311371", "HUS0000311371"),
        ("HUS0000311371", "HUS0000311371"),  # idempotente
        ("hus 311371", "HUS0000311371"),
        ("", ""),
        ("ACTA-99", "ACTA-99"),  # lo que no reconoce, lo deja igual
    ],
)
def test_factura_larga(entrada, esperado):
    assert org.factura_larga(entrada) == esperado


def test_limpiar_texto_glosa_corta_en_la_ultima_repeticion():
    crudo = (
        "39145-Procedimientos-3202- La consulta no esta justificada "
        "-3202- La consulta no esta justificada"
    )
    assert org.limpiar_texto_glosa(crudo, "3202") == "La consulta no esta justificada"


def test_limpiar_texto_glosa_sin_codigo_usa_la_clasificacion():
    """La glosa total por FURIPS no trae causal: la celda solo repite el servicio."""
    crudo = "29117-Procedimientos-Terapia respiratoria: higiene bronquial"
    assert org.limpiar_texto_glosa(crudo, "", "GLOSADA TOTAL POR FURIPS") == (
        "GLOSADA TOTAL POR FURIPS"
    )


def test_limpiar_texto_glosa_sin_marca_devuelve_el_texto():
    assert org.limpiar_texto_glosa("  texto   suelto ", "9999") == "texto suelto"


@pytest.mark.parametrize(
    ("clasificacion", "grupo"),
    [
        ("PERTINENCIA", "CL"),
        ("PERTINENCIA (NO DERIVADOS DEL SINIESTRO)", "CL"),
        ("SOPORTES", "SO"),
        ("HABILITACION REPS", "SO"),
        ("TARIFAS", "TA"),
        ("FACTURACION", "FA"),
        ("CODIGOS CUPS", "FA"),
        ("GLOSADA TOTAL POR  FURIPS", ""),
        ("", ""),
    ],
)
def test_grupo_dgh(clasificacion, grupo):
    assert org.grupo_dgh(clasificacion) == grupo


@pytest.mark.parametrize(
    ("clasificaciones", "tipo"),
    [
        ({"SOPORTES", "TARIFAS"}, 0),
        ({"PERTINENCIA"}, 1),
        ({"PERTINENCIA", "SOPORTES"}, 2),
    ],
)
def test_crotipobj_factura(clasificaciones, tipo):
    assert org.crotipobj_factura(clasificaciones) == tipo


def test_construir_crdobserv_lleva_codigo_servicio_y_valor():
    fila = org.FilaAdres(
        cod_elemento="29117",
        descripcion="Terapia respiratoria",
        codigo_glosa="3106",
        texto_glosa="Soporte de material ausente",
    )
    assert org.construir_crdobserv("3106", fila, 31800) == (
        "3106 Soporte de material ausente (29117-Terapia respiratoria)$31800"
    )


def test_construir_crdobserv_sin_descripcion_solo_deja_el_codigo():
    fila = org.FilaAdres(cod_elemento="29117", codigo_glosa="3106", texto_glosa="X")
    assert org.construir_crdobserv("3106", fila, 100) == "3106 X (29117)$100"


@pytest.mark.parametrize(
    ("valor", "tope", "saldo", "esperado", "hay_motivo"),
    [
        (1000.0, 5000.0, 9000.0, 1000, False),  # cabe: no se toca
        (8000.0, 5000.0, 9000.0, 5000, True),  # tope del servicio
        (8000.0, 0.0, 6000.0, 6000, True),  # sin tope de servicio, manda el saldo
        (8000.0, 0.0, 0.0, 8000, False),  # sin cruce en DGH: no hay con qué topar
        (1364.5, 0.0, 0.0, 1364, False),  # pesos enteros
    ],
)
def test_aplicar_tope(valor, tope, saldo, esperado, hay_motivo):
    final, motivo = org.aplicar_tope(valor, tope, saldo)
    assert final == esperado
    assert bool(motivo) is hay_motivo


# ─── Homologación del código de servicio ─────────────────────────────────────


def _fila(cod, descripcion="", vrecl=0.0, cant=1.0, tipo="Procedimientos"):
    return org.FilaAdres(
        factura="HUS0000000001",
        cod_elemento=cod,
        descripcion=descripcion,
        tipo_elemento=tipo,
        valor_reclamado=vrecl,
        cantidad=cant,
    )


def test_resolver_codigo_directo():
    lineas = [org.LineaDgh(slnserpro="873420", desc_institucional="RADIOGRAFIA", valor=95400)]
    r = org.resolver_slnserpro(_fila("873420"), lineas, {})
    assert (r.slnserpro, r.metodo) == ("873420", org.METODO_CODIGO)


def test_resolver_codigo_directo_ignora_ceros_de_relleno():
    """DGH escribe 19935303-04 y el ADRES 19935303-4: es el mismo medicamento."""
    lineas = [org.LineaDgh(slnserpro="19935303-04", nombre_medicamento="ACETAMINOFEN", valor=800)]
    r = org.resolver_slnserpro(_fila("19935303-4"), lineas, {})
    assert r.slnserpro == "19935303-04"


def test_resolver_homologa_soat_a_cups():
    lineas = [
        org.LineaDgh(slnserpro="939403", cups="939403", desc_institucional="TERAPIA", valor=31800)
    ]
    r = org.resolver_slnserpro(_fila("29117"), lineas, {"29117": {"939403"}})
    assert (r.slnserpro, r.metodo) == ("939403", org.METODO_SOAT)


def test_resolver_por_descripcion_igual():
    lineas = [org.LineaDgh(slnserpro="105M01", desc_institucional="INTERNACIÓN EN UCI", valor=100)]
    r = org.resolver_slnserpro(_fila("99999", "Internacion en UCI"), lineas, {})
    assert (r.slnserpro, r.metodo) == ("105M01", org.METODO_DESC)


def test_resolver_por_valor_y_palabras_en_comun():
    """El ADRES dice «Habitación de cuatro ó mas camas» y DGH «Internación
    complejidad alta cuatro o mas camas»: distinto nombre, mismo servicio."""
    lineas = [
        org.LineaDgh(
            slnserpro="10A004",
            desc_institucional="INTERNACION COMPLEJIDAD ALTA CUATRO O MAS CAMAS",
            valor=359500,
        ),
        org.LineaDgh(slnserpro="FMQ0040", nombre_medicamento="VENDA DE ALGODON", valor=9300),
    ]
    fila = _fila("38134", "Habitación de cuatro ó mas camas", vrecl=359500)
    r = org.resolver_slnserpro(fila, lineas, {})
    assert (r.slnserpro, r.metodo) == ("10A004", org.METODO_VALOR)


def test_resolver_por_valor_no_decide_si_hay_dos_candidatos():
    """Dos servicios distintos con el mismo valor: nadie adivina cuál era."""
    lineas = [
        org.LineaDgh(slnserpro="AAA", desc_institucional="CUATRO O MAS CAMAS ALTA", valor=1000),
        org.LineaDgh(slnserpro="BBB", desc_institucional="CUATRO O MAS CAMAS MEDIA", valor=1000),
    ]
    fila = _fila("38134", "Habitación de cuatro ó mas camas", vrecl=1000)
    assert org.resolver_slnserpro(fila, lineas, {}).slnserpro == ""


def test_resolver_sin_cruce_devuelve_candidato_pero_no_lo_escribe():
    """Lo que no se pudo homologar sale vacío, con la pista aparte: no se inventa."""
    lineas = [
        org.LineaDgh(slnserpro="786301", desc_institucional="EXTRACCION DE MATERIAL", valor=1)
    ]
    r = org.resolver_slnserpro(_fila("39001", "Honorarios Cirujano Grupo 03"), lineas, {})
    assert r.slnserpro == ""
    assert r.metodo == org.METODO_SIN_CRUCE
    assert r.candidato == "786301"


def test_resolver_sin_lineas_no_revienta():
    assert org.resolver_slnserpro(_fila("29117"), [], {}).slnserpro == ""


# ─── Lotes ───────────────────────────────────────────────────────────────────


def test_lotes_parte_de_a_300_facturas_sin_romper_ninguna():
    registros = [
        {"CRNCXC": f"HUS{n:010d}", "CROVALOBJ": 1} for n in range(1, 325) for _ in range(2)
    ]
    grupos = org.lotes(registros, 300)
    assert len(grupos) == 2
    assert [len({r["CRNCXC"] for r in g}) for g in grupos] == [300, 24]
    assert sum(len(g) for g in grupos) == len(registros)
    # ninguna factura queda partida entre dos lotes
    assert not ({r["CRNCXC"] for r in grupos[0]} & {r["CRNCXC"] for r in grupos[1]})


def test_lotes_sin_tope_deja_todo_junto():
    registros = [{"CRNCXC": "HUS1", "CROVALOBJ": 1}]
    assert org.lotes(registros, 0) == [registros]
    assert org.lotes([], 300) == []


# ─── Conversión completa ─────────────────────────────────────────────────────


def _conversion(filas, dgh=None, soat=None, **kw):
    return org.construir_registros(filas, dgh or {}, soat or {}, fecha=HOY, **kw)


def test_no_se_pierde_ningun_renglon():
    """«Que todos los servicios queden completos»: sale una objeción por glosa,
    aunque no se haya podido homologar el código."""
    filas = [
        _fila("29117", "Terapia"),
        _fila("NO-EXISTE", "Algo que DGH no tiene"),
        _fila("", ""),
    ]
    for f in filas:
        f.codigo_glosa = "3106"
        f.valor_glosado = 100
    conversion = _conversion(filas)
    assert len(conversion.registros) == 3


def test_las_16_columnas_y_sus_constantes():
    fila = _fila("29117", "Terapia")
    fila.codigo_glosa = "3106"
    fila.clasificacion = "SOPORTES"
    fila.valor_glosado = 31800
    registro = _conversion([fila]).registros[0]
    assert set(registro) == set(org.COLUMNAS_OBJECIONES)
    assert registro["CDCONSEC"] == "1"  # texto, como el archivo real
    assert registro["GENUSUARIO4"] == "999"
    assert registro["CROCLAOBJ"] == 0
    assert registro["CROTIPOBJ"] == 0  # soportes: administrativa
    assert registro["CRNCXC"] == "HUS0000000001"
    assert registro["CROVALOBJ"] == 31800
    assert registro["CDFECDOC"] == HOY and registro["CROFECOBJ"] == HOY


def test_consecutivo_por_factura():
    filas = []
    for n, factura in enumerate(("HUS0000000001", "HUS0000000001", "HUS0000000002"), start=1):
        f = _fila("X", "Y")
        f.factura = factura
        f.codigo_glosa = "3106"
        f.valor_glosado = n
        filas.append(f)
    consecutivos = [r["CDCONSEC"] for r in _conversion(filas).registros]
    assert consecutivos == ["1", "1", "2"]


def test_el_guardian_recorta_al_valor_del_servicio_en_dgh():
    fila = _fila("873420", "Radiografia")
    fila.codigo_glosa = "4307"
    fila.valor_glosado = 200000
    dgh = {
        "HUS0000000001": [
            org.LineaDgh(
                slnserpro="873420", desc_institucional="RADIOGRAFIA", valor=95400, saldo=500000
            )
        ]
    }
    conversion = _conversion([fila], dgh)
    assert conversion.registros[0]["CROVALOBJ"] == 95400
    assert conversion.recorte == pytest.approx(104600)
    assert any(r.motivo == org.REV_VALOR_AJUSTADO for r in conversion.revisiones)


def test_el_tope_suma_las_lineas_repetidas_del_mismo_servicio():
    """DGH trae el servicio en varios renglones: el tope es la suma, no uno solo."""
    fila = _fila("873420", "Radiografia")
    fila.codigo_glosa = "4307"
    fila.valor_glosado = 200000
    dgh = {
        "HUS0000000001": [
            org.LineaDgh(slnserpro="873420", desc_institucional="RADIOGRAFIA", valor=95400),
            org.LineaDgh(slnserpro="873420", desc_institucional="RADIOGRAFIA", valor=95400),
        ]
    }
    assert _conversion([fila], dgh).registros[0]["CROVALOBJ"] == 190800


def test_la_glosa_total_queda_marcada_y_se_puede_excluir():
    fila = _fila("29117", "Terapia")
    fila.codigo_glosa = ""
    fila.clasificacion = "GLOSADA TOTAL POR  FURIPS"
    fila.texto_glosa = "GLOSADA TOTAL POR  FURIPS"
    fila.valor_glosado = 31800
    conversion = _conversion([fila])
    assert conversion.registros[0]["CRNCONOBJ"] is None
    assert any(r.motivo == org.REV_SIN_CODIGO_GLOSA for r in conversion.revisiones)
    assert _conversion([fila], incluir_glosa_total=False).registros == []


def test_el_mapa_traduce_el_codigo_del_adres_al_de_dgh():
    fila = _fila("29117", "Terapia")
    fila.codigo_glosa = "3106"
    fila.valor_glosado = 100
    registro = _conversion([fila], mapa_codigos={"3106": "SO3401"}).registros[0]
    assert registro["CRNCONOBJ"] == "SO3401"
    assert registro["CRDOBSERV"].startswith("SO3401 ")


def test_la_factura_que_no_esta_en_dgh_queda_avisada_una_sola_vez():
    filas = []
    for n in range(3):
        f = _fila("X", "Y")
        f.codigo_glosa = "3106"
        f.valor_glosado = n + 1
        filas.append(f)
    conversion = _conversion(filas, {"HUS0000000009": []})
    avisos = [r for r in conversion.revisiones if r.motivo == org.REV_FACTURA_SIN_DGH]
    assert len(avisos) == 1


def test_la_glosa_aceptada_completa_queda_avisada():
    fila = _fila("X", "Y")
    fila.codigo_glosa = "3106"
    fila.valor_glosado = 5000
    fila.valor_aceptado = 5000
    conversion = _conversion([fila])
    assert any(r.motivo == org.REV_TODO_ACEPTADO for r in conversion.revisiones)


# ─── De punta a punta, contra archivos de verdad ─────────────────────────────


def test_de_punta_a_punta(tmp_path):
    adres = _libro(
        tmp_path,
        "ADRES.xlsx",
        {
            "ReporteGlosasReclamPJ_RADICACIO": [
                CAB_REPORTE,
                [
                    "HUS0000000001",
                    "31068",
                    1,
                    31800,
                    0,
                    0,
                    31800,
                    "Procedimientos",
                    "29117",
                    "Terapia respiratoria",
                    "",
                ],
                [
                    "HUS0000000001",
                    "31068",
                    1,
                    95400,
                    0,
                    0,
                    95400,
                    "Procedimientos",
                    "38134",
                    "Habitación de cuatro ó mas camas",
                    "",
                ],
                [
                    "HUS0000000002",
                    "31069",
                    1,
                    500,
                    0,
                    0,
                    500,
                    "Medicamentos",
                    "555",
                    "Otro paquete",
                    "",
                ],
            ],
            "Hoja1": [
                CAB_GLOSAS,
                glosa("HUS0000000001", "29117", 31800, "3106", "SOPORTES"),
                glosa("HUS0000000001", "38134", 95400, "3209", "PERTINENCIA", vrecl=95400),
                glosa("HUS0000000002", "555", 500, "3106", "SOPORTES", paquete="31069"),
            ],
        },
    )
    dgh = _libro(
        tmp_path,
        "DGH.xlsx",
        {
            "DGDATATABLE": [
                CAB_DGH,
                linea_dgh(
                    "HUS0000000001",
                    servicio="939403",
                    desc="TERAPIA RESPIRATORIA INTEGRAL",
                    cups="939403",
                    valor=31800,
                    saldo=500000,
                ),
                linea_dgh(
                    "HUS0000000001",
                    servicio="10A004",
                    desc="INTERNACION COMPLEJIDAD ALTA CUATRO O MAS CAMAS",
                    cups="10A004",
                    valor=95400,
                    saldo=500000,
                ),
            ]
        },
    )
    homologador = _libro(
        tmp_path,
        "HOM.xlsx",
        {
            "CUPS": [
                ["Homologador Gold Standard"],
                [],
                ["CUPS VIGENTE", "Código SOAT"],
                ["939403", "29117"],
            ]
        },
    )
    salida = tmp_path / "salida"
    assert (
        org.main(
            [
                "--adres",
                str(adres),
                "--dgh",
                str(dgh),
                "--homologador",
                str(homologador),
                "--salida",
                str(salida),
                "--paquete",
                "31068",
                "--fecha",
                "2026-08-21",
            ]
        )
        == 0
    )

    wb = openpyxl.load_workbook(str(salida / "OBJECIONES_ADRES_LOTE_01.xlsx"))
    ws = wb["OBJECIONES"]
    filas = list(ws.iter_rows(values_only=True))
    assert filas[0] == org.COLUMNAS_OBJECIONES
    assert len(filas) == 3  # solo el paquete 31068
    assert [f[10] for f in filas[1:]] == ["939403", "10A004"]  # homologado y por valor
    assert [f[13] for f in filas[1:]] == [31800, 95400]
    assert [f[15] for f in filas[1:]] == [2, 2]  # soportes + pertinencia = mezclada
    assert ws.cell(row=2, column=1).number_format == "@"  # CDCONSEC es texto
    assert isinstance(ws.cell(row=2, column=1).value, str)

    control = openpyxl.load_workbook(str(salida / "REVISAR_OBJECIONES_ADRES.xlsx"))
    assert control.sheetnames == ["RESUMEN", "REVISAR", "CODIGOS"]
    resumen = {r[0]: r[1] for r in control["RESUMEN"].iter_rows(values_only=True)}
    assert resumen["Glosas leídas del ADRES"] == 2
    assert resumen["Objeciones escritas"] == 2


def test_no_confunde_la_tabla_dinamica_con_la_hoja_de_glosas(tmp_path):
    """El libro del ADRES trae una dinámica con «Suma de Valor Glosado»: si el
    bot se queda con esa, escribe todas las objeciones en cero."""
    adres = _libro(
        tmp_path,
        "ADRES.xlsx",
        {
            "Hoja3": [
                [
                    "Número Factura",
                    "FECHA DE FACTURA",
                    "FECHA DE RADICACION",
                    "Número Paquete",
                    "Cantidad Reclamado",
                    "Cod Elemento",
                    "Descripción Glosa",
                    "CODIGO NUMERICO",
                    "CLASIFICACION DE LA GLOSA",
                    "Suma de Valor Glosado",
                    "Suma de VALOR ACEPTADO",
                ],
                ["HUS0000000001", "", "", "31068", 0, "29117", "x", "3106", "SOPORTES", 31800, 0],
            ],
            "Hoja1": [CAB_GLOSAS, glosa("HUS0000000001", "29117", 31800, "3106", "SOPORTES")],
        },
    )
    filas = org.leer_adres(adres, paquete="31068")
    assert [f.valor_glosado for f in filas] == [31800]


def test_sin_hoja_de_glosas_avisa_claro(tmp_path):
    vacio = _libro(tmp_path, "VACIO.xlsx", {"Hoja1": [["A", "B"], [1, 2]]})
    with pytest.raises(ValueError, match="No encontré"):
        org.leer_adres(vacio)
