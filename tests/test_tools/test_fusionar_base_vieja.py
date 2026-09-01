"""Pruebas de la fusión de la base vieja de la VM con la base viva del PC.

Lo importante: trae lo que falta (glosas con toda su historia, precedentes,
usuarios, contratos, tarifas), NUNCA pisa lo que ya está en la viva, es
idempotente y no truena si la base vieja es más antigua (tablas o columnas
que no existen).
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "fusionar_base_vieja", RAIZ / "tools" / "fusionar_base_vieja.py"
)
imp = importlib.util.module_from_spec(spec)
sys.modules["fusionar_base_vieja"] = imp
spec.loader.exec_module(imp)


def _crear_db(ruta: Path) -> None:
    from sqlalchemy import create_engine

    from app.models.db import Base

    engine = create_engine(f"sqlite:///{ruta}")
    Base.metadata.create_all(engine)
    engine.dispose()


@pytest.fixture()
def bases(tmp_path):
    """(ruta_vieja, ruta_viva) con los datos del escenario real de la mudanza."""
    vieja = tmp_path / "rescate" / "motorglosas-rescate.db"
    vieja.parent.mkdir()
    viva = tmp_path / "data" / "motorglosas.db"
    viva.parent.mkdir()
    _crear_db(vieja)
    _crear_db(viva)

    cv = sqlite3.connect(vieja)
    cv.executescript(
        """
        INSERT INTO usuarios (id, nombre, email, password_hash, rol, activo)
        VALUES (1, 'YESID', 'yesid@x.com', 'hash-viejo', 'SUPER_ADMIN', 1),
               (2, 'ELIAS', 'elias@x.com', 'hash-elias', 'AUDITOR', 1);

        INSERT INTO historial (id, eps, factura, codigo_glosa, valor_objetado,
                               creado_en, dictamen)
        VALUES (10, 'COOSALUD', 'HUS100', 'TA0801', 5000.0,
                '2026-05-01 10:00:00', 'DICTAMEN G1'),
               (11, 'AXA', 'HUS200', 'SO0601', 800.0,
                '2026-06-01 09:00:00', 'DICTAMEN G2');

        INSERT INTO conceptos_glosa (glosa_id, codigo_glosa, valor_objetado)
        VALUES (10, 'TA0801', 5000.0);
        INSERT INTO dictamen_versiones (glosa_id, dictamen_html, accion)
        VALUES (10, '<p>V1</p>', 'CREAR');
        INSERT INTO comentarios_glosa (glosa_id, autor_email, texto)
        VALUES (10, 'yesid@x.com', 'ojo con esta');
        INSERT INTO notas_privadas (glosa_id, autor_email, contenido)
        VALUES (10, 'yesid@x.com', 'nota mia');
        INSERT INTO conciliaciones (id, glosa_id, resultado, valor_conciliado)
        VALUES (7, 10, 'GANADA', 5000.0);
        INSERT INTO adjuntos_conciliacion (conciliacion_id, nombre, contenido_b64)
        VALUES (7, 'acta.png', 'YWJj');
        INSERT INTO comentarios_thread (id, glosa_id, seccion, parent_id,
                                        autor_email, contenido, resuelto)
        VALUES (3, 10, 'intro', NULL, 'yesid@x.com', 'padre', 0),
               (4, 10, 'intro', 3, 'elias@x.com', 'hijo', 0);

        INSERT INTO plantillas_gold (eps, codigo_glosa, argumento, glosa_origen_id)
        VALUES ('COOSALUD', 'TA0801', 'ARGUMENTO GANADOR', 10);
        INSERT INTO plantillas (nombre, plantilla) VALUES ('P1', 'TEXTO P1');

        INSERT INTO contratos (eps, detalles, pdf_path)
        VALUES ('COOSALUD', 'detalle viejo', '/data/contratos/coosalud.pdf'),
               ('NUEVA EPS', 'detalle viejo NE', NULL);
        INSERT INTO clausulas_contrato (eps, numero_clausula, texto_literal)
        VALUES ('COOSALUD', 'QUINTA', 'texto 1'), ('COOSALUD', 'SEXTA', 'texto 2');

        INSERT INTO tarifas_contratadas (eps, codigo_cups, valor_pactado,
                                         tipo_tarifa, activa)
        VALUES ('COOSALUD', '890201', 12000.0, 'VALOR_FIJO', 1),
               ('AXA', '890305', 990.0, 'VALOR_FIJO', 1);

        INSERT INTO entidad_credenciales (nit, empresa, bloque, usuario_cifrado)
        VALUES ('800', 'AXA', 'RADICACION', 'token-fernet');

        INSERT INTO rutas_factura (factura_hus, ruta_carpeta)
        VALUES ('HUS100', 'Y:/soportes/HUS100');
        INSERT INTO snippets (usuario_email, atajo, contenido, uso_count, visibilidad)
        VALUES ('yesid@x.com', '/ratif', 'texto largo de ratificacion', 0, 'PRIVADO');
        """
    )
    cv.commit()
    cv.close()

    cn = sqlite3.connect(viva)
    cn.executescript(
        """
        INSERT INTO usuarios (id, nombre, email, password_hash, rol, activo)
        VALUES (1, 'YESID', 'yesid@x.com', 'hash-pc', 'SUPER_ADMIN', 1);
        INSERT INTO historial (id, eps, factura, codigo_glosa, valor_objetado, creado_en)
        VALUES (1, 'SANITAS', 'HUS900', 'FA1701', 100.0, '2026-08-10 08:00:00');
        INSERT INTO contratos (eps, detalles) VALUES ('NUEVA EPS', 'detalle VIVO');
        INSERT INTO tarifas_contratadas (eps, codigo_cups, valor_pactado,
                                         tipo_tarifa, activa)
        VALUES ('AXA', '890305', 1500.0, 'VALOR_FIJO', 1);
        """
    )
    cn.commit()
    cn.close()
    return str(vieja), str(viva)


def _correr(vieja, viva, aplicar=False):
    argv = ["prog", vieja] + (["aplicar"] if aplicar else []) + [viva]
    previo = sys.argv
    sys.argv = argv
    try:
        assert imp.main() == 0
    finally:
        sys.argv = previo


def test_fusion_trae_lo_que_falta_sin_pisar_nada(bases):
    vieja, viva = bases
    _correr(vieja, viva, aplicar=True)
    con = sqlite3.connect(viva)

    # Las dos glosas viejas llegaron; la de la viva sigue intacta.
    assert con.execute("SELECT COUNT(*) FROM historial").fetchone()[0] == 3
    nid, dictamen = con.execute(
        "SELECT id, dictamen FROM historial WHERE factura='HUS100'"
    ).fetchone()
    assert dictamen == "DICTAMEN G1"

    # Usuarios: el del PC conserva su clave; el que faltaba llega con la vieja.
    assert (
        con.execute("SELECT password_hash FROM usuarios WHERE email='yesid@x.com'").fetchone()[0]
        == "hash-pc"
    )
    assert (
        con.execute("SELECT password_hash FROM usuarios WHERE email='elias@x.com'").fetchone()[0]
        == "hash-elias"
    )

    # La historia de la glosa viaja con el id NUEVO (remapeado).
    assert con.execute("SELECT glosa_id FROM conceptos_glosa").fetchone()[0] == nid
    assert con.execute("SELECT glosa_id FROM dictamen_versiones").fetchone()[0] == nid
    assert con.execute("SELECT glosa_id FROM notas_privadas").fetchone()[0] == nid
    conc_id, conc_glosa = con.execute("SELECT id, glosa_id FROM conciliaciones").fetchone()
    assert conc_glosa == nid
    assert con.execute("SELECT conciliacion_id FROM adjuntos_conciliacion").fetchone()[0] == conc_id
    assert con.execute("SELECT glosa_origen_id FROM plantillas_gold").fetchone()[0] == nid

    # El hilo conserva la relación padre → hijo con los ids nuevos.
    padre_id = con.execute("SELECT id FROM comentarios_thread WHERE contenido='padre'").fetchone()[
        0
    ]
    assert (
        con.execute("SELECT parent_id FROM comentarios_thread WHERE contenido='hijo'").fetchone()[0]
        == padre_id
    )

    # Contratos: el vivo no se toca; el nuevo llega con el PDF apuntando al PC.
    assert (
        con.execute("SELECT detalles FROM contratos WHERE eps='NUEVA EPS'").fetchone()[0]
        == "detalle VIVO"
    )
    pdf = con.execute("SELECT pdf_path FROM contratos WHERE eps='COOSALUD'").fetchone()[0]
    assert pdf == str(Path(viva).resolve().parent / "contratos" / "coosalud.pdf")
    assert (
        con.execute("SELECT COUNT(*) FROM clausulas_contrato WHERE eps='COOSALUD'").fetchone()[0]
        == 2
    )

    # Tarifas: el par (AXA, 890305) ya existía en la viva → manda la viva.
    assert con.execute("SELECT COUNT(*) FROM tarifas_contratadas").fetchone()[0] == 2
    assert (
        con.execute("SELECT valor_pactado FROM tarifas_contratadas WHERE eps='AXA'").fetchone()[0]
        == 1500.0
    )

    # Vault (viva vacía → se copia), rutas y snippets.
    assert con.execute("SELECT COUNT(*) FROM entidad_credenciales").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM rutas_factura").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM snippets").fetchone()[0] == 1

    # Antes de escribir quedó copia de seguridad, y huella en el audit_log.
    respaldos = list((Path(viva).parent / "backups").glob("motorglosas-antes-fusion-*.db"))
    assert len(respaldos) == 1
    assert (
        con.execute("SELECT COUNT(*) FROM audit_log WHERE accion='FUSION_BASE_VIEJA'").fetchone()[0]
        == 1
    )
    con.close()


def test_idempotente(bases):
    vieja, viva = bases
    _correr(vieja, viva, aplicar=True)
    _correr(vieja, viva, aplicar=True)
    con = sqlite3.connect(viva)
    for tabla, esperado in [
        ("historial", 3),
        ("usuarios", 2),
        ("conceptos_glosa", 1),
        ("dictamen_versiones", 1),
        ("comentarios_glosa", 1),
        ("notas_privadas", 1),
        ("conciliaciones", 1),
        ("adjuntos_conciliacion", 1),
        ("comentarios_thread", 2),
        ("plantillas_gold", 1),
        ("plantillas", 1),
        ("contratos", 2),
        ("clausulas_contrato", 2),
        ("tarifas_contratadas", 2),
        ("entidad_credenciales", 1),
        ("rutas_factura", 1),
        ("snippets", 1),
    ]:
        n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        assert n == esperado, f"{tabla}: {n} != {esperado}"
    con.close()


def test_solo_mirar_no_escribe(bases):
    vieja, viva = bases
    _correr(vieja, viva, aplicar=False)
    con = sqlite3.connect(viva)
    assert con.execute("SELECT COUNT(*) FROM historial").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM plantillas_gold").fetchone()[0] == 0
    con.close()
    assert not list((Path(viva).parent / "backups").glob("*.db"))


def test_vieja_mas_antigua_no_truena(bases):
    """La base vieja puede no tener tablas/columnas que hoy existen."""
    vieja, viva = bases
    cv = sqlite3.connect(vieja)
    cv.executescript(
        """
        DROP TABLE rutas_factura;
        DROP TABLE snippets;
        DROP INDEX IF EXISTS ix_historial_numero_nota_credito;
        ALTER TABLE historial DROP COLUMN numero_nota_credito;
        """
    )
    cv.commit()
    cv.close()
    _correr(vieja, viva, aplicar=True)
    con = sqlite3.connect(viva)
    assert con.execute("SELECT COUNT(*) FROM historial").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM rutas_factura").fetchone()[0] == 0
    con.close()


def test_vault_con_datos_en_la_viva_no_se_mezcla(bases):
    vieja, viva = bases
    con = sqlite3.connect(viva)
    con.execute(
        "INSERT INTO entidad_credenciales (nit, empresa, bloque, usuario_cifrado) "
        "VALUES ('900', 'SANITAS', 'CARTERA', 'token-del-pc')"
    )
    con.commit()
    con.close()
    _correr(vieja, viva, aplicar=True)
    con = sqlite3.connect(viva)
    filas = con.execute("SELECT nit FROM entidad_credenciales").fetchall()
    assert filas == [("900",)]
    con.close()
