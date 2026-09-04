"""Lo que comparten los radicadores de portal (V3, Pilar 1).

Cada portal tiene sus pantallas y sus mañas, pero la conversación con el motor
es SIEMPRE la misma: pedir una glosa, avisar antes de pulsar, y reportar qué
pasó. Eso vive aquí, una sola vez, para que un arreglo valga para los tres.

Lo que cada bot pone de su parte son dos funciones:

    abrir_sesion(playwright, args) -> (page, cerrar)
        Deja el navegador dentro del portal, como sea que ese portal entre.

    radicar(page, fila) -> (radicado, ruta_comprobante)
        Radica UNA glosa y devuelve la evidencia. Si no puede, levanta.
        Si levanta DESPUÉS de haber enviado, el motor la manda a
        verificación humana — nunca se reintenta a ciegas.

Arquitectura: docs/ARQUITECTURA_V3_PILAR1_RPA.md
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import socket
import sys
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("radicador")

MOTOR_POR_DEFECTO = "http://127.0.0.1:8080"


# ─── La regla del piloto ────────────────────────────────────────────────


class PilotoNoConfirmado(RuntimeError):
    """Se pidió un masivo sin haber confirmado el piloto de 1 factura."""


class SesionNoDisponible(RuntimeError):
    """El portal no dejó entrar sin una persona (captcha, token, 2FA).

    No es un fallo del bot: es un portal que no se puede automatizar en frío.
    Las glosas de esa corrida se marcan HUMANO_REQUERIDO con su motivo.
    """


def limite_efectivo(limite: int, piloto_ok: bool) -> int:
    """Cuántas facturas se pueden radicar en esta corrida.

    La regla del hospital se ganó a golpes: antes de un cargue masivo se corre
    UNA factura y se mira en el portal. Aquí no se confía en que el auditor se
    acuerde — el bot no deja pasar de una hasta que alguien diga,
    explícitamente, que revisó la primera.
    """
    if limite <= 1:
        return 1
    if not piloto_ok:
        raise PilotoNoConfirmado(
            f"Pidió radicar {limite} facturas de una. Primero corra el piloto de 1, "
            "mírela en el portal y, si quedó bien, repita agregando --piloto-ok. "
            "(Regla del hospital: piloto antes de cualquier masivo.)"
        )
    return limite


def sha256_de(ruta: Path) -> str:
    """Huella del comprobante. Peso probatorio (engancha con el Pilar 6)."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


# ─── La conversación con el motor ───────────────────────────────────────


class ColaMotor:
    """Solo transporta QUÉ radicar y qué pasó. Nunca credenciales."""

    def __init__(self, base_url: str, token: str, portal: str, equipo: str, timeout: float = 30.0):
        import httpx

        self.base = base_url.rstrip("/")
        self.portal = portal
        self.equipo = equipo
        self._c = httpx.Client(
            timeout=timeout, headers={"X-Agente-Token": token}, follow_redirects=True
        )

    def reclamar(self) -> Optional[dict]:
        r = self._c.post(
            f"{self.base}/radicacion/reclamar",
            json={"portal": self.portal, "equipo": self.equipo},
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


# ─── El molde de la línea de órdenes ────────────────────────────────────


def parser_comun(descripcion: str, evidencias_por_defecto: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=descripcion)
    p.add_argument("--motor", default=os.environ.get("MOTOR_URL", MOTOR_POR_DEFECTO))
    p.add_argument("--limite", type=int, default=1, help="Cuántas radicar (por defecto 1).")
    p.add_argument(
        "--piloto-ok",
        action="store_true",
        help="Confirma que ya revisó la primera factura en el portal.",
    )
    p.add_argument("--con-cabeza", action="store_true", help="Mostrar el navegador.")
    p.add_argument("--lento", action="store_true", help="Ir despacio (para mirar).")
    p.add_argument("--evidencias", default=evidencias_por_defecto)
    return p


# ─── El motor del bot: igual para los tres portales ─────────────────────


def correr(
    portal: str,
    args: Any,
    abrir_sesion: Callable[[Any, Any], tuple],
    radicar: Callable[[Any, dict], tuple[str, str]],
) -> int:
    """El ciclo completo. `abrir_sesion` y `radicar` los pone cada portal.

    El orden de las dos llamadas del medio no es casual: se avisa al motor
    ANTES de pulsar. Si el PC se apaga en ese instante, la fila ya quedó
    marcada como dudosa y nadie la va a reintentar a ciegas.
    """
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
            "      habla con el motor. Es la MISMA del .env del servidor.\n\n"
        )
        return 2

    cola = ColaMotor(args.motor, token, portal=portal, equipo=socket.gethostname())
    parte = {"ok": 0, "dudosas": 0, "fallidas": 0, "humano": 0}

    try:
        primera = cola.reclamar()
        if primera is None:
            logger.info(f"No hay nada pendiente de radicar en {portal}.")
            return 0

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            try:
                page, cerrar = abrir_sesion(pw, args)
            except SesionNoDisponible as e:
                # El portal exige una persona. Se devuelve la fila reclamada
                # al lugar correcto y se dice por qué, sin fingir autonomía.
                cola.humano_requerido(int(primera["radicacion_id"]), str(e))
                sys.stderr.write(f"\n  [!] {e}\n\n")
                return 3

            try:
                fila = primera
                while fila is not None and sum(parte.values()) < tope:
                    rid = int(fila["radicacion_id"])
                    factura = str(fila.get("factura") or "")
                    logger.info(f"→ Factura {factura} (radicación {rid})")
                    try:
                        cola.en_portal(rid)
                        radicado, comprobante = radicar(page, fila)
                    except Exception as e:  # noqa: BLE001
                        # Se pulsó y no sabemos si quedó: el motor la manda a
                        # verificación humana, NO de vuelta a la cola.
                        cola.fallida(rid, f"Se envió y no se pudo confirmar: {e}")
                        logger.warning(f"  ⚠ quedó DUDOSA, la revisa una persona: {e}")
                        parte["dudosas"] += 1
                    else:
                        ruta, sha = "", ""
                        if comprobante and Path(comprobante).is_file():
                            ruta = str(comprobante)
                            sha = sha256_de(Path(comprobante))
                        cola.radicada(rid, radicado=radicado, ruta=ruta, sha=sha)
                        logger.info(f"  ✓ radicada · {radicado}")
                        parte["ok"] += 1
                    if sum(parte.values()) >= tope:
                        break
                    fila = cola.reclamar()
            finally:
                cerrar()
    finally:
        cola.cerrar()

    logger.info(
        f"\nListo. Radicadas: {parte['ok']} · dudosas (las mira una persona): "
        f"{parte['dudosas']} · fallidas: {parte['fallidas']}"
    )
    if tope == 1 and parte["ok"] == 1:
        logger.info(
            f"Era el PILOTO: abra {portal} y confirme que esa factura quedó bien.\n"
            "Si quedó, repita con  --limite N --piloto-ok"
        )
    return 0 if not parte["fallidas"] else 1
