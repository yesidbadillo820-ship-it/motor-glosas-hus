"""«Analizar glosa» lee los soportes con el auditor forense — 19-08-2026.

Yesid: «me gustaría que este auditor forense estuviera anclado en el apartado
de analizar glosa, porque es exactamente lo que se le pide que haga», y que la
respuesta de la glosa salga de esa lectura.

Estaba a medias. El pre-pass forense existía desde julio, pero:

  · venía APAGADO (`GLOSA_AUDITOR_FORENSE_PREPASS` con valor por defecto «0»);
  · y aun prendido solo miraba los PDF que el auditor subiera A MANO. Los
    soportes que el indexador ya tiene del servidor de radicación se leían
    como texto plano y nunca llegaban al forense, que es el que sabe citar
    folios.

O sea: para una factura ya radicada, con sus 12 soportes en el servidor, el
dictamen se armaba sin que nadie hubiera leído la historia clínica con lupa.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routers.analizar import _pdfs_del_servidor_para_forense


@pytest.fixture
def expediente(tmp_path: Path):
    """Los soportes de HUS468334 en disco, como los ve el indexador."""
    archivos = [
        ("HEV_900006037_HUS468334.pdf", "historia_clinica"),
        ("FEV_900006037_HUS468334.pdf", "factura_electronica"),
        ("EPICRISIS HUS468334.pdf", "otro"),
        ("HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf", "otro"),
        ("OPF_900006037_HUS468334.pdf", "otros_procedimientos"),
        ("CRC_900006037_HUS468334.pdf", "comprobante_recibido_cobro"),
        ("RIPS_900006037_HUS468334.json", "rips"),
    ]
    salida = []
    for nombre, tipo in archivos:
        ruta = tmp_path / nombre
        ruta.write_bytes(
            b"%PDF-1.4\n" + b"0" * 2048 if nombre.endswith(".pdf") else b"{}" + b"0" * 2048
        )
        salida.append({"nombre_archivo": nombre, "tipo": tipo, "ruta": str(ruta)})
    return salida


def _con_indice(monkeypatch, soportes):
    from app.services import soportes_autodiscovery_service as svc

    class _Indexer:
        def lookup(self, factura, auto_rebuild=True):
            return soportes

    monkeypatch.setattr(svc, "get_indexer", lambda: _Indexer())


class TestLeeLosSoportesDelServidor:
    async def test_saca_los_pdf_de_la_factura_sin_que_nadie_los_adjunte(
        self, monkeypatch, expediente
    ):
        _con_indice(monkeypatch, expediente)
        pdfs = await _pdfs_del_servidor_para_forense("HUS468334", "req-1")
        assert pdfs, "no se leyó ningún soporte del servidor"
        assert all(datos.startswith(b"%PDF") for _n, datos in pdfs)

    async def test_abre_la_historia_clinica_y_los_anexos(self, monkeypatch, expediente):
        _con_indice(monkeypatch, expediente)
        nombres = [n for n, _d in await _pdfs_del_servidor_para_forense("HUS468334", "req-1")]
        assert "HEV_900006037_HUS468334.pdf" in nombres
        assert "HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf" in nombres

    async def test_nunca_manda_el_rips_json(self, monkeypatch, expediente):
        _con_indice(monkeypatch, expediente)
        nombres = [n for n, _d in await _pdfs_del_servidor_para_forense("HUS468334", "req-1")]
        assert not [n for n in nombres if n.lower().endswith(".json")]


class TestNoRevientaNunca:
    """Si el forense falla, la glosa se responde igual — sin folios, pero se
    responde. Nunca puede tumbar el dictamen."""

    async def test_sin_numero_de_factura(self):
        assert await _pdfs_del_servidor_para_forense(None, "req-1") == []
        assert await _pdfs_del_servidor_para_forense("", "req-1") == []

    async def test_factura_sin_soportes(self, monkeypatch):
        _con_indice(monkeypatch, [])
        assert await _pdfs_del_servidor_para_forense("HUS999999", "req-1") == []

    async def test_indexador_caido(self, monkeypatch):
        from app.services import soportes_autodiscovery_service as svc

        def _explota():
            raise RuntimeError("el share no responde")

        monkeypatch.setattr(svc, "get_indexer", _explota)
        assert await _pdfs_del_servidor_para_forense("HUS468334", "req-1") == []

    async def test_archivo_borrado_del_servidor(self, monkeypatch, tmp_path):
        _con_indice(
            monkeypatch,
            [
                {
                    "nombre_archivo": "HEV_1.pdf",
                    "tipo": "historia_clinica",
                    "ruta": str(tmp_path / "no_existe" / "HEV_1.pdf"),
                }
            ],
        )
        assert await _pdfs_del_servidor_para_forense("HUS1", "req-1") == []


class TestElPrePassQuedoPrendido:
    def test_viene_prendido_por_defecto(self):
        fuente = (
            Path(__file__).resolve().parents[2] / "app" / "api" / "routers" / "analizar.py"
        ).read_text(encoding="utf-8")
        assert 'os.getenv("GLOSA_AUDITOR_FORENSE_PREPASS", "1")' in fuente, (
            "el pre-pass forense volvió a quedar apagado por defecto"
        )

    def test_si_no_hay_adjuntos_los_busca_en_el_servidor(self):
        fuente = (
            Path(__file__).resolve().parents[2] / "app" / "api" / "routers" / "analizar.py"
        ).read_text(encoding="utf-8")
        assert "_pdfs_del_servidor_para_forense(numero_factura, req_id)" in fuente


class TestElAuditorSabeQueEstaPasando:
    """Leer los folios tarda 1-2 minutos. Una pantalla quieta se lee como
    «se colgó», y el auditor recarga y pierde el trabajo."""

    def _fuente(self) -> str:
        return (
            Path(__file__).resolve().parents[2] / "app" / "api" / "routers" / "analizar.py"
        ).read_text(encoding="utf-8")

    def test_avisa_antes_de_empezar_a_leer_no_solo_al_terminar(self):
        fuente = self._fuente()
        assert '"auditor_forense_inicio"' in fuente
        # El aviso de inicio va ANTES de la llamada, no después.
        assert fuente.index('"auditor_forense_inicio"') < fuente.index(
            "_ev = await evidencia_para_dictamen("
        )

    def test_la_pantalla_sabe_traducir_ese_aviso(self):
        index = (Path(__file__).resolve().parents[2] / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "auditor_forense_inicio: function" in index, (
            "el motor manda un aviso que la pantalla no sabe mostrar"
        )
