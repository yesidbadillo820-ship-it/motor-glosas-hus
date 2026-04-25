"""Tests del servicio de alertas por correo — R51 P4."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.alerta_service import AlertaService, EmailService


class _GlosaFake:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class TestEmailServiceConfig:
    def test_sin_smtp_user_retorna_no_configurado(self, monkeypatch):
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        svc = EmailService()
        ok, msg = svc.enviar_alerta_glosas([
            _GlosaFake(id=1, eps="X", codigo_glosa="TA0201",
                      valor_objetado=100, dias_restantes=2, estado="RADICADA"),
        ])
        assert ok is False
        assert "SMTP" in msg or "configurado" in msg.lower()

    def test_sin_glosas_retorna_nada_para_alertar(self, monkeypatch):
        monkeypatch.setenv("SMTP_USER", "user@hus.com")
        monkeypatch.setenv("SMTP_PASSWORD", "x")
        svc = EmailService()
        ok, msg = svc.enviar_alerta_glosas([])
        assert ok is True
        assert "No hay glosas" in msg

    def test_sin_destinatarios_configurados(self, monkeypatch):
        monkeypatch.setenv("SMTP_USER", "user@hus.com")
        monkeypatch.setenv("SMTP_PASSWORD", "x")
        monkeypatch.delenv("ALERTAS_EMAIL", raising=False)
        svc = EmailService()
        ok, msg = svc.enviar_alerta_glosas([
            _GlosaFake(id=1, eps="FAMISANAR", codigo_glosa="TA0201",
                      valor_objetado=100, dias_restantes=2, estado="RADICADA"),
        ])
        assert ok is False
        assert "destinatarios" in msg.lower()


class TestRenderizadoHtmlYTexto:
    def test_html_contiene_datos_de_glosa(self):
        svc = EmailService()
        glosa = _GlosaFake(
            id=42, eps="FAMISANAR", codigo_glosa="TA0201",
            valor_objetado=168563, dias_restantes=3, estado="RADICADA",
        )
        html = svc._generar_html_alerta([glosa], dias_limite=5)
        assert "42" in html
        assert "FAMISANAR" in html
        assert "TA0201" in html
        assert "168,563" in html  # formato de miles

    def test_texto_plano_contiene_datos(self):
        svc = EmailService()
        glosa = _GlosaFake(
            id=7, eps="SALUD TOTAL", codigo_glosa="SO0101",
            valor_objetado=50000, dias_restantes=1, estado="RADICADA",
        )
        texto = svc._generar_texto_alerta([glosa], dias_limite=5)
        assert "SALUD TOTAL" in texto
        assert "SO0101" in texto
        assert "50,000" in texto

    def test_ordenamiento_por_dias_restantes(self):
        svc = EmailService()
        glosas = [
            _GlosaFake(id=1, eps="A", codigo_glosa="X", valor_objetado=100,
                       dias_restantes=5, estado="RADICADA"),
            _GlosaFake(id=2, eps="B", codigo_glosa="Y", valor_objetado=200,
                       dias_restantes=1, estado="RADICADA"),
        ]
        html = svc._generar_html_alerta(glosas, dias_limite=10)
        # La de días=1 (más urgente) debe aparecer antes que la de días=5
        pos_id1 = html.find(">1<")  # columna ID de glosa 1
        pos_id2 = html.find(">2<")  # columna ID de glosa 2
        assert pos_id2 < pos_id1


class TestAlertasEmail:
    def test_destinatarios_desde_env(self, monkeypatch):
        monkeypatch.setenv("ALERTAS_EMAIL", "a@hus.com, b@hus.com, c@hus.com")
        dest = EmailService()._obtener_destinatarios()
        assert dest == ["a@hus.com", "b@hus.com", "c@hus.com"]

    def test_destinatarios_vacio_sin_env(self, monkeypatch):
        monkeypatch.delenv("ALERTAS_EMAIL", raising=False)
        assert EmailService()._obtener_destinatarios() == []


class TestAlertaServiceOrquestador:
    def test_sin_alertas_no_envia(self, monkeypatch):
        """Si el repo no trae glosas, no se envía nada (exito=True)."""
        from app.repositories import glosa_repository as gr_mod
        mock_repo = MagicMock()
        mock_repo.alertas_proximas.return_value = []
        monkeypatch.setattr(gr_mod, "GlosaRepository",
                            lambda db: mock_repo)
        ok, msg = AlertaService().verificar_y_enviar_alertas(
            db=MagicMock(), dias_limite=5, forzar=False,
        )
        assert ok is True
        assert "No hay glosas" in msg

    def test_default_umbral_5_dias(self):
        assert AlertaService().dias_umbral_default == 5
