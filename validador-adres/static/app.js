/* Validador ADRES — frontend interactivo (sin dependencias) */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const estado = {
  archivos: [],
  trabajoId: sessionStorage.getItem("trabajoId") || null,
  facturas: [],
  hallazgos: null, // globales (perezoso)
  filtroEstado: "",
  busqueda: "",
  orden: { campo: "factura", asc: true },
  filtroSev: "",
  filtroOrigen: "",
  busquedaHallazgo: "",
  listaVisible: [], // facturas tras filtro (para navegación ant/sig)
};

const fmtPesos = (n) => (n == null ? "—" : "$" + Math.round(n).toLocaleString("es-CO"));
const CLASE_ESTADO = { "CON ERRORES": "err", REVISAR: "adv", CUMPLE: "ok" };
const CLASE_SEV = { ERROR: "err", ADVERTENCIA: "adv", INFO: "info", OK: "ok" };
const ICONO_SEV = { ERROR: "i-err", ADVERTENCIA: "i-adv", INFO: "i-doc", OK: "i-ok" };

function esc(t) {
  const d = document.createElement("div");
  d.textContent = t == null ? "" : String(t);
  return d.innerHTML;
}
const icono = (id, tam = 14) =>
  `<svg class="ic" width="${tam}" height="${tam}"><use href="#${id}"/></svg>`;

function toast(msj, tipo = "") {
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.textContent = msj;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

/* ── Tema claro/oscuro ─────────────────────────────────────────────────── */
function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  localStorage.setItem("tema", tema);
  $("#btn-tema use").setAttribute("href", tema === "oscuro" ? "#i-sol" : "#i-luna");
}
aplicarTema(localStorage.getItem("tema") || "claro");
$("#btn-tema").addEventListener("click", () =>
  aplicarTema(document.documentElement.dataset.tema === "oscuro" ? "claro" : "oscuro")
);

/* ── Selección de archivos ─────────────────────────────────────────────── */
const zona = $("#zona-drop");
const inputArchivos = $("#input-archivos");
zona.addEventListener("click", () => inputArchivos.click());
zona.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputArchivos.click(); }
});
["dragover", "dragenter"].forEach((ev) =>
  zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("encima"); })
);
["dragleave", "drop"].forEach((ev) =>
  zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("encima"); })
);
zona.addEventListener("drop", (e) => agregarArchivos(e.dataTransfer.files));
inputArchivos.addEventListener("change", () => {
  agregarArchivos(inputArchivos.files);
  inputArchivos.value = "";
});

function agregarArchivos(lista) {
  let rechazados = 0;
  for (const f of lista) {
    const ext = f.name.toLowerCase().split(".").pop();
    if (!["txt", "zip"].includes(ext)) { rechazados++; continue; }
    if (estado.archivos.some((x) => x.name === f.name && x.size === f.size)) continue;
    estado.archivos.push(f);
  }
  if (rechazados) toast(`${rechazados} archivo(s) ignorados (solo .txt y .zip)`, "err");
  pintarListaArchivos();
}

function pintarListaArchivos() {
  $("#lista-archivos").innerHTML = estado.archivos
    .map(
      (f, i) => `<li>
        <span>${icono("i-doc")} ${esc(f.name)} <small>(${(f.size / 1048576).toFixed(1)} MB)</small></span>
        <button class="quitar" data-i="${i}" aria-label="Quitar ${esc(f.name)}">✕</button>
      </li>`
    )
    .join("");
  $$("#lista-archivos .quitar").forEach((b) =>
    b.addEventListener("click", () => {
      estado.archivos.splice(Number(b.dataset.i), 1);
      pintarListaArchivos();
    })
  );
  $("#btn-validar").disabled = estado.archivos.length === 0;
}

/* ── Subida y progreso ─────────────────────────────────────────────────── */
$("#btn-validar").addEventListener("click", async () => {
  $("#error-carga").classList.add("oculto");
  $("#panel-carga").classList.add("oculto");
  $("#panel-progreso").classList.remove("oculto");
  ponerProgreso(3, "Subiendo archivos al servidor…");

  const fd = new FormData();
  estado.archivos.forEach((f) => fd.append("archivos", f));
  try {
    const r = await fetch(`/api/validar?sin_pdf=${$("#chk-sin-pdf").checked}`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error((await r.json()).detail || `Error ${r.status}`);
    const { id } = await r.json();
    estado.trabajoId = id;
    sessionStorage.setItem("trabajoId", id);
    sondear();
  } catch (e) {
    mostrarErrorCarga(e.message);
  }
});

function ponerProgreso(pct, msj) {
  $("#barra-relleno").style.width = pct + "%";
  $("#progreso-pct").textContent = Math.round(pct) + "%";
  if (msj) $("#progreso-texto").textContent = msj;
}

function anotarLog(msj) {
  const log = $("#progreso-log");
  const linea = document.createElement("div");
  linea.textContent = "· " + msj;
  log.prepend(linea);
  while (log.children.length > 8) log.lastChild.remove();
}

function mostrarErrorCarga(msj) {
  sessionStorage.removeItem("trabajoId");
  $("#panel-progreso").classList.add("oculto");
  $("#panel-carga").classList.remove("oculto");
  const err = $("#error-carga");
  err.textContent = "No se pudo validar: " + msj;
  err.classList.remove("oculto");
  toast("La validación falló", "err");
}

let ultimoMensaje = "";
async function sondear() {
  try {
    const r = await fetch(`/api/validaciones/${estado.trabajoId}/estado`);
    if (!r.ok) throw new Error("estado " + r.status);
    const d = await r.json();
    if (d.estado === "ERROR") return mostrarErrorCarga(d.mensaje);
    const pct = d.total ? Math.max(5, (d.progreso / d.total) * 100) : 5;
    ponerProgreso(pct, d.mensaje || "Procesando…");
    if (d.mensaje && d.mensaje !== ultimoMensaje) {
      ultimoMensaje = d.mensaje;
      anotarLog(d.mensaje);
    }
    if (d.estado === "LISTO") return cargarResultados();
    setTimeout(sondear, 650);
  } catch (e) {
    mostrarErrorCarga(e.message);
  }
}

/* ── Resultados ────────────────────────────────────────────────────────── */
async function cargarResultados() {
  const r = await fetch(`/api/validaciones/${estado.trabajoId}`);
  if (!r.ok || r.status === 202) return mostrarErrorCarga("resultado no disponible");
  const d = await r.json();
  estado.facturas = d.facturas;

  $("#panel-carga").classList.add("oculto");
  $("#panel-progreso").classList.add("oculto");
  $("#panel-resultados").classList.remove("oculto");
  $("#btn-nueva").classList.remove("oculto");
  const btnExcel = $("#btn-excel");
  btnExcel.href = `/api/validaciones/${estado.trabajoId}/excel`;
  btnExcel.classList.remove("oculto");
  btnExcel.addEventListener("click", () => toast("Descargando informe Excel…", "ok"), { once: true });

  pintarKpis(d.kpis);
  pintarDistribucion(d.kpis);
  pintarGraficas(d.graficas);
  pintarTabla();

  const obs = $("#obs-archivos");
  if (d.obs_archivos && d.obs_archivos.length) {
    obs.innerHTML =
      "<strong>Observaciones de los TXT:</strong> " +
      d.obs_archivos.slice(0, 5).map(esc).join(" · ") +
      (d.obs_archivos.length > 5 ? ` · (+${d.obs_archivos.length - 5} más en el Excel)` : "");
    obs.classList.remove("oculto");
  }
  toast(`Validación lista: ${d.kpis.facturas} facturas`, "ok");
}

function animarNumero(el, destino, formato) {
  const t0 = performance.now();
  const dur = 650;
  const paso = (t) => {
    const p = Math.min(1, (t - t0) / dur);
    const v = destino * (1 - Math.pow(1 - p, 3));
    el.textContent = formato ? formato(v) : Math.round(v).toLocaleString("es-CO");
    if (p < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}

function pintarKpis(k) {
  const defs = [
    ["Facturas", k.facturas, "azul", null],
    ["Con errores", k.con_errores, "err", "i-err"],
    ["Para revisar", k.revisar, "adv", "i-adv"],
    ["Cumplen", k.cumplen, "ok", "i-ok"],
    ["Hallazgos ERROR", k.errores, "err", null],
    ["Advertencias", k.advertencias, "adv", null],
    ["Valor facturado", k.vr_facturado, "azul dinero", null],
  ];
  $("#kpis").innerHTML = defs
    .map(
      ([nombre, , cls, ic], i) => `<div class="kpi ${cls}" style="animation-delay:${i * 45}ms">
        <div class="valor" data-kpi="${i}">0</div>
        <div class="nombre">${ic ? icono(ic, 13) : ""}${esc(nombre)}</div>
      </div>`
    )
    .join("");
  defs.forEach(([, valor], i) => {
    const el = document.querySelector(`[data-kpi="${i}"]`);
    if (i === 6) animarNumero(el, valor || 0, (v) => fmtPesos(v));
    else animarNumero(el, valor || 0);
  });
}

function pintarDistribucion(k) {
  const total = k.facturas || 1;
  const partes = [
    ["err", k.con_errores, "Con errores"],
    ["adv", k.revisar, "Para revisar"],
    ["ok", k.cumplen, "Cumplen"],
  ].filter(([, n]) => n > 0);
  $("#barra-distro").innerHTML = partes
    .map(
      ([cls, n, nombre]) =>
        `<div class="seg ${cls}" style="flex:${n}" data-tip="${esc(nombre)}: ${n} de ${total}"></div>`
    )
    .join("");
  $("#leyenda-distro").innerHTML = partes
    .map(
      ([cls, n, nombre]) => `<span><span class="punto seg ${cls}"></span>${esc(nombre)}:
        <strong>${n}</strong> (${Math.round((n / total) * 100)}%)</span>`
    )
    .join("");
  $("#distro-total").textContent = `${k.facturas} facturas · ${fmtPesos(k.vr_facturado)}`;
  activarTooltips("#barra-distro .seg");
}

/* ── Gráficas SVG (barras horizontales apiladas ERROR/ADVERTENCIA) ─────── */
function barrasH(idCont, filas, clave, onClick) {
  const cont = $(idCont);
  if (!filas.length) {
    cont.innerHTML = `<p class="ayuda">Sin datos para graficar. ✔</p>`;
    return;
  }
  const ANCHO = 560, ALTO_F = 34, MARGEN_IZQ = 230, MARGEN_DER = 46;
  const alto = filas.length * ALTO_F + 6;
  const max = Math.max(...filas.map((f) => f.error + f.advertencia), 1);
  const escala = (v) => (v / max) * (ANCHO - MARGEN_IZQ - MARGEN_DER);

  let svg = `<svg viewBox="0 0 ${ANCHO} ${alto}" role="img" aria-label="Gráfica de barras">`;
  filas.forEach((f, i) => {
    const y = i * ALTO_F + 4;
    const wErr = escala(f.error);
    const wAdv = escala(f.advertencia);
    const total = f.error + f.advertencia;
    const nombre = f[clave];
    const corto = nombre.length > 34 ? nombre.slice(0, 32) + "…" : nombre;
    svg += `<g class="banda" data-i="${i}" data-tip="${esc(nombre)} — ${f.error} error(es), ${f.advertencia} advertencia(s)">
      <rect class="fondo-banda" x="0" y="${y - 3}" width="${ANCHO}" height="${ALTO_F - 2}" fill="transparent"/>
      <text class="etiqueta" x="${MARGEN_IZQ - 10}" y="${y + 16}" text-anchor="end">${esc(corto)}</text>
      ${wErr > 0 ? `<rect class="err" x="${MARGEN_IZQ}" y="${y + 4}" width="${Math.max(wErr, 3)}" height="16" rx="4"/>` : ""}
      ${wAdv > 0 ? `<rect class="adv" x="${MARGEN_IZQ + wErr + (wErr ? 2 : 0)}" y="${y + 4}" width="${Math.max(wAdv, 3)}" height="16" rx="4"/>` : ""}
      <text class="valor-barra" x="${MARGEN_IZQ + wErr + wAdv + 8}" y="${y + 16}">${total}</text>
    </g>`;
  });
  svg += `</svg>
  <div class="leyenda">
    <span><span class="punto seg err"></span>Errores</span>
    <span><span class="punto seg adv"></span>Advertencias</span>
  </div>`;
  cont.innerHTML = svg;
  activarTooltips(`${idCont} .banda`);
  if (onClick)
    cont.querySelectorAll(".banda").forEach((g) =>
      g.addEventListener("click", () => onClick(filas[Number(g.dataset.i)]))
    );
}

function pintarGraficas(g) {
  barrasH("#graf-origen", g.por_origen, "origen", (f) => {
    estado.filtroOrigen = f.origen;
    cambiarVista("hallazgos");
  });
  barrasH(
    "#graf-conceptos",
    g.por_concepto.map((c) => ({ ...c, concepto: c.concepto })),
    "concepto",
    (f) => {
      estado.busquedaHallazgo = f.concepto.replace(/^Campo [^·]+· /, "");
      cambiarVista("hallazgos");
    }
  );
  barrasH(
    "#graf-top",
    g.top_facturas.map((f) => ({ ...f, error: f.errores, advertencia: f.advertencias, nombre: f.factura })),
    "nombre",
    (f) => abrirDetalle(f.nombre)
  );
}

/* Tooltips flotantes */
function activarTooltips(sel) {
  $$(sel).forEach((el) => {
    el.addEventListener("mousemove", (e) => {
      const tip = $("#tooltip");
      tip.textContent = el.dataset.tip || "";
      tip.classList.remove("oculto");
      const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 10);
      tip.style.left = x + "px";
      tip.style.top = Math.max(8, e.clientY - tip.offsetHeight - 10) + "px";
    });
    el.addEventListener("mouseleave", () => $("#tooltip").classList.add("oculto"));
  });
}

/* ── Vistas ────────────────────────────────────────────────────────────── */
function cambiarVista(nombre) {
  $$(".vista").forEach((b) => b.classList.toggle("activo", b.dataset.vista === nombre));
  ["tablero", "facturas", "hallazgos"].forEach((v) =>
    $(`#vista-${v}`).classList.toggle("oculto", v !== nombre)
  );
  if (nombre === "hallazgos") pintarHallazgosGlobales();
}
$$(".vista").forEach((b) => b.addEventListener("click", () => cambiarVista(b.dataset.vista)));

/* ── Tabla de facturas: filtro + orden ─────────────────────────────────── */
function facturasFiltradas() {
  const q = estado.busqueda.trim().toUpperCase();
  let filas = estado.facturas
    .filter((f) => !estado.filtroEstado || f.estado === estado.filtroEstado)
    .filter(
      (f) =>
        !q ||
        f.factura.includes(q) ||
        (f.paciente || "").toUpperCase().includes(q) ||
        (f.documento || "").toUpperCase().includes(q)
    );
  const { campo, asc } = estado.orden;
  const ordenEstado = { "CON ERRORES": 0, REVISAR: 1, CUMPLE: 2 };
  filas.sort((a, b) => {
    let va = a[campo], vb = b[campo];
    if (campo === "estado") { va = ordenEstado[va]; vb = ordenEstado[vb]; }
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "string") return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    return asc ? va - vb : vb - va;
  });
  return filas;
}

function chipSoporte(nombre, valor) {
  if (valor === "SI") return `<span class="sop si">${nombre} ✓</span>`;
  if (valor === "SIN TEXTO") return `<span class="sop sintexto">${nombre} s/texto</span>`;
  if (valor === "FALTA") return `<span class="sop falta">${nombre} falta</span>`;
  return `<span class="sop">${nombre} —</span>`;
}

function pintarTabla() {
  const filas = facturasFiltradas();
  estado.listaVisible = filas.map((f) => f.factura);
  $("#sin-filas").classList.toggle("oculto", filas.length > 0);
  $("#tabla-facturas tbody").innerHTML = filas
    .map(
      (f) => `<tr data-factura="${esc(f.factura)}" tabindex="0">
      <td class="fact">${esc(f.factura)}</td>
      <td>${esc(f.paciente || "—")}</td>
      <td>${esc(f.documento || "—")}</td>
      <td>${esc(f.ingreso || "—")}</td>
      <td class="num">${fmtPesos(f.vr_facturado)}</td>
      <td><div class="sops">
        ${chipSoporte("RIPS", f.soportes.rips)}${chipSoporte("CUV", f.soportes.cuv)}
        ${chipSoporte("XML", f.soportes.fev_xml)}${chipSoporte("FAC", f.soportes.factura_pdf)}
        ${chipSoporte("EPI", f.soportes.epicrisis)}
      </div></td>
      <td class="num">${f.errores || ""}</td>
      <td class="num">${f.advertencias || ""}</td>
      <td><span class="chip ${CLASE_ESTADO[f.estado] || "neutro"}">${esc(f.estado)}</span></td>
    </tr>`
    )
    .join("");
  $$("#tabla-facturas tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => abrirDetalle(tr.dataset.factura));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") abrirDetalle(tr.dataset.factura); });
  });
  // indicadores de orden
  $$("#tabla-facturas th.ordenable").forEach((th) => {
    th.querySelector(".flecha")?.remove();
    if (th.dataset.orden === estado.orden.campo) {
      th.insertAdjacentHTML("beforeend", `<span class="flecha">${estado.orden.asc ? "▲" : "▼"}</span>`);
    }
  });
}

$$("#tabla-facturas th.ordenable").forEach((th) =>
  th.addEventListener("click", () => {
    const campo = th.dataset.orden;
    if (estado.orden.campo === campo) estado.orden.asc = !estado.orden.asc;
    else estado.orden = { campo, asc: campo === "factura" || campo === "paciente" };
    pintarTabla();
  })
);
$("#buscar").addEventListener("input", (e) => { estado.busqueda = e.target.value; pintarTabla(); });
$$("#filtros-estado .filtro").forEach((b) =>
  b.addEventListener("click", () => {
    $$("#filtros-estado .filtro").forEach((x) => x.classList.remove("activo"));
    b.classList.add("activo");
    estado.filtroEstado = b.dataset.estado;
    pintarTabla();
  })
);
$("#btn-nueva").addEventListener("click", () => {
  sessionStorage.removeItem("trabajoId");
  location.reload();
});

/* ── Hallazgos globales ────────────────────────────────────────────────── */
async function pintarHallazgosGlobales() {
  if (!estado.hallazgos) {
    const r = await fetch(`/api/validaciones/${estado.trabajoId}/hallazgos`);
    if (!r.ok) return;
    estado.hallazgos = (await r.json()).hallazgos;
    const origenes = [...new Set(estado.hallazgos.map((h) => h.origen))].sort();
    $("#filtro-origen").innerHTML =
      `<option value="">Todos los orígenes</option>` +
      origenes.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join("");
  }
  $("#buscar-hallazgo").value = estado.busquedaHallazgo;
  $("#filtro-origen").value = estado.filtroOrigen;
  $$("#filtros-sev .filtro").forEach((b) =>
    b.classList.toggle("activo", b.dataset.sev === estado.filtroSev)
  );

  const q = estado.busquedaHallazgo.trim().toUpperCase();
  const lista = estado.hallazgos.filter(
    (h) =>
      (!estado.filtroSev || h.severidad === estado.filtroSev) &&
      (!estado.filtroOrigen || h.origen === estado.filtroOrigen) &&
      (!q ||
        h.factura.includes(q) ||
        (h.concepto || "").toUpperCase().includes(q) ||
        (h.detalle || "").toUpperCase().includes(q))
  );
  $("#conteo-hallazgos").textContent =
    `${lista.length} hallazgo(s)` +
    (lista.length !== estado.hallazgos.length ? ` de ${estado.hallazgos.length}` : "");
  $("#lista-hallazgos").innerHTML = lista
    .slice(0, 400)
    .map((h, i) => tarjetaHallazgo(h, true, i))
    .join("") + (lista.length > 400 ? `<p class="ayuda">Mostrando 400 de ${lista.length} — afine el filtro o revise el Excel.</p>` : "");
  $$("#lista-hallazgos .hallazgo.click").forEach((el) =>
    el.addEventListener("click", () => abrirDetalle(el.dataset.factura))
  );
}

function tarjetaHallazgo(h, conFactura, i = 0) {
  return `<article class="hallazgo ${CLASE_SEV[h.severidad] || ""} ${conFactura ? "click" : ""}"
      ${conFactura ? `data-factura="${esc(h.factura)}"` : ""} style="animation-delay:${Math.min(i * 18, 300)}ms">
    <div class="fila1">
      <span class="chip ${CLASE_SEV[h.severidad] || "neutro"}">${icono(ICONO_SEV[h.severidad] || "i-doc", 12)}${esc(h.severidad)}</span>
      ${conFactura ? `<strong class="fact">${esc(h.factura)}</strong>` : ""}
      <span class="concepto">${esc(h.concepto)}</span>
      <span class="meta">${esc(h.origen)}${h.campo && h.campo !== "-" ? " · campo " + esc(h.campo) : ""}</span>
    </div>
    ${
      h.valor_furips || h.valor_soporte
        ? `<div class="valores">FURIPS: <strong>${esc(h.valor_furips || "—")}</strong>` +
          (h.valor_soporte ? ` · Soporte: <strong>${esc(h.valor_soporte)}</strong>` : "") +
          (h.fuente ? ` <span class="meta">(${esc(h.fuente)})</span>` : "") + `</div>`
        : ""
    }
    <p class="detalle-txt">${esc(h.detalle)}</p>
    <div class="meta">${esc(h.regla)}</div>
  </article>`;
}

$("#buscar-hallazgo").addEventListener("input", (e) => {
  estado.busquedaHallazgo = e.target.value;
  pintarHallazgosGlobales();
});
$("#filtro-origen").addEventListener("change", (e) => {
  estado.filtroOrigen = e.target.value;
  pintarHallazgosGlobales();
});
$$("#filtros-sev .filtro").forEach((b) =>
  b.addEventListener("click", () => {
    estado.filtroSev = b.dataset.sev;
    pintarHallazgosGlobales();
  })
);

/* ── Detalle de factura ────────────────────────────────────────────────── */
let detalleActual = null;

async function abrirDetalle(factura) {
  const r = await fetch(
    `/api/validaciones/${estado.trabajoId}/facturas/${encodeURIComponent(factura)}`
  );
  if (!r.ok) return toast("No se pudo abrir la factura", "err");
  detalleActual = await r.json();
  const d = detalleActual;
  $("#detalle-titulo").textContent = d.factura;
  $("#detalle-sub").textContent =
    `${d.paciente || "(sin paciente)"} · ${d.documento || ""} · ${fmtPesos(d.vr_facturado)}` +
    ` · ingreso ${d.ingreso || "—"}`;
  $("#detalle-chip").innerHTML =
    `<span class="chip ${CLASE_ESTADO[d.estado] || "neutro"}">${esc(d.estado)}</span>`;
  $("#n-hallazgos").textContent = d.hallazgos.length;
  $("#n-lineas").textContent = d.lineas.length;
  $$(".tab").forEach((t) => t.classList.toggle("activo", t.dataset.tab === "hallazgos"));
  pintarTab("hallazgos");
  $("#fondo-detalle").classList.remove("oculto");
  document.body.style.overflow = "hidden";
  actualizarNavDetalle();
}

function actualizarNavDetalle() {
  const i = estado.listaVisible.indexOf(detalleActual?.factura);
  $("#btn-fact-ant").disabled = i <= 0;
  $("#btn-fact-sig").disabled = i < 0 || i >= estado.listaVisible.length - 1;
}
$("#btn-fact-ant").addEventListener("click", () => {
  const i = estado.listaVisible.indexOf(detalleActual.factura);
  if (i > 0) abrirDetalle(estado.listaVisible[i - 1]);
});
$("#btn-fact-sig").addEventListener("click", () => {
  const i = estado.listaVisible.indexOf(detalleActual.factura);
  if (i >= 0 && i < estado.listaVisible.length - 1) abrirDetalle(estado.listaVisible[i + 1]);
});

function cerrarDetalle() {
  $("#fondo-detalle").classList.add("oculto");
  document.body.style.overflow = "";
}
$("#btn-cerrar-detalle").addEventListener("click", cerrarDetalle);
$("#fondo-detalle").addEventListener("click", (e) => {
  if (e.target.id === "fondo-detalle") cerrarDetalle();
});
document.addEventListener("keydown", (e) => {
  if ($("#fondo-detalle").classList.contains("oculto")) return;
  if (e.key === "Escape") cerrarDetalle();
  if (e.key === "ArrowLeft") $("#btn-fact-ant").click();
  if (e.key === "ArrowRight") $("#btn-fact-sig").click();
});
$$(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("activo"));
    t.classList.add("activo");
    pintarTab(t.dataset.tab);
  })
);

function pintarTab(tab) {
  const d = detalleActual;
  const cuerpo = $("#detalle-cuerpo");
  if (!d) return;

  if (tab === "hallazgos") {
    cuerpo.innerHTML = d.hallazgos.length
      ? d.hallazgos.map((h, i) => tarjetaHallazgo(h, false, i)).join("")
      : `<p class="ayuda">${icono("i-ok", 15)} Sin hallazgos: la factura cumple la malla y los cruces disponibles.</p>`;
  } else if (tab === "campos") {
    cuerpo.innerHTML = tablaMini(
      ["Nº", "Sección", "Campo", "Valor", "Obligatoriedad", "Estado", "Observación"],
      d.campos_f1.map((c) => [
        c.n, c.seccion, c.campo, c.valor, c.obligatoriedad,
        `<span class="chip ${CLASE_SEV[c.estado] || "ok"}">${esc(c.estado)}</span>`,
        c.obs,
      ]),
      [5]
    );
  } else if (tab === "lineas") {
    cuerpo.innerHTML = tablaMini(
      ["Nº", "Tipo", "Código", "Descripción", "Cant.", "Vr. unit.", "Vr. fact.", "Vr. recl.", "Estado", "Observación"],
      d.lineas.map((l) => [
        l.n, l.tipo, l.codigo, l.descripcion, l.cantidad,
        fmtPesos(l.vr_unitario), fmtPesos(l.vr_facturado), fmtPesos(l.vr_reclamado),
        `<span class="chip ${CLASE_SEV[l.estado] || "ok"}">${esc(l.estado)}</span>`,
        l.obs,
      ]),
      [8]
    );
  } else if (tab === "cruces") {
    cuerpo.innerHTML = tablaMini(
      ["Dato", "FURIPS", "RIPS", "CUV", "XML", "Factura PDF", "Epicrisis", "Resultado", "Observación"],
      d.cruces.map((c) => [
        c.dato, c.furips, c.rips, c.cuv, c.xml, c.factura_pdf, c.epicrisis,
        `<span class="chip ${
          c.resultado === "COINCIDE" ? "ok" : c.resultado === "SIN DATO PARA CRUZAR" ? "info" : "adv"
        }">${esc(c.resultado)}</span>`,
        c.obs,
      ]),
      [7]
    );
  } else if (tab === "archivos") {
    cuerpo.innerHTML = d.archivos.length
      ? tablaMini(
          ["Archivo", "Tipo de soporte", "Tamaño (KB)", "Texto legible"],
          d.archivos.map((a) => [a.archivo, a.tipo, Math.round(a.bytes / 1024), a.legible])
        )
      : `<p class="ayuda">No se encontraron soportes para esta factura.</p>`;
  }
}

function tablaMini(cabeceras, filas, colsSinEscapar = []) {
  const th = cabeceras.map((c) => `<th>${esc(c)}</th>`).join("");
  const tb = filas
    .map(
      (fila) =>
        `<tr>${fila
          .map((v, i) => `<td>${colsSinEscapar.includes(i) ? v : esc(v == null ? "" : v)}</td>`)
          .join("")}</tr>`
    )
    .join("");
  return `<div class="tabla-scroll"><table class="tabla-mini"><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`;
}

/* ── Reanudar sesión previa (recarga de página) ────────────────────────── */
(async function reanudar() {
  if (!estado.trabajoId) return;
  try {
    const r = await fetch(`/api/validaciones/${estado.trabajoId}/estado`);
    if (!r.ok) throw 0;
    const d = await r.json();
    if (d.estado === "LISTO") {
      $("#panel-carga").classList.add("oculto");
      await cargarResultados();
      toast("Se recuperó la validación anterior", "ok");
    } else if (d.estado === "PROCESANDO") {
      $("#panel-carga").classList.add("oculto");
      $("#panel-progreso").classList.remove("oculto");
      sondear();
    }
  } catch {
    sessionStorage.removeItem("trabajoId");
  }
})();
