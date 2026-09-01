"""Una pantalla que no cargó no puede quedarse callada.

25-08-2026. Se contaron las 278 funciones de `index.html` que le piden datos al
motor. 77 tienen su `catch` — pero el catch **solo escribe en la consola del
navegador**, que el auditor no abre nunca. Si se cae la red, la tabla vieja se
queda en pantalla con cara de estar al dia y el auditor concilia contra numeros
que ya no son.

(El primer conteo dio 24 y estaba mal: se caian de la cuenta las funciones que
mezclan un catch vacio con uno de consola. Contadas bien: 77. Es la segunda vez
que un conteo de estos sale corto — la primera fue el de las pantallas mudas,
que dio 14 y eran 7.)

EL CASO QUE LO DECIDIO. La tarjeta de glosas por vencerse. Si falla, no
aparece — y el auditor no se entera de que habia glosas a punto de vencerse.
Una glosa no contestada dentro del plazo **se entiende aceptada** (Art. 57 de
la Ley 1438 de 2011). O sea que el silencio de esa tarjeta cuesta plata.
Ademas se devolvia callada tambien cuando el servidor respondia con error, no
solo cuando fallaba la red.

QUE CUIDA ESTA PRUEBA. Que las pantallas donde el auditor mira plata o toma
decisiones avisen cuando no cargan. No cubre los adornos (insignias, banners,
sugerencias): que un adorno no cargue no le hace perder plata a nadie.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"

# Las pantallas donde el auditor mira plata o decide algo.
PANTALLAS_DE_PLATA = [
    ("vencCargarTarjeta", "la tarjeta de glosas por vencerse"),
    ("loadHist", "el historial de glosas"),
    ("loadDash", "el tablero"),
    ("loadDashCobranza", "el tablero de cobranza"),
    ("loadResumenMes", "el resumen del mes"),
    ("loadMando", "el tablero de mando"),
    ("loadMandoIAPorUsuario", "el uso de IA por usuario"),
    ("loadMandoVacaciones", "las vacaciones del equipo"),
    ("loadMandoDetector", "el detector de riesgos"),
    ("loadGlosasAdres", "las glosas de ADRES"),
    ("loadContratos", "los contratos"),
    ("cargarPlataRecuperada", "la plata recuperada"),
    ("cargarAnaliticaPredictiva", "la analítica predictiva"),
    ("cargarComentarios", "los comentarios del expediente"),
]


@pytest.fixture(scope="module")
def html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _cuerpo_de(html: str, nombre: str) -> str:
    """El cuerpo de una función, hasta que empiece la siguiente."""
    lineas = html.split("\n")
    inicios = [
        i
        for i, ln in enumerate(lineas)
        if re.match(r"\s*(?:async\s+)?function\s+[A-Za-z_$][\w$]*", ln)
    ]
    for k, i in enumerate(inicios):
        if re.match(rf"\s*(?:async\s+)?function\s+{re.escape(nombre)}\b", lineas[i]):
            fin = inicios[k + 1] if k + 1 < len(inicios) else len(lineas)
            return "\n".join(lineas[i:fin])
    raise AssertionError(f"no existe la función {nombre} en index.html")


class TestElAyudanteExiste:
    def test_hay_una_sola_forma_de_avisar(self, html):
        assert html.count("function avisarNoCargo(") == 1

    def test_el_aviso_dice_que_lo_de_pantalla_puede_estar_viejo(self, html):
        cuerpo = _cuerpo_de(html, "avisarNoCargo")
        assert "puede estar desactualizado" in cuerpo, (
            "el auditor tiene que saber que la tabla que ve ya no es de fiar"
        )
        assert "No se pudo cargar" in cuerpo

    def test_no_repite_el_aviso_a_cada_segundo(self, html):
        """Con la red caída fallan seis cosas a la vez; seis avisos seguidos no
        los lee nadie."""
        cuerpo = _cuerpo_de(html, "avisarNoCargo")
        assert "15000" in cuerpo
        assert "_avisosDeCarga" in cuerpo

    def test_el_aviso_nunca_puede_tumbar_la_pantalla(self, html):
        """Si avisar fallara, no puede llevarse por delante lo que sí cargó."""
        cuerpo = _cuerpo_de(html, "avisarNoCargo")
        assert "try{" in cuerpo and "catch" in cuerpo


class TestLasPantallasDePlataAvisan:
    @pytest.mark.parametrize("funcion,etiqueta", PANTALLAS_DE_PLATA)
    def test_avisa_con_su_nombre_en_cristiano(self, html, funcion, etiqueta):
        cuerpo = _cuerpo_de(html, funcion)
        assert f"avisarNoCargo('{etiqueta}'" in cuerpo, (
            f"{funcion} falla en silencio: el auditor se queda con la pantalla vieja"
        )

    @pytest.mark.parametrize("funcion,_", PANTALLAS_DE_PLATA)
    def test_ya_no_se_queda_solo_en_la_consola(self, html, funcion, _):
        cuerpo = _cuerpo_de(html, funcion)
        catches = re.findall(r"catch\s*\([^)]*\)\s*\{(.*?)\}", cuerpo, re.S)
        solo_consola = [
            c for c in catches if re.search(r"console\.", c) and "avisarNoCargo" not in c
        ]
        assert not solo_consola, (
            f"{funcion} tiene un catch que solo va a la consola: {solo_consola}"
        )


class TestLaTarjetaDeVencimientos:
    """La más grave de todas: su silencio se traduce en glosas aceptadas por
    vencimiento (Art. 57 Ley 1438 de 2011)."""

    def test_avisa_tambien_cuando_el_servidor_responde_con_error(self, html):
        cuerpo = _cuerpo_de(html, "vencCargarTarjeta")
        assert "if(!r.ok){ avisarNoCargo(" in cuerpo, (
            "antes hacía «if(!r.ok) return;» y el error del servidor pasaba callado"
        )

    def test_no_queda_ningun_return_callado(self, html):
        cuerpo = _cuerpo_de(html, "vencCargarTarjeta")
        assert "if(!r.ok) return;" not in cuerpo


class TestLaCortinaDiceLaVerdad:
    """La cortina de carga contaba una historia que no era.

    `showLoading()` no recibia parametro y rotaba siempre la misma lista:
    «Identificando tipo de glosa», «Verificando normativa aplicable»… Cinco
    llamadas SI le pasaban un mensaje —«Borrando datos…», «Enviando alertas por
    correo…»— y la funcion lo descartaba.

    Resultado: mientras el sistema BORRABA DATOS, la pantalla le decia al
    auditor que estaba analizando una glosa.
    """

    def test_recibe_el_mensaje_de_quien_la_llama(self, html):
        assert "function showLoading(mensaje){" in html

    def test_si_le_dan_mensaje_lo_muestra_y_no_rota(self, html):
        cuerpo = _cuerpo_de(html, "showLoading")
        assert "if(mensaje){" in cuerpo
        i_msg = cuerpo.index("if(mensaje){")
        i_rot = cuerpo.index("setInterval")
        assert i_msg < i_rot, "el mensaje propio debe cortar antes de arrancar la rotación"

    def test_sin_mensaje_sigue_narrando_el_analisis(self, html):
        cuerpo = _cuerpo_de(html, "showLoading")
        assert "loadMsgs[0]" in cuerpo and "setInterval" in cuerpo

    def test_no_deja_dos_rotaciones_corriendo(self, html):
        """Dos llamadas seguidas dejaban dos setInterval vivos pisándose."""
        cuerpo = _cuerpo_de(html, "showLoading")
        assert "clearInterval(loadInterval)" in cuerpo

    def test_las_llamadas_con_mensaje_siguen_ahi(self, html):
        for mensaje in ("Borrando datos…", "Enviando alertas por correo…", "Analizando con IA…"):
            assert f"showLoading('{mensaje}')" in html, mensaje
