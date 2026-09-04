/* ═══════════════════════════════════════════════════════════════════
   HEALTH-TECH UI — Motor Glosas HUS (03-09-2026)  ·  window.HT

   1. Pantalla dividida: visor de soportes (izquierda, congelado, con
      zoom) | panel de decisión (derecha). CERO ventanas nuevas.
      Los dos lados cargan POR SEPARADO con esqueletos independientes:
      un PDF de 20 MB o un 404 en el visor jamás congela el panel de
      decisión.
   2. Bandeja Auto-Pilot como tablero Kanban con tarjetas (confianza,
      modelo_utilizado, semáforo de vencimiento).
   3. Barras de vencimiento que se consumen: ancho SIEMPRE entre 0 y
      100 aunque los días sean 0 o negativos.
   4. Modo oscuro grafito por defecto (body.dark ya existe; aquí solo
      se vuelve el arranque estándar, respetando la elección guardada).

   Este archivo se carga AL FINAL de index.html: puede reusar sus
   helpers (authH, escHtml, toast, fmtCOP) y reemplazar verGlosa /
   verBorradoresAutoPilot para que todo pase en la misma pantalla.
═══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── Helpers con respaldo (por si algún día cambian en index.html) ── */
  function _authH() { return (typeof window.authH === 'function') ? window.authH() : {}; }
  function _esc(t) {
    if (typeof window.escHtml === 'function') return window.escHtml(t == null ? '' : String(t));
    return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function _cop(v) {
    if (typeof window.fmtCOP === 'function') return window.fmtCOP(v || 0);
    if (typeof window.cop === 'function') return window.cop(v || 0);
    return '$' + String(Math.round(v || 0));
  }
  function _toast(t, m, k) {
    if (typeof window.toast === 'function') return window.toast(t, m, k);
    alert(t + '\n' + m);
  }

  var HT = {};
  window.HT = HT;

  /* ════ 4. MODO OSCURO GRAFITO POR DEFECTO ══════════════════════════
     Antes: oscuro solo si el gestor lo había prendido. Ahora: oscuro
     salvo que el gestor haya elegido claro ('0'). Su elección guardada
     sigue mandando. */
  HT.iniciarTema = function () {
    try {
      if (localStorage.getItem('dark') !== '0') document.body.classList.add('dark');
    } catch (e) { document.body.classList.add('dark'); }
  };

  /* ════ 3. SEMÁFORO DE VENCIMIENTOS ═════════════════════════════════
     Barra que se consume: llena = todo el plazo por delante, vacía =
     plazo agotado. Rojo estricto ≤ 3 días hábiles (incluye HOY y las
     vencidas), ámbar 4-7, verde tenue > 7. El ancho se recorta SIEMPRE
     a [0,100]: días 0, negativos o basura no rompen la caja. */
  HT.LIMITE_DIAS_HABILES = 20;

  HT.nivelVencimiento = function (dias) {
    var d = Number(dias);
    if (dias == null || isNaN(d)) return 'na';
    if (d <= 3) return 'rojo';
    if (d <= 7) return 'ambar';
    return 'verde';
  };

  HT.anchoVencimiento = function (dias, limite) {
    var d = Number(dias), lim = Number(limite) || HT.LIMITE_DIAS_HABILES;
    if (dias == null || isNaN(d)) return 0;
    var pct = Math.round((d / lim) * 100);
    return Math.max(0, Math.min(100, pct)); /* clamp duro: [0,100] */
  };

  HT.barraVencimiento = function (dias, opts) {
    opts = opts || {};
    var nivel = HT.nivelVencimiento(dias);
    if (nivel === 'na') {
      return '<span class="ht-venc-label" style="color:var(--text4)" title="Sin fecha base para calcular el vencimiento">— sin fecha</span>';
    }
    var d = Number(dias);
    var pct = HT.anchoVencimiento(dias, opts.limite);
    var texto = d < 0 ? ('Vencida hace ' + Math.abs(d) + 'd')
      : d === 0 ? 'Vence HOY'
      : (d + 'd hábiles');
    var extra = (d <= 0) ? ' ht-venc-vencida' : '';
    var title = 'Días hábiles restantes (fecha de radicación vs hoy, sin festivos): ' + d;
    return '<span class="ht-venc ht-venc-' + nivel + extra + '" title="' + _esc(title) + '">' +
      '<span class="ht-venc-track"><span class="ht-venc-fill" style="width:' + pct + '%"></span></span>' +
      '<span class="ht-venc-label">' + _esc(texto) + '</span>' +
      '</span>';
  };

  /* ── Badges de tarjeta ─────────────────────────────────────────────── */
  function _badgeConfianza(c) {
    if (c == null || isNaN(Number(c))) return '<span class="ht-badge" title="Sin evaluación registrada en la bitácora">s/conf.</span>';
    return '<span class="ht-badge ht-badge-confianza" title="Confianza matemática del evaluador">' +
      Math.round(Number(c) * 100) + '%</span>';
  }
  function _badgeModelo(m) {
    var txt = (m || '').trim() || 'modelo s/registro';
    return '<span class="ht-badge ht-badge-modelo" title="Modelo que produjo el dictamen: ' + _esc(txt) + '">' + _esc(txt) + '</span>';
  }

  function _skel(alturas) {
    return alturas.map(function (h) {
      return '<div class="ht-skel" style="height:' + h + 'px;margin:.45rem 0"></div>';
    }).join('');
  }

  /* ════ 2. TABLERO KANBAN DE BORRADORES ═════════════════════════════ */
  function _tarjetaBorrador(b) {
    var esOcr = ((b.nota_workflow || '').indexOf('ERROR_OCR') === 0);
    return '<div class="ht-card" onclick="HT.abrirSplitView(' + Number(b.glosa_id) + ',\'' +
      _esc(String(b.factura || '')).replace(/'/g, '') + '\')" title="Abrir en pantalla dividida">' +
      '<div class="ht-card-fila">' +
        '<span class="ht-card-factura">' + _esc(b.factura || ('#' + b.glosa_id)) + '</span>' +
        '<span class="ht-card-valor ht-num">' + _cop(b.valor_objetado || 0) + '</span>' +
      '</div>' +
      '<div class="ht-card-eps">' + _esc(b.eps || '—') + ' · <span class="ht-dato">' + _esc(b.codigo_glosa || '—') + '</span></div>' +
      '<div class="ht-card-fila" style="justify-content:flex-start;gap:.35rem">' +
        _badgeConfianza(b.confianza) + _badgeModelo(b.modelo_utilizado || b.modelo_ia) +
        (esOcr ? '<span class="ht-badge ht-badge-ocr" title="' + _esc(b.nota_workflow || '') + '">⛔ ERROR_OCR</span>' : '') +
      '</div>' +
      HT.barraVencimiento(b.dias_restantes) +
      '</div>';
  }

  function _tarjetaLiberada(f) {
    return '<div class="ht-card" onclick="HT.abrirSplitView(' + Number(f.glosa_id) + ')" title="Abrir en pantalla dividida">' +
      '<div class="ht-card-fila">' +
        '<span class="ht-card-factura">Glosa #' + Number(f.glosa_id) + '</span>' +
        '<span class="ht-badge ht-badge-ok">✓ liberada</span>' +
      '</div>' +
      '<div class="ht-card-eps" title="Quién la liberó">' + _esc(f.actor || '—') + '</div>' +
      '<div class="ht-card-fila" style="justify-content:flex-start;gap:.35rem">' + _badgeModelo(f.modelo_utilizado) + '</div>' +
      '</div>';
  }

  function _columna(id, titulo, contenidoHtml, n) {
    return '<div class="ht-col" id="' + id + '">' +
      '<div class="ht-col-head"><span>' + titulo + '</span><span class="ht-col-count">' + n + '</span></div>' +
      '<div class="ht-col-cards">' + contenidoHtml + '</div>' +
      '</div>';
  }

  HT.abrirKanbanBorradores = function () {
    var viejo = document.getElementById('ht-kb');
    if (viejo) viejo.remove();
    var ov = document.createElement('div');
    ov.id = 'ht-kb';
    ov.className = 'ht-kb-overlay';
    ov.innerHTML =
      '<div class="ht-kb-head">' +
        '<div>' +
          '<h3 style="margin:0;font-size:1rem;color:var(--text)">📤 Borradores del Auto-Pilot — tablero</h3>' +
          '<p style="margin:.15rem 0 0;font-size:.74rem;color:var(--text3)">La máquina propone; nada sale sin su clic. Toque una tarjeta para revisarla en pantalla dividida.</p>' +
        '</div>' +
        '<div style="display:flex;gap:.5rem">' +
          '<button class="ht-btn ht-btn-neutro" onclick="HT.abrirKanbanBorradores()">⟳ Actualizar</button>' +
          '<button class="ht-btn ht-btn-neutro" onclick="document.getElementById(\'ht-kb\').remove()">✕ Cerrar</button>' +
        '</div>' +
      '</div>' +
      '<div class="ht-kb-cols" id="ht-kb-cols">' +
        _columna('ht-col-cuarentena', '🟡 En cuarentena', _skel([64, 64, 64]), '…') +
        _columna('ht-col-ocr', '⛔ Detenidas por OCR', _skel([64]), '…') +
        _columna('ht-col-liberadas', '✅ Liberadas recientes', _skel([52, 52]), '…') +
      '</div>';
    document.body.appendChild(ov);

    /* Las dos fuentes cargan en paralelo; si una falla, la otra igual pinta. */
    var pBorradores = fetch('/autopilot/borradores?limite=200', { headers: _authH() })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    var pBitacora = fetch('/autopilot/bitacora?limite=200', { headers: _authH() })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });

    pBorradores.then(function (d) {
      var todos = d.borradores || [];
      var ocr = todos.filter(function (b) { return ((b.nota_workflow || '').indexOf('ERROR_OCR') === 0); });
      var normales = todos.filter(function (b) { return ocr.indexOf(b) === -1; });
      _pintarColumna('ht-col-cuarentena', normales.map(_tarjetaBorrador),
        'No hay borradores en espera. El worker deja aquí lo que pasa sus reglas.');
      _pintarColumna('ht-col-ocr', ocr.map(_tarjetaBorrador),
        'Ninguna glosa detenida por cortes del OCR. Buena señal.');
    }).catch(function (e) {
      _pintarError('ht-col-cuarentena', 'No se pudo consultar la bandeja (' + e.message + ').');
      _pintarError('ht-col-ocr', 'Sin datos (' + e.message + ').');
    });

    pBitacora.then(function (d) {
      var lib = (d.decisiones || []).filter(function (f) { return f.decision === 'LIBERADA_POR_HUMANO'; }).slice(0, 15);
      _pintarColumna('ht-col-liberadas', lib.map(_tarjetaLiberada),
        'Todavía nadie libera borradores. Cada liberación queda aquí, a nombre de quien la dio.');
    }).catch(function (e) {
      _pintarError('ht-col-liberadas', 'No se pudo leer la bitácora (' + e.message + ').');
    });
  };

  function _pintarColumna(id, tarjetas, vacioMsg) {
    var col = document.getElementById(id);
    if (!col) return;
    col.querySelector('.ht-col-count').textContent = tarjetas.length;
    col.querySelector('.ht-col-cards').innerHTML =
      tarjetas.length ? tarjetas.join('') : '<div class="ht-estado">' + _esc(vacioMsg) + '</div>';
  }
  function _pintarError(id, msg) {
    var col = document.getElementById(id);
    if (!col) return;
    col.querySelector('.ht-col-count').textContent = '!';
    col.querySelector('.ht-col-cards').innerHTML = '<div class="ht-estado ht-estado-error">⚠️ ' + _esc(msg) + '</div>';
  }

  /* ════ 1. PANTALLA DIVIDIDA ════════════════════════════════════════ */
  var _visorZoom = 1;
  var _visorURL = null; /* blob vigente, se libera al cambiar/cerrar */

  HT.cerrarSplitView = function () {
    var ov = document.getElementById('ht-sv');
    if (ov) ov.remove();
    if (_visorURL) { try { URL.revokeObjectURL(_visorURL); } catch (e) {} _visorURL = null; }
  };

  HT.abrirSplitView = function (glosaId, facturaConocida) {
    HT.cerrarSplitView();
    _visorZoom = 1;
    var ov = document.createElement('div');
    ov.id = 'ht-sv';
    ov.className = 'ht-sv-overlay';
    ov.innerHTML =
      '<div class="ht-sv-top">' +
        '<div style="min-width:0"><b style="color:var(--text)">Glosa #' + Number(glosaId) + '</b>' +
          ' <span id="ht-sv-sub" style="font-size:.75rem;color:var(--text3)"></span></div>' +
        '<button class="ht-btn ht-btn-neutro" onclick="HT.cerrarSplitView()">✕ Cerrar (Esc)</button>' +
      '</div>' +
      '<div class="ht-sv-grid">' +
        '<div class="ht-visor" id="ht-visor">' +
          '<div class="ht-visor-tabs" id="ht-visor-tabs"><span class="ht-skel" style="height:24px;width:60%"></span></div>' +
          '<div class="ht-visor-tools">' +
            '<button class="ht-zoom-btn" onclick="HT.zoom(-0.25)" title="Alejar">−</button>' +
            '<span class="ht-zoom-nivel" id="ht-zoom-nivel">100%</span>' +
            '<button class="ht-zoom-btn" onclick="HT.zoom(0.25)" title="Acercar">+</button>' +
            '<button class="ht-zoom-btn" onclick="HT.zoom(0)" title="Tamaño real" style="width:auto;padding:0 .5rem;font-size:.68rem">⟲ 100%</button>' +
          '</div>' +
          '<div class="ht-visor-lienzo" id="ht-visor-lienzo">' + _skel([180, 180]) + '</div>' +
        '</div>' +
        '<div class="ht-panel">' +
          '<div class="ht-panel-scroll" id="ht-panel-scroll">' + _skel([22, 14, 14, 120, 90]) + '</div>' +
          '<div class="ht-panel-acciones" id="ht-panel-acciones"></div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(ov);
    document.addEventListener('keydown', _escCierra);

    /* Panel de decisión y visor arrancan EN PARALELO e INDEPENDIENTES:
       el visor puede tardar (PDF de 20 MB) o caerse (404) sin que el
       panel derecho espere ni se quede en blanco. */
    _cargarPanel(glosaId);
    if (facturaConocida) { _cargarListaSoportes(facturaConocida); }
  };

  function _escCierra(ev) {
    if (ev.key === 'Escape') { HT.cerrarSplitView(); document.removeEventListener('keydown', _escCierra); }
  }

  HT.zoom = function (delta) {
    _visorZoom = (delta === 0) ? 1 : Math.max(0.5, Math.min(3, _visorZoom + delta));
    var wrap = document.getElementById('ht-zoomwrap');
    var nivel = document.getElementById('ht-zoom-nivel');
    if (nivel) nivel.textContent = Math.round(_visorZoom * 100) + '%';
    if (wrap) {
      wrap.style.transform = 'scale(' + _visorZoom + ')';
      wrap.style.width = (100 / _visorZoom) + '%';
      wrap.style.height = (100 / _visorZoom) + '%';
    }
  };

  /* ── Derecha: el panel de decisión ────────────────────────────────── */
  function _cargarPanel(glosaId) {
    var pGlosa = fetch('/glosas/' + glosaId, { headers: _authH() })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    var pBit = fetch('/autopilot/bitacora?glosa_id=' + glosaId + '&limite=20', { headers: _authH() })
      .then(function (r) { return r.ok ? r.json() : { decisiones: [] }; })
      .catch(function () { return { decisiones: [] }; });

    Promise.allSettled([pGlosa, pBit]).then(function (res) {
      var caja = document.getElementById('ht-panel-scroll');
      var acciones = document.getElementById('ht-panel-acciones');
      if (!caja) return;
      if (res[0].status !== 'fulfilled') {
        caja.innerHTML = '<div class="ht-estado ht-estado-error">⚠️ No se pudo cargar la glosa (' +
          _esc(res[0].reason && res[0].reason.message || 'error') + ').' +
          '</div><div style="text-align:center;margin-top:.6rem">' +
          '<button class="ht-btn ht-btn-neutro" onclick="HT.abrirSplitView(' + glosaId + ')">Reintentar</button></div>';
        return;
      }
      var g = res[0].value;
      var bit = (res[1].status === 'fulfilled' ? res[1].value.decisiones : []) || [];
      var cand = null;
      for (var i = 0; i < bit.length; i++) { if (bit[i].decision === 'CANDIDATA') { cand = bit[i]; break; } }

      var sub = document.getElementById('ht-sv-sub');
      if (sub) sub.textContent = (g.eps || '') + ' · ' + (g.factura || 's/factura');

      /* El visor arranca apenas se conoce la factura (si no vino antes). */
      if (g.factura && !document.getElementById('ht-visor-tabs').dataset.lista) {
        _cargarListaSoportes(g.factura);
      }

      var enCuarentena = (g.workflow_state === 'PENDIENTE_APROBACION_HUMANA');
      var esOcr = ((g.nota_workflow || '').indexOf('ERROR_OCR') === 0);

      caja.innerHTML =
        '<h3>' + _esc(g.eps || '—') + ' · <span class="ht-dato">' + _esc(g.codigo_glosa || '—') + '</span></h3>' +
        '<dl class="ht-kv">' +
          '<dt>Factura</dt><dd class="ht-dato">' + _esc(g.factura || '—') + '</dd>' +
          '<dt>Valor objetado</dt><dd class="ht-num" style="font-weight:800">' + _cop(g.valor_objetado || 0) + '</dd>' +
          '<dt>Estado</dt><dd>' + _esc(g.workflow_state || g.estado || '—') +
            (esOcr ? ' <span class="ht-badge ht-badge-ocr">⛔ ERROR_OCR</span>' : '') + '</dd>' +
          '<dt>Vencimiento</dt><dd>' + HT.barraVencimiento(g.dias_restantes) + '</dd>' +
        '</dl>' +
        '<div style="display:flex;gap:.4rem;flex-wrap:wrap;margin:.5rem 0 .8rem">' +
          _badgeConfianza(cand ? cand.confianza : null) +
          _badgeModelo((cand && cand.modelo_utilizado) || g.modelo_ia) +
          (cand && cand.riesgo ? '<span class="ht-badge">riesgo ' + _esc(cand.riesgo) + '</span>' : '') +
        '</div>' +
        (cand ? '<div class="ht-estado" style="text-align:left;border-style:solid">📐 <b>Regla aplicada:</b> ' +
          _esc(cand.regla_aplicada || '—') + '</div>' : '') +
        '<h3 style="margin-top:1rem">Dictamen</h3>' +
        (g.dictamen
          ? '<div class="ht-dictamen">' + g.dictamen + '</div>'
          : '<div class="ht-estado">Esta glosa no tiene dictamen todavía' +
            (esOcr ? ' — quedó detenida por un corte del OCR. Re-analícela cuando la red esté estable.' : '.') +
            '</div>');

      if (acciones) {
        acciones.innerHTML = enCuarentena
          ? '<button class="ht-btn ht-btn-esmeralda" onclick="HT.liberar(' + glosaId + ')">✔ Liberar (queda RESPONDIDA a su nombre)</button>' +
            '<button class="ht-btn ht-btn-carmesi" onclick="HT.devolver(' + glosaId + ')">✖ Devolver a revisión manual</button>'
          : '<span style="font-size:.72rem;color:var(--text3);align-self:center">Solo lectura — esta glosa no está en la bandeja de borradores.</span>';
      }
    });
  }

  /* ── Izquierda: visor de soportes ─────────────────────────────────── */
  function _cargarListaSoportes(factura) {
    var tabs = document.getElementById('ht-visor-tabs');
    if (!tabs) return;
    tabs.dataset.lista = '1';
    fetch('/soportes-auto/factura/' + encodeURIComponent(factura), { headers: _authH() })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        var docs = d.soportes || [];
        if (!docs.length) {
          tabs.innerHTML = '';
          _lienzo('<div class="ht-estado">' +
            (d.construyendo
              ? '⏳ El índice de soportes se está reconstruyendo. Intente de nuevo en un momento.'
              : 'El indexador no conoce soportes para la factura ' + _esc(factura) + '.') + '</div>');
          return;
        }
        tabs.innerHTML = docs.slice(0, 12).map(function (s, i) {
          return '<button class="ht-visor-tab' + (i === 0 ? ' activa' : '') + '" ' +
            'title="' + _esc(s.nombre_archivo || '') + '" ' +
            'onclick="HT.verDocumento(this,\'' + _esc(factura).replace(/'/g, '') + '\',\'' +
            _esc(s.nombre_archivo || '').replace(/'/g, '') + '\')">' +
            _esc((s.tipo_codigo || 'DOC') + ' · ' + (s.nombre_archivo || '')) + '</button>';
        }).join('');
        HT.verDocumento(tabs.querySelector('.ht-visor-tab'), factura, docs[0].nombre_archivo || '');
      })
      .catch(function (e) {
        tabs.innerHTML = '';
        _lienzo('<div class="ht-estado ht-estado-error">⚠️ No se pudo listar el expediente (' + _esc(e.message) + ').</div>');
      });
  }

  function _lienzo(html) {
    var l = document.getElementById('ht-visor-lienzo');
    if (l) l.innerHTML = html;
  }

  HT.verDocumento = function (btn, factura, nombre) {
    var tabs = document.querySelectorAll('.ht-visor-tab');
    tabs.forEach(function (t) { t.classList.remove('activa'); });
    if (btn && btn.classList) btn.classList.add('activa');
    _lienzo(_skel([160, 160]));
    if (_visorURL) { try { URL.revokeObjectURL(_visorURL); } catch (e) {} _visorURL = null; }

    var url = '/soportes-auto/archivo?factura=' + encodeURIComponent(factura) +
      '&nombre=' + encodeURIComponent(nombre);
    fetch(url, { headers: _authH() })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        var tipo = r.headers.get('Content-Type') || '';
        return r.blob().then(function (b) { return { blob: b, tipo: tipo }; });
      })
      .then(function (res) {
        _visorURL = URL.createObjectURL(res.blob);
        var inner;
        if (res.tipo.indexOf('pdf') !== -1) {
          inner = '<iframe src="' + _visorURL + '" title="' + _esc(nombre) + '"></iframe>';
        } else if (res.tipo.indexOf('image') !== -1) {
          inner = '<img src="' + _visorURL + '" alt="' + _esc(nombre) + '">';
        } else {
          return res.blob.text().then(function (txt) {
            _lienzo('<div class="ht-zoomwrap" id="ht-zoomwrap"><pre>' + _esc(txt.slice(0, 100000)) + '</pre></div>');
            HT.zoom(0);
          });
        }
        _lienzo('<div class="ht-zoomwrap" id="ht-zoomwrap">' + inner + '</div>');
        HT.zoom(0);
      })
      .catch(function (e) {
        /* El error del documento vive en el visor; el panel derecho sigue. */
        _lienzo('<div class="ht-estado ht-estado-error">⚠️ No se pudo abrir «' + _esc(nombre) + '» (' + _esc(e.message) + ').' +
          '<br><button class="ht-btn ht-btn-neutro" style="margin-top:.6rem" ' +
          'onclick="HT.verDocumento(null,\'' + _esc(factura).replace(/'/g, '') + '\',\'' + _esc(nombre).replace(/'/g, '') + '\')">Reintentar</button></div>');
      });
  };

  /* ── Acciones humanas (esmeralda / carmesí) ───────────────────────── */
  HT.liberar = function (glosaId) {
    if (!confirm('✔ Liberar el borrador de la glosa #' + glosaId + '\n\nQuedará RESPONDIDA a su nombre y la liberación se anota en la bitácora.\n\n¿Confirma?')) return;
    fetch('/autopilot/liberar/' + glosaId, { method: 'POST', headers: _authH() })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { _toast('No se liberó', res.d.detail || 'Error', 'error'); return; }
        _toast('✓ Liberada', 'La glosa #' + glosaId + ' salió de borradores a su nombre.', 'success');
        HT.cerrarSplitView();
        if (document.getElementById('ht-kb')) HT.abrirKanbanBorradores();
      })
      .catch(function (e) { _toast('Error', e.message, 'error'); });
  };

  HT.devolver = function (glosaId) {
    var motivo = prompt('✖ Devolver a revisión manual\n\nLa glosa #' + glosaId + ' saldrá de borradores SIN radicarse y volverá a la bandeja normal.\n\nMotivo (opcional):', '');
    if (motivo === null) return;
    fetch('/autopilot/devolver/' + glosaId + '?motivo=' + encodeURIComponent(motivo || ''), { method: 'POST', headers: _authH() })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { _toast('No se devolvió', res.d.detail || 'Error', 'error'); return; }
        _toast('↩ Devuelta', 'La glosa #' + glosaId + ' volvió a revisión manual (queda en la bitácora).', 'success');
        HT.cerrarSplitView();
        if (document.getElementById('ht-kb')) HT.abrirKanbanBorradores();
      })
      .catch(function (e) { _toast('Error', e.message, 'error'); });
  };

  /* ════ BANDEJA «EN ESPERA DE EPS» (V3, Pilar 1) ═══════════════════════
     Lo que ya se radicó en el portal —con su número y la huella del
     comprobante— y, sobre todo, lo que se quedó atorado: los envíos que no
     se pudieron confirmar y los portales que piden una persona.

     La regla de oro de este circuito se ve aquí: una radicación dudosa NO
     vuelve sola a la cola. Sale de la duda cuando alguien mira el portal y
     dice qué pasó. Estos botones son ese «alguien».
  ═════════════════════════════════════════════════════════════════════ */

  var _ESTADOS_ATORADOS = ['EN_PORTAL_SIN_CONFIRMAR', 'VERIFICAR_MANUAL'];

  HT.esAtorada = function (estado) { return _ESTADOS_ATORADOS.indexOf(estado) !== -1; };

  function _pillEstado(e) {
    var mapa = {
      RADICADA: ['#059669', '✓ radicada en la EPS'],
      EN_PORTAL_SIN_CONFIRMAR: ['#dc2626', '⚠ enviada sin confirmar'],
      VERIFICAR_MANUAL: ['#dc2626', '⚠ hay que mirar el portal'],
      HUMANO_REQUERIDO: ['#d97706', '✋ la hace una persona'],
      PENDIENTE: ['#1565c0', '⏳ en cola'],
      RECLAMADA: ['#1565c0', '⏳ radicando ahora'],
      FALLIDA: ['#6b7280', '✗ falló (reintentable)'],
    };
    var c = mapa[e] || ['#6b7280', e || '—'];
    return '<span class="ht-badge" style="background:' + c[0] + ';color:#fff;border-color:transparent">' + _esc(c[1]) + '</span>';
  }

  function _huella(sha) {
    if (!sha) return '<span style="color:var(--text4)">sin comprobante</span>';
    /* La huella completa no cabe y no se lee; los primeros 16 identifican y
       el title trae la de verdad, que es la que vale ante la Supersalud. */
    return '<span class="ht-dato" title="SHA-256 del comprobante: ' + _esc(sha) + '">' +
      _esc(sha.slice(0, 16)) + '…</span>';
  }

  function _filaEspera(f) {
    var atorada = HT.esAtorada(f.estado);
    var acciones = '';
    if (atorada) {
      acciones =
        '<button class="ht-btn ht-btn-esmeralda" style="padding:.3rem .7rem;font-size:.72rem" ' +
        'onclick="HT.resolverRadicacion(' + f.id + ',true)" ' +
        'title="Miré el portal y SÍ quedó radicada">✔ Sí quedó</button> ' +
        '<button class="ht-btn ht-btn-carmesi" style="padding:.3rem .7rem;font-size:.72rem" ' +
        'onclick="HT.resolverRadicacion(' + f.id + ',false)" ' +
        'title="Miré el portal y NO quedó: vuelve a la cola">✖ No quedó</button>';
    } else if (f.estado === 'HUMANO_REQUERIDO') {
      acciones =
        '<button class="ht-btn ht-btn-esmeralda" style="padding:.3rem .7rem;font-size:.72rem" ' +
        'onclick="HT.resolverRadicacion(' + f.id + ',true)" ' +
        'title="La radiqué a mano en el portal">✔ La radiqué a mano</button>';
    }
    return '<tr>' +
      '<td style="padding:.45rem .6rem" class="ht-dato">' + _esc(f.eps || '—') + '</td>' +
      '<td style="padding:.45rem .6rem" class="ht-dato">' + _esc(f.portal || '—') + '</td>' +
      '<td style="padding:.45rem .6rem">' + _pillEstado(f.estado) + '</td>' +
      '<td style="padding:.45rem .6rem" class="ht-dato">' + _esc(f.radicado_numero || '—') + '</td>' +
      '<td style="padding:.45rem .6rem">' + _huella(f.comprobante_sha256) + '</td>' +
      '<td style="padding:.45rem .6rem;color:var(--text3);font-size:.72rem">' + _esc((f.ultimo_error || '').slice(0, 90)) + '</td>' +
      '<td style="padding:.45rem .6rem;white-space:nowrap">' + acciones + '</td>' +
    '</tr>';
  }

  HT.abrirBandejaEspera = function () {
    var viejo = document.getElementById('ht-espera');
    if (viejo) viejo.remove();
    var ov = document.createElement('div');
    ov.id = 'ht-espera';
    ov.className = 'ht-kb-overlay';
    ov.innerHTML =
      '<div class="ht-kb-head">' +
        '<div>' +
          '<h3 style="margin:0;font-size:1rem;color:var(--text)">📮 En espera de EPS — libro de radicación</h3>' +
          '<p style="margin:.15rem 0 0;font-size:.74rem;color:var(--text3)">Lo radicado con su comprobante, y lo que quedó atorado esperando a una persona.</p>' +
        '</div>' +
        '<div style="display:flex;gap:.5rem">' +
          '<button class="ht-btn ht-btn-neutro" onclick="HT.abrirBandejaEspera()">⟳ Actualizar</button>' +
          '<button class="ht-btn ht-btn-neutro" onclick="document.getElementById(\'ht-espera\').remove()">✕ Cerrar</button>' +
        '</div>' +
      '</div>' +
      '<div id="ht-espera-cuerpo" style="flex:1;overflow:auto">' + _skel([28, 28, 28, 28]) + '</div>';
    document.body.appendChild(ov);

    fetch('/radicacion/cola?limite=500', { headers: _authH() })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        var filas = d.filas || [];
        var atoradas = filas.filter(function (f) { return HT.esAtorada(f.estado) || f.estado === 'HUMANO_REQUERIDO'; });
        var resto = filas.filter(function (f) { return atoradas.indexOf(f) === -1; });
        var cuerpo = document.getElementById('ht-espera-cuerpo');
        if (!cuerpo) return;
        if (!filas.length) {
          cuerpo.innerHTML = '<div class="ht-estado">El libro está vacío: todavía no se ha encolado ninguna radicación.</div>';
          return;
        }
        var cab = '<thead><tr style="text-align:left;color:var(--text3);font-size:.74rem">' +
          '<th style="padding:.45rem .6rem">Entidad</th><th style="padding:.45rem .6rem">Portal</th>' +
          '<th style="padding:.45rem .6rem">Estado</th><th style="padding:.45rem .6rem">Radicado</th>' +
          '<th style="padding:.45rem .6rem">Huella del comprobante</th><th style="padding:.45rem .6rem">Detalle</th>' +
          '<th></th></tr></thead>';
        var resumen = Object.keys(d.por_estado || {}).map(function (k) {
          return _pillEstado(k) + ' <b>' + d.por_estado[k] + '</b>';
        }).join(' &nbsp; ');
        cuerpo.innerHTML =
          '<div style="margin:.2rem 0 .9rem;font-size:.78rem">' + resumen + '</div>' +
          (atoradas.length
            ? '<h4 style="margin:.6rem 0 .3rem;font-size:.85rem;color:var(--ht-carmesi)">Necesitan que usted mire el portal (' + atoradas.length + ')</h4>' +
              '<table style="width:100%;border-collapse:collapse;font-size:.8rem">' + cab +
              '<tbody>' + atoradas.map(_filaEspera).join('') + '</tbody></table>'
            : '<div class="ht-estado" style="border-style:solid">Nada atorado. Ninguna radicación quedó a medias.</div>') +
          (resto.length
            ? '<h4 style="margin:1.2rem 0 .3rem;font-size:.85rem;color:var(--text2)">El resto del libro (' + resto.length + ')</h4>' +
              '<table style="width:100%;border-collapse:collapse;font-size:.8rem">' + cab +
              '<tbody>' + resto.map(_filaEspera).join('') + '</tbody></table>'
            : '');
      })
      .catch(function (e) {
        var cuerpo = document.getElementById('ht-espera-cuerpo');
        if (cuerpo) cuerpo.innerHTML = '<div class="ht-estado ht-estado-error">⚠️ No se pudo leer el libro de radicación (' + _esc(e.message) + ').</div>';
      });
  };

  HT.resolverRadicacion = function (id, quedoRadicada) {
    var pregunta = quedoRadicada
      ? '✔ Confirmar que SÍ quedó radicada\n\nUsted miró el portal y la respuesta está allá. La glosa pasará a «radicada en la EPS» y saldrá del semáforo de urgencia.\n\n¿Confirma?'
      : '✖ Confirmar que NO quedó radicada\n\nUsted miró el portal y la respuesta NO está. La glosa vuelve a la cola para intentarlo otra vez.\n\n¿Confirma?';
    if (!confirm(pregunta)) return;
    var radicado = '';
    if (quedoRadicada) {
      radicado = prompt('Número de radicado que muestra el portal (si lo tiene a la vista; puede dejarlo vacío):', '') || '';
    }
    fetch('/radicacion/' + id + '/verificar', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, _authH()),
      body: JSON.stringify({ quedo_radicada: !!quedoRadicada, radicado_numero: radicado }),
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { _toast('No se pudo resolver', res.d.detail || 'Error', 'error'); return; }
        _toast(quedoRadicada ? '✓ Confirmada' : '↩ De vuelta a la cola',
          quedoRadicada ? 'Queda como radicada en la EPS.' : 'Se intentará de nuevo.', 'success');
        HT.abrirBandejaEspera();
      })
      .catch(function (e) { _toast('Error', e.message, 'error'); });
  };

  /* ── Cero saltos entre ventanas: los flujos viejos entran aquí ────── */
  window.verGlosa = function (id) { HT.abrirSplitView(id); };
  window.verBorradoresAutoPilot = function () { HT.abrirKanbanBorradores(); };
  window.verBandejaEsperaEPS = function () { HT.abrirBandejaEspera(); };

  HT.iniciarTema();
})();
