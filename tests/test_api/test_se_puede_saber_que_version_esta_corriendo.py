"""Se puede saber qué versión del motor está respondiendo — 19-08-2026.

El 19-08 se persiguió durante horas un defecto que **ya estaba corregido en
disco**. El archivo tenía el arreglo, el auditor lo confirmó con PowerShell, y
el motor seguía comportándose como si no. No había forma de responder la
pregunta más básica:

    ¿el motor que me está respondiendo tiene el código nuevo,
    o sigue con el viejo cargado en memoria?

`/sistema/version` existía para eso, pero leía el commit de `RENDER_GIT_COMMIT`
— una variable que solo existe en Render. En el PC de cartera respondía «dev»
siempre, así que el aviso de «hay una versión nueva» tampoco saltaba nunca.

Ahora el commit se lee del `.git` del propio repositorio, y se acompaña de la
hora en que arrancó el proceso. Con los dos datos juntos, si el commit es nuevo
pero el proceso es más viejo que él, se sabe de un vistazo que falta reiniciar.
"""

from __future__ import annotations

import re
import subprocess

from app.api.routers.sistema import _commit_del_repo, info_version


class TestElCommitEsElDeVerdad:
    def test_coincide_con_el_que_dice_git(self):
        real = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20
        ).stdout.strip()
        if not real:  # pragma: no cover - sin git en el entorno
            return
        assert _commit_del_repo() == real

    def test_no_responde_dev_en_un_repositorio_de_verdad(self):
        """«dev» era la respuesta siempre fuera de Render: inservible."""
        assert info_version()["commit"] != "dev"

    def test_el_corto_son_los_primeros_siete(self):
        v = info_version()
        assert v["commit"] == v["commit_full"][:7]
        assert re.fullmatch(r"[0-9a-f]{7}", v["commit"]), v["commit"]


class TestSeSabeCuandoArranco:
    def test_dice_la_hora_de_arranque_del_proceso(self):
        arranque = info_version()["proceso_arrancado_en"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", arranque), arranque

    def test_dice_cuanto_lleva_arriba(self):
        assert info_version()["proceso_lleva_segundos"] >= 0


class TestNoRevientaNunca:
    """La versión es lo primero que se mira cuando algo va mal: no puede ser
    justamente lo que falle."""

    def test_sin_git_devuelve_vacio_en_vez_de_reventar(self, monkeypatch, tmp_path):
        import app.api.routers.sistema as mod

        monkeypatch.setattr(mod, "_commit_del_repo", lambda: "")
        assert info_version()["commit"] in ("dev", "")

    def test_el_endpoint_no_pide_sesion(self):
        """Es público a propósito: sirve para diagnosticar sin poder entrar."""
        import inspect

        assert "current_user" not in inspect.signature(info_version).parameters


class TestSaleEnElDiagnostico:
    def test_la_pantalla_de_diagnostico_lo_reporta(self):
        from pathlib import Path

        fuente = (
            Path(__file__).resolve().parents[2] / "app" / "api" / "routers" / "diagnostico.py"
        ).read_text(encoding="utf-8")
        assert '"version"' in fuente
        assert "proceso_arrancado_en" in fuente
