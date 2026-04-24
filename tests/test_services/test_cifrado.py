"""Tests del servicio de cifrado Fernet (Ronda 50 Paso 6)."""
from __future__ import annotations

import pytest

from app.services import cifrado


@pytest.fixture(autouse=True)
def _reset_fernet():
    """Cada test arranca con _FERNET reseteado (la singleton se recarga)."""
    cifrado._FERNET = None
    yield
    cifrado._FERNET = None


class TestSinKey:
    """Sin GLOSAS_ENCRYPTION_KEY: el sistema opera en modo plano."""

    def test_esta_habilitado_false(self, monkeypatch):
        monkeypatch.delenv("GLOSAS_ENCRYPTION_KEY", raising=False)
        assert cifrado.esta_habilitado() is False

    def test_cifrar_devuelve_plano(self, monkeypatch):
        monkeypatch.delenv("GLOSAS_ENCRYPTION_KEY", raising=False)
        assert cifrado.cifrar("secreto") == "secreto"

    def test_descifrar_sin_prefijo_devuelve_plano(self, monkeypatch):
        monkeypatch.delenv("GLOSAS_ENCRYPTION_KEY", raising=False)
        assert cifrado.descifrar("texto plano") == "texto plano"


class TestConKey:
    """Con key válida: cifra y descifra round-trip."""

    @pytest.fixture
    def key_valida(self, monkeypatch):
        # Generar key Fernet válida para el test
        from cryptography.fernet import Fernet
        k = Fernet.generate_key().decode()
        monkeypatch.setenv("GLOSAS_ENCRYPTION_KEY", k)
        cifrado._FERNET = None  # forzar recarga
        return k

    def test_esta_habilitado_true(self, key_valida):
        assert cifrado.esta_habilitado() is True

    def test_cifrar_produce_prefijo_y_base64(self, key_valida):
        c = cifrado.cifrar("datos sensibles")
        assert c is not None
        assert c.startswith("fenc:")
        assert c != "datos sensibles"

    def test_round_trip(self, key_valida):
        original = "paciente: María G., 45 años, DM tipo 2"
        cifrado_val = cifrado.cifrar(original)
        recuperado = cifrado.descifrar(cifrado_val)
        assert recuperado == original

    def test_round_trip_unicode(self, key_valida):
        original = "Hernández — España — 测试"
        assert cifrado.descifrar(cifrado.cifrar(original)) == original


class TestCasosEdge:
    def test_cifrar_none(self):
        assert cifrado.cifrar(None) is None

    def test_cifrar_string_vacio(self):
        assert cifrado.cifrar("") == ""

    def test_descifrar_none(self):
        assert cifrado.descifrar(None) is None

    def test_descifrar_string_vacio(self):
        assert cifrado.descifrar("") == ""

    def test_descifrar_valor_no_cifrado_pasa(self, monkeypatch):
        # Tiene una key pero el dato no está cifrado (no tiene prefijo fenc:)
        from cryptography.fernet import Fernet
        monkeypatch.setenv("GLOSAS_ENCRYPTION_KEY", Fernet.generate_key().decode())
        cifrado._FERNET = None
        assert cifrado.descifrar("valor antiguo plano") == "valor antiguo plano"

    def test_key_invalida_no_crashea(self, monkeypatch):
        monkeypatch.setenv("GLOSAS_ENCRYPTION_KEY", "key-claramente-invalida")
        cifrado._FERNET = None
        # No debería levantar — se loguea warning y devuelve tal cual
        assert cifrado.cifrar("test") == "test"
        assert cifrado.esta_habilitado() is False
