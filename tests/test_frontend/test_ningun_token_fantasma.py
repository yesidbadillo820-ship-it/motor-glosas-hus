"""Ningún color puede apuntar a un token que no existe (24-08-2026).

EL CASO QUE LO DESTAPÓ. El botón «Aplicar a las marcadas» del lote de glosas
ADRES salió **invisible** en el PC de cartera: letra blanca sobre fondo
blanco. Su estilo decía `background:var(--primary)`… y `--primary` no existe
en el portal — el token era inventado, el fondo quedó transparente, y el
botón desapareció justo cuando las auditoras empezaron a usar la función.

Al barrer el archivo completo aparecieron SIETE tokens fantasma en 65 sitios
(`--text-3` por `--text3`, `--bg2` por `--bg-card`, `--r-sm` por `--r`…):
textos y fondos que se estaban pintando con el color heredado por accidente,
no con el del diseño.

REGLA: un `var(--x)` sin valor de respaldo debe apuntar a un token definido
en el propio archivo, en sinac-ds.css, o puesto por JavaScript
(`setProperty`). Con respaldo —`var(--x, #fff)`— se permite: degrada bien.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "static"
ARCHIVOS = [STATIC / "index.html", STATIC / "sinac-ds.css", STATIC / "sinac-ux.js"]


def _texto(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _definidos() -> set[str]:
    tokens: set[str] = set()
    for p in ARCHIVOS:
        t = _texto(p)
        tokens |= set(re.findall(r"(--[A-Za-z0-9-]+)\s*:", t))
        tokens |= set(re.findall(r"setProperty\(\s*['\"](--[A-Za-z0-9-]+)", t))
    return tokens


def _usados_sin_respaldo() -> dict[str, int]:
    usos: dict[str, int] = {}
    for p in ARCHIVOS:
        for token in re.findall(r"var\(\s*(--[A-Za-z0-9-]+)\s*\)", _texto(p)):
            usos[token] = usos.get(token, 0) + 1
    return usos


class TestNingunTokenFantasma:
    def test_todo_var_sin_respaldo_apunta_a_algo_que_existe(self):
        definidos = _definidos()
        fantasmas = {t: n for t, n in _usados_sin_respaldo().items() if t not in definidos}
        assert not fantasmas, (
            f"Tokens usados sin respaldo y jamás definidos: {fantasmas}. "
            f"El elemento se pinta transparente o con el color heredado — así "
            f"quedó invisible el botón del lote de glosas ADRES. Use un token "
            f"de la paleta real o agregue un valor de respaldo."
        )

    def test_la_paleta_real_sigue_existiendo(self):
        """Si alguien renombra la paleta entera, la prueba de arriba pasaría
        con el portal en blanco. Los tokens de siempre tienen que estar."""
        definidos = _definidos()
        for esencial in ("--text3", "--bg-card", "--border", "--c-blue", "--c-red", "--r"):
            assert esencial in definidos, f"desapareció {esencial} de la paleta"

    def test_el_boton_del_lote_quedo_con_color_de_verdad(self):
        """El caso concreto que lo destapó, para que no regrese."""
        t = _texto(STATIC / "index.html")
        i = t.index("Aplicar a las marcadas")
        contexto = t[max(0, i - 400) : i]
        assert "var(--primary)" not in contexto
        assert "var(--c-blue)" in contexto
