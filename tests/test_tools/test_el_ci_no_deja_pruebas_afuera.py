"""El CI reparte la suite en cuatro máquinas. Ninguna prueba puede perderse.

10-09-2026. «Tengo que esperar hasta 15 minutos que un PR pase una
validación» (Yesid). Medido en el CI de verdad —no en la máquina de quien
programa—:

    en serie ............................................. ~13 min
    -n auto --dist loadfile, una sola máquina ............ 6 min 07 s
    tres máquinas, reparto por nombre de archivo ......... 4 min 46 s

Dentro de una máquina ya no queda nada que exprimir: el runner da 2 núcleos
y poner más procesos NO ayuda (medido: -n 2 → 4m35, -n 4 → 4m33; estas
pruebas gastan procesador, no espera).

POR QUÉ NO BASTÓ CON REPARTIR. Las tres máquinas tardaron 2m34, 3m51 y 4m46:
dos terminaban y se quedaban mirando a la tercera. El reloj lo marca la más
lenta, no el promedio. El reparto era por NOMBRE de archivo —impares a un
grupo, pares al otro— y los archivos no duran lo mismo. Ahora se reparte por
lo que cada archivo TARDA de verdad (`scripts/repartir_pruebas.py` sobre
`tests/duraciones_pruebas.json`), y las cuatro máquinas quedan parejas.

EL RIESGO DE REPARTIR, y por eso existe este archivo: que un grupo se quede
sin su parte y nadie lo note. Un verde que no probó nada es peor que quince
minutos de espera — el auditor radica confiado en un motor que nadie revisó.

Esta prueba reconstruye el mismo reparto que hace el CI y comprueba que la
suma dé la suite entera: ni una prueba de menos, ni una repetida.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CI = RAIZ / ".github" / "workflows" / "ci.yml"
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.repartir_pruebas import (  # noqa: E402
    archivos_de_prueba,
    duraciones_medidas,
    repartir,
)

GRUPOS_DEL_CI = 4


def _reparto() -> list[list[str]]:
    """El mismo reparto que hace el CI, con el mismo script."""
    return repartir(archivos_de_prueba(), GRUPOS_DEL_CI, duraciones_medidas())


class TestElRepartoCubreTodo:
    def test_los_grupos_suman_la_suite_entera(self):
        todos = archivos_de_prueba()
        repartidos = [a for g in _reparto() for a in g]
        assert len(repartidos) == len(todos)

    def test_ningun_archivo_queda_en_dos_grupos(self):
        repartidos = [a for g in _reparto() for a in g]
        vistos: set[str] = set()
        repetidos = {a for a in repartidos if a in vistos or vistos.add(a)}
        assert not repetidos, f"se correrían dos veces: {sorted(repetidos)}"

    def test_ningun_archivo_se_queda_sin_grupo(self):
        sin_grupo = set(archivos_de_prueba()) - {a for g in _reparto() for a in g}
        assert not sin_grupo, f"estos archivos NO los correría nadie: {sorted(sin_grupo)}"

    def test_ningun_grupo_queda_vacio(self):
        vacios = [i for i, g in enumerate(_reparto(), start=1) if not g]
        assert not vacios, f"los grupos {vacios} no correrían nada: un verde que no probó nada"

    def test_el_reparto_es_siempre_el_mismo(self):
        """Determinista, para poder reproducir un fallo corriendo ese grupo."""
        assert _reparto() == _reparto()

    def test_las_maquinas_quedan_parejas(self):
        """Si una dobla a otra, el reloj lo marca la lenta y no se gana nada."""
        pesos = duraciones_medidas()
        cargas = [sum(pesos.get(a, 0.0) for a in g) for g in _reparto()]
        assert min(cargas) > 0
        assert max(cargas) / min(cargas) <= 1.25, (
            f"reparto desbalanceado: {[round(c) for c in cargas]} segundos"
        )

    def test_un_archivo_nuevo_sin_medir_entra_igual(self):
        """Nunca se queda por fuera: vale la mediana de los demás."""
        nuevo = "tests/test_services/test_recien_nacido_que_nadie_midio.py"
        con_el_nuevo = repartir([*archivos_de_prueba(), nuevo], GRUPOS_DEL_CI, duraciones_medidas())
        assert nuevo in [a for g in con_el_nuevo for a in g]

    def test_sin_mediciones_reparte_igual_por_cantidad(self):
        """Si el archivo de duraciones se pierde, el CI no se cae: reparte por número."""
        grupos = repartir(archivos_de_prueba(), GRUPOS_DEL_CI, {})
        tamanos = [len(g) for g in grupos]
        assert max(tamanos) - min(tamanos) <= 1


class TestLasDuracionesNoSePudren:
    """Un archivo de duraciones muy viejo devuelve el CI al desbalance."""

    def test_existe_y_tiene_datos(self):
        medidas = duraciones_medidas()
        assert len(medidas) > 100, "sin mediciones el reparto vuelve a ser por cantidad"

    def test_cubre_la_mayor_parte_de_la_suite(self):
        archivos = set(archivos_de_prueba())
        medidos = archivos & set(duraciones_medidas())
        cobertura = len(medidos) / max(len(archivos), 1)
        assert cobertura >= 0.5, (
            f"solo el {cobertura:.0%} de los archivos está medido. Rehacer con: "
            "python -m pytest tests --junitxml=junit.xml && "
            "python scripts/repartir_pruebas.py --medir junit.xml"
        )

    def test_no_apunta_a_archivos_que_ya_no_existen(self):
        """Un fantasma en la tabla no rompe nada, pero avisa de que está vieja."""
        fantasmas = set(duraciones_medidas()) - set(archivos_de_prueba())
        assert len(fantasmas) <= len(archivos_de_prueba()) * 0.2, (
            f"{len(fantasmas)} archivos medidos ya no existen: la tabla está vieja"
        )


class TestElCiEstaConfiguradoAsi:
    def _ci(self) -> dict:
        return yaml.safe_load(CI.read_text(encoding="utf-8"))

    def test_hay_cuatro_grupos_numerados(self):
        grupos = self._ci()["jobs"]["test"]["strategy"]["matrix"]["grupo"]
        assert grupos == [1, 2, 3, 4]

    def test_el_ci_pide_los_mismos_grupos_que_esta_prueba_reconstruye(self):
        """Si el CI pide 5 y acá se comprueban 4, la comprobación no vale."""
        assert len(self._ci()["jobs"]["test"]["strategy"]["matrix"]["grupo"]) == GRUPOS_DEL_CI
        assert f"--grupos {GRUPOS_DEL_CI}" in CI.read_text(encoding="utf-8")

    def test_un_grupo_que_falla_no_cancela_los_otros(self):
        """Dos fallos distintos se ven en la misma corrida, no en dos."""
        assert self._ci()["jobs"]["test"]["strategy"]["fail-fast"] is False

    def test_el_reparto_lo_hace_el_script_y_no_el_yaml(self):
        """La lógica metida en el YAML es la que nadie revisa hasta que falla."""
        texto = CI.read_text(encoding="utf-8")
        assert "python scripts/repartir_pruebas.py --grupos" in texto
        assert (RAIZ / "scripts" / "repartir_pruebas.py").exists()
        assert (RAIZ / "tests" / "duraciones_pruebas.json").exists()

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

    def test_ese_trabajo_espera_a_todos_los_grupos(self):
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


class TestNingunTrabajoMiraAOtroQueNoEspera:
    """Un `needs.X.result` sin declarar `X` en `needs` falla SIEMPRE, y callado.

    10-09-2026, y lo pagué en la misma tarde. Al hacer que `ci-ok` pasara por
    el agregador, cambié el `echo` de `needs.test` a `needs.test-ok` y **se me
    quedó la condición mirando el viejo**. GitHub no da error de sintaxis:
    devuelve la cadena vacía, la comparación con «success» falla, y el paso
    reporta ROJO en cada corrida — con todo lo demás en verde.

    Es el mismo tipo de defecto que el del nombre del chequeo obligatorio: no
    se ve como un error de configuración, se ve como si el código estuviera
    mal. Y uno se pone a buscar donde no es.

    Esta prueba recorre TODOS los trabajos y comprueba que cada `needs.X` que
    usan esté declarado. No comprueba una lista de nombres: se adapta sola si
    mañana se agrega otro trabajo.
    """

    def test_todas_las_referencias_estan_declaradas(self):
        d = yaml.safe_load(CI.read_text(encoding="utf-8"))
        rotas = []
        for nombre, job in d["jobs"].items():
            declarados = set(job.get("needs") or [])
            cuerpo = yaml.safe_dump(job)
            for usado in sorted(set(re.findall(r"needs\.([A-Za-z0-9_-]+)\.result", cuerpo))):
                if usado not in declarados:
                    rotas.append(f"«{nombre}» usa needs.{usado} sin declararlo en needs")
        assert not rotas, (
            "esto devuelve vacío y deja el chequeo en rojo en TODAS las corridas: "
            + "; ".join(rotas)
        )

    def test_ci_ok_comprueba_todos_los_que_espera(self):
        """Si mira menos de los que espera, algo rojo pasaría por verde."""
        texto = CI.read_text(encoding="utf-8")
        d = yaml.safe_load(texto)
        for trabajo in d["jobs"]["ci-ok"]["needs"]:
            assert f"needs.{trabajo}.result" in texto, (
                f"«ci-ok» espera a {trabajo} pero no mira su resultado: podría pasar en rojo"
            )
