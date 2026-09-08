"""La mesa de conciliación: el acta vive en el motor mientras se trabaja.

Antes el acta se bajaba en Excel y se llenaba por fuera. Una audiencia con
la EPS dura horas: si se cerraba el archivo sin guardar, o dos personas lo
abrían a la vez, el trabajo se perdía o se pisaba.

Lo que estas pruebas cuidan:

  · que lo que trajo la EPS **no se pueda editar** — si el valor objetado se
    pudiera cambiar, el acta dejaría de cuadrar con lo que la EPS mandó y la
    mesa se discutiría sobre cifras distintas;
  · que lo que decide la mesa se guarde renglón por renglón y sobreviva a
    cerrar el navegador;
  · que la contabilidad salga del DGH cuando se puede, y **no se invente**
    cuando el centro de costo no está en el catálogo;
  · que una mesa cerrada no admita cambios, y que al cerrarla se aprenda.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
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
from app.models.db import (
    ConceptoGlosaRecord,
    ConciliacionTipificacionRecord,
    MesaLineaRecord,
    UsuarioRecord,
)

MODELO = Path(__file__).resolve().parents[2] / "plantillas" / "ACTA_SINAC_modelo.xlsm"

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


def _excel(filas):
    wb = openpyxl.Workbook()
    for f in filas:
        wb.active.append(f)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _eps(*glosas):
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
                "MOTIVO",
                valor,
                "SERVICIO",
                "AR002328",
            ]
        )
    return _excel(filas)


def _lista(*facturas):
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
    usuario = UsuarioRecord(id=1, email="aud@hus.gov.co", rol="COORDINADOR", activo=1)
    app.dependency_overrides[get_db] = lambda: db
    for d in (deps.get_auditor_o_superior, deps.get_coordinador_o_admin, deps.get_usuario_actual):
        app.dependency_overrides[d] = lambda: usuario
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


def _abrir(cliente, lista, eps, **extra):
    return cliente.post(
        "/conciliaciones/mesa/abrir",
        files={"facturas": ("l.xlsx", lista), "archivo_eps": ("e.xlsx", eps)},
        data={**ENCABEZADO, **extra},
    )


# ══════════════════════════════════════════════════════════════════════════
class TestAbrirLaMesa:
    def test_el_acta_queda_guardada_con_sus_renglones(self, cliente, db):
        r = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685)))
        assert r.status_code == 201, r.text
        m = r.json()
        assert m["estado"] == "ABIERTA"
        assert m["resumen"]["lineas"] == 1
        assert db.query(MesaLineaRecord).filter_by(mesa_id=m["id"]).count() == 1

    def test_nada_llega_repartido(self, cliente):
        """Aceptar, levantar y ratificar se escriben EN la audiencia."""
        linea = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()[
            "lineas"
        ][0]
        assert (linea["acepta_ips"], linea["levanta_entidad"], linea["ratificado"]) == (0, 0, 0)
        assert linea["pendiente"] == linea["glosa_inicial"] == 6685

    def test_lo_que_falta_decidir_viene_marcado(self, cliente):
        linea = _abrir(cliente, _lista("542497"), _eps(("542497", "CL0301", 100))).json()["lineas"][
            0
        ]
        assert linea["tipo_glosa"] == ""
        assert "MIXTA" in linea["aviso"]

    def test_dos_tandas_distintas_se_rechazan_diciendo_por_que(self, cliente):
        r = _abrir(cliente, _lista("542497"), _eps(("420099", "TA0201", 1)))
        assert r.status_code == 422 and "misma tanda" in r.json()["detail"]


class TestLaContabilidadSaleDelDGH:
    def test_con_el_centro_de_costo_cargado_se_llena_sola(self, cliente, db):
        db.add(
            ConceptoGlosaRecord(
                glosa_id=1,
                factura="HUS0000542497",
                codigo_glosa="TA0201",
                centro_costo="732101 - UCI ADULTOS",
            )
        )
        db.commit()
        linea = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()[
            "lineas"
        ][0]
        assert linea["centro_costo"] == "732101 - UCI ADULTOS"
        assert linea["cuenta_contable"] == "43122801"
        # 020 es el concepto de ACTAS. El de glosa inicial (004) sería otro
        # asiento: una conciliación es siempre por acta.
        assert linea["concepto_nota"] == "020"

    def test_un_centro_que_no_esta_en_el_catalogo_no_se_inventa(self, cliente, db):
        """El DGH maneja más centros que el catálogo de contabilidad.
        Acercarlo al más parecido sería un asiento mal hecho."""
        db.add(
            ConceptoGlosaRecord(
                glosa_id=1,
                factura="HUS0000542497",
                codigo_glosa="TA0201",
                centro_costo="734005 - LABORATORIO - INMUNOLOGIA",
            )
        )
        db.commit()
        linea = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()["lineas"][
            0
        ]
        assert linea["centro_costo"] == "734005 - LABORATORIO - INMUNOLOGIA"
        assert linea["cuenta_contable"] == "" and linea["concepto_nota"] == ""

    def test_sin_dato_del_dgh_las_tres_van_vacias(self, cliente):
        linea = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()["lineas"][
            0
        ]
        assert (linea["centro_costo"], linea["cuenta_contable"]) == ("", "")


class TestTrabajarLaMesa:
    def _una(self, cliente):
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()
        return m["id"], m["lineas"][0]["id"]

    def test_lo_que_se_escribe_se_guarda_y_sobrevive(self, cliente):
        mid, lid = self._una(cliente)
        r = cliente.patch(
            f"/conciliaciones/mesa/{mid}/linea/{lid}",
            json={"levanta_entidad": 6685, "texto_conciliacion": "SE LEVANTA LA GLOSA"},
        )
        assert r.status_code == 200 and r.json()["pendiente"] == 0

        # Como si el auditor cerrara el navegador y volviera.
        linea = cliente.get(f"/conciliaciones/mesa/{mid}").json()["lineas"][0]
        assert linea["levanta_entidad"] == 6685
        assert linea["texto_conciliacion"] == "SE LEVANTA LA GLOSA"

    def test_lo_que_trajo_la_eps_no_se_puede_cambiar(self, cliente):
        """El valor objetado y el código son de la EPS. Si se pudieran editar,
        el acta dejaría de cuadrar con lo que ella mandó."""
        mid, lid = self._una(cliente)
        cliente.patch(
            f"/conciliaciones/mesa/{mid}/linea/{lid}",
            json={"glosa_inicial": 1, "cod_glosa": "XX9999", "factura": "OTRA"},
        )
        linea = cliente.get(f"/conciliaciones/mesa/{mid}").json()["lineas"][0]
        assert linea["glosa_inicial"] == 6685
        assert linea["cod_glosa"] == "TA0201"

    def test_el_resumen_se_recalcula_a_cada_cambio(self, cliente):
        mid, lid = self._una(cliente)
        r = cliente.patch(f"/conciliaciones/mesa/{mid}/linea/{lid}", json={"acepta_ips": 6685})
        assert r.json()["resumen"]["acepta_ips"] == 6685
        assert r.json()["resumen"]["sin_repartir"] == 0

    def test_se_puede_repartir_de_mas_sin_que_el_motor_estorbe(self, cliente):
        """En una mesa se tantea y se corrige. Bloquear a mitad de una
        negociación molesta; el descuadre se ve en el pendiente."""
        mid, lid = self._una(cliente)
        r = cliente.patch(f"/conciliaciones/mesa/{mid}/linea/{lid}", json={"ratificado": 99999})
        assert r.status_code == 200 and r.json()["pendiente"] < 0

    def test_resolver_el_tipo_le_quita_el_aviso(self, cliente):
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "CL0301", 100))).json()
        assert m["lineas"][0]["aviso"]
        cliente.patch(
            f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}",
            json={"tipo_glosa": "MEDICO"},
        )
        assert cliente.get(f"/conciliaciones/mesa/{m['id']}").json()["lineas"][0]["aviso"] == ""

    def test_un_renglon_de_otra_mesa_no_se_toca(self, cliente):
        mid_a, _ = self._una(cliente)
        _, lid_b = self._una(cliente)
        r = cliente.patch(f"/conciliaciones/mesa/{mid_a}/linea/{lid_b}", json={"acepta_ips": 1})
        assert r.status_code == 404


class TestCerrarYReabrir:
    def _una(self, cliente):
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()
        return m["id"], m["lineas"][0]["id"]

    def test_al_cerrar_se_aprende_la_tipificacion(self, cliente, db):
        mid, _ = self._una(cliente)
        r = cliente.post(f"/conciliaciones/mesa/{mid}/cerrar")
        assert r.status_code == 200 and r.json()["aprendido"]["nuevas"] == 1
        fila = db.query(ConciliacionTipificacionRecord).one()
        assert (fila.factura_clave, fila.cod_glosa, fila.tipo_glosa) == (
            "542497",
            "TA0201",
            "ADMINISTRATIVA",
        )

    def test_una_mesa_cerrada_no_admite_cambios(self, cliente):
        mid, lid = self._una(cliente)
        cliente.post(f"/conciliaciones/mesa/{mid}/cerrar")
        r = cliente.patch(f"/conciliaciones/mesa/{mid}/linea/{lid}", json={"acepta_ips": 1})
        assert r.status_code == 409

    def test_se_puede_cerrar_con_renglones_pendientes(self, cliente):
        """Hay actas que quedan a medias para una segunda sesión. Se cierra,
        pero el parte dice cuántos quedaron."""
        mid, _ = self._una(cliente)
        r = cliente.post(f"/conciliaciones/mesa/{mid}/cerrar")
        assert r.json()["resumen"]["sin_repartir"] == 1

    def test_si_la_memoria_falla_la_mesa_SE_CIERRA_IGUAL(self, cliente, monkeypatch):
        """Aprender es un extra; cerrar es lo que el auditor vino a hacer.

        Caso real (07-09-2026): en el PC del hospital cerrar contestó «no se
        pudo» sobre una mesa de 146 renglones ya trabajada. La audiencia
        terminada y el acta sin cerrar por un accesorio.
        """
        from app.services import acta_conciliacion_armar as armador

        mid, _ = self._una(cliente)

        def revienta(*a, **kw):
            raise RuntimeError("no such table: conciliacion_tipificacion")

        monkeypatch.setattr(armador, "aprender", revienta)
        r = cliente.post(f"/conciliaciones/mesa/{mid}/cerrar")
        assert r.status_code == 200
        assert r.json()["estado"] == "CERRADA"
        # Y se dice qué pasó, en vez de fingir que se guardó.
        assert "no se pudo guardar la tipificación" in r.json()["aviso_memoria"]
        assert "conciliacion_tipificacion" in r.json()["aviso_memoria"]

    def test_y_queda_cerrada_de_verdad(self, cliente, monkeypatch):
        from app.services import acta_conciliacion_armar as armador

        mid, lid = self._una(cliente)
        monkeypatch.setattr(
            armador, "aprender", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("x"))
        )
        cliente.post(f"/conciliaciones/mesa/{mid}/cerrar")
        assert (
            cliente.patch(
                f"/conciliaciones/mesa/{mid}/linea/{lid}", json={"acepta_ips": 1}
            ).status_code
            == 409
        )

    def test_reabrir_devuelve_la_mesa_al_trabajo(self, cliente):
        mid, lid = self._una(cliente)
        cliente.post(f"/conciliaciones/mesa/{mid}/cerrar")
        assert cliente.post(f"/conciliaciones/mesa/{mid}/reabrir").status_code == 200
        assert (
            cliente.patch(
                f"/conciliaciones/mesa/{mid}/linea/{lid}", json={"acepta_ips": 1}
            ).status_code
            == 200
        )

    def test_lo_aprendido_llena_la_proxima_mesa(self, cliente):
        """«Son las mismas cuentas de siempre»: lo que decidió el médico
        auditor no se vuelve a preguntar."""
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "CL0301", 100))).json()
        cliente.patch(
            f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}",
            json={"tipo_glosa": "MEDICO"},
        )
        cliente.post(f"/conciliaciones/mesa/{m['id']}/cerrar")

        otra = _abrir(cliente, _lista("542497"), _eps(("542497", "CL0301", 100))).json()
        assert otra["lineas"][0]["tipo_glosa"] == "MEDICO"
        assert otra["lineas"][0]["aviso"] == ""


class TestElDetalleParaRefutarEnLaMesa:
    """Cuando la EPS sostiene una glosa: ¿qué tenemos para refutarla?"""

    def _con_glosa_en_el_motor(self, cliente, db):
        from app.models.db import GlosaRecord

        db.add(
            GlosaRecord(
                eps="COOSALUD",
                factura="HUS0000542497",
                codigo_glosa="TA0201",
                valor_objetado=6685,
                estado="PENDIENTE",
                workflow_state="RESPONDIDA",
                etapa="OBJECION",
                dictamen="<div>ESE HUS NO ACEPTA LA GLOSA</div>",
            )
        )
        db.commit()
        return _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()

    def test_el_renglon_se_enlaza_con_la_glosa_del_motor(self, cliente, db):
        m = self._con_glosa_en_el_motor(cliente, db)
        d = cliente.get(f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}").json()
        assert d["glosa_id"]
        assert d["glosa"]["dictamen"], "sin el dictamen no hay con qué refutar en la mesa"
        assert d["glosa"]["workflow_state"] == "RESPONDIDA"

    def test_una_glosa_que_el_motor_no_tiene_lo_dice_sin_fallar(self, cliente):
        """Hay facturas que la EPS glosa y que nunca entraron por recepción."""
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()
        d = cliente.get(f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}").json()
        assert d["glosa_id"] is None and d["glosa"] is None
        assert "no está en el historial del motor" in d["nota"]

    def test_el_enlace_respeta_el_codigo_no_solo_la_factura(self, cliente, db):
        """Una factura tiene varias glosas: traerse la primera sería mostrar
        el historial de otra."""
        from app.models.db import GlosaRecord

        db.add(
            GlosaRecord(
                eps="X",
                factura="HUS0000542497",
                codigo_glosa="SO9999",
                valor_objetado=1,
                estado="P",
                dictamen="OTRA COSA",
            )
        )
        db.commit()
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()
        d = cliente.get(f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}").json()
        assert d["glosa_id"] is None, "se enlazó a una glosa de otro código"

    def test_los_soportes_dicen_cual_de_los_tres_estados(self, cliente):
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()
        d = cliente.get(f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}").json()
        assert d["soportes"]["estado"] in (
            "CON_SOPORTES",
            "SIN_SOPORTES",
            "INDEXANDO",
            "SIN_INDICE",
        )

    def test_el_soporte_llega_con_su_nombre_y_no_en_blanco(self, cliente, monkeypatch):
        """El indexador contesta con DICCIONARIOS, no con objetos.

        Si se leen con `getattr` en vez de `.get`, el cajón muestra la
        cantidad correcta pero la lista sale con los nombres vacíos: el
        auditor ve «3 soportes» y tres renglones en blanco, y en una
        audiencia eso es lo mismo que no tener nada.
        """
        from app.services import soportes_autodiscovery_service as sas

        class _IndiceFalso:
            def stats(self):
                return {"construyendo": False}

            def lookup(self, factura, auto_rebuild=True):
                return [
                    {
                        "nombre_archivo": "FEV-HUS542497.pdf",
                        "tipo": "factura_electronica",
                        "tipo_codigo": "FEV",
                        "tamano_kb": 210,
                        "ruta": "/soportes/FEV-HUS542497.pdf",
                    }
                ]

        monkeypatch.setattr(sas, "get_indexer", lambda: _IndiceFalso())
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()
        d = cliente.get(f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}").json()

        sop = d["soportes"]
        assert sop["estado"] == "CON_SOPORTES" and sop["cuantos"] == 1
        assert sop["archivos"][0]["nombre"] == "FEV-HUS542497.pdf"
        assert sop["archivos"][0]["tipo_codigo"] == "FEV"

    def test_los_soportes_de_la_mesa_se_piden_por_factura_no_por_renglon(self, cliente):
        """Una factura con doce glosas comparte sus soportes."""
        m = _abrir(
            cliente,
            _lista("542497"),
            _eps(("542497", "TA0201", 100), ("542497", "SO3601", 200)),
        ).json()
        s = cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes").json()
        assert len(s) == 1 and "HUS0000542497" in s

    def test_un_renglon_de_otra_mesa_no_se_puede_espiar(self, cliente, db):
        a = self._con_glosa_en_el_motor(cliente, db)
        b = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()
        r = cliente.get(f"/conciliaciones/mesa/{a['id']}/linea/{b['lineas'][0]['id']}")
        assert r.status_code == 404


class TestComentariosDelEquipo:
    def test_se_guardan_contra_la_glosa_para_que_sirvan_la_proxima_vez(self, cliente, db):
        from app.models.db import ComentarioGlosaRecord, GlosaRecord

        db.add(
            GlosaRecord(
                eps="COOSALUD",
                factura="HUS0000542497",
                codigo_glosa="TA0201",
                valor_objetado=6685,
                estado="P",
                dictamen="<div>X</div>",
            )
        )
        db.commit()
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()
        lid = m["lineas"][0]["id"]

        r = cliente.post(
            f"/conciliaciones/mesa/{m['id']}/linea/{lid}/comentario",
            json={"texto": "La EPS insiste; buscar la factura de compra."},
        )
        assert r.status_code == 201
        # Contra la glosa, no contra la mesa: la misma glosa puede volver a
        # otra audiencia y lo anotado sirve las dos veces.
        assert db.query(ComentarioGlosaRecord).one().glosa_id == r.json()["glosa_id"]

        d = cliente.get(f"/conciliaciones/mesa/{m['id']}/linea/{lid}").json()
        assert d["comentarios"][0]["texto"].startswith("La EPS insiste")
        assert d["comentarios"][0]["autor"] == "aud@hus.gov.co"

    def test_sin_glosa_enlazada_se_explica_en_vez_de_perder_el_comentario(self, cliente):
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()
        r = cliente.post(
            f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}/comentario",
            json={"texto": "algo"},
        )
        assert r.status_code == 409
        assert "no está enlazado" in r.json()["detail"]

    def test_un_comentario_vacio_se_rechaza(self, cliente):
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()
        r = cliente.post(
            f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}/comentario",
            json={"texto": "   "},
        )
        assert r.status_code in (409, 422)


@pytest.mark.skipif(not MODELO.is_file(), reason="falta el modelo del acta")
class TestElActaQueSaleDeLaMesa:
    def test_sale_con_lo_conciliado_y_con_macros(self, cliente):
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 6685))).json()
        cliente.patch(
            f"/conciliaciones/mesa/{m['id']}/linea/{m['lineas'][0]['id']}",
            json={"levanta_entidad": 6685, "texto_conciliacion": "SE LEVANTA"},
        )
        r = cliente.get(f"/conciliaciones/mesa/{m['id']}/acta.xlsm")
        assert r.status_code == 200
        assert any("vbaProject" in n for n in zipfile.ZipFile(io.BytesIO(r.content)).namelist())

        from app.services.acta_conciliacion_excel import leer_acta, revisar

        acta = leer_acta(r.content)
        assert acta.lineas[0].levanta_entidad == 6685
        assert acta.lineas[0].resultado == "LEVANTADA TOTAL"
        assert revisar(acta)["hallazgos"] == []

    def test_una_mesa_cerrada_igual_se_puede_descargar(self, cliente):
        """El acta se firma DESPUÉS de cerrar: bloquear la descarga sería
        dejar la audiencia sin su documento."""
        m = _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()
        cliente.post(f"/conciliaciones/mesa/{m['id']}/cerrar")
        assert cliente.get(f"/conciliaciones/mesa/{m['id']}/acta.xlsm").status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Subir soportes EN la mesa
# ═══════════════════════════════════════════════════════════════════════

_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def _subir(cliente, mesa_id, nombre, datos, mime, factura="HUS0000542497", nota=""):
    return cliente.post(
        f"/conciliaciones/mesa/{mesa_id}/soportes-subidos",
        files={"archivo": (nombre, datos, mime)},
        data={"factura": factura, "nota": nota},
    )


@pytest.fixture(autouse=True)
def carpeta_de_soportes_aparte(tmp_path, monkeypatch):
    """Los archivos de prueba NO se escriben en el repositorio.

    Sin esto, la suite dejaba 47 MB de PDF de mentiras en `data/`, que es
    donde el motor de verdad guarda los soportes del hospital.
    """
    monkeypatch.setenv("SOPORTES_MESA_ROOT", str(tmp_path / "soportes_mesa"))
    yield


class TestDondeQuedanLosArchivos:
    """El motor se actualiza solo cada cinco minutos.

    Si los soportes cayeran en una ruta del contenedor y no en el volumen
    persistente, la evidencia de una audiencia duraría minutos.
    """

    def test_van_al_volumen_persistente_del_hospital(self, monkeypatch, tmp_path):
        from app.services import mesa_conciliacion as svc

        monkeypatch.delenv("SOPORTES_MESA_ROOT", raising=False)
        # Es lo que el docker-compose del hospital le pone al contenedor.
        monkeypatch.setenv("SOPORTES_ROOT", str(tmp_path / "data" / "soportes"))
        carpeta = svc.carpeta_de_soportes()
        assert carpeta == tmp_path / "data" / "soportes_mesa", (
            "los soportes tienen que quedar junto a la base, en /data — el volumen "
            "que sobrevive a las actualizaciones"
        )
        assert carpeta.is_dir()

    def test_se_puede_mandar_a_otra_carpeta_a_proposito(self, monkeypatch, tmp_path):
        from app.services import mesa_conciliacion as svc

        monkeypatch.setenv("SOPORTES_MESA_ROOT", str(tmp_path / "otra"))
        assert svc.carpeta_de_soportes() == tmp_path / "otra"


class TestSubirSoportesEnLaMesa:
    """El indexador solo LEE lo ya archivado. Lo que aparece en la audiencia
    —el correo del médico, la autorización que la EPS pide en el momento—
    no está ahí y no puede esperar a la próxima pasada del indexador."""

    def _mesa(self, cliente):
        return _abrir(cliente, _lista("542497"), _eps(("542497", "TA0201", 100))).json()

    def test_un_pdf_entra_y_se_puede_volver_a_bajar(self, cliente):
        m = self._mesa(cliente)
        r = _subir(
            cliente, m["id"], "autorizacion.pdf", _PDF, "application/pdf", nota="La autorización"
        )
        assert r.status_code == 201, r.text
        subido = r.json()
        assert subido["nombre"] == "autorizacion.pdf"
        assert subido["tamano_bytes"] == len(_PDF)
        assert subido["subido_por"], "hay que dejar constancia de quién lo subió"

        listado = cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes-subidos").json()
        assert len(listado) == 1 and listado[0]["nota"] == "La autorización"

        bajado = cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes-subidos/{subido['id']}")
        assert bajado.status_code == 200
        assert bajado.content == _PDF, "lo que se baja tiene que ser lo mismo que se subió"

    def test_una_imagen_tambien(self, cliente):
        m = self._mesa(cliente)
        assert _subir(cliente, m["id"], "foto.png", _PNG, "image/png").status_code == 201

    def test_un_excel_se_rechaza_con_su_motivo(self, cliente):
        """Solo PDF e imágenes. Un Excel hay que pasarlo antes a PDF."""
        m = self._mesa(cliente)
        r = _subir(
            cliente,
            m["id"],
            "glosas.xlsx",
            b"PK\x03\x04algo",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        assert r.status_code == 422
        detalle = r.json()["detail"]
        assert "PDF" in detalle and "imágenes" in detalle
        assert "glosas.xlsx" in detalle, "el motivo tiene que nombrar el archivo"

    def test_un_ejecutable_disfrazado_de_pdf_no_pasa(self, cliente):
        """El content-type lo manda el navegador y se puede poner a mano."""
        m = self._mesa(cliente)
        r = _subir(cliente, m["id"], "virus.pdf", b"MZ\x90\x00" + b"\x00" * 50, "application/pdf")
        assert r.status_code == 422
        assert "no lo es" in r.json()["detail"]

    def test_un_escaneo_de_los_de_verdad_entra(self, cliente):
        """Los escaneos de cartera pesan entre 25 y 40 MB.

        El tope nació en 15 MB —un número que puse yo, no un dato— y los
        dejaba a TODOS afuera. Esta prueba es la que impide que alguien lo
        vuelva a bajar sin darse cuenta.
        """
        m = self._mesa(cliente)
        escaneo = _PDF + b"\x00" * (30 * 1024 * 1024)
        r = _subir(cliente, m["id"], "historia_escaneada.pdf", escaneo, "application/pdf")
        assert r.status_code == 201, r.text
        assert r.json()["tamano_bytes"] == len(escaneo)

    def test_un_archivo_muy_pesado_se_rechaza_diciendo_cuanto_pesa(self, cliente, monkeypatch):
        """Se baja el tope a propósito para no mover 50 MB en una prueba."""
        from app.services import mesa_conciliacion as svc

        monkeypatch.setattr(svc, "MAX_BYTES_SOPORTE", 2 * 1024 * 1024)
        m = self._mesa(cliente)
        grande = _PDF + b"\x00" * (3 * 1024 * 1024)
        r = _subir(cliente, m["id"], "escaneo.pdf", grande, "application/pdf")
        assert r.status_code == 422
        detalle = r.json()["detail"]
        assert "MB" in detalle and "escaneo.pdf" in detalle
        assert "Herramientas PDF" in detalle, "hay que decirle cómo bajarle el peso"

    def test_lo_que_pasa_del_tope_no_queda_ocupando_disco(self, cliente, monkeypatch):
        """Se corta MIENTRAS se escribe; lo escrito a medias se borra."""
        from app.services import mesa_conciliacion as svc

        monkeypatch.setattr(svc, "MAX_BYTES_SOPORTE", 2 * 1024 * 1024)
        m = self._mesa(cliente)
        antes = sum(1 for _ in svc.carpeta_de_soportes().rglob("*") if _.is_file())
        _subir(
            cliente, m["id"], "enorme.pdf", _PDF + b"\x00" * (5 * 1024 * 1024), "application/pdf"
        )
        despues = sum(1 for _ in svc.carpeta_de_soportes().rglob("*") if _.is_file())
        assert despues == antes, "quedó un archivo a medio escribir ocupando disco"

    def test_el_archivo_no_se_guarda_en_la_base(self, cliente, db):
        """Un escaneo de 40 MB en base64 son 53 MB de texto.

        El contenedor del hospital corre con 640 MB y su propio compose
        documenta que el OOM killer ya mató procesos. Guardarlos en la base
        obligaba a cargarlos enteros hasta para listarlos.
        """
        from app.models.db import SoporteMesaRecord

        m = self._mesa(cliente)
        subido = _subir(cliente, m["id"], "a.pdf", _PDF, "application/pdf").json()
        reg = db.query(SoporteMesaRecord).filter(SoporteMesaRecord.id == subido["id"]).first()
        assert not reg.contenido_b64, "el contenido no puede quedar en la base"
        assert reg.ruta_relativa, "tiene que decir dónde quedó el archivo"
        assert len(reg.sha256 or "") == 64, "sin resumen no se puede saber si se dañó"

    def test_listar_no_lee_el_contenido_de_los_archivos(self, cliente, db):
        """Listar diez soportes de 40 MB no puede cargar 400 MB a memoria."""
        from app.models.db import SoporteMesaRecord

        m = self._mesa(cliente)
        _subir(cliente, m["id"], "a.pdf", _PDF, "application/pdf")
        # Se simula un soporte VIEJO, de los que sí tienen el contenido en la
        # base: listar no lo debe traer.
        db.add(
            SoporteMesaRecord(
                mesa_id=m["id"],
                factura="HUS0000542497",
                nombre="viejo.pdf",
                mime_type="application/pdf",
                tamano_bytes=10,
                contenido_b64="X" * 200000,
            )
        )
        db.commit()
        listado = cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes-subidos").json()
        assert len(listado) == 2
        for fila in listado:
            assert "contenido_b64" not in fila, "el contenido no puede salir en el listado"

    def test_un_soporte_viejo_de_la_base_todavia_se_puede_bajar(self, cliente, db):
        """Lo que ya se subió antes del cambio no se puede perder."""
        import base64

        from app.models.db import SoporteMesaRecord

        m = self._mesa(cliente)
        reg = SoporteMesaRecord(
            mesa_id=m["id"],
            factura="HUS0000542497",
            nombre="antiguo.pdf",
            mime_type="application/pdf",
            tamano_bytes=len(_PDF),
            contenido_b64=base64.b64encode(_PDF).decode("ascii"),
        )
        db.add(reg)
        db.commit()
        db.refresh(reg)
        r = cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes-subidos/{reg.id}")
        assert r.status_code == 200 and r.content == _PDF

    def test_si_el_archivo_desaparecio_del_disco_se_dice_claro(self, cliente, db):
        from app.models.db import SoporteMesaRecord
        from app.services import mesa_conciliacion as svc

        m = self._mesa(cliente)
        subido = _subir(cliente, m["id"], "a.pdf", _PDF, "application/pdf").json()
        reg = db.query(SoporteMesaRecord).filter(SoporteMesaRecord.id == subido["id"]).first()
        (svc.carpeta_de_soportes() / reg.ruta_relativa).unlink()
        r = cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes-subidos/{subido['id']}")
        assert r.status_code == 404
        assert "volver a cargarlo" in r.json()["detail"]

    def test_al_borrarlo_tambien_se_va_el_archivo(self, cliente, db):
        from app.models.db import SoporteMesaRecord
        from app.services import mesa_conciliacion as svc

        m = self._mesa(cliente)
        subido = _subir(cliente, m["id"], "a.pdf", _PDF, "application/pdf").json()
        reg = db.query(SoporteMesaRecord).filter(SoporteMesaRecord.id == subido["id"]).first()
        ruta = svc.carpeta_de_soportes() / reg.ruta_relativa
        assert ruta.is_file()
        cliente.delete(f"/conciliaciones/mesa/{m['id']}/soportes-subidos/{subido['id']}")
        assert not ruta.exists(), "el archivo quedó ocupando disco para siempre"

    def test_el_nombre_del_usuario_no_escribe_fuera_de_la_carpeta(self, cliente, db):
        """Un nombre con `../` no puede sacar el archivo de su sitio."""
        from app.models.db import SoporteMesaRecord
        from app.services import mesa_conciliacion as svc

        m = self._mesa(cliente)
        subido = _subir(cliente, m["id"], "../../../etc/pasado.pdf", _PDF, "application/pdf").json()
        reg = db.query(SoporteMesaRecord).filter(SoporteMesaRecord.id == subido["id"]).first()
        destino = (svc.carpeta_de_soportes() / reg.ruta_relativa).resolve()
        assert destino.is_relative_to(svc.carpeta_de_soportes().resolve())

    def test_un_archivo_vacio_se_rechaza(self, cliente):
        m = self._mesa(cliente)
        r = _subir(cliente, m["id"], "vacio.pdf", b"", "application/pdf")
        assert r.status_code == 422
        assert "vac" in r.json()["detail"].lower()

    def test_sin_factura_no_se_guarda(self, cliente):
        m = self._mesa(cliente)
        r = _subir(cliente, m["id"], "x.pdf", _PDF, "application/pdf", factura="   ")
        assert r.status_code == 422

    def test_los_soportes_se_filtran_por_factura(self, cliente):
        m = _abrir(
            cliente,
            _lista("542497", "542498"),
            _eps(("542497", "TA0201", 100), ("542498", "SO3601", 200)),
        ).json()
        _subir(cliente, m["id"], "a.pdf", _PDF, "application/pdf", factura="HUS0000542497")
        _subir(cliente, m["id"], "b.pdf", _PDF, "application/pdf", factura="HUS0000542498")
        r = cliente.get(
            f"/conciliaciones/mesa/{m['id']}/soportes-subidos?factura=HUS0000542497"
        ).json()
        assert len(r) == 1 and r[0]["nombre"] == "a.pdf"

    def test_una_mesa_cerrada_no_recibe_soportes(self, cliente):
        """El acta ya se firmó: meterle evidencia después la descuadra."""
        m = self._mesa(cliente)
        linea = m["lineas"][0]
        cliente.patch(
            f"/conciliaciones/mesa/{m['id']}/linea/{linea['id']}",
            json={"valor_aceptado": 100, "tipo_glosa": "ADMINISTRATIVA"},
        )
        cliente.post(f"/conciliaciones/mesa/{m['id']}/cerrar")
        r = _subir(cliente, m["id"], "tarde.pdf", _PDF, "application/pdf")
        assert r.status_code == 409
        assert "cerrada" in r.json()["detail"].lower()

    def test_no_se_pueden_espiar_los_soportes_de_otra_mesa(self, cliente):
        """Cambiar el número en la dirección no puede abrir otra audiencia."""
        a = self._mesa(cliente)
        b = self._mesa(cliente)
        subido = _subir(cliente, a["id"], "reservado.pdf", _PDF, "application/pdf").json()
        r = cliente.get(f"/conciliaciones/mesa/{b['id']}/soportes-subidos/{subido['id']}")
        assert r.status_code == 404

    def test_un_soporte_subido_por_error_se_puede_quitar(self, cliente):
        m = self._mesa(cliente)
        subido = _subir(cliente, m["id"], "equivocado.pdf", _PDF, "application/pdf").json()
        assert (
            cliente.delete(
                f"/conciliaciones/mesa/{m['id']}/soportes-subidos/{subido['id']}"
            ).status_code
            == 200
        )
        assert cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes-subidos").json() == []

    def test_el_nombre_no_puede_romper_la_cabecera_al_bajarlo(self, cliente):
        """Un nombre con comillas o saltos de línea inyecta otra cabecera."""
        m = self._mesa(cliente)
        subido = _subir(
            cliente, m["id"], 'malo";\r\nX-Inyectado: si.pdf', _PDF, "application/pdf"
        ).json()
        r = cliente.get(f"/conciliaciones/mesa/{m['id']}/soportes-subidos/{subido['id']}")
        assert r.status_code == 200
        assert "x-inyectado" not in {k.lower() for k in r.headers}
        assert "\r" not in r.headers.get("content-disposition", "")
