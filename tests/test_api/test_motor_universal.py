"""Motor Universal: un perfil por pagador, armado desde los registros.

Nada de código por pagador: el perfil consulta la malla, los perfiles de
lote y el catálogo de automatizaciones. Agregar capacidad = agregar una
ficha en el registro correspondiente, y aparece sola en pantalla, API y
chat.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.db import UsuarioRecord
from app.services import perfil_pagador as pp


class TestPerfilUnificado:
    def test_coosalud_junta_los_tres_registros(self):
        p = pp.perfil("COOSALUD")
        assert p["malla"]["en_malla"] is True
        assert p["lotes_masivos"]["bot_que_carga"].startswith("responder_glosas_coosalud")
        assert p["total_capacidades"] >= 2
        assert any("lotes" in c.lower() for c in p["capacidades"])

    def test_savia_encuentra_su_conversor(self):
        p = pp.perfil("SAVIA SALUD")
        assert any("SAVIA" in c["nombre"] for c in p["conversores"])

    def test_todo_pagador_de_la_malla_tiene_perfil(self):
        mapa = pp.catalogo()
        assert len(mapa) >= 15
        assert all(x["total_capacidades"] >= 1 for x in mapa)

    def test_una_fuente_caida_no_tumba_el_perfil(self, monkeypatch):
        monkeypatch.setattr(pp, "_lotes_de", lambda _p: (_ for _ in ()).throw(RuntimeError("rota")))
        p = pp.perfil("COOSALUD")
        assert p["lotes_masivos"] is None
        assert p["malla"]["en_malla"] is True  # las demás fuentes llegaron


class TestAPIyIA:
    @pytest.fixture
    def cliente(self):
        from app.api.deps import get_usuario_actual
        from app.main import app

        u = UsuarioRecord(id=1, email="v@hus.gov.co", nombre="V", rol="VIEWER", activo=1)
        app.dependency_overrides[get_usuario_actual] = lambda: u
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def test_endpoints(self, cliente):
        r = cliente.get("/malla/perfil", params={"pagador": "COOSALUD"})
        assert r.status_code == 200 and r.json()["total_capacidades"] >= 2
        r2 = cliente.get("/malla/pagadores")
        assert r2.status_code == 200 and len(r2.json()["pagadores"]) >= 15

    async def test_la_ia_tiene_el_perfil(self):
        from app.services import asistente_maestro as am

        assert any(t["name"] == "perfil_pagador" for t in am.TOOLS_ASISTENTE)
        d = json.loads(
            await am.execute_tool_asistente(
                "perfil_pagador", {"pagador": "COOSALUD"}, db=None, current_user=None
            )
        )
        assert d["total_capacidades"] >= 2


class TestPantalla:
    def test_la_fila_de_contratos_muestra_capacidades(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "mallaCapacidades" in html
        assert "El sistema con este pagador" in html
        assert "/malla/perfil?pagador=" in html
