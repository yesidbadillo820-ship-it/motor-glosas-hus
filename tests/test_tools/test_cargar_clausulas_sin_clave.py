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


class TestGuardarContraLaBaseDeVerdad:
    """Las pruebas de la primera versión revisaban el archivo y las reglas,
    pero NUNCA guardaron contra el modelo real. Así pasó de largo que la
    columna se llama `numero_clausula` y el archivo dice `numero`: el bot dijo
    «17 cláusulas listas», mostró la base correcta… y reventó en el PC de
    cartera al escribir la primera fila (24-08-2026)."""

    @pytest.fixture()
    def base(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        import app.database as database
        from app.models.db import Base

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        fabrica = sessionmaker(bind=engine)
        monkeypatch.setattr(database, "SessionLocal", fabrica)
        yield fabrica
        engine.dispose()

    def test_guarda_de_verdad_y_en_las_columnas_correctas(self, base):
        from app.models.db import ClausulaContrato

        r = bot.guardar("POSITIVA", [_clausula()], reemplazar=True)
        assert r["insertadas"] == 1 and r["total_actual"] == 1

        s = base()
        fila = s.query(ClausulaContrato).one()
        s.close()
        assert fila.eps == "POSITIVA"
        assert fila.numero_clausula == "CLÁUSULA QUINTA (Otrosí 02)"
        assert fila.tema == "TA"
        assert fila.pagina == 5
        assert "pago por evento" in fila.texto_literal

    def test_reemplazar_borra_lo_viejo_y_agregar_no(self, base):
        bot.guardar("POSITIVA", [_clausula(titulo="vieja")], reemplazar=True)
        r = bot.guardar("POSITIVA", [_clausula(titulo="nueva")], reemplazar=True)
        assert r["total_actual"] == 1
        r = bot.guardar("POSITIVA", [_clausula(titulo="extra")], reemplazar=False)
        assert r["total_actual"] == 2

    def test_si_revienta_a_mitad_no_borra_lo_que_habia(self, base):
        """El incidente exacto del 24-08: con reemplazar, primero se borran las
        existentes y luego se insertan. Si el insertar revienta, el borrado NO
        puede quedar hecho — el auditor perdería sus cláusulas por un intento
        fallido, igual que el instalador que borraba la tarea de arranque."""
        from app.models.db import ClausulaContrato

        bot.guardar("POSITIVA", [_clausula(titulo="la que ya estaba")], reemplazar=True)
        rota = _clausula()
        del rota["numero"]  # el bot revienta al leerla
        with pytest.raises(KeyError):
            bot.guardar("POSITIVA", [rota], reemplazar=True)

        s = base()
        vivas = s.query(ClausulaContrato).count()
        s.close()
        assert vivas == 1, "el intento fallido se llevó las cláusulas que había"

    def test_el_lote_real_de_positiva_entra_completo(self, base):
        from pathlib import Path

        ruta = Path(
            "/tmp/claude-0/-home-user-motor-glosas-hus/"
            "f7600728-984d-52f4-a29a-9a155772437a/scratchpad/clausulas_positiva.json"
        )
        if not ruta.exists():
            pytest.skip("el lote de POSITIVA no está en esta máquina")
        buenas, _ = bot.revisar(bot.leer_lote(ruta))
        r = bot.guardar("POSITIVA", buenas, reemplazar=True)
        assert r["insertadas"] == 17 and r["total_actual"] == 17


class TestSiLaEpsNoExisteLoDiceEnCristiano:
    """SEGUROS MUNDIAL (24-08): la EPS no existía en Contratos y la llave
    foránea tumbó el guardado con un traceback de 60 líneas de SQLAlchemy.
    El auditor no tiene por qué descifrar eso."""

    def test_una_eps_sin_registro_recibe_instrucciones_no_traceback(self, monkeypatch):
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        import app.database as database
        from app.models.db import Base

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi, rec):
            dbapi.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))

        import pytest as _pytest

        with _pytest.raises(SystemExit) as exc:
            bot.guardar("SEGUROS MUNDIAL", [_clausula()], reemplazar=True)
        mensaje = str(exc.value)
        assert "NO existe en la pantalla de Contratos" in mensaje
        assert "Créela primero" in mensaje
        assert "No se guardó ni se borró nada" in mensaje
        engine.dispose()


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
