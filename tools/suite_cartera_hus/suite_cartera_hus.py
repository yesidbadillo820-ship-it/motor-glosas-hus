"""
SUITE CARTERA HUS — Menú único de radicación, glosas y cruces masivos.
ESE Hospital Universitario de Santander · Cartera / Auditoría de Cuentas Médicas

Un solo programa para el analista:
  1. Elegir la EPS en el menú (con buscador) y ver su ficha de radicación.
  2. Cargar el archivo base (ZIP del portal, Excel, PDF renombrado .cmd…).
  3. Ejecutar la acción: organizar masivo, consolidar + cruzar con DGH,
     generar OBJECIONES, compilar evidencias o lanzar el bot ya existente
     de esa entidad.
Toda salida queda en SALIDAS/<ENTIDAD>/<fecha>_<proceso>/ con el estándar
CONTROL.csv + EVIDENCIAS.docx + REVISAR.csv + RESUMEN.txt.

Interfaz en Tkinter puro (funciona sin internet en cualquier PC con Python).
Si `customtkinter` está instalado, se usa automáticamente un tema moderno.
"""

import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from nucleo import archivos, cruces_dgh, registro, reportes  # noqa: E402

CARPETA_SALIDAS = os.path.join(BASE, "SALIDAS")

# --------------------------------------------------------------- apariencia
COLOR_FONDO = "#f4f6f8"
COLOR_BARRA = "#0e4d64"  # verde-azul institucional
COLOR_ACENTO = "#128a5e"
COLOR_TEXTO_BARRA = "#ffffff"
FUENTE = ("Segoe UI", 10)
FUENTE_TITULO = ("Segoe UI", 15, "bold")


class Suite(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Suite Cartera HUS — Radicación · Glosas · Cruces masivos")
        self.geometry("1080x680")
        self.minsize(940, 600)
        self.configure(bg=COLOR_FONDO)

        self.entidades = registro.cargar_entidades()
        self.entidad_actual = None
        self.ruta_archivo = tk.StringVar(value="")
        self.cola_log = queue.Queue()
        self._ocupado = False

        self._construir()
        self._refrescar_lista()
        self.after(120, self._vaciar_cola_log)
        self.log("Suite Cartera HUS lista. Entidades cargadas: %d." % len(self.entidades))
        conteo = registro.resumen_estados(self.entidades)
        self.log(
            "  🟢 Operativas: %d   🟡 Por armar: %d   🔴 Sin datos: %d"
            % (conteo.get("OPERATIVA", 0), conteo.get("POR_ARMAR", 0), conteo.get("SIN_DATOS", 0))
        )

    # ------------------------------------------------------------ interfaz

    def _construir(self):
        barra = tk.Frame(self, bg=COLOR_BARRA, height=56)
        barra.pack(fill="x")
        tk.Label(
            barra,
            text="  Suite Cartera HUS",
            bg=COLOR_BARRA,
            fg=COLOR_TEXTO_BARRA,
            font=FUENTE_TITULO,
        ).pack(side="left", pady=10)
        tk.Label(
            barra,
            text="ESE Hospital Universitario de Santander · "
            "Cartera / Auditoría de Cuentas Médicas  ",
            bg=COLOR_BARRA,
            fg="#cfe3ec",
            font=("Segoe UI", 9),
        ).pack(side="right")

        cuerpo = tk.Frame(self, bg=COLOR_FONDO)
        cuerpo.pack(fill="both", expand=True, padx=10, pady=8)
        cuerpo.columnconfigure(0, weight=2, uniform="c")
        cuerpo.columnconfigure(1, weight=3, uniform="c")
        cuerpo.rowconfigure(0, weight=1)

        # ---------- panel izquierdo: entidad
        izq = tk.LabelFrame(
            cuerpo, text=" 1 · Entidad (EPS / pagador) ", bg=COLOR_FONDO, font=FUENTE
        )
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        izq.columnconfigure(0, weight=1)

        self.var_busqueda = tk.StringVar()
        buscador = tk.Entry(izq, textvariable=self.var_busqueda, font=FUENTE)
        buscador.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        buscador.insert(0, "")
        self.var_busqueda.trace_add("write", lambda *_: self._refrescar_lista())
        tk.Label(
            izq,
            text="Escriba nombre o NIT para filtrar",
            bg=COLOR_FONDO,
            fg="#666",
            font=("Segoe UI", 8),
        ).grid(row=1, column=0, sticky="w", padx=10)

        self.lista = tk.Listbox(
            izq,
            font=FUENTE,
            activestyle="none",
            selectbackground=COLOR_ACENTO,
            selectforeground="white",
            height=12,
        )
        self.lista.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        izq.rowconfigure(2, weight=1)
        self.lista.bind("<<ListboxSelect>>", self._al_elegir)

        self.ficha = tk.Text(
            izq,
            height=9,
            font=("Segoe UI", 9),
            bg="#ffffff",
            relief="solid",
            bd=1,
            wrap="word",
            state="disabled",
        )
        self.ficha.grid(row=3, column=0, sticky="ew", padx=8, pady=(2, 4))

        fila_btn = tk.Frame(izq, bg=COLOR_FONDO)
        fila_btn.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(fila_btn, text="🌐 Abrir portal", command=self._abrir_portal).pack(side="left")
        ttk.Button(fila_btn, text="📋 Copiar correo", command=self._copiar_correo).pack(
            side="left", padx=6
        )

        # ---------- panel derecho: archivo + acciones
        der = tk.Frame(cuerpo, bg=COLOR_FONDO)
        der.grid(row=0, column=1, sticky="nsew")
        der.columnconfigure(0, weight=1)
        der.rowconfigure(2, weight=1)

        arch = tk.LabelFrame(
            der, text=" 2 · Archivo base (ZIP, Excel, PDF, .cmd…) ", bg=COLOR_FONDO, font=FUENTE
        )
        arch.grid(row=0, column=0, sticky="ew")
        arch.columnconfigure(0, weight=1)
        tk.Entry(arch, textvariable=self.ruta_archivo, font=("Segoe UI", 9), state="readonly").grid(
            row=0, column=0, sticky="ew", padx=8, pady=8
        )
        ttk.Button(arch, text="Elegir archivo…", command=self._elegir_archivo).grid(
            row=0, column=1, padx=(0, 4)
        )
        ttk.Button(arch, text="Elegir carpeta…", command=self._elegir_carpeta).grid(
            row=0, column=2, padx=(0, 8)
        )

        acc = tk.LabelFrame(der, text=" 3 · Acciones ", bg=COLOR_FONDO, font=FUENTE)
        acc.grid(row=1, column=0, sticky="ew", pady=6)
        for i in range(3):
            acc.columnconfigure(i, weight=1)

        botones = [
            ("📦 Organizar masivo\n(ZIP → lotes de 300)", self.accion_organizar),
            ("🔗 Consolidar + cruzar\n(Pandas, sin Excel)", self.accion_consolidar),
            ("📋 Generar OBJECIONES\n(formato DGH)", self.accion_objeciones),
            ("🖼️ Compilar evidencias\n(pantallazos → Word)", self.accion_evidencias),
            ("🤖 Ejecutar bot\nde esta entidad", self.accion_bot),
            ("➕ Registrar bot\nexistente", self.accion_registrar_bot),
        ]
        for i, (texto, comando) in enumerate(botones):
            b = tk.Button(
                acc,
                text=texto,
                command=comando,
                font=FUENTE,
                bg="white",
                relief="groove",
                bd=1,
                height=2,
                cursor="hand2",
                justify="center",
            )
            b.grid(row=i // 3, column=i % 3, sticky="ew", padx=6, pady=5)

        fila2 = tk.Frame(acc, bg=COLOR_FONDO)
        fila2.grid(row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(fila2, text="📂 Abrir carpeta de SALIDAS", command=self._abrir_salidas).pack(
            side="left"
        )
        self.progreso = ttk.Progressbar(fila2, mode="indeterminate", length=180)
        self.progreso.pack(side="right")

        consola_marco = tk.LabelFrame(
            der, text=" Registro del proceso ", bg=COLOR_FONDO, font=FUENTE
        )
        consola_marco.grid(row=2, column=0, sticky="nsew")
        consola_marco.columnconfigure(0, weight=1)
        consola_marco.rowconfigure(0, weight=1)
        self.consola = tk.Text(
            consola_marco,
            font=("Consolas", 9),
            bg="#101820",
            fg="#d7e3ea",
            state="disabled",
            wrap="word",
        )
        self.consola.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        scroll = ttk.Scrollbar(consola_marco, command=self.consola.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.consola.configure(yscrollcommand=scroll.set)

    # -------------------------------------------------------------- entidad

    def _refrescar_lista(self):
        filtradas = registro.buscar(self.entidades, self.var_busqueda.get())
        self._visibles = filtradas
        self.lista.delete(0, "end")
        icono = {"OPERATIVA": "🟢", "POR_ARMAR": "🟡", "SIN_DATOS": "🔴"}
        for e in filtradas:
            self.lista.insert(
                "end", " %s %s" % (icono.get(e.get("estado_radicacion"), "⚪"), e["nombre"][:58])
            )

    def _al_elegir(self, _evento=None):
        sel = self.lista.curselection()
        if not sel:
            return
        self.entidad_actual = self._visibles[sel[0]]
        e = self.entidad_actual
        rad = e.get("radicacion", {})
        glo = e.get("glosas", {})
        lineas = [
            "%s   ·   NIT %s" % (e["nombre"], e.get("nit", "s/d")),
            "Estado: %s" % registro.ETIQUETA_ESTADO.get(e.get("estado_radicacion"), "s/d"),
            "",
            "RADICACIÓN → %s" % (rad.get("link") or "solo correo / por armar"),
            "  Usuario: %s" % (rad.get("usuario") or "—"),
            "  Correo: %s" % (rad.get("correo") or "—"),
            "  Contacto: %s %s"
            % (rad.get("contacto") or "—", ("(" + rad["cargo"] + ")") if rad.get("cargo") else ""),
            "GLOSAS → %s" % (glo.get("medio") or "—"),
        ]
        if glo.get("observaciones"):
            lineas.append("  Nota: %s" % glo["observaciones"][:180])
        bots = registro.bots_de(e["nombre"].split()[0]) or registro.bots_de(e["nombre"])
        if bots:
            lineas.append("Bots registrados: %d" % len(bots))
        self.ficha.configure(state="normal")
        self.ficha.delete("1.0", "end")
        self.ficha.insert("1.0", "\n".join(lineas))
        self.ficha.configure(state="disabled")

    def _exigir_entidad(self):
        if not self.entidad_actual:
            messagebox.showwarning(
                "Falta la entidad", "Primero elija la EPS en la lista de la izquierda."
            )
            return False
        return True

    def _abrir_portal(self):
        if not self._exigir_entidad():
            return
        link = self.entidad_actual.get("radicacion", {}).get("link", "")
        if link.lower().startswith("http"):
            webbrowser.open(link)
            self.log("Portal abierto: %s" % link[:90])
        else:
            messagebox.showinfo(
                "Sin portal",
                "Esta entidad no tiene link de plataforma registrado.\n"
                "Radicación por: %s"
                % (self.entidad_actual.get("radicacion", {}).get("correo") or "sin datos"),
            )

    def _copiar_correo(self):
        if not self._exigir_entidad():
            return
        correo = self.entidad_actual.get("radicacion", {}).get("correo", "")
        if correo:
            self.clipboard_clear()
            self.clipboard_append(correo)
            self.log("Correo copiado al portapapeles: %s" % correo[:90])
        else:
            messagebox.showinfo("Sin correo", "Esta entidad no tiene correo registrado.")

    # -------------------------------------------------------------- archivo

    def _elegir_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Elegir archivo base",
            filetypes=[
                ("Todos los archivos", "*.*"),
                ("ZIP", "*.zip"),
                ("Excel", "*.xlsx;*.xls"),
                ("PDF / CMD", "*.pdf;*.cmd"),
                ("CSV", "*.csv"),
            ],
        )
        if ruta:
            self.ruta_archivo.set(ruta)
            tipo = archivos.tipo_real(ruta)
            self.log(
                "Archivo cargado: %s  →  tipo real detectado: %s"
                % (os.path.basename(ruta), tipo.upper())
            )
            if os.path.splitext(ruta)[1].lower() == ".cmd" and tipo == "pdf":
                self.log("  (Es un PDF renombrado como .cmd: se procesa como PDF.)")

    def _elegir_carpeta(self):
        ruta = filedialog.askdirectory(title="Elegir carpeta base")
        if ruta:
            self.ruta_archivo.set(ruta)
            self.log("Carpeta cargada: %s" % ruta)

    def _exigir_archivo(self, tipos=None):
        ruta = self.ruta_archivo.get()
        if not ruta or not os.path.exists(ruta):
            messagebox.showwarning(
                "Falta el archivo", "Cargue primero el archivo o carpeta base (paso 2)."
            )
            return None
        if tipos and not os.path.isdir(ruta):
            real = archivos.tipo_real(ruta)
            if real not in tipos:
                messagebox.showwarning(
                    "Tipo de archivo",
                    "Esta acción espera: %s.\nEl archivo cargado es: %s."
                    % (", ".join(tipos).upper(), real.upper()),
                )
                return None
        return ruta

    # ---------------------------------------------------- ejecución en hilo

    def _correr(self, nombre, funcion):
        if self._ocupado:
            messagebox.showinfo("En proceso", "Espere a que termine la tarea actual.")
            return
        self._ocupado = True
        self.progreso.start(12)
        self.log("")
        self.log("══════ %s ══════" % nombre.upper())

        def envoltura():
            try:
                funcion()
                self.cola_log.put("✔ %s: terminado." % nombre)
            except Exception as e:
                self.cola_log.put("✖ ERROR en %s: %s" % (nombre, e))
                self.cola_log.put(traceback.format_exc(limit=3))
            finally:
                self.cola_log.put(("__FIN__",))

        threading.Thread(target=envoltura, daemon=True).start()

    def _vaciar_cola_log(self):
        try:
            while True:
                item = self.cola_log.get_nowait()
                if isinstance(item, tuple) and item[0] == "__FIN__":
                    self._ocupado = False
                    self.progreso.stop()
                else:
                    self._escribir(item)
        except queue.Empty:
            pass
        self.after(120, self._vaciar_cola_log)

    def log(self, texto):
        self.cola_log.put(texto)

    def _escribir(self, texto):
        self.consola.configure(state="normal")
        self.consola.insert("end", str(texto) + "\n")
        self.consola.see("end")
        self.consola.configure(state="disabled")

    # -------------------------------------------------------------- acciones

    def accion_organizar(self):
        if not self._exigir_entidad():
            return
        ruta = (
            self._exigir_archivo(tipos=("zip",))
            if not os.path.isdir(self.ruta_archivo.get())
            else self.ruta_archivo.get()
        )
        if not ruta:
            return
        entidad = self.entidad_actual

        def tarea():
            rep = reportes.ReporteEstandar(
                entidad["nombre"], "organizar_masivo", base=CARPETA_SALIDAS, log=self.log
            )
            resumen = cruces_dgh.organizar_cargue(ruta, rep.carpeta, log=self.log)
            rep.registrar(
                "(masivo)",
                "ORGANIZADO",
                "%(facturas)d facturas en %(lotes)d lotes · "
                "%(sin_clasificar)d sin clasificar · "
                "%(incompletas)d incompletas" % resumen,
            )
            rep.cerrar()

        self._correr("Organizar masivo", tarea)

    def accion_consolidar(self):
        if not self._exigir_entidad():
            return
        ruta = self.ruta_archivo.get()
        if not ruta or not os.path.exists(ruta):
            messagebox.showwarning(
                "Falta la carpeta",
                "Cargue la carpeta ya organizada (o el ZIP del portal) en el paso 2.",
            )
            return
        base_dgh = filedialog.askopenfilename(
            title="(Opcional) Base DGH 'Servicios Facturados' — Cancelar para omitir",
            filetypes=[("Excel/CSV", "*.xlsx;*.xls;*.csv"), ("Todos", "*.*")],
        )
        entidad = self.entidad_actual

        def tarea():
            origen = ruta
            rep = reportes.ReporteEstandar(
                entidad["nombre"], "consolidar_cruce", base=CARPETA_SALIDAS, log=self.log
            )
            if not os.path.isdir(origen):
                self.log("La entrada es un archivo: se extrae primero…")
                origen = os.path.join(rep.carpeta, "_EXTRACCION")
                archivos.extraer_zip_recursivo(ruta, origen, log=self.log)
            consolidado, _ = cruces_dgh.consolidar(origen, log=self.log)
            if base_dgh:
                consolidado = cruces_dgh.cruzar_con_base(consolidado, base_dgh, log=self.log)
            salida = os.path.join(rep.carpeta, "CONSOLIDADO_GLOSAS.xlsx")
            consolidado.to_excel(salida, index=False)
            self.log("Consolidado guardado: %s" % salida)
            for fac, grupo in consolidado.groupby("factura"):
                rep.registrar(
                    fac,
                    "CONSOLIDADA",
                    "%d servicios glosados" % len(grupo),
                    round(float(grupo["valor_glosado"].sum()), 2),
                    "CONSOLIDADO_GLOSAS.xlsx",
                )
            rep.cerrar()
            self._guardar_consolidado(salida)

        self._correr("Consolidar + cruzar", tarea)

    def _guardar_consolidado(self, ruta):
        self._ultimo_consolidado = ruta
        self.log("→ Este consolidado queda listo para 'Generar OBJECIONES'.")

    def accion_objeciones(self):
        if not self._exigir_entidad():
            return
        sugerido = getattr(self, "_ultimo_consolidado", "")
        ruta = self.ruta_archivo.get()
        if (
            sugerido
            and os.path.exists(sugerido)
            and messagebox.askyesno(
                "Consolidado",
                "¿Usar el consolidado recién generado?\n%s" % os.path.basename(sugerido),
            )
        ):
            ruta = sugerido
        elif not ruta or not os.path.exists(ruta) or os.path.isdir(ruta):
            ruta = filedialog.askopenfilename(
                title="Elegir el CONSOLIDADO_GLOSAS.xlsx",
                filetypes=[("Excel", "*.xlsx;*.xls"), ("Todos", "*.*")],
            )
        if not ruta:
            return
        ya_objetadas = filedialog.askopenfilename(
            title="(Opcional) Lista de facturas YA objetadas (una por fila) — Cancelar para omitir",
            filetypes=[("Excel/CSV/TXT", "*.xlsx;*.xls;*.csv;*.txt"), ("Todos", "*.*")],
        )
        entidad = self.entidad_actual

        def tarea():
            import pandas as pd

            rep = reportes.ReporteEstandar(
                entidad["nombre"], "objeciones_dgh", base=CARPETA_SALIDAS, log=self.log
            )
            consolidado = pd.read_excel(ruta, dtype={"factura": str})
            excluir = set()
            if ya_objetadas:
                lista = cruces_dgh.leer_tabla(ya_objetadas, log=self.log)
                excluir = set(lista.iloc[:, 0].dropna().astype(str).str.strip())
                self.log("Facturas a excluir por ya objetadas: %d" % len(excluir))
            cruces_dgh.generar_objeciones(
                consolidado,
                rep.carpeta,
                entidad=entidad,
                facturas_ya_objetadas=excluir,
                reporte=rep,
                log=self.log,
            )
            rep.cerrar()
            self.log(
                "Recuerde validar el PRIMER cargue contra DGH y ajustar "
                "config/mapeo_dgh.json si algún encabezado difiere."
            )

        self._correr("Generar OBJECIONES DGH", tarea)

    def accion_evidencias(self):
        if not self._exigir_entidad():
            return
        carpeta = filedialog.askdirectory(title="Carpeta con los pantallazos (PNG/JPG)")
        if not carpeta:
            return
        entidad = self.entidad_actual

        def tarea():
            rep = reportes.ReporteEstandar(
                entidad["nombre"], "evidencias", base=CARPETA_SALIDAS, log=self.log
            )
            ruta = rep.compilar_evidencias_word(carpeta)
            if ruta:
                rep.registrar("(lote)", "COMPILADO", os.path.basename(ruta), "", ruta)
            rep.cerrar()

        self._correr("Compilar evidencias", tarea)

    def accion_bot(self):
        if not self._exigir_entidad():
            return
        nombre = self.entidad_actual["nombre"]
        bots = registro.bots_de(nombre) or registro.bots_de(nombre.split()[0])
        if not bots:
            for clave in registro.cargar_bots():
                if clave != "_LEAME" and clave.upper() in nombre.upper():
                    bots = registro.bots_de(clave)
                    break
        if not bots:
            messagebox.showinfo(
                "Sin bots",
                "Esta entidad no tiene bots registrados.\n"
                "Use '➕ Registrar bot existente' para apuntar al .bat/.py "
                "actual.",
            )
            return
        ventana = tk.Toplevel(self)
        ventana.title("Bots de %s" % nombre[:40])
        ventana.configure(bg=COLOR_FONDO)
        ventana.geometry("460x%d" % (90 + 46 * len(bots)))
        tk.Label(ventana, text="Elija el bot a ejecutar:", bg=COLOR_FONDO, font=FUENTE).pack(pady=8)
        for b in bots:
            tk.Button(
                ventana,
                text="🤖 %s" % b["nombre"],
                font=FUENTE,
                bg="white",
                relief="groove",
                cursor="hand2",
                command=lambda r=b["ruta"], v=ventana: (
                    v.destroy(),
                    registro.ejecutar_bot(r, log=self.log),
                ),
            ).pack(fill="x", padx=16, pady=4)

    def accion_registrar_bot(self):
        if not self._exigir_entidad():
            return
        ruta = filedialog.askopenfilename(
            title="Elegir el .bat / .py / .exe del bot existente",
            filetypes=[("Ejecutables", "*.bat;*.cmd;*.py;*.ps1;*.exe"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        nombre_bot = os.path.splitext(os.path.basename(ruta))[0]
        registro.registrar_bot(self.entidad_actual["nombre"], nombre_bot, ruta)
        self.log(
            "Bot registrado para %s: %s → %s"
            % (self.entidad_actual["nombre"][:40], nombre_bot, ruta)
        )
        messagebox.showinfo("Registrado", "El bot quedó disponible en '🤖 Ejecutar bot'.")

    def _abrir_salidas(self):
        os.makedirs(CARPETA_SALIDAS, exist_ok=True)
        if os.name == "nt":
            os.startfile(CARPETA_SALIDAS)
        else:
            subprocess.Popen(["xdg-open", CARPETA_SALIDAS])


def main():
    faltantes = []
    try:
        import pandas  # noqa: F401
        import openpyxl  # noqa: F401
    except ImportError:
        faltantes.append("pandas / openpyxl (cruces y OBJECIONES)")
    try:
        import docx  # noqa: F401
    except ImportError:
        faltantes.append("python-docx (Word de evidencias)")

    app = Suite()
    if faltantes:
        app.log("[!] Componentes opcionales sin instalar: " + "; ".join(faltantes))
        app.log(
            "    Ejecute INICIAR_SUITE.bat con internet una vez, o: "
            "pip install pandas openpyxl python-docx"
        )
    app.mainloop()


if __name__ == "__main__":
    main()
