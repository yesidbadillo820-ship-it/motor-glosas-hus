"""«Analizar con IA» de Salud Total, conectado de verdad al motor.

OT-045 · 13-08-2026. El botón «Analizar con IA (Análisis completo)» existía
desde antes y **no llamaba a la IA**: caía en las mismas plantillas por
código de glosa que las otras dos opciones. Yesid pidió que hiciera lo que
promete, no que le cambiáramos el nombre.

Ahora cada fila de la notificación se convierte en una glosa y pasa por
`GlosaService.analizar`, el MISMO camino que usa el portal — con las
cláusulas del contrato, las tarifas pactadas y la homologación CUPS → SOAT.

**Lo que estas pruebas cuidan, además de que funcione:**

  · **Que la casilla de la entidad no se desborde.** «Observación IPS» admite
    500 caracteres y un dictamen del motor tiene miles. Si se pasa, Salud
    Total rechaza el archivo entero.
  · **Que ninguna fila se quede vacía.** Si la IA falla o se demora, esa
    glosa cae a la respuesta por plantilla. Una fila en blanco en el archivo
    que se radica es una glosa sin responder, y una glosa sin responder se da
    por aceptada: es plata perdida.
  · **Que los valores no los toque la IA.** El radicado, el registro y el
    valor glosado salen del archivo, no del dictamen.

La IA va simulada: estas pruebas comprueban la costura, no la calidad del
texto que redacta el modelo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.models.db import UsuarioRecord

RADICADO = "350000214021421"

CABECERA = (
    "FechaRad_|NumeroRad_|PrefijoFac_|NumeroFac_|Numreg|NumeroDocAfl_|NombreComplAfl|Nap|"
    "NombreServicio|ValorTotalServ|CantidadFac|ValorUnitario|ValorGlosaFinal|"
    "ValorGlosaTotalxServ|DescripcionMotivo|Observaciones|CodMotvGlosaGeneral|"
    "MotvGlosaGeneral|CodMotvGlosaEspc|MotvGlosaEspc|DescripcionDevolucion|"
    "CausalDevolucion|MotivoDevolucion|ValorBrutoFactura|"
)
FILA = (
    f"07/03/2026 2:07:00 AM|{RADICADO}|HUS|523938|605090729|00000000|PACIENTE|0|"
    "RADIOGRAFIA DE TORAX|280000.00|2|140000.00|93340.00|93340|"
    "Diferencias con los valores pactados||TA|Tarifas|TA23|Otros procedimientos||||1589100.00|"
)
NOTIFICACION = "\r\n".join([CABECERA, FILA, FILA.replace("605090729", "605089544")]) + "\r\n"


def _archivo(texto: str = NOTIFICACION):
    return {"file": ("NotificacionGLS.txt", texto.encode("latin-1"), "text/plain")}


class _ResultadoFalso:
    """Lo que devuelve `GlosaService.analizar`, en lo que acá importa."""

    def __init__(self, dictamen: str):
        self.dictamen = dictamen
        self.modelo_ia = "modelo-de-prueba"
        self.score = 88.0


class _IAFalsa:
    """Motor simulado. `fallar_en` dice qué registros no responde."""

    def __init__(
        self, dictamen: str = "", fallar_en: set[str] | None = None, demorar: bool = False
    ):
        self.dictamen = dictamen or (
            "ESE HUS NO ACEPTA LA GLOSA POR TARIFAS. El valor cobrado corresponde "
            "a la tarifa pactada en el contrato S-13-1-03-1-04958, anexo de "
            "servicios y tarifas. La entidad no puede aplicar descuentos "
            "unilaterales. Se solicita el levantamiento."
        )
        self.fallar_en = fallar_en or set()
        self.demorar = demorar
        self.llamadas = 0

    async def analizar(self, entrada, **_kw):
        self.llamadas += 1
        texto = entrada.tabla_excel
        for reg in self.fallar_en:
            if reg in texto:
                raise RuntimeError("el proveedor de IA no respondió")
        if self.demorar:
            import asyncio

            await asyncio.sleep(3600)
        return _ResultadoFalso(self.dictamen)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def auditor(db_session):
    u = UsuarioRecord(
        id=1,
        email="auditor@hus.gov.co",
        nombre="Auditor",
        rol="AUDITOR",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, auditor):
    from app.api.deps import get_auditor_o_superior
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_auditor_o_superior] = lambda: auditor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def ia(monkeypatch):
    """Reemplaza el motor por uno simulado. Devuelve el simulador."""
    from app.services import salud_total_ia as mod

    falsa = _IAFalsa()
    monkeypatch.setattr(mod, "_analizar_una", mod._analizar_una)  # se conserva el real

    import app.services.glosa_service as gs

    monkeypatch.setattr(gs, "GlosaService", lambda *a, **k: falsa)
    return falsa


class TestElBotonYaLlamaALaIA:
    def test_la_ruta_existe(self):
        from app.main import app

        rutas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/salud-total/analizar-ia" in rutas

    def test_exige_sesion(self):
        from app.main import app

        with TestClient(app) as c:
            assert c.post("/api/salud-total/analizar-ia", files=_archivo()).status_code in (
                401,
                403,
            )

    def test_analiza_cada_glosa_con_el_motor(self, client, ia):
        r = client.post("/api/salud-total/analizar-ia", files=_archivo())
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 2
        assert d["analizadas_con_ia"] == 2
        assert ia.llamadas == 2, "no llamó al motor una vez por glosa"

    def test_la_observacion_sale_del_dictamen_y_no_de_la_plantilla(self, client, ia):
        d = client.post("/api/salud-total/analizar-ia", files=_archivo()).json()
        obs = d["glosas"][0]["Observacion_IPS"]
        assert "S-13-1-03-1-04958" in obs, "no llegó el dictamen de la IA"
        assert d["glosas"][0]["AnalizadaPorIA"] is True

    def test_el_texto_que_recibe_la_ia_lleva_lo_de_la_glosa(self):
        from app.services.salud_total_ia import _texto_de_la_glosa

        texto = _texto_de_la_glosa(
            {
                "PrefijoFac": "HUS",
                "NumeroFac": "523938",
                "NumeroRad": RADICADO,
                "NUMREG": "605090729",
                "NombreServicio": "RADIOGRAFIA DE TORAX",
                "ValorTotalServ": 280000.0,
                "ValorGlosaTotalxServ": 93340.0,
                "CodMotvGlosaGeneral": "TA",
                "CodMotvGlosaEspc": "TA23",
                "DescripcionMotivo": "Diferencias con los valores pactados",
            }
        )
        assert "$93.340" in texto
        assert "HUS523938" in texto
        assert "TA23" in texto
        # Los dos códigos NO se pegan: «TATA23» no es ningún código.
        assert "TATA23" not in texto


class TestLaCasillaDeLaEntidadNoSeDesborda:
    """«Observación IPS» admite 500 caracteres. Si se pasa, Salud Total
    rechaza el archivo entero."""

    def test_un_dictamen_largo_se_condensa(self, client, monkeypatch):
        import app.services.glosa_service as gs

        largo = ("ESE HUS NO ACEPTA LA GLOSA POR TARIFAS. " * 40).strip()
        monkeypatch.setattr(gs, "GlosaService", lambda *a, **k: _IAFalsa(dictamen=largo))
        d = client.post("/api/salud-total/analizar-ia", files=_archivo()).json()
        for g in d["glosas"]:
            assert len(g["Observacion_IPS"]) <= 500, len(g["Observacion_IPS"])

    def test_el_corte_deja_la_frase_cerrada(self):
        """Cortar a la brava deja la defensa a mitad de frase, y esa frase la
        lee un auditor de la EPS buscando cómo ratificar."""
        from app.services.salud_total_ia import _condensar

        texto = ("Primera frase con argumento de peso. " * 30).strip()
        salida = _condensar(texto)
        assert len(salida) <= 500
        assert salida.endswith("."), salida[-40:]

    def test_un_dictamen_corto_no_se_toca(self):
        from app.services.salud_total_ia import _condensar

        assert _condensar("Corto y claro.") == "Corto y claro."

    def test_un_dictamen_vacio_no_revienta(self):
        from app.services.salud_total_ia import _condensar

        assert _condensar("") == ""
        assert _condensar(None) == ""


class TestNingunaFilaSeQuedaVacia:
    """Una fila en blanco en el archivo que se radica es una glosa sin
    responder, y una glosa sin responder se da por aceptada: plata perdida."""

    def test_si_la_ia_falla_esa_glosa_sale_por_plantilla(self, client, monkeypatch):
        import app.services.glosa_service as gs

        monkeypatch.setattr(gs, "GlosaService", lambda *a, **k: _IAFalsa(fallar_en={"605089544"}))
        d = client.post("/api/salud-total/analizar-ia", files=_archivo()).json()
        assert d["total"] == 2
        assert d["analizadas_con_ia"] == 1
        assert d["por_plantilla"] == 1
        for g in d["glosas"]:
            assert g["Observacion_IPS"].strip(), "una fila quedó sin observación"
            assert g["Codigo_Respuesta_a_glosas"].strip()

    def test_si_la_ia_falla_entera_el_archivo_igual_sale(self, client, monkeypatch):
        import app.services.glosa_service as gs

        class _Muerta:
            async def analizar(self, *_a, **_k):
                raise RuntimeError("proveedor caído")

        monkeypatch.setattr(gs, "GlosaService", lambda *a, **k: _Muerta())
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "ia"}
        )
        assert r.status_code == 200, "la pantalla se habría quedado sin archivo"
        lineas = r.text.strip().split("\n")
        assert len(lineas) == 3, "cabecera + 2 glosas"  # ninguna fila se perdió
        assert RADICADO in r.text
        for fila in lineas[1:]:
            assert fila.split("|")[-1].strip(), "una fila quedó sin observación"

    def test_la_pantalla_avisa_cuantas_salieron_por_plantilla(self, client, monkeypatch):
        """El auditor tiene que saber cuáles revisar a mano."""
        import app.services.glosa_service as gs

        monkeypatch.setattr(gs, "GlosaService", lambda *a, **k: _IAFalsa(fallar_en={"605089544"}))
        d = client.post("/api/salud-total/analizar-ia", files=_archivo()).json()
        assert d["por_plantilla"] == 1
        marcadas = [g for g in d["glosas"] if g.get("AnalizadaPorIA") is False]
        assert len(marcadas) == 1


class TestLaIANoTocaLosNumeros:
    """El radicado, el registro y el valor glosado salen del archivo de la
    entidad. Si los pusiera la IA, volveríamos al «3,5E+14» del 13-08."""

    def test_los_valores_son_los_del_archivo(self, client, ia):
        d = client.post("/api/salud-total/analizar-ia", files=_archivo()).json()
        g = d["glosas"][0]
        assert g["NumeroRad"] == RADICADO
        assert g["ValorGlosaTotalxServ"] == 93340.0
        assert g["CodMotvGlosaGeneral"] == "TA"

    def test_el_archivo_generado_conserva_los_valores(self, client, ia):
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "ia"}
        )
        assert r.status_code == 200
        primera = r.text.strip().split("\n")[1].split("|")
        assert primera[0] == RADICADO
        assert primera[5] == "93340"


class TestArchivosQueNoSirven:
    def test_un_archivo_que_no_es_txt_se_rechaza(self, client):
        r = client.post(
            "/api/salud-total/analizar-ia",
            files={"file": ("x.xlsx", b"PK\x03\x04", "application/vnd.ms-excel")},
        )
        assert r.status_code == 400

    def test_un_txt_sin_glosas_lo_dice(self, client):
        r = client.post("/api/salud-total/analizar-ia", files=_archivo(CABECERA + "\r\n"))
        assert r.status_code == 400
        assert r.json()["detail"]


class TestNuncaSaleHtmlALaEntidad:
    """13-08-2026, corrección en caliente.

    La primera versión de esto recortaba el dictamen sin quitarle las
    etiquetas, y el archivo que se generó traía en la casilla de la entidad:

        <table border="1" style="width:100%;border-collapse:collapse;…

    cortado a mitad de un atributo de estilo. Ilegible, con el argumento en
    ninguna parte, y con 44 filas así. El dictamen del motor viene en HTML
    porque está hecho para verse en pantalla y en el PDF.
    """

    HTML_REAL = (
        '<table border="1" style="width:100%;border-collapse:collapse;font-size:11px;'
        'margin-bottom:15px;background:white;"> <tr style="background-color:#1e40af;'
        'color:white;"><th style="padding:10px;text-align:center;">CÓDIGO GLOSA</th>'
        "</tr></table><h3>ARGUMENTACIÓN JURÍDICA</h3>"
        "<p>ESE HUS NO ACEPTA LA GLOSA POR TARIFAS. El valor cobrado corresponde a la "
        "tarifa pactada en el contrato S-13-1-03-1-04958, anexo de servicios y tarifas. "
        "La entidad no puede aplicar descuentos unilaterales sin soporte contractual. "
        "Se solicita el levantamiento inmediato de la objeción.</p>"
        "<div>Nota: Generado con asistencia de IA</div>"
    )

    def test_el_html_del_dictamen_no_llega_a_la_casilla(self):
        from app.services.salud_total_ia import _condensar

        salida = _condensar(self.HTML_REAL)
        assert "<" not in salida and ">" not in salida, salida[:120]
        assert "border-collapse" not in salida
        assert "padding:10px" not in salida

    def test_lo_que_queda_es_el_argumento(self):
        from app.services.salud_total_ia import _condensar

        salida = _condensar(self.HTML_REAL)
        assert "S-13-1-03-1-04958" in salida, "se perdió el argumento"
        assert salida.startswith("ESE HUS NO ACEPTA"), salida[:60]

    def test_no_arrastra_el_pie_de_pagina(self):
        """«Generado con asistencia de IA» no tiene por qué viajar a la EPS."""
        from app.services.salud_total_ia import _condensar

        assert "asistencia de IA" not in _condensar(self.HTML_REAL)

    def test_si_el_dictamen_es_puro_html_esa_fila_cae_a_plantilla(self, client, monkeypatch):
        """Guarda dura: antes que mandar etiquetas a la entidad, se prefiere
        la plantilla, que es texto probado."""
        import app.services.glosa_service as gs

        solo_tabla = '<table style="width:100%"><tr><td>x</td></tr></table>'
        monkeypatch.setattr(gs, "GlosaService", lambda *a, **k: _IAFalsa(dictamen=solo_tabla))
        d = client.post("/api/salud-total/analizar-ia", files=_archivo()).json()
        assert d["analizadas_con_ia"] == 0
        assert d["por_plantilla"] == 2
        for g in d["glosas"]:
            assert "<" not in g["Observacion_IPS"]
            assert g["Observacion_IPS"].strip()

    def test_ninguna_fila_del_archivo_lleva_etiquetas(self, client, monkeypatch):
        """La comprobación de punta a punta, sobre el archivo que se radica."""
        import app.services.glosa_service as gs

        monkeypatch.setattr(gs, "GlosaService", lambda *a, **k: _IAFalsa(dictamen=self.HTML_REAL))
        r = client.post(
            "/api/salud-total/procesar", files=_archivo(), data={"tipo_respuesta": "ia"}
        )
        assert r.status_code == 200
        assert "<table" not in r.text and "border-collapse" not in r.text
        for fila in r.text.strip().split("\n")[1:]:
            obs = fila.split("|")[-1]
            assert "<" not in obs and ">" not in obs, obs[:100]
            assert "S-13-1-03-1-04958" in obs, "se perdió el argumento en el archivo"

    def test_un_argumento_demasiado_corto_no_pasa_por_defensa(self, client, monkeypatch):
        """Tres palabras no defienden nada: mejor la plantilla completa."""
        import app.services.glosa_service as gs

        monkeypatch.setattr(
            gs, "GlosaService", lambda *a, **k: _IAFalsa(dictamen="<p>No aplica.</p>")
        )
        d = client.post("/api/salud-total/analizar-ia", files=_archivo()).json()
        assert d["analizadas_con_ia"] == 0


class TestLosPesosSeEscribenComoPesos:
    """13-08-2026. La primera versión le pasaba a la IA el número tal cual
    salía del archivo —`93340.0`— y la IA lo copiaba al dictamen. En el
    documento que se radica quedaba «FACTURADA POR $ 93340.0». Un decimal en
    un valor en pesos, en un documento legal, se lee como descuido."""

    def test_el_valor_va_con_puntos_de_mil_y_sin_decimales(self):
        from app.services.salud_total_ia import _pesos

        assert _pesos(93340.0) == "$93.340"
        assert _pesos(1589100) == "$1.589.100"
        assert _pesos(729.0) == "$729"

    def test_un_valor_vacio_no_revienta(self):
        from app.services.salud_total_ia import _pesos

        assert _pesos(None) == "$0"
        assert _pesos("") == "$0"

    def test_el_texto_que_lee_la_ia_no_lleva_decimales(self):
        from app.services.salud_total_ia import _texto_de_la_glosa

        texto = _texto_de_la_glosa({"ValorTotalServ": 280000.0, "ValorGlosaTotalxServ": 93340.0})
        assert "$93.340" in texto
        assert "$280.000" in texto
        assert "93340.0" not in texto, "el decimal se le está pasando a la IA"

    def test_se_distingue_lo_facturado_de_lo_objetado(self):
        """Son dos cifras distintas y el dictamen no las puede confundir: el
        servicio se facturó por $280.000 y la entidad objetó $93.340."""
        from app.services.salud_total_ia import _texto_de_la_glosa

        texto = _texto_de_la_glosa({"ValorTotalServ": 280000.0, "ValorGlosaTotalxServ": 93340.0})
        assert "VALOR FACTURADO DEL SERVICIO: $280.000" in texto
        assert "VALOR OBJETADO POR LA ENTIDAD: $93.340" in texto
