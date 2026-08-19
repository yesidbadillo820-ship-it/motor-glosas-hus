"""El dictamen no dice haber aportado soportes que nadie miró — 19-08-2026.

Yesid probó «Analizar glosa» con la factura HUS468334 y una glosa **SO0201 —
falta de soporte**. En ese tipo de glosa la lista de soportes ES el argumento:
el hospital contesta «sí los mandamos» y la relaciona.

El dictamen contestó con esto, bajo el título «RELACIÓN DE SOPORTES APORTADOS»
y con su marco legal al lado:

    1  Historia clínica institucional      Res. 1995/1999
    2  RIPS radicados                      Res. 866/2021
    3  Factura electrónica No. HUS468334   Res. 2275/2023 (FEV)

Esa lista era una **plantilla fija escrita a mano en el código**, que salía por
el solo hecho de que el auditor hubiera escrito un número de factura. Nadie
miraba si esos documentos existían. Y la argumentación afirmaba además haber
aportado «DESCRIPCIÓN QUIRÚRGICA Y REGISTRO ANESTÉSICO» — para una radiografía
de rodilla, donde no hubo cirugía.

Si la EPS verifica y los documentos no están, la glosa se ratifica y el
hospital pierde credibilidad. Y lo absurdo: el sistema YA SABE cuáles son los
soportes reales de esa factura — el indexador los tiene.
"""

from __future__ import annotations

import re

import pytest

from app.services.glosa_service import GlosaService

# El expediente real de HUS468334, tal como lo devuelve el indexador.
EXPEDIENTE = [
    ("FEV_900006037_HUS468334.pdf", "factura_electronica"),
    ("HEV_900006037_HUS468334.pdf", "historia_clinica"),
    ("CRC_900006037_HUS468334.pdf", "comprobante_recibido_cobro"),
    ("OPF_900006037_HUS468334.pdf", "otros_procedimientos"),
    ("PDE_900006037_HUS468334.pdf", "pde"),
    ("PDX_900006037_HUS468334.pdf", "pdx"),
    ("RESULTADOSMSPS_900006037_HUS468334.pdf", "resultados_msps"),
    ("EPICRISIS HUS468334.pdf", "otro"),
    ("RIPS_900006037_HUS468334.json", "rips"),
    ("ad0900060370000468334.xml", "xml_cufe"),
]


@pytest.fixture
def servicio(monkeypatch):
    from app.services import soportes_autodiscovery_service as svc

    class _Idx:
        def lookup(self, factura, auto_rebuild=True):
            if "468334" not in (factura or ""):
                return []
            return [{"nombre_archivo": n, "tipo": t, "ruta": "/srv/" + n} for n, t in EXPEDIENTE]

    monkeypatch.setattr(svc, "get_indexer", lambda: _Idx())
    return GlosaService.__new__(GlosaService)


def _texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


class TestConExpedienteEnElServidor:
    def test_relaciona_los_soportes_que_de_verdad_estan(self, servicio):
        filas, cuantos, aviso = servicio._soportes_reales("HUS468334")
        assert cuantos == len(EXPEDIENTE)
        assert aviso == ""
        texto = _texto("".join(filas))
        assert "Historia clínica" in texto
        assert "Resultados de apoyo diagnóstico" in texto

    def test_cada_renglon_dice_el_nombre_del_archivo(self, servicio):
        """Para que el auditor pueda ir a abrirlo y confirmarlo."""
        texto = _texto("".join(servicio._soportes_reales("HUS468334")[0]))
        assert "HEV_900006037_HUS468334.pdf" in texto
        assert "EPICRISIS HUS468334.pdf" in texto

    def test_no_inventa_documentos_que_no_estan(self, servicio):
        """Lo que decía la plantilla vieja y no existe en este expediente."""
        texto = _texto("".join(servicio._soportes_reales("HUS468334")[0])).upper()
        for inventado in (
            "AUTORIZACIÓN PREVIA",
            "DOCUMENTO DE IDENTIDAD",
            "DESCRIPCIÓN QUIRÚRGICA",
            "REGISTRO ANESTÉSICO",
        ):
            assert inventado not in texto, f"el dictamen sigue afirmando «{inventado}»"

    def test_cada_soporte_va_con_su_norma(self, servicio):
        texto = _texto("".join(servicio._soportes_reales("HUS468334")[0]))
        assert "Res. 1995/1999" in texto
        assert "Res. 2275/2023" in texto

    def test_no_repite_el_mismo_tipo_de_documento(self, servicio):
        filas = servicio._soportes_reales("HUS468334")[0]
        docs = [re.search(r"<td [^>]*>([^<]+)<div", f).group(1) for f in filas]
        assert len(docs) == len(set(docs)), docs


class TestSinExpediente:
    """Lo más importante: cuando no hay con qué probar, no se afirma."""

    def test_no_relaciona_ningun_soporte(self, servicio):
        filas, cuantos, aviso = servicio._soportes_reales("HUS999999")
        assert filas == []
        assert cuantos == 0
        assert aviso, "no se avisa nada: el dictamen sale mudo sobre los soportes"

    def test_avisa_que_esta_por_verificar(self, servicio):
        aviso = _texto(servicio._soportes_reales("HUS999999")[2])
        assert "POR VERIFICAR" in aviso
        assert "no relaciona soportes" in aviso

    def test_el_aviso_no_dice_que_se_aportaron(self, servicio):
        aviso = _texto(servicio._soportes_reales("HUS999999")[2]).upper()
        assert "SOPORTES APORTADOS" not in aviso

    def test_sin_numero_de_factura_no_dice_nada(self, servicio):
        assert servicio._soportes_reales(None) == ([], 0, "")
        assert servicio._soportes_reales("") == ([], 0, "")


class TestElIndiceCaido:
    """Si el servidor de radicación no responde, no se inventa una lista."""

    def test_no_revienta_y_no_afirma_nada(self, monkeypatch):
        from app.services import soportes_autodiscovery_service as svc

        def _explota():
            raise RuntimeError("el share no responde")

        monkeypatch.setattr(svc, "get_indexer", _explota)
        servicio = GlosaService.__new__(GlosaService)
        filas, cuantos, aviso = servicio._soportes_reales("HUS468334")
        assert filas == []
        assert cuantos == 0
        assert "POR VERIFICAR" in _texto(aviso)
