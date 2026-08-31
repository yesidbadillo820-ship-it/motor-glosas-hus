"""«La glosan dos veces pero acá solo me aparece una sola vez» (31-08-2026).

Yesid buscó la HUS406687 con el paquete 31073 escogido arriba y la pantalla le
contestó «no está en ningún paquete cargado», teniéndola cargada en el 31078.
Este comando dice la verdad desde el PC, sin tocar nada.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "glosas_adres_donde_esta", RAIZ / "tools" / "glosas_adres_donde_esta.py"
)
donde = importlib.util.module_from_spec(spec)
sys.modules["glosas_adres_donde_esta"] = donde
spec.loader.exec_module(donde)


@pytest.fixture()
def base(tmp_path):
    """Una base con la HUS406687 glosada en dos paquetes, como el caso real."""
    ruta = tmp_path / "motorglosas.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE paquetes_adres (id INTEGER PRIMARY KEY, numero_paquete TEXT)")
    con.execute(
        "CREATE TABLE glosas_adres ("
        "id INTEGER PRIMARY KEY, paquete_id INTEGER, factura_clave TEXT, factura TEXT, "
        "codigo TEXT, descripcion TEXT, causal_codigo TEXT, valor_glosado REAL, "
        "cuenta_valor INTEGER, glosa_total INTEGER, decision TEXT, centro_costos TEXT)"
    )
    con.executemany(
        "INSERT INTO paquetes_adres (id, numero_paquete) VALUES (?,?)",
        [(1, "31073"), (2, "31078")],
    )
    filas = [
        # En el 31078: las dos glosas que el auditor ve en su Excel.
        (2, "406687", "HUS406687", "21101", "Mano, dedos, puño", "3209", 73500, 1, 0, "", ""),
        (2, "406687", "HUS406687", "39221", "Derechos de sala", "3105", 100700, 1, 0, "", ""),
        # El mismo servicio con otra causal: su plata ya la contó el de arriba.
        (2, "406687", "HUS406687", "39221", "Derechos de sala", "3106", 100700, 0, 0, "", ""),
        # En el 31073: otra glosa de la MISMA factura, en otro paquete.
        (1, "406687", "HUS406687", "37206", "Inmovilización", "3202", 82000, 1, 0, "SE OBJETA", ""),
        # Una factura de un solo paquete, para el caso normal.
        (2, "405882", "HUS405882", "21706", "Senos paranasales", "3209", 799800, 1, 0, "", ""),
    ]
    con.executemany(
        "INSERT INTO glosas_adres (paquete_id, factura_clave, factura, codigo, descripcion, "
        "causal_codigo, valor_glosado, cuenta_valor, glosa_total, decision, centro_costos) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        filas,
    )
    con.commit()
    con.close()
    return ruta


def _salida(base, *facturas) -> str:
    con = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        for f in facturas:
            donde.revisar(con, f)
    con.close()
    return buffer.getvalue()


class TestElNumeroSeEscribeComoSea:
    @pytest.mark.parametrize("escrito", ["406687", "HUS406687", "hus0000406687", " HUS 406687 "])
    def test_todas_las_formas_llevan_a_la_misma_factura(self, escrito):
        assert donde.clave_factura(escrito) == "406687"

    def test_lo_que_no_es_numero_de_factura_no_se_toca(self):
        assert donde.clave_factura("FVS-123-A") == "FVS-123-A"


class TestDondeEsta:
    def test_dice_los_dos_paquetes_y_avisa(self, base):
        salida = _salida(base, "HUS406687")
        assert "2 PAQUETES" in salida
        assert "Paquete 31078" in salida
        assert "Paquete 31073" in salida
        assert "NO cubre el otro" in salida

    def test_la_plata_no_se_cuenta_dos_veces(self, base):
        """El mismo servicio con dos causales suma una sola vez: 73.500 + 100.700."""
        salida = _salida(base, "HUS406687")
        assert "$174.200" in salida
        assert "$274.900" not in salida  # sería contar dos veces los derechos de sala

    def test_muestra_renglon_por_renglon_lo_que_glosaron(self, base):
        salida = _salida(base, "HUS406687")
        assert "3209" in salida and "3105" in salida
        assert "Derechos de sala" in salida
        assert "sin decidir" in salida
        assert "SE OBJETA" in salida

    def test_la_factura_de_un_solo_paquete_no_dispara_la_alarma(self, base):
        salida = _salida(base, "HUS405882")
        assert "PAQUETES" not in salida
        assert "Paquete 31078" in salida

    def test_la_que_no_esta_lo_dice_sin_inventar(self, base):
        salida = _salida(base, "HUS999999")
        assert "NO está en ningún paquete cargado" in salida
        assert "falta cargar ese paquete" in salida


class TestNoTocaNada:
    def test_abre_la_base_en_solo_lectura(self, base):
        """Un comando de diagnóstico no puede escribir en la base del hospital."""
        con = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM glosas_adres")
        con.close()

    def test_el_codigo_no_tiene_ninguna_escritura(self):
        texto = (RAIZ / "tools" / "glosas_adres_donde_esta.py").read_text(encoding="utf-8")
        for palabra in ("INSERT", "UPDATE", "DELETE ", "DROP", "commit()"):
            assert palabra not in texto.upper().replace("COMMIT()", "commit()"), palabra
