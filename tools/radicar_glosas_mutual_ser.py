"""Radicador autónomo de MUTUAL SER (V3, Pilar 1).

MUTUAL SER TIENE reCAPTCHA — y eso manda sobre el diseño.

La matriz de portales lo clasificó como automatizable, pero el bot de
respuestas que ya existe entra con `login_interactivo(...timeout_captcha_s)`:
una persona resuelve el captcha en pantalla y la sesión queda guardada en un
archivo (`storage_state`) para reusarla después sin captcha.

Por eso este radicador NO intenta pasar el captcha ni finge autonomía:

  · Si hay una SESIÓN GUARDADA y sigue viva → radica solo, escondido.
  · Si NO la hay (o venció) → NO adivina: marca la glosa HUMANO_REQUERIDO
    con el motivo, y le dice al auditor cómo sembrar la sesión.

Sembrar la sesión (una vez, cuando venza):

    py tools/responder_glosas_mutual_ser.py --con-cabeza ...
    (resolver el captcha; la sesión queda guardada)

Después, el piloto:

    py tools/radicar_glosas_mutual_ser.py                      (piloto de 1)
    py tools/radicar_glosas_mutual_ser.py --limite 20 --piloto-ok

CREDENCIALES: del entorno del PC. **El motor nunca las ve.**
"""

from __future__ import annotations

import sys
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

from radicador_comun import (  # noqa: E402
    PilotoNoConfirmado,  # noqa: F401
    SesionNoDisponible,
    correr,
    limite_efectivo,  # noqa: F401
    parser_comun,
)

PORTAL = "MUTUAL_SER"
SESION_POR_DEFECTO = "data/mutualser_sesion.json"

_COMO_SEMBRAR = (
    "MUTUAL SER pide reCAPTCHA y no hay sesión guardada válida. Un robot no "
    "puede resolverlo. Siembre la sesión UNA vez con:\n"
    "    py tools/responder_glosas_mutual_ser.py --con-cabeza\n"
    "resuelva el captcha en pantalla, y vuelva a correr este radicador."
)


def abrir_sesion(pw, args):
    from responder_glosas_mutual_ser import _exigir_playwright, _login_ok

    _exigir_playwright()
    sesion = Path(args.storage_state)
    if not sesion.is_file():
        raise SesionNoDisponible(_COMO_SEMBRAR)

    navegador = pw.chromium.launch(headless=not args.con_cabeza, slow_mo=300 if args.lento else 0)
    ctx = navegador.new_context(storage_state=str(sesion))
    page = ctx.new_page()
    try:
        from responder_glosas_mutual_ser import PORTAL_LOGIN

        page.goto(PORTAL_LOGIN, wait_until="domcontentloaded")
        if not _login_ok(page):
            raise SesionNoDisponible(
                "La sesión guardada de MUTUAL SER ya venció.\n" + _COMO_SEMBRAR
            )
    except SesionNoDisponible:
        navegador.close()
        raise
    except Exception as e:
        navegador.close()
        raise SesionNoDisponible(f"No se pudo reusar la sesión de MUTUAL SER: {e}") from e
    return page, navegador.close


def radicar(page, fila: dict) -> tuple[str, str]:
    """Cierra en el portal una respuesta YA cargada.

    Se usa `solo_finalizar=True`, que es justo lo que hace un radicador: no
    vuelve a llenar ni a subir soportes —eso ya lo hizo el bot de respuestas—,
    entra a subsanar, elige el código y envía. `grupos` va vacío a propósito:
    esa rama no lo usa, y fabricarle datos sería inventar.
    """
    from responder_glosas_mutual_ser import normalizar_factura, procesar_factura

    factura = str(fila.get("factura") or "")
    corta = normalizar_factura(factura)
    evidencias = Path(radicar.evidencias)
    evidencias.mkdir(parents=True, exist_ok=True)

    codigo = str(fila.get("codigo_respuesta") or "").strip() or "RE9901"
    reg = procesar_factura(
        page,
        corta,
        {"grupos": []},
        evidencias,
        finalizar=True,
        codigo=codigo,
        solo_finalizar=True,
    )
    if str(reg.get("estado") or "").upper() != "OK":
        raise RuntimeError(f"El portal no confirmó el envío ({reg.get('detalle')}).")

    candidatos = sorted(
        evidencias.glob(f"*{corta}*.png"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return f"MUTUALSER-{corta}", str(candidatos[0]) if candidatos else ""


def main(argv=None) -> int:
    p = parser_comun("Radicador autónomo de MUTUAL SER (piloto de 1)", "data/evidencias_radicacion")
    p.add_argument(
        "--storage-state",
        default=SESION_POR_DEFECTO,
        help="Archivo con la sesión sembrada a mano (por el reCAPTCHA).",
    )
    args = p.parse_args(argv)
    radicar.evidencias = args.evidencias
    return correr(PORTAL, args, abrir_sesion, radicar)


if __name__ == "__main__":
    raise SystemExit(main())
