"""La búsqueda de soportes nunca espera al reindexado — 18-08-2026.

Yesid apuntó el motor al servidor real (\\\\Prime\\radicacion_2026), le dio
«Reindexar ahora» y, mientras corría, buscó una factura: la pantalla devolvió
**Error 524**. La causa: `rebuild()` pedía el candado bloqueando y recorría
miles de archivos por red durante minutos; cualquier búsqueda se quedaba
haciendo cola hasta que el proxy la cortaba.

Ahora:
  • si ya hay una reconstrucción en curso, otra NO se encola: se devuelve el
    estado y ya;
  • `lookup`/`buscar` responden con lo que haya en el índice en vez de esperar;
  • `stats()` dice si está construyendo, para que la pantalla lo muestre.
"""

from __future__ import annotations

import threading
import time

from app.services.soportes_autodiscovery_service import SoportesIndexer


def _paquete(tmp_path, factura="548170", eps="NUEVA EPS"):
    carpeta = (
        tmp_path
        / "8. AGOSTO 2026 - SOPORTES RADICACION"
        / eps
        / "SOFIA"
        / "ENV-232984-okdgh"
        / "SOPORTES"
        / f"HUS{factura}"
    )
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"FEV_900006037_HUS{factura}.pdf").write_bytes(b"%PDF-1.4")
    return tmp_path


class TestNoSeEncolanReconstrucciones:
    def test_un_segundo_rebuild_no_espera_al_primero(self, tmp_path):
        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        idx._lock.acquire()  # simula una reconstrucción en curso
        try:
            inicio = time.time()
            idx.rebuild()  # no debe quedarse esperando
            assert time.time() - inicio < 2.0
        finally:
            idx._lock.release()

    def test_la_busqueda_no_espera_al_reindexado(self, tmp_path):
        """El caso exacto del 524: buscar mientras reindexa."""
        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        idx._construyendo = True
        idx._lock.acquire()
        try:
            inicio = time.time()
            idx.lookup("HUS548170")  # con índice frío y build en curso
            idx.buscar("548170")
            assert time.time() - inicio < 2.0, "la búsqueda se quedó esperando"
        finally:
            idx._construyendo = False
            idx._lock.release()

    def test_el_estado_dice_si_esta_construyendo(self, tmp_path):
        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        assert idx.stats()["construyendo"] is False
        idx._construyendo = True
        assert idx.stats()["construyendo"] is True

    def test_el_candado_queda_libre_despues_de_reconstruir(self, tmp_path):
        """Si el finally no liberara, el motor quedaría trancado para siempre."""
        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        idx.rebuild()
        assert idx._lock.acquire(blocking=False), "el candado quedó tomado"
        idx._lock.release()
        assert idx.stats()["construyendo"] is False

    def test_una_raiz_que_no_existe_tampoco_deja_trancado(self, tmp_path):
        idx = SoportesIndexer(raiz=str(tmp_path / "no_existe"))
        idx.raiz = tmp_path / "tampoco_existe"
        idx.rebuild()
        assert idx._lock.acquire(blocking=False), "el candado quedó tomado tras el error"
        idx._lock.release()

    def test_reconstruir_de_verdad_sigue_funcionando(self, tmp_path):
        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        st = idx.rebuild()
        assert st["facturas_indexadas"] == 1
        assert idx.lookup("HUS548170")[0]["eps"] == "NUEVA EPS"

    def test_dos_hilos_a_la_vez_no_se_traban(self, tmp_path):
        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        errores = []

        def correr():
            try:
                idx.rebuild()
            except Exception as e:  # pragma: no cover
                errores.append(e)

        hilos = [threading.Thread(target=correr) for _ in range(3)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=20)
        assert not any(h.is_alive() for h in hilos), "un hilo quedó colgado"
        assert errores == []


class TestLaRespuestaAvisaQueSigueIndexando:
    """«No encontré nada» y «no he terminado de mirar» son cosas distintas.

    19-08-2026. Yesid buscó HUS548170 mientras el indexador iba por 11.367
    facturas y la pantalla contestó «Sin soportes», con causas que no incluían
    la verdadera: las carpetas se recorren por orden (FEBRERO, MARZO, …) y
    AGOSTO sale de últimas. El auditor podía creer que la factura no tenía
    soportes.
    """

    def test_el_estado_viaja_en_la_respuesta_de_la_ruta(self, tmp_path):
        from fastapi.testclient import TestClient

        from app.api.deps import get_usuario_actual
        from app.main import app
        from app.models.db import UsuarioRecord
        from app.services import soportes_autodiscovery_service as svc

        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        idx.rebuild()
        idx._construyendo = True  # simula indexación en curso
        usuario = UsuarioRecord(id=1, email="a@b.c", rol="SUPER_ADMIN", activo=1)
        app.dependency_overrides[get_usuario_actual] = lambda: usuario
        original = svc._indexer_singleton
        svc._indexer_singleton = idx
        try:
            with TestClient(app) as c:
                d = c.get("/soportes-auto/factura/HUS999999").json()
            assert d["total"] == 0
            assert d["construyendo"] is True
            assert d["facturas_indexadas"] >= 1
        finally:
            svc._indexer_singleton = original
            app.dependency_overrides.clear()

    def test_cuando_termina_ya_no_dice_que_esta_indexando(self, tmp_path):
        idx = SoportesIndexer(raiz=str(_paquete(tmp_path)))
        idx.rebuild()
        assert idx.stats()["construyendo"] is False
