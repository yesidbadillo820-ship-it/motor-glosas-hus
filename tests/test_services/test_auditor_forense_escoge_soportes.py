"""El Auditor Forense abre los documentos donde está la respuesta.

19-08-2026. La consulta solo admite 5 documentos, así que el orden en que se
escogen decide qué lee la IA. Se estaban tomando los 5 primeros del orden con
que la pantalla de Soportes LISTA los archivos, y ese orden es otro: allá
manda la factura, acá tiene que mandar la historia clínica.

Con los 12 soportes reales de la factura HUS468334 el resultado era:

  se mandaban  ->  FEV (factura), HEV (historia), RIPS **.json**,
                   CRC (comprobante de recibido de cobro), RESULTADOSMSPS
  quedaban     ->  EPICRISIS, HOJA DE ADMINISTRACION DE MEDICAMENTOS,
  sin abrir        OPF (otros procedimientos), PDE, PDX

Dos daños:

  · uno de los cinco cupos se gastaba en un `.json`, que no es un PDF y la IA
    no puede abrir;
  · los documentos con la evidencia clínica no se abrían nunca. A la pregunta
    «¿qué medicamentos se le administraron al paciente?» la IA contestaba «no
    encontré evidencia» sin haber mirado la HOJA DE ADMINISTRACIÓN DE
    MEDICAMENTOS. Con esa respuesta el gestor acepta una glosa que debía
    objetar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.auditor_forense import escoger_soportes_para_forense

# Los 12 soportes reales de HUS468334, tal como los devuelve el indexador.
REALES = [
    ("FEV_900006037_HUS468334.pdf", "factura_electronica"),
    ("HEV_900006037_HUS468334.pdf", "historia_clinica"),
    ("CRC_900006037_HUS468334.pdf", "comprobante_recibido_cobro"),
    ("OPF_900006037_HUS468334.pdf", "otros_procedimientos"),
    ("PDE_900006037_HUS468334.pdf", "pde"),
    ("PDX_900006037_HUS468334.pdf", "pdx"),
    ("RESULTADOSMSPS_900006037_HUS468334.pdf", "resultados_msps"),
    ("EPICRISIS HUS468334.pdf", "otro"),
    ("HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf", "otro"),
    ("RIPS_900006037_HUS468334.json", "rips"),
    ("ad0900060370000468334.xml", "xml_cufe"),
    ("CUV_900006037_HUS468334.txt", "otro"),
]


@pytest.fixture
def expediente(tmp_path: Path) -> list[dict]:
    """Escribe los 12 archivos en disco: los PDF con firma `%PDF` de verdad."""
    soportes = []
    for nombre, tipo in REALES:
        ruta = tmp_path / nombre
        if nombre.lower().endswith(".pdf"):
            ruta.write_bytes(b"%PDF-1.4\n" + b"0" * 2048)
        else:
            ruta.write_bytes(b"{}" if nombre.endswith(".json") else b"<xml/>")
        soportes.append({"nombre_archivo": nombre, "tipo": tipo, "ruta": str(ruta)})
    return soportes


def _nombres(lista) -> list[str]:
    return [s["nombre_archivo"] for s in lista]


class TestLoQueSeLeManda:
    def test_nunca_se_manda_algo_que_no_sea_pdf(self, expediente):
        elegidos, _ = escoger_soportes_para_forense(expediente)
        assert all(s["nombre_archivo"].lower().endswith(".pdf") for s in elegidos), _nombres(
            elegidos
        )

    def test_el_rips_json_y_el_xml_quedan_afuera(self, expediente):
        elegidos, omitidos = escoger_soportes_para_forense(expediente)
        assert "RIPS_900006037_HUS468334.json" not in _nombres(elegidos)
        assert "ad0900060370000468334.xml" not in _nombres(elegidos)
        # Y se dice por qué, no desaparecen en silencio.
        motivos = {s["nombre_archivo"]: s["motivo"] for s in omitidos}
        assert motivos["RIPS_900006037_HUS468334.json"] == "no es un PDF"

    def test_la_historia_clinica_va_primero(self, expediente):
        elegidos, _ = escoger_soportes_para_forense(expediente)
        assert elegidos[0]["nombre_archivo"] == "HEV_900006037_HUS468334.pdf"

    def test_se_abren_los_anexos_clinicos(self, expediente):
        """Epicrisis y hoja de medicamentos: ahí vive la respuesta."""
        elegidos = _nombres(escoger_soportes_para_forense(expediente)[0])
        assert "EPICRISIS HUS468334.pdf" in elegidos
        assert "HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf" in elegidos

    def test_el_comprobante_de_recibido_no_desplaza_a_lo_clinico(self, expediente):
        """El CRC solo dice que se radicó, no qué se le hizo al paciente."""
        elegidos = _nombres(escoger_soportes_para_forense(expediente)[0])
        assert "CRC_900006037_HUS468334.pdf" not in elegidos

    def test_se_respeta_el_tope_de_cinco(self, expediente):
        elegidos, _ = escoger_soportes_para_forense(expediente)
        assert len(elegidos) == 5


class TestNoSeOcultaLoQueQuedoSinLeer:
    def test_todo_soporte_o_se_lee_o_se_reporta(self, expediente):
        elegidos, omitidos = escoger_soportes_para_forense(expediente)
        assert len(elegidos) + len(omitidos) == len(expediente)

    def test_los_omitidos_por_cupo_dicen_que_fue_por_cupo(self, expediente):
        _, omitidos = escoger_soportes_para_forense(expediente)
        por_cupo = [s for s in omitidos if "caben" in s["motivo"]]
        assert por_cupo, "no se avisa que hubo documentos cortados por el tope"

    def test_cada_omitido_trae_su_motivo(self, expediente):
        _, omitidos = escoger_soportes_para_forense(expediente)
        assert all((s.get("motivo") or "").strip() for s in omitidos)


class TestArchivosDanados:
    def test_un_pdf_que_no_es_pdf_no_se_manda(self, tmp_path):
        """Un archivo renombrado a .pdf rompe la consulta entera si se manda."""
        falso = tmp_path / "HEV_900006037_HUS1.pdf"
        falso.write_bytes(b"esto no es un PDF, es texto plano suelto")
        elegidos, omitidos = escoger_soportes_para_forense(
            [{"nombre_archivo": falso.name, "tipo": "historia_clinica", "ruta": str(falso)}]
        )
        assert elegidos == []
        assert "no es un PDF válido" in omitidos[0]["motivo"]

    def test_un_archivo_que_ya_no_esta_en_el_servidor_se_reporta(self, tmp_path):
        fantasma = str(tmp_path / "no_existe" / "HEV_900006037_HUS1.pdf")
        elegidos, omitidos = escoger_soportes_para_forense(
            [
                {
                    "nombre_archivo": "HEV_900006037_HUS1.pdf",
                    "tipo": "historia_clinica",
                    "ruta": fantasma,
                }
            ]
        )
        assert elegidos == []
        assert omitidos[0]["motivo"]

    def test_una_factura_sin_ningun_pdf_no_revienta(self, tmp_path):
        j = tmp_path / "RIPS_900006037_HUS1.json"
        j.write_bytes(b"{}")
        elegidos, omitidos = escoger_soportes_para_forense(
            [{"nombre_archivo": j.name, "tipo": "rips", "ruta": str(j)}]
        )
        assert elegidos == []
        assert len(omitidos) == 1

    def test_sin_soportes_devuelve_dos_listas_vacias(self):
        assert escoger_soportes_para_forense([]) == ([], [])


# ─── La ruta completa ────────────────────────────────────────────────────────


class TestLaRutaDevuelveLoQueLaPantallaNecesita:
    """No basta con escoger bien: la respuesta tiene que decirlo."""

    def _app(self, monkeypatch, soportes, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.deps import get_auditor_o_superior
        from app.api.routers.auditor_forense import router
        from app.models.db import UsuarioRecord
        from app.services import auditor_forense as af
        from app.services import soportes_autodiscovery_service as svc

        class _Indexer:
            def lookup(self, factura, auto_rebuild=True):
                return soportes

        monkeypatch.setattr(svc, "get_indexer", lambda: _Indexer())

        async def _falso_auditar(**kw):
            return {"html": "<p>respuesta</p>", "modelo": "prueba"}

        monkeypatch.setattr(af, "auditar_forense", _falso_auditar)

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_auditor_o_superior] = lambda: UsuarioRecord(
            id=1, email="a@b.c", rol="AUDITOR", activo=1
        )
        return TestClient(app)

    def test_la_respuesta_trae_los_omitidos_con_su_motivo(self, monkeypatch, expediente, tmp_path):
        c = self._app(monkeypatch, expediente, tmp_path)
        r = c.post(
            "/auditor-forense/",
            json={"factura": "HUS468334", "pregunta": "¿qué medicamentos se administraron?"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["soportes_usados"]) == 5
        assert d["soportes_indexados"] == 12
        assert len(d["soportes_omitidos"]) == 7
        assert all(o["motivo"] for o in d["soportes_omitidos"])

    def test_se_abre_la_hoja_de_medicamentos(self, monkeypatch, expediente, tmp_path):
        """La pregunta del gestor se responde con ese documento, no sin él."""
        c = self._app(monkeypatch, expediente, tmp_path)
        d = c.post(
            "/auditor-forense/",
            json={"factura": "HUS468334", "pregunta": "¿qué medicamentos se administraron?"},
        ).json()
        assert "HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf" in d["soportes_usados"]

    def test_el_rips_json_nunca_sale_como_leido(self, monkeypatch, expediente, tmp_path):
        c = self._app(monkeypatch, expediente, tmp_path)
        d = c.post(
            "/auditor-forense/", json={"factura": "HUS468334", "pregunta": "audita la factura"}
        ).json()
        assert not [n for n in d["soportes_usados"] if n.lower().endswith(".json")]

    def test_una_factura_solo_con_json_avisa_claro_y_no_da_error_500(self, monkeypatch, tmp_path):
        j = tmp_path / "RIPS_900006037_HUS1.json"
        j.write_bytes(b"{}" + b"0" * 2000)
        c = self._app(
            monkeypatch,
            [{"nombre_archivo": j.name, "tipo": "rips", "ruta": str(j)}],
            tmp_path,
        )
        r = c.post("/auditor-forense/", json={"factura": "HUS1", "pregunta": "audita la factura"})
        assert r.status_code == 422, r.status_code
        assert "ninguno es un PDF" in r.json()["detail"]
