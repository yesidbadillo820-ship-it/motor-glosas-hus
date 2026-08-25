"""Tests del bot que mete cada soporte en la carpeta de su factura.

Mover archivos NO se deshace, así que lo que más se prueba acá es lo que el bot
**no** debe hacer: no pisar nada, no tocar lo que ya está en su carpeta, y no
mover nada mientras no se lo pidan a propósito.

Los nombres de los archivos son los reales de la carpeta CAROLINA del
paquete 31068.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import organizar_soportes_por_factura as org  # noqa: E402


def crear(carpeta: Path, *nombres: str) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    for n in nombres:
        (carpeta / n).write_text(f"contenido de {n}", encoding="utf-8")
    return carpeta


class TestSacarLaFacturaDelNombre:
    @pytest.mark.parametrize(
        "nombre,esperado",
        [
            ("HUS392861-MEDICAMENTOS.pdf", "HUS392861"),
            ("HUS400387 ANGIOTOMOGRAFIA.pdf", "HUS400387"),
            ("HUS376265--procedimiento.pdf", "HUS376265"),
            ("HUS396998_FACTURA DE COMPRA.pdf", "HUS396998"),
            ("HUS382278- INTERCONSULTAS, FOLIO 17,34,126.pdf", "HUS382278"),
            ("HUS390610_HABILITACION REPS - copia.pdf", "HUS390610"),
            ("hus383283 gasas parafinadas.pdf", "HUS383283"),  # en minúscula
            ("HUS 0000352890 recibido.pdf", "HUS352890"),  # con espacio y ceros
        ],
    )
    def test_los_nombres_reales_del_paquete(self, nombre, esperado):
        assert org.factura_del_nombre(nombre) == esperado

    @pytest.mark.parametrize(
        "nombre",
        [
            "RESUMEN DEL LOTE.pdf",
            "acta de conciliación.pdf",
            "HUSABC-algo.pdf",  # HUS sin número
            "",
        ],
    )
    def test_lo_que_no_trae_factura(self, nombre):
        assert org.factura_del_nombre(nombre) == ""


class TestSimulacion:
    def test_por_defecto_no_mueve_nada(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "HUS392861-MEDICAMENTOS.pdf")
        planes = org.organizar(carpeta)
        assert planes[0].estado == org.ESTADO_MOVIDO  # lo que HARÍA
        assert (carpeta / "HUS392861-MEDICAMENTOS.pdf").exists()  # sigue ahí
        assert not (carpeta / "HUS392861").exists()  # no creó la carpeta

    def test_avisa_qué_carpetas_crearía(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "HUS392861-MEDICAMENTOS.pdf")
        (carpeta / "HUS383781").mkdir()
        crear(carpeta, "HUS383781- INTERCONSULTA.pdf")
        planes = {p.archivo: p for p in org.organizar(carpeta)}
        assert planes["HUS392861-MEDICAMENTOS.pdf"].carpeta_creada is True
        assert planes["HUS383781- INTERCONSULTA.pdf"].carpeta_creada is False

    def test_dos_archivos_de_la_misma_factura_cuentan_una_sola_carpeta(self, tmp_path):
        carpeta = crear(
            tmp_path / "CAROLINA",
            "HUS396998_FACTURA DE COMPRA.pdf",
            "HUS396998-PROCEDIMIENTO.pdf",
        )
        planes = org.organizar(carpeta)
        assert sum(1 for p in planes if p.carpeta_creada) == 1


class TestMoverDeVerdad:
    def test_mete_cada_uno_en_su_carpeta(self, tmp_path):
        carpeta = crear(
            tmp_path / "CAROLINA",
            "HUS392861-MEDICAMENTOS.pdf",
            "HUS400387 ANGIOTOMOGRAFIA.pdf",
        )
        org.organizar(carpeta, aplicar=True)
        assert (carpeta / "HUS392861" / "HUS392861-MEDICAMENTOS.pdf").exists()
        assert (carpeta / "HUS400387" / "HUS400387 ANGIOTOMOGRAFIA.pdf").exists()
        assert not (carpeta / "HUS392861-MEDICAMENTOS.pdf").exists()

    def test_crea_la_carpeta_que_falta_y_usa_la_que_ya_existe(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "HUS383781- INTERCONSULTA.pdf")
        (carpeta / "HUS383781").mkdir()
        crear(carpeta, "HUS392861-MEDICAMENTOS.pdf")
        org.organizar(carpeta, aplicar=True)
        assert (carpeta / "HUS383781" / "HUS383781- INTERCONSULTA.pdf").exists()
        assert (carpeta / "HUS392861" / "HUS392861-MEDICAMENTOS.pdf").exists()

    def test_varios_soportes_de_la_misma_factura_van_juntos(self, tmp_path):
        carpeta = crear(
            tmp_path / "CAROLINA",
            "HUS383283 GASAS PARAFINADAS.pdf",
            "HUS383283 PROCEDIMIENTO QCO.pdf",
            "HUS383283-INSUMOS.pdf",
            "HUS383283-PROCEDIMIENTO QX.pdf",
        )
        org.organizar(carpeta, aplicar=True)
        assert len(list((carpeta / "HUS383283").glob("*.pdf"))) == 4

    def test_el_contenido_del_archivo_no_cambia(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "HUS392861-MEDICAMENTOS.pdf")
        antes = (carpeta / "HUS392861-MEDICAMENTOS.pdf").read_text(encoding="utf-8")
        org.organizar(carpeta, aplicar=True)
        despues = (carpeta / "HUS392861" / "HUS392861-MEDICAMENTOS.pdf").read_text(encoding="utf-8")
        assert despues == antes


class TestNoPisarNada:
    def test_si_ya_hay_uno_con_ese_nombre_el_nuevo_se_renombra(self, tmp_path):
        """Lo que ya estaba archivado no se pierde nunca."""
        carpeta = tmp_path / "CAROLINA"
        crear(carpeta / "HUS392861", "HUS392861-MEDICAMENTOS.pdf")
        (carpeta / "HUS392861" / "HUS392861-MEDICAMENTOS.pdf").write_text("EL VIEJO", "utf-8")
        (carpeta / "HUS392861-MEDICAMENTOS.pdf").write_text("EL NUEVO", "utf-8")

        planes = org.organizar(carpeta, aplicar=True)
        assert planes[0].estado == org.ESTADO_RENOMBRADO
        viejo = carpeta / "HUS392861" / "HUS392861-MEDICAMENTOS.pdf"
        nuevo = carpeta / "HUS392861" / "HUS392861-MEDICAMENTOS (2).pdf"
        assert viejo.read_text(encoding="utf-8") == "EL VIEJO"
        assert nuevo.read_text(encoding="utf-8") == "EL NUEVO"
        assert "no pisarlo" in planes[0].observacion

    def test_un_tercero_con_el_mismo_nombre_tampoco_pisa(self, tmp_path):
        carpeta = tmp_path / "CAROLINA"
        destino = carpeta / "HUS1"
        destino.mkdir(parents=True)
        (destino / "HUS1.pdf").write_text("uno", "utf-8")
        (destino / "HUS1 (2).pdf").write_text("dos", "utf-8")
        (carpeta / "HUS1.pdf").write_text("tres", "utf-8")
        org.organizar(carpeta, aplicar=True)
        assert (destino / "HUS1 (3).pdf").read_text(encoding="utf-8") == "tres"
        assert (destino / "HUS1.pdf").read_text(encoding="utf-8") == "uno"


class TestLoQueNoSeToca:
    def test_lo_que_ya_esta_dentro_de_una_carpeta_se_queda_quieto(self, tmp_path):
        carpeta = tmp_path / "CAROLINA"
        crear(carpeta / "HUS352904", "HUS352904-algo.pdf", "otro archivo.pdf")
        carpeta.mkdir(exist_ok=True)
        org.organizar(carpeta, aplicar=True)
        assert (carpeta / "HUS352904" / "HUS352904-algo.pdf").exists()
        assert (carpeta / "HUS352904" / "otro archivo.pdf").exists()

    def test_los_que_no_dicen_la_factura_se_quedan(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "RESUMEN DEL LOTE.pdf", "HUS1-algo.pdf")
        planes = {p.archivo: p for p in org.organizar(carpeta, aplicar=True)}
        assert planes["RESUMEN DEL LOTE.pdf"].estado == org.ESTADO_SIN_FACTURA
        assert (carpeta / "RESUMEN DEL LOTE.pdf").exists()
        assert (carpeta / "HUS1" / "HUS1-algo.pdf").exists()

    def test_no_toca_los_que_no_son_del_patron(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "HUS1-algo.pdf", "HUS1-nota.docx")
        org.organizar(carpeta, aplicar=True)
        assert (carpeta / "HUS1-nota.docx").exists()  # no es PDF: se queda
        assert (carpeta / "HUS1" / "HUS1-algo.pdf").exists()

    def test_con_patron_todo_si_mueve_los_demas(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "HUS1-algo.pdf", "HUS1-nota.docx")
        org.organizar(carpeta, patron="*", aplicar=True)
        assert (carpeta / "HUS1" / "HUS1-nota.docx").exists()

    def test_ignora_los_temporales_de_office(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "~$HUS1-algo.pdf")
        assert org.organizar(carpeta, aplicar=True) == []
        assert (carpeta / "~$HUS1-algo.pdf").exists()


class TestReporteYCLI:
    def test_el_reporte_csv(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", "HUS392861-MEDICAMENTOS.pdf", "RESUMEN DEL LOTE.pdf")
        reporte = tmp_path / "r.csv"
        assert (
            org.main(
                [
                    "--carpeta",
                    str(carpeta),
                    "--aplicar",
                    "--reporte-csv",
                    str(reporte),
                ]
            )
            == 0
        )
        lineas = reporte.read_text(encoding="utf-8-sig").splitlines()
        assert lineas[0].startswith("ARCHIVO;FACTURA;CARPETA")
        assert any("HUS392861;HUS392861;" in ln and org.ESTADO_MOVIDO in ln for ln in lineas[1:])
        assert any(org.ESTADO_SIN_FACTURA in ln for ln in lineas[1:])

    def test_la_simulacion_lo_dice_en_pantalla(self, tmp_path, capsys):
        carpeta = crear(tmp_path / "CAROLINA", "HUS392861-MEDICAMENTOS.pdf")
        assert org.main(["--carpeta", str(carpeta)]) == 0
        texto = capsys.readouterr().out
        assert "Se moverían 1 archivo(s)" in texto
        assert "SIMULACIÓN: no se movió nada" in texto
        assert "HUS392861" in texto
        assert (carpeta / "HUS392861-MEDICAMENTOS.pdf").exists()

    def test_al_aplicar_no_dice_simulacion(self, tmp_path, capsys):
        carpeta = crear(tmp_path / "CAROLINA", "HUS392861-MEDICAMENTOS.pdf")
        assert org.main(["--carpeta", str(carpeta), "--aplicar"]) == 0
        texto = capsys.readouterr().out
        assert "Se movieron 1 archivo(s)" in texto
        assert "SIMULACIÓN" not in texto

    def test_carpeta_inexistente(self, tmp_path, caplog):
        assert org.main(["--carpeta", str(tmp_path / "no_existe")]) == 1
        assert "No existe la carpeta" in caplog.text

    def test_carpeta_sin_nada_suelto(self, tmp_path, capsys):
        carpeta = tmp_path / "CAROLINA"
        (carpeta / "HUS352904").mkdir(parents=True)
        assert org.main(["--carpeta", str(carpeta)]) == 0
        assert "No hay archivos sueltos que organizar" in capsys.readouterr().out


class TestElCasoRealDeCarolina:
    """Los nombres tal como están hoy en la carpeta del paquete 31068."""

    SUELTOS = [
        "HUS390610_HABILITACION REPS MEDICINA FISICA Y REHABILITACION - copia.pdf",
        "HUS392861-MEDICAMENTOS.pdf",
        "HUS394696-recibido del usuario.pdf",
        "HUS396396-procedimiento.pdf",
        "HUS396720-nota de procedimiento.pdf",
        "HUS396998_FACTURA DE COMPRA.pdf",
        "HUS396998-PROCEDIMIENTO.pdf",
        "HUS397503-PROCEDIMIENTO.pdf",
        "HUS400387 ANGIOTOMOGRAFIA.pdf",
        "HUS402069-FIRMAS E HC .pdf",
        "HUS376265--procedimiento.pdf",
        "HUS380267 RECIBIDO.pdf",
        "HUS381290-DESCRPCION.pdf",
        "HUS382278- INTERCONSULTAS, FOLIO 17,34,126.pdf",
        "HUS382278_ HOJA DE GASTOS.pdf",
        "HUS382278-folio inmovilizacion.pdf",
        "HUS382674-SALA.pdf",
        "HUS383283 GASAS PARAFINADAS.pdf",
        "HUS383283 PROCEDIMIENTO QCO.pdf",
        "HUS383283-INSUMOS.pdf",
        "HUS383283-PROCEDIMIENTO QX.pdf",
        "HUS383781- INTERCONSULTA.pdf",
        "HUS383781_HABILITACION REPS MEDICINA FISICA Y REHABILITACION.pdf",
        "HUS384047-CUIDADO DE LA PIEL.pdf",
        "HUS384132_HOJA DE GASTOS APOSITO.pdf",
        "HUS384132_vesell.pdf",
        "HUS384132-DESCRPCION QX.pdf",
        "HUS384132-JUNTA MEDICA FOLIO 131.pdf",
        "HUS386253-soporte consulta.pdf",
        "HUS388262-FOLIO 7 INMOVILIZACION.pdf",
        "HUS388795-INSUMOS.pdf",
        "HUS390152- SOLICITUD DE AYUDA DIAGNOSTICA.pdf",
        "HUS390152-CATETER.pdf",
        "HUS390152-prodemiento soporte.pdf",
        "HUS390378-folio 7.pdf",
    ]
    CARPETAS = [
        "HUS311371",
        "HUS352904",
        "HUS353885",
        "HUS356290",
        "HUS378538",
        "HUS379029",
        "HUS379083",
        "HUS380217",
        "HUS381256",
        "HUS382278",
        "HUS383480",
        "HUS383781",
        "HUS388262",
        "HUS388347",
        "HUS389521",
        "HUS389652",
        "HUS389901",
        "HUS390152",
        "HUS390610",
        "HUS392219",
        "HUS393393",
        "HUS393506",
        "HUS393935",
        "HUS395677",
        "HUS399029",
        "HUS402270",
        "HUS402830",
        "HUS403059",
        "HUS403194",
        "HUS403476",
        "HUS404761",
    ]

    def _carpeta(self, tmp_path):
        carpeta = crear(tmp_path / "CAROLINA", *self.SUELTOS)
        for c in self.CARPETAS:
            (carpeta / c).mkdir()
        return carpeta

    def test_los_35_sueltos_encuentran_su_factura(self, tmp_path):
        planes = org.organizar(self._carpeta(tmp_path))
        assert len(planes) == 35
        assert all(p.estado == org.ESTADO_MOVIDO for p in planes)

    def test_las_carpetas_nuevas_son_las_que_faltaban(self, tmp_path):
        planes = org.organizar(self._carpeta(tmp_path))
        nuevas = sorted({p.carpeta for p in planes if p.carpeta_creada})
        # Cinco de los sueltos ya tienen carpeta: 382278, 383781, 388262, 390152, 390610.
        assert "HUS382278" not in nuevas
        assert "HUS390610" not in nuevas
        assert "HUS392861" in nuevas and "HUS400387" in nuevas
        assert len(nuevas) == 18  # 23 facturas distintas, 5 ya tenían carpeta

    def test_al_aplicar_no_queda_ningun_pdf_suelto(self, tmp_path):
        carpeta = self._carpeta(tmp_path)
        org.organizar(carpeta, aplicar=True)
        assert list(carpeta.glob("*.pdf")) == []
        # y siguen estando los 35, cada uno adentro de una carpeta
        assert len(list(carpeta.rglob("*.pdf"))) == 35

    def test_los_cuatro_de_la_383283_quedan_juntos(self, tmp_path):
        carpeta = self._carpeta(tmp_path)
        org.organizar(carpeta, aplicar=True)
        assert len(list((carpeta / "HUS383283").glob("*.pdf"))) == 4

    def test_las_carpetas_que_ya_existian_no_se_duplican(self, tmp_path):
        carpeta = self._carpeta(tmp_path)
        antes = {p.name for p in carpeta.iterdir() if p.is_dir()}
        org.organizar(carpeta, aplicar=True)
        despues = {p.name for p in carpeta.iterdir() if p.is_dir()}
        assert antes <= despues
        assert len(despues) == len(antes) + 18


# ─── El número de factura cuando no va al principio ──────────────────────────


@pytest.mark.parametrize(
    ("nombre", "factura"),
    [
        # Lo de siempre: el número al principio.
        ("HUS392861-MEDICAMENTOS.pdf", "HUS392861"),
        ("HUS 0000352890 recibido.pdf", "HUS352890"),
        # El PDF de respuesta que arma el motor lleva su propio prefijo.
        ("RTA_ADRES_HUS311371.pdf", "HUS311371"),
        ("Reporte_Factura_HUS298253_CAROLINA.docx", "HUS298253"),
        # Los del ADRES traen el código de habilitación adelante.
        ("680010079201_HUS378523_FACOSTE.pdf", "HUS378523"),
        ("680010079201_HUS0000352890_FACTURA.xml", "HUS352890"),
        # Si empieza por un número, ese manda aunque el nombre traiga otro.
        ("HUS311371 y HUS352890 juntas.pdf", "HUS311371"),
        # Sin número al comienzo y con dos distintos adentro: no se adivina.
        ("copia de HUS311371 y HUS352890.pdf", ""),
        # El número en la mitad, sin ambigüedad: sí se resuelve. (Antes no: la
        # regla era «solo al comienzo», y dejaba fuera los RTA_ADRES_* y los
        # archivos del ADRES, que traen el código de habilitación adelante.)
        ("factura HUS352890.pdf", "HUS352890"),
        # La misma factura repetida sí se resuelve.
        ("HUS311371 - copia HUS311371.pdf", "HUS311371"),
        # Sin número, nada.
        ("REPS.pdf", ""),
    ],
)
def test_factura_del_nombre_aunque_no_este_al_principio(nombre, factura):
    assert org.factura_del_nombre(nombre) == factura


# ─── Carpetas que traen una nota detrás del número ───────────────────────────


def test_encuentra_la_carpeta_aunque_traiga_una_nota_detras(tmp_path):
    """El equipo le pone notas a las carpetas: `HUS379477_PEND. CARTA CORONEL`.

    Sin esto, el soporte de la HUS379477 no encontraría su carpeta y se crearía
    una segunda, vacía, al lado de la buena.
    """
    for nombre in ("HUS379477_PEND. CARTA CORONEL", "HUS367368 ACEPTADO", "HUS378523_MAOS"):
        (tmp_path / nombre).mkdir()
    mapa = org.carpetas_por_factura(tmp_path)
    assert set(mapa) == {"HUS379477", "HUS367368", "HUS378523"}
    assert mapa["HUS379477"].name == "HUS379477_PEND. CARTA CORONEL"


def test_el_soporte_cae_en_la_carpeta_con_nota_y_no_crea_otra(tmp_path):
    (tmp_path / "HUS379477_PEND. CARTA CORONEL").mkdir()
    (tmp_path / "RTA_ADRES_HUS379477.pdf").write_bytes(b"%PDF-1.4\n")
    org.organizar(tmp_path, aplicar=True)
    assert (tmp_path / "HUS379477_PEND. CARTA CORONEL" / "RTA_ADRES_HUS379477.pdf").exists()
    assert not (tmp_path / "HUS379477").exists()  # no se creó una carpeta gemela


def test_dos_carpetas_para_la_misma_factura_gana_la_primera_alfabetica(tmp_path):
    for nombre in ("HUS1 ZETA", "HUS1 ALFA"):
        (tmp_path / nombre).mkdir()
    assert org.carpetas_por_factura(tmp_path)["HUS1"].name == "HUS1 ALFA"


# ─── --solo-carpetas-existentes ──────────────────────────────────────────────


def _lote(tmp_path):
    """La carpeta de un gestor con UNA factura, y el lote de las tres."""
    (tmp_path / "HUS1").mkdir()
    for n in (1, 2, 3):
        (tmp_path / f"RTA_ADRES_HUS{n}.pdf").write_bytes(b"%PDF-1.4\n")
    return tmp_path


def test_solo_existentes_no_crea_carpetas_de_otros_gestores(tmp_path):
    """Al repartir un lote de 324 respuestas sobre la carpeta de un gestor, solo
    deben caer las suyas: las demás no pueden crear carpetas aquí."""
    org.organizar(_lote(tmp_path), aplicar=True, solo_existentes=True)
    assert (tmp_path / "HUS1" / "RTA_ADRES_HUS1.pdf").exists()
    assert not (tmp_path / "HUS2").exists() and not (tmp_path / "HUS3").exists()
    # Las que no eran de este gestor siguen sueltas, sin perderse.
    assert (tmp_path / "RTA_ADRES_HUS2.pdf").exists()


def test_solo_existentes_las_lista_para_que_no_pasen_calladas(tmp_path):
    planes = org.organizar(_lote(tmp_path), solo_existentes=True)
    sin_carpeta = [m for m in planes if m.estado == org.ESTADO_SIN_CARPETA]
    assert sorted(m.factura for m in sin_carpeta) == ["HUS2", "HUS3"]


def test_sin_la_opcion_sigue_creando_carpetas_como_siempre(tmp_path):
    org.organizar(_lote(tmp_path), aplicar=True)
    assert all((tmp_path / f"HUS{n}").is_dir() for n in (1, 2, 3))


def test_main_con_solo_carpetas_existentes(tmp_path):
    reporte = tmp_path / "r.csv"
    assert (
        org.main(
            [
                "--carpeta",
                str(_lote(tmp_path)),
                "--aplicar",
                "--solo-carpetas-existentes",
                "--reporte-csv",
                str(reporte),
            ]
        )
        == 0
    )
    assert (tmp_path / "HUS1" / "RTA_ADRES_HUS1.pdf").exists()
    assert "SIN CARPETA PARA ESA FACTURA" in reporte.read_text(encoding="utf-8-sig")
