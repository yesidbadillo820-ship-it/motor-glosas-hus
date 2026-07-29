"""Centro de Automatización: el auditor corre las herramientas sin consola.

Hasta ahora las 34 herramientas de `tools/` solo se usaban copiando el guion
a un PC con Python. Estas pruebas verifican lo único que importa: que subir
el Excel del pagador por la aplicación devuelva el archivo del ERP, con el
contenido correcto.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ROL_AUDITOR, ROL_VIEWER, UsuarioRecord

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _usuario(rol=ROL_AUDITOR):
    return UsuarioRecord(id=1, email="ana@hus.com", nombre="Ana Torres", rol=rol, activo=1)


@pytest.fixture
def cliente(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    estado = {"usuario": _usuario()}
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: estado["usuario"]
    with TestClient(app) as c:
        c.estado = estado
        yield c
    app.dependency_overrides.clear()


def _excel_savia() -> bytes:
    """Un Excel con el layout real de SAVIA: 8 columnas, dos facturas.

    Los valores llevan centavos a propósito: es el caso que el bot leía
    multiplicado por cien antes de converger los lectores de pesos.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "Numero_factura",
            "Cod_Servicio",
            "Servicio",
            "Cantidad_Servicio",
            "Valor_Unitario",
            "Valor_Glosa",
            "Motivo_Esp_Glosa_Valor_A",
            "Observacion_Glosa_A",
        ]
    )
    ws.append(["HUS443697", "890201", "CONSULTA", 1, "50.000", "1.365,50", "TA08", "Tarifa"])
    ws.append(["HUS443697", "890301", "CONTROL", 2, "30.000", "60.000", "FA01", "Facturación"])
    ws.append(["HUS503425", "890201", "CONSULTA", 1, "50.000", "950.000", "SO61", "Soportes"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestCatalogo:
    def test_el_auditor_ve_lo_que_puede_correr(self, cliente):
        d = cliente.get("/automatizaciones").json()
        assert d["total"] >= 4
        ids = {a["id"] for g in d["grupos"] for a in g["automatizaciones"]}
        assert "objeciones-savia" in ids

    def test_cada_ficha_dice_para_que_sirve(self, cliente):
        """Un catálogo sin 'cuándo usarla' obliga a preguntarle a alguien."""
        d = cliente.get("/automatizaciones").json()
        for g in d["grupos"]:
            for a in g["automatizaciones"]:
                assert a["que_hace"].strip()
                assert a["cuando_usarla"].strip()
                assert a["extensiones"]

    def test_el_viewer_no_entra(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        assert cliente.get("/automatizaciones").status_code == 403


class TestCorridaReal:
    """La prueba que importa: entra el Excel del pagador, sale el del ERP."""

    def _ejecutar(self, cliente, opciones=None):
        return cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("SAVIA_SALUD.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": json.dumps(opciones or {})},
        )

    def test_devuelve_un_archivo_por_factura(self, cliente):
        r = self._ejecutar(cliente)
        assert r.status_code == 200, r.text
        assert r.headers["X-Archivos-Generados"] == "2"
        nombres = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        assert any("443697" in n for n in nombres)
        assert any("503425" in n for n in nombres)

    def test_el_archivo_trae_las_16_columnas_del_erp(self, cliente):
        r = self._ejecutar(cliente)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        wb = openpyxl.load_workbook(io.BytesIO(z.read(z.namelist()[0])))
        encabezados = [c.value for c in wb["OBJECIONES"][1]]
        assert len(encabezados) == 16
        assert encabezados[0] == "CDCONSEC"
        assert "CROVALOBJ" in encabezados

    def test_el_valor_con_centavos_no_se_infla(self, cliente):
        """`1.365,50` tiene que salir 1.365, no 136.550.

        Es el bug del ×100 verificado de punta a punta: desde el Excel que
        sube el auditor hasta la celda del archivo que se carga al ERP.
        """
        r = self._ejecutar(cliente)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nombre = next(n for n in z.namelist() if "443697" in n)
        wb = openpyxl.load_workbook(io.BytesIO(z.read(nombre)))
        ws = wb["OBJECIONES"]
        col = [c.value for c in ws[1]].index("CROVALOBJ")
        valores = [ws.cell(row=f, column=col + 1).value for f in range(2, ws.max_row + 1)]
        assert 1365 in valores
        assert 136550 not in valores

    def test_el_valor_con_punto_de_miles_no_se_divide(self, cliente):
        """`950.000` son novecientos cincuenta mil, no novecientos cincuenta."""
        r = self._ejecutar(cliente)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nombre = next(n for n in z.namelist() if "503425" in n)
        wb = openpyxl.load_workbook(io.BytesIO(z.read(nombre)))
        ws = wb["OBJECIONES"]
        col = [c.value for c in ws[1]].index("CROVALOBJ")
        assert ws.cell(row=2, column=col + 1).value == 950000

    def test_los_parametros_llegan_a_la_herramienta(self, cliente):
        """El sufijo del código lo elige el auditor en la pantalla."""
        r = self._ejecutar(cliente, {"codigo_sufijo": "07"})
        z = zipfile.ZipFile(io.BytesIO(r.content))
        wb = openpyxl.load_workbook(io.BytesIO(z.read(z.namelist()[0])))
        ws = wb["OBJECIONES"]
        col = [c.value for c in ws[1]].index("CRNCONOBJ")
        codigos = {ws.cell(row=f, column=col + 1).value for f in range(2, ws.max_row + 1)}
        assert any(str(c).endswith("07") for c in codigos)


class TestErroresQueSeExplican:
    """Un error que no dice qué hacer obliga al auditor a llamar a alguien."""

    def test_extension_equivocada(self, cliente):
        r = cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("glosas.pdf", b"%PDF-1.4", "application/pdf")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 400
        assert ".xlsx" in r.json()["detail"]

    def test_archivo_vacio(self, cliente):
        r = cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("vacio.xlsx", b"", "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 400
        assert "vac" in r.json()["detail"].lower()

    def test_automatizacion_inexistente(self, cliente):
        r = cliente.post(
            "/automatizaciones/no-existe/ejecutar",
            files={"archivo": ("x.xlsx", b"x", "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 404

    def test_el_viewer_no_ejecuta(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("x.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 403

    def test_un_tropiezo_interno_no_es_un_500(self, cliente, monkeypatch):
        """Lo que vio el auditor en producción: «Error 500» pelado. Cualquier
        excepción inesperada del motor debe volver como 400 con explicación."""
        import dataclasses

        from app.services import automatizaciones as svc

        roto = dataclasses.replace(svc.obtener("objeciones-savia"), argumentos=_revienta)
        monkeypatch.setattr(svc, "obtener", lambda _id: roto)

        r = cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("SAVIA.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 400, r.text
        assert "inesperada" in r.json()["detail"]
        assert "KeyError" in r.json()["detail"]

    def test_un_resumen_roto_no_tumba_la_previsualizacion(self, cliente, monkeypatch):
        """El resumen es cortesía: si no se deja calcular, el «ver qué sale»
        igual responde qué archivos salieron."""
        from app.services import automatizaciones as svc

        def _explota(archivos):
            raise RuntimeError("resumen roto a propósito")

        monkeypatch.setattr(svc, "resumir", _explota)
        r = cliente.post(
            "/automatizaciones/objeciones-savia/previsualizar",
            files={"archivo": ("SAVIA.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["archivos"]
        assert d["resumen"] == {}

    def test_nombre_de_archivo_raro_no_tumba_la_descarga(self):
        """Un «→» o un emoji en el nombre rompía el encabezado HTTP."""
        from app.api.routers.automatizaciones import _nombre_para_header

        assert _nombre_para_header("OBJECIONES → ERP 🧾.xlsx") == "OBJECIONES _ ERP _.xlsx"
        assert _nombre_para_header("ñandú á.xlsx") == "ñandú á.xlsx"  # latin-1 vale
        assert _nombre_para_header("") == "archivo"


def _revienta(entrada, salida, opciones):
    raise KeyError("argumento que no existe")


class TestQuedaEnAuditoria:
    def test_se_registra_quien_corrio_que(self, cliente, db_session):
        cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("SAVIA.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        from app.models.db import AuditLogRecord

        filas = (
            db_session.query(AuditLogRecord)
            .filter(AuditLogRecord.accion == "EJECUTAR_AUTOMATIZACION")
            .all()
        )
        assert filas, "la corrida no quedó registrada"
        assert filas[-1].usuario_email == "ana@hus.com"


class TestLaPantallaExiste:
    """La capacidad sin pantalla es una capacidad que nadie usa.

    El Motor de Vencimientos ya había pasado por eso: construido, probado y
    desconectado de la interfaz durante semanas. Esta prueba amarra el panel
    al endpoint para que no vuelva a pasar.
    """

    def _html(self) -> str:
        from pathlib import Path

        ruta = Path(__file__).resolve().parent.parent.parent / "static" / "index.html"
        return ruta.read_text(encoding="utf-8", errors="ignore")

    def test_hay_entrada_en_el_menu(self):
        assert 'id="sn-automatizacion"' in self._html()

    def test_hay_panel(self):
        assert 'id="p-automatizacion"' in self._html()

    def test_el_panel_se_carga_al_abrir_la_pestana(self):
        assert "if(id==='automatizacion') autoCargar();" in self._html()

    def test_la_pantalla_llama_a_los_dos_endpoints(self):
        html = self._html()
        assert "'/automatizaciones'" in html
        assert "'/automatizaciones/' + id + '/ejecutar'" in html


class TestHerramientasQueTrabajanSobreCarpeta:
    """Varias herramientas de `tools/` reciben una carpeta, no un archivo.

    Así se usan por doble clic en el PC del auditor: se sueltan en la carpeta
    y procesan todo lo que encuentran. Para correrlas desde la aplicación, el
    archivo subido se deja dentro de la carpeta de trabajo y se recoge lo que
    aparezca ahí — menos el original, que si no volvería como resultado.
    """

    def test_el_indice_de_soportes_sale_en_excel(self, cliente):
        txt = "\n".join(
            [
                "HUS0000443697|RIPS|2026-01-15|ruta/uno.json",
                "HUS0000443697|FEV|2026-01-15|ruta/dos.xml",
                "HUS0000503425|RIPS|2026-01-16|ruta/tres.json",
            ]
        ).encode("utf-8")
        r = cliente.post(
            "/automatizaciones/indice-soportes/ejecutar",
            files={"archivo": ("indice_facturas_HUS.txt", txt, "text/plain")},
            data={"opciones": json.dumps({"delimitador": "|"})},
        )
        assert r.status_code == 200, r.text
        # La herramienta entrega el Excel y además el CSV: los dos van en un ZIP.
        assert r.headers["X-Archivos-Generados"] == "2"
        nombres = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        assert any(n.endswith(".xlsx") for n in nombres), nombres
        assert any(n.endswith(".csv") for n in nombres), nombres

    def test_no_devuelve_el_archivo_que_se_subio(self, cliente):
        """Si el original volviera como resultado, el auditor descargaría lo
        mismo que subió y creería que la herramienta no hizo nada."""
        txt = b"HUS0000443697|RIPS|2026-01-15|ruta/uno.json\n"
        r = cliente.post(
            "/automatizaciones/indice-soportes/ejecutar",
            files={"archivo": ("indice.txt", txt, "text/plain")},
            data={"opciones": json.dumps({"delimitador": "|"})},
        )
        assert r.status_code == 200
        nombres = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        assert "indice.txt" not in nombres, nombres


class TestCatalogoCompleto:
    def test_estan_las_siete_herramientas(self, cliente):
        d = cliente.get("/automatizaciones").json()
        ids = {a["id"] for g in d["grupos"] for a in g["automatizaciones"]}
        assert {
            "objeciones-savia",
            "objeciones-vco",
            "objeciones-emssanar",
            "indice-soportes",
            "excel-a-csv",
            "revisar-xml",
            "tramite-masivo",
        } <= ids

    def test_los_grupos_ordenan_el_catalogo(self, cliente):
        """Con siete herramientas ya hace falta agrupar; con veinte, más."""
        d = cliente.get("/automatizaciones").json()
        nombres = {g["nombre"] for g in d["grupos"]}
        assert {"Conversión", "Soportes", "Radicación", "Cargue"} <= nombres


class TestVerQueSaleAntesDeCargarlo:
    """La regla del área: no hacer un cargue masivo sin mirar antes qué sale.

    Hasta ahora "mirar" era abrir el Excel a mano. Acá el auditor ve cuántas
    facturas, cuántas objeciones y cuánta plata trae el resultado. Si el total
    no se parece al del archivo que mandó la EPS, hay algo mal — y se ve antes
    de cargarlo al ERP, no después.
    """

    def _previsualizar(self, cliente):
        return cliente.post(
            "/automatizaciones/objeciones-savia/previsualizar",
            files={"archivo": ("SAVIA.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )

    def test_dice_cuantas_facturas_y_cuantas_objeciones(self, cliente):
        d = self._previsualizar(cliente).json()
        assert d["ok"] is True
        assert d["resumen"]["facturas"] == 2
        assert d["resumen"]["filas"] == 3

    def test_dice_cuanta_plata(self, cliente):
        """1.365,50 + 60.000 + 950.000 = 1.011.365 en pesos enteros."""
        d = self._previsualizar(cliente).json()
        assert d["resumen"]["valor_total"] == pytest.approx(1_011_365, abs=2)

    def test_el_total_delata_un_valor_inflado(self, cliente):
        """Si el ×100 volviera, el total saltaría a la vista: 1,1 millones
        contra 136 millones. Es justamente para eso que se muestra."""
        d = self._previsualizar(cliente).json()
        assert d["resumen"]["valor_total"] < 2_000_000

    def test_no_devuelve_el_archivo(self, cliente):
        """Previsualizar es mirar, no descargar."""
        r = self._previsualizar(cliente)
        assert r.headers["content-type"].startswith("application/json")

    def test_el_viewer_no_previsualiza(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        assert self._previsualizar(cliente).status_code == 403

    def test_la_pantalla_tiene_el_boton(self):
        """El botón EN LA FICHA, no solo la función.

        La versión anterior verificaba que existiera la función
        `autoPrevisualizar` — y pasaba mientras el botón que la llama nunca
        llegó a la ficha (un reemplazo con escapes falló en silencio). El
        auditor lo vio en producción: solo aparecía "Ejecutar". Ahora se exige
        el botón dentro del generador de fichas.
        """
        from pathlib import Path

        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "autoPrevisualizar" in html
        assert "/previsualizar" in html
        assert "Ver qué sale" in html, "el botón de previsualizar no está en la ficha"
        assert "auto-prev-" in html, "falta el id del botón en la ficha"

    def test_la_pantalla_es_interactiva(self):
        """Lo que el área pidió con nombre propio: arrastrar el archivo,
        filtrar por grupo, buscar en vivo. Y el scroll, que no existía."""
        import re
        from pathlib import Path

        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "autoSoltar" in html, "no se puede arrastrar el archivo"
        assert "auto-chip" in html, "no hay pestañas por grupo"
        assert "autoBuscarEnVivo" in html, "no hay búsqueda en vivo"
        # El scroll: .panel es overflow:hidden, el área DEBE traer el suyo.
        area = re.search(r"\.auto-area\{[^}]*\}", html).group(0)
        assert "overflow-y:auto" in area, "la pantalla queda estática: no scrollea"
