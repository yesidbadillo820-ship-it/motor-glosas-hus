"""Pruebas del armador/revisor del índice de soportes de COOSALUD.

Lo que se cuida: que el índice quede en el formato EXACTO que el bot del
portal sabe leer, y que la revisión previa avise de lo que dejaría facturas
en PENDIENTE_PDX (carpeta perdida, sin PDF, PDF más pesado que el tope).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tools"))

from indice_soportes_coosalud import (  # noqa: E402
    carpetas_de_facturas,
    cmd_armar,
    cmd_revisar,
    escribir_indice,
    leer_indice,
    leer_lista,
    main,
    normalizar,
)
from responder_glosas_coosalud import MAX_PDF_MB, cargar_indice  # noqa: E402


def _carpeta(base: Path, factura: str, pdf: str | None = None, mb: float = 1.0) -> Path:
    c = base / "COOSALUD" / "VANESSA" / "RIPS" / "ENV-226686-OK" / factura
    c.mkdir(parents=True, exist_ok=True)
    if pdf:
        (c / pdf).write_bytes(b"x" * int(mb * 1024 * 1024))
    return c


class TestNormalizar:
    def test_los_ceros_de_adelante_no_hacen_otra_factura(self):
        assert normalizar("HUS0000541781") == normalizar("HUS541781") == "HUS541781"

    def test_aguanta_minusculas_y_espacios(self):
        assert normalizar("  hus0000541781 ") == "HUS541781"

    def test_lo_que_no_es_factura_se_deja_igual(self):
        assert normalizar("CARPETA") == "CARPETA"


class TestArmarElIndice:
    def test_halla_las_carpetas_de_factura(self, tmp_path):
        _carpeta(tmp_path, "HUS541781")
        _carpeta(tmp_path, "HUS543423")
        hallado = carpetas_de_facturas(tmp_path)
        assert set(hallado) == {"HUS541781", "HUS543423"}

    def test_no_confunde_una_carpeta_que_solo_empieza_por_hus(self, tmp_path):
        _carpeta(tmp_path, "HUS541781")
        (tmp_path / "HUSTORIAS CLINICAS").mkdir()
        assert set(carpetas_de_facturas(tmp_path)) == {"HUS541781"}

    def test_una_raiz_que_no_existe_no_revienta(self, tmp_path):
        assert carpetas_de_facturas(tmp_path / "no_existe") == {}

    def test_no_se_mete_dentro_de_la_carpeta_de_la_factura(self, tmp_path, monkeypatch):
        """El share está en red: cada carpeta que se abre es un viaje.

        Adentro de HUS<numero> están los PDF y los RIPS, que acá no interesan.
        Si el recorrido entrara ahí, sobre el árbol del hospital serían cientos
        de miles de visitas para no usar ninguna.
        """
        c = _carpeta(tmp_path, "HUS541781", "PDX_541781.pdf", mb=0.01)
        (c / "RIPS").mkdir()
        (c / "IMG").mkdir()

        visitadas = []
        real = os.scandir

        def espia(ruta):
            visitadas.append(str(ruta))
            return real(ruta)

        monkeypatch.setattr(os, "scandir", espia)
        assert set(carpetas_de_facturas(tmp_path)) == {"HUS541781"}
        assert not any(str(c) in v for v in visitadas), (
            f"se metió dentro de la carpeta de la factura: {visitadas}"
        )

    def test_una_carpeta_sin_permiso_no_tumba_el_recorrido(self, tmp_path, monkeypatch):
        _carpeta(tmp_path, "HUS541781")
        real = os.scandir

        def a_veces_falla(ruta):
            if "ENV-" in str(ruta):
                raise PermissionError("sin permiso")
            return real(ruta)

        monkeypatch.setattr(os, "scandir", a_veces_falla)
        # La rama que falla se salta; el recorrido sigue y no revienta.
        assert carpetas_de_facturas(tmp_path) == {}

    def test_halla_la_factura_aunque_cuelgue_hondo(self, tmp_path):
        hondo = tmp_path / "COOSALUD" / "VANESSA" / "RIPS" / "ENV-1" / "SUB" / "OTRA"
        (hondo / "HUS541781").mkdir(parents=True)
        assert set(carpetas_de_facturas(tmp_path)) == {"HUS541781"}

    def test_el_indice_se_relee_igual(self, tmp_path):
        c = _carpeta(tmp_path, "HUS541781")
        salida = tmp_path / "idx.txt"
        escribir_indice({"HUS541781": c}, salida)
        assert leer_indice(salida) == {"HUS541781": c}

    def test_el_formato_es_EL_QUE_EL_BOT_LEE(self, tmp_path):
        """El bot hace Path(linea) sobre la línea entera.

        Con rutas de Windows (las de verdad), lo que escribimos tiene que
        caerle al bot como una ruta ABSOLUTA. Si alguien le pusiera un
        prefijo tipo `HUS541781<tab>`, el bot armaría una ruta relativa
        inexistente y la factura quedaría en PENDIENTE_PDX sin decir por qué.
        """
        win = Path(r"Y:\8. AGOSTO 2026 - SOPORTES RADICACION\COOSALUD\HUS541781")
        salida = tmp_path / "idx.txt"
        escribir_indice({"HUS541781": win}, salida)
        leido = cargar_indice(salida)
        assert set(leido) == {"HUS541781"}
        assert str(leido["HUS541781"]) == str(win)
        assert "\t" not in salida.read_text(encoding="utf-8")

    def test_el_indice_viejo_con_tabulacion_igual_se_entiende(self, tmp_path):
        """Para no perder lo ya indexado a mano al correr --actualizar."""
        salida = tmp_path / "idx.txt"
        salida.write_text(
            "HUS500258\tY:\\7. JULIO 2026 - SOPORTES RADICACION\\HUS500258\n",
            encoding="utf-8",
        )
        assert set(leer_indice(salida)) == {"HUS500258"}

    def test_actualizar_conserva_los_meses_viejos(self, tmp_path):
        vieja = _carpeta(tmp_path / "julio", "HUS500258")
        salida = tmp_path / "idx.txt"
        escribir_indice({"HUS500258": vieja}, salida)
        agosto = tmp_path / "agosto"
        _carpeta(agosto, "HUS541781")
        args = type("A", (), {"raiz": [str(agosto)], "salida": str(salida), "actualizar": True})()
        assert cmd_armar(args) == 0
        assert set(leer_indice(salida)) == {"HUS500258", "HUS541781"}

    def test_sin_actualizar_se_rehace_desde_cero(self, tmp_path):
        salida = tmp_path / "idx.txt"
        escribir_indice({"HUS500258": tmp_path / "vieja" / "HUS500258"}, salida)
        agosto = tmp_path / "agosto"
        _carpeta(agosto, "HUS541781")
        args = type("A", (), {"raiz": [str(agosto)], "salida": str(salida), "actualizar": False})()
        assert cmd_armar(args) == 0
        assert set(leer_indice(salida)) == {"HUS541781"}

    def test_si_no_halla_nada_no_borra_el_indice_bueno(self, tmp_path):
        salida = tmp_path / "idx.txt"
        c = _carpeta(tmp_path / "julio", "HUS500258")
        escribir_indice({"HUS500258": c}, salida)
        vacia = tmp_path / "vacia"
        vacia.mkdir()
        args = type("A", (), {"raiz": [str(vacia)], "salida": str(salida), "actualizar": False})()
        assert cmd_armar(args) == 1
        assert set(leer_indice(salida)) == {"HUS500258"}


class TestLeerLaLista:
    def test_saca_las_facturas_aunque_vengan_con_basura_alrededor(self, tmp_path):
        p = tmp_path / "l.txt"
        p.write_text("# pendientes\nHUS0000541781\nHUS543423 (soportes)\n\n", encoding="utf-8")
        assert leer_lista(p) == ["HUS541781", "HUS543423"]

    def test_no_repite_la_misma_factura(self, tmp_path):
        p = tmp_path / "l.txt"
        p.write_text("HUS541781\nHUS0000541781\n", encoding="utf-8")
        assert leer_lista(p) == ["HUS541781"]

    def test_una_lista_vacia_no_revienta(self, tmp_path):
        p = tmp_path / "l.txt"
        p.write_text("", encoding="utf-8")
        assert leer_lista(p) == []


class TestRevisarAntesDeCorrerElPortal:
    def _args(self, idx, lista):
        return type("A", (), {"indice": str(idx), "lista": str(lista)})()

    def _prep(self, tmp_path, mapa, facturas):
        idx = tmp_path / "idx.txt"
        escribir_indice(mapa, idx)
        lista = tmp_path / "l.txt"
        lista.write_text("\n".join(facturas), encoding="utf-8")
        return idx, lista

    def test_con_todo_en_su_sitio_da_via_libre(self, tmp_path, capsys):
        c = _carpeta(tmp_path, "HUS541781", "PDX_541781.pdf", mb=2)
        idx, lista = self._prep(tmp_path, {"HUS541781": c}, ["HUS541781"])
        assert cmd_revisar(self._args(idx, lista)) == 0
        assert "Puede correr el portal" in capsys.readouterr().out

    def test_avisa_de_la_que_no_esta_en_el_indice(self, tmp_path, capsys):
        idx, lista = self._prep(tmp_path, {}, ["HUS541781"])
        assert cmd_revisar(self._args(idx, lista)) == 1
        assert "NO está en el índice" in capsys.readouterr().out

    def test_avisa_cuando_la_carpeta_ya_no_esta(self, tmp_path, capsys):
        idx, lista = self._prep(
            tmp_path, {"HUS541781": tmp_path / "se_borro" / "HUS541781"}, ["HUS541781"]
        )
        assert cmd_revisar(self._args(idx, lista)) == 1
        assert "no se alcanza" in capsys.readouterr().out

    def test_avisa_cuando_la_carpeta_no_tiene_pdf(self, tmp_path, capsys):
        c = _carpeta(tmp_path, "HUS541781")
        idx, lista = self._prep(tmp_path, {"HUS541781": c}, ["HUS541781"])
        assert cmd_revisar(self._args(idx, lista)) == 1
        assert "sin PDX/HAM/PDE" in capsys.readouterr().out

    def test_avisa_del_pdf_que_no_cabe_en_el_portal(self, tmp_path, capsys):
        c = _carpeta(tmp_path, "HUS541781", "PDX_541781.pdf", mb=MAX_PDF_MB + 1.5)
        idx, lista = self._prep(tmp_path, {"HUS541781": c}, ["HUS541781"])
        assert cmd_revisar(self._args(idx, lista)) == 1
        salida = capsys.readouterr().out
        assert "pesa" in salida and str(MAX_PDF_MB) in salida

    def test_dice_cuando_va_un_ham_en_vez_del_pdx(self, tmp_path, capsys):
        c = _carpeta(tmp_path, "HUS541781", "HAM_541781.pdf", mb=1)
        idx, lista = self._prep(tmp_path, {"HUS541781": c}, ["HUS541781"])
        assert cmd_revisar(self._args(idx, lista)) == 0
        assert "no había PDX" in capsys.readouterr().out

    def test_la_factura_con_ceros_cruza_igual(self, tmp_path, capsys):
        c = _carpeta(tmp_path, "HUS541781", "PDX_541781.pdf", mb=1)
        idx, lista = self._prep(tmp_path, {"HUS541781": c}, ["HUS0000541781"])
        assert cmd_revisar(self._args(idx, lista)) == 0


class TestLaLineaDeComandos:
    def test_sin_subcomando_no_arranca(self):
        with pytest.raises(SystemExit):
            main([])
