"""La pantalla no estampa el sello verde sobre un dictamen bloqueado (08-09-2026).

Prueba de cinco casos desde Analizar: cuatro salieron con «✓ VALIDADO POR
QUALITY GATE» arriba y «⛔ NO RADICAR TODAVÍA» abajo, en la misma tarjeta. Un
sello junto a una prohibición no significa nada, y enseña a ignorar los dos.

El motor ahora manda `bloqueado_para_radicar` y sus motivos. Acá se cuida que
la pantalla los use.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")


def _funcion(nombre: str) -> str:
    i = HTML.index(f"function {nombre}(")
    siguiente = HTML.find("\nfunction ", i + 1)
    return HTML[i : siguiente if siguiente > 0 else i + 6000]


class TestElSelloRojo:
    def test_la_pantalla_lee_el_bloqueo_del_motor(self):
        cuerpo = _funcion("renderResult")
        assert "d.bloqueado_para_radicar" in cuerpo
        assert "d.motivos_bloqueo" in cuerpo

    def test_bloqueado_apaga_el_sello_verde(self):
        cuerpo = _funcion("renderResult")
        assert "if(qgBloqueado) qgOk = false;" in cuerpo

    def test_bloqueado_pone_el_sello_rojo_en_su_lugar(self):
        cuerpo = _funcion("renderResult")
        assert "⛔ NO LISTO PARA RADICAR" in cuerpo
        assert "' qg-bloqueado'" in cuerpo

    def test_el_verde_solo_sale_cuando_no_esta_bloqueado(self):
        cuerpo = _funcion("renderResult")
        i = cuerpo.index("qgBloqueado\n        ? ")
        trozo = cuerpo[i : i + 400]
        assert "NO LISTO PARA RADICAR" in trozo and "VALIDADO POR QUALITY GATE" in trozo, (
            "los dos sellos tienen que ser las dos ramas de un mismo condicional"
        )

    def test_los_motivos_salen_en_el_titulo_del_sello(self):
        cuerpo = _funcion("renderResult")
        assert "escHtml(qgMotivos" in cuerpo, "sin motivo, el rojo no le dice al gestor qué revisar"


class TestElEstilo:
    def test_el_sello_bloqueado_se_ve(self):
        assert ".card-doc.qg-bloqueado .qg-seal{display:inline-block" in HTML

    def test_es_rojo_no_verde(self):
        i = HTML.index(".card-doc.qg-bloqueado .qg-seal{")
        assert "#b91c1c" in HTML[i : i + 160]

    def test_tambien_al_imprimir(self):
        i = HTML.index("@media print{")
        assert ".card-doc.qg-bloqueado .qg-seal{position:static" in HTML[i:]

    def test_reserva_el_espacio_en_la_cabecera_como_el_verde(self):
        assert "#p-analizar .res-dictamen.qg-bloqueado .res-dictamen-hdr" in HTML


class TestElMarcadorNoSeImprime:
    def test_la_portada_del_consolidado_no_dice_otra_sin_definir(self):
        cuerpo = _funcion("imprimirLoteConsolidado")
        assert "ENTIDAD PAGADORA SIN IDENTIFICAR" in cuerpo
        i = cuerpo.index("var eps = ")
        assert "OTRA" in cuerpo[i : i + 400], (
            "la sustitución tiene que ir pegada a la lectura del desplegable"
        )
