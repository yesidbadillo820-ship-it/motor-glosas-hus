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
