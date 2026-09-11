"""El indexador no puede machacar el servidor de archivos del hospital.

11-09-2026, con la plataforma lenta en horas de trabajo. Yesid la ve
«Indexando…» a las 8:35 a.m., recorriendo `\\Prime\\radicacion_2026`:
101.991 facturas, 426.405 archivos, todo al otro lado de la red.

Dos defectos, los dos medidos antes de tocar nada:

1. **Se recorría el servidor entero en CADA arranque.** El motor del hospital
   se autodespliega —baja la rama cada 5 minutos y se reinicia si hay commit
   nuevo—, así que hay reinicios a cualquier hora del día laboral. El
   recorrido de las 2 AM ya deja el índice al día; repetirlo porque hubo un
   despliegue no agrega nada y se lleva minutos de red.

2. **Se le pedía al servidor seis veces más de lo necesario.** Por cada
   carpeta se listaba tres veces (una en el recorrido, otra para contar, otra
   para leer) más un `stat`; y de cada archivo se volvía a preguntar tamaño y
   fecha uno por uno. Medido sobre un árbol igual al del hospital:
   **23.712 viajes al servidor donde alcanzaban 3.904**.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.services.soportes_autodiscovery_service import SoportesIndexer


def _arbol(raiz: Path, facturas: int = 40, por_factura: int = 4) -> None:
    """La estructura real: {MES} / {EPS} / {radicador} / ENV-xxx / HUS{n}/."""
    for i in range(facturas):
        d = (
            raiz
            / "9. SEPTIEMBRE 2026 - SOPORTES RADICACION"
            / "NUEVA EPS"
            / "YESID PEREZ"
            / f"ENV-{i % 7:03d}"
            / f"HUS{400000 + i:010d}"
        )
        d.mkdir(parents=True, exist_ok=True)
        for tipo in ("FEV", "HEV", "RIPS", "CRC")[:por_factura]:
            (d / f"{tipo}_900006037_HUS{400000 + i:010d}.pdf").write_bytes(b"x" * 100)


def _indexador(raiz: Path) -> SoportesIndexer:
    ix = SoportesIndexer(raiz=str(raiz))
    # Un indexador limpio: sin lo que hubiera quedado en disco de otra corrida.
    ix._indice = {}
    ix._firmas = {}
    ix._construido_en = 0.0
    ix._cargado_de_disco = False
    ix._guardar_en_disco = lambda: None  # type: ignore[method-assign]
    return ix


class _ContadorDeViajes:
    """Cuenta cada ida y vuelta al servidor: listar carpetas y preguntar por
    archivos. Es lo único caro cuando el servidor está al otro lado de la red."""

    def __enter__(self):
        self.n = 0
        self._scandir, self._stat, self._pstat = os.scandir, os.stat, Path.stat

        def scandir(p, *a, **k):
            self.n += 1
            return self._scandir(p, *a, **k)

        def stat(p, *a, **k):
            self.n += 1
            return self._stat(p, *a, **k)

        def pstat(inst, *a, **k):
            self.n += 1
            return self._pstat(inst, *a, **k)

        os.scandir, os.stat, Path.stat = scandir, stat, pstat  # type: ignore[assignment]
        return self

    def __exit__(self, *a):
        os.scandir, os.stat, Path.stat = self._scandir, self._stat, self._pstat  # type: ignore[assignment]


class TestNoLePideDeMasAlServidor:
    def test_un_solo_listado_por_carpeta(self, tmp_path: Path):
        """Con 40 facturas hay ~50 carpetas. Más de 3 viajes por carpeta
        significa que se volvió a pedir lo que ya se tenía."""
        _arbol(tmp_path)
        ix = _indexador(tmp_path)
        with _ContadorDeViajes() as c:
            stats = ix.rebuild()
        carpetas = sum(1 for _ in tmp_path.rglob("*") if _.is_dir()) + 1
        assert stats["archivos_indexados"] == 160
        assert c.n <= carpetas * 2, (
            f"{c.n} viajes al servidor para {carpetas} carpetas. "
            "Se está pidiendo lo mismo varias veces."
        )

    def test_indexa_exactamente_lo_mismo_que_hay(self, tmp_path: Path):
        _arbol(tmp_path, facturas=12)
        ix = _indexador(tmp_path)
        stats = ix.rebuild()
        assert stats["archivos_indexados"] == 48
        assert stats["facturas_indexadas"] == 12
        assert len(ix.lookup("HUS0000400000", auto_rebuild=False)) == 4


class TestElEscaneoDiferencialSigueFuncionando:
    """Cambió cómo se reconoce una carpeta intacta. Tiene que seguir sirviendo."""

    def test_la_segunda_pasada_se_salta_todo(self, tmp_path: Path):
        _arbol(tmp_path, facturas=20)
        ix = _indexador(tmp_path)
        ix.rebuild()
        primeras = ix._archivos_escaneados
        ix.rebuild()
        assert primeras == 80
        assert ix._archivos_escaneados == 0, "releyó archivos de carpetas que no cambiaron"
        assert ix._carpetas_saltadas > 0
        assert ix.stats()["archivos_indexados"] == 80, "el índice no puede encogerse"

    def test_un_archivo_nuevo_se_ve(self, tmp_path: Path):
        _arbol(tmp_path, facturas=5)
        ix = _indexador(tmp_path)
        ix.rebuild()
        carpeta = next(tmp_path.rglob("HUS0000400003"))
        (carpeta / "OPF_900006037_HUS0000400003.pdf").write_bytes(b"y" * 50)
        ix.rebuild()
        assert ix.stats()["archivos_indexados"] == 21
        assert len(ix.lookup("400003", auto_rebuild=False)) == 5

    def test_una_factura_nueva_entera_se_ve(self, tmp_path: Path):
        _arbol(tmp_path, facturas=5)
        ix = _indexador(tmp_path)
        ix.rebuild()
        nueva = (
            tmp_path
            / "9. SEPTIEMBRE 2026 - SOPORTES RADICACION"
            / "NUEVA EPS"
            / "YESID PEREZ"
            / "ENV-000"
            / "HUS0000499999"
        )
        nueva.mkdir(parents=True)
        (nueva / "FEV_900006037_HUS0000499999.pdf").write_bytes(b"z" * 10)
        ix.rebuild()
        assert len(ix.lookup("499999", auto_rebuild=False)) == 1

    def test_un_archivo_borrado_se_ve(self, tmp_path: Path):
        _arbol(tmp_path, facturas=5)
        ix = _indexador(tmp_path)
        ix.rebuild()
        objetivo = next(tmp_path.rglob("CRC_900006037_HUS0000400002.pdf"))
        objetivo.unlink()
        ix.rebuild()
        assert len(ix.lookup("400002", auto_rebuild=False)) == 3

    def test_el_tamano_y_la_fecha_salen_bien(self, tmp_path: Path):
        """Se leen del listado de la carpeta, no preguntando archivo por
        archivo. Tienen que dar lo mismo."""
        _arbol(tmp_path, facturas=2)
        ix = _indexador(tmp_path)
        ix.rebuild()
        for fila in ix.lookup("400000", auto_rebuild=False):
            real = Path(fila["ruta"])
            assert fila["tamano_kb"] == max(1, real.stat().st_size // 1024)
            assert abs(fila["fecha_mod"] - real.stat().st_mtime) < 1.0


class TestElArranqueNoRecorrePorGusto:
    """El motor se reinicia varias veces al día por el autodespliegue."""

    def test_con_el_indice_fresco_no_se_recorre(self, tmp_path: Path, monkeypatch):
        import asyncio

        from app.services import soportes_reindex_scheduler as sch

        _arbol(tmp_path, facturas=3)
        ix = _indexador(tmp_path)
        ix.rebuild()  # como el recorrido de las 2 AM
        llamadas = {"n": 0}
        rebuild_real = ix.rebuild

        def contar():
            llamadas["n"] += 1
            return rebuild_real()

        ix.rebuild = contar  # type: ignore[method-assign]
        monkeypatch.setattr(sch, "get_indexer", lambda: ix, raising=False)
        monkeypatch.setattr("app.services.soportes_autodiscovery_service.get_indexer", lambda: ix)
        asyncio.run(sch._ejecutar_safe(solo_si_hace_falta=True))
        assert llamadas["n"] == 0, "recorrió el servidor por un reinicio, con el índice al día"

    def test_con_el_indice_viejo_si_se_recorre(self, tmp_path: Path, monkeypatch):
        """Si el motor estuvo apagado a las 2 AM, hay que ponerse al día."""
        import asyncio
        import time

        from app.services import soportes_reindex_scheduler as sch

        _arbol(tmp_path, facturas=3)
        ix = _indexador(tmp_path)
        ix.rebuild()
        ix._construido_en = time.time() - (sch._HORAS_PARA_NO_REPETIR + 1) * 3600
        llamadas = {"n": 0}
        rebuild_real = ix.rebuild

        def contar():
            llamadas["n"] += 1
            return rebuild_real()

        ix.rebuild = contar  # type: ignore[method-assign]
        monkeypatch.setattr("app.services.soportes_autodiscovery_service.get_indexer", lambda: ix)
        asyncio.run(sch._ejecutar_safe(solo_si_hace_falta=True))
        assert llamadas["n"] == 1

    def test_sin_indice_se_recorre(self, tmp_path: Path, monkeypatch):
        import asyncio

        from app.services import soportes_reindex_scheduler as sch

        _arbol(tmp_path, facturas=3)
        ix = _indexador(tmp_path)
        assert ix.construido_hace() is None
        llamadas = {"n": 0}
        rebuild_real = ix.rebuild

        def contar():
            llamadas["n"] += 1
            return rebuild_real()

        ix.rebuild = contar  # type: ignore[method-assign]
        monkeypatch.setattr("app.services.soportes_autodiscovery_service.get_indexer", lambda: ix)
        asyncio.run(sch._ejecutar_safe(solo_si_hace_falta=True))
        assert llamadas["n"] == 1

    def test_el_boton_reindexar_ahora_siempre_recorre(self, tmp_path: Path, monkeypatch):
        """Lo que el auditor pide a mano no se le discute."""
        import asyncio

        from app.services import soportes_reindex_scheduler as sch

        _arbol(tmp_path, facturas=3)
        ix = _indexador(tmp_path)
        ix.rebuild()
        llamadas = {"n": 0}
        rebuild_real = ix.rebuild

        def contar():
            llamadas["n"] += 1
            return rebuild_real()

        ix.rebuild = contar  # type: ignore[method-assign]
        monkeypatch.setattr("app.services.soportes_autodiscovery_service.get_indexer", lambda: ix)
        asyncio.run(sch._ejecutar_safe())  # sin solo_si_hace_falta
        assert llamadas["n"] == 1
