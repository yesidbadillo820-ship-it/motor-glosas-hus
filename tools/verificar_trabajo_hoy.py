"""¿Quedó bien instalado el trabajo del 19-08-2026? — mira, no cambia nada.

Revisa en el servidor de cartera las cuatro cosas que se entregaron hoy:

  1. Glosas ADRES muestra las CANTIDADES (reclamada, aprobada, glosada).
  2. Al ADRES no se le declara dos veces la misma plata.
  3. «Aplicar sugerencias» ya no acepta glosas por $0.
  4. El Auditor Forense abre los documentos correctos y vive dentro de
     «Analizar glosa» (ya no está en HERRAMIENTAS).

Las tres primeras se comprueban corriendo la lógica de verdad. La cuarta se
comprueba contra los soportes REALES del servidor de radicación: se le pide
una factura y se muestra qué documentos abriría la IA y cuáles no.

No toca la base de datos, no llama a la IA y no cuesta un peso.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

OK = "  [OK]  "
MAL = "  [FALLA]"
fallas: list[str] = []
# Revisiones que no se pudieron hacer porque el PC no tiene el codigo nuevo.
desactualizado: list[str] = []


def titulo(texto: str) -> None:
    print()
    print("=" * 70)
    print(f"  {texto}")
    print("=" * 70)


def revisar(nombre: str, condicion: bool, detalle: str = "") -> None:
    print(f"{OK if condicion else MAL} {nombre}")
    if detalle:
        print(f"          {detalle}")
    if not condicion:
        fallas.append(nombre)


def correr_revision(funcion, *args) -> None:
    """Corre una revisión sin que nada pueda tumbar el programa.

    19-08-2026. La primera vez que Yesid corrió esto, su PC tenía el
    verificador NUEVO contra el código VIEJO —el autodeploy había bajado los
    archivos a medias— y el programa se cerró escupiendo un traceback de
    Python. Un bot de doble clic para el área de cartera nunca puede hacer
    eso: hay que decir en castellano qué pasó y qué hacer.
    """
    try:
        funcion(*args)
    except (ImportError, AttributeError) as e:
        print()
        print(f"{MAL} Esta revision no se pudo hacer: a este PC todavia no le")
        print("          ha llegado el codigo nuevo.")
        print(f"          (detalle tecnico: {e})")
        print()
        print("          QUE HACER: espere 5 minutos a que el motor se")
        print("          actualice solo, o de doble clic a:")
        print("             C:\\motor-glosas\\repo\\tools\\autodeploy_motor_local.cmd")
        print("          y vuelva a correr esta verificacion.")
        desactualizado.append(funcion.__name__)
    except Exception as e:  # noqa: BLE001 - el verificador nunca puede tumbarse
        print()
        print(f"{MAL} Esta revision fallo por algo inesperado:")
        print(f"          {type(e).__name__}: {e}")
        print("          Copie esta pantalla y mandela al chat.")
        fallas.append(funcion.__name__)


# ─── 1. Las cantidades en la pantalla de Glosas ADRES ────────────────────────


def revisar_cantidades() -> None:
    titulo("1) Glosas ADRES muestra las cantidades")
    from app.models.db import GlosaAdresRecord
    from app.services.preauditoria_adres import cantidad_glosada, glosa_dict

    # El caso real de la factura HUS353885, dispositivo 2022DM-0008875-R1.
    g = GlosaAdresRecord(
        id=1,
        factura_clave="353885",
        factura="HUS353885",
        codigo="2022DM-0008875-R1",
        descripcion="EQUIPO DE INFUSION",
        causal_codigo="3106",
        cant_reclamada=3.0,
        valor_reclamado=13800.0,
        cant_aprobada=1.0,
        valor_aprobado=4600.0,
        valor_glosado=9200.0,
        cuenta_valor=True,
    )
    d = glosa_dict(g)
    for campo in ("cant_reclamada", "valor_reclamado", "cant_aprobada", "valor_aprobado"):
        revisar(f"La pantalla recibe «{campo}»", d.get(campo) is not None)
    revisar(
        "Calcula la cantidad GLOSADA (reclamada menos aprobada)",
        d.get("cant_glosada") == 2.0,
        "Factura HUS353885: reclamo 3, le aprobaron 1, le glosaron 2 por $9.200",
    )
    revisar(
        "Una glosa de tarifa da cantidad glosada CERO (le bajaron el precio)",
        cantidad_glosada(1, 1) == 0.0,
    )
    revisar("Nunca da una cantidad glosada negativa", cantidad_glosada(1, 3) == 0.0)

    index = (RAIZ / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")
    revisar("La tabla pinta las tres cantidades", "gaCantGlosada(g)" in index)
    revisar("La casilla de aceptar dice de cuantos items", "glosado(s)" in index)


# ─── 2. Al ADRES no se le declara dos veces la misma plata ───────────────────


def revisar_aceptado_doble() -> None:
    titulo("2) Al ADRES no se le declara dos veces la misma plata")
    from glosas_adres_por_factura import aceptado_sin_duplicar

    tac = ("HUS311371", "879101", 700000.0)
    casos = [
        (
            "Acepta en las dos causales del mismo item",
            [(tac, 700000, 700000, True), (tac, 700000, 700000, False)],
            700000,
        ),
        (
            "Reparte 300.000 y 400.000 entre las causales",
            [(tac, 700000, 300000, True), (tac, 700000, 400000, False)],
            700000,
        ),
        (
            "Acepta solo en el renglon repetido",
            [(tac, 700000, 0, True), (tac, 700000, 700000, False)],
            700000,
        ),
        ("Acepta parcial 200.000", [(tac, 700000, 200000, True), (tac, 700000, 0, False)], 200000),
        (
            "Dos items iguales de verdad cuentan los dos",
            [(tac, 700000, 700000, True), (tac, 700000, 700000, True)],
            1400000,
        ),
    ]
    for nombre, renglones, esperado in casos:
        got = aceptado_sin_duplicar(renglones)
        revisar(nombre, got == esperado, f"declara ${got:,.0f}".replace(",", "."))

    from preauditar_glosas_adres import FilaMacro, armar_texto_respuesta

    def fila(causal: str, texto: str) -> FilaMacro:
        return FilaMacro(
            factura="HUS311371",
            codigo="879101",
            descripcion="TAC DE CRANEO SIMPLE",
            valor_glosado=700000.0,
            codigo_numerico=causal,
            descripcion_glosa=texto,
            observacion="SE ACEPTA",
            cantidad_aceptada="1",
            valor_aceptado=700000.0,
            observacion_tecnico="",
        )

    encabezado = armar_texto_respuesta(
        [fila("3209", "Servicio no pertinente"), fila("3106", "Falta soporte de HC")]
    ).split("\n")[0]
    revisar(
        "La carta que se radica declara el valor correcto",
        "$700.000" in encabezado and "$1.400.000" not in encabezado,
        encabezado[-52:],
    )


# ─── 3. Aplicar sugerencias ya no acepta por $0 ──────────────────────────────


def revisar_aceptado_en_cero() -> None:
    titulo("3) «Aplicar sugerencias» ya no acepta glosas por $0")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.db import GlosaAdresRecord, PaqueteAdresRecord
    from app.services.preauditoria_adres import aplicar_sugerencias

    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    paq = PaqueteAdresRecord(numero_paquete="X", archivo="r.xlsx", importado_por="p")
    db.add(paq)
    db.flush()
    db.add(
        GlosaAdresRecord(
            paquete_id=paq.id,
            factura_clave="1",
            factura="HUS1",
            codigo="C1",
            descripcion="OMEPRAZOL",
            causal_codigo="3106",
            cant_reclamada=3.0,
            cant_aprobada=1.0,
            valor_glosado=100006.0,
            cuenta_valor=True,
            sugerencia="SE ACEPTA",
            confianza="APRENDIDA",
        )
    )
    db.commit()
    aplicar_sugerencias(db, paquete_id=paq.id, usuario="verificador")
    g = db.query(GlosaAdresRecord).one()
    revisar(
        "Al aceptar en bloque queda escrito CUANTO se acepta",
        (g.valor_aceptado or 0) == 100006.0,
        f"valor aceptado: ${(g.valor_aceptado or 0):,.0f}".replace(",", "."),
    )
    revisar(
        "Y la cantidad que se declara es la GLOSADA, no la reclamada",
        g.cantidad_aceptada == "2",
        f"cantidad aceptada: {g.cantidad_aceptada}",
    )
    db.close()


# ─── 4. El Auditor Forense ───────────────────────────────────────────────────


def revisar_forense(factura: str | None) -> None:
    titulo("4) El Auditor Forense")
    index = (RAIZ / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")
    revisar(
        "Ya no esta duplicado en HERRAMIENTAS", "sidebarTab(this,'auditor-forense')" not in index
    )
    revisar(
        "Sigue dentro del dictamen de «Analizar glosa»", "renderAuditorForensePanel(d)" in index
    )
    revisar("Avisa que documentos NO alcanzo a leer", "afAvisoOmitidos(data)" in index)

    analizar = (RAIZ / "app" / "api" / "routers" / "analizar.py").read_text(encoding="utf-8")
    revisar(
        "Corre solo al responder una glosa (viene prendido)",
        'os.getenv("GLOSA_AUDITOR_FORENSE_PREPASS", "1")' in analizar,
    )
    revisar(
        "Saca los soportes del servidor de radicacion",
        "_pdfs_del_servidor_para_forense(numero_factura, req_id)" in analizar,
    )

    if not factura:
        print("\n  (Para probarlo contra una factura real, vuelva a correr esto")
        print("   escribiendo el numero cuando se lo pida.)")
        return

    from app.services.auditor_forense import escoger_soportes_para_forense

    soportes = buscar_soportes_de_una_factura(factura)
    if soportes is None:
        return
    if not soportes:
        print(f"\n  No se encontraron soportes de {factura} en el servidor.")
        print("  Revise el numero de la factura, o mirela en la pantalla «Soportes».")
        return

    elegidos, omitidos = escoger_soportes_para_forense(soportes)
    print(f"\n  {factura}: {len(soportes)} soporte(s) en el servidor")
    print(f"\n  LA IA ABRE ESTOS {len(elegidos)}:")
    for s in elegidos:
        print(f"     - {s.get('nombre_archivo')}")
    print(f"\n  Y AVISA QUE NO ABRIO ESTOS {len(omitidos)}:")
    for s in omitidos:
        print(f"     - {s.get('nombre_archivo')}  ({s.get('motivo')})")

    nombres = " ".join(s.get("nombre_archivo", "").upper() for s in elegidos)
    revisar("Abre la historia clinica", "HEV" in nombres or "HISTORIA" in nombres)
    revisar(
        "No manda archivos que no sean PDF",
        all((s.get("nombre_archivo") or "").lower().endswith(".pdf") for s in elegidos),
    )


def buscar_soportes_de_una_factura(factura: str):
    """Los soportes de UNA factura, buscados directo en el servidor.

    19-08-2026. Antes esto llamaba a `get_indexer().lookup()`, que al correr en
    un proceso aparte encuentra el indice frio y se pone a INDEXAR EL SERVIDOR
    ENTERO: 11.367 facturas y 102.729 archivos por red. Varios minutos sin
    imprimir una sola linea — parecia colgado — y todo ese trabajo se botaba al
    cerrar el programa. Ademas contradecia el «esto solo mira, no cuesta» del
    encabezado.

    Ahora se busca solo esa factura y se para apenas se encuentra su carpeta.
    Se reutiliza la clasificacion del indexador para no tener dos verdades.

    Devuelve None si el auditor corta la busqueda o si no hay servidor.
    """
    import os
    import time

    from app.services.soportes_autodiscovery_service import (
        _clasificar_archivo,
        get_indexer,
        normalizar_factura,
    )

    raiz = Path(str(getattr(get_indexer(), "raiz", "") or ""))
    if not str(raiz) or not raiz.exists():
        print(f"\n  No se llega al servidor de radicacion ({raiz or 'sin configurar'}).")
        print("  Esto se revisa desde la pantalla «Soportes» del portal.")
        return None

    objetivo = normalizar_factura(factura)
    if not objetivo:
        print(f"\n  «{factura}» no parece un numero de factura.")
        return None

    print(f"\n  Buscando los soportes de {factura} en {raiz}")
    print("  (busca SOLO esa factura, no indexa el servidor entero)")

    encontrados: list[dict] = []
    carpetas = 0
    arranque = time.time()
    LIMITE_SEG = 180

    for actual, _subcarpetas, archivos in os.walk(raiz):
        carpetas += 1
        if carpetas % 400 == 0:
            print(f"     ... {carpetas} carpetas revisadas ({int(time.time() - arranque)}s)")
        for nombre in archivos:
            if normalizar_factura(nombre) != objetivo and objetivo not in nombre:
                continue
            clase = _clasificar_archivo(nombre)
            encontrados.append(
                {
                    "nombre_archivo": nombre,
                    "tipo": clase[1] if clase else "otro",
                    "ruta": os.path.join(actual, nombre),
                }
            )
        # Su carpeta se llama como la factura: al hallarla, ya esta todo.
        if encontrados and objetivo in Path(actual).name:
            break
        if time.time() - arranque > LIMITE_SEG:
            print(f"\n  Se corto la busqueda a los {LIMITE_SEG // 60} minutos: el servidor")
            print("  esta lento o la factura no esta en las carpetas recorridas.")
            print("  Puede mirarla en la pantalla «Soportes» del portal.")
            return None

    return encontrados


def main() -> int:
    print()
    print("  MOTOR DE GLOSAS HUS - Verificacion del trabajo del 19-08-2026")
    print("  (esto SOLO MIRA: no cambia nada, no llama a la IA, no cuesta)")

    factura = ""
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            factura = input(
                "\n  Numero de una factura radicada para probar el forense\n"
                "  (ej. HUS468334, o Enter para saltarlo): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            factura = ""

    correr_revision(revisar_cantidades)
    correr_revision(revisar_aceptado_doble)
    correr_revision(revisar_aceptado_en_cero)
    correr_revision(revisar_forense, factura or None)

    titulo("RESULTADO")
    if desactualizado:
        print(f"  ESTE PC ESTA DESACTUALIZADO - {len(desactualizado)} revision(es)")
        print("  no se pudieron hacer porque falta bajar el codigo nuevo.")
        print()
        print("  QUE HACER, en orden:")
        print("    1. De doble clic a tools\\autodeploy_motor_local.cmd")
        print("    2. Espere a que termine (unos segundos)")
        print("    3. Vuelva a correr esta verificacion")
        print()
        print("  Si despues de eso sigue igual, copie esta pantalla y mandela")
        print("  al chat: quiere decir que el cambio todavia no se ha subido.")
        return 2
    if fallas:
        print(f"  FALLA - {len(fallas)} revision(es) no pasaron:")
        for f in fallas:
            print(f"     - {f}")
        print("\n  Copie esta pantalla y mandela al chat.")
        return 1
    print("  VERIFICADO - todo el trabajo del 19-08 quedo bien instalado.")
    print("\n  Copie esta pantalla y mandela al chat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
