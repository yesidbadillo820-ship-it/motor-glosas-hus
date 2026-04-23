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
