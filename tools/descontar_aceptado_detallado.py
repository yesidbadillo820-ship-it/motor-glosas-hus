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


def _contador_de_items(idx: IndiceHoja, est) -> int | None:
    """La casilla de 'cuántos servicios' de la fila del subtotal, si existe.

    En esa fila hay dos números: la cantidad de ítems y el importe. El importe
    es el último. Se devuelve el otro tal cual, para volver a escribirlo igual.
    """
    numeros = _celdas_numericas(idx.celdas(est.fila_subtotal))
    return int(_parse_valor(numeros[-2].valor)) if len(numeros) > 1 else None


def _cuentan_por_bloque(items: list) -> list[bool]:
    """Qué renglones suman al subtotal, decidido bloque por bloque.

    Una cirugía se imprime así: un renglón CON consecutivo (el procedimiento,
    con su valor total) y debajo, SIN consecutivo, el desglose de ese valor —
    cirujano, anestesiólogo, ayudantía, derechos de sala, materiales—. Ese
    desglose **no vuelve a sumar**: ya está dentro del procedimiento.

    Pero cuando al paciente le hicieron VARIAS cirugías, debajo del mismo
    procedimiento se imprimen los honorarios de todas, y los de la segunda en
    adelante **sí suman**, porque no están dentro de ningún renglón.

    Se resuelve acumulando: los primeros renglones sin consecutivo se van
    sumando hasta completar exactamente el valor del procedimiento que tienen
    encima —ese es su desglose y no cuenta—; lo que siga después es cirugía
    aparte y sí cuenta.

    El caso que lo enseñó es la HUS388262: dos osteosíntesis y cuatro tandas de
    honorarios. La regla anterior decidía de una sola vez para toda la factura
    y dejó el subtotal $1.400.050 por encima de lo que correspondía.
    """
    cuenta = [True] * len(items)
    i = 0
    while i < len(items):
        if not items[i].desglose:
            i += 1
            continue
        fin = i
        while fin < len(items) and items[fin].desglose:
            fin += 1
        padre = items[i - 1] if i > 0 and not items[i - 1].desglose else None
        if padre is not None:
            acumulado = 0.0
            for k in range(i, fin):
                acumulado = round(acumulado + items[k].vr_ent, 2)
                cuenta[k] = False
                if abs(acumulado - padre.vr_ent) < 0.01:
                    break  # acá se completó el desglose del procedimiento
            else:
                # Nunca cuadró con el padre: no es su desglose, sí cuenta.
                for k in range(i, fin):
                    cuenta[k] = True
        i = fin
    return cuenta


def filas_que_cuentan(items: list, subtotal: float) -> tuple[list[bool], bool]:
    """(qué renglones suman, ¿el modelo cuadra con el subtotal del archivo?)

    La comprobación de cierre del bot: si la suma de los renglones que el
    modelo da por buenos **no** reproduce el subtotal que trae el archivo, es
    que esta factura no se entendió. En ese caso solo se dan por seguros los
    renglones con consecutivo —que siempre suman— y la factura queda marcada
    para que el auditor la revise: nunca se escribe un subtotal que no se pueda
    justificar.

    En el paquete 31068 el modelo cuadra en 318 de las 320 facturas.
    """
    cuenta = _cuentan_por_bloque(items)
    if (
        abs(round(sum(i.vr_ent for i, c in zip(items, cuenta, strict=True) if c), 2) - subtotal)
        < 0.01
    ):
        return cuenta, True
    return [not i.desglose for i in items], False


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
        cuenta_fila, cuadra = filas_que_cuentan(items, subtotal_antes)
        cuentan = {id(it): c for it, c in zip(items, cuenta_fila, strict=True)}
        # El contador de ítems de la fila del subtotal se conserva tal como lo
        # dejó el sistema del hospital: este bot cambia valores, nunca borra
        # servicios, así que no tiene por qué moverlo.
        n_items_original = _contador_de_items(idx, est)

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
                if cuentan[id(it)]
            ),
            2,
        )
        subtotal_despues = round(subtotal_antes - descontado, 2)
        res.subtotal_despues = subtotal_despues
        res.estado = "AJUSTADA" if res.descuentos else "SIN_ACEPTADO"
        if not cuadra:
            res.sin_cruzar.append(
                "REVISAR A MANO: no se pudo reproducir el subtotal del archivo "
                f"(${subtotal_antes:,.0f}) con los renglones de la factura, así que "
                "solo se descontaron los servicios numerados"
            )
        if res.descuentos:
            recalcular_totales(idx, fac, est, subtotal_despues, n_items_original)

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
