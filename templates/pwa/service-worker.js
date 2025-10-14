const CACHE_NAME = '{{ cache_name }}';
const PRECACHE_URLS = [
{% for url in asset_urls %}  '{{ url }}'{% if not forloop.last %},{% endif %}
{% endfor %}
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch((error) => console.warn('[kwc] Precache failed', error))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;

  if (request.method !== 'GET') {
    return;
  }

  const requestUrl = new URL(request.url);
  const isSameOrigin = requestUrl.origin === self.location.origin;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match('{{ offline_url }}'))
        )
    );
    return;
  }

  if (!isSameOrigin) {
    return;
  }

  const cacheControl = request.headers.get('Cache-Control') || '';
  const shouldBypassCache =
    requestUrl.pathname.includes('/api/') ||
    cacheControl.toLowerCase().includes('no-store') ||
    request.cache === 'no-store';

  if (shouldBypassCache) {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(null, {
          status: 503,
          statusText: 'Service Unavailable',
        })
      )
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type === 'opaque') {
            return response;
          }

          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request));
    })
  );
});
