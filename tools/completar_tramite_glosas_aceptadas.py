"""Completa RESPUESTA/NO/FECHA DE TRAMITE Y/O ACTA en el consolidado de glosas aceptadas.

Cruza el archivo mensual de glosas aceptadas (hoja BD) contra la hoja GENERAL de la
CIRCULARIZACION DE GLOSAS para llenar, en las filas de tipo ACTA que estan pendientes:

  - col W  RESPUESTA TRAMITE GLOSA Y/O ACTA  (conceptos de conciliacion unificados)
  - col X  NO DE TRAMITE Y/O ACTA            (numero de acta)
  - col Y  FECHA DE TRAMITE Y/O ACTA         (fecha de firma del acta)

Reglas de resolucion, por fila pendiente:
  1. Se busca la factura en GENERAL, restringida al acta citada en OBSERVC NOTA
     CREDITO (col I) cuando esa acta existe alli para la factura.
  2. Si un subconjunto de las glosas del acta suma exactamente el VALOR ACEPTADO de
     la nota, la respuesta son esos conceptos unificados (separados por " | ").
  3. Si no cuadra la suma, o la factura no esta en la circularizacion (p.ej. actas de
     vigencia 2025), la respuesta se toma del texto de la propia observacion de la
     nota credito (la parte posterior a "DONDE"/"EN LA CUAL"/nro de acta), que es el
     mismo concepto del acta con el valor efectivamente acreditado.
  4. Numero y fecha de acta salen de GENERAL cuando la factura esta alli; si no, de
     la observacion de la nota credito. Diferencias (valor o numero de acta citado
     vs registrado) quedan en el reporte de revision.

Uso:
    python tools/completar_tramite_glosas_aceptadas.py ACEPTADAS.xlsx CIRCULARIZACION.xlsx SALIDA.xlsx [REPORTE.csv]
"""

import csv
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime

import openpyxl

# Columnas (0-based) de la hoja BD del archivo de glosas aceptadas
BD_FACTURA, BD_OBS, BD_VALOR = 2, 8, 9
BD_RESPUESTA, BD_NUM, BD_FECHA, BD_TIPO_TRAMITE = 22, 23, 24, 26
BD_HEADER_ROW = 4

# Columnas (0-based) de la hoja GENERAL de la circularizacion
GEN_FACTURA, GEN_VAL_ACEPTADO, GEN_ACTA, GEN_FECHA, GEN_CONCEPTO = 1, 5, 11, 12, 13

RE_ACTA = re.compile(r"ACTA\s*(?:DE\s+CONCILIACI\w+\s*)?(?:N\s*[°º\.]?\s*)?(\d{3,4})", re.I)
RE_FECHA_DMA = re.compile(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})")
MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
         "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
         "DICIEMBRE": 12}
RE_FECHA_TEXTO = re.compile(r"(\d{1,2})\s+DE\s+(" + "|".join(MESES) + r")\s+DE\s+(\d{4})", re.I)


def limpiar(texto):
    if texto is None:
        return ""
    return str(texto).replace("_x000D_", "").replace("\r", "").strip()


def a_numero(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return round(float(v))
    try:
        return round(float(str(v).replace(",", "").strip()))
    except ValueError:
        return 0


def a_fecha(v):
    if isinstance(v, datetime):
        return v
    s = limpiar(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parsear_obs(obs):
    """Extrae (acta, fecha, respuesta) de la observacion de la nota credito."""
    texto = limpiar(obs)
    m = RE_ACTA.search(texto)
    acta = int(m.group(1)) if m else None
    fecha = None
    resto = texto[m.end():] if m else texto
    mf = RE_FECHA_DMA.search(resto[:60])
    if mf:
        d, mth, y = (int(x) for x in mf.groups())
        try:
            fecha = datetime(y, mth, d)
        except ValueError:
            fecha = None
    else:
        mt = RE_FECHA_TEXTO.search(resto[:80])
        if mt:
            try:
                fecha = datetime(int(mt.group(3)), MESES[mt.group(2).upper()], int(mt.group(1)))
            except ValueError:
                fecha = None

    respuesta = ""
    ancla = re.search(r"DONDE\s*:?|EN LA CUAL\s*[;:]?", resto, re.I)
    if ancla:
        respuesta = resto[ancla.end():]
    else:
        inicio = re.search(r"EN CONCILI\w+|ESE HUS", resto, re.I)
        if inicio:
            respuesta = resto[inicio.start():]
    respuesta = respuesta.strip(" :;,.\n")
    # colapsa el texto cuando la observacion trae la misma respuesta duplicada
    mitad = len(respuesta) // 2
    if mitad > 40:
        a, b = respuesta[:mitad].strip(" .\n"), respuesta[mitad:].strip(" .\n")
        if a and a == b:
            respuesta = a
    return acta, fecha, respuesta.strip()


def buscar_subconjunto(vals, objetivo):
    """Indices cuyo valor suma exactamente `objetivo`; None si no existe."""
    no_cero = [(i, v) for i, v in enumerate(vals) if v > 0]
    if objetivo == sum(v for _, v in no_cero):
        return list(range(len(vals)))  # todas las filas, incluidas las de valor 0
    for i, v in no_cero:
        if v == objetivo:
            return [i]
    alcanzables = {0: []}
    for i, v in no_cero:
        nuevos = {}
        for s, idxs in alcanzables.items():
            ns = s + v
            if ns <= objetivo and ns not in alcanzables and ns not in nuevos:
                nuevos[ns] = idxs + [i]
        alcanzables.update(nuevos)
        if len(alcanzables) > 500000:
            break
    return alcanzables.get(objetivo)


def cargar_general(ruta):
    wb = openpyxl.load_workbook(ruta, read_only=True)
    ws = wb["GENERAL"]
    por_factura = defaultdict(list)
    for fila in ws.iter_rows(min_row=3, values_only=True):
        factura = limpiar(fila[GEN_FACTURA])
        if not factura.upper().startswith("HUS"):
            continue
        acta = a_numero(fila[GEN_ACTA])
        por_factura[factura.upper()].append({
            "val": a_numero(fila[GEN_VAL_ACEPTADO]),
            "acta": acta or None,
            "fecha": a_fecha(fila[GEN_FECHA]),
            "concepto": limpiar(fila[GEN_CONCEPTO]),
        })
    wb.close()
    return por_factura


def resolver_fila(factura, valor, obs, general):
    """Devuelve (respuesta, acta, fecha, notas_de_revision)."""
    acta_obs, fecha_obs, resp_obs = parsear_obs(obs)
    notas = []
    candidatas = general.get(factura.upper(), [])

    grupo = []
    if candidatas:
        por_acta = defaultdict(list)
        for c in candidatas:
            por_acta[c["acta"]].append(c)
        if acta_obs in por_acta:
            grupo = por_acta[acta_obs]
        else:
            con_cuadre = [g for g in por_acta.values()
                          if buscar_subconjunto([c["val"] for c in g], valor)]
            candidatos = con_cuadre or list(por_acta.values())
            grupo = max(candidatos, key=lambda g: g[0]["fecha"] or datetime.min)
            if acta_obs and grupo:
                notas.append(f"NC cita acta {acta_obs}; circularizacion la registra en acta {grupo[0]['acta']}")

    if grupo:
        acta, fecha = grupo[0]["acta"], grupo[0]["fecha"]
        subconjunto = buscar_subconjunto([c["val"] for c in grupo], valor)
        if subconjunto is not None:
            conceptos = list(dict.fromkeys(
                grupo[i]["concepto"] for i in subconjunto if grupo[i]["concepto"]))
            return " | ".join(conceptos), acta, fecha, notas
        total = sum(c["val"] for c in grupo)
        notas.append(f"valor aceptado {valor:,} no cuadra con el acta ({total:,}); respuesta tomada de la observacion de la NC")
        if resp_obs:
            return resp_obs, acta, fecha, notas
        notas.append("sin texto extraible en la observacion; se unifican todos los conceptos del acta")
        return " | ".join(c["concepto"] for c in grupo if c["concepto"]), acta, fecha, notas

    notas.append("factura no esta en la circularizacion; datos tomados de la observacion de la NC")
    return resp_obs, acta_obs, fecha_obs, notas


def normalizar_encabezado(v):
    s = unicodedata.normalize("NFD", limpiar(v).upper())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    ruta_bd, ruta_circ, ruta_salida = sys.argv[1:4]
    ruta_reporte = sys.argv[4] if len(sys.argv) > 4 else None

    general = cargar_general(ruta_circ)
    wb = openpyxl.load_workbook(ruta_bd)
    ws = wb["BD"]

    encabezado = [normalizar_encabezado(c.value) for c in ws[BD_HEADER_ROW]]
    assert "RESPUESTA TRAMITE" in encabezado[BD_RESPUESTA], encabezado[BD_RESPUESTA]

    reporte, llenas = [], 0
    for fila in ws.iter_rows(min_row=BD_HEADER_ROW + 1):
        factura = limpiar(fila[BD_FACTURA].value)
        if not factura:
            continue
        pendiente = (not limpiar(fila[BD_RESPUESTA].value)
                     and fila[BD_NUM].value is None and fila[BD_FECHA].value is None)
        if not pendiente:
            continue
        valor = a_numero(fila[BD_VALOR].value)
        respuesta, acta, fecha, notas = resolver_fila(
            factura, valor, fila[BD_OBS].value, general)
        if respuesta:
            fila[BD_RESPUESTA].value = respuesta
        if acta:
            fila[BD_NUM].value = acta
        if fecha:
            fila[BD_FECHA].value = fecha
            fila[BD_FECHA].number_format = "dd/mm/yyyy"
        llenas += 1
        if not (respuesta and acta and fecha):
            notas.append("INCOMPLETA: revisar manualmente")
        for n in notas:
            reporte.append({"fila": fila[0].row, "factura": factura,
                            "valor_aceptado": valor, "acta": acta, "nota": n})

    wb.save(ruta_salida)
    print(f"Filas diligenciadas: {llenas}")
    print(f"Archivo generado: {ruta_salida}")
    if ruta_reporte:
        with open(ruta_reporte, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["fila", "factura", "valor_aceptado", "acta", "nota"])
            w.writeheader()
            w.writerows(reporte)
        print(f"Reporte de revision ({len(reporte)} notas): {ruta_reporte}")
    else:
        for r in reporte:
            print(f"  fila {r['fila']} {r['factura']}: {r['nota']}")


if __name__ == "__main__":
    main()
