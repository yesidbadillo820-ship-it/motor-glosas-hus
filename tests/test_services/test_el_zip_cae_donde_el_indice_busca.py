"""El .zip de soportes tiene que caer donde el índice sí busca (20-08-2026).

La carpeta de soportes se resolvía en DOS lugares con reglas distintas:

    Indexador                        Subida del .zip
    1. config/soportes_root.txt      1. SOPORTES_LOCAL_ROOT
    2. SOPORTES_ROOT                 2. SOPORTES_ROOT
    3. SOPORTES_LOCAL_ROOT           3. /tmp/motor-soportes
    4. /tmp/motor-soportes

La subida **ni siquiera leía** `config/soportes_root.txt`, que es donde el
hospital dejó escrita la suya (`\\\\Prime\\radicacion_2026`).

Resultado: el auditor subía un .zip, el motor decía «subido», y los PDFs
quedaban en una carpeta que el índice **nunca recorre**. Después buscaba la
factura, no aparecía, y no había forma de entender por qué — el archivo
estaba, pero en otro lado.

Dos lugares decidiendo lo mismo con reglas distintas es un defecto esperando
el momento.
"""

from __future__ import annotations

from app.services import soportes_autodiscovery_service as svc


class TestUnaSolaRespuestaParaTodos:
    def test_manda_el_archivo_del_hospital_sobre_las_variables(self, monkeypatch, tmp_path):
        """`config/soportes_root.txt` va primero a propósito: el vigilante que
        revive el motor conserva las variables de cuando ÉL arrancó."""
        monkeypatch.setattr(svc, "_raiz_configurada", lambda: r"\\Prime\radicacion_2026")
        monkeypatch.setenv("SOPORTES_ROOT", str(tmp_path / "otra"))
        monkeypatch.setenv("SOPORTES_LOCAL_ROOT", str(tmp_path / "otra-mas"))
        assert svc.raiz_de_soportes() == r"\\Prime\radicacion_2026"

    def test_sin_ese_archivo_manda_SOPORTES_ROOT(self, monkeypatch, tmp_path):
        monkeypatch.setattr(svc, "_raiz_configurada", lambda: None)
        monkeypatch.setenv("SOPORTES_ROOT", str(tmp_path / "share"))
        monkeypatch.setenv("SOPORTES_LOCAL_ROOT", str(tmp_path / "local"))
        assert svc.raiz_de_soportes() == str(tmp_path / "share")

    def test_después_SOPORTES_LOCAL_ROOT(self, monkeypatch, tmp_path):
        monkeypatch.setattr(svc, "_raiz_configurada", lambda: None)
        monkeypatch.delenv("SOPORTES_ROOT", raising=False)
        monkeypatch.setenv("SOPORTES_LOCAL_ROOT", str(tmp_path / "local"))
        assert svc.raiz_de_soportes() == str(tmp_path / "local")

    def test_y_sin_nada_configurado_el_default(self, monkeypatch):
        monkeypatch.setattr(svc, "_raiz_configurada", lambda: None)
        monkeypatch.delenv("SOPORTES_ROOT", raising=False)
        monkeypatch.delenv("SOPORTES_LOCAL_ROOT", raising=False)
        assert svc.raiz_de_soportes() == "/tmp/motor-soportes"


class TestElIndiceYLaSubidaMiranLoMismo:
    """La prueba que importa: que no puedan volver a separarse."""

    def test_el_indexador_usa_el_resolvedor_unico(self, monkeypatch, tmp_path):
        destino = tmp_path / "elegida"
        monkeypatch.setattr(svc, "raiz_de_soportes", lambda: str(destino))
        indexador = svc.SoportesIndexer()
        assert str(indexador.raiz) == str(destino)

    def test_la_subida_del_zip_usa_el_mismo(self, monkeypatch, tmp_path):
        destino = tmp_path / "elegida"
        monkeypatch.setattr(svc, "raiz_de_soportes", lambda: str(destino))
        from app.api.routers import soportes as router

        assert str(router._local_root()) == str(destino)

    def test_caen_en_la_MISMA_carpeta(self, monkeypatch, tmp_path):
        """El caso real: el hospital configura su share y las dos cosas —el
        índice y la subida— tienen que apuntar ahí."""
        destino = tmp_path / "radicacion_2026"
        monkeypatch.setattr(svc, "_raiz_configurada", lambda: str(destino))
        monkeypatch.delenv("SOPORTES_ROOT", raising=False)
        monkeypatch.delenv("SOPORTES_LOCAL_ROOT", raising=False)

        from app.api.routers import soportes as router

        assert str(router._local_root()) == str(svc.SoportesIndexer().raiz)

    def test_el_router_ya_no_resuelve_por_su_cuenta(self):
        """Si alguien vuelve a poner la resolución a mano en el router, esta
        prueba se pone roja."""
        import inspect

        from app.api.routers import soportes as router

        fuente = inspect.getsource(router._local_root)
        assert 'os.getenv("SOPORTES_LOCAL_ROOT")' not in fuente, (
            "El router volvió a resolver la carpeta por su cuenta. Así fue como "
            "los .zip terminaron en una carpeta que el índice nunca recorre."
        )
        assert "raiz_de_soportes" in fuente
