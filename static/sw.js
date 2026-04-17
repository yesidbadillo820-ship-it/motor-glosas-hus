// Service Worker para Motor Glosas HUS - cache shell + estrategia red-primero para datos.
const CACHE = 'hus-glosas-v1';
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

  // Estáticos: cache-first con actualización en segundo plano
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
