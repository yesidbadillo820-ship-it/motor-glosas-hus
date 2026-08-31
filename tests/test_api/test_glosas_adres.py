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
from app.models.db import ROL_COORDINADOR, ROL_SUPER_ADMIN, UsuarioRecord

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
    # Causal 4506: la trabajan dos áreas. Ésta es corriente → gestores.
    (
        "HUS352890",
        "Insumo",
        "INS-100",
        "GASA ESTERIL 10X10",
        5000,
        "4506- El material hace parte de otro servicio",
    ),
    # Ésta es material de osteosíntesis → médicas.
    (
        "HUS352890",
        "Material de Osteosintesis",
        "OST-200",
        "TORNILLO CORTICAL 3.5MM",
        450000,
        "4506- El material hace parte de otro servicio",
    ),
    # Sin causal: es el desglose de una GLOSA TOTAL. No se responde ítem por
    # ítem, así que la pantalla no lo muestra.
    ("HUS352890", "Procedimientos", "TOT-1", "Terapia respiratoria: sesión", 12000, ""),
    ("HUS311371", "Medicamentos", "TOT-2", "DIPIRONA 1 G", 3400, ""),
    # El MISMO ítem con DOS causales: el reporte del ADRES abre una fila por
    # cada una, pero la plata es una sola. Si se cuenta dos veces, la glosa de
    # la factura sale inflada.
    (
        "HUS311371",
        "Procedimientos",
        "DOS-1",
        "TAC DE CRANEO SIMPLE",
        700000,
        "3209- La ayuda diagnóstica no tiene justificación",
    ),
    (
        "HUS311371",
        "Procedimientos",
        "DOS-1",
        "TAC DE CRANEO SIMPLE",
        700000,
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
def admin():
    return UsuarioRecord(
        id=3, email="admin@hus.gov.co", rol=ROL_SUPER_ADMIN, activo=1, nombre="Super Admin"
    )


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
        # Las 9 filas se guardan (incluidas las 2 de glosa total y las 2 del
        # mismo ítem con dos causales): la pantalla las oculta o las junta, pero
        # el paquete conserva el reporte completo.
        assert d["filas"] == 9
        assert d["facturas"] == 2
        # El ítem de las dos causales cuenta UNA sola vez: 700.000, no 1.400.000.
        assert d["valor_glosado"] == pytest.approx(
            37600 + 85800 + 31800 + 5000 + 450000 + 12000 + 3400 + 700000
        )

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
        assert d["resumen"]["glosas"] == 4
        assert d["resumen"]["pendientes"] == 4
        assert d["resumen"]["valor_glosado"] == pytest.approx(37600 + 85800 + 5000 + 450000)

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


class TestValorAceptado:
    """Aceptar una glosa es reconocer plata: hay que poder decir CUÁNTO.

    Es lo que va en la respuesta al ADRES («CANTIDAD ACEPTADA n . POR VALOR
    $x»). Al principio la pantalla no tenía dónde escribirlo y todo quedaba en
    $0 aunque el gestor marcara SE ACEPTA.
    """

    def test_se_guarda_el_valor_y_la_cantidad_aceptada(self, client, paquete):
        g = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]
        r = client.post(
            f"/glosas-adres/glosa/{g['id']}",
            json={"decision": "SE ACEPTA", "valor_aceptado": 37600, "cantidad_aceptada": "2"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["valor_aceptado"] == pytest.approx(37600)
        assert r.json()["cantidad_aceptada"] == "2"

    def test_el_resumen_de_la_factura_lo_suma(self, client, paquete):
        g = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]
        client.post(
            f"/glosas-adres/glosa/{g['id']}",
            json={"decision": "SE ACEPTA", "valor_aceptado": 30000},
        )
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert d["resumen"]["valor_aceptado"] == pytest.approx(30000)

    def test_la_lista_de_facturas_tambien_lo_suma(self, client, paquete):
        g = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]
        client.post(
            f"/glosas-adres/glosa/{g['id']}",
            json={"decision": "SE ACEPTA", "valor_aceptado": 30000},
        )
        una = next(
            f
            for f in client.get("/glosas-adres/facturas", params={"paquete_id": paquete}).json()
            if f["factura"] == "HUS352890"
        )
        assert una["valor_aceptado"] == pytest.approx(30000)

    def test_se_puede_volver_a_cero_al_cambiar_de_decision(self, client, paquete):
        g = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]
        client.post(
            f"/glosas-adres/glosa/{g['id']}",
            json={"decision": "SE ACEPTA", "valor_aceptado": 37600, "cantidad_aceptada": "1"},
        )
        r = client.post(
            f"/glosas-adres/glosa/{g['id']}",
            json={"decision": "SE OBJETA", "valor_aceptado": 0, "cantidad_aceptada": ""},
        )
        assert r.json()["valor_aceptado"] == 0
        assert not r.json()["cantidad_aceptada"]

    def test_el_pdf_muestra_el_valor_aceptado(self, client, paquete):
        pytest.importorskip("reportlab")
        pdfplumber = pytest.importorskip("pdfplumber")
        import io as _io

        g = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]
        client.post(
            f"/glosas-adres/glosa/{g['id']}",
            json={
                "decision": "SE ACEPTA",
                "valor_aceptado": 37600,
                "cantidad_aceptada": "1",
                "observacion_tecnico": "SE RECONOCE EL VALOR.",
            },
        )
        r = client.get("/glosas-adres/factura/HUS0000352890/evidencia.pdf")
        with pdfplumber.open(_io.BytesIO(r.content)) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
        # La fórmula de la macro para el caso aceptado.
        assert "CANTIDAD ACEPTADA" in texto
        assert "$37.600" in texto


class TestDecision:
    def test_el_gestor_guarda_su_decision(self, client, paquete):
        gid = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]["id"]
        r = client.post(
            f"/glosas-adres/glosa/{gid}",
            json={
                "decision": "SE SUBSANA",
                "observacion_tecnico": "SE ANEXA SOPORTE DE ENTREGA.",
                "centro_costos": "SERVICIO FARMACEUTICO",  # sin código: se normaliza
            },
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["decision"] == "SE SUBSANA"
        assert d["observacion_tecnico"] == "SE ANEXA SOPORTE DE ENTREGA."
        # Se guarda en la forma oficial del catálogo, aunque lo manden sin código.
        assert d["centro_costos"] == "580501-SERVICIO FARMACEUTICO"
        assert d["centro_costos_por"] == "coordinador@hus.gov.co"
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
        # Solo las de esa factura que traen sugerencia: la de SOPORTES y la de
        # glosa total (que se subsana corrigiendo el FURIPS).
        assert r.json()["aplicadas"] == 2

        otra = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert not otra["glosas"][0]["decision"]


class TestGlosasTotales:
    """Las filas sin causal son el desglose de una reclamación glosada entera.

    El ADRES glosó todo por el FURIPS; esas líneas no traen causal propia y no
    se responden una por una, así que la pantalla no las muestra. Pero se
    cuentan y se dicen: nada desaparece en silencio.
    """

    def test_no_se_muestran_pero_se_cuentan(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert d["resumen"]["glosas"] == 4  # las 4 con causal
        assert d["resumen"]["glosas_totales_ocultas"] == 1
        assert d["resumen"]["valor_glosas_totales"] == pytest.approx(12000)
        assert "GLOSA TOTAL" in d["aviso_glosas_totales"]
        assert all(not g["glosa_total"] for g in d["glosas"])

    def test_el_valor_glosado_del_resumen_no_incluye_las_totales(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert d["resumen"]["valor_glosado"] == pytest.approx(37600 + 85800 + 5000 + 450000)

    def test_todas_las_visibles_traen_la_descripcion_de_la_glosa(self, client, paquete):
        """Lo que faltaba: la descripción no salía porque esas filas venían vacías."""
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert all((g["causal_texto"] or "").strip() for g in d["glosas"])

    def test_se_pueden_ver_si_el_auditor_las_pide(self, client, paquete):
        d = client.get(
            "/glosas-adres/factura/HUS0000352890", params={"incluir_totales": "true"}
        ).json()
        assert d["resumen"]["glosas"] == 5
        assert any(g["glosa_total"] for g in d["glosas"])


def _archivo_facturas(valores: dict[str, float]) -> bytes:
    """El `FACTURAS PAQUETE NNNNN_NN FACTURAS.xlsx`, con su pinta real."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FACTURAS"
    ws.append(
        ["", "No.", "Etiquetas de fila", "Suma de Valor Reclamado", "", "Suma de Valor Glosado"]
    )
    for n, (factura, glosado) in enumerate(valores.items(), start=1):
        ws.append(["", n, factura, 0, 0, glosado])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class TestNoContarDosVecesLaMismaPlata:
    """El reporte del ADRES abre UNA FILA POR CADA CAUSAL del mismo ítem.

    Las filas se conservan todas (el gestor decide causal por causal) pero la
    plata de un ítem es una sola. En el paquete 31078 sumar en bruto daba
    $585 millones contra $297 millones reales.
    """

    def test_las_dos_filas_del_mismo_item_se_muestran(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        tac = [g for g in d["glosas"] if g["codigo"] == "DOS-1"]
        assert len(tac) == 2  # una por causal, para poder decidir cada una
        assert {g["causal_codigo"] for g in tac} == {"3209", "3106"}

    def test_pero_su_plata_cuenta_una_sola_vez(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        tac = [g for g in d["glosas"] if g["codigo"] == "DOS-1"]
        assert sum(1 for g in tac if g["cuenta_valor"]) == 1
        # 31.800 del omeprazol + 700.000 del TAC (no 1.400.000)
        assert d["resumen"]["valor_glosado"] == pytest.approx(731800)

    def test_la_lista_de_facturas_tampoco_la_cuenta_dos_veces(self, client, paquete):
        una = next(
            f
            for f in client.get("/glosas-adres/facturas", params={"paquete_id": paquete}).json()
            if f["factura"] == "HUS311371"
        )
        # En la lista la plata es TODA la que glosó el ADRES (la que hay que
        # defender): 31.800 + 700.000 del TAC contado una vez + 3.400 de la
        # glosa total. Lo que NO cuenta dos veces es el TAC.
        assert una["valor_glosado"] == pytest.approx(735200)
        assert una["glosas"] == 3  # las que se responden renglón por renglón
        assert una["glosas_totales_ocultas"] == 1


class TestVerificarContraElAdres:
    """Juntar las filas no alcanza: hay facturas donde el reporte repite sin
    explicación. Ahí el sistema lo dice en vez de mostrar una cifra falsa."""

    def test_sin_el_archivo_de_facturas_no_hay_con_que_verificar(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert d["valor_glosado_oficial"] is None
        assert d["aviso_descuadre"] == ""

    def test_con_el_archivo_la_cifra_del_paquete_es_la_oficial(self, client):
        oficial = _archivo_facturas({"HUS352890": 500000, "HUS311371": 731800})
        r = client.post(
            "/glosas-adres/importar",
            files={
                "archivo": ("reporte.xlsx", _reporte_bytes()),
                "facturas": ("FACTURAS PAQUETE 31068_2 FACTURAS.xlsx", oficial),
            },
        )
        assert r.status_code == 200, r.text
        # Manda la cifra oficial, no la suma del reporte.
        assert r.json()["valor_glosado"] == pytest.approx(1231800)

    def test_avisa_cuando_el_detalle_no_cuadra_con_el_adres(self, client):
        # El ADRES dice que la 311371 tiene glosado 400.000, no 731.800.
        oficial = _archivo_facturas({"HUS352890": 590400, "HUS311371": 400000})
        client.post(
            "/glosas-adres/importar",
            files={
                "archivo": ("reporte.xlsx", _reporte_bytes()),
                "facturas": ("f.xlsx", oficial),
            },
        )
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert d["valor_glosado_oficial"] == pytest.approx(400000)
        assert "no cuadra" in d["aviso_descuadre"].lower() or "ADRES dice" in d["aviso_descuadre"]
        assert "$400.000" in d["aviso_descuadre"]
        assert "portal" in d["aviso_descuadre"]

    def test_no_avisa_cuando_si_cuadra(self, client):
        # 31.800 del omeprazol + 700.000 del TAC + 3.400 de la glosa total.
        oficial = _archivo_facturas({"HUS352890": 590400, "HUS311371": 735200})
        client.post(
            "/glosas-adres/importar",
            files={
                "archivo": ("reporte.xlsx", _reporte_bytes()),
                "facturas": ("f.xlsx", oficial),
            },
        )
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert d["aviso_descuadre"] == ""

    def test_la_lista_marca_cuales_cuadran_y_cuales_no(self, client):
        # La 352890 cuadra; a la 311371 el ADRES le dice 400.000 y no cuadra.
        oficial = _archivo_facturas({"HUS352890": 590400, "HUS311371": 400000})
        r = client.post(
            "/glosas-adres/importar",
            files={
                "archivo": ("reporte.xlsx", _reporte_bytes()),
                "facturas": ("f.xlsx", oficial),
            },
        )
        paq = r.json()["paquete_id"]
        por_factura = {
            f["factura"]: f
            for f in client.get("/glosas-adres/facturas", params={"paquete_id": paq}).json()
        }
        assert por_factura["HUS352890"]["cuadra"] is True
        assert por_factura["HUS311371"]["cuadra"] is False
        assert por_factura["HUS311371"]["valor_glosado_oficial"] == pytest.approx(400000)

    def test_un_archivo_de_facturas_ilegible_no_tumba_el_cargue(self, client):
        """Mejor cargar sin verificar que no cargar."""
        r = client.post(
            "/glosas-adres/importar",
            files={
                "archivo": ("reporte.xlsx", _reporte_bytes()),
                "facturas": ("f.xlsx", b"esto no es un excel"),
            },
        )
        assert r.status_code == 200, r.text
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert d["valor_glosado_oficial"] is None


class TestListaDeFacturas:
    """Al cargar el archivo del ADRES salen de una vez las facturas a auditar."""

    def test_lista_las_facturas_con_su_avance(self, client, paquete):
        r = client.get("/glosas-adres/facturas", params={"paquete_id": paquete})
        assert r.status_code == 200, r.text
        por_factura = {f["factura"]: f for f in r.json()}
        assert set(por_factura) == {"HUS352890", "HUS311371"}

        una = por_factura["HUS352890"]
        assert una["estado"] == "PENDIENTE"
        assert una["glosas"] == 4  # sin contar la de glosa total
        assert una["glosas_totales_ocultas"] == 1
        assert una["pendientes"] == 4
        assert una["avance"] == 0
        assert una["por_asignar"] == 2  # las dos de causal 4506

    def test_al_decidir_una_glosa_la_factura_avanza_sola(self, client, paquete):
        gid = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]["id"]
        client.post(f"/glosas-adres/glosa/{gid}", json={"decision": "SE SUBSANA"})
        una = next(
            f
            for f in client.get("/glosas-adres/facturas", params={"paquete_id": paquete}).json()
            if f["factura"] == "HUS352890"
        )
        assert una["estado"] == "EN PROCESO"
        assert una["decididas"] == 1
        assert una["avance"] == 25

    def test_se_puede_filtrar_por_estado(self, client, paquete):
        r = client.get(
            "/glosas-adres/facturas", params={"paquete_id": paquete, "estado": "CERRADA"}
        )
        assert r.json() == []
        r = client.get(
            "/glosas-adres/facturas", params={"paquete_id": paquete, "estado": "PENDIENTE"}
        )
        assert len(r.json()) == 2

    def test_se_puede_buscar_por_numero(self, client, paquete):
        r = client.get("/glosas-adres/facturas", params={"paquete_id": paquete, "buscar": "35289"})
        assert [f["factura"] for f in r.json()] == ["HUS352890"]

    def test_sin_paquetes_devuelve_lista_vacia(self, client):
        assert client.get("/glosas-adres/facturas").json() == []


class TestCerrarYReabrir:
    def test_cerrar_y_volver_a_abrir_deja_constancia(self, client, paquete):
        r = client.post("/glosas-adres/factura/HUS0000352890/estado", json={"estado": "CERRADA"})
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "CERRADA"
        assert r.json()["cerrada_por"] == "coordinador@hus.gov.co"

        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert d["estado"] == "CERRADA"

        r = client.post("/glosas-adres/factura/HUS0000352890/estado", json={"estado": "EN PROCESO"})
        assert r.json()["estado"] == "EN PROCESO"
        assert r.json()["reabierta_por"] == "coordinador@hus.gov.co"
        assert r.json()["cerrada_por"] == "coordinador@hus.gov.co"  # queda el rastro

    def test_una_factura_cerrada_no_se_reabre_sola_al_editar(self, client, paquete):
        client.post("/glosas-adres/factura/HUS0000352890/estado", json={"estado": "CERRADA"})
        gid = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]["id"]
        client.post(f"/glosas-adres/glosa/{gid}", json={"observacion_tecnico": "otra cosa"})
        assert client.get("/glosas-adres/factura/HUS0000352890").json()["estado"] == "CERRADA"

    def test_estado_invalido_da_400(self, client, paquete):
        r = client.post("/glosas-adres/factura/HUS0000352890/estado", json={"estado": "LO QUE SEA"})
        assert r.status_code == 400

    def test_factura_inexistente_da_404(self, client, paquete):
        r = client.post("/glosas-adres/factura/HUS0000000009/estado", json={"estado": "CERRADA"})
        assert r.status_code == 404

    def test_recargar_el_paquete_conserva_el_cierre(self, client, paquete):
        client.post("/glosas-adres/factura/HUS0000352890/estado", json={"estado": "CERRADA"})
        r = client.post("/glosas-adres/importar", files={"archivo": ("r.xlsx", _reporte_bytes())})
        assert r.status_code == 200, r.text
        assert client.get("/glosas-adres/factura/HUS0000352890").json()["estado"] == "CERRADA"


class TestEvidenciaPDF:
    def test_genera_un_pdf_descargable(self, client, paquete):
        pytest.importorskip("reportlab")
        r = client.get("/glosas-adres/factura/HUS0000352890/evidencia.pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert "RTA_ADRES_HUS352890.pdf" in r.headers["content-disposition"]
        assert r.content.startswith(b"%PDF")
        assert len(r.content) > 1500

    def test_el_pdf_no_lista_las_glosas_totales(self, client, paquete):
        pytest.importorskip("reportlab")
        pdfplumber = pytest.importorskip("pdfplumber")
        import io as _io

        r = client.get("/glosas-adres/factura/HUS0000352890/evidencia.pdf")
        with pdfplumber.open(_io.BytesIO(r.content)) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
        assert "REPORTE RTA ADRES" in texto
        assert "HUS352890" in texto
        assert "RTA GLOSA COMPLETA" in texto
        # El renglón de glosa total no va en la tabla, pero sí se dice al pie.
        assert "Terapia respiratoria" not in texto
        assert "GLOSA TOTAL" in texto

    def test_factura_inexistente_da_404(self, client, paquete):
        assert client.get("/glosas-adres/factura/NO-EXISTE/evidencia.pdf").status_code == 404


class TestRepartoDeAreas:
    """La causal 4506 la trabajan gestores (FACTURACION) y médicas (PERTINENCIA).

    Quién la toma depende de qué se glosó. Hasta el 31-08-2026 solo un SUPER
    ADMIN podía repartirla, y con eso las glosas compartidas se quedaban
    quietas esperando a una sola persona. **El área pidió abrirlo a los
    gestores** y así quedó.

    Lo que sostiene que sea aceptable abrirlo: el reparto es acotado (solo
    causales de dos áreas), deja testigo de quién y cuándo, y es reversible.
    Y el motor sigue calculando su propia sugerencia con el motivo — que es lo
    que hay que mirar antes de mandar a facturación algo que le toca al médico
    auditor (osteosíntesis, material de alto costo).
    """

    def test_la_4506_llega_marcada_para_repartir(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        cuatro = [g for g in d["glosas"] if g["causal_codigo"] == "4506"]
        assert len(cuatro) == 2
        assert all(g["requiere_asignacion"] for g in cuatro)
        assert d["resumen"]["por_asignar"] == 2

    def test_sugiere_medicas_para_osteosintesis_y_gestores_para_lo_demas(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        por_codigo = {g["codigo"]: g for g in d["glosas"]}
        assert por_codigo["OST-200"]["area_sugerida"] == "PERTINENCIA"
        assert por_codigo["INS-100"]["area_sugerida"] == "FACTURACION"
        # Siempre con el motivo escrito, nunca a secas.
        assert por_codigo["OST-200"]["motivo_area"]
        assert por_codigo["INS-100"]["motivo_area"]

    def test_por_asignar_lista_las_pendientes(self, client, paquete):
        r = client.get("/glosas-adres/por-asignar", params={"paquete_id": paquete})
        assert r.status_code == 200
        assert {g["codigo"] for g in r.json()} == {"INS-100", "OST-200"}

    def test_el_gestor_si_puede_repartir(self, db_session, coordinador, gestor):
        """Cambió el 31-08-2026 a pedido del área.

        Antes esta prueba exigía un 403 para el gestor. La regla cambió por
        decisión de quien usa el motor, no porque la prueba estorbara: las
        glosas compartidas se quedaban esperando a la única persona que podía
        repartirlas. Queda el testigo de quién lo hizo.
        """
        from app.api.deps import get_coordinador_o_admin, get_usuario_actual
        from app.main import app

        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: coordinador
        app.dependency_overrides[get_coordinador_o_admin] = lambda: coordinador
        try:
            c = TestClient(app)
            c.post("/glosas-adres/importar", files={"archivo": ("r.xlsx", _reporte_bytes())})
            gid = next(
                g["id"]
                for g in c.get("/glosas-adres/factura/HUS0000352890").json()["glosas"]
                if g["causal_codigo"] == "4506"
            )
            app.dependency_overrides[get_usuario_actual] = lambda: gestor
            r = c.post(f"/glosas-adres/glosa/{gid}/area", json={"area": "PERTINENCIA"})
            assert r.status_code == 200, r.text
            cuerpo = r.json()
            assert cuerpo["clasificacion"] == "PERTINENCIA"
            assert cuerpo["requiere_asignacion"] is False
            # El testigo es lo que hace aceptable haber abierto el permiso.
            assert cuerpo["area_asignada_por"] == gestor.email
        finally:
            app.dependency_overrides.clear()

    def test_el_gestor_no_puede_repartir_una_causal_que_no_se_comparte(
        self, db_session, coordinador, gestor
    ):
        """Abrir el permiso no es dejar repartir lo que sea: fuera de las
        causales de dos áreas el motor sigue respondiendo con error."""
        from app.api.deps import get_coordinador_o_admin, get_usuario_actual
        from app.main import app

        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: coordinador
        app.dependency_overrides[get_coordinador_o_admin] = lambda: coordinador
        try:
            c = TestClient(app)
            c.post("/glosas-adres/importar", files={"archivo": ("r.xlsx", _reporte_bytes())})
            gid = next(
                g["id"]
                for g in c.get("/glosas-adres/factura/HUS0000352890").json()["glosas"]
                if g["causal_codigo"] != "4506"
            )
            app.dependency_overrides[get_usuario_actual] = lambda: gestor
            r = c.post(f"/glosas-adres/glosa/{gid}/area", json={"area": "PERTINENCIA"})
            assert r.status_code == 400, r.text
        finally:
            app.dependency_overrides.clear()

    def test_el_super_admin_reparte_y_se_recalcula_la_sugerencia(self, db_session, admin):
        from app.api.deps import get_admin, get_coordinador_o_admin, get_usuario_actual
        from app.main import app

        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: admin
        app.dependency_overrides[get_coordinador_o_admin] = lambda: admin
        app.dependency_overrides[get_admin] = lambda: admin
        try:
            c = TestClient(app)
            c.post("/glosas-adres/importar", files={"archivo": ("r.xlsx", _reporte_bytes())})
            gid = next(
                g["id"]
                for g in c.get("/glosas-adres/factura/HUS0000352890").json()["glosas"]
                if g["codigo"] == "OST-200"
            )
            r = c.post(f"/glosas-adres/glosa/{gid}/area", json={"area": "PERTINENCIA"})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["clasificacion"] == "PERTINENCIA"
            assert d["requiere_asignacion"] is False
            assert d["area_asignada_por"] == "admin@hus.gov.co"
            # Al pasar a pertinencia, el bot deja de sugerir: la firma un médico.
            assert not d["sugerencia"]
            assert "médico" in (d["motivo"] or "")

            # Área inválida y causal que no se reparte, ambas rechazadas.
            assert c.post(f"/glosas-adres/glosa/{gid}/area", json={"area": "X"}).status_code == 400
            otra = next(
                g["id"]
                for g in c.get("/glosas-adres/factura/HUS0000352890").json()["glosas"]
                if g["causal_codigo"] == "3106"
            )
            assert (
                c.post(f"/glosas-adres/glosa/{otra}/area", json={"area": "FACTURACION"}).status_code
                == 400
            )
        finally:
            app.dependency_overrides.clear()


class TestCentrosDeCostos:
    def test_el_catalogo_oficial_llega_a_la_pantalla(self, client, paquete):
        r = client.get("/glosas-adres/centros-costos", params={"paquete_id": paquete})
        assert r.status_code == 200
        catalogo = r.json()
        assert len(catalogo) == 45
        assert "733001-QUIROFANOS" in catalogo
        assert "510406-DIREC SUBGCIA DE ALTO COSTO" in catalogo

    def test_la_factura_trae_el_catalogo_para_el_desplegable(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert "733001-QUIROFANOS" in d["catalogo_centros"]

    def test_los_centros_propuestos_salen_con_su_codigo(self, client, paquete):
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert d["glosas"][0]["centro_costos"] == "580501-SERVICIO FARMACEUTICO"


class TestSinDetallado:
    def test_avisa_y_muestra_igual_lo_que_se_tiene(self, client, paquete):
        """Las 4 facturas sin detallado no pueden dejar al gestor sin nada."""
        d = client.get("/glosas-adres/factura/HUS0000311371").json()
        assert d["resumen"]["items_detallado"] == 0
        assert "no tiene detallado" in d["aviso_detallado"]
        # Y aun así trae todo lo del reporte del ADRES.
        assert d["resumen"]["glosas"] == 3  # el omeprazol + las 2 filas del TAC
        assert d["glosas"][0]["valor_glosado"] == pytest.approx(31800)
        assert d["glosas"][0]["causal_codigo"] == "3106"

    def test_con_detallado_no_hay_aviso(self, client, paquete):
        client.post(
            "/glosas-adres/importar-bitacora",
            data={"paquete_id": str(paquete)},
            files={"archivo": ("b.csv", BITACORA_CSV)},
        )
        d = client.get("/glosas-adres/factura/HUS0000352890").json()
        assert d["aviso_detallado"] == ""


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


class TestInformeExcel:
    """El paquete completo, bajado como archivo (pedido del 31-08-2026).

    Yesid pidió dos cosas, y las dos se prueban acá:

    1. «Un informe así como el que tenemos en el apartado de preauditoría» — el
       resumen, las causales, el reparto y el avance, con fórmulas vivas.
    2. «Los archivos descargados deben ser así como estos», mandando dos
       `RTA_GLOSA_ADRES_PAQ_31068_*` — o sea que la hoja de datos tiene que
       seguir siendo la de siempre: las 26 columnas de la macro, en su orden,
       con el encabezado en la fila 1, para que sirvan la tabla dinámica y los
       bots que la leen.

    Y lo que más duele si falla: que los números del archivo sean los mismos de
    la pantalla — la plata del ítem glosado con dos causales y lo aceptado, que
    no se le puede declarar dos veces al ADRES.
    """

    HOJAS = [
        "CÓMO LEER",
        "RESUMEN",
        "POR QUÉ NOS GLOSAN",
        "POR ÁREA Y CENTRO",
        "POR GESTOR",
        "FACTURAS",
        "Hoja1",
    ]
    DECISION = "OBSERVACION (SE ACEPTA - SE OBJETA -  SE SUBSANA )"

    def _libro(self, client, **params):
        r = client.get("/glosas-adres/informe.xlsx", params=params)
        assert r.status_code == 200, r.text
        return openpyxl.load_workbook(io.BytesIO(r.content)), r

    def _filas(self, hoja, encabezado: int = 4) -> list[dict]:
        cols = {
            (hoja.cell(encabezado, i).value or "").strip(): i
            for i in range(1, hoja.max_column + 1)
            if hoja.cell(encabezado, i).value
        }
        salida = []
        for f in range(encabezado + 1, hoja.max_row + 1):
            if not hoja.cell(f, 1).value:
                continue
            salida.append({nombre: hoja.cell(f, i).value for nombre, i in cols.items()})
        return salida

    def _datos(self, wb) -> list[dict]:
        """Las filas de la hoja de siempre, cuyo encabezado va en la fila 1."""
        return self._filas(wb["Hoja1"], encabezado=1)

    def test_trae_las_hojas_del_informe(self, client, paquete):
        wb, _ = self._libro(client)
        assert wb.sheetnames == self.HOJAS

    def test_la_hoja_de_datos_conserva_el_formato_de_la_macro(self, client, paquete):
        """Las 26 columnas, en su orden, con el encabezado en la fila 1."""
        from app.services.preauditoria_adres import COLUMNAS_MACRO

        wb, _ = self._libro(client)
        hd = wb["Hoja1"]
        encabezado = [hd.cell(1, i).value for i in range(1, len(COLUMNAS_MACRO) + 1)]
        assert encabezado == COLUMNAS_MACRO
        # Y los datos arrancan en la 2, sin fila de título en medio.
        assert hd.cell(2, 3).value in {"HUS311371", "HUS352890"}

    def test_el_bot_de_objeciones_puede_leer_el_archivo_bajado(self, client, paquete, tmp_path):
        """La prueba de fuego: que el archivo sirva para lo de siempre.

        `organizar_objeciones_adres.py` busca la hoja de glosas por sus
        encabezados **en la primera fila**. Si el informe le pusiera un título
        arriba, el bot no encontraría nada y el auditor se quedaría sin las
        objeciones para el DGH.
        """
        organizar = pytest.importorskip("organizar_objeciones_adres")
        r = client.get("/glosas-adres/informe.xlsx")
        ruta = tmp_path / "RTA_GLOSA_ADRES.xlsx"
        ruta.write_bytes(r.content)
        filas = organizar.leer_adres(ruta)
        assert filas, "el bot de objeciones no encontró la hoja de glosas"
        assert {f.factura for f in filas} >= {"HUS311371", "HUS352890"}

    def test_el_archivo_se_baja_con_el_nombre_del_area(self, client, paquete):
        _, r = self._libro(client)
        assert "spreadsheetml" in r.headers["content-type"]
        nombre = r.headers["content-disposition"]
        assert "RTA_GLOSA_ADRES_PAQ_31068_" in nombre
        assert nombre.endswith('.xlsx"')

    def test_una_fila_por_glosa_con_lo_que_escribio_el_gestor(self, client, paquete):
        gid = client.get("/glosas-adres/factura/HUS0000352890").json()["glosas"][0]["id"]
        client.post(
            f"/glosas-adres/glosa/{gid}",
            json={
                "decision": "SE OBJETA",
                "observacion_tecnico": "SE ANEXA HOJA DE GASTO Y REGISTRO DE ENTREGA.",
            },
        )
        wb, _ = self._libro(client)
        filas = self._datos(wb)
        assert len(filas) == len(FILAS)  # todas las filas del reporte, ninguna se pierde
        objetada = [f for f in filas if f[self.DECISION] == "SE OBJETA"]
        assert len(objetada) == 1
        assert objetada[0]["OBSERVACION TECNICO / PROFESIONAL"] == (
            "SE ANEXA HOJA DE GASTO Y REGISTRO DE ENTREGA."
        )
        assert objetada[0]["QUIÉN DECIDIÓ"] == "coordinador@hus.gov.co"
        # La respuesta consolidada sale armada, como la de la macro.
        assert "SE OBJETA" in (objetada[0]["RTA GLOSA COMPLETA"] or "")

    def test_lo_que_no_se_ha_decidido_queda_en_blanco(self, client, paquete):
        """La columna de la macro solo lleva las tres decisiones, o nada."""
        wb, _ = self._libro(client)
        valores = {f[self.DECISION] for f in self._datos(wb)}
        assert valores <= {None, "SE ACEPTA", "SE OBJETA", "SE SUBSANA"}

    def test_la_plata_del_mismo_item_no_se_cuenta_dos_veces(self, client, paquete):
        """Las dos causales del TAC salen las dos, pero solo una suma."""
        wb, _ = self._libro(client)
        filas = self._datos(wb)
        tac = [f for f in filas if f["Cod Elemento"] == "DOS-1"]
        assert len(tac) == 2
        assert sorted(f["CUENTA PARA LA PLATA"] for f in tac) == ["NO", "SÍ"]
        glosado = sum(
            f["Valor Glosado"]
            for f in filas
            if f["Número Factura"] == "HUS311371" and f["CUENTA PARA LA PLATA"] == "SÍ"
        )
        # Lo mismo que muestra la pantalla: 31.800 + 700.000 + 3.400.
        assert glosado == pytest.approx(735200)

    def test_lo_aceptado_no_se_le_declara_dos_veces_al_adres(self, client, paquete):
        """Aceptar en las dos causales del mismo servicio no duplica la plata."""
        tac = [
            g
            for g in client.get("/glosas-adres/factura/HUS0000311371").json()["glosas"]
            if g["codigo"] == "DOS-1"
        ]
        for g in tac:
            client.post(
                f"/glosas-adres/glosa/{g['id']}",
                json={"decision": "SE ACEPTA", "valor_aceptado": 700000},
            )
        wb, _ = self._libro(client)
        filas = [f for f in self._datos(wb) if f["Número Factura"] == "HUS311371"]
        # Lo escrito por el gestor son 1.400.000 (dos renglones de 700.000)…
        assert sum(f["VALOR ACEPTADO"] for f in filas) == pytest.approx(1400000)
        # …pero lo que se declara es 700.000, que es lo que el ítem tiene glosado.
        assert sum(f["VALOR ACEPTADO QUE SE DECLARA"] for f in filas) == pytest.approx(700000)
        fila_factura = next(f for f in self._filas(wb["FACTURAS"]) if f["Factura"] == "HUS311371")
        assert fila_factura["Aceptado"] == pytest.approx(700000)
        assert fila_factura["Sigue glosado"] == pytest.approx(35200)

    def test_las_glosas_totales_se_marcan_y_no_cuentan_como_trabajo(self, client, paquete):
        wb, _ = self._libro(client)
        filas = self._datos(wb)
        totales = [f for f in filas if f["TIPO DE RENGLÓN"] == "GLOSA TOTAL"]
        assert {f["Cod Elemento"] for f in totales} == {"TOT-1", "TOT-2"}
        fila = next(f for f in self._filas(wb["FACTURAS"]) if f["Factura"] == "HUS311371")
        assert fila["Glosas a responder"] == 3  # las que se responden una por una
        assert fila["Glosa total (renglones)"] == 1

    def test_los_numeros_del_resumen_son_formulas_vivas(self, client, paquete):
        """Si el auditor corrige una fila, los resúmenes se recalculan solos."""
        wb, _ = self._libro(client)
        rs = wb["RESUMEN"]
        formulas = [
            rs.cell(f, c).value
            for f in range(5, 20)
            for c in (3, 4)
            if isinstance(rs.cell(f, c).value, str)
        ]
        assert formulas, "el resumen no trajo ninguna fórmula"
        assert all(v.startswith("=") for v in formulas)
        assert all("Hoja1!" in v for v in formulas if "COUNTIF" in v or "SUMIF" in v)
        assert any("COUNTIF" in v for v in formulas)
        assert any("SUMIFS" in v for v in formulas)

    def test_las_causales_salen_agrupadas_con_su_valor(self, client, paquete):
        wb, _ = self._libro(client)
        filas = self._filas(wb["POR QUÉ NOS GLOSAN"])
        causales = {str(f["Causal"]) for f in filas if f["Causal"] != "TOTAL"}
        assert {"3106", "3202", "3209", "4506"} <= causales
        soporte = next(f for f in filas if f["Causal"] == "3106")
        assert "Soporte" in (soporte["Descripción de la causal"] or "")
        assert soporte["Facturas"] == 2  # la 352890 y la 311371
        assert str(soporte["Valor glosado"]).startswith("=")  # es fórmula, no número pegado
        assert "soporte" in (soporte["Qué hace falta para responderla"] or "").lower()

    def test_el_trabajo_sin_dueno_queda_a_la_vista(self, client, paquete):
        """El reporte no trae gestor: eso tiene que verse, no desaparecer."""
        wb, _ = self._libro(client)
        gestores = {f["Gestor"] for f in self._filas(wb["POR GESTOR"]) if f["Gestor"] != "TOTAL"}
        assert "(sin gestor asignado)" in gestores

    def test_trae_sus_graficos(self, client, paquete):
        wb, _ = self._libro(client)
        assert len(wb["RESUMEN"]._charts) == 1
        assert len(wb["POR QUÉ NOS GLOSAN"]._charts) == 1
        assert len(wb["POR GESTOR"]._charts) == 1

    def test_la_factura_avisa_cuando_no_cuadra_con_el_adres(self, client):
        oficial = _archivo_facturas({"HUS352890": 590400, "HUS311371": 400000})
        r = client.post(
            "/glosas-adres/importar",
            files={
                "archivo": ("reporte.xlsx", _reporte_bytes()),
                "facturas": ("f.xlsx", oficial),
            },
        )
        wb, _ = self._libro(client, paquete_id=r.json()["paquete_id"])
        por_factura = {f["Factura"]: f for f in self._filas(wb["FACTURAS"])}
        assert por_factura["HUS352890"]["¿Cuadra?"] == "SÍ"
        assert por_factura["HUS311371"]["¿Cuadra?"] == "NO CUADRA"
        assert por_factura["HUS311371"]["Valor glosado (ADRES)"] == pytest.approx(400000)

    def test_sin_ningun_paquete_cargado_lo_dice_y_no_se_cae(self, client):
        r = client.get("/glosas-adres/informe.xlsx")
        assert r.status_code == 404
        assert "paquete" in r.json()["detail"].lower()

    def test_se_puede_pedir_un_paquete_por_su_id(self, client, paquete):
        _, r = self._libro(client, paquete_id=paquete)
        assert "31068" in r.headers["content-disposition"]

    def test_un_paquete_que_no_existe_da_404(self, client, paquete):
        r = client.get("/glosas-adres/informe.xlsx", params={"paquete_id": 999999})
        assert r.status_code == 404


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


def test_glosas_adres_reemplaza_a_cobranza_live_en_el_menu():
    """Glosas ADRES entra al menú y Cobranza Live sale, como pidió el auditor.

    Una fusión anterior las había dejado conviviendo, por prudencia. El auditor
    lo pidió de nuevo de forma explícita, así que Cobranza Live se retira del
    menú. **Solo del menú**: `loadDashCobranza()` y el endpoint
    `/glosas/stats/dashboard-cobranza` siguen vivos, para que devolver la
    pantalla sea volver a poner el botón.
    """
    html = Path(__file__).resolve().parents[2] / "static" / "index.html"
    if not html.exists():  # pragma: no cover - en algunos despliegues no se copia
        pytest.skip("static/index.html no está en este entorno")
    texto = html.read_text(encoding="utf-8", errors="ignore")
    assert "Glosas ADRES" in texto
    # Nada que la lleve al menú: ni botón, ni panel, ni pestaña, ni alias.
    assert "p-cobranza-live" not in texto
    assert "sidebarTab(this,'cobranza-live')" not in texto
    assert "tabs.push(['cobranza-live'" not in texto
    # Pero el código que la pintaba sigue ahí, para poder devolverla.
    assert "function loadDashCobranza" in texto
