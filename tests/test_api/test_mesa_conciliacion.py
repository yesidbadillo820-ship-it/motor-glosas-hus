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
