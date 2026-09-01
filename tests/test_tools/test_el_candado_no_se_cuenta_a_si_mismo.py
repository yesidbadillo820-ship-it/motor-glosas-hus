"""El candado del vigilante no puede contarse a sí mismo (21-08-2026, tarde).

QUÉ PASÓ. En la mañana se le puso un candado al vigilante para que no
hubiera cuatro ventanas abiertas a la vez: antes de arrancar, cuenta cuántos
procesos están corriendo `servidor_motor_local` y, si hay más de uno, el que
sobra se cierra.

La cuenta la hace una orden de PowerShell… y esa orden **lleva escrito
adentro el texto que busca**. Así que PowerShell se contaba a sí mismo:

    1 vigilante de verdad  +  1 PowerShell contando  =  2

Dos es «más de uno», así que el vigilante se cerraba SIEMPRE, incluso siendo
el único. Se reinició el PC de cartera esa tarde: el túnel subió y el motor
nunca arrancó — el portal contestó «Bad gateway 502».

POR QUÉ LAS PRUEBAS VIEJAS NO LO VIERON. Miraban que el texto del candado
estuviera escrito en el archivo. Estaba escrito. Lo que nadie probó fue la
**cuenta**, que era lo único que importaba. Estas pruebas simulan la lista de
procesos de Windows y hacen la cuenta de verdad.
"""

from __future__ import annotations

import re
from pathlib import Path

RUTA = Path(__file__).resolve().parents[2] / "tools" / "servidor_motor_local.cmd"


def _lineas_de_guardia() -> list[str]:
    texto = RUTA.read_bytes().decode("utf-8", errors="replace")
    return [ln for ln in texto.splitlines() if ln.startswith("powershell -NoProfile")]


def _filtro_de(linea: str):
    """Traduce el `Where-Object` de la línea a algo que se pueda ejecutar acá.

    Entiende las tres formas que usa el archivo: `$_.Name -eq 'x'`,
    `$_.Name -like 'x*'` y `$_.CommandLine -match 'patrón'`. PowerShell no
    distingue mayúsculas en ninguna de las tres.
    """
    bloque = re.search(r"Where-Object\s*\{(.+?)\}", linea, re.DOTALL)
    assert bloque, f"esta línea no filtra nada: {linea[:80]}"
    cuerpo = bloque.group(1)

    exige_nombre_igual = re.findall(r"\$_\.Name\s+-eq\s+'([^']+)'", cuerpo)
    exige_nombre_como = re.findall(r"\$_\.Name\s+-like\s+'([^']+)'", cuerpo)
    exige_orden = re.findall(r"\$_\.CommandLine\s+-match\s+'([^']+)'", cuerpo)

    def coincide(proceso: dict) -> bool:
        nombre = proceso["Name"]
        orden = proceso["CommandLine"]
        for esperado in exige_nombre_igual:
            if nombre.lower() != esperado.lower():
                return False
        for patron in exige_nombre_como:
            if not re.fullmatch(patron.replace("*", ".*"), nombre, re.IGNORECASE):
                return False
        for patron in exige_orden:
            if not re.search(patron, orden, re.IGNORECASE):
                return False
        return True

    return coincide


def _contar(linea: str, procesos: list[dict]) -> int:
    """Cuántos procesos ve esa línea, contándose a sí misma como haría Windows.

    Windows no esconde el proceso que pregunta: la orden de PowerShell aparece
    en la lista con su propia línea de ordenes. Por eso se agrega acá.
    """
    filtro = _filtro_de(linea)
    tabla = procesos + [{"Name": "powershell.exe", "CommandLine": linea}]
    return sum(1 for p in tabla if filtro(p))


VIGILANTE = {
    "Name": "cmd.exe",
    "CommandLine": 'cmd /c "C:\\motor-glosas\\repo\\tools\\servidor_motor_local.cmd"',
}


class TestElCandadoDelVigilante:
    """La línea 1: ¿cuántos vigilantes hay?"""

    def _linea(self) -> str:
        candados = [ln for ln in _lineas_de_guardia() if "$n -gt 1" in ln]
        assert len(candados) == 1, "debe haber un solo candado de vigilantes"
        return candados[0]

    def test_un_vigilante_solo_se_cuenta_UNA_vez(self):
        """El defecto exacto del 21-08: acá daba 2 y el motor no arrancaba."""
        assert _contar(self._linea(), [VIGILANTE]) == 1

    def test_y_por_lo_tanto_arranca(self):
        n = _contar(self._linea(), [VIGILANTE])
        assert not (n > 1), (
            "El vigilante se cierra creyendo que sobra. Con esto, al reiniciar "
            "el PC el túnel sube y el motor NO: el portal contesta 502."
        )

    def test_dos_vigilantes_si_se_notan(self):
        """El candado tiene que seguir sirviendo para lo que se hizo."""
        assert _contar(self._linea(), [VIGILANTE, dict(VIGILANTE)]) == 2

    def test_sin_ningun_vigilante_la_cuenta_es_cero(self):
        assert _contar(self._linea(), []) == 0

    def test_no_confunde_a_quien_solo_menciona_el_archivo(self):
        """Un `findstr`, un editor o la ventana del autodespliegue pueden tener
        el nombre del archivo escrito y no son vigilantes."""
        mirones = [
            {"Name": "findstr.exe", "CommandLine": "findstr servidor_motor_local"},
            {"Name": "notepad.exe", "CommandLine": "notepad tools\\servidor_motor_local.cmd"},
        ]
        assert _contar(self._linea(), [VIGILANTE] + mirones) == 1


class TestLaComprobacionDeUvicorn:
    """La línea 2: ¿ya hay un motor en el 8080?"""

    def _linea(self) -> str:
        lineas = [ln for ln in _lineas_de_guardia() if "uvicorn" in ln]
        assert len(lineas) == 1
        return lineas[0]

    def _motor(self, puerto: str) -> dict:
        return {
            "Name": "python.exe",
            "CommandLine": (
                "C:\\motor-glosas\\repo\\venv\\Scripts\\python.exe -m uvicorn "
                f"app.main:app --host 127.0.0.1 --port {puerto}"
            ),
        }

    def test_sin_motor_no_ve_ninguno(self):
        """Se salvaba de casualidad: la orden lleva escrito 'uvicorn
        app.main:app', y solo no coincidía porque el otro patrón traía `\\s+`
        en vez de un espacio de verdad. Ahora no depende de la suerte."""
        assert _contar(self._linea(), []) == 0

    def test_ve_el_motor_de_la_pagina_publica(self):
        assert _contar(self._linea(), [self._motor("8080")]) == 1

    def test_no_confunde_el_motor_de_pruebas(self):
        """El del 8000 es el de pruebas del auditor: que siga abierto no puede
        impedir que la página por internet vuelva sola."""
        assert _contar(self._linea(), [self._motor("8000")]) == 0


class TestLoQueNoSePuedePerder:
    def test_conserva_los_finales_de_linea_de_windows(self):
        b = RUTA.read_bytes()
        assert b.count(b"\r\n") > 50
        assert b.count(b"\n") == b.count(b"\r\n"), "hay saltos de línea sueltos"
