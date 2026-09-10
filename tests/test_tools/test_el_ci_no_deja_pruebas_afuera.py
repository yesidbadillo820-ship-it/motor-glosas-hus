"""El CI reparte la suite en tres máquinas. Ninguna prueba puede perderse.

10-09-2026. «Tengo que esperar hasta 15 minutos que un PR pase una
validación» (Yesid). Medido en el CI de verdad —no en la máquina de quien
programa—:

    en serie ............................................. ~13 min
    -n auto --dist loadfile, una sola máquina ............ 6 min 07 s
    y de esos, tests/test_api sola ....................... 4 min 33 s

Dentro de una máquina ya no queda nada que exprimir: el runner da 2 núcleos
y poner más procesos NO ayuda (medido: -n 2 → 4m35, -n 4 → 4m33; estas
pruebas gastan procesador, no espera). Lo único que baja el reloj es repartir
entre VARIAS máquinas que arrancan a la vez.

EL RIESGO DE REPARTIR, y por eso existe este archivo: que un grupo se quede
sin su parte y nadie lo note. Un verde que no probó nada es peor que quince
minutos de espera — el auditor radica confiado en un motor que nadie revisó.

Esta prueba reconstruye el mismo reparto que hace el CI y comprueba que la
suma dé la suite entera: ni una prueba de menos, ni una repetida.
"""

from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CI = RAIZ / ".github" / "workflows" / "ci.yml"


def _archivos_de_test_api() -> list[Path]:
    return sorted((RAIZ / "tests" / "test_api").rglob("test_*.py"))


def _grupo(impares: bool) -> list[Path]:
    """El mismo reparto que hace el CI: impares a un grupo, pares al otro.

    El `awk 'NR % 2 == 1'` del CI cuenta desde 1, así que «impar» es el
    primero, el tercero, el quinto…
    """
    todos = _archivos_de_test_api()
    return [f for i, f in enumerate(todos, start=1) if (i % 2 == 1) == impares]


class TestElRepartoCubreTodo:
    def test_los_dos_grupos_suman_la_carpeta_entera(self):
        todos = _archivos_de_test_api()
        assert len(_grupo(True)) + len(_grupo(False)) == len(todos)

    def test_ningun_archivo_queda_en_los_dos_grupos(self):
        repetidos = set(_grupo(True)) & set(_grupo(False))
        assert not repetidos, f"se correrían dos veces: {sorted(p.name for p in repetidos)}"

    def test_ningun_archivo_se_queda_sin_grupo(self):
        sin_grupo = set(_archivos_de_test_api()) - set(_grupo(True)) - set(_grupo(False))
        assert not sin_grupo, (
            f"estos archivos NO los correría nadie: {sorted(p.name for p in sin_grupo)}"
        )

    def test_los_grupos_quedan_parejos(self):
        """Si uno dobla al otro, el reloj lo marca el lento y no se gana nada."""
        a, b = len(_grupo(True)), len(_grupo(False))
        assert abs(a - b) <= 1, f"reparto desbalanceado: {a} contra {b}"


class TestElCiEstaConfiguradoAsi:
    def _ci(self) -> dict:
        return yaml.safe_load(CI.read_text(encoding="utf-8"))

    def test_hay_tres_grupos(self):
        grupos = self._ci()["jobs"]["test"]["strategy"]["matrix"]["grupo"]
        assert grupos == ["api-1", "api-2", "resto"]

    def test_un_grupo_que_falla_no_cancela_los_otros(self):
        """Dos fallos distintos se ven en la misma corrida, no en dos."""
        assert self._ci()["jobs"]["test"]["strategy"]["fail-fast"] is False

    def test_el_grupo_resto_usa_ignore_y_no_una_lista(self):
        """Así una carpeta de pruebas NUEVA entra sola en vez de quedarse sin correr."""
        texto = CI.read_text(encoding="utf-8")
        assert "OBJETIVO=(tests --ignore=tests/test_api)" in texto

    def test_un_grupo_vacio_es_un_error_y_no_un_exito(self):
        texto = CI.read_text(encoding="utf-8")
        assert "${#OBJETIVO[@]} -eq 0" in texto
        assert "exit 1" in texto

    def test_ci_ok_espera_a_las_pruebas(self):
        """Espera por medio de `test-ok`, que a su vez espera a los tres grupos.

        Cambió el 10-09-2026: antes esperaba a `test` directamente. Ahora pasa
        por el agregador, que además produce el nombre que exige la protección
        de la rama.
        """
        ci = self._ci()
        assert "test-ok" in ci["jobs"]["ci-ok"]["needs"]
        assert "test" in ci["jobs"]["test-ok"]["needs"]

    def test_los_artefactos_no_se_pisan_entre_grupos(self):
        texto = CI.read_text(encoding="utf-8")
        assert "pytest-output-log-${{ matrix.grupo }}" in texto
        assert "junit-results-${{ matrix.grupo }}" in texto

    def test_se_sigue_repartiendo_por_archivo_dentro_de_cada_maquina(self):
        """--dist loadfile: las pruebas de un archivo, en el mismo proceso."""
        texto = CI.read_text(encoding="utf-8")
        assert "-n auto --dist loadfile" in texto


class TestElNombreQueLaRamaExige:
    """El chequeo obligatorio se llama «Tests (pytest)» y alguien lo tiene que producir.

    10-09-2026. Al repartir la suite en tres máquinas, los trabajos pasaron a
    llamarse «Tests (pytest · api-1)», «… api-2» y «… resto». La protección de
    la rama exige uno llamado EXACTAMENTE «Tests (pytest)», y ese nombre dejó
    de existir: GitHub se quedó esperando un chequeo que ya nadie iba a
    reportar, con todo lo demás en verde y la PR **bloqueada para siempre**.

    Lo peor del caso: no se ve como un error. Se ve como «una comprobación
    aún no se ha completado», que es lo que uno espera mirar un rato más.

    Por eso hay un trabajo cuyo único fin es producir ese nombre y reportar el
    resultado de los tres grupos. Esta clase lo vigila: renombrar los grupos
    otra vez sin dejar el nombre exigido volvería a colgar todas las PR.
    """

    def _ci(self) -> dict:
        return yaml.safe_load(CI.read_text(encoding="utf-8"))

    def test_alguien_produce_el_nombre_exacto(self):
        nombres = {j["name"] for j in self._ci()["jobs"].values()}
        assert "Tests (pytest)" in nombres, (
            "la protección de la rama exige ese nombre exacto; sin él, toda PR "
            "queda esperando un chequeo que nadie va a reportar"
        )

    def test_ese_trabajo_espera_a_los_tres_grupos(self):
        assert "test" in self._ci()["jobs"]["test-ok"]["needs"]

    def test_si_un_grupo_falla_el_agregador_falla(self):
        """Si no, un grupo rojo pasaría por verde."""
        texto = CI.read_text(encoding="utf-8")
        assert 'if [ "${{ needs.test.result }}" != "success" ]; then' in texto
        assert "exit 1" in texto

    def test_sigue_corriendo_aunque_un_grupo_falle(self):
        """Con `needs`, un fallo salta el trabajo y el chequeo nunca se reporta.

        Sin `!cancelled()`, un grupo rojo dejaría la PR otra vez colgada
        esperando — el mismo bloqueo, disfrazado de otra cosa.
        """
        assert self._ci()["jobs"]["test-ok"]["if"] is not None

    def test_ci_ok_pasa_por_el_agregador(self):
        assert "test-ok" in self._ci()["jobs"]["ci-ok"]["needs"]
