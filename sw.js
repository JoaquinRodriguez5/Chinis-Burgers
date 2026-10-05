const CACHE_NAME = 'chinis-burgers-live';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// Estrategia: Buscar SIEMPRE en la red primero
self.addEventListener('fetch', (event) => {
  // Ignorar peticiones a la API de Render
  if (event.request.url.includes('onrender.com')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Si la red responde bien, guardamos una copia y mostramos lo NUEVO
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Si NO hay internet, recién ahí usa lo guardado en memoria
        return caches.match(event.request);
      })
  );
});