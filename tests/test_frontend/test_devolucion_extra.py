"""«Excepción al tope de 3 devoluciones» en la pantalla (07-09-2026).

Caso HUS315614: coordinación necesitó autorizar una cuarta devolución. El
backend ya lo permite con testigo; esta prueba fija que la PANTALLA:

  · muestra el botón SOLO a coordinación/admin y SOLO cuando ya se agotó el
    cupo (`limite && ES_ADMIN`),
  · manda el motivo al endpoint correcto,
  · no deja autorizar sin motivo.
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


class TestElBoton:
    def test_solo_para_coordinacion_y_solo_en_el_tope(self):
        """No puede salirle al auditor, ni antes de agotar el cupo."""
        js = _script()
        assert "autorizarDevolucionExtra(" in js
        # El botón se pinta condicionado a (limite && ES_ADMIN).
        assert re.search(r"limite\s*&&\s*ES_ADMIN", js), "el botón no está gateado por rol y tope"

    def test_el_boton_llama_a_la_funcion(self):
        assert "onclick=\"autorizarDevolucionExtra('+f.id+')\"" in TEXTO


class TestLaFuncion:
    def _cuerpo(self) -> str:
        m = re.search(r"async function autorizarDevolucionExtra\(id\)\{(.*?)\n\}", _script(), re.S)
        assert m, "no existe autorizarDevolucionExtra"
        return m.group(1)

    def test_manda_al_endpoint_correcto(self):
        cuerpo = self._cuerpo()
        assert "/autorizar-devolucion-extra" in cuerpo
        assert "method:'POST'" in cuerpo
        assert "motivo" in cuerpo

    def test_no_autoriza_sin_motivo(self):
        """El motivo es el testigo de la excepción: sin él no se manda."""
        cuerpo = self._cuerpo()
        # Corta si el motivo queda vacío (return antes del fetch).
        assert re.search(r"if\(!motivo\)\{[^}]*return", cuerpo)

    def test_refresca_la_ventana_al_terminar(self):
        assert "abrirAuditar(id)" in self._cuerpo()


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
