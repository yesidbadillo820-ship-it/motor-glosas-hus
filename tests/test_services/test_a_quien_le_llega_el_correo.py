"""¿A qué correo le llega el plan de trabajo de cada gestor? (20-08-2026)

Yesid preguntó: «ahora yo subo ahí el archivo, ¿y cómo se comprueba que le
llega a los correos de los gestores?».

La pantalla decía «📧 Correos enviados: 3» y nada más. Con eso no hay forma de
saber que a CAROLINA no le llegó nada porque su nombre en el Excel no coincide
con ningún usuario del portal — que es la falla que de verdad ocurre, no que
se caiga el servidor de correo.

Los usuarios de acá abajo son los REALES del portal (los pasó Yesid), y los
gestores son los del archivo `GLOSAS_19_AGOSTO_1.xlsx` (85 glosas).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, UsuarioRecord
from app.services.email_service import _buscar_emails_por_gestor, emails_por_gestor

# Los 23 usuarios activos del portal, tal como están registrados.
USUARIOS_REALES = [
    ("YESID PEREZ", "glosashus09@sinacsc.com"),
    ("DIANEYDA QUINTERO", "glosashus11@sinacsc.com"),
    ("CAROLINA CIFUENTES", "glosashus02@sinacsc.com"),
    ("JHON JAIMES", "glosashus04@sinacsc.com"),
    ("MARICELA ROJAS", "glosashus05@sinacsc.com"),
    ("IRMA RIOS", "carterahus01@sinacsc.com"),
    ("RUBY MILENA", "carterahus04@sinacsc.com"),
    ("PATRICIA QUIÑONES", "carterahus05@sinacsc.com"),
    ("KAREN ORTIZ", "radicadevoluciones@sinacsc.com"),
    ("SEBASTIAN SANCHES", "devoluciones01@sinacsc.com"),
    ("CLAUDIA SUAREZ", "glosashus08@sinacsc.com"),
    ("VANESA OSPINA", "glosashus07@sinacsc.com"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)", "glosashus12@sinacsc.com"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)", "devoluciones02@sinacsc.com"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)", "glosashus10@sinacsc.com"),
    ("A_A_A_A (EQUIPO ASEGURADORAS)", "glosashus16@sinacsc.com"),
    ("LAURA DIAZ", "auditorhus01@sinacsc.com"),
    ("LEIDY JHOANA SANGUINO", "auditorhus02@sinacsc.com"),
    ("LEYDI ZULAY GONZALEZ", "auditorhus03@sinacsc.com"),
    ("JOHANNA MORENO", "devoluciones03@sinacsc.com"),
    ("EDGAR SILVA", "devoluciones1@sinacsc.com"),
    ("OSCAR VILLAMIZAR", "glosashus03@sinacsc.com"),
    ("IVAN ARCINIEGAS", "glosashus13@sinacsc.com"),
]

# Los gestores del archivo del 19 de agosto, con sus glosas.
GESTORES_DEL_ARCHIVO = {
    "YESID PEREZ": 35,
    "IVAN ARCINIEGAS": 26,
    "IRMA RIOS": 7,
    "MARICELA ROJAS": 7,
    "EQUIPO ASEGURADORAS": 6,
    "KAREN ORTIZ": 4,
}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    for nombre, email in USUARIOS_REALES:
        sesion.add(UsuarioRecord(nombre=nombre, email=email, activo=1, password_hash="x"))
    sesion.commit()
    yield sesion
    sesion.close()


class TestElArchivoRealDeYesid:
    def test_los_seis_gestores_tienen_correo(self, db):
        cruce = emails_por_gestor(list(GESTORES_DEL_ARCHIVO), db=db)
        sin_correo = [g for g, correos in cruce.items() if not correos]
        assert not sin_correo, f"Estos gestores no recibirían nada: {sin_correo}"

    def test_equipo_aseguradoras_le_llega_a_los_cuatro(self, db):
        """Los cuatro usuarios se llaman «A_A_A_A (EQUIPO ASEGURADORAS)», así
        que el nombre del Excel tiene que alcanzarlos a todos."""
        correos = _buscar_emails_por_gestor(["EQUIPO ASEGURADORAS"], db=db)
        assert len(correos) == 4
        assert "glosashus12@sinacsc.com" in correos

    def test_cada_gestor_va_a_su_propio_buzon(self, db):
        cruce = emails_por_gestor(list(GESTORES_DEL_ARCHIVO), db=db)
        assert cruce["IRMA RIOS"] == ["carterahus01@sinacsc.com"]
        assert cruce["KAREN ORTIZ"] == ["radicadevoluciones@sinacsc.com"]
        assert cruce["IVAN ARCINIEGAS"] == ["glosashus13@sinacsc.com"]

    def test_el_nombre_de_pila_tambien_alcanza(self, db):
        """En el Excel a veces va solo el nombre: «CAROLINA» por «CAROLINA
        CIFUENTES»."""
        assert _buscar_emails_por_gestor(["CAROLINA"], db=db) == ["glosashus02@sinacsc.com"]


class TestUnaLetraSueltaNoLeEscribeATodoElMundo:
    """El defecto que aparece con un dedazo en el Excel.

    El cruce aceptaba «contiene» sin exigir un mínimo, así que una celda de
    gestor con una sola letra —una «A»— le mandaba el correo a 22 de los 23
    usuarios, porque casi todo nombre lleva una A. Cada quien recibía un plan
    de trabajo que no era el suyo, y con 85 glosas eso es un desastre de ida y
    vuelta. Una «S» alcanzaba a 17.
    """

    @pytest.mark.parametrize("basura", ["A", "S", "E", "AN", "O", "R"])
    def test_un_nombre_corto_no_alcanza_a_nadie(self, db, basura):
        correos = _buscar_emails_por_gestor([basura], db=db)
        assert correos == [], f"«{basura}» le escribiría a {len(correos)} personas"

    def test_los_nombres_de_verdad_siguen_funcionando(self, db):
        """La mitad que importa: el piso no puede dejar sin correo a nadie."""
        for gestor in GESTORES_DEL_ARCHIVO:
            assert _buscar_emails_por_gestor([gestor], db=db), (
                f"«{gestor}» se quedó sin correo por culpa del filtro"
            )

    def test_un_nombre_corto_pero_EXACTO_si_vale(self, db):
        """Si alguien se registra literalmente así, es esa persona."""
        db.add(UsuarioRecord(nombre="ANA", email="ana@sinacsc.com", activo=1, password_hash="x"))
        db.commit()
        assert _buscar_emails_por_gestor(["ANA"], db=db) == ["ana@sinacsc.com"]

    def test_las_celdas_vacias_o_de_relleno_no_alcanzan_a_nadie(self, db):
        for basura in ("N/A", "-", "SIN ASIGNAR", "", "   "):
            assert _buscar_emails_por_gestor([basura], db=db) == []


class TestElResumenDiceAQuienLeLlego:
    """Lo que el auditor ve en pantalla después de subir el archivo."""

    def test_el_cruce_nombra_a_los_que_no_tienen_usuario(self, db):
        cruce = emails_por_gestor(["IRMA RIOS", "PEPITO PEREZ"], db=db)
        assert cruce["IRMA RIOS"]
        assert cruce["PEPITO PEREZ"] == []

    def test_sin_base_de_datos_no_se_inventa_un_cruce(self):
        assert emails_por_gestor(["IRMA RIOS"], db=None) == {}

    @pytest.mark.asyncio
    async def test_el_resumen_queda_con_el_detalle_del_correo(self, db, monkeypatch):
        from app.services import email_service as es

        async def _ok(destinatario, asunto, html):
            return True

        monkeypatch.setattr(es, "enviar_email", _ok)
        resumen = {
            "total": 85,
            "creadas": 85,
            "actualizadas": 0,
            "ratificadas": 0,
            "extemporaneas": 0,
            "semaforo": {},
            "por_gestor": {g: [] for g in GESTORES_DEL_ARCHIVO},
        }
        await es.enviar_resumen_importacion_recepcion(resumen, db=db)

        correo = resumen.get("correo")
        assert correo is not None, "el resumen no trae el detalle del correo"
        assert correo["gestores_sin_correo"] == []
        assert set(correo["por_gestor"]) == set(GESTORES_DEL_ARCHIVO)
        assert correo["por_gestor"]["IRMA RIOS"] == ["carterahus01@sinacsc.com"]

    @pytest.mark.asyncio
    async def test_y_avisa_cuando_un_gestor_se_queda_por_fuera(self, db, monkeypatch):
        from app.services import email_service as es

        async def _ok(destinatario, asunto, html):
            return True

        monkeypatch.setattr(es, "enviar_email", _ok)
        resumen = {
            "total": 2,
            "creadas": 2,
            "actualizadas": 0,
            "ratificadas": 0,
            "extemporaneas": 0,
            "semaforo": {},
            "por_gestor": {"IRMA RIOS": [], "GESTOR QUE NO EXISTE": []},
        }
        await es.enviar_resumen_importacion_recepcion(resumen, db=db)
        assert resumen["correo"]["gestores_sin_correo"] == ["GESTOR QUE NO EXISTE"]
