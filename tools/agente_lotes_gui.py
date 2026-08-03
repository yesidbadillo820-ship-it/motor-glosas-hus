"""Ventana de escritorio del Agente de Lotes — Motor Glosas HUS.

La versión "aplicación" del agente: una ventana con la configuración
(URL de la app + token, guardados para siempre en
%APPDATA%\\MotorGlosasHUS\\agente_lotes.json), un botón Iniciar/Detener
y el log en vivo. Pensada para doble clic (tools\\AgenteLotes.pyw) —
cero PowerShell, cero setx.

Solo usa stdlib: tkinter viene incluido con Python en Windows.
"""

from __future__ import annotations

import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# El módulo vive en tools/ (sin __init__.py): al abrirse por doble clic vía
# AgenteLotes.pyw el import directo funciona porque el launcher agrega esta
# carpeta al sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agente_lotes import (  # noqa: E402
    BOTS_POR_TIPO,
    INTERVALO_PROGRESO,
    ApiLotes,
    cargar_config,
    construir_comando,
    guardar_config,
    leer_reporte,
)

INTERVALO_POLL = 60  # segundos entre consultas a la cola cuando no hay lotes


class AgenteWorker(threading.Thread):
    """Loop del agente en un hilo aparte; le habla a la ventana por una cola.

    Eventos: ("log", texto), ("estado", texto), ("fin", None).
    """

    daemon = True

    def __init__(self, opciones: dict, eventos: queue.Queue, stop_event: threading.Event):
        super().__init__(name="agente-lotes")
        self.opciones = opciones
        self.eventos = eventos
        self.stop_event = stop_event

    def log(self, texto: str) -> None:
        self.eventos.put(("log", texto))

    def estado(self, texto: str) -> None:
        self.eventos.put(("estado", texto))

    def run(self) -> None:
        api = ApiLotes(self.opciones["url"], self.opciones["token"], socket.gethostname())
        self.log(f"Agente '{api.agente}' conectado a {api.base}")
        while not self.stop_event.is_set():
            try:
                tarea = api.reclamar()
            except Exception as e:
                self.log(f"Sin conexión con la app: {e}")
                self.estado("Sin conexión — reintentando…")
                self._esperar(INTERVALO_POLL)
                continue
            if tarea is None:
                self.estado("En espera de lotes… (la cola está vacía)")
                self._esperar(INTERVALO_POLL)
                continue
            try:
                self._procesar(api, tarea)
            except Exception as e:
                self.log(f"Fallo procesando la tarea {tarea['tarea_id']}: {e}")
                try:
                    api.completar(tarea["tarea_id"], False, [], f"Excepción en el agente: {e}")
                except Exception as e2:
                    self.log(f"Tampoco pude reportar el fallo a la app: {e2}")
        self.estado("Detenido")
        self.eventos.put(("fin", None))

    def _esperar(self, segundos: float) -> None:
        fin = time.monotonic() + segundos
        while not self.stop_event.is_set() and time.monotonic() < fin:
            time.sleep(0.5)

    def _procesar(self, api: ApiLotes, tarea: dict) -> None:
        tarea_id = tarea["tarea_id"]
        bot = BOTS_POR_TIPO.get(tarea["tipo"])
        if bot is None or not bot.exists():
            api.completar(tarea_id, False, [], f"Tipo de tarea no soportado: {tarea['tipo']}")
            self.log(f"Tarea {tarea_id} rechazada: tipo {tarea['tipo']} no soportado.")
            return

        carpeta = Path(self.opciones["workdir"]) / f"lote_{tarea['lote_id']}"
        reporte = carpeta / "reporte.csv"
        self.estado(f"Lote {tarea['lote_id']}: descargando Excel…")
        api.descargar_excel(tarea_id, carpeta / tarea["nombre_archivo"])

        indice = self.opciones.get("indice") or None
        comando = construir_comando(
            bot,
            tarea,
            carpeta,
            indice=Path(indice) if indice else None,
            cerrar_residuales=self.opciones.get("cerrar_residuales", False),
            con_cabeza=self.opciones.get("con_cabeza", False),
        )
        self.log(f"Lote {tarea['lote_id']}: iniciando bot ({tarea['total_facturas']} facturas)…")
        # CREATE_NO_WINDOW: bajo pythonw (doble clic) evita que el bot abra
        # una consola negra; sus logs quedan en bot.log dentro de la carpeta
        # del lote.
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        proceso = subprocess.Popen(comando, creationflags=flags)
        reportadas = 0
        ultimo_progreso = time.monotonic()
        while proceso.poll() is None:
            if self.stop_event.is_set():
                proceso.terminate()
                try:
                    proceso.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                filas = leer_reporte(reporte)
                api.completar(tarea_id, False, filas, "Detenido por el usuario desde el agente.")
                self.log(f"Lote {tarea['lote_id']}: detenido por el usuario.")
                return
            time.sleep(1)
            if time.monotonic() - ultimo_progreso >= INTERVALO_PROGRESO:
                ultimo_progreso = time.monotonic()
                filas = leer_reporte(reporte)
                if len(filas) > reportadas:
                    api.progreso(tarea_id, filas)
                    reportadas = len(filas)
                self.estado(
                    f"Lote {tarea['lote_id']}: {len(filas)}/{tarea['total_facturas']} "
                    "facturas procesadas…"
                )

        filas = leer_reporte(reporte)
        exito = proceso.returncode == 0
        error = None if exito else f"El bot terminó con código {proceso.returncode} (ver bot.log)."
        api.completar(tarea_id, exito, filas, error)
        resultado = "COMPLETADO" if exito else f"ERROR ({error})"
        self.log(f"Lote {tarea['lote_id']} terminado: {resultado} — {len(filas)} facturas.")


class VentanaAgente:
    def __init__(self) -> None:
        self.raiz = tk.Tk()
        self.raiz.title("Agente de Lotes — Motor Glosas HUS")
        self.raiz.minsize(640, 520)
        self.eventos: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: AgenteWorker | None = None

        config = cargar_config()
        self.var_url = tk.StringVar(value=config.get("url", ""))
        self.var_token = tk.StringVar(value=config.get("token", ""))
        self.var_workdir = tk.StringVar(
            value=config.get("workdir", str(Path.home() / "lotes_agente"))
        )
        self.var_indice = tk.StringVar(value=config.get("indice", ""))
        self.var_con_cabeza = tk.BooleanVar(value=config.get("con_cabeza", False))
        self.var_residuales = tk.BooleanVar(value=config.get("cerrar_residuales", False))
        self.var_estado = tk.StringVar(value="Detenido")

        self._armar_widgets()
        self.raiz.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        self.raiz.after(200, self._bombear_eventos)

    def _armar_widgets(self) -> None:
        relleno = {"padx": 8, "pady": 4}

        marco_cfg = ttk.LabelFrame(self.raiz, text="Conexión (se guarda sola)")
        marco_cfg.pack(fill="x", **relleno)
        marco_cfg.columnconfigure(1, weight=1)
        ttk.Label(marco_cfg, text="URL de la app:").grid(row=0, column=0, sticky="w", **relleno)
        ttk.Entry(marco_cfg, textvariable=self.var_url).grid(
            row=0, column=1, columnspan=2, sticky="ew", **relleno
        )
        ttk.Label(marco_cfg, text="Token del agente:").grid(row=1, column=0, sticky="w", **relleno)
        ttk.Entry(marco_cfg, textvariable=self.var_token, show="•").grid(
            row=1, column=1, columnspan=2, sticky="ew", **relleno
        )

        marco_op = ttk.LabelFrame(self.raiz, text="Opciones")
        marco_op.pack(fill="x", **relleno)
        marco_op.columnconfigure(1, weight=1)
        ttk.Label(marco_op, text="Carpeta de trabajo:").grid(row=0, column=0, sticky="w", **relleno)
        ttk.Entry(marco_op, textvariable=self.var_workdir).grid(
            row=0, column=1, sticky="ew", **relleno
        )
        ttk.Button(marco_op, text="Examinar…", command=self._elegir_workdir).grid(
            row=0, column=2, **relleno
        )
        ttk.Label(marco_op, text="Índice de soportes (opcional):").grid(
            row=1, column=0, sticky="w", **relleno
        )
        ttk.Entry(marco_op, textvariable=self.var_indice).grid(
            row=1, column=1, sticky="ew", **relleno
        )
        ttk.Button(marco_op, text="Examinar…", command=self._elegir_indice).grid(
            row=1, column=2, **relleno
        )
        ttk.Checkbutton(
            marco_op, text="Mostrar el navegador del bot (debug)", variable=self.var_con_cabeza
        ).grid(row=2, column=0, columnspan=3, sticky="w", **relleno)
        ttk.Checkbutton(
            marco_op,
            text="Cerrar glosas residuales del portal con RE9901",
            variable=self.var_residuales,
        ).grid(row=3, column=0, columnspan=3, sticky="w", **relleno)

        marco_ctl = ttk.Frame(self.raiz)
        marco_ctl.pack(fill="x", **relleno)
        self.boton = ttk.Button(marco_ctl, text="▶  Iniciar agente", command=self._alternar)
        self.boton.pack(side="left", padx=8)
        ttk.Label(marco_ctl, text="Estado:").pack(side="left", padx=(16, 4))
        ttk.Label(marco_ctl, textvariable=self.var_estado, font=("Segoe UI", 9, "bold")).pack(
            side="left"
        )

        self.log = scrolledtext.ScrolledText(self.raiz, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self._log("Configura la URL y el token (una sola vez) y presiona Iniciar.")
        self._log("Los lotes se suben desde la app web, sección Lotes.")

    # ─── Acciones ────────────────────────────────────────────────────────────

    def _elegir_workdir(self) -> None:
        carpeta = filedialog.askdirectory(title="Carpeta de trabajo del agente")
        if carpeta:
            self.var_workdir.set(carpeta)

    def _elegir_indice(self) -> None:
        archivo = filedialog.askopenfilename(
            title="Índice de soportes (TXT)", filetypes=[("Texto", "*.txt"), ("Todos", "*.*")]
        )
        if archivo:
            self.var_indice.set(archivo)

    def _alternar(self) -> None:
        if self.worker and self.worker.is_alive():
            self._detener()
        else:
            self._iniciar()

    def _iniciar(self) -> None:
        url = self.var_url.get().strip()
        token = self.var_token.get().strip()
        if not url or not token:
            messagebox.showwarning(
                "Faltan datos",
                "Escribe la URL de la app y el token del agente.\n"
                "El token es el mismo AGENTE_LOTES_TOKEN del servidor "
                "(pídeselo al administrador).",
            )
            return
        opciones = {
            "url": url,
            "token": token,
            "workdir": self.var_workdir.get().strip() or str(Path.home() / "lotes_agente"),
            "indice": self.var_indice.get().strip(),
            "con_cabeza": self.var_con_cabeza.get(),
            "cerrar_residuales": self.var_residuales.get(),
        }
        guardar_config(opciones)
        self.stop_event.clear()
        self.worker = AgenteWorker(opciones, self.eventos, self.stop_event)
        self.worker.start()
        self.boton.config(text="■  Detener agente")
        self.var_estado.set("Iniciando…")
        self._log("Agente iniciado.")

    def _detener(self) -> None:
        if not messagebox.askyesno(
            "Detener agente",
            "Si hay un lote en proceso, el bot se interrumpirá y el lote "
            "quedará en ERROR (se puede reintentar después).\n\n¿Detener el agente?",
        ):
            return
        self.stop_event.set()
        self.boton.config(state="disabled", text="Deteniendo…")
        self._log("Deteniendo… (espera a que termine el paso actual)")

    def _al_cerrar(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                "Cerrar",
                "El agente sigue corriendo. ¿Detenerlo y cerrar la ventana?",
            ):
                return
            self.stop_event.set()
        self.raiz.destroy()

    # ─── Comunicación con el hilo ────────────────────────────────────────────

    def _log(self, texto: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {texto}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _bombear_eventos(self) -> None:
        try:
            while True:
                tipo, dato = self.eventos.get_nowait()
                if tipo == "log":
                    self._log(dato)
                elif tipo == "estado":
                    self.var_estado.set(dato)
                elif tipo == "fin":
                    self.boton.config(state="normal", text="▶  Iniciar agente")
        except queue.Empty:
            pass
        self.raiz.after(200, self._bombear_eventos)

    def correr(self) -> None:
        self.raiz.mainloop()


def main() -> None:
    VentanaAgente().correr()


if __name__ == "__main__":
    main()
