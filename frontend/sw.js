// Service Worker for PWA functionality - v3
const CACHE_NAME = 'kids-video-player-v3';
const urlsToCache = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/manifest.json',
  '/icon-192x192.png',
  '/vendor/plyr.css',
  '/vendor/plyr.js'
];

// 安装 Service Worker
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] 预缓存应用骨架');
      return cache.addAll(urlsToCache);
    })
  );
});

// 更新与清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] 删除旧缓存:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 拦截网络请求
self.addEventListener('fetch', (event) => {
  // 只处理 GET 请求
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);

  // 严格排除：动态 API、视频流、封面、字幕以及 Range 请求绝不走 SW 缓存
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/static/') ||
    url.pathname.startsWith('/covers/') ||
    url.pathname.startsWith('/subtitles/') ||
    event.request.headers.has('range')
  ) {
    return; // 直接由浏览器原生网络处理
  }

  // 对静态资源采用 Network-First（网络优先，弱网/离线降级到缓存）
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // 网络失败时降级到本地缓存
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // 如果导航请求失败，返回首页
          if (event.request.mode === 'navigate') {
            return caches.match('/index.html');
          }
          return new Response('Offline resource not available', { status: 503 });
        });
      })
  );
});