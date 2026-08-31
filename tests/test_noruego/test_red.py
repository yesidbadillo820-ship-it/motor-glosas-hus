"""La dirección con la que el celular alcanza a este computador.

Es la pieza que falló en la primera prueba real (31-08): el bot no logró
mostrar la IP y el usuario terminó escribiendo el texto de relleno
«LA-IP-DE-ARRIBA» en el navegador, con su respectivo error de DNS.
"""

from __future__ import annotations

import socket

import pytest

from noruego import red


def test_no_se_le_manda_nada_a_la_referencia(monkeypatch):
    """El socket es UDP y solo se «conecta»: no puede salir tráfico del hospital."""
    enviados: list[object] = []

    class SocketFalso:
        def __init__(self, familia, tipo):
            assert familia == socket.AF_INET
            assert tipo == socket.SOCK_DGRAM, "tiene que ser UDP, no una conexión real"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def settimeout(self, _segundos):
            pass

        def connect(self, destino):
            assert destino == red.REFERENCIA

        def send(self, datos):  # pragma: no cover - si se llama, la prueba falla
            enviados.append(datos)

        def sendto(self, *args):  # pragma: no cover - igual que send
            enviados.append(args)

        def getsockname(self):
            return ("192.168.1.15", 51234)

    monkeypatch.setattr(socket, "socket", SocketFalso)
    assert red.direccion_lan() == "192.168.1.15"
    assert not enviados, "no se debe enviar ni un byte hacia afuera"


def test_sin_red_no_revienta(monkeypatch):
    """El PC de cartera a veces arranca sin wifi: el bot no puede caerse."""

    def revienta(*_args, **_kwargs):
        raise OSError("network is unreachable")

    monkeypatch.setattr(socket, "socket", revienta)
    assert red.direccion_lan() is None
    assert red.enlace_de_esta_maquina() is None


@pytest.mark.parametrize("ip", ["127.0.0.1", "127.0.1.1", "0.0.0.0", ""])
def test_las_direcciones_que_el_celular_no_alcanza_se_descartan(ip):
    assert not red.sirve_para_el_celular(ip)


@pytest.mark.parametrize("ip", ["192.168.1.15", "10.0.0.4", "172.16.3.9"])
def test_las_direcciones_de_red_local_sirven(ip):
    assert red.sirve_para_el_celular(ip)


def test_una_ip_de_loopback_no_se_ofrece_como_enlace(monkeypatch):
    """Servir 127.0.0.1 al celular es peor que no dar nada: nunca funciona."""
    monkeypatch.setattr(red, "direccion_lan", lambda: None)
    assert red.enlace_de_esta_maquina() is None


def test_el_enlace_apunta_a_donde_la_app_queda_servida():
    """`exportar` deja la app en static/noruego/ y `app/` sirve esa carpeta."""
    assert red.enlace("192.168.1.15") == "http://192.168.1.15:8000/static/noruego/index.html"


def test_el_puerto_se_puede_cambiar():
    assert red.enlace("10.0.0.4", 8080) == "http://10.0.0.4:8080/static/noruego/index.html"


def test_el_enlace_no_lleva_texto_de_relleno():
    """Nada de «LA-IP-DE-ARRIBA»: lo que se imprime se copia tal cual."""
    url = red.enlace("192.168.1.15")
    assert "<" not in url and ">" not in url
    assert url.startswith("http://192.168.1.15:")


def test_la_direccion_de_verdad_de_esta_maquina():
    """Prueba de humo: en este entorno debe salir algo utilizable o None."""
    ip = red.direccion_lan()
    assert ip is None or red.sirve_para_el_celular(ip)
