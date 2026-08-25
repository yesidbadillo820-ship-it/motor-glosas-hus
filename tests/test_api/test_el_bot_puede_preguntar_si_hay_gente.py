"""El autodespliegue tiene que poder preguntar si hay alguien trabajando
(24-08-2026).

`GET /sistema/ocupacion` es la pregunta que hace el bot local antes de apagar
el motor para aplicar código nuevo. Si hay gente trabajando, espera un hueco.

TRES COSAS QUE ESTA PANTALLA CUIDA:

- Que se pueda preguntar **sin clave**: la hace un bot que no tiene sesión. Por
  eso mismo, que no diga nada delicado — ni quién, ni en qué, ni cuántos son.
- Que el **middleware** de verdad marque lo que una persona pide, porque de
  nada sirve la pregunta si nadie apunta la respuesta.
- Que la propia pregunta **no se cuente a sí misma**. Ese error ya se cometió
  este mes con el candado del vigilante, que se contaba a sí mismo y dejó el
  hospital sin portal tras un reinicio.
"""

from __future__ import annotations

import pytest

from app.services import actividad


@pytest.fixture(autouse=True)
def _limpio():
    actividad.reiniciar_para_pruebas()
    yield
    actividad.reiniciar_para_pruebas()


class TestLaPreguntaSeContesta:
    def test_contesta_sin_pedir_clave(self, client):
        """El bot no tiene sesión: si exigiera clave, no podría preguntar y
        volveríamos a tumbar la página en plena jornada."""
        r = client.get("/sistema/ocupacion")
        assert r.status_code == 200

    def test_dice_lo_que_el_bot_necesita(self, client):
        d = client.get("/sistema/ocupacion").json()
        assert set(d) == {"segundos_inactivo", "hay_gente_trabajando", "umbral_segundos"}
        assert isinstance(d["hay_gente_trabajando"], bool)
        assert isinstance(d["segundos_inactivo"], int)

    def test_y_nada_mas(self, client):
        """Se contesta sin clave: no puede filtrar quién estaba trabajando ni
        en qué."""
        crudo = client.get("/sistema/ocupacion").text.lower()
        for palabra in ("email", "usuario", "nombre", "factura", "glosa"):
            assert palabra not in crudo


class TestElMiddlewareApuntaLoQueImporta:
    def test_una_pantalla_abierta_por_alguien_cuenta(self, client):
        client.get("/glosas/historial")
        assert client.get("/sistema/ocupacion").json()["hay_gente_trabajando"]

    def test_lo_que_el_portal_se_pregunta_solo_no_cuenta(self, client):
        for _ in range(20):
            client.get("/health")
            client.get("/sistema/ia-presence")
        assert not client.get("/sistema/ocupacion").json()["hay_gente_trabajando"]

    def test_la_propia_pregunta_no_se_cuenta_a_si_misma(self, client):
        """Si se contara, el bot se vería a sí mismo como «gente trabajando» y
        no aplicaría un cambio jamás. Es el mismo error del candado del
        vigilante, que se contaba a sí mismo y dejó el hospital sin portal."""
        for _ in range(10):
            client.get("/sistema/ocupacion")
        assert not client.get("/sistema/ocupacion").json()["hay_gente_trabajando"]

    def test_escribir_cuenta_aunque_la_respuesta_sea_un_error(self, client):
        """Una gestora sin sesión que intenta guardar sigue siendo una gestora
        trabajando: la interrupción le duele igual."""
        client.post("/glosas/analizar", json={})
        assert client.get("/sistema/ocupacion").json()["hay_gente_trabajando"]


class TestNoPuedeTumbarElPortal:
    def test_el_portal_sigue_contestando_todo_lo_demas(self, client):
        """El middleware corre en CADA petición. Si estorbara, sería mucho peor
        que el problema que resuelve."""
        assert client.get("/health").status_code == 200
        assert client.get("/sistema/version").status_code == 200

    def test_aunque_el_servicio_falle_la_peticion_pasa(self, client, monkeypatch):
        def _revienta(*a, **k):
            raise RuntimeError("algo se rompió")

        monkeypatch.setattr(actividad, "marcar_actividad", _revienta)
        assert client.get("/health").status_code == 200
