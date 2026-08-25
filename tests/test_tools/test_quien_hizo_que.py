"""«¿Por qué esto quedó a nombre de otro gestor?» tiene que poder responderse.

25-08-2026. Yesid: «algunos envíos que recepciona y gestiona la gestora Vanesa
quedan como si hubieran sido del gestor Óscar». El sistema guarda el nombre en
tres momentos distintos —quién registró el oficio, quién escribió el envío y
quién auditó cada factura— y los tres salen de la sesión abierta en el
navegador, no de quién esté sentado al computador.

Este comando pone los tres datos uno al lado del otro, con fecha y hora, y NO
cambia nada.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "preauditoria_quien_hizo_que", RAIZ / "tools" / "preauditoria_quien_hizo_que.py"
)
quien = importlib.util.module_from_spec(spec)
sys.modules["preauditoria_quien_hizo_que"] = quien
spec.loader.exec_module(quien)


@pytest.fixture()
def db(tmp_path):
    from sqlalchemy import create_engine

    from app.models.db import Base

    ruta = tmp_path / "motorglosas.db"
    engine = create_engine(f"sqlite:///{ruta}")
    Base.metadata.create_all(engine)
    engine.dispose()

    con = sqlite3.connect(ruta)
    con.execute(
        "INSERT INTO preaud_oficios_recepcion (id, numero_radicado, fecha_recibido, creado_por, "
        "creado_en) VALUES (1,'FHUS-AS-I01197-26','2026-08-20 07:54','OSCAR VILLAMIZAR',"
        "'2026-08-20 07:54')"
    )
    con.execute(
        "INSERT INTO preaud_envios_cargados (envio, oficio_id, total_facturas, nuevas, "
        "reingresos, cargado_por, cargado_en) VALUES "
        "('232050',1,1,1,0,'OSCAR VILLAMIZAR','2026-08-20 08:10')"
    )
    con.execute(
        "INSERT INTO preaud_facturas (id, factura, envio_actual, oficio_actual_id, oficio_fhus, "
        "estado, resultado_actual, ronda_actual, num_subsanacion, num_devoluciones, "
        "pendiente_subsanacion, auditor, fecha_auditoria, creado_por) VALUES "
        "(1,'HUS0000540174','232050',1,'FHUS-AS-I01197-26','RADICADA','RADICAR',1,0,0,0,"
        "'VANESA OSPINA','2026-08-20 09:30','OSCAR VILLAMIZAR')"
    )
    con.execute(
        "INSERT INTO preaud_factura_eventos (factura_id, factura, tipo_evento, oficio_id, "
        "subsanacion_num, ronda, creado_en, creado_por, auditor) VALUES "
        "(1,'HUS0000540174','ESCRITA',1,0,1,'2026-08-20 08:10','OSCAR VILLAMIZAR',"
        "'OSCAR VILLAMIZAR')"
    )
    con.execute(
        "INSERT INTO preaud_factura_eventos (factura_id, factura, tipo_evento, oficio_id, "
        "subsanacion_num, ronda, creado_en, creado_por, auditor) VALUES "
        "(1,'HUS0000540174','RADICADA',1,0,1,'2026-08-20 09:30','VANESA OSPINA','VANESA OSPINA')"
    )
    con.commit()
    con.close()
    return str(ruta)


def _correr(capsys, buscado, ruta):
    sys.argv = ["preauditoria_quien_hizo_que.py", buscado, ruta]
    assert quien.main() == 0
    return capsys.readouterr().out


class TestPoneLosTresNombresAlLado:
    def test_dice_quien_registro_el_oficio(self, capsys, db):
        salida = _correr(capsys, "FHUS-AS-I01197-26", db)
        assert "LO REGISTRÓ:  OSCAR VILLAMIZAR" in salida

    def test_dice_quien_escribio_cada_envio(self, capsys, db):
        salida = _correr(capsys, "FHUS-AS-I01197-26", db)
        assert "232050" in salida and "lo escribió OSCAR VILLAMIZAR" in salida

    def test_dice_quien_audito_cada_factura(self, capsys, db):
        salida = _correr(capsys, "FHUS-AS-I01197-26", db)
        assert "la auditó VANESA OSPINA" in salida

    def test_muestra_el_historial_en_orden_con_su_firma(self, capsys, db):
        salida = _correr(capsys, "FHUS-AS-I01197-26", db)
        i_escrita = salida.index("ESCRITA")
        i_radicada = salida.index("RADICADA", salida.index("RENGLÓN POR RENGLÓN"))
        assert i_escrita < i_radicada, "el historial no sale en orden"
        assert "VANESA OSPINA" in salida[i_radicada : i_radicada + 120]

    def test_explica_de_donde_sale_el_nombre(self, capsys, db):
        """Esa es la respuesta a la pregunta del auditor."""
        salida = _correr(capsys, "FHUS-AS-I01197-26", db)
        assert "sale de la SESIÓN abierta en el navegador" in salida
        assert "cerrar sesión" in salida


class TestBuscarPorEnvio:
    def test_encuentra_el_oficio_donde_se_escribio(self, capsys, db):
        salida = _correr(capsys, "232050", db)
        assert "se escribió en 1 oficio" in salida
        assert "FHUS-AS-I01197-26" in salida

    def test_lo_que_no_existe_se_dice_claro(self, capsys, db):
        salida = _correr(capsys, "999999", db)
        assert "No hay ningún oficio" in salida


class TestSoloMira:
    def test_no_cambia_nada_en_la_base(self, capsys, db):
        antes = sqlite3.connect(db).execute("SELECT auditor FROM preaud_facturas").fetchall()
        _correr(capsys, "FHUS-AS-I01197-26", db)
        assert (
            sqlite3.connect(db).execute("SELECT auditor FROM preaud_facturas").fetchall() == antes
        )

    def test_marca_lo_que_vino_del_excel(self, capsys, db):
        """Ese nombre no lo puso nadie en la página: lo traía la columna
        AUDITOR del Excel importado."""
        con = sqlite3.connect(db)
        con.execute(
            "UPDATE preaud_facturas SET creado_por='importacion-historica-excel' WHERE id=1"
        )
        con.commit()
        con.close()
        salida = _correr(capsys, "FHUS-AS-I01197-26", db)
        assert "[vino del Excel]" in salida

    def test_base_inexistente_avisa_sin_reventar(self, capsys, tmp_path):
        sys.argv = ["x", "FHUS-AS-I01197-26", str(tmp_path / "no_existe.db")]
        assert quien.main() == 1
        assert "No se encontró la base de datos" in capsys.readouterr().out
