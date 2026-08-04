"""Quién está atendiendo: proceso, hora de arranque y clave de IA en uso.

Incidente 04-08-2026 (equipo local, Windows). El auditor cambió la clave de
Groq en el `.env` y reinició el motor. El arranque escribió en el log:

    [IA-PROVIDERS] primary=groq | groq=OK gsk_vn06EE… | anthropic=OK …

…pero la pantalla de Diagnóstico —que lee exactamente la misma variable—
mostraba `gsk_5CxaRq…`, y el análisis seguía fallando con «su clave está
inválida o vencida». Dos valores distintos de la misma variable en el mismo
servidor es imposible… dentro de UN proceso.

La causa: había DOS motores vivos. En Windows un segundo `uvicorn` puede
quedarse con un puerto ya ocupado (SO_REUSEADDR no es exclusivo como en
Linux), así que las peticiones caían unas veces en el motor nuevo y otras en
el viejo: clave vieja, código viejo, resultados contradictorios. Nada en la
pantalla lo decía y el auditor perdió la tarde persiguiendo un archivo `.env`
que estaba bien.

Este módulo hace visible lo invisible: cuántos motores hay, desde cuándo, y
con qué clave está trabajando el que responde.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

# Un proceso cuenta como "motor" si sirve ESTA aplicación con un servidor
# ASGI. Un pytest o un script que importe app.main NO cuenta: no atiende
# el puerto.
_SERVIDORES = ("uvicorn", "gunicorn", "hypercorn", "daphne")
_APP = ("app.main", "app/main")


def _es_motor(cmdline) -> bool:
    texto = " ".join(cmdline or "").lower()
    if not any(a in texto for a in _APP):
        return False
    return any(s in texto for s in _SERVIDORES)


def prefijo(valor: str | None) -> str:
    """Los primeros 10 caracteres de una clave: identifican sin revelar.

    Es el mismo trozo que ya muestran el log de arranque y el Diagnóstico,
    justamente para poder compararlos de un vistazo.
    """
    valor = (valor or "").strip()
    return valor[:10] if valor else ""


def claves_en_uso() -> dict:
    """Prefijo de las claves que este proceso tiene cargadas AHORA."""
    from app.core.config import get_settings

    cfg = get_settings()
    return {
        "groq": prefijo(cfg.groq_api_key),
        "anthropic": prefijo(cfg.anthropic_api_key),
        "gemini": prefijo(cfg.gemini_api_key),
        "principal": (cfg.primary_ai or "").lower(),
    }


def _hora_arranque(pid: int) -> str | None:
    try:
        import psutil

        creado = psutil.Process(pid).create_time()
        return datetime.fromtimestamp(creado, tz=timezone.utc).isoformat()
    except Exception:
        return None


def huella() -> dict:
    """La cédula del proceso que está respondiendo esta petición."""
    return {
        "pid": os.getpid(),
        "arrancado_en": _hora_arranque(os.getpid()),
        "claves": claves_en_uso(),
    }


def _mi_cadena() -> set:
    """Mi PID y el de mis padres: con `--reload` el motor son dos procesos."""
    cadena = {os.getpid()}
    try:
        import psutil

        for padre in psutil.Process(os.getpid()).parents():
            cadena.add(padre.pid)
    except Exception:
        pass
    return cadena


def motores_vivos() -> list[dict]:
    """Los motores independientes que corren ahora mismo en esta máquina.

    `uvicorn --reload` son dos procesos (el vigilante y el que sirve) pero UN
    solo motor: por eso se cuentan únicamente las raíces —los procesos cuyo
    padre no es también un motor—.
    """
    try:
        import psutil
    except Exception:
        return []

    encontrados: dict[int, dict] = {}
    for proc in psutil.process_iter(["pid", "ppid", "cmdline", "create_time"]):
        try:
            info = proc.info
            if _es_motor(info.get("cmdline")):
                encontrados[info["pid"]] = info
        except Exception:
            continue

    mia = _mi_cadena()
    raices = []
    for info in encontrados.values():
        if info.get("ppid") in encontrados:
            continue  # es el hijo de otro motor: mismo motor
        creado = info.get("create_time")
        raices.append(
            {
                "pid": info["pid"],
                "arrancado_en": (
                    datetime.fromtimestamp(creado, tz=timezone.utc).isoformat() if creado else None
                ),
                "soy_yo": info["pid"] in mia,
                "comando": " ".join(info.get("cmdline") or [])[:160],
            }
        )
    raices.sort(key=lambda m: m["arrancado_en"] or "")
    return raices


def estado_motor() -> dict:
    """Sección lista para el panel de Diagnóstico (y para el log de arranque).

    Verde: un solo motor. Rojo: dos o más — no es un detalle técnico, es la
    diferencia entre trabajar con la clave nueva o con la vieja sin saberlo.
    """
    claves = claves_en_uso()
    yo = huella()
    vivos = motores_vivos()
    data = {
        "pid": yo["pid"],
        "arrancado_en": yo["arrancado_en"],
        "claves_en_uso": claves,
        "motores": vivos,
    }

    if len(vivos) > 1:
        pids = ", ".join(f"PID {m['pid']}{' (este)' if m['soy_yo'] else ''}" for m in vivos)
        return {
            "estado": "error",
            "mensaje": (
                f"Hay {len(vivos)} motores corriendo al mismo tiempo ({pids}). "
                "Las respuestas salen de cualquiera de ellos, y el más viejo "
                "puede tener la clave de IA o el código anteriores: por eso una "
                "pantalla muestra un dato y otra muestra otro. Cerrá los "
                "sobrantes con doble clic en tools\\REINICIAR_MOTOR.cmd."
            ),
            "data": data,
        }

    detalle = f"Un solo motor atendiendo · PID {yo['pid']}"
    if claves.get("groq"):
        detalle += f" · clave Groq {claves['groq']}…"
    if claves.get("principal"):
        detalle += f" · proveedor principal {claves['principal'].upper()}"
    return {"estado": "ok", "mensaje": detalle, "data": data}
