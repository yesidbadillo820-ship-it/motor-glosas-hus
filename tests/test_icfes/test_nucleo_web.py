"""La aplicación web y la consola tienen que calcular exactamente lo mismo.

La app lleva adentro una traducción a JavaScript del cálculo de `icfes/plan.py`,
`icfes/puntaje.py` y `icfes/repaso.py`. Una traducción se desvía sola con el
tiempo: alguien cambia una fórmula en Python y nadie se acuerda del JavaScript.
Entonces el estudiante ve un plan en el computador y otro distinto en el
celular, y deja de creerle al sistema.

Esta prueba evita eso por la vía dura: extrae el bloque NUCLEO de la plantilla,
lo corre con node y compara sus resultados, uno por uno, contra los de Python.

Si node no está instalado, la prueba se salta en vez de fallar: no todos los
computadores del hospital lo tienen, y no es una dependencia del sistema.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from icfes.banco import cargar_banco
from icfes.dominio import ORDEN_AREAS, Area
from icfes.exportar_web import PLANTILLA, construir_datos
from icfes.plan import generar_plan, repartir_horas
from icfes.puntaje import estimar_puntaje_area, meta_por_area, puntaje_global
from icfes.repaso import Tarjeta, calificar

NODE = shutil.which("node")
sin_node = pytest.mark.skipif(NODE is None, reason="node no está instalado en esta máquina")

INICIO = date(2026, 8, 20)
EXAMEN = date(2027, 8, 8)

#: Tres escenarios distintos a propósito: uno parejo, uno muy desigual y uno
#: donde el estudiante ya casi alcanzó la meta (que es donde los redondeos y
#: los topes de 100 hacen más ruido).
CASOS = [
    {"diag": dict.fromkeys(ORDEN_AREAS, 50.0), "meta": 400, "horas": 12, "dias": 6},
    {
        "diag": {
            Area.LECTURA_CRITICA: 62.0,
            Area.MATEMATICAS: 31.0,
            Area.SOCIALES_CIUDADANAS: 55.0,
            Area.CIENCIAS_NATURALES: 48.0,
            Area.INGLES: 25.0,
        },
        "meta": 400,
        "horas": 14,
        "dias": 6,
    },
    {
        "diag": {
            Area.LECTURA_CRITICA: 88.0,
            Area.MATEMATICAS: 90.0,
            Area.SOCIALES_CIUDADANAS: 85.0,
            Area.CIENCIAS_NATURALES: 87.0,
            Area.INGLES: 70.0,
        },
        "meta": 450,
        "horas": 8,
        "dias": 5,
    },
]

GUION = """
const fs = require("node:fs");
const fuente = fs.readFileSync(process.argv[2], "utf8");
const nucleo = fuente.split("/* <NUCLEO> */")[1].split("/* </NUCLEO> */")[0];
const M = new Function(nucleo + `return {puntajeArea, puntajeGlobal, metaPorArea,
  repartirHoras, generarPlan, calificarTarjeta};`)();
const entrada = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const {areas, cfgPlan, orden, curva, casos} = entrada;
const cfg = Object.assign({}, cfgPlan, {areasFicha: areas});
const salida = {casos: []};
for (const c of casos){
  const p = M.generarPlan(c.diag, "2027-08-08", c.meta, c.horas, "2026-08-20", cfg, c.dias);
  const rep = M.repartirHoras(c.diag, c.meta, areas, orden, cfgPlan.piso_area);
  const reparto = {}; for (const a of orden) reparto[a] = Math.round(rep[a]*1e9)/1e9;
  salida.casos.push({
    meta_por_area: M.metaPorArea(c.meta, c.diag, areas, orden),
    reparto,
    global: M.puntajeGlobal(c.diag, areas, orden),
    semanas: p.semanas.length,
    bloques: p.semanas.reduce((s,x) => s + x.bloques.length, 0),
    simulacros: p.semanas.flatMap(s =>
      s.bloques.filter(b => b.tipo === "simulacro_completo").map(b => b.fecha)),
    detalle: p.semanas.map(s => ({n:s.numero, fase:s.fase, bloques:s.bloques})),
  });
}
salida.puntajes = entrada.puntajes.map(([c,t]) => [c, t, M.puntajeArea(c, t, curva)]);
let t = null, hoy = "2026-08-20"; salida.repaso = [];
for (const cal of entrada.calidades){
  t = M.calificarTarjeta(t, cal, hoy, "2027-08-08");
  salida.repaso.push({reps:t.reps, facilidad:t.facilidad, intervalo:t.intervalo, proxima:t.proxima});
  hoy = t.proxima;
}
console.log(JSON.stringify(salida));
"""

PUNTAJES = [(0, 50), (13, 50), (25, 50), (34, 50), (42, 50), (50, 50), (29, 58), (19, 41)]
CALIDADES = [4, 5, 3, 5, 1, 4, 5, 5, 0, 4]


@pytest.fixture(scope="module")
def resultado_js(tmp_path_factory):
    """Corre el núcleo de la app con node y devuelve lo que calculó."""
    if NODE is None:
        pytest.skip("node no está instalado")
    carpeta = tmp_path_factory.mktemp("nucleo")
    datos = construir_datos(cargar_banco())
    entrada = {
        "areas": datos["areas"],
        "cfgPlan": datos["plan"],
        "orden": datos["plan"]["orden_areas"],
        "curva": datos["escalas"]["curva"],
        "puntajes": [list(p) for p in PUNTAJES],
        "calidades": CALIDADES,
        "casos": [
            {
                "diag": {a.value: v for a, v in c["diag"].items()},
                "meta": c["meta"],
                "horas": c["horas"],
                "dias": c["dias"],
            }
            for c in CASOS
        ],
    }
    (carpeta / "entrada.json").write_text(json.dumps(entrada), encoding="utf-8")
    (carpeta / "correr.js").write_text(GUION, encoding="utf-8")
    proceso = subprocess.run(
        [NODE, str(carpeta / "correr.js"), str(PLANTILLA), str(carpeta / "entrada.json")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proceso.returncode == 0, f"node falló:\n{proceso.stderr[:2000]}"
    return json.loads(proceso.stdout)


def test_la_plantilla_marca_el_nucleo_para_poder_verificarlo():
    fuente = Path(PLANTILLA).read_text(encoding="utf-8")
    assert fuente.count("/* <NUCLEO> */") == 1
    assert fuente.count("/* </NUCLEO> */") == 1


@sin_node
def test_el_puntaje_por_area_es_el_mismo(resultado_js):
    esperado = [[c, t, estimar_puntaje_area(c, t)] for c, t in PUNTAJES]
    assert resultado_js["puntajes"] == esperado


@sin_node
def test_el_repaso_espaciado_es_el_mismo(resultado_js):
    tarjeta = Tarjeta("X")
    hoy = date(2026, 8, 20)
    esperado = []
    for calidad in CALIDADES:
        tarjeta = calificar(tarjeta, calidad, hoy, EXAMEN)
        esperado.append(
            {
                "reps": tarjeta.repeticiones,
                "facilidad": tarjeta.facilidad,
                "intervalo": tarjeta.intervalo_dias,
                "proxima": tarjeta.proxima_fecha.isoformat(),
            }
        )
        hoy = tarjeta.proxima_fecha
    assert resultado_js["repaso"] == esperado


@sin_node
@pytest.mark.parametrize("indice", range(len(CASOS)))
def test_las_metas_y_el_reparto_de_horas_son_los_mismos(resultado_js, indice):
    caso = CASOS[indice]
    js = resultado_js["casos"][indice]
    metas = meta_por_area(caso["meta"], caso["diag"])
    assert js["meta_por_area"] == {a.value: metas[a] for a in ORDEN_AREAS}
    reparto = repartir_horas(caso["diag"], caso["meta"])
    assert js["reparto"] == {a.value: round(reparto[a], 9) for a in ORDEN_AREAS}
    assert js["global"] == puntaje_global(caso["diag"])


@sin_node
@pytest.mark.parametrize("indice", range(len(CASOS)))
def test_el_plan_completo_es_identico_bloque_por_bloque(resultado_js, indice):
    """La prueba de fondo: cada bloque de cada semana, en las dos versiones."""
    caso = CASOS[indice]
    js = resultado_js["casos"][indice]
    plan = generar_plan(
        caso["diag"],
        EXAMEN,
        caso["meta"],
        caso["horas"],
        inicio=INICIO,
        dias_por_semana=caso["dias"],
    )
    assert js["semanas"] == len(plan.semanas)
    assert js["bloques"] == sum(len(s.bloques) for s in plan.semanas)
    assert js["simulacros"] == [f.isoformat() for f in plan.simulacros_completos()]

    esperado = [
        {
            "n": s.numero,
            "fase": s.fase,
            "bloques": [
                {
                    "fecha": b.fecha.isoformat(),
                    "tipo": b.tipo.value,
                    "minutos": b.minutos,
                    "area": b.area.value if b.area else None,
                    "foco": b.foco,
                }
                for b in s.bloques
            ],
        }
        for s in plan.semanas
    ]
    assert js["detalle"] == esperado
