"""La Resolución 3047 de 2008 está derogada, y el motor la citaba como vigente.

27-08-2026. El auditor mandó un dictamen real —GL-134, factura HUS0000498954,
causal SO0102— cuya defensa entera se fundaba en el «Anexo Técnico N.° 5 de la
Resolución 3047 de 2008». La citaba **seis veces**, incluidas cuatro filas de
la tabla de soportes. El revisor de citas no dijo nada, porque para el corpus
esa norma estaba vigente.

LA PRUEBA, verificada contra el normograma de la Superintendencia Nacional de
Salud el 27-08-2026 — Res. 2335 de 2023, artículo 20, texto vigente tras la
modificación del artículo 2 de la Res. 1886 de 2024:

    «El presente acto administrativo deroga la Resolución número 3047 de 2008
     y sus modificatorias, la Resolución número 416 de 2009 y la Resolución
     número 4331 de 2012, así como la Resolución número 3253 de 2009; a partir
     del 1 de abril de 2026.»

O sea: llevaba casi cinco meses derogada cuando salió ese dictamen.

Y NO ES LA PRIMERA VEZ. Ya se había corregido el 05-08 («la Resolución 3047
seguía citándose, también en la plantilla guardada en la base») y el 13-08
(«seis plantillas fundaban la defensa en la Resolución 3047»). Volvió las dos
veces porque se corregían las plantillas guardadas y **no la fuente**: el
prompt le seguía pidiendo a la IA que la citara, y la tabla de soportes la
llevaba escrita a mano.

Es la lección del 05-08, otra vez: «escribir la regla no era el trabajo; el
trabajo era comprobar que llegara».
"""

from __future__ import annotations

import pathlib

import pytest

from app.services.normativa_completa import RESOLUCIONES

RAIZ = pathlib.Path(__file__).resolve().parents[2]

# La fecha desde la que dejó de regir. Antes de ella la 3047 SÍ era aplicable,
# así que las menciones que llevan esta fecha al lado son correctas.
DESDE = "01-04-2026"


class TestElCorpusSabeQueEstaDerogada:
    def test_no_figura_como_vigente(self):
        n = RESOLUCIONES["RESOLUCION 3047 DE 2008"]
        assert n["vigente"] is False, (
            "el corpus la daba por vigente, y por eso el revisor de citas "
            "aprobaba dictámenes fundados en ella"
        )

    def test_dice_quien_la_derogo_y_desde_cuando(self):
        n = RESOLUCIONES["RESOLUCION 3047 DE 2008"]
        texto = n.get("derogada_por", "")
        assert "2335" in texto, "falta decir qué resolución la derogó"
        assert "1 DE ABRIL DE 2026" in texto.upper() or "01-04-2026" in texto, (
            "sin la fecha no se puede decidir si aplicaba al servicio que se factura"
        )

    def test_queda_anotada_la_fuente_contra_la_que_se_verifico(self):
        n = RESOLUCIONES["RESOLUCION 3047 DE 2008"]
        assert "27-08-2026" in n.get("verificada", "")

    def test_el_articulo_que_la_deroga_esta_cargado_con_su_texto(self):
        """Sin el artículo cargado, el motor afirma la derogatoria sin poder probarla."""
        art = RESOLUCIONES["RESOLUCION 2335 DE 2023"]["articulos"]["20"]
        assert "deroga la Resolucion numero 3047 de 2008" in art["texto"]
        assert "1 de abril de 2026" in art["texto"]


def _archivos_que_escriben_dictamen() -> list[pathlib.Path]:
    return [
        RAIZ / "app" / "services" / "glosa_ia_prompts.py",
        RAIZ / "app" / "services" / "glosa_service.py",
        RAIZ / "app" / "services" / "banco_respuestas_hus.py",
        RAIZ / "app" / "services" / "excel_radicable.py",
        RAIZ / "app" / "services" / "contexto_contractual_enriquecido.py",
    ]


class TestNadieLaPresentaComoLaFuenteVigente:
    """Cada mención que quede tiene que ir acompañada de su fecha de corte o de
    la palabra «derogada». Una mención pelada es la que produce el dictamen
    tumbable."""

    @pytest.mark.parametrize("ruta", _archivos_que_escriben_dictamen(), ids=lambda p: p.name)
    def test_toda_mencion_dice_desde_cuando_no_rige(self, ruta: pathlib.Path):
        # Se mira la línea y las dos siguientes: una cadena larga se parte en
        # varias líneas de código y la fecha suele quedar en la de abajo, pero
        # en el dictamen sale todo junto.
        lineas = ruta.read_text(encoding="utf-8").splitlines()
        crudas = []
        for n, linea in enumerate(lineas, 1):
            if "3047" not in linea:
                continue
            if linea.lstrip().startswith("#"):
                continue  # los comentarios explican, no salen en el dictamen
            ventana = " ".join(lineas[n - 1 : n + 2]).lower()
            acompanada = DESDE in ventana or "derogad" in ventana or "1 de abril de 2026" in ventana
            if not acompanada:
                crudas.append(f"  {ruta.name}:{n}  {linea.strip()[:110]}")
        assert not crudas, (
            "Estas líneas citan la Res. 3047/2008 sin decir que está derogada ni "
            "desde cuándo. Tal como están, salen en el dictamen y la entidad lo "
            "tumba sin discutir el fondo:\n" + "\n".join(crudas)
        )

    def test_la_tabla_de_soportes_ancla_en_la_vigente(self):
        """Las cuatro filas que salieron impresas en el dictamen del auditor."""
        from app.services.glosa_service import GlosaService

        tabla = GlosaService._MARCO_LEGAL_SOPORTE  # noqa: SLF001
        for clave in ("resultados_msps", "otros_procedimientos", "pde", "pdx"):
            _, marco = tabla[clave]
            assert "2284/2023" in marco, f"{clave} sigue anclado en la norma derogada"
            assert DESDE in marco, f"{clave} no dice desde cuándo dejó de aplicar la vieja"


class TestLoQueNoSePierde:
    """Para un servicio anterior al 1 de abril de 2026 la 3047 SÍ era la norma
    aplicable. Por eso no se borra: se marca."""

    def test_la_norma_sigue_en_el_corpus(self):
        assert "RESOLUCION 3047 DE 2008" in RESOLUCIONES

    def test_dice_para_que_servicios_todavia_sirve(self):
        n = RESOLUCIONES["RESOLUCION 3047 DE 2008"]
        junto = (n.get("ambito", "") + " " + n.get("notas", "")).lower()
        assert "antes del 1 de abril de 2026" in junto or "anteriores" in junto
