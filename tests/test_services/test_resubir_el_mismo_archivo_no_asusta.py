"""Resubir el mismo archivo no es un error (20-08-2026).

Yesid volvió a subir `GLOSAS 19 AGOSTO.xlsx` —el mismo que ya había entrado
bien— y la pantalla le mostró:

    ⚠ Importación procesada — 0 glosas detectadas
    TOTAL 0 · NUEVAS 0 · ACTUALIZADAS 0 · RATIFICADAS 0 · EXTEMPORÁNEAS 29

    Posibles causas:
    • El Excel no tiene la hoja correcta…
    • Los headers de las columnas no matchean…

Dos problemas de golpe:

1. **«0 detectadas» junto a «29 extemporáneas»** no pueden ser ciertas a la
   vez. Los contadores de ratificadas/extemporáneas se sumaban al CLASIFICAR
   la fila, antes de saber si la fila iba a entrar; una fila que después
   resultaba duplicada hacía `continue` y se saltaba el total, pero su
   extemporaneidad ya estaba contada.

2. **El aviso lo mandaba a buscar un problema que no existía** — la hoja, los
   encabezados —. El archivo estaba perfecto: las 35 glosas ya estaban
   importadas, que es lo normal al resubir el mismo archivo.
"""

from __future__ import annotations

import pathlib
import re


class TestLosContadoresNoSeAdelantan:
    """Ratificadas y extemporáneas se cuentan cuando la fila SÍ entra."""

    def _fuente(self) -> str:
        return (
            pathlib.Path(__file__).resolve().parents[2] / "app/services/recepcion_service.py"
        ).read_text(encoding="utf-8")

    def test_ya_no_se_cuentan_al_clasificar(self):
        fuente = self._fuente()
        # El bloque de clasificación arma `dictamen` y `requiere_ia`; ahí ya no
        # puede haber un contador.
        bloque = re.search(
            r"dictamen = _dictamen_extemporanea\(.*?requiere_ia = False", fuente, re.S
        )
        assert bloque, "cambió el bloque de clasificación de extemporáneas"
        assert "resumen.extemporaneas += 1" not in bloque.group(0), (
            "La extemporaneidad se vuelve a contar antes de saber si la fila "
            "entra: una fila duplicada la sumaría igual, y la pantalla muestra "
            "«0 detectadas · 29 extemporáneas»."
        )

    def test_se_cuentan_junto_al_total(self):
        fuente = self._fuente()
        bloque = re.search(r"resumen\.total \+= 1.*?resumen\.semaforo\[semaforo\]", fuente, re.S)
        assert bloque, "cambió el bloque donde se suma el total"
        texto = bloque.group(0)
        assert "resumen.extemporaneas += 1" in texto
        assert "resumen.ratificadas += 1" in texto

    def test_la_fila_duplicada_sigue_saliendo_del_bucle(self):
        """El `continue` del duplicado no se puede haber perdido: sin él, la
        glosa se contaría dos veces."""
        fuente = self._fuente()
        bloque = re.search(r"if es_duplicado_exacto:.*?continue", fuente, re.S)
        assert bloque, "el duplicado exacto dejó de saltarse"


class TestLaPantallaNoAsusta:
    def _html(self) -> str:
        return (
            pathlib.Path(__file__).resolve().parents[2] / "static/importar-recepcion.html"
        ).read_text(encoding="utf-8")

    def test_distingue_duplicadas_de_archivo_ilegible(self):
        html = self._html()
        assert "totalNum === 0 && duplicadas > 0" in html, (
            "La pantalla volvió a tratar igual «todas duplicadas» y «no se "
            "pudo leer el archivo». Son dos cosas distintas."
        )

    def test_cuando_todas_ya_estaban_lo_dice_en_verde(self):
        html = self._html()
        assert "nada nuevo que registrar" in html
        assert "YA estaban importadas" in html
        assert "el archivo está bien" in html

    def test_y_no_le_manda_a_revisar_los_encabezados(self):
        """El aviso de la hoja y los encabezados solo aplica cuando de verdad
        no se leyó ninguna fila."""
        html = self._html()
        bloque = re.search(r"if\(totalNum === 0 && duplicadas > 0\)\{.*?\} else if", html, re.S)
        assert bloque
        assert "headers" not in bloque.group(0).lower()

    def test_el_aviso_de_archivo_ilegible_sigue_existiendo(self):
        """La otra mitad: un Excel de verdad ilegible tiene que avisar."""
        html = self._html()
        assert "No se leyó ninguna fila del archivo" in html
        assert "no tiene la hoja correcta" in html

    def test_se_muestra_cuantas_ya_estaban(self):
        """Antes el número de duplicadas no se veía en ninguna parte, así que
        el auditor no tenía cómo saber qué había pasado."""
        html = self._html()
        assert 'id="s-dup"' in html
        assert "YA ESTABAN" in html
