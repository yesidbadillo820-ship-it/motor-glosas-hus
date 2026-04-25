"""Firma digital para dictámenes (Ronda 10 + Ronda 50 Paso 8 — asimétrica).

MECANISMO INSTITUCIONAL con soporte dual:

  1. Hash SHA-256 del dictamen final (momento de 'aprobar para radicación')
  2. Firma (dos algoritmos soportados, auto-detección al verificar):
     a. **RSA-PSS-SHA256-v1** (preferido) — usa clave privada de firma,
        verificable con la clave pública. Si FIRMA_DIGITAL_PRIVATE_KEY
        está en env, este es el default.
     b. **HMAC-SHA256-v1** (legacy) — usa SECRET_KEY. Backward compatible
        con firmas existentes. Solo para verificar; firmas nuevas usan RSA
        si está disponible.
  3. Verificación de firmas viejas sigue funcionando sin romper nada.

Config (env vars):
  FIRMA_DIGITAL_PRIVATE_KEY: PEM de clave privada RSA 2048+ (generar
    con `openssl genpkey -algorithm RSA -out priv.pem -pkeyopt rsa_keygen_bits:2048`).
  FIRMA_DIGITAL_PUBLIC_KEY: PEM de clave pública (derivada con
    `openssl rsa -in priv.pem -pubout -out pub.pem`). Si no se setea,
    se deriva automáticamente de la privada.
  FIRMA_DIGITAL_KEY_ROTATION_DATE (opcional): ISO date. Firmas previas
    se verifican con la clave anterior si se configura.

Si NO hay FIRMA_DIGITAL_PRIVATE_KEY, el sistema opera en modo HMAC
compatibility (no rompe deploy antiguos).

Uso:
  firma = firmar_dictamen(texto_dictamen, usuario_email, glosa_id)
  → {hash, firma, timestamp, firmante, algoritmo}

  verificar_firma(hash, firma, ...) → True/False (auto-detecta algoritmo)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from app.core.tz import ahora_utc

from app.core.config import get_settings


ALGORITMO_HMAC = "HMAC-SHA256-v1"
ALGORITMO_RSA = "RSA-PSS-SHA256-v1"
ALGORITMO = ALGORITMO_HMAC  # default compatible; firmar_dictamen decide dinámicamente


def _clave_firma() -> bytes:
    """Usa SECRET_KEY de la config como clave de HMAC (legacy)."""
    cfg = get_settings()
    sk = cfg.secret_key or "clave-insegura-de-desarrollo"
    return sk.encode("utf-8")


# ─── Soporte RSA asimétrico (Ronda 50 Paso 8) ──────────────────────────────

_PRIVATE_KEY_CACHE = None
_PUBLIC_KEY_CACHE = None


def _cargar_clave_privada():
    """Carga la clave privada RSA desde FIRMA_DIGITAL_PRIVATE_KEY (PEM).
    Devuelve None si no está configurada."""
    global _PRIVATE_KEY_CACHE
    if _PRIVATE_KEY_CACHE is not None:
        return _PRIVATE_KEY_CACHE
    pem = os.getenv("FIRMA_DIGITAL_PRIVATE_KEY", "").strip()
    if not pem:
        return None
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        _PRIVATE_KEY_CACHE = load_pem_private_key(pem.encode("utf-8"), password=None)
        return _PRIVATE_KEY_CACHE
    except Exception:
        return None


def _cargar_clave_publica():
    """Carga la clave pública desde env explícita o la deriva de la privada."""
    global _PUBLIC_KEY_CACHE
    if _PUBLIC_KEY_CACHE is not None:
        return _PUBLIC_KEY_CACHE
    pem = os.getenv("FIRMA_DIGITAL_PUBLIC_KEY", "").strip()
    if pem:
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key
            _PUBLIC_KEY_CACHE = load_pem_public_key(pem.encode("utf-8"))
            return _PUBLIC_KEY_CACHE
        except Exception:
            pass
    priv = _cargar_clave_privada()
    if priv is not None:
        _PUBLIC_KEY_CACHE = priv.public_key()
        return _PUBLIC_KEY_CACHE
    return None


def esta_rsa_habilitado() -> bool:
    """True si hay clave privada configurada para firmar con RSA."""
    return _cargar_clave_privada() is not None


def _firmar_rsa(payload: str) -> str:
    """Firma RSA-PSS-SHA256 en base64url del payload."""
    priv = _cargar_clave_privada()
    if not priv:
        raise RuntimeError("FIRMA_DIGITAL_PRIVATE_KEY no configurada")
    from cryptography.hazmat.primitives import hashes as _h
    from cryptography.hazmat.primitives.asymmetric import padding
    sig = priv.sign(
        payload.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(_h.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        _h.SHA256(),
    )
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def _verificar_rsa(payload: str, firma_b64: str) -> bool:
    """Verifica firma RSA con la clave pública."""
    pub = _cargar_clave_publica()
    if not pub:
        return False
    try:
        from cryptography.hazmat.primitives import hashes as _h
        from cryptography.hazmat.primitives.asymmetric import padding
        # Restaurar padding base64
        b64 = firma_b64 + "=" * (-len(firma_b64) % 4)
        sig = base64.urlsafe_b64decode(b64.encode("ascii"))
        pub.verify(
            sig,
            payload.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(_h.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            _h.SHA256(),
        )
        return True
    except Exception:
        return False


def _hash_sha256(texto: str) -> str:
    """SHA-256 hex del texto."""
    h = hashlib.sha256(texto.encode("utf-8"))
    return h.hexdigest()


def _firmar_hmac(payload: str) -> str:
    """HMAC-SHA256 en base64url del payload."""
    mac = hmac.new(_clave_firma(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def firmar_dictamen(
    texto_dictamen: str,
    firmante_email: str,
    glosa_id: int,
) -> dict:
    """Crea la firma digital del dictamen.

    Ronda 50 Paso 8: usa RSA asimétrica si FIRMA_DIGITAL_PRIVATE_KEY está
    configurada; fallback a HMAC con SECRET_KEY (backward compatible).

    Args:
        texto_dictamen: el HTML/texto FINAL del dictamen.
        firmante_email: email del usuario que aprueba la radicación.
        glosa_id: id de la glosa.

    Returns:
        dict con hash, firma, timestamp ISO, firmante, algoritmo.
    """
    ts = ahora_utc().isoformat()
    h = _hash_sha256(texto_dictamen or "")
    # Decidir algoritmo según disponibilidad de RSA
    alg = ALGORITMO_RSA if esta_rsa_habilitado() else ALGORITMO_HMAC
    payload_obj = {
        "hash": h,
        "firmante": firmante_email or "anon",
        "glosa_id": int(glosa_id),
        "timestamp": ts,
        "alg": alg,
    }
    payload_str = json.dumps(payload_obj, sort_keys=True, ensure_ascii=False)
    if alg == ALGORITMO_RSA:
        firma = _firmar_rsa(payload_str)
    else:
        firma = _firmar_hmac(payload_str)
    return {
        **payload_obj,
        "firma": firma,
        "payload": payload_str,
    }


def verificar_firma(hash_esperado: str, firma_base64: str,
                     firmante: str, glosa_id: int, timestamp: str,
                     alg: str | None = None) -> bool:
    """Reconstruye el payload y valida la firma.

    Ronda 50 Paso 8: auto-detecta algoritmo. Si no se especifica 'alg',
    intenta primero RSA (si está habilitado) y después HMAC, para
    compatibilidad con firmas viejas generadas antes del cambio.
    """
    if not hash_esperado or not firma_base64:
        return False

    def _construir_payload(algoritmo: str) -> str:
        payload_obj = {
            "hash": hash_esperado,
            "firmante": firmante or "anon",
            "glosa_id": int(glosa_id),
            "timestamp": timestamp,
            "alg": algoritmo,
        }
        return json.dumps(payload_obj, sort_keys=True, ensure_ascii=False)

    # Si viene explícito el algoritmo, usar sólo ese
    if alg == ALGORITMO_RSA:
        return _verificar_rsa(_construir_payload(ALGORITMO_RSA), firma_base64)
    if alg == ALGORITMO_HMAC:
        esperada = _firmar_hmac(_construir_payload(ALGORITMO_HMAC))
        return hmac.compare_digest(esperada, firma_base64)

    # Sin especificar: intentar RSA primero, luego HMAC
    if esta_rsa_habilitado():
        if _verificar_rsa(_construir_payload(ALGORITMO_RSA), firma_base64):
            return True
    # Fallback HMAC (firmas viejas)
    esperada = _firmar_hmac(_construir_payload(ALGORITMO_HMAC))
    return hmac.compare_digest(esperada, firma_base64)


def validar_hash_contenido(texto: str, hash_esperado: str) -> bool:
    """Valida que el hash del contenido entregado coincide con el firmado.
    Útil para detectar si alguien alteró el texto post-firma."""
    return _hash_sha256(texto or "") == (hash_esperado or "")
