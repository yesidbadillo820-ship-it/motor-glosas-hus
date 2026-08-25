"""Una etiqueta no puede parecer un botón.

QUÉ PASÓ (25-08-2026). Yesid escribió: «tengo estos botones pero no hacen
nada», y mandó la foto de la columna WORKFLOW de «Mis glosas». Ahí salía un
rectángulo morado con relleno que decía «— Editar manual», encima del chip de
RADICADA o BORRADOR.

No estaban dañados: NUNCA fueron botones. Es el nivel de auto-piloto de la
glosa —«esta requiere intervención humana»— y siempre fue informativo. El
problema es que estaba pintado con fondo sólido y color de acción, o sea
idéntico a los botones del sistema. En un portal donde todo lo morado se
puede hacer clic, una etiqueta disfrazada de botón enseña a desconfiar de la
interfaz: uno le da clic, no pasa nada, y la próxima vez ya no confía en
ningún botón.

Ahora va con borde y sin relleno, igual que el chip de estado que tiene al
lado, que sí se lee como lo que es.

Y de paso el icono: el lápiz iba como «✏» sin selector de emoji, que en
Windows se dibuja como una raya. Por eso la etiqueta se leía «— Editar
manual» en vez de «✏️ Editar manual». Los otros dos niveles usan 🤖 y ⚡, que
sí se ven bien porque son emoji completos.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _index() -> str:
    return (RAIZ / "static" / "index.html").read_text(encoding="utf-8")


def _niveles() -> str:
    return (RAIZ / "app" / "services" / "autopiloto_nivel.py").read_text(encoding="utf-8")


class TestElChipDeAutopilotoSeLeeComoEtiqueta:
    def test_ya_no_lleva_relleno_solido(self):
        assert "style=\"background:' + apnBg + ';color:#fff;border:0" not in _index(), (
            "el chip de auto-piloto volvió a pintarse como un botón"
        )

    def test_va_con_borde_como_el_chip_de_estado(self):
        i = _index()
        assert "background:transparent;color:' + apnBg + ';border:1px solid ' + apnBg" in i

    def test_conserva_el_porque_al_pasar_el_mouse(self):
        """Quitarle el relleno no podía costarle la explicación."""
        i = _index()
        assert "title=\"' + apnTooltip + '\"" in i


class TestElLapizSeDibuja:
    def test_el_icono_de_editar_lleva_selector_de_emoji(self):
        assert '"icono": "✏️"' in _niveles(), (
            "sin el selector, Windows dibuja el lápiz como una raya y la "
            "etiqueta se lee «— Editar manual»"
        )

    def test_los_otros_dos_niveles_siguen_igual(self):
        n = _niveles()
        assert '"icono": "🤖"' in n
        assert '"icono": "⚡"' in n

    def test_las_tres_etiquetas_siguen_diciendo_lo_mismo(self):
        n = _niveles()
        for etiqueta in ("Mecánica", "Revisar y aprobar", "Editar manual"):
            assert etiqueta in n
