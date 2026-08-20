"""El botón «Probar correo» del panel de Diagnóstico (20-08-2026).

Yesid importó el archivo de recepción DOS veces sin que saliera un solo
correo. La causa: el `.env` del servidor no tiene nada de correo —ni usuario,
ni contraseña—. Pero comprobarlo costaba volver a importar el archivo entero y
mirar el resultado: cinco minutos por intento, para algo que se responde en
dos segundos.

Este botón manda un mensaje al buzón de quien lo aprieta y dice qué pasó,
traduciendo los errores de SMTP —que son crípticos— a algo accionable.
"""

from __future__ import annotations

import pytest

from app.api.routers.admin import _explicar_error_smtp, probar_correo


class _Usuario:
    email = "glosashus09@sinacsc.com"
    rol = "SUPER_ADMIN"


class TestCuandoNoHayCorreoConfigurado:
    """El caso de Yesid."""

    @pytest.mark.asyncio
    async def test_lo_dice_sin_rodeos(self, monkeypatch):
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "", raising=False)

        r = await probar_correo(current_user=_Usuario())
        assert r["ok"] is False
        assert "no tiene correo configurado" in r["titulo"].lower()

    @pytest.mark.asyncio
    async def test_nombra_exactamente_lo_que_falta(self, monkeypatch):
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "", raising=False)

        r = await probar_correo(current_user=_Usuario())
        assert "SMTP_USER" in r["detalle"]
        assert "SMTP_PASSWORD" in r["detalle"]

    @pytest.mark.asyncio
    async def test_avisa_que_NINGUN_correo_sale(self, monkeypatch):
        """No solo el de recepción: también las alertas de vencimiento."""
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "", raising=False)

        r = await probar_correo(current_user=_Usuario())
        assert "vencimiento" in r["detalle"].lower()

    @pytest.mark.asyncio
    async def test_no_muestra_la_contraseña(self, monkeypatch):
        """Ni siquiera cuando está puesta: se dice «configurada» y ya."""
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "un-secreto-real", raising=False)

        r = await probar_correo(current_user=_Usuario())
        texto = str(r)
        assert "un-secreto-real" not in texto
        assert r["config"]["smtp_password"] == "(configurada)"


class TestCuandoSiEstaConfigurado:
    @pytest.mark.asyncio
    async def test_sale_el_correo_y_lo_confirma(self, monkeypatch):
        from app.api.routers import admin as mod
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "motor@sinacsc.com", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "xxxx", raising=False)

        async def _ok(destinatario, asunto, html, **kw):
            return True

        monkeypatch.setattr("app.services.email_service.enviar_email", _ok)
        r = await mod.probar_correo(current_user=_Usuario())
        assert r["ok"] is True
        assert r["destinatario"] == "glosashus09@sinacsc.com"

    @pytest.mark.asyncio
    async def test_si_el_servidor_lo_rechaza_lo_dice(self, monkeypatch):
        from app.api.routers import admin as mod
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "motor@sinacsc.com", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "xxxx", raising=False)

        async def _falla(destinatario, asunto, html, **kw):
            return False

        monkeypatch.setattr("app.services.email_service.enviar_email", _falla)
        r = await mod.probar_correo(current_user=_Usuario())
        assert r["ok"] is False
        assert "contraseña de aplicación" in r["detalle"]


class TestLosErroresSeTraducen:
    """Un error de SMTP en crudo no le dice nada al auditor."""

    def test_credenciales_malas_apunta_a_la_clave_de_aplicacion(self):
        msg = _explicar_error_smtp("(535, b'5.7.8 Username and Password not accepted')")
        assert "contraseña de aplicación" in msg

    def test_firewall(self):
        msg = _explicar_error_smtp("[Errno 110] Connection timed out")
        assert "firewall" in msg.lower()

    def test_host_malo(self):
        msg = _explicar_error_smtp("[Errno -2] Name or service not known")
        assert "SMTP_HOST" in msg

    def test_uno_desconocido_no_inventa_una_causa(self):
        msg = _explicar_error_smtp("algo rarísimo que nadie ha visto")
        assert "rechazó el envío" in msg
