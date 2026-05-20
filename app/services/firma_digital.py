"""Firma digital de dictámenes usando HMAC-SHA256.

Genera un hash SHA-256 del contenido del dictamen y una firma HMAC-SHA256
del hash usando la SECRET_KEY de configuración. Esto permite verificar
integridad del documento: si el hash cambia (texto modificado), la firma
ya no valida.

Esquema:
  hash = SHA256(texto)
  firma = HMAC-SHA256(secret, hash_hex)

Verificación (solo con hash + firma, sin necesidad del texto original):
  firma_esperada = HMAC-SHA256(secret, hash_hex_recibido)
  valida = compare_digest(firma_esperada, firma_recibida)
"""

import base64
import hashlib
import hmac
from datetime import datetime, timezone

from app.core.config import get_settings


def firmar_dictamen(
    texto_dictamen: str,
    firmante_email: str,
    glosa_id: int = 0,
) -> dict:
    """Genera la firma HMAC-SHA256 del dictamen.

    Args:
        texto_dictamen: Contenido HTML/texto del dictamen.
        firmante_email: Email del auditor que firma.
        glosa_id: ID de la glosa (informativo).

    Returns:
        dict con keys: hash, firma, alg, timestamp, firmante, verificable.
        - hash: SHA-256 hex del texto (64 chars).
        - firma: HMAC-SHA256(secret, hash_hex) en Base64.
    """
    cfg = get_settings()
    secret = (cfg.secret_key or "dev-secret").encode("utf-8")
    texto_bytes = texto_dictamen.encode("utf-8")

    # Hash del texto
    hash_hex = hashlib.sha256(texto_bytes).hexdigest()

    # Firma: HMAC del hash hex (no del texto completo)
    # Esto permite verificar sin tener el texto original.
    firma_bytes = hmac.new(secret, hash_hex.encode("utf-8"), hashlib.sha256).digest()
    firma_b64 = base64.b64encode(firma_bytes).decode("utf-8")

    return {
        "hash": hash_hex,
        "firma": firma_b64,
        "alg": "HMAC-SHA256",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "firmante": firmante_email,
        "verificable": True,
    }


def verificar_firma(hash_hex: str, firma_b64: str, texto_dictamen: str = "") -> bool:
    """Verifica la integridad de un dictamen firmado.

    Recomputa HMAC-SHA256(secret, hash_hex) y compara con firma_b64.
    No requiere el texto original — solo el hash y la firma.

    Si se proporciona texto_dictamen, también verifica que el hash
    corresponda al texto (doble verificación).

    Args:
        hash_hex: Hash SHA-256 de 64 chars hexadecimales.
        firma_b64: Firma HMAC-SHA256 en Base64.
        texto_dictamen: Texto original (opcional, para doble verificación).

    Returns:
        True si la firma es válida, False en caso contrario.
    """
    try:
        cfg = get_settings()
        secret = (cfg.secret_key or "dev-secret").encode("utf-8")

        # Si tenemos el texto, verificamos que el hash sea correcto
        if texto_dictamen:
            hash_esperado = hashlib.sha256(texto_dictamen.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(hash_esperado, hash_hex):
                return False

        # Verificar la firma HMAC sobre el hash hex
        firma_esperada_bytes = hmac.new(
            secret, hash_hex.encode("utf-8"), hashlib.sha256
        ).digest()
        try:
            firma_recibida_bytes = base64.b64decode(firma_b64)
        except Exception:
            return False

        return hmac.compare_digest(firma_esperada_bytes, firma_recibida_bytes)
    except Exception:
        return False
