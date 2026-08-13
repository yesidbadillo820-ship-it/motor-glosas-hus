"""La pantalla «Salud Total» vuelve a tener backend.

OT-033 · 13-08-2026. Yesid abrió la pantalla con una notificación real de
Salud Total y le salió «Not Found». La causa: en la limpieza de mayo de 2026
se borró `app/api/routers/salud_total.py` por no tener llamadores en el
código Python — pero sí tenía uno, el JavaScript de la pantalla, que sigue
llamando a `/api/salud-total/preview` y `/api/salud-total/procesar`. El
servicio nunca se borró: le faltaba la puerta, no el motor.

Estas pruebas fijan lo que se rompió y lo que puede volver a romperse:

  · **Que las dos rutas existan.** Es el defecto que reportó el auditor.
  · **Que el radicado salga como texto.** El archivo que se había armado por
    fuera traía «3,5E+14» en las 44 filas en vez de 350000214021421: así
    Salud Total no puede casar ninguna respuesta con su glosa.
  · **Que el valor glosado sea el glosado.** En la radiografía de tórax la
    glosa es de $93.340 y el valor total del servicio es $280.000. Tomar la
    columna equivocada, y de paso multiplicarla por cien, puso $28.000.000
    donde iban $93.340.
  · **Que el código del motivo sea la sigla.** Va «TA», no «Tarifas».
  · **Que no se alegue extemporaneidad sin fecha de recepción.** El plazo
    del Art. 57 de la Ley 1438/2011 corre desde que la EPS recibe la
    factura. Antes, sin ese dato, se contaba desde la radicación de la glosa
    hasta hoy y se escribía «han transcurrido N días hábiles» en un
    documento que se radica ante la entidad.

Los datos son los de la notificación real salvo el nombre y la cédula del
paciente, que aquí van anonimizados.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.models.db import UsuarioRecord

RADICADO = "350000214021421"

CABECERA = (
    "FechaRad_|NumeroRad_|PrefijoFac_|NumeroFac_|Numreg|NumeroDocAfl_|NombreComplAfl|Nap|"
    "NombreServicio|ValorTotalServ|CantidadFac|ValorUnitario|ValorGlosaFinal|"
    "ValorGlosaTotalxServ|DescripcionMotivo|Observaciones|CodMotvGlosaGeneral|"
    "MotvGlosaGeneral|CodMotvGlosaEspc|MotvGlosaEspc|DescripcionDevolucion|"
    "CausalDevolucion|MotivoDevolucion|ValorBrutoFactura|"
)

# Radiografía de tórax: servicio $280.000, glosa $93.340. Es la fila con la
# que se detectó el error de los $28.000.000.
FILA_RADIOGRAFIA = (
    f"07/03/2026 2:07:00 AM|{RADICADO}|HUS|523938|605090729|00000000|PACIENTE DE PRUEBA|0|"
    "RADIOGRAFIA DE TORAX (P.A. O A.P. Y LATERAL, DECUBITO LATERAL, OBLICUAS O LATERAL)|"
    "280000.00|2|140000.00|93340.00|93340|"
    "Los cargos por otros procedimientos no quirurgicos presentan diferencias con los "
    "valores pactados o establecidos por la norma||TA|Tarifas|TA23|"
    "Otros procedimientos no quirurgicos||||1589100.00|"
)

FILA_TOXOIDE = (
    f"07/03/2026 2:07:00 AM|{RADICADO}|HUS|523938|605089544|00000000|PACIENTE DE PRUEBA|0|"
    "TOXOIDE TETANICO PURIFICADO CONCENTRADO JERINGA PRELLENADA|"
    "20700.00|1|20700.00|8409.00|8409|"
    "Los cargos por medicamentos o APME presentan diferencias con los valores pactados"
    "||TA|Tarifas|TA07|Medicamentos y APME||||1589100.00|"
)

NOTIFICACION = "\r\n".join([CABECERA, FILA_RADIOGRAFIA, FILA_TOXOIDE]) + "\r\n"


def _archivo(texto: str = NOTIFICACION, nombre: str = "NotificacionGLS.txt"):
    # latin-1 es como llegan de la entidad.
    return {"file": (nombre, texto.encode("latin-1"), "text/plain")}


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


@pytest.fixture
def auditor(db_session):
    u = UsuarioRecord(
        id=1,
        email="auditor@hus.gov.co",
        nombre="Auditor",
        rol="AUDITOR",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, auditor):
    from app.api.deps import get_auditor_o_superior
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_auditor_o_superior] = lambda: auditor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestLaPantallaYaNoDaNotFound:
    """El defecto que reportó el auditor: las rutas no existían."""

    def test_las_dos_rutas_estan_montadas(self):
        from app.main import app

        rutas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/salud-total/preview" in rutas
        assert "/api/salud-total/procesar" in rutas

    def test_preview_responde(self, client):
        r = client.post(
            "/api/salud-total/preview", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["total_registros"] == 2

    def test_procesar_devuelve_el_archivo(self, client):
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        )
        assert r.status_code == 200, r.text
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "RTAGLOSA_900006037" in r.headers.get("content-disposition", "")


class TestSinSesionNoSePasa:
    """Por acá salen documentos que se radican ante la entidad."""

    def test_preview_exige_rol(self):
        from app.main import app

        with TestClient(app) as c:
            r = c.post("/api/salud-total/preview", files=_archivo())
            assert r.status_code in (401, 403), r.status_code

    def test_procesar_exige_rol(self):
        from app.main import app

        with TestClient(app) as c:
            r = c.post("/api/salud-total/procesar", files=_archivo())
            assert r.status_code in (401, 403), r.status_code


class TestLosTresErroresDelArchivoDel13DeAgosto:
    """El archivo que se armó por fuera del portal traía estos tres errores
    en las 44 filas. Ninguno se puede repetir."""

    def _filas(self, client) -> list[dict]:
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        )
        assert r.status_code == 200, r.text
        lineas = r.text.strip().split("\n")
        cab = lineas[0].split("|")
        return [dict(zip(cab, ln.split("|"))) for ln in lineas[1:]]

    def test_el_radicado_sale_completo_y_como_texto(self, client):
        """«3,5E+14» deja el archivo inservible: la entidad no puede casar
        ninguna respuesta con su glosa."""
        for f in self._filas(client):
            assert f["NumeroRad"] == RADICADO, f["NumeroRad"]
            assert "E+" not in f["NumeroRad"].upper()

    def test_el_valor_glosado_es_el_glosado(self, client):
        """En la radiografía la glosa es $93.340; el servicio vale $280.000.
        El archivo malo decía $28.000.000."""
        f = self._filas(client)[0]
        # Se escribe «93340», como lo escribe la entidad, no «93340.0».
        assert f["ValorGlosaTotalxServ"] == "93340", f["ValorGlosaTotalxServ"]

    def test_el_codigo_del_motivo_es_la_sigla_no_la_descripcion(self, client):
        """Va «TA», no «Tarifas»."""
        for f in self._filas(client):
            assert f["CodMotvGlosaGeneral"] == "TA", f["CodMotvGlosaGeneral"]
            assert f["CodMotvGlosaEspc"].startswith("TA")

    def test_ninguna_observacion_trae_saltos_de_linea(self, client):
        """El archivo malo tenía 105 líneas para 44 glosas: las
        observaciones traían saltos de línea adentro y partían las filas."""
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        )
        assert len(r.text.strip().split("\n")) == 3  # cabecera + 2 glosas


class TestNoSeAlegaUnPlazoQueNadiePuedeProbar:
    """El plazo del Art. 57 de la Ley 1438/2011 corre desde que la EPS
    RECIBE la factura. Sin esa fecha no hay punto de partida."""

    def test_sin_fecha_no_se_escriben_dias_transcurridos(self, client):
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        )
        assert "DÍAS HÁBILES" not in r.text.upper()
        assert "{DIAS}" not in r.text

    def test_sin_fecha_no_se_usa_el_codigo_de_extemporanea(self, client):
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        )
        assert "RE9502" not in r.text, "se alegó extemporaneidad sin con qué contarla"

    def test_la_pantalla_avisa_que_falta_la_fecha(self, client):
        r = client.post(
            "/api/salud-total/preview", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        )
        assert r.json()["sin_fecha_recepcion"] is True

    def test_con_fecha_si_se_cuenta_el_plazo(self, client):
        """Factura recibida el 02/06/2026, glosa radicada el 03/07/2026:
        más de 20 días hábiles, luego sí es extemporánea y se dice cuántos."""
        r = client.post(
            "/api/salud-total/procesar",
            files=_archivo(),
            data={"tipo_respuesta": "extemporanea", "fecha_recepcion": "2026-06-02"},
        )
        assert "RE9502" in r.text
        assert "DÍAS HÁBILES" in r.text.upper()
        assert "{DIAS}" not in r.text

    def test_con_fecha_dentro_del_plazo_no_se_alega_extemporaneidad(self, client):
        """Recibida el 01/07/2026 y glosada el 03/07: dos días hábiles."""
        r = client.post(
            "/api/salud-total/procesar",
            files=_archivo(),
            data={"tipo_respuesta": "extemporanea", "fecha_recepcion": "2026-07-01"},
        )
        assert "RE9502" not in r.text

    def test_una_fecha_posterior_a_la_glosa_no_cuenta_como_plazo(self, client):
        """Yesid digitó 30/07/2026 en una glosa radicada el 03/07/2026. La
        EPS no puede glosar una factura antes de recibirla: el dato está mal
        y no sirve para contar el plazo. Antes salía «0 días» en silencio."""
        datos = {"tipo_respuesta": "extemporanea", "fecha_recepcion": "2026-07-30"}
        prev = client.post("/api/salud-total/preview", files=_archivo(), data=datos).json()
        assert prev["sin_fecha_recepcion"] is True, "la fecha invertida se dio por buena"
        arch = client.post("/api/salud-total/procesar", files=_archivo(), data=datos).text
        assert "RE9502" not in arch
        assert "DÍAS HÁBILES" not in arch.upper()

    def test_la_vista_previa_y_el_archivo_dicen_lo_mismo(self, client):
        """Si la vista previa calculara sin la fecha, mostraría un código y
        el archivo descargado traería otro."""
        datos = {"tipo_respuesta": "extemporanea", "fecha_recepcion": "2026-06-02"}
        prev = client.post("/api/salud-total/preview", files=_archivo(), data=datos).json()
        arch = client.post("/api/salud-total/procesar", files=_archivo(), data=datos).text
        assert prev["sin_fecha_recepcion"] is False
        assert prev["glosas"][0]["Codigo_Respuesta_a_glosas"] in arch


class TestLoQueLaPantallaNecesitaParaPintar:
    """El JavaScript lee estas llaves por nombre: si cambian, la tabla sale
    vacía sin dar error."""

    def test_el_resumen_trae_los_cuatro_totales(self, client):
        d = client.post(
            "/api/salud-total/preview", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        ).json()
        for k in ("total_registros", "total_glosado", "total_aceptado", "total_rechazado"):
            assert k in d, k
        assert d["total_glosado"] == 93340.0 + 8409.0
        assert d["total_rechazado"] == d["total_glosado"] - d["total_aceptado"]

    def test_cada_glosa_trae_las_columnas_de_la_tabla(self, client):
        d = client.post(
            "/api/salud-total/preview", files=_archivo(), data={"tipo_respuesta": "extemporanea"}
        ).json()
        for k in (
            "NumeroRad",
            "NUMREG",
            "NombreServicio",
            "ValorGlosaTotalxServ",
            "Codigo_Respuesta_a_glosas",
            "ConceptoRespuesta",
        ):
            assert k in d["glosas"][0], k


class TestArchivosQueNoSirven:
    def test_un_archivo_que_no_es_txt_se_rechaza(self, client):
        r = client.post(
            "/api/salud-total/preview",
            files={"file": ("glosas.xlsx", b"PK\x03\x04", "application/vnd.ms-excel")},
            data={"tipo_respuesta": "extemporanea"},
        )
        assert r.status_code == 400

    def test_un_txt_sin_filas_lo_dice_en_palabras(self, client):
        r = client.post(
            "/api/salud-total/preview",
            files=_archivo(CABECERA + "\r\n"),
            data={"tipo_respuesta": "extemporanea"},
        )
        assert r.status_code == 400
        assert "glosas" in r.json()["detail"].lower()

    def test_una_fecha_de_recepcion_mal_escrita_no_tumba_la_ruta(self, client):
        """Si la fecha viene rota se responde de fondo, no se revienta."""
        r = client.post(
            "/api/salud-total/procesar",
            files=_archivo(),
            data={"tipo_respuesta": "extemporanea", "fecha_recepcion": "02-06-2026"},
        )
        assert r.status_code == 200
        assert "RE9502" not in r.text

    def test_el_acento_del_archivo_latin1_sobrevive(self, client):
        texto = NOTIFICACION.replace("RADIOGRAFIA", "RADIOGRAFÍA")
        d = client.post(
            "/api/salud-total/preview",
            files=_archivo(texto),
            data={"tipo_respuesta": "extemporanea"},
        ).json()
        assert "RADIOGRAFÍA" in d["glosas"][0]["NombreServicio"]
