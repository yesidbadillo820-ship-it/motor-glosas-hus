"""El correo lleva fecha e identificador, o el servidor lo rechaza.

QUÉ PASÓ (25-08-2026). El hospital pasó su correo al servidor institucional
(correopremium) y TODOS los envíos empezaron a rebotar:

    550 5.7.1 Command rejected

El panel del motor decía que la causa más común era la contraseña. No era: se
probó el login a mano contra el mismo servidor y entró perfecto. Lo que pasaba
es que el mensaje salía solo con tres encabezados —Asunto, De y Para— y le
faltaban la FECHA y el IDENTIFICADOR DE MENSAJE.

El estándar de correo (RFC 5322) exige la fecha, y los servidores endurecidos
rechazan como sospechoso lo que llega sin fecha ni identificador. Gmail era
permisivo y los aceptaba igual, así que el defecto llevaba meses ahí sin que
nadie lo notara: solo salió a la luz el día que se cambió de servidor.
"""

import re

import pytest

from app.services import email_service


class _CfgFalsa:
    smtp_host = "mail.ejemplo.com"
    smtp_port = 587
    smtp_user = "buzon@ejemplo.com"
    smtp_password = "loquesea"


class _ServidorDeMentira:
    """Se queda con el mensaje en vez de mandarlo."""

    ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, u, p):
        pass

    def send_message(self, msg):
        _ServidorDeMentira.ultimo = msg


@pytest.fixture
def mensaje(monkeypatch):
    monkeypatch.setattr(email_service, "get_settings", lambda: _CfgFalsa())
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *a, **k: _ServidorDeMentira())
    monkeypatch.setattr(email_service, "_anotar", lambda *a, **k: None)
    _ServidorDeMentira.ultimo = None
    assert email_service._enviar_sync("alguien@hus.gov.co", "Prueba", "<p>hola</p>")
    return _ServidorDeMentira.ultimo


class TestLosEncabezadosQueElServidorExige:
    def test_lleva_fecha(self, mensaje):
        assert mensaje["Date"], "sin fecha el servidor responde 550 Command rejected"

    def test_la_fecha_tiene_el_formato_del_estandar(self, mensaje):
        # Ej: "Tue, 25 Aug 2026 10:26:03 -0500"
        assert re.match(
            r"^[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}$",
            mensaje["Date"],
        ), mensaje["Date"]

    def test_lleva_identificador_de_mensaje(self, mensaje):
        assert mensaje["Message-ID"]
        assert mensaje["Message-ID"].startswith("<")
        assert mensaje["Message-ID"].endswith(">")

    def test_el_identificador_usa_el_dominio_de_quien_envia(self, mensaje):
        """Un identificador con un dominio ajeno también huele mal."""
        assert mensaje["Message-ID"].endswith("@ejemplo.com>")


class TestLoQueYaEstabaSigueIgual:
    def test_conserva_asunto_de_y_para(self, mensaje):
        assert mensaje["Subject"] == "Prueba"
        assert mensaje["From"] == "buzon@ejemplo.com"
        assert mensaje["To"] == "alguien@hus.gov.co"

    def test_el_cuerpo_sigue_siendo_html(self, mensaje):
        assert "hola" in mensaje.as_string()
