"""Incidente 3-jul-2026 (502 en producción): docker-compose inyectó
SMTP_PORT="" y Settings reventó al importar (crash-loop del contenedor).
Regresión en dos capas: Settings tolera envs vacías, y el compose no
puede volver a declarar variables con default vacío (VAR: ${VAR:-})."""

from __future__ import annotations

import re


def test_settings_arranca_con_smtp_port_vacio(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "")
    from app.core.config import Settings

    s = Settings()
    assert s.smtp_port == 587  # env vacía = no configurado → default


def test_settings_arranca_con_el_env_que_inyectaba_el_compose_roto(monkeypatch):
    """El set exacto de vars que el compose del 3-jul inyectaba en blanco."""
    for var in (
        "SMTP_PORT",
        "SMTP_HOST",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "ALLOWED_ORIGINS",
    ):
        monkeypatch.setenv(var, "")
    from app.core.config import Settings

    Settings()  # no debe lanzar


def test_compose_sin_defaults_vacios():
    """Guard de la CLASE de bug: ninguna variable del compose puede tener
    default vacío `${VAR:-}` — compose inyecta "" y los campos tipados de
    Settings mueren al parsear."""
    lineas = [
        ln
        for ln in open("docker-compose.yml", encoding="utf-8").read().splitlines()
        if not ln.strip().startswith("#")  # el comentario-advertencia trae el ejemplo
    ]
    vacias = re.findall(r"\$\{([A-Z_]+):-\}", "\n".join(lineas))
    # Excepciones deliberadas: secretos string opcionales que el código
    # trata como "no configurado" cuando están vacíos.
    permitidas = {
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "SENTRY_DSN",
        "POSTHOG_API_KEY",
        "ALLOWED_ORIGINS",
        # agente_lotes_token es str y "" significa "endpoints del agente
        # deshabilitados" — comportamiento diseñado (piloto 17-jul-2026).
        "AGENTE_LOTES_TOKEN",
    }
    problematicas = [v for v in vacias if v not in permitidas]
    assert not problematicas, (
        f"Variables con default VACÍO en docker-compose: {problematicas} — "
        "inyectan string vacío al contenedor y pueden tumbar el arranque "
        "(incidente 3-jul-2026, smtp_port)."
    )
