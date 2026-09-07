"""Con qué dirección se ve este computador desde el celular.

El bot `tools\\NORUEGO.cmd` necesita imprimir el enlace **exacto** que el
usuario escribe en el teléfono. Antes lo sacaba de `ipconfig`, y eso falla de
dos maneras en el PC de cartera:

1. `ipconfig` lista varias direcciones (wifi, cable, VirtualBox, WSL) y
   ninguna dice cuál es la que ve el celular.
2. Si la línea del bot sale mal, el usuario termina escribiendo el texto de
   relleno («LA-IP-DE-ARRIBA») en el navegador. Pasó de verdad el 31-08.

Aquí se averigua de una sola forma y se arma el enlace completo, para que el
bot no tenga que adivinar ni el usuario tenga que interpretar nada.
"""

from __future__ import annotations

import socket

#: Dirección a la que se «apunta» para saber por dónde sale este equipo.
#: Es la DNS pública de Google, pero **no se le envía ni un byte**: en UDP,
#: `connect()` solo fija la ruta de salida en el propio sistema operativo.
#: Por eso funciona igual sin internet y no genera tráfico hacia afuera.
REFERENCIA = ("8.8.8.8", 80)

#: Puerto en el que el bot levanta el servidor del hospital.
PUERTO_POR_DEFECTO = 8000

#: Ruta con la que `app/` sirve la aplicación generada en `static/noruego/`.
RUTA_APP = "/static/noruego/index.html"


def sirve_para_el_celular(ip: str) -> bool:
    """Descarta las direcciones que el teléfono nunca podría alcanzar."""
    return bool(ip) and not ip.startswith("127.") and ip != "0.0.0.0"


def direccion_lan() -> str | None:
    """La IP de este equipo en su red, o ``None`` si no se pudo averiguar."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(REFERENCIA)
            ip = str(sock.getsockname()[0])
    except OSError:
        return None
    return ip if sirve_para_el_celular(ip) else None


def enlace(ip: str, puerto: int = PUERTO_POR_DEFECTO) -> str:
    """El enlace completo, listo para copiar en el navegador del celular."""
    return f"http://{ip}:{puerto}{RUTA_APP}"


def enlace_de_esta_maquina(puerto: int = PUERTO_POR_DEFECTO) -> str | None:
    """El enlace de este computador, o ``None`` si no se pudo averiguar la IP."""
    ip = direccion_lan()
    return enlace(ip, puerto) if ip else None
