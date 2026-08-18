"""descontar_aceptado_detallado.py — le quita al detallado lo que se aceptó.

Después de que el equipo responde las glosas en la macro, algunas quedan como
**SE ACEPTA** con un **VALOR ACEPTADO**: esa plata el hospital ya no la reclama.
Este bot la descuenta del detallado de la factura y vuelve a cuadrar los totales.

Ejemplo real (factura HUS352890 del paquete 31068):

    ANTES    39145 CONSULTA DE URGENCIAS   1,00   $85.800   →  VR ENT $85.800
             FMQ0046 VENDA DE GASA         5,00    $9.400   →  VR ENT $47.000
             SUBTOTAL $132.800

    En la macro, la consulta quedó SE ACEPTA con VALOR ACEPTADO $2.400.

    DESPUÉS  39145 CONSULTA DE URGENCIAS   1,00   $83.400   →  VR ENT $83.400
             FMQ0046 VENDA DE GASA         5,00    $9.400   →  VR ENT $47.000
             SUBTOTAL $130.400

Se recalculan el VR UNIT, el subtotal, el total de la orden y el total en
letras. El formato del detallado no se toca: celdas combinadas, anchos, bordes
y formato de moneda quedan igual.

**El cruce no es por código a secas.** El detallado usa el código del hospital
(`FMQ0046`) y la macro el del ADRES (`2016DM-0000315-R2`), así que se reusa el
mismo motor de rondas del ajustador: código → descripción → cantidad+valor →
valor, con emparejamiento único. Lo que no cruza se informa, no se adivina.

USO (Windows, desde C:\\temp-notas):

    py tools\\descontar_aceptado_detallado.py ^
        --detallados "D:\\...\\EXCEL_POR_FACTURA" ^
        --macro      "D:\\...\\RTA GLOSA ADRES PAQ 31068 - ok ok.xlsx" ^
        --salida     "D:\\...\\POR_FACTURA_SIN_ACEPTADO" ^
        --bitacora   "D:\\...\\DESCUENTOS_31068.csv"

Requiere: py -m pip install openpyxl
"""

from __future__ import annotations

import argparse
import csv
import glob
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dinero import a_texto  # noqa: E402
from ajustar_detallado_glosas import (  # noqa: E402
    FilaGlosa,
    IndiceHoja,
    ItemReporte,
    _abrir_libro,
    _celdas_numericas,
    _norm,
    _parse_valor,
    detectar_estructura,
    emparejar,
    leer_bloques,
    normalizar_factura,
    recalcular_totales,
    segmentar_facturas,
)

logger = logging.getLogger("descontar_aceptado")

# Columnas de la macro (1-based), en el orden fijo que espera el VBA.
COL_FACTURA = 3
COL_CANT_RECLAMADA = 5
COL_VALOR_RECLAMADO = 6
COL_CANT_APROBADA = 7
COL_VALOR_APROBADO = 8
COL_VALOR_GLOSADO = 9
COL_TIPO_ELEMENTO = 12
COL_COD_ELEMENTO = 13
COL_DESC_ELEMENTO = 14
COL_DESC_GLOSA = 15
COL_OBSERVACION = 19
COL_VALOR_ACEPTADO = 23


@dataclass
class Descuento:
    """Lo que se le quitó a un ítem del detallado."""

    factura: str
    codigo: str
    nombre: str
    vr_ent_antes: float
    aceptado: float
    vr_ent_despues: float
    cruce: str
    causales: str = ""


@dataclass
class ResultadoFactura:
    factura: str
    archivo: str
    estado: str  # AJUSTADA | SIN_ACEPTADO | SIN_ESTRUCTURA | SIN_MACRO
    subtotal_antes: float = 0.0
    subtotal_despues: float = 0.0
    aceptado_macro: float = 0.0
    descuentos: list[Descuento] = field(default_factory=list)
    # El ítem del detallado al que corresponde cada descuento, en el mismo
    # orden: hace falta para saber si cuenta o no para el subtotal.
    items_tocados: list = field(default_factory=list)
    sin_cruzar: list[str] = field(default_factory=list)
    observacion: str = ""

    @property
    def descontado(self) -> float:
        return round(self.subtotal_antes - self.subtotal_despues, 2)


def leer_aceptados(ruta: Path) -> dict[str, list[FilaGlosa]]:
    """Las filas de la macro que quedaron con VALOR ACEPTADO > 0, por factura.

    Solo esas: son las que el hospital dejó de reclamar. Las SE OBJETA y las
    SE SUBSANA se siguen reclamando completas, así que no tocan el detallado.
    """
    wb = _abrir_libro(ruta, solo_datos=True, solo_lectura=True)
    try:
        ws = wb.worksheets[0]
        salida: dict[str, list[FilaGlosa]] = {}
        for fila in ws.iter_rows(min_row=2, values_only=True):
            if len(fila) < COL_VALOR_ACEPTADO:
                continue
            factura = str(fila[COL_FACTURA - 1] or "").strip()
            if not factura.upper().startswith("HUS"):
                continue
            aceptado = _parse_valor(fila[COL_VALOR_ACEPTADO - 1])
            if aceptado <= 0:
                continue
            salida.setdefault(normalizar_factura(factura), []).append(
                FilaGlosa(
                    factura=factura,
                    codigo=str(fila[COL_COD_ELEMENTO - 1] or "").strip(),
                    descripcion=str(fila[COL_DESC_ELEMENTO - 1] or "").strip(),
                    tipo_elemento=str(fila[COL_TIPO_ELEMENTO - 1] or "").strip(),
                    cant_reclamada=_parse_valor(fila[COL_CANT_RECLAMADA - 1]),
                    valor_reclamado=_parse_valor(fila[COL_VALOR_RECLAMADO - 1]),
                    cant_aprobada=_parse_valor(fila[COL_CANT_APROBADA - 1]),
                    valor_aprobado=_parse_valor(fila[COL_VALOR_APROBADO - 1]),
                    # Acá va el ACEPTADO, no el glosado: es lo que se descuenta.
                    valor_glosado=aceptado,
                    descripcion_glosa=str(fila[COL_DESC_GLOSA - 1] or "").strip(),
                )
            )
        return salida
    finally:
        wb.close()


def _subtotal_de_la_hoja(idx: IndiceHoja, est) -> float:
    """El VALOR SUBTOTAL que ya trae el archivo. Es el bueno: no se recalcula."""
    numeros = _celdas_numericas(idx.celdas(est.fila_subtotal))
    return round(_parse_valor(numeros[-1].valor), 2) if numeros else 0.0


def _desglose_cuenta(subtotal: float, items: list) -> bool:
    """¿Los renglones sin consecutivo suman en el subtotal de ESTA factura?

    No siempre. En 50 de las 320 facturas del paquete 31068 los honorarios de
    cirujano y de ayudantía vienen sin consecutivo —el lector los marca como
    desglose— pero sí están sumados en el subtotal. Se decide comparando: gana
    la suma que más se parezca al subtotal que trae el archivo.
    """
    con = round(sum(i.vr_ent for i in items), 2)
    sin = round(sum(i.vr_ent for i in items if not i.desglose), 2)
    return abs(subtotal - con) <= abs(subtotal - sin)


def _agrupar(glosas: list[FilaGlosa]) -> list[ItemReporte]:
    """Junta las filas de la macro que son el mismo ítem, sumando lo aceptado."""
    items: dict[tuple[str, str], ItemReporte] = {}
    for g in glosas:
        clave = (_norm(g.codigo), _norm(g.descripcion))
        item = items.get(clave)
        if item is None:
            item = ItemReporte(codigo=g.codigo, descripcion=g.descripcion, tipo=g.tipo_elemento)
            items[clave] = item
        item.filas.append(g)
    return list(items.values())


def procesar_archivo(
    ruta: Path, aceptados: dict[str, list[FilaGlosa]], destino: Path
) -> ResultadoFactura:
    """Descuenta lo aceptado en un detallado de una sola factura."""
    wb = _abrir_libro(ruta, solo_datos=False)
    try:
        ws = wb.worksheets[0]
        idx = IndiceHoja(ws)
        facturas = segmentar_facturas(idx)
        if not facturas:
            return ResultadoFactura(
                factura=ruta.stem,
                archivo=ruta.name,
                estado="SIN_ESTRUCTURA",
                observacion="No se encontró la cabecera de la factura en la hoja.",
            )
        fac = facturas[0]
        est = detectar_estructura(idx, fac)
        if est is None:
            return ResultadoFactura(
                factura=fac.factura or ruta.stem,
                archivo=ruta.name,
                estado="SIN_ESTRUCTURA",
                observacion="No se encontró la tabla de servicios (CÓDIGO/CANT/VR ENT).",
            )

        numero = fac.factura or ruta.stem
        clave = normalizar_factura(numero)
        bloques = leer_bloques(idx, est)
        # Se cruzan TODOS los ítems, incluidos los que el lector marca como
        # desglose: los honorarios de cirujano y de ayudantía vienen sin
        # consecutivo y aun así son servicios de verdad que se pueden aceptar.
        items = [it for b in bloques for it in b.items]
        # El subtotal NO se recalcula desde cero. Se toma el que ya trae el
        # archivo —que es el bueno, lo dejó el ajustador— y solo se le resta lo
        # que este bot descuente. Recalcularlo daba $106 millones de menos en
        # 50 facturas, porque en ellas los renglones de desglose SÍ cuentan.
        subtotal_antes = _subtotal_de_la_hoja(idx, est)
        cuentan_desglose = _desglose_cuenta(subtotal_antes, items)

        filas_macro = aceptados.get(clave, [])
        res = ResultadoFactura(
            factura=numero,
            archivo=ruta.name,
            estado="SIN_ACEPTADO",
            subtotal_antes=subtotal_antes,
            subtotal_despues=subtotal_antes,
            aceptado_macro=round(sum(f.valor_glosado for f in filas_macro), 2),
        )
        if not filas_macro:
            res.observacion = "La macro no trae ningún VALOR ACEPTADO para esta factura."
            destino.parent.mkdir(parents=True, exist_ok=True)
            wb.save(destino)
            return res

        reporte = _agrupar(filas_macro)
        pares, huerfanos = emparejar(items, reporte)

        for i, (rep, criterio) in pares.items():
            item = items[i]
            aceptado = round(rep.valor_glosado, 2)  # acá vive el ACEPTADO
            if aceptado <= 0:
                continue
            nuevo = round(item.vr_ent - aceptado, 2)
            if nuevo < 0:
                # Nunca dejar un servicio en negativo: se descuenta hasta cero y
                # se avisa, porque significa que el cruce o la macro no cuadran.
                res.sin_cruzar.append(
                    f"{item.codigo} {item.nombre[:40]}: aceptado ${aceptado:,.0f} "
                    f"es mayor que el valor del servicio ${item.vr_ent:,.0f}"
                )
                nuevo = 0.0
            res.items_tocados.append(item)
            res.descuentos.append(
                Descuento(
                    factura=numero,
                    codigo=item.codigo,
                    nombre=item.nombre,
                    vr_ent_antes=item.vr_ent,
                    aceptado=aceptado,
                    vr_ent_despues=nuevo,
                    cruce=criterio,
                    causales=rep.causales,
                )
            )
            if item.celda_vr_ent is not None:
                idx.escribir(item.celda_vr_ent, nuevo)
            # El VR UNIT se recalcula para que cuadre con la cantidad.
            if item.cantidad:
                unit = round(nuevo / item.cantidad, 2)
                for celda in idx.celdas(item.fila):
                    if celda is item.celda_vr_ent or celda is item.celda_cantidad:
                        continue
                    if _parse_valor(celda.valor) == item.vr_unit and item.vr_unit:
                        idx.escribir(celda, unit)
                        break
            item.vr_ent = nuevo

        for rep in huerfanos:
            res.sin_cruzar.append(
                f"{rep.codigo} {rep.descripcion[:40]}: aceptado "
                f"${rep.valor_glosado:,.0f} sin ítem en el detallado"
            )

        # Solo se le resta al subtotal lo que se descontó en ítems que cuentan.
        descontado = round(
            sum(
                d.vr_ent_antes - d.vr_ent_despues
                for d, it in zip(res.descuentos, res.items_tocados, strict=True)
                if cuentan_desglose or not it.desglose
            ),
            2,
        )
        subtotal_despues = round(subtotal_antes - descontado, 2)
        res.subtotal_despues = subtotal_despues
        res.estado = "AJUSTADA" if res.descuentos else "SIN_ACEPTADO"
        if res.descuentos:
            n_items = sum(1 for it in items if cuentan_desglose or not it.desglose)
            recalcular_totales(idx, fac, est, subtotal_despues, n_items)

        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        return res
    finally:
        wb.close()


def escribir_bitacora(ruta: Path, resultados: list[ResultadoFactura]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(
            [
                "FACTURA",
                "ESTADO",
                "SUBTOTAL_ANTES",
                "SUBTOTAL_DESPUES",
                "DESCONTADO",
                "ACEPTADO_EN_LA_MACRO",
                "CUADRA",
                "CODIGO",
                "SERVICIO",
                "VR_ENT_ANTES",
                "ACEPTADO",
                "VR_ENT_DESPUES",
                "CRUCE_POR",
                "CAUSALES",
                "AVISOS",
            ]
        )
        for r in sorted(resultados, key=lambda x: x.factura):
            cuadra = "SI" if abs(r.descontado - r.aceptado_macro) < 1 else "NO"
            avisos = " | ".join(r.sin_cruzar) or r.observacion
            if not r.descuentos:
                w.writerow(
                    [
                        r.factura,
                        r.estado,
                        f"{r.subtotal_antes:.2f}",
                        f"{r.subtotal_despues:.2f}",
                        "0.00",
                        f"{r.aceptado_macro:.2f}",
                        cuadra,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        avisos,
                    ]
                )
                continue
            for d in r.descuentos:
                w.writerow(
                    [
                        r.factura,
                        r.estado,
                        f"{r.subtotal_antes:.2f}",
                        f"{r.subtotal_despues:.2f}",
                        f"{r.descontado:.2f}",
                        f"{r.aceptado_macro:.2f}",
                        cuadra,
                        d.codigo,
                        d.nombre,
                        f"{d.vr_ent_antes:.2f}",
                        f"{d.aceptado:.2f}",
                        f"{d.vr_ent_despues:.2f}",
                        d.cruce,
                        d.causales,
                        avisos,
                    ]
                )


def _archivos(patron: str) -> list[Path]:
    p = Path(patron)
    if p.is_dir():
        return sorted(x for x in p.glob("*.xlsx") if not x.name.startswith("~$"))
    return sorted(Path(x) for x in glob.glob(patron) if not Path(x).name.startswith("~$"))


def procesar(
    detallados: str, macro: Path, salida: Path, bitacora: Path | None = None
) -> list[ResultadoFactura]:
    archivos = _archivos(detallados)
    if not archivos:
        raise ValueError(f"No se encontró ningún Excel en {detallados!r}")
    aceptados = leer_aceptados(macro)
    logger.info(
        "Macro: %d factura(s) con VALOR ACEPTADO, por $%s",
        len(aceptados),
        f"{sum(f.valor_glosado for v in aceptados.values() for f in v):,.0f}".replace(",", "."),
    )
    resultados = []
    for n, ruta in enumerate(archivos, 1):
        try:
            res = procesar_archivo(ruta, aceptados, salida / ruta.name)
        except Exception as e:  # noqa: BLE001 - una factura mala no tumba el lote
            logger.warning("  %s: %s", ruta.name, e)
            res = ResultadoFactura(
                factura=ruta.stem, archivo=ruta.name, estado="ERROR", observacion=str(e)
            )
        resultados.append(res)
        if n % 50 == 0:
            logger.info("  %d/%d…", n, len(archivos))
    if bitacora:
        escribir_bitacora(bitacora, resultados)
    return resultados


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Le descuenta al detallado de cada factura el VALOR ACEPTADO de la macro."
    )
    p.add_argument("--detallados", required=True, help="Carpeta o patrón de los Excel por factura")
    p.add_argument("--macro", required=True, type=Path, help="Excel de la macro con las respuestas")
    p.add_argument("--salida", required=True, type=Path, help="Carpeta donde dejar los ajustados")
    p.add_argument("--bitacora", type=Path, help="CSV con el detalle de lo descontado")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = construir_parser().parse_args(argv)
    try:
        resultados = procesar(args.detallados, args.macro, args.salida, args.bitacora)
    except Exception as e:  # noqa: BLE001 - mensaje claro para el auditor
        logger.error("No se pudo procesar: %s", e)
        return 1

    ajustadas = [r for r in resultados if r.estado == "AJUSTADA"]
    con_avisos = [r for r in resultados if r.sin_cruzar]
    errores = [r for r in resultados if r.estado == "ERROR"]
    descuadradas = [r for r in resultados if abs(r.descontado - r.aceptado_macro) >= 1]

    print()
    print(f"Facturas procesadas   : {len(resultados)}")
    print(f"  con descuento        : {len(ajustadas)}")
    print(f"  sin nada que aceptar : {len(resultados) - len(ajustadas) - len(errores)}")
    print(f"Total antes           : {a_texto(sum(r.subtotal_antes for r in resultados))}")
    print(f"Total descontado      : {a_texto(sum(r.descontado for r in resultados))}")
    print(f"TOTAL FINAL           : {a_texto(sum(r.subtotal_despues for r in resultados))}")
    if descuadradas:
        print(f"\nOJO — {len(descuadradas)} factura(s) donde lo descontado NO cuadra con la macro:")
        for r in sorted(descuadradas, key=lambda x: -abs(x.descontado - x.aceptado_macro))[:10]:
            print(
                f"   {r.factura:<12} descontado {a_texto(r.descontado):>14}  "
                f"macro {a_texto(r.aceptado_macro):>14}"
            )
    if con_avisos:
        print(f"\n{len(con_avisos)} factura(s) con avisos de cruce (ver la bitácora).")
    if errores:
        print(f"\n{len(errores)} factura(s) con error:")
        for r in errores[:5]:
            print(f"   {r.factura}: {r.observacion[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
