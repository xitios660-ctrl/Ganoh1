// GANOH Café Bistrô Service Worker
const CACHE_NAME = 'ganoh-cafe-v1';
const STATIC_CACHE = 'ganoh-static-v1';
const API_CACHE = 'ganoh-api-v1';

// Static assets to cache
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json'
];

// API routes to cache
const API_ROUTES = [
  '/api/stores',
  '/api/menu/runner',
  '/api/menu/gym-londres',
  '/api/categories'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      console.log('[SW] Caching static assets');
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (![CACHE_NAME, STATIC_CACHE, API_CACHE].includes(cache)) {
            console.log('[SW] Deleting old cache:', cache);
            return caches.delete(cache);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch event - serve from cache, update in background
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests except for order sync
  if (request.method !== 'GET') {
    // Handle offline order submission
    if (request.method === 'POST' && url.pathname.includes('/api/orders') && !url.pathname.includes('/sync')) {
      event.respondWith(handleOfflineOrder(request));
      return;
    }
    return;
  }

  // API requests - network first, cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request));
    return;
  }

  // Static assets - cache first, network fallback
  event.respondWith(cacheFirstStrategy(request));
});

// Network first strategy for API
async function networkFirstStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // Return offline fallback for menu requests
    if (request.url.includes('/api/menu/')) {
      return new Response(JSON.stringify({
        items: [],
        categories: [],
        adicionais: [],
        store: { name: 'Offline Mode' },
        offline: true
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    throw error;
  }
}

// Cache first strategy for static assets
async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    // Update cache in background
    fetch(request).then(response => {
      if (response.ok) {
        caches.open(STATIC_CACHE).then(cache => {
          cache.put(request, response);
        });
      }
    }).catch(() => {});
    return cachedResponse;
  }
  
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    // Return offline page for navigation requests
    if (request.mode === 'navigate') {
      return caches.match('/');
    }
    throw error;
  }
}

// Handle offline order submission
async function handleOfflineOrder(request) {
  try {
    const networkResponse = await fetch(request.clone());
    return networkResponse;
  } catch (error) {
    // Store order for later sync
    const orderData = await request.json();
    
    // Notify client to store order locally
    self.clients.matchAll().then(clients => {
      clients.forEach(client => {
        client.postMessage({
          type: 'OFFLINE_ORDER',
          order: orderData
        });
      });
    });
    
    // Return success response with offline flag
    return new Response(JSON.stringify({
      success: true,
      offline: true,
      message: 'Pedido salvo localmente. Será sincronizado quando a conexão for restaurada.',
      order: {
        ...orderData,
        id: `offline_${Date.now()}`,
        status: 'pending_sync'
      }
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// Background sync for offline orders
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-orders') {
    event.waitUntil(syncOfflineOrders());
  }
});

// Sync offline orders
async function syncOfflineOrders() {
  // This will be handled by the main app
  self.clients.matchAll().then(clients => {
    clients.forEach(client => {
      client.postMessage({
        type: 'SYNC_ORDERS'
      });
    });
  });
}

// Listen for messages from main app
self.addEventListener('message', (event) => {
  if (event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data.type === 'CACHE_MENU') {
    // Cache menu data
    const { store, data } = event.data;
    caches.open(API_CACHE).then(cache => {
      const response = new Response(JSON.stringify(data));
      cache.put(`/api/menu/${store}`, response);
    });
  }
});
