"""El panel de correo dice lo que pasó, no lo que suele pasar.

QUÉ PASÓ (25-08-2026). El hospital pasó su correo al servidor institucional y
todos los envíos rebotaron. El panel de Diagnóstico decía, con estas palabras:

    «El servidor de correo rechazó el envío. La causa más común es que
     SMTP_PASSWORD no sea una "contraseña de aplicación". El detalle exacto
     queda en el log del servidor.»

Eso costó una mañana entera. La contraseña estaba bien —se probó el login a
mano contra ese mismo servidor y entró perfecto— y el error real era otro:
«550 5.7.1 Command rejected», que significa que el servidor aceptó la conexión
y RECHAZÓ EL MENSAJE, porque le faltaba la fecha en el encabezado.

Dos defectos en ese texto, y los dos son de diseño, no de redacción:

1. **Adivinaba.** Decía «la causa más común es…» sin haber mirado el error.
   Un mensaje que adivina manda a la gente por el camino equivocado con toda
   la autoridad de un diagnóstico.
2. **Escondía el dato que sí tenía.** El error exacto YA se guardaba en la base
   con cada intento, y aun así mandaba al auditor a bucear en un log de 3 MB
   por consola.

Ahora el panel lee el error anotado, lo traduce, y cuando no lo entiende lo
dice — en vez de culpar a la contraseña.
"""

import pytest

from app.api.routers.admin import _explicar_error_smtp


class TestElRechazoDelMensajeNoSeConfundeConLaClave:
    """El caso que costó la mañana."""

    ERROR_REAL = "(550, b'5.7.1 Command rejected')"

    def test_dice_que_no_es_la_contrasena(self):
        texto = _explicar_error_smtp(self.ERROR_REAL, "mail.sinacsc.com", 587)
        assert "NO es la contraseña" in texto

    def test_explica_que_el_servidor_acepto_la_conexion(self):
        texto = _explicar_error_smtp(self.ERROR_REAL, "mail.sinacsc.com", 587)
        assert "aceptó la conexión" in texto

    def test_apunta_a_donde_de_verdad_estaba(self):
        texto = _explicar_error_smtp(self.ERROR_REAL, "mail.sinacsc.com", 587)
        assert "encabezado" in texto or "remitente" in texto

    @pytest.mark.parametrize(
        "error", ["550 5.7.1", "Command rejected", "Sender address not allowed"]
    )
    def test_reconoce_las_formas_del_rechazo(self, error):
        assert "NO es la contraseña" in _explicar_error_smtp(error)


class TestLaClaveSiSeSenalaCuandoDeVerdadEsLaClave:
    @pytest.mark.parametrize(
        "error",
        [
            "535 b'5.7.8 Username and Password not accepted'",
            "SMTPAuthenticationError: bad credentials",
        ],
    )
    def test_lo_dice(self, error):
        assert "NO aceptó el usuario o la contraseña" in _explicar_error_smtp(error)

    def test_no_asume_que_todo_correo_es_gmail(self):
        """El hospital ya no usa Gmail: el consejo tiene que servir para los dos."""
        texto = _explicar_error_smtp("535 credentials")
        assert "servidor propio" in texto


class TestCuandoNoEntiendeElErrorLoDice:
    def test_no_culpa_a_la_contrasena_por_defecto(self):
        texto = _explicar_error_smtp("un error que nadie ha visto antes")
        assert "contraseña" not in texto.lower()

    def test_manda_al_detalle_tecnico_no_al_log(self):
        texto = _explicar_error_smtp("un error que nadie ha visto antes")
        assert "detalle técnico" in texto


class TestElServidorSeNombraPorSuNombre:
    def test_el_tiempo_agotado_nombra_el_servidor_configurado(self):
        """Antes decía «no se pudo conectar a smtp.gmail.com» pasara lo que
        pasara, aunque el hospital ya no use Gmail."""
        texto = _explicar_error_smtp("timed out", "mail.sinacsc.com", 587)
        assert "mail.sinacsc.com:587" in texto
        assert "gmail" not in texto.lower()
