"""Un anexo tarifario sin contrato ni vigencia.

OT-036 · 13-08-2026. Con el contrato de FAMISANAR firmado ya se pueden
cargar las 6.655 tarifas como pactadas. Al preparar el cargue apareció que
el archivo —`PROPUESTA_2026_BASE_FINAL_FAMISANAR.xlsx`— son cinco hojas de
códigos y valores y nada más: no dice a qué contrato pertenece ni desde
cuándo rige.

Cargadas así quedaban sin vigencia, y una tarifa de 2026 sirve entonces para
defender una factura de 2024. El motor tiene desde julio la malla
contractual con vigencia por fecha justamente para no hacer eso.

La solución es del cargue, no del dictamen: quien sube el archivo puede
escribir el número del contrato y las fechas. Lo que venga dentro del Excel
sigue mandando sobre lo que se escriba a mano.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.models.db import TarifaContratadaRecord, UsuarioRecord

CONTRATO = "S-13-1-03-1-04958"


def _excel_sin_metadatos() -> bytes:
    """Como llega el anexo de FAMISANAR: códigos y valores, sin encabezado."""
    wb = Workbook()
    ws = wb.active
    ws.title = "UVB"
    ws.append(
        ["CUPS", "DESCRIPCION CUPS", "VALOR UVB 2026", "GRUPO / FACTOR", "TIPO", "PROPUESTA FINAL"]
    )
    ws.append(["010101", "PUNCION CISTERNAL VIA LATERAL", 880800, 4, "GRUPOS", 836800])
    ws.append(["010201", "PUNCION ASPIRACION DE LIQUIDO", 1114800, 5, "GRUPOS", 1059100])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


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
def coordinador(db_session):
    u = UsuarioRecord(
        id=1,
        email="coord@hus.gov.co",
        nombre="Coordinador",
        rol="COORDINADOR",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, coordinador):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: coordinador
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _subir(client, params: str = "") -> dict:
    r = client.post(
        "/tarifas-contratadas/import-excel?eps_override=FAMISANAR" + params,
        files={
            "archivo": (
                "PROPUESTA_2026_BASE_FINAL_FAMISANAR.xlsx",
                _excel_sin_metadatos(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestSeCargaConSuContratoYSuVigencia:
    def test_las_fechas_escritas_quedan_guardadas(self, client, db_session):
        _subir(
            client,
            "&contrato_override="
            + CONTRATO
            + "&vigencia_desde_override=2026-04-15"
            + "&vigencia_hasta_override=2027-04-14",
        )
        t = db_session.query(TarifaContratadaRecord).filter_by(codigo_cups="010101").first()
        assert t is not None
        assert t.contrato_numero == CONTRATO
        assert (
            t.vigencia_desde is not None and t.vigencia_desde.strftime("%Y-%m-%d") == "2026-04-15"
        )
        assert (
            t.vigencia_hasta is not None and t.vigencia_hasta.strftime("%Y-%m-%d") == "2027-04-14"
        )

    def test_sin_escribir_nada_se_cargan_igual_pero_sin_vigencia(self, client, db_session):
        """No se rompe el cargue de quien no tenga el dato a la mano: se sube
        y queda constancia de que no hay vigencia."""
        _subir(client)
        t = db_session.query(TarifaContratadaRecord).filter_by(codigo_cups="010101").first()
        assert t is not None
        assert t.vigencia_desde is None
        assert t.contrato_numero is None

    def test_una_vigencia_al_reves_se_rechaza(self, client):
        """Escribir el año de cierre en la casilla de inicio es fácil, y deja
        una vigencia que nunca se cumple: ninguna tarifa aplicaría jamás."""
        r = client.post(
            "/tarifas-contratadas/import-excel?eps_override=FAMISANAR"
            "&vigencia_desde_override=2027-04-14&vigencia_hasta_override=2026-04-15",
            files={
                "archivo": (
                    "anexo.xlsx",
                    _excel_sin_metadatos(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert r.status_code == 400
        assert "vigencia" in r.json()["detail"].lower()

    def test_se_acepta_la_fecha_como_la_escribe_el_auditor(self, client, db_session):
        """La pantalla manda AAAA-MM-DD, pero por la API entra DD/MM/AAAA."""
        _subir(client, "&vigencia_desde_override=15/04/2026")
        t = db_session.query(TarifaContratadaRecord).filter_by(codigo_cups="010101").first()
        assert t.vigencia_desde.strftime("%Y-%m-%d") == "2026-04-15"


class TestLoQueSeCargaEsLoPactado:
    def test_entra_el_valor_pactado_y_no_el_de_referencia(self, client, db_session):
        """OT-014: en la hoja UVB conviven el valor de referencia y el pactado
        (ese menos el 5%). Si gana el de referencia, el motor defiende con una
        tarifa más alta que la pactada y la entidad ratifica la glosa."""
        _subir(client)
        t = db_session.query(TarifaContratadaRecord).filter_by(codigo_cups="010101").first()
        assert t.valor_pactado == 836800.0, "se cargó el valor de referencia"

    def test_la_uvb_no_se_carga_como_tarifa_propia(self, client, db_session):
        """Son la UVB por grupos, no tarifas propias del hospital: decir otra
        cosa en el dictamen es describir mal el contrato."""
        _subir(client)
        t = db_session.query(TarifaContratadaRecord).filter_by(codigo_cups="010101").first()
        assert t.modalidad == "UVB POR GRUPOS"


class TestLaPantallaMandaLosCampos:
    def test_el_formulario_pide_contrato_y_fechas(self):
        from pathlib import Path

        html = Path(__file__).resolve().parents[2] / "static" / "index.html"
        if not html.exists():  # pragma: no cover
            pytest.skip("static/index.html no está en este entorno")
        texto = html.read_text(encoding="utf-8", errors="ignore")
        for campo in ("tar-xlsx-contrato", "tar-xlsx-desde", "tar-xlsx-hasta"):
            assert campo in texto, campo
        for param in (
            "contrato_override=",
            "vigencia_desde_override=",
            "vigencia_hasta_override=",
        ):
            assert param in texto, param
