"""El motor tiene que arrancar sin ahogarse y decir la verdad sobre su salud.

09-09-2026, hallazgos verificados de los análisis de código del auditor.

**1 · El arranque se ahogaba solo.** El `lifespan` es `async`, y adentro
reintentaba la conexión a la base con `time.sleep()`. Un sleep normal no
cede el turno: se queda el hilo entero. Con la base caída, los cinco
reintentos suman 2+4+8+16 = **30 segundos** en los que el servidor no
contesta ni el `/health` ni acepta una conexión — parece muerto cuando en
realidad está esperando.

**2 · El `/health` mentía.** Devolvía `status: ok` sin tocar la base. El
balanceador leía «ok» y le seguía mandando trabajo a una instancia que no
podía guardar ni leer una glosa. El auditor veía errores sueltos sin
entender por qué: para el sistema, esa instancia estaba sana.

**3 · CORS sin `PUT`.** Hay cuatro endpoints que lo usan (metadatos de
contrato, notas privadas, presets de filtros, estado de sugerencias). Hoy no
se nota porque la pantalla se sirve del mismo servidor; el día que salga de
otro dominio, esos cuatro fallan sin explicación.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db


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
def client(db_session):
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _codigo(objeto) -> str:
    """El código de algo, SIN sus comentarios.

    Hace falta: los comentarios que explican un arreglo suelen citar la forma
    vieja para dejar dicho qué se cambió. Buscándola sobre el texto completo,
    la prueba se encuentra a sí misma y falla por su propia documentación.
    """
    return "\n".join(
        ln for ln in inspect.getsource(objeto).splitlines() if not ln.lstrip().startswith("#")
    )


class TestElArranqueNoSeAhoga:
    def test_ya_no_usa_un_sleep_bloqueante(self):
        from app import main

        fuente = _codigo(main.lifespan)
        assert "_time.sleep(" not in fuente, (
            "El lifespan es async: un sleep normal se queda el hilo entero y "
            "el servidor no contesta ni el /health mientras espera."
        )

    def test_espera_cediendo_el_turno(self):
        from app import main

        assert "await _asyncio.sleep(espera)" in _codigo(main.lifespan)


class TestElHealthDiceLaVerdad:
    def test_con_la_base_sana_responde_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_sigue_trayendo_la_version(self, client):
        """Lo que ya hacía no se puede perder."""
        assert "version" in client.get("/health").json()

    def test_con_la_base_caida_responde_503(self, client):
        """503 es lo que el balanceador entiende como «sacame de la rotación».
        Un 200 con la base caída le dice que siga mandando tráfico."""

        class _BaseCaida:
            def execute(self, *_a, **_k):
                raise RuntimeError("connection refused")

        from app.main import app

        app.dependency_overrides[get_db] = lambda: _BaseCaida()
        try:
            r = client.get("/health")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 503, (
            f"Devolvió {r.status_code} con la base caída. El balanceador le "
            "sigue mandando trabajo a una instancia que no puede guardar nada."
        )

    def test_y_dice_QUE_fue_lo_que_fallo(self, client):
        """«Degradado» a secas obliga a salir a adivinar."""

        class _BaseCaida:
            def execute(self, *_a, **_k):
                raise RuntimeError("connection refused")

        from app.main import app

        app.dependency_overrides[get_db] = lambda: _BaseCaida()
        try:
            detalle = client.get("/health").json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert "base de datos" in detalle["motivo"]

    def test_la_consulta_es_la_mas_barata_posible(self):
        """Un health-check que pesa termina desactivándose."""
        from app.api.routers import health

        assert 'text("SELECT 1")' in _codigo(health.health)


class TestCorsDejaPasarLoQueElMotorOFRECE:
    @staticmethod
    def _metodos() -> list[str]:
        from app.main import app

        for m in app.user_middleware:
            if "CORS" in str(m.cls):
                return list(m.kwargs.get("allow_methods") or [])
        pytest.fail("No se encontró el middleware de CORS")

    def test_PUT_esta_permitido(self):
        """Cuatro endpoints lo usan: metadatos de contrato, notas privadas,
        presets de filtros y estado de sugerencias."""
        assert "PUT" in self._metodos()

    @pytest.mark.parametrize("metodo", ["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
    def test_los_que_ya_estaban_siguen(self, metodo):
        assert metodo in self._metodos()

    def test_ningun_endpoint_queda_fuera_de_la_lista(self):
        """La prueba de verdad: que la lista cubra lo que el motor ofrece.
        Si mañana alguien agrega un endpoint con un método nuevo, esto avisa."""
        from app.main import app

        usados = set()
        for ruta in app.routes:
            usados |= {m for m in (getattr(ruta, "methods", None) or set()) if m != "HEAD"}
        permitidos = set(self._metodos())
        faltan = usados - permitidos
        assert not faltan, (
            f"El motor ofrece {sorted(faltan)} y CORS no los permite. Desde otro "
            "dominio, el navegador ni siquiera manda esas peticiones."
        )

    def test_se_expone_el_identificador_de_la_peticion(self):
        """Para que la pantalla pueda mostrarlo cuando algo falla y el auditor
        tenga qué pasarnos."""
        from app.core.correlation import HEADER
        from app.main import app

        for m in app.user_middleware:
            if "CORS" in str(m.cls):
                assert HEADER in (m.kwargs.get("expose_headers") or [])
                return
        pytest.fail("No se encontró el middleware de CORS")
