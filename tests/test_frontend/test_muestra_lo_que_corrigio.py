"""El motor arreglaba el dictamen en silencio.

31-08-2026, segunda idea del repaso de diseño.

El motor ya corrige solo lo que la IA escribe mal antes de entregar el
dictamen: retira códigos citados como CUPS que no están en el catálogo, le
pone a una norma derogada su fecha y cuál rige hoy, corrige el año de una
norma real, endereza el artículo citado, y quita del recuadro del servicio el
código de la causal.

**Todo eso pasaba sin que nadie lo viera.** El dictamen salía limpio y el
gestor no sabía que se le habían quitado tres cosas.

Enseñarlo no cuesta trabajo nuevo —ya está hecho por dentro— y sirve para dos
cosas: el gestor le cree al motor porque ve que revisa, y **aprende qué mirar**
cuando revise a mano.

DOS DECISIONES DE DISEÑO QUE LA PRUEBA FIJA:

1. **Va arriba del dictamen, no debajo.** Tiene que verlo antes de leer el
   texto, no después de haberlo radicado.
2. **No sale impreso.** Es una nota interna del motor para el gestor, no parte
   del escrito que va a la EPS. Si saliera en el papel, el hospital le estaría
   entregando a la entidad la lista de lo que tuvo que corregirse.

Y las redes no se tocaron: siguen siendo funciones puras de texto a texto. Lo
que se anota se deduce comparando el texto antes y después, en el sitio donde
ya se comparaba para saber si había que volver a revisar las citas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
CSS = (RAIZ / "static" / "sinac-ds.css").read_text(encoding="utf-8")
MOTOR = (RAIZ / "app" / "services" / "glosa_service.py").read_text(encoding="utf-8")
ESQUEMA = (RAIZ / "app" / "models" / "schemas.py").read_text(encoding="utf-8")


class TestElMotorAnotaLoQueCorrige:
    def test_el_campo_existe_en_la_respuesta(self):
        assert "correcciones: Optional[list[str]] = None" in ESQUEMA

    def test_se_entrega_en_el_dictamen(self):
        assert 'correcciones=(locals().get("_correcciones") or None)' in MOTOR

    def test_vacio_cuando_no_paso_por_las_redes(self):
        """Hay caminos de salida temprana. Ahí el campo va vacío, que es la
        verdad, y no una lista falsa de correcciones que nadie hizo."""
        i = MOTOR.index('correcciones=(locals().get("_correcciones")')
        assert "or None" in MOTOR[i : i + 120]

    @pytest.mark.parametrize(
        "red",
        [
            "_dictamen_cups_respaldado",
            "_dictamen_anio_ok",
            "_dictamen_derogada_ok",
            "_dictamen_art_ok",
        ],
    )
    def test_cada_red_del_cuerpo_deja_su_nota(self, red: str):
        i = MOTOR.index(f"if {red} != dictamen:")
        assert "_correcciones.append(" in MOTOR[i : i + 700], red

    def test_tambien_la_causal_del_recuadro(self):
        """Esa red corre mucho antes que las del cuerpo, así que deja marca y
        se suma después. Si no, quedaría fuera de la lista."""
        assert "_quito_la_causal_del_servicio" in MOTOR
        i = MOTOR.index("_correcciones: list[str] = []")
        assert "_quito_la_causal_del_servicio" in MOTOR[i : i + 600]

    def test_las_redes_no_se_tocaron(self):
        """Siguen siendo funciones puras de texto a texto: lo que se anota se
        deduce comparando antes y después, fuera de ellas."""
        i = MOTOR.index("def _neutralizar_cups_sin_respaldo")
        assert "_correcciones" not in MOTOR[i : i + 3000]


class TestSeVeEnPantalla:
    def test_la_pantalla_lee_el_campo(self):
        assert "d.correcciones" in HTML

    def test_no_pinta_el_panel_si_no_hubo_nada_que_corregir(self):
        i = HTML.index("window._paCorrecciones =")
        assert "length" in HTML[i : i + 160]

    def test_va_arriba_del_dictamen(self):
        """Antes de leer el texto, no después de haberlo radicado."""
        assert HTML.index("res-correcciones") < HTML.index("'<div class=\"res-dictamen card-doc'")

    def test_dice_cuantas_fueron(self):
        assert "corrección" in HTML and "correcciones' )" not in HTML

    def test_dice_que_el_gestor_no_tiene_que_hacer_nada(self):
        """Un aviso que parece tarea se ignora. Este informa, no pide."""
        assert "no hace falta" in HTML

    def test_el_texto_va_escapado(self):
        i = HTML.index("window._paCorrecciones.map(")
        assert "escHtml(c)" in HTML[i : i + 160]


class TestNoSaleEnElPapelQueVaALaEps:
    def test_el_panel_lleva_no_print(self):
        """Si saliera impreso, el hospital le estaría entregando a la entidad
        la lista de lo que tuvo que corregirse."""
        i = HTML.index("res-correcciones")
        assert "no-print" in HTML[i - 200 : i + 200]

    def test_la_regla_de_impresion_existe(self):
        bloque = CSS[CSS.index(".res-correcciones {") : CSS.index(".sds-kbd {")]
        assert "@media print" in bloque
        assert re.search(r"\.no-print\s*\{\s*display:\s*none", bloque)


class TestUsaElVocabularioDeColor:
    def test_reusa_los_tokens_de_significado(self):
        """El panel no inventa colores propios: usa los del sistema."""
        bloque = CSS[CSS.index(".res-correcciones {") : CSS.index(".sds-kbd {")]
        assert "--sds-probado" in bloque
        assert "#" not in bloque.split("@media print")[0], "no debe haber hex sueltos"

    def test_usa_el_componente_de_estado(self):
        i = HTML.index("res-correcciones-hdr")
        assert "sds-estado es-probado" in HTML[i : i + 300]
