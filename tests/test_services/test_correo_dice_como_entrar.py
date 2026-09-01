"""El aviso de glosas le dice al gestor cómo entrar al Motor.

QUÉ PIDIÓ YESID (25-08-2026). Varios gestores reciben el aviso de que tienen
glosas asignadas y no saben cómo entrar al portal a responderlas. Pidió que el
propio correo lo explique — usuario, el correo; clave, lo que va antes del
arroba — y añadió «o si se puede colocar mucho mejor».

(Primero se escribió apuntando al webmail institucional. Yesid corrigió: son
las credenciales de entrada al MOTOR, no al correo. Queda anotado porque el
recuadro se ve casi igual y es fácil volver a confundirlo.)

LO QUE SE HIZO MEJOR, que no es cosmético:

1. **El usuario va personalizado.** Ese correo se manda a cada destinatario por
   separado, así que se puede escribir SU dirección en vez de una regla general.
   Cada quien lee la suya y no la de los demás. Antes el HTML se armaba una sola
   vez fuera del bucle y era idéntico para todos; ahora se arma adentro.

2. **Solo a quien tiene cuenta.** El aviso también va a las direcciones de
   difusión general, que no siempre son usuarios del portal. Explicarle a
   alguien cómo entrar con una cuenta que no tiene solo lo confunde.

3. **La clave se nombra como de primer ingreso y no se imprime.** Escrita en un
   correo, esa regla sirve para TODAS las cuentas, y un correo se reenvía. Se
   dice que es solo para entrar la primera vez y se recuerda que el portal
   obliga a cambiarla en ese momento — y eso es cierto: el modal «Cambio de
   contraseña requerido» no deja operar sin cambiarla. La clave de nadie se
   escribe, ni la del propio destinatario.
"""

import pytest

from app.services.email_service import bloque_acceso_al_motor


USUARIOS = {"carterahus02@sinacsc.com", "devoluciones02@sinacsc.com"}


class TestSoloAQuienTieneCuenta:
    @pytest.mark.parametrize("correo", sorted(USUARIOS))
    def test_a_los_usuarios_del_portal_si(self, correo):
        assert bloque_acceso_al_motor(correo, USUARIOS).strip()

    @pytest.mark.parametrize(
        "correo", ["alertas@hus.gov.co", "yesidbadillo820@gmail.com", "otro@sinacsc.com"]
    )
    def test_a_los_de_difusion_general_no(self, correo):
        assert bloque_acceso_al_motor(correo, USUARIOS) == ""

    @pytest.mark.parametrize("correo", ["", None, "sin-arroba"])
    def test_una_direccion_rota_no_rompe_el_correo(self, correo):
        assert bloque_acceso_al_motor(correo, USUARIOS) == ""

    def test_sin_lista_de_usuarios_no_filtra(self):
        """Compatibilidad: si nadie pasa la lista, se pinta igual."""
        assert bloque_acceso_al_motor("quien.sea@hus.gov.co").strip()


class TestCadaQuienVeLoSuyo:
    def test_escribe_la_direccion_del_destinatario(self):
        html = bloque_acceso_al_motor("carterahus02@sinacsc.com", USUARIOS)
        assert "carterahus02@sinacsc.com" in html

    def test_no_menciona_la_direccion_de_otro(self):
        html = bloque_acceso_al_motor("carterahus02@sinacsc.com", USUARIOS)
        assert "devoluciones02@sinacsc.com" not in html

    def test_manda_al_portal_y_no_al_webmail(self):
        """La confusión que hubo que corregir: es el Motor, no el correo."""
        html = bloque_acceso_al_motor("carterahus02@sinacsc.com", USUARIOS)
        assert "iaglosassinac" in html
        assert "webmail" not in html.lower()


class TestLaClaveSePresentaComoDePrimerIngreso:
    def _html(self) -> str:
        return bloque_acceso_al_motor("carterahus02@sinacsc.com", USUARIOS).lower()

    def test_dice_que_es_de_primer_ingreso(self):
        assert "primer ingreso" in self._html()

    def test_avisa_que_el_portal_obliga_a_cambiarla(self):
        html = self._html()
        assert "cambie" in html
        assert "obligatorio" in html

    def test_no_imprime_la_clave_de_nadie(self):
        """Se explica la regla; no se escribe el dato de nadie."""
        html = bloque_acceso_al_motor("carterahus02@sinacsc.com", USUARIOS)
        # «carterahus02» solo puede aparecer como parte de la dirección
        # completa, nunca suelto como si fuera la contraseña impresa.
        assert html.count("carterahus02") == html.count("carterahus02@sinacsc.com")


class TestNoSeCuelaCodigoEnElCorreo:
    def test_una_direccion_con_html_sale_escapada(self):
        malicioso = '"><script>alert(1)</script>@sinacsc.com'
        html = bloque_acceso_al_motor(malicioso, {malicioso})
        assert "<script>" not in html
