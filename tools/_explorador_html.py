"""Render del Explorador de Radicación (HTML autocontenido).

`render_html(datos)` devuelve una página HTML única: CSS embebido, datos en JSON
y toda la interacción (filtros por estado, búsqueda, copiar ruta, detalle) en
JavaScript puro, sin dependencias ni internet.
"""

from __future__ import annotations

import json
from datetime import datetime

_PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<style>
  :root{
    --navy:#1e3a8a;--blue:#2563eb;--blue2:#3b82f6;--blue-bg:#eff6ff;--green:#16a34a;
    --bg:#f1f5f9;--card:#fff;--border:#e2e8f0;--text:#0f172a;--muted:#64748b;
    --shadow:0 1px 3px rgba(15,23,42,.08);--radius:13px;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  header.top{background:linear-gradient(120deg,var(--navy),var(--blue));color:#fff;padding:20px 28px}
  header.top .brand{display:flex;align-items:center;gap:14px}
  header.top .logo{width:42px;height:42px;border-radius:11px;background:rgba(255,255,255,.16);
    display:grid;place-items:center;font-weight:800;font-size:18px}
  header.top h1{margin:0;font-size:20px}header.top .sub{margin:2px 0 0;opacity:.85;font-size:13px}
  .wrap{max-width:1280px;margin:0 auto;padding:20px}
  .chips{display:flex;flex-wrap:wrap;gap:10px;margin:2px 0 18px}
  .chip{background:#fff;border:1px solid var(--border);border-radius:12px;padding:9px 14px;cursor:pointer;
    display:flex;flex-direction:column;gap:1px;min-width:104px;box-shadow:var(--shadow);transition:.12s}
  .chip:hover{transform:translateY(-1px)}
  .chip.on{box-shadow:0 0 0 2px var(--c)}
  .chip .n{font-size:21px;font-weight:800;color:var(--c);font-variant-numeric:tabular-nums}
  .chip .l{font-size:11px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.3px}
  .panel{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow)}
  .toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
  .toolbar input,.toolbar select{padding:9px 12px;border:1px solid var(--border);border-radius:9px;font-size:13px;background:#fff;color:var(--text)}
  .toolbar input{flex:1;min-width:220px}
  .btn{padding:9px 14px;border:1px solid var(--blue);background:#fff;color:var(--blue);border-radius:9px;font-size:13px;font-weight:600;cursor:pointer}
  .btn:hover{background:var(--blue-bg)}
  .count{margin-left:auto;color:var(--muted);font-size:13px;font-weight:600}
  .tablewrap{max-height:64vh;overflow:auto;border:1px solid var(--border);border-radius:11px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--border);vertical-align:top}
  th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);cursor:pointer;
    position:sticky;top:0;background:#fff;white-space:nowrap}
  th:hover{color:var(--blue)}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tr.clickable{cursor:pointer}tr.clickable:hover td{background:var(--blue-bg)}
  .badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap}
  .fac{font-weight:700}
  .path{font-family:ui-monospace,"Cascadia Code",Consolas,monospace;font-size:12px;color:var(--muted);
    max-width:330px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle}
  .copy{border:none;background:var(--bg);border-radius:7px;padding:3px 8px;cursor:pointer;font-size:12px;margin-left:6px}
  .copy:hover{background:#dbeafe}
  .falta{color:#9f1239;font-size:12.5px}
  .empty{color:var(--muted);text-align:center;padding:34px;font-style:italic}
  .modal-bg{position:fixed;inset:0;background:rgba(15,23,42,.55);display:none;place-items:center;z-index:50}
  .modal-bg.on{display:grid}
  .modal{background:#fff;border-radius:16px;max-width:620px;width:94%;max-height:88vh;overflow:auto;box-shadow:0 20px 50px rgba(0,0,0,.35)}
  .modal .mh{background:linear-gradient(120deg,var(--navy),var(--blue));color:#fff;padding:16px 20px;
    border-radius:16px 16px 0 0;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0}
  .modal .mh h3{margin:0;font-size:17px}.modal .x{cursor:pointer;font-size:24px;background:none;border:none;color:#fff}
  .modal .mb{padding:6px 20px 18px}
  .drow{display:flex;justify-content:space-between;gap:16px;padding:9px 0;border-bottom:1px solid var(--border)}
  .drow .k{color:var(--muted)}.drow .v{font-weight:600;text-align:right;max-width:62%}
  .pathbox{background:var(--bg);border:1px solid var(--border);border-radius:9px;padding:10px 12px;margin-top:6px;
    font-family:ui-monospace,Consolas,monospace;font-size:12.5px;word-break:break-all;display:flex;gap:8px;align-items:center;justify-content:space-between}
  .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#0f172a;color:#fff;
    padding:10px 18px;border-radius:10px;font-size:13px;opacity:0;transition:.2s;pointer-events:none;z-index:60}
  .toast.on{opacity:1}
</style>
</head>
<body>
<header class="top"><div class="brand"><div class="logo">HUS</div><div>
  <h1>__TITULO__</h1>
  <p class="sub">Buscador de facturas radicadas · <b id="total"></b> facturas · <span id="fecha"></span></p>
</div></div></header>

<div class="wrap">
  <div class="chips" id="chips"></div>
  <div class="panel">
    <div class="toolbar">
      <input id="q" placeholder="Buscar por factura, entidad o carpeta…">
      <select id="f-ent"><option value="">Todas las entidades</option></select>
      <button class="btn" id="export">⬇ Exportar lista</button>
      <span class="count" id="count"></span>
    </div>
    <div class="tablewrap"><table>
      <thead><tr id="thead"></tr></thead>
      <tbody id="tbody"></tbody>
    </table></div>
  </div>
</div>

<div class="modal-bg" id="modal"><div class="modal">
  <div class="mh"><h3 id="m-title">Factura</h3><button class="x" id="m-close">&times;</button></div>
  <div class="mb" id="m-body"></div>
</div></div>
<div class="toast" id="toast">Ruta copiada ✓</div>

<script>
const DATA = __DATA__;
const COL = {};
DATA.estados.forEach(e=>COL[e.estado]=e.color);
const colEstado = e => COL[e] || "#64748b";
const fmt = n => "$ " + Math.round(n||0).toLocaleString("es-CO");
const fmtShort = n => {n=n||0;const a=Math.abs(n);
  if(a>=1e9)return "$ "+(n/1e9).toFixed(1).replace(".",",")+" mil M";
  if(a>=1e6)return "$ "+(n/1e6).toFixed(1).replace(".",",")+" M";
  if(a>=1e3)return "$ "+(n/1e3).toFixed(0)+" K";return "$ "+Math.round(n);};

let filtroEstado="", sortK="", sortDir=1, vista=[];

function copiar(txt){
  const ta=document.createElement("textarea");ta.value=txt;ta.style.position="fixed";ta.style.opacity="0";
  document.body.appendChild(ta);ta.select();
  try{document.execCommand("copy");}catch(e){}
  document.body.removeChild(ta);
  const t=document.getElementById("toast");t.classList.add("on");setTimeout(()=>t.classList.remove("on"),1400);
}

function renderChips(){
  const all = `<div class="chip ${filtroEstado===''?'on':''}" style="--c:var(--blue)" data-e="">
      <div class="n">${DATA.total.toLocaleString("es-CO")}</div><div class="l">Todas</div></div>`;
  document.getElementById("chips").innerHTML = all + DATA.estados.map(e=>
    `<div class="chip ${filtroEstado===e.estado?'on':''}" style="--c:${e.color}" data-e="${e.estado}">
       <div class="n">${e.n.toLocaleString("es-CO")}</div><div class="l">${e.label}</div></div>`).join("");
}

const COLS=[
  {k:"factura",t:"Factura"},{k:"entidad",t:"Entidad"},{k:"estado",t:"Estado"},
  {k:"falta",t:"¿Qué le falta?"},{k:"servicios",t:"Servicios"},{k:"valor",t:"Valor",n:1},
  {k:"carpeta",t:"Carpeta (dónde está)"}
];

function pinta(){
  const q=document.getElementById("q").value.toLowerCase();
  const fe=document.getElementById("f-ent").value;
  let rows=DATA.facturas.filter(f=>{
    if(filtroEstado&&f.estado!==filtroEstado)return false;
    if(fe&&f.entidad!==fe)return false;
    if(q&&!((f.factura+" "+f.entidad+" "+f.carpeta+" "+f.falta).toLowerCase().includes(q)))return false;
    return true;
  });
  if(sortK)rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];
    if(typeof x==="number")return sortDir*((x||0)-(y||0));
    return sortDir*String(x||"").localeCompare(String(y||""));});
  vista=rows;
  document.getElementById("thead").innerHTML=COLS.map(c=>`<th class="${c.n?'num':''}" data-k="${c.k}">${c.t}${sortK===c.k?(sortDir<0?" ▾":" ▴"):""}</th>`).join("");
  document.getElementById("tbody").innerHTML = rows.length? rows.slice(0,1000).map((f,i)=>`
    <tr class="clickable" data-i="${DATA.facturas.indexOf(f)}">
      <td class="fac">${f.factura}</td>
      <td>${f.entidad}</td>
      <td><span class="badge" style="background:${colEstado(f.estado)}1f;color:${colEstado(f.estado)}">${f.estado}</span></td>
      <td class="falta">${f.falta||'<span class="badge" style="background:#16a34a1f;color:#16a34a">Lista ✓</span>'}</td>
      <td>${f.servicios||'—'}</td>
      <td class="num">${f.valor?fmtShort(f.valor):'—'}</td>
      <td>${f.carpeta?`<span class="path" title="${f.carpeta}">${f.carpeta}</span><button class="copy" data-copy="${encodeURIComponent(f.carpeta)}" title="Copiar ruta">📋</button>`:'—'}</td>
    </tr>`).join("") : `<tr><td colspan="${COLS.length}" class="empty">Sin facturas para este filtro.</td></tr>`;
  const tope = rows.length>1000 ? " (muestra 1.000)" : "";
  document.getElementById("count").textContent = rows.length.toLocaleString("es-CO")+" de "+DATA.total.toLocaleString("es-CO")+tope;
}

function abrir(i){
  const f=DATA.facturas[i]; if(!f)return;
  const row=(k,v)=>v?`<div class="drow"><span class="k">${k}</span><span class="v">${v}</span></div>`:"";
  const c=colEstado(f.estado);
  document.getElementById("m-title").textContent=f.factura+" · "+f.entidad;
  document.getElementById("m-body").innerHTML=
    row("Estado",`<span class="badge" style="background:${c}1f;color:${c}">${f.estado}</span>`)
    +(f.falta?`<div class="drow"><span class="k">¿Qué le falta?</span><span class="v falta">${f.falta}</span></div>`:"")
    +row("Canal",f.canal)+row("Servicios",f.servicios)+row("Valor",f.valor?fmt(f.valor):"—")
    +row("Soportes presentes",f.soportes_presentes)
    +row("Soportes faltantes",f.soportes_faltantes)
    +row("Soportes clínicos esperados",f.soportes_esperados_faltantes)
    +row("Archivos sin tipificar",f.archivos_sin_clasificar)
    +row("Detalle",f.detalle)
    +(f.carpeta?`<div style="margin-top:12px"><div class="k" style="color:var(--muted);font-size:12px">📁 Carpeta (dónde está):</div>
       <div class="pathbox"><span>${f.carpeta}</span><button class="btn" data-copy="${encodeURIComponent(f.carpeta)}">Copiar</button></div></div>`:"")
    +(f.ruta_paquete?`<div style="margin-top:10px"><div class="k" style="color:var(--muted);font-size:12px">📦 Paquete armado:</div>
       <div class="pathbox"><span>${f.ruta_paquete}</span><button class="btn" data-copy="${encodeURIComponent(f.ruta_paquete)}">Copiar</button></div></div>`:"");
  document.getElementById("modal").classList.add("on");
}
const cerrar=()=>document.getElementById("modal").classList.remove("on");

function exportar(){
  const cols=["factura","entidad","estado","falta","servicios","valor","soportes_faltantes","soportes_esperados_faltantes","archivos_sin_clasificar","carpeta"];
  const linea=f=>cols.map(c=>'"'+String(f[c]==null?"":f[c]).replace(/"/g,'""')+'"').join(";");
  const csv="﻿"+cols.join(";")+"\n"+vista.map(linea).join("\n");
  const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8;"}));
  a.download="facturas_"+(filtroEstado||"todas")+".csv";a.click();URL.revokeObjectURL(a.href);
}

function init(){
  document.getElementById("total").textContent=DATA.total.toLocaleString("es-CO");
  document.getElementById("fecha").textContent=DATA.fecha||"";
  renderChips();
  const fe=document.getElementById("f-ent");
  DATA.entidades.forEach(e=>fe.add(new Option(e,e)));
  document.getElementById("chips").addEventListener("click",ev=>{
    const ch=ev.target.closest(".chip"); if(!ch)return; filtroEstado=ch.dataset.e; renderChips(); pinta();
  });
  document.getElementById("q").addEventListener("input",pinta);
  fe.addEventListener("change",pinta);
  document.getElementById("export").addEventListener("click",exportar);
  document.getElementById("thead").addEventListener("click",e=>{const k=e.target.dataset.k;if(!k)return;
    if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=1;}pinta();});
  document.getElementById("tbody").addEventListener("click",e=>{
    const cp=e.target.closest("[data-copy]");
    if(cp){e.stopPropagation();copiar(decodeURIComponent(cp.dataset.copy));return;}
    const tr=e.target.closest("tr[data-i]"); if(tr)abrir(+tr.dataset.i);
  });
  document.getElementById("m-close").addEventListener("click",cerrar);
  document.getElementById("modal").addEventListener("click",e=>{if(e.target.id==="modal")cerrar();});
  document.getElementById("m-body").addEventListener("click",e=>{
    const cp=e.target.closest("[data-copy]"); if(cp)copiar(decodeURIComponent(cp.dataset.copy));});
  document.addEventListener("keydown",e=>{if(e.key==="Escape")cerrar();});
  pinta();
}
init();
</script>
</body>
</html>
"""


def render_html(datos: dict) -> str:
    datos.setdefault("fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
    payload = json.dumps(datos, ensure_ascii=False)
    return _PLANTILLA.replace("__DATA__", payload).replace(
        "__TITULO__", str(datos.get("titulo", "Explorador de Radicación — ESE HUS"))
    )
