// Service Worker para Motor Glosas HUS - cache shell + estrategia red-primero para datos.
// ⚠ IMPORTANTE: subir la versión del cache cada vez que cambie el HTML/CSS/JS
//   estático para que los clientes existentes reciban la nueva versión.
const CACHE = 'hus-glosas-v5';
const SHELL = [
  '/',
  '/manifest.webmanifest',
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
      keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
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

  // API y POSTs: red-primero, sin caché (evita servir datos viejos)
  if (url.pathname.startsWith('/glosas') || url.pathname.startsWith('/analizar') ||
      url.pathname.startsWith('/conciliaciones') || url.pathname.startsWith('/admin') ||
      url.pathname.startsWith('/mi-desempeno') || url.pathname.startsWith('/busqueda-semantica') ||
      url.pathname.startsWith('/informes') || url.pathname.startsWith('/plantillas-gold') ||
      url.pathname.startsWith('/audit') || url.pathname.startsWith('/usuarios')) {
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
      }).catch(() => caches.match(req))
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
