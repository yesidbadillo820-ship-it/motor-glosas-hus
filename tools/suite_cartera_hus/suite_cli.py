"""
suite_cli — La misma Suite Cartera HUS, pero por línea de comandos (sin ventana).

Sirve para automatizar (tareas programadas, servidores sin pantalla, pruebas)
lo que en la ventana se hace con botones. Todo cae en el mismo estándar de
salida: SALIDAS/<ENTIDAD>/<fecha>_<proceso>/ con CONTROL.csv + REVISAR.csv +
RESUMEN.txt (+ EVIDENCIAS.docx / OBJECIONES_LOTE_XX.xlsx según la acción).

Ejemplos:
    python suite_cli.py entidades --buscar coosalud
    python suite_cli.py organizar PORTAL.zip --entidad "COOSALUD"
    python suite_cli.py consolidar SALIDAS/COOSALUD/2026.../ --base-dgh BASE.xlsx --entidad COOSALUD
    python suite_cli.py objeciones CONSOLIDADO_GLOSAS.xlsx --entidad COOSALUD --ya-objetadas ya.csv
    python suite_cli.py evidencias carpeta_pantallazos/ --entidad COOSALUD
    python suite_cli.py todo PORTAL.zip --entidad COOSALUD --base-dgh BASE.xlsx
"""

import argparse
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from nucleo import (  # noqa: E402
    ai_tools,
    archivos,
    cruces_dgh,
    msg_tools,
    office_tools,
    pdf_tools,
    registro,
    reportes,
)

CARPETA_SALIDAS = os.path.join(BASE, "SALIDAS")


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------- resolver entidad


def resolver_entidad(texto):
    """Encuentra la entidad por NIT o por nombre (coincidencia flexible).

    Devuelve el dict de la entidad. Si hay varias coincidencias, elige la
    exacta o, si no, avisa y toma la primera.
    """
    ents = registro.cargar_entidades()
    if not texto:
        raise SystemExit("[X] Falta --entidad (NIT o nombre de la EPS).")
    t = texto.strip().upper()
    # 1) NIT exacto
    for e in ents:
        if str(e.get("nit", "")).strip() == texto.strip():
            return e
    # 2) nombre exacto
    for e in ents:
        if e.get("nombre", "").strip().upper() == t:
            return e
    # 3) contiene
    coincidencias = [
        e for e in ents if t in e.get("nombre", "").upper() or t in str(e.get("nit", ""))
    ]
    if not coincidencias:
        raise SystemExit(
            "[X] No hay ninguna entidad que coincida con %r. "
            "Pruebe: python suite_cli.py entidades --buscar %s" % (texto, texto)
        )
    if len(coincidencias) > 1:
        log(
            "[i] %d entidades coinciden con %r; se usa la primera: %s"
            % (len(coincidencias), texto, coincidencias[0]["nombre"])
        )
        for e in coincidencias[:6]:
            log("      · %s (NIT %s)" % (e["nombre"], e.get("nit", "s/d")))
    return coincidencias[0]


# ----------------------------------------------------------------- subcomandos


def cmd_entidades(args):
    ents = registro.buscar(registro.cargar_entidades(), args.buscar or "")
    icono = {"OPERATIVA": "🟢", "POR_ARMAR": "🟡", "SIN_DATOS": "🔴"}
    for e in ents:
        rad = e.get("radicacion", {})
        log(
            "%s  %-55s NIT %-12s %s"
            % (
                icono.get(e.get("estado_radicacion"), "⚪"),
                e["nombre"][:55],
                e.get("nit", "s/d") or "s/d",
                rad.get("link") or rad.get("correo") or "",
            )
        )
    conteo = registro.resumen_estados(ents)
    log(
        "\nTotal: %d  ·  🟢 %d  🟡 %d  🔴 %d"
        % (
            len(ents),
            conteo.get("OPERATIVA", 0),
            conteo.get("POR_ARMAR", 0),
            conteo.get("SIN_DATOS", 0),
        )
    )
    return 0


def cmd_organizar(args):
    entidad = resolver_entidad(args.entidad)
    rep = reportes.ReporteEstandar(
        entidad["nombre"], "organizar_masivo", base=CARPETA_SALIDAS, log=log
    )
    resumen = cruces_dgh.organizar_cargue(args.entrada, rep.carpeta, log=log)
    rep.registrar(
        "(masivo)",
        "ORGANIZADO",
        "%(facturas)d facturas en %(lotes)d lotes · "
        "%(sin_clasificar)d sin clasificar · "
        "%(incompletas)d incompletas" % resumen,
    )
    rep.cerrar()
    return 0


def cmd_consolidar(args):
    entidad = resolver_entidad(args.entidad)
    rep = reportes.ReporteEstandar(
        entidad["nombre"], "consolidar_cruce", base=CARPETA_SALIDAS, log=log
    )
    origen = args.entrada
    if not os.path.isdir(origen):
        log("La entrada es un archivo: se extrae primero…")
        origen = os.path.join(rep.carpeta, "_EXTRACCION")
        archivos.extraer_zip_recursivo(args.entrada, origen, log=log)
    consolidado, _ = cruces_dgh.consolidar(origen, log=log)
    if args.base_dgh:
        consolidado = cruces_dgh.cruzar_con_base(consolidado, args.base_dgh, log=log)
    salida = os.path.join(rep.carpeta, "CONSOLIDADO_GLOSAS.xlsx")
    consolidado.to_excel(salida, index=False)
    log("Consolidado guardado: %s" % salida)
    for fac, grupo in consolidado.groupby("factura"):
        rep.registrar(
            fac,
            "CONSOLIDADA",
            "%d servicios glosados" % len(grupo),
            round(float(grupo["valor_glosado"].sum()), 2),
            "CONSOLIDADO_GLOSAS.xlsx",
        )
    rep.cerrar()
    log(
        "→ Consolidado listo para: python suite_cli.py objeciones %s --entidad %r"
        % (salida, args.entidad)
    )
    return 0


def _leer_ya_objetadas(ruta):
    if not ruta:
        return set()
    lista = cruces_dgh.leer_tabla(ruta, log=log)
    return set(lista.iloc[:, 0].dropna().astype(str).str.strip())


def cmd_objeciones(args):
    import pandas as pd

    entidad = resolver_entidad(args.entidad)
    rep = reportes.ReporteEstandar(
        entidad["nombre"], "objeciones_dgh", base=CARPETA_SALIDAS, log=log
    )
    consolidado = pd.read_excel(args.consolidado, dtype={"factura": str})
    excluir = _leer_ya_objetadas(args.ya_objetadas)
    if excluir:
        log("Facturas a excluir por ya objetadas: %d" % len(excluir))
    cruces_dgh.generar_objeciones(
        consolidado,
        rep.carpeta,
        entidad=entidad,
        facturas_ya_objetadas=excluir,
        reporte=rep,
        log=log,
    )
    rep.cerrar()
    log(
        "Recuerde validar el PRIMER cargue contra DGH y ajustar "
        "config/mapeo_dgh.json si algún encabezado difiere."
    )
    return 0


def cmd_evidencias(args):
    entidad = resolver_entidad(args.entidad)
    rep = reportes.ReporteEstandar(entidad["nombre"], "evidencias", base=CARPETA_SALIDAS, log=log)
    ruta = rep.compilar_evidencias_word(args.carpeta)
    if ruta:
        rep.registrar("(lote)", "COMPILADO", os.path.basename(ruta), "", ruta)
    rep.cerrar()
    return 0


def cmd_todo(args):
    """Cadena completa: organizar → consolidar (+cruce) → OBJECIONES, de una."""
    entidad = resolver_entidad(args.entidad)
    rep = reportes.ReporteEstandar(
        entidad["nombre"], "cargue_completo", base=CARPETA_SALIDAS, log=log
    )

    log("══════ 1/3 · ORGANIZAR ══════")
    organizado = os.path.join(rep.carpeta, "ORGANIZADO")
    cruces_dgh.organizar_cargue(args.entrada, organizado, log=log)

    log("══════ 2/3 · CONSOLIDAR + CRUZAR ══════")
    consolidado, _ = cruces_dgh.consolidar(organizado, log=log)
    if args.base_dgh:
        consolidado = cruces_dgh.cruzar_con_base(consolidado, args.base_dgh, log=log)
    ruta_cons = os.path.join(rep.carpeta, "CONSOLIDADO_GLOSAS.xlsx")
    consolidado.to_excel(ruta_cons, index=False)
    log("Consolidado guardado: %s" % ruta_cons)

    log("══════ 3/3 · OBJECIONES ══════")
    excluir = _leer_ya_objetadas(args.ya_objetadas)
    if excluir:
        log("Facturas a excluir por ya objetadas: %d" % len(excluir))
    cruces_dgh.generar_objeciones(
        consolidado,
        rep.carpeta,
        entidad=entidad,
        facturas_ya_objetadas=excluir,
        reporte=rep,
        log=log,
    )
    for fac, grupo in consolidado.groupby("factura"):
        rep.registrar(
            fac,
            "PROCESADA",
            "%d servicios" % len(grupo),
            round(float(grupo["valor_glosado"].sum()), 2),
            "CONSOLIDADO_GLOSAS.xlsx",
        )
    rep.cerrar()
    log("Recuerde validar el PRIMER cargue contra DGH antes del masivo.")
    return 0


def cmd_pdf(args):
    """Caja de herramientas PDF (offline). Cada operación imprime la ruta de salida."""
    op = args.op
    ent = args.entradas
    sal = args.salida

    def uno():
        if not ent:
            raise SystemExit("Falta el PDF de entrada.")
        return ent[0]

    if op == "unir":
        print(pdf_tools.unir(ent, sal or "UNIDO.pdf", log=log))
    elif op == "dividir":
        pdf_tools.dividir(uno(), sal, cada=args.cada, log=log)
    elif op == "extraer":
        print(pdf_tools.extraer_paginas(uno(), args.paginas, sal, log=log))
    elif op == "eliminar":
        print(pdf_tools.eliminar_paginas(uno(), args.paginas, sal, log=log))
    elif op == "reordenar":
        orden = [int(x) for x in args.orden.replace(" ", "").split(",") if x]
        print(pdf_tools.reordenar(uno(), orden, sal, log=log))
    elif op == "rotar":
        print(pdf_tools.rotar(uno(), args.grados, args.paginas, sal, log=log))
    elif op == "recortar":
        print(pdf_tools.recortar(uno(), args.margen, sal, log=log))
    elif op == "numerar":
        print(pdf_tools.numerar(uno(), sal, log=log))
    elif op == "marca":
        print(pdf_tools.marca_agua(uno(), args.texto or "CARTERA HUS", sal, log=log))
    elif op == "img2pdf":
        print(pdf_tools.imagenes_a_pdf(ent, sal or "IMAGENES.pdf", log=log))
    elif op == "pdf2img":
        pdf_tools.pdf_a_imagenes(uno(), sal, dpi=args.dpi, log=log)
    elif op == "comprimir":
        print(pdf_tools.comprimir(uno(), sal, log=log))
    elif op == "reparar":
        print(pdf_tools.reparar(uno(), sal, log=log))
    elif op == "proteger":
        print(pdf_tools.proteger(uno(), args.password, sal, log=log))
    elif op == "desbloquear":
        print(pdf_tools.desbloquear(uno(), args.password or "", sal, log=log))
    elif op == "censurar":
        textos = [t.strip() for t in (args.texto or "").split(",") if t.strip()]
        print(pdf_tools.censurar(uno(), textos, sal, log=log))
    elif op == "info":
        pdf_tools.info(uno(), log=log)
    # --- conversiones Office (fase 2) ---
    elif op == "office2pdf":
        print(office_tools.a_pdf(uno(), salida=sal, log=log))
    elif op == "pdf2word":
        print(office_tools.pdf_a_word(uno(), sal, log=log))
    elif op == "pdf2excel":
        print(office_tools.pdf_a_excel(uno(), sal, log=log))
    elif op == "pdf2ppt":
        print(office_tools.pdf_a_powerpoint(uno(), sal, log=log))
    elif op == "pdfa":
        print(office_tools.pdf_a_pdfa(uno(), salida=sal, log=log))
    # --- inteligencia / IA (fase 3, requiere GEMINI_API_KEY) ---
    elif op == "resumir":
        print(ai_tools.resumir(uno(), sal, log=log))
    elif op == "traducir":
        print(ai_tools.traducir(uno(), args.idioma, sal, log=log))
    elif op == "markdown":
        print(ai_tools.a_markdown(uno(), sal, log=log))
    elif op == "ocr":
        print(ai_tools.ocr(uno(), sal, log=log))
    return 0


def cmd_correos(args):
    """Correos .msg de relación de pagos -> Excel consolidado (una sola fila por pago)."""
    print(msg_tools.consolidar(args.entradas, args.salida, log=log))
    return 0


def construir_parser():
    p = argparse.ArgumentParser(
        prog="suite_cli",
        description="Suite Cartera HUS por línea de comandos (radicación, "
        "glosas y cruces masivos, sin ventana).",
    )
    sub = p.add_subparsers(dest="accion", required=True)

    s = sub.add_parser("entidades", help="Listar entidades y su estado.")
    s.add_argument("--buscar", default="", help="Filtro por nombre o NIT.")
    s.set_defaults(func=cmd_entidades)

    s = sub.add_parser("organizar", help="ZIP/carpeta del portal → lotes de 300.")
    s.add_argument("entrada", help="ZIP del portal o carpeta con los archivos.")
    s.add_argument("--entidad", required=True, help="NIT o nombre de la EPS.")
    s.set_defaults(func=cmd_organizar)

    s = sub.add_parser("consolidar", help="Excel de glosas → CONSOLIDADO_GLOSAS.xlsx.")
    s.add_argument("entrada", help="Carpeta organizada (o ZIP del portal).")
    s.add_argument("--entidad", required=True, help="NIT o nombre de la EPS.")
    s.add_argument("--base-dgh", default="", help="(Opcional) Base DGH para cruzar.")
    s.set_defaults(func=cmd_consolidar)

    s = sub.add_parser("objeciones", help="CONSOLIDADO → OBJECIONES_LOTE_XX.xlsx.")
    s.add_argument("consolidado", help="CONSOLIDADO_GLOSAS.xlsx.")
    s.add_argument("--entidad", required=True, help="NIT o nombre de la EPS.")
    s.add_argument(
        "--ya-objetadas", default="", help="(Opcional) Listado de facturas ya objetadas a excluir."
    )
    s.set_defaults(func=cmd_objeciones)

    s = sub.add_parser("evidencias", help="Pantallazos de una carpeta → Word.")
    s.add_argument("carpeta", help="Carpeta con PNG/JPG.")
    s.add_argument("--entidad", required=True, help="NIT o nombre de la EPS.")
    s.set_defaults(func=cmd_evidencias)

    s = sub.add_parser("todo", help="organizar → consolidar → objeciones, de una.")
    s.add_argument("entrada", help="ZIP del portal o carpeta con los archivos.")
    s.add_argument("--entidad", required=True, help="NIT o nombre de la EPS.")
    s.add_argument("--base-dgh", default="", help="(Opcional) Base DGH para cruzar.")
    s.add_argument(
        "--ya-objetadas", default="", help="(Opcional) Listado de facturas ya objetadas a excluir."
    )
    s.set_defaults(func=cmd_todo)

    s = sub.add_parser("pdf", help="Caja de herramientas PDF (unir, dividir, comprimir…).")
    s.add_argument(
        "op",
        choices=[
            "unir",
            "dividir",
            "extraer",
            "eliminar",
            "reordenar",
            "rotar",
            "recortar",
            "numerar",
            "marca",
            "img2pdf",
            "pdf2img",
            "comprimir",
            "reparar",
            "proteger",
            "desbloquear",
            "censurar",
            "info",
            "office2pdf",
            "pdf2word",
            "pdf2excel",
            "pdf2ppt",
            "pdfa",
            "resumir",
            "traducir",
            "markdown",
            "ocr",
        ],
        help="Operación a realizar.",
    )
    s.add_argument("entradas", nargs="*", help="PDF(s) o imágenes de entrada.")
    s.add_argument("-o", "--salida", default=None, help="Ruta/carpeta de salida.")
    s.add_argument("--paginas", default=None, help="Rango de páginas, ej: '1-3,5'.")
    s.add_argument("--orden", default="", help="Nuevo orden para 'reordenar', ej: '3,1,2'.")
    s.add_argument("--grados", type=int, default=90, help="Grados para 'rotar' (90/180/270).")
    s.add_argument("--cada", type=int, default=1, help="Páginas por archivo en 'dividir'.")
    s.add_argument("--dpi", type=int, default=150, help="Resolución para 'pdf2img'.")
    s.add_argument("--margen", type=float, default=0.05, help="Margen (0-0.45) para 'recortar'.")
    s.add_argument("--password", default=None, help="Contraseña para proteger/desbloquear.")
    s.add_argument("--texto", default=None, help="Texto para 'marca' o términos de 'censurar'.")
    s.add_argument("--idioma", default="inglés", help="Idioma destino para 'traducir'.")
    s.set_defaults(func=cmd_pdf)

    s = sub.add_parser("correos", help="Correos .msg de relación de pagos -> Excel consolidado.")
    s.add_argument(
        "entradas", nargs="+", help="Archivo(s) .msg, carpeta con .msg, y/o .zip que los contenga."
    )
    s.add_argument("-o", "--salida", required=True, help="Ruta del Excel consolidado de salida.")
    s.set_defaults(func=cmd_correos)
    return p


def main(argv=None):
    args = construir_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        log("✖ ERROR: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
