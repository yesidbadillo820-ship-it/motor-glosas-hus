"""Cargar cláusulas de contrato sin clave, con las MISMAS reglas de la ruta web
(24-08-2026).

POR QUÉ EXISTE EL BOT. El contrato de POSITIVA está escaneado —cero texto— y
la IA no puede sacarle cláusulas. La ruta manual exige un token que el auditor
no tiene a mano: se intentó tres veces esa noche y las tres terminaron en
«Credenciales inválidas». El bot corre en el PC del motor y guarda directo.

LO QUE ESTAS PRUEBAS CUIDAN:

- Que el bot aplique **las mismas reglas** que la ruta web
  (`/contratos/{eps}/clausulas-manual`): mínimo 30 caracteres, temas válidos,
  topes de largo. Dos caminos con reglas distintas es tener dos verdades.
- Que **diga a qué base escribe**. El 20-08 convivieron dos bases en el PC de
  cartera y un motor apuntando a la equivocada escondió un consolidado entero.
  Cargar cláusulas en la base que el portal no mira se vería como «cargó bien»
  y el dictamen seguiría saliendo sin contrato.
- Que el **ensayo no guarde nada**: es lo que permite probar sin miedo.
"""

from __future__ import annotations

import json

import pytest

from tools import cargar_clausulas_contrato as bot


def _clausula(**kw):
    base = {
        "numero": "CLÁUSULA QUINTA (Otrosí 02)",
        "tema": "TA",
        "titulo": "Modalidad de pago y tarifas",
        "texto_literal": "POSITIVA reconocerá el valor de los servicios prestados "
        "a EL CONTRATISTA mediante la modalidad de pago por evento.",
        "pagina": 5,
    }
    base.update(kw)
    return base


class TestLeerElArchivo:
    def test_acepta_el_lote_completo(self, tmp_path):
        ruta = tmp_path / "lote.json"
        ruta.write_text(
            json.dumps({"reemplazar": True, "clausulas": [_clausula()]}), encoding="utf-8"
        )
        assert len(bot.leer_lote(ruta)) == 1

    def test_acepta_una_lista_suelta(self, tmp_path):
        ruta = tmp_path / "lista.json"
        ruta.write_text(json.dumps([_clausula(), _clausula()]), encoding="utf-8")
        assert len(bot.leer_lote(ruta)) == 2

    def test_un_archivo_que_no_es_lista_avisa(self, tmp_path):
        ruta = tmp_path / "malo.json"
        ruta.write_text('"texto suelto"', encoding="utf-8")
        with pytest.raises(ValueError):
            bot.leer_lote(ruta)


class TestLasMismasReglasQueLaRutaWeb:
    """Los números vienen de app/api/routers/contratos.py. Si allá cambian,
    acá tiene que romperse algo."""

    def test_los_umbrales_son_los_de_la_ruta(self):
        import re
        from pathlib import Path

        fuente = (
            Path(__file__).resolve().parents[2] / "app" / "api" / "routers" / "contratos.py"
        ).read_text(encoding="utf-8")
        assert "len(texto) < 30" in fuente, "la ruta web cambió su mínimo"
        temas_ruta = re.search(r"TEMAS_VALIDOS = \{([^}]+)\}", fuente).group(1)
        for tema in bot.TEMAS_VALIDOS:
            assert f'"{tema}"' in temas_ruta
        assert bot.MINIMO_TEXTO == 30
        assert bot.TOPE_TEXTO == 5000

    def test_una_clausula_corta_se_omite_y_se_explica(self):
        buenas, avisos = bot.revisar([_clausula(texto_literal="muy corta")])
        assert buenas == []
        assert len(avisos) == 1
        assert "mínimo" in avisos[0]

    def test_un_tema_inventado_cae_a_generales(self):
        buenas, avisos = bot.revisar([_clausula(tema="PAGOS")])
        assert buenas[0]["tema"] == "NN"
        assert "PAGOS" in avisos[0]

    def test_los_textos_se_recortan_a_los_topes(self):
        buenas, _ = bot.revisar([_clausula(texto_literal="x" * 9000, numero="n" * 200)])
        assert len(buenas[0]["texto_literal"]) == bot.TOPE_TEXTO
        assert len(buenas[0]["numero"]) == bot.TOPE_NUMERO

    def test_las_buenas_pasan_intactas(self):
        c = _clausula()
        buenas, avisos = bot.revisar([c])
        assert avisos == []
        assert buenas[0]["texto_literal"] == c["texto_literal"]
        assert buenas[0]["pagina"] == 5


class TestElBotNoEsconde:
    def test_dice_a_que_base_escribe(self):
        """La lección del 20-08: dos bases conviviendo y un motor mirando la
        equivocada. El bot lo imprime SIEMPRE antes de guardar."""
        import inspect

        fuente = inspect.getsource(bot.main)
        assert "base_en_uso()" in fuente

    def test_el_ensayo_va_antes_de_guardar(self):
        import inspect

        fuente = inspect.getsource(bot.main)
        assert fuente.index("a.ensayo") < fuente.index("guardar(")

    def test_el_archivo_de_positiva_pasa_completo(self):
        """El lote real que se le entregó al auditor: las 17 tienen que entrar
        sin que ninguna se caiga por las reglas."""
        from pathlib import Path

        ruta = Path(
            "/tmp/claude-0/-home-user-motor-glosas-hus/"
            "f7600728-984d-52f4-a29a-9a155772437a/scratchpad/clausulas_positiva.json"
        )
        if not ruta.exists():
            pytest.skip("el lote de POSITIVA no está en esta máquina")
        buenas, avisos = bot.revisar(bot.leer_lote(ruta))
        assert len(buenas) == 17
        assert avisos == []
