"""La argumentación no puede nombrar soportes que no están — 19-08-2026.

Segunda vuelta. La tabla «RELACIÓN DE SOPORTES APORTADOS» ya sale del
expediente real, pero **la argumentación** —que es el texto que se radica—
seguía inventando. Respondiendo una glosa SO0201 de la factura HUS468334 por
«ausencia de soportes de la CONSULTA DE URGENCIAS», el dictamen escribió:

    «LA FACTURA HUS468334 INCLUYE LA FACTURA ELECTRÓNICA, AUTORIZACIÓN
     PREVIA, EPICRISIS, HOJA DE ADMINISTRACIÓN DE MEDICAMENTOS, APOYO
     DIAGNÓSTICO, DESCRIPCIÓN QUIRÚRGICA, RIPS JSON Y CUV»

Ni la autorización previa ni la descripción quirúrgica están en ese
expediente — y era una consulta de urgencias, no hubo cirugía. **El propio
dictamen se contradecía**: el texto afirmaba documentos que su tabla no
listaba, en la misma hoja.

El prompt ya prohíbe inventar normas y estimar tarifas, pero no decía nada de
los soportes. Como no se puede tocar el prompt global, el inventario
verificado se le pasa como DATO DEL CASO, que es lo que es.
"""

from __future__ import annotations

import pytest

from app.api.routers.analizar import _inventario_de_soportes

EXPEDIENTE = [
    ("FEV_900006037_HUS468334.pdf", "factura_electronica"),
    ("HEV_900006037_HUS468334.pdf", "historia_clinica"),
    ("EPI_900006037_HUS468334.pdf", "epicrisis"),
    ("HAU_900006037_HUS468334.pdf", "hoja_atencion_urgencias"),
    ("HAM_900006037_HUS468334.pdf", "hoja_administracion_medicamentos"),
    ("HUS468334.json", "rips"),
]


@pytest.fixture
def con_expediente(monkeypatch):
    from app.services import soportes_autodiscovery_service as svc

    class _Idx:
        def lookup(self, factura, auto_rebuild=True):
            if "468334" not in (factura or ""):
                return []
            return [{"nombre_archivo": n, "tipo": t, "ruta": "/srv/" + n} for n, t in EXPEDIENTE]

    monkeypatch.setattr(svc, "get_indexer", lambda: _Idx())


class TestElInventarioQueVeLaIA:
    def test_nombra_los_soportes_reales(self, con_expediente):
        texto = _inventario_de_soportes("HUS468334", "req-1")
        assert "Hoja de atención de urgencias" in texto
        assert "Epicrisis" in texto
        assert "HAU_900006037_HUS468334.pdf" in texto

    def test_dice_cuantos_son_para_que_no_agregue(self, con_expediente):
        texto = _inventario_de_soportes("HUS468334", "req-1")
        assert f"Son estos {len(EXPEDIENTE)}, ni uno más" in texto

    def test_prohibe_expresamente_los_que_la_ia_venia_inventando(self, con_expediente):
        texto = _inventario_de_soportes("HUS468334", "req-1").lower()
        for inventado in ("autorización previa", "descripción quirúrgica"):
            assert inventado in texto, f"no se le advierte sobre «{inventado}»"
        assert "no se aportó" in texto

    def test_explica_la_consecuencia(self, con_expediente):
        """La regla se obedece mejor cuando se sabe por qué existe."""
        assert "ratifique la glosa" in _inventario_de_soportes("HUS468334", "req-1")


class TestSinExpedienteNoDiceNada:
    def test_factura_sin_soportes(self, con_expediente):
        assert _inventario_de_soportes("HUS999999", "req-1") == ""

    def test_sin_numero_de_factura(self, con_expediente):
        assert _inventario_de_soportes(None, "req-1") == ""
        assert _inventario_de_soportes("", "req-1") == ""

    def test_indexador_caido_no_tumba_el_analisis(self, monkeypatch):
        from app.services import soportes_autodiscovery_service as svc

        def _explota():
            raise RuntimeError("el share no responde")

        monkeypatch.setattr(svc, "get_indexer", _explota)
        assert _inventario_de_soportes("HUS468334", "req-1") == ""


class TestSeLeEntregaAlPrompt:
    def test_el_inventario_se_antepone_al_contexto(self):
        from pathlib import Path

        fuente = (
            Path(__file__).resolve().parents[2] / "app" / "api" / "routers" / "analizar.py"
        ).read_text(encoding="utf-8")
        assert "_inventario_de_soportes(numero_factura, req_id)" in fuente
        assert "contexto_pdf = _inventario" in fuente


class TestElPuntajeNoCastigaLoQueElMotorYaResolvio:
    """El desglose decía «No se anexaron soportes. La defensa documental es
    débil» sobre una factura con DOCE soportes en el expediente: el contador
    solo miraba los PDF subidos a mano y no los que el motor encuentra solo."""

    def _contar(self, contexto: str) -> int:
        n = 0
        n = max(n, contexto.count("═══ DOCUMENTO:"))
        n = max(n, contexto.count("═══ SOPORTE AUTO"))
        return n

    def test_los_soportes_del_servidor_cuentan(self):
        contexto = "\n".join(f"═══ SOPORTE AUTO (HEV): {n} ═══\ntexto" for n, _t in EXPEDIENTE)
        assert self._contar(contexto) == len(EXPEDIENTE)

    def test_el_contador_del_motor_los_mira(self):
        from pathlib import Path

        fuente = (
            Path(__file__).resolve().parents[2] / "app" / "services" / "glosa_service.py"
        ).read_text(encoding="utf-8")
        assert 'txt.count("═══ SOPORTE AUTO")' in fuente

    def test_el_mensaje_distingue_no_haber_de_no_adjuntar(self):
        from pathlib import Path

        fuente = (
            Path(__file__).resolve().parents[2] / "app" / "services" / "confidence_scorer.py"
        ).read_text(encoding="utf-8")
        assert "ni adjuntos ni encontrados en el servidor" in fuente


class TestLaReglaEstaEnElPromptGlobal:
    """19-08-2026. Yesid: «si dicho prompt interfiere en futuras correcciones
    tocará modificarlo».

    Y sí interfería. Las REGLAS INQUEBRANTABLES prohibían inventar normas,
    valores y tarifas — pero **nada sobre inventar soportes**, que es lo que
    estaba pasando. Pasarle el inventario del caso ayuda, pero solo existe
    cuando la factura está indexada; sin regla global, en cualquier otro caso
    la IA vuelve a completar de memoria.
    """

    def _base(self) -> str:
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        return SYSTEM_BASE

    def test_hay_regla_inquebrantable_contra_inventar_soportes(self):
        assert "PROHIBIDO INVENTAR SOPORTES" in self._base()

    def test_va_entre_las_reglas_inquebrantables(self):
        """Es la misma familia que inventar normas o tarifas: mismo nivel."""
        base = self._base()
        i_bloque = base.index("REGLAS DE SEGURIDAD INQUEBRANTABLES")
        i_regla = base.index("PROHIBIDO INVENTAR SOPORTES")
        i_fin = base.index("EXCLUSIVIDAD DE CRITERIO")
        assert i_bloque < i_regla < i_fin

    def test_nombra_los_dos_documentos_que_la_ia_inventaba(self):
        base = self._base().upper()
        assert "AUTORIZACIÓN PREVIA" in base
        assert "DESCRIPCIÓN QUIRÚRGICA" in base

    def test_dice_que_hacer_cuando_no_hay_inventario(self):
        """Sin lista verificada, la salida correcta es no enumerar nada."""
        assert "NO enumeres documentos" in self._base()

    def test_manda_el_inventario_del_caso_sobre_cualquier_lista(self):
        assert "SOPORTES QUE DE VERDAD OBRAN EN EL EXPEDIENTE" in self._base()

    def test_el_caso_del_cups_inventado_quedo_escrito(self):
        """Un caso real concreto pesa más que una prohibición abstracta."""
        assert "348240" in self._base()
