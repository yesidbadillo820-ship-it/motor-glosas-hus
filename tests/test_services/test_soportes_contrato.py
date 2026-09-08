"""Que el indexador no pueda pintar una pantalla en blanco.

El caso que lo enseñó: `lookup()` devuelve DICCIONARIOS y en el cajón de la
mesa se leían con `getattr`. No falló nada — el auditor vio «3 soportes» y
tres renglones vacíos. En una audiencia eso se lee como «esta factura no
tiene con qué defenderse», y no era verdad.

Acá se cuida que cada respuesta rara del indexador acabe en un estado que la
pantalla pueda pintar como lo que es.
"""

from __future__ import annotations

import pytest

from app.services.soportes_contrato import (
    EstadoSoportes,
    RespuestaSoportes,
    SoporteDeFactura,
    leer_soportes,
    validar_lista,
)


def _entrada(**cambios):
    base = {
        "factura": "HUS0000542497",
        "factura_norm": "542497",
        "tipo": "factura_electronica",
        "tipo_codigo": "FEV",
        "ruta": "/soportes/FEV-542497.pdf",
        "nombre_archivo": "FEV-542497.pdf",
        "extension": ".pdf",
        "eps": "COOSALUD",
        "env": "ENV-001",
        "mes": "SEPTIEMBRE",
        "anio": 2026,
        "tamano_kb": 210,
        "fecha_mod": 1757000000.0,
    }
    base.update(cambios)
    return base


class _Indice:
    """Un indexador de mentiras, para poner al de verdad en cada situación."""

    def __init__(self, devuelve=None, construyendo=False, estalla=False, stats=None):
        self._devuelve = devuelve if devuelve is not None else []
        self._construyendo = construyendo
        self._estalla = estalla
        self._stats = stats

    def stats(self):
        if self._stats is not None:
            return self._stats
        return {"construyendo": self._construyendo, "construido_en_epoch": 1757000000.0}

    def lookup(self, factura, auto_rebuild=True):
        if self._estalla:
            raise RuntimeError("la ruta de soportes no responde")
        return self._devuelve


@pytest.fixture
def indice(monkeypatch):
    def poner(idx):
        from app.services import soportes_autodiscovery_service as sas

        monkeypatch.setattr(sas, "get_indexer", lambda: idx)
        return idx

    return poner


class TestLoQueLlegaDelIndexador:
    def test_un_diccionario_normal_se_lee_completo(self, indice):
        indice(_Indice([_entrada()]))
        r = leer_soportes("HUS0000542497")
        assert r.estado is EstadoSoportes.CON_SOPORTES
        assert r.cuantos == 1
        a = r.archivos[0]
        assert a.nombre == "FEV-542497.pdf", "el nombre no puede llegar vacío"
        assert a.tipo_codigo == "FEV"
        assert a.tamano_kb == 210

    def test_los_campos_de_mas_no_estorban(self, indice):
        """El indexador trae más datos de los que la pantalla usa."""
        indice(_Indice([_entrada(firma_interna="x", lo_que_sea=123)]))
        assert leer_soportes("542497").estado is EstadoSoportes.CON_SOPORTES

    def test_un_registro_sin_nombre_se_descarta_y_se_cuenta(self, indice):
        """Un renglón sin nombre ES la fila en blanco que se quiere evitar."""
        indice(_Indice([_entrada(), _entrada(nombre_archivo=""), _entrada(nombre_archivo="   ")]))
        r = leer_soportes("542497")
        assert r.estado is EstadoSoportes.CON_SOPORTES
        assert r.cuantos == 1 and r.descartados == 2
        assert "incompleta" in r.detalle.lower(), "hay que avisar que la lista no está entera"

    def test_un_registro_malo_no_tumba_a_los_buenos(self, indice):
        indice(
            _Indice([_entrada(), "esto no es un registro", None, _entrada(nombre_archivo="B.pdf")])
        )
        r = leer_soportes("542497")
        assert r.cuantos == 2 and r.descartados == 2

    def test_si_TODO_viene_mal_se_dice_que_es_un_error(self, indice):
        """Nunca «no tiene soportes» cuando la verdad es «no se pudo leer»."""
        indice(_Indice(["basura", 42, None]))
        r = leer_soportes("542497")
        assert r.estado is EstadoSoportes.DATOS_INVALIDOS
        assert r.archivos == []
        assert "no se muestra nada" in r.detalle.lower()

    def test_una_respuesta_que_no_es_lista_es_un_error(self, indice):
        indice(_Indice({"factura": "x"}))
        assert leer_soportes("542497").estado is EstadoSoportes.DATOS_INVALIDOS

    def test_el_indexador_caido_no_es_sin_soportes(self, indice):
        indice(_Indice(estalla=True))
        r = leer_soportes("542497")
        assert r.estado is EstadoSoportes.SIN_INDICE
        assert "no quiere decir que la factura no tenga" in r.detalle.lower()

    def test_indexando_no_es_sin_soportes(self, indice):
        indice(_Indice([], construyendo=True))
        r = leer_soportes("542497")
        assert r.estado is EstadoSoportes.INDEXANDO
        assert "todavía no se sabe" in r.detalle.lower()

    def test_un_indice_que_nunca_se_ha_armado_tampoco(self, indice):
        indice(_Indice([], stats={"construyendo": False, "construido_en_epoch": None}))
        assert leer_soportes("542497").estado is EstadoSoportes.INDEXANDO

    def test_un_indice_con_error_guardado_se_reporta(self, indice):
        indice(_Indice([], stats={"construyendo": False, "ultimo_error": "ruta Z: no montada"}))
        r = leer_soportes("542497")
        assert r.estado is EstadoSoportes.SIN_INDICE
        assert "Z:" in r.detalle

    def test_vacio_de_verdad_si_se_termino_de_buscar(self, indice):
        indice(_Indice([]))
        assert leer_soportes("542497").estado is EstadoSoportes.SIN_SOPORTES

    def test_sin_factura_no_se_consulta(self, indice):
        indice(_Indice([_entrada()]))
        assert leer_soportes("   ").estado is EstadoSoportes.SIN_SOPORTES

    def test_nunca_lanza(self, monkeypatch):
        """Una mesa no se puede caer porque el índice falle: la EPS está esperando."""
        from app.services import soportes_autodiscovery_service as sas

        def explota():
            raise RuntimeError("boom")

        monkeypatch.setattr(sas, "get_indexer", explota)
        assert leer_soportes("542497").estado is EstadoSoportes.SIN_INDICE


class TestElContratoAprieta:
    def test_no_pasa_un_soporte_sin_nombre(self):
        with pytest.raises(ValueError):
            SoporteDeFactura(nombre="  ")

    def test_no_pasa_un_tamano_absurdo(self):
        with pytest.raises(ValueError):
            SoporteDeFactura(nombre="x.pdf", tamano_kb=-1)

    def test_la_respuesta_no_admite_campos_inventados(self):
        with pytest.raises(ValueError):
            RespuestaSoportes(estado=EstadoSoportes.SIN_SOPORTES, campo_raro=1)

    def test_hay_problema_distingue_error_de_ausencia(self):
        assert RespuestaSoportes(estado=EstadoSoportes.SIN_INDICE).hay_problema
        assert RespuestaSoportes(estado=EstadoSoportes.DATOS_INVALIDOS).hay_problema
        assert not RespuestaSoportes(estado=EstadoSoportes.SIN_SOPORTES).hay_problema
        assert not RespuestaSoportes(estado=EstadoSoportes.INDEXANDO).hay_problema

    def test_el_tope_corta_pero_no_miente(self):
        buenos, descartados = validar_lista([_entrada() for _ in range(60)], tope=10)
        assert len(buenos) == 10 and descartados == 0

    def test_tambien_acepta_objetos(self):
        """Por si otro indexador entrega objetos en vez de diccionarios."""

        class Obj:
            nombre_archivo = "HEV-1.pdf"
            tipo = "historia_clinica"
            tipo_codigo = "HEV"
            tamano_kb = 12
            ruta = "/x/HEV-1.pdf"

        buenos, descartados = validar_lista([Obj()])
        assert descartados == 0 and buenos[0].nombre == "HEV-1.pdf"
