"""Tests para app.services.aprendizaje_diff — aprende por DIFF de versiones."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import DictamenVersionRecord, GlosaRecord
from app.services.aprendizaje_diff import (
    diff_normas_agregadas,
    extraer_normas,
    patron_diff_gestor,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


class TestExtraerNormas:
    def test_detecta_sentencia(self):
        normas = extraer_normas("Conforme a la Sentencia T-760/2008 de la Corte")
        assert "sent:T-760/2008" in normas

    def test_detecta_articulo(self):
        normas = extraer_normas("Según el Art. 177 de la Ley 100/1993")
        assert "art:177" in normas
        assert "ley:100" in normas

    def test_detecta_resolucion(self):
        normas = extraer_normas("Res. 2284 de 2023")
        assert "res:2284" in normas

    def test_detecta_decreto(self):
        normas = extraer_normas("Decreto 4747/2007")
        assert "dec:4747" in normas

    def test_detecta_circular(self):
        normas = extraer_normas("Circular Externa 047/2025")
        assert "circ:047" in normas

    def test_devuelve_set_vacio_para_texto_sin_normas(self):
        assert extraer_normas("Esto es solo texto plano sin normas") == set()

    def test_devuelve_set_vacio_para_string_vacio(self):
        assert extraer_normas("") == set()

    def test_ignora_tags_html(self):
        normas = extraer_normas("<p>Conforme al <b>Art. 57</b> de la Ley 1438</p>")
        assert "art:57" in normas
        assert "ley:1438" in normas


class TestDiffNormasAgregadas:
    def test_norma_nueva_se_detecta(self):
        orig = "El dictamen cita Art. 177 Ley 100"
        edit = "El dictamen cita Art. 177 Ley 100 y Sentencia T-760/2008"
        agregadas = diff_normas_agregadas(orig, edit)
        assert "sent:T-760/2008" in agregadas
        assert "art:177" not in agregadas  # ya estaba

    def test_sin_cambios_devuelve_vacio(self):
        texto = "Art. 177 Ley 100, Sentencia T-760"
        assert diff_normas_agregadas(texto, texto) == set()

    def test_norma_quitada_no_es_agregada(self):
        orig = "Art. 177 + Sentencia T-760/2008"
        edit = "Art. 177 solamente"  # quitaron la sentencia
        assert "sent:T-760/2008" not in diff_normas_agregadas(orig, edit)

    def test_multiples_normas_agregadas(self):
        orig = "Base legal: Art. 177"
        edit = "Base legal: Art. 177, Decreto 4747/2007 y Res. 2284/2023"
        agregadas = diff_normas_agregadas(orig, edit)
        assert "dec:4747" in agregadas
        assert "res:2284" in agregadas


class TestPatronDiffGestor:
    def _crear_glosa(self, db, gid: int, codigo: str = "TA0201", eps: str = "FAMISANAR"):
        g = GlosaRecord(
            id=gid,
            codigo_glosa=codigo,
            eps=eps,
            estado="RESPONDIDA",
        )
        db.add(g)
        db.commit()
        return g

    def _crear_versiones(
        self,
        db,
        gid: int,
        textos: list[str],
        autor: str = "yesid@hus.gov.co",
        dias_atras_inicial: int = 30,
    ):
        """Crea N versiones cronológicas separadas por 1 día."""
        base = datetime.now(timezone.utc) - timedelta(days=dias_atras_inicial)
        for i, t in enumerate(textos):
            db.add(
                DictamenVersionRecord(
                    glosa_id=gid,
                    dictamen_html=t,
                    accion="REFINAR" if i > 0 else "CREAR",
                    autor_email=autor,
                    creado_en=base + timedelta(days=i),
                )
            )
        db.commit()

    def test_sin_versiones_devuelve_vacio(self, db_session):
        r = patron_diff_gestor(db_session, "nadie@hus.gov.co")
        assert r["n_diffs"] == 0
        assert r["normas_recurrentes"] == []
        assert r["hint_para_prompt"] == ""

    def test_email_vacio_devuelve_vacio(self, db_session):
        r = patron_diff_gestor(db_session, "")
        assert r["n_diffs"] == 0

    def test_detecta_norma_agregada_3_veces(self, db_session):
        # 3 glosas distintas donde el gestor agrega T-760 en la 2da versión
        for gid in (1, 2, 3):
            self._crear_glosa(db_session, gid)
            self._crear_versiones(
                db_session,
                gid,
                ["<p>Dictamen base sin T-760</p>", "<p>Dictamen + Sentencia T-760/2008</p>"],
            )
        r = patron_diff_gestor(db_session, "yesid@hus.gov.co", min_repeticiones=3)
        normas = [n["norma"] for n in r["normas_recurrentes"]]
        assert any("T-760" in n for n in normas)
        assert r["n_glosas_analizadas"] == 3
        assert r["n_diffs"] == 3
        assert "T-760" in r["hint_para_prompt"]

    def test_norma_agregada_solo_1_vez_no_se_reporta(self, db_session):
        # 1 sola adición no genera patrón (umbral default = 3)
        self._crear_glosa(db_session, 1)
        self._crear_versiones(
            db_session,
            1,
            ["base", "base + Sentencia T-1025"],
        )
        r = patron_diff_gestor(db_session, "yesid@hus.gov.co")
        assert r["normas_recurrentes"] == []

    def test_filtro_por_codigo_glosa(self, db_session):
        # 3 glosas TA0201 con T-760 agregada — dentro del filtro
        for gid in (1, 2, 3):
            self._crear_glosa(db_session, gid, codigo="TA0201")
            self._crear_versiones(db_session, gid, ["base", "base + T-760/2008"])
        # 3 glosas SO0501 con otra norma — fuera del filtro
        for gid in (10, 11, 12):
            self._crear_glosa(db_session, gid, codigo="SO0501")
            self._crear_versiones(db_session, gid, ["base", "base + Sentencia T-1025"])

        r = patron_diff_gestor(db_session, "yesid@hus.gov.co", codigo_glosa="TA0201")
        normas = " ".join(n["norma"] for n in r["normas_recurrentes"])
        assert "T-760" in normas
        # T-1025 NO debería aparecer porque las SO0501 quedan fuera del filtro
        assert "T-1025" not in normas

    def test_hint_para_prompt_incluye_conteo(self, db_session):
        for gid in (1, 2, 3, 4):
            self._crear_glosa(db_session, gid)
            self._crear_versiones(db_session, gid, ["sin norma", "ahora con Art. 57 Ley 1438"])
        r = patron_diff_gestor(db_session, "yesid@hus.gov.co")
        # Debe mencionar 'agregada X veces'
        assert "veces" in r["hint_para_prompt"]
