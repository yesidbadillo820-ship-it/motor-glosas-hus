"""Tests para POST /plantillas-gold/importar-masivo y GET /plantillas-gold/cobertura."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import GlosaRecord, PlantillaGoldRecord, UsuarioRecord


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
def usuario_admin():
    return UsuarioRecord(
        id=1, email="admin@hus.gov.co", rol="SUPER_ADMIN", activo=1, nombre="Admin"
    )


@pytest.fixture
def client(db_session, usuario_admin):
    from app.api.deps import get_coordinador_o_admin, get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_admin
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


ARG_VALIDO = "x" * 100  # Argumento de 100 chars (pasa el min de 50)


class TestImportarMasivoJSON:
    def test_importa_lista_completa(self, client, db_session):
        payload = {
            "plantillas": [
                {
                    "eps": "FAMISANAR",
                    "codigo_glosa": "TA0201",
                    "titulo": "Defensa TA0201 FAMISANAR",
                    "argumento": ARG_VALIDO + "uno",
                },
                {
                    "eps": "NUEVA EPS",
                    "codigo_glosa": "SO0501",
                    "titulo": "Defensa SO0501",
                    "argumento": ARG_VALIDO + "dos",
                },
            ]
        }
        r = client.post("/plantillas-gold/importar-masivo", json=payload)
        assert r.status_code == 201
        body = r.json()
        assert body["total_recibidas"] == 2
        assert body["creadas"] == 2
        assert body["omitidas_duplicado"] == 0
        assert body["omitidas_error"] == 0
        assert len(body["ids_creadas"]) == 2
        # Verificar en BD
        assert db_session.query(PlantillaGoldRecord).count() == 2

    def test_detecta_duplicados_en_segundo_request(self, client, db_session):
        payload = {
            "plantillas": [
                {
                    "eps": "FAMISANAR",
                    "codigo_glosa": "TA0201",
                    "titulo": "T1",
                    "argumento": ARG_VALIDO,
                }
            ]
        }
        r1 = client.post("/plantillas-gold/importar-masivo", json=payload)
        assert r1.json()["creadas"] == 1

        r2 = client.post("/plantillas-gold/importar-masivo", json=payload)
        assert r2.status_code == 201
        body = r2.json()
        assert body["creadas"] == 0
        assert body["omitidas_duplicado"] == 1

    def test_reporta_errores_por_fila_sin_abortar(self, client, db_session):
        payload = {
            "plantillas": [
                {
                    "eps": "FAMISANAR",
                    "codigo_glosa": "TA0201",
                    "titulo": "Ok",
                    "argumento": ARG_VALIDO,
                },
                # Esta falla: argumento muy corto
                {
                    "eps": "NUEVA EPS",
                    "codigo_glosa": "SO0501",
                    "titulo": "Corto",
                    "argumento": "corto",
                },
                # Esta falla: eps vacío
                {
                    "eps": "",
                    "codigo_glosa": "FA0101",
                    "titulo": "Sin eps",
                    "argumento": ARG_VALIDO + "_unicox",
                },
            ]
        }
        r = client.post("/plantillas-gold/importar-masivo", json=payload)
        body = r.json()
        assert body["creadas"] == 1
        assert body["omitidas_error"] == 2
        assert len(body["errores"]) == 2

    def test_rechaza_lote_demasiado_grande(self, client):
        # 5001 filas → 413
        payload = {
            "plantillas": [
                {
                    "eps": f"EPS{i}",
                    "codigo_glosa": "TA0201",
                    "titulo": f"T{i}",
                    "argumento": ARG_VALIDO + str(i),
                }
                for i in range(5001)
            ]
        }
        r = client.post("/plantillas-gold/importar-masivo", json=payload)
        assert r.status_code == 413


class TestImportarMasivoCSV:
    def test_importa_csv_uploaded(self, client, db_session):
        csv_content = (
            "eps,codigo_glosa,titulo,argumento\n"
            f"FAMISANAR,TA0201,Defensa A,{ARG_VALIDO}aaa\n"
            f"NUEVA EPS,SO0501,Defensa B,{ARG_VALIDO}bbb\n"
        )
        files = {"archivo": ("plantillas.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        r = client.post("/plantillas-gold/importar-masivo/archivo", files=files)
        assert r.status_code == 201
        body = r.json()
        assert body["creadas"] == 2

    def test_importa_json_uploaded(self, client, db_session):
        data = [
            {
                "eps": "SURA",
                "codigo_glosa": "AU0301",
                "titulo": "Defensa AU",
                "argumento": ARG_VALIDO,
            }
        ]
        files = {
            "archivo": (
                "plantillas.json",
                io.BytesIO(json.dumps(data).encode("utf-8")),
                "application/json",
            )
        }
        r = client.post("/plantillas-gold/importar-masivo/archivo", files=files)
        assert r.status_code == 201
        assert r.json()["creadas"] == 1

    def test_sin_archivo_falla(self, client):
        # Sin archivo el endpoint multipart devuelve 422 (validación de FastAPI)
        r = client.post("/plantillas-gold/importar-masivo/archivo")
        assert r.status_code == 422


class TestCobertura:
    def test_sin_datos_devuelve_estructura_vacia(self, client):
        r = client.get("/plantillas-gold/cobertura")
        assert r.status_code == 200
        body = r.json()
        assert body["resumen"]["combinaciones_con_plantilla"] == 0
        assert body["resumen"]["combinaciones_sin_plantilla"] == 0

    def test_identifica_huecos(self, client, db_session):
        # 1 plantilla para (FAMISANAR, TA0201)
        db_session.add(
            PlantillaGoldRecord(
                eps="FAMISANAR",
                codigo_glosa="TA0201",
                titulo="T",
                argumento=ARG_VALIDO,
                usos=5,
                activa=1,
            )
        )
        # 2 glosas reales: 1 con plantilla, 1 sin
        db_session.add(GlosaRecord(eps="FAMISANAR", codigo_glosa="TA0201", valor_objetado=100000))
        db_session.add(GlosaRecord(eps="SURA", codigo_glosa="SO0501", valor_objetado=500000))
        db_session.commit()

        r = client.get("/plantillas-gold/cobertura")
        body = r.json()
        assert body["resumen"]["combinaciones_con_plantilla"] == 1
        # SURA × SO0501 NO tiene plantilla
        huecos = body["eps_codigo_sin_plantilla"]
        assert any(h["eps"] == "SURA" and h["codigo_glosa"] == "SO0501" for h in huecos)
        # FAMISANAR × TA0201 está cubierta
        cubiertas = body["eps_codigo_con_plantilla"]
        assert any(c["eps"] == "FAMISANAR" and c["usos_total"] == 5 for c in cubiertas)
