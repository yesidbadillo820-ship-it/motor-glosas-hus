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
    from app.services.soportes_autodiscovery_service import get_indexer

    print(f"\n  Buscando los soportes de {factura} en el servidor...")
    soportes = get_indexer().lookup(factura) or []
    if not soportes:
        print(f"  No hay soportes indexados para {factura}.")
        print("  Revise en la pantalla «Soportes» que el indexado haya terminado.")
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

    revisar_cantidades()
    revisar_aceptado_doble()
    revisar_aceptado_en_cero()
    revisar_forense(factura or None)

    titulo("RESULTADO")
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
