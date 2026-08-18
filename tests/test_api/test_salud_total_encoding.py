"""El archivo de Salud Total se descarga en ANSI, no en UTF-8 — 18-08-2026.

El portal de Salud Total lee el TXT en Windows-1252 (ANSI): el archivo que el
HUS sube y que sí funciona está en ese formato. El sistema lo enviaba en UTF-8,
así que en el portal los acentos salían rotos: «clínica» se veía «clÃ­nica» y
«CÓDIGO» «CÃDIGO», en un documento que se radica ante la EPS.

Se detectó con una corrida real del botón «Analizar con IA»: el RTAGLOSA que
salió venía en UTF-8; el archivo humano que había funcionado, en ANSI.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_auditor_o_superior
from app.auth import get_password_hash
from app.database import Base, get_db
from app.models.db import UsuarioRecord
from app.services.salud_total_service import a_bytes_portal

CABECERA = (
    "FechaRad_|NumeroRad_|PrefijoFac_|NumeroFac_|Numreg|NumeroDocAfl_|NombreComplAfl|Nap|"
    "NombreServicio|ValorTotalServ|CantidadFac|ValorUnitario|ValorGlosaFinal|"
    "ValorGlosaTotalxServ|DescripcionMotivo|Observaciones|CodMotvGlosaGeneral|"
    "MotvGlosaGeneral|CodMotvGlosaEspc|MotvGlosaEspc|DescripcionDevolucion|"
    "CausalDevolucion|MotivoDevolucion|ValorBrutoFactura|"
)
FILA = (
    "07/16/2026 11:47:00 AM|350000284269130|HUS|531434|606871081|1043651578|PACIENTE|0|"
    "RADIOGRAFIA|280000.00|2|140000.00|93340.00|93340|"
    "Los cargos presentan diferencias con los valores pactados||TA|Tarifas|TA02|"
    "Otros procedimientos||||1589100.00|"
)
NOTIFICACION = "\r\n".join([CABECERA, FILA]) + "\r\n"


class TestElHelperDeCodificacion:
    def test_no_sale_en_utf8(self):
        """El byte 0xC3 delata UTF-8: no puede aparecer."""
        b = a_bytes_portal("HISTORIA CLÍNICA, CÓDIGO Y OBJECIÓN SEGÚN ART. 57")
        assert b"\xc3" not in b

    def test_los_acentos_se_leen_bien_en_ansi(self):
        t = "CLÍNICA CÓDIGO OBJECIÓN TÉRMINOS ARTÍCULO NIÑO"
        assert a_bytes_portal(t).decode("cp1252") == t

    def test_translitera_los_signos_que_mete_la_ia(self):
        # Guion largo y comillas curvas no existen en 1252 tal cual.
        b = a_bytes_portal("VALOR — «texto» “curvo”")
        txt = b.decode("cp1252")
        assert "—" not in txt  # el guion largo se volvió "-"
        assert "-" in txt

    def test_no_revienta_con_cualquier_caracter(self):
        # Un carácter exótico no debe tumbar la descarga.
        a_bytes_portal("PRUEBA ☃ \U0001f600 FIN")  # no lanza


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    u = UsuarioRecord(
        id=1, email="a@b.c", rol="SUPER_ADMIN", activo=1, password_hash=get_password_hash("x")
    )
    s.add(u)
    s.commit()
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([s]).__next__()
    app.dependency_overrides[get_auditor_o_superior] = lambda: u
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    s.close()
    engine.dispose()


class TestLaDescargaReal:
    def test_el_archivo_descargado_no_es_utf8(self, client):
        r = client.post(
            "/api/salud-total/procesar",
            data={"tipo_respuesta": "extemporanea"},
            files={"file": ("NotificacionGLS.txt", NOTIFICACION.encode("latin-1"), "text/plain")},
        )
        assert r.status_code == 200
        assert b"\xc3" not in r.content  # no UTF-8
        # Y se lee bien como ANSI (contiene la palabra con acento del texto real).
        texto = r.content.decode("cp1252")
        assert "SOAT VIGENTE" in texto
        assert "ARTÍCULO 57" in texto
