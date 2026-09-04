"""El endpoint con el RIPS real y el tablero de prevención (04-09-2026).

Dos cosas que esta suite protege:

1. **Que el HIS pueda hablarnos como habla.** `POST /pre-auditoria/evaluar`
   recibe el RIPS de la Resolución 2275/2023 tal cual, sin que el hospital
   tenga que transformar nada. Se prueba con el archivo real que entregó el
   HIS, no con uno inventado.

2. **Que la cifra de «dinero salvado» sea defendible ante gerencia.** Solo
   cuenta lo que de verdad se corrigió: una factura que fue BLOQUEADA y
   después volvió a pasar. Una bloqueada que nunca volvió NO se cuenta —no
   sabemos si la corrigieron o si la timbraron igual—, y va aparte en
   `riesgo_sin_resolver`. Inflar esa cifra sería la forma más rápida de que
   nadie vuelva a creerle al tablero.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database import Base, get_db
from app.models.db import PreAuditoriaEventoRecord, UsuarioRecord

RAIZ = Path(__file__).resolve().parents[2]
FIXTURE = RAIZ / "tests" / "fixtures" / "rips" / "Rips_HUS558039.json"
TOKEN_HIS = "token-del-his-para-pruebas-0123456789"


@pytest.fixture(scope="module")
def rips_real() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


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
def cliente(db, monkeypatch):
    from app.api import deps
    from app.main import app

    monkeypatch.setenv("AGENTE_LOTES_TOKEN", TOKEN_HIS)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    get_settings.cache_clear()
    auditor = UsuarioRecord(id=1, email="auditor@hus.gov.co", rol="AUDITOR", activo=1)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[deps.get_auditor_o_superior] = lambda: auditor
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def evaluar(cliente, cuerpo):
    return cliente.post(
        "/pre-auditoria/evaluar", json=cuerpo, headers={"X-Agente-Token": TOKEN_HIS}
    )


# ═══════════════════════════════════════════════════════════════════════
class TestElHisHablaRips:
    def test_el_archivo_real_del_hospital_se_evalua(self, cliente, rips_real):
        r = evaluar(cliente, rips_real)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["factura"] == "HUS558039"
        assert d["valor_factura"] == 117300
        assert d["status"] in ("APROBADO", "ADVERTENCIA", "BLOQUEO")

    def test_una_consulta_limpia_pasa(self, cliente, rips_real):
        d = evaluar(cliente, rips_real).json()
        assert d["status"] == "APROBADO", d["alertas"]
        assert d["recomendacion_accion"] == "TIMBRAR"

    def test_sin_notas_clinicas_la_ia_se_omite_sin_abortar(self, cliente, rips_real):
        """El RIPS nunca trae texto narrativo. Eso NO puede detener nada."""
        d = evaluar(cliente, rips_real).json()
        assert d["cruce_clinico"]["estado"] == "OMITIDO_SIN_NOTAS"
        assert d["status"] == "APROBADO"  # no se ensucia con una advertencia

    def test_la_respuesta_dice_que_no_pudo_revisar(self, cliente, rips_real):
        d = evaluar(cliente, rips_real).json()
        texto = " ".join(d["omisiones"])
        assert "EPS" in texto and "notas clínicas" in texto

    def test_el_contrato_de_salida_no_cambio(self, cliente, rips_real):
        d = evaluar(cliente, rips_real).json()
        assert {"status", "alertas", "valor_en_riesgo", "recomendacion_accion"} <= set(d)

    def test_queda_la_fila_en_el_libro(self, cliente, db, rips_real):
        d = evaluar(cliente, rips_real).json()
        fila = db.get(PreAuditoriaEventoRecord, d["evento_id"])
        assert fila.factura == "HUS558039"
        assert fila.cruce_clinico_estado == "OMITIDO_SIN_NOTAS"
        # El payload queda tal como llegó, para poder repetir la evaluación.
        assert json.loads(fila.payload_base)["items"][0]["cups"] == "890264"

    def test_un_rips_sin_numero_de_factura_se_rechaza(self, cliente, rips_real):
        cuerpo = dict(rips_real)
        cuerpo.pop("numFactura")
        assert evaluar(cliente, cuerpo).status_code == 422

    def test_la_forma_interna_sigue_funcionando(self, cliente):
        """El endpoint no rompe a quien ya lo llamaba con la otra forma."""
        r = evaluar(
            cliente,
            {
                "factura": "HUS000111",
                "eps": "COOSALUD",
                "items": [{"cups": "890201", "valor_unitario": 60000, "valor_total": 60000}],
                "valor_total": 60000,
            },
        )
        assert r.status_code == 200
        assert r.json()["factura"] == "HUS000111"


class TestElRipsSeCruzaConLasReglas:
    """Las nueve reglas duras siguen mandando: el RIPS solo cambia la puerta."""

    def _rips_con(self, servicios, **kw):
        base = {
            "numFactura": "HUS900010",
            "usuarios": [
                {
                    "numDocumentoIdentificacion": "10000000001",
                    "codSexo": "M",
                    "fechaNacimiento": "1985-03-01",
                    "servicios": servicios,
                }
            ],
        }
        base.update(kw)
        return base

    def test_un_parto_en_un_paciente_masculino_se_bloquea(self, cliente):
        d = evaluar(
            cliente,
            self._rips_con(
                {
                    "procedimientos": [
                        {
                            "codProcedimiento": "740101",
                            "grupoServicios": "04",
                            "vrServicio": 800000,
                            "fechaInicioAtencion": "2026-08-24 10:00",
                        }
                    ]
                }
            ),
        ).json()
        assert d["status"] == "BLOQUEO"
        assert d["recomendacion_accion"] == "CORREGIR_ANTES_DE_TIMBRAR"
        assert any(a["regla"] == "cruce_genero" for a in d["alertas"])
        assert d["valor_en_riesgo"] == 800000

    def test_dos_vias_para_la_misma_cirugia_se_bloquean(self, cliente):
        d = evaluar(
            cliente,
            self._rips_con(
                {
                    "procedimientos": [
                        {
                            "codProcedimiento": "511001",
                            "grupoServicios": "04",
                            "vrServicio": 1800000,
                            "fechaInicioAtencion": "2026-08-24 10:00",
                        },
                        {
                            "codProcedimiento": "511002",
                            "grupoServicios": "04",
                            "vrServicio": 2400000,
                            "fechaInicioAtencion": "2026-08-24 10:00",
                        },
                    ]
                }
            ),
        ).json()
        assert d["status"] == "BLOQUEO"
        assert any(a["regla"] == "vias_quirurgicas" for a in d["alertas"])

    def test_uci_sin_criterio_en_las_notas_advierte(self, cliente):
        cuerpo = self._rips_con(
            {
                "hospitalizacion": [
                    {
                        "fechaInicioAtencion": "2026-08-20 10:00",
                        "fechaEgreso": "2026-08-25 10:00",
                        "codDiagnosticoPrincipal": "A419",
                    }
                ],
                "otrosServicios": [
                    {
                        "tipoOS": "03",
                        "codTecnologiaSalud": "S11201",
                        "nomTecnologiaSalud": "ESTANCIA EN UCI ADULTOS",
                        "cantidadOS": 3,
                        "vrUnitOS": 1500000,
                        "vrServicio": 4500000,
                    }
                ],
            },
            notasClinicas="Paciente estable, evoluciona bien, tolera vía oral.",
        )
        d = evaluar(cliente, cuerpo).json()
        assert d["status"] == "ADVERTENCIA"
        assert any(a["regla"] == "uci_sin_soporte" for a in d["alertas"])


# ═══════════════════════════════════════════════════════════════════════
class TestElDineroSalvado:
    def _evento(self, db, factura, estado, riesgo):
        db.add(
            PreAuditoriaEventoRecord(
                factura=factura,
                eps="COOSALUD",
                estado=estado,
                recomendacion_accion="X",
                valor_en_riesgo=riesgo,
                valor_factura=riesgo * 3,
                total_alertas=1 if estado != "APROBADO" else 0,
            )
        )
        db.commit()

    def test_una_bloqueada_que_se_corrigio_si_cuenta(self, cliente, db):
        self._evento(db, "HUS1", "BLOQUEO", 500000)
        self._evento(db, "HUS1", "APROBADO", 0)
        r = cliente.get("/pre-auditoria/resumen").json()
        assert r["dinero_salvado"] == 500000
        assert r["riesgo_sin_resolver"] == 0
        assert r["facturas_corregidas"] == 1

    def test_una_bloqueada_que_nunca_volvio_NO_cuenta(self, cliente, db):
        """La disciplina que hace creíble el tablero: no sabemos qué pasó
        con esa factura, así que no se presume que la salvamos."""
        self._evento(db, "HUS2", "BLOQUEO", 900000)
        r = cliente.get("/pre-auditoria/resumen").json()
        assert r["dinero_salvado"] == 0
        assert r["riesgo_sin_resolver"] == 900000

    def test_volver_con_advertencia_tambien_cuenta_como_corregida(self, cliente, db):
        self._evento(db, "HUS3", "BLOQUEO", 300000)
        self._evento(db, "HUS3", "ADVERTENCIA", 10000)
        r = cliente.get("/pre-auditoria/resumen").json()
        assert r["dinero_salvado"] == 300000

    def test_dos_bloqueos_de_la_misma_factura_no_se_suman_dos_veces(self, cliente, db):
        self._evento(db, "HUS4", "BLOQUEO", 400000)
        self._evento(db, "HUS4", "BLOQUEO", 400000)
        self._evento(db, "HUS4", "APROBADO", 0)
        r = cliente.get("/pre-auditoria/resumen").json()
        assert r["dinero_salvado"] == 400000
        assert r["facturas_bloqueadas"] == 1

    def test_volver_a_bloquearse_despues_de_pasar_la_deja_sin_resolver(self, cliente, db):
        """Se corrigió, pero la corrección trajo otro problema: sigue abierta."""
        self._evento(db, "HUS5", "BLOQUEO", 200000)
        self._evento(db, "HUS5", "APROBADO", 0)
        self._evento(db, "HUS5", "BLOQUEO", 700000)
        r = cliente.get("/pre-auditoria/resumen").json()
        assert r["dinero_salvado"] == 0
        assert r["riesgo_sin_resolver"] == 700000

    def test_el_conteo_por_estado(self, cliente, db):
        self._evento(db, "HUS6", "APROBADO", 0)
        self._evento(db, "HUS7", "ADVERTENCIA", 1000)
        self._evento(db, "HUS8", "BLOQUEO", 2000)
        r = cliente.get("/pre-auditoria/resumen").json()
        assert r["por_estado"] == {"APROBADO": 1, "ADVERTENCIA": 1, "BLOQUEO": 1}
        assert r["evaluaciones"] == 3

    def test_sin_datos_el_tablero_no_revienta(self, cliente):
        r = cliente.get("/pre-auditoria/resumen").json()
        assert r["dinero_salvado"] == 0 and r["evaluaciones"] == 0

    def test_el_tablero_no_esta_abierto_a_cualquiera(self, db, monkeypatch):
        from app.main import app

        get_settings.cache_clear()
        app.dependency_overrides[get_db] = lambda: db
        try:
            assert TestClient(app).get("/pre-auditoria/resumen").status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_una_sola_consulta_aunque_haya_muchas_facturas(self, cliente, db):
        """Regla de rendimiento del proyecto: nada de N+1."""
        for i in range(40):
            self._evento(db, f"HUS{i:03d}", "BLOQUEO", 1000)
            self._evento(db, f"HUS{i:03d}", "APROBADO", 0)

        from app.services import preauditoria_concurrente as motor

        consultas = []
        from sqlalchemy import event

        def espiar(conn, cur, stmt, params, ctx, muchos):
            if "pre_auditoria_eventos" in stmt:
                consultas.append(stmt)

        event.listen(db.get_bind(), "before_cursor_execute", espiar)
        try:
            r = motor.resumen(db)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", espiar)

        assert r["dinero_salvado"] == 40000
        assert len(consultas) == 1, f"se hicieron {len(consultas)} consultas"
