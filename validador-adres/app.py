"""Validador ADRES Web — app independiente del Motor Glosas HUS.

Aplicación web para validar reclamaciones FURIPS (Circular 022/2023 ADRES)
desde el navegador: se suben los TXT FURIPS 1 y 2 y un ZIP con los soportes
(RIPS/CUV JSON, factura XML/PDF, epicrisis PDF — en carpetas por factura o
en carpeta plana), la validación corre en el servidor con progreso en vivo
y el resultado se ve en un tablero con semáforo por factura, hallazgos
filtrables y descarga del informe Excel completo.

El motor de validación es el MISMO de la herramienta de línea de comandos
(`tools/adres/validar_furips.py`): malla de los 102 campos del FURIPS 1 y
9 del FURIPS 2, coherencia FURIPS1↔FURIPS2 y cruce contra los soportes.

USO
---
    py -m uvicorn app:app --host 0.0.0.0 --port 8010
    # o en Windows: doble clic a VALIDADOR_ADRES_WEB.cmd

Luego abrir http://localhost:8010
"""

from __future__ import annotations

import logging
import shutil
import sys
import tempfile
import threading
import uuid
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Motor de validación: el mismo de tools/adres (sin duplicar código)
_RAIZ_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ_REPO / "tools" / "adres"))
import validar_furips as vf  # noqa: E402

logger = logging.getLogger("validador_adres_web")
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(
    title="Validador ADRES — FURIPS",
    description="Validación de reclamaciones FURIPS vs Circular 022/2023 y soportes",
    version="1.0.0",
)

_DIR_TRABAJO = Path(tempfile.gettempdir()) / "validador_adres_web"
_DIR_TRABAJO.mkdir(parents=True, exist_ok=True)

MAX_MB_ARCHIVO = 500
_EXT_PERMITIDAS = {".txt", ".zip", ".json", ".xml", ".pdf"}

# Trabajos en memoria: {id: {"estado", "progreso", "total", "mensaje",
#                            "resultados", "obs", "resumen", "creado"}}
_trabajos: dict[str, dict] = {}
_lock = threading.Lock()


def _limpiar_trabajos_viejos(max_trabajos: int = 20) -> None:
    """Mantiene solo los últimos trabajos (memoria y disco acotados)."""
    with _lock:
        if len(_trabajos) <= max_trabajos:
            return
        viejos = sorted(_trabajos, key=lambda k: _trabajos[k]["creado"])[:-max_trabajos]
        for k in viejos:
            carpeta = _DIR_TRABAJO / k
            _trabajos.pop(k, None)
            shutil.rmtree(carpeta, ignore_errors=True)


def _guardar_subida(archivo: UploadFile, destino: Path) -> Path:
    ext = Path(archivo.filename or "archivo").suffix.lower()
    if ext not in _EXT_PERMITIDAS:
        raise HTTPException(400, f"Extensión no permitida: {ext}")
    nombre = Path(archivo.filename or f"archivo{ext}").name  # sin rutas
    ruta = destino / nombre
    tam = 0
    with ruta.open("wb") as fh:
        while True:
            trozo = archivo.file.read(1024 * 1024)
            if not trozo:
                break
            tam += len(trozo)
            if tam > MAX_MB_ARCHIVO * 1024 * 1024:
                ruta.unlink(missing_ok=True)
                raise HTTPException(413, f"{nombre} supera {MAX_MB_ARCHIVO} MB")
            fh.write(trozo)
    return ruta


def _extraer_zip_seguro(ruta_zip: Path, destino: Path) -> int:
    """Extrae el ZIP evitando path traversal. Devuelve archivos extraídos."""
    extraidos = 0
    with zipfile.ZipFile(ruta_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            nombre = Path(info.filename)
            # normalizar: sin absolutos ni '..'
            partes = [p for p in nombre.parts if p not in ("..", "/", "\\") and ":" not in p]
            if not partes:
                continue
            destino_final = destino.joinpath(*partes)
            destino_final.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as origen, destino_final.open("wb") as sal:
                shutil.copyfileobj(origen, sal)
            extraidos += 1
    ruta_zip.unlink(missing_ok=True)
    return extraidos


def _severidad_orden(sev: str) -> int:
    return {"ERROR": 0, "ADVERTENCIA": 1, "INFO": 2}.get(sev, 3)


def _resumen_factura(res) -> dict:
    reg = res.registro_f1
    c = {n: reg[n - 1] for n in range(1, 103)} if reg else {}
    tipos = {s["tipo"]: s for s in res.soportes}

    def sop(tipo: str) -> str:
        if not res.archivos:
            return "—"
        s = tipos.get(tipo)
        if not s:
            return "FALTA"
        if s.get("legible") == "NO (escaneado)":
            return "SIN TEXTO"
        return "SI"

    estado = "CON ERRORES" if res.errores else ("REVISAR" if res.advertencias else "CUMPLE")
    return {
        "factura": res.factura,
        "consecutivo": c.get(4, ""),
        "paciente": " ".join(x for x in (c.get(8), c.get(9), c.get(6), c.get(7)) if x),
        "documento": f"{c.get(10, '')} {c.get(11, '')}".strip(),
        "fecha_evento": c.get(23, ""),
        "ingreso": f"{c.get(80, '')} {c.get(81, '')}".strip(),
        "egreso": f"{c.get(82, '')} {c.get(83, '')}".strip(),
        "vr_facturado": (vf.a_entero(c.get(97, "")) or 0) + (vf.a_entero(c.get(99, "")) or 0)
        if reg
        else None,
        "vr_reclamado": (vf.a_entero(c.get(98, "")) or 0) + (vf.a_entero(c.get(100, "")) or 0)
        if reg
        else None,
        "lineas_f2": len(res.lineas_f2),
        "furips1": bool(reg),
        "soportes": {
            "rips": sop("RIPS JSON"),
            "cuv": sop("CUV JSON"),
            "fev_xml": sop("FACTURA XML"),
            "factura_pdf": sop("FACTURA PDF"),
            "epicrisis": sop("EPICRISIS"),
        },
        "errores": res.errores,
        "advertencias": res.advertencias,
        "estado": estado,
    }


def _detalle_factura(res) -> dict:
    d = _resumen_factura(res)
    d["hallazgos"] = [
        {
            "origen": h.origen,
            "severidad": h.severidad,
            "campo": h.campo,
            "concepto": h.concepto,
            "valor_furips": h.valor_furips,
            "valor_soporte": h.valor_soporte,
            "fuente": h.fuente,
            "regla": h.regla,
            "detalle": h.detalle,
        }
        for h in sorted(res.hallazgos, key=lambda h: (_severidad_orden(h.severidad), h.origen))
    ]
    d["campos_f1"] = (
        [
            {
                "n": n,
                "seccion": seccion,
                "campo": nombre,
                "valor": res.registro_f1[n - 1],
                "obligatoriedad": vf.TEXTO_OBLIG.get(oblig, oblig),
                "estado": res.estado_campos_f1.get(n, ("OK", ""))[0],
                "obs": res.estado_campos_f1.get(n, ("OK", ""))[1],
            }
            for (n, seccion, nombre, _l, _f, _v, oblig) in vf.E1
        ]
        if res.registro_f1
        else []
    )
    d["lineas"] = [
        {
            "n": i,
            "tipo": f"{ln[2]} - {vf.TIPOS_SERVICIO_F2.get(ln[2], '?')}",
            "codigo": ln[3],
            "descripcion": ln[4],
            "cantidad": vf.a_entero(ln[5]),
            "vr_unitario": vf.a_entero(ln[6]),
            "vr_facturado": vf.a_entero(ln[7]),
            "vr_reclamado": vf.a_entero(ln[8]),
            "estado": res.estado_lineas_f2[i - 1][0] if i <= len(res.estado_lineas_f2) else "OK",
            "obs": res.estado_lineas_f2[i - 1][1] if i <= len(res.estado_lineas_f2) else "",
        }
        for i, ln in enumerate(res.lineas_f2, 1)
    ]
    d["cruces"] = res.cruces
    d["archivos"] = res.soportes
    return d


def _correr_validacion(trabajo_id: str, raiz: Path, sin_pdf: bool) -> None:
    tr = _trabajos[trabajo_id]
    try:
        rutas_f1, rutas_f2 = vf.descubrir_archivos_furips(raiz)
        if not rutas_f1 and not rutas_f2:
            tr.update(
                estado="ERROR",
                mensaje="No se encontró ningún archivo FURIPS1*.txt / FURIPS2*.txt "
                "en lo subido. Suba los TXT o inclúyalos dentro del ZIP.",
            )
            return
        registros_f1, obs1 = vf.leer_furips1(rutas_f1)
        lineas_f2, obs2 = vf.leer_furips2(rutas_f2)
        soportes = vf.descubrir_soportes(raiz)
        claves = sorted(set(registros_f1) | set(soportes) | set(lineas_f2))

        tr.update(total=len(claves), progreso=0, mensaje="Validando facturas…")
        resultados = []
        for i, clave in enumerate(claves, 1):
            regs = registros_f1.get(clave, [])
            res = vf.ResultadoFactura(factura=clave)
            res.archivos = sorted(soportes.get(clave, []))
            res.carpeta = res.archivos[0].parent if res.archivos else None
            res.lineas_f2 = lineas_f2.get(clave, [])
            if len(regs) > 1:
                res.agregar(
                    "ESTRUCTURA",
                    vf.ADVERTENCIA,
                    "-",
                    "Registros duplicados",
                    f"{len(regs)} registros",
                    "Circular 022/2023",
                    f"La factura aparece {len(regs)} veces en el FURIPS 1; "
                    f"se valida el primer registro.",
                )
            res.registro_f1 = regs[0] if regs else None
            vf.validar_malla_f1(res)
            vf.validar_furips2(res)
            vf.analizar_carpeta(res, sin_pdf=sin_pdf)
            vf.cruzar_soportes(res)
            resultados.append(res)
            tr.update(progreso=i, mensaje=f"Validando {clave} ({i}/{len(claves)})…")

        tr["resultados"] = resultados
        tr["obs"] = obs1 + obs2
        tr["resumen"] = [_resumen_factura(r) for r in resultados]
        tr.update(estado="LISTO", mensaje="Validación completada.")
    except Exception as e:  # el trabajo reporta el error, el servidor sigue vivo
        logger.exception(f"Trabajo {trabajo_id} falló")
        tr.update(estado="ERROR", mensaje=f"Error inesperado durante la validación: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/validar")
async def crear_validacion(
    archivos: list[UploadFile] = File(..., description="TXT FURIPS y/o ZIP de soportes"),
    sin_pdf: bool = False,
):
    _limpiar_trabajos_viejos()
    trabajo_id = uuid.uuid4().hex[:12]
    raiz = _DIR_TRABAJO / trabajo_id
    raiz.mkdir(parents=True, exist_ok=True)

    n_zip = 0
    for archivo in archivos:
        ruta = _guardar_subida(archivo, raiz)
        if ruta.suffix.lower() == ".zip":
            try:
                n_zip += _extraer_zip_seguro(ruta, raiz)
            except zipfile.BadZipFile as e:
                raise HTTPException(400, f"{ruta.name} no es un ZIP válido") from e

    _trabajos[trabajo_id] = {
        "estado": "PROCESANDO",
        "progreso": 0,
        "total": 0,
        "mensaje": "Preparando validación…",
        "creado": datetime.now().isoformat(),
        "resultados": None,
        "obs": [],
        "resumen": [],
    }
    threading.Thread(
        target=_correr_validacion, args=(trabajo_id, raiz, sin_pdf), daemon=True
    ).start()
    return {"id": trabajo_id, "archivos_zip": n_zip}


@app.get("/api/validaciones/{trabajo_id}/estado")
def estado_validacion(trabajo_id: str):
    tr = _trabajos.get(trabajo_id)
    if not tr:
        raise HTTPException(404, "Validación no encontrada (el servidor pudo reiniciarse).")
    return {
        "estado": tr["estado"],
        "progreso": tr["progreso"],
        "total": tr["total"],
        "mensaje": tr["mensaje"],
    }


@app.get("/api/validaciones/{trabajo_id}")
def resultado_validacion(trabajo_id: str):
    tr = _trabajos.get(trabajo_id)
    if not tr:
        raise HTTPException(404, "Validación no encontrada.")
    if tr["estado"] != "LISTO":
        return JSONResponse({"estado": tr["estado"], "mensaje": tr["mensaje"]}, status_code=202)
    resumen = tr["resumen"]
    tot_err = sum(r["errores"] for r in resumen)
    tot_adv = sum(r["advertencias"] for r in resumen)

    # Agregaciones para las gráficas del tablero
    por_origen: Counter = Counter()
    por_concepto: Counter = Counter()
    for res in tr["resultados"]:
        for h in res.hallazgos:
            if h.severidad in ("ERROR", "ADVERTENCIA"):
                por_origen[(h.origen, h.severidad)] += 1
                etiqueta = h.concepto
                if h.campo and h.campo not in ("-",) and not h.campo.startswith("L"):
                    etiqueta = f"Campo {h.campo} · {h.concepto}"
                por_concepto[(etiqueta, h.severidad)] += 1
    origenes = sorted(
        {o for (o, _s) in por_origen},
        key=lambda o: -sum(por_origen.get((o, sev), 0) for sev in ("ERROR", "ADVERTENCIA")),
    )
    graf_origen = [
        {
            "origen": o,
            "error": por_origen.get((o, "ERROR"), 0),
            "advertencia": por_origen.get((o, "ADVERTENCIA"), 0),
        }
        for o in origenes
    ]
    conceptos = sorted(
        {c for (c, _s) in por_concepto},
        key=lambda c: -sum(por_concepto.get((c, sev), 0) for sev in ("ERROR", "ADVERTENCIA")),
    )[:10]
    graf_conceptos = [
        {
            "concepto": c,
            "error": por_concepto.get((c, "ERROR"), 0),
            "advertencia": por_concepto.get((c, "ADVERTENCIA"), 0),
        }
        for c in conceptos
    ]
    top_facturas = sorted(resumen, key=lambda r: (-r["errores"], -r["advertencias"]))[:10]

    return {
        "estado": "LISTO",
        "kpis": {
            "facturas": len(resumen),
            "con_errores": sum(1 for r in resumen if r["estado"] == "CON ERRORES"),
            "revisar": sum(1 for r in resumen if r["estado"] == "REVISAR"),
            "cumplen": sum(1 for r in resumen if r["estado"] == "CUMPLE"),
            "errores": tot_err,
            "advertencias": tot_adv,
            "vr_facturado": sum(r["vr_facturado"] or 0 for r in resumen),
        },
        "graficas": {
            "por_origen": graf_origen,
            "por_concepto": graf_conceptos,
            "top_facturas": [
                {
                    "factura": r["factura"],
                    "errores": r["errores"],
                    "advertencias": r["advertencias"],
                    "vr": r["vr_facturado"],
                }
                for r in top_facturas
                if r["errores"] or r["advertencias"]
            ],
        },
        "obs_archivos": tr["obs"],
        "facturas": resumen,
    }


@app.get("/api/validaciones/{trabajo_id}/hallazgos")
def hallazgos_globales(trabajo_id: str):
    tr = _trabajos.get(trabajo_id)
    if not tr or tr["estado"] != "LISTO":
        raise HTTPException(404, "Validación no disponible.")
    hallazgos = [
        {
            "factura": res.factura,
            "origen": h.origen,
            "severidad": h.severidad,
            "campo": h.campo,
            "concepto": h.concepto,
            "valor_furips": h.valor_furips,
            "valor_soporte": h.valor_soporte,
            "fuente": h.fuente,
            "regla": h.regla,
            "detalle": h.detalle,
        }
        for res in tr["resultados"]
        for h in res.hallazgos
    ]
    hallazgos.sort(key=lambda h: (_severidad_orden(h["severidad"]), h["factura"]))
    return {"hallazgos": hallazgos}


@app.get("/api/validaciones/{trabajo_id}/facturas/{factura}")
def detalle_factura(trabajo_id: str, factura: str):
    tr = _trabajos.get(trabajo_id)
    if not tr or tr["estado"] != "LISTO":
        raise HTTPException(404, "Validación no disponible.")
    for res in tr["resultados"]:
        if res.factura == factura:
            return _detalle_factura(res)
    raise HTTPException(404, f"Factura {factura} no está en esta validación.")


@app.get("/api/validaciones/{trabajo_id}/excel")
def descargar_excel(trabajo_id: str):
    tr = _trabajos.get(trabajo_id)
    if not tr or tr["estado"] != "LISTO":
        raise HTTPException(404, "Validación no disponible.")
    salida = _DIR_TRABAJO / trabajo_id / "INFORME_VALIDACION_FURIPS.xlsx"
    if not salida.exists():
        vf.generar_excel(tr["resultados"], tr["obs"], salida)
    fecha = datetime.now().strftime("%Y%m%d")
    return FileResponse(
        salida,
        filename=f"INFORME_VALIDACION_FURIPS_{fecha}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/salud")
def salud():
    motores = []
    for modulo in ("pdfplumber", "pypdf"):
        try:
            __import__(modulo)
            motores.append(modulo)
        except ImportError:
            pass
    return {"ok": True, "motores_pdf": motores, "trabajos_en_memoria": len(_trabajos)}


# Frontend estático (al final, para no tapar /api/*)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
