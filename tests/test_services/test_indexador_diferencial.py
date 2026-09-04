"""El índice de soportes sobrevive al reinicio y no relee lo que no cambió.

QUÉ PASÓ (04-09-2026). El índice vivía SOLO en memoria. Cada reinicio de
uvicorn —y hay varios al día por el autodespliegue— lo borraba, y el motor
volvía a recorrer 473.581 archivos por la red del hospital: horas. Peor
todavía: el `rebuild` empezaba haciendo `self._indice = {}`, así que durante
todo ese rato el buscador contestaba VACÍO a todo el mundo. El motor quedaba
ciego justo mientras trabajaba, y eso fue lo que motivó el candado HTTP 423
que terminó paralizando la operación entera.

LO QUE ESTAS PRUEBAS CUIDAN:

1. El índice se guarda y se recupera: al arrancar ya hay con qué responder.
2. Una carpeta que no cambió NO se vuelve a leer.
3. Una carpeta que SÍ cambió se relee.
4. Mientras se reconstruye, el índice viejo sigue respondiendo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.soportes_autodiscovery_service import SoportesIndexer


@pytest.fixture
def raiz(tmp_path):
    """Un árbol parecido al del servidor de radicación."""
    env = tmp_path / "2026" / "ENERO" / "COOSALUD" / "ENV-1001-OK"
    env.mkdir(parents=True)
    (env / "HUS495050_FEV.pdf").write_text("factura", encoding="utf-8")
    (env / "HUS495050_HEV.pdf").write_text("historia", encoding="utf-8")
    otra = tmp_path / "2026" / "ENERO" / "COOSALUD" / "ENV-1002-OK"
    otra.mkdir(parents=True)
    (otra / "HUS495051_FEV.pdf").write_text("factura", encoding="utf-8")
    return tmp_path


@pytest.fixture
def cache_aislado(tmp_path, monkeypatch):
    """El caché de cada prueba, aparte del de verdad."""
    # Fuera del árbol que se indexa: si no, el propio caché se cuenta como
    # un archivo escaneado y falsea la medición.
    destino = tmp_path.parent / f"cache_{tmp_path.name}" / "soportes_indice.json"
    monkeypatch.setattr(SoportesIndexer, "_ruta_cache", lambda self: destino)
    return destino


def _indexador(raiz: Path) -> SoportesIndexer:
    return SoportesIndexer(raiz=str(raiz), ttl_segundos=3600)


class TestElIndiceSobreviveAlReinicio:
    def test_se_guarda_al_terminar(self, raiz, cache_aislado):
        idx = _indexador(raiz)
        idx.rebuild()
        assert cache_aislado.is_file(), "el índice no quedó guardado en disco"
        datos = json.loads(cache_aislado.read_text(encoding="utf-8"))
        assert datos["raiz"] == str(raiz)
        assert "495050" in datos["indice"]

    def test_al_arrancar_de_nuevo_NO_empieza_de_cero(self, raiz, cache_aislado):
        _indexador(raiz).rebuild()

        # Esto es el reinicio de uvicorn: una instancia nueva, memoria vacía.
        reiniciado = _indexador(raiz)
        assert reiniciado._cargado_de_disco is True
        assert reiniciado.lookup("HUS495050", auto_rebuild=False), (
            "tras el reinicio el buscador quedó vacío: vuelve el problema de las horas"
        )

    def test_si_cambia_la_carpeta_raiz_el_cache_viejo_se_ignora(
        self, raiz, cache_aislado, tmp_path
    ):
        _indexador(raiz).rebuild()
        otra_raiz = tmp_path / "otro_servidor"
        otra_raiz.mkdir()
        idx = _indexador(otra_raiz)
        assert idx._cargado_de_disco is False
        assert idx._indice == {}

    def test_un_cache_corrupto_no_tumba_el_motor(self, raiz, cache_aislado):
        cache_aislado.parent.mkdir(parents=True, exist_ok=True)
        cache_aislado.write_text("{esto no es json", encoding="utf-8")
        idx = _indexador(raiz)  # no debe reventar
        assert idx._cargado_de_disco is False
        idx.rebuild()
        assert idx.lookup("HUS495050", auto_rebuild=False)


class TestEscaneoDiferencial:
    def test_lo_que_no_cambio_no_se_vuelve_a_leer(self, raiz, cache_aislado):
        idx = _indexador(raiz)
        idx.rebuild()
        leidos_primera = idx.stats()["archivos_escaneados"]
        assert leidos_primera > 0

        idx.rebuild()  # nada cambió en el disco
        assert idx.stats()["archivos_escaneados"] == 0, (
            "releyó archivos de carpetas intactas: eso es lo que costaba horas"
        )
        assert idx._carpetas_saltadas > 0

    def test_el_indice_queda_igual_aunque_se_salten_carpetas(self, raiz, cache_aislado):
        idx = _indexador(raiz)
        idx.rebuild()
        antes = {f: len(v) for f, v in idx._indice.items()}
        idx.rebuild()
        despues = {f: len(v) for f, v in idx._indice.items()}
        assert antes == despues, "saltarse carpetas perdió soportes"

    def test_una_carpeta_que_cambio_SI_se_relee(self, raiz, cache_aislado):
        idx = _indexador(raiz)
        idx.rebuild()
        env = raiz / "2026" / "ENERO" / "COOSALUD" / "ENV-1001-OK"
        (env / "HUS495050_RIPS.json").write_text("{}", encoding="utf-8")

        idx.rebuild()
        assert idx.stats()["archivos_escaneados"] > 0, "no se enteró del archivo nuevo"
        nombres = {s["nombre_archivo"] for s in idx.lookup("HUS495050", auto_rebuild=False)}
        assert "HUS495050_RIPS.json" in nombres

    def test_una_factura_nueva_aparece(self, raiz, cache_aislado):
        idx = _indexador(raiz)
        idx.rebuild()
        nueva = raiz / "2026" / "FEBRERO" / "COOSALUD" / "ENV-2001-OK"
        nueva.mkdir(parents=True)
        (nueva / "HUS777777_FEV.pdf").write_text("factura", encoding="utf-8")

        idx.rebuild()
        assert idx.lookup("HUS777777", auto_rebuild=False), "no vio la carpeta nueva"


class TestNoSeQuedaCiegoMientrasTrabaja:
    def test_el_indice_viejo_responde_durante_la_reconstruccion(self, raiz, cache_aislado):
        """El defecto que originó todo: `self._indice = {}` al empezar."""
        import inspect

        # Solo el CÓDIGO: los comentarios de rebuild citan la línea vieja para
        # explicar por qué se quitó, y eso no es el defecto.
        codigo = "\n".join(
            ln
            for ln in inspect.getsource(SoportesIndexer.rebuild).splitlines()
            if not ln.strip().startswith("#")
        )
        assert "self._indice = {}" not in codigo, (
            "el rebuild vuelve a vaciar el índice: el motor queda ciego mientras escanea"
        )
        # Y el cambiazo ocurre al final, con el índice ya armado.
        assert "self._indice = nuevo_indice" in codigo

    def test_si_la_raiz_desaparece_no_se_pierde_lo_que_ya_habia(self, raiz, cache_aislado):
        idx = _indexador(raiz)
        idx.rebuild()
        tenia = len(idx._indice)
        assert tenia > 0

        idx.raiz = raiz / "carpeta_que_no_existe"
        idx.rebuild()
        assert len(idx._indice) == tenia, (
            "una raíz caída (red del hospital abajo) borró el índice bueno"
        )
