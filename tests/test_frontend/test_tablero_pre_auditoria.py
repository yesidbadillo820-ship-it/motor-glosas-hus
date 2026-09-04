"""La pantalla de Pre-Auditoría Concurrente (V3, Pilar 2 — 04-09-2026).

El tablero donde el auditor ve lo que el HIS consulta ANTES de timbrar. Lo
que estas pruebas cuidan, que son las lecciones que ya costaron caro en este
repositorio:

  · **Que las rutas que llama existan.** Es el caso «Salud Total»: una
    pantalla llamando a un router borrado, tres meses en Not Found.
  · **Que la plata pase por `fmtCOP`.** Un `toLocaleString` suelto hace que
    la misma cifra salga distinta según la pantalla.
  · **Que haya estado de carga, de error y de vacío.** Una tabla en blanco
    no distingue «no hay nada» de «se cayó el servidor».
  · **Que la cifra de dinero salvado se explique en la pantalla**, no solo
    en el código: quien la lea tiene que saber qué está contando.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def html() -> str:
    return (RAIZ / "static" / "index.html").read_text(encoding="utf-8")


class TestLaPantallaExiste:
    def test_el_panel_esta_declarado(self, html):
        assert 'id="p-pre-auditoria"' in html

    def test_hay_entrada_en_el_menu(self, html):
        assert "sidebarTab(this,'pre-auditoria')" in html
        assert 'id="sn-pre-auditoria"' in html

    def test_al_entrar_se_carga_sola(self, html):
        assert "if(id==='pre-auditoria') preAudCargar();" in html

    def test_no_pisa_el_prefijo_que_ya_existia(self, html):
        """`pa*` ya lo usa el ajuste de «Mis glosas». Por eso `preAud*`."""
        assert "function paCargar(" not in html
        assert "function preAudCargar(" in html


class TestLasRutasQueLlama:
    RUTAS = ["/pre-auditoria/resumen", "/pre-auditoria/eventos"]

    @pytest.mark.parametrize("ruta", RUTAS)
    def test_la_pantalla_la_llama(self, html, ruta):
        assert ruta in html

    @pytest.mark.parametrize("ruta", RUTAS)
    def test_y_el_backend_la_atiende(self, ruta):
        from app.main import app

        caminos = {getattr(r, "path", "") for r in app.routes}
        assert ruta in caminos

    def test_va_con_la_credencial_del_usuario(self, html):
        bloque = html[html.index("function preAudPedir(") :]
        assert "authH()" in bloque[:400], "las llamadas del tablero van sin sesión"


class TestLaPlataYLosNumeros:
    def test_toda_la_plata_pasa_por_el_formateador_unico(self, html):
        bloque = _bloque_preaud(html)
        assert "fmtCOP(" in bloque
        assert "toLocaleString" not in bloque, "hay plata formateada a mano"

    def test_los_conteos_no_se_vuelven_pesos(self, html):
        bloque = _bloque_preaud(html)
        assert "fmtNum(r.evaluaciones" in bloque
        assert "fmtCOP(r.evaluaciones" not in bloque

    def test_las_columnas_de_valor_van_a_la_derecha(self, html):
        bloque = _bloque_preaud(html)
        assert bloque.count("text-align:right") >= 2

    def test_no_se_le_pega_un_signo_al_formateador(self, html):
        for variante in ("'$' + fmtCOP", '"$" + fmtCOP', "$' + fmtCOP("):
            assert variante not in _bloque_preaud(html)


class TestLosTresEstadosDeLaPantalla:
    def test_estado_de_carga(self, html):
        assert "Cargando…" in _bloque_preaud(html)

    def test_estado_vacio_que_explica(self, html):
        assert "Todavía no hay evaluaciones" in _bloque_preaud(html)

    def test_estado_de_error_con_reintento(self, html):
        bloque = _bloque_preaud(html)
        assert "No se pudo leer el tablero" in bloque
        assert "Reintentar" in bloque

    def test_el_error_dice_qué_pasó_y_no_solo_falló(self, html):
        assert "escHtml(e.message" in _bloque_preaud(html)


class TestElDineroSalvadoSeExplica:
    def test_la_tarjeta_existe(self, html):
        assert "Dinero salvado" in _bloque_preaud(html)

    def test_dice_qué_está_contando(self, html):
        """Sin esta frase, alguien puede leer la cifra como «lo que evitamos»
        cuando en realidad es «lo que ya se corrigió y volvió a pasar»."""
        assert "se corrigieron y volvieron a pasar" in _bloque_preaud(html)

    def test_y_muestra_aparte_lo_que_no_se_sabe(self, html):
        bloque = _bloque_preaud(html)
        assert "Riesgo sin resolver" in bloque
        assert "no sabemos qué se hizo" in bloque


class TestLosColoresSonDelSistemaDeDiseño:
    def test_usa_los_tokens_de_la_casa(self, html):
        bloque = _bloque_preaud(html)
        for token in ("var(--sinac-green-600", "var(--sinac-red-600", "var(--sinac-amber-600"):
            assert token in bloque, f"falta {token}"

    def test_todo_color_trae_su_respaldo(self, html):
        """Si el token no cargó, el color no puede quedar en nada."""
        bloque = _bloque_preaud(html)
        sueltos = re.findall(r"var\(--sinac-[a-z]+-\d+\)", bloque)
        assert not sueltos, f"colores sin respaldo: {sueltos}"

    def test_no_inventa_una_paleta_nueva(self, html):
        bloque = _bloque_preaud(html)
        hex_sueltos = set(re.findall(r"(?<!,)#[0-9A-Fa-f]{6}(?!\w)", bloque))
        # Los únicos hex admitidos son los respaldos de los tokens y el blanco
        # del texto sobre la pastilla de color.
        assert hex_sueltos <= {"#059669", "#DC2626", "#D97706"}, hex_sueltos


class TestLoQueNoSeToco:
    @pytest.mark.parametrize(
        "otro", ["p-glosas-adres", "p-dashboard", "p-mis-glosas", "p-resumen-mes", "p-tarifas"]
    )
    def test_los_otros_paneles_siguen_ahi(self, html, otro):
        assert f'id="{otro}"' in html

    def test_el_javascript_compila(self, tmp_path):
        """Un error de sintaxis en index.html tumba TODA la página, no solo
        el tablero nuevo."""
        import subprocess

        html = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
        bloques = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
        assert bloques, "no se encontró el bloque de scripts"
        for i, b in enumerate(bloques):
            f = tmp_path / f"b{i}.js"
            f.write_text(b, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            assert r.returncode == 0, f"el bloque {i} no compila:\n{r.stderr[:600]}"


def _bloque_preaud(html: str) -> str:
    """Solo el trozo del tablero: así las pruebas no se contaminan con el
    resto de las 27 mil líneas de la página."""
    inicio = html.index("//  PRE-AUDITORÍA CONCURRENTE (V3, Pilar 2)")
    fin = html.index("</script>", inicio)
    return html[inicio:fin]
