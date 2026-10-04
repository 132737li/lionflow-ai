/* ==========================================
   LionFlow AI — Service Worker (PWA) v2
   Version améliorée : cache uniquement les statiques
   ========================================== */

const STATIC_CACHE = 'lionflow-static-v10';
const DYNAMIC_CACHE = 'lionflow-dynamic-v10';

// Uniquement les fichiers STATIQUES
const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/images/logo.png',
    '/static/images/icon-192x192.png',
    '/static/images/icon-512x512.png',
];

// ==========================================
// INSTALLATION
// ==========================================
self.addEventListener('install', (event) => {
    console.log('[SW] Installation v2');
    event.waitUntil(
        caches.open(STATIC_CACHE).then((cache) => {
            return cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn('[SW] Erreur mise en cache:', err);
            });
        })
    );
    self.skipWaiting();
});

// ==========================================
// ACTIVATION — supprime les anciens caches
// ==========================================
self.addEventListener('activate', (event) => {
    console.log('[SW] Activation v2');
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== STATIC_CACHE && key !== DYNAMIC_CACHE) {
                        console.log('[SW] Suppression cache:', key);
                        return caches.delete(key);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// ==========================================
// INTERCEPTION DES REQUÊTES
// ==========================================
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Ignorer tout sauf GET
    if (request.method !== 'GET') return;

    // Ignorer les requêtes externes (CDN, API, etc.)
    if (url.origin !== location.origin) return;

    // Ignorer l'API REST
    if (url.pathname.startsWith('/api/')) return;

    // Ignorer les webhooks
    if (url.pathname.includes('/webhook')) return;

    // Ignorer le Service Worker lui-même
    if (url.pathname === '/sw.js') return;

    // ---- Fichiers statiques : Cache First ----
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then((cached) => {
                if (cached) return cached;
                return fetch(request).then((response) => {
                    if (response && response.status === 200) {
                        const clone = response.clone();
                        caches.open(STATIC_CACHE).then((cache) => {
                            cache.put(request, clone);
                        });
                    }
                    return response;
                });
            }).catch(() => {
                // Fallback silencieux si offline
                return new Response('', { status: 503 });
            })
        );
        return;
    }

    // ---- Pages HTML : Network First (PAS de fallback "Hors connexion") ----
    // On laisse le navigateur gérer les erreurs normalement
    event.respondWith(
        fetch(request)
            .then((response) => {
                // Cache les pages réussies seulement
                if (response && response.status === 200) {
                    const clone = response.clone();
                    caches.open(DYNAMIC_CACHE).then((cache) => {
                        cache.put(request, clone);
                    });
                }
                return response;
            })
            .catch(() => {
                // En cas d'erreur réseau, on cherche dans le cache
                return caches.match(request).then((cached) => {
                    if (cached) return cached;
                    // Sinon, on laisse le navigateur afficher son erreur
                    // (plus de page "Hors connexion" custom)
                    throw new Error('Offline');
                });
            })
    );
    // ==========================================
// NOTIFICATIONS PUSH
// ==========================================
self.addEventListener('push', (event) => {
    console.log('[SW] Push reçu');

    let data = {
        title: 'LionFlow AI',
        body: 'Nouvelle notification',
        icon: '/static/images/icon-192x192.png',
        badge: '/static/images/icon-96x96.png',
        url: '/',
    };

    if (event.data) {
        try {
            data = Object.assign(data, event.data.json());
        } catch (e) {
            console.warn('[SW] Payload push invalide:', e);
        }
    }

    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.badge,
        vibrate: [200, 100, 200],
        tag: data.tag || 'lionflow-notification',
        renotify: true,
        requireInteraction: false,
        data: {
            url: data.url || '/',
        },
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// ==========================================
// CLIC SUR NOTIFICATION
// ==========================================
self.addEventListener('notificationclick', (event) => {
    console.log('[SW] Notification cliquée');
    event.notification.close();

    const url = (event.notification.data && event.notification.data.url) || '/';
    const fullUrl = new URL(url, self.location.origin).href;

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // Si une fenêtre de l'app est déjà ouverte, la focus
            for (const client of clientList) {
                if (client.url === fullUrl && 'focus' in client) {
                    return client.focus();
                }
            }
            // Sinon, ouvre une nouvelle fenêtre
            if (clients.openWindow) {
                return clients.openWindow(fullUrl);
            }
        })
    );
});
});