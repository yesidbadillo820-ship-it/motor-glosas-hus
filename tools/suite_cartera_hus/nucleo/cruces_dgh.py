"""
nucleo.cruces_dgh — Motor central de cruces masivos (reemplaza Power Query + BUSCARV).

Un solo módulo, en Pandas, para procesar cualquier masivo del portal de una EPS
y dejarlo listo para el cargue de OBJECIONES en DGH (Dinámica Gerencial):

    1. organizar_cargue()    ZIP del portal (con ZIPs adentro) → clasifica en
                             DETALLE / GLOSAS / FACTURA y arma lotes de máx. 300
                             facturas alineadas.
    2. consolidar()          Miles de Excel → un solo DataFrame de glosas con la
                             OBSERVACION_FINAL agrupada por factura + servicio.
    3. cruzar_con_base()     Cruza el consolidado contra la base de DGH
                             ('Servicios Facturados') sin abrir Excel.
    4. generar_objeciones()  Produce los OBJECIONES_LOTE_XX.xlsx con las 16
                             columnas del mapeo, aplicando las mismas reglas
                             que valida DGH ANTES de subir:
                               · guardián de valores (nunca supera servicio/saldo)
                               · exclusión de facturas ya objetadas
                               · depuración de duplicados
                               · aviso de facturas con copago
                             Todo lo excluido queda en REVISAR con su motivo.

Las columnas se detectan por sinónimos definidos en config/mapeo_dgh.json,
para que el mismo motor sirva a distintas EPS sin tocar el código.
"""

import json
import os
import re
import shutil
import unicodedata
from datetime import date

from . import archivos

try:
    import pandas as pd
except ImportError:  # el launcher avisa; aquí solo evitamos romper el import
    pd = None

RUTA_MAPEO_DEFECTO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "mapeo_dgh.json",
)


def _exigir_pandas():
    if pd is None:
        raise RuntimeError(
            "Falta pandas/openpyxl. Ejecute INICIAR_SUITE.bat con internet una vez, "
            "o instale manualmente:  pip install pandas openpyxl"
        )


def cargar_mapeo(ruta=None):
    with open(ruta or RUTA_MAPEO_DEFECTO, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ helpers


def _normalizar(texto):
    """MAYÚSCULAS, sin tildes, espacios colapsados — para comparar encabezados."""
    s = str(texto).strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def encontrar_columna(df, candidatos):
    """Devuelve el nombre real de la columna del df que corresponde a alguno
    de los sinónimos, o None. Prefiere coincidencia exacta; luego 'contiene'."""
    normales = {_normalizar(c): c for c in df.columns}
    cand_norm = [_normalizar(c) for c in candidatos]
    for cn in cand_norm:
        if cn in normales:
            return normales[cn]
    for cn in cand_norm:
        for col_norm, original in normales.items():
            if cn and cn in col_norm:
                return original
    return None


def a_numero(v):
    """Convierte importes en formato colombiano/UE a float.

    Reglas (coma = decimal, punto = miles, como en los portales de EPS):
      · '1.234.567,89' -> 1234567.89      · '1234,56' -> 1234.56
      · '1.234.567'    -> 1234567         · '50.000'  -> 50000   · '2.500' -> 2500
      · '1.5' / '12.34' / '100.5'         -> se respetan como decimal real
      · '1,234,567.89' (formato US)       -> 1234567.89
    El caso ambiguo de un solo punto se resuelve por el nº de dígitos a la
    derecha: exactamente 3 => separador de miles (así viene el peso colombiano).
    """
    if v is None or (isinstance(v, float) and pd is not None and pd.isna(v)):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    # deja solo dígitos, signo y separadores (quita '$', 'COP', espacios, NBSP…)
    s = re.sub(r"[^0-9,.\-]", "", str(v).strip())
    if not s or s in ("-", ".", ","):
        return 0.0
    if "," in s and "." in s:
        # el separador que aparece de último es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # 1.234.567,89 (CO/UE)
        else:
            s = s.replace(",", "")  # 1,234,567.89 (US)
    elif "," in s:
        s = s.replace(",", ".")  # 1234,56
    elif "." in s:
        decimales = s.rpartition(".")[2]
        if s.count(".") > 1 or len(decimales) == 3:
            s = s.replace(".", "")  # 1.234.567 / 50.000 / 2.500 -> miles
        # 1, 2 o >3 dígitos a la derecha -> es decimal real: se deja igual
    try:
        return float(s)
    except ValueError:
        return 0.0


def leer_tabla(ruta, log=print):
    """Lee un xlsx/xls/csv de forma tolerante y ubica sola la fila de encabezados."""
    _exigir_pandas()
    tipo = archivos.tipo_real(ruta)
    if tipo == "csv" or ruta.lower().endswith((".csv", ".txt")):
        # Prueba varias codificaciones (los CSV de Windows suelen venir en
        # latin-1) y separadores. Si ninguno da >1 columna, devuelve la mejor
        # lectura de una sola columna — así funciona la lista de facturas "ya
        # objetadas" (una por fila), que antes reventaba con ValueError.
        una_columna = None
        for enc in ("utf-8-sig", "latin-1"):
            for sep in (";", ",", "\t"):
                try:
                    df = pd.read_csv(ruta, sep=sep, dtype=str, encoding=enc, engine="python")
                except Exception:
                    continue
                if df.shape[1] > 1:
                    return df
                if una_columna is None and df.shape[1] == 1:
                    una_columna = df
        if una_columna is not None:
            return una_columna
        raise ValueError("No se pudo leer como CSV/TXT: %s" % ruta)

    df = pd.read_excel(ruta, dtype=str)
    # Si vino con encabezados 'Unnamed', buscar la fila real de títulos
    sin_nombre = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
    if sin_nombre > len(df.columns) / 2:
        crudo = pd.read_excel(ruta, header=None, dtype=str, nrows=12)
        mejor_fila, mejor_puntaje = 0, -1
        for i in range(min(10, len(crudo))):
            fila = crudo.iloc[i]
            puntaje = sum(1 for v in fila if isinstance(v, str) and v.strip())
            if puntaje > mejor_puntaje:
                mejor_fila, mejor_puntaje = i, puntaje
        df = pd.read_excel(ruta, header=mejor_fila, dtype=str)
    return df


# ------------------------------------------------------- 1. organizar cargue


def organizar_cargue(entrada, carpeta_salida, mapeo=None, max_por_lote=None, log=print):
    """ZIP del portal (o carpeta suelta) → LOTE_01, LOTE_02… de máx. N facturas.

    Cada lote queda con subcarpetas DETALLE / GLOSAS / FACTURA alineadas por
    número de factura. Lo que no se pudo clasificar o no tiene factura
    reconocible queda en SIN_CLASIFICAR (nada se pierde).
    Devuelve un dict con las cifras del proceso.
    """
    mapeo = mapeo or cargar_mapeo()
    max_por_lote = max_por_lote or mapeo.get("max_facturas_por_lote", 300)
    os.makedirs(carpeta_salida, exist_ok=True)

    # 1) obtener la lista de archivos (extrayendo ZIP anidados si aplica)
    carpeta_ext = None
    if os.path.isdir(entrada):
        lista = [r for r, _ in archivos.inventariar(entrada)]
        log("Carpeta de entrada: %d archivos." % len(lista))
    else:
        log("Extrayendo ZIP (incluye ZIPs internos)…")
        carpeta_ext = os.path.join(carpeta_salida, "_EXTRACCION")
        lista = archivos.extraer_zip_recursivo(entrada, carpeta_ext, log=log)

    # 2) clasificar por tipo y por factura
    por_factura = {}
    sin_clasificar = []
    for ruta in lista:
        nombre = os.path.basename(ruta)
        tipo = archivos.clasificar_archivo(nombre)
        factura = archivos.extraer_factura(nombre)
        if tipo and factura:
            por_factura.setdefault(factura, {}).setdefault(tipo, []).append(ruta)
        else:
            sin_clasificar.append(ruta)

    facturas = sorted(por_factura)
    log(
        "Clasificadas %d facturas · %d archivos sin clasificar."
        % (len(facturas), len(sin_clasificar))
    )

    # 3) armar lotes alineados
    resumen = {
        "facturas": len(facturas),
        "lotes": 0,
        "sin_clasificar": len(sin_clasificar),
        "incompletas": 0,
    }
    incompletas = []
    for i in range(0, len(facturas), max_por_lote):
        n_lote = resumen["lotes"] + 1
        grupo = facturas[i : i + max_por_lote]
        base_lote = os.path.join(carpeta_salida, "LOTE_%02d" % n_lote)
        for tipo in ("DETALLE", "GLOSAS", "FACTURA"):
            os.makedirs(os.path.join(base_lote, tipo), exist_ok=True)
        for fac in grupo:
            tipos = por_factura[fac]
            if len(tipos) < 3:
                faltan = {"DETALLE", "GLOSAS", "FACTURA"} - set(tipos)
                incompletas.append((fac, ", ".join(sorted(faltan))))
                resumen["incompletas"] += 1
            for tipo, rutas in tipos.items():
                for r in rutas:
                    shutil.copy2(r, os.path.join(base_lote, tipo, os.path.basename(r)))
        resumen["lotes"] = n_lote
        log("  LOTE_%02d listo: %d facturas." % (n_lote, len(grupo)))

    # 4) lo no clasificado, aparte y visible
    if sin_clasificar:
        aparte = os.path.join(carpeta_salida, "SIN_CLASIFICAR")
        os.makedirs(aparte, exist_ok=True)
        for r in sin_clasificar:
            shutil.copy2(r, os.path.join(aparte, os.path.basename(r)))

    if incompletas:
        ruta_inc = os.path.join(carpeta_salida, "FACTURAS_INCOMPLETAS.csv")
        with open(ruta_inc, "w", encoding="utf-8-sig") as f:
            f.write("factura;archivos_faltantes\n")
            for fac, faltan in incompletas:
                f.write("%s;%s\n" % (fac, faltan))
        log(
            "  [!] %d facturas con archivos faltantes → FACTURAS_INCOMPLETAS.csv" % len(incompletas)
        )

    # 5) limpiar la extracción intermedia: todo ya quedó copiado en los
    #    lotes o en SIN_CLASIFICAR (evita lecturas dobles al consolidar)
    if carpeta_ext and os.path.isdir(carpeta_ext):
        shutil.rmtree(carpeta_ext, ignore_errors=True)

    return resumen


# --------------------------------------------------------- 2. consolidación


def consolidar(carpeta, mapeo=None, log=print):
    """Lee TODOS los Excel de GLOSAS y DETALLE bajo `carpeta` y devuelve
    (df_consolidado, avisos). Una fila por servicio glosado, con:
        factura, codigo_servicio, nombre_servicio, codigo_glosa, tipo_glosa,
        valor_glosado, valor_servicio, saldo, copago, observacion_final,
        tipo_objecion
    """
    _exigir_pandas()
    mapeo = mapeo or cargar_mapeo()
    origen = mapeo["campos_origen"]
    avisos = []

    tablas_glosas, tablas_detalle = [], []
    for ruta, tipo in archivos.inventariar(carpeta):
        if tipo not in ("xlsx", "xls", "csv"):
            continue
        clase = archivos.clasificar_archivo(os.path.basename(ruta))
        if clase not in ("GLOSAS", "DETALLE"):
            continue
        try:
            df = leer_tabla(ruta, log=log)
        except Exception as e:
            avisos.append("No se pudo leer %s: %s" % (os.path.basename(ruta), e))
            continue
        df["__archivo"] = os.path.basename(ruta)
        fac = archivos.extraer_factura(os.path.basename(ruta))
        if fac:
            df["__factura_archivo"] = fac
        (tablas_glosas if clase == "GLOSAS" else tablas_detalle).append(df)

    if not tablas_glosas:
        raise ValueError("No se hallaron archivos de GLOSAS legibles en la carpeta.")
    log(
        "Consolidando %d archivos de GLOSAS y %d de DETALLE…"
        % (len(tablas_glosas), len(tablas_detalle))
    )

    g = pd.concat(tablas_glosas, ignore_index=True, sort=False)

    def col(df, campo):
        return encontrar_columna(df, origen.get(campo, []))

    # --- campos base desde GLOSAS
    salida = pd.DataFrame()
    c_fac = col(g, "factura")
    salida["factura"] = g[c_fac] if c_fac else g.get("__factura_archivo", "")
    salida["factura"] = salida["factura"].fillna("").astype(str).str.strip()
    if "__factura_archivo" in g.columns:
        vacias = salida["factura"] == ""
        salida.loc[vacias, "factura"] = g.loc[vacias, "__factura_archivo"]
    # re-normalizar: donde __factura_archivo era NaN, factura volvió a NaN y el
    # groupby de más abajo (dropna=True) borraría esos renglones SIN dejar
    # rastro. Con "" sobreviven y quedan visibles en el consolidado.
    salida["factura"] = salida["factura"].fillna("").astype(str).str.strip()

    # códigos de servicio y de glosa: si el archivo no trae columna propia de
    # servicio, el emparejado por "contiene" podría engancharla a la de glosa
    # (ambas llevan "CODIGO"). Si resuelven a la MISMA columna, se deja el
    # servicio en blanco en vez de agrupar/sumar por la clave equivocada.
    c_serv = col(g, "codigo_servicio")
    c_glo = col(g, "codigo_glosa")
    if c_serv is not None and c_serv == c_glo:
        avisos.append(
            "No se distingue 'código de servicio' de 'código de glosa' (ambos "
            "apuntan a %r); se deja el servicio en blanco." % c_serv
        )
        c_serv = None
    salida["codigo_servicio"] = g[c_serv].fillna("").astype(str).str.strip() if c_serv else ""
    salida["codigo_glosa"] = g[c_glo].fillna("").astype(str).str.strip() if c_glo else ""

    for campo in ("prefijo", "consecutivo_item", "nombre_servicio"):
        c = col(g, campo)
        salida[campo] = g[c].fillna("").astype(str).str.strip() if c else ""

    c = col(g, "descripcion_glosa")
    salida["descripcion_glosa"] = g[c].fillna("").astype(str).str.strip() if c else ""
    c = col(g, "valor_glosado")
    salida["valor_glosado"] = g[c].map(a_numero) if c else 0.0
    salida["__archivo"] = g["__archivo"]

    # renglones byte-idénticos (mismo factura+servicio+glosa+valor+descripción):
    # son duplicados de exportación del portal. Se deja uno; evita inflar el
    # valor glosado al sumar más abajo.
    claves_dup = [
        "factura",
        "codigo_servicio",
        "codigo_glosa",
        "valor_glosado",
        "descripcion_glosa",
    ]
    n_antes = len(salida)
    salida = salida.drop_duplicates(subset=claves_dup, keep="first")
    if n_antes - len(salida):
        log(
            "  Depurados %d renglones idénticos (duplicados de exportación)."
            % (n_antes - len(salida))
        )

    # tipo de glosa (médica CL vs administrativa) y tipo de objeción por factura
    medicas = tuple(mapeo.get("tipos_glosa_medica", ["CL"]))
    salida["tipo_glosa"] = (
        salida["codigo_glosa"]
        .str.upper()
        .map(lambda cg: "MEDICA" if cg.startswith(medicas) else "ADMINISTRATIVA")
    )

    # --- OBSERVACION_FINAL: unir descripciones por factura + servicio + glosa
    def observacion(grupo):
        textos = [t for t in grupo if t]
        vista = []
        for t in textos:
            if t not in vista:
                vista.append(t)
        return " | ".join(vista)

    claves = ["factura", "codigo_servicio", "codigo_glosa"]
    obs = salida.groupby(claves)["descripcion_glosa"].apply(observacion).rename("observacion_final")
    agreg = {
        "prefijo": "first",
        "consecutivo_item": "first",
        "nombre_servicio": "first",
        "tipo_glosa": "first",
        "valor_glosado": "sum",
        "__archivo": "first",
    }
    consolidado = salida.groupby(claves, as_index=False).agg(agreg)
    consolidado = consolidado.merge(obs.reset_index(), on=claves, how="left")

    # respuesta estándar donde el portal no trae texto
    respuesta = mapeo.get("respuesta_estandar", "")
    consolidado["observacion_final"] = consolidado["observacion_final"].where(
        consolidado["observacion_final"].astype(str).str.strip() != "", respuesta
    )

    # tipo de objeción por factura: administrativa / médica / mixta
    tipos_fac = consolidado.groupby("factura")["tipo_glosa"].agg(
        lambda s: "MIXTA" if s.nunique() > 1 else s.iloc[0]
    )
    consolidado["tipo_objecion"] = consolidado["factura"].map(tipos_fac)

    # --- valores de referencia desde DETALLE (valor servicio, saldo, copago)
    for campo in ("valor_servicio", "saldo", "copago"):
        consolidado[campo] = float("nan")
    if tablas_detalle:
        d = pd.concat(tablas_detalle, ignore_index=True, sort=False)
        c_fac_d = col(d, "factura")
        c_cod_d = col(d, "codigo_servicio")
        if c_fac_d and c_cod_d:
            ref = pd.DataFrame(
                {
                    "factura": d[c_fac_d].fillna("").astype(str).str.strip(),
                    "codigo_servicio": d[c_cod_d].fillna("").astype(str).str.strip(),
                }
            )
            for campo in ("valor_servicio", "saldo", "copago"):
                c = col(d, campo)
                ref[campo] = d[c].map(a_numero) if c else float("nan")
            ref = ref.groupby(["factura", "codigo_servicio"], as_index=False).max()
            consolidado = consolidado.drop(columns=["valor_servicio", "saldo", "copago"]).merge(
                ref, on=["factura", "codigo_servicio"], how="left"
            )
        else:
            avisos.append(
                "El DETALLE no trae columnas reconocibles de factura/"
                "código: no se cruzaron valores de referencia."
            )

    log(
        "Consolidado: %d servicios glosados en %d facturas · $%s glosados."
        % (
            len(consolidado),
            consolidado["factura"].nunique(),
            "{:,.0f}".format(consolidado["valor_glosado"].sum()).replace(",", "."),
        )
    )
    for a in avisos:
        log("  [!] " + a)
    return consolidado, avisos


# ------------------------------------------------- 3. cruce con la base DGH


def cruzar_con_base(consolidado, ruta_base, mapeo=None, log=print):
    """Cruza el consolidado contra la base de DGH ('Servicios Facturados').

    Marca cada fila con 'cruza_dgh' (True/False) y completa valor_servicio /
    saldo / copago cuando la base los trae mejores. Soporta bases grandes en
    CSV o Excel.
    """
    _exigir_pandas()
    mapeo = mapeo or cargar_mapeo()
    origen = mapeo["campos_origen"]
    log("Leyendo base DGH: %s …" % os.path.basename(ruta_base))
    base = leer_tabla(ruta_base, log=log)

    c_fac = encontrar_columna(base, origen["factura"])
    c_cod = encontrar_columna(base, origen["codigo_servicio"])
    if not c_fac or not c_cod:
        raise ValueError(
            "La base DGH no trae columnas reconocibles de "
            "factura y código de servicio. Revise campos_origen "
            "en config/mapeo_dgh.json."
        )

    ref = pd.DataFrame(
        {
            "factura": base[c_fac].fillna("").astype(str).str.strip(),
            "codigo_servicio": base[c_cod].fillna("").astype(str).str.strip(),
        }
    )
    for campo in ("valor_servicio", "saldo", "copago"):
        c = encontrar_columna(base, origen.get(campo, []))
        ref["dgh_" + campo] = base[c].map(a_numero) if c else float("nan")
    ref = ref.groupby(["factura", "codigo_servicio"], as_index=False).max()

    antes = len(consolidado)
    cruz = consolidado.merge(ref, on=["factura", "codigo_servicio"], how="left")
    cruz["cruza_dgh"] = (
        cruz["dgh_valor_servicio"].notna() | cruz["dgh_saldo"].notna() | cruz["dgh_copago"].notna()
    )
    for campo in ("valor_servicio", "saldo", "copago"):
        cruz[campo] = cruz[campo].fillna(cruz["dgh_" + campo])
        cruz.drop(columns=["dgh_" + campo], inplace=True)

    n_ok = int(cruz["cruza_dgh"].sum())
    log(
        "Cruce DGH: %d de %d servicios cruzan (%.1f%%)."
        % (n_ok, antes, 100.0 * n_ok / max(antes, 1))
    )
    return cruz


# ---------------------------------------------- 4. generación de OBJECIONES


def generar_objeciones(
    consolidado,
    carpeta_salida,
    entidad=None,
    mapeo=None,
    facturas_ya_objetadas=None,
    reporte=None,
    log=print,
):
    """Aplica las reglas de DGH y escribe OBJECIONES_LOTE_XX.xlsx + REVISAR.

    Reglas (las mismas que valida DGH, aplicadas ANTES de subir):
      · Guardián de valores: la objeción nunca supera el valor del servicio ni
        el saldo (descontando copago cuando existe); si se pasa, se AJUSTA al
        tope en vez de perderse.
      · Facturas ya objetadas: se excluyen completas (un repetido tumba el
        cargue en DGH) y quedan en REVISAR.
      · Duplicados exactos (factura+código+glosa): queda uno, el resto a REVISAR.
      · Facturas con copago: se marcan con aviso (pueden requerir registro
        manual dirigido, según el hallazgo documentado del área).
    """
    _exigir_pandas()
    mapeo = mapeo or cargar_mapeo()
    os.makedirs(carpeta_salida, exist_ok=True)
    facturas_ya_objetadas = {str(f).strip() for f in (facturas_ya_objetadas or [])}
    entidad = entidad or {}
    df = consolidado.copy()

    # --- guardas defensivas: el usuario puede elegir un Excel que no salió de
    #     'Consolidar + cruzar'. Sin esto, faltar una columna tumbaba el proceso.
    faltan_clave = [c for c in ("factura", "valor_glosado") if c not in df.columns]
    if faltan_clave:
        raise ValueError(
            "El archivo elegido no tiene las columnas internas %s. Genere primero "
            "el CONSOLIDADO_GLOSAS.xlsx con 'Consolidar + cruzar', o verifique que "
            "eligió el archivo correcto." % ", ".join(faltan_clave)
        )
    for c in (
        "codigo_servicio",
        "codigo_glosa",
        "nombre_servicio",
        "prefijo",
        "consecutivo_item",
        "observacion_final",
        "tipo_objecion",
    ):
        if c not in df.columns:
            df[c] = ""
    for c in ("valor_servicio", "saldo", "copago"):
        if c not in df.columns:
            df[c] = float("nan")

    def registrar_exclusion(filas, motivo):
        if reporte is not None:
            for _, fila in filas.iterrows():
                reporte.excluir(
                    fila.get("factura", ""),
                    motivo,
                    "%s / glosa %s / $%s"
                    % (
                        fila.get("codigo_servicio", ""),
                        fila.get("codigo_glosa", ""),
                        "{:,.0f}".format(a_numero(fila.get("valor_glosado", 0))),
                    ),
                )

    # 1) excluir facturas ya objetadas
    ya = df["factura"].isin(facturas_ya_objetadas)
    if ya.any():
        registrar_exclusion(df[ya], "FACTURA_YA_OBJETADA")
        log(
            "  Excluidas %d filas de %d facturas ya objetadas."
            % (int(ya.sum()), df.loc[ya, "factura"].nunique())
        )
        df = df[~ya]

    # 2) duplicados exactos
    claves = ["factura", "codigo_servicio", "codigo_glosa"]
    dup = df.duplicated(subset=claves, keep="first")
    if dup.any():
        registrar_exclusion(df[dup], "DUPLICADO")
        log("  Depurados %d duplicados." % int(dup.sum()))
        df = df[~dup]

    # 3) guardián de valores
    df["valor_objetado"] = df["valor_glosado"].map(a_numero)
    tope_servicio = df["valor_servicio"].map(a_numero)
    copago = df["copago"].map(a_numero).fillna(0)
    tope_efectivo = tope_servicio - copago  # hallazgo DGH: descuenta copago
    tope_saldo = df["saldo"].map(a_numero)

    ajustadas = 0
    for tope in (tope_efectivo, tope_saldo):
        valido = tope.notna() & (tope > 0)
        exceso = valido & (df["valor_objetado"] > tope)
        ajustadas += int(exceso.sum())
        df.loc[exceso, "valor_objetado"] = tope[exceso]
    if ajustadas:
        log("  Guardián de valores: %d objeciones ajustadas al tope de DGH." % ajustadas)
    df["valor_aceptado"] = 0

    # 4) aviso de copago
    con_copago = sorted(df.loc[copago > 0, "factura"].unique())
    if con_copago:
        log(
            "  [!] %d facturas con copago (pueden requerir registro manual): %s%s"
            % (len(con_copago), ", ".join(con_copago[:8]), "…" if len(con_copago) > 8 else "")
        )
        with open(
            os.path.join(carpeta_salida, "FACTURAS_CON_COPAGO.csv"), "w", encoding="utf-8-sig"
        ) as f:
            f.write("factura\n" + "\n".join(con_copago) + "\n")

    # 5) construir columnas de salida según el mapeo
    hoy = date.today().strftime("%d/%m/%Y")
    tokens = {
        "{FECHA_HOY}": hoy,
        "{NIT_ENTIDAD}": str(entidad.get("nit", "")),
        "{NOMBRE_ENTIDAD}": entidad.get("nombre", ""),
        "{USUARIO}": mapeo.get("usuario_defecto", ""),
    }
    columnas = mapeo["columnas_salida"]
    mapa = mapeo["mapa"]
    salida = pd.DataFrame(index=df.index)
    for col_salida in columnas:
        fuente = mapa.get(col_salida, "")
        if fuente in tokens:
            salida[col_salida] = tokens[fuente]
        elif isinstance(fuente, str) and fuente.startswith("="):
            salida[col_salida] = fuente[1:]
        elif fuente in df.columns:
            salida[col_salida] = df[fuente]
        else:
            salida[col_salida] = ""

    # 6) partir en lotes de N facturas y escribir
    max_fac = mapeo.get("max_facturas_por_lote", 300)
    salida["__factura"] = df["factura"].values
    facturas = sorted(salida["__factura"].unique())
    rutas = []
    for i in range(0, len(facturas), max_fac):
        grupo = set(facturas[i : i + max_fac])
        lote = salida[salida["__factura"].isin(grupo)].drop(columns="__factura")
        n = len(rutas) + 1
        ruta = os.path.join(carpeta_salida, "OBJECIONES_LOTE_%02d.xlsx" % n)
        lote.to_excel(ruta, index=False)
        rutas.append(ruta)
        valor = df[df["factura"].isin(grupo)]["valor_objetado"].sum()
        log(
            "  OBJECIONES_LOTE_%02d.xlsx → %d filas · %d facturas · $%s"
            % (n, len(lote), len(grupo), "{:,.0f}".format(valor).replace(",", "."))
        )
        if reporte is not None:
            for fac in sorted(grupo):
                filas_fac = df[df["factura"] == fac]
                reporte.registrar(
                    fac,
                    "EN_LOTE_%02d" % n,
                    "%d objeciones" % len(filas_fac),
                    round(float(filas_fac["valor_objetado"].sum()), 2),
                    os.path.basename(ruta),
                )

    total = df["valor_objetado"].sum()
    log(
        "TOTAL: %d filas de objeción · %d facturas · $%s en %d lote(s)."
        % (len(df), len(facturas), "{:,.0f}".format(total).replace(",", "."), len(rutas))
    )
    return rutas
