"""La contraseña de aplicación se pega con espacios (20-08-2026).

Google la muestra en cuatro grupos de cuatro —«abcd efgh ijkl mnop»— y uno la
pega tal cual, que es lo natural. Los espacios son solo para leerla: no son
parte de la clave.

El problema es que algunos servidores la aceptan así y otros la rechazan, y el
error que devuelven es **el mismo** «Username and Password not accepted» que
sale cuando la clave está de verdad equivocada. Así uno se pone a generar
claves nuevas sin necesidad, que es exactamente el rato que se puede perder.
"""

from __future__ import annotations

import pytest

from app.services.email_service import clave_para_el_servidor


class TestLaDeGoogleSeLimpia:
    def test_pegada_con_espacios_funciona(self):
        assert clave_para_el_servidor("abcd efgh ijkl mnop") == "abcdefghijklmnop"

    def test_pegada_sin_espacios_tambien(self):
        assert clave_para_el_servidor("abcdefghijklmnop") == "abcdefghijklmnop"

    def test_con_espacios_de_sobra_alrededor(self):
        assert clave_para_el_servidor("  abcd efgh ijkl mnop  ") == "abcdefghijklmnop"

    def test_con_numeros_tambien(self):
        assert clave_para_el_servidor("ab1d ef2h ij3l mn4p") == "ab1def2hij3lmn4p"


class TestLasDemasNoSeTocan:
    """La mitad que importa: hay servidores donde un espacio SÍ es parte de la
    contraseña. Limpiarla ahí sería romperla."""

    def test_una_frase_de_paso_se_respeta(self):
        clave = "mi clave larga con espacios de verdad"
        assert clave_para_el_servidor(clave) == clave

    @pytest.mark.parametrize(
        "clave",
        [
            "abc defg hijk lmno",  # los grupos no son de 4
            "abcd efgh ijkl",  # solo 3 grupos
            "abcd efgh ijkl mnop qrst",  # 5 grupos
            "abcd-efgh-ijkl-mnop",  # separados por guiones
            "abcd  efgh ijkl mnop",  # doble espacio
        ],
    )
    def test_lo_que_no_tiene_la_forma_exacta_se_manda_tal_cual(self, clave):
        assert clave_para_el_servidor(clave) == clave.strip()

    def test_vacia_no_revienta(self):
        assert clave_para_el_servidor("") == ""
        assert clave_para_el_servidor(None) == ""


class TestElEnvioLaUsa:
    def test_el_login_pasa_por_la_limpieza(self):
        """Si alguien vuelve a mandar `cfg.smtp_password` directo, esta prueba
        se pone roja."""
        import inspect

        from app.services import email_service as es

        fuente = inspect.getsource(es._enviar_sync)
        assert "clave_para_el_servidor(cfg.smtp_password)" in fuente
        assert "server.login(cfg.smtp_user, cfg.smtp_password)" not in fuente
