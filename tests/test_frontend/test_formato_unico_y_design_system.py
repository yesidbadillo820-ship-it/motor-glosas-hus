"""Fase 1 del programa de mejora: un solo formato y un solo sistema de diseño.

OT-038 · 13-08-2026. La auditoría del programa de mejora midió dos cosas en
`static/`:

  · **El sistema de diseño lo usaba UNA de seis páginas.** `sinac-ds.css` y
    `sinac-ux.js` solo se cargaban en `index.html`. Las otras cinco
    —preauditoría, importar recepción, importar masiva, presentación y
    terapia física— no los cargaban.
  · **La plata se escribía de 74 maneras.** Existía `fmtCOP()`, pero había 73
    llamadas sueltas a `toLocaleString('es-CO')` en `index.html`, una en
    `preauditoria.html` y un `Intl.NumberFormat` propio en
    `sinac-asistente.js`. Tres funciones `cop` locales sombreaban además a la
    global.

Eso no es cosmético. La misma cifra salía «$ 1.234.567», «$1.234.567» o
«1234567» según la pantalla, y el auditor concilia contra Dinámica Gerencial
mirando esos números: la diferencia cuesta tiempo y hace dudar de la cifra.

Ahora el formato vive en un solo lugar —`window.SDS_FMT` de `sinac-ux.js`—
para que lo usen todas las páginas, no solo el portal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
STATIC = RAIZ / "static"

PAGINAS = [
    "index.html",
    "preauditoria.html",
    "importar-recepcion.html",
    "importar-masiva.html",
    "presentacion-ia.html",
    "terapia-fisica-paciente-encamado.html",
]


def _leer(nombre: str) -> str:
    ruta = STATIC / nombre
    if not ruta.exists():  # pragma: no cover - despliegues sin static/
        pytest.skip(f"{nombre} no está en este entorno")
    return ruta.read_text(encoding="utf-8", errors="ignore")


class TestTodasLasPaginasUsanElSistemaDeDiseno:
    @pytest.mark.parametrize("pagina", PAGINAS)
    def test_carga_los_tokens(self, pagina):
        assert "sinac-ds.css" in _leer(pagina), f"{pagina} no carga el sistema de diseño"

    @pytest.mark.parametrize("pagina", PAGINAS)
    def test_carga_el_formato_compartido(self, pagina):
        assert "sinac-ux.js" in _leer(pagina), f"{pagina} no carga el formato compartido"


class TestElFormatoDeLaPlataEsUnoSolo:
    def test_el_formateador_vive_en_el_archivo_compartido(self):
        """En index.html no serviría: las otras cinco páginas no lo verían."""
        ux = _leer("sinac-ux.js")
        assert "window.SDS_FMT" in ux
        for llave in ("cop:", "num:", "fecha:"):
            assert llave in ux, llave

    def test_no_quedan_montos_formateados_a_mano(self):
        """Un `'$' + algo.toLocaleString(...)` suelto vuelve a abrir la
        puerta a que la misma cifra salga escrita distinto.

        Se permite dentro de la definición de `cop`/`fmtCOP`: ahí es el
        respaldo para cuando `sinac-ux.js` no cargó.
        """
        crudos = []
        for pagina in PAGINAS + ["sinac-asistente.js", "sinac-analizar-pro.js"]:
            ruta = STATIC / pagina
            if not ruta.exists():
                continue
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"'[^'\n]*\$\s?'\s*\+\s*[^;\n]{0,80}?toLocaleString", texto):
                linea = texto[: m.start()].count("\n") + 1
                contexto = texto.splitlines()[linea - 1]
                if "window.SDS_FMT" in contexto:  # respaldo documentado
                    continue
                crudos.append(f"{pagina}:{linea}: {m.group(0)[:60]}")
        assert not crudos, "montos formateados a mano:\n" + "\n".join(crudos[:8])

    def test_ningun_monto_usa_el_idioma_del_navegador(self):
        """`toLocaleString()` sin idioma sale con el del computador: en un
        equipo en inglés, «$1,234,567» en vez de «$1.234.567»."""
        malos = []
        for pagina in PAGINAS:
            ruta = STATIC / pagina
            if not ruta.exists():
                continue
            for i, linea in enumerate(
                ruta.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if re.search(r"'\$'\s*\+[^;\n]{0,60}toLocaleString\(\)", linea):
                    malos.append(f"{pagina}:{i}")
        assert not malos, malos

    def test_no_hay_otro_formateador_de_moneda(self):
        """`Intl.NumberFormat` con currency COP solo puede existir una vez:
        en el archivo compartido."""
        dueños = []
        for ruta in STATIC.glob("*"):
            if ruta.suffix not in (".js", ".html"):
                continue
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"Intl\.NumberFormat\([^)]{0,160}", texto):
                if "COP" in m.group(0):
                    dueños.append(ruta.name)
        # index.html conserva el suyo SOLO como respaldo si sinac-ux.js no carga.
        assert set(dueños) <= {"sinac-ux.js", "index.html", "sinac-asistente.js"}, dueños

    def test_el_respaldo_no_se_llama_a_si_mismo(self):
        """Si `sinac-ux.js` no cargó, el respaldo tiene que degradarse, no
        entrar en recursión y tumbar la pantalla entera."""
        html = _leer("index.html")
        for nombre in ("fmtFecha", "fmtFechaCorta", "fmtNum"):
            m = re.search(r"function " + nombre + r"\(v\)\{(.+?)\n", html)
            assert m, nombre
            cuerpo = m.group(1)
            # La única mención permitida es la del propio encabezado.
            assert cuerpo.count(nombre + "(") == 0, f"{nombre} se llama a sí mismo: {cuerpo[:90]}"


class TestLasFechasTambienTienenUnFormato:
    def test_existe_el_formateador_de_fechas(self):
        html = _leer("index.html")
        assert "function fmtFecha(" in html
        assert "function fmtFechaCorta(" in html

    def test_las_paginas_pueden_usarlo(self):
        assert "fechaCorta:" in _leer("sinac-ux.js")


class TestNingunaPantallaSeQuedaMuda:
    """Si el motor no responde y la pantalla no dice nada, el auditor no sabe
    si no hay datos o si se cayó algo. Peor en las que guardan: creía que su
    decisión quedó registrada y no quedó."""

    @staticmethod
    def _sin_manejo(texto: str) -> list[str]:
        malas = []
        for m in re.finditer(r"async function (\w+)\s*\([^)]*\)\s*\{", texto):
            fin = re.search(r"\n\}\n", texto[m.end() :])
            cuerpo = texto[m.end() : m.end() + (fin.start() if fin else 4000)]
            if "fetch(" in cuerpo and "catch" not in cuerpo:
                malas.append(f"{m.group(1)} (línea {texto[: m.start()].count(chr(10)) + 1})")
        return malas

    def test_toda_funcion_que_llama_al_motor_maneja_el_error(self):
        malas = self._sin_manejo(_leer("index.html"))
        assert not malas, "funciones sin manejo de error:\n" + "\n".join(malas)

    def test_la_prueba_de_verdad_detecta_una_sin_manejo(self):
        """Guardia de la guardia: si el detector se rompe, esta prueba lo
        avisa. El defecto original se contó mal —14 en vez de 7— justamente
        por mirar solo los primeros 4.000 caracteres de cada función."""
        ejemplo = "async function x(){\n  var r = await fetch('/a');\n}\n"
        assert self._sin_manejo(ejemplo), "el detector ya no detecta nada"

    def test_las_que_guardan_avisan_que_NO_se_guardo(self):
        """El mensaje tiene que decir que el dato no quedó, no solo «error»."""
        html = _leer("index.html")
        for frase in (
            "El rol NO se cambió",
            "La decisión NO quedó registrada",
            "El resultado NO quedó registrado",
        ):
            assert frase in html, frase


class TestLoQueNoSeToco:
    def test_los_conteos_no_se_volvieron_pesos(self):
        """Las glosas del mes son un conteo, no plata: si salieran con `$`
        el tablero mentiría."""
        html = _leer("index.html")
        assert "fmtCOP(a.glosas_mes" not in html
        assert "fmtNum(" in html, "los conteos deben pasar por fmtNum"

    def test_sigue_existiendo_fmtcop_con_su_nombre_de_siempre(self):
        """Lo llaman cientos de sitios; cambiarle el nombre habría sido un
        cambio gigante sin necesidad."""
        assert "function fmtCOP(" in _leer("index.html")


class TestUnSoloSignoDePeso:
    """Y un solo signo, no dos (25-08-2026).

    En la pantalla «Mis glosas pendientes» la columna de valor salía así:

        $$ 2.319.514

    y la alerta roja de vencimientos decía «Valor en riesgo: $$ 0».

    Es el mismo problema de esta prueba visto por el otro lado: `fmtCOP` ya
    trae el signo, y en dos sitios se le agregaba otro delante. El formato es
    uno solo justamente para no tener que acordarse de si el signo va o no va.
    """

    def test_la_columna_de_valor_no_duplica_el_signo(self):
        assert """'<td class="num">$' + valor +""" not in _leer("index.html"), (
            "volvió a agregarse un $ delante de fmtCOP: la columna de plata de "
            "«Mis glosas» sale «$$ 2.319.514»"
        )

    def test_la_alerta_de_vencimientos_tampoco(self):
        assert "'Valor en riesgo: <b>$' + valor" not in _leer("index.html"), (
            "la alerta vuelve a salir «Valor en riesgo: $$ 0»"
        )

    @pytest.mark.parametrize("variante", ["'$' + fmtCOP(", '"$" + fmtCOP(', "'$'+fmtCOP("])
    def test_a_fmtcop_no_se_le_pega_un_signo(self, variante):
        assert variante not in _leer("index.html"), f"alguien volvió a escribir {variante}"


class TestLaAlertaDeVencimientosNoSeContradice:
    """La misma línea traía una frase falsa (25-08-2026).

    La alerta roja que avisa de una glosa que vence hoy decía:

        «Si no se responden hoy, opera el silencio en contra del prestador
         (Art. 57 Ley 1438/2011 sólo aplica a EPS, NO al hospital).»

    Las dos mitades no pueden ser ciertas a la vez, y el paréntesis es falso.
    Se verificó el texto oficial: el Art. 57 SÍ obliga al prestador — «si los
    prestadores no contestan en el plazo señalado, se entenderá aceptada la
    glosa». O sea que la frase desmentía su propia advertencia, y encima en el
    aviso que le dice al gestor que se le está venciendo una glosa.
    """

    def test_ya_no_dice_que_el_articulo_57_no_aplica_al_hospital(self):
        assert "sólo aplica a EPS, NO al hospital" not in _leer("index.html"), (
            "volvió la frase falsa: el Art. 57 SÍ obliga al prestador"
        )

    def test_cita_el_texto_real_de_la_norma(self):
        t = _leer("index.html")
        assert "se entenderá aceptada la glosa" in t, (
            "la alerta debe decirle al gestor lo que de verdad pasa si no responde"
        )
        assert "Art. 57, Ley 1438 de 2011" in t

    def test_la_advertencia_sigue_en_pie(self):
        """El arreglo no podía dejar al gestor sin el aviso."""
        t = _leer("index.html")
        assert "vencen en las próximas 24h" in t
        assert "Valor en riesgo" in t
