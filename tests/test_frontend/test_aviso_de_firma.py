"""«¿Por qué me están saliendo otros auditores?» — el aviso de firma.

31-08-2026, caso real: una devolución de la HUS0000554177 quedó firmada por
LAURA DIAZ y la hizo otro gestor. El sistema firma cada movimiento con la
SESIÓN abierta en el navegador, no con quién está sentado al computador: si
alguien deja su sesión abierta, todo lo que haga el siguiente queda a su
nombre. La regla de oficina («cada uno con su usuario») ya demostró que sola
no alcanza.

El control escogido por Yesid: antes de firmar, la pantalla dice grande con
qué nombre va a quedar el movimiento y da la salida de una — «No soy yo →
cambiar de usuario». Va en los tres puntos donde se firma:

  · la ventana de auditar (radicar / devolver / dejar pendiente),
  · el paso 4, «Cargar envío» (firma el evento ESCRITA),
  · el paso 3, «Registrar oficio» (firma la recepción).
"""

from __future__ import annotations

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


class TestElAvisoExiste:
    def test_hay_una_sola_funcion_que_arma_el_aviso(self):
        """Una sola pieza: si mañana cambia el texto, cambia en los tres puntos."""
        assert _script().count("function avisoFirma(") == 1

    def test_dice_quien_va_a_firmar_y_da_la_salida(self):
        js = _script()
        assert "Quedará firmado por" in js
        assert "No soy yo" in js
        # La salida es cerrar la sesión equivocada, no un simple aviso.
        assert re.search(r"No soy yo[^<]*</a>|javascript:salir\(\)", js)

    def test_el_nombre_sale_de_la_sesion_no_de_un_texto_fijo(self):
        """Debe mostrar al dueño de la sesión: es exactamente lo que va a firmar
        el servidor, porque el nombre y el token se guardan juntos al entrar."""
        cuerpo = re.search(r"function avisoFirma\(\)\{(.*?)\n\}", _script(), re.S)
        assert cuerpo, "no existe avisoFirma()"
        assert "localStorage.getItem('hus_user')" in cuerpo.group(1)

    def test_el_nombre_se_escapa_antes_de_pintarse(self):
        cuerpo = re.search(r"function avisoFirma\(\)\{(.*?)\n\}", _script(), re.S)
        assert "esc(" in cuerpo.group(1)


class TestEstaEnLosTresPuntosQueFirman:
    def test_en_la_ventana_de_auditar(self):
        """Encima de los botones radicar / devolver / dejar pendiente."""
        abrir = re.search(r"async function abrirAuditar\(id\)\{.*?\n\}", _script(), re.S)
        assert abrir, "no existe abrirAuditar"
        assert "avisoFirma()" in abrir.group(0)
        # y ANTES de los botones de decisión, no después.
        assert abrir.group(0).index("avisoFirma()") < abrir.group(0).index("au-botones")

    def test_en_el_paso_de_cargar_envio(self):
        """El «Cargar envío» firma el evento ESCRITA (el caso de Elías)."""
        js = _script()
        idx = js.find("commitEnvio('+o.id+')\">Cargar envío")
        assert idx > 0
        assert "avisoFirma()" in js[idx : idx + 300]

    def test_en_el_registro_del_oficio(self):
        """El «Registrar oficio» firma la recepción (el caso de Vanesa y Óscar)."""
        assert 'id="of-firma"' in TEXTO
        assert re.search(r"of-firma'?\)?;?\s*if\(f\)\s*f\.innerHTML=avisoFirma\(\)", _script())


class TestSigueCompilando:
    def test_los_bloques_de_script_compilan(self, tmp_path):
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
