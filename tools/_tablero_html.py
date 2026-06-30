"""Render del tablero HTML de Radicación y Cartera (autocontenido).

`render_html(datos)` devuelve una página HTML única: CSS embebido, datos en
JSON y gráficos dibujados en SVG con JavaScript puro (sin dependencias ni
internet). Se abre con doble clic y se comparte por red o correo.

El módulo de Python solo inyecta los datos; toda la lógica de pintado vive en el
JS estático de la plantilla (por eso usamos marcadores __DATA__/__TITULO__ y no
un f-string, para no pelear con las llaves de JS/CSS).
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
    --navy:#1e3a8a; --blue:#2563eb; --blue2:#3b82f6; --blue-bg:#eff6ff;
    --green:#16a34a; --green-bg:#f0fdf4; --rose:#e11d48; --rose-bg:#fff1f2;
    --amber:#d97706; --amber-bg:#fffbeb; --slate:#475569; --slate2:#94a3b8;
    --bg:#f1f5f9; --card:#ffffff; --border:#e2e8f0; --text:#0f172a; --muted:#64748b;
    --shadow:0 1px 3px rgba(15,23,42,.08),0 1px 2px rgba(15,23,42,.04);
    --radius:14px;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    font-size:14px;line-height:1.5}
  a{color:var(--blue)}
  header.top{background:linear-gradient(120deg,var(--navy),var(--blue));color:#fff;
    padding:22px 28px;box-shadow:var(--shadow)}
  header.top .brand{display:flex;align-items:center;gap:14px}
  header.top .logo{width:42px;height:42px;border-radius:11px;background:rgba(255,255,255,.16);
    display:grid;place-items:center;font-weight:800;font-size:18px;letter-spacing:.5px}
  header.top h1{margin:0;font-size:20px;font-weight:700}
  header.top .sub{margin:2px 0 0;opacity:.85;font-size:13px}
  .wrap{max-width:1280px;margin:0 auto;padding:22px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:8px}
  .kpi{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
    padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden}
  .kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent,var(--blue))}
  .kpi .lbl{color:var(--muted);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.4px}
  .kpi .val{font-size:24px;font-weight:800;margin-top:6px;letter-spacing:-.5px}
  .kpi .hint{font-size:12px;color:var(--muted);margin-top:3px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
  @media(max-width:880px){.grid{grid-template-columns:1fr}}
  .panel{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
    padding:18px;box-shadow:var(--shadow)}
  .panel.full{grid-column:1/-1}
  .panel h2{margin:0 0 14px;font-size:15px;font-weight:700;display:flex;align-items:center;gap:8px}
  .panel h2 .tag{font-size:11px;font-weight:600;color:var(--muted);background:var(--bg);
    border-radius:20px;padding:2px 9px}
  .legend{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:12px;font-size:12px;color:var(--slate)}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .legend i{width:11px;height:11px;border-radius:3px;display:inline-block}
  .bars-h{display:flex;flex-direction:column;gap:11px}
  .barow{display:grid;grid-template-columns:150px 1fr;align-items:center;gap:10px}
  .barow .nm{font-size:12px;color:var(--slate);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
  .track{background:var(--bg);border-radius:7px;height:22px;display:flex;overflow:hidden;position:relative}
  .seg{height:100%;transition:width .5s}
  .barow .amt{font-size:11px;color:var(--muted);margin-top:2px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}
  th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);
    cursor:pointer;user-select:none;position:sticky;top:0;background:var(--card)}
  th:hover{color:var(--blue)}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tr:hover td{background:var(--blue-bg)}
  .badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700}
  .toolbar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px;align-items:center}
  .toolbar input,.toolbar select{padding:8px 11px;border:1px solid var(--border);border-radius:9px;
    font-size:13px;background:#fff;color:var(--text)}
  .toolbar input{flex:1;min-width:180px}
  .tablewrap{max-height:560px;overflow:auto;border:1px solid var(--border);border-radius:11px}
  .muted{color:var(--muted)}
  .foot{text-align:center;color:var(--muted);font-size:12px;padding:24px 0 8px}
  .pill{font-size:12px;font-weight:700;padding:3px 10px;border-radius:20px}
  .empty{color:var(--muted);text-align:center;padding:30px;font-style:italic}
</style>
</head>
<body>
<header class="top">
  <div class="brand">
    <div class="logo">HUS</div>
    <div>
      <h1>__TITULO__</h1>
      <p class="sub">Cuentas Médicas y Cartera · Corte: <b id="fcorte"></b></p>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="kpis" id="kpis"></div>

  <div class="grid">
    <div class="panel full">
      <h2>Radicado · Pagado · Saldo por entidad <span class="tag" id="tag-ent"></span></h2>
      <div class="bars-h" id="bars-entidad"></div>
      <div class="legend">
        <span><i style="background:var(--green)"></i>Pagado</span>
        <span><i style="background:var(--rose)"></i>Glosado / Devuelto</span>
        <span><i style="background:var(--blue2)"></i>En trámite (por pagar)</span>
      </div>
    </div>

    <div class="panel">
      <h2>Estado de cartera</h2>
      <div id="donut-cartera"></div>
    </div>
    <div class="panel">
      <h2>Estado de radicación <span class="tag">ayuda a radicar</span></h2>
      <div id="donut-radicacion"></div>
    </div>

    <div class="panel">
      <h2>Mora de la cartera (aging) <span class="tag">saldo por días</span></h2>
      <div id="aging"></div>
    </div>
    <div class="panel">
      <h2>Tendencia mensual <span class="tag">radicado vs pagado</span></h2>
      <div id="tendencia"></div>
    </div>

    <div class="panel full">
      <h2>Top motivos de glosa / devolución</h2>
      <div id="motivos"></div>
    </div>

    <div class="panel full">
      <h2>Detalle por factura <span class="tag" id="tag-tabla"></span></h2>
      <div class="toolbar">
        <input id="q" placeholder="Buscar factura, entidad, motivo…">
        <select id="f-ent"><option value="">Todas las entidades</option></select>
        <select id="f-car"><option value="">Todos los estados de cartera</option></select>
      </div>
      <div class="tablewrap">
        <table id="tabla">
          <thead><tr id="thead"></tr></thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="foot">Generado por el Tablero de Radicación y Cartera · ESE Hospital Universitario de Santander · __FECHA__</div>
</div>

<script>
const DATA = __DATA__;

/* ── formato ── */
const fmtCOP = n => "$ " + Math.round(n||0).toLocaleString("es-CO");
const fmtShort = n => {
  n = n||0; const a = Math.abs(n);
  if(a>=1e9) return "$ "+(n/1e9).toFixed(1).replace(".",",")+" mil M";
  if(a>=1e6) return "$ "+(n/1e6).toFixed(1).replace(".",",")+" M";
  if(a>=1e3) return "$ "+(n/1e3).toFixed(0)+" K";
  return "$ "+Math.round(n);
};
const pct = n => (n||0).toFixed(1).replace(".",",")+"%";

const COL_CARTERA = {
  PAGADA:"#16a34a", PAGO_PARCIAL:"#3b82f6", RADICADA_TRAMITE:"#6366f1",
  GLOSADA_DEVUELTA:"#e11d48", PENDIENTE_RADICAR:"#d97706"
};
const COL_RAD = {
  LISTA:"#16a34a", REVISAR_TIPIFICACION:"#d97706", FALTAN_SOPORTES:"#e11d48",
  SIN_CUV:"#e11d48", SIN_RIPS:"#e11d48", SIN_FEV:"#e11d48",
  ENTIDAD_NO_RESUELTA:"#ea580c", PARTICULAR:"#94a3b8", "—":"#cbd5e1"
};
const LBL_CARTERA = {
  PAGADA:"Pagada", PAGO_PARCIAL:"Pago parcial", RADICADA_TRAMITE:"Radicada (en trámite)",
  GLOSADA_DEVUELTA:"Glosada / Devuelta", PENDIENTE_RADICAR:"Pendiente por radicar"
};
const colCartera = k => COL_CARTERA[k]||"#94a3b8";
const lblCartera = k => LBL_CARTERA[k]||k;
const colRad = k => COL_RAD[k]||"#94a3b8";

/* ── KPIs ── */
function renderKPIs(){
  const k = DATA.kpis;
  const cards = [
    {lbl:"Facturas radicadas", val:(k.n_facturas).toLocaleString("es-CO"), hint:k.n_listas+" listas", acc:"var(--navy)"},
    {lbl:"Valor radicado", val:fmtShort(k.radicado), hint:fmtCOP(k.radicado), acc:"var(--blue)"},
    {lbl:"Pagado", val:fmtShort(k.pagado), hint:pct(k.pct_recaudo)+" de recaudo", acc:"var(--green)"},
    {lbl:"Glosado / Devuelto", val:fmtShort(k.glosado+k.devuelto), hint:pct(k.pct_glosa)+" del radicado", acc:"var(--rose)"},
    {lbl:"Saldo (debiendo)", val:fmtShort(k.saldo), hint:k.n_glosadas+" con glosa", acc:"var(--amber)"},
  ];
  document.getElementById("kpis").innerHTML = cards.map(c=>
    `<div class="kpi" style="--accent:${c.acc}">
       <div class="lbl">${c.lbl}</div><div class="val">${c.val}</div><div class="hint">${c.hint}</div>
     </div>`).join("");
}

/* ── barras horizontales apiladas por entidad ── */
function renderEntidades(){
  const ents = DATA.entidades.slice(0,12);
  const max = Math.max(1, ...ents.map(e=>e.radicado));
  document.getElementById("tag-ent").textContent = DATA.entidades.length+" entidades";
  document.getElementById("bars-entidad").innerHTML = ents.map(e=>{
    const tram = Math.max(0, e.saldo-(e.glosado+e.devuelto));
    const w = v => (100*v/max).toFixed(2)+"%";
    return `<div class="barow"><div>
        <div class="nm" title="${e.entidad}">${e.entidad}</div>
        <div class="amt">${fmtShort(e.radicado)} · ${pct(e.pct_recaudo)} recaudo</div>
      </div>
      <div class="track" title="${e.entidad}\nRadicado ${fmtCOP(e.radicado)}\nPagado ${fmtCOP(e.pagado)}\nGlosa/Dev ${fmtCOP(e.glosado+e.devuelto)}\nEn trámite ${fmtCOP(tram)}">
        <div class="seg" style="width:${w(e.pagado)};background:var(--green)"></div>
        <div class="seg" style="width:${w(e.glosado+e.devuelto)};background:var(--rose)"></div>
        <div class="seg" style="width:${w(tram)};background:var(--blue2)"></div>
      </div></div>`;
  }).join("") || '<div class="empty">Sin datos de radicación.</div>';
}

/* ── donut SVG ── */
function donut(elId, entries){
  entries = entries.filter(e=>e.value>0);
  const total = entries.reduce((s,e)=>s+e.value,0);
  const el = document.getElementById(elId);
  if(!total){ el.innerHTML='<div class="empty">Sin datos.</div>'; return; }
  const R=70,r=44,cx=90,cy=90; let a=-Math.PI/2; const arcs=[];
  entries.forEach(e=>{
    const frac=e.value/total, a2=a+frac*2*Math.PI, big=frac>.5?1:0;
    const x1=cx+R*Math.cos(a),y1=cy+R*Math.sin(a),x2=cx+R*Math.cos(a2),y2=cy+R*Math.sin(a2);
    const xi=cx+r*Math.cos(a2),yi=cy+r*Math.sin(a2),xi2=cx+r*Math.cos(a),yi2=cy+r*Math.sin(a);
    arcs.push(`<path d="M${x1} ${y1} A${R} ${R} 0 ${big} 1 ${x2} ${y2} L${xi} ${yi} A${r} ${r} 0 ${big} 0 ${xi2} ${yi2} Z" fill="${e.color}"><title>${e.label}: ${e.value} (${(100*frac).toFixed(1)}%)</title></path>`);
    a=a2;
  });
  const leg = entries.map(e=>`<span><i style="background:${e.color}"></i>${e.label} · <b>${e.value}</b></span>`).join("");
  el.innerHTML = `<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <svg width="180" height="180" viewBox="0 0 180 180">${arcs.join("")}
      <text x="90" y="86" text-anchor="middle" font-size="22" font-weight="800" fill="#0f172a">${total}</text>
      <text x="90" y="104" text-anchor="middle" font-size="11" fill="#64748b">facturas</text></svg>
    <div class="legend" style="flex-direction:column;gap:7px">${leg}</div></div>`;
}

/* ── aging: barras verticales ── */
function renderAging(){
  const ag = DATA.aging, names=Object.keys(ag), max=Math.max(1,...Object.values(ag));
  const cols={"0-30":"#16a34a","31-60":"#3b82f6","61-90":"#d97706","+90":"#e11d48"};
  const W=480,H=200,pad=34,bw=70, gap=(W-2*pad-bw*names.length)/(names.length-1||1);
  const bars=names.map((n,i)=>{
    const v=ag[n], h=(H-pad-24)*(v/max), x=pad+i*(bw+gap), y=H-pad-h;
    return `<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="6" fill="${cols[n]||'#3b82f6'}"><title>${n} días: ${fmtCOP(v)}</title></rect>
      <text x="${x+bw/2}" y="${y-7}" text-anchor="middle" font-size="11" font-weight="700" fill="#0f172a">${fmtShort(v)}</text>
      <text x="${x+bw/2}" y="${H-pad+16}" text-anchor="middle" font-size="11" fill="#64748b">${n} días</text>`;
  }).join("");
  const tot=Object.values(ag).reduce((s,v)=>s+v,0);
  document.getElementById("aging").innerHTML = tot?
    `<svg width="100%" viewBox="0 0 ${W} ${H}"><line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="#e2e8f0"/>${bars}</svg>`
    : '<div class="empty">Sin saldos en mora (cargá fechas y pagos en el seguimiento).</div>';
}

/* ── tendencia mensual: barras agrupadas ── */
function renderTendencia(){
  const ms=DATA.meses; if(!ms.length){document.getElementById("tendencia").innerHTML='<div class="empty">Sin fechas de radicación cargadas.</div>';return;}
  const max=Math.max(1,...ms.map(m=>Math.max(m.radicado,m.pagado)));
  const W=480,H=210,pad=34,gw=(W-2*pad)/ms.length,bw=Math.min(20,gw/2.6);
  const bars=ms.map((m,i)=>{
    const xc=pad+i*gw+gw/2;
    const hr=(H-pad-24)*(m.radicado/max), hp=(H-pad-24)*(m.pagado/max);
    return `<rect x="${xc-bw-2}" y="${H-pad-hr}" width="${bw}" height="${hr}" rx="4" fill="#2563eb"><title>${m.mes} radicado ${fmtCOP(m.radicado)}</title></rect>
      <rect x="${xc+2}" y="${H-pad-hp}" width="${bw}" height="${hp}" rx="4" fill="#16a34a"><title>${m.mes} pagado ${fmtCOP(m.pagado)}</title></rect>
      <text x="${xc}" y="${H-pad+16}" text-anchor="middle" font-size="10" fill="#64748b">${m.mes.slice(2)}</text>`;
  }).join("");
  document.getElementById("tendencia").innerHTML =
    `<svg width="100%" viewBox="0 0 ${W} ${H}"><line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="#e2e8f0"/>${bars}</svg>
     <div class="legend"><span><i style="background:#2563eb"></i>Radicado</span><span><i style="background:#16a34a"></i>Pagado</span></div>`;
}

/* ── motivos de glosa ── */
function renderMotivos(){
  const mo=DATA.motivos; if(!mo.length){document.getElementById("motivos").innerHTML='<div class="empty">Aún no se registran glosas con motivo en el seguimiento.</div>';return;}
  const max=Math.max(1,...mo.map(m=>m.valor));
  document.getElementById("motivos").innerHTML = `<div class="bars-h">`+mo.map(m=>
    `<div class="barow"><div><div class="nm" title="${m.motivo}">${m.motivo}</div><div class="amt">${m.n} factura(s)</div></div>
     <div class="track"><div class="seg" style="width:${(100*m.valor/max).toFixed(1)}%;background:linear-gradient(90deg,#e11d48,#fb7185)"></div>
     <span style="position:absolute;right:8px;top:3px;font-size:11px;font-weight:700;color:#334155">${fmtShort(m.valor)}</span></div></div>`
  ).join("")+`</div>`;
}

/* ── tabla por factura ── */
const COLS=[
  {k:"factura",t:"Factura"},{k:"entidad",t:"Entidad"},
  {k:"radicado",t:"Radicado",n:1},{k:"glosado",t:"Glosa/Dev",n:1},
  {k:"pagado",t:"Pagado",n:1},{k:"saldo",t:"Saldo",n:1},
  {k:"pct_recaudo",t:"% Rec.",n:1},{k:"dias_mora",t:"Mora",n:1},
  {k:"estado_cartera",t:"Cartera"},{k:"estado_radicacion",t:"Radicación"},
  {k:"motivo_glosa",t:"Motivo"}
];
let sortK="saldo",sortDir=-1;
function pintaTabla(){
  const q=document.getElementById("q").value.toLowerCase();
  const fe=document.getElementById("f-ent").value, fc=document.getElementById("f-car").value;
  let rows=DATA.facturas.filter(f=>{
    if(fe&&f.entidad!==fe)return false;
    if(fc&&f.estado_cartera!==fc)return false;
    if(q&&!(f.factura+" "+f.entidad+" "+(f.motivo_glosa||"")).toLowerCase().includes(q))return false;
    return true;
  });
  rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(typeof x==="string"){x=x||"";y=y||"";return sortDir*x.localeCompare(y);}return sortDir*((x||0)-(y||0));});
  document.getElementById("thead").innerHTML=COLS.map(c=>`<th class="${c.n?'num':''}" data-k="${c.k}">${c.t}${sortK===c.k?(sortDir<0?" ▾":" ▴"):""}</th>`).join("");
  document.getElementById("tbody").innerHTML = rows.length? rows.map(f=>{
    const td=(v,n)=>`<td class="${n?'num':''}">${v}</td>`;
    return `<tr>
      ${td(f.factura)}${td(f.entidad)}
      ${td(fmtShort(f.radicado),1)}${td(f.glosado+f.devuelto?fmtShort(f.glosado+f.devuelto):"—",1)}
      ${td(f.pagado?fmtShort(f.pagado):"—",1)}${td(fmtShort(f.saldo),1)}
      ${td(pct(f.pct_recaudo),1)}${td(f.dias_mora==null?"—":f.dias_mora,1)}
      <td><span class="badge" style="background:${colCartera(f.estado_cartera)}22;color:${colCartera(f.estado_cartera)}">${lblCartera(f.estado_cartera)}</span></td>
      <td><span class="badge" style="background:${colRad(f.estado_radicacion)}22;color:${colRad(f.estado_radicacion)}">${f.estado_radicacion||"—"}</span></td>
      ${td(f.motivo_glosa||"—")}
    </tr>`;
  }).join("") : `<tr><td colspan="${COLS.length}" class="empty">Sin facturas para el filtro.</td></tr>`;
  document.getElementById("tag-tabla").textContent=rows.length+" / "+DATA.facturas.length+" facturas";
}

/* ── init ── */
function init(){
  document.getElementById("fcorte").textContent=DATA.generado;
  renderKPIs(); renderEntidades(); renderAging(); renderTendencia(); renderMotivos();
  donut("donut-cartera", Object.entries(DATA.estados_cartera).map(([k,v])=>({label:lblCartera(k),value:v,color:colCartera(k)})));
  donut("donut-radicacion", Object.entries(DATA.estados_radicacion).map(([k,v])=>({label:k,value:v,color:colRad(k)})));
  const fe=document.getElementById("f-ent");
  [...new Set(DATA.facturas.map(f=>f.entidad))].sort().forEach(e=>fe.add(new Option(e,e)));
  const fc=document.getElementById("f-car");
  [...new Set(DATA.facturas.map(f=>f.estado_cartera))].sort().forEach(e=>fc.add(new Option(lblCartera(e),e)));
  ["q"].forEach(id=>document.getElementById(id).addEventListener("input",pintaTabla));
  ["f-ent","f-car"].forEach(id=>document.getElementById(id).addEventListener("change",pintaTabla));
  document.getElementById("thead").addEventListener("click",e=>{
    const k=e.target.dataset.k; if(!k)return; if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=-1;} pintaTabla();
  });
  pintaTabla();
}
init();
</script>
</body>
</html>
"""


def render_html(datos: dict) -> str:
    payload = json.dumps(datos, ensure_ascii=False)
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        _PLANTILLA.replace("__DATA__", payload)
        .replace("__TITULO__", str(datos.get("titulo", "Tablero de Cartera — ESE HUS")))
        .replace("__FECHA__", fecha)
    )
