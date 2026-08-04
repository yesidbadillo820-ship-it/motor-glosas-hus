"""Quién está atendiendo: proceso, hora de arranque y clave de IA en uso.

Incidente 04-08-2026 (equipo local, Windows). El auditor cambió la clave de
Groq en el `.env` y reinició el motor. El arranque escribió en el log:

    [IA-PROVIDERS] primary=groq | groq=OK gsk_vn06EE… | anthropic=OK …

…pero la pantalla de Diagnóstico —que lee exactamente la misma variable—
mostraba `gsk_5CxaRq…`, y el análisis seguía fallando con «su clave está
inválida o vencida». Dos valores distintos de la misma variable en el mismo
servidor es imposible… dentro de UN proceso.

La causa (confirmada esa misma tarde, y NO era la que se sospechó primero):
en el PC del hospital corren **dos motores a la vez, en puertos distintos**.
El del puerto 8080 lo mantiene vivo `tools/servidor_motor_local.cmd` y es el
que alimenta la página por internet a través del túnel de Cloudflare; el del
8000 es el que el auditor levanta a mano para probar. El del 8080 llevaba
horas arriba, así que conservaba la clave y el código anteriores — y el
navegador estaba hablando con **ese**. De ahí las dos verdades.

(La primera hipótesis fue que en Windows dos uvicorn podían compartir el
mismo puerto. Quedó descartada en vivo: al intentar levantar un segundo
motor en el 8080 salió «WinError 10048 — solo se permite un uso de cada
dirección de socket». No comparten puerto; simplemente eran dos.)

Este módulo hace visible lo invisible: cuántos motores hay, en qué puerto,
desde cuándo, y con qué clave trabaja el que está respondiendo. Y distingue
lo que es una pelea de verdad (dos en el mismo puerto) de lo que es normal
en este equipo (dos instalaciones, cada una en lo suyo) — porque el aviso
anterior no lo distinguía y el auditor terminó cerrando la página pública.
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


def puerto_de(cmdline) -> str:
    """El puerto que sirve ese motor, leído de su propia línea de comando.

    Es el dato que faltaba el 04-08-2026 (segunda vuelta). El aviso decía
    «hay dos motores, cerrá el sobrante» y el auditor cerró… el que sirve
    la página por internet: `--port 8080`, el que mira el túnel de
    Cloudflare. No era un sobrante, era el otro sistema. Con el puerto a la
    vista, el aviso puede decir la verdad: si comparten puerto se pelean,
    y si no, son dos instalaciones distintas —cada una con su propia copia
    de las claves—.
    """
    partes = list(cmdline or [])
    for i, p in enumerate(partes):
        if p == "--port" and i + 1 < len(partes):
            return str(partes[i + 1]).strip()
        if str(p).startswith("--port="):
            return str(p).split("=", 1)[1].strip()
    return ""


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
                # Sin --port, uvicorn sirve en el 8000: se nombra así para que
                # el aviso no tenga huecos.
                "puerto": puerto_de(info.get("cmdline")) or "8000",
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
        quienes = ", ".join(
            f"PID {m['pid']} (puerto {m['puerto']}{', este' if m['soy_yo'] else ''})" for m in vivos
        )
        puertos = {m["puerto"] for m in vivos}

        # Mismo puerto = se pelean de verdad: uno de los dos sobra.
        if len(puertos) == 1:
            return {
                "estado": "error",
                "mensaje": (
                    f"Hay {len(vivos)} motores peleando por el mismo puerto ({quienes}). "
                    "Las respuestas salen de cualquiera de ellos, y el más viejo "
                    "puede tener la clave de IA o el código anteriores: por eso una "
                    "pantalla muestra un dato y otra muestra otro. Cerrá el sobrante "
                    "con doble clic en tools\\REINICIAR_MOTOR.cmd."
                ),
                "data": data,
            }

        # Puertos distintos: NO es un sobrante, son dos instalaciones. El
        # 04-08-2026 el aviso anterior decía «cerrá los sobrantes» y el
        # auditor cerró el motor del puerto 8080 — el que sirve la página
        # por internet. No estaba de más: era el otro sistema, con su propia
        # copia de las claves, y era justamente el que el navegador estaba
        # usando.
        nota = ""
        if "8080" in puertos:
            nota = (
                " En este equipo el del puerto 8080 es el que sirve la página por "
                "internet (el túnel), y el 8000 es el de pruebas locales: NO lo cierres "
                "pensando que sobra."
            )
        return {
            "estado": "warning",
            "mensaje": (
                f"Hay {len(vivos)} motores distintos corriendo en este equipo ({quienes}). "
                "No se estorban —cada uno tiene su puerto— pero son copias separadas: "
                "cada una leyó las claves y el código cuando arrancó, así que pueden "
                "mostrar datos distintos. Si cambiás el archivo de claves, hay que "
                "reiniciar TODAS." + nota
            ),
            "data": data,
        }

    detalle = f"Un solo motor atendiendo · PID {yo['pid']}"
    if vivos and vivos[0].get("puerto"):
        detalle += f" · puerto {vivos[0]['puerto']}"
    if claves.get("groq"):
        detalle += f" · clave Groq {claves['groq']}…"
    if claves.get("principal"):
        detalle += f" · proveedor principal {claves['principal'].upper()}"
    return {"estado": "ok", "mensaje": detalle, "data": data}
