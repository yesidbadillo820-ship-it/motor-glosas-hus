"""«La causal 4302 es tarifas» (Yesid, 02-09-2026).

En el paquete 31073 las glosas con causal 4302 quedaron «sin clasificar»
porque esa causal no salió en el paquete del que se aprendió la tabla. La
tabla ya quedó corregida, pero la clasificación se guarda al cargar: este
comando arregla lo ya cargado sin volver a subir el Excel — y estas pruebas
vigilan que solo toque lo que está en blanco.
"""

from __future__ import annotations

import importlib.util
import io
import sqlite3
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "glosas_adres_reclasificar", RAIZ / "tools" / "glosas_adres_reclasificar.py"
)
recla = importlib.util.module_from_spec(spec)
sys.modules["glosas_adres_reclasificar"] = recla
spec.loader.exec_module(recla)


@pytest.fixture()
def base(tmp_path):
    """Una base como quedó el 31073: glosas 4302 en blanco junto a trabajo hecho."""
    ruta = tmp_path / "motorglosas.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE paquetes_adres (id INTEGER PRIMARY KEY, numero_paquete TEXT)")
    con.execute(
        "CREATE TABLE glosas_adres ("
        "id INTEGER PRIMARY KEY, paquete_id INTEGER, factura_clave TEXT, "
        "causal_codigo TEXT, clasificacion TEXT, decision TEXT, "
        "sugerencia TEXT, confianza TEXT, motivo TEXT, "
        "requiere_asignacion INTEGER DEFAULT 0, area_asignada_por TEXT)"
    )
    con.execute("INSERT INTO paquetes_adres (id, numero_paquete) VALUES (1, '31073')")
    filas = [
        # (id, causal, clasificacion, decision, sugerencia, confianza, reparte, asignada_por)
        # 1: la 4302 en blanco y sin decidir — el caso que motivó el comando.
        (1, "4302", "", "", "", "", 0, ""),
        # 2: la 4302 en blanco pero YA decidida — se clasifica sin pisar lo decidido.
        (2, "4302", "", "SE OBJETA", "", "", 0, ""),
        # 3: la 4506 en blanco — esa la reparte un SUPER ADMIN, no un comando.
        (3, "4506", "", "", "", "", 1, ""),
        # 4: una ya clasificada — ni mirarla.
        (4, "3106", "SOPORTES", "", "SE SUBSANA", "REGLA", 0, ""),
        # 5: una causal que no está en la tabla — se avisa, no se inventa.
        (5, "9999", "", "", "", "", 0, ""),
    ]
    con.executemany(
        "INSERT INTO glosas_adres (id, paquete_id, factura_clave, causal_codigo, "
        "clasificacion, decision, sugerencia, confianza, motivo, requiere_asignacion, "
        "area_asignada_por) VALUES (?, 1, 'F1', ?, ?, ?, ?, ?, '', ?, ?)",
        filas,
    )
    con.commit()
    con.close()
    return ruta


def _correr(base, aplicar: bool) -> str:
    con = sqlite3.connect(base) if aplicar else sqlite3.connect(f"file:{base}?mode=ro", uri=True)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        recla.reclasificar(con, aplicar=aplicar)
    con.close()
    return buffer.getvalue()


def _glosa(base, id_) -> tuple:
    con = sqlite3.connect(base)
    fila = con.execute(
        "SELECT clasificacion, decision, sugerencia, confianza FROM glosas_adres WHERE id=?",
        (id_,),
    ).fetchone()
    con.close()
    return fila


class TestElEnsayoNoTocaNada:
    def test_dice_lo_que_haria_pero_no_escribe(self, base):
        salida = _correr(base, aplicar=False)
        assert "ENSAYO" in salida
        assert "2 glosa(s) con causal 4302 → TARIFAS" in salida
        assert "31073" in salida
        assert _glosa(base, 1) == ("", "", "", "")  # sigue igualita

    def test_avisa_la_causal_que_sigue_por_fuera_de_la_tabla(self, base):
        salida = _correr(base, aplicar=False)
        assert "9999" in salida
        assert "siguen sin clasificar" in salida


class TestAplicar:
    def test_la_4302_queda_tarifas_con_su_sugerencia(self, base):
        _correr(base, aplicar=True)
        clasif, decision, sugerencia, confianza = _glosa(base, 1)
        assert clasif == "TARIFAS"
        assert (sugerencia, confianza) == ("SE OBJETA", "REGLA")
        assert decision == ""  # decidir sigue siendo del gestor

    def test_lo_ya_decidido_se_clasifica_sin_pisarle_la_decision(self, base):
        _correr(base, aplicar=True)
        clasif, decision, sugerencia, _ = _glosa(base, 2)
        assert clasif == "TARIFAS"
        assert decision == "SE OBJETA"
        assert sugerencia == ""  # ya está decidida: no hay nada que sugerir

    def test_la_4506_sigue_esperando_al_super_admin(self, base):
        _correr(base, aplicar=True)
        assert _glosa(base, 3)[0] == ""

    def test_lo_clasificado_y_lo_desconocido_no_se_tocan(self, base):
        _correr(base, aplicar=True)
        assert _glosa(base, 4) == ("SOPORTES", "", "SE SUBSANA", "REGLA")
        assert _glosa(base, 5)[0] == ""

    def test_correrlo_dos_veces_no_dana_nada(self, base):
        _correr(base, aplicar=True)
        # La segunda pasada ya no encuentra ninguna 4302 en blanco: cero cambios.
        salida = _correr(base, aplicar=True)
        assert "causal 4302" not in salida
        assert "0 glosa(s)" in salida
        assert _glosa(base, 1)[0] == "TARIFAS"


class TestUnaBaseSana:
    def test_sin_pendientes_lo_dice_y_ya(self, base):
        _correr(base, aplicar=True)
        con = sqlite3.connect(base)
        con.execute("DELETE FROM glosas_adres WHERE id IN (3, 5)")
        con.commit()
        con.close()
        salida = _correr(base, aplicar=False)
        assert "No hay ninguna glosa sin clasificar" in salida
