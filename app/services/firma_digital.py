"""Firma digital para dictámenes (Ronda 10 — versión pragmática).

No integramos directamente con una autoridad certificadora (eso requiere
contrato y pki infra), pero implementamos el MECANISMO institucional:

  1. Hash SHA-256 del dictamen final (en el momento exacto de "aprobar
     para radicación")
  2. Firma HMAC-SHA256 del hash con la clave secreta del sistema (SECRET_KEY)
  3. Cadena verificable: quien reciba el PDF puede llamar a
     /firma-digital/verificar?hash=...&firma=... y obtener confirmación
     de que viene del HUS sin modificaciones.

Cuando HUS contrate una PKI real (Andes SCD, Certicámara, etc.), solo
reemplazamos _firmar_hmac() por la llamada a la PKI y el flujo del
sistema no cambia.

Uso:
  firma = firmar_dictamen(texto_dictamen, usuario_email, glosa_id)
  → {hash, firma, timestamp, firmante, algoritmo}

  verificar_firma(hash, firma) → True/False
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime

from app.core.config import get_settings


ALGORITMO = "HMAC-SHA256-v1"


def _clave_firma() -> bytes:
    """Usa SECRET_KEY de la config como clave de HMAC."""
    cfg = get_settings()
    sk = cfg.secret_key or "clave-insegura-de-desarrollo"
    return sk.encode("utf-8")


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

    Args:
        texto_dictamen: el HTML/texto FINAL del dictamen (sin modificaciones
          posteriores).
        firmante_email: email del usuario que aprueba la radicación.
        glosa_id: id de la glosa (amarra la firma al registro).

    Returns:
        dict con hash, firma, timestamp ISO, firmante, algoritmo. Este dict
        se serializa y se adjunta al pie del PDF.
    """
    ts = datetime.utcnow().isoformat()
    h = _hash_sha256(texto_dictamen or "")
    payload_obj = {
        "hash": h,
        "firmante": firmante_email or "anon",
        "glosa_id": int(glosa_id),
        "timestamp": ts,
        "alg": ALGORITMO,
    }
    payload_str = json.dumps(payload_obj, sort_keys=True, ensure_ascii=False)
    firma = _firmar_hmac(payload_str)
    return {
        **payload_obj,
        "firma": firma,
        "payload": payload_str,  # útil para debug; el cliente ignora
    }


def verificar_firma(hash_esperado: str, firma_base64: str,
                     firmante: str, glosa_id: int, timestamp: str) -> bool:
    """Reconstruye el payload y valida que la firma sea correcta.

    Si alguno de los parámetros fue alterado (incluido el hash), la
    verificación falla.
    """
    if not hash_esperado or not firma_base64:
        return False
    payload_obj = {
        "hash": hash_esperado,
        "firmante": firmante or "anon",
        "glosa_id": int(glosa_id),
        "timestamp": timestamp,
        "alg": ALGORITMO,
    }
    payload_str = json.dumps(payload_obj, sort_keys=True, ensure_ascii=False)
    esperada = _firmar_hmac(payload_str)
    # comparación segura contra timing attacks
    return hmac.compare_digest(esperada, firma_base64)


def validar_hash_contenido(texto: str, hash_esperado: str) -> bool:
    """Valida que el hash del contenido entregado coincide con el firmado.
    Útil para detectar si alguien alteró el texto post-firma."""
    return _hash_sha256(texto or "") == (hash_esperado or "")
