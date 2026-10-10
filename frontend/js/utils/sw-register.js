/**
 * 注册 PWA 的 Service Worker。
 *
 * 注意：SW 脚本本身在 frontend/sw.js（后端 catch-all 把它映射为 /sw.js），
 * 不能放进本目录 —— SW 的作用域由脚本 URL 决定，/js/sw.js 只能拿到 /js/ 作用域，
 * 页面就不在它的控制范围内了。
 */

export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    return;
  }

  // Service Worker 只在「安全上下文」生效：https 或 localhost / 127.0.0.1。
  // 通过局域网 IP（http://192.168.x.x:8000）访问时浏览器会拒绝注册，
  // 这里静默跳过，播放功能完全不受影响。
  if (!window.isSecureContext) {
    console.info(
      '[PWA] 当前是非安全上下文（需 https 或 localhost），跳过 Service Worker 注册。' +
        '局域网 IP 访问时 PWA 安装与离线缓存不可用，属浏览器限制。'
    );
    return;
  }

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then((registration) => {
        console.info('[PWA] Service Worker 已注册，作用域:', registration.scope);

        registration.addEventListener('updatefound', () => {
          const installing = registration.installing;
          if (!installing) return;
          installing.addEventListener('statechange', () => {
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              console.info('[PWA] 已有新版本在后台就绪，下次打开自动生效');
            }
          });
        });
      })
      .catch((error) => {
        console.warn('[PWA] Service Worker 注册失败:', error);
      });
  });
}
