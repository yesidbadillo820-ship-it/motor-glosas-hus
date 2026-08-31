"""«0 próximas a vencer» cuando en realidad no se pudo preguntar.

31-08-2026, tercera idea del repaso de diseño — y la que más cuesta de todas.

La pantalla de inicio pide las alertas con `.catch(()=>null)`, así que si la
consulta falla llega `null`. Y el código igual escribía **0** en la tarjeta
«Próximas a vencer» y pintaba el pill **verde** de «✓ sin glosas próximas a
vencer».

Eso no es cierto. No es que no haya ninguna: es que **no se pudo preguntar**.

Y aquí la diferencia cuesta plata. Una glosa que no se contesta dentro del
plazo **se da por aceptada** (Art. 57 de la Ley 1438 de 2011). El auditor abre
el motor por la mañana, ve un cero tranquilizador en verde, y se dedica a otra
cosa mientras el plazo corre.

El propio archivo ya lo tenía escrito desde agosto: *«El caso que lo decidió es
la tarjeta de vencimientos: si falla, no aparece, y el auditor no se entera de
que había glosas por vencerse»*. Se puso un aviso flotante — pero ese aviso se
va en cinco segundos y **el número falso se queda en pantalla**.

Ahora: cuando no se sabe, se dice que no se sabe.

Lo mismo con el pill de contratos: sin respuesta, «0 contratos cargados» es
igual de falso.

Comprobado corriendo en node los tres casos, no solo leyendo el código:

    consulta falla   → «—» + «no se pudo consultar» + pill ámbar
    responde vacía   → «0» + «en 5 días» + pill verde
    responde con 3   → «3» + «1 ya vencida» + pill rojo
"""

from __future__ import annotations

import re
from pathlib import Path

HTML = (Path(__file__).resolve().parents[2] / "static" / "index.html").read_text(encoding="utf-8")


def _bloque() -> str:
    i = HTML.index("var _hayAlertas = !!(alertas")
    return HTML[i : HTML.index("// ─── Top entidades + Top causales ───", i)]


class TestLaTarjetaNoInventaUnCero:
    def test_distingue_no_hay_de_no_se(self):
        assert "_hayAlertas" in _bloque()

    def test_sin_respuesta_muestra_raya_y_no_cero(self):
        b = _bloque()
        assert "_hayAlertas ? nVencen : '—'" in b

    def test_lo_dice_en_el_subtitulo(self):
        assert "no se pudo consultar" in _bloque()

    def test_el_subtitulo_no_se_pinta_tranquilizador(self):
        """Si no se sabe, no puede salir en el gris de «todo normal»."""
        b = _bloque()
        i = b.index("no se pudo consultar")
        assert "down" in b[i : i + 200]


class TestElPillVerdeEsUnaAfirmacion:
    def test_solo_dice_sin_glosas_cuando_de_verdad_pregunto(self):
        """El verde de «todo en orden» es justo lo que no se puede afirmar
        cuando no se pudo preguntar."""
        b = _bloque()
        i = b.index("sin glosas próximas a vencer")
        assert "else if(_hayAlertas)" in b[max(0, i - 200) : i]

    def test_sin_respuesta_avisa_en_ambar(self):
        b = _bloque()
        assert "no se pudo revisar si hay glosas próximas a vencer" in b
        i = b.index("no se pudo revisar si hay glosas")
        assert "pill warn" in b[i : i + 200]


class TestElPillDeContratosTampocoMiente:
    def test_sin_respuesta_no_dice_cero_contratos(self):
        b = _bloque()
        assert "no se pudo consultar cuántos contratos hay cargados" in b

    def test_con_respuesta_sigue_contando_igual(self):
        b = _bloque()
        assert "contrato' + (nContratos===1?'':'s')" in b


class TestNoSeRompioLoQueYaFuncionaba:
    def test_sigue_contando_las_ya_vencidas_aparte(self):
        """No es lo mismo «vence pronto» que «ya se venció»: decirle al gestor
        que algo vence pronto cuando el plazo ya pasó es tranquilizarlo al
        revés."""
        b = _bloque()
        assert "dias_restantes||0) <= 0" in b
        assert "ya vencida" in b

    def test_el_rojo_de_ya_vencida_manda_sobre_todo(self):
        b = _bloque()
        assert re.search(r"nVencidas\s*>\s*0", b)
        assert "ya vencido" in b
