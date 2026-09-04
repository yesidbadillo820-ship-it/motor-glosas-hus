"""Con qué dirección se abre desde el celular la aplicación ya generada.

Existe por una lección que costó dos intentos en el curso de noruego: si el
programa imprime un hueco —«<la dirección con la que entra al Motor>»— tarde o
temprano alguien lo copia tal cual en el navegador y el celular contesta que la
página no existe. Aquí no se imprime ningún hueco: **o sale un enlace completo,
listo para copiar, o no sale enlace y se dice por qué**.

La dirección es la misma con la que el motor arma los enlaces de sus correos
(`APP_BASE_URL`). No se importa `app.core.config` —este módulo no depende del
motor— sino que se lee de donde el motor la lee: primero la variable de
entorno, después el `.env` del repositorio, y si no hay ninguna de las dos, el
mismo valor por defecto que trae el motor.
"""

from __future__ import annotations

import os
from pathlib import Path

#: La carpeta que el servidor del motor publica en `/static/`.
CARPETA_PUBLICADA = "static"

#: Las variables donde puede estar la dirección, en orden de preferencia.
#: `APP_BASE_URL` es la del motor; `MOTOR_GLOSAS_URL` la que ya usan los bots
#: del auditor (ver `docs/ENTREGA_MODULO_AGENTE_LOTES.md`).
VARIABLES = ("APP_BASE_URL", "MOTOR_GLOSAS_URL")

#: El mismo valor por defecto que `app/core/config.py`. Está repetido a
#: propósito: duplicar una constante pública es más barato que hacer que este
#: módulo dependa del motor para poder correr.
POR_DEFECTO = "https://iaglosassinac.help"

RAIZ = Path(__file__).resolve().parent.parent


def _limpiar(valor: str) -> str:
    """Quita comillas y la barra final, que si no salen dobles en el enlace."""
    return valor.strip().strip("\"'").rstrip("/")


def _del_env(ruta: Path) -> str | None:
    """Busca la dirección en el `.env` del motor, sin librerías."""
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.removeprefix("export ").strip().upper()
        if clave in VARIABLES and _limpiar(valor):
            return _limpiar(valor)
    return None


def direccion_del_motor(raiz: Path = RAIZ) -> str:
    """La dirección con la que se entra al Motor de Glosas, ya resuelta."""
    for variable in VARIABLES:
        valor = _limpiar(os.environ.get(variable, ""))
        if valor:
            return valor
    for candidato in (Path.cwd() / ".env", raiz / ".env"):
        valor = _del_env(candidato)
        if valor:
            return valor
    return POR_DEFECTO


def ruta_publicada(destino: Path, raiz: Path = RAIZ) -> str | None:
    """La ruta web de la aplicación, o None si quedó fuera de `static/`.

    Con `--salida` el auditor puede dejarla en cualquier carpeta. Si esa
    carpeta no la publica el servidor, no hay enlace que dar: se dice, en vez
    de inventar uno que no va a abrir.
    """
    try:
        dentro = (raiz / CARPETA_PUBLICADA).resolve()
        relativa = destino.resolve().relative_to(dentro)
    except (OSError, ValueError):
        return None
    return f"/{CARPETA_PUBLICADA}/{relativa.as_posix()}/index.html"


def enlace_celular(destino: Path, raiz: Path = RAIZ) -> str | None:
    """El enlace completo para copiar en el celular, o None si no lo hay."""
    ruta = ruta_publicada(destino, raiz)
    return None if ruta is None else f"{direccion_del_motor(raiz)}{ruta}"
