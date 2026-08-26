"""El bot que une los soportes de cada factura en un solo PDF.

Lo que se cuida: que el orden sea EXACTAMENTE el que pide el área (respuesta a
glosa, epicrisis, historia clínica, ayudas, medicamentos, enfermería, insumos,
otros), que ningún archivo se pierda por no reconocerse, que el detallado no se
cuele en el PDF y que sin `--aplicar` no se escriba nada.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import unir_soportes_adres as org  # noqa: E402

pypdf = pytest.importorskip("pypdf")


def _pdf(ruta: Path, paginas: int = 1) -> Path:
    """Un PDF mínimo pero de verdad, para que el motor lo pueda unir."""
    escritor = pypdf.PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=200, height=200)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "wb") as fh:
        escritor.write(fh)
    return ruta


# ─── Clasificación por el nombre del archivo ─────────────────────────────────


@pytest.mark.parametrize(
    ("nombre", "clave"),
    [
        ("HUS383283 RESPUESTA A GLOSA.pdf", "RESPUESTA"),
        ("680010079201_HUS349166_EPICRIS.pdf", "EPICRISIS"),
        ("HUS1 - EPI.pdf", "EPICRISIS"),
        ("HUS1 CONSULTA DE URGENCIAS.pdf", "URGENCIAS"),
        ("HUS1 TERAPIAS RESPIRATORIAS.pdf", "TERAPIAS"),
        ("HUS1-CURACIONES.pdf", "CURACIONES"),
        ("HUS1 EVOLUCIONES MEDICAS.pdf", "EVOLUCIONES"),
        ("HUS1 DESCRIPCION QUIRURGICA.pdf", "PROCEDIMIENTOS"),
        ("HUS1 HISTORIA CLINICA.pdf", "HISTORIA"),
        ("HUS400387 ANGIOTOMOGRAFIA.pdf", "AYUDAS"),
        ("HUS392861-MEDICAMENTOS.pdf", "MEDICAMENTOS"),
        ("HUS1 NOTAS DE ENFERMERIA.pdf", "ENFERMERIA"),
        ("HUS1 GASTOS QUIROFANO.pdf", "INSUMOS"),
        ("REPS.pdf", "OTROS"),
        ("cualquier cosa.pdf", "OTROS"),
        # El equipo nombra los archivos con la abreviatura sola.
        ("EPI.pdf", "EPICRISIS"),
        ("HC.pdf", "HISTORIA"),
        ("HC (2).pdf", "HISTORIA"),
        ("DX.pdf", "AYUDAS"),
        ("MED.pdf", "MEDICAMENTOS"),
        ("NTE.pdf", "ENFERMERIA"),
        ("INS.pdf", "INSUMOS"),
        ("OTROS.pdf", "OTROS"),
        # Y los exámenes, con el nombre con que salen en el detallado.
        ("GLUCOMETRIA 1.pdf", "AYUDAS"),
        ("GASES ARTERIALES.pdf", "AYUDAS"),
        ("LACTATO.pdf", "AYUDAS"),
    ],
)
def test_clasificar(nombre, clave):
    assert org.clasificar(nombre).clave == clave


def test_otros_con_nombre_propio_cuenta_como_reconocido():
    """«OTROS.pdf» es el grupo OTROS a propósito, no un archivo que nadie supo
    clasificar: no puede salir en la lista de «revisar». «papel raro.pdf» sí."""
    for nombre in ("OTROS.pdf", "OTROS (2).pdf", "REPS.pdf", "CERTIFICACION SOAT.pdf"):
        grupo, reconocido = org.clasificar_con_marca(nombre)
        assert grupo.clave == "OTROS" and reconocido, nombre
    grupo, reconocido = org.clasificar_con_marca("papel raro.pdf")
    assert grupo.clave == "OTROS" and not reconocido


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("DETALLADO HUS1.xlsx", True),
        ("HUS1 detallado de factura.pdf", True),
        ("HUS1 EPICRISIS.pdf", False),
    ],
)
def test_es_detallado(nombre, esperado):
    assert org.es_detallado(nombre) is esperado


@pytest.mark.parametrize(
    ("carpeta", "factura"),
    [
        ("HUS383283", "HUS383283"),
        ("HUS379477_PEND. CARTA CORONEL", "HUS379477"),
        ("HUS367368 ACEPTADO", "HUS367368"),
        ("HUS0000352890", "HUS352890"),
        ("SIN NUMERO", "SIN NUMERO"),
    ],
)
def test_factura_de_carpeta(carpeta, factura):
    assert org._factura_de_carpeta(Path(carpeta)) == factura


# ─── El orden, que es lo que pidió el área ───────────────────────────────────


def _carpeta_completa(tmp_path: Path) -> Path:
    raiz = tmp_path / "CAROLINA"
    fac = raiz / "HUS383283"
    # A propósito en desorden: el bot tiene que ordenarlos.
    for nombre in (
        "HUS383283 SOPORTE RARO.pdf",
        "HUS383283 INSUMOS.pdf",
        "HUS383283 NOTAS DE ENFERMERIA.pdf",
        "HUS383283 MEDICAMENTOS.pdf",
        "HUS383283 AYUDAS DIAGNOSTICAS.pdf",
        "HUS383283 PROCEDIMIENTOS.pdf",
        "HUS383283 EVOLUCIONES.pdf",
        "HUS383283 CURACIONES.pdf",
        "HUS383283 TERAPIAS.pdf",
        "HUS383283 CONSULTA DE URGENCIAS.pdf",
        "HUS383283 EPICRISIS.pdf",
        "HUS383283 RESPUESTA A GLOSA.pdf",
    ):
        _pdf(fac / nombre)
    return raiz


def test_el_orden_es_el_de_la_lista_del_area(tmp_path):
    plan = org.planificar(_carpeta_completa(tmp_path))
    assert len(plan) == 1
    assert [s.grupo.clave for s in plan[0].soportes] == [
        "RESPUESTA",
        "EPICRISIS",
        "URGENCIAS",
        "TERAPIAS",
        "CURACIONES",
        "EVOLUCIONES",
        "PROCEDIMIENTOS",
        "AYUDAS",
        "MEDICAMENTOS",
        "ENFERMERIA",
        "INSUMOS",
        "OTROS",
    ]


def test_dentro_de_un_grupo_manda_el_orden_natural(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    for n in (10, 2, 1):
        _pdf(fac / f"HUS1 EVOLUCIONES {n}.pdf")
    orden = [s.ruta.name for s in org.planificar(raiz)[0].soportes]
    assert orden == ["HUS1 EVOLUCIONES 1.pdf", "HUS1 EVOLUCIONES 2.pdf", "HUS1 EVOLUCIONES 10.pdf"]


def test_el_detallado_no_entra_al_pdf(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HUS1 EPICRISIS.pdf")
    _pdf(fac / "HUS1 DETALLADO DE FACTURA.pdf")
    (fac / "DETALLADO HUS1.xlsx").write_bytes(b"x")
    plan = org.planificar(raiz)[0]
    assert [s.ruta.name for s in plan.soportes] == ["HUS1 EPICRISIS.pdf"]
    assert sorted(d.name for d in plan.detallados) == [
        "DETALLADO HUS1.xlsx",
        "HUS1 DETALLADO DE FACTURA.pdf",
    ]


def test_ningun_archivo_se_pierde(tmp_path):
    """Lo que no se reconoce va a OTROS, pero va: no se queda por fuera."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    for nombre in ("HUS1 EPICRISIS.pdf", "papel suelto.pdf", "documento sin nombre.pdf"):
        _pdf(fac / nombre)
    plan = org.planificar(raiz)[0]
    assert len(plan.soportes) == 3
    assert sum(1 for s in plan.soportes if not s.reconocido) == 2


def test_avisa_los_soportes_obligatorios_que_faltan(tmp_path):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS1" / "HUS1 MEDICAMENTOS.pdf")
    assert org.planificar(raiz)[0].faltantes() == ["RESPUESTA A GLOSA", "EPICRISIS"]


def test_la_lista_de_facturas_filtra(tmp_path):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS1" / "a EPICRISIS.pdf")
    _pdf(raiz / "HUS2" / "b EPICRISIS.pdf")
    plan = org.planificar(raiz, facturas={"HUS2"})
    assert [f.factura for f in plan] == ["HUS2"]


# ─── Escritura ───────────────────────────────────────────────────────────────


def test_sin_aplicar_no_escribe_nada(tmp_path):
    raiz = _carpeta_completa(tmp_path)
    plan = org.unir(raiz, aplicar=False)
    assert plan[0].estado == org.ESTADO_SIMULADO
    assert not (raiz / "HUS383283" / "HUS383283_SOPORTES.pdf").exists()


def test_con_aplicar_une_en_orden(tmp_path):
    raiz = _carpeta_completa(tmp_path)
    plan = org.unir(raiz, aplicar=True)
    destino = raiz / "HUS383283" / "HUS383283_SOPORTES.pdf"
    assert destino.exists()
    assert plan[0].estado == org.ESTADO_UNIDO
    assert plan[0].paginas == 12  # una página por soporte
    assert len(pypdf.PdfReader(str(destino)).pages) == 12


def test_no_se_come_su_propio_consolidado(tmp_path):
    """Se puede correr dos veces sin que el PDF unido se anide dentro de sí mismo."""
    raiz = _carpeta_completa(tmp_path)
    org.unir(raiz, aplicar=True)
    plan = org.unir(raiz, aplicar=True)
    assert plan[0].paginas == 12
    assert all(not s.ruta.stem.upper().endswith(org.SUFIJO_UNIDO) for s in plan[0].soportes)


def test_una_carpeta_sin_pdf_no_revienta(tmp_path):
    raiz = tmp_path / "G"
    (raiz / "HUS1").mkdir(parents=True)
    plan = org.unir(raiz, aplicar=True)
    assert plan[0].estado == org.ESTADO_SIN_PDF


def test_un_pdf_dañado_no_tumba_el_lote(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HUS1 EPICRISIS.pdf")
    (fac / "HUS1 MEDICAMENTOS.pdf").write_bytes(b"esto no es un PDF")
    plan = org.unir(raiz, aplicar=True)
    assert plan[0].estado == org.ESTADO_UNIDO
    assert plan[0].paginas == 1
    assert plan[0].omitidos  # el dañado queda anotado


def test_reporte_csv(tmp_path):
    raiz = _carpeta_completa(tmp_path)
    plan = org.unir(raiz, aplicar=False)
    ruta = tmp_path / "reporte.csv"
    org.escribir_reporte(ruta, plan)
    texto = ruta.read_text(encoding="utf-8-sig")
    assert "FACTURA;ORDEN;GRUPO" in texto
    assert "RESPUESTA A GLOSA" in texto
    # El «OTRO SOPORTE RARO» no se reconoce: tiene que quedar marcado.
    assert "NO - revisar" in texto


def test_leer_facturas(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    for fila in ([None], ["HUS311371"], ["HUS0000352890"], ["texto cualquiera"], [None]):
        ws.append(fila)
    ruta = tmp_path / "facturas.xlsx"
    wb.save(str(ruta))
    assert org.leer_facturas(ruta) == {"HUS311371", "HUS352890"}


def test_main_de_punta_a_punta(tmp_path):
    raiz = _carpeta_completa(tmp_path)
    reporte = tmp_path / "r.csv"
    assert org.main(["--carpeta", str(raiz), "--aplicar", "--reporte-csv", str(reporte)]) == 0
    assert (raiz / "HUS383283" / "HUS383283_SOPORTES.pdf").exists()
    assert reporte.exists()


def test_main_avisa_si_la_carpeta_no_existe(tmp_path):
    assert org.main(["--carpeta", str(tmp_path / "no-existe")]) == 1


# ─── Nombres con las palabras pegadas ────────────────────────────────────────


def test_palabras_pegadas_sin_separador():
    """`RegistroEnfermeria.pdf` no trae guion ni espacio entre las dos palabras.

    Sin cortar donde cambia de minúscula a mayúscula quedaba
    «REGISTROENFERMERIA», donde ENFERMERIA ya no es una palabra suelta, y el
    archivo se iba a OTROS (caso real de la HUS389652).
    """
    assert org.clasificar("RegistroEnfermeria.pdf").clave == "ENFERMERIA"
    assert org.clasificar("NotasEnfermeria.pdf").clave == "ENFERMERIA"
    assert org.clasificar("HistoriaClinica.pdf").clave == "HISTORIA"
    assert org.clasificar("AyudasDiagnosticas.pdf").clave == "AYUDAS"
    # Lo que ya venía en mayúsculas sigue igual.
    assert org.clasificar("HUS400387 ANGIOTOMOGRAFIA.pdf").clave == "AYUDAS"
    assert org.clasificar("NTE-C.pdf").clave == "ENFERMERIA"


def test_lo_que_de_verdad_no_dice_nada_sigue_a_revisar():
    """`HUS390378-folio 7.pdf` no dice de qué es: tiene que salir a revisar."""
    grupo, reconocido = org.clasificar_con_marca("HUS390378-folio 7.pdf")
    assert grupo.clave == "OTROS" and not reconocido


# ─── Renombrado numerado dentro del folio ────────────────────────────────────


def test_nombre_numerado():
    grupo = next(g for g in org.GRUPOS if g.clave == "RESPUESTA")
    assert org.nombre_numerado(1, grupo) == "1 RESPUESTA A GLOSA.pdf"
    assert org.nombre_numerado(12, grupo, ".PDF") == "12 RESPUESTA A GLOSA.PDF"


def test_nombre_numerado_sin_caracteres_que_windows_rechaza():
    """Los títulos con «/» o «:» no pueden llegar tal cual a un nombre de archivo."""
    grupo = org.Grupo(99, "X", 'A/B:C"D', ())
    assert org.nombre_numerado(1, grupo) == "1 A B C D.pdf"


def test_renombrar_deja_los_soportes_como_los_nombra_el_area(tmp_path):
    """`📁 HUS179983 OK / 1 RESPUESTA A GLOSA / 2 HISTORIA CLINICA / 3 OTRO`."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS352904"
    for nombre in ("RTA_ADRES_HUS352904.pdf", "HC.pdf", "OTROS.pdf", "DX.pdf"):
        _pdf(fac / nombre)
    org.renombrar_en_orden(org.planificar(raiz)[0], aplicar=True)
    assert sorted(p.name for p in fac.iterdir()) == [
        "1 RESPUESTA A GLOSA.pdf",
        "2 HISTORIA CLINICA.pdf",
        "3 AYUDAS DIAGNOSTICAS.pdf",
        "4 OTROS.pdf",
    ]


def test_renombrar_no_pisa_cuando_el_nombre_nuevo_es_el_de_otro(tmp_path):
    """El nombre que le toca a un archivo puede ser el que todavía tiene otro.

    Renombrando de una, uno pisaría al otro: por eso se hace en dos vueltas.
    """
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    # «2 HISTORIA CLINICA.pdf» ya existe, pero le toca ser el 3.
    for nombre in ("1 RESPUESTA A GLOSA.pdf", "2 HISTORIA CLINICA.pdf", "DX.pdf"):
        _pdf(fac / nombre)
    org.renombrar_en_orden(org.planificar(raiz)[0], aplicar=True)
    nombres = sorted(p.name for p in fac.iterdir())
    assert nombres == [
        "1 RESPUESTA A GLOSA.pdf",
        "2 HISTORIA CLINICA.pdf",
        "3 AYUDAS DIAGNOSTICAS.pdf",
    ]
    assert len(nombres) == 3  # no se perdió ni se duplicó ninguno


def test_renombrar_dos_veces_deja_lo_mismo(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    for nombre in ("RTA_ADRES_HUS1.pdf", "HC.pdf"):
        _pdf(fac / nombre)
    for _ in range(2):
        org.renombrar_en_orden(org.planificar(raiz)[0], aplicar=True)
    assert sorted(p.name for p in fac.iterdir()) == [
        "1 RESPUESTA A GLOSA.pdf",
        "2 HISTORIA CLINICA.pdf",
    ]


def test_renombrar_sin_aplicar_no_toca_nada(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HC.pdf")
    plan = org.renombrar_en_orden(org.planificar(raiz)[0], aplicar=False)
    assert plan == [(fac / "HC.pdf", "1 HISTORIA CLINICA.pdf")]
    assert (fac / "HC.pdf").exists()


def test_main_renombrar(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    for nombre in ("RTA_ADRES_HUS1.pdf", "HC.pdf"):
        _pdf(fac / nombre)
    assert org.main(["--carpeta", str(raiz), "--renombrar", "--aplicar"]) == 0
    assert (fac / "1 RESPUESTA A GLOSA.pdf").exists()
    # En modo renombrar NO se arma el PDF unido.
    assert not (fac / "HUS1_SOPORTES.pdf").exists()


# ─── Los dos folios de cada factura ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("nombre", "clave"),
    [
        ("680010079201_HUS311736_FACTURA.pdf", "FACTURA"),
        ("1 FACTURA.pdf", "FACTURA"),
        ("HUS1 DETALLADO DE FACTURA.pdf", "DETALLADO"),
        ("2 DETALLADO.pdf", "DETALLADO"),
        ("3 REPRESENTACION GRAFICA DIAN.pdf", "DIAN"),
        ("HUS1 representacion grafica.pdf", "DIAN"),
        ("4 NOTAS CREDITO.pdf", "NOTAS"),
        ("HUS1 NOTA CREDITO 123.pdf", "NOTAS"),
    ],
)
def test_clasificar_el_folio_de_la_factura(nombre, clave):
    grupo = org.clasificar(nombre)
    assert grupo.clave == clave
    assert grupo.folio == org.FOLIO_FACTURA


def test_los_soportes_clinicos_siguen_en_su_folio():
    """Agregar los grupos de la factura no puede mover a los de siempre."""
    for nombre in ("HC.pdf", "DX.pdf", "RTA_ADRES_HUS1.pdf", "680010079201_HUS1_EPICRIS.pdf"):
        assert org.clasificar(nombre).folio == org.FOLIO_EPICRIS, nombre


def _carpeta_con_los_dos_folios(tmp_path: Path) -> Path:
    raiz = tmp_path / "CAROLINA"
    fac = raiz / "HUS352904"
    for nombre in (
        "RTA_ADRES_HUS352904.pdf",
        "680010079201_HUS352904_EPICRIS.pdf",
        "HC.pdf",
        "DX.pdf",
        "OTROS.pdf",
        "680010079201_HUS352904_FACTURA.pdf",
        "HUS352904 DETALLADO.pdf",
    ):
        _pdf(fac / nombre)
    return raiz


def test_planificar_reparte_los_dos_folios(tmp_path):
    plan = org.planificar(_carpeta_con_los_dos_folios(tmp_path))[0]
    assert [s.grupo.clave for s in plan.soportes] == [
        "RESPUESTA",
        "EPICRISIS",
        "HISTORIA",
        "AYUDAS",
        "OTROS",
    ]
    assert [s.grupo.clave for s in plan.soportes_factura] == ["FACTURA", "DETALLADO"]


@pytest.mark.parametrize(
    ("nombre", "factura", "esperado"),
    [
        ("680010079201_HUS352904_EPICRIS", "HUS352904", "680010079201"),
        ("680010079201_HUS352904_FACTURA.pdf", "HUS352904", "680010079201"),
        # El número que sigue es de OTRA factura: no es el NIT de esta.
        ("680010079201_HUS999999_EPICRIS", "HUS352904", ""),
        ("HC", "HUS352904", ""),
        ("2 EPICRISIS", "HUS352904", ""),
    ],
)
def test_prefijo_del_nombre(nombre, factura, esperado):
    assert org.prefijo_del_nombre(nombre, factura) == esperado


def test_nombre_folio():
    assert (
        org.nombre_folio("680010079201", "HUS352904", org.SUFIJO_EPICRIS)
        == "680010079201_HUS352904_EPICRIS.pdf"
    )
    # Sin NIT no se inventa ninguno: queda el número de factura solo.
    assert org.nombre_folio("", "HUS352904", org.SUFIJO_FACTURA) == "HUS352904_FACTURA.pdf"


def test_armar_folios_deja_los_dos_pdf_con_su_nombre(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    fac = raiz / "HUS352904"
    plan = org.armar_folios(raiz, aplicar=True)[0]

    assert sorted(p.name for p in fac.iterdir()) == [
        "1 FACTURA.pdf",
        "1 RESPUESTA A GLOSA.pdf",
        "2 DETALLADO.pdf",
        "2 EPICRISIS.pdf",
        "3 HISTORIA CLINICA.pdf",
        "4 AYUDAS DIAGNOSTICAS.pdf",
        "5 OTROS.pdf",
        "680010079201_HUS352904_EPICRIS.pdf",
        "680010079201_HUS352904_FACTURA.pdf",
    ]
    assert plan.paginas == 5 and plan.paginas_factura == 2
    assert plan.estado == org.ESTADO_UNIDO and plan.estado_factura == org.ESTADO_UNIDO


def test_el_folio_lleva_los_soportes_en_orden(tmp_path):
    """El nombre del folio es el que traía la epicrisis: numerar primero es lo
    que lo deja libre."""
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    plan = org.armar_folios(raiz, aplicar=True)[0]
    assert [s.ruta.name for s in plan.soportes] == [
        "1 RESPUESTA A GLOSA.pdf",
        "2 EPICRISIS.pdf",
        "3 HISTORIA CLINICA.pdf",
        "4 AYUDAS DIAGNOSTICAS.pdf",
        "5 OTROS.pdf",
    ]
    assert [s.ruta.name for s in plan.soportes_factura] == ["1 FACTURA.pdf", "2 DETALLADO.pdf"]


def test_armar_folios_dos_veces_deja_lo_mismo(tmp_path):
    """El folio no puede volver a meterse dentro de sí mismo."""
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    fac = raiz / "HUS352904"
    org.armar_folios(raiz, aplicar=True)
    antes = sorted(p.name for p in fac.iterdir())
    plan = org.armar_folios(raiz, aplicar=True)[0]
    assert sorted(p.name for p in fac.iterdir()) == antes
    assert plan.paginas == 5 and plan.paginas_factura == 2
    assert len(pypdf.PdfReader(str(fac / "680010079201_HUS352904_EPICRIS.pdf")).pages) == 5
    assert [p.name for p in plan.folios_previos] == [
        "680010079201_HUS352904_EPICRIS.pdf",
        "680010079201_HUS352904_FACTURA.pdf",
    ]


def test_sin_aplicar_no_arma_ningun_folio(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    fac = raiz / "HUS352904"
    antes = sorted(p.name for p in fac.iterdir())
    plan = org.armar_folios(raiz, aplicar=False)[0]
    assert sorted(p.name for p in fac.iterdir()) == antes
    assert plan.estado == org.ESTADO_SIMULADO and plan.estado_factura == org.ESTADO_SIMULADO


def test_sin_nit_el_folio_queda_con_el_numero_de_factura(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HC.pdf")
    plan = org.armar_folios(raiz, aplicar=True)[0]
    assert plan.prefijo == ""
    assert (fac / "HUS1_EPICRIS.pdf").exists()


def test_el_prefijo_por_argumento_solo_llena_lo_que_falta(tmp_path):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS1" / "HC.pdf")
    _pdf(raiz / "HUS2" / "680010079201_HUS2_EPICRIS.pdf")
    plan = org.armar_folios(raiz, aplicar=True, prefijo="900123456")
    assert (raiz / "HUS1" / "900123456_HUS1_EPICRIS.pdf").exists()
    # La HUS2 ya traía su NIT en los archivos: ese manda.
    assert (raiz / "HUS2" / "680010079201_HUS2_EPICRIS.pdf").exists()
    assert [f.prefijo for f in plan] == ["900123456", "680010079201"]


# ─── Las notas crédito, que todavía no existen ───────────────────────────────


def test_las_notas_credito_quedan_pendientes_y_no_son_una_falta(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    plan = org.planificar(raiz)[0]
    assert plan.notas_pendientes() is True
    assert "NOTAS CREDITO" not in plan.faltantes_factura()


def test_cuando_lleguen_las_notas_entran_de_cuartas(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    fac = raiz / "HUS352904"
    org.armar_folios(raiz, aplicar=True)
    _pdf(fac / "HUS352904 NOTA CREDITO 88.pdf")
    plan = org.armar_folios(raiz, aplicar=True)[0]
    assert plan.notas_pendientes() is False
    assert [s.ruta.name for s in plan.soportes_factura] == [
        "1 FACTURA.pdf",
        "2 DETALLADO.pdf",
        "3 NOTAS CREDITO.pdf",
    ]
    assert plan.paginas_factura == 3


def test_avisa_los_renglones_que_le_faltan_al_folio_de_la_factura(tmp_path):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS1" / "680010079201_HUS1_FACTURA.pdf")
    plan = org.planificar(raiz)[0]
    assert plan.faltantes_factura() == ["DETALLADO", "REPRESENTACION GRAFICA DIAN"]


# ─── La factura, que vive en la carpeta del XML ──────────────────────────────


def test_indice_facturas(tmp_path):
    xml = tmp_path / "XML"
    _pdf(xml / "680010079201_HUS311736_FACTURA.pdf")
    _pdf(xml / "680010079201_HUS352904_FACTURA.pdf")
    (xml / "680010079201_HUS311736_FACTURA.xml").write_text("<x/>", encoding="utf-8")
    assert sorted(org.indice_facturas(xml)) == ["HUS311736", "HUS352904"]


def test_copiar_facturas_trae_la_factura_a_su_carpeta(tmp_path):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS311736" / "HC.pdf")
    _pdf(raiz / "HUS999" / "HC.pdf")
    xml = tmp_path / "XML"
    _pdf(xml / "680010079201_HUS311736_FACTURA.pdf")

    plan = org.planificar(raiz)
    copias = org.copiar_facturas(plan, org.indice_facturas(xml), aplicar=True)
    assert [(c.factura, c.estado) for c in copias] == [
        ("HUS311736", org.ESTADO_COPIADA),
        ("HUS999", org.ESTADO_SIN_FACTURA),
    ]
    assert (raiz / "HUS311736" / "680010079201_HUS311736_FACTURA.pdf").exists()
    # Y el NIT de la factura copiada ya sirve para nombrar los dos folios.
    assert plan[0].prefijo == "680010079201"
    org.aplicar_folios(plan, aplicar=True)
    assert (raiz / "HUS311736" / "680010079201_HUS311736_EPICRIS.pdf").exists()
    assert (raiz / "HUS311736" / "1 FACTURA.pdf").exists()


def test_copiar_facturas_no_pisa_la_que_ya_esta(tmp_path):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS311736" / "680010079201_HUS311736_FACTURA.pdf", paginas=7)
    xml = tmp_path / "XML"
    _pdf(xml / "680010079201_HUS311736_FACTURA.pdf", paginas=1)
    plan = org.planificar(raiz)
    copias = org.copiar_facturas(plan, org.indice_facturas(xml), aplicar=True)
    assert copias[0].estado == org.ESTADO_YA_ESTABA
    ruta = raiz / "HUS311736" / "680010079201_HUS311736_FACTURA.pdf"
    assert len(pypdf.PdfReader(str(ruta)).pages) == 7


def test_copiar_facturas_sin_aplicar_no_copia(tmp_path):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS311736" / "HC.pdf")
    xml = tmp_path / "XML"
    _pdf(xml / "680010079201_HUS311736_FACTURA.pdf")
    copias = org.copiar_facturas(org.planificar(raiz), org.indice_facturas(xml), aplicar=False)
    assert copias[0].estado == org.ESTADO_SE_COPIARIA
    assert not (raiz / "HUS311736" / "680010079201_HUS311736_FACTURA.pdf").exists()


# ─── El detallado, que sale en Excel ─────────────────────────────────────────


def test_avisa_el_detallado_que_todavia_esta_en_excel(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HC.pdf")
    (fac / "DETALLADO HUS1.xlsx").write_bytes(b"x")
    plan = org.planificar(raiz)[0]
    assert [d.name for d in plan.detallados_sin_pdf] == ["DETALLADO HUS1.xlsx"]
    assert "DETALLADO" in plan.faltantes_factura()


def test_si_el_detallado_ya_esta_en_pdf_no_hay_nada_que_convertir(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HUS1 DETALLADO.pdf")
    (fac / "DETALLADO HUS1.xlsx").write_bytes(b"x")
    plan = org.planificar(raiz)[0]
    assert plan.detallados_sin_pdf == []
    assert org.convertir_detallados([plan], aplicar=False) == []


def test_convertir_detallados_simulando(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HC.pdf")
    (fac / "DETALLADO HUS1.xlsx").write_bytes(b"x")
    hechos = org.convertir_detallados(org.planificar(raiz), aplicar=False)
    assert [(f, r.name, e) for f, r, e in hechos] == [
        ("HUS1", "DETALLADO HUS1.xlsx", org.ESTADO_SE_PASARIA)
    ]
    assert not (fac / "DETALLADO HUS1.pdf").exists()


def test_sin_excel_ni_libreoffice_no_revienta(tmp_path, monkeypatch):
    """En un equipo sin Excel ni LibreOffice el bot avisa, no se cae."""
    import excel_a_pdf

    def _sin_motor(pedido, ruta):
        raise SystemExit("No hay con qué convertir")

    monkeypatch.setattr(excel_a_pdf, "elegir_motor", _sin_motor)
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HC.pdf")
    (fac / "DETALLADO HUS1.xlsx").write_bytes(b"x")
    hechos = org.convertir_detallados(org.planificar(raiz), aplicar=True)
    assert hechos and hechos[0][2].startswith(org.ESTADO_ERROR)


# ─── Reporte y CLI del modo folio ────────────────────────────────────────────


def test_reporte_csv_de_los_dos_folios(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    plan = org.armar_folios(raiz, aplicar=False)
    ruta = tmp_path / "folios.csv"
    org.escribir_reporte(ruta, plan)
    texto = ruta.read_text(encoding="utf-8-sig")
    assert "OBSERVACION;FOLIO" in texto
    assert f"REPRESENTACION GRAFICA DIAN;;NO;{raiz / 'HUS352904'}" in texto
    assert "PENDIENTE: las notas crédito" in texto
    assert org.FOLIO_FACTURA in texto


def test_main_folio_de_punta_a_punta(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    xml = tmp_path / "XML"
    _pdf(xml / "680010079201_HUS352904_FACTURA.pdf")
    reporte = tmp_path / "r.csv"
    assert (
        org.main(
            [
                "--carpeta",
                str(raiz),
                "--folio",
                "--carpeta-facturas",
                str(xml),
                "--aplicar",
                "--reporte-csv",
                str(reporte),
            ]
        )
        == 0
    )
    fac = raiz / "HUS352904"
    assert (fac / "680010079201_HUS352904_EPICRIS.pdf").exists()
    assert (fac / "680010079201_HUS352904_FACTURA.pdf").exists()
    assert reporte.exists()
    # El consolidado viejo NO se arma en modo folio.
    assert not (fac / "HUS352904_SOPORTES.pdf").exists()


def test_main_folio_avisa_si_la_carpeta_de_facturas_no_existe(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    assert (
        org.main(
            ["--carpeta", str(raiz), "--folio", "--carpeta-facturas", str(tmp_path / "no-existe")]
        )
        == 1
    )


def test_main_folio_sin_aplicar_no_escribe(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    fac = raiz / "HUS352904"
    antes = sorted(p.name for p in fac.iterdir())
    assert org.main(["--carpeta", str(raiz), "--folio"]) == 0
    assert sorted(p.name for p in fac.iterdir()) == antes


def test_una_carpeta_vacia_no_revienta_en_modo_folio(tmp_path):
    raiz = tmp_path / "G"
    (raiz / "HUS1").mkdir(parents=True)
    plan = org.armar_folios(raiz, aplicar=True)[0]
    assert plan.estado == org.ESTADO_SIN_PDF and plan.estado_factura == org.ESTADO_SIN_PDF


def test_un_pdf_dañado_no_tumba_el_folio_de_la_factura(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "680010079201_HUS1_FACTURA.pdf")
    (fac / "HUS1 DETALLADO.pdf").write_bytes(b"esto no es un PDF")
    plan = org.armar_folios(raiz, aplicar=True)[0]
    assert plan.estado_factura == org.ESTADO_UNIDO
    assert plan.paginas_factura == 1
    assert plan.omitidos


def test_renombrar_lista_deja_la_ruta_nueva_en_el_soporte(tmp_path):
    """El folio se arma con los nombres YA numerados: si la ruta no se
    actualiza, se uniría un archivo que ya no existe."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HC.pdf")
    plan = org.planificar(raiz)[0]
    org.renombrar_lista(plan.soportes, aplicar=True)
    assert plan.soportes[0].ruta == fac / "1 HISTORIA CLINICA.pdf"
    assert plan.soportes[0].ruta.exists()


def test_la_simulacion_muestra_el_folio_como_va_a_quedar(tmp_path):
    """La simulación no copia ni convierte, pero sí tiene que mostrar el folio
    completo: si no, el auditor ve «falta la FACTURA» donde no falta."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS311736"
    _pdf(fac / "HC.pdf")
    (fac / "DETALLADO HUS311736.xlsx").write_bytes(b"x")
    xml = tmp_path / "XML"
    _pdf(xml / "680010079201_HUS311736_FACTURA.pdf")

    plan = org.planificar(raiz)
    org.copiar_facturas(plan, org.indice_facturas(xml), aplicar=False)
    org.convertir_detallados(plan, aplicar=False)
    assert [s.grupo.clave for s in plan[0].soportes_factura] == ["FACTURA", "DETALLADO"]
    assert plan[0].faltantes_factura() == ["REPRESENTACION GRAFICA DIAN"]
    # …pero en el disco no se tocó nada.
    assert sorted(p.name for p in fac.iterdir()) == ["DETALLADO HUS311736.xlsx", "HC.pdf"]
    assert plan[0].destino_epicris.name == "680010079201_HUS311736_EPICRIS.pdf"


def test_renombrar_no_se_cae_si_el_archivo_ya_no_esta(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "HC.pdf")
    plan = org.planificar(raiz)[0]
    plan.soportes.append(org.Soporte(ruta=fac / "se lo llevaron.pdf", grupo=org.GRUPO_OTROS))
    org.renombrar_lista(plan.soportes, aplicar=True)
    assert (fac / "1 HISTORIA CLINICA.pdf").exists()


def test_el_folio_no_se_anida_aunque_falte_ese_soporte(tmp_path):
    """El caso que se escapó en la prueba real: la HUS311736 no tiene epicrisis.

    El folio `..._EPICRIS.pdf` de la primera corrida se colaba como si fuera una
    epicrisis y en la segunda corrida el folio crecía metido dentro de sí mismo.
    """
    raiz = tmp_path / "G"
    fac = raiz / "HUS311736"
    _pdf(fac / "RTA_ADRES_HUS311736.pdf")
    _pdf(fac / "HC.pdf")
    _pdf(fac / "680010079201_HUS311736_FACTURA.pdf")
    org.armar_folios(raiz, aplicar=True)
    antes = sorted(p.name for p in fac.iterdir())
    plan = org.armar_folios(raiz, aplicar=True)[0]
    assert sorted(p.name for p in fac.iterdir()) == antes
    assert plan.paginas == 2  # la respuesta y la historia clínica, nada más
    assert len(pypdf.PdfReader(str(fac / "680010079201_HUS311736_EPICRIS.pdf")).pages) == 2


def test_avisa_cuando_no_puede_saber_si_es_folio_o_soporte_nuevo(tmp_path):
    """Carpeta ya armada + un `..._EPICRIS.pdf` sin su «2 EPICRISIS.pdf» al lado:
    se toma como el folio anterior, pero tiene que quedar avisado."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS311736"
    _pdf(fac / "1 RESPUESTA A GLOSA.pdf")
    _pdf(fac / "680010079201_HUS311736_EPICRIS.pdf")
    plan = org.planificar(raiz)[0]
    assert [p.name for p in plan.folios_dudosos] == ["680010079201_HUS311736_EPICRIS.pdf"]
    ruta = tmp_path / "r.csv"
    org.escribir_reporte(ruta, [plan])
    assert "REVISAR: se tomó como el folio" in ruta.read_text(encoding="utf-8-sig")


def test_el_folio_de_la_primera_corrida_no_es_dudoso(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    org.armar_folios(raiz, aplicar=True)
    plan = org.planificar(raiz)[0]
    assert len(plan.folios_previos) == 2 and plan.folios_dudosos == []


def test_una_factura_bloqueada_no_tumba_las_demas(tmp_path, monkeypatch):
    """En el share del hospital son 324 facturas. Un archivo abierto en Acrobat
    —o el share que se cae— no puede dejar sin folio a las otras 323."""
    raiz = tmp_path / "G"
    for numero in ("HUS1", "HUS2", "HUS3"):
        _pdf(raiz / numero / "HC.pdf")

    original = Path.rename

    def _rename(self, destino):
        if "HUS2" in str(self):
            raise PermissionError(13, "El archivo está abierto en otro programa")
        return original(self, destino)

    monkeypatch.setattr(Path, "rename", _rename)
    plan = org.armar_folios(raiz, aplicar=True)

    assert (raiz / "HUS1" / "HUS1_EPICRIS.pdf").exists()
    assert (raiz / "HUS3" / "HUS3_EPICRIS.pdf").exists()
    malas = [f for f in plan if f.estado == org.ESTADO_ERROR]
    assert [f.factura for f in malas] == ["HUS2"]
    assert malas[0].omitidos and "no pude renombrar" in malas[0].omitidos[0]
