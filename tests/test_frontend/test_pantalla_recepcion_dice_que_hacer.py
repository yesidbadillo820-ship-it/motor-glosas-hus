"""La pantalla de Recepción dice QUÉ HACER, no solo cuántas llegaron.

20-08-2026. Yesid: «que en la página esta recepción sea más intuitiva, sepan
qué entidad deben trabajar, cómo la deben trabajar, qué respuesta es la más
adecuada, los tiempos de radicación vs el tiempo de la notificación de la
glosa; si es médica que se trabaje en conjunto con el médico auditor; si son
extemporáneas tener cuidado; las ratificadas de una vez que salga el mensaje
de texto fijo».

Antes la pantalla mostraba cinco contadores y un semáforo. El gestor sabía que
habían llegado 90 glosas y ninguna otra cosa.

El plan lo arma el motor (`app/services/plan_de_trabajo.py`) y viaja dentro de
`por_gestor`; la pantalla solo lo pinta. Así el correo y la pantalla dicen
SIEMPRE lo mismo: si mañana cambia una regla, cambia en los dos lados.

Se corren las funciones DE VERDAD sacadas del HTML, contra los datos reales de
la importación de Yesid del 19-08.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = RAIZ / "static" / "importar-recepcion.html"


def _fuente_del_plan() -> str:
    """Saca del HTML solo el bloque del plan, sin el resto de la página."""
    if not PAGINA.exists():  # pragma: no cover
        pytest.skip("static/importar-recepcion.html no está en este entorno")
    t = PAGINA.read_text(encoding="utf-8")
    i = t.index("var COLOR_URGENCIA")
    j = t.index("document.execCommand('copy')")
    return t[i : t.index("\n}", j) + 2]


def _pintar(por_gestor: dict) -> str:
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    guion = (
        _fuente_del_plan()
        + "\nvar DOM={};"
        + "\nglobal.document={getElementById:function(id){return DOM[id]||(DOM[id]={innerHTML:''});}};"
        # `window` existe siempre en el navegador; acá hay que simularlo porque
        # el formato único de la plata vive en `window.SDS_FMT.cop`.
        + "\nglobal.window={SDS_FMT:{cop:function(v){return '$'+Math.round(Number(v||0));}}};"
        + f"\npintarPlanDeTrabajo({json.dumps({'por_gestor': por_gestor}, ensure_ascii=False)});"
        + "\nconsole.log(DOM['plan-trabajo'].innerHTML);"
    )
    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=60, encoding="utf-8"
    )
    assert r.returncode == 0, f"la pantalla falló al pintar:\n{r.stderr[:700]}"
    return r.stdout


def _glosa(**kw) -> dict:
    base = {
        "factura": "HUS0000515462",
        "eps": "COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT UVB",
        "valor": 5_724_661,
        "vence": "27/08/2026",
        "estado": "RATIFICADA",
        "causal": "TA0601",
        "plan": {
            "prioridad": 1,
            "urgencia": "PRONTO",
            "titular": "Tarifas · RATIFICADA",
            "ruta": "Se trabaja desde cartera: es administrativa/técnica.",
            "respuesta_sugerida": "Texto fijo de ratificada.",
            "avisos": [],
            "con_medico": False,
            "texto_listo": "",
        },
    }
    base.update(kw)
    return base


class TestElJavascriptDeLaPaginaCompila:
    def test_la_pagina_entera_compila(self, tmp_path):
        """Un error de sintaxis deja la pantalla sin NADA de JavaScript.
        Pasó el 20-08 en index.html y dejó el portal sin login."""
        if not shutil.which("node"):  # pragma: no cover
            pytest.skip("node no está instalado")
        t = PAGINA.read_text(encoding="utf-8")
        bloques = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", t, re.S)
        assert bloques
        for n, cuerpo in enumerate(bloques):
            f = tmp_path / f"b{n}.js"
            f.write_text(cuerpo, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            assert r.returncode == 0, f"bloque #{n + 1} no compila:\n{r.stderr[:500]}"


class TestLoQueVeElGestor:
    def test_dice_la_entidad_y_la_plata(self):
        h = _pintar({"YESID PEREZ": [_glosa()]})
        assert "COMPAÑIA MUNDIAL" in h
        # El valor tiene que estar; CÓMO se escribe lo decide el formato único
        # del portal (`window.SDS_FMT.cop`), que tiene sus propias pruebas.
        assert "5724661" in h.replace(".", "").replace(",", "")

    def test_dice_como_se_trabaja(self):
        assert "Cómo se trabaja" in _pintar({"G": [_glosa()]})

    def test_dice_que_responder(self):
        assert "Qué responder" in _pintar({"G": [_glosa()]})

    def test_muestra_la_causal(self):
        assert "TA0601" in _pintar({"G": [_glosa()]})


class TestLoUrgentePrimero:
    def test_ordena_por_prioridad(self):
        tranquila = _glosa(factura="HUS-TRANQUILA", plan={**_glosa()["plan"], "prioridad": 3})
        urgente = _glosa(factura="HUS-URGENTE", plan={**_glosa()["plan"], "prioridad": 0})
        h = _pintar({"G": [tranquila, urgente]})
        assert h.index("HUS-URGENTE") < h.index("HUS-TRANQUILA")

    def test_a_igual_prioridad_manda_la_plata(self):
        poca = _glosa(factura="HUS-POCA", valor=1000)
        mucha = _glosa(factura="HUS-MUCHA", valor=9_000_000)
        h = _pintar({"G": [poca, mucha]})
        assert h.index("HUS-MUCHA") < h.index("HUS-POCA")


class TestLasMedicas:
    def _con_medico(self):
        p = {
            **_glosa()["plan"],
            "con_medico": True,
            "ruta": "CON EL MÉDICO AUDITOR — DRA. LOPEZ. No se responde solo desde cartera.",
        }
        return _glosa(plan=p)

    def test_se_ve_que_va_con_el_medico(self):
        h = _pintar({"G": [self._con_medico()]})
        assert "MÉDICO AUDITOR" in h
        assert "DRA. LOPEZ" in h

    def test_se_distingue_a_simple_vista(self):
        """Va en rojo: no es una glosa que cartera responda sola."""
        assert "#dc2626" in _pintar({"G": [self._con_medico()]})


class TestLasRatificadas:
    def _ratificada(self):
        p = {
            **_glosa()["plan"],
            "texto_listo": "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE...",
        }
        return _glosa(plan=p)

    def test_el_texto_sale_listo_para_copiar(self):
        h = _pintar({"G": [self._ratificada()]})
        assert "ESE HUS NO ACEPTA GLOSA RATIFICADA" in h
        assert "Copiar la respuesta de ratificada" in h

    def test_una_inicial_no_muestra_ese_boton(self):
        assert "Copiar la respuesta" not in _pintar({"G": [_glosa()]})


class TestLosAvisos:
    def test_la_extemporaneidad_se_ve(self):
        p = {**_glosa()["plan"], "avisos": ["EXTEMPORÁNEA — la EPS notificó fuera del plazo."]}
        assert "EXTEMPOR" in _pintar({"G": [_glosa(plan=p)]})

    def test_los_dias_entre_radicacion_y_notificacion_se_ven(self):
        p = {
            **_glosa()["plan"],
            "avisos": ["La EPS se tomó 56 días entre la radicación y la notificación."],
        }
        assert "56 días" in _pintar({"G": [_glosa(plan=p)]})


class TestNoSeRompeConDatosRaros:
    def test_sin_glosas_no_pinta_nada(self):
        assert _pintar({}).strip() == ""

    def test_una_glosa_sin_plan_no_tumba_la_pantalla(self):
        g = _glosa()
        del g["plan"]
        assert "HUS0000515462" in _pintar({"G": [g]})

    def test_escapa_lo_que_viene_del_archivo(self):
        """El nombre de una EPS con < > no puede inyectar HTML."""
        h = _pintar({"G": [_glosa(eps="<script>alert(1)</script>")]})
        assert "<script>alert(1)</script>" not in h
        assert "&lt;script&gt;" in h
