"""El color con nombre de significado, y nunca solo.

31-08-2026. Del repaso de diseño salieron dos cosas concretas y medibles
sobre la paleta del motor.

**1. Los tokens se llamaban por su tono, no por su papel.**
`--sds-amber`, `--sds-rose`. Eso obliga a acordarse de si el ámbar era
«revisar» o era «error», y el día que haya que cambiar un tono hay que
buscarlo archivo por archivo. Los nombres nuevos dicen el papel, que es lo que
no cambia. Los viejos NO se tocan: todo lo que ya los usa sigue igual.

**2. Dos tonos que se parecían demasiado.**
El ámbar del motor (`#E65100`) es un rojo anaranjado: medido en la rueda de
color está a **21 grados** del rojo de error (`#C62828`). En un monitor de sala
de facturación, y para quien no distingue bien el rojo —alrededor de uno de
cada doce hombres—, esos dos avisos son el mismo aviso. El `#A67500` está a
**42 grados**: el doble de separación.

**3. La plata no tenía color propio.**
Un valor en riesgo se pintaba con el rojo de error. Una glosa de $16 millones
bien defendida no es un error: es lo que está en juego. Sacar el dinero del
semáforo deja el semáforo para lo que sí es estado.

**4. El color nunca va solo.**
Color + icono + palabra, siempre las tres. En este motor pesa más que en otros
porque **el dictamen se imprime**, y en blanco y negro el color no existe.
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[2] / "static" / "sinac-ds.css").read_text(encoding="utf-8")


def _tono(hexa: str) -> float:
    """Grados en la rueda de color (0-360)."""
    h = hexa.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def _valor(token: str) -> str:
    m = re.search(rf"{re.escape(token)}\s*:\s*([^;]+);", CSS)
    assert m, f"no existe el token {token}"
    return m.group(1).strip()


class TestSeLlamanPorSuPapel:
    @pytest.mark.parametrize(
        "token", ["--sds-probado", "--sds-revisar", "--sds-contradicho", "--sds-plata"]
    )
    def test_existe_el_nombre_de_significado(self, token: str):
        assert _valor(token)

    @pytest.mark.parametrize("token", ["--sds-amber", "--sds-rose", "--sds-success"])
    def test_no_se_rompio_ninguno_de_los_viejos(self, token: str):
        """Todo lo que ya los usa tiene que seguir pintando igual."""
        assert _valor(token)

    def test_probado_y_contradicho_reusan_el_color_de_siempre(self):
        assert "--sds-success" in _valor("--sds-probado")
        assert "--sds-rose" in _valor("--sds-contradicho")


class TestLosTonosSeDistinguen:
    def test_revisar_se_separo_del_rojo(self):
        """21 grados era muy poco; ahora son 42."""
        separacion = abs(_tono("#A67500") - _tono("#C62828"))
        assert separacion > 35, f"solo {separacion:.0f}° de separación"

    def test_el_ambar_viejo_si_estaba_pegado(self):
        """Se deja medido para que se vea por qué se cambió."""
        assert abs(_tono("#E65100") - _tono("#C62828")) < 25

    def test_revisar_no_hereda_el_ambar_viejo(self):
        assert "#A67500" in _valor("--sds-revisar")


class TestLaPlataNoEsUnError:
    def test_tiene_color_propio(self):
        assert "#00695C" in _valor("--sds-plata")

    def test_no_es_el_rojo_de_error(self):
        assert "rose" not in _valor("--sds-plata")
        assert "#C62828" not in _valor("--sds-plata")


class TestElColorNuncaVaSolo:
    @pytest.mark.parametrize("estado", ["probado", "revisar", "contradicho", "plata"])
    def test_cada_estado_lleva_su_icono(self, estado: str):
        assert f".sds-estado.es-{estado}::before" in CSS

    @pytest.mark.parametrize("estado", ["probado", "revisar", "contradicho", "plata"])
    def test_cada_estado_lleva_su_color(self, estado: str):
        assert f".sds-estado.es-{estado} " in CSS or f".sds-estado.es-{estado}{{" in CSS

    def test_el_icono_viaja_al_copiar_y_pegar(self):
        """Va como carácter en ::before, no como imagen: el gestor copia el
        estado a un correo o a un Excel y el icono se va con él."""
        bloque = CSS[CSS.index(".sds-estado {") : CSS.index(".sds-kbd {")]
        assert "content:" in bloque
        assert "<svg" not in bloque

    def test_impreso_queda_legible_sin_color(self):
        """El dictamen se imprime. En blanco y negro el fondo de color no
        sale, así que el borde y el icono son lo único que separa un estado
        de otro."""
        bloque = CSS[CSS.index(".sds-estado {") : CSS.index(".sds-kbd {")]
        assert "@media print" in bloque
        assert "border-color: #000" in bloque
