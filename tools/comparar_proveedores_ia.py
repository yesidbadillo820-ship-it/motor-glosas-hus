"""Corre LA MISMA glosa por cada proveedor de IA y los pone lado a lado.

POR QUÉ EXISTE (10-09-2026, pedido de Yesid). Él preguntó cuál IA gratis da
«un mejor dictamen». Eso no se opina: se mide. Y para medirlo hace falta un
caso donde ya sepamos cuál es la respuesta correcta.

EL CASO PATRÓN es real y está aquí adentro: la factura HUS0000541440 del
Dispensario Médico. Sabemos las respuestas porque las sacamos de los papeles
—la factura electrónica y la recepción de objeción N° 189801—, no de una
suposición:

  · Son OCHO conceptos, no uno: $55.985.100 en total.
  · SÍ había contrato: el 440-DIGSA/DMBUG-2025, tarifa SOAT SMLV −20%.
    La atención fue del 10 al 16 de julio y el contrato corría hasta el 30.
  · La glosa NO está extemporánea: 20 días hábiles exactos, y el límite es
    «más de 20». Se salvaron por un día, gracias a dos festivos de agosto.
  · La factura vale $126.565.918. Ni un dictamen puede decir otra cosa.
  · El coil FMQ6476 es un INSUMO, no un procedimiento, y no tiene CUPS.
  · El IOBITRIDOL es un medio de contraste yodado. Decir que es un
    antiséptico es falso — ya salió una vez y no puede repetirse.

Cada uno de esos puntos es una fila de la tabla de resultados. No se puntúa
«qué tan bonito escribe»: se cuenta cuántos hechos verificables acierta.

CÓMO SE USA (desde la carpeta del motor, con el .env cargado):

    py tools/comparar_proveedores_ia.py                 # todos los que tengan llave
    py tools/comparar_proveedores_ia.py --solo groq,gemini
    py tools/comparar_proveedores_ia.py --guardar comparacion.md

LO QUE ESTE PROGRAMA NO HACE: no decide por usted. Imprime qué acertó y qué
falló cada uno sobre el mismo caso, y la decisión es del área.

OJO CON EL COSTO: Groq y Gemini son gratis dentro de su cuota. Anthropic se
paga. Por eso Anthropic NO entra salvo que lo pida expresamente con --solo.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


# ── El caso patrón, tal como lo mandó la entidad ────────────────────────────
GLOSA_PATRON = """RECEPCIÓN DE OBJECIÓN N° 189801 · GLOSA INICIAL · ADMINISTRATIVO
FACTURA: HUS0000541440 · FECHA FACTURA: 24/07/2026 · VALOR FACTURA: $126.565.918
FECHA OBJECIÓN: 25/08/2026
CONTRATO: U22031 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO
TERCERO: 901541137 DISPENSARIO MEDICO BUCARAMANGA
SERVICIO: 734106 - ANGIOGRAFIA HEMODINAMIA

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6276 MICROGUÍA CON PUNTA 0,10 - 14 REGULAR 0.014" X 200 CM
VALOR OBJETADO: $6.390.700,00
Observaciones: SE OBJETA MATERIAL DE PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR SANIDAD MILITAR PARA SU RESPECTIVO COBRO.

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6456 CATÉTER INTRODUCTOR LARGO AXS INFINITY 90CM
VALOR OBJETADO: $8.099.200,00
Observaciones: SE OBJETA MATERIAL DE PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR SANIDAD MILITAR PARA SU RESPECTIVO COBRO.

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL MODELO TARGET 360 ULTRA
VALOR OBJETADO: $6.898.700,00
Observaciones: SE OBJETA MATERIAL DE PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR SANIDAD MILITAR PARA SU RESPECTIVO COBRO.

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL MODELO TARGET 360 ULTRA (2 unidades)
VALOR OBJETADO: $13.797.400,00
Observaciones: SE OBJETA MATERIAL DE PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR SANIDAD MILITAR PARA SU RESPECTIVO COBRO.

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL MODELO TARGET 360 ULTRA
VALOR OBJETADO: $6.898.700,00
Observaciones: SE OBJETA MATERIAL DE PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR SANIDAD MILITAR PARA SU RESPECTIVO COBRO.

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL MODELO TARGET 360 ULTRA
VALOR OBJETADO: $6.898.700,00
Observaciones: SE OBJETA MATERIAL DE PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR SANIDAD MILITAR PARA SU RESPECTIVO COBRO.

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL MODELO TARGET 360 ULTRA
VALOR OBJETADO: $6.898.700,00
Observaciones: SE OBJETA MATERIAL DE PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR SANIDAD MILITAR PARA SU RESPECTIVO COBRO.

FA0701 - Los cargos por Medicamentos o APME que vienen relacionados en los soportes de cobro, presentan diferencias con las cantidades que fueron facturadas
224249-2 IOBITRIDOL 300MG/50ML (XENETIX) (EQUIVALENTE A 30%P/V DE YODO)
VALOR OBJETADO: $103.000,00
Observaciones: SE OBJETA MEDIO DE CONTRASTE UTILIZADO SEGUN NOTA OPERATORIA SE UTILIZA 40CC LA HOJA DE GASTOS REGISTRA FRASCO DE 100 ML 50 ML POR LO TANTO NO SE RECONOCE COBRO DE 4 UNIDADES.

TOTAL OBJETADO: $55.985.100,00"""


@dataclass
class Comprobacion:
    """Un hecho verificable del caso, con cómo se reconoce en el dictamen."""

    nombre: str
    debe_decir: tuple[str, ...] = ()
    no_puede_decir: tuple[str, ...] = ()
    por_que: str = ""

    def evaluar(self, dictamen: str) -> tuple[bool, str]:
        d = " ".join((dictamen or "").upper().split())
        for prohibido in self.no_puede_decir:
            if prohibido.upper() in d:
                return False, f"dijo «{prohibido}»"
        if not self.debe_decir:
            return True, ""
        for exigido in self.debe_decir:
            if exigido.upper() in d:
                return True, ""
        return False, f"no menciona {self.debe_decir[0]}"


# Cada fila salió de un papel, no de una opinión.
COMPROBACIONES = (
    Comprobacion(
        "Reconoce el contrato",
        debe_decir=("440-DIGSA", "440 DIGSA"),
        no_puede_decir=("SIN CONTRATO PACTADO",),
        por_que="la atención fue del 10 al 16 de julio y el contrato corría hasta el 30",
    ),
    Comprobacion(
        "Usa la tarifa pactada",
        debe_decir=("-20", "− 20", "20 %", "20%"),
        no_puede_decir=("SOAT PLENO",),
        por_que="el contrato pacta SOAT SMLV −20 %, no tarifa plena",
    ),
    Comprobacion(
        "Responde el total objetado",
        debe_decir=("55.985.100", "55985100"),
        por_que="son ocho conceptos; responder uno concede el resto",
    ),
    Comprobacion(
        "Contesta las DOS causales",
        debe_decir=("FA0701",),
        por_que="SO4201 y FA0701 son pleitos distintos",
    ),
    Comprobacion(
        "No inventa el valor de la factura",
        no_puede_decir=("224.249", "$224249"),
        por_que="224249-2 es el código del IOBITRIDOL; la factura vale $126.565.918",
    ),
    Comprobacion(
        "No declara extemporánea la glosa",
        no_puede_decir=("ES EXTEMPOR", "GLOSA EXTEMPOR"),
        por_que="20 días hábiles exactos, y el límite es más de 20",
    ),
    Comprobacion(
        "No llama CUPS al código del insumo",
        no_puede_decir=("CUPS FMQ", "CÓDIGO CUPS FMQ", "CUPS 734106"),
        por_que="FMQ6476 es un material del HUS; los insumos no tienen CUPS",
    ),
    Comprobacion(
        "No repite el disparate del iobitridol",
        no_puede_decir=("ANTIS", "NO ES UN MEDIO DE CONTRASTE"),
        por_que="es un medio de contraste yodado, y ya salió mal una vez",
    ),
    Comprobacion(
        "Nombra lo que la entidad de verdad pide",
        debe_decir=("FACTURA DE COMPRA", "COTIZACI"),
        por_que="los siete renglones de SO4201 piden eso, no la historia clínica",
    ),
)


async def _correr(proveedor: str) -> tuple[str, str, float]:
    """Devuelve (dictamen, modelo, segundos) del proveedor pedido."""
    import time

    from app.core.config import get_settings
    from app.models.schemas import GlosaInput
    from app.services.glosa_service import GlosaService

    cfg = get_settings()
    servicio = GlosaService(
        anthropic_api_key=cfg.anthropic_api_key,
        groq_api_key=cfg.groq_api_key,
        gemini_api_key=cfg.gemini_api_key,
        primary_ai=proveedor,
    )
    entrada = GlosaInput(
        eps="DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA",
        texto_glosa=GLOSA_PATRON,
        etapa="INICIAL",
        numero_factura="HUS0000541440",
        fecha_radicacion="2026-07-24",
        fecha_recepcion="2026-08-25",
        valor_aceptado=0,
    )
    t0 = time.time()
    resultado = await servicio.analizar(entrada)
    segundos = time.time() - t0
    dictamen = getattr(resultado, "dictamen", "") or getattr(resultado, "respuesta", "") or ""
    modelo = getattr(resultado, "modelo_ia", "") or proveedor
    return dictamen, modelo, segundos


def _tabla(resultados: dict) -> str:
    anchos = max((len(p) for p in resultados), default=8)
    lineas = [
        "",
        "═" * 78,
        "  MISMA GLOSA, DISTINTA IA — factura HUS0000541440 · 8 conceptos · $55.985.100",
        "═" * 78,
        "",
    ]
    for prov, datos in resultados.items():
        if datos.get("error"):
            lineas.append(f"  {prov.upper():<{anchos}}  ✗ no respondió: {datos['error']}")
            continue
        aciertos = sum(1 for ok, _ in datos["notas"] if ok)
        lineas.append(
            f"  {prov.upper():<{anchos}}  {aciertos}/{len(COMPROBACIONES)} aciertos  "
            f"· {datos['segundos']:.1f}s · {datos['modelo']}"
        )
    lineas.append("")
    lineas.append("─" * 78)
    lineas.append("  DETALLE — cada fila salió de un papel, no de una opinión")
    lineas.append("─" * 78)
    for i, comp in enumerate(COMPROBACIONES):
        lineas.append("")
        lineas.append(f"  {comp.nombre}")
        lineas.append(f"    ({comp.por_que})")
        for prov, datos in resultados.items():
            if datos.get("error"):
                continue
            ok, motivo = datos["notas"][i]
            lineas.append(f"      {'✓' if ok else '✗'} {prov:<10} {motivo}")
    lineas.append("")
    lineas.append("═" * 78)
    lineas.append("  Esto NO decide por usted: cuenta hechos verificables, no estilo.")
    lineas.append("═" * 78)
    return "\n".join(lineas)


async def _principal() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--solo",
        default="",
        help="proveedores separados por coma (groq, gemini, anthropic). "
        "Anthropic SE PAGA: solo entra si lo nombra acá.",
    )
    ap.add_argument("--guardar", default="", help="archivo .md donde dejar el resultado")
    args = ap.parse_args()

    from app.core.config import get_settings

    cfg = get_settings()
    disponibles = []
    if args.solo:
        pedidos = [p.strip().lower() for p in args.solo.split(",") if p.strip()]
    else:
        # Por defecto SOLO los gratis. Anthropic se paga: no se gasta sin pedirlo.
        pedidos = ["groq", "gemini"]
    llaves = {
        "groq": cfg.groq_api_key,
        "gemini": cfg.gemini_api_key,
        "anthropic": cfg.anthropic_api_key,
    }
    for p in pedidos:
        if p not in llaves:
            print(f"  ⚠ proveedor desconocido: {p}")
        elif not llaves[p]:
            print(f"  ⚠ {p}: sin llave configurada, se salta")
        else:
            disponibles.append(p)
    if not disponibles:
        print("No hay ningún proveedor con llave. Revise el .env.")
        return 1

    resultados: dict = {}
    for prov in disponibles:
        print(f"  … corriendo {prov}", flush=True)
        try:
            dictamen, modelo, segundos = await _correr(prov)
            resultados[prov] = {
                "modelo": modelo,
                "segundos": segundos,
                "dictamen": dictamen,
                "notas": [c.evaluar(dictamen) for c in COMPROBACIONES],
            }
        except Exception as e:  # noqa: BLE001 — se reporta, no se traga
            resultados[prov] = {"error": str(e)[:160]}

    salida = _tabla(resultados)
    print(salida)
    if args.guardar:
        destino = Path(args.guardar)
        cuerpo = [salida, "", "", "# Los dictámenes completos", ""]
        for prov, datos in resultados.items():
            cuerpo += [f"## {prov}", "", datos.get("dictamen") or datos.get("error", ""), ""]
        destino.write_text("\n".join(cuerpo), encoding="utf-8")
        print(f"\n  Guardado en {destino}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(asyncio.run(_principal()))
