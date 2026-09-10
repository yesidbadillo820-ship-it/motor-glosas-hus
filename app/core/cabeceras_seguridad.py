"""Las cabeceras que le dicen al navegador cómo tratar esta página.

09-09-2026, hallazgo de los dos análisis de código del auditor: el motor no
enviaba **ninguna**. No es que estuvieran mal configuradas — no existían.

Cada una tapa una forma concreta de atacar a quien tiene la sesión abierta,
y todas se resuelven del lado del navegador: el servidor solo tiene que
pedirlo. Son de las pocas defensas que cuestan una línea y no se pueden
saltar desde afuera.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# El motor sirve su propia pantalla y no se embebe en ninguna parte.
_CABECERAS = {
    # Que nadie meta el portal dentro de un <iframe> suyo para engañar al
    # auditor y que haga clic en algo que no ve (clickjacking). Con la sesión
    # abierta, un clic robado radica una respuesta.
    "X-Frame-Options": "DENY",
    # Que el navegador NO adivine el tipo de un archivo. Sin esto, un PDF de
    # soportes con contenido raro puede terminar interpretado como página y
    # ejecutarse en la sesión del auditor.
    "X-Content-Type-Options": "nosniff",
    # Que al salir del portal no se le mande la dirección completa a la otra
    # página. Las URLs del motor llevan números de factura y de glosa.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # El motor no usa cámara, micrófono ni ubicación: se apagan de plano, para
    # que un script inyectado tampoco pueda pedirlas.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

# Solo tiene sentido sobre HTTPS: le dice al navegador que para este dominio
# no vuelva a intentar por HTTP ni aunque se lo pidan. Un año, que es lo
# recomendado; se manda solo cuando la petición llegó cifrada, para no
# romper el desarrollo local ni las pruebas.
_HSTS = "max-age=31536000; includeSubDomains"


class CabecerasDeSeguridad(BaseHTTPMiddleware):
    """Agrega las cabeceras a toda respuesta, sin excepción.

    No se toca `Content-Security-Policy` a propósito. Es la más potente de
    todas, pero la pantalla del motor tiene estilos y scripts escritos
    directamente en el HTML: una CSP puesta a ojo dejaría el portal en
    blanco, y una CSP con `unsafe-inline` no protege de nada mientras da la
    impresión de que sí. Merece su propio trabajo, con la pantalla delante.
    """

    async def dispatch(self, request: Request, call_next):
        respuesta = await call_next(request)
        for nombre, valor in _CABECERAS.items():
            respuesta.headers.setdefault(nombre, valor)
        if request.url.scheme == "https":
            respuesta.headers.setdefault("Strict-Transport-Security", _HSTS)
        return respuesta
