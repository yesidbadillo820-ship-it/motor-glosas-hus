"""Una tecla que llega vacía no puede reventar la pantalla.

09-09-2026. En la consola del auditor, al entrar al portal, salía dos veces
seguidas:

    sinac-ux.js:216 Uncaught TypeError:
    Cannot read properties of undefined (reading 'toLowerCase')

Lo dispara el gestor de contraseñas del navegador: al autocompletar usuario y
clave lanza eventos de tecla **sin la tecla** (`e.key` viene vacío), y el
manejador de atajos hacía `e.key.toLowerCase()` a secas. Lo mismo pasa con
los teclados que componen caracteres (acentos, emoji).

Dos veces = una por cada campo que autocompletó.

No tumbaba la pantalla, pero sí apagaba TODOS los atajos en ese evento y
dejaba dos errores rojos en la consola — que es exactamente donde uno mira
cuando algo va mal, y ahí estorban para encontrar el problema de verdad.

QUÉ CUIDA ESTA PRUEBA. Que se compruebe la tecla antes de usarla, en los dos
sitios donde se llamaba a `.toLowerCase()`, y que los atajos sigan
funcionando cuando la tecla sí viene.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
UX = RAIZ / "static" / "sinac-ux.js"


@pytest.fixture(autouse=True)
def _hay_node():
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")


def test_el_archivo_compila():
    r = subprocess.run(
        ["node", "--check", str(UX)], capture_output=True, text=True, timeout=30, check=False
    )
    assert r.returncode == 0, r.stderr


def test_ya_no_se_llama_toLowerCase_sobre_la_tecla_sin_mirar():
    """La forma exacta que reventaba: `e.key.toLowerCase()` a pelo.

    Usarlo NO está prohibido; lo que no puede es ir sin comprobar antes que
    la tecla sea texto. Por eso se revisa renglón por renglón en vez de
    buscar la cadena en todo el archivo: el propio arreglo la contiene, ya
    comprobada, y una prueba que la prohibiera del todo obligaría a escribir
    el arreglo de forma retorcida para esquivarla.
    """
    sueltas = [
        (i, ln.strip())
        for i, ln in enumerate(UX.read_text(encoding="utf-8").splitlines(), 1)
        if "e.key.toLowerCase()" in ln and "typeof e.key === 'string'" not in ln
    ]
    assert not sueltas, (
        "Hay `e.key.toLowerCase()` sin comprobar la tecla. Con el "
        "autocompletado del navegador, `e.key` llega vacío y revienta:\n"
        + "\n".join(f"  sinac-ux.js:{i}  {ln}" for i, ln in sueltas)
    )


def test_se_comprueba_que_la_tecla_sea_texto():
    fuente = UX.read_text(encoding="utf-8")
    assert "typeof e.key === 'string'" in fuente, (
        "No se comprueba el tipo de la tecla antes de usarla."
    )


def test_sin_tecla_el_manejador_se_sale_temprano():
    """No basta con no reventar: sin tecla no hay atajo que buscar, y seguir
    adelante solo da oportunidades de fallar más abajo."""
    fuente = UX.read_text(encoding="utf-8")
    i = fuente.index("typeof e.key === 'string'")
    assert "if (!tecla) return;" in fuente[i : i + 200]


def test_el_evento_del_autocompletado_ya_no_revienta(tmp_path):
    """La prueba de verdad: se dispara el mismo evento que manda el gestor de
    contraseñas —sin `key`— contra el manejador real."""
    guion = tmp_path / "prueba.mjs"
    guion.write_text(
        """
const errores = [];
// Un navegador de mentiras, lo mínimo que toca el módulo.
const handlers = [];
globalThis.document = {
  addEventListener: (tipo, fn) => { if (tipo === 'keydown') handlers.push(fn); },
  activeElement: { tagName: 'BODY' },
  body: { classList: { contains: () => false } },
  querySelector: () => null, querySelectorAll: () => [],
  createElement: () => ({ style:{}, classList:{add(){},remove(){},contains(){return false}},
    appendChild(){}, addEventListener(){}, setAttribute(){}, remove(){} }),
  getElementById: () => null,
  readyState: 'complete',
};
globalThis.window = { addEventListener(){}, location:{ hash:'' }, matchMedia: () => ({matches:false, addEventListener(){}}) };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.navigator = { platform: 'Linux' };

await import(process.argv[2]);

if (!handlers.length) { console.log('SIN_MANEJADOR'); process.exit(0); }

// 1) El evento del gestor de contraseñas: SIN `key`.
for (const fn of handlers) {
  try { fn({ metaKey:false, ctrlKey:false, altKey:false, preventDefault(){} }); }
  catch (e) { errores.push('sin key: ' + e.message); }
  // 2) Y con `key` en null, que es la otra forma en que llega.
  try { fn({ key:null, metaKey:false, ctrlKey:false, altKey:false, preventDefault(){} }); }
  catch (e) { errores.push('key null: ' + e.message); }
  // 3) Con una tecla de verdad: tiene que seguir funcionando.
  try { fn({ key:'Escape', metaKey:false, ctrlKey:false, altKey:false, preventDefault(){} }); }
  catch (e) { errores.push('key Escape: ' + e.message); }
}
console.log(errores.length ? 'REVENTO: ' + errores.join(' | ') : 'OK');
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["node", str(guion), str(UX)], capture_output=True, text=True, timeout=30, check=False
    )
    salida = (r.stdout + r.stderr).strip()
    if "SIN_MANEJADOR" in salida:
        pytest.skip("el módulo no registró el manejador en este entorno de mentiras")
    assert "REVENTO" not in salida, (
        "El manejador de atajos sigue reventando con un evento sin tecla — "
        f"el mismo que manda el autocompletado del navegador.\n{salida}"
    )
    assert "Cannot read properties" not in salida, salida
