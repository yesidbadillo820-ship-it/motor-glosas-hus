"""Cifrado opcional de campos sensibles con Fernet (AES-128 AEAD).

Activación: setear env var ``GLOSAS_ENCRYPTION_KEY`` con una clave Fernet.
Generar con:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Si la key NO está seteada, las funciones devuelven el texto plano y el
sistema sigue operando normalmente (backward compatible).

Uso:
    from app.services.cifrado import cifrar, descifrar
    dato_seguro = cifrar("nombre paciente")     # -> bytes base64 si hay key
    plano = descifrar(dato_seguro)               # -> str original
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger("motor_glosas")

_FERNET = None


def _get_fernet():
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = os.getenv("GLOSAS_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
        return _FERNET
    except Exception as e:
        logger.warning(f"GLOSAS_ENCRYPTION_KEY inválida: {e}")
        return None


def esta_habilitado() -> bool:
    return _get_fernet() is not None


def cifrar(texto: str | None) -> str | None:
    """Cifra el texto si hay Fernet configurado; si no, devuelve tal cual."""
    if texto is None or texto == "":
        return texto
    f = _get_fernet()
    if not f:
        return texto
    try:
        return "fenc:" + f.encrypt(texto.encode("utf-8")).decode("ascii")
    except Exception as e:
        logger.warning(f"Error cifrando: {e}")
        return texto


def descifrar(dato: str | None) -> str | None:
    """Descifra si el dato tiene prefijo ``fenc:``; si no, devuelve tal cual."""
    if not dato or not isinstance(dato, str):
        return dato
    if not dato.startswith("fenc:"):
        return dato
    f = _get_fernet()
    if not f:
        # clave desapareció — devolvemos el valor codificado para no crashear
        return dato
    try:
        return f.decrypt(dato[5:].encode("ascii")).decode("utf-8")
    except Exception as e:
        logger.warning(f"Error descifrando: {e}")
        return dato
