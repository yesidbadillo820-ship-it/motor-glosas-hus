"""Arma el ACTA SINAC a partir de la lista de facturas y el archivo de la EPS.

EL TRABAJO QUE REEMPLAZA. Antes de cada mesa de conciliación, alguien copiaba
a mano —factura por factura, renglón por renglón— los datos del archivo que
manda la EPS al formato del acta. Cien facturas son doscientos y pico de
renglones, y cada uno con nueve datos que trasladar. Es media jornada, y un
número mal copiado se discute en la mesa como si fuera real.

CÓMO FUNCIONA. Entran dos archivos y salen las líneas del acta:

  · **la lista de facturas** — una columna de Excel con las que van a esta
    mesa (`HUS0000542497`, `542497`, `HUS542497`: se reconocen las tres);
  · **el archivo de la EPS** — el consolidado con una fila por glosa.

Se cruzan por número de factura y se arma una línea por glosa.

LO QUE SE DEDUCE Y LO QUE NO. La tipificación sale del código de glosa, que
la determina sin ambigüedad (CL→PERTINENCIA, FA→FACTURACIÓN, SO→SOPORTES,
TA→TARIFAS). El TIPO también, pero **solo para tres de ellas**: facturación,
soportes y tarifas son siempre ADMINISTRATIVA.

Las de PERTINENCIA se reparten entre MIXTA y MÉDICO —46 y 25 en el acta 709
del Dispensario— y **eso no lo decide un código, lo decide un médico
auditor**. Esas líneas salen marcadas para que las reparta una persona, y no
se rellenan con la más común: en una mesa de conciliación, un tipo mal puesto
manda la glosa al abogado equivocado.

LA MEMORIA. Cada reparto que hace un humano queda guardado por factura y
código (`ConciliacionTipificacionRecord`). La próxima vez que esa misma glosa
aparezca —y aparecen, son las mismas cuentas de siempre— el armador ya sabe
qué era. Con el tiempo hasta las de pertinencia se llenan solas.

Se apoya en las estructuras que ya existen en `acta_conciliacion_excel`
(`Acta`, `LineaActa`), así que lo que sale de acá se puede pasar tal cual por
el `revisar()` de ese módulo: el acta no solo llega llena, llega cuadrada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Any, Optional

from app.services.acta_conciliacion_excel import Acta, LineaActa

# ── El prefijo de las facturas del hospital y su ancho ──────────────────
PREFIJO_HUS = "HUS"
ANCHO_NUMERO = 10

# ── Del código de glosa a la tipificación ───────────────────────────────
# Sale del Manual Único: las dos primeras letras del código son la familia.
# Verificado contra el acta 709 del Dispensario: 71 CL, 50 FA, 52 SO y 84 TA,
# sin una sola excepción.
TIPIFICACION_POR_FAMILIA: dict[str, str] = {
    "CL": "PERTINENCIA",
    "FA": "FACTURACION",
    "SO": "SOPORTES",
    "TA": "TARIFAS",
}

# ── De la tipificación al tipo de glosa ─────────────────────────────────
# Solo estas tres son deterministas. PERTINENCIA queda fuera a propósito:
# se reparte entre MIXTA y MÉDICO según el caso clínico, y eso lo decide
# una persona. Ver la cabecera del módulo.
TIPO_POR_TIPIFICACION: dict[str, str] = {
    "FACTURACION": "ADMINISTRATIVA",
    "SOPORTES": "ADMINISTRATIVA",
    "TARIFAS": "ADMINISTRATIVA",
}
TIPIFICACION_QUE_DECIDE_UN_HUMANO = "PERTINENCIA"


def _sin_tildes(texto: Any) -> str:
    s = str(texto or "")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper().strip()


def _solo_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def clave_factura(valor: Any) -> str:
    """La llave con la que se cruzan los dos archivos.

    Se queda con los dígitos y les quita los ceros de la izquierda, así
    `HUS0000542497`, `542497` y `HUS542497` son la misma factura. Sin esto el
    cruce falla en silencio y el acta sale vacía sin decir por qué.
    """
    return _solo_digitos(valor).lstrip("0")


def factura_larga(valor: Any, prefijo: str = PREFIJO_HUS) -> str:
    """El número como lo quiere el acta: HUS + 10 dígitos con ceros."""
    digitos = _solo_digitos(valor)
    if not digitos:
        return ""
    return f"{prefijo}{digitos.zfill(ANCHO_NUMERO)}"


def cod_glosa_normalizado(valor: Any) -> str:
    """«CL03 01 CALIDAD-HONORARIOS…» → «CL0301». También «so23 01» → «SO2301».

    La EPS escribe el código con un espacio en medio y a veces en minúscula,
    y le pega la descripción. El acta lo quiere pegado y en mayúscula.
    """
    texto = _sin_tildes(valor)
    m = re.match(r"\s*([A-Z]{2})\s*(\d{2})\s*(\d{2})", texto)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = re.match(r"\s*([A-Z]{2})\s*(\d{3,4})", texto)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return ""


def familia_de(cod: str) -> str:
    return (cod or "")[:2].upper()


# ═══════════════════════════════════════════════════════════════════════
#  Lo que entra
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class Encabezado:
    """Lo que el auditor escribe en la pantalla antes de generar."""

    nit: str = ""
    razon_social: str = ""
    fecha_conciliacion: Optional[date] = None
    numero_acta: str = ""
    periodo: str = ""


@dataclass
class Aviso:
    """Algo que el armador no pudo resolver solo. No es un error: es una
    casilla que tiene que llenar una persona, dicha en voz alta."""

    factura: str
    motivo: str
    fila_excel: int = 0


@dataclass
class Resultado:
    acta: Acta
    avisos: list[Aviso] = field(default_factory=list)
    # Facturas de la lista que el archivo de la EPS no menciona.
    sin_glosas: list[str] = field(default_factory=list)
    # Facturas del archivo de la EPS que no estaban en la lista.
    fuera_de_lista: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
#  Leer la lista de facturas
# ═══════════════════════════════════════════════════════════════════════
# Encabezados que se descartan si aparecen en la primera fila. La lista real
# del auditor NO trae encabezado, pero cuesta nada tolerarlo.
_ENCABEZADOS_LISTA = ("FACTURA", "FACTURAS", "NUMERO FACTURA", "NRO FACTURA", "N FACTURA")


def leer_lista_facturas(contenido: bytes) -> list[str]:
    """Las facturas que van a esta mesa. Una columna de Excel.

    Se toman TODAS las columnas con datos, no solo la A: si el auditor pega
    la lista en la B porque en la A tenía otra cosa, igual funciona. Se
    conserva el orden en que vienen, que es el orden con el que el auditor
    va a trabajar en la mesa.
    """
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    vistas: set[str] = set()
    facturas: list[str] = []
    for ws in wb.worksheets:
        for fila in ws.iter_rows(values_only=True):
            for celda in fila:
                if celda in (None, ""):
                    continue
                if _sin_tildes(celda) in _ENCABEZADOS_LISTA:
                    continue
                clave = clave_factura(celda)
                if not clave or clave in vistas:
                    continue
                vistas.add(clave)
                facturas.append(clave)
    wb.close()
    return facturas


# ═══════════════════════════════════════════════════════════════════════
#  Leer el archivo de la EPS
# ═══════════════════════════════════════════════════════════════════════
# Qué columna es cuál, buscada POR NOMBRE y no por posición: cada EPS manda
# el consolidado con las columnas en otro orden, y basta con que agreguen una
# al principio para que un índice fijo lea todo corrido.
_COLUMNAS_EPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prefijo", ("PREFIJO",)),
    ("factura", ("FACTURA",)),
    ("radicado", ("RADICADO",)),
    ("numero_acta", ("NUMERO ACTA RESPUESTA", "NUMERO ACTA")),
    ("fecha_atencion", ("FECHA ATENCION",)),
    ("fecha_radicacion", ("FECHA RADICACION",)),
    ("valor_factura", ("VALOR FACTURA",)),
    ("cod_glosa", ("CODIGO CONCEPTO DE GLOSA", "CODIGO GLOSA")),
    ("motivo", ("MOTIVO DE GLOSA", "MOTIVO GLOSA")),
    ("valor_objetado", ("VALOR OBJETADO",)),
    ("servicio", ("SERVICIO OBJETADO",)),
    ("respuesta_ips", ("RESPUESTA A GLOSA POR IPS EN RTA_GLOSA", "RESPUESTA A GLOSA POR IPS")),
    ("respuesta_auditor", ("RESPUESTA AUDITOR A IPS EN RTA_GLOSA",)),
)


def _indice_columnas(fila_encabezado: tuple) -> dict[str, int]:
    """Empareja los encabezados con los campos. Gana el más específico:
    «FACTURA» no debe robarse la columna de «VALOR FACTURA»."""
    encabezados = [
        (_sin_tildes(v), i) for i, v in enumerate(fila_encabezado) if v not in (None, "")
    ]
    indice: dict[str, int] = {}
    for campo, etiquetas in _COLUMNAS_EPS:
        for etiqueta in etiquetas:
            exacto = next((i for texto, i in encabezados if texto == etiqueta), None)
            if exacto is not None:
                indice[campo] = exacto
                break
    return indice


def leer_archivo_eps(contenido: bytes) -> tuple[list[dict], dict[str, int]]:
    """Una fila por glosa. Devuelve las filas y qué columna era cuál.

    El encabezado se busca en las primeras filas en vez de darlo por hecho en
    la primera: estos consolidados suelen traer un título o un logo encima.
    """
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    ws = wb.worksheets[0]
    filas = list(ws.iter_rows(values_only=True))
    wb.close()

    indice: dict[str, int] = {}
    inicio = 0
    for n, fila in enumerate(filas[:10]):
        candidato = _indice_columnas(fila)
        if "factura" in candidato and "valor_objetado" in candidato:
            indice, inicio = candidato, n + 1
            break
    if not indice:
        return [], {}

    salida: list[dict] = []
    for n, fila in enumerate(filas[inicio:], start=inicio + 1):

        def dato(campo: str) -> Any:
            i = indice.get(campo)
            return fila[i] if i is not None and i < len(fila) else None

        if not dato("factura"):
            continue
        salida.append(
            {
                "fila_excel": n,
                "prefijo": str(dato("prefijo") or PREFIJO_HUS).strip() or PREFIJO_HUS,
                "factura": dato("factura"),
                "radicado": dato("radicado"),
                "numero_acta": dato("numero_acta"),
                "fecha_atencion": dato("fecha_atencion"),
                "fecha_radicacion": dato("fecha_radicacion"),
                "valor_factura": dato("valor_factura"),
                "cod_glosa": dato("cod_glosa"),
                "motivo": dato("motivo"),
                "valor_objetado": dato("valor_objetado"),
                "servicio": dato("servicio"),
                "respuesta_ips": dato("respuesta_ips"),
                "respuesta_auditor": dato("respuesta_auditor"),
            }
        )
    return salida, indice


# ═══════════════════════════════════════════════════════════════════════
#  Armar
# ═══════════════════════════════════════════════════════════════════════


def _dinero(valor: Any) -> float:
    if valor in (None, ""):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = re.sub(r"[^\d,.\-]", "", str(valor))
    if limpio.count(",") and limpio.count("."):
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count(","):
        limpio = limpio.replace(",", ".")
    try:
        return float(limpio or 0)
    except ValueError:
        return 0.0


def _fecha(valor: Any) -> str:
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")
    return str(valor or "").strip()


def armar(
    facturas: list[str],
    filas_eps: list[dict],
    encabezado: Encabezado,
    memoria: Optional[dict[tuple[str, str], str]] = None,
) -> Resultado:
    """Cruza las dos entradas y devuelve el acta lista para la mesa.

    `memoria` es lo aprendido de mesas anteriores: `(factura, cod) -> TIPO`.
    Es lo que va llenando solas las líneas de pertinencia con el tiempo.
    """
    memoria = memoria or {}
    en_lista = {clave_factura(f) for f in facturas if clave_factura(f)}
    orden = {clave: n for n, clave in enumerate(facturas)}

    lineas: list[LineaActa] = []
    avisos: list[Aviso] = []
    con_glosa: set[str] = set()
    fuera: list[str] = []

    pertinentes = []
    for fila in filas_eps:
        clave = clave_factura(fila["factura"])
        if not clave:
            continue
        if clave not in en_lista:
            if clave not in fuera:
                fuera.append(clave)
            continue
        con_glosa.add(clave)
        pertinentes.append((orden.get(clave, 10**6), fila))

    # El orden del acta es el de la lista del auditor, no el del archivo de
    # la EPS: así puede ir siguiéndola de arriba abajo en la mesa.
    pertinentes.sort(key=lambda p: p[0])

    for item, (_, fila) in enumerate(pertinentes, start=1):
        cod = cod_glosa_normalizado(fila["cod_glosa"])
        familia = familia_de(cod)
        tipificacion = TIPIFICACION_POR_FAMILIA.get(familia, "")
        larga = factura_larga(fila["factura"], str(fila["prefijo"]))

        tipo = TIPO_POR_TIPIFICACION.get(tipificacion, "")
        if not tipo:
            recordado = memoria.get((clave_factura(larga), cod))
            if recordado:
                tipo = recordado

        if not cod:
            avisos.append(
                Aviso(
                    larga,
                    f"No se pudo leer el código de glosa de «{str(fila['cod_glosa'])[:40]}»",
                    fila["fila_excel"],
                )
            )
        elif not tipificacion:
            avisos.append(
                Aviso(
                    larga,
                    f"El código {cod} es de una familia que el acta modelo no usa "
                    f"({familia}): hay que escribir la tipificación a mano",
                    fila["fila_excel"],
                )
            )
        elif not tipo and tipificacion == TIPIFICACION_QUE_DECIDE_UN_HUMANO:
            avisos.append(
                Aviso(
                    larga,
                    f"{cod} es de PERTINENCIA: falta decir si es MIXTA o MÉDICO "
                    "(lo decide el médico auditor)",
                    fila["fila_excel"],
                )
            )

        glosa = _dinero(fila["valor_objetado"])
        lineas.append(
            LineaActa(
                fila_excel=0,
                item=str(item),
                radicado=str(fila["numero_acta"] or fila["radicado"] or "").strip(),
                factura=larga,
                fecha_factura=_fecha(fila["fecha_atencion"]),
                tipo_glosa=tipo,
                tipificacion=tipificacion,
                cod_glosa=cod,
                descripcion=str(fila["motivo"] or fila["servicio"] or "").strip(),
                valor_factura=_dinero(fila["valor_factura"]),
                glosa_inicial=glosa,
                # Todo lo glosado entra a la mesa sin repartir: los valores de
                # aceptar, levantar y ratificar se escriben EN la audiencia.
                pendiente=glosa,
                acepta_ips=0.0,
                levanta_entidad=0.0,
                ratificado=0.0,
                texto_conciliacion="",
            )
        )

    sin_glosas = [f for f in facturas if clave_factura(f) not in con_glosa]

    acta = Acta(
        nit=encabezado.nit,
        razon_social=encabezado.razon_social,
        periodo=encabezado.periodo,
        cantidad_facturas_declarada=len(con_glosa),
        valor_a_conciliar_declarado=round(sum(x.glosa_inicial for x in lineas), 2),
        lineas=lineas,
    )
    return Resultado(acta=acta, avisos=avisos, sin_glosas=sin_glosas, fuera_de_lista=fuera)


# ═══════════════════════════════════════════════════════════════════════
#  Escribir el acta sobre el modelo
# ═══════════════════════════════════════════════════════════════════════
# Las casillas del encabezado se buscan POR SU ETIQUETA y se escribe en la
# celda de al lado, igual que hace `leer_acta` al leerlas. Si mañana el
# formato mueve una columna, esto sigue funcionando; con coordenadas fijas,
# el acta saldría con el NIT en el lugar de la razón social.
_CASILLAS_ENCABEZADO: tuple[tuple[str, str], ...] = (
    ("NIT", "nit"),
    ("RAZON SOCIAL", "razon_social"),
    ("FECHA CONCILIACION", "fecha_conciliacion"),
    ("NUMERO ACTA", "numero_acta"),
    ("PERIODO", "periodo"),
    ("CANTIDAD FACTURAS", "cantidad_facturas"),
    ("VALOR A CONCILIAR", "valor_a_conciliar"),
)

# El orden de las columnas de la tabla, por su etiqueta en la fila 11.
_COLUMNAS_ACTA: tuple[tuple[str, str], ...] = (
    ("ITEM", "item"),
    ("RADICADO", "radicado"),
    ("NUMERO FACTURA", "factura"),
    ("FECHA FACTURA", "fecha_factura"),
    ("TIPO DE GLOSA", "tipo_glosa"),
    ("TIPIFICACION", "tipificacion"),
    ("COD GLOSA", "cod_glosa"),
    ("DESCRIPCION GLOSA", "descripcion"),
    ("VALOR FACTURA", "valor_factura"),
    ("VALOR GLOSA INICIAL", "glosa_inicial"),
    ("VALOR PENDIENTE", "pendiente"),
    ("VALOR ACEPTA IPS", "acepta_ips"),
    ("VALOR LEVANTA", "levanta_entidad"),
    ("VALOR RATIFICADO", "ratificado"),
    ("DESCRIPCION DE CONCILIACION", "texto_conciliacion"),
)

_MARCA_FALTA_HUMANO = "◄ DEFINIR"


def _escribir(ws, fila: int, col: int, valor: Any) -> bool:
    """Escribe respetando las celdas combinadas del formato oficial.

    El encabezado del acta modelo tiene casi todas sus casillas combinadas
    —el NIT ocupa tres columnas, la razón social ocho— y openpyxl solo deja
    escribir en la celda de arriba a la izquierda del grupo: en cualquier
    otra levanta «attribute is read-only». Sin esto, generar el acta se cae
    en la primera casilla del encabezado.

    Devuelve False si el sitio ya estaba ocupado, para que quien llama siga
    buscando a la derecha.
    """
    from openpyxl.cell.cell import MergedCell

    celda = ws.cell(fila, col)
    if isinstance(celda, MergedCell):
        for rango in ws.merged_cells.ranges:
            if (rango.min_row <= fila <= rango.max_row) and (rango.min_col <= col <= rango.max_col):
                celda = ws.cell(rango.min_row, rango.min_col)
                break
        else:
            return False
    if celda.value not in (None, ""):
        return False
    celda.value = valor
    return True


def _buscar_etiqueta(ws, etiqueta: str, hasta_fila: int = 12) -> Optional[tuple[int, int]]:
    for fila in range(1, hasta_fila + 1):
        for col in range(1, 70):
            if _sin_tildes(ws.cell(fila, col).value).startswith(etiqueta):
                return fila, col
    return None


def _fila_encabezado_tabla(ws) -> tuple[int, dict[str, int]]:
    """Dónde empieza la tabla y qué columna es cada campo."""
    for fila in range(1, 30):
        etiquetas = {}
        for col in range(1, 70):
            texto = _sin_tildes(ws.cell(fila, col).value)
            if not texto:
                continue
            for prefijo, campo in _COLUMNAS_ACTA:
                if texto.startswith(prefijo) and campo not in etiquetas:
                    etiquetas[campo] = col
        if "factura" in etiquetas and "glosa_inicial" in etiquetas:
            return fila, etiquetas
    return 0, {}


def escribir_en_modelo(
    resultado: Resultado,
    modelo: bytes,
    encabezado: Encabezado,
    marcar_pendientes: bool = True,
) -> bytes:
    """Vuelca el acta sobre el .xlsm modelo y devuelve el archivo.

    Se conserva el libro tal cual —macros incluidas— porque el acta que se
    lleva a la mesa es la del formato oficial, con sus botones. Generar un
    .xlsx limpio sería más fácil y le serviría a nadie.

    Las casillas que tiene que decidir una persona salen marcadas con
    «◄ DEFINIR» en vez de vacías: una celda en blanco en un acta de cien
    renglones se pasa por alto; un texto raro, no.
    """
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(modelo), keep_vba=True)
    ws = wb["ACTA"] if "ACTA" in wb.sheetnames else wb.worksheets[0]

    acta = resultado.acta
    valores = {
        "nit": encabezado.nit,
        "razon_social": encabezado.razon_social,
        "fecha_conciliacion": encabezado.fecha_conciliacion,
        "numero_acta": encabezado.numero_acta,
        "periodo": encabezado.periodo,
        "cantidad_facturas": acta.cantidad_facturas_declarada,
        "valor_a_conciliar": acta.valor_a_conciliar_declarado,
    }
    for etiqueta, campo in _CASILLAS_ENCABEZADO:
        valor = valores.get(campo)
        if valor in (None, ""):
            continue
        sitio = _buscar_etiqueta(ws, etiqueta)
        if sitio is None:
            continue
        fila, col = sitio
        # A la derecha de la etiqueta, en la primera celda libre: el formato
        # deja una o dos columnas de separación según la casilla.
        for salto in range(1, 6):
            if _escribir(ws, fila, col + salto, valor):
                break

    fila_enc, columnas = _fila_encabezado_tabla(ws)
    if not columnas:
        raise ValueError(
            "El modelo no tiene la tabla del acta (no se encontró la fila con "
            "«NUMERO FACTURA» y «VALOR GLOSA INICIAL»)."
        )

    faltantes = {a.factura for a in resultado.avisos}
    for n, linea in enumerate(acta.lineas):
        fila = fila_enc + 1 + n
        for campo, col in columnas.items():
            valor = getattr(linea, campo, "")
            if campo == "tipo_glosa" and not valor and marcar_pendientes:
                valor = _MARCA_FALTA_HUMANO if linea.factura in faltantes else ""
            if campo == "tipificacion" and not valor and marcar_pendientes:
                valor = _MARCA_FALTA_HUMANO
            destino = ws.cell(fila, col)
            from openpyxl.cell.cell import MergedCell

            if isinstance(destino, MergedCell):
                for rango in ws.merged_cells.ranges:
                    if (rango.min_row <= fila <= rango.max_row) and (
                        rango.min_col <= col <= rango.max_col
                    ):
                        destino = ws.cell(rango.min_row, rango.min_col)
                        break
                else:
                    continue
            destino.value = valor if valor != "" else None

    salida = BytesIO()
    wb.save(salida)
    wb.close()
    return salida.getvalue()


# ═══════════════════════════════════════════════════════════════════════
#  La memoria: lo que ya se decidió una vez no se vuelve a preguntar
# ═══════════════════════════════════════════════════════════════════════


def memoria_de(db: Any, facturas: list[str]) -> dict[tuple[str, str], str]:
    """Lo aprendido en mesas anteriores para estas facturas.

    Una sola consulta con todas las facturas, no una por factura: un acta de
    cien cuentas con doscientos renglones haría doscientas consultas.
    """
    from app.models.db import ConciliacionTipificacionRecord

    claves = [clave_factura(f) for f in facturas]
    claves = [c for c in claves if c]
    if not claves:
        return {}

    recordado: dict[tuple[str, str], str] = {}
    # Se pregunta de a mil: SQLite no acepta un IN ilimitado.
    for i in range(0, len(claves), 1000):
        filas = (
            db.query(
                ConciliacionTipificacionRecord.factura_clave,
                ConciliacionTipificacionRecord.cod_glosa,
                ConciliacionTipificacionRecord.tipo_glosa,
            )
            .filter(ConciliacionTipificacionRecord.factura_clave.in_(claves[i : i + 1000]))
            .filter(ConciliacionTipificacionRecord.tipo_glosa.isnot(None))
            .all()
        )
        for factura, cod, tipo in filas:
            if tipo:
                recordado[(factura, cod)] = tipo
    return recordado


def aprender(
    db: Any,
    lineas: list[LineaActa],
    numero_acta: str = "",
    usuario: str = "",
) -> dict[str, int]:
    """Guarda lo que una persona decidió, para no volver a preguntárselo.

    Se llama con el acta YA trabajada. Solo se aprende de las líneas que
    traen tipo escrito y que no son la marca de pendiente: si el auditor dejó
    la casilla sin resolver, no hay nada que aprender.
    """
    from app.models.db import ConciliacionTipificacionRecord

    parte = {"nuevas": 0, "actualizadas": 0, "sin_dato": 0}
    for linea in lineas:
        clave = clave_factura(linea.factura)
        cod = (linea.cod_glosa or "").strip().upper()
        tipo = (linea.tipo_glosa or "").strip().upper()
        if not clave or not cod or not tipo or _MARCA_FALTA_HUMANO in tipo:
            parte["sin_dato"] += 1
            continue

        fila = (
            db.query(ConciliacionTipificacionRecord)
            .filter(ConciliacionTipificacionRecord.factura_clave == clave)
            .filter(ConciliacionTipificacionRecord.cod_glosa == cod)
            .first()
        )
        if fila is None:
            db.add(
                ConciliacionTipificacionRecord(
                    factura_clave=clave,
                    cod_glosa=cod,
                    tipificacion=(linea.tipificacion or "").strip().upper() or None,
                    tipo_glosa=tipo,
                    tipo_deducido=TIPO_POR_TIPIFICACION.get(
                        TIPIFICACION_POR_FAMILIA.get(familia_de(cod), ""), ""
                    )
                    or None,
                    definido_por=(usuario or "")[:200] or None,
                    numero_acta=(numero_acta or "")[:60] or None,
                )
            )
            parte["nuevas"] += 1
        elif fila.tipo_glosa != tipo:
            fila.tipo_glosa = tipo
            fila.definido_por = (usuario or "")[:200] or fila.definido_por
            fila.numero_acta = (numero_acta or "")[:60] or fila.numero_acta
            parte["actualizadas"] += 1
    db.commit()
    return parte
