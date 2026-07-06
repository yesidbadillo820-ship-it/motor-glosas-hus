/* ═══════════════════════════════════════════════════════════════════
   SINAC Asistente Predictivo — Frontend para Ola 4
   Motor Glosas HUS 2.0 — Plan Transformación, mayo 2026.

   Llama a /asistente/predecir con debounce 250ms mientras el gestor
   escribe en el textarea de "Texto de la glosa", y muestra debajo:
     - Códigos detectados
     - Valor detectado
     - Plantilla predicha
     - Complejidad estimada + modelo IA que se usará
     - Sugerencias contextuales

   NO bloquea ni interfiere con el flujo existente — solo añade un
   panel de "Detección automática" debajo del textarea.
═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  const DEBOUNCE_MS = 250;
  let timer = null;
  let ultimoTexto = '';

  function token() {
    return (
      localStorage.getItem('token') ||
      localStorage.getItem('auth_token') ||
      localStorage.getItem('jwt') ||
      ''
    );
  }

  function obtenerEPSActual() {
    const sel = document.querySelector('select[name="eps"], #eps-select, select[id*="eps"]');
    return sel ? sel.value : '';
  }

  function obtenerTextarea() {
    return document.querySelector('textarea[name="tabla_excel"], textarea[id*="texto"]');
  }

  function obtenerPanel() {
    let panel = document.getElementById('sds-asistente-panel');
    if (panel) return panel;

    const textarea = obtenerTextarea();
    if (!textarea) return null;

    panel = document.createElement('div');
    panel.id = 'sds-asistente-panel';
    panel.style.cssText = `
      margin-top: 10px;
      padding: 12px 14px;
      background: linear-gradient(135deg, #f0f9ff, #fafafa);
      border: 1px solid var(--sds-blue-500, #3b82f6);
      border-radius: var(--sds-radius-md, 8px);
      font-family: Inter, sans-serif;
      font-size: .78rem;
      color: var(--sds-gray-900, #0f172a);
      box-shadow: var(--sds-shadow-sm, 0 1px 2px rgba(0,0,0,.05));
      display: none;
      animation: sds-fade-in .25s ease;
    `;
    textarea.parentElement.insertBefore(panel, textarea.nextSibling);
    return panel;
  }

  function chip(label, value, color = 'var(--sds-blue-700)') {
    return `<span style="display:inline-flex;align-items:center;gap:4px;
            background:white;padding:3px 8px;border-radius:999px;
            border:1px solid var(--sds-gray-200,#e2e8f0);font-size:.72rem;
            color:${color};margin-right:6px;margin-bottom:4px">
            <span style="opacity:.7;font-weight:500">${label}</span>
            <strong>${value}</strong></span>`;
  }

  function renderPrediccion(data) {
    const panel = obtenerPanel();
    if (!panel) return;
    if (!data.codigos_detectados.length && !data.valores_detectados.length) {
      panel.style.display = 'none';
      return;
    }

    const chips = [];
    if (data.codigos_detectados.length) {
      chips.push(chip('Código', data.codigos_detectados.join(', ')));
    }
    if (data.valor_principal) {
      chips.push(
        chip(
          'Valor',
          new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })
            .format(data.valor_principal)
        )
      );
    }
    if (data.numero_factura) chips.push(chip('Factura', data.numero_factura));
    if (data.fecha_detectada) chips.push(chip('Fecha', data.fecha_detectada));

    const complejidadColor = {
      SIMPLE: 'var(--sds-success, #16a34a)',
      MEDIA: 'var(--sds-blue-700, #1d4ed8)',
      COMPLEJA: 'var(--sds-amber, #d97706)',
    }[data.complejidad_estimada] || 'inherit';
    chips.push(chip('Complejidad', data.complejidad_estimada, complejidadColor));

    if (data.es_ratificacion) chips.push(chip('Tipo', 'Ratificación', 'var(--sds-amber)'));
    if (data.es_extemporanea) chips.push(chip('Tipo', 'Extemporánea', 'var(--sds-amber)'));

    let plantillaHTML = '';
    if (data.plantilla_predicha) {
      const p = data.plantilla_predicha;
      const conf = Math.round(p.confianza * 100);
      plantillaHTML = `
        <div style="margin-top:8px;padding-top:8px;border-top:1px dashed var(--sds-gray-200,#e2e8f0)">
          <span style="font-weight:600;color:var(--sds-gray-600)">📋 Plantilla predicha:</span>
          <strong style="color:var(--sds-blue-700)">${p.plantilla_id}</strong>
          <span style="color:var(--sds-gray-400)">·</span>
          ${p.titulo}
          <span style="color:var(--sds-gray-400);font-size:.7rem">(${conf}% confianza)</span>
        </div>`;
    }

    let modeloHTML = '';
    if (data.modelo_recomendado) {
      const m = data.modelo_recomendado;
      modeloHTML = `
        <div style="margin-top:6px;font-size:.72rem;color:var(--sds-gray-600)">
          🧠 IA: <strong>${m.modelo}</strong>
          (${m.complejidad} · ~${m.tiempo_estimado_s}s)
          — ${m.razon}
        </div>`;
    }

    let sugerenciasHTML = '';
    if (data.sugerencias && data.sugerencias.length) {
      sugerenciasHTML =
        '<div style="margin-top:10px;border-top:1px solid var(--sds-gray-200,#e2e8f0);padding-top:8px">' +
        data.sugerencias
          .slice(0, 3)
          .map((s) => {
            const bg = s.tipo === 'warning'
              ? 'var(--sds-amber-bg, #fffbeb)'
              : s.tipo === 'victoria_previa'
              ? 'var(--sds-success-bg, #f0fdf4)'
              : 'white';
            const accion = s.accion_label && s.accion_url
              ? `<a href="${s.accion_url}" style="color:var(--sds-blue-700);font-size:.7rem">${s.accion_label} →</a>`
              : '';
            return `<div style="background:${bg};padding:6px 10px;border-radius:6px;margin-bottom:4px">
                      <strong style="font-size:.78rem">${s.titulo}</strong>
                      <div style="font-size:.72rem;color:var(--sds-gray-600);margin-top:2px">${s.descripcion} ${accion}</div>
                    </div>`;
          })
          .join('') +
        '</div>';
    }

    panel.innerHTML = `
      <div style="font-weight:600;font-size:.72rem;letter-spacing:.05em;
                  text-transform:uppercase;color:var(--sds-gray-600);margin-bottom:6px">
        ⚡ DETECCIÓN AUTOMÁTICA (en tiempo real)
      </div>
      <div>${chips.join('')}</div>
      ${plantillaHTML}
      ${modeloHTML}
      ${sugerenciasHTML}
    `;
    panel.style.display = 'block';
  }

  async function predecir(texto, eps) {
    if (!texto || texto.length < 5) {
      const p = obtenerPanel();
      if (p) p.style.display = 'none';
      return;
    }
    const t = token();
    if (!t) return;

    try {
      const r = await fetch('/asistente/predecir', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer ' + t,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ texto: texto, eps: eps || '' }),
      });
      if (!r.ok) return;
      const data = await r.json();
      renderPrediccion(data);
    } catch (e) {
      // Falla silenciosa — el asistente es valor agregado, no crítico
      console.debug('[SDS Asistente] fallo:', e.message);
    }
  }

  function attachListeners() {
    const textarea = obtenerTextarea();
    if (!textarea || textarea._sdsAttached) return;
    textarea._sdsAttached = true;

    textarea.addEventListener('input', () => {
      const txt = textarea.value;
      if (txt === ultimoTexto) return;
      ultimoTexto = txt;
      clearTimeout(timer);
      timer = setTimeout(() => predecir(txt, obtenerEPSActual()), DEBOUNCE_MS);
    });
    console.log('[SINAC Asistente] Listo. Empezá a escribir en el textarea.');
  }

  // Reintentar attach periódicamente porque el textarea puede renderizarse
  // tarde si el panel se carga después de la sidebar.
  function init() {
    attachListeners();
    setInterval(attachListeners, 2000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
