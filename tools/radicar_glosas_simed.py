"""Radicador autónomo de SIMED — Dispensario Médico (V3, Pilar 1).

Mismo patrón que el de COOSALUD: pide una glosa al motor, la radica con el
navegador escondido y devuelve el comprobante. La conversación con el motor
vive en `radicador_comun.py`; aquí solo van los pasos propios del portal, y
esos se reutilizan de `responder_glosas_simed.py`, que ya está probado.

EL PILOTO ES OBLIGATORIO. Por defecto radica UNA factura y se detiene:

    py tools/radicar_glosas_simed.py                      (piloto de 1)
    py tools/radicar_glosas_simed.py --limite 20 --piloto-ok

OJO CON EL CUV. Antes de cargar notas crédito al SIMED se valida el CUV
(`tools/verificar_cuv_notas.py`): el portal acepta notas con CUV inválido pero
quedan mal radicadas. Este bot radica RESPUESTAS DE GLOSA, no notas, así que
no le aplica — pero conviene no confundir los dos flujos.

CREDENCIALES: del entorno del PC, igual que el bot de respuestas.
**El motor nunca las ve.**
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

PORTAL = "SIMED"


def abrir_sesion(pw, args):
    from responder_glosas_simed import cargar_credenciales, login

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
        raise SesionNoDisponible(f"No se pudo entrar a SIMED: {e}") from e
    return page, navegador.close


def radicar(page, fila: dict) -> tuple[str, str]:
    """Abre la factura y pulsa el botón de enviar del portal.

    `enviar_finalizar` es la misma función que usa el bot de respuestas: filtra
    la factura en la grilla, pulsa el botón verde y valida el OK del portal.
    Devuelve el texto de confirmación, que es la evidencia de que quedó.
    """
    from responder_glosas_simed import abrir_factura, enviar_finalizar, normalizar_factura

    factura = str(fila.get("factura") or "")
    corta = normalizar_factura(factura)
    evidencias = Path(radicar.evidencias)
    evidencias.mkdir(parents=True, exist_ok=True)

    abrir_factura(page, corta)
    resultado = enviar_finalizar(page, corta, evidencias)
    if not resultado or "OK" not in str(resultado).upper():
        raise RuntimeError(f"El portal no confirmó el envío ({resultado}).")

    # `enviar_finalizar` deja su pantallazo en la carpeta de evidencias; se
    # busca el más reciente de esta factura para guardar su huella.
    candidatos = sorted(
        evidencias.glob(f"*{corta}*.png"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    comprobante = str(candidatos[0]) if candidatos else ""
    return f"SIMED-{corta}", comprobante


def main(argv=None) -> int:
    p = parser_comun(
        "Radicador autónomo de SIMED / Dispensario (piloto de 1)",
        "data/evidencias_radicacion",
    )
    args = p.parse_args(argv)
    radicar.evidencias = args.evidencias
    return correr(PORTAL, args, abrir_sesion, radicar)


if __name__ == "__main__":
    raise SystemExit(main())
