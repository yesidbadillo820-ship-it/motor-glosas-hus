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


class TestElCorreoDeLasDoctoras:
    """«Tener presente que también les llegue al correo de las doctoras»
    (pedido de Yesid, 20-08-2026).

    Las médicas auditoras entran SOLO cuando el lote trae glosas médicas
    —pertinencia o calidad—, que son las que no se pueden contestar desde
    cartera sin concepto clínico. Si entraran siempre, se les llenaría el
    buzón de tarifas y facturación que no les competen, y terminarían
    ignorando también las que sí.
    """

    def _resumen(self, con_medico: bool) -> dict:
        return {
            "total": 1,
            "creadas": 1,
            "actualizadas": 0,
            "ratificadas": 0,
            "extemporaneas": 0,
            "semaforo": {},
            "por_gestor": {
                "IRMA RIOS": [
                    {"factura": "HUS1", "plan": {"con_medico": con_medico}},
                ]
            },
        }

    def _con_doctoras(self, db):
        """Marca a LAURA DIAZ como del equipo médico — que es exactamente lo
        que hace el coordinador en la pantalla de Usuarios."""
        from app.models.db import UsuarioRecord

        u = (
            db.query(UsuarioRecord)
            .filter(UsuarioRecord.email == "auditorhus01@sinacsc.com")
            .first()
        )
        u.equipo = "AUDITORIA MEDICA"
        db.commit()

    def test_una_glosa_medica_se_reconoce(self, db):
        from app.services.email_service import _hay_glosas_medicas

        assert _hay_glosas_medicas(self._resumen(True))
        assert not _hay_glosas_medicas(self._resumen(False))

    def test_se_las_encuentra_por_el_campo_equipo(self, db):
        from app.services.email_service import emails_de_medicos_auditores

        self._con_doctoras(db)
        assert emails_de_medicos_auditores(db=db) == ["auditorhus01@sinacsc.com"]

    def test_o_por_la_configuracion_del_servidor(self, db, monkeypatch):
        from app.core.config import get_settings
        from app.services.email_service import emails_de_medicos_auditores

        cfg = get_settings()
        monkeypatch.setattr(
            cfg, "medicos_auditores_email", "dra1@hus.gov.co, dra2@hus.gov.co", raising=False
        )
        correos = emails_de_medicos_auditores(db=None)
        assert correos == ["dra1@hus.gov.co", "dra2@hus.gov.co"]

    def test_sin_señalarlas_no_se_adivina_quien_es_medico(self, db):
        """Ser SUPER_ADMIN, o tener un correo que empiece por «auditor», NO
        vuelve médico a nadie. Mandarle historia clínica a quien no es del
        área por una corazonada del sistema sería peor que no mandarla."""
        from app.services.email_service import emails_de_medicos_auditores

        assert emails_de_medicos_auditores(db=db) == []

    @pytest.mark.asyncio
    async def test_con_glosas_medicas_les_llega(self, db, monkeypatch):
        from app.services import email_service as es

        async def _ok(destinatario, asunto, html):
            return True

        monkeypatch.setattr(es, "enviar_email", _ok)
        self._con_doctoras(db)
        resumen = self._resumen(True)
        await es.enviar_resumen_importacion_recepcion(resumen, db=db)
        correo = resumen["correo"]
        assert correo["hay_glosas_medicas"] is True
        assert "auditorhus01@sinacsc.com" in correo["medicos_auditores"]
        assert any(d["email"] == "auditorhus01@sinacsc.com" for d in correo["destinatarios"])

    @pytest.mark.asyncio
    async def test_sin_glosas_medicas_NO_les_llega(self, db, monkeypatch):
        from app.services import email_service as es

        async def _ok(destinatario, asunto, html):
            return True

        monkeypatch.setattr(es, "enviar_email", _ok)
        self._con_doctoras(db)
        resumen = self._resumen(False)
        await es.enviar_resumen_importacion_recepcion(resumen, db=db)
        correo = resumen["correo"]
        assert correo["hay_glosas_medicas"] is False
        assert correo["medicos_auditores"] == []
        assert all(d["email"] != "auditorhus01@sinacsc.com" for d in correo["destinatarios"])


class TestACadaDoctoraLoSuyo:
    """El Excel del HUS dice QUÉ doctora lleva cada glosa (20-08-2026).

    La columna `PROFESIONAL(MEDICO)` trae «LAURA DIAZ», «LEIDY SANGUINO» o
    «ZULAY GONZALEZ» según el caso, y la columna `TIPO GLOSA` dice si es
    Administrativo, Medico o Mixta.

    Yesid confirmó que son solo esas tres las médicas auditoras. Con el nombre
    por glosa, a cada una le llega lo suyo en vez de mandarles a las tres el
    lote entero: quien recibe treinta glosas que no son suyas deja de abrir el
    correo, y ahí se pierden también las que sí.

    OJO con los nombres: el Excel escribe «LEIDY SANGUINO» y el portal la
    tiene como «LEIDY JHOANA SANGUINO»; «ZULAY GONZALEZ» contra «LEYDI ZULAY
    GONZALEZ». Sin comparar por tokens, esos dos correos no saldrían nunca.
    """

    # Los nombres EXACTOS como aparecen en el Excel del 19 de agosto.
    EN_EL_EXCEL = {
        "LAURA DIAZ": "auditorhus01@sinacsc.com",
        "LEIDY SANGUINO": "auditorhus02@sinacsc.com",
        "ZULAY GONZALEZ": "auditorhus03@sinacsc.com",
    }

    def _resumen(self, glosas: list[tuple[bool, str]]) -> dict:
        return {
            "total": len(glosas),
            "creadas": len(glosas),
            "actualizadas": 0,
            "ratificadas": 0,
            "extemporaneas": 0,
            "semaforo": {},
            "por_gestor": {
                "YESID PEREZ": [
                    {
                        "factura": f"HUS{i}",
                        "plan": {"con_medico": medica, "profesional_medico": quien},
                    }
                    for i, (medica, quien) in enumerate(glosas)
                ]
            },
        }

    def test_las_tres_del_excel_resuelven_a_su_correo(self, db):
        from app.services.email_service import emails_de_las_doctoras

        resumen = self._resumen([(True, n) for n in self.EN_EL_EXCEL])
        encontradas, sin_correo = emails_de_las_doctoras(resumen, db=db)
        assert encontradas == self.EN_EL_EXCEL
        assert sin_correo == []

    def test_el_segundo_nombre_no_las_deja_por_fuera(self, db):
        """«LEIDY SANGUINO» (Excel) vs «LEIDY JHOANA SANGUINO» (portal)."""
        from app.services.email_service import emails_de_las_doctoras

        encontradas, _ = emails_de_las_doctoras(self._resumen([(True, "LEIDY SANGUINO")]), db=db)
        assert encontradas == {"LEIDY SANGUINO": "auditorhus02@sinacsc.com"}

    def test_una_glosa_administrativa_no_nombra_doctora(self, db):
        from app.services.email_service import _doctoras_nombradas

        assert _doctoras_nombradas(self._resumen([(False, "")])) == []

    def test_no_se_repite_la_misma_doctora(self, db):
        """LAURA DIAZ sale en varias filas del Excel; el correo es uno solo."""
        from app.services.email_service import _doctoras_nombradas

        resumen = self._resumen([(True, "LAURA DIAZ"), (True, "LAURA DIAZ")])
        assert _doctoras_nombradas(resumen) == ["LAURA DIAZ"]

    def test_un_nombre_que_no_esta_en_el_portal_se_reporta(self, db):
        from app.services.email_service import emails_de_las_doctoras

        encontradas, sin_correo = emails_de_las_doctoras(
            self._resumen([(True, "DRA QUE NO EXISTE")]), db=db
        )
        assert encontradas == {}
        assert sin_correo == ["DRA QUE NO EXISTE"]

    @pytest.mark.asyncio
    async def test_a_cada_una_le_llega_y_a_las_otras_no(self, db, monkeypatch):
        """Si el lote solo trae glosas de LAURA, no se molesta a las otras."""
        from app.services import email_service as es

        async def _ok(destinatario, asunto, html):
            return True

        monkeypatch.setattr(es, "enviar_email", _ok)
        resumen = self._resumen([(True, "LAURA DIAZ")])
        await es.enviar_resumen_importacion_recepcion(resumen, db=db)
        correo = resumen["correo"]
        assert correo["doctoras"] == {"LAURA DIAZ": "auditorhus01@sinacsc.com"}
        enviados = {d["email"] for d in correo["destinatarios"]}
        assert "auditorhus01@sinacsc.com" in enviados
        assert "auditorhus02@sinacsc.com" not in enviados
        assert "auditorhus03@sinacsc.com" not in enviados

    @pytest.mark.asyncio
    async def test_sin_glosas_medicas_no_se_molesta_a_ninguna(self, db, monkeypatch):
        from app.services import email_service as es

        async def _ok(destinatario, asunto, html):
            return True

        monkeypatch.setattr(es, "enviar_email", _ok)
        resumen = self._resumen([(False, "")])
        await es.enviar_resumen_importacion_recepcion(resumen, db=db)
        enviados = {d["email"] for d in resumen["correo"]["destinatarios"]}
        assert not any(e.startswith("auditorhus") for e in enviados)

    @pytest.mark.asyncio
    async def test_si_el_excel_no_dice_quien_se_avisa_a_todas(self, db, monkeypatch):
        """Glosa médica sin doctora anotada: mejor avisarle a todas las
        registradas que dejarla sin avisar a nadie."""
        from app.services import email_service as es

        monkeypatch.setattr(es, "enviar_email", lambda d, a, h: _true())

        async def _true():
            return True

        u = (
            db.query(__import__("app.models.db", fromlist=["x"]).UsuarioRecord)
            .filter_by(email="auditorhus01@sinacsc.com")
            .first()
        )
        u.equipo = "AUDITORIA MEDICA"
        db.commit()

        resumen = self._resumen([(True, "")])
        await es.enviar_resumen_importacion_recepcion(resumen, db=db)
        correo = resumen["correo"]
        assert correo["doctoras"] == {}
        assert "auditorhus01@sinacsc.com" in correo["medicos_auditores"]


class TestElAvisoDiceLaCausaDeVerdad:
    """20-08-2026. Yesid importó, no salió correo, y la pantalla marcó la
    importación como «✗ sin destinatarios» — que suena a que no se encontró a
    quién mandarle. Importó otra vez buscando el error en la lista de
    gestores. Pero la causa era otra: **el servidor no tiene el correo
    configurado**, y ese mismo estado se ponía para las dos cosas.

    Un aviso que apunta al lugar equivocado hace perder más tiempo que no
    tener aviso.
    """

    def _estado(self, envio: dict) -> str:
        """Qué estado le quedaría a la importación con ese resultado."""
        enviados = int(envio.get("enviados", 0) or 0)
        motivo = envio.get("motivo") or ""
        if enviados <= 0 and motivo == "SIN_CORREO_CONFIG":
            return "SIN_CORREO_CONFIG"
        if enviados <= 0 and motivo == "SIN_ARCHIVO_ORIGINAL":
            return "SIN_ARCHIVO_ORIGINAL"
        if enviados <= 0:
            return "SIN_DESTINATARIOS"
        return "PARCIAL" if envio.get("gestores_sin_email") else "ENVIADO"

    @pytest.mark.asyncio
    async def test_sin_smtp_el_motivo_lo_dice(self, db, monkeypatch):
        from app.core.config import get_settings
        from app.services.email_service import enviar_excel_recepcion_con_respuestas

        cfg = get_settings()
        monkeypatch.setattr(cfg, "smtp_user", "", raising=False)
        monkeypatch.setattr(cfg, "smtp_password", "", raising=False)

        envio = await enviar_excel_recepcion_con_respuestas(
            resumen={}, excel_original=b"x", glosa_ids=[], db=db
        )
        assert envio["motivo"] == "SIN_CORREO_CONFIG"
        assert envio["enviados"] == 0

    def test_y_el_estado_no_culpa_a_los_gestores(self):
        assert self._estado({"enviados": 0, "motivo": "SIN_CORREO_CONFIG"}) == "SIN_CORREO_CONFIG"

    def test_sin_archivo_original_es_otra_cosa(self):
        assert (
            self._estado({"enviados": 0, "motivo": "SIN_ARCHIVO_ORIGINAL"})
            == "SIN_ARCHIVO_ORIGINAL"
        )

    def test_sin_destinatarios_de_verdad_sigue_diciendolo(self):
        """Cuando SÍ hay correo configurado y aun así no hubo a quién
        mandarle, el estado de siempre sigue valiendo."""
        assert self._estado({"enviados": 0}) == "SIN_DESTINATARIOS"

    def test_cuando_sale_bien_no_se_marca_error(self):
        assert self._estado({"enviados": 3}) == "ENVIADO"
        assert self._estado({"enviados": 3, "gestores_sin_email": ["X"]}) == "PARCIAL"

    def test_la_pantalla_tiene_una_etiqueta_para_cada_causa(self):
        import pathlib

        html = (
            pathlib.Path(__file__).resolve().parents[2] / "static/importar-recepcion.html"
        ).read_text(encoding="utf-8")
        for estado in ("SIN_DESTINATARIOS", "SIN_CORREO_CONFIG", "SIN_ARCHIVO_ORIGINAL"):
            assert estado in html, f"la pantalla no sabe pintar {estado}"
        assert "no tiene correo configurado" in html
