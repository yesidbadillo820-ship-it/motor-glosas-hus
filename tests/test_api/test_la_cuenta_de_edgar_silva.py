"""La cuenta de Edgar Silva se volvia a crear sola en cada arranque.

25-08-2026: los correos con las glosas a `devoluciones1@sinacsc.com` rebotaban.
La cuenta buena de Edgar Silva es `carterahus02@sinacsc.com`.

26-08: el area decidio dejar solo la buena. Pero borrarla en la pantalla de
Usuarios NO bastaba: la cuenta mala estaba SEMBRADA en el codigo de arranque
(app/main.py), asi que reaparecia en cada reinicio del motor. Por eso el
problema sobrevivio a que alguien la borrara.

Esta prueba fija la decision del area donde de verdad vive.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MAIN = RAIZ / "app" / "main.py"


def _siembra() -> str:
    return MAIN.read_text(encoding="utf-8")


class TestLaSiembraDeUsuarios:
    def test_edgar_silva_queda_con_la_cuenta_buena(self):
        src = _siembra()
        assert '("carterahus02@sinacsc.com", "AUDITOR", "EDGAR SILVA")' in src

    def test_la_cuenta_que_rebota_ya_no_se_siembra(self):
        """`devoluciones1@` rebotaba. Si vuelve al arranque, los correos con
        las glosas de Edgar se pierden otra vez."""
        assert "devoluciones1@sinacsc.com" not in _siembra()

    def test_edgar_silva_aparece_una_sola_vez(self):
        assert len(re.findall(r'"EDGAR SILVA"', _siembra())) == 1

    def test_no_se_repite_ningun_correo_en_la_siembra(self):
        """Dos entradas con el mismo correo dejarían al gestor con dos cuentas
        y los envíos repartidos entre ellas."""
        correos = re.findall(r'\("([a-z0-9.]+@sinacsc\.com)",\s*"[A-Z_]+"', _siembra())
        repetidos = {c for c in correos if correos.count(c) > 1}
        assert not repetidos, f"correos sembrados dos veces: {sorted(repetidos)}"
