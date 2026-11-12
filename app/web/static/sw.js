/* Service worker AMA. Servit din rădăcină (/sw.js) ca să controleze tot site-ul.
 * Ține în cache DOAR fișiere statice din /static/. Niciodată HTML, JSON sau răspunsuri autentificate:
 * orice altă cerere trece direct la rețea (nu apelăm respondWith). */
const CACHE = 'ama-static-v1';
const PRECACHE = [
  '/static/css/tema.css',
  '/static/js/app.js',
  '/static/vendor/htmx-2.0.4.min.js',
  '/static/vendor/alpine-csp-3.14.9.min.js',
  '/static/icons/icon-192.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((chei) => Promise.all(chei.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) {
    return; // rețea, fără cache
  }
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const gasit = await cache.match(req);
      const reincarca = fetch(req).then((rasp) => {
        if (rasp.ok) cache.put(req, rasp.clone());
        return rasp;
      });
      return gasit || reincarca;
    })
  );
});

self.addEventListener('push', (event) => {
  let date = {};
  try { date = event.data ? event.data.json() : {}; } catch (e) { date = {}; }
  const titlu = typeof date.titlu === 'string' && date.titlu ? date.titlu : 'AMA';
  const optiuni = {
    body: typeof date.text === 'string' ? date.text : '',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    tag: typeof date.nivel === 'string' ? date.nivel : 'ama',
    data: { url: typeof date.url === 'string' ? date.url : '/' },
  };
  event.waitUntil(self.registration.showNotification(titlu, optiuni));
});

function adresaSigura(valoare) {
  try {
    const u = new URL(valoare, self.location.origin);
    return u.origin === self.location.origin ? u.href : self.location.origin + '/';
  } catch (e) {
    return self.location.origin + '/';
  }
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const tinta = adresaSigura(event.notification.data && event.notification.data.url);
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((ferestre) => {
      for (const f of ferestre) {
        if (f.url.startsWith(self.location.origin) && 'focus' in f) {
          return f.focus().then((c) => ('navigate' in c ? c.navigate(tinta) : c));
        }
      }
      return self.clients.openWindow(tinta);
    })
  );
});
