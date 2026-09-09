"""El diagnóstico de calidad tiene que verse SIN abrir una terminal.

09-09-2026. El auditor preguntó por qué la confianza de los dictámenes no
sube del 40%. La respuesta solo se puede dar con los números de la base de
datos real del hospital, así que el día anterior se publicó la ruta
`/admin/diagnostico-calidad`.

QUÉ SALIÓ MAL. Él escribió esa dirección en el navegador y lo único que
apareció fue:

    {"detail":"Token de autenticación requerido"}

Y es correcto que aparezca: la ruta exige el token de la sesión, y el
navegador —escribiendo la URL a mano— no lo manda. O sea que la ruta
existía pero era inalcanzable para la única persona que la necesitaba.

QUÉ CUIDA ESTA PRUEBA. Que el diagnóstico esté dentro del motor, en una
pantalla que ya tiene la sesión iniciada: que exista el panel, que el botón
llame a la función, que la función pida la ruta CON el token, que si falla
lo diga en pantalla (y no solo en la consola, que el auditor no abre nunca),
y que el panel sea solo para SUPER_ADMIN.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"


def _pagina() -> str:
    return INDEX.read_text(encoding="utf-8")


def _funcion(nombre: str, texto: str) -> str:
    """El cuerpo de una función del `index.html`, hasta la siguiente."""
    ini = texto.index(f"function {nombre}(")
    sig = texto.find("\nfunction ", ini + 1)
    return texto[ini : sig if sig != -1 else ini + 4000]


def test_el_panel_del_diagnostico_existe_en_la_pantalla():
    pagina = _pagina()
    assert 'id="admin-diagnostico-card"' in pagina, (
        "No existe el panel del diagnóstico de calidad. Sin él, la única forma de "
        "ver esos números es escribir /admin/diagnostico-calidad en el navegador, "
        "que responde «Token de autenticación requerido»."
    )
    assert "cargarDiagnosticoCalidad()" in pagina, (
        "El panel existe pero ningún botón llama a cargarDiagnosticoCalidad()."
    )


def test_el_diagnostico_se_pide_con_el_token_de_la_sesion():
    cuerpo = _funcion("cargarDiagnosticoCalidad", _pagina())
    assert "/admin/diagnostico-calidad" in cuerpo, (
        "cargarDiagnosticoCalidad no pide la ruta del diagnóstico."
    )
    assert "authH()" in cuerpo, (
        "La petición va SIN el token de la sesión. Así el servidor contesta "
        "«Token de autenticación requerido», que es exactamente el error que "
        "esta pantalla vino a resolver."
    )


def test_si_el_diagnostico_no_carga_se_dice_en_pantalla():
    cuerpo = _funcion("cargarDiagnosticoCalidad", _pagina())
    assert "catch" in cuerpo, "cargarDiagnosticoCalidad no maneja el fallo de red."
    # El aviso tiene que quedar en la caja de la pantalla, no solo en la consola.
    assert cuerpo.count("diag-calidad-salida") >= 1
    tras_el_catch = cuerpo[cuerpo.index("catch") :]
    assert "caja.innerHTML" in tras_el_catch, (
        "Cuando falla, no escribe nada en la pantalla. Un catch que solo llama a "
        "console.error deja al auditor mirando un panel vacío sin saber por qué."
    )
    # Y también cuando el servidor contesta con error, no solo cuando cae la red.
    assert "r.ok" in cuerpo, (
        "No revisa si el servidor contestó con error (403, 500…): con `fetch`, un "
        "503 no lanza excepción, así que sin este chequeo el fallo pasa callado."
    )


def test_el_panel_del_diagnostico_es_solo_para_super_admin():
    pagina = _pagina()
    # Nace oculto en el marcado…
    m = re.search(r'id="admin-diagnostico-card"[^>]*style="([^"]*)"', pagina)
    assert m and "display:none" in m.group(1).replace(" ", ""), (
        "El panel del diagnóstico no nace oculto: un auditor sin rol lo vería "
        "durante el instante previo a que el JavaScript lo esconda."
    )
    # …y solo lo destapa el rol SUPER_ADMIN.
    cuerpo = _funcion("loadUsuarios", pagina)
    assert "admin-diagnostico-card" in cuerpo, (
        "Nadie muestra el panel del diagnóstico: quedaría oculto para todos."
    )
    linea = next(ln for ln in cuerpo.splitlines() if "diagCard.style.display" in ln)
    assert "SUPER_ADMIN" in linea, (
        "El panel se muestra sin comprobar el rol. La ruta es solo de "
        "SUPER_ADMIN: cualquier otro vería un botón que siempre da error."
    )
