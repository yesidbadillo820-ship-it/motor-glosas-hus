"""En la ventana de auditar se ve el plazo del ADRES y los reparos de fechas.

08-09-2026. La revisión se pide APARTE de la factura y sin esperarla: leer el
RIPS toca el servidor de facturación electrónica y la ventana tiene que abrir
ya. Lo que se prueba acá es la función real de pintado (`atencionHtml`),
ejecutada en Node contra la página de verdad.

Lo importante del criterio:
  · una cuenta prescrita se ve en rojo y con qué hacer;
  · una por vencer, en amarillo;
  · a una factura que NO es del ADRES no se le pinta nada;
  · el texto del gestor y del servidor va escapado (nadie inyecta HTML).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = RAIZ / "static" / "preauditoria.html"
TEXTO = PAGINA.read_text(encoding="utf-8")


def _script() -> str:
    return "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", TEXTO, re.S))


def _fuente_de(nombre: str) -> str:
    m = re.search(r"function " + nombre + r"\([^)]*\)\s*\{", _script())
    assert m, f"no existe la función {nombre}"
    fin = re.search(r"\n\}\n", _script()[m.end() :])
    assert fin, f"no se encontró el cierre de {nombre}"
    return _script()[m.start() : m.end() + fin.end()]


def _pintar(dictamen: dict) -> str:
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    guion = "%s\n%s\n%s\nconsole.log(JSON.stringify(atencionHtml(%s)));" % (
        _fuente_de("esc"),
        _fuente_de("fDia"),
        _fuente_de("atencionHtml"),
        json.dumps(dictamen, ensure_ascii=False),
    )
    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"la función falló:\n{r.stderr[:600]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _dictamen(**cambios) -> dict:
    base = {
        "factura": "HUS0000556635",
        "aplica": True,
        "motivo": "",
        "fechas": {
            "fecha_ingreso": "2024-03-10T08:00:00",
            "fecha_egreso": "2024-03-25T14:00:00",
            "tipo_atencion": "HOSPITALIZACION",
            "completas": True,
        },
        "prescripcion": None,
        "hallazgos": [],
        "hay_reparos_graves": False,
    }
    base.update(cambios)
    return base


class TestElPlazo:
    def test_una_cuenta_prescrita_sale_en_rojo_y_dice_que_hacer(self):
        html = _pintar(
            _dictamen(
                prescripcion={
                    "estado": "PRESCRITA",
                    "resumen": "Prescrita: el egreso fue el 25/03/2024 y el plazo de 18 meses "
                    "venció el 25/09/2025, hace 348 días.",
                }
            )
        )
        assert "aviso-err" in html
        assert "Cuenta prescrita" in html
        assert "25/09/2025" in html
        assert "coordinación" in html  # le dice al gestor qué hacer

    def test_una_por_vencer_sale_en_amarillo(self):
        html = _pintar(
            _dictamen(
                prescripcion={
                    "estado": "POR_VENCER",
                    "resumen": "Por vencer: quedan 12 días (8 hábiles).",
                }
            )
        )
        assert "aviso-warn" in html and "Por vencer" in html
        assert "aviso-err" not in html

    def test_una_vigente_sale_en_verde_y_sin_alarma(self):
        html = _pintar(
            _dictamen(
                prescripcion={"estado": "VIGENTE", "resumen": "Vigente: vence el 10/12/2027."}
            )
        )
        assert "aviso-ok" in html
        assert "aviso-err" not in html and "aviso-warn" not in html


class TestLosReparos:
    def test_un_reparo_grave_sale_primero_y_en_rojo(self):
        html = _pintar(
            _dictamen(
                hay_reparos_graves=True,
                hallazgos=[
                    {"codigo": "X", "gravedad": "ADVIERTE", "mensaje": "algo menor"},
                    {"codigo": "Y", "gravedad": "GRAVE", "mensaje": "la factura es anterior"},
                ],
            )
        )
        assert html.index("la factura es anterior") < html.index("algo menor")
        assert "aviso-err" in html

    def test_un_aviso_informativo_no_se_pinta_como_alarma(self):
        html = _pintar(
            _dictamen(
                hallazgos=[
                    {
                        "codigo": "SIN_FECHAS_DECLARADAS",
                        "gravedad": "INFORMA",
                        "mensaje": "nadie contrastó",
                    }
                ]
            )
        )
        assert "nadie contrastó" in html
        assert "aviso-err" not in html and "aviso-warn" not in html


class TestCuandoNoAplica:
    def test_a_una_factura_que_no_es_del_adres_no_se_le_pinta_nada(self):
        assert _pintar(_dictamen(aplica=False, fechas=None)) == ""

    def test_sin_dictamen_no_revienta(self):
        assert _pintar(None) == ""

    def test_sin_rips_no_se_muestran_fechas_pero_si_el_motivo(self):
        html = _pintar(
            _dictamen(
                fechas=None,
                hallazgos=[
                    {
                        "codigo": "RIPS_NO_ENCONTRADO",
                        "gravedad": "ADVIERTE",
                        "mensaje": "No se encontró el RIPS de HUS0000556635 en el servidor.",
                    }
                ],
            )
        )
        assert "No se encontró el RIPS" in html
        assert "ingreso" not in html


class TestLasFechas:
    def test_se_leen_en_formato_colombiano(self):
        html = _pintar(_dictamen())
        assert "25/03/2024" in html and "10/03/2024" in html
        assert "HOSPITALIZACION" in html

    def test_unas_fechas_incompletas_no_se_muestran_a_medias(self):
        html = _pintar(
            _dictamen(fechas={"fecha_ingreso": "2024-03-10T08:00:00", "completas": False})
        )
        assert "Según el RIPS" not in html


class TestSeguridad:
    def test_el_texto_del_servidor_va_escapado(self):
        html = _pintar(
            _dictamen(
                hallazgos=[
                    {"codigo": "X", "gravedad": "GRAVE", "mensaje": "<img src=x onerror=alert(1)>"}
                ]
            )
        )
        assert "<img" not in html
        assert "&lt;img" in html

    def test_el_resumen_del_plazo_tambien(self):
        html = _pintar(
            _dictamen(prescripcion={"estado": "VIGENTE", "resumen": "<script>malo</script>"})
        )
        assert "<script>malo" not in html
        assert "&lt;script&gt;" in html


class TestElEnganche:
    def test_la_ventana_de_auditar_trae_el_recuadro(self):
        assert "'<div id=\"au-atencion\"></div>'+" in TEXTO

    def test_se_pide_aparte_y_sin_esperar_a_la_factura(self):
        """Sin `await`: la ventana abre ya y el dato llega después."""
        assert "cargarAtencion(f.id);" in TEXTO
        assert "await cargarAtencion" not in TEXTO

    def test_usa_la_ruta_del_backend(self):
        assert "'/preauditoria/facturas/'+id+'/atencion'" in TEXTO

    def test_los_bloques_de_script_siguen_compilando(self, tmp_path):
        if not shutil.which("node"):  # pragma: no cover
            pytest.skip("node no está instalado en este entorno")
        bloques = [
            c
            for c in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", TEXTO, re.S)
            if c.strip()
        ]
        for i, cuerpo in enumerate(bloques):
            archivo = tmp_path / f"b{i}.js"
            archivo.write_text(cuerpo, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(archivo)], capture_output=True, text=True)
            assert r.returncode == 0, f"el bloque {i} no compila:\n{r.stderr}"
