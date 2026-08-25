"""Un cambio no puede tumbarle la página a quien está trabajando (24-08-2026).

Pedido de Yesid, textual: «necesito que cada vez que hagamos cambios y demás no
se les esté cayendo la página a los gestores a cada rato».

El autodespliegue baja código nuevo cada 5 minutos y, para aplicarlo, apaga el
motor y lo vuelve a levantar: entre 15 y 30 segundos de página caída, y lo que
estuviera a medio hacer se pierde —un dictamen que la IA estaba redactando se
va con el motor—.

Ahora el bot pregunta antes. Si hay alguien trabajando, espera cinco minutos y
vuelve a preguntar.

EL PUNTO FINO, que es donde esto se rompe si se hace mal: **una pestaña abierta
no es alguien trabajando**. El portal se refresca solo —pregunta la salud cada
30 segundos, los indicadores cada 30, el estado de la IA cada 5—. Si eso
contara, una pantalla olvidada encendida el viernes bloquearía los cambios
hasta el lunes. Y al revés: si no contara lo que sí es trabajo, le cortaríamos
a la gestora en plena respuesta.
"""

from __future__ import annotations

import pytest

from app.services import actividad


@pytest.fixture(autouse=True)
def _limpio():
    actividad.reiniciar_para_pruebas()
    yield
    actividad.reiniciar_para_pruebas()


class TestUnaPestanaAbiertaNoEsTrabajo:
    """Lo que el portal se pregunta solo, con los intervalos reales de
    static/index.html."""

    @pytest.mark.parametrize(
        "ruta",
        [
            "/health",
            "/analytics/",
            "/notificaciones/badge",
            "/inteligencia/diagnostico",
            "/admin/diagnostico",
            "/sistema/ia-presence",
            "/sistema/version",
            "/favicon.ico",
        ],
    )
    def test_lo_que_se_pide_solo_no_cuenta(self, ruta):
        assert not actividad.es_trabajo_de_una_persona("GET", ruta), (
            f"{ruta} se pide sola cada tanto. Si contara, una pantalla "
            f"olvidada encendida bloquearía los cambios para siempre."
        )

    def test_los_archivos_de_la_pagina_tampoco(self):
        assert not actividad.es_trabajo_de_una_persona("GET", "/static/index.html")
        assert not actividad.es_trabajo_de_una_persona("GET", "/static/sinac-ds.css")

    def test_la_pregunta_del_propio_autodespliegue_no_cuenta(self):
        """Si contara, el bot se vería a sí mismo como «gente trabajando» y no
        aplicaría un cambio jamás."""
        assert not actividad.es_trabajo_de_una_persona("GET", "/sistema/ocupacion")

    def test_una_pestana_olvidada_no_bloquea_nada(self):
        """El caso completo: solo tráfico automático durante un buen rato."""
        for _ in range(50):
            for ruta in ("/health", "/analytics/", "/sistema/ia-presence"):
                actividad.marcar_actividad("GET", ruta)
        assert not actividad.hay_gente_trabajando()


class TestLoQueSiEsTrabajo:
    def test_responder_una_glosa_cuenta(self):
        assert actividad.es_trabajo_de_una_persona("POST", "/glosas/analizar")

    @pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
    def test_todo_lo_que_modifica_cuenta_siempre(self, metodo):
        """Aunque la ruta se parezca a una de las automáticas: si alguien
        escribe, alguien está trabajando."""
        assert actividad.es_trabajo_de_una_persona(metodo, "/analytics/")

    @pytest.mark.parametrize(
        "ruta",
        [
            "/",
            "/glosas/historial",
            "/glosas/adres/paquetes",
            "/preauditoria",
            "/contratos/",
            "/usuarios/asignables",
            "/exportar/excel",
        ],
    )
    def test_abrir_una_pantalla_cuenta(self, ruta):
        assert actividad.es_trabajo_de_una_persona("GET", ruta)

    def test_una_ruta_parecida_a_una_automatica_si_cuenta(self):
        """`/analytics/` se pide sola; `/analytics/algo` la pidió alguien."""
        assert actividad.es_trabajo_de_una_persona("GET", "/analytics/exportar")
        assert actividad.es_trabajo_de_una_persona("GET", "/admin/diagnostico-profundo")


class TestElSilencioSeMide:
    def test_recien_arrancado_no_hay_a_quien_interrumpir(self):
        """Si el motor acaba de subir, nadie alcanzó a trabajar. Bloquear el
        despliegue ahí sería esperar por nadie."""
        assert not actividad.hay_gente_trabajando()
        assert actividad.segundos_inactivo() > actividad.SEGUNDOS_DE_SILENCIO

    def test_apenas_alguien_trabaja_se_nota(self):
        actividad.marcar_actividad("POST", "/glosas/analizar")
        assert actividad.hay_gente_trabajando()
        assert actividad.segundos_inactivo() < 5

    def test_pasado_el_silencio_queda_libre(self, monkeypatch):
        """Se maneja el reloj a mano para no tener que esperar minuto y medio
        de verdad. Hay que controlarlo DESDE el momento en que se marca: si se
        cambia después, el reloj falso arranca por debajo del real y parecería
        que el tiempo fue para atrás."""
        reloj = [1000.0]
        monkeypatch.setattr(actividad.time, "monotonic", lambda: reloj[0])

        actividad.marcar_actividad("POST", "/glosas/analizar")
        assert actividad.hay_gente_trabajando()

        # Justo antes de que se cumpla el silencio: todavía hay alguien.
        reloj[0] += actividad.SEGUNDOS_DE_SILENCIO - 1
        assert actividad.hay_gente_trabajando()

        # Y pasado el silencio, queda libre.
        reloj[0] += 2
        assert not actividad.hay_gente_trabajando()

    def test_el_umbral_da_para_un_hueco_normal_pero_no_es_eterno(self):
        """Noventa segundos: alcanza para contestar el teléfono, y no tanto
        como para que nunca aparezca un hueco en toda la mañana."""
        assert 60 <= actividad.SEGUNDOS_DE_SILENCIO <= 180


class TestNoPuedeTumbarElPortal:
    def test_marcar_actividad_nunca_revienta(self):
        """Esto corre en CADA petición. Si revienta, el portal entero deja de
        responder — sería mucho peor que el problema que resuelve."""
        for metodo, ruta in [("", ""), (None, None), ("GET", ""), ("", "/x")]:
            actividad.marcar_actividad(metodo, ruta)  # type: ignore[arg-type]

    def test_la_pregunta_no_dice_nada_delicado(self):
        """La contesta un bot sin clave: no puede filtrar quién trabaja, en qué,
        ni cuántos son."""
        import inspect

        fuente = inspect.getsource(actividad)
        for palabra in ("usuario", "email", "nombre", "glosa_id", "factura"):
            assert palabra not in fuente.split('"""')[-1], (
                f"el servicio guarda «{palabra}»: eso no hace falta para saber "
                f"si hay alguien trabajando"
            )
