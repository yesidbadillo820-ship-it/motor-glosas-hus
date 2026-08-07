"""Las 26 cláusulas reales nunca llegaban a la base del hospital.

OT-020 · 06-08-2026. `data/clausulas_contrato_base.json` trae 26 cláusulas
LITERALES de contratos firmados, pero solo se cargaban corriendo a mano
`scripts/seed_clausulas_contrato.py`. Nadie lo corrió nunca: el Diagnóstico
del hospital reporta «0 cláusulas extraídas de 0 contratos con PDF subido».

Las consecuencias se veían en TODOS los dictámenes de prueba:

  · el desglose de confianza siempre encabezaba con «te falta: cláusula del
    contrato vigente con esta EPS», y ninguno pasó de 51%;
  · el motor no tenía una cláusula real que citar, así que o evadía la que
    la EPS invocaba o se inventaba una;
  · el verificador de citas no podía validar ninguna cita contractual,
    porque su corpus de cláusulas venía vacío.

Además, tres claves del archivo no coinciden con el catálogo de contratos
—"SEGUROS DE VIDA AURORA S.A." por AURORA (8 de las 26), "COMPENSAR EPS" por
COMPENSAR y "FAMISANAR" por FAMISANAR EPS—. Sin traducirlas, o la llave
foránea rechaza la fila, o la cláusula queda guardada bajo un nombre que
nadie va a buscar.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

RAIZ = Path(__file__).resolve().parent.parent.parent


_ARRANQUE = """
import os, sys
sys.path.insert(0, {raiz!r})
os.environ["DATABASE_URL"] = {url!r}
os.environ["DISABLE_SCHEDULERS"] = "1"
os.environ.setdefault("SECRET_KEY", "x" * 40)
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app):
    pass
"""


@pytest.fixture(scope="module")
def base_recien_arrancada():
    """Arranca la app en un proceso aparte contra una base vacía.

    En proceso no sirve: `app.database` ya quedó importado por otras
    pruebas con su propio engine, así que la app escribiría en la base de
    siempre y estaríamos leyendo otra. El subproceso es la única forma de
    probar de verdad lo que pasa en el arranque del hospital.
    """
    import subprocess

    d = tempfile.mkdtemp()
    url = f"sqlite:///{d}/seed_clausulas.db"
    r = subprocess.run(
        [sys.executable, "-c", _ARRANQUE.format(raiz=str(RAIZ), url=url)],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        timeout=300,
    )
    assert r.returncode == 0, f"el arranque falló:\n{r.stderr[-2000:]}"
    e = create_engine(url, connect_args={"check_same_thread": False})
    yield sessionmaker(bind=e)()


def _archivo() -> list[dict]:
    with (RAIZ / "data" / "clausulas_contrato_base.json").open(encoding="utf-8") as fh:
        return json.load(fh)["clausulas"]


class TestElArchivoSigueSirviendo:
    def test_trae_clausulas_con_texto_real(self):
        filas = _archivo()
        assert len(filas) >= 26
        for c in filas:
            t = (c.get("texto_literal") or "").strip()
            assert t, c.get("eps")
            assert not (t.startswith("[") and t.endswith("]")), f"placeholder sin llenar: {c}"

    def test_cada_clausula_dice_de_qué_pagador_es(self):
        for c in _archivo():
            assert (c.get("eps") or "").strip(), c


class TestLasClavesSeTraducenAlCatalogo:
    def test_las_tres_que_no_coincidian(self):
        """Sin traducir, AURORA pierde sus 8 cláusulas — el bloque más grande."""
        import sys

        sys.path.insert(0, str(RAIZ))
        from app.main import CONTRATOS_DEFAULT

        catalogo = set(CONTRATOS_DEFAULT)
        for largo, esperado in (
            ("SEGUROS DE VIDA AURORA S.A.", "AURORA"),
            ("COMPENSAR EPS", "COMPENSAR"),
            ("FAMISANAR", "FAMISANAR EPS"),
        ):
            candidatos = [k for k in catalogo if k in largo.upper() or largo.upper() in k]
            assert candidatos == [esperado], (largo, candidatos)

    def test_el_seed_traduce_por_contencion_unica(self):
        import inspect

        from app import main

        src = inspect.getsource(main.lifespan)
        assert "_clave_de_contrato" in src
        assert "len(candidatos) == 1" in src, "una coincidencia ambigua no puede resolverse sola"


class TestSeSiembranAlArrancar:
    def test_las_26_quedan_cargadas(self, base_recien_arrancada):
        from app.models.db import ClausulaContrato

        filas = base_recien_arrancada.query(ClausulaContrato).all()
        assert len(filas) == len(_archivo()), "se perdieron cláusulas en el camino"

    def test_aurora_conserva_sus_ocho(self, base_recien_arrancada):
        from app.models.db import ClausulaContrato

        n = (
            base_recien_arrancada.query(ClausulaContrato)
            .filter(ClausulaContrato.eps == "AURORA")
            .count()
        )
        assert n == 8

    def test_quedan_bajo_la_clave_que_usa_el_auditor(self, base_recien_arrancada):
        """Si se guardan con la razón social larga, el motor no las encuentra."""
        from app.models.db import ClausulaContrato

        eps = {c.eps for c in base_recien_arrancada.query(ClausulaContrato).all()}
        assert "SEGUROS DE VIDA AURORA S.A." not in eps
        assert "AURORA" in eps
        assert "COMPENSAR" in eps
        assert "FAMISANAR EPS" in eps

    def test_todas_traen_texto_y_tema_valido(self, base_recien_arrancada):
        from app.models.db import ClausulaContrato

        for c in base_recien_arrancada.query(ClausulaContrato).all():
            assert (c.texto_literal or "").strip(), c.eps
            assert c.tema in {"TA", "SO", "AU", "CO", "FA", "NN"}, (c.eps, c.tema)

    def test_el_verificador_de_citas_ya_tiene_corpus(self, base_recien_arrancada):
        """Era la razón por la que ninguna cita contractual se podía validar."""
        from app.services.citation_verifier import _corpus_clausulas_contrato

        assert _corpus_clausulas_contrato(eps="AURORA").strip()

    def test_el_motor_ya_puede_conservar_una_clausula_real(self, base_recien_arrancada):
        """Con la base vacía, la guarda de OT-001 borraba toda cláusula
        numerada. Con las reales cargadas, las que existan se conservan."""
        from app.services.glosa_service import _clausulas_cargadas

        assert _clausulas_cargadas("AURORA")
