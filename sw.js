/* VetDose Service Worker — cache-first para datos, network-first para el resto */
const CACHE   = 'vetdose-v1';
const PRECACHE = [
  './index.html',
  './manifest.json',
  './styles.css',
  './static/vademecum_base.json',
  './static/vademecum_dosis.json',
  './static/vademecum_admin.html',
];

/* Instalación: pre-cache de ficheros críticos */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

/* Activación: borrar caches antiguas */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

/* Fetch: cache-first para assets del precache; network-first para el resto */
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  /* Solo peticiones GET same-origin */
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;

  /* JSON grandes: stale-while-revalidate para tener siempre datos frescos */
  if (url.pathname.endsWith('.json')) {
    event.respondWith(
      caches.open(CACHE).then(async cache => {
        const cached = await cache.match(event.request);
        const fetchPromise = fetch(event.request).then(resp => {
          if (resp.ok) cache.put(event.request, resp.clone());
          return resp;
        }).catch(() => null);
        return cached || fetchPromise;
      })
    );
    return;
  }

  /* Resto: cache-first */
  event.respondWith(
    caches.match(event.request).then(cached =>
      cached || fetch(event.request).then(resp => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(event.request, clone));
        }
        return resp;
      })
    )
  );
});
