"""No afirmar que el contrato venció cuando no se sabe (21-08-2026).

Yesid analizó dos glosas de FAMISANAR —`CO0701` y `TA0701`— y los dictámenes
salieron diciendo:

    «…SE ENCUENTRA FUERA DE LA VIGENCIA DEL CONTRATO S-13-1-03-1-04958,
     POR LO QUE DEBE APLICARSE EL MARCO NORMATIVO GENERAL»

y el encabezado de uno decía **«Contrato: SIN CONTRATO PACTADO»** mientras la
línea de abajo decía «Tarifa pactada: SOAT UVB VIGENTE -5 %».

**Ese contrato rige del 15/04/2026 al 14/04/2027** — el propio dictamen citaba
su anexo tarifario dos párrafos más abajo.

Ante la EPS eso es de lo peor que se puede escribir: **quien dice que no tiene
contrato vigente pierde el derecho a exigir la tarifa pactada.**

LA CAUSA: el motor tomaba **la primera fecha que apareciera** en el número de
factura, el radicado o los primeros 5.000 caracteres de los PDF, y la trataba
como la fecha de la atención. Esa primera fecha puede ser la de nacimiento del
paciente, la de expedición de un documento o la de validación del CUV.

No lo causó un dato malo: lo causó **adivinar**.
"""

from __future__ import annotations

import inspect
import re

from app.services import glosa_ia_prompts as mod


def _fuente() -> str:
    return inspect.getsource(mod)


class TestSoloCuentaUnaFechaEtiquetada:
    def test_ya_no_se_toma_la_primera_fecha_suelta(self):
        """El patrón viejo `\\b(\\d{4}-...)\\b` sin etiqueta enganchaba
        cualquier fecha del expediente."""
        f = _fuente()
        assert 'r"\\b(\\d{4}-\\d{1,2}-\\d{1,2}|\\d{1,2}/\\d{1,2}/\\d{4})\\b"' not in f, (
            "volvió a tomarse la primera fecha suelta como fecha de atención"
        )

    def test_el_patron_exige_la_etiqueta(self):
        """Se mira el bloque que DE VERDAD corre.

        Hay dos alertas de vigencia en el archivo. La primera vive en
        `build_contrato_context`, que no tiene ningún llamador —código muerto—
        y además solo actúa si alguien le PASA la fecha: no adivina. La que
        importa es la del prompt del dictamen, que es la que armaba la fecha
        por su cuenta.
        """
        f = _fuente()
        i = f.index('"\\n\\n⚠ ⚠ ⚠ ALERTA DE VIGENCIA ⚠ ⚠ ⚠\\n"')
        trozo = f[max(0, i - 2500) : i]
        for etiqueta in ("atenci", "prestaci", "factura"):
            assert etiqueta in trozo, f"el patrón no exige la etiqueta «{etiqueta}»"

    def test_la_alerta_muerta_sigue_sin_llamadores(self):
        """Si algún día alguien empieza a usar `build_contrato_context`, tiene
        que pasarle una fecha CONFIABLE — no la primera que encuentre."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        usos = 0
        for py in (raiz / "app").rglob("*.py"):
            texto = py.read_text(encoding="utf-8", errors="replace")
            usos += texto.count("build_contrato_context(") - texto.count(
                "def build_contrato_context("
            )
        assert usos == 0, (
            "alguien empezó a usar build_contrato_context: revise que la fecha "
            "que le pasa sea la de atención de verdad y no una adivinada"
        )

    def test_la_fecha_de_atencion_tampoco_se_adivina(self):
        """El otro sitio: el dato que se le muestra a la IA."""
        f = _fuente()
        i = f.index('datos["fecha_atencion"] = m.group(1)')
        trozo = f[max(0, i - 900) : i]
        assert "atenci" in trozo and "ingreso" in trozo
        assert 'r"\\b(\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4})\\b"' not in trozo


class TestElPatronEnLaPractica:
    """Se prueba el patrón mismo contra textos reales."""

    PATRON = (
        r"(?:fecha\s+(?:de\s+)?(?:atenci[oó]n|prestaci[oó]n|servicio|ingreso|egreso|factura)"
        r"|f\.?\s*(?:atenci[oó]n|factura|prestaci[oó]n)"
        r"|fecha_atencion|fecha_factura)"
        r"[\s:=]*(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})"
    )

    def test_reconoce_la_fecha_etiquetada(self):
        for texto, esperado in [
            ("FECHA DE ATENCION: 05/06/2026", "05/06/2026"),
            ("Fecha de prestación 2026-06-05", "2026-06-05"),
            ("F. ATENCION 12/03/2026", "12/03/2026"),
            ("fecha_factura=2026-04-20", "2026-04-20"),
            ("FECHA DE INGRESO: 01/01/2026", "01/01/2026"),
        ]:
            m = re.search(self.PATRON, texto, re.IGNORECASE)
            assert m, f"no reconoció «{texto}»"
            assert m.group(1) == esperado

    def test_NO_engancha_una_fecha_cualquiera(self):
        """Lo que causó el defecto: fechas sueltas del expediente."""
        for texto in [
            "PACIENTE NACIDO EL 14/07/1985",
            "Documento expedido 03/02/2020",
            "CUV validado 2026-08-10 por el Ministerio",
            "HUS0000525618  GLS-2024-00001",
            "Resolución 2284 del 2023",
        ]:
            assert not re.search(self.PATRON, texto, re.IGNORECASE), (
                f"enganchó una fecha que no es la de atención: «{texto}»"
            )

    def test_sin_fecha_no_hay_alerta(self):
        """No saber cuándo se prestó el servicio NO es prueba de que el
        contrato estuviera vencido."""
        assert not re.search(self.PATRON, "glosa sin ninguna fecha", re.IGNORECASE)


class TestQuedaExplicadoElPorQue:
    def test_el_codigo_cuenta_el_caso_real(self):
        f = _fuente()
        assert "S-13-1-03-1-04958" in f
        assert "adivinar" in f
