"""El bot que pega la nota crédito como última hoja del folio de la factura.

Lo que se cuida aquí es lo que le costaría plata o un rechazo al hospital: que
la nota quede DE ÚLTIMA y no en la mitad, que no se pegue dos veces si el bot se
corre otra vez, que el folio original nunca se pierda, y que las facturas sin
nota (y las notas sin factura) queden reportadas en vez de pasar de largo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import anexar_notas_credito_adres as nc  # noqa: E402

pytest.importorskip("pypdf")

from pypdf import PdfReader, PdfWriter  # noqa: E402


def pdf(ruta: Path, paginas: int, ancho: float = 200.0) -> Path:
    """Crea un PDF de prueba. El ancho sirve para distinguir unas hojas de otras."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=ancho, height=300)
    with ruta.open("wb") as f:
        escritor.write(f)
    return ruta


def anchos(ruta: Path) -> list[int]:
    return [round(float(p.mediabox.width)) for p in PdfReader(str(ruta)).pages]


@pytest.fixture
def paquete(tmp_path: Path):
    """Una carpeta de notas y una de radicación, con una factura emparejada."""
    notas = tmp_path / "NC ADRES"
    radicacion = tmp_path / "GI-XX-XXXXX-2026"
    pdf(notas / "HUS354116.pdf", 1, ancho=999)
    pdf(radicacion / "680010079201_HUS354116_FACTURA.pdf", 3, ancho=100)
    pdf(radicacion / "680010079201_HUS354116_EPICRIS.pdf", 2, ancho=100)
    return notas, radicacion


class TestComoEmparejaLaFacturaConSuNota:
    def test_los_ceros_de_mas_no_estorban(self):
        assert nc.numero_de_factura("680010079201_HUS0000354116_FACTURA.pdf") == "HUS354116"
        assert nc.numero_de_factura("HUS354116.pdf") == "HUS354116"

    def test_un_nombre_sin_factura_no_inventa_una(self):
        assert nc.numero_de_factura("resumen del paquete.pdf") is None

    def test_solo_toma_los_folios_de_la_factura_no_los_clinicos(self, paquete):
        _, radicacion = paquete
        folios = nc.facturas_de_la_radicacion(radicacion)
        assert list(folios) == ["HUS354116"]
        assert folios["HUS354116"].name.endswith("_FACTURA.pdf")


class TestQueLaNotaQuedeDeUltima:
    def test_simulacro_no_toca_nada(self, paquete):
        notas, radicacion = paquete
        folio = radicacion / "680010079201_HUS354116_FACTURA.pdf"
        antes = folio.read_bytes()

        [r] = [x for x in nc.anexar(notas, radicacion) if x.factura == "HUS354116"]

        assert folio.read_bytes() == antes
        assert not (radicacion / nc.RESPALDO).exists()
        assert r.hojas_antes == 3 and r.hojas_nota == 1 and r.hojas_despues == 4
        assert r.estado.startswith("SIMULACRO")

    def test_al_aplicar_la_nota_queda_en_la_ultima_hoja(self, paquete):
        notas, radicacion = paquete
        folio = radicacion / "680010079201_HUS354116_FACTURA.pdf"

        [r] = [x for x in nc.anexar(notas, radicacion, aplicar=True) if x.factura == "HUS354116"]

        assert anchos(folio) == [100, 100, 100, 999]
        assert r.hojas_despues == 4 and r.cuadra
        assert r.estado == "nota pegada de última hoja"

    def test_el_folio_original_queda_guardado(self, paquete):
        notas, radicacion = paquete
        nc.anexar(notas, radicacion, aplicar=True)

        respaldo = radicacion / nc.RESPALDO / "680010079201_HUS354116_FACTURA.pdf"
        assert respaldo.exists()
        assert anchos(respaldo) == [100, 100, 100]

    def test_el_folio_clinico_no_se_toca(self, paquete):
        notas, radicacion = paquete
        clinico = radicacion / "680010079201_HUS354116_EPICRIS.pdf"
        antes = clinico.read_bytes()

        nc.anexar(notas, radicacion, aplicar=True)

        assert clinico.read_bytes() == antes


class TestQueNoSePegueDosVeces:
    def test_correrlo_otra_vez_no_repite_la_nota(self, paquete):
        notas, radicacion = paquete
        folio = radicacion / "680010079201_HUS354116_FACTURA.pdf"
        nc.anexar(notas, radicacion, aplicar=True)

        [r] = [x for x in nc.anexar(notas, radicacion, aplicar=True) if x.factura == "HUS354116"]

        assert anchos(folio) == [100, 100, 100, 999]
        assert r.estado == "ya tenía la nota pegada, no se toca"

    def test_rehacer_parte_del_folio_guardado_y_no_acumula(self, paquete):
        notas, radicacion = paquete
        folio = radicacion / "680010079201_HUS354116_FACTURA.pdf"
        nc.anexar(notas, radicacion, aplicar=True)
        pdf(notas / "HUS354116.pdf", 2, ancho=777)  # llegó una nota corregida

        [r] = [
            x
            for x in nc.anexar(notas, radicacion, aplicar=True, rehacer=True)
            if x.factura == "HUS354116"
        ]

        assert anchos(folio) == [100, 100, 100, 777, 777]
        assert r.hojas_antes == 3 and r.cuadra


class TestLoQueNoCuadraSeReportaNoSeAdivina:
    def test_una_nota_sin_factura_no_se_pega_en_otra(self, tmp_path):
        notas, radicacion = tmp_path / "NC", tmp_path / "GI"
        pdf(notas / "HUS999999.pdf", 1)
        pdf(radicacion / "680010079201_HUS354116_FACTURA.pdf", 3, ancho=100)

        resultados = nc.anexar(notas, radicacion, aplicar=True)

        huerfana = next(r for r in resultados if r.factura == "HUS999999")
        assert huerfana.estado == "la factura no está en la carpeta de radicación"
        assert anchos(radicacion / "680010079201_HUS354116_FACTURA.pdf") == [100, 100, 100]

    def test_las_facturas_sin_nota_salen_en_el_informe(self, paquete):
        notas, radicacion = paquete
        pdf(radicacion / "680010079201_HUS380112_FACTURA.pdf", 2)

        resultados = nc.anexar(notas, radicacion, aplicar=True)

        sola = next(r for r in resultados if r.factura == "HUS380112")
        assert sola.estado == "sin nota crédito en la carpeta"

    def test_un_pdf_ilegible_no_borra_la_factura(self, paquete):
        notas, radicacion = paquete
        (notas / "HUS354116.pdf").write_bytes(b"esto no es un PDF")
        folio = radicacion / "680010079201_HUS354116_FACTURA.pdf"

        [r] = [x for x in nc.anexar(notas, radicacion, aplicar=True) if x.factura == "HUS354116"]

        assert anchos(folio) == [100, 100, 100]
        assert r.estado.startswith("no se pudo leer")

    def test_dos_notas_para_la_misma_factura_se_avisan(self, paquete):
        notas, _ = paquete
        pdf(notas / "NC HUS0000354116.pdf", 1)

        repetidas = nc.notas_repetidas(notas)

        assert [f for f, _ in repetidas] == ["HUS354116"]


class TestElInforme:
    def test_trae_una_fila_por_factura_con_el_conteo_de_hojas(self, paquete, tmp_path):
        notas, radicacion = paquete
        resultados = nc.anexar(notas, radicacion, aplicar=True)

        destino = nc.escribir_informe(resultados, tmp_path / nc.INFORME)

        lineas = destino.read_text(encoding="utf-8-sig").strip().splitlines()
        assert lineas[0].startswith("FACTURA;NOTA CREDITO;FOLIO DE LA FACTURA")
        assert "HUS354116" in lineas[1]
        assert ";3;1;4;" in lineas[1]

    def test_el_bot_completo_deja_el_informe_y_no_revienta(self, paquete, capsys):
        notas, radicacion = paquete

        assert nc.main([str(notas), str(radicacion), "--aplicar"]) == 0

        assert (notas / nc.INFORME).exists()
        assert "notas pegadas" in capsys.readouterr().out

    def test_avisa_cuando_la_carpeta_no_existe(self, tmp_path, capsys):
        assert nc.main([str(tmp_path / "no hay"), str(tmp_path)]) == 2
        assert "No existe la carpeta" in capsys.readouterr().out


def test_motor_embebido_en_cmd_identico_al_py():
    """La copia embebida tras #PYSTART# en el .cmd debe ser el .py exacto.

    Es el código que ejecuta el auditor (copia SOLO el .cmd al servidor): si
    alguien edita el .py y olvida regenerar el .cmd, este test lo detecta.
    """
    raiz = Path(__file__).resolve().parents[2]
    lineas = (raiz / "tools" / "ANEXAR_NOTAS_CREDITO.cmd").read_text(encoding="utf-8").splitlines()
    marcador = "#PY" + "START#"  # partido para no autodetectarse
    idx = next(i for i, ln in enumerate(lineas) if marcador in ln)
    embebido = "\n".join(lineas[idx + 1 :]).strip("\n")
    fuente = (
        (raiz / "tools" / "anexar_notas_credito_adres.py")
        .read_text(encoding="utf-8")
        .replace("\r\n", "\n")
        .strip("\n")
    )
    assert embebido == fuente, (
        "La copia embebida en tools/ANEXAR_NOTAS_CREDITO.cmd difiere de "
        "tools/anexar_notas_credito_adres.py. Regenera el .cmd."
    )
