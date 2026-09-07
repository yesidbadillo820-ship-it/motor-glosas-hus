"""Tres defectos de producción hallados auditando el código (07-09-2026).

Ninguno lo destapó una prueba: los tres estaban en la letra chica y aparecen
solo con volumen o con el paso del tiempo. Estas pruebas los fijan.

1. **UNA FACTURA GRANDE DEVOLVÍA HTTP 500.** `traducir()` corría fuera del
   `try/except`, así que el tope de `items` del PayloadFactura salía como
   ValidationError crudo. Una estancia larga de UCI pasa de 2.000 renglones
   sin esfuerzo, y el endpoint promete en su propio docstring que lo único
   que devuelve error es un cuerpo ilegible (422).

2. **EL TABLERO SE TRAÍA EL RIPS COMPLETO DE CADA FILA.** `payload_base`
   guarda el archivo tal como llegó —531 KB en HUS559077— y la lista lo
   cargaba sin mostrarlo: ~265 MB por consulta con `limite=500`. El motor es
   un solo proceso para todo el hospital.

3. **«DINERO SALVADO» SE CONGELABA A LOS 5.000 EVENTOS.** El tope iba sobre
   un orden ASCENDENTE, o sea que conservaba los más VIEJOS. Al mes de uso la
   cifra dejaba de crecer, en silencio y a la baja. Es la que mira gerencia.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.routers.pre_auditoria import quien_pregunta
from app.database import Base, get_db
from app.main import app
from app.models.db import PreAuditoriaEventoRecord
from app.services import preauditoria_concurrente as motor


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    s.info["engine"] = eng
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


@pytest.fixture
def cliente(db, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[quien_pregunta] = lambda: "his"
    app.dependency_overrides[deps.get_auditor_o_superior] = lambda: object()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _rips(n_consultas: int, factura: str = "HUS900001") -> dict:
    return {
        "numDocumentoIdObligado": "900006037",
        "numFactura": factura,
        "usuarios": [
            {
                "tipoDocumentoIdentificacion": "CC",
                "numDocumentoIdentificacion": "1",
                "fechaNacimiento": "1978-08-10",
                "codSexo": "F",
                "consecutivo": 1,
                "servicios": {
                    "consultas": [
                        {
                            "codConsulta": f"89{i:04d}",
                            "vrServicio": 1000,
                            "fechaInicioAtencion": "2026-08-24 06:22",
                            "codDiagnosticoPrincipal": "M542",
                        }
                        for i in range(n_consultas)
                    ]
                },
            }
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
class TestUnaFacturaGrandeNoTumbaElEndpoint:
    @pytest.mark.parametrize("n", [2001, 5000])
    def test_pasar_los_dos_mil_renglones_ya_no_es_un_500(self, cliente, n):
        """El tope viejo era 2.000 y fallaba con 500."""
        r = cliente.post("/pre-auditoria/evaluar", json=_rips(n))
        assert r.status_code == 200, r.text
        assert r.json()["status"] in ("APROBADO", "ADVERTENCIA", "BLOQUEO")

    def test_pasado_el_techo_de_verdad_responde_422_y_explica(self, cliente):
        """Un archivo equivocado (un RIPS de cápita) se rechaza limpio: nunca
        un 500, que deja al facturador sin saber si timbrar."""
        r = cliente.post("/pre-auditoria/evaluar", json=_rips(20_001))
        assert r.status_code == 422
        assert "too_long" in r.text or "grande" in r.text

    def test_el_endpoint_nunca_devuelve_500_por_tamano(self, cliente):
        """La promesa del docstring, hecha prueba."""
        for n in (0, 1, 2001, 20_001):
            assert cliente.post("/pre-auditoria/evaluar", json=_rips(n)).status_code != 500

    def test_el_tope_de_usuarios_tambien_existe(self):
        """Sin tope, Pydantic construye el cuerpo entero antes de revisarlo."""
        from app.services.preauditoria_rips import MAX_POR_FAMILIA, MAX_USUARIOS, RipsFactura

        campos = RipsFactura.model_fields["usuarios"].metadata
        assert any(getattr(m, "max_length", None) == MAX_USUARIOS for m in campos)
        assert MAX_POR_FAMILIA > 0 and MAX_USUARIOS > 0


# ══════════════════════════════════════════════════════════════════════════
class TestElTableroNoArrastraElRipsCompleto:
    def _con_eventos(self, db, cuantos: int, peso: int = 100_000):
        for i in range(cuantos):
            db.add(
                PreAuditoriaEventoRecord(
                    factura=f"F{i}",
                    estado="BLOQUEO",
                    valor_en_riesgo=100.0,
                    payload_base=json.dumps({"relleno": "x" * peso}),
                    alertas="[]",
                )
            )
        db.commit()

    def test_la_lista_no_pide_payload_base(self, cliente, db):
        self._con_eventos(db, 5)
        consultas: list[str] = []
        event.listen(
            db.info["engine"],
            "before_cursor_execute",
            lambda c, cu, st, p, ctx, em: consultas.append(st),
        )
        r = cliente.get("/pre-auditoria/eventos?limite=5")
        assert r.status_code == 200 and len(r.json()) == 5

        select = [q for q in consultas if "FROM pre_auditoria_eventos" in q][-1]
        assert "payload_base" not in select, "el tablero volvió a arrastrar el RIPS entero"
        # Ojo con el subrayado: `total_alertas` SÍ se pide y es correcto;
        # lo que no debe venir es la columna `alertas`, que guarda el JSON.
        assert "pre_auditoria_eventos.alertas" not in select, (
            "el tablero volvió a arrastrar el JSON de las alertas"
        )

    def test_pero_la_tabla_sigue_mostrando_todo_lo_que_muestra(self, cliente, db):
        """Acotar la consulta no puede vaciar la pantalla."""
        self._con_eventos(db, 1)
        fila = cliente.get("/pre-auditoria/eventos").json()[0]
        for campo in ("id", "factura", "estado", "valor_en_riesgo", "total_alertas", "creado_en"):
            assert campo in fila, f"falta {campo} en la fila del tablero"

    def test_el_detalle_de_uno_si_trae_las_alertas(self, cliente, db):
        """El payload completo se lee donde hace falta: UNA fila."""
        db.add(
            PreAuditoriaEventoRecord(
                factura="F9",
                estado="BLOQUEO",
                valor_en_riesgo=1.0,
                payload_base="{}",
                alertas=json.dumps([{"titulo": "un reparo"}]),
            )
        )
        db.commit()
        fila = cliente.get("/pre-auditoria/eventos").json()[0]
        detalle = cliente.get(f"/pre-auditoria/eventos/{fila['id']}").json()
        assert detalle["alertas"][0]["titulo"] == "un reparo"


# ══════════════════════════════════════════════════════════════════════════
class TestLaCifraDeGerenciaNoSeCongela:
    def _bloqueadas(self, db, cuantas: int):
        for i in range(cuantas):
            db.add(
                PreAuditoriaEventoRecord(
                    factura=f"G{i}",
                    estado="BLOQUEO",
                    valor_en_riesgo=1_000_000.0,
                    payload_base="{}",
                    alertas="[]",
                )
            )
        db.commit()

    def test_cuenta_todas_las_del_periodo_no_las_primeras_n(self, db):
        """El defecto viejo: `limit(5000)` sobre orden ascendente dejaba fuera
        justamente las más nuevas."""
        self._bloqueadas(db, 60)
        r = motor.resumen(db)
        assert r["evaluaciones"] == 60
        assert r["facturas_bloqueadas"] == 60
        assert r["riesgo_sin_resolver"] == 60_000_000.0

    def test_el_resumen_dice_que_periodo_esta_mostrando(self, db):
        """«Desde siempre» sería mentira; el tablero tiene que decir la ventana."""
        assert motor.resumen(db)["dias"] == 90
        assert motor.resumen(db, dias=30)["dias"] == 30

    def test_la_plata_salvada_sigue_siendo_la_corregida_de_verdad(self, db):
        """Regresión de la definición estricta: bloqueada y DESPUÉS pasó."""
        db.add(
            PreAuditoriaEventoRecord(
                factura="H1",
                estado="BLOQUEO",
                valor_en_riesgo=500_000.0,
                payload_base="{}",
                alertas="[]",
            )
        )
        db.commit()
        db.add(
            PreAuditoriaEventoRecord(
                factura="H1",
                estado="APROBADO",
                valor_en_riesgo=0.0,
                payload_base="{}",
                alertas="[]",
            )
        )
        db.add(
            PreAuditoriaEventoRecord(
                factura="H2",
                estado="BLOQUEO",
                valor_en_riesgo=300_000.0,
                payload_base="{}",
                alertas="[]",
            )
        )
        db.commit()
        r = motor.resumen(db)
        assert r["dinero_salvado"] == 500_000.0
        assert r["riesgo_sin_resolver"] == 300_000.0

    def test_el_orden_ascendente_no_se_puede_perder(self, db):
        """«Bloqueada y después pasó» solo se lee hacia adelante en el tiempo.
        Si alguien pone `desc()` para «traer lo último», esto lo delata."""
        import inspect

        fuente = inspect.getsource(motor.resumen)
        assert ".order_by(PreAuditoriaEventoRecord.id.asc())" in fuente
        assert ".limit(" not in fuente, "volvió el tope por filas"
