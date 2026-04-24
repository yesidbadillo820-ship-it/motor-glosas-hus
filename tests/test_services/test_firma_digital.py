"""Tests de la firma digital (Ronda 10)."""
from app.services.firma_digital import (
    firmar_dictamen,
    validar_hash_contenido,
    verificar_firma,
)


def test_firmar_y_verificar_ok():
    texto = "Dictamen de prueba: ESE HUS no acepta la glosa TA0201."
    firma = firmar_dictamen(texto, "test@hus.gov.co", 42)
    assert "hash" in firma and "firma" in firma
    assert len(firma["hash"]) == 64  # SHA-256 hex
    assert len(firma["firma"]) > 20
    # Verificación correcta
    ok = verificar_firma(
        hash_esperado=firma["hash"],
        firma_base64=firma["firma"],
        firmante=firma["firmante"],
        glosa_id=firma["glosa_id"],
        timestamp=firma["timestamp"],
    )
    assert ok


def test_firma_falla_si_hash_modificado():
    texto = "Dictamen original."
    firma = firmar_dictamen(texto, "u@hus.gov.co", 1)
    # Modificar el hash intencionalmente
    ok = verificar_firma(
        hash_esperado="0" * 64,
        firma_base64=firma["firma"],
        firmante=firma["firmante"],
        glosa_id=firma["glosa_id"],
        timestamp=firma["timestamp"],
    )
    assert not ok


def test_firma_falla_si_timestamp_modificado():
    firma = firmar_dictamen("x", "u@hus.gov.co", 1)
    ok = verificar_firma(
        hash_esperado=firma["hash"],
        firma_base64=firma["firma"],
        firmante=firma["firmante"],
        glosa_id=firma["glosa_id"],
        timestamp="2099-01-01T00:00:00",
    )
    assert not ok


def test_validar_hash_contenido():
    texto = "hola mundo"
    firma = firmar_dictamen(texto, "u@hus.gov.co", 1)
    assert validar_hash_contenido(texto, firma["hash"])
    assert not validar_hash_contenido("hola mundo!", firma["hash"])


# ─── Ronda 50 Paso 8: firma RSA asimétrica ──────────────────────────────

import pytest


@pytest.fixture
def rsa_key_configurada(monkeypatch):
    """Genera un par RSA temporal y lo inyecta vía env vars."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_priv = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("FIRMA_DIGITAL_PRIVATE_KEY", pem_priv)
    # Reset cache
    from app.services import firma_digital as fd
    fd._PRIVATE_KEY_CACHE = None
    fd._PUBLIC_KEY_CACHE = None
    yield
    fd._PRIVATE_KEY_CACHE = None
    fd._PUBLIC_KEY_CACHE = None


def test_rsa_habilitado_sin_env(monkeypatch):
    monkeypatch.delenv("FIRMA_DIGITAL_PRIVATE_KEY", raising=False)
    from app.services import firma_digital as fd
    fd._PRIVATE_KEY_CACHE = None
    assert fd.esta_rsa_habilitado() is False


def test_rsa_habilitado_con_env(rsa_key_configurada):
    from app.services import firma_digital as fd
    assert fd.esta_rsa_habilitado() is True


def test_firma_usa_rsa_cuando_hay_clave(rsa_key_configurada):
    from app.services.firma_digital import (
        firmar_dictamen, verificar_firma, ALGORITMO_RSA,
    )
    r = firmar_dictamen("texto dictamen", "firmante@hus.com", 42)
    assert r["alg"] == ALGORITMO_RSA
    assert verificar_firma(r["hash"], r["firma"], r["firmante"], r["glosa_id"], r["timestamp"])


def test_verificar_falla_con_firma_alterada(rsa_key_configurada):
    from app.services.firma_digital import firmar_dictamen, verificar_firma
    r = firmar_dictamen("texto", "x@hus.com", 1)
    # Alterar la firma
    firma_mala = r["firma"][:-4] + "XXXX"
    assert verificar_firma(r["hash"], firma_mala, r["firmante"], r["glosa_id"], r["timestamp"]) is False


def test_firma_vieja_hmac_sigue_verificandose(monkeypatch):
    """Backward compat: firmas HMAC generadas antes del Paso 8 se verifican."""
    monkeypatch.delenv("FIRMA_DIGITAL_PRIVATE_KEY", raising=False)
    from app.services import firma_digital as fd
    fd._PRIVATE_KEY_CACHE = None
    from app.services.firma_digital import (
        firmar_dictamen, verificar_firma, ALGORITMO_HMAC,
    )
    r = firmar_dictamen("abc", "y@hus.com", 2)
    assert r["alg"] == ALGORITMO_HMAC
    assert verificar_firma(r["hash"], r["firma"], r["firmante"], r["glosa_id"], r["timestamp"])
