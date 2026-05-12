// Service Worker para Motor Glosas HUS - cache shell + estrategia red-primero para datos.
// ⚠ IMPORTANTE: subir la versión del cache cada vez que cambie el HTML/CSS/JS
//   estático para que los clientes existentes reciban la nueva versión.
const CACHE = 'hus-glosas-v7';
const RUNTIME_CACHE = 'hus-runtime-v1';
const SHELL = [
  '/',
  '/manifest.webmanifest',
];

// Whitelist de endpoints API que se pueden cachear (read-only, datos
// poco volatiles). Cuando estamos offline servimos lo cacheado.
const CACHEABLE_API_PATTERNS = [
  /^\/usuarios\/yo$/,
  /^\/usuarios\/yo\/heatmap/,
  /^\/contratos\/?$/,
  /^\/cups\/buscar/,
  /^\/snippets$/,
  /^\/presets-filtros$/,
  /^\/notificaciones\/badge$/,
  /^\/version$/,
  /^\/health$/,
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE && k !== RUNTIME_CACHE).map((k) => caches.delete(k))
    ))
  );
  self.clients.claim();
});

// ─── PUSH NOTIFICATIONS (Tier 4 #15) ──────────────────────────────
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = { title: 'Motor Glosas HUS', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'Motor Glosas HUS';
  const opts = {
    body: data.body || '',
    icon: data.icon || '/static/icon-192.png',
    badge: data.badge || '/static/icon-192.png',
    tag: data.tag || 'motor-glosas',
    data: { url: data.url || '/' },
    requireInteraction: data.requireInteraction || false,
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((wins) => {
      for (const w of wins) {
        if (w.url.includes(url) && 'focus' in w) return w.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});

// ─── SYNC OFFLINE (Tier 4 #18 stub) ────────────────────────────────
self.addEventListener('sync', (event) => {
  if (event.tag === 'flush-drafts') {
    // Hook futuro: empujar drafts pendientes guardados en IndexedDB
  }
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // API endpoints CACHEABLES (read-only, datos relativamente estables):
  // estrategia stale-while-revalidate. Sirve lo cacheado al instante,
  // refresca en background. Si esta offline, cacheado salva el dia.
  if (CACHEABLE_API_PATTERNS.some((p) => p.test(url.pathname))) {
    e.respondWith(
      caches.open(RUNTIME_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        const fetchPromise = fetch(req).then((networkResp) => {
          if (networkResp && networkResp.ok) {
            cache.put(req, networkResp.clone()).catch(() => {});
          }
          return networkResp;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // API y POSTs no whitelisteados: red-primero, sin cache (evita datos viejos)
  if (url.pathname.startsWith('/glosas') || url.pathname.startsWith('/analizar') ||
      url.pathname.startsWith('/conciliaciones') || url.pathname.startsWith('/admin') ||
      url.pathname.startsWith('/mi-desempeno') || url.pathname.startsWith('/busqueda-semantica') ||
      url.pathname.startsWith('/informes') || url.pathname.startsWith('/plantillas-gold') ||
      url.pathname.startsWith('/audit') || url.pathname.startsWith('/usuarios') ||
      url.pathname.startsWith('/eventos') || url.pathname.startsWith('/dashboard') ||
      url.pathname.startsWith('/sistema') || url.pathname.startsWith('/auditor') ||
      url.pathname.startsWith('/asistente') || url.pathname.startsWith('/chat') ||
      url.pathname.startsWith('/notas-privadas') || url.pathname.startsWith('/comentarios') ||
      url.pathname.startsWith('/webhooks') || url.pathname.startsWith('/push') ||
      url.pathname.startsWith('/prediccion-ia') || url.pathname.startsWith('/rutas-facturas')) {
    return; // browser handles normally
  }

  // Documentos HTML (páginas): RED-primero, con fallback al cache si no hay
  // red. Esto garantiza que cambios recién desplegados se reflejen al instante
  // sin obligar al usuario a limpiar caché.
  const acceptsHTML = (req.headers.get('accept') || '').includes('text/html');
  const esPagina = req.mode === 'navigate' || acceptsHTML;
  if (esPagina) {
    e.respondWith(
      fetch(req).then((networkResp) => {
        if (networkResp && networkResp.ok) {
          const clone = networkResp.clone();
          caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => {});
        }
        return networkResp;
      }).catch(() => caches.match(req).then((cached) => {
        if (cached) return cached;
        // Offline fallback: pagina inline que avisa
        return new Response(
          '<!doctype html><html><head><meta charset="utf-8"><title>Sin conexion</title>'+
          '<style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#f1f5f9;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem;text-align:center}'+
          '.box{max-width:400px}h1{font-size:1.5rem;margin:0 0 .5rem}p{color:#94a3b8;line-height:1.5}'+
          'button{margin-top:1rem;background:#0ea5e9;color:#fff;border:0;padding:.65rem 1.2rem;border-radius:8px;cursor:pointer;font-size:.85rem}</style>'+
          '</head><body><div class="box"><h1>Sin conexion</h1>'+
          '<p>Estas offline. El motor necesita internet para responder glosas, pero los datos cacheados siguen disponibles.</p>'+
          '<button onclick="location.reload()">Reintentar</button></div></body></html>',
          { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      }))
    );
    return;
  }

  // Estáticos (imágenes, fuentes, íconos): cache-first con actualización
  // en segundo plano.
  e.respondWith(
    caches.match(req).then((cached) => {
      const fetchPromise = fetch(req).then((networkResp) => {
        if (networkResp && networkResp.ok) {
          const clone = networkResp.clone();
          caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => {});
        }
        return networkResp;
      }).catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
