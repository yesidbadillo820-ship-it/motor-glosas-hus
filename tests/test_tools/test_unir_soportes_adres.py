"""El bot que une los soportes de cada factura en un solo PDF.

Lo que se cuida: que el orden sea EXACTAMENTE el que pide el área (respuesta a
glosa, epicrisis, historia clínica, ayudas, medicamentos, enfermería, insumos,
otros), que ningún archivo se pierda por no reconocerse, que el detallado no se
cuele en el PDF y que sin `--aplicar` no se escriba nada.
"""

from __future__ import annotations

import logging
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


def test_una_epicrisis_sin_firma_es_un_soporte_no_un_folio(tmp_path):
    """LA REGRESIÓN QUE MÁS IMPORTA.

    La epicrisis del ADRES viene llamada `680010079201_HUS######_EPICRIS.pdf`,
    que es exactamente como se llamará el folio. Antes el bot decidía por el
    nombre y por si la carpeta traía archivos numerados: en una carpeta donde el
    auditor ya había numerado algo a mano, tomaba la epicrisis DE VERDAD por un
    folio viejo, la dejaba fuera del folio y acto seguido la pisaba. La epicrisis
    se perdía para siempre y el folio subía al ADRES sin ella.
    """
    raiz = tmp_path / "G"
    fac = raiz / "HUS352904"
    _pdf(fac / "1 RESPUESTA A GLOSA.pdf", paginas=1)  # numerado a mano
    epicrisis = _pdf(fac / "680010079201_HUS352904_EPICRIS.pdf", paginas=5)
    _pdf(fac / "HC.pdf", paginas=3)

    plan = org.armar_folios(raiz, aplicar=True)[0]

    # La epicrisis entró al folio, no se perdió.
    assert plan.folios_previos == []
    assert [s.grupo.clave for s in plan.soportes] == ["RESPUESTA", "EPICRISIS", "HISTORIA"]
    assert plan.paginas == 9  # 1 + 5 + 3: las cinco páginas de la epicrisis están
    # La epicrisis se renombró (no se borró): sus 5 páginas siguen ahí.
    assert len(pypdf.PdfReader(str(fac / "2 EPICRISIS.pdf")).pages) == 5
    # Y esa ruta ahora la ocupa el folio, con las 9 páginas.
    assert len(pypdf.PdfReader(str(epicrisis)).pages) == 9
    assert org.es_folio_nuestro(epicrisis)


def test_el_folio_queda_firmado_y_se_reconoce_en_la_corrida_siguiente(tmp_path):
    raiz = _carpeta_con_los_dos_folios(tmp_path)
    org.armar_folios(raiz, aplicar=True)
    fac = raiz / "HUS352904"
    assert org.es_folio_nuestro(fac / "680010079201_HUS352904_EPICRIS.pdf")
    assert org.es_folio_nuestro(fac / "680010079201_HUS352904_FACTURA.pdf")
    # Un soporte cualquiera NO lleva la firma.
    assert not org.es_folio_nuestro(fac / "1 RESPUESTA A GLOSA.pdf")
    plan = org.planificar(raiz)[0]
    assert sorted(p.name for p in plan.folios_previos) == [
        "680010079201_HUS352904_EPICRIS.pdf",
        "680010079201_HUS352904_FACTURA.pdf",
    ]


def test_no_pisa_un_archivo_que_no_escribio_el_bot(tmp_path):
    """Si en la ruta del folio hay algo sin firma, no se arma nada: no se pisa."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "1 RESPUESTA A GLOSA.pdf")
    # Un archivo ajeno, justo donde iría el folio, que el renombrado no libera.
    ajeno = _pdf(fac / "HUS1_EPICRIS.pdf", paginas=7)
    ajeno.chmod(0o444)
    plan = org.planificar(raiz)[0]
    plan.soportes = [s for s in plan.soportes if s.ruta != ajeno]  # se quedó fuera
    org.aplicar_folios([plan], aplicar=True)
    assert plan.estado == org.ESTADO_NO_PISA
    assert len(pypdf.PdfReader(str(ajeno)).pages) == 7  # intacto
    assert plan.omitidos and "no lo escribió este bot" in plan.omitidos[0]


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


# ─── La factura que ya viene con el folio armado adentro ─────────────────────


def _pdf_con_texto(ruta: Path, paginas: list[str]) -> Path:
    """Un PDF con texto de verdad, para probar lo que el bot lee adentro."""
    reportlab = pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas  # noqa: PLC0415

    ruta.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(ruta))
    for texto in paginas:
        c.drawString(40, 700, texto)
        c.showPage()
    c.save()
    assert reportlab
    return ruta


# Así viene de verdad el 680010079201_HUS311736_FACTURA.pdf del paquete 31068:
# 19 páginas con los cuatro renglones del folio ya pegados.
PAGINAS_FACTURA_REAL = (
    ["FACTURA ELECTRONICA DE VENTA HUS311736 CUFE 67811444d5d4"] * 7
    + ["DETALLADO FACTURA ELECTRONICA HUS311736"] * 2
    + ["Representacion Grafica Codigo Unico de Factura - CUFE :"]
    + ["Datos Totales Total Bruto Factura"] * 8
    + ["NOTA Credito N 253292 GLOSA VIG ANTERIOR"]
)


def test_ve_los_renglones_que_la_factura_ya_trae_pegados(tmp_path):
    ruta = _pdf_con_texto(tmp_path / "680010079201_HUS311736_FACTURA.pdf", PAGINAS_FACTURA_REAL)
    assert org.renglones_que_trae(ruta) == {"DETALLADO", "DIAN", "NOTAS"}


def test_una_factura_sola_no_trae_nada_pegado(tmp_path):
    ruta = _pdf_con_texto(
        tmp_path / "680010079201_HUS1_FACTURA.pdf",
        ["FACTURA ELECTRONICA DE VENTA HUS1"] * 3,
    )
    assert org.renglones_que_trae(ruta) == set()


def test_un_pdf_ilegible_no_afirma_nada(tmp_path):
    ruta = tmp_path / "roto.pdf"
    ruta.write_bytes(b"esto no es un PDF")
    assert org.renglones_que_trae(ruta) == set()


def test_no_le_pega_otro_detallado_a_la_factura_que_ya_lo_trae(tmp_path):
    """El defecto que se evitó: el folio subiría al ADRES con el detallado DOS
    veces, porque el ..._FACTURA.pdf del XML ya lo trae adentro."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS311736"
    _pdf(fac / "HC.pdf")
    _pdf_con_texto(fac / "680010079201_HUS311736_FACTURA.pdf", PAGINAS_FACTURA_REAL)
    (fac / "DETALLADO HUS311736.xlsx").write_bytes(b"x")

    plan = org.planificar(raiz)
    assert [d.name for d in plan[0].detallados_sin_pdf] == ["DETALLADO HUS311736.xlsx"]

    org.revisar_facturas(plan)
    assert plan[0].trae_la_factura == {"DETALLADO", "DIAN", "NOTAS"}
    # Ya no se convierte ni se agrega: el detallado está dentro de la factura.
    assert org.convertir_detallados(plan, aplicar=False) == []
    assert [s.grupo.clave for s in plan[0].soportes_factura] == ["FACTURA"]


def test_lo_que_la_factura_ya_trae_no_sale_como_faltante(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS311736"
    _pdf_con_texto(fac / "680010079201_HUS311736_FACTURA.pdf", PAGINAS_FACTURA_REAL)
    plan = org.planificar(raiz)
    # Sin mirar adentro, el bot creería que faltan dos renglones.
    assert plan[0].faltantes_factura() == ["DETALLADO", "REPRESENTACION GRAFICA DIAN"]
    assert plan[0].notas_pendientes() is True
    org.revisar_facturas(plan)
    assert plan[0].faltantes_factura() == []
    assert plan[0].notas_pendientes() is False


def test_revisar_facturas_mira_la_carpeta_del_xml_en_simulacion(tmp_path):
    """En simulación la factura todavía no se copió: hay que mirarla en su carpeta."""
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS311736" / "HC.pdf")
    xml = tmp_path / "XML"
    _pdf_con_texto(xml / "680010079201_HUS311736_FACTURA.pdf", PAGINAS_FACTURA_REAL)

    plan = org.planificar(raiz)
    indice = org.indice_facturas(xml)
    org.copiar_facturas(plan, indice, aplicar=False)
    org.revisar_facturas(plan, indice)
    assert plan[0].trae_la_factura == {"DETALLADO", "DIAN", "NOTAS"}


# ─── Lo que encontró la revisión adversarial ─────────────────────────────────


@pytest.mark.parametrize(
    "nombre",
    ["NC_263272_HUS352904.pdf", "NC 253292.pdf", "NC_311561_HUS311736.pdf"],
)
def test_las_notas_credito_con_el_nombre_del_hospital(nombre):
    """El hospital las nombra `NC_<numero>_HUS<factura>.pdf`.

    Antes caían en OTROS del folio CLÍNICO y el reporte seguía diciendo que las
    notas crédito faltaban.
    """
    grupo = org.clasificar(nombre)
    assert grupo.clave == "NOTAS" and grupo.folio == org.FOLIO_FACTURA


@pytest.mark.parametrize(
    "nombre", ["HC.pdf", "RESONANCIA.pdf", "INCAPACIDAD.pdf", "NTE-C.pdf", "CONSENTIMIENTO.pdf"]
)
def test_la_abreviatura_NC_no_dispara_falsos_positivos(nombre):
    assert org.clasificar(nombre).clave != "NOTAS"


@pytest.mark.parametrize(
    "clave", ["URGENCIAS", "TERAPIAS", "CURACIONES", "EVOLUCIONES", "PROCEDIMIENTOS", "HISTORIA"]
)
def test_el_nombre_que_escribe_el_bot_se_relee_en_el_mismo_grupo(clave):
    """`3 HISTORIA CLINICA - TERAPIAS.pdf` se releía como HISTORIA a secas.

    En la segunda corrida el soporte cambiaba de grupo, se renumeraba, y el
    folio salía con las páginas en otro orden. HISTORIA CLINICA es genérico:
    cualquier grupo más preciso le gana.
    """
    grupo = next(g for g in org.GRUPOS if g.clave == clave)
    assert org.clasificar(org.nombre_numerado(3, grupo)).clave == clave


def test_el_orden_del_folio_no_cambia_entre_corridas(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    for nombre in ("RTA_ADRES_HUS1.pdf", "EPI.pdf", "TERAPIAS.pdf", "CURACIONES.pdf", "HC.pdf"):
        _pdf(fac / nombre)
    primera = [s.grupo.clave for s in org.armar_folios(raiz, aplicar=True)[0].soportes]
    segunda = [s.grupo.clave for s in org.armar_folios(raiz, aplicar=True)[0].soportes]
    assert (
        primera
        == segunda
        == [
            "RESPUESTA",
            "EPICRISIS",
            "TERAPIAS",
            "CURACIONES",
            "HISTORIA",
        ]
    )


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        # Así lo deja `dividir_detallado_por_factura.py`: el número y nada más.
        ("HUS352904.xlsx", True),
        ("HUS0000352890.xlsx", True),
        ("DETALLADO HUS1.xlsx", True),
        # Un PDF con ese nombre no es el detallado.
        ("HUS352904.pdf", False),
        ("HUS352904 EPICRISIS.pdf", False),
    ],
)
def test_reconoce_el_detallado_que_deja_el_bot_hermano(nombre, esperado):
    assert org.es_detallado(nombre) is esperado


def test_avisa_el_soporte_que_no_entro_al_folio(tmp_path, caplog):
    """Un PDF dañado se omite y el folio SÍ se arma. No puede pasar en silencio:
    al ADRES subiría un folio al que le falta una hoja."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "RTA_ADRES_HUS1.pdf")
    (fac / "HUS1 EPICRISIS.pdf").write_bytes(b"esto no es un PDF")
    with caplog.at_level(logging.INFO, logger="unir_soportes_adres"):
        assert org.main(["--carpeta", str(raiz), "--folio", "--aplicar"]) == 0
    salida = caplog.text
    assert "NO entraron al folio" in salida
    # Con el nombre que TIENE ahora en la carpeta, que es el que el auditor va
    # a buscar: para entonces ya quedó numerado.
    assert "2 EPICRISIS.pdf" in salida


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("680010079201_HUS352904_EPICRIS", "680010079201"),
        ("680010079201_HUS352904_FACTURA", "680010079201"),
        # Una FECHA o un número de ingreso NO son el NIT.
        ("20240913_HUS352904 EVOLUCION", ""),
        ("13092024 HUS352904 HC", ""),
        ("190029_HUS352904_ingreso", ""),
        # Ni el NIT de otra factura.
        ("680010079201_HUS999999_EPICRIS", ""),
    ],
)
def test_una_fecha_no_puede_pasar_por_NIT(nombre, esperado):
    """Con «números al principio y esta factura después» bastaba, y el folio
    salía llamándose `20240913_HUS352904_EPICRIS.pdf`."""
    assert org.prefijo_del_nombre(nombre, "HUS352904") == esperado


def test_en_el_mapa_de_nombres_tambien_gana_la_palabra_mas_larga():
    """El resultado no puede depender del orden en que estén las líneas del JSON."""
    for mapa in (
        {"TAC": "AYUDAS", "TAC DE TORAX": "OTROS"},
        {"TAC DE TORAX": "OTROS", "TAC": "AYUDAS"},
    ):
        assert org.clasificar("HUS1 TAC DE TORAX.pdf", mapa).clave == "OTROS"


def test_el_reporte_abierto_en_excel_no_tumba_la_corrida(tmp_path, monkeypatch, caplog):
    """En Windows un CSV abierto en Excel no se deja escribir. El trabajo ya
    está hecho: no se pierde por no poder dejar el listado."""
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS1" / "RTA_ADRES_HUS1.pdf")

    def _bloqueado(ruta, plan):
        raise PermissionError(13, "El archivo está abierto en otro programa")

    monkeypatch.setattr(org, "escribir_reporte", _bloqueado)
    with caplog.at_level(logging.INFO, logger="unir_soportes_adres"):
        codigo = org.main(
            [
                "--carpeta",
                str(raiz),
                "--folio",
                "--aplicar",
                "--reporte-csv",
                str(tmp_path / "r.csv"),
            ]
        )
    assert codigo == 0
    assert (raiz / "HUS1" / "HUS1_EPICRIS.pdf").exists()  # el folio sí se armó
    assert "abierto en Excel" in caplog.text


def test_renombrar_tambien_numera_el_folio_de_la_factura(tmp_path):
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "RTA_ADRES_HUS1.pdf")
    _pdf(fac / "680010079201_HUS1_FACTURA.pdf")
    assert org.main(["--carpeta", str(raiz), "--renombrar", "--aplicar"]) == 0
    assert sorted(p.name for p in fac.iterdir()) == ["1 FACTURA.pdf", "1 RESPUESTA A GLOSA.pdf"]


def test_avisa_las_banderas_que_no_hacen_nada_sin_folio(tmp_path, caplog):
    raiz = tmp_path / "G"
    _pdf(raiz / "HUS1" / "HC.pdf")
    with caplog.at_level(logging.WARNING, logger="unir_soportes_adres"):
        org.main(["--carpeta", str(raiz), "--prefijo", "900123456", "--convertir-detallado"])
    assert "--prefijo" in caplog.text and "--convertir-detallado" in caplog.text
    assert "solo funciona" in caplog.text


def test_avisa_los_archivos_que_no_son_pdf(tmp_path, caplog):
    """Una epicrisis en Word o una radiografía en JPG no entran al folio.
    No pueden desaparecer sin que el auditor se entere."""
    raiz = tmp_path / "G"
    fac = raiz / "HUS1"
    _pdf(fac / "RTA_ADRES_HUS1.pdf")
    (fac / "EPICRISIS.docx").write_bytes(b"x")
    (fac / "RADIOGRAFIA.jpg").write_bytes(b"x")
    (fac / "Thumbs.db").write_bytes(b"x")  # basura de Windows: esta no se avisa
    plan = org.planificar(raiz)[0]
    assert sorted(p.name for p in plan.no_son_pdf) == ["EPICRISIS.docx", "RADIOGRAFIA.jpg"]
    with caplog.at_level(logging.INFO, logger="unir_soportes_adres"):
        org.main(["--carpeta", str(raiz), "--folio"])
    assert "NO son PDF" in caplog.text and "EPICRISIS.docx" in caplog.text
