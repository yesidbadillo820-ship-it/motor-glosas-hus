/* ═══════════════════════════════════════════════════════════════════
   SINAC Analizar PRO — transformaciones visuales del panel Analizar
   Motor Glosas HUS 2.0 — 28 mayo 2026.

   Usa MutationObserver sobre #result-area para transformar los
   elementos cuando aparecen, SIN tocar el render del backend:
     1. Probabilidad de éxito → gauge circular animado
     2. Pills de código → color por familia (TA/SO/CO/FA/CL/AU) + valor grande
     3. Dictamen → clase "héroe" (sello marca de agua) + citas legales
        clickeables que abren un drawer lateral.

   NOTA: el loading premium (skeleton) y el empty state NO se implementan
   aquí porque el código existente YA los provee, y mejor:
     - Loading  → #pa-pipeline (visualización de 7 agentes, paShowPipeline)
     - Empty    → #landing-hero / pa-empty-rich
   Duplicarlos causaría doble loader y sobrescribiría el landing.

   El marcado de citas usa TreeWalker sobre nodos de texto (nunca
   innerHTML-replace sobre contenedores con <table>), porque ese enfoque
   ya corrompió el dictamen una vez y por eso paMarcarCitasEnDictamen()
   quedó desactivado.
═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // Umbrales alineados con el render del backend (index.html ~14513):
  //   score >= 85 → verde, >= 65 → ámbar, resto → rojo.
  // Mantenerlos iguales evita que el gauge muestre verde donde el backend
  // considera el score "medio" (incoherencia de color + subtítulo).
  const UMBRAL_ALTO = 85;
  const UMBRAL_MEDIO = 65;
  const COLOR_EXITO = (pct) =>
    pct >= UMBRAL_ALTO ? '#16a34a' : pct >= UMBRAL_MEDIO ? '#d97706' : '#e11d48';

  // ──────────────────────────────────────────────────────────────────
  // 1. GAUGE CIRCULAR (Probabilidad de éxito)
  // ──────────────────────────────────────────────────────────────────
  function transformarGauge(scoreEl) {
    if (!scoreEl || scoreEl.dataset.sdsGauge) return;
    const valEl = scoreEl.querySelector('.score-val');
    const labelEl = scoreEl.querySelector('.score-label');
    if (!valEl) return;
    // El score puede venir con decimales ("89.5%") o coma decimal ("89,5%").
    // Quitar todo salvo dígitos/punto/coma, normalizar coma→punto, redondear
    // y acotar a 0–100 (un parse ingenuo convertía "89.5%" en 895).
    const raw = (valEl.textContent || '').replace(/[^\d.,]/g, '').replace(/,/g, '.');
    let pct = Math.round(parseFloat(raw));
    if (!isFinite(pct)) pct = 0;
    pct = Math.max(0, Math.min(100, pct));
    const color = COLOR_EXITO(pct);
    const titulo = labelEl ? labelEl.textContent : 'Probabilidad de éxito de la defensa';

    const R = 46;
    const C = 2 * Math.PI * R;
    const offset = C * (1 - pct / 100);

    scoreEl.dataset.sdsGauge = '1';
    scoreEl.innerHTML =
      '<div class="sds-gauge-wrap">' +
      '<div class="sds-gauge">' +
      '<svg viewBox="0 0 104 104">' +
      '<circle class="sds-gauge-track" cx="52" cy="52" r="' + R + '" fill="none" stroke-width="11"/>' +
      '<circle class="sds-gauge-fill" cx="52" cy="52" r="' + R + '" fill="none" stroke-width="11" ' +
      'stroke="' + color + '" stroke-dasharray="' + C.toFixed(1) + '" ' +
      'stroke-dashoffset="' + C.toFixed(1) + '"/>' +
      '</svg>' +
      '<div class="sds-gauge-label">' +
      '<div class="sds-gauge-pct" style="color:' + color + '">' + pct + '%</div>' +
      '<div class="sds-gauge-cap">éxito</div>' +
      '</div>' +
      '</div>' +
      '<div class="sds-gauge-text">' +
      '<div class="sds-gauge-text-title"></div>' +
      '<div class="sds-gauge-text-sub">' +
      (pct >= UMBRAL_ALTO
        ? 'Alta probabilidad de levantamiento. Argumento sólido.'
        : pct >= UMBRAL_MEDIO
        ? 'Probabilidad media. Considera reforzar con soportes.'
        : 'Probabilidad baja. Requiere más evidencia documental.') +
      '</div>' +
      '</div>' +
      '</div>';
    // Título por textContent (evita inyección desde el render)
    const tEl = scoreEl.querySelector('.sds-gauge-text-title');
    if (tEl) tEl.textContent = titulo;

    // Animar el llenado
    requestAnimationFrame(function () {
      const fill = scoreEl.querySelector('.sds-gauge-fill');
      if (fill) {
        requestAnimationFrame(function () {
          fill.style.strokeDashoffset = offset.toFixed(1);
        });
      }
    });
  }

  // ──────────────────────────────────────────────────────────────────
  // 2. CHIPS CON IDENTIDAD (color por familia + valor grande)
  // ──────────────────────────────────────────────────────────────────
  const FAMILIAS = ['TA', 'SO', 'CO', 'FA', 'CL', 'AU'];

  function transformarChips(container) {
    container.querySelectorAll('.pill-code:not([data-sds])').forEach(function (el) {
      el.dataset.sds = '1';
      const fam = (el.textContent || '').trim().toUpperCase().slice(0, 2);
      if (FAMILIAS.indexOf(fam) >= 0) el.classList.add('sds-fam-' + fam);
    });
    container.querySelectorAll('.pill-gray:not([data-sds])').forEach(function (el) {
      el.dataset.sds = '1';
      if ((el.textContent || '').indexOf('$') >= 0) el.classList.add('sds-valor-big');
    });
  }

  // ──────────────────────────────────────────────────────────────────
  // 3. DICTAMEN HÉROE + citas clickeables (TreeWalker seguro)
  // ──────────────────────────────────────────────────────────────────
  // Una sola regex combinada; se aplica SOLO a nodos de texto.
  // Cubre las formas reales que aparecen en los dictámenes del banco HUS:
  //   · prosa:    "ART. 168 DE LA LEY 100 DE 1993", "Artículo 56 de la Ley 1438 de 2011"
  //   · suelta:   "Decreto 4747 de 2007", "Resolución 3047 de 2008"
  //   · compacta: "Ley 1438/2011", "Resolución 2284/2023" (lista FUNDAMENTO)
  //   · acuerdo:  "Acuerdo 002/2001" (Consejo Superior de Salud FF.MM., etc.)
  //   · sentencia:"Sentencia T-760/2008", "Sentencia C-313 de 2014"
  // Los conectores internos usan [^\S\n] (espacio sin salto de línea) para no
  // fusionar dos citas que estén en renglones distintos del mismo nodo.
  const _NORMA = '(?:Ley|Decreto|Resoluci[óo]n|C[óo]digo|Acuerdo|Circular)';
  const _ART = '(?:Art[íi]culos?|Arts?\\.)';
  const _ANIO = '(?:[^\\S\\n]*\\/[^\\S\\n]*\\d{2,4}|[^\\S\\n]+de[^\\S\\n]+\\d{4})';
  const RE_CITA = new RegExp(
    [
      // A) Artículo(s) [de (la)] Norma N [de YYYY | /YYYY]
      _ART +
        '[^\\S\\n]*\\d+[º°]?(?:[^\\S\\n]*(?:,|y|e)[^\\S\\n]*\\d+[º°]?)*' +
        '(?:[^\\S\\n]+(?:de[^\\S\\n]+la|del|de))?' +
        '[^\\S\\n]+' +
        _NORMA +
        '[^\\S\\n]+\\d[\\d.]*(?:' +
        _ANIO +
        ')?',
      // B) Norma N de YYYY   (suelta, sin artículo previo)
      _NORMA + '[^\\S\\n]+\\d[\\d.]*[^\\S\\n]+de[^\\S\\n]+\\d{4}',
      // C) Norma N/YYYY      (forma compacta de la lista FUNDAMENTO)
      _NORMA + '[^\\S\\n]+\\d[\\d.]*[^\\S\\n]*\\/[^\\S\\n]*\\d{2,4}',
      // D) Sentencia X-NNN/YYYY  o  X-NNN de YYYY
      'Sentencia[^\\S\\n]+[TCSU]+-?[^\\S\\n]?\\d+(?:[^\\S\\n]*[\\/-][^\\S\\n]*|[^\\S\\n]+de[^\\S\\n]+)\\d{2,4}',
    ].join('|'),
    'gi'
  );
  // Pre-filtro rápido por nodo de texto: debe incluir TODOS los tipos de
  // norma de RE_CITA, o el nodo se descarta antes de correr la regex.
  const PREFILTRO = /(Art|Ley|Decreto|Resol|C[óo]digo|Acuerdo|Circular|Sentencia)/i;

  function wrapCitasEnNodo(textNode) {
    const text = textNode.nodeValue;
    RE_CITA.lastIndex = 0;
    let m;
    let last = 0;
    let frag = null;
    while ((m = RE_CITA.exec(text)) !== null) {
      if (m[0].length === 0) {
        RE_CITA.lastIndex++;
        continue;
      }
      if (!frag) frag = document.createDocumentFragment();
      const start = m.index;
      const end = start + m[0].length;
      if (start > last) frag.appendChild(document.createTextNode(text.slice(last, start)));
      const chip = document.createElement('span');
      chip.className = 'sds-cita-chip';
      chip.setAttribute('role', 'button');
      chip.setAttribute('tabindex', '0');
      chip.dataset.cita = m[0];
      chip.textContent = m[0];
      frag.appendChild(chip);
      last = end;
    }
    if (frag) {
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      textNode.parentNode.replaceChild(frag, textNode);
      return true;
    }
    return false;
  }

  function transformarDictamen(dictEl) {
    if (!dictEl || dictEl.dataset.sdsHero) return;
    dictEl.dataset.sdsHero = '1';
    dictEl.classList.add('sds-hero');

    const body = dictEl.querySelector('.res-dictamen-body');
    if (!body) return;

    // Recolectar nodos de texto candidatos SIN mutar durante el walk.
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        const p = node.parentElement;
        if (!p) return NodeFilter.FILTER_REJECT;
        if (p.closest('.sds-cita-chip, .pa-cite, a, button, script, style'))
          return NodeFilter.FILTER_REJECT;
        const v = node.nodeValue;
        if (!v || v.length < 6) return NodeFilter.FILTER_REJECT;
        if (!PREFILTRO.test(v)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const nodos = [];
    let n;
    let visitados = 0;
    while ((n = walker.nextNode()) !== null && visitados < 500) {
      nodos.push(n);
      visitados++;
    }
    let chips = 0;
    for (let i = 0; i < nodos.length && chips < 60; i++) {
      if (wrapCitasEnNodo(nodos[i])) chips++;
    }
  }

  // ── Drawer lateral con la cita ──
  function abrirDrawerNorma(cita) {
    let drawer = document.getElementById('sds-norma-drawer');
    if (!drawer) {
      drawer = document.createElement('div');
      drawer.id = 'sds-norma-drawer';
      drawer.className = 'sds-norma-drawer';
      drawer.innerHTML =
        '<div class="sds-norma-drawer-hdr">' +
        '<h3>📖 Norma citada</h3>' +
        '<button class="sds-norma-drawer-close" aria-label="Cerrar">✕</button>' +
        '</div>' +
        '<div class="sds-norma-drawer-body" id="sds-norma-drawer-body"></div>';
      document.body.appendChild(drawer);
      drawer
        .querySelector('.sds-norma-drawer-close')
        .addEventListener('click', cerrarDrawerNorma);
    }
    const body = drawer.querySelector('#sds-norma-drawer-body');
    body.textContent = '';

    const titulo = document.createElement('div');
    titulo.style.cssText =
      'font-size:1.05rem;font-weight:700;color:var(--sds-blue-700,#1d4ed8);margin-bottom:12px';
    titulo.textContent = cita;
    body.appendChild(titulo);

    const desc = document.createElement('p');
    desc.style.color = 'var(--sds-gray-600,#475569)';
    desc.textContent = 'Esta es una de las normas en las que se fundamenta el dictamen.';
    body.appendChild(desc);

    const btn = document.createElement('button');
    btn.style.cssText =
      'margin-top:16px;padding:10px 16px;background:var(--sds-blue-600,#2563eb);' +
      'color:white;border:none;border-radius:8px;cursor:pointer;font-weight:600;' +
      "font-family:Inter,sans-serif;font-size:.85rem";
    btn.textContent = 'Ver texto completo en Consulta Normativa →';
    btn.addEventListener('click', function () {
      cerrarDrawerNorma();
      const nav = document.querySelector('.sn-item[onclick*="consulta-normativa"]');
      if (nav) nav.click();
    });
    body.appendChild(btn);

    drawer.classList.add('open');
  }

  function cerrarDrawerNorma() {
    const drawer = document.getElementById('sds-norma-drawer');
    if (drawer) drawer.classList.remove('open');
  }

  // Delegación: click / Enter en cualquier chip de cita
  document.addEventListener('click', function (e) {
    const chip = e.target.closest && e.target.closest('.sds-cita-chip');
    if (chip) abrirDrawerNorma(chip.dataset.cita || chip.textContent);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      cerrarDrawerNorma();
      return;
    }
    if (e.key === 'Enter' || e.key === ' ') {
      const chip = e.target.closest && e.target.closest('.sds-cita-chip');
      if (chip) {
        e.preventDefault();
        abrirDrawerNorma(chip.dataset.cita || chip.textContent);
      }
    }
  });

  // ──────────────────────────────────────────────────────────────────
  // OBSERVER PRINCIPAL
  // ──────────────────────────────────────────────────────────────────
  function procesarResultado(area) {
    const score = area.querySelector('.res-score:not([data-sds-gauge])');
    const dict = area.querySelector('.res-dictamen:not([data-sds-hero])');
    if (score || dict) {
      if (score) transformarGauge(score);
      transformarChips(area);
      if (dict) transformarDictamen(dict);
      if (!area.dataset.sdsAnimated) {
        area.dataset.sdsAnimated = '1';
        area.classList.add('sds-result-in');
        setTimeout(function () {
          area.classList.remove('sds-result-in');
        }, 500);
      }
    }
  }

  function init() {
    const area = document.getElementById('result-area');
    if (!area) {
      setTimeout(init, 1000);
      return;
    }
    const observer = new MutationObserver(function () {
      procesarResultado(area);
    });
    observer.observe(area, { childList: true, subtree: true });
    procesarResultado(area);
    console.log('[SINAC Analizar PRO] Inicializado — gauge, chips, dictamen héroe.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
