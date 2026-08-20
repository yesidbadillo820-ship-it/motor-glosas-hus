"""Dos motores no pueden escribir en dos bases distintas (20-08-2026).

El valor por defecto era `sqlite:///./glosas.db` — una ruta **relativa**, o sea
relativa a la carpeta desde la que se arrancó cada motor.

El panel de Diagnóstico del PC de cartera destapó lo que eso significa: había
**DOS motores corriendo** (puerto 8080 y puerto 8000). Arrancados desde
carpetas distintas, cada uno escribe en SU PROPIA base. El auditor vio las
glosas pasar de 62 a 35 y el historial de importaciones reiniciarse — no se
había perdido nada, estaba en la otra base.

Trabajar sobre una base creyendo estar viendo la otra es de lo peor que le
puede pasar a cartera: se responde una glosa que en «la» base sigue pendiente,
y nadie se entera hasta que vence.
"""

from __future__ import annotations

from pathlib import Path

from app.core import config as cfg


class TestLaRutaEsAbsoluta:
    def test_ya_no_es_relativa(self):
        assert "///./" not in cfg._RUTA_BD_POR_DEFECTO, (
            "Volvió la ruta relativa: dos motores arrancados desde carpetas "
            "distintas escribirían en dos bases diferentes."
        )
        assert cfg._RUTA_BD_POR_DEFECTO.startswith("sqlite:////")

    def test_apunta_a_la_raiz_del_repositorio(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        raiz = Path(cfg.__file__).resolve().parents[2]
        assert cfg._ruta_de_la_base() == f"sqlite:///{(raiz / 'glosas.db').as_posix()}"

    def test_no_cambia_arranque_desde_donde_arranque(self, tmp_path, monkeypatch):
        """Lo esencial: la misma respuesta desde cualquier carpeta."""
        desde_repo = cfg._ruta_de_la_base()
        monkeypatch.chdir(tmp_path)
        assert cfg._ruta_de_la_base() == desde_repo


class TestNoLeEsconderLosDatosANadie:
    """La otra mitad, y la que de verdad importa: si un despliegue ya tiene su
    base en otra carpeta, cambiársela le escondería sus datos — justo el daño
    que este arreglo viene a evitar."""

    def test_si_ya_hay_una_base_en_la_carpeta_actual_se_respeta(self, tmp_path, monkeypatch):
        (tmp_path / "glosas.db").write_bytes(b"SQLite format 3\x00")
        monkeypatch.chdir(tmp_path)
        # Se simula que en la raíz NO hay ninguna.
        monkeypatch.setattr(
            cfg.Path, "is_file", lambda self: self == tmp_path / "glosas.db", raising=False
        )
        assert cfg._ruta_de_la_base() == f"sqlite:///{(tmp_path / 'glosas.db').as_posix()}"

    def test_pero_si_la_raiz_ya_tiene_la_suya_manda_esa(self, tmp_path, monkeypatch):
        (tmp_path / "glosas.db").write_bytes(b"SQLite format 3\x00")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cfg.Path, "is_file", lambda self: True, raising=False)
        raiz = Path(cfg.__file__).resolve().parents[2]
        assert cfg._ruta_de_la_base() == f"sqlite:///{(raiz / 'glosas.db').as_posix()}"


class TestElEnvSigueMandando:
    def test_un_DATABASE_URL_explicito_no_se_toca(self):
        """Si el hospital configura su propia base —Postgres, otra ruta— eso
        manda sobre cualquier valor por defecto."""
        s = cfg.Settings(_env_file=None, DATABASE_URL="postgresql://x/y", SECRET_KEY="k" * 32)
        assert s.database_url == "postgresql://x/y"
