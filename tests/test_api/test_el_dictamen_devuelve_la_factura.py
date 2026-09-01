"""El dictamen devuelve el número de factura que digitó el auditor.

19-08-2026. En la prueba de Yesid, el recuadro del Auditor Forense al pie del
dictamen salió como:

    🔍 Auditor Forense IA · N/A

y su botón quedaba inservible: preguntaba por una factura llamada «N/A».

El esquema traía `factura: Optional[str] = "N/A"` y **nadie lo llenaba nunca**.
El dato estaba ahí desde el principio — el auditor lo había escrito en el
formulario, y el encabezado del dictamen lo imprimía bien («N° Factura:
HUS468334»). Solo faltaba devolverlo.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _analizar() -> str:
    return (RAIZ / "app" / "api" / "routers" / "analizar.py").read_text(encoding="utf-8")


def _index() -> str:
    return (RAIZ / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")


class TestElMotorLaDevuelve:
    def test_llena_el_campo_con_lo_que_digito_el_auditor(self):
        assert "resultado.factura = numero_factura" in _analizar()

    def test_no_pisa_una_factura_que_la_ia_ya_extrajo(self):
        """Si la IA sacó la factura del texto de la glosa, esa manda."""
        fuente = _analizar()
        m = re.search(r"if numero_factura and \(([^)]+)\)", fuente)
        assert m, "no se encontró la guarda"
        assert "not resultado.factura" in m.group(1)
        assert '"N/A"' in m.group(1)

    def test_el_esquema_tiene_el_campo(self):
        from app.models.schemas import GlosaResult

        assert "factura" in GlosaResult.model_fields


class TestElRecuadroNoDependeDelServidor:
    """19-08-2026, segunda vuelta. Se arregló el backend —se comprobó de punta
    a punta que la respuesta trae `factura: "HUS468334"`— y aun así el recuadro
    seguía diciendo «N/A» en el PC de cartera.

    La raíz es que el esquema trae `factura` con valor de fábrica **«N/A»**: un
    texto, no un vacío. La pantalla hacía `d.factura || d.numero_factura`, y
    «N/A» es un valor verdadero en JavaScript, así que lo tomaba por bueno.

    O sea: bastaba un motor un poco desactualizado —o cualquier camino que no
    llenara el campo— para que el botón quedara inservible. Ahora «N/A» se
    trata como falta de dato, y si el motor no manda nada se toma la factura
    del formulario, que es donde el auditor la escribió.
    """

    def _fuente(self) -> str:
        m = re.search(r"function renderAuditorForensePanel\(d\)\{.*?\n\}\n", _index(), re.S)
        assert m, "no se encontró renderAuditorForensePanel"
        return m.group(0)

    def test_no_toma_por_buena_la_palabra_NA(self):
        assert "'N/A'" in self._fuente(), "«N/A» vuelve a pasar como si fuera una factura"

    def test_cae_al_formulario_si_el_motor_no_la_manda(self):
        assert "f-factura" in self._fuente(), "el recuadro depende de que el servidor esté al día"

    def test_si_no_hay_factura_en_ninguna_parte_no_se_pinta(self):
        assert "if(!factura) return '';" in self._fuente()


class TestLaPantallaLaUsa:
    def test_el_recuadro_forense_lee_la_factura_del_dictamen(self):
        texto = _index()
        m = re.search(r"function renderAuditorForensePanel\(d\)\{.*?\n\}\n", texto, re.S)
        assert m, "no se encontró renderAuditorForensePanel"
        assert "d.factura" in m.group(0)

    def test_sin_factura_el_recuadro_no_se_pinta(self):
        """Mejor no mostrarlo que mostrarlo pidiendo «N/A»."""
        texto = _index()
        m = re.search(r"function renderAuditorForensePanel\(d\)\{.*?\n\}\n", texto, re.S)
        assert "if(!factura) return '';" in m.group(0)
