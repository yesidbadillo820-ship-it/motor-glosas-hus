#!/usr/bin/env python3
"""HOSPIAI — Architecture Governance (Fase 1.7).

El sistema que gobierna la propia arquitectura, para que la plataforma pueda
evolucionar durante años sin perder trazabilidad, compatibilidad ni calidad:

1. **Registro único de artefactos**: TODO es un artefacto versionado — agentes,
   reglas, ontologías, catálogos, SDK, motor. `artefactos` los lista con su
   versión, dependencia y huella (hash); la huella detecta cuando un artefacto
   CAMBIÓ sin subir de versión (deriva silenciosa).
2. **Contratos de compatibilidad**: `compatibilidad` verifica (a) que cada
   agente declare con qué versión MAYOR del SDK fue construido y que coincida
   con la vigente, y (b) que cada implementación CUMPLA el contrato en vivo
   (formato estándar de resultado, validación, explicar). Ningún cambio del
   Core rompe un agente sin detectarse.
3. **Banco de casos de referencia** (`data/golden/casos.json`): expedientes
   sintéticos representativos (cirugía, urgencias, hospitalización, sin RIPS…).
   `golden` los construye, corre el motor REAL sobre ellos y compara dictamen y
   faltantes contra lo esperado — la red de regresión funcional que corre
   también en las pruebas automáticas. (Casos reales anonimizados pueden
   agregarse localmente; al repo solo entran sintéticos.)
4. **Salud operativa** (`salud`): misiones pendientes/fallidas, reintentos,
   duraciones, corridas — para ver cuándo un componente se degrada.

Solo lee el repo y el Expediente Digital; no toca los shares.

Uso:
    py tools\\hospiai_gobernanza.py artefactos
    py tools\\hospiai_gobernanza.py compatibilidad
    py tools\\hospiai_gobernanza.py golden
    py tools\\hospiai_gobernanza.py salud [--db data\\hospiai.db]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_agentes as hag  # noqa: E402
import hospiai_db  # noqa: E402
import hospiai_sdk as sdk  # noqa: E402
import radicar_facturacion as rad  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
RUTA_GOLDEN = RAIZ / "data" / "golden" / "casos.json"
RUTA_HUELLAS = RAIZ / "data" / "artefactos_huellas.json"


# ─── 1. Registro único de artefactos ─────────────────────────────────────────


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]


def descubrir_artefactos() -> list[dict]:
    """Inventario vivo: cada pieza de la plataforma como artefacto versionado
    (id, tipo, versión, origen, dependencias). La versión sale del propio
    artefacto — una sola fuente de verdad, sin duplicar registros a mano."""
    arts: list[dict] = []

    def _json(ruta: Path) -> dict:
        return json.loads(ruta.read_text(encoding="utf-8-sig")) if ruta.is_file() else {}

    arts.append(
        {
            "id": "CORE-SDK",
            "tipo": "SDK",
            "version": sdk.VERSION_SDK,
            "origen": "tools/hospiai_sdk.py",
            "depende_de": ["CORE-EXPEDIENTE"],
        }
    )
    arts.append(
        {
            "id": "CORE-MOTOR",
            "tipo": "MOTOR",
            "version": rad.VERSION_MOTOR,
            "origen": "tools/radicar_facturacion.py",
            "depende_de": ["RULES-RADICACION", "CATALOGO-PAGADORES"],
        }
    )
    arts.append(
        {
            "id": "CORE-EXPEDIENTE",
            "tipo": "ESQUEMA",
            "version": "1.2",
            "origen": "tools/hospiai_db.py",
            "depende_de": [],
        }
    )
    reglas = _json(RAIZ / "data" / "reglas_radicacion.json")
    arts.append(
        {
            "id": "RULES-RADICACION",
            "tipo": "REGLAS",
            "version": str(reglas.get("version", "?")),
            "origen": "data/reglas_radicacion.json",
            "depende_de": [],
        }
    )
    perfiles = _json(RAIZ / "data" / "perfiles_radicacion.json")
    arts.append(
        {
            "id": "CATALOGO-PAGADORES",
            "tipo": "CATALOGO",
            "version": str(perfiles.get("version", "1")),
            "origen": "data/perfiles_radicacion.json",
            "depende_de": [],
        }
    )
    for f in sorted((RAIZ / "data" / "ontologias").glob("*.json")):
        o = _json(f)
        arts.append(
            {
                "id": f"ONTOLOGIA-{o.get('ontologia', f.stem).upper()}",
                "tipo": "ONTOLOGIA",
                "version": str(o.get("version", "?")),
                "origen": f"data/ontologias/{f.name}",
                "depende_de": [],
            }
        )
    registro = _json(RAIZ / "data" / "agentes.json")
    for a in registro.get("agentes", []):
        arts.append(
            {
                "id": a["id"],
                "tipo": "AGENTE",
                "version": a.get("version", "?"),
                "estado": a.get("estado", ""),
                "origen": "data/agentes.json",
                "depende_de": (
                    ["CORE-SDK"] if str(a.get("implementacion", "")).startswith("sdk") else []
                )
                + a.get("depende_de", []),
                "requiere_sdk": a.get("requiere_sdk", ""),
            }
        )
    for art in arts:
        ruta = RAIZ / art["origen"]
        art["huella"] = _hash(ruta) if ruta.is_file() else ""
    return arts


def verificar_deriva(arts: list[dict], actualizar: bool = False) -> list[str]:
    """Detecta artefactos cuyo CONTENIDO cambió sin subir la versión (misma
    versión, distinta huella que la última registrada). Con actualizar=True
    sella las huellas actuales como línea base."""
    base = json.loads(RUTA_HUELLAS.read_text(encoding="utf-8")) if RUTA_HUELLAS.is_file() else {}
    avisos = []
    for a in arts:
        clave = a["id"]
        previa = base.get(clave)
        if previa and previa["huella"] != a["huella"] and previa["version"] == a["version"]:
            avisos.append(
                f"{clave}: cambió el contenido ({previa['huella']} → {a['huella']}) "
                f"pero la versión sigue en {a['version']} — subir la versión."
            )
    if actualizar:
        RUTA_HUELLAS.write_text(
            json.dumps(
                {a["id"]: {"version": a["version"], "huella": a["huella"]} for a in arts},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
    return avisos


# ─── 2. Contratos de compatibilidad ──────────────────────────────────────────


def verificar_compatibilidad() -> list[dict]:
    """Por cada agente con implementación SDK: (a) versión mayor del SDK
    declarada vs. vigente, (b) conformidad EN VIVO con el contrato (formato
    estándar, OMITIDO ante misión ajena, explicar completo)."""
    mayor_sdk = sdk.VERSION_SDK.split(".")[0]
    reg = hag.registro_con_implementaciones()
    informes: list[dict] = []
    claves_estandar = {
        "agente", "version", "expediente", "resultado", "confianza",
        "hallazgos", "evidencias", "salida", "detalle", "duracion_ms", "versiones",
    }  # fmt: skip
    for ficha in reg.listar():
        aid = ficha["id"]
        info = {"id": aid, "nombre": ficha.get("nombre", ""), "compatible": True, "motivos": []}
        req = str(ficha.get("requiere_sdk", "")).split(".")[0]
        implementado = aid in reg._clases
        if implementado and req and req != mayor_sdk:
            info["compatible"] = False
            info["motivos"].append(f"construido para SDK {req}.x, vigente {sdk.VERSION_SDK}")
        if implementado:
            try:
                inst = reg.instanciar(aid)
                if type(inst)._trabajar is sdk.Agente._trabajar:
                    info["compatible"] = False
                    info["motivos"].append("no implementa _trabajar()")
                exp = inst.explicar()
                faltan = {"id", "capacidades", "entradas", "salidas"} - set(exp)
                if faltan:
                    info["compatible"] = False
                    info["motivos"].append(f"explicar() incompleto: faltan {sorted(faltan)}")
                ajena = sdk.Mision(codigo="MISION-000000", tipo="__PRUEBA_CONTRATO__")
                res = inst.ejecutar(ajena)
                if set(res.a_dict()) != claves_estandar:
                    info["compatible"] = False
                    info["motivos"].append("el resultado no cumple el formato estándar")
                elif res.resultado != "OMITIDO":
                    info["compatible"] = False
                    info["motivos"].append("no valida el tipo de misión (debió OMITIR)")
            except Exception as e:
                info["compatible"] = False
                info["motivos"].append(f"falla al instanciar/ejecutar: {e}")
        else:
            info["motivos"].append("sin implementación SDK (legacy/planeado) — no aplica")
        informes.append(info)
    return informes


# ─── 3. Banco de casos de referencia (golden) ────────────────────────────────


def _construir_caso(base: Path, caso: dict) -> tuple[str, list, Path]:
    """Materializa un expediente sintético según su especificación."""
    espec = caso["construir"]
    fac = caso.get("factura", "HUS900001")
    d = base / caso["id"] / fac
    d.mkdir(parents=True)
    if espec.get("con_rips", True):
        rips = {
            "numFactura": fac,
            "numDocumentoIdObligado": "900006037",
            "usuarios": [
                {"servicios": espec.get("servicios") or {"consultas": [{"vrServicio": 1}]}}
            ],
        }
        (d / f"Rips_{fac}.json").write_text(json.dumps(rips), encoding="utf-8")
    if espec.get("con_fev", True):
        (d / f"FEV_900006037_{fac}.xml").write_text(
            f'<?xml version="1.0"?><Invoice xmlns:cbc="x"><cbc:ID>{fac}</cbc:ID></Invoice>',
            encoding="utf-8",
        )
    if espec.get("con_cuv", True):
        (d / f"CUV_900006037_{fac}.json").write_text("{}", encoding="utf-8")
    for cod in espec.get("soportes_extra", []):
        (d / f"{cod}_900006037_{fac}.pdf").write_text("x", encoding="utf-8")
    return fac, rad._archivos_de(d), d


def correr_golden(ruta_casos: Path | None = None) -> list[dict]:
    """Corre el MOTOR REAL sobre cada caso de referencia y compara dictamen y
    faltantes contra lo esperado. Cualquier cambio de regla/agente que altere
    un resultado esperado aparece aquí ANTES de llegar a producción."""
    casos = json.loads((ruta_casos or RUTA_GOLDEN).read_text(encoding="utf-8-sig"))["casos"]
    cfg = rad.cargar_perfiles(None)
    rad.cargar_reglas(None, cfg)
    resultados = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for caso in casos:
            fac, archivos, carpeta = _construir_caso(base, caso)
            res = rad.procesar_factura(fac, archivos, carpeta, caso.get("entidad"), cfg)
            esperado = caso["esperado"]
            obtenido = {
                "dictamen": res.estado,
                "faltan": sorted(res.soportes_faltantes + res.soportes_esperados_faltantes),
            }
            ok = obtenido["dictamen"] == esperado["dictamen"] and obtenido["faltan"] == sorted(
                esperado.get("faltan", [])
            )
            resultados.append(
                {"id": caso["id"], "ok": ok, "esperado": esperado, "obtenido": obtenido}
            )
    return resultados


# ─── 4. Salud operativa (observabilidad) ─────────────────────────────────────


def salud(db_path: Path) -> dict:
    con = hospiai_db.abrir(db_path)
    try:
        q = lambda s, a=(): con.execute(s, a).fetchall()  # noqa: E731
        misiones = {
            r["estado"]: r["n"]
            for r in q("SELECT estado, COUNT(*) n FROM misiones GROUP BY estado")
        }
        reintentadas = q("SELECT COUNT(*) n FROM misiones WHERE intentos > 1")[0]["n"]
        total_mis = sum(misiones.values())
        por_tipo = q(
            "SELECT tipo, COUNT(*) n,"
            " ROUND(AVG((julianday(actualizada)-julianday(creada))*86400000)) prom_ms"
            " FROM misiones WHERE estado IN ('OK','ERROR') GROUP BY tipo ORDER BY n DESC LIMIT 10"
        )
        corridas = q(
            "SELECT id, iniciada, terminada, total_expedientes,"
            " ROUND((julianday(terminada)-julianday(iniciada))*86400) seg"
            " FROM corridas ORDER BY id DESC LIMIT 5"
        )
        agentes_ev = q(
            "SELECT agente, COUNT(*) n FROM eventos GROUP BY agente ORDER BY n DESC LIMIT 10"
        )
    finally:
        con.close()
    return {
        "misiones": misiones,
        "tasa_error": (misiones.get("ERROR", 0) / total_mis) if total_mis else 0.0,
        "reintentadas": reintentadas,
        "misiones_por_tipo": [dict(r) for r in por_tipo],
        "corridas": [dict(r) for r in corridas],
        "eventos_por_agente": [dict(r) for r in agentes_ev],
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gobernanza de la arquitectura HOSPIAI (solo lee).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sa = sub.add_parser("artefactos", help="Registro único de artefactos versionados.")
    sa.add_argument("--sellar", action="store_true", help="Sella las huellas actuales como base.")
    sub.add_parser("compatibilidad", help="Contratos de compatibilidad SDK↔agentes (en vivo).")
    sub.add_parser("golden", help="Corre el banco de casos de referencia (regresión).")
    ss = sub.add_parser("salud", help="Métricas operativas de la plataforma.")
    ss.add_argument("--db", type=Path, default=RAIZ / "data" / "hospiai.db")
    args = p.parse_args(argv)

    if args.cmd == "artefactos":
        arts = descubrir_artefactos()
        print("=" * 86)
        print(f"{'ID':<26} {'TIPO':<10} {'VER.':<12} {'HUELLA':<18} ORIGEN")
        for a in arts:
            print(
                f"{a['id']:<26} {a['tipo']:<10} {a['version']:<12}"
                f" {a['huella'] or '—':<18} {a['origen']}"
            )
        print("=" * 86)
        avisos = verificar_deriva(arts, actualizar=args.sellar)
        for v in avisos:
            print(f"⚠ DERIVA: {v}")
        if args.sellar:
            print(f"Huellas selladas como línea base → {RUTA_HUELLAS.name}")
        elif not avisos:
            print(f"{len(arts)} artefacto(s), sin deriva contra la línea base.")
        return 1 if avisos else 0

    if args.cmd == "compatibilidad":
        informes = verificar_compatibilidad()
        rotos = [i for i in informes if not i["compatible"]]
        print("=" * 76)
        print(f"Contrato SDK vigente: v{sdk.VERSION_SDK}")
        for i in informes:
            marca = "✔" if i["compatible"] else "✘"
            print(f"  {marca} {i['id']:<7} {i['nombre']:<24} {'; '.join(i['motivos'])}")
        print("=" * 76)
        print(
            "Sin rupturas de contrato." if not rotos else f"{len(rotos)} agente(s) INCOMPATIBLES."
        )
        return 1 if rotos else 0

    if args.cmd == "golden":
        resultados = correr_golden()
        fallas = [r for r in resultados if not r["ok"]]
        print("=" * 76)
        for r in resultados:
            marca = "✔" if r["ok"] else "✘"
            print(f"  {marca} {r['id']:<32} esperado {r['esperado']['dictamen']}", end="")
            print("" if r["ok"] else f"  → OBTENIDO {r['obtenido']}")
        print("=" * 76)
        print(
            f"{len(resultados) - len(fallas)}/{len(resultados)} caso(s) de referencia en verde."
            + ("" if not fallas else "  ⚠ REGRESIÓN FUNCIONAL DETECTADA.")
        )
        return 1 if fallas else 0

    s = salud(args.db)
    print("=" * 64)
    print("Salud de la plataforma:")
    print(f"  Misiones: {s['misiones'] or '(sin misiones)'}  ·  reintentadas: {s['reintentadas']}")
    print(f"  Tasa de error de misiones: {s['tasa_error']:.1%}")
    for t in s["misiones_por_tipo"]:
        print(f"    {t['tipo']:<24} {t['n']:>5,}  prom. {t['prom_ms'] or 0:.0f} ms")
    print("  Corridas recientes:")
    for c in s["corridas"]:
        print(
            f"    #{c['id']}  {c['iniciada']}  {c['total_expedientes']:,} exp."
            f"  en {c['seg'] or 0:.0f} s"
        )
    print("  Eventos por agente:")
    for a in s["eventos_por_agente"]:
        print(f"    {a['agente']:<28} {a['n']:>6,}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
