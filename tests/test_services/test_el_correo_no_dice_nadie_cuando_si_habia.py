"""«Nadie a quien enviarlo» solo cuando de verdad no había nadie (20-08-2026).

El estado del envío se decidía así: si no salió ningún correo → «✗ nadie a
quien enviarlo». Sin mirar si **sí había destinatarios** y lo que falló fue el
servidor de correo.

Eso manda al auditor a revisar la lista de gestores —que está bien— mientras
el problema está en otro lado. Nos pasó hoy: el `.env` no tenía la
configuración del correo y la pantalla decía «nadie a quien enviarlo».

Es la misma familia de defecto que veníamos corrigiendo toda la jornada: un
mensaje que no distingue causas manda a buscar donde no es.
"""

from __future__ import annotations

from app.services.auto_responder_service import _actualizar_estado_recepcion


def _estado(envio: dict, monkeypatch) -> str:
    """Corre la decisión sin tocar la base: se captura lo que iba a guardar."""

    class _Rec:
        def __init__(self):
            self.estado = "LISTO"

    rec = _Rec()

    class _Q:
        def filter(self, *a, **k):
            return self

        def first(self):
            return rec

    class _S:
        def query(self, *a, **k):
            return _Q()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("app.database.SessionLocal", lambda: _S())
    _actualizar_estado_recepcion(1, envio)
    return rec.estado


class TestCuandoElServidorRechaza:
    def test_no_dice_que_no_habia_a_quien_enviarle(self, monkeypatch):
        estado = _estado({"enviados": 0, "destinatarios": 3, "motivo": "FALLO_ENVIO"}, monkeypatch)
        assert estado == "FALLO_ENVIO"
        assert estado != "SIN_DESTINATARIOS"


class TestCuandoDeVerdadNoHabiaNadie:
    def test_ahi_si_lo_dice(self, monkeypatch):
        estado = _estado({"enviados": 0, "destinatarios": 0, "motivo": ""}, monkeypatch)
        assert estado == "SIN_DESTINATARIOS"


class TestLosDemasCasosNoCambian:
    def test_sin_correo_configurado_sigue_igual(self, monkeypatch):
        estado = _estado(
            {"enviados": 0, "destinatarios": 2, "motivo": "SIN_CORREO_CONFIG"}, monkeypatch
        )
        assert estado == "SIN_CORREO_CONFIG"

    def test_sin_archivo_original_sigue_igual(self, monkeypatch):
        estado = _estado(
            {"enviados": 0, "destinatarios": 2, "motivo": "SIN_ARCHIVO_ORIGINAL"}, monkeypatch
        )
        assert estado == "SIN_ARCHIVO_ORIGINAL"

    def test_todo_bien_sigue_siendo_enviado(self, monkeypatch):
        estado = _estado({"enviados": 3, "gestores_sin_email": []}, monkeypatch)
        assert estado == "ENVIADO"

    def test_con_gestores_sin_email_sigue_siendo_parcial(self, monkeypatch):
        estado = _estado({"enviados": 2, "gestores_sin_email": ["CAROLINA"]}, monkeypatch)
        assert estado == "PARCIAL"


class TestLaPantallaLoSabeDecir:
    def test_hay_etiqueta_para_el_fallo_del_servidor(self):
        import pathlib

        html = (
            pathlib.Path(__file__).resolve().parents[2] / "static/importar-recepcion.html"
        ).read_text(encoding="utf-8")
        assert "FALLO_ENVIO" in html
        assert "el servidor de correo rechazó el envío" in html
