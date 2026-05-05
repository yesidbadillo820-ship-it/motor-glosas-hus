"""
normativa_grafo.py — Foundation del Knowledge Graph de normativa.

Modela las relaciones entre normas del corpus normativa_completa como
un grafo dirigido. Cada arista tiene un tipo:

  modifica_a       — N1 modifica el texto/alcance de N2
  modificada_por   — inverso de modifica_a
  cita_a           — N1 cita expresamente a N2 en su texto
  reglamenta_a     — N1 desarrolla/reglamenta a N2 (decreto → ley)
  deroga_a         — N1 deroga total/parcial a N2
  fundamenta_a     — N1 sirve de base jurídica a N2 (sentencia → ley)

Por qué un grafo y no atributos en cada norma:
  1. Mantenemos `normativa_completa.py` pristine (esa fuente de verdad
     ya tiene 5000+ líneas de texto literal).
  2. Las relaciones se pueden expandir incremental sin tocar el
     corpus base.
  3. Un grafo permite traverse: "dame todas las normas que
     fundamentan/sustentan a la Res. 2284/2023" → puedo seguir las
     aristas hacia atrás recursivamente.
  4. Cuando el motor cita una norma, podemos auto-incluir las que
     la sustentan = dictamen jurídicamente más sólido.

ESTADO ACTUAL (foundation): ~30 aristas explícitas para las normas
más usadas en glosas. Iremos sumando con el tiempo según los
dictamenes reales y los hallazgos de Yesid.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("motor_glosas")


# Tipos de relación (controlled vocabulary)
TIPOS_RELACION = {
    "modifica_a",
    "modificada_por",
    "cita_a",
    "reglamenta_a",
    "deroga_a",
    "fundamenta_a",
    "complementa_a",
}


# Aristas del grafo. Cada tupla: (origen, tipo, destino, nota_breve).
# Las claves usan la nomenclatura de _TODAS_LAS_NORMAS / claves típicas
# del corpus normativa_completa. Si una clave no existe en el corpus,
# se ignora silenciosamente (ver _resolver_clave abajo).
ARISTAS_GRAFO: list[tuple[str, str, str, str]] = [
    # ─── Decreto 4747 de 2007 (régimen IPS-EPS de glosas) ─────────────
    ("decreto_4747_2007", "reglamenta_a", "ley_100_1993",
     "Decreto 4747/2007 reglamenta artículos de la Ley 100 sobre relaciones IPS-EPS"),
    ("res_3047_2008", "reglamenta_a", "decreto_4747_2007",
     "Res. 3047/2008 establece formatos de glosas previstos en el Dec. 4747"),
    ("res_4331_2012", "modifica_a", "res_3047_2008",
     "Res. 4331/2012 modifica parcialmente la Res. 3047/2008"),
    ("res_2275_2023", "modifica_a", "res_3047_2008",
     "Res. 2275/2023 actualiza la Res. 3047/2008 con factura electrónica"),
    ("res_2284_2023", "modifica_a", "res_3047_2008",
     "Res. 2284/2023 (Manual Único de Glosas) actualiza el codigo de glosas"),

    # ─── Ley 1438 de 2011 (reforma SGSSS — silencio Art. 57) ──────────
    ("ley_1438_2011", "modifica_a", "ley_100_1993",
     "Ley 1438/2011 reforma SGSSS, introduce art. 57 (silencio favor IPS)"),
    ("res_2284_2023", "fundamenta_a", "ley_1438_2011",
     "El Manual Único de Glosas se apoya en plazos y silencios Art. 57 Ley 1438"),

    # ─── Sentencias C/T como fundamento ─────────────────────────────
    ("sentencia_t_760_2008", "fundamenta_a", "ley_100_1993",
     "T-760/2008 desarrolla el derecho fundamental a la salud sobre Ley 100"),
    ("sentencia_t_1025_2002", "fundamenta_a", "ley_100_1993",
     "T-1025/2002 sobre urgencias, art. 168 Ley 100"),
    ("ley_1751_2015", "fundamenta_a", "sentencia_t_760_2008",
     "Ley Estatutaria de Salud cristaliza la doctrina T-760/2008"),

    # ─── Decreto 780 de 2016 (compilatorio) ────────────────────────
    ("decreto_780_2016", "complementa_a", "decreto_4747_2007",
     "Decreto Único Reglamentario 780/2016 compila todo el sector salud"),
    ("decreto_780_2016", "complementa_a", "decreto_1011_2006",
     "Compila el SOGCS"),

    # ─── Resoluciones de habilitación y soportes ────────────────────
    ("res_1995_1999", "complementa_a", "ley_100_1993",
     "Historia clínica como documento médico-legal"),
    ("res_3100_2019", "modifica_a", "res_2003_2014",
     "Res. 3100/2019 actualiza condiciones de habilitación"),

    # ─── C. Comercio + C. Civil (cláusulas anti-rebatimiento) ──────
    ("art_871_codigo_comercio", "complementa_a", "ley_100_1993",
     "Buena fe contractual aplica a contratos IPS-EPS"),
    ("art_1602_codigo_civil", "complementa_a", "ley_100_1993",
     "Fuerza vinculante de los contratos pactados"),
]


def _normalizar_clave(clave: str) -> str:
    """Normaliza una clave a snake_case minúsculas, espacios = '_'."""
    if not clave:
        return ""
    repl = str.maketrans("áéíóúñ", "aeioun")
    return clave.translate(repl).lower().replace(" ", "_").strip()


def _resolver_clave(clave: str, corpus: dict) -> Optional[str]:
    """Mapea una clave del grafo a una clave real del corpus normativa_completa.

    El grafo usa formas como "ley_100_1993" o "res_2284_2023", pero el
    corpus tiene claves variadas. Probamos varias formas.
    """
    if not clave or not corpus:
        return None
    n = _normalizar_clave(clave)
    # Match directo
    if n in corpus:
        return n
    # Match con variantes capitalización
    for k in corpus.keys():
        if _normalizar_clave(k) == n:
            return k
    # Match parcial (ej. "ley_100_1993" → "LEY 100 DE 1993")
    n_no_de = n.replace("_de_", "_")
    for k in corpus.keys():
        if _normalizar_clave(k).replace("_de_", "_") == n_no_de:
            return k
    return None


def obtener_relaciones(clave: str) -> list[dict]:
    """Devuelve todas las aristas que tocan la clave (entrantes + salientes).

    Cada elemento:
        {
          "direccion": "saliente" | "entrante",
          "tipo": "modifica_a" | ... ,
          "otra": "<clave del nodo en el otro extremo>",
          "nota": "<descripción breve>",
        }
    """
    n = _normalizar_clave(clave)
    if not n:
        return []
    out = []
    for origen, tipo, destino, nota in ARISTAS_GRAFO:
        if origen == n:
            out.append({"direccion": "saliente", "tipo": tipo, "otra": destino, "nota": nota})
        elif destino == n:
            # Para las entrantes, invertimos el tipo si aplica
            tipo_inv = {
                "modifica_a": "modificada_por",
                "modificada_por": "modifica_a",
                "cita_a": "citada_por",
                "reglamenta_a": "reglamentada_por",
                "deroga_a": "derogada_por",
                "fundamenta_a": "fundamentada_por",
                "complementa_a": "complementada_por",
            }.get(tipo, tipo)
            out.append({"direccion": "entrante", "tipo": tipo_inv, "otra": origen, "nota": nota})
    return out


def normas_que_sustentan(clave: str, max_profundidad: int = 2) -> list[str]:
    """Búsqueda en grafo: devuelve las normas que sustentan a `clave`.

    Semántica de las aristas (importante):
      - "X fundamenta_a Y" → "X se fundamenta en Y" → Y soporta a X
      - "X reglamenta_a Y" → "X reglamenta/desarrolla a Y" → Y es la base de X
      - "X modifica_a Y" → Y existía antes; X actualizó parte
      - "X complementa_a Y" → relación lateral, no jerárquica

    Para encontrar lo que sustenta a `clave`, seguimos las aristas
    SALIENTES de `clave` con tipo `fundamenta_a` o `reglamenta_a`,
    recursivamente hasta `max_profundidad` saltos. Eso devuelve la
    cadena de fundamentos jurídicos: Manual de Glosas → Ley 1438 →
    Ley 100, por ejemplo.

    Útil para enriquecer una cita: cuando el dictamen cita Res 2284/2023,
    el motor puede auto-mencionar Ley 1438 que la sustenta, dando peso
    jurídico adicional sin pedirle a la IA que lo deduzca sola.
    """
    n = _normalizar_clave(clave)
    visitados = {n}
    frontera = [n]
    sustentos = []
    aristas_sustentantes = {"fundamenta_a", "reglamenta_a"}

    for _ in range(max_profundidad):
        nueva_frontera = []
        for nodo in frontera:
            for origen, tipo, destino, _nota in ARISTAS_GRAFO:
                # Aristas SALIENTES de `nodo` con tipo sustentante
                # (X fundamenta_a Y → Y es el sustento de X)
                if origen == nodo and tipo in aristas_sustentantes:
                    if destino not in visitados:
                        visitados.add(destino)
                        sustentos.append(destino)
                        nueva_frontera.append(destino)
        if not nueva_frontera:
            break
        frontera = nueva_frontera
    return sustentos


def construir_bloque_grafo_para_prompt(clave_principal: str) -> str:
    """Construye un bloque de texto con las normas relacionadas para
    inyectar en el prompt IA cuando se está citando una norma específica.

    Devuelve "" si no hay relaciones en el grafo para esa clave.
    """
    rels = obtener_relaciones(clave_principal)
    if not rels:
        return ""
    lineas = [f"\n[GRAFO NORMATIVO — relaciones de {clave_principal}]"]
    for r in rels[:8]:  # cap a 8 para no inflar prompt
        flecha = "→" if r["direccion"] == "saliente" else "←"
        lineas.append(f"  {flecha} {r['tipo']} :: {r['otra']} ({r['nota']})")
    sustentos = normas_que_sustentan(clave_principal, max_profundidad=2)
    if sustentos:
        lineas.append(
            f"  [SUSTENTOS HEREDADOS]: al citar {clave_principal} también puedes "
            f"apoyarte en: {', '.join(sustentos[:5])}"
        )
    return "\n".join(lineas) + "\n"


def listar_aristas() -> list[dict]:
    """Devuelve todas las aristas del grafo en formato JSON-serializable.
    Útil para endpoints /admin/grafo o visualizaciones."""
    return [
        {"origen": o, "tipo": t, "destino": d, "nota": n}
        for o, t, d, n in ARISTAS_GRAFO
    ]


def estadisticas_grafo() -> dict:
    """Estadísticas básicas del grafo: nodos únicos, aristas por tipo."""
    nodos = set()
    por_tipo: dict[str, int] = {}
    for o, t, d, _ in ARISTAS_GRAFO:
        nodos.add(o)
        nodos.add(d)
        por_tipo[t] = por_tipo.get(t, 0) + 1
    return {
        "total_aristas": len(ARISTAS_GRAFO),
        "total_nodos": len(nodos),
        "aristas_por_tipo": por_tipo,
        "nodos": sorted(nodos),
    }
