/* Service Worker —— 儿童视频播放器
 *
 * ⚠️ 位置说明（不要挪走）
 *   本文件必须留在 frontend/ 根目录：后端的 catch-all 路由把它映射为 /sw.js。
 *   Service Worker 的作用域由**脚本自身的 URL** 决定，只有 /sw.js 才能拿到根作用域 /，
 *   从而接管 index.html（由 / 提供）。若挪到 frontend/js/ 下会退化成 /js/ 作用域，
 *   页面根本不在控制范围内。这是「前端 JS 一律放 js/」约定的唯一例外。
 *
 * 缓存边界（改这里之前先读）
 *   缓存   静态壳（HTML / CSS / JS 模块 / vendor / 图标 / manifest）
 *          /covers/* 封面、/subtitles/* 字幕（cache-first，内容基本不变）
 *   不缓存 /api/hls/*  m3u8 每次请求都要重新解析直链（后端已带 no-store），
 *                     分片是流式数据，缓存既拿不到完整响应体又会撑爆配额
 *          /static/*   <video> 会发 Range 请求，Cache API 不支持部分响应
 *          其余 /api/*  观看进度、限时心跳、设置、缓存状态必须实时
 */

const VERSION = 'v1';
const SHELL_CACHE = `player-shell-${VERSION}`;
const MEDIA_CACHE = `player-media-${VERSION}`;

/* 封面 + 字幕的缓存条目上限，超出后按插入顺序淘汰最旧的。
   防止长期使用后 Cache Storage 无限增长。 */
const MEDIA_CACHE_LIMIT = 300;

/* 预缓存的应用外壳。
   注意不含带 ?v= 的入口文件（js/main.js、styles.css 在页面里带版本 query），
   那些由下面的 stale-while-revalidate 在首次访问时写入缓存。 */
const SHELL_ASSETS = [
  '/',
  '/styles.css',
  '/styles/tokens.css',
  '/styles/base.css',
  '/styles/layout.css',
  '/styles/library.css',
  '/styles/settings.css',
  '/styles/player.css',
  '/styles/timelimits.css',
  '/vendor/plyr.css',
  '/vendor/plyr.js',
  '/vendor/hls.min.js',
  '/manifest.json',
  '/icon-192x192.png',
  '/icon-512x512.png',
];

/* ---------------------------------------------------------------- install */

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      /* 逐个添加：任一个资源 404 / 超时都不应让整批预缓存失败 */
      await Promise.allSettled(
        SHELL_ASSETS.map(async (asset) => {
          try {
            const response = await fetch(asset, { cache: 'reload' });
            if (response && response.ok) await cache.put(asset, response);
          } catch (err) {
            /* 单个资源失败可忽略，运行时还会再补 */
          }
        })
      );
      await self.skipWaiting();
    })()
  );
});

/* --------------------------------------------------------------- activate */

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith('player-') && key !== SHELL_CACHE && key !== MEDIA_CACHE)
          .map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

/* ------------------------------------------------------------------ fetch */

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  /* 只接管同源请求 */
  if (url.origin !== self.location.origin) return;

  /* 非 GET（进度上报、设置保存、创建下载任务等）一律直连 */
  if (request.method !== 'GET') return;

  /* 视频流与分片：完全不拦截 —— 详见文件头的缓存边界说明 */
  if (url.pathname.startsWith('/api/hls/') || url.pathname.startsWith('/static/')) return;

  /* 其余接口：网络直连，不做缓存 */
  if (url.pathname.startsWith('/api/')) return;

  /* 封面：文件名基于 episode_id，内容不会变 → cache-first */
  if (url.pathname.startsWith('/covers/')) {
    event.respondWith(cacheFirst(request, MEDIA_CACHE, MEDIA_CACHE_LIMIT));
    return;
  }

  /* 字幕：同样 cache-first */
  if (url.pathname.startsWith('/subtitles/')) {
    event.respondWith(cacheFirst(request, MEDIA_CACHE, MEDIA_CACHE_LIMIT));
    return;
  }

  /* 页面导航：network-first，离线时回退到缓存的首页外壳 */
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, SHELL_CACHE, '/'));
    return;
  }

  /* 其余静态资源（CSS / JS 模块 / vendor / 图标）：stale-while-revalidate */
  event.respondWith(staleWhileRevalidate(request, SHELL_CACHE));
});

/* -------------------------------------------------------------- 策略实现 */

/** 缓存优先；未命中再走网络并写入缓存。 */
async function cacheFirst(request, cacheName, limit) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request, { ignoreSearch: true });
  if (hit) return hit;

  try {
    const response = await fetch(request);
    if (response && response.ok) {
      await cache.put(request, response.clone());
      if (limit) await trimCache(cache, limit);
    }
    return response;
  } catch (err) {
    return new Response('', { status: 504, statusText: 'Offline' });
  }
}

/** 网络优先；失败时依次回退到自身缓存与 fallbackUrl 对应的外壳缓存。 */
async function networkFirst(request, cacheName, fallbackUrl) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response && response.ok) await cache.put(request, response.clone());
    return response;
  } catch (err) {
    const hit = await cache.match(request, { ignoreSearch: true });
    if (hit) return hit;
    if (fallbackUrl) {
      const fallback = await cache.match(fallbackUrl, { ignoreSearch: true });
      if (fallback) return fallback;
    }
    return new Response('<h1>当前离线</h1><p>请连接局域网后重试。</p>', {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }
}

/** 先返回缓存，同时后台拉取新版本写回缓存。 */
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request, { ignoreSearch: true });

  const network = fetch(request)
    .then(async (response) => {
      if (response && response.ok) await cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);

  return cached || (await network) || new Response('', { status: 504, statusText: 'Offline' });
}

/** 条目超出上限时，按插入顺序淘汰最旧的。 */
async function trimCache(cache, limit) {
  try {
    const keys = await cache.keys();
    if (keys.length <= limit) return;
    const excess = keys.length - limit;
    for (let i = 0; i < excess; i += 1) {
      await cache.delete(keys[i]);
    }
  } catch (err) {
    /* 淘汰失败不影响主流程 */
  }
}
