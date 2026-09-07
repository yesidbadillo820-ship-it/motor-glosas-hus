"""La mesa de conciliación en pantalla (07-09-2026).

El acta se arma, se queda en el motor y se trabaja acá renglón por renglón
durante la audiencia. Lo que estas pruebas cuidan es lo que se rompe en una
mesa de verdad, con cien renglones y una EPS del otro lado:

  · que la plata se muestre con el formato único del hospital;
  · que los renglones que necesitan a una persona **se vean**;
  · que la tabla ancha se recorra en su propia caja y no desborde la página;
  · que una mesa cerrada no se pueda editar por accidente;
  · y que el panel que ya existía siga en su sitio.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")


def _funcion(nombre: str) -> str:
    """El cuerpo de una función del index, para mirarla de cerca."""
    i = HTML.index(f"function {nombre}(")
    return HTML[i : i + 2600]


class TestLaMesaLlamaLoQueExiste:
    @pytest.mark.parametrize(
        "ruta",
        [
            "'/conciliaciones/mesa/abrir'",
            "'/conciliaciones/mesa?limite=50'",
            "'/conciliaciones/mesa/' + MESA.id + '/acta.xlsm'",
            "'/conciliaciones/mesa/' + MESA.id + '/cerrar'",
        ],
    )
    def test_las_rutas_estan_escritas_como_las_sirve_el_motor(self, ruta):
        assert ruta in HTML

    def test_guardar_un_renglon_va_por_patch(self):
        cuerpo = _funcion("mesaGuardar")
        assert "'/conciliaciones/mesa/' + MESA.id + '/linea/'" in cuerpo
        assert "method:'PATCH'" in cuerpo


class TestLoQueVeElAuditor:
    def test_la_plata_usa_el_formato_unico(self):
        """Regla del repo: fmtCOP, nunca un toLocaleString suelto."""
        for fn in ("mesaPintar", "mesaCifras"):
            cuerpo = _funcion(fn)
            assert "fmtCOP(" in cuerpo, f"{fn} no usa fmtCOP"
            assert "toLocaleString" not in cuerpo, f"{fn} formatea la plata a mano"

    def test_los_renglones_que_faltan_decidir_se_marcan(self):
        cuerpo = _funcion("mesaPintar")
        assert "falta" in cuerpo and "l.aviso" in cuerpo
        assert ".mesa-tabla tr.falta{" in HTML, "sin el color, la marca no se ve"

    def test_el_pendiente_se_ve_distinto_en_cero_que_en_rojo(self):
        assert ".mesa-pend-0{" in HTML and ".mesa-pend-x{" in HTML
        assert "mesa-pend-" in _funcion("mesaPintar")

    def test_el_texto_del_servicio_no_estira_la_tabla(self):
        """Una descripción de glosa es larguísima: se corta y se ve completa
        al pasar el mouse."""
        assert ".mesa-tabla .serv{" in HTML
        assert "text-overflow:ellipsis" in HTML[HTML.index(".mesa-tabla .serv{") :][:200]
        assert 'class="serv" title=' in _funcion("mesaPintar")


class TestLaTablaAnchaNoRompeLaPagina:
    def test_se_recorre_dentro_de_su_caja(self):
        regla = HTML[HTML.index(".mesa-tabla-wrap{") :][:160]
        assert "overflow:auto" in regla, "la tabla tiene doce columnas: sin esto desborda la página"
        assert "max-height" in regla, "sin tope de alto se pierde el encabezado en una mesa larga"

    def test_el_encabezado_se_queda_fijo(self):
        """Con cien renglones, sin encabezado fijo no se sabe qué columna se
        está llenando."""
        regla = HTML[HTML.index(".mesa-tabla th{") :][:160]
        assert "position:sticky" in regla


class TestUnaMesaCerradaNoSeToca:
    def test_los_campos_quedan_deshabilitados(self):
        cuerpo = _funcion("mesaPintar")
        assert "cerrada" in cuerpo and "disabled" in cuerpo

    def test_y_los_botones_de_un_clic_desaparecen(self):
        """Dejarlos puestos invita a tocar algo que el motor va a rechazar."""
        assert "cerrada ? '' : '<div class=\"mesa-todo\">" in _funcion("mesaPintar")

    def test_cerrar_avisa_lo_que_queda_sin_repartir(self):
        cuerpo = _funcion("mesaCerrar")
        assert "sin_repartir" in cuerpo and "confirm(" in cuerpo


class TestNoSeLlevoPorDelanteLoQueYaEstaba:
    @pytest.mark.parametrize("fn", ["actaxRevisar", "actaxOptimizar", "armarVer", "armarDescargar"])
    def test_los_paneles_anteriores_siguen(self, fn):
        assert f"function {fn}" in HTML

    def test_el_area_de_conciliacion_sigue_scrolleando(self):
        """El arreglo del scroll no puede perderse al agregar la mesa."""
        regla = re.search(r"\.concil-area\{([^}]*)\}", HTML).group(1)
        assert "overflow-y:auto" in regla and "flex:1" in regla
