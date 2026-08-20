"""«¿Cómo miro eso acá?» — el registro de correos enviados (20-08-2026).

Yesid configuró el correo en el servidor y **los correos empezaron a salir**.
Pero en la bandeja de la cuenta que envía aparecieron los rebotes:

    🏥 Motor Glosas HUS — 150 glosas importadas desde recepción
       «Address not found — Your message wasn't delivered…»
       «Message blocked…»

Y preguntó cómo mirar eso desde el portal. No se podía: cada correo salía sin
dejar rastro, y para saber si algo se había enviado había que entrar a Gmail —
justo lo que un auditor no debería tener que hacer.

LO QUE ESTO SÍ Y NO RESUELVE, que es la mitad importante: acá queda si el
servidor de correo **aceptó** el mensaje. Que **llegue** al buzón es otra cosa;
cuando la dirección no existe, el rebote aparece minutos después en la cuenta
que envía y NO se ve desde acá. Prometer entrega sería mentir, así que la
pantalla lo dice.
"""

from __future__ import annotations

from app.services import email_service as es


class TestSeAnotaCadaIntento:
    def test_un_envio_bueno_queda_anotado(self, monkeypatch):
        anotados = []
        monkeypatch.setattr(
            es, "_anotar_envio", lambda d, a, ok, error="": anotados.append((d, a, ok, error))
        )
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "", raising=False)

        es._enviar_sync("gestor@hus.gov.co", "Prueba", "<p>x</p>")
        assert anotados, "no se anotó el intento"
        assert anotados[0][0] == "gestor@hus.gov.co"
        assert anotados[0][2] is False

    def test_sin_correo_configurado_dice_por_que(self, monkeypatch):
        anotados = []
        monkeypatch.setattr(
            es, "_anotar_envio", lambda d, a, ok, error="": anotados.append((d, a, ok, error))
        )
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "", raising=False)

        es._enviar_sync("x@hus.gov.co", "Prueba", "<p>x</p>")
        assert "no tiene correo configurado" in anotados[0][3]

    def test_si_el_registro_falla_el_correo_igual_sale(self, monkeypatch):
        """El registro es secundario: no puede tumbar un envío."""
        from app.core.config import get_settings

        def _revienta(*a, **kw):
            raise RuntimeError("la base no está")

        monkeypatch.setattr(es, "_anotar_envio", _revienta)  # revienta el registro
        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "", raising=False)

        # No debe propagar: devuelve False porque no hay SMTP, no porque
        # el registro haya fallado.
        try:
            resultado = es._enviar_sync("x@hus.gov.co", "Prueba", "<p>x</p>")
        except RuntimeError:
            raise AssertionError("un fallo del registro tumbó el envío") from None
        assert resultado is False


class TestElContextoSeDeduceDelAsunto:
    def test_reconoce_de_donde_salio(self):
        assert es._contexto_de("Prueba de correo — Motor de Glosas HUS") == "prueba"
        assert es._contexto_de("Motor Glosas HUS — 150 glosas importadas desde recepción") == (
            "recepcion"
        )
        assert es._contexto_de("Glosas que vencen en 3 días") == "vencimientos"

    def test_uno_desconocido_no_se_inventa(self):
        assert es._contexto_de("Cualquier otra cosa") == "otro"


class TestLoQueDiceLaPantalla:
    def test_el_endpoint_advierte_que_aceptado_no_es_entregado(self):
        """La mitad importante: no prometer lo que no se puede saber."""
        import inspect

        from app.api.routers import admin

        fuente = inspect.getsource(admin.correos_recientes)
        assert "ACEPTÓ" in fuente
        assert "Address not found" in fuente

    def test_el_modelo_guarda_lo_necesario(self):
        from app.models.db import EnvioCorreoRecord

        cols = {c.name for c in EnvioCorreoRecord.__table__.columns}
        for campo in ("destinatario", "asunto", "contexto", "aceptado", "error", "creado_en"):
            assert campo in cols, f"falta la columna {campo}"
