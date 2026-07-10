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

Interfaz en Tkinter/ttk (tema 'clam' repintado): tarjetas, indicadores (KPI) y
una tabla de resultados. Funciona sin internet en cualquier PC con Python.
"""

import csv
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

# ------------------------------------------------------------------ paleta
BG = "#eaeef2"  # fondo general
CARD = "#ffffff"  # tarjetas
HEADER = "#0e4d64"  # barra institucional (verde-azul)
HEADER_2 = "#12617f"
ACCENT = "#128a5e"  # verde acción
ACCENT_HOVER = "#0f7550"
BLUE = "#0e6ba8"
INK = "#1b2a33"  # texto principal
MUTED = "#63727c"  # texto secundario
LINE = "#d6dee4"  # bordes
VERDE = "#1f9d55"
AMBAR = "#c9821a"
ROJO = "#d94a3d"

FAM = "Segoe UI"  # en Windows; en otros SO Tk cae a la fuente por defecto
F = (FAM, 10)
F_SM = (FAM, 9)
F_MINI = (FAM, 8)
F_BOLD = (FAM, 10, "bold")
F_H1 = (FAM, 16, "bold")
F_KPI = (FAM, 18, "bold")
F_KPI_RES = (FAM, 14, "bold")  # tiles de resultados (importes, más angostos)
F_KPI_LBL = (FAM, 8)

ICONO_ESTADO = {"OPERATIVA": "🟢", "POR_ARMAR": "🟡", "SIN_DATOS": "🔴"}


class Suite(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Suite Cartera HUS — Radicación · Glosas · Cruces masivos")
        self.geometry("1200x840")
        self.minsize(1060, 720)
        self.configure(bg=BG)

        self.entidades = registro.cargar_entidades()
        self.entidad_actual = None
        self.ruta_archivo = tk.StringVar(value="")
        self.cola_log = queue.Queue()
        self._ocupado = False
        self._ultima_carpeta = None

        self._estilos()
        self._construir()
        self._refrescar_lista()
        self._kpis_entidades()
        self.after(120, self._vaciar_cola_log)
        self.log("Suite Cartera HUS lista. %d entidades cargadas." % len(self.entidades))

    # ------------------------------------------------------------- estilos

    def _estilos(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=INK, font=F)
        st.configure("Card.TFrame", background=CARD)
        st.configure("Bg.TFrame", background=BG)
        st.configure("Card.TLabel", background=CARD, foreground=INK, font=F)
        st.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=F_SM)
        st.configure("H2.TLabel", background=CARD, foreground=INK, font=F_BOLD)
        st.configure("KPI.TLabel", background=CARD, foreground=HEADER, font=F_KPI)
        st.configure("KPILbl.TLabel", background=CARD, foreground=MUTED, font=F_KPI_LBL)

        # entradas
        st.configure(
            "TEntry", fieldbackground="white", bordercolor=LINE, insertcolor=INK, padding=5
        )
        # botones de acción (secundarios, claros)
        st.configure(
            "Accion.TButton",
            background="white",
            foreground=INK,
            font=F,
            borderwidth=1,
            focusthickness=0,
            padding=(10, 12),
        )
        st.map(
            "Accion.TButton",
            background=[("active", "#eef6f2")],
            bordercolor=[("active", ACCENT)],
        )
        # botón primario (verde)
        st.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="white",
            font=F_BOLD,
            borderwidth=0,
            padding=(12, 8),
        )
        st.map("Primary.TButton", background=[("active", ACCENT_HOVER)])
        # botón sutil (chip)
        st.configure(
            "Chip.TButton",
            background="#eef2f5",
            foreground=INK,
            font=F_SM,
            borderwidth=0,
            padding=(8, 5),
        )
        st.map("Chip.TButton", background=[("active", "#dde6ec")])
        # Treeview de resultados
        st.configure(
            "Res.Treeview",
            background="white",
            fieldbackground="white",
            foreground=INK,
            rowheight=24,
            borderwidth=0,
            font=F_SM,
        )
        st.configure(
            "Res.Treeview.Heading",
            background="#f0f4f7",
            foreground=MUTED,
            font=(FAM, 8, "bold"),
            relief="flat",
        )
        st.map("Res.Treeview", background=[("selected", "#d7ebe1")], foreground=[("selected", INK)])
        st.configure("TProgressbar", background=ACCENT, troughcolor=LINE, borderwidth=0)
        st.configure("Vertical.TScrollbar", background="#cdd7de", borderwidth=0, arrowsize=12)

    # ----------------------------------------------------------- utilidades UI

    def _tarjeta(self, padre, **grid):
        """Un marco blanco con borde fino (tarjeta)."""
        cont = tk.Frame(padre, bg=LINE)  # borde
        cont.grid(**grid)
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)
        card = ttk.Frame(cont, style="Card.TFrame", padding=1)
        card.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        return card

    def _titulo_tarjeta(self, card, texto, fila=0):
        lbl = ttk.Label(card, text=texto, style="H2.TLabel")
        lbl.grid(row=fila, column=0, columnspan=9, sticky="w", padx=12, pady=(10, 4))
        return lbl

    # -------------------------------------------------------------- construir

    def _construir(self):
        # ---- barra superior
        barra = tk.Frame(self, bg=HEADER, height=62)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        tk.Label(
            barra,
            text="  🏥  Suite Cartera HUS",
            bg=HEADER,
            fg="white",
            font=F_H1,
        ).pack(side="left", pady=12, padx=6)
        tk.Label(
            barra,
            text="ESE Hospital Universitario de Santander\nCartera · Auditoría de Cuentas Médicas  ",
            bg=HEADER,
            fg="#bcd7e2",
            font=F_MINI,
            justify="right",
        ).pack(side="right", pady=10)

        # ---- fila de KPIs de entidades
        self.kpis_top = tk.Frame(self, bg=BG)
        self.kpis_top.pack(fill="x", padx=12, pady=(10, 2))
        self._kpi_tiles = {}
        for i, (clave, etiqueta, color) in enumerate(
            [
                ("total", "ENTIDADES", HEADER),
                ("OPERATIVA", "🟢 OPERATIVAS", VERDE),
                ("POR_ARMAR", "🟡 POR ARMAR", AMBAR),
                ("SIN_DATOS", "🔴 SIN DATOS", ROJO),
            ]
        ):
            self.kpis_top.columnconfigure(i, weight=1)
            self._kpi_tiles[clave] = self._kpi_tile(self.kpis_top, etiqueta, color, 0, i)

        # ---- cuerpo: izquierda (entidad) / derecha (trabajo)
        cuerpo = tk.Frame(self, bg=BG)
        cuerpo.pack(fill="both", expand=True, padx=12, pady=8)
        cuerpo.columnconfigure(0, weight=0, minsize=340)
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)

        self._panel_entidad(cuerpo)
        self._panel_trabajo(cuerpo)

    def _kpi_tile(self, padre, etiqueta, color, r, c, font=F_KPI):
        borde = tk.Frame(padre, bg=LINE)
        borde.grid(row=r, column=c, sticky="ew", padx=4)
        card = tk.Frame(borde, bg=CARD)
        card.pack(fill="both", expand=True, padx=1, pady=1)
        franja = tk.Frame(card, bg=color, width=5)
        franja.pack(side="left", fill="y")
        val = tk.Label(card, text="—", bg=CARD, fg=INK, font=font, anchor="w")
        val.pack(anchor="w", padx=(12, 8), pady=(7, 0))
        tk.Label(card, text=etiqueta, bg=CARD, fg=MUTED, font=F_KPI_LBL, anchor="w").pack(
            anchor="w", padx=12, pady=(0, 7)
        )
        return val

    def _panel_entidad(self, padre):
        card = self._tarjeta(padre, row=0, column=0, sticky="nsew", padx=(0, 8))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)
        self._titulo_tarjeta(card, "1 · Entidad  (EPS / pagador)")

        self.var_busqueda = tk.StringVar()
        ent = ttk.Entry(card, textvariable=self.var_busqueda, font=F)
        ent.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 0))
        self.var_busqueda.trace_add("write", lambda *_: self._refrescar_lista())
        ttk.Label(card, text="🔎  Escriba nombre o NIT para filtrar", style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", padx=12, pady=(2, 6)
        )

        marco_lista = tk.Frame(card, bg=CARD)
        marco_lista.grid(row=3, column=0, sticky="nsew", padx=12)
        marco_lista.rowconfigure(0, weight=1)
        marco_lista.columnconfigure(0, weight=1)
        self.lista = tk.Listbox(
            marco_lista,
            font=F,
            activestyle="none",
            bg="white",
            fg=INK,
            selectbackground=ACCENT,
            selectforeground="white",
            highlightthickness=1,
            highlightbackground=LINE,
            relief="flat",
            height=10,
        )
        self.lista.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(marco_lista, command=self.lista.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.lista.configure(yscrollcommand=sb.set)
        self.lista.bind("<<ListboxSelect>>", self._al_elegir)

        # ficha
        self.ficha = tk.Text(
            card,
            height=8,
            font=F_SM,
            bg="#f7fafb",
            fg=INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            wrap="word",
            padx=10,
            pady=8,
            state="disabled",
        )
        self.ficha.grid(row=4, column=0, sticky="ew", padx=12, pady=8)

        fila = tk.Frame(card, bg=CARD)
        fila.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 12))
        ttk.Button(
            fila, text="🌐  Abrir portal", style="Chip.TButton", command=self._abrir_portal
        ).pack(side="left")
        ttk.Button(
            fila, text="📋  Copiar correo", style="Chip.TButton", command=self._copiar_correo
        ).pack(side="left", padx=6)

    def _panel_trabajo(self, padre):
        der = tk.Frame(padre, bg=BG)
        der.grid(row=0, column=1, sticky="nsew")
        der.columnconfigure(0, weight=1)
        der.rowconfigure(2, weight=1)

        # --- 2 · archivo
        card = self._tarjeta(der, row=0, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        self._titulo_tarjeta(card, "2 · Archivo base  (ZIP del portal, Excel, PDF, .cmd…)")
        fila = tk.Frame(card, bg=CARD)
        fila.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        fila.columnconfigure(0, weight=1)
        ent = ttk.Entry(fila, textvariable=self.ruta_archivo, font=F_SM, state="readonly")
        ent.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(
            fila, text="📄 Elegir archivo…", style="Chip.TButton", command=self._elegir_archivo
        ).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(
            fila, text="📁 Elegir carpeta…", style="Chip.TButton", command=self._elegir_carpeta
        ).grid(row=0, column=2)

        # --- 3 · acciones (tarjetas)
        card = self._tarjeta(der, row=1, column=0, sticky="ew", pady=8)
        for i in range(3):
            card.columnconfigure(i, weight=1, uniform="acc")
        self._titulo_tarjeta(card, "3 · Acciones")
        acciones = [
            ("📦", "Organizar masivo", "ZIP → lotes de 300", self.accion_organizar),
            ("🔗", "Consolidar + cruzar", "Pandas, sin Excel", self.accion_consolidar),
            ("📋", "Generar OBJECIONES", "formato DGH", self.accion_objeciones),
            ("🖼️", "Compilar evidencias", "pantallazos → Word", self.accion_evidencias),
            ("🤖", "Ejecutar bot", "de esta entidad", self.accion_bot),
            ("➕", "Registrar bot", "apuntar .bat/.py", self.accion_registrar_bot),
        ]
        for idx, (ic, tit, sub, cmd) in enumerate(acciones):
            self._boton_accion(card, ic, tit, sub, cmd, 1 + idx // 3, idx % 3)
        barra_inf = tk.Frame(card, bg=CARD)
        barra_inf.grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(2, 12))
        ttk.Button(
            barra_inf,
            text="📂 Abrir carpeta de SALIDAS",
            style="Chip.TButton",
            command=self._abrir_salidas,
        ).pack(side="left")
        self.progreso = ttk.Progressbar(barra_inf, mode="indeterminate", length=180)
        self.progreso.pack(side="right")
        self.lbl_estado = tk.Label(barra_inf, text="Listo", bg=CARD, fg=MUTED, font=F_SM)
        self.lbl_estado.pack(side="right", padx=10)

        # --- resultados (KPIs de proceso + tabla + consola)
        card = self._tarjeta(der, row=2, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1, minsize=170)  # la tabla siempre visible
        self._titulo_tarjeta(card, "Resultados del último proceso")

        kf = tk.Frame(card, bg=CARD)
        kf.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        self._kpi_res = {}
        for i, (clave, etq, col) in enumerate(
            [
                ("facturas", "FACTURAS", HEADER),
                ("glosado", "GLOSADO", ROJO),
                ("objetado", "OBJETADO", ACCENT),
                ("revisar", "REVISAR", AMBAR),
            ]
        ):
            kf.columnconfigure(i, weight=1)
            self._kpi_res[clave] = self._kpi_tile(kf, etq, col, 0, i, font=F_KPI_RES)

        # tabla de resultados
        marco_tabla = tk.Frame(card, bg=CARD)
        marco_tabla.grid(row=3, column=0, sticky="nsew", padx=12, pady=4)
        marco_tabla.rowconfigure(0, weight=1)
        marco_tabla.columnconfigure(0, weight=1)
        cols = ("factura", "estado", "detalle", "valor")
        self.tabla = ttk.Treeview(
            marco_tabla, columns=cols, show="headings", style="Res.Treeview", height=6
        )
        for c, txt, w, anchor in [
            ("factura", "FACTURA", 130, "w"),
            ("estado", "ESTADO", 120, "w"),
            ("detalle", "DETALLE", 260, "w"),
            ("valor", "VALOR", 120, "e"),
        ]:
            self.tabla.heading(c, text=txt)
            self.tabla.column(c, width=w, anchor=anchor)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(marco_tabla, command=self.tabla.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tabla.configure(yscrollcommand=sb.set)
        self.tabla.tag_configure("par", background="#f6f9fb")

        # consola (log técnico, colapsable visualmente)
        cf = tk.Frame(card, bg=CARD)
        cf.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 12))
        cf.columnconfigure(0, weight=1)
        self.consola = tk.Text(
            cf,
            font=("Consolas", 8),
            bg="#0f1a20",
            fg="#cfe0e8",
            height=4,
            relief="flat",
            wrap="word",
            state="disabled",
        )
        self.consola.grid(row=0, column=0, sticky="ew")
        sb = ttk.Scrollbar(cf, command=self.consola.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.consola.configure(yscrollcommand=sb.set)

    def _boton_accion(self, card, icono, titulo, sub, cmd, r, c):
        borde = tk.Frame(card, bg=LINE, cursor="hand2")
        borde.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
        inner = tk.Frame(borde, bg="white")
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(inner, text=icono, bg="white", font=(FAM, 20)).pack(pady=(9, 0))
        tk.Label(
            inner,
            text=titulo,
            bg="white",
            fg=INK,
            font=(FAM, 9, "bold"),
            wraplength=150,
            justify="center",
        ).pack()
        tk.Label(inner, text=sub, bg="white", fg=MUTED, font=F_MINI).pack(pady=(0, 9))

        def _hover(_e, on):
            col = "#eef6f2" if on else "white"
            inner.configure(bg=col)
            for w in inner.winfo_children():
                w.configure(bg=col)
            borde.configure(bg=ACCENT if on else LINE)

        for w in (borde, inner, *inner.winfo_children()):
            w.bind("<Button-1>", lambda _e: cmd())
            w.bind("<Enter>", lambda e: _hover(e, True))
            w.bind("<Leave>", lambda e: _hover(e, False))

    # -------------------------------------------------------------- KPIs

    def _kpis_entidades(self):
        c = registro.resumen_estados(self.entidades)
        self._kpi_tiles["total"].configure(text=str(len(self.entidades)))
        for k in ("OPERATIVA", "POR_ARMAR", "SIN_DATOS"):
            self._kpi_tiles[k].configure(text=str(c.get(k, 0)))

    def _fmt_pesos(self, v):
        try:
            return "$ " + "{:,.0f}".format(float(v)).replace(",", ".")
        except (ValueError, TypeError):
            return "$ 0"

    def _fmt_pesos_compacto(self, v):
        """Importe corto para las fichas KPI: '$ 48,3 M', '$ 320 K', '$ 900'."""
        try:
            v = float(v)
        except (ValueError, TypeError):
            return "$ 0"
        a = abs(v)
        if a >= 1_000_000:
            return ("$ %.1f M" % (v / 1_000_000)).replace(".", ",")
        if a >= 1_000:
            return "$ %.0f K" % (v / 1_000)
        return "$ %.0f" % v

    # ------------------------------------------------------------- entidad

    def _refrescar_lista(self):
        filtradas = registro.buscar(self.entidades, self.var_busqueda.get())
        self._visibles = filtradas
        self.lista.delete(0, "end")
        for e in filtradas:
            self.lista.insert(
                "end",
                "  %s  %s" % (ICONO_ESTADO.get(e.get("estado_radicacion"), "⚪"), e["nombre"][:52]),
            )

    def _al_elegir(self, _e=None):
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
            lineas.append("  Nota: %s" % glo["observaciones"][:160])
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
                "Esta entidad no tiene link de plataforma registrado.\nRadicación por: %s"
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
            self.log("Archivo: %s  →  tipo real: %s" % (os.path.basename(ruta), tipo.upper()))
            if os.path.splitext(ruta)[1].lower() == ".cmd" and tipo == "pdf":
                self.log("  (PDF renombrado como .cmd: se procesa como PDF.)")

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
        self.lbl_estado.configure(text="Procesando: %s…" % nombre, fg=BLUE)
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
                    self.lbl_estado.configure(text="Listo", fg=MUTED)
                elif isinstance(item, tuple) and item[0] == "__RESULTADOS__":
                    self._cargar_resultados(item[1])
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

    def _senal_resultados(self, carpeta):
        self._ultima_carpeta = carpeta
        self.cola_log.put(("__RESULTADOS__", carpeta))

    def _cargar_resultados(self, carpeta):
        """Lee CONTROL.csv del proceso y llena la tabla + los KPIs."""
        self.tabla.delete(*self.tabla.get_children())
        ruta = os.path.join(carpeta, "CONTROL.csv")
        filas = []
        if os.path.exists(ruta):
            try:
                with open(ruta, encoding="utf-8-sig", newline="") as f:
                    filas = list(csv.DictReader(f, delimiter=";"))
            except OSError:
                filas = []
        total_valor = 0.0
        for i, fila in enumerate(filas):
            valor = cruces_dgh.a_numero(fila.get("valor", 0))
            total_valor += valor
            self.tabla.insert(
                "",
                "end",
                values=(
                    fila.get("factura", ""),
                    fila.get("estado", ""),
                    (fila.get("detalle", "") or "")[:60],
                    self._fmt_pesos(valor),
                ),
                tags=("par",) if i % 2 else (),
            )
        facturas = len({f.get("factura", "") for f in filas})
        self._kpi_res["facturas"].configure(text=str(facturas))
        self._kpi_res["objetado"].configure(text=self._fmt_pesos_compacto(total_valor))

        # glosado y a-revisar salen de otros artefactos, si existen
        glosado = self._suma_columna_consolidado(carpeta)
        self._kpi_res["glosado"].configure(
            text=self._fmt_pesos_compacto(glosado) if glosado else "—"
        )
        revisar = self._contar_revisar(carpeta)
        self._kpi_res["revisar"].configure(text=str(revisar))
        self.log("Resultados cargados en la tabla: %d filas." % len(filas))

    def _suma_columna_consolidado(self, carpeta):
        ruta = os.path.join(carpeta, "CONSOLIDADO_GLOSAS.xlsx")
        if not os.path.exists(ruta):
            return 0.0
        try:
            import pandas as pd

            df = pd.read_excel(ruta)
            if "valor_glosado" in df.columns:
                return float(df["valor_glosado"].map(cruces_dgh.a_numero).sum())
        except Exception:
            return 0.0
        return 0.0

    def _contar_revisar(self, carpeta):
        ruta = os.path.join(carpeta, "REVISAR.csv")
        if not os.path.exists(ruta):
            return 0
        try:
            with open(ruta, encoding="utf-8-sig", newline="") as f:
                return max(0, sum(1 for _ in f) - 1)
        except OSError:
            return 0

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
                "%(facturas)d facturas en %(lotes)d lotes · %(sin_clasificar)d sin clasificar · "
                "%(incompletas)d incompletas" % resumen,
            )
            rep.cerrar()
            self._senal_resultados(rep.carpeta)

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
            self._ultimo_consolidado = salida
            self.log("→ Este consolidado queda listo para 'Generar OBJECIONES'.")
            self._senal_resultados(rep.carpeta)

        self._correr("Consolidar + cruzar", tarea)

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
                "Recuerde validar el PRIMER cargue contra DGH y ajustar config/mapeo_dgh.json "
                "si algún encabezado difiere."
            )
            self._senal_resultados(rep.carpeta)

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
            self._senal_resultados(rep.carpeta)

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
                "Esta entidad no tiene bots registrados.\nUse '➕ Registrar bot' para apuntar al "
                ".bat/.py actual.",
            )
            return
        ventana = tk.Toplevel(self)
        ventana.title("Bots de %s" % nombre[:40])
        ventana.configure(bg=BG)
        ventana.geometry("460x%d" % (90 + 46 * len(bots)))
        tk.Label(ventana, text="Elija el bot a ejecutar:", bg=BG, fg=INK, font=F_BOLD).pack(pady=10)
        for b in bots:
            tk.Button(
                ventana,
                text="🤖  %s" % b["nombre"],
                font=F,
                bg="white",
                fg=INK,
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
        carpeta = self._ultima_carpeta or CARPETA_SALIDAS
        os.makedirs(carpeta, exist_ok=True)
        if os.name == "nt":
            os.startfile(carpeta)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", carpeta])
        else:
            subprocess.Popen(["xdg-open", carpeta])


def main():
    faltantes = []
    try:
        import openpyxl  # noqa: F401
        import pandas  # noqa: F401
    except ImportError:
        faltantes.append("pandas / openpyxl (cruces y OBJECIONES)")
    try:
        import docx  # noqa: F401
    except ImportError:
        faltantes.append("python-docx (Word de evidencias)")

    app = Suite()
    if faltantes:
        app.log("[!] Componentes opcionales sin instalar: " + "; ".join(faltantes))
        app.log("    Ejecute INICIAR_SUITE.bat con internet una vez.")
    app.mainloop()


if __name__ == "__main__":
    main()
