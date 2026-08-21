"""Snippets: los atajos de texto del gestor (20-08-2026).

Qué son: usted define `/ratif` y, al escribirlo en cualquier casilla del
portal y pulsar Tab, se convierte en su párrafo de ratificación completo.

La tabla estaba creada en la base de datos y la pantalla «Gestionar mis
snippets» estaba hecha. Lo que faltaba era el medio: el router devolvía lista
vacía y no tenía crear, ni borrar, ni registrar el uso. El auditor abría el
gestor, escribía su atajo, guardaba… y le salía «Falló».
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, SnippetRecord
from app.services import snippets_service as svc

YO = "yesid@hus.gov.co"
OTRO = "carolina@hus.gov.co"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    yield sesion
    sesion.close()


class TestCrear:
    def test_se_crea_y_queda_en_la_lista(self, db):
        snip, error = svc.crear(db, email=YO, atajo="/ratif", contenido="TEXTO LARGO")
        assert error == ""
        assert snip["atajo"] == "/ratif"
        assert len(svc.listar(db, YO)) == 1

    def test_el_atajo_siempre_arranca_con_barra(self, db):
        """Si se guarda «ratif» sin barra, la pantalla nunca lo expande: queda
        un atajo muerto que en la lista se ve perfecto."""
        snip, _ = svc.crear(db, email=YO, atajo="ratif", contenido="X")
        assert snip["atajo"] == "/ratif"

    def test_y_va_en_minusculas(self, db):
        snip, _ = svc.crear(db, email=YO, atajo="/RATIF", contenido="X")
        assert snip["atajo"] == "/ratif"

    def test_sin_atajo_no_se_crea(self, db):
        snip, error = svc.crear(db, email=YO, atajo="   ", contenido="X")
        assert snip is None and error

    def test_sin_contenido_no_se_crea(self, db):
        snip, error = svc.crear(db, email=YO, atajo="/x", contenido="  ")
        assert snip is None and error

    def test_no_se_puede_repetir_el_mismo_atajo(self, db):
        """Dos «/ratif» sería una ruleta: la pantalla expande el primero que
        encuentra. Mejor decirlo que dejarlo al azar."""
        svc.crear(db, email=YO, atajo="/ratif", contenido="A")
        snip, error = svc.crear(db, email=YO, atajo="/ratif", contenido="B")
        assert snip is None
        assert "/ratif" in error

    def test_pero_dos_personas_si_pueden_tener_el_mismo(self, db):
        svc.crear(db, email=YO, atajo="/ratif", contenido="el mio")
        snip, error = svc.crear(db, email=OTRO, atajo="/ratif", contenido="el suyo")
        assert error == "" and snip is not None

    def test_una_visibilidad_rara_cae_a_privado(self, db):
        snip, _ = svc.crear(db, email=YO, atajo="/x", contenido="X", visibilidad="LO QUE SEA")
        assert snip["visibilidad"] == "PRIVADO"


class TestListar:
    def test_solo_veo_los_mios_y_los_compartidos(self, db):
        svc.crear(db, email=YO, atajo="/mio", contenido="A")
        svc.crear(db, email=OTRO, atajo="/suyo", contenido="B")
        svc.crear(db, email=OTRO, atajo="/global", contenido="C", visibilidad="GLOBAL")
        svc.crear(db, email=OTRO, atajo="/equipo", contenido="D", visibilidad="EQUIPO")
        atajos = {s["atajo"] for s in svc.listar(db, YO)}
        assert atajos == {"/mio", "/global", "/equipo"}
        assert "/suyo" not in atajos

    def test_los_mas_usados_quedan_arriba(self, db):
        a, _ = svc.crear(db, email=YO, atajo="/poco", contenido="A")
        b, _ = svc.crear(db, email=YO, atajo="/mucho", contenido="B")
        for _ in range(3):
            svc.registrar_uso(db, email=YO, snippet_id=b["id"])
        assert svc.listar(db, YO)[0]["atajo"] == "/mucho"
        assert a["id"] != b["id"]

    def test_dice_cuales_son_mios(self, db):
        svc.crear(db, email=YO, atajo="/mio", contenido="A")
        svc.crear(db, email=OTRO, atajo="/global", contenido="C", visibilidad="GLOBAL")
        por_atajo = {s["atajo"]: s for s in svc.listar(db, YO)}
        assert por_atajo["/mio"]["es_mio"] is True
        assert por_atajo["/global"]["es_mio"] is False

    def test_la_pantalla_recibe_todos_los_campos_que_pinta(self, db):
        svc.crear(db, email=YO, atajo="/x", contenido="X", descripcion="una nota")
        s = svc.listar(db, YO)[0]
        for campo in ("id", "atajo", "contenido", "descripcion", "visibilidad", "uso_count"):
            assert campo in s, f"la pantalla pinta «{campo}» y no viene"


class TestBorrar:
    def test_borro_el_mio(self, db):
        snip, _ = svc.crear(db, email=YO, atajo="/x", contenido="X")
        ok, error = svc.borrar(db, email=YO, snippet_id=snip["id"])
        assert ok and error == ""
        assert svc.listar(db, YO) == []

    def test_no_puedo_borrar_el_de_otra_persona(self, db):
        """Un GLOBAL lo ve todo el mundo, pero solo lo borra su dueño."""
        snip, _ = svc.crear(db, email=OTRO, atajo="/g", contenido="X", visibilidad="GLOBAL")
        ok, error = svc.borrar(db, email=YO, snippet_id=snip["id"])
        assert not ok and "otra persona" in error
        assert db.query(SnippetRecord).count() == 1

    def test_borrar_uno_que_ya_no_esta_avisa_claro(self, db):
        ok, error = svc.borrar(db, email=YO, snippet_id=9999)
        assert not ok and "no existe" in error


class TestRegistrarUso:
    def test_suma_al_contador(self, db):
        snip, _ = svc.crear(db, email=YO, atajo="/x", contenido="X")
        assert svc.registrar_uso(db, email=YO, snippet_id=snip["id"])
        assert svc.listar(db, YO)[0]["uso_count"] == 1

    def test_puedo_usar_uno_compartido_aunque_no_sea_mio(self, db):
        snip, _ = svc.crear(db, email=OTRO, atajo="/g", contenido="X", visibilidad="GLOBAL")
        assert svc.registrar_uso(db, email=YO, snippet_id=snip["id"])

    def test_no_puedo_usar_el_privado_de_otra_persona(self, db):
        snip, _ = svc.crear(db, email=OTRO, atajo="/p", contenido="X")
        assert not svc.registrar_uso(db, email=YO, snippet_id=snip["id"])

    def test_uno_que_no_existe_no_revienta(self, db):
        """La pantalla llama esto sin esperar respuesta: no puede tumbar nada."""
        assert svc.registrar_uso(db, email=YO, snippet_id=9999) is False


class TestNormalizarAtajo:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("/ratif", "/ratif"),
            ("ratif", "/ratif"),
            ("  /Ratif  ", "/ratif"),
            ("//ratif", "/ratif"),
            ("/mi-atajo_2", "/mi-atajo_2"),
            ("/con espacios", "/conespacios"),
            ("", ""),
            ("/", ""),
        ],
    )
    def test_casos(self, entrada, esperado):
        assert svc.normalizar_atajo(entrada) == esperado
