"""Tests del wrapper HTML de auditoría previa (R59 P3)."""
from __future__ import annotations

from app.services.glosa_service import GlosaService


def _svc():
    """Factory para tests — no necesita configuración real."""
    return GlosaService.__new__(GlosaService)


class TestWrapperAuditoriaHtml:
    def test_metadata_eps_codigo(self):
        html = _svc()._wrapper_auditoria_html(
            codigo="TA0201", eps="FAMISANAR",
            contenido_html="<p>hallazgos</p>",
        )
        assert "TA0201" in html
        assert "FAMISANAR" in html

    def test_no_contiene_jerga_de_defensa(self):
        """REGRESIÓN: el wrapper NO debe agregar 'NO ACEPTA' o
        'levantamiento' — esto desautoriza el modo neutral."""
        html = _svc()._wrapper_auditoria_html(
            codigo="X", eps="X", contenido_html="<p>x</p>",
        )
        assert "NO ACEPTA" not in html
        assert "levantamiento" not in html.lower()
        assert "respetuosamente" not in html.lower()

    def test_contiene_disclaimer(self):
        """Aviso explícito de que es informe INTERNO, no respuesta oficial."""
        html = _svc()._wrapper_auditoria_html(
            codigo="X", eps="X", contenido_html="",
        )
        assert "INFORME INTERNO" in html.upper() or "informe interno" in html.lower()
        assert "EPS" in html  # menciona que no es respuesta a EPS

    def test_pasa_contenido_sin_modificar(self):
        contenido = '<section data-block="resumen"><h3>1. Resumen</h3><p>caso x</p></section>'
        html = _svc()._wrapper_auditoria_html(
            codigo="X", eps="X", contenido_html=contenido,
        )
        # El wrapper solo envuelve, no toca el contenido del LLM
        assert contenido in html

    def test_factura_y_radicado_opcionales(self):
        html = _svc()._wrapper_auditoria_html(
            codigo="X", eps="X", contenido_html="",
            numero_factura="FE-2026-001", numero_radicado="RAD-99",
        )
        assert "FE-2026-001" in html
        assert "RAD-99" in html

    def test_sin_factura_ni_radicado_no_explota(self):
        html = _svc()._wrapper_auditoria_html(
            codigo="X", eps="X", contenido_html="",
            numero_factura=None, numero_radicado=None,
        )
        # No debe haber 'None' literal en el HTML
        assert "None" not in html

    def test_encabezado_dice_auditoria_previa(self):
        html = _svc()._wrapper_auditoria_html(
            codigo="X", eps="X", contenido_html="",
        )
        assert "Auditoría previa" in html or "AUDITORÍA PREVIA" in html.upper()


class TestModoAuditoriaIntegracion:
    def test_glosainput_acepta_modo_auditoria_previa(self):
        from app.models.schemas import GlosaInput
        g = GlosaInput(
            eps="FAMISANAR", etapa="RESPUESTA",
            tabla_excel="texto suficiente para validar",
            modo_respuesta="auditoria_previa",
        )
        assert g.modo_respuesta == "auditoria_previa"

    def test_get_system_prompt_auditoria_disponible(self):
        from app.services.glosa_ia_prompts import get_system_prompt_auditoria
        p = get_system_prompt_auditoria("FAMISANAR")
        # Debe ser distinto al prompt de defensa estándar
        from app.services.glosa_ia_prompts import get_system_prompt
        p_defensa = get_system_prompt("TA", "FAMISANAR")
        assert p != p_defensa
        # Y NO debe contener "ESE HUS NO ACEPTA"
        assert "AUDITOR" in p
