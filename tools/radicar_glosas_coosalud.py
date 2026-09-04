"""Radicador autónomo de COOSALUD — prueba de concepto (V3, Pilar 1).

QUÉ HACE. Le pide al motor UNA glosa lista para radicar, la radica en el
portal de COOSALUD con el navegador escondido, y le devuelve al motor el
comprobante. Nada más.

QUÉ **NO** HACE, a propósito:

  · No decide qué se radica. Eso lo decidió el motor con los escudos de la
    V2 (estado RESPONDIDA, liberación humana si vino del Auto-Pilot,
    control de calidad, dictamen no vencido).
  · No reintenta cuando no sabe si quedó. Si se pulsó «Terminar Respuesta»
    y no se alcanzó a ver el cartel de cierre, la fila queda para que una
    PERSONA mire el portal. Radicar dos veces le hace daño real al hospital.
  · No inventa pasos del portal: reutiliza las funciones ya probadas de
    `responder_glosas_coosalud.py` (login, abrir factura, terminar).

EL PILOTO ES OBLIGATORIO (regla del CLAUDE.md). Por defecto radica UNA sola
factura. Para ir por más hay que haber mirado esa primera y decirlo:

    py tools/radicar_glosas_coosalud.py                      (piloto de 1)
    py tools/radicar_glosas_coosalud.py --limite 20 --piloto-ok

CREDENCIALES: las lee del entorno del PC (COOSALUD_USER / COOSALUD_PASSWORD),
igual que el bot de respuestas. **El motor nunca las ve.**

REQUISITOS:
    py -m pip install playwright httpx
    py -m playwright install chromium
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import socket
import sys
from pathlib import Path
from typing import Any, Optional

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

logger = logging.getLogger("radicador_coosalud")

PORTAL = "COOSALUD"
MOTOR_POR_DEFECTO = "http://127.0.0.1:8080"


# ─── Regla del piloto ───────────────────────────────────────────────────


class PilotoNoConfirmado(RuntimeError):
    """Se pidió un masivo sin haber confirmado el piloto de 1 factura."""


def limite_efectivo(limite: int, piloto_ok: bool) -> int:
    """Cuántas facturas se pueden radicar en esta corrida.

    La regla del hospital es vieja y se ganó a golpes: antes de un cargue
    masivo, se corre UNA factura y se mira en el portal. Aquí no se confía
    en que el auditor se acuerde — el bot no deja pasar de una hasta que
    alguien diga, explícitamente, que revisó la primera.
    """
    if limite <= 1:
        return 1
    if not piloto_ok:
        raise PilotoNoConfirmado(
            f"Pidió radicar {limite} facturas de una. Primero corra el piloto de 1, "
            "mírela en el portal de COOSALUD y, si quedó bien, repita agregando "
            "--piloto-ok. (Regla del hospital: piloto antes de cualquier masivo.)"
        )
    return limite


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


# ─── Cliente de la cola del motor ───────────────────────────────────────


class ColaMotor:
    """Habla con el motor. Solo transporta QUÉ radicar y qué pasó."""

    def __init__(self, base_url: str, token: str, equipo: str, timeout: float = 30.0):
        import httpx

        self.base = base_url.rstrip("/")
        self.equipo = equipo
        self._c = httpx.Client(
            timeout=timeout, headers={"X-Agente-Token": token}, follow_redirects=True
        )

    def reclamar(self) -> Optional[dict]:
        r = self._c.post(
            f"{self.base}/radicacion/reclamar",
            json={"portal": PORTAL, "equipo": self.equipo},
        )
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def en_portal(self, rid: int) -> None:
        self._c.post(f"{self.base}/radicacion/{rid}/en-portal").raise_for_status()

    def radicada(self, rid: int, radicado: str, ruta: str = "", sha: str = "") -> dict:
        r = self._c.post(
            f"{self.base}/radicacion/{rid}/radicada",
            json={
                "radicado_numero": radicado,
                "comprobante_ruta": ruta,
                "comprobante_sha256": sha,
            },
        )
        r.raise_for_status()
        return r.json()

    def fallida(self, rid: int, error: str) -> None:
        self._c.post(f"{self.base}/radicacion/{rid}/fallida", json={"error": error[:4000]})

    def humano_requerido(self, rid: int, motivo: str) -> None:
        self._c.post(
            f"{self.base}/radicacion/{rid}/humano-requerido", json={"error": motivo[:4000]}
        )

    def cerrar(self) -> None:
        try:
            self._c.close()
        except Exception:
            pass


# ─── Una factura, de principio a fin ────────────────────────────────────


def radicar_una(page: Any, fila: dict, cola: ColaMotor, evidencias: Path) -> str:
    """Radica UNA glosa. Devuelve 'OK', 'DUDOSA' o 'FALLIDA'.

    El orden de las dos líneas del medio no es casual: se avisa al motor
    ANTES de pulsar. Si el PC se apaga en ese instante, la fila ya quedó
    marcada como dudosa y nadie la va a reintentar a ciegas.
    """
    from responder_glosas_coosalud import abrir_factura, terminar_respuesta

    rid = int(fila["radicacion_id"])
    factura = str(fila.get("factura") or "")
    logger.info(f"→ Factura {factura} (radicación {rid})")

    try:
        abrir_factura(page, factura)
    except Exception as e:
        # Todavía no se envió nada: se puede reintentar sin riesgo.
        cola.fallida(rid, f"No se pudo abrir la factura en el portal: {e}")
        logger.warning(f"  ✗ no se pudo abrir: {e}")
        return "FALLIDA"

    # ── El punto sin retorno ──
    cola.en_portal(rid)
    try:
        resultado = terminar_respuesta(page, factura, evidencias)
    except Exception as e:
        # Se pulsó y no sabemos si quedó: NO se marca fallida (eso invitaría
        # a reintentar). El motor la manda a verificación humana.
        cola.fallida(rid, f"Se envió y no se pudo confirmar: {e}")
        logger.warning(f"  ⚠ quedó DUDOSA, la revisa una persona: {e}")
        return "DUDOSA"

    if resultado != "OK":
        cola.fallida(rid, f"El portal no mostró el cartel de cierre ({resultado}).")
        logger.warning(f"  ⚠ quedó DUDOSA: {resultado}")
        return "DUDOSA"

    comprobante = evidencias / f"{factura}_cierre.png"
    ruta, sha = ("", "")
    if comprobante.is_file():
        ruta, sha = str(comprobante), sha256_de(comprobante)
    cola.radicada(rid, radicado=f"COOSALUD-{factura}", ruta=ruta, sha=sha)
    logger.info(f"  ✓ radicada · comprobante {comprobante.name}")
    return "OK"


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Radicador autónomo de COOSALUD (piloto de 1)")
    p.add_argument("--motor", default=os.environ.get("MOTOR_URL", MOTOR_POR_DEFECTO))
    p.add_argument("--limite", type=int, default=1, help="Cuántas radicar (por defecto 1).")
    p.add_argument(
        "--piloto-ok",
        action="store_true",
        help="Confirma que ya revisó la primera factura en el portal.",
    )
    p.add_argument("--con-cabeza", action="store_true", help="Mostrar el navegador.")
    p.add_argument("--lento", action="store_true", help="Ir despacio (para mirar).")
    p.add_argument("--evidencias", default="data/evidencias_radicacion")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        tope = limite_efectivo(args.limite, args.piloto_ok)
    except PilotoNoConfirmado as e:
        sys.stderr.write(f"\n  [!] {e}\n\n")
        return 2

    token = os.environ.get("AGENTE_LOTES_TOKEN", "").strip()
    if not token:
        sys.stderr.write(
            "\n  [!] Falta AGENTE_LOTES_TOKEN: es la llave con la que este bot\n"
            "      habla con el motor. Pídasela al administrador.\n\n"
        )
        return 2

    from responder_glosas_coosalud import _exigir_playwright, cargar_credenciales, login

    _exigir_playwright()
    from playwright.sync_api import sync_playwright

    usuario, clave = cargar_credenciales()
    evidencias = Path(args.evidencias)
    cola = ColaMotor(args.motor, token, equipo=socket.gethostname())
    parte = {"ok": 0, "dudosas": 0, "fallidas": 0}

    try:
        primera = cola.reclamar()
        if primera is None:
            logger.info("No hay nada pendiente de radicar en COOSALUD.")
            return 0

        with sync_playwright() as pw:
            navegador = pw.chromium.launch(
                headless=not args.con_cabeza, slow_mo=300 if args.lento else 0
            )
            page = navegador.new_page()
            try:
                login(page, usuario, clave)
                fila = primera
                while fila is not None and sum(parte.values()) < tope:
                    r = radicar_una(page, fila, cola, evidencias)
                    parte["ok" if r == "OK" else "dudosas" if r == "DUDOSA" else "fallidas"] += 1
                    if sum(parte.values()) >= tope:
                        break
                    fila = cola.reclamar()
            finally:
                navegador.close()
    finally:
        cola.cerrar()

    logger.info(
        f"\nListo. Radicadas: {parte['ok']} · dudosas (las mira una persona): "
        f"{parte['dudosas']} · fallidas: {parte['fallidas']}"
    )
    if tope == 1 and parte["ok"] == 1:
        logger.info(
            "Era el PILOTO: abra COOSALUD y confirme que esa factura quedó bien.\n"
            "Si quedó, repita con  --limite N --piloto-ok"
        )
    return 0 if not parte["fallidas"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
