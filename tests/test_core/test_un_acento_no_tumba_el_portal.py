"""Un acento mal guardado en el .env no puede dejar al hospital sin portal.

20-08-2026. El `.env` del PC de cartera quedó con un guion largo en
codificación de Windows —en un COMENTARIO, ni siquiera en una clave—:

    # Generado por REVIVIR_EXPRESS_SIN_DOCKER.cmd — no compartir.

pydantic-settings lee ese archivo como UTF-8. Ese byte (0x97) no es UTF-8
válido, así que la construcción de la configuración reventaba y **el motor no
volvía a arrancar**. Cloudflare mostraba «Bad gateway · Host Error» y el área
de cartera se quedó sin portal, sin una sola pista de por qué.

Un archivo de texto mal guardado en una máquina no puede tumbar la
herramienta. Si el `.env` no es UTF-8 se reintenta con la codificación de
Windows y, en último caso, se arranca solo con las variables del entorno —
avisando en el registro, pero arrancando.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

# El renglón exacto que tumbó el portal: guion largo cp1252 (0x97).
LINEA_ROTA = b"# Generado por REVIVIR_EXPRESS_SIN_DOCKER.cmd \x97 no compartir.\n"


def _arrancar_con(env_bytes: bytes, tmp_path: Path) -> subprocess.CompletedProcess:
    (tmp_path / ".env").write_bytes(env_bytes)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(RAIZ)!r});"
            "from app.core.config import get_settings; c = get_settings();"
            "print('OK', (c.groq_api_key or ''))",
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=120,
    )


class TestElEnvRoto:
    def test_el_caso_real_no_es_utf8(self):
        """Si esto deja de ser cierto, la prueba dejó de reproducir el caso."""
        with pytest.raises(UnicodeDecodeError):
            LINEA_ROTA.decode("utf-8")

    def test_el_motor_arranca_igual(self, tmp_path):
        r = _arrancar_con(b"SECRET_KEY=abc\n" + LINEA_ROTA + b"GROQ_API_KEY=gsk_prueba\n", tmp_path)
        assert r.returncode == 0, f"el motor NO arrancó:\n{r.stderr[-700:]}"
        assert "OK" in r.stdout

    def test_y_las_claves_se_leen_bien(self, tmp_path):
        """Arrancar no basta: si pierde las claves, no sirve de nada."""
        r = _arrancar_con(b"SECRET_KEY=abc\n" + LINEA_ROTA + b"GROQ_API_KEY=gsk_prueba\n", tmp_path)
        assert "gsk_prueba" in r.stdout, r.stdout

    def test_una_clave_con_acento_tambien_sobrevive(self, tmp_path):
        r = _arrancar_con("SECRET_KEY=abc\nGROQ_API_KEY=gsk_ñandú\n".encode("cp1252"), tmp_path)
        assert r.returncode == 0, r.stderr[-500:]


class TestElEnvSano:
    def test_un_env_normal_sigue_funcionando(self, tmp_path):
        r = _arrancar_con("SECRET_KEY=abc\nGROQ_API_KEY=gsk_normal\n".encode(), tmp_path)
        assert r.returncode == 0
        assert "gsk_normal" in r.stdout

    def test_sin_env_arranca_con_el_entorno(self, tmp_path):
        r = _arrancar_con(b"", tmp_path)
        assert r.returncode == 0, r.stderr[-500:]


class TestElLectorBlindado:
    def test_existe_y_lo_usa_get_settings(self):
        fuente = (RAIZ / "app" / "core" / "config.py").read_text(encoding="utf-8")
        assert "_leer_configuracion" in fuente
        assert "settings = _leer_configuracion()" in fuente

    def test_reintenta_con_la_codificacion_de_windows(self):
        fuente = (RAIZ / "app" / "core" / "config.py").read_text(encoding="utf-8")
        assert "cp1252" in fuente

    def test_avisa_en_el_registro_en_vez_de_callar(self):
        """Que arranque no significa que se tape el problema."""
        fuente = (RAIZ / "app" / "core" / "config.py").read_text(encoding="utf-8")
        assert "no son UTF-8" in fuente
