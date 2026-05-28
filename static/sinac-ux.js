/* ═══════════════════════════════════════════════════════════════════
   SINAC UX — Motor Glosas HUS 2.0
   Ola 3 del Plan de Transformación, mayo 2026.

   Provee:
     1. Modo Enfocado (auto-activar al hacer click Analizar)
     2. Command Palette ⌘K / Ctrl+K
     3. Atajos de teclado para power users
     4. Tooltips contextuales para citas legales

   Se carga después del JS existente. NO sobrescribe nada — añade
   funcionalidad nueva via event listeners no-invasivos.
═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ──────────────────────────────────────────────────────────────────
  // 1. MODO ENFOCADO
  // ──────────────────────────────────────────────────────────────────
  function activarModoEnfocado() {
    document.body.classList.add('sds-focus-mode');
    mostrarToast('Modo Enfocado activado — presiona Esc para salir');
  }

  function desactivarModoEnfocado() {
    document.body.classList.remove('sds-focus-mode');
  }

  // Indicador visual del modo enfocado
  function instalarIndicadorFocus() {
    if (document.querySelector('.sds-focus-indicator')) return;
    const el = document.createElement('div');
    el.className = 'sds-focus-indicator';
    el.textContent = 'Modo Enfocado';
    el.title = 'Presiona Esc para salir';
    el.addEventListener('click', desactivarModoEnfocado);
    document.body.appendChild(el);
  }

  // Auto-activar al click en "Analizar con IA"
  // DESACTIVADO (27 may 2026): causaba confusión — el modo enfocado se
  // activaba solo y atenuaba el formulario. Ahora es OPT-IN via ⌘K o
  // el comando "Activar Modo Enfocado" en el palette.
  function installAutoFocus() {
    // Intencionalmente vacío. El modo enfocado solo se activa manualmente.
    return;
  }

  // ──────────────────────────────────────────────────────────────────
  // 2. COMMAND PALETTE ⌘K
  // ──────────────────────────────────────────────────────────────────
  const PALETTE_ACTIONS = [
    { id: 'nav-analizar', label: 'Ir a Analizar glosa', icon: '🔍', shortcut: 'A', action: () => navegarA('#p-analizar') },
    { id: 'nav-mis-glosas', label: 'Ir a Mis glosas', icon: '📋', shortcut: 'M', action: () => navegarA('#p-mis-glosas') },
    { id: 'nav-historial', label: 'Ir a Historial', icon: '📚', shortcut: 'H', action: () => navegarA('#p-historial') },
    { id: 'nav-alertas', label: 'Ir a Alertas', icon: '🔔', action: () => navegarA('#p-alertas') },
    { id: 'nav-contratos', label: 'Ir a Contratos', icon: '📄', action: () => navegarA('#p-contratos') },
    { id: 'nav-tarifas', label: 'Ir a Tarifas', icon: '💰', action: () => navegarA('#p-tarifas') },
    { id: 'nav-dashboard', label: 'Ir a Dashboard', icon: '📊', action: () => navegarA('#p-dashboard') },
    { id: 'nav-cobranza', label: 'Ir a Cobranza Live', icon: '💼', action: () => navegarA('#p-cobranza-live') },
    { id: 'nav-importar-masiva', label: 'Ir a Importación masiva', icon: '⬆️', action: () => navegarA('#p-importar-masiva') },
    { id: 'nav-importar-recepcion', label: 'Ir a Importar recepción', icon: '📥', action: () => navegarA('#p-importar-recepcion') },
    { id: 'nav-consulta-normativa', label: 'Consulta Normativa', icon: '⚖️', action: () => navegarA('#p-consulta-normativa') },
    { id: 'nav-soportes', label: 'Soportes', icon: '📎', action: () => navegarA('#p-soportes') },
    { id: 'nav-auditor', label: 'Auditor Forense', icon: '🔍', action: () => navegarA('#p-auditor-forense') },
    { id: 'nav-diagnostico', label: 'Diagnóstico IA', icon: '🩺', action: () => navegarA('#p-diagnostico') },
    { id: 'action-focus', label: 'Activar Modo Enfocado', icon: '🎯', action: activarModoEnfocado },
    { id: 'action-blur', label: 'Salir de Modo Enfocado', icon: '🔓', action: desactivarModoEnfocado },
    { id: 'action-help', label: 'Mostrar atajos de teclado', icon: '⌨️', shortcut: '?', action: mostrarAtajos },
    { id: 'action-logout', label: 'Cerrar sesión', icon: '🚪', action: () => { window.location.href = '/auth/logout'; } },
  ];

  let paletteState = {
    open: false,
    query: '',
    activeIdx: 0,
    filtered: PALETTE_ACTIONS,
  };

  function crearPaletteUI() {
    if (document.getElementById('sds-palette-backdrop')) return;
    const backdrop = document.createElement('div');
    backdrop.className = 'sds-palette-backdrop';
    backdrop.id = 'sds-palette-backdrop';
    backdrop.innerHTML = `
      <div class="sds-palette" role="dialog" aria-label="Comando rápido">
        <input
          type="text"
          class="sds-palette-input"
          placeholder="Busca algo... (ej. analizar, mis glosas, alertas)"
          aria-label="Buscar comando"
        />
        <div class="sds-palette-results"></div>
        <div class="sds-palette-footer">
          <span><span class="sds-kbd">↑↓</span> navegar · <span class="sds-kbd">Enter</span> ejecutar · <span class="sds-kbd">Esc</span> cerrar</span>
          <span><span class="sds-kbd">⌘K</span> abrir</span>
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);

    const input = backdrop.querySelector('.sds-palette-input');
    const results = backdrop.querySelector('.sds-palette-results');

    input.addEventListener('input', () => {
      paletteState.query = input.value;
      filtrarYRenderizar(results);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        cerrarPalette();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        paletteState.activeIdx = Math.min(paletteState.activeIdx + 1, paletteState.filtered.length - 1);
        filtrarYRenderizar(results);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        paletteState.activeIdx = Math.max(paletteState.activeIdx - 1, 0);
        filtrarYRenderizar(results);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        ejecutarActivo();
      }
    });

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) cerrarPalette();
    });
  }

  function filtrarYRenderizar(container) {
    const q = paletteState.query.toLowerCase().trim();
    paletteState.filtered = q
      ? PALETTE_ACTIONS.filter(a => a.label.toLowerCase().includes(q) || (a.id && a.id.includes(q)))
      : PALETTE_ACTIONS;

    if (paletteState.activeIdx >= paletteState.filtered.length) {
      paletteState.activeIdx = 0;
    }

    container.innerHTML = paletteState.filtered.length === 0
      ? '<div style="padding:24px;text-align:center;color:var(--sds-gray-400);font-size:.85rem">Sin coincidencias</div>'
      : paletteState.filtered.map((a, i) => `
          <div class="sds-palette-item ${i === paletteState.activeIdx ? 'active' : ''}" data-idx="${i}">
            <div class="sds-palette-item-icon">${a.icon}</div>
            <div class="sds-palette-item-text">${a.label}</div>
            ${a.shortcut ? `<div class="sds-palette-item-shortcut">${a.shortcut}</div>` : ''}
          </div>
        `).join('');

    container.querySelectorAll('.sds-palette-item').forEach(el => {
      el.addEventListener('click', () => {
        paletteState.activeIdx = parseInt(el.dataset.idx, 10);
        ejecutarActivo();
      });
    });

    // Scroll into view del activo
    const active = container.querySelector('.sds-palette-item.active');
    if (active) active.scrollIntoView({ block: 'nearest' });
  }

  function abrirPalette() {
    crearPaletteUI();
    const backdrop = document.getElementById('sds-palette-backdrop');
    backdrop.classList.add('open');
    paletteState.open = true;
    paletteState.query = '';
    paletteState.activeIdx = 0;
    const input = backdrop.querySelector('.sds-palette-input');
    input.value = '';
    filtrarYRenderizar(backdrop.querySelector('.sds-palette-results'));
    setTimeout(() => input.focus(), 50);
  }

  function cerrarPalette() {
    const backdrop = document.getElementById('sds-palette-backdrop');
    if (backdrop) backdrop.classList.remove('open');
    paletteState.open = false;
  }

  function ejecutarActivo() {
    const action = paletteState.filtered[paletteState.activeIdx];
    if (action) {
      cerrarPalette();
      try { action.action(); } catch (e) { console.error('[SDS] action failed:', e); }
    }
  }

  // ──────────────────────────────────────────────────────────────────
  // 3. ATAJOS GLOBALES DE TECLADO
  // ──────────────────────────────────────────────────────────────────
  function installShortcuts() {
    document.addEventListener('keydown', (e) => {
      // No capturar si el usuario está escribiendo en un input/textarea
      const enInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);

      // ⌘K / Ctrl+K — Command Palette
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        paletteState.open ? cerrarPalette() : abrirPalette();
        return;
      }

      // Escape — salir de modo enfocado
      if (e.key === 'Escape' && document.body.classList.contains('sds-focus-mode')) {
        desactivarModoEnfocado();
        return;
      }

      // Si está en input, no procesar atajos de una sola letra
      if (enInput) return;

      switch (e.key.toLowerCase()) {
        case '?':
          e.preventDefault();
          mostrarAtajos();
          break;
        // Atajos de navegación
        case 'a':
          if (!e.altKey) return;
          e.preventDefault();
          navegarA('#p-analizar');
          break;
        case 'm':
          if (!e.altKey) return;
          e.preventDefault();
          navegarA('#p-mis-glosas');
          break;
        case 'h':
          if (!e.altKey) return;
          e.preventDefault();
          navegarA('#p-historial');
          break;
      }
    });
  }

  // ──────────────────────────────────────────────────────────────────
  // 4. UTILIDADES
  // ──────────────────────────────────────────────────────────────────
  function navegarA(panelId) {
    // Compatibilidad con el navegador SPA existente del app
    const ev = new CustomEvent('sds-nav', { detail: { panel: panelId } });
    document.dispatchEvent(ev);
    // Fallback: si hay un link/botón que apunte a ese panel, click
    const link = document.querySelector(`[data-panel="${panelId.replace('#p-', '')}"], a[href="${panelId}"]`);
    if (link) link.click();
  }

  function mostrarToast(mensaje) {
    let toast = document.querySelector('.sds-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'sds-toast';
      Object.assign(toast.style, {
        position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)',
        background: 'var(--sds-gray-900, #0f172a)', color: 'white',
        padding: '10px 18px', borderRadius: '8px', fontSize: '0.85rem',
        fontFamily: 'Inter, sans-serif', boxShadow: 'var(--sds-shadow-md)',
        zIndex: 99999, opacity: 0, transition: 'opacity .2s',
      });
      document.body.appendChild(toast);
    }
    toast.textContent = mensaje;
    toast.style.opacity = '1';
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { toast.style.opacity = '0'; }, 2400);
  }

  function mostrarAtajos() {
    const html = `
      <div style="font-family:Inter,sans-serif">
        <h3 style="margin:0 0 16px;font-size:1.1rem;color:var(--sds-gray-900)">⌨️ Atajos de teclado</h3>
        <table style="width:100%;border-collapse:collapse;font-size:.85rem">
          <tr><td style="padding:6px 0"><span class="sds-kbd">⌘K</span> / <span class="sds-kbd">Ctrl+K</span></td><td>Command Palette</td></tr>
          <tr><td style="padding:6px 0"><span class="sds-kbd">Esc</span></td><td>Salir de Modo Enfocado</td></tr>
          <tr><td style="padding:6px 0"><span class="sds-kbd">?</span></td><td>Mostrar esta ayuda</td></tr>
          <tr><td style="padding:6px 0"><span class="sds-kbd">Alt+A</span></td><td>Ir a Analizar glosa</td></tr>
          <tr><td style="padding:6px 0"><span class="sds-kbd">Alt+M</span></td><td>Ir a Mis glosas</td></tr>
          <tr><td style="padding:6px 0"><span class="sds-kbd">Alt+H</span></td><td>Ir a Historial</td></tr>
        </table>
        <p style="margin:16px 0 0;font-size:.75rem;color:var(--sds-gray-400)">
          Tip: <span class="sds-kbd">⌘K</span> es el camino más rápido. Empieza a escribir lo que necesitas.
        </p>
      </div>
    `;
    const overlay = document.createElement('div');
    Object.assign(overlay.style, {
      position: 'fixed', inset: 0, background: 'rgba(15,23,42,.6)',
      backdropFilter: 'blur(8px)', zIndex: 99999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      animation: 'sds-fade-in .2s',
    });
    overlay.innerHTML = `
      <div style="background:white;padding:24px 28px;border-radius:12px;
                  box-shadow:var(--sds-shadow-lg);max-width:480px;width:90vw">
        ${html}
      </div>
    `;
    overlay.addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
  }

  // ──────────────────────────────────────────────────────────────────
  // INIT
  // ──────────────────────────────────────────────────────────────────
  function init() {
    instalarIndicadorFocus();
    installAutoFocus();
    installShortcuts();
    console.log('[SINAC UX] Inicializado. Presiona ⌘K para abrir Command Palette.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Exponer API mínima para debugging
  window.SDS_UX = {
    abrir: abrirPalette,
    cerrar: cerrarPalette,
    focus: activarModoEnfocado,
    unfocus: desactivarModoEnfocado,
    ayuda: mostrarAtajos,
  };
})();
