"""Los códigos de soporte que de verdad usa el servidor de radicación.

19-08-2026. Yesid respondió una glosa **SO0201 — «ausencia de soportes que
evidencian la realización de la CONSULTA DE URGENCIAS»** sobre la factura
HUS468334, y la relación de soportes del dictamen salió así:

    4  EPI_900006037_HUS468334.pdf   Res. 3047/2008 Anexo 5
    5  HAM_900006037_HUS468334.pdf   Res. 3047/2008 Anexo 5
    6  HAU_900006037_HUS468334.pdf   Res. 3047/2008 Anexo 5
    7  HUS468334.json                Res. 3047/2008 Anexo 5
    8  HUS468334.xml                 Res. 3047/2008 Anexo 5
    9  HUS468334_CUV.json            Res. 3047/2008 Anexo 5

**Seis de doce soportes sin clasificar**, listados con su nombre de archivo
crudo en un anexo que se radica ante la EPS, y todos con la misma norma
—incorrecta para el RIPS, el XML y el CUV—.

Lo grave no es lo feo. Es que:

  · **HAU es la hoja de atención de urgencias** — el documento que prueba
    exactamente lo que la EPS decía que faltaba;
  · **EPI es la epicrisis** y **HAM la hoja de administración de
    medicamentos**;
  · y como el Auditor Forense escoge qué leer POR TIPO, los tres competían de
    últimas contra cualquier archivo suelto.
"""

from __future__ import annotations

import re

import pytest

from app.services.auditor_forense import escoger_soportes_para_forense
from app.services.glosa_service import GlosaService
from app.services.soportes_autodiscovery_service import _clasificar_archivo

# Los 12 archivos reales de HUS468334, con los nombres exactos del servidor.
EXPEDIENTE = [
    "FEV_900006037_HUS468334.pdf",
    "HEV_900006037_HUS468334.pdf",
    "CRC_900006037_HUS468334.pdf",
    "EPI_900006037_HUS468334.pdf",
    "HAM_900006037_HUS468334.pdf",
    "HAU_900006037_HUS468334.pdf",
    "HUS468334.json",
    "HUS468334.xml",
    "HUS468334_CUV.json",
    "OPF_900006037_HUS468334.pdf",
    "PDE_900006037_HUS468334.pdf",
    "PDX_900006037_HUS468334.pdf",
]


class TestElIndexadorLosReconoce:
    @pytest.mark.parametrize(
        "archivo,tipo",
        [
            ("EPI_900006037_HUS468334.pdf", "epicrisis"),
            ("HAM_900006037_HUS468334.pdf", "hoja_administracion_medicamentos"),
            ("HAU_900006037_HUS468334.pdf", "hoja_atencion_urgencias"),
        ],
    )
    def test_los_codigos_clinicos_del_anexo_tecnico(self, archivo, tipo):
        assert _clasificar_archivo(archivo)[1] == tipo

    @pytest.mark.parametrize(
        "archivo,tipo",
        [
            ("HUS468334.json", "rips"),
            ("HUS468334.xml", "xml_cufe"),
            ("HUS468334_CUV.json", "cuv"),
        ],
    )
    def test_los_que_solo_llevan_el_numero_de_factura(self, archivo, tipo):
        """El servidor los nombra sin prefijo: se reconocen por extensión."""
        assert _clasificar_archivo(archivo)[1] == tipo

    def test_ningun_soporte_del_expediente_queda_sin_clasificar(self):
        sin = [n for n in EXPEDIENTE if not _clasificar_archivo(n)]
        assert not sin, f"quedan sin reconocer: {sin}"

    def test_no_se_rompe_lo_que_ya_funcionaba(self):
        for archivo, tipo in (
            ("FEV_900006037_HUS468334.pdf", "factura_electronica"),
            ("HEV_900006037_HUS468334.pdf", "historia_clinica"),
            ("CRC_900006037_HUS468334.pdf", "comprobante_recibido_cobro"),
            ("FURIPS_1_900006037.txt", "furips"),
        ):
            assert _clasificar_archivo(archivo)[1] == tipo, archivo


@pytest.fixture
def expediente(tmp_path, monkeypatch):
    from app.services import soportes_autodiscovery_service as svc

    soportes = []
    for nombre in EXPEDIENTE:
        ruta = tmp_path / nombre
        ruta.write_bytes(b"%PDF-1.4\n" + b"0" * 2048 if nombre.endswith(".pdf") else b"x" * 2048)
        clase = _clasificar_archivo(nombre)
        soportes.append(
            {
                "nombre_archivo": nombre,
                "tipo": clase[1] if clase else "otro",
                "ruta": str(ruta),
            }
        )

    class _Idx:
        def lookup(self, factura, auto_rebuild=True):
            return soportes if "468334" in (factura or "") else []

    monkeypatch.setattr(svc, "get_indexer", lambda: _Idx())
    return soportes


class TestLaRelacionQueSeRadica:
    def _docs(self, expediente):
        filas = GlosaService.__new__(GlosaService)._soportes_reales("HUS468334")[0]
        return [re.search(r"<td [^>]*>([^<]+)<div", f).group(1) for f in filas]

    def test_ningun_renglon_muestra_el_nombre_del_archivo_como_documento(self, expediente):
        """En un anexo que se radica, «HUS468334.json» no es un documento."""
        for doc in self._docs(expediente):
            assert not doc.endswith((".pdf", ".json", ".xml", ".txt")), doc

    def test_la_hoja_de_urgencias_sale_con_su_nombre(self, expediente):
        """Era el documento que la EPS decía que faltaba."""
        assert "Hoja de atención de urgencias" in self._docs(expediente)

    def test_el_rips_no_se_cita_con_la_norma_de_los_soportes_clinicos(self, expediente):
        filas = GlosaService.__new__(GlosaService)._soportes_reales("HUS468334")[0]
        rips = [f for f in filas if "RIPS radicados" in f][0]
        assert "Res. 2275/2023" in rips
        assert "3047" not in rips


class TestQueAbreElAuditorForense:
    def test_abre_la_hoja_de_atencion_de_urgencias(self, expediente):
        """La glosa era por «falta soporte de la consulta de urgencias»."""
        elegidos = [s["nombre_archivo"] for s in escoger_soportes_para_forense(expediente)[0]]
        assert "HAU_900006037_HUS468334.pdf" in elegidos

    def test_abre_la_epicrisis_y_la_hoja_de_medicamentos(self, expediente):
        elegidos = [s["nombre_archivo"] for s in escoger_soportes_para_forense(expediente)[0]]
        assert "EPI_900006037_HUS468334.pdf" in elegidos
        assert "HAM_900006037_HUS468334.pdf" in elegidos

    def test_el_cuv_no_se_manda_como_pdf(self, expediente):
        omitidos = {
            s["nombre_archivo"]: s["motivo"] for s in escoger_soportes_para_forense(expediente)[1]
        }
        assert omitidos["HUS468334_CUV.json"] == "no es un PDF"
