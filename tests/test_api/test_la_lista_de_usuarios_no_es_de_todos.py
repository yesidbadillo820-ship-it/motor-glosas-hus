"""La lista de usuarios del portal no puede pedirla cualquiera (21-08-2026).

QUÉ HABÍA. `GET /usuarios/` solo exigía haber entrado con la clave. Cualquier
auditor podía pedir el listado **entero** de cuentas del portal —27 personas,
con nombre, correo, rol y también las cuentas inactivas de quienes ya no
están— escribiendo la dirección a mano.

POR QUÉ ESTABA ASÍ. No fue descuido: cinco pantallas la usaban de verdad
—importación masiva, asignar en lote, reasignar una glosa, reasignar todo lo
de un gestor y el buscador de Ctrl+K—. Todas para lo mismo: llenar un
desplegable de «¿a quién le paso esto?». Pedían la lista completa y filtraban
en el navegador. Cerrar la puerta sin más habría dejado esas cinco pantallas
sin desplegable.

QUÉ SE HIZO. El filtro se pasó al servidor: `GET /usuarios/asignables` trae
solo lo que un desplegable necesita —quién está activo y puede recibir
trabajo—. La lista completa quedó donde corresponde, en `GET /usuarios/`, que
ahora exige rol de coordinación.

Ese cambio del menú de esta mañana escondía el botón de Usuarios, y se dijo
con todas las letras que **esconder un botón ordena la pantalla pero no
protege el dato**. Esto es lo que sí lo protege.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.main import app
from app.models.db import (
    ROL_AUDITOR,
    ROL_COORDINADOR,
    ROL_SUPER_ADMIN,
    ROL_VIEWER,
    Base,
    UsuarioRecord,
)


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
def cliente(db_session):
    """El portal visto por alguien. Por defecto, una auditora."""
    estado = {
        "usuario": UsuarioRecord(
            id=99, email="laura@hus.gov.co", nombre="Laura", rol=ROL_AUDITOR, activo=1
        )
    }
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: estado["usuario"]
    with TestClient(app) as c:
        c.estado = estado
        yield c
    app.dependency_overrides.clear()


def _rol(cliente, rol):
    cliente.estado["usuario"] = UsuarioRecord(
        id=99, email="u@hus.gov.co", nombre="U", rol=rol, activo=1
    )


def _sembrar(db):
    """El equipo real, en pequeño: tres médicas auditoras, la coordinación,
    alguien que solo mira y una cuenta de quien ya no está."""
    gente = [
        UsuarioRecord(nombre="Laura Díaz", email="laura@hus.gov.co", rol=ROL_AUDITOR, activo=1),
        UsuarioRecord(nombre="Leidy Sanguino", email="leidy@hus.gov.co", rol=ROL_AUDITOR, activo=1),
        UsuarioRecord(nombre="Zulay González", email="zulay@hus.gov.co", rol=ROL_AUDITOR, activo=1),
        UsuarioRecord(nombre="Coordina", email="coord@hus.gov.co", rol=ROL_COORDINADOR, activo=1),
        UsuarioRecord(nombre="Solo Mira", email="mira@hus.gov.co", rol=ROL_VIEWER, activo=1),
        UsuarioRecord(nombre="Ya No Está", email="exfun@hus.gov.co", rol=ROL_AUDITOR, activo=0),
    ]
    for u in gente:
        u.password_hash = "x"
        db.add(u)
    db.commit()


class TestLaPuertaQuedoCerrada:
    def test_una_auditora_ya_no_saca_el_listado_entero(self, cliente, db_session):
        _sembrar(db_session)
        r = cliente.get("/usuarios/")
        assert r.status_code == 403, (
            "Cualquiera que entre con su clave sigue pudiendo sacar la lista "
            "completa de cuentas del portal, con correos y roles."
        )

    def test_el_que_solo_mira_tampoco(self, cliente, db_session):
        _sembrar(db_session)
        _rol(cliente, ROL_VIEWER)
        assert cliente.get("/usuarios/").status_code == 403

    def test_la_coordinacion_si_puede(self, cliente, db_session):
        """Cerrar la puerta no puede dejar sin trabajar a quien administra."""
        _sembrar(db_session)
        _rol(cliente, ROL_COORDINADOR)
        r = cliente.get("/usuarios/")
        assert r.status_code == 200
        assert len(r.json()) == 6, "a la coordinación le sigue saliendo todo el mundo"

    def test_y_el_administrador_tambien(self, cliente, db_session):
        _sembrar(db_session)
        _rol(cliente, ROL_SUPER_ADMIN)
        assert cliente.get("/usuarios/").status_code == 200


class TestLosDesplegablesSiguenFuncionando:
    """Lo que no se puede romper: las cinco pantallas que arman un
    desplegable de «¿a quién le paso esto?»."""

    def test_una_auditora_si_puede_pedir_a_quien_asignar(self, cliente, db_session):
        _sembrar(db_session)
        r = cliente.get("/usuarios/asignables")
        assert r.status_code == 200

    def test_salen_los_que_pueden_recibir_trabajo(self, cliente, db_session):
        _sembrar(db_session)
        correos = {u["email"] for u in cliente.get("/usuarios/asignables").json()}
        assert correos == {
            "laura@hus.gov.co",
            "leidy@hus.gov.co",
            "zulay@hus.gov.co",
            "coord@hus.gov.co",
        }

    def test_no_sale_quien_ya_no_esta(self, cliente, db_session):
        """Asignarle una glosa a una cuenta inactiva es perderla de vista."""
        _sembrar(db_session)
        correos = {u["email"] for u in cliente.get("/usuarios/asignables").json()}
        assert "exfun@hus.gov.co" not in correos

    def test_no_sale_quien_solo_mira(self, cliente, db_session):
        _sembrar(db_session)
        correos = {u["email"] for u in cliente.get("/usuarios/asignables").json()}
        assert "mira@hus.gov.co" not in correos

    def test_trae_lo_que_el_desplegable_pinta(self, cliente, db_session):
        """Las pantallas muestran el nombre y el rol, y asignan por correo o
        por id. Si falta alguno, el desplegable sale vacío o en blanco."""
        _sembrar(db_session)
        uno = cliente.get("/usuarios/asignables").json()[0]
        assert set(uno) >= {"id", "nombre", "email", "rol", "activo"}
        assert uno["nombre"] and uno["email"] and uno["rol"]

    def test_trae_activo_para_que_el_filtro_del_portal_siga_pasando(self, cliente, db_session):
        """Las pantallas filtran con `u.activo === 1`. Si la respuesta no
        trajera ese campo, el filtro las dejaría a todas por fuera y el
        desplegable saldría vacío sin que nadie entendiera por qué."""
        _sembrar(db_session)
        for u in cliente.get("/usuarios/asignables").json():
            assert u["activo"] == 1

    def test_salen_en_orden_de_nombre(self, cliente, db_session):
        """Un desplegable de seis nombres sin orden se busca a ojo."""
        _sembrar(db_session)
        nombres = [u["nombre"] for u in cliente.get("/usuarios/asignables").json()]
        assert nombres == sorted(nombres)

    def test_sin_nadie_activo_contesta_vacio_y_no_revienta(self, db_session, cliente):
        """Caso borde: base recién montada. La pantalla tiene su propio
        camino alterno —pedir el correo a mano— pero solo si esto responde."""
        r = cliente.get("/usuarios/asignables")
        assert r.status_code == 200
        assert r.json() == []


class TestLasFilasViejasNoSePierden:
    """La base guarda el rol como texto. Una fila escrita distinta hace años
    dejaría a esa persona fuera del desplegable sin que nadie entienda por qué
    —y su trabajo se le seguiría asignando a otro—."""

    def _agregar(self, db, rol):
        u = UsuarioRecord(nombre="Antigua", email="vieja@hus.gov.co", rol=rol, activo=1)
        u.password_hash = "x"
        db.add(u)
        db.commit()

    def test_en_minusculas_sigue_saliendo(self, cliente, db_session):
        self._agregar(db_session, "auditor")
        correos = {u["email"] for u in cliente.get("/usuarios/asignables").json()}
        assert "vieja@hus.gov.co" in correos

    def test_con_espacios_sigue_saliendo(self, cliente, db_session):
        self._agregar(db_session, "  COORDINADOR ")
        correos = {u["email"] for u in cliente.get("/usuarios/asignables").json()}
        assert "vieja@hus.gov.co" in correos

    def test_admin_a_secas_sigue_saliendo(self, cliente, db_session):
        """La forma vieja de escribir SUPER_ADMIN, que este archivo ya
        contempla en otra parte."""
        self._agregar(db_session, "ADMIN")
        correos = {u["email"] for u in cliente.get("/usuarios/asignables").json()}
        assert "vieja@hus.gov.co" in correos

    def test_pero_un_rol_inventado_no_entra(self, cliente, db_session):
        """Tolerar formas viejas no es aceptar cualquier cosa."""
        self._agregar(db_session, "INVITADO")
        correos = {u["email"] for u in cliente.get("/usuarios/asignables").json()}
        assert "vieja@hus.gov.co" not in correos

    def test_una_fila_sin_rol_queda_como_auditora(self, cliente, db_session):
        """No es capricho de esta lista: el modelo pone AUDITOR por defecto
        cuando la fila no trae rol (`app/models/db.py`). O sea que una cuenta
        sin rol YA era una auditora en todo el sistema, no solo acá. Se deja
        escrito para que quede claro que sale a propósito y no por descuido."""
        self._agregar(db_session, None)
        salida = cliente.get("/usuarios/asignables").json()
        vieja = [u for u in salida if u["email"] == "vieja@hus.gov.co"]
        assert vieja, "una cuenta sin rol desapareció del desplegable"
        assert vieja[0]["rol"] == ROL_AUDITOR


class TestNoSeFiltroNadaDeMas:
    def test_no_manda_la_contrasena(self, cliente, db_session):
        _sembrar(db_session)
        for u in cliente.get("/usuarios/asignables").json():
            assert "password_hash" not in u
            assert "totp_secret" not in u

    def test_no_manda_el_id_de_escritorio_remoto(self, cliente, db_session):
        """`rustdesk_id` deja entrar al PC de esa persona. La lista completa ya
        lo reservaba para la coordinación; esta no lo manda a nadie."""
        _sembrar(db_session)
        for u in cliente.get("/usuarios/asignables").json():
            assert "rustdesk_id" not in u
