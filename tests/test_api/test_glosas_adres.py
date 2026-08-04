"""Tests del módulo web de Glosas ADRES (POST/GET /glosas-adres/...).

Lo que se prueba acá es el camino que hace el gestor todos los días: el
coordinador carga el reporte del ADRES una sola vez y a partir de ahí el gestor
**solo escribe el número de factura** y la pantalla le trae todo — glosas
clasificadas, centro de costos, sugerencia con su motivo, el detallado cruzado
y el texto de respuesta.

También se prueba lo que más duele si falla: que volver a cargar el paquete
**no le borre al equipo las decisiones que ya tomó**, y que aplicar las
sugerencias en bloque tampoco le pise lo que un gestor escribió a mano.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ROL_COORDINADOR, UsuarioRecord

openpyxl = pytest.importorskip("openpyxl")

CABECERA_REPORTE = [
    "Código Habilitación",
    "Número Radicación",
    "Número Factura",
    "Número Paquete",
    "Cantidad Reclamado",
    "Valor Reclamado",
    "Cantidad Aprobada",
    "Valor Aprobado",
    "Valor Glosado",
    "Tip- Num Doc Victima",
    "Consecutivo Item",
    "Tipo Elemento",
    "Cod Elemento",
    "Descripción Elemento",
    "Descripción Glosa",
    "Descripción Anotación",
]

# (factura, tipo, cod, descripción, glosado, causal)
FILAS = [
    (
        "HUS352890",
        "Dispositivos Médicos",
        "2016DM-315",
        "VENDA DE GASA 6 X 5 YARDAS",
        37600,
        "3106- Soporte de material  ausente o incompleto",
    ),
    (
        "HUS352890",
        "Procedimientos",
        "39145",
        "Consulta de urgencias",
        85800,
        "3202- La consulta no esta justificada",
    ),
    (
        "HUS311371",
        "Medicamentos",
        "19942122-09",
        "OMEPRAZOL CAPSULAS",
        31800,
        "3106- Soporte de material  ausente o incompleto",
    ),
]


def _reporte_bytes() -> bytes:
    """Un reporte del ADRES con la misma pinta del real, en memoria."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(6):  # el reporte real trae el título arriba
        ws.append([])
    ws.append(CABECERA_REPORTE)
    for factura, tipo, cod, desc, glosado, causal in FILAS:
        ws.append(
            [
                "680010079201",
                "14345108",
                factura,
                "31068",
                1,
                glosado + 1000,
                0,
                1000,
                glosado,
                "CC-91246389",
                "",
                tipo,
                cod,
                desc,
                causal,
                "",
            ]
        )
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# Mismo formato que emite `tools/ajustar_detallado_glosas.py`: separado por
# punto y coma, con BOM, para que Excel lo abra bien en el hospital.
BITACORA_CSV = (
    "﻿FACTURA;HOJA;GRUPO;CODIGO;NOMBRE;CANT_ORIGINAL;VR_ENT_ORIGINAL;"
    "VALOR_RECLAMADO;VALOR_APROBADO;VALOR_GLOSADO;ACCION;CANT_NUEVA;VR_ENT_NUEVO;"
    "CRUCE_POR;FILAS_REPORTE;CAUSALES_GLOSA;TIPO_RENGLON;OBSERVACION\n"
    "HUS352890;lote dos;CONSULTAS MEDICAS;39145;CONSULTA DE URGENCIAS;1;85800;"
    "86800;1000;85800;CONSERVADO;1;85800;codigo;12;"
    "3202- La consulta no esta justificada;ITEM;Sigue glosado en su totalidad\n"
    "HUS352890;lote dos;MEDICAMENTOS POS;19992190-3;DICLOFENACO SODICO;1;900;"
    "0;0;0;QUITADO;0;0;codigo;;;ITEM;La entidad ya lo aprobó (valor glosado 0)\n"
    # Las ELIMINADA no se cargan: son facturas que ni siquiera iban en el paquete.
    "HUS352890;lote dos;OTROS;ZZZ;RENGLON BORRADO;1;100;0;0;0;ELIMINADA;0;0;;;;ITEM;\n"
).encode("utf-8")


@pytest.fixture()
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


@pytest.fixture()
def coordinador():
    return UsuarioRecord(
        id=1, email="coordinador@hus.gov.co", rol=ROL_COORDINADOR, activo=1, nombre="Coordinador"
    )


@pytest.fixture()
def gestor():
    return UsuarioRecord(id=2, email="gestor@hus.gov.co", rol="AUDITOR", activo=1, nombre="Gestor")


@pytest.fixture()
def client(db_session, coordinador):
    """Cliente autenticado como coordinador (puede cargar y decidir)."""
    from app.api.deps import get_coordinador_o_admin, get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: coordinador
    app.dependency_overrides[get_coordinador_o_admin] = lambda: coordinador
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def paquete(client):
    """Deja el reporte ya cargado y devuelve el id del paquete."""
    r = client.post(
        "/glosas-adres/importar",
        files={"archivo": ("ReporteGlosasReclamPAQUETE 31068.xlsx", _reporte_bytes())},
    )
    assert r.status_code == 200, r.text
    return r.json()["paquete_id"]


class TestCargue:
    def test_importar_cuenta_filas_facturas_y_valor(self, client):
        r = client.post(
            "/glosas-adres/importar",
            files={"archivo": ("ReporteGlosasReclamPAQUETE 31068.xlsx", _reporte_bytes())},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["numero_paquete"] == "31068"
        assert d["filas"] == 3
        assert d["facturas"] == 2
        assert d["valor_glosado"] == pytest.approx(37600 + 85800 + 31800)

    def test_archivo_vacio_da_400(self, client):
        r = client.post("/glosas-adres/importar", files={"archivo": ("vacio.xlsx", b"")})
        assert r.status_code == 400

    def test_archivo_que_no_es_excel_da_error_claro(self, client):
        r = client.post("/glosas-adres/importar", files={"archivo": ("cosa.xlsx", b"no soy excel")})
        assert r.status_code in (400, 500)
        assert "reporte" in r.json()["detail"].lower() or r.status_code == 400

    def test_paquetes_lista_lo_cargado(self, client, paquete):
        r = client.get("/glosas-adres/paquetes")
        assert r.status_code == 200
        d = r.json()
        assert len(d) == 1
        assert d[0]["id"] == paquete
        assert d[0]["numero"] == "31068"
        assert d[0]["facturas"] == 2
        assert d[0]["importado_por"] == "coordinador@hus.gov.co"

    def test_bitacora_de_paquete_inexistente_da_404(self, client):
        r = client.post(
            "/glosas-adres/importar-bitacora",
            data={"paquete_id": "999"},
            files={"archivo": ("b.csv", BITACORA_CSV)},
        )
        assert r.status_code == 404

    def test_bitacora_carga_el_detallado(self, client, paquete):
        r = client.post(
            "/glosas-adres/importar-bitacora",
            data={"paquete_id": str(paquete)},
            files={"archivo": ("BITACORA_31068.csv", BITACORA_CSV)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["items"] == 2


class TestConsulta:
    def test_buscar_autocompleta_por_pedazo_de_factura(self, client, paquete):
        r = client.get("/glosas-adres/buscar", params={"q": "35289"})
        assert r.status_code == 200
        assert r.json() == ["HUS352890"]

    def test_buscar_sin_texto_devuelve_todas(self, client, paquete):
        r = client.get("/glosas-adres/buscar")
        assert sorted(r.json()) == ["HUS311371", "HUS352890"]

    def test_factura_trae_todo_de_una_sola_vez(self, client, paquete):
        r = client.get("/glosas-adres/factura/HUS0000352890")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["encontrada"] is True
        assert d["resumen"]["glosas"] == 2
        assert d["resumen"]["pendientes"] == 2
        assert d["resumen"]["valor_glosado"] == pytest.approx(37600 + 85800)

    def test_el_bot_clasifica_y_sugiere_con_su_motivo(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        por_causal = {g["causal_codigo"]: g for g in d["glosas"]}

        soporte = por_causal["3106"]
        assert soporte["clasificacion"] == "SOPORTES"
        assert soporte["sugerencia"] == "SE SUBSANA"
        assert soporte["motivo"]  # nunca sugerir sin decir por qué

        # La pertinencia médica no se sugiere: la define el médico auditor.
        pertinencia = por_causal["3202"]
        assert pertinencia["clasificacion"] == "PERTINENCIA"
        assert not pertinencia["sugerencia"]

    def test_factura_que_no_existe_da_404(self, client, paquete):
        assert client.get("/glosas-adres/factura/HUS0000000001").status_code == 404

    def test_el_detallado_cruzado_llega_con_la_factura(self, client, paquete):
        client.post(
            "/glosas-adres/importar-bitacora",
            data={"paquete_id": str(paquete)},
            files={"archivo": ("b.csv", BITACORA_CSV)},
        )
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert d["resumen"]["items_detallado"] == 2
        # Solo sigue glosado lo que quedó CONSERVADO/AJUSTADO.
        assert d["resumen"]["sigue_glosado_detallado"] == pytest.approx(85800)
        acciones = {i["codigo"]: i["accion"] for i in d["items"]}
        assert acciones == {"39145": "CONSERVADO", "19992190-3": "QUITADO"}

    def test_respuesta_cierra_con_el_parrafo_de_extemporanea(self, client, paquete):
        r = client.get("/glosas-adres/factura/HUS0000352890/respuesta")
        assert r.status_code == 200
        texto = r.json()["texto"]
        assert "RESOLUCION 1236 DE 2023" in texto
        assert "GLOSA EXTEMPORANEA" in texto


class TestDecision:
    def test_el_gestor_guarda_su_decision(self, client, paquete):
        gid = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]["id"]
        r = client.post(
            f"/glosas-adres/glosa/{gid}",
            json={
                "decision": "SE SUBSANA",
                "observacion_tecnico": "SE ANEXA SOPORTE DE ENTREGA.",
                "centro_costos": "SERVICIO FARMACEUTICO",
            },
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["decision"] == "SE SUBSANA"
        assert d["observacion_tecnico"] == "SE ANEXA SOPORTE DE ENTREGA."
        assert d["centro_costos"] == "SERVICIO FARMACEUTICO"
        assert d["decidido_por"] == "coordinador@hus.gov.co"

    def test_glosa_inexistente_da_404(self, client, paquete):
        assert (
            client.post("/glosas-adres/glosa/99999", json={"decision": "SE ACEPTA"}).status_code
            == 404
        )

    def test_decision_invalida_da_400(self, client, paquete):
        gid = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]["id"]
        r = client.post(f"/glosas-adres/glosa/{gid}", json={"decision": "LO QUE SEA"})
        assert r.status_code == 400

    def test_aplicar_sugerencias_no_pisa_lo_que_el_gestor_escribio(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        soporte = next(g for g in d["glosas"] if g["causal_codigo"] == "3106")
        client.post(
            f"/glosas-adres/glosa/{soporte['id']}",
            json={"decision": "SE OBJETA", "observacion_tecnico": "EL SOPORTE YA SE ENVIO."},
        )

        r = client.post("/glosas-adres/aplicar-sugerencias", json={"paquete_id": paquete})
        assert r.status_code == 200, r.text

        d2 = client.get("/glosas-adres/factura/HUS0000352890").json()
        quedo = next(g for g in d2["glosas"] if g["id"] == soporte["id"])
        assert quedo["decision"] == "SE OBJETA"
        assert quedo["observacion_tecnico"] == "EL SOPORTE YA SE ENVIO."

    def test_aplicar_sugerencias_solo_a_una_factura(self, client, paquete):
        r = client.post(
            "/glosas-adres/aplicar-sugerencias",
            json={"paquete_id": paquete, "factura": "HUS0000352890"},
        )
        assert r.json()["aplicadas"] == 1  # solo la de SOPORTES de esa factura

        otra = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert not otra["glosas"][0]["decision"]


class TestRecargarNoBorraTrabajo:
    def test_volver_a_cargar_el_paquete_conserva_las_decisiones(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        gid = next(g for g in d["glosas"] if g["causal_codigo"] == "3202")["id"]
        client.post(
            f"/glosas-adres/glosa/{gid}",
            json={
                "decision": "SE OBJETA",
                "observacion_tecnico": "LA CONSULTA SI ESTABA JUSTIFICADA, SE ANEXA HISTORIA.",
                "medico": "DR. PEREZ",
            },
        )

        r = client.post(
            "/glosas-adres/importar",
            files={"archivo": ("ReporteGlosasReclamPAQUETE 31068.xlsx", _reporte_bytes())},
        )
        assert r.status_code == 200, r.text

        d2 = client.get("/glosas-adres/factura/HUS0000352890").json()
        recuperada = next(g for g in d2["glosas"] if g["causal_codigo"] == "3202")
        assert recuperada["decision"] == "SE OBJETA"
        assert "SE ANEXA HISTORIA" in recuperada["observacion_tecnico"]
        assert recuperada["medico"] == "DR. PEREZ"


class TestPermisos:
    def test_un_gestor_no_puede_cargar_el_paquete(self, db_session, gestor):
        from app.api.deps import get_usuario_actual
        from app.main import app

        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: gestor
        try:
            c = TestClient(app)
            r = c.post("/glosas-adres/importar", files={"archivo": ("r.xlsx", _reporte_bytes())})
            assert r.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_el_gestor_si_puede_consultar_y_decidir(self, db_session, coordinador, gestor):
        from app.api.deps import get_coordinador_o_admin, get_usuario_actual
        from app.main import app

        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: coordinador
        app.dependency_overrides[get_coordinador_o_admin] = lambda: coordinador
        try:
            c = TestClient(app)
            c.post("/glosas-adres/importar", files={"archivo": ("r.xlsx", _reporte_bytes())})
            app.dependency_overrides[get_usuario_actual] = lambda: gestor
            gid = c.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]["id"]
            r = c.post(f"/glosas-adres/glosa/{gid}", json={"decision": "SE SUBSANA"})
            assert r.status_code == 200
            assert r.json()["decidido_por"] == "gestor@hus.gov.co"
        finally:
            app.dependency_overrides.clear()


def test_el_router_esta_montado_en_la_app():
    from app.main import app

    def caminar(rutas):
        """FastAPI puede envolver los routers incluidos, así que hay que bajar."""
        for r in rutas:
            camino = getattr(r, "path", None)
            if camino:
                yield camino
            interno = getattr(r, "original_router", None) or getattr(r, "router", None)
            if interno is not None:
                yield from caminar(interno.routes)

    rutas = set(caminar(app.routes))
    assert "/glosas-adres/importar" in rutas
    assert "/glosas-adres/factura/{numero}" in rutas


def test_glosas_adres_convive_con_cobranza_live():
    """Las dos pantallas conviven en el menú.

    El plan original (28-07) era que Glosas ADRES reemplazara a Cobranza
    Live, pero al rescatar este PR (04-08) Cobranza Live seguía viva en
    producción y en uso: quitarle una pantalla al equipo no es decisión
    de una fusión. Si algún día se decide retirarla, se cambia aquí.
    """
    html = Path(__file__).resolve().parents[2] / "static" / "index.html"
    if not html.exists():  # pragma: no cover - en algunos despliegues no se copia
        pytest.skip("static/index.html no está en este entorno")
    texto = html.read_text(encoding="utf-8", errors="ignore")
    assert "Cobranza Live" in texto
    assert "Glosas ADRES" in texto
