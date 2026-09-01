"""«Dice que no tiene facturación electrónica y sí la tiene».

26-08-2026. Tres facturas (HUS544942, HUS542599, HUS544936) salían con
«Correo F.E.: NO» teniéndola. Sin correo el sistema NO deja radicar: el auditor
queda obligado a devolver una factura que estaba bien.

El dato sale de cruzar la factura con el Formato de Facturación Electrónica. Si
el número viene escrito distinto —«544942» en vez de «HUS0000544942»— el cruce
falla en silencio.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "preauditoria_revisar_fe", RAIZ / "tools" / "preauditoria_revisar_fe.py"
)
fe = importlib.util.module_from_spec(spec)
sys.modules["preauditoria_revisar_fe"] = fe
spec.loader.exec_module(fe)


class TestElNumeroSeEscribeSiempreIgual:
    """La misma regla que ahora aplican las dos fuentes al cargarse."""

    @pytest.mark.parametrize(
        "escrito", ["544942", "HUS544942", "hus0000544942", " HUS 544942 ", "HUS0000544942"]
    )
    def test_todas_las_formas_llevan_al_mismo_numero(self, escrito):
        assert fe.canonizar(escrito) == "HUS0000544942"

    def test_lo_que_no_es_un_numero_de_factura_no_se_toca(self):
        """No se inventa: un código con letras se deja como está."""
        assert fe.canonizar("FVS-123-A") == "FVS-123-A"
        assert fe.canonizar("") == ""

    def test_el_servicio_usa_exactamente_la_misma_regla(self):
        from app.services.preauditoria_service import canonizar_factura

        for escrito in ("544942", "HUS544942", "HUS0000544942", "FVS-123-A"):
            assert canonizar_factura(escrito) == fe.canonizar(escrito)


@pytest.fixture()
def db(tmp_path):
    from sqlalchemy import create_engine

    from app.models.db import Base

    ruta = tmp_path / "motorglosas.db"
    engine = create_engine(f"sqlite:///{ruta}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return str(ruta)


def _fe(ruta, factura, archivo="DGReport.xlsx"):
    con = sqlite3.connect(ruta)
    con.execute(
        "INSERT INTO preaud_fuente_dgreport (factura, correo_fe, fuente_archivo) VALUES (?,'SI',?)",
        (factura, archivo),
    )
    con.commit()
    con.close()


def _correr(capsys, args, ruta):
    sys.argv = ["preauditoria_revisar_fe.py"] + args + [ruta]
    assert fe.main() == 0
    return capsys.readouterr().out


class TestDiceCualDeLosDosProblemasEs:
    def test_cuando_si_esta_lo_confirma(self, capsys, db):
        _fe(db, "HUS0000544942")
        salida = _correr(capsys, ["HUS544942"], db)
        assert "SÍ está en el Formato F.E." in salida

    def test_cuando_esta_escrita_distinta_lo_dice_y_dice_qué_hacer(self, capsys, db):
        """Este es el caso silencioso: la factura está, pero no cruza."""
        _fe(db, "544942")
        salida = _correr(capsys, ["HUS0000544942"], db)
        assert "con el número escrito DISTINTO" in salida
        assert "guardada como «544942»" in salida
        assert "suba otra vez el Formato F.E." in salida

    def test_cuando_no_esta_manda_a_subir_el_archivo(self, capsys, db):
        salida = _correr(capsys, ["HUS544936"], db)
        assert "NO aparece en el Formato F.E." in salida
        assert "baje del DGH el Formato F.E. actualizado" in salida

    def test_revisa_varias_de_una_vez(self, capsys, db):
        _fe(db, "HUS0000544942")
        salida = _correr(capsys, ["HUS544942", "HUS542599", "HUS544936"], db)
        for numero in ("HUS0000544942", "HUS0000542599", "HUS0000544936"):
            assert numero in salida

    def test_no_cambia_nada(self, capsys, db):
        _fe(db, "HUS0000544942")
        antes = sqlite3.connect(db).execute("SELECT * FROM preaud_fuente_dgreport").fetchall()
        _correr(capsys, ["HUS544942"], db)
        assert (
            sqlite3.connect(db).execute("SELECT * FROM preaud_fuente_dgreport").fetchall() == antes
        )

    def test_base_inexistente_avisa_sin_reventar(self, capsys, tmp_path):
        sys.argv = ["x", "HUS544942", str(tmp_path / "no.db")]
        assert fe.main() == 1
        assert "No se encontró la base de datos" in capsys.readouterr().out
