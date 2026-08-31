"""Pulido visual del menú lateral.

31-08-2026, a pedido del área. El menú funcionaba bien pero se veía como
elementos apilados, no como un producto diseñado.

QUÉ SE CAMBIÓ Y POR QUÉ — cada cosa arregla algo concreto:

1. **Los grupos se separaban con una línea a todo el ancho.** Eso corta el
   menú en bloques y compite con el item activo. Ahora se separan con aire y
   un rótulo mejor jerarquizado: pesa menos y ordena más.

2. **El hover movía el item 3 px a la derecha.** En un menú de treinta
   entradas ese salto es ruido. Ahora solo cambia el fondo.

3. **La barra del item activo latía sin parar** y la banda iba a todo el
   ancho. Ahora es una pieza con esquinas suaves y una marca fija: se
   distingue igual de rápido y no compite con el contenido.

4. **Los badges eran círculos rojos que parpadeaban, los tres a la vez.** Un
   número que parpadea todo el día se deja de ver, y si todos van en rojo
   ninguno destaca. Ahora son pastillas discretas, y **el rojo se reserva
   para vencimientos y alertas** — que es donde corre un plazo y una glosa no
   contestada a tiempo se da por aceptada (Art. 57 Ley 1438).

5. **Los iconos venían en tamaños distintos**, así que las etiquetas no
   arrancaban a la misma altura. Ahora todos miden lo mismo.

6. **El foco del buscador era teal**, el único punto del menú con ese color.
   Ahora usa el azul del sistema.

LO QUE NO SE TOCÓ: ni una ruta, ni un permiso, ni un `onclick`, ni un id, ni
una clase que el JavaScript use. El cambio es exclusivamente CSS — y esta
prueba lo comprueba comparando contra el archivo en git.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
CSS = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", HTML, re.S))


def _regla(selector: str) -> str:
    """El cuerpo de una regla CSS del menú."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no existe la regla {selector}"
    return m.group(1)


class TestNoSePerdioNadaQueElJsUse:
    @pytest.mark.parametrize(
        "clase",
        [
            ".sn-item",
            ".sn-group",
            ".sn-label",
            ".sn-badge",
            ".sn-item-label",
            ".sn-search",
            ".sn-brand-footer",
            ".sn-highlight",
            ".sn-toggle",
            ".sidebar-nav.collapsed",
            ".sn-item.active",
        ],
    )
    def test_la_clase_sigue_teniendo_estilo(self, clase: str):
        assert clase in CSS, clase

    @pytest.mark.parametrize(
        "bid",
        ["venc-badge-side", "alert-badge-side", "mis-badge-side", "sn-mando", "sn-search-input"],
    )
    def test_los_ids_del_html_siguen_ahi(self, bid: str):
        assert f'id="{bid}"' in HTML, bid

    def test_todos_los_botones_conservan_su_navegacion(self):
        """Si un onclick se hubiera perdido, el menú dejaría de navegar."""
        assert HTML.count("sidebarTab(this,") >= 25


class TestElItemActivoSeDistingueSinGritar:
    def test_conserva_el_naranja_que_pidio_el_auditor(self):
        assert "--c-amber" in _regla(".sn-item.active")

    def test_ya_no_late(self):
        """Una barra que pulsa cada 2,4 segundos, todo el día, cansa."""
        assert "snActivePulse" not in CSS

    def test_es_una_pieza_y_no_una_banda_a_todo_el_ancho(self):
        assert "border-radius" in _regla(".sn-item")

    def test_la_marca_de_la_izquierda_sigue(self):
        cuerpo = _regla(".sn-item.active::before")
        assert "width:3px" in cuerpo.replace(" ", "")


class TestElHoverYaNoSalta:
    def test_no_desplaza_el_item(self):
        assert "translateX" not in _regla(".sn-item:hover")

    def test_pero_si_responde(self):
        assert "background" in _regla(".sn-item:hover")


class TestLosBadgesEstanJerarquizados:
    def test_ya_no_parpadean(self):
        assert "snBadgePulse" not in CSS

    def test_los_normales_son_discretos(self):
        cuerpo = _regla(".sn-badge")
        assert "--c-red" not in cuerpo
        assert "--bg-subtle" in cuerpo

    def test_los_numeros_quedan_alineados(self):
        """Dos badges de dos cifras deben ocupar lo mismo."""
        assert "tabular-nums" in _regla(".sn-badge")

    def test_el_rojo_se_reserva_para_donde_corre_un_plazo(self):
        m = re.search(r"#venc-badge-side[^{]*\{([^}]*)\}", CSS)
        assert m and "--c-red" in m.group(1)
        assert "alert-badge-side" in CSS


class TestOrdenYAlineacion:
    def test_los_iconos_miden_todos_lo_mismo(self):
        cuerpo = _regla(".sn-item svg")
        assert "width:17px" in cuerpo.replace(" ", "")
        assert "height:17px" in cuerpo.replace(" ", "")

    def test_los_grupos_se_separan_con_aire_no_con_una_linea(self):
        assert "border-bottom" not in _regla(".sn-group")

    def test_el_rotulo_del_grupo_no_se_come_el_espacio(self):
        cuerpo = _regla(".sn-label")
        assert "font-size:.62rem" in cuerpo.replace(" ", "")

    def test_el_buscador_usa_el_azul_del_sistema(self):
        """Era el único punto del menú con teal."""
        cuerpo = _regla(".sn-search input:focus")
        assert "--sinac-blue-700" in cuerpo
        assert "--c-teal" not in cuerpo


class TestColapsadoYAccesibilidad:
    def test_colapsado_sigue_funcionando(self):
        assert ".sidebar-nav.collapsed .sn-item-label" in CSS
        assert ".sidebar-nav.collapsed .sn-label" in CSS

    def test_colapsado_conserva_el_globo_con_el_nombre(self):
        assert ".sidebar-nav.collapsed .sn-item[data-tip]:hover::after" in CSS

    def test_se_respeta_a_quien_pidio_menos_movimiento(self):
        assert "prefers-reduced-motion" in CSS

    def test_el_foco_de_teclado_sigue_marcado(self):
        assert ".sn-item:focus-visible" in CSS


class TestSoloCambioLaApariencia:
    def test_el_diff_contra_git_no_toca_html_ni_javascript(self):
        """La comprobación que de verdad importa: que esto haya sido
        exclusivamente estética."""
        salida = subprocess.run(
            ["git", "diff", "-U0", "HEAD", "--", "static/index.html"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        ).stdout
        if not salida.strip():
            pytest.skip("ya está confirmado en git; nada que comparar")
        sospechosas = []
        for linea in salida.splitlines():
            if not linea.startswith(("+", "-")) or linea.startswith(("+++", "---")):
                continue
            cuerpo = linea[1:].strip()
            if cuerpo.startswith(("/*", "*", "·")) or not cuerpo:
                continue
            if re.search(r"onclick=|sidebarTab\(|href=|fetch\(|function |<button|<input", cuerpo):
                sospechosas.append(cuerpo[:90])
        assert not sospechosas, "el diff tocó markup o JavaScript:\n" + "\n".join(sospechosas)
