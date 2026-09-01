"""Si falta el .env, hay que decirlo (20-08-2026).

La otra mitad del arreglo de la ruta. Anclar bien el archivo evita que se
pierda, pero no sirve de nada si cuando falta el motor **se calla**: desde
afuera, «no encontré el archivo» y «el archivo está vacío» se ven exactamente
igual, y el auditor termina buscando el problema donde no está.

Fue justo lo que pasó: Yesid agregó el correo, el motor siguió diciendo que no
estaba configurado, y no había manera de distinguir «no guardaste las líneas»
de «no encuentro tu archivo».
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import diagnostico_del_env


class TestCuandoElArchivoNoEsta:
    def test_lo_dice(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("app.core.config._ruta_del_env", lambda: str(tmp_path / ".env"))
        d = diagnostico_del_env()
        assert d["existe"] is False
        assert d["aviso"]

    def test_avisa_que_todo_corre_con_los_valores_por_defecto(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config._ruta_del_env", lambda: str(tmp_path / ".env"))
        d = diagnostico_del_env()
        assert "variables del entorno" in d["aviso"]
        assert "sin que nada lo diga" in d["aviso"]

    def test_detecta_el_punto_env_punto_txt_del_bloc_de_notas(self, tmp_path, monkeypatch):
        """El descuido clásico: el Bloc de notas guarda «.env» como «.env.txt»
        y Windows esconde la extensión, así que en el explorador se ve bien."""
        (tmp_path / ".env.txt").write_text("SMTP_USER=x\n", encoding="utf-8")
        monkeypatch.setattr("app.core.config._ruta_del_env", lambda: str(tmp_path / ".env"))
        d = diagnostico_del_env()
        assert ".env.txt" in d["archivos_parecidos"]
        assert "Bloc de" in d["aviso"]


class TestNoGritaPorLoNormal:
    """Un aviso que salta por algo normal enseña a ignorar los avisos."""

    def test_el_env_example_del_repositorio_no_es_un_descuido(self, tmp_path, monkeypatch):
        (tmp_path / ".env.example").write_text("SECRET_KEY=\n", encoding="utf-8")
        monkeypatch.setattr("app.core.config._ruta_del_env", lambda: str(tmp_path / ".env"))
        d = diagnostico_del_env()
        assert d["archivos_parecidos"] == []

    def test_ni_las_demas_plantillas(self, tmp_path, monkeypatch):
        for nombre in (".env.sample", ".env.template", ".env.dist"):
            (tmp_path / nombre).write_text("x=1\n", encoding="utf-8")
        monkeypatch.setattr("app.core.config._ruta_del_env", lambda: str(tmp_path / ".env"))
        assert diagnostico_del_env()["archivos_parecidos"] == []

    def test_con_el_archivo_presente_no_hay_aviso(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("SECRET_KEY=abc\n", encoding="utf-8")
        monkeypatch.setattr("app.core.config._ruta_del_env", lambda: str(tmp_path / ".env"))
        d = diagnostico_del_env()
        assert d["existe"] is True
        assert d["aviso"] == ""


class TestElPanelDeDiagnosticoLoMuestra:
    def test_hay_una_seccion_de_configuracion(self):
        import inspect

        from app.api.routers import diagnostico

        fuente = inspect.getsource(diagnostico.diagnostico_completo)
        assert '"configuracion"' in fuente
        assert "diagnostico_del_env" in fuente

    def test_se_marca_como_error_y_no_como_aviso_menor(self):
        """Sin `.env` el motor corre sin claves de IA ni correo: eso no es un
        detalle, es que media aplicación no funciona."""
        import inspect

        from app.api.routers import diagnostico

        fuente = inspect.getsource(diagnostico.diagnostico_completo)
        assert '"ok" if _env["existe"] else "error"' in fuente

    def test_una_carpeta_ilegible_no_tumba_el_diagnostico(self, monkeypatch):
        """El panel nunca se puede caer entero por esta revisión."""
        monkeypatch.setattr(
            "app.core.config._ruta_del_env",
            lambda: str(Path("/carpeta/que/no/existe/.env")),
        )
        d = diagnostico_del_env()
        assert d["existe"] is False
