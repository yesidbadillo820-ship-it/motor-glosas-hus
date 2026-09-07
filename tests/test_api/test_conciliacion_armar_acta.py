"""La ruta y la pantalla de «Armar el acta» (07-09-2026).

El auditor sube dos archivos —la lista de facturas de la mesa y el
consolidado que mandó la EPS— y baja el ACTA SINAC del formato oficial, con
las macros, lista para llevar a la audiencia.

Lo que se cuida acá es el trato con quien la usa: que los errores digan qué
hacer en vez de un HTTP pelado, que el archivo salga con el nombre del acta,
y que la pantalla no llame rutas que no existen.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.database import Base, get_db
from app.main import app
from app.models.db import ConciliacionTipificacionRecord, UsuarioRecord

RAIZ = Path(__file__).resolve().parents[2]
MODELO = RAIZ / "plantillas" / "ACTA_SINAC_modelo.xlsm"
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")

CABECERA = [
    "RADICADO",
    "PREFIJO",
    "FACTURA",
    "FECHA ATENCION",
    "FECHA RADICACION",
    "VALOR FACTURA",
    "CODIGO CONCEPTO DE GLOSA",
    "MOTIVO DE GLOSA",
    "VALOR OBJETADO",
    "SERVICIO OBJETADO",
    "NUMERO ACTA RESPUESTA",
]


def _excel(filas: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    for fila in filas:
        wb.active.append(fila)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _eps(*glosas) -> bytes:
    filas = [CABECERA]
    for factura, cod, valor in glosas:
        filas.append(
            [
                "560611",
                "HUS",
                factura,
                date(2025, 9, 1),
                date(2025, 10, 7),
                1_000_000,
                cod,
                "MOTIVO DE LA GLOSA",
                valor,
                "SERVICIO",
                "AR002328",
            ]
        )
    return _excel(filas)


def _lista(*facturas) -> bytes:
    return _excel([[f] for f in facturas])


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


@pytest.fixture
def cliente(db):
    usuario = UsuarioRecord(id=1, email="aud@hus.gov.co", rol="AUDITOR", activo=1)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[deps.get_auditor_o_superior] = lambda: usuario
    app.dependency_overrides[deps.get_usuario_actual] = lambda: usuario
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


ENCABEZADO = {
    "nit": "901541137",
    "razon_social": "DISPENSARIO MEDICO",
    "numero_acta": "710",
    "periodo": "SEP 2026",
    "fecha_conciliacion": "2026-09-08",
}


def _armar(cliente, lista, eps, **extra):
    return cliente.post(
        "/conciliaciones/acta-excel/armar",
        files={"facturas": ("lista.xlsx", lista), "archivo_eps": ("eps.xlsx", eps)},
        data={**ENCABEZADO, **extra},
    )


# ══════════════════════════════════════════════════════════════════════════
class TestVerQueSaleAntesDeGenerar:
    def test_el_parte_dice_lo_que_el_auditor_necesita_saber(self, cliente):
        r = _armar(
            cliente,
            _lista("HUS0000542497", "HUS0000542501"),
            _eps(("542497", "TA0201", 6685), ("542497", "SO3601", 12000)),
            solo_revisar="true",
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["lineas"] == 2
        assert d["facturas_con_glosa"] == 1
        assert d["facturas_en_lista"] == 2
        assert d["valor_a_conciliar"] == 18685
        assert d["sin_glosas"] == ["542501"]

    def test_las_casillas_que_decide_una_persona_se_enumeran(self, cliente):
        r = _armar(cliente, _lista("542497"), _eps(("542497", "CL0301", 100)), solo_revisar="true")
        d = r.json()
        assert d["total_avisos"] == 1
        assert "MIXTA" in d["avisos"][0]["motivo"]
        assert d["avisos"][0]["factura"] == "HUS0000542497"

    def test_el_mismo_aviso_de_la_misma_factura_no_se_repite(self, cliente):
        """Caso real (07-09-2026): HUS0000453962 tenía tres glosas CO4601 y
        la lista mostró tres veces la misma frase, tapando los avisos
        distintos que venían detrás. Cada renglón sigue teniendo su aviso —
        la mesa los marca uno por uno—; lo que se agrupa es el resumen."""
        r = _armar(
            cliente,
            _lista("542497"),
            _eps(("542497", "CO4601", 100), ("542497", "CO4601", 200), ("542497", "CO4601", 300)),
            solo_revisar="true",
        )
        d = r.json()
        assert len(d["avisos"]) == 1, "el resumen repitió el mismo aviso"
        assert d["avisos"][0]["renglones"] == 3, "no dice cuántos renglones son"
        # El total NO se agrupa: es el trabajo que hay por delante.
        assert d["total_avisos"] == 3

    def test_avisos_distintos_de_la_misma_factura_se_muestran_todos(self):
        """Agrupar no puede esconder un motivo diferente."""
        from app.api.routers.conciliacion import _avisos_agrupados
        from app.services.acta_conciliacion_armar import Aviso

        agrupados = _avisos_agrupados([
            Aviso("HUS1", "falta el tipo", 2),
            Aviso("HUS1", "falta el tipo", 3),
            Aviso("HUS1", "familia CO sin tipificación", 4),
            Aviso("HUS2", "falta el tipo", 5),
        ])
        assert len(agrupados) == 3
        assert [a["renglones"] for a in agrupados] == [2, 1, 1]

    def test_lo_que_venia_en_la_eps_y_no_en_la_lista_se_dice(self, cliente):
        r = _armar(cliente, _lista("542497"), _eps(("999999", "TA0201", 10)), solo_revisar="true")
        assert r.json()["fuera_de_lista"] == ["999999"]


@pytest.mark.skipif(not MODELO.is_file(), reason="falta el modelo del acta")
class TestElArchivoQueSeDescarga:
    def test_sale_el_xlsm_con_el_numero_del_acta_en_el_nombre(self, cliente):
        r = _armar(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685)))
        assert r.status_code == 200
        assert 'filename="ACTA_SINAC_710.xlsm"' in r.headers["content-disposition"]
        assert r.headers["content-type"].startswith("application/vnd.ms-excel")

    def test_el_parte_viaja_en_la_cabecera_para_avisar_sin_abrir_el_archivo(self, cliente):
        import json

        r = _armar(cliente, _lista("542497"), _eps(("542497", "CL0301", 100)))
        parte = json.loads(r.headers["X-Acta-Parte"])
        assert parte["lineas"] == 1 and parte["total_avisos"] == 1

    def test_el_libro_es_de_verdad_un_excel_con_macros(self, cliente):
        import zipfile

        r = _armar(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685)))
        nombres = zipfile.ZipFile(BytesIO(r.content)).namelist()
        assert any("vbaProject" in n for n in nombres)


class TestLosErroresDicenQueHacer:
    """Un HTTP pelado deja al auditor sin saber qué corregir."""

    def test_una_lista_sin_facturas_reconocibles(self, cliente):
        r = _armar(cliente, _excel([["hola"], ["mundo"]]), _eps(("542497", "TA0201", 1)))
        assert r.status_code == 422
        assert "HUS0000542497" in r.json()["detail"]

    def test_un_archivo_de_eps_sin_encabezado(self, cliente):
        r = _armar(cliente, _lista("542497"), _excel([["a"], ["b"]]))
        assert r.status_code == 422
        assert "FACTURA" in r.json()["detail"]

    def test_dos_archivos_de_tandas_distintas(self, cliente):
        """El caso real: la lista es de septiembre y el archivo de la EPS de
        enero. Cero coincidencias — hay que decirlo, no devolver un acta vacía."""
        r = _armar(cliente, _lista("542497"), _eps(("420099", "TA0201", 1)))
        assert r.status_code == 422
        assert "misma tanda" in r.json()["detail"]

    def test_una_fecha_mal_escrita(self, cliente):
        r = _armar(
            cliente,
            _lista("542497"),
            _eps(("542497", "TA0201", 1)),
            fecha_conciliacion="8 de septiembre",
        )
        assert r.status_code == 422 and "AAAA-MM-DD" in r.json()["detail"]

    def test_sin_los_dos_archivos_no_arranca(self, cliente):
        r = cliente.post(
            "/conciliaciones/acta-excel/armar",
            files={"facturas": ("l.xlsx", _lista("1"))},
            data=ENCABEZADO,
        )
        assert r.status_code == 422


@pytest.mark.skipif(not MODELO.is_file(), reason="falta el modelo del acta")
class TestAprenderDeLaMesa:
    def test_el_acta_trabajada_deja_la_tipificacion_guardada(self, cliente, db):
        libro = _armar(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).content
        r = cliente.post(
            "/conciliaciones/acta-excel/aprender",
            files={"archivo": ("acta.xlsm", libro)},
            data={"numero_acta": "710"},
        )
        assert r.status_code == 200
        assert r.json()["aprendido"]["nuevas"] == 1

        fila = db.query(ConciliacionTipificacionRecord).one()
        assert (fila.factura_clave, fila.cod_glosa) == ("542497", "TA0201")
        assert fila.tipo_glosa == "ADMINISTRATIVA"
        assert fila.definido_por == "aud@hus.gov.co" and fila.numero_acta == "710"

    def test_lo_marcado_como_pendiente_no_se_aprende(self, cliente, db):
        libro = _armar(cliente, _lista("542497"), _eps(("542497", "CL0301", 100))).content
        r = cliente.post(
            "/conciliaciones/acta-excel/aprender", files={"archivo": ("a.xlsm", libro)}
        )
        assert r.json()["aprendido"]["nuevas"] == 0
        assert db.query(ConciliacionTipificacionRecord).count() == 0


class TestLaPantalla:
    def test_llama_a_las_rutas_que_existen(self):
        assert "'/conciliaciones/acta-excel/armar'" in HTML

    def test_pide_los_dos_archivos_por_separado(self):
        assert "armar-file-fact" in HTML and "armar-file-eps" in HTML
        assert "fd.append('facturas'" in HTML and "fd.append('archivo_eps'" in HTML

    def test_tiene_las_casillas_del_encabezado(self):
        for campo in ("armar-nit", "armar-razon", "armar-acta", "armar-periodo", "armar-fecha"):
            assert f'id="{campo}"' in HTML, f"falta {campo}"

    def test_la_plata_se_muestra_con_el_formato_unico(self):
        """Regla del repo: `fmtCOP`, nunca un toLocaleString suelto."""
        bloque = HTML[HTML.index("function armarPintarParte") :][:1600]
        assert "fmtCOP(" in bloque
        assert "toLocaleString" not in bloque

    def test_avisa_cuando_algo_queda_para_una_persona(self):
        bloque = HTML[HTML.index("function armarPintarParte") :][:1600]
        assert "decide una persona" in bloque and "DEFINIR" in bloque

    def test_no_se_llevo_por_delante_el_panel_que_ya_existia(self):
        for fn in ("actaxRevisar", "actaxOptimizar", "actaxPdf"):
            assert f"function {fn}" in HTML or f"{fn}()" in HTML
