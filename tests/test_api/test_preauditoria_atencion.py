"""La ruta que le da a la pantalla las fechas de atención y el plazo.

08-09-2026. `GET /preauditoria/facturas/{id}/atencion`. Se pide aparte de la
factura porque toca el servidor de facturación electrónica.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import get_db
from app.models.db import (
    Base,
    FacturaPreauditoriaRecord,
    RadicacionCuentaRecord,
    UsuarioRecord,
)

NIT_ADRES = "901037916"


@pytest.fixture
def db_session():
    motor = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def usuario(db_session):
    u = UsuarioRecord(
        id=1,
        nombre="CLAUDIA",
        email="claudia@hus.gov.co",
        rol="AUDITOR",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _factura_adres(db, numero="HUS0000556635", entidad="ADRES", nit=NIT_ADRES):
    db.add(
        RadicacionCuentaRecord(
            factura=numero,
            envio="228254",
            f_factura=datetime(2024, 3, 28),
            f_recibido=datetime(2024, 4, 2),
            valor=6344350.0,
            nit=nit,
            entidad=entidad,
        )
    )
    f = FacturaPreauditoriaRecord(factura=numero, envio_actual="228254", estado="NUEVA")
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _sembrar_rips(raiz, periodo, factura, ingreso, egreso):
    carpeta = raiz / periodo / "FACTURAS_SALUD" / factura
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"Rips_{factura}.json").write_text(
        json.dumps(
            {
                "numFactura": factura,
                "usuarios": [
                    {
                        "tipoDocumentoIdentificacion": "CC",
                        "numDocumentoIdentificacion": "1",
                        "codSexo": "F",
                        "servicios": {
                            "hospitalizacion": [
                                {"fechaInicioAtencion": ingreso, "fechaEgreso": egreso}
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.rips_localizador._raiz_configurada", lambda: str(tmp_path))
    return tmp_path


class TestLaRuta:
    def test_devuelve_el_dictamen_de_una_factura_del_adres(self, client, db_session, servidor):
        f = _factura_adres(db_session)
        _sembrar_rips(servidor, "202403", "HUS0000556635", "2024-03-10 08:00", "2024-03-25 14:00")

        r = client.get(f"/preauditoria/facturas/{f.id}/atencion")
        assert r.status_code == 200
        d = r.json()
        assert d["aplica"] is True
        assert d["fechas"]["fecha_egreso"] == "2024-03-25T14:00:00"
        assert d["prescripcion"]["fecha_corte"] == "2025-09-25"
        assert d["prescripcion"]["estado"] in {"PRESCRITA", "POR_VENCER", "VIGENTE"}

    def test_a_una_factura_de_eps_le_dice_que_no_aplica(self, client, db_session, servidor):
        f = _factura_adres(db_session, entidad="NUEVA EPS S.A.", nit="800251440")
        d = client.get(f"/preauditoria/facturas/{f.id}/atencion").json()
        assert d["aplica"] is False
        assert "no es del ADRES" in d["motivo"]

    def test_una_factura_que_no_existe_da_404(self, client):
        assert client.get("/preauditoria/facturas/99999/atencion").status_code == 404

    def test_sin_rips_responde_igual_y_no_se_cae(self, client, db_session, servidor):
        f = _factura_adres(db_session)  # sin sembrar el archivo
        r = client.get(f"/preauditoria/facturas/{f.id}/atencion")
        assert r.status_code == 200
        d = r.json()
        assert d["aplica"] is True
        assert d["fechas"] is None and d["prescripcion"] is None
        assert any(h["codigo"] == "RIPS_NO_ENCONTRADO" for h in d["hallazgos"])

    def test_la_respuesta_trae_siempre_las_mismas_llaves(self, client, db_session, servidor):
        """La pantalla lee estas llaves sin preguntar: no pueden faltar."""
        f = _factura_adres(db_session)
        d = client.get(f"/preauditoria/facturas/{f.id}/atencion").json()
        for llave in (
            "factura",
            "aplica",
            "motivo",
            "fechas",
            "prescripcion",
            "hallazgos",
            "hay_reparos_graves",
        ):
            assert llave in d, f"falta la llave {llave}"


class TestNoRompeLoQueYaHabia:
    def test_ver_factura_sigue_igual(self, client, db_session, servidor):
        """La ruta vieja no cambió: la revisión va aparte, no dentro."""
        f = _factura_adres(db_session)
        d = client.get(f"/preauditoria/facturas/{f.id}").json()
        assert d["factura"] == "HUS0000556635"
        assert "prescripcion" not in d  # el DTO de siempre no se tocó
