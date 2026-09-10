"""Lo que el motor le entrega al navegador, y lo que no le entrega a nadie.

09-09-2026, hallazgos verificados de los dos análisis de código del auditor.
Cuatro cosas que no rompían nada hoy pero dejaban la puerta entornada.

**1 · Cero cabeceras de seguridad.** No estaban mal configuradas: no
existían. Cada una tapa una forma concreta de atacar a quien tiene la sesión
abierta, y todas se resuelven pidiéndoselo al navegador.

**2 · `/docs` y `/redoc` abiertos.** Publicaban el mapa completo del motor
—cada ruta, cada parámetro— sin pedir contraseña. Todo lo de adentro sigue
exigiendo token, así que no es una brecha por sí sola; es el plano del
edificio pegado en la puerta.

**3 · Fragmentos de claves en el registro.** «OK sk-ant-api03…»: diez
caracteres no alcanzan para usar la clave, pero dicen de qué proveedor y de
qué tipo es, y le ahorran la mitad del trabajo a quien tenga una copia
parcial. Una credencial no se publica «un poquito».

**4 · El contenedor como root.** Si alguna vez se logra ejecutar algo
adentro, con root ese algo escribe donde quiera.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


class TestLasCabecerasQueProtegenAlAuditor:
    @pytest.mark.parametrize(
        "cabecera,valor,por_que",
        [
            (
                "X-Frame-Options",
                "DENY",
                "sin esto, el portal se puede meter en un iframe ajeno y "
                "robarle un clic al auditor con la sesión abierta",
            ),
            (
                "X-Content-Type-Options",
                "nosniff",
                "sin esto, un PDF de soportes con contenido raro puede "
                "terminar interpretado como página",
            ),
            (
                "Referrer-Policy",
                "strict-origin-when-cross-origin",
                "las URLs del motor llevan números de factura y de glosa",
            ),
        ],
    )
    def test_van_en_toda_respuesta(self, client, cabecera, valor, por_que):
        r = client.get("/health")
        assert r.headers.get(cabecera) == valor, f"Falta {cabecera}: {por_que}."

    def test_se_apagan_los_permisos_que_el_motor_no_usa(self, client):
        """Cámara, micrófono y ubicación: si no se usan, que no se puedan
        ni pedir."""
        permisos = client.get("/health").headers.get("Permissions-Policy", "")
        for p in ("camera=()", "microphone=()", "geolocation=()"):
            assert p in permisos, permisos

    def test_van_tambien_en_las_respuestas_de_error(self, client):
        """Una respuesta de error es una respuesta igual: si las cabeceras
        solo salieran en el camino feliz, no protegerían de nada."""
        r = client.get("/una-ruta-que-no-existe")
        assert r.status_code == 404
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_HSTS_solo_sobre_https(self, client):
        """Mandarlo en HTTP rompería el desarrollo local: el navegador se
        negaría a volver a entrar sin cifrado."""
        assert "Strict-Transport-Security" not in client.get("/health").headers

    def test_HSTS_si_va_sobre_https(self):
        from app.main import app

        with TestClient(app, base_url="https://motor.local") as c:
            hsts = c.get("/health").headers.get("Strict-Transport-Security", "")
        assert "max-age=31536000" in hsts and "includeSubDomains" in hsts


class TestLaDocumentacionDeLaApi:
    def test_apagada_por_defecto(self):
        """Lo seguro tiene que ser lo que pasa cuando nadie configura nada."""
        from app.core.config import Settings

        assert Settings.model_fields["docs_publicos"].default is False

    def test_no_se_sirve_cuando_esta_apagada(self, client):
        for ruta in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(ruta).status_code == 404, ruta

    def test_se_puede_encender_para_desarrollar(self):
        """Apagarla no puede significar perderla: en desarrollo hace falta."""
        import inspect

        from app import main

        fuente = inspect.getsource(main)
        assert "cfg.docs_publicos" in fuente


class TestLasClavesNoSeLoguean:
    def test_solo_se_dice_si_esta_o_no(self):
        from app.core.logging_utils import clave_para_log

        salida = clave_para_log("sk-ant-api03-ZZZZZZZZZZZZZZZZ")
        assert salida == "CONFIGURADA"
        assert "sk-ant" not in salida

    @pytest.mark.parametrize("vacia", ["", None, "   "])
    def test_la_ausencia_tambien_se_dice(self, vacia):
        from app.core.logging_utils import clave_para_log

        assert clave_para_log(vacia) == "AUSENTE"

    def test_no_queda_ningun_recorte_de_clave_en_el_codigo(self):
        """La forma exacta que había: `key[:10]`, `api_key[:8]`."""
        import re

        sospechosos = []
        for f in (RAIZ / "app").rglob("*.py"):
            for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if ln.lstrip().startswith("#"):
                    continue
                # `cache_key` / `clave_cache` NO son credenciales: son
                # índices ya derivados. Se excluyen por nombre, no por
                # criterio, para que la regla siga siendo estricta.
                if re.search(r"\b(?:cache_key|clave_cache)\b", ln):
                    continue
                if re.search(r"(?:api_)?key\w*\[:\d+\]|_(?:ant|gem|grq)\[:\d+\]", ln, re.I):
                    sospechosos.append(f"{f.relative_to(RAIZ)}:{i}  {ln.strip()[:70]}")
        assert not sospechosos, "Se está logueando un pedazo de credencial:\n" + "\n".join(
            sospechosos
        )


class TestElContenedorNoCorreComoRoot:
    DOCKERFILE = (RAIZ / "Dockerfile").read_text(encoding="utf-8")

    def test_se_crea_un_usuario_propio(self):
        assert "useradd" in self.DOCKERFILE

    def test_y_se_cambia_a_el_antes_del_arranque(self):
        i_user = self.DOCKERFILE.index("USER motor")
        i_cmd = self.DOCKERFILE.index('CMD ["uvicorn"')
        assert i_user < i_cmd, "El USER va después del CMD: no aplica."

    def test_las_carpetas_que_el_motor_escribe_le_pertenecen(self):
        """`/data` es donde se monta el volumen de los soportes: sin el
        chown, el motor arranca y no puede guardar un solo PDF."""
        assert "chown -R motor:motor /app /data" in self.DOCKERFILE
