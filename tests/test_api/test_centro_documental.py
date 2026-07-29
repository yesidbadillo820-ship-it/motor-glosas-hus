"""El Centro Documental: la carpeta del expediente se arma sola.

Dictamen y PDF radicable, versiones, actas de conciliación, paquete de
evidencia y soportes del share — cada documento con su tipo, su origen y
cómo obtenerlo (enlace del sistema o ruta del share). Sin tablas nuevas y
sin búsquedas manuales.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import ConciliacionRecord, GlosaRecord
from app.services import centro_documental as cd


@pytest.fixture
def db_session():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


class _IndexerFake:
    def lookup(self, factura, auto_rebuild=True):
        return [
            {
                "tipo_codigo": "HEV",
                "nombre_archivo": f"HEV_{factura}.pdf",
                "ruta": f"\\\\172.16.32.83\\fe\\{factura}\\HEV.pdf",
            },
            {
                "tipo_codigo": "RIPS",
                "nombre_archivo": f"RIPS_{factura}.json",
                "ruta": f"\\\\172.16.32.83\\fe\\{factura}\\RIPS.json",
            },
        ]


def _glosa(db, con_dictamen=True, factura="HUS0000446262"):
    g = GlosaRecord(
        eps="COMPENSAR",
        codigo_glosa="TA0601",
        valor_objetado=1_000_000,
        estado="RESPONDIDA",
        etapa="RESPUESTA",
        factura=factura,
        dictamen="<div>dictamen</div>" if con_dictamen else None,
    )
    db.add(g)
    db.commit()
    return g


class TestLaCarpetaSeArmaSola:
    def test_todos_los_grupos_con_su_como_obtenerlo(self, db_session, monkeypatch):
        import app.services.soportes_autodiscovery_service as sas

        monkeypatch.setattr(sas, "get_indexer", lambda: _IndexerFake())
        g = _glosa(db_session)
        db_session.add(
            ConciliacionRecord(
                glosa_id=g.id,
                fecha_audiencia=datetime.now(timezone.utc),
                acta_numero="806",
                resultado="ACUERDO_PARCIAL",
            )
        )
        db_session.commit()

        d = cd.documentos_de(g, db_session)

        nombres_grupo = [x["nombre"] for x in d["grupos"]]
        assert "Respuesta del hospital" in nombres_grupo
        assert "Conciliación" in nombres_grupo
        assert "Evidencia legal" in nombres_grupo
        assert any(n.startswith("Soportes de la factura") for n in nombres_grupo)

        planos = [doc for gr in d["grupos"] for doc in gr["documentos"]]
        urls = {doc["url"] for doc in planos if doc["url"]}
        assert f"/glosas/{g.id}/dictamen.pdf" in urls
        assert f"/glosas/{g.id}/paquete-evidencia.json" in urls
        assert any(u.startswith("/conciliaciones/") and u.endswith("/pdf") for u in urls)

        # Los del share llevan RUTA (no se sirven por la web: son PHI)
        share = [doc for doc in planos if doc["origen"] == "share"]
        assert share and all(doc["ruta"] and not doc["url"] for doc in share)
        assert d["total_documentos"] == len(planos)

    def test_sin_dictamen_no_promete_pdf(self, db_session, monkeypatch):
        import app.services.soportes_autodiscovery_service as sas

        monkeypatch.setattr(sas, "get_indexer", lambda: _IndexerFake())
        g = _glosa(db_session, con_dictamen=False)
        d = cd.documentos_de(g, db_session)
        assert "Respuesta del hospital" not in [x["nombre"] for x in d["grupos"]]

    def test_indexer_caido_no_tumba_la_carpeta(self, db_session, monkeypatch):
        import app.services.soportes_autodiscovery_service as sas

        def _explota():
            raise RuntimeError("share caído")

        monkeypatch.setattr(sas, "get_indexer", _explota)
        g = _glosa(db_session)
        d = cd.documentos_de(g, db_session)
        assert d["total_documentos"] >= 1  # lo del sistema llega igual


class TestIntegradoAlExpediente:
    def test_el_expediente_trae_la_carpeta(self, db_session, monkeypatch):
        """Fuente única: la misma consolidación que usan pantalla e IA."""
        import app.services.soportes_autodiscovery_service as sas

        monkeypatch.setattr(sas, "get_indexer", lambda: _IndexerFake())
        from app.api.routers.glosas import construir_expediente

        g = _glosa(db_session)
        exp = construir_expediente(g.id, db_session)
        assert exp["documentos"]["total_documentos"] >= 3
        assert any(x["nombre"] == "Evidencia legal" for x in exp["documentos"]["grupos"])


class TestPantalla:
    def test_el_expediente_muestra_el_centro_documental(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "Centro Documental" in html
        assert "exp-doc-grupo" in html
        assert "function expDescargar" in html  # descarga con la sesión, no <a> plano
