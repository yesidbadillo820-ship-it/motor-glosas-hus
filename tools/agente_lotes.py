"""Agente local de lotes — corre en el PC del hospital y ejecuta los bots.

La app (Motor Glosas) encola tareas cuando un auditor sube un Excel
consolidado en /lotes. Este agente hace polling a la API, reclama la tarea,
descarga el Excel, corre el bot del portal (responder_glosas_coosalud.py)
y reporta el resultado factura por factura leyendo el CSV --reporte del bot.

Solo usa stdlib (urllib): en el PC del hospital no hay que instalar nada
más que lo que ya usa el bot (Python + playwright + openpyxl).

Versión de escritorio (recomendada para el día a día): doble clic en
tools\\AgenteLotes.pyw — abre una ventana donde se configura URL/token una
sola vez y se inicia/detiene el agente con un botón. Este CLI queda para
uso avanzado y automatización.

Uso CLI (PowerShell, desde la carpeta del proyecto):
    py tools\\agente_lotes.py --url http://servidor:8000 --token <token>
    py tools\\agente_lotes.py --una-vez      # procesa 1 tarea y sale
    py tools\\agente_lotes.py --con-cabeza   # muestra el browser (debug)

URL y token también pueden venir de las variables MOTOR_GLOSAS_URL /
AGENTE_LOTES_TOKEN, o de la configuración guardada por la ventana de
escritorio (%APPDATA%\\MotorGlosasHUS\\agente_lotes.json).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("agente_lotes")

TOOLS_DIR = Path(__file__).resolve().parent
BOTS_POR_TIPO = {"RESPONDER_COOSALUD": TOOLS_DIR / "responder_glosas_coosalud.py"}
# Cada cuántos segundos se relee el CSV del bot para reportar progreso
# incremental (el bot escribe append-as-you-go).
INTERVALO_PROGRESO = 30


# ─── Configuración compartida con la ventana de escritorio ───────────────────


def ruta_config() -> Path:
    """%APPDATA%\\MotorGlosasHUS\\agente_lotes.json (o ~/.config en Linux)."""
    base = os.environ.get("APPDATA")
    raiz = Path(base) if base else Path.home() / ".config"
    return raiz / "MotorGlosasHUS" / "agente_lotes.json"


def cargar_config() -> dict:
    try:
        return json.loads(ruta_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_config(config: dict) -> None:
    ruta = ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def construir_comando(
    bot: Path,
    tarea: dict,
    carpeta: Path,
    *,
    indice: Path | None = None,
    cerrar_residuales: bool = False,
    con_cabeza: bool = False,
) -> list[str]:
    """Arma la línea de comando del bot para una tarea (CLI y ventana)."""
    comando = [
        sys.executable,
        str(bot),
        "--excel",
        str(carpeta / tarea["nombre_archivo"]),
        "--hoja",
        tarea["hoja"],
        "--todas",
        "--reporte",
        str(carpeta / "reporte.csv"),
        "--evidencias",
        str(carpeta / "EVIDENCIA"),
        "--log",
        str(carpeta / "bot.log"),
    ]
    if tarea.get("incluir_calidad"):
        comando.append("--incluir-calidad")
    if indice:
        comando += ["--indice", str(indice)]
    if cerrar_residuales:
        comando.append("--cerrar-residuales")
    if con_cabeza:
        comando.append("--con-cabeza")
    return comando


class ApiLotes:
    def __init__(self, base_url: str, token: str, agente: str):
        self.base = base_url.rstrip("/")
        self.token = token
        self.agente = agente

    def _request(self, metodo: str, ruta: str, payload: dict | None = None) -> tuple[int, bytes]:
        req = urllib.request.Request(
            f"{self.base}{ruta}",
            method=metodo,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "X-Agente-Token": self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def reclamar(self) -> dict | None:
        status, cuerpo = self._request(
            "POST", "/agente/lotes/tareas/reclamar", {"agente": self.agente}
        )
        if status == 204:
            return None
        if status != 200:
            raise RuntimeError(f"reclamar → HTTP {status}: {cuerpo[:300]!r}")
        return json.loads(cuerpo)

    def descargar_excel(self, tarea_id: int, destino: Path) -> None:
        status, cuerpo = self._request("GET", f"/agente/lotes/tareas/{tarea_id}/excel")
        if status != 200:
            raise RuntimeError(f"descargar excel → HTTP {status}: {cuerpo[:300]!r}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(cuerpo)

    def progreso(self, tarea_id: int, resultados: list[dict]) -> None:
        status, cuerpo = self._request(
            "POST",
            f"/agente/lotes/tareas/{tarea_id}/progreso",
            {"exito": True, "resultados": resultados},
        )
        if status != 200:
            logger.warning(f"progreso → HTTP {status}: {cuerpo[:200]!r}")

    def completar(
        self, tarea_id: int, exito: bool, resultados: list[dict], error: str | None
    ) -> None:
        status, cuerpo = self._request(
            "POST",
            f"/agente/lotes/tareas/{tarea_id}/completar",
            {"exito": exito, "resultados": resultados, "error": error},
        )
        if status != 200:
            raise RuntimeError(f"completar → HTTP {status}: {cuerpo[:300]!r}")


def leer_reporte(ruta: Path) -> list[dict]:
    """Lee el CSV --reporte del bot: filas {factura, estado, detalle}."""
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8-sig", newline="") as fh:
        return [
            {
                "factura": (r.get("factura") or "").strip(),
                "estado": (r.get("estado") or "").strip(),
                "detalle": (r.get("detalle") or "").strip(),
            }
            for r in csv.DictReader(fh)
            if (r.get("factura") or "").strip()
        ]


def procesar_tarea(api: ApiLotes, tarea: dict, args: argparse.Namespace) -> None:
    tarea_id = tarea["tarea_id"]
    bot = BOTS_POR_TIPO.get(tarea["tipo"])
    if bot is None or not bot.exists():
        api.completar(tarea_id, False, [], f"Tipo de tarea no soportado: {tarea['tipo']}")
        return

    carpeta = args.workdir / f"lote_{tarea['lote_id']}"
    reporte = carpeta / "reporte.csv"
    api.descargar_excel(tarea_id, carpeta / tarea["nombre_archivo"])

    comando = construir_comando(
        bot,
        tarea,
        carpeta,
        indice=args.indice,
        cerrar_residuales=args.cerrar_residuales,
        con_cabeza=args.con_cabeza,
    )
    logger.info(f"Tarea {tarea_id} (lote {tarea['lote_id']}): {' '.join(comando)}")
    proceso = subprocess.Popen(comando)
    reportadas = 0
    while proceso.poll() is None:
        time.sleep(INTERVALO_PROGRESO)
        filas = leer_reporte(reporte)
        if len(filas) > reportadas:
            api.progreso(tarea_id, filas)
            reportadas = len(filas)
            logger.info(f"  progreso: {reportadas}/{tarea['total_facturas']} facturas")

    filas = leer_reporte(reporte)
    exito = proceso.returncode == 0
    error = None if exito else f"El bot terminó con código {proceso.returncode} (ver bot.log)."
    api.completar(tarea_id, exito, filas, error)
    logger.info(f"Tarea {tarea_id} terminada: exito={exito}, {len(filas)} facturas reportadas.")


def main() -> int:
    config = cargar_config()
    parser = argparse.ArgumentParser(description="Agente local de lotes del Motor Glosas.")
    parser.add_argument(
        "--url",
        default=os.environ.get("MOTOR_GLOSAS_URL", "") or config.get("url", ""),
        help="URL de la app (o env MOTOR_GLOSAS_URL, o la config de la ventana).",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENTE_LOTES_TOKEN", "") or config.get("token", ""),
        help="Token compartido (o env AGENTE_LOTES_TOKEN, o la config de la ventana).",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("lotes_agente"),
        help="Carpeta local para Excel/reportes/evidencias (default: lotes_agente).",
    )
    parser.add_argument(
        "--intervalo", type=int, default=60, help="Segundos entre polls (default 60)."
    )
    parser.add_argument("--una-vez", action="store_true", help="Procesar 1 tarea y salir.")
    parser.add_argument(
        "--indice", type=Path, default=None, help="TXT índice factura→carpeta (PDX SOPORTES)."
    )
    parser.add_argument(
        "--cerrar-residuales",
        action="store_true",
        help="Pasar --cerrar-residuales al bot (RE9901 a glosas fuera del Excel).",
    )
    parser.add_argument("--con-cabeza", action="store_true", help="Mostrar el browser del bot.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if not args.url or not args.token:
        sys.stderr.write(
            "ERROR: faltan MOTOR_GLOSAS_URL y/o AGENTE_LOTES_TOKEN "
            "(env, --url/--token, o configuralos una vez en la ventana "
            "de escritorio: doble clic en tools\\AgenteLotes.pyw).\n"
        )
        return 2

    api = ApiLotes(args.url, args.token, socket.gethostname())
    logger.info(f"Agente '{api.agente}' → {api.base} (workdir: {args.workdir.resolve()})")
    while True:
        try:
            tarea = api.reclamar()
        except (RuntimeError, urllib.error.URLError) as e:
            logger.warning(f"No pude reclamar tarea ({e}); reintento en {args.intervalo}s.")
            tarea = None
        if tarea is not None:
            try:
                procesar_tarea(api, tarea, args)
            except Exception:
                logger.exception(f"Fallo procesando la tarea {tarea['tarea_id']}")
                try:
                    api.completar(
                        tarea["tarea_id"], False, [], "Excepción en el agente (ver consola)."
                    )
                except Exception:
                    logger.exception("Tampoco pude reportar el fallo a la app.")
            if args.una_vez:
                return 0
        elif args.una_vez:
            logger.info("Sin tareas pendientes.")
            return 0
        else:
            time.sleep(args.intervalo)


if __name__ == "__main__":
    sys.exit(main())
