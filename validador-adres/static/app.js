/* Validador ADRES — lógica del frontend (sin dependencias) */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const estado = {
  archivos: [],          // File[] elegidos
  trabajoId: null,
  facturas: [],          // resumen por factura
  filtroEstado: "",
  busqueda: "",
};

const fmtPesos = (n) =>
  n == null ? "—" : "$" + Math.round(n).toLocaleString("es-CO");

const CLASE_ESTADO = { "CON ERRORES": "err", "REVISAR": "adv", "CUMPLE": "ok" };
const CLASE_SEV = { ERROR: "err", ADVERTENCIA: "adv", INFO: "info", OK: "ok" };

function esc(t) {
  const d = document.createElement("div");
  d.textContent = t == null ? "" : String(t);
  return d.innerHTML;
}

/* ── Paso 1: selección de archivos ─────────────────────────────────────── */
const zona = $("#zona-drop");
const inputArchivos = $("#input-archivos");

zona.addEventListener("click", () => inputArchivos.click());
zona.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") inputArchivos.click();
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
  for (const f of lista) {
    const ext = f.name.toLowerCase().split(".").pop();
    if (!["txt", "zip"].includes(ext)) continue;
    if (estado.archivos.some((x) => x.name === f.name && x.size === f.size)) continue;
    estado.archivos.push(f);
  }
  pintarListaArchivos();
}

function pintarListaArchivos() {
  const ul = $("#lista-archivos");
  ul.innerHTML = estado.archivos
    .map(
      (f, i) => `<li>
        <span>📄 ${esc(f.name)} <small>(${(f.size / 1024 / 1024).toFixed(1)} MB)</small></span>
        <button class="quitar" data-i="${i}" aria-label="Quitar ${esc(f.name)}">✕</button>
      </li>`
    )
    .join("");
  ul.querySelectorAll(".quitar").forEach((b) =>
    b.addEventListener("click", () => {
      estado.archivos.splice(Number(b.dataset.i), 1);
      pintarListaArchivos();
    })
  );
  $("#btn-validar").disabled = estado.archivos.length === 0;
}

/* ── Paso 2: subir y validar con progreso ──────────────────────────────── */
$("#btn-validar").addEventListener("click", async () => {
  const err = $("#error-carga");
  err.classList.add("oculto");
  $("#panel-carga").classList.add("oculto");
  $("#panel-progreso").classList.remove("oculto");
  $("#progreso-texto").textContent = "Subiendo archivos…";
  $("#barra-relleno").style.width = "4%";

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
    sondear();
  } catch (e) {
    mostrarErrorCarga(e.message);
  }
});

function mostrarErrorCarga(msj) {
  $("#panel-progreso").classList.add("oculto");
  $("#panel-carga").classList.remove("oculto");
  const err = $("#error-carga");
  err.textContent = "No se pudo validar: " + msj;
  err.classList.remove("oculto");
}

async function sondear() {
  try {
    const r = await fetch(`/api/validaciones/${estado.trabajoId}/estado`);
    if (!r.ok) throw new Error("estado " + r.status);
    const d = await r.json();
    if (d.estado === "ERROR") return mostrarErrorCarga(d.mensaje);
    const pct = d.total ? Math.max(6, Math.round((d.progreso / d.total) * 100)) : 6;
    $("#barra-relleno").style.width = pct + "%";
    $("#progreso-texto").textContent = d.mensaje || "Procesando…";
    if (d.estado === "LISTO") return cargarResultados();
    setTimeout(sondear, 700);
  } catch (e) {
    mostrarErrorCarga(e.message);
  }
}

/* ── Paso 3: resultados ────────────────────────────────────────────────── */
async function cargarResultados() {
  const r = await fetch(`/api/validaciones/${estado.trabajoId}`);
  const d = await r.json();
  estado.facturas = d.facturas;

  $("#panel-progreso").classList.add("oculto");
  $("#panel-resultados").classList.remove("oculto");
  $("#btn-nueva").classList.remove("oculto");
  const btnExcel = $("#btn-excel");
  btnExcel.href = `/api/validaciones/${estado.trabajoId}/excel`;
  btnExcel.classList.remove("oculto");

  pintarKpis(d.kpis);
  pintarDistribucion(d.kpis);
  pintarTabla();

  const obs = $("#obs-archivos");
  if (d.obs_archivos && d.obs_archivos.length) {
    obs.innerHTML =
      "<strong>Observaciones de los archivos TXT:</strong> " +
      d.obs_archivos.slice(0, 5).map(esc).join(" · ") +
      (d.obs_archivos.length > 5 ? ` · (+${d.obs_archivos.length - 5} más en el Excel)` : "");
    obs.classList.remove("oculto");
  }
}

function pintarKpis(k) {
  const defs = [
    ["Facturas", k.facturas, ""],
    ["Con errores", k.con_errores, "err"],
    ["Para revisar", k.revisar, "adv"],
    ["Cumplen", k.cumplen, "ok"],
    ["Hallazgos ERROR", k.errores, "err"],
    ["Advertencias", k.advertencias, "adv"],
    ["Valor facturado", fmtPesos(k.vr_facturado), ""],
  ];
  $("#kpis").innerHTML = defs
    .map(
      ([nombre, valor, cls]) => `<div class="kpi ${cls}">
        <div class="valor">${esc(valor)}</div><div class="nombre">${esc(nombre)}</div>
      </div>`
    )
    .join("");
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
        `<div class="seg ${cls}" style="flex:${n}" title="${esc(nombre)}: ${n}"></div>`
    )
    .join("");
  $("#leyenda-distro").innerHTML = partes
    .map(
      ([cls, n, nombre]) => `<span>
        <span class="punto seg ${cls}"></span>${esc(nombre)}: <strong>${n}</strong>
        (${Math.round((n / total) * 100)}%)</span>`
    )
    .join("");
  $("#distro-total").textContent = `${k.facturas} facturas · ${fmtPesos(k.vr_facturado)}`;
}

function chipSoporte(nombre, valor) {
  if (valor === "SI") return `<span class="sop">${nombre} ✓</span>`;
  if (valor === "SIN TEXTO") return `<span class="sop sintexto">${nombre} sin texto</span>`;
  if (valor === "FALTA") return `<span class="sop falta">${nombre} falta</span>`;
  return `<span class="sop">${nombre} —</span>`;
}

function pintarTabla() {
  const q = estado.busqueda.trim().toUpperCase();
  const filas = estado.facturas
    .filter((f) => !estado.filtroEstado || f.estado === estado.filtroEstado)
    .filter(
      (f) =>
        !q ||
        f.factura.includes(q) ||
        (f.paciente || "").toUpperCase().includes(q) ||
        (f.documento || "").toUpperCase().includes(q)
    );
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
    tr.addEventListener("keydown", (e) => {
      if (e.key === "Enter") abrirDetalle(tr.dataset.factura);
    });
  });
}

$("#buscar").addEventListener("input", (e) => {
  estado.busqueda = e.target.value;
  pintarTabla();
});
$$("#filtros-estado .filtro").forEach((b) =>
  b.addEventListener("click", () => {
    $$("#filtros-estado .filtro").forEach((x) => x.classList.remove("activo"));
    b.classList.add("activo");
    estado.filtroEstado = b.dataset.estado;
    pintarTabla();
  })
);

$("#btn-nueva").addEventListener("click", () => location.reload());

/* ── Detalle de factura ────────────────────────────────────────────────── */
let detalleActual = null;

async function abrirDetalle(factura) {
  const r = await fetch(
    `/api/validaciones/${estado.trabajoId}/facturas/${encodeURIComponent(factura)}`
  );
  if (!r.ok) return;
  detalleActual = await r.json();
  $("#detalle-titulo").textContent = detalleActual.factura;
  $("#detalle-sub").textContent =
    `${detalleActual.paciente || ""} · ${detalleActual.documento || ""} · ` +
    `${fmtPesos(detalleActual.vr_facturado)} · ${detalleActual.errores} errores, ` +
    `${detalleActual.advertencias} advertencias`;
  $$(".tab").forEach((t) => t.classList.toggle("activo", t.dataset.tab === "hallazgos"));
  pintarTab("hallazgos");
  $("#fondo-detalle").classList.remove("oculto");
  document.body.style.overflow = "hidden";
}

function cerrarDetalle() {
  $("#fondo-detalle").classList.add("oculto");
  document.body.style.overflow = "";
}
$("#btn-cerrar-detalle").addEventListener("click", cerrarDetalle);
$("#fondo-detalle").addEventListener("click", (e) => {
  if (e.target.id === "fondo-detalle") cerrarDetalle();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") cerrarDetalle();
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
      ? d.hallazgos
          .map(
            (h) => `<article class="hallazgo ${CLASE_SEV[h.severidad] || ""}">
          <div class="fila1">
            <span class="chip ${CLASE_SEV[h.severidad] || "neutro"}">${esc(h.severidad)}</span>
            <span class="concepto">${esc(h.concepto)}</span>
            <span class="meta">${esc(h.origen)}${h.campo && h.campo !== "-" ? " · campo " + esc(h.campo) : ""}</span>
          </div>
          ${
            h.valor_furips || h.valor_soporte
              ? `<div class="valores">FURIPS: <strong>${esc(h.valor_furips || "—")}</strong>` +
                (h.valor_soporte ? ` · Soporte: <strong>${esc(h.valor_soporte)}</strong>` : "") +
                (h.fuente ? ` <span class="meta">(${esc(h.fuente)})</span>` : "") +
                `</div>`
              : ""
          }
          <p class="detalle-txt">${esc(h.detalle)}</p>
          <div class="meta">${esc(h.regla)}</div>
        </article>`
          )
          .join("")
      : `<p class="ayuda">Sin hallazgos: la factura cumple la malla y los cruces disponibles. ✔</p>`;
  } else if (tab === "campos") {
    cuerpo.innerHTML = tablaMini(
      ["Nº", "Sección", "Campo", "Valor", "Obligatoriedad", "Estado", "Observación"],
      d.campos_f1.map((c) => [
        c.n,
        c.seccion,
        c.campo,
        c.valor,
        c.obligatoriedad,
        `<span class="chip ${CLASE_SEV[c.estado] || "ok"}">${esc(c.estado)}</span>`,
        c.obs,
      ]),
      [5]
    );
  } else if (tab === "lineas") {
    cuerpo.innerHTML = tablaMini(
      ["Nº", "Tipo", "Código", "Descripción", "Cant.", "Vr. unit.", "Vr. fact.", "Vr. recl.", "Estado", "Observación"],
      d.lineas.map((l) => [
        l.n,
        l.tipo,
        l.codigo,
        l.descripcion,
        l.cantidad,
        fmtPesos(l.vr_unitario),
        fmtPesos(l.vr_facturado),
        fmtPesos(l.vr_reclamado),
        `<span class="chip ${CLASE_SEV[l.estado] || "ok"}">${esc(l.estado)}</span>`,
        l.obs,
      ]),
      [8]
    );
  } else if (tab === "cruces") {
    cuerpo.innerHTML = tablaMini(
      ["Dato", "FURIPS", "RIPS", "CUV", "XML", "Factura PDF", "Epicrisis", "Resultado", "Observación"],
      d.cruces.map((c) => [
        c.dato,
        c.furips,
        c.rips,
        c.cuv,
        c.xml,
        c.factura_pdf,
        c.epicrisis,
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
