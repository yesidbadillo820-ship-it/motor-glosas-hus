"""El validador ADRES y el buscador de autorizaciones, dentro del portal.

OT-031 · 13-08-2026. Las dos herramientas vivían fuera de la página: el
validador como una aplicación aparte en el puerto 8010 que hay que levantar
con un doble clic, y el buscador de autorizaciones como bot de escritorio.
Yesid pidió que vivan DENTRO del portal — donde el equipo ya está trabajando
y donde ya hay sesión, roles y registro.

Lo que estas pruebas fijan, además de que funcione:

  · **Que pidan sesión.** Por acá entran soportes con historia clínica. Sin
    control de rol, cualquiera con la URL sube y descarga.
  · **Que un ZIP no pueda escribir fuera de su carpeta.** Un ZIP con rutas
    tipo `../../` (zip-slip) es la forma clásica de sacar archivos de donde
    deben quedar, y al validador llegan ZIP del servidor de facturación.
  · **Que el trabajo pesado no bloquee.** Validar un paquete grande tarda
    minutos: la subida responde de una con un identificador y el navegador
    pregunta por él.
"""

from __future__ import annotations

import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app

AUT = "4724500503082"


@pytest.fixture
def cliente():
    return TestClient(app)


def _rips_json(sin_autorizacion: int = 3) -> bytes:
    datos = {
        "numDocumentoIdObligado": "900006037",
        "numFactura": "HUS544245",
        "usuarios": [
            {
                "servicios": {
                    "consultas": [{"codConsulta": "890201", "numAutorizacion": AUT}],
                    "medicamentos": [
                        {"codTecnologiaSalud": f"MED{i}", "numAutorizacion": None}
                        for i in range(sin_autorizacion)
                    ],
                }
            }
        ],
    }
    return json.dumps(datos, ensure_ascii=False).encode("utf-8")


class TestSinSesionNoSePasa:
    """Por acá entran soportes con historia clínica."""

    def test_validar_exige_sesion(self, cliente):
        r = cliente.post(
            "/validador-adres/validar",
            files=[("archivos", ("FURIPS1.txt", b"x", "text/plain"))],
        )
        assert r.status_code in (401, 403), r.status_code

    def test_estado_exige_sesion(self, cliente):
        assert cliente.get("/validador-adres/estado/loquesea").status_code in (401, 403)

    def test_excel_exige_sesion(self, cliente):
        assert cliente.get("/validador-adres/excel/loquesea").status_code in (401, 403)

    def test_autorizaciones_exige_sesion(self, cliente):
        r = cliente.post(
            "/validador-adres/autorizaciones",
            files=[("archivos", ("RIPS.json", _rips_json(), "application/json"))],
        )
        assert r.status_code in (401, 403), r.status_code


class TestElZipNoPuedeEscribirFuera:
    """zip-slip: un ZIP con rutas `../../` sacaría archivos de la carpeta del
    trabajo. Al validador llegan ZIP del servidor de facturación."""

    def test_las_entradas_que_se_salen_se_descartan(self, tmp_path):
        from app.services.validador_adres_service import extraer_zip_seguro

        malo = tmp_path / "malo.zip"
        with zipfile.ZipFile(malo, "w") as zf:
            zf.writestr("../../fuera.txt", "no deberia salir")
            zf.writestr("adentro/bien.txt", "esto si")
        destino = tmp_path / "trabajo"
        destino.mkdir()
        n = extraer_zip_seguro(malo, destino)
        assert n == 1, "se extrajo la entrada que se salía de la carpeta"
        assert (destino / "adentro" / "bien.txt").exists()
        assert not (tmp_path.parent / "fuera.txt").exists()
        assert not (tmp_path / "fuera.txt").exists()

    def test_un_zip_normal_se_extrae_completo(self, tmp_path):
        from app.services.validador_adres_service import extraer_zip_seguro

        z = tmp_path / "bueno.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("FURIPS1.txt", "linea")
            zf.writestr("sub/FURIPS2.txt", "linea")
        destino = tmp_path / "t"
        destino.mkdir()
        assert extraer_zip_seguro(z, destino) == 2


class TestQueSeAceptaSubir:
    def test_solo_las_extensiones_del_tramite(self):
        from app.services.validador_adres_service import extension_permitida

        for buena in ("FURIPS1.txt", "lote.zip", "RIPS.json", "factura.xml", "epicrisis.pdf"):
            assert extension_permitida(buena), buena
        for mala in ("virus.exe", "macro.docm", "script.bat", "sin_extension"):
            assert not extension_permitida(mala), mala


class TestElTrabajoEnSegundoPlano:
    """Validar un paquete grande tarda minutos: la subida no puede quedarse
    esperando a que termine."""

    def test_crear_trabajo_da_id_y_carpeta(self):
        from app.services.validador_adres_service import crear_trabajo, estado

        trabajo_id, carpeta = crear_trabajo()
        assert trabajo_id and carpeta.exists()
        assert estado(trabajo_id)["estado"] == "EN_COLA"

    def test_un_trabajo_que_no_existe_no_revienta(self):
        from app.services.validador_adres_service import estado

        assert estado("noexiste") is None

    def test_sin_furips_el_trabajo_lo_dice_en_palabras(self, tmp_path):
        """El auditor tiene que entender qué le faltó subir."""
        from app.services.validador_adres_service import correr_validacion, crear_trabajo, estado

        trabajo_id, carpeta = crear_trabajo()
        (carpeta / "cualquier.txt").write_text("nada que ver", encoding="utf-8")
        correr_validacion(trabajo_id, carpeta)
        tr = estado(trabajo_id)
        assert tr["estado"] == "ERROR"
        assert "FURIPS" in tr["mensaje"]

    def test_un_fallo_del_motor_no_tumba_el_servidor(self, tmp_path, monkeypatch):
        from app.services import validador_adres_service as vas

        trabajo_id, carpeta = vas.crear_trabajo()

        class _Roto:
            def __getattr__(self, _n):
                raise RuntimeError("motor caído")

        monkeypatch.setattr(vas, "_motor", lambda: _Roto())
        vas.correr_validacion(trabajo_id, carpeta)  # no debe propagar
        assert vas.estado(trabajo_id)["estado"] == "ERROR"

    def test_no_se_acumulan_trabajos_sin_fin(self):
        """Cada trabajo guarda el paquete subido: sin límite, el disco del PC
        de cartera se llena."""
        from app.services import validador_adres_service as vas

        for _ in range(vas.MAX_TRABAJOS_VIVOS + 5):
            vas.crear_trabajo()
        assert len(vas._trabajos) <= vas.MAX_TRABAJOS_VIVOS

    def test_se_borran_las_carpetas_de_arranques_anteriores(self, monkeypatch):
        """El motor del hospital se reinicia a diario y la memoria de
        trabajos vuelve a cero, pero las carpetas con los paquetes subidos
        siguen en disco. Sin este barrido no se borraban nunca."""
        import os
        import time

        from app.services import validador_adres_service as vas

        huerfana = vas.DIR_TRABAJOS / "de_un_arranque_viejo"
        huerfana.mkdir(parents=True, exist_ok=True)
        (huerfana / "paquete.zip").write_bytes(b"x" * 1024)
        viejo = time.time() - (vas.HORAS_HUERFANO + 1) * 3600
        os.utime(huerfana, (viejo, viejo))

        vas._limpiar_viejos()
        assert not huerfana.exists(), "la carpeta huérfana sobrevivió al barrido"

    def test_una_carpeta_reciente_no_se_toca(self):
        """Un trabajo en curso de otro usuario no se puede borrar."""
        from app.services import validador_adres_service as vas

        reciente = vas.DIR_TRABAJOS / "recien_creada"
        reciente.mkdir(parents=True, exist_ok=True)
        vas._limpiar_viejos()
        assert reciente.exists()


class TestLasRutasEstanMontadas:
    def test_las_cuatro_existen(self):
        rutas = {getattr(r, "path", "") for r in app.routes}
        for esperada in (
            "/validador-adres/validar",
            "/validador-adres/estado/{trabajo_id}",
            "/validador-adres/excel/{trabajo_id}",
            "/validador-adres/autorizaciones",
        ):
            assert esperada in rutas, esperada

    def test_el_portal_y_la_app_aparte_comparten_el_codigo(self):
        """Si cada una tuviera su copia, una corrección habría que hacerla
        dos veces y tarde o temprano dirían cosas distintas de la misma
        factura."""
        import inspect

        from app.api.routers import validador_adres

        src = inspect.getsource(validador_adres)
        assert "validador_adres_service" in src
        assert "def correr_validacion" not in src, "la orquestación se duplicó en el router"
