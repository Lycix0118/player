import { VideoPlayerApp } from './app.js';
import { registerServiceWorker } from './utils/sw-register.js';

document.addEventListener('DOMContentLoaded', () => {
    window.videoPlayerApp = new VideoPlayerApp();
});

// PWA：注册 Service Worker 以支持安装到桌面与离线打开外壳。
// 非安全上下文（局域网 IP 的 http 访问）会自动跳过，不影响播放。
registerServiceWorker();
