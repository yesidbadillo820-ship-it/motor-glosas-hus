"""Agente universal de bots del HUS: reclama trabajos de la cola y los corre.

Corre en un PC del hospital (doble clic en AGENTE_BOTS.cmd). Cada pocos
segundos le pregunta a la plataforma si hay trabajo encolado; si lo hay,
corre el bot que corresponda y reporta el resultado — la tarjeta del bot
en la pantalla de Automatización se actualiza sola.

Usa el MISMO token del agente de lotes (AGENTE_LOTES_TOKEN) y la misma
URL (MOTOR_GLOSAS_URL): si el agente de lotes ya está configurado en ese
PC, este no pide nada nuevo.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SEGUNDOS_ENTRE_CONSULTAS = 10
LIMITE_SEGUNDOS_BOT = 60 * 60  # una hora por trabajo: los masivos son largos


def _config_guardada() -> dict:
    """La misma configuración que guarda la ventana del agente de lotes."""
    base = os.environ.get("APPDATA") or str(Path.home())
    ruta = Path(base) / "MotorGlosasHUS" / "agente_lotes.json"
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _llamar(url: str, token: str, ruta: str, cuerpo: dict | None) -> tuple[int, dict]:
    datos = json.dumps(cuerpo or {}).encode("utf-8")
    peticion = urllib.request.Request(
        url.rstrip("/") + ruta,
        data=datos,
        headers={"Content-Type": "application/json", "X-Agente-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            if r.status == 204:
                return 204, {}
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}


def _correr_bot(comando: str, parametros: dict) -> tuple[bool, str, str]:
    """Corre el bot y captura su salida. Los parámetros van como variables
    de entorno BOT_PARAM_<NOMBRE> (cada bot lee las suyas si las necesita)."""
    entorno = dict(os.environ)
    for clave, valor in (parametros or {}).items():
        entorno[f"BOT_PARAM_{str(clave).upper()}"] = str(valor)
    piezas = shlex.split(comando, posix=(os.name != "nt"))
    try:
        proceso = subprocess.run(
            piezas,
            cwd=str(RAIZ),
            env=entorno,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LIMITE_SEGUNDOS_BOT,
        )
        salida = (proceso.stdout or "") + ("\n" + proceso.stderr if proceso.stderr else "")
        return (
            proceso.returncode == 0,
            salida[-18000:],
            ("" if proceso.returncode == 0 else f"El bot terminó con código {proceso.returncode}"),
        )
    except subprocess.TimeoutExpired:
        return False, "", f"El bot superó el límite de {LIMITE_SEGUNDOS_BOT // 60} minutos"
    except FileNotFoundError:
        return False, "", f"No se encontró el comando: {comando}"
    except Exception as e:  # el agente nunca se cae por un bot roto
        return False, "", f"{type(e).__name__}: {e}"


def main(argv=None) -> int:
    config = _config_guardada()
    parser = argparse.ArgumentParser(description="Agente universal de bots del HUS")
    parser.add_argument(
        "--url",
        default=os.environ.get("MOTOR_GLOSAS_URL", "") or config.get("url", ""),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENTE_LOTES_TOKEN", "") or config.get("token", ""),
    )
    parser.add_argument("--una-vez", action="store_true", help="Atiende un trabajo y sale")
    args = parser.parse_args(argv)

    if not args.url or not args.token:
        print(
            "ERROR: faltan MOTOR_GLOSAS_URL y/o AGENTE_LOTES_TOKEN.\n"
            "Son los mismos del agente de lotes: configúralos una vez y sirven para ambos."
        )
        return 2

    equipo = socket.gethostname()
    print(f"Agente de bots listo en {equipo}. Consultando cada {SEGUNDOS_ENTRE_CONSULTAS} s…")
    while True:
        estado, trabajo = _llamar(
            args.url, args.token, "/bots/trabajos/reclamar", {"equipo": equipo}
        )
        if estado == 200 and trabajo.get("trabajo_id"):
            tid = trabajo["trabajo_id"]
            comando = trabajo.get("comando") or ""
            print(f"→ Trabajo #{tid}: {trabajo.get('bot_id')} ({comando})")
            if not comando:
                _llamar(
                    args.url,
                    args.token,
                    f"/bots/trabajos/{tid}/finalizar",
                    {"exito": False, "error": "El bot no tiene comando configurado"},
                )
            else:
                _llamar(
                    args.url,
                    args.token,
                    f"/bots/trabajos/{tid}/progreso",
                    {"mensaje": f"Corriendo en {equipo}…"},
                )
                exito, registro, error = _correr_bot(comando, trabajo.get("parametros") or {})
                _llamar(
                    args.url,
                    args.token,
                    f"/bots/trabajos/{tid}/finalizar",
                    {"exito": exito, "registro": registro, "error": error},
                )
                print(f"   {'✓ terminado' if exito else '❌ ' + error}")
            if args.una_vez:
                return 0
        elif estado not in (200, 204):
            print(f"   aviso: el servidor respondió {estado}; reintento en un momento")
        if args.una_vez:
            return 0
        time.sleep(SEGUNDOS_ENTRE_CONSULTAS)


if __name__ == "__main__":
    sys.exit(main())
