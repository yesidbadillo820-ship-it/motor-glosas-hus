"""El renglón del servicio lo arma el motor, no el modelo.

01-09-2026. «Servicio objetado» no es redacción: es un dato verificable — qué
se facturó. Sale del catálogo CUPS, no de lo que el modelo quiera escribir.

NOTA DE HISTORIA. Este archivo nació junto a un contrato Pydantic que le pedía
al modelo un objeto JSON en vez del XML de once etiquetas. Esa parte se
revirtió el mismo día por decisión del auditor: la corrida de prueba no mejoró
y no valía la pena seguir peleando con el formato. Lo que quedó —y quedó porque
NUNCA dependió del JSON— es esto: el renglón del servicio armado con datos
duros. Si alguien vuelve a intentar la salida estructurada, que sepa que el
punto delicado era `validador_dictamen._extraer_argumento_xml`: solo entiende
`<argumento>` y rechazaría un dictamen bueno por «falta el tag».
"""

import pytest

from app.services.glosa_service import _linea_servicio_determinista


class TestElRenglonDelServicioSaleDeLaBase:
    def test_cups_del_catalogo_trae_su_descripcion_oficial(self):
        r = _linea_servicio_determinista("902210", "lo que el modelo quiera", "", "CL4506")
        assert "HEMOGRAMA" in r
        assert "(CUPS 902210)" in r

    def test_cups_fuera_del_catalogo_no_se_imprime(self):
        """215601 sale de los PDF y NO figura en el catálogo oficial.

        Poner un código que la entidad no encuentra al cruzarlo es justo lo
        que le sirve para ratificar. El aviso de «revise el código» va aparte.
        """
        r = _linea_servicio_determinista("215601", "OSTEOSÍNTESIS DE FÉMUR", "", "CL4506")
        assert r == "OSTEOSÍNTESIS DE FÉMUR"
        assert "215601" not in r

    @pytest.mark.parametrize(
        "sufijo",
        ["- código CL4506", "(CL4506)", "[CL4506]", "ref. CL4506", "CL4506", "código CL4506"],
    )
    def test_la_causal_nunca_llega_al_renglon(self, sufijo: str):
        r = _linea_servicio_determinista("", f"OSTEOSÍNTESIS DE FÉMUR {sufijo}", "", "CL4506")
        assert r == "OSTEOSÍNTESIS DE FÉMUR"

    def test_sin_datos_no_inventa_un_servicio(self):
        assert _linea_servicio_determinista("", "", "", "CL4506") == ""

    def test_si_solo_queda_el_codigo_devuelve_vacio(self):
        """Mejor sin renglón que con un rótulo huérfano."""
        assert _linea_servicio_determinista("", "CL4506", "", "CL4506") == ""

    def test_codigo_de_glosa_raro_no_rompe(self):
        for basura in ("", "   ", "N/A", "902210"):
            r = _linea_servicio_determinista("", "OSTEOSÍNTESIS DE FÉMUR", "", basura)
            assert r == "OSTEOSÍNTESIS DE FÉMUR"
