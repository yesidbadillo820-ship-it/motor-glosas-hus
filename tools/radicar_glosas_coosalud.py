"""Radicador autónomo de COOSALUD (V3, Pilar 1).

Le pide al motor UNA glosa lista para radicar, la radica en el portal con el
navegador escondido, y le devuelve el comprobante. Nada más.

Lo que **NO** hace, a propósito:
  · No decide qué se radica — eso lo decidió el motor con los escudos de la V2.
  · No reintenta cuando no sabe si quedó: eso lo revisa una persona.
  · No inventa pasos del portal: reutiliza las funciones ya probadas de
    `responder_glosas_coosalud.py`.

EL PILOTO ES OBLIGATORIO. Por defecto radica UNA factura y se detiene:

    py tools/radicar_glosas_coosalud.py                      (piloto de 1)
    py tools/radicar_glosas_coosalud.py --limite 20 --piloto-ok

CREDENCIALES: del entorno del PC (COOSALUD_USER / COOSALUD_PASSWORD), igual
que el bot de respuestas. **El motor nunca las ve.**

REQUISITOS:  py -m pip install playwright httpx  ·  py -m playwright install chromium
"""

from __future__ import annotations

import sys
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

from radicador_comun import (  # noqa: E402
    PilotoNoConfirmado,  # noqa: F401  (lo importan las pruebas)
    SesionNoDisponible,
    correr,
    limite_efectivo,  # noqa: F401
    parser_comun,
    sha256_de,  # noqa: F401
)

PORTAL = "COOSALUD"


def abrir_sesion(pw, args):
    from responder_glosas_coosalud import cargar_credenciales, login

    # OJO: acá NO se vuelve a exigir playwright. `radicador_comun.correr()` ya
    # importó `sync_playwright` y abrió el contexto antes de llamar a esta
    # función: si faltara, el proceso ni habría llegado hasta acá. La llamada
    # que había era inalcanzable en producción y, donde sí se alcanzaba (una
    # prueba, un PC sin playwright), mataba el proceso con `sys.exit(2)` en vez
    # de dejar que `abrir_sesion` diera su respuesta honesta —
    # `SesionNoDisponible`— que es la que manda la glosa a manos de una persona.
    usuario, clave = cargar_credenciales()
    navegador = pw.chromium.launch(headless=not args.con_cabeza, slow_mo=300 if args.lento else 0)
    page = navegador.new_page()
    try:
        login(page, usuario, clave)
    except Exception as e:
        navegador.close()
        raise SesionNoDisponible(f"No se pudo entrar a COOSALUD: {e}") from e
    return page, navegador.close


def radicar(page, fila: dict) -> tuple[str, str]:
    """Abre la factura y cierra la respuesta. Devuelve (radicado, comprobante)."""
    from responder_glosas_coosalud import abrir_factura, terminar_respuesta

    factura = str(fila.get("factura") or "")
    evidencias = Path(radicar.evidencias)
    abrir_factura(page, factura)
    resultado = terminar_respuesta(page, factura, evidencias)
    if resultado != "OK":
        raise RuntimeError(f"El portal no mostró el cartel de cierre ({resultado}).")
    comprobante = evidencias / f"{factura}_cierre.png"
    return f"COOSALUD-{factura}", str(comprobante)


def main(argv=None) -> int:
    p = parser_comun("Radicador autónomo de COOSALUD (piloto de 1)", "data/evidencias_radicacion")
    args = p.parse_args(argv)
    radicar.evidencias = args.evidencias
    return correr(PORTAL, args, abrir_sesion, radicar)


if __name__ == "__main__":
    raise SystemExit(main())
