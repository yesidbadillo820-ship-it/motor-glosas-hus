"""El .env se encuentra arranque el motor desde donde arranque (20-08-2026).

`Settings.model_config` decía `"env_file": ".env"` — una ruta **relativa**, que
Pydantic resuelve contra la carpeta desde la que se arrancó el proceso, no
contra la del repositorio.

Si el motor arranca desde otra carpeta, el `.env` **no se encuentra** y toda la
configuración cae a sus valores por defecto **en silencio**: sin claves de IA,
sin correo, sin nada. Y no hay ningún aviso, porque «no encontré el archivo» y
«el archivo está vacío» se ven exactamente igual.

Que en este repositorio ya exista `config/soportes_root.txt`, leído por ruta
absoluta y con un comentario explicando que las variables de entorno no
sobrevivían al vigilante que revive el motor, dice que esta clase de problema
ya había mordido antes por otro lado.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core import config as cfg


class TestLaRutaEsAbsoluta:
    def test_no_es_relativa(self):
        assert os.path.isabs(cfg._RUTA_ENV), (
            "La ruta del .env volvió a ser relativa. Si el motor arranca desde "
            "otra carpeta, la configuración entera cae a los valores por "
            "defecto sin avisar."
        )

    def test_apunta_a_la_raiz_del_repositorio(self):
        raiz = Path(__file__).resolve().parents[2]
        assert Path(cfg._RUTA_ENV) == raiz / ".env"

    def test_la_clase_la_usa(self):
        assert cfg.Settings.model_config["env_file"] == cfg._RUTA_ENV

    def test_manda_el_env_de_la_carpeta_actual_si_existe(self, tmp_path, monkeypatch):
        """Arrancar desde una carpeta con su propio .env es legítimo: así
        corren las pruebas del portal y así puede correr una segunda
        instancia. Ese caso NO se puede romper."""
        (tmp_path / ".env").write_text("SECRET_KEY=abc\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert Path(cfg._ruta_del_env()) == tmp_path / ".env"

    def test_pero_sin_uno_local_cae_al_del_repositorio(self, tmp_path, monkeypatch):
        """El caso que estaba roto: el motor arranca desde otra carpeta y el
        .env del hospital no se encontraba."""
        monkeypatch.chdir(tmp_path)
        raiz = Path(cfg.__file__).resolve().parents[2]
        assert Path(cfg._ruta_del_env()) == raiz / ".env"

    def test_el_reintento_con_otra_codificacion_tambien(self):
        """El .env del HUS ya llegó una vez con acentos en codificación de
        Windows. Ese reintento tiene que buscar el MISMO archivo."""
        import inspect

        fuente = inspect.getsource(cfg._leer_configuracion)
        assert '_env_file=".env"' not in fuente, (
            "El reintento con cp1252 volvió a la ruta relativa: buscaría el "
            ".env en otra carpeta que el primer intento."
        )
        assert "_ruta_del_env" in fuente


class TestSigueLeyendoLaConfiguracion:
    """La otra mitad: anclar la ruta no puede dejar de leer nada."""

    def test_las_settings_se_construyen(self):
        s = cfg.get_settings()
        assert s.app_name

    def test_los_valores_por_defecto_estan(self):
        s = cfg.get_settings()
        assert s.smtp_host == "smtp.gmail.com"
        assert s.smtp_port == 587
