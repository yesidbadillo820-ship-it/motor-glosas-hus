// Panel de Domicilios — SPA admin
const TOKEN = localStorage.getItem('token');
const USER = JSON.parse(localStorage.getItem('usuario') || 'null');
if (!TOKEN || !USER) { window.location.href = '/login'; }

document.getElementById('userBadge').textContent = `${USER.nombre} · ${USER.rol}`;
document.getElementById('logoutBtn').addEventListener('click', () => {
  localStorage.clear();
  window.location.href = '/login';
});

const fmt = n => new Intl.NumberFormat('es-CO', {style:'currency', currency:'COP', maximumFractionDigits:0}).format(n||0);
const fmtN = n => new Intl.NumberFormat('es-CO').format(n||0);
const fmtDate = s => s ? new Date(s).toLocaleString('es-CO', {dateStyle:'short', timeStyle:'short'}) : '—';

async function api(path, opts = {}) {
  const headers = {'Content-Type':'application/json', 'Authorization': `Bearer ${TOKEN}`, ...(opts.headers||{})};
  const res = await fetch(path, {...opts, headers});
  if (res.status === 401) { localStorage.clear(); window.location.href='/login'; throw new Error('no-auth'); }
  if (!res.ok) {
    const j = await res.json().catch(()=>({}));
    throw new Error(j.detail || `Error ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

const toast = (msg, kind='info') => {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `fixed bottom-6 right-6 text-white px-4 py-2 rounded-lg shadow-lg z-50 ${
    kind==='error' ? 'bg-red-600' : kind==='ok' ? 'bg-green-600' : 'bg-slate-800'
  }`;
  el.classList.remove('hidden');
  setTimeout(()=>el.classList.add('hidden'), 2800);
};

const openModal = (title, html) => {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = html;
  document.getElementById('modal').classList.remove('hidden');
  document.getElementById('modal').classList.add('flex');
};
const closeModal = () => {
  document.getElementById('modal').classList.add('hidden');
  document.getElementById('modal').classList.remove('flex');
};
window.closeModal = closeModal;

// Routing
const views = ['dashboard','pedidos','repartidores','clientes','comercios','zonas'];
const renderers = {};
function showView(name) {
  views.forEach(v => document.getElementById('view-'+v).classList.toggle('hidden', v!==name));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view===name));
  if (renderers[name]) renderers[name]();
}
document.querySelectorAll('.nav-btn').forEach(b => b.addEventListener('click', ()=>showView(b.dataset.view)));

// ============ DASHBOARD ============
renderers.dashboard = async () => {
  const c = document.getElementById('view-dashboard');
  c.innerHTML = '<div class="text-slate-500">Cargando…</div>';
  try {
    const m = await api('/api/dashboard/metricas');
    const card = (lbl, val, cls='') => `
      <div class="bg-white rounded-xl shadow-sm p-4 ${cls}">
        <div class="text-xs uppercase tracking-wide text-slate-500">${lbl}</div>
        <div class="text-2xl font-bold mt-1 text-slate-800">${val}</div>
      </div>`;
    c.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        ${card('Pedidos hoy', fmtN(m.pedidos_hoy))}
        ${card('Pendientes', `<span class="text-amber-600">${fmtN(m.pendientes)}</span>`)}
        ${card('En ruta', `<span class="text-indigo-600">${fmtN(m.en_ruta)}</span>`)}
        ${card('Entregados hoy', `<span class="text-green-600">${fmtN(m.entregados_hoy)}</span>`)}
        ${card('Repartidores disponibles', `${m.repartidores_disponibles} / ${m.repartidores_total}`)}
        ${card('Cancelados hoy', `<span class="text-red-600">${fmtN(m.cancelados_hoy)}</span>`)}
        ${card('Ingresos hoy', fmt(m.ingresos_hoy))}
        ${card('Ticket promedio', fmt(m.ticket_promedio_hoy))}
      </div>

      <div class="grid md:grid-cols-2 gap-4">
        <div class="bg-white rounded-xl shadow-sm p-5">
          <h3 class="font-semibold text-slate-800 mb-3">Top repartidores hoy</h3>
          ${m.top_repartidores_hoy.length === 0
            ? '<p class="text-slate-400 text-sm">Sin entregas registradas hoy.</p>'
            : `<table class="w-full text-sm">
                <thead><tr class="text-left text-slate-500 border-b">
                  <th class="py-2">Repartidor</th><th>Entregas</th><th>Comisiones</th>
                </tr></thead>
                <tbody>${m.top_repartidores_hoy.map(r => `
                  <tr class="border-b last:border-0">
                    <td class="py-2">${r.repartidor}</td>
                    <td>${r.entregas}</td>
                    <td>${fmt(r.comisiones)}</td>
                  </tr>`).join('')}
                </tbody></table>`}
        </div>
        <div class="bg-white rounded-xl shadow-sm p-5">
          <h3 class="font-semibold text-slate-800 mb-3">Pedidos por zona (hoy)</h3>
          ${m.pedidos_por_zona.length === 0
            ? '<p class="text-slate-400 text-sm">Sin pedidos por zona hoy.</p>'
            : m.pedidos_por_zona.map(z => `
              <div class="flex items-center gap-3 py-1">
                <div class="w-32 text-sm text-slate-700 truncate">${z.zona}</div>
                <div class="flex-1 bg-slate-100 rounded h-3 overflow-hidden">
                  <div class="bg-blue-500 h-3" style="width:${Math.min(100, z.pedidos*10)}%"></div>
                </div>
                <div class="w-10 text-right text-sm font-semibold">${z.pedidos}</div>
              </div>`).join('')}
        </div>
      </div>`;
  } catch (e) { c.innerHTML = `<div class="text-red-600">${e.message}</div>`; }
};

// ============ PEDIDOS ============
let estadoFiltro = '';
renderers.pedidos = async () => {
  const c = document.getElementById('view-pedidos');
  c.innerHTML = '<div class="text-slate-500">Cargando…</div>';
  try {
    const url = estadoFiltro ? `/api/pedidos?estado=${estadoFiltro}` : '/api/pedidos';
    const pedidos = await api(url);
    const filtros = ['','PENDIENTE','ASIGNADO','EN_RUTA','ENTREGADO','CANCELADO'];
    c.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div class="flex flex-wrap gap-2">
          ${filtros.map(f => `
            <button data-f="${f}" class="filtro-btn px-3 py-1.5 rounded-lg text-sm ${estadoFiltro===f?'bg-blue-600 text-white':'bg-white text-slate-700 hover:bg-slate-100'}">
              ${f || 'Todos'}
            </button>`).join('')}
        </div>
        <button onclick="formPedido()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-semibold">+ Nuevo pedido</button>
      </div>

      <div class="bg-white rounded-xl shadow-sm overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-slate-600 text-left">
            <tr>
              <th class="px-3 py-2">Código</th>
              <th class="px-3 py-2">Cliente</th>
              <th class="px-3 py-2">Comercio</th>
              <th class="px-3 py-2">Dirección</th>
              <th class="px-3 py-2">Repartidor</th>
              <th class="px-3 py-2">Total</th>
              <th class="px-3 py-2">Estado</th>
              <th class="px-3 py-2">Creado</th>
              <th class="px-3 py-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${pedidos.length === 0
              ? '<tr><td colspan="9" class="text-center py-8 text-slate-400">Sin pedidos para mostrar.</td></tr>'
              : pedidos.map(p => `
                <tr class="border-t hover:bg-slate-50">
                  <td class="px-3 py-2 font-mono text-xs">${p.codigo}</td>
                  <td class="px-3 py-2">
                    <div class="font-medium">${p.cliente_nombre||'—'}</div>
                    <div class="text-xs text-slate-500">${p.cliente_telefono||''}</div>
                  </td>
                  <td class="px-3 py-2">${p.comercio_nombre||'—'}</td>
                  <td class="px-3 py-2 text-xs max-w-[180px] truncate" title="${p.direccion_entrega}">${p.direccion_entrega}</td>
                  <td class="px-3 py-2">${p.repartidor_nombre||'<span class="text-slate-400">Sin asignar</span>'}</td>
                  <td class="px-3 py-2 font-semibold">${fmt(p.total)}</td>
                  <td class="px-3 py-2"><span class="badge b-${p.estado}">${p.estado}</span></td>
                  <td class="px-3 py-2 text-xs text-slate-500">${fmtDate(p.creado_en)}</td>
                  <td class="px-3 py-2">
                    <div class="flex gap-1">
                      ${p.estado!=='ENTREGADO' && p.estado!=='CANCELADO' ? `<button onclick="asignarPedido(${p.id})" class="text-blue-600 hover:underline text-xs">Asignar</button>` : ''}
                      ${p.estado==='ASIGNADO' ? `<button onclick="cambiarEstado(${p.id},'EN_RUTA')" class="text-indigo-600 hover:underline text-xs">→ Ruta</button>` : ''}
                      ${p.estado==='EN_RUTA' ? `<button onclick="cambiarEstado(${p.id},'ENTREGADO')" class="text-green-600 hover:underline text-xs">Entregar</button>` : ''}
                      ${p.estado!=='ENTREGADO' && p.estado!=='CANCELADO' ? `<button onclick="cancelarPedido(${p.id})" class="text-red-600 hover:underline text-xs">Cancelar</button>` : ''}
                    </div>
                  </td>
                </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    document.querySelectorAll('.filtro-btn').forEach(b => b.addEventListener('click', ()=>{
      estadoFiltro = b.dataset.f; renderers.pedidos();
    }));
  } catch (e) { c.innerHTML = `<div class="text-red-600">${e.message}</div>`; }
};

window.formPedido = async () => {
  const [clientes, comercios, zonas] = await Promise.all([
    api('/api/clientes'), api('/api/comercios'), api('/api/zonas'),
  ]);
  if (clientes.length === 0) {
    return toast('Crea primero un cliente en la pestaña Clientes', 'error');
  }
  openModal('Nuevo pedido', `
    <form id="frmPedido" class="space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs text-slate-600 mb-1">Cliente *</label>
          <select name="cliente_id" required class="w-full border rounded px-2 py-2 text-sm">
            ${clientes.map(c => `<option value="${c.id}">${c.nombre} — ${c.telefono}</option>`).join('')}
          </select>
        </div>
        <div>
          <label class="block text-xs text-slate-600 mb-1">Comercio</label>
          <select name="comercio_id" class="w-full border rounded px-2 py-2 text-sm">
            <option value="">— Sin comercio —</option>
            ${comercios.map(c => `<option value="${c.id}">${c.nombre}</option>`).join('')}
          </select>
        </div>
        <div class="col-span-2">
          <label class="block text-xs text-slate-600 mb-1">Descripción del pedido *</label>
          <textarea name="descripcion" required rows="2" class="w-full border rounded px-2 py-2 text-sm" placeholder="Ej: 2 hamburguesas, 1 gaseosa"></textarea>
        </div>
        <div class="col-span-2">
          <label class="block text-xs text-slate-600 mb-1">Dirección de entrega *</label>
          <input name="direccion_entrega" required class="w-full border rounded px-2 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-slate-600 mb-1">Teléfono</label>
          <input name="telefono_entrega" class="w-full border rounded px-2 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-slate-600 mb-1">Zona</label>
          <select name="zona_id" class="w-full border rounded px-2 py-2 text-sm">
            <option value="">— Selecciona —</option>
            ${zonas.map(z => `<option value="${z.id}" data-tarifa="${z.tarifa_base}">${z.nombre} (${fmt(z.tarifa_base)})</option>`).join('')}
          </select>
        </div>
        <div>
          <label class="block text-xs text-slate-600 mb-1">Valor productos</label>
          <input name="valor_productos" type="number" min="0" step="100" value="0" class="w-full border rounded px-2 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-slate-600 mb-1">Costo de envío</label>
          <input name="costo_envio" type="number" min="0" step="100" value="0" class="w-full border rounded px-2 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-slate-600 mb-1">Método de pago</label>
          <select name="metodo_pago" class="w-full border rounded px-2 py-2 text-sm">
            <option>EFECTIVO</option><option>TRANSFERENCIA</option><option>TARJETA</option>
          </select>
        </div>
        <div class="col-span-2">
          <label class="block text-xs text-slate-600 mb-1">Notas</label>
          <input name="notas" class="w-full border rounded px-2 py-2 text-sm" />
        </div>
      </div>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" onclick="closeModal()" class="px-4 py-2 text-sm rounded bg-slate-200 hover:bg-slate-300">Cancelar</button>
        <button class="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white font-semibold">Crear</button>
      </div>
    </form>`);
  document.getElementById('frmPedido').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    const body = {
      cliente_id: parseInt(fd.cliente_id),
      comercio_id: fd.comercio_id ? parseInt(fd.comercio_id) : null,
      zona_id: fd.zona_id ? parseInt(fd.zona_id) : null,
      descripcion: fd.descripcion,
      direccion_entrega: fd.direccion_entrega,
      telefono_entrega: fd.telefono_entrega || null,
      notas: fd.notas || null,
      valor_productos: parseFloat(fd.valor_productos)||0,
      costo_envio: parseFloat(fd.costo_envio)||0,
      metodo_pago: fd.metodo_pago,
    };
    try {
      await api('/api/pedidos', {method:'POST', body: JSON.stringify(body)});
      closeModal();
      toast('Pedido creado','ok');
      renderers.pedidos();
    } catch (err) { toast(err.message, 'error'); }
  });
  // autofill costo envío al cambiar zona
  document.querySelector('select[name=zona_id]').addEventListener('change', e => {
    const opt = e.target.selectedOptions[0];
    const tarifa = opt?.dataset.tarifa;
    const ce = document.querySelector('input[name=costo_envio]');
    if (tarifa && (!ce.value || ce.value === '0')) ce.value = tarifa;
  });
};

window.asignarPedido = async (pid) => {
  const reps = await api('/api/repartidores?solo_activos=true');
  if (reps.length === 0) return toast('No hay repartidores. Crea uno primero.','error');
  openModal('Asignar repartidor', `
    <form id="frmAsig" class="space-y-3">
      <select name="repartidor_id" required class="w-full border rounded px-2 py-2">
        ${reps.map(r => `<option value="${r.id}">${r.nombre} — ${r.vehiculo}${r.disponible?' ✅':' ⛔'}</option>`).join('')}
      </select>
      <div class="flex justify-end gap-2">
        <button type="button" onclick="closeModal()" class="px-4 py-2 text-sm rounded bg-slate-200">Cancelar</button>
        <button class="px-4 py-2 text-sm rounded bg-blue-600 text-white">Asignar</button>
      </div>
    </form>`);
  document.getElementById('frmAsig').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    try {
      await api(`/api/pedidos/${pid}/asignar`, {method:'POST', body: JSON.stringify({repartidor_id: parseInt(fd.repartidor_id)})});
      closeModal(); toast('Repartidor asignado','ok'); renderers.pedidos();
    } catch (err) { toast(err.message,'error'); }
  });
};

window.cambiarEstado = async (pid, estado) => {
  try {
    await api(`/api/pedidos/${pid}/estado`, {method:'POST', body: JSON.stringify({estado})});
    toast(`Pedido → ${estado}`,'ok'); renderers.pedidos();
  } catch (err) { toast(err.message,'error'); }
};

window.cancelarPedido = async (pid) => {
  const motivo = prompt('Motivo de cancelación (opcional):') || '';
  try {
    await api(`/api/pedidos/${pid}/estado`, {method:'POST', body: JSON.stringify({estado:'CANCELADO', motivo})});
    toast('Pedido cancelado','ok'); renderers.pedidos();
  } catch (err) { toast(err.message,'error'); }
};

// ============ REPARTIDORES ============
renderers.repartidores = async () => {
  const c = document.getElementById('view-repartidores');
  c.innerHTML = '<div class="text-slate-500">Cargando…</div>';
  try {
    const reps = await api('/api/repartidores');
    c.innerHTML = `
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-xl font-bold text-slate-800">Repartidores (${reps.length})</h2>
        <button onclick="formRepartidor()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-semibold">+ Nuevo</button>
      </div>
      <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
        ${reps.length===0 ? '<p class="text-slate-400">Sin repartidores aún.</p>' : reps.map(r => `
          <div class="bg-white rounded-xl shadow-sm p-4">
            <div class="flex items-center justify-between mb-2">
              <h3 class="font-bold text-slate-800">${r.nombre}</h3>
              <span class="text-xs ${r.disponible?'text-green-600':'text-slate-400'}">${r.disponible?'● Disponible':'● Ocupado'}</span>
            </div>
            <p class="text-sm text-slate-600">📞 ${r.telefono}</p>
            <p class="text-sm text-slate-600">🛵 ${r.vehiculo}${r.placa?` · ${r.placa}`:''}</p>
            <div class="flex gap-2 mt-3">
              <button onclick="toggleDisponible(${r.id}, ${r.disponible?0:1})" class="text-xs px-2 py-1 rounded ${r.disponible?'bg-amber-100 text-amber-700':'bg-green-100 text-green-700'}">
                ${r.disponible?'Marcar ocupado':'Marcar disponible'}
              </button>
              <button onclick="formRepartidor(${r.id})" class="text-xs px-2 py-1 rounded bg-slate-100 text-slate-700">Editar</button>
              <button onclick="eliminarRepartidor(${r.id})" class="text-xs px-2 py-1 rounded bg-red-100 text-red-700">Eliminar</button>
            </div>
          </div>`).join('')}
      </div>`;
  } catch (e) { c.innerHTML = `<div class="text-red-600">${e.message}</div>`; }
};
window.toggleDisponible = async (id, val) => {
  try {
    await api(`/api/repartidores/${id}/disponibilidad?disponible=${val}`, {method:'POST'});
    renderers.repartidores();
  } catch (err) { toast(err.message,'error'); }
};
window.eliminarRepartidor = async (id) => {
  if (!confirm('¿Eliminar este repartidor?')) return;
  try { await api(`/api/repartidores/${id}`, {method:'DELETE'}); renderers.repartidores(); }
  catch (err) { toast(err.message,'error'); }
};
window.formRepartidor = async (id=null) => {
  let r = {nombre:'', telefono:'', documento:'', vehiculo:'MOTO', placa:'', disponible:1, activo:1};
  if (id) r = (await api('/api/repartidores')).find(x=>x.id===id) || r;
  openModal(id?'Editar repartidor':'Nuevo repartidor', `
    <form id="frmRep" class="grid grid-cols-2 gap-3">
      <input name="nombre" required placeholder="Nombre *" value="${r.nombre}" class="col-span-2 border rounded px-2 py-2 text-sm" />
      <input name="telefono" required placeholder="Teléfono *" value="${r.telefono||''}" class="border rounded px-2 py-2 text-sm" />
      <input name="documento" placeholder="Documento" value="${r.documento||''}" class="border rounded px-2 py-2 text-sm" />
      <select name="vehiculo" class="border rounded px-2 py-2 text-sm">
        ${['MOTO','BICICLETA','AUTO','CAMIONETA','APIE'].map(v=>`<option ${r.vehiculo===v?'selected':''}>${v}</option>`).join('')}
      </select>
      <input name="placa" placeholder="Placa" value="${r.placa||''}" class="border rounded px-2 py-2 text-sm" />
      <div class="col-span-2 flex justify-end gap-2 pt-2">
        <button type="button" onclick="closeModal()" class="px-4 py-2 text-sm rounded bg-slate-200">Cancelar</button>
        <button class="px-4 py-2 text-sm rounded bg-blue-600 text-white">Guardar</button>
      </div>
    </form>`);
  document.getElementById('frmRep').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.disponible = 1; body.activo = 1;
    try {
      await api(id?`/api/repartidores/${id}`:'/api/repartidores',
        {method: id?'PUT':'POST', body: JSON.stringify(body)});
      closeModal(); toast('Guardado','ok'); renderers.repartidores();
    } catch (err) { toast(err.message,'error'); }
  });
};

// ============ CLIENTES ============
renderers.clientes = async () => {
  const c = document.getElementById('view-clientes');
  c.innerHTML = '<div class="text-slate-500">Cargando…</div>';
  try {
    const clientes = await api('/api/clientes');
    c.innerHTML = `
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-xl font-bold text-slate-800">Clientes (${clientes.length})</h2>
        <button onclick="formCliente()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-semibold">+ Nuevo</button>
      </div>
      <div class="bg-white rounded-xl shadow-sm overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-slate-600">
            <tr><th class="px-3 py-2">Nombre</th><th class="px-3 py-2">Teléfono</th><th class="px-3 py-2">Dirección</th><th></th></tr>
          </thead>
          <tbody>
            ${clientes.length===0 ? '<tr><td colspan="4" class="text-center py-6 text-slate-400">Sin clientes aún.</td></tr>' :
              clientes.map(c => `
                <tr class="border-t hover:bg-slate-50">
                  <td class="px-3 py-2 font-medium">${c.nombre}</td>
                  <td class="px-3 py-2">${c.telefono}</td>
                  <td class="px-3 py-2 text-xs">${c.direccion||'—'}</td>
                  <td class="px-3 py-2 text-right">
                    <button onclick="formCliente(${c.id})" class="text-blue-600 text-xs hover:underline">Editar</button>
                    <button onclick="eliminarCliente(${c.id})" class="text-red-600 text-xs hover:underline ml-2">Eliminar</button>
                  </td>
                </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) { c.innerHTML = `<div class="text-red-600">${e.message}</div>`; }
};
window.formCliente = async (id=null) => {
  let c = {nombre:'', telefono:'', direccion:'', notas:''};
  if (id) c = (await api('/api/clientes')).find(x=>x.id===id) || c;
  openModal(id?'Editar cliente':'Nuevo cliente', `
    <form id="frmCli" class="grid grid-cols-2 gap-3">
      <input name="nombre" required placeholder="Nombre *" value="${c.nombre}" class="col-span-2 border rounded px-2 py-2 text-sm" />
      <input name="telefono" required placeholder="Teléfono *" value="${c.telefono}" class="border rounded px-2 py-2 text-sm" />
      <input name="direccion" placeholder="Dirección" value="${c.direccion||''}" class="border rounded px-2 py-2 text-sm" />
      <textarea name="notas" rows="2" placeholder="Notas" class="col-span-2 border rounded px-2 py-2 text-sm">${c.notas||''}</textarea>
      <div class="col-span-2 flex justify-end gap-2">
        <button type="button" onclick="closeModal()" class="px-4 py-2 text-sm rounded bg-slate-200">Cancelar</button>
        <button class="px-4 py-2 text-sm rounded bg-blue-600 text-white">Guardar</button>
      </div>
    </form>`);
  document.getElementById('frmCli').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target).entries());
    try {
      await api(id?`/api/clientes/${id}`:'/api/clientes',
        {method: id?'PUT':'POST', body: JSON.stringify(body)});
      closeModal(); toast('Guardado','ok'); renderers.clientes();
    } catch (err) { toast(err.message,'error'); }
  });
};
window.eliminarCliente = async (id) => {
  if (!confirm('¿Eliminar este cliente?')) return;
  try { await api(`/api/clientes/${id}`, {method:'DELETE'}); renderers.clientes(); }
  catch (err) { toast(err.message,'error'); }
};

// ============ COMERCIOS ============
renderers.comercios = async () => {
  const c = document.getElementById('view-comercios');
  c.innerHTML = '<div class="text-slate-500">Cargando…</div>';
  try {
    const list = await api('/api/comercios');
    c.innerHTML = `
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-xl font-bold text-slate-800">Comercios (${list.length})</h2>
        <button onclick="formComercio()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-semibold">+ Nuevo</button>
      </div>
      <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
        ${list.length===0 ? '<p class="text-slate-400">Sin comercios.</p>' : list.map(co => `
          <div class="bg-white rounded-xl shadow-sm p-4">
            <h3 class="font-bold text-slate-800">${co.nombre}</h3>
            <p class="text-xs text-slate-500">${co.categoria||''}</p>
            <p class="text-sm text-slate-600 mt-1">📍 ${co.direccion||'—'}</p>
            <p class="text-sm text-slate-600">📞 ${co.telefono||'—'}</p>
            <div class="flex gap-2 mt-3">
              <button onclick="formComercio(${co.id})" class="text-xs px-2 py-1 rounded bg-slate-100 text-slate-700">Editar</button>
              <button onclick="eliminarComercio(${co.id})" class="text-xs px-2 py-1 rounded bg-red-100 text-red-700">Eliminar</button>
            </div>
          </div>`).join('')}
      </div>`;
  } catch (e) { c.innerHTML = `<div class="text-red-600">${e.message}</div>`; }
};
window.formComercio = async (id=null) => {
  let co = {nombre:'', categoria:'', direccion:'', telefono:'', activo:1};
  if (id) co = (await api('/api/comercios')).find(x=>x.id===id) || co;
  openModal(id?'Editar comercio':'Nuevo comercio', `
    <form id="frmCom" class="grid grid-cols-2 gap-3">
      <input name="nombre" required placeholder="Nombre *" value="${co.nombre}" class="col-span-2 border rounded px-2 py-2 text-sm" />
      <input name="categoria" placeholder="Categoría (Restaurante, Tienda…)" value="${co.categoria||''}" class="border rounded px-2 py-2 text-sm" />
      <input name="telefono" placeholder="Teléfono" value="${co.telefono||''}" class="border rounded px-2 py-2 text-sm" />
      <input name="direccion" placeholder="Dirección" value="${co.direccion||''}" class="col-span-2 border rounded px-2 py-2 text-sm" />
      <div class="col-span-2 flex justify-end gap-2">
        <button type="button" onclick="closeModal()" class="px-4 py-2 text-sm rounded bg-slate-200">Cancelar</button>
        <button class="px-4 py-2 text-sm rounded bg-blue-600 text-white">Guardar</button>
      </div>
    </form>`);
  document.getElementById('frmCom').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.activo = 1;
    try {
      await api(id?`/api/comercios/${id}`:'/api/comercios',
        {method: id?'PUT':'POST', body: JSON.stringify(body)});
      closeModal(); toast('Guardado','ok'); renderers.comercios();
    } catch (err) { toast(err.message,'error'); }
  });
};
window.eliminarComercio = async (id) => {
  if (!confirm('¿Eliminar este comercio?')) return;
  try { await api(`/api/comercios/${id}`, {method:'DELETE'}); renderers.comercios(); }
  catch (err) { toast(err.message,'error'); }
};

// ============ ZONAS ============
renderers.zonas = async () => {
  const c = document.getElementById('view-zonas');
  c.innerHTML = '<div class="text-slate-500">Cargando…</div>';
  try {
    const zonas = await api('/api/zonas');
    c.innerHTML = `
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-xl font-bold text-slate-800">Zonas y tarifas (${zonas.length})</h2>
        <button onclick="formZona()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-semibold">+ Nueva</button>
      </div>
      <div class="bg-white rounded-xl shadow-sm overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-slate-600">
            <tr><th class="px-3 py-2">Zona</th><th class="px-3 py-2">Tarifa base</th><th class="px-3 py-2">Descripción</th><th></th></tr>
          </thead>
          <tbody>
            ${zonas.length===0 ? '<tr><td colspan="4" class="text-center py-6 text-slate-400">Sin zonas.</td></tr>' :
              zonas.map(z => `
                <tr class="border-t hover:bg-slate-50">
                  <td class="px-3 py-2 font-medium">${z.nombre}</td>
                  <td class="px-3 py-2 font-semibold">${fmt(z.tarifa_base)}</td>
                  <td class="px-3 py-2 text-xs text-slate-500">${z.descripcion||''}</td>
                  <td class="px-3 py-2 text-right">
                    <button onclick="formZona(${z.id})" class="text-blue-600 text-xs hover:underline">Editar</button>
                    <button onclick="eliminarZona(${z.id})" class="text-red-600 text-xs hover:underline ml-2">Eliminar</button>
                  </td>
                </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) { c.innerHTML = `<div class="text-red-600">${e.message}</div>`; }
};
window.formZona = async (id=null) => {
  let z = {nombre:'', tarifa_base:0, descripcion:'', activa:1};
  if (id) z = (await api('/api/zonas')).find(x=>x.id===id) || z;
  openModal(id?'Editar zona':'Nueva zona', `
    <form id="frmZona" class="grid grid-cols-2 gap-3">
      <input name="nombre" required placeholder="Nombre zona *" value="${z.nombre}" class="border rounded px-2 py-2 text-sm" />
      <input name="tarifa_base" type="number" min="0" step="100" placeholder="Tarifa base" value="${z.tarifa_base||0}" class="border rounded px-2 py-2 text-sm" />
      <input name="descripcion" placeholder="Descripción" value="${z.descripcion||''}" class="col-span-2 border rounded px-2 py-2 text-sm" />
      <div class="col-span-2 flex justify-end gap-2">
        <button type="button" onclick="closeModal()" class="px-4 py-2 text-sm rounded bg-slate-200">Cancelar</button>
        <button class="px-4 py-2 text-sm rounded bg-blue-600 text-white">Guardar</button>
      </div>
    </form>`);
  document.getElementById('frmZona').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    const body = {nombre: fd.nombre, tarifa_base: parseFloat(fd.tarifa_base)||0, descripcion: fd.descripcion, activa: 1};
    try {
      await api(id?`/api/zonas/${id}`:'/api/zonas',
        {method: id?'PUT':'POST', body: JSON.stringify(body)});
      closeModal(); toast('Guardado','ok'); renderers.zonas();
    } catch (err) { toast(err.message,'error'); }
  });
};
window.eliminarZona = async (id) => {
  if (!confirm('¿Eliminar esta zona?')) return;
  try { await api(`/api/zonas/${id}`, {method:'DELETE'}); renderers.zonas(); }
  catch (err) { toast(err.message,'error'); }
};

// Init
showView('dashboard');
// auto-refresh dashboard cada 30s
setInterval(() => {
  if (!document.getElementById('view-dashboard').classList.contains('hidden')) renderers.dashboard();
}, 30000);
