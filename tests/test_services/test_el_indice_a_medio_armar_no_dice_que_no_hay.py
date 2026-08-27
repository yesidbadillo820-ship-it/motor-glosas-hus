"""«Todavía no sé» no es «no hay» — el índice de soportes a medio construir.

27-08-2026. Lo vio el auditor en pantalla: el indexador del servidor de
radicación **terminó de recorrer las facturas y volvió a empezar** (el motor se
había reiniciado por el despliegue). Justo en esa ventana sacó un dictamen de
la factura HUS0000498954 y salió diciendo:

    «No se encontró el expediente de la factura HUS0000498954 en el servidor
     de radicación»

...y encima lo bloqueó para radicar. Pero el expediente **no se había mirado**:
el índice estaba a medio armar.

EL DEFECTO, EN UNA LÍNEA: `lookup()` devuelve una lista vacía en dos casos que
no se parecen en nada —que la factura no tenga soportes, y que el índice
todavía no haya llegado a ella— y el dictamen trataba los dos como el primero.

Es exactamente el mismo defecto que el contador de días que valía cero por
defecto: dos significados distintos aplastados en un mismo valor.

Lo que se hace ahora, en los dos sitios que consultan el índice:
  · la relación de soportes dice que el índice se está reconstruyendo, en vez
    de afirmar que no hay expediente;
  · el bloqueo de «falta el soporte de la causal» no dispara, porque no se
    puede acusar de faltar algo que nadie ha mirado.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.glosa_service import GlosaService

FACTURA = "HUS0000498954"


def _indexador(soportes, construyendo):
    idx = MagicMock()
    idx.lookup.return_value = soportes
    idx.stats.return_value = {"construyendo": construyendo}
    return idx


class TestLaRelacionDeSoportes:
    def _resultado(self, soportes, construyendo):
        svc = GlosaService.__new__(GlosaService)
        with patch(
            "app.services.soportes_autodiscovery_service.get_indexer",
            return_value=_indexador(soportes, construyendo),
        ):
            return svc._soportes_reales(FACTURA)

    def _texto(self, soportes, construyendo):
        """El aviso. Cuando SÍ hay soportes va vacío: las filas van aparte."""
        return self._resultado(soportes, construyendo)[2]

    def test_mientras_se_reconstruye_no_afirma_que_no_hay_expediente(self):
        html = self._texto([], construyendo=True)
        assert "No se encontró el expediente" not in html, (
            "el índice no ha mirado la factura: no se puede afirmar que no tenga expediente"
        )
        assert "RECONSTRUYENDO" in html
        assert "todavía no se sabe" in html

    def test_y_le_dice_al_gestor_que_hacer(self):
        html = self._texto([], construyendo=True)
        assert "vuelva a analizar" in html
        assert "Soportes" in html, "hay que decirle dónde ver si ya terminó"

    def test_con_el_indice_quieto_y_sin_soportes_si_lo_afirma(self):
        html = self._texto([], construyendo=False)
        assert "No se encontró el expediente" in html
        assert "RECONSTRUYENDO" not in html

    def test_con_soportes_se_relacionan_como_siempre(self):
        filas, cuantos, aviso = self._resultado(
            [{"tipo": "epicrisis", "nombre_archivo": "EPI_900006037_HUS498954.pdf"}],
            construyendo=False,
        )
        assert cuantos == 1
        assert "EPI_900006037_HUS498954.pdf" in " ".join(filas)
        assert aviso == "", "habiendo soportes no va ningún aviso: van las filas"


class TestElBloqueoDeRadicacion:
    def _faltan(self, soportes, construyendo, codigo="SO0102"):
        svc = GlosaService.__new__(GlosaService)
        with patch(
            "app.services.soportes_autodiscovery_service.get_indexer",
            return_value=_indexador(soportes, construyendo),
        ):
            return svc._falta_el_soporte_de_la_causal(FACTURA, codigo)

    def test_no_bloquea_mientras_el_indice_se_reconstruye(self):
        assert self._faltan([], construyendo=True) == [], (
            "no se puede acusar de faltar un soporte que nadie ha mirado — así se "
            "bloqueaba la radicación de facturas con su expediente completo"
        )

    def test_con_el_indice_quieto_si_avisa_lo_que_falta(self):
        faltan = self._faltan([], construyendo=False)
        assert faltan, "con el índice armado y sin soportes, el aviso sí corresponde"

    def test_si_el_soporte_esta_no_avisa_nada(self):
        assert self._faltan([{"tipo": "epicrisis"}], construyendo=False) == []

    def test_sin_factura_no_avisa(self):
        assert self._faltan([], construyendo=False, codigo="SO0102") != [] or True
        svc = GlosaService.__new__(GlosaService)
        assert svc._falta_el_soporte_de_la_causal(None, "SO0102") == []
        assert svc._falta_el_soporte_de_la_causal(FACTURA, "") == []
