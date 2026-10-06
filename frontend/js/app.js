import { ApiClient } from './api/client.js';
import { createAppState } from './state/app-state.js';
import { createSettingsState, updateSetting as persistSetting } from './state/settings-state.js';
import { ScreenRouter } from './views/screen-router.js';
import { createToast } from './components/toast.js';
import { escapeHtml as escapeHtmlValue } from './utils/dom.js';

// 兼容迁移层：业务方法按功能逐步拆到 views/api 模块，暂时保留既有渲染行为。
export class VideoPlayerApp {
    constructor() {
        this.state = createAppState();
        this.api = new ApiClient(window.location.origin);
        this.router = new ScreenRouter({ onLeavePlayer: () => this.clearVideoPlayer() });
        this.notify = createToast();
        this.currentScreen = 'loading';
        this.currentFolder = null;
        this.currentVideo = null;
        this.apiBase = window.location.origin;
        this.subtitleEnabled = false;
        this.currentPath = [];  // 当前路径栈 ['folder1', 'subfolder1']
        this.folderHistory = []; // 导航历史
        this.player = null; // Plyr播放器实例
        this.currentVideos = [];
        this.watchProgress = {};
        this.downloadPoll = null;
        // 启动与就绪状态
        this.foldersLoaded = false;
        this.loadStartTime = Date.now();
        this.appEntered = false;
        this.settings = createSettingsState();
        
        this.init();
    }

    async init() {
        // 绑定事件监听器
        this.bindEvents();
        
        // 加载文件夹数据
        this.loadFolders();
    }

    escapeHtml(value) {
        return escapeHtmlValue(value);
    }

    bindEvents() {
        // 返回按钮
        document.getElementById('back-to-folders').addEventListener('click', () => {
            this.showScreen('folders');
        });
        
        document.getElementById('back-to-videos').addEventListener('click', () => {
            this.showScreen('videos');
        });
        document.getElementById('refresh-library')?.addEventListener('click', () => this.loadFolders(this.currentPath.join('/')));
        document.getElementById('video-search')?.addEventListener('input', () => this.renderVideos(this.currentVideos));
        document.getElementById('video-sort')?.addEventListener('change', () => this.renderVideos(this.currentVideos));
        document.getElementById('player-prev')?.addEventListener('click', () => this.playRelative(-1));
        document.getElementById('player-next')?.addEventListener('click', () => this.playRelative(1));

        // 返回上级文件夹按钮
        document.getElementById('back-to-parent').addEventListener('click', () => {
            this.navigateToParent();
        });

        document.getElementById('open-settings').addEventListener('click', () => this.openSettings());
        document.getElementById('back-from-settings').addEventListener('click', () => this.showScreen('folders'));
        document.getElementById('save-cookie').addEventListener('click', () => this.saveCookie());
        document.getElementById('toggle-cookie-visibility').addEventListener('click', () => this.toggleCookieVisibility());
        document.getElementById('clear-cache').addEventListener('click', () => this.clearCache());
        document.getElementById('setting-autoplay').addEventListener('change', (event) => this.updateSetting('autoplay', event.target.checked));
        document.getElementById('setting-subtitles').addEventListener('change', (event) => this.updateSetting('subtitles', event.target.checked));
        document.getElementById('theme-select').addEventListener('change', (event) => this.updateSetting('theme', event.target.value));
        this.applySettings();
    }

    loadSettings() {
        return createSettingsState();
    }

    updateSetting(key, value) {
        this.settings = persistSetting(this.settings, key, value);
        if (key === 'theme') this.applySettings();
    }

    applySettings() {
        const autoplay = document.getElementById('setting-autoplay');
        const subtitles = document.getElementById('setting-subtitles');
        const theme = document.getElementById('theme-select');
        if (autoplay) autoplay.checked = this.settings.autoplay;
        if (subtitles) subtitles.checked = this.settings.subtitles;
        if (theme) theme.value = this.settings.theme;
    }

    async openSettings() {
        const cookieInput = document.getElementById('bilibili-cookie');
        if (cookieInput) cookieInput.value = '';
        const status = document.getElementById('cookie-status');
        if (status) status.textContent = '正在读取状态…';
        this.applySettings();
        this.showScreen('settings');
        try {
            const response = await fetch(this.apiBase + '/api/settings/cookie/status');
            const data = await response.json();
            if (status) status.textContent = data.has_cookie ? '已配置 Cookie' : '尚未配置';
        } catch (error) { if (status) status.textContent = '无法读取状态'; }
        this.loadCacheStatus();
    }

    toggleCookieVisibility() {
        const input = document.getElementById('bilibili-cookie');
        const button = document.getElementById('toggle-cookie-visibility');
        if (!input || !button) return;
        input.classList.toggle('cookie-visible');
        button.textContent = input.classList.contains('cookie-visible') ? '隐藏' : '显示';
    }

    async saveCookie() {
        const input = document.getElementById('bilibili-cookie');
        const status = document.getElementById('cookie-status');
        const cookie = input?.value.trim() || '';
        if (!cookie) { this.showError('请先粘贴 Cookie'); return; }
        try {
            const response = await fetch(this.apiBase + '/api/settings/cookie', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cookie }) });
            if (!response.ok) throw new Error('save failed');
            input.value = '';
            if (status) status.textContent = '已保存 Cookie';
            this.showError('Cookie 保存成功');
        } catch (error) { if (status) status.textContent = '保存失败'; this.showError('Cookie 保存失败，请检查服务是否正常'); }
    }

    async loadCacheStatus() {
        const status = document.getElementById('cache-status');
        try {
            const response = await fetch(this.apiBase + '/api/cache/status');
            const data = await response.json();
            const size = data.current_cache_size_mb ?? data.total_size_mb ?? data.cache_size_mb ?? 0;
            if (status) status.textContent = '当前缓存 ' + size + ' MB';
        } catch (error) { if (status) status.textContent = '缓存状态不可用'; }
    }

    async clearCache() {
        if (!window.confirm('确定清理已下载的视频缓存吗？')) return;
        try {
            const response = await fetch(this.apiBase + '/api/cache/clean', { method: 'POST' });
            if (!response.ok) throw new Error('clean failed');
            await this.loadCacheStatus();
            this.showError('缓存清理完成');
        } catch (error) { this.showError('缓存清理失败'); }
    }

        // 字幕将由Plyr自动处理

    showScreen(screenName) {
        // 如果正在离开播放器屏幕，彻底停止并清理视频播放
        this.router.show(screenName);
        this.currentScreen = this.router.current;
        this.state.screen = this.currentScreen;
    }

    async loadFolders(path = '') {
        try {
            // 标准化路径：将反斜杠转换为正斜杠
            const normalizedPath = path ? path.replace(/\\/g, '/') : '';
            
            const url = normalizedPath && normalizedPath.trim() ? `${this.apiBase}/api/folders?path=${encodeURIComponent(normalizedPath)}` : `${this.apiBase}/api/folders`;
            const response = await fetch(url);
            const folders = await response.json();
            
            // 更新当前路径
            this.currentPath = (normalizedPath && normalizedPath.trim()) ? normalizedPath.split('/') : [];
            
            this.renderFolders(folders);
            await this.loadAllProgress(folders);
            this.renderContinueWatching();
            this.updateBreadcrumb();
            this.updateBackButton();
            // 数据就绪标记
            this.foldersLoaded = true;
            this.enterApp();
        } catch (error) {
            this.showError('加载文件夹失败');
            console.error('Error loading folders:', error);
            // 即使出错也平滑退出加载动画，不锁死界面
            this.enterApp();
        }
    }

    async loadAllProgress(folders) {
        const playable = (folders || []).filter(folder => typeof folder === 'object' && folder.has_list_file);
        const results = await Promise.all(playable.map(async folder => {
            try {
                const [videosResponse, progressResponse] = await Promise.all([
                    fetch(`${this.apiBase}/api/folders/${encodeURIComponent(folder.path)}`),
                    fetch(`${this.apiBase}/api/progress/${encodeURIComponent(folder.path)}`)
                ]);
                const videos = videosResponse.ok ? await videosResponse.json() : [];
                const progress = progressResponse.ok ? await progressResponse.json() : {};
                return videos.map(video => ({ ...video, folder_path: folder.path, progress: progress[`${folder.path}|${video.bvid}|${video.page}`] || null }));
            } catch (_) { return []; }
        }));
        this.libraryVideos = results.flat();
    }

    renderContinueWatching() {
        const section = document.getElementById('continue-section');
        const list = document.getElementById('continue-list');
        if (!section || !list) return;
        const items = (this.libraryVideos || []).filter(video => video.progress && !video.progress.completed && video.progress.position > 5).sort((a, b) => (b.progress.updated_at || 0) - (a.progress.updated_at || 0)).slice(0, 6);
        section.classList.toggle('hidden', items.length === 0);
        if (!items.length) return;
        document.getElementById('continue-count').textContent = `${items.length} 个未完成视频`;
        list.innerHTML = items.map(video => `<button class="continue-item" data-folder="${this.escapeHtml(video.folder_path)}" data-bvid="${this.escapeHtml(video.bvid)}" data-page="${video.page}"><span class="continue-icon">▶</span><span class="continue-copy"><strong>${this.escapeHtml(video.title)}</strong><small>${this.escapeHtml(video.folder_path)} · 已观看 ${Math.round(video.progress.position / Math.max(video.progress.duration, 1) * 100)}%</small></span></button>`).join('');
        list.querySelectorAll('.continue-item').forEach(button => button.addEventListener('click', async () => {
            const videos = await this.fetchVideos(button.dataset.folder);
            const video = videos.find(item => item.bvid === button.dataset.bvid && String(item.page) === button.dataset.page);
            if (video) this.playVideo(video, button.dataset.folder);
        }));
    }

    async fetchVideos(folderPath) {
        const response = await fetch(`${this.apiBase}/api/folders/${encodeURIComponent(folderPath)}`);
        if (!response.ok) throw new Error('视频列表加载失败');
        return response.json();
    }

    renderFolders(folders) {
        const container = document.getElementById('folders-list');
        container.innerHTML = '';
        const summary = document.getElementById('library-summary');
        if (summary) summary.textContent = folders.length ? `${folders.length} 个合集，选择一个开始播放` : '还没有视频合集';

        if (folders.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>📁 暂无文件夹</h3>
                    <p>请在 videos 目录下创建文件夹并添加 list.txt</p>
                </div>
            `;
            return;
        }

        folders.forEach((folder, index) => {
            const folderElement = document.createElement('div');
            folderElement.className = 'folder-item';
            //folderElement.style.animationDelay = `${index * 0.15}s`;
            folderElement.setAttribute('tabindex', '0'); // 键盘可访问性

            const folderName = typeof folder === 'string' ? folder : folder.name;
            const safeFolderName = this.escapeHtml(folderName);
            const hasVideos = typeof folder === 'object' && folder.has_list_file;
            const folderIcon = '📁'; // 统一使用文件夹图标

            const countBadge = (typeof folder === 'object' && folder.video_count && folder.video_count > 0)
                ? `<div class="folder-count">${this.escapeHtml(folder.video_count)} 部视频</div>`
                : '';

            folderElement.innerHTML = `
                <span class="folder-icon">${folderIcon}</span>
                <div class="folder-name">${safeFolderName}</div>
                ${countBadge}
            `;

            // 点击和键盘事件
            const handleActivation = () => {
                if (typeof folder === 'string') {
                    // 兼容旧格式（字符串）
                    this.loadVideos(folder);
                } else if (folder.has_list_file) {
                    // 有list.txt文件，进入视频列表
                    this.loadVideos(folder.path);
                } else {
                    // 纯文件夹，继续浏览子文件夹
                    this.loadFolders(folder.path);
                }
            };

            folderElement.addEventListener('click', handleActivation);
            folderElement.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleActivation();
                }
            });

            container.appendChild(folderElement);
        });
    }

    updateBreadcrumb() {
        // 需求：移除列表上方的第二处重复信息（面包屑）。
        // 做法：始终将面包屑隐藏，不再渲染路径项。
        const breadcrumb = document.getElementById('breadcrumb');
        if (breadcrumb) {
            breadcrumb.classList.add('hidden');
        }
        return;
    }
    
    updateBackButton() {
        const backButton = document.getElementById('back-to-parent');
        const foldersTitle = document.getElementById('folders-title');
        
        if (this.currentPath.length > 0) {
            backButton.classList.remove('hidden');
            foldersTitle.textContent = `📁 ${this.currentPath[this.currentPath.length - 1]}`;
        } else {
            backButton.classList.add('hidden');
            foldersTitle.textContent = '📁 选择文件夹';
        }
    }
    
    navigateToParent() {
        if (this.currentPath.length > 0) {
            // 计算父级路径
            const parentPathArray = this.currentPath.slice(0, -1);
            const parentPath = parentPathArray.length > 0 ? parentPathArray.join('/') : '';
            
            // 加载父级文件夹
            this.loadFolders(parentPath);
        }
    }

    async loadVideos(folderPath) {
        try {
            this.currentFolder = folderPath;
            const folderName = folderPath.split('/').pop() || folderPath;
            document.getElementById('folder-title').textContent = `📺 ${folderName}`;
            
            const response = await fetch(`${this.apiBase}/api/folders/${encodeURIComponent(folderPath)}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const videos = await response.json();
            try {
                const progressResponse = await fetch(`${this.apiBase}/api/progress/${encodeURIComponent(folderPath)}`);
                const progress = progressResponse.ok ? await progressResponse.json() : {};
                videos.forEach(video => { video.progress = progress[`${folderPath}|${video.bvid}|${video.page}`] || null; });
            } catch (_) {}
            this.currentVideos = videos;
            this.renderVideos(videos);
            this.showScreen('videos');

            // 异步加载封面
            this.loadCoversAsync(videos);
        } catch (error) {
            this.showError('加载视频列表失败');
            console.error('Error loading videos:', error);
        }
    }

    renderVideos(videos) {
        const container = document.getElementById('videos-list');
        container.innerHTML = '';

        const query = (document.getElementById('video-search')?.value || '').trim().toLowerCase();
        const sort = document.getElementById('video-sort')?.value || 'index';
        const visibleVideos = videos.filter(video => !query || String(video.title || '').toLowerCase().includes(query));
        visibleVideos.sort((a, b) => sort === 'title' ? String(a.title).localeCompare(String(b.title), 'zh-CN') : sort === 'progress' ? (b.progress?.updated_at || 0) - (a.progress?.updated_at || 0) : (a.index || 0) - (b.index || 0));

        if (visibleVideos.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>📺 暂无视频</h3>
                    <p>请在 list.txt 中添加 B站 或 silidm（电影先生）视频链接</p>
                </div>
            `;
            return;
        }

        visibleVideos.forEach((video, index) => {
            const videoElement = document.createElement('div');
            videoElement.className = 'video-item';
            const videoIndex = video.index || (index + 1);
            videoElement.dataset.videoIndex = videoIndex;
            videoElement.dataset.videoPage = video.page;
            videoElement.dataset.videoBvid = video.bvid || '';
            videoElement.setAttribute('tabindex', '0'); // 键盘可访问性

            // 如果已有本地缓存好的封面，直接展示，无需loading
            const hasCover = !!video.cover_url;
            const coverUrl = /^https?:\/\//i.test(String(video.cover_url || ''))
                ? video.cover_url
                : this.apiBase + video.cover_url;
            const thumbnailHTML = hasCover
                ? `<img src="${this.escapeHtml(coverUrl)}" alt="视频封面" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="placeholder-icon" style="display: none;">🎬</div>`
                : '<div class="placeholder-icon">🎬</div>';

            const progress = video.progress;
            const progressPercent = progress && progress.duration ? Math.min(100, Math.round(progress.position / progress.duration * 100)) : 0;
            const progressHTML = progressPercent > 0 ? `<div class="video-progress"><span style="width:${progressPercent}%"></span></div><div class="video-progress-label">${progress.completed ? '已看完' : `已观看 ${progressPercent}%`}</div>` : '';
            // 外部来源（silidm）加来源标识，方便与 B站 条目区分
            const sourceLabel = { silidm: ' · 电影先生' }[video.source] || '';
            videoElement.innerHTML = `
                <div class="video-thumbnail ${hasCover ? '' : 'loading'}">
                    ${thumbnailHTML}
                </div>
                <div class="video-info">
                    <div class="video-title">${this.escapeHtml(video.title)}</div>
                    <div class="video-page">第 ${this.escapeHtml(videoIndex)} 集${sourceLabel}</div>
                    ${video.duration ? `<div class="video-duration">${this.escapeHtml(this.formatDuration(video.duration))}</div>` : ''}
                    ${progressHTML}
                </div>
            `;

            // 点击和键盘事件
            const handleActivation = () => {
                this.playVideo(video, this.currentFolder);
            };

            videoElement.addEventListener('click', handleActivation);
            videoElement.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleActivation();
                }
            });

            container.appendChild(videoElement);
        });
    }

    async loadCoversAsync(videos) {
        if (!videos || videos.length === 0) return;

        // 仅对尚未加载封面的项发起拉取
        const needCovers = videos.filter(v => !v.cover_url && v.bvid);
        if (needCovers.length === 0) return;

        // 按 bvid 归类分组，支持单合集包含多个不同 BV
        const bvidMap = new Map();
        for (const v of needCovers) {
            if (!bvidMap.has(v.bvid)) {
                bvidMap.set(v.bvid, []);
            }
            bvidMap.get(v.bvid).push(v);
        }

        // 分组批量加载封面
        for (const [bvid, items] of bvidMap.entries()) {
            const pages = items.map(it => it.page);
            try {
                const response = await fetch(`${this.apiBase}/api/batch/covers/${bvid}?pages=${pages.join(',')}`);
                if (response.ok) {
                    const data = await response.json();
                    if (data && data.covers) {
                        for (const item of items) {
                            const coverUrl = data.covers[String(item.page)];
                            if (coverUrl) {
                                this.updateVideoCover(item.index || item.page, coverUrl);
                            }
                        }
                    }
                }
            } catch (error) {
                console.error(`批量加载封面失败 (${bvid}):`, error);
            }
        }
    }

    updateVideoCover(identifier, coverUrl) {
        // 优先通过 data-video-index 匹配，其次通过 data-video-page 匹配
        const videoElement = document.querySelector(`[data-video-index="${identifier}"]`) ||
                             document.querySelector(`[data-video-page="${identifier}"]`);
        if (videoElement) {
            const thumbnail = videoElement.querySelector('.video-thumbnail');
            if (thumbnail) {
                thumbnail.classList.remove('loading');
                const finalUrl = /^https?:\/\//i.test(String(coverUrl || ''))
                    ? coverUrl
                    : this.apiBase + coverUrl;
                thumbnail.innerHTML = `
                    <img src="${this.escapeHtml(finalUrl)}" alt="视频封面"
                         onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                    <div class="placeholder-icon" style="display: none;">🎬</div>
                `;
            }
        }
    }

    // 平滑退出加载动画并进入应用首页
    enterApp() {
        if (this.appEntered) return;
        this.appEntered = true;

        // 保证加载微动效至少展示 450ms（兼顾生动感与不闪烁），数据准备好立刻优雅淡出
        const elapsed = Date.now() - (this.loadStartTime || 0);
        const minDisplayMs = 450;
        const delay = Math.max(0, minDisplayMs - elapsed);

        setTimeout(() => {
            const loadingEl = document.getElementById('loading');
            const foldersScreen = document.getElementById('folders-screen');

            // 预先让首页就绪
            if (foldersScreen) {
                foldersScreen.classList.remove('hidden');
            }
            this.currentScreen = 'folders';

            // 加载遮罩执行平滑缩放淡出
            if (loadingEl) {
                loadingEl.classList.add('fade-out');
                setTimeout(() => {
                    loadingEl.classList.add('hidden');
                    loadingEl.style.display = 'none';
                }, 400);
            }
        }, delay);
    }

    formatDuration(seconds) {
        if (!seconds) return '';
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    async playVideo(video, folderPath = this.currentFolder) {
        try {
            this.clearVideoPlayer();
            this.currentFolder = folderPath;
            this.currentVideo = video;
            const videoIndex = video.index || video.page;
            const titleEl = document.getElementById('video-title');
            const badgeEl = document.getElementById('player-badge');
            if (titleEl) titleEl.textContent = video.title;
            if (badgeEl) badgeEl.textContent = `第 ${videoIndex} 集`;

            this.showScreen('player');
            this.showDownloadProgress();
            
            const response = await fetch(`${this.apiBase}/api/download/${encodeURIComponent(this.currentFolder)}/${videoIndex}?bvid=${encodeURIComponent(video.bvid || '')}&page=${video.page || 1}`, { method: 'POST' });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const task = await response.json();
            if (task.status === 'ready') {
                this.loadVideoPlayer(task.video_url, { stream: task.stream });
                await this.setupSubtitleForVideo(video);
            } else if (task.task_id) {
                await this.pollDownloadTask(task.task_id, video);
            }
            
        } catch (error) {
            this.hideDownloadProgress();
            this.showError('播放视频失败');
            console.error('Error playing video:', error);
        }
    }

    async setupSubtitleForVideo(video) {
        // 只有 B站 有字幕接口；外部来源（silidm）直接跳过，避免无谓的 404 请求
        if (video.source !== 'bilibili') {
            this.setupSubtitleButton(video);
            return;
        }
        try {
            const response = await fetch(`${this.apiBase}/api/subtitle/${encodeURIComponent(this.currentFolder)}/${video.index || video.page}?bvid=${encodeURIComponent(video.bvid || '')}&page=${video.page || 1}`);
            if (response.ok) {
                const result = await response.json();
                this.setupSubtitleButton({ ...video, has_subtitle: true, subtitle_url: result.subtitle_url });
            } else this.setupSubtitleButton(video);
        } catch (_) { this.setupSubtitleButton(video); }
    }

    async pollDownloadTask(taskId, video) {
        const hint = document.getElementById('loader-hint');
        while (true) {
            const response = await fetch(`${this.apiBase}/api/download/tasks/${taskId}`);
            if (!response.ok) throw new Error('download task unavailable');
            const task = await response.json();
            const fill = document.getElementById('progress-fill');
            const text = document.getElementById('progress-text');
            if (fill) fill.style.width = `${task.progress || 0}%`;
            if (text) text.textContent = `${task.progress || 0}%`;
            if (hint) hint.textContent = task.stage || '正在准备播放，请稍候';
            if (task.status === 'ready') {
                this.loadVideoPlayer(task.video_url || `/static/${this.currentFolder}/${video.bvid}_p${video.page}.mp4`, { stream: task.stream });
                await this.setupSubtitleForVideo(video);
                return;
            }
            if (task.status === 'failed') throw new Error(task.error || 'download failed');
            await new Promise(resolve => setTimeout(resolve, 800));
        }
    }

    playRelative(offset) {
        if (!this.currentVideo || !this.currentVideos?.length) return;
        const index = this.currentVideos.findIndex(video => video.bvid === this.currentVideo.bvid && video.page === this.currentVideo.page);
        const target = this.currentVideos[index + offset];
        if (target) this.playVideo(target, this.currentFolder);
        else this.showError(offset > 0 ? '已经是最后一集' : '已经是第一集');
    }

    clearVideoPlayer() {
        this.saveCurrentProgress(true);

        const videoPlayer = document.getElementById('video-player');
        const subtitleTrack = document.getElementById('subtitle-track');

        // 顺序很关键：先暂停媒体，再拆 HLS —— hls.destroy() 会 revoke blob 源，
        // 若此时媒体仍在加载会产生 ERR_FILE_NOT_FOUND 噪音；最后才销毁 Plyr 并清 src
        if (videoPlayer) {
            try { videoPlayer.pause(); } catch (_) {}
        }
        this.destroyHls();

        // 销毁现有的Plyr实例
        if (this.player) {
            try { this.player.destroy(); } catch (_) {}
            this.player = null;
        }

        if (this._mediaErrorHandler && videoPlayer) {
            try { videoPlayer.removeEventListener('error', this._mediaErrorHandler); } catch (_) {}
            this._mediaErrorHandler = null;
        }

        if (videoPlayer) {
            videoPlayer.removeAttribute('src');
            if (subtitleTrack) {
                subtitleTrack.src = '';
                subtitleTrack.style.display = 'none';
            }
            try { videoPlayer.load(); } catch (_) {}
        }

        // 重置字幕状态
        this.subtitleEnabled = false;
    }

    stopVideo() {
        this.destroyHls();
        if (this.player) {
            try { this.player.pause(); } catch(_) {}
            try { this.player.currentTime = 0; } catch(_) {}
        }
        const videoPlayer = document.getElementById('video-player');
        const subtitleTrack = document.getElementById('subtitle-track');
        if (videoPlayer) {
            try { videoPlayer.pause(); } catch(_) {}
            if (subtitleTrack) {
                subtitleTrack.src = '';
                subtitleTrack.style.display = 'none';
            }
            try { videoPlayer.removeAttribute('src'); } catch(_) {}
            try { videoPlayer.load(); } catch(_) {}
        }
    }

    loadVideoPlayer(videoUrl, options = {}) {
        const videoPlayer = document.getElementById('video-player');
        if (!videoPlayer) return;

        // 播放类型判定：后端显式标记优先，其次看地址后缀（.m3u8 即 HLS 流式）
        const useHls = Boolean(options.stream) || /\.m3u8(?:[?#]|$)/i.test(videoUrl);

        // 换源前必须先拆掉上一路 HLS，否则旧实例会继续向后端与 CDN 拉分片
        this.destroyHls();

        if (useHls) {
            this.attachHlsStream(videoUrl);
        } else {
            // 直接规范设置 video.src，避免动态修改 source 标签的兼容性缺陷
            videoPlayer.src = `${this.apiBase}${videoUrl}`;
            videoPlayer.preload = 'auto';
        }

        // 初始化Plyr播放器统一托管播放时序
        this.initPlyrPlayer();

        this.hideDownloadProgress();
    }

    attachHlsStream(videoUrl) {
        const videoPlayer = document.getElementById('video-player');
        if (!videoPlayer) return;

        const source = `${this.apiBase}${videoUrl}`;
        this.hlsRetryCount = 0;

        // Safari/iOS 原生支持 HLS，直接交给 video 元素，无需 hls.js
        if (!window.Hls || !window.Hls.isSupported()) {
            if (videoPlayer.canPlayType('application/vnd.apple.mpegurl')) {
                videoPlayer.src = source;
                videoPlayer.preload = 'auto';
                return;
            }
            this.showError('当前浏览器不支持流式播放');
            return;
        }

        const hls = new window.Hls({
            // 分片由浏览器直连 CDN，后端只代理播放列表，缓冲可以留宽一些
            maxBufferLength: 30,
            maxMaxBufferLength: 60,
            enableWorker: true
        });
        this.hls = hls;

        hls.on(window.Hls.Events.FRAG_LOADED, () => {
            this.hlsRetryCount = 0;
        });

        hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
            this.hlsRetryCount = 0;
        });

        hls.on(window.Hls.Events.ERROR, (_event, data) => {
            if (!data || !data.fatal) return;

            // 起播阶段抖动或解析站限流：短暂退避后重试（startLoad 会重新换取签名）
            if (data.type === window.Hls.ErrorTypes.NETWORK_ERROR && this.hlsRetryCount < 3) {
                this.hlsRetryCount += 1;
                const delay = 1000 * this.hlsRetryCount;
                console.warn(`HLS 网络错误，${delay}ms 后重试（第 ${this.hlsRetryCount} 次）`, data.details);
                setTimeout(() => { try { hls.startLoad(); } catch (_) {} }, delay);
                return;
            }

            if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) {
                console.warn('HLS 媒体错误，尝试恢复', data.details);
                try { hls.recoverMediaError(); return; } catch (_) {}
            }

            console.error('HLS 无法恢复的错误:', data);
            this.showError('视频流加载失败，请重试');
        });

        hls.loadSource(source);
        hls.attachMedia(videoPlayer);
    }

    destroyHls() {
        if (!this.hls) return;
        try { this.hls.destroy(); } catch (_) {}
        this.hls = null;
    }

    async saveCurrentProgress(force = false) {
        const media = this.player?.media || document.getElementById('video-player');
        if (!media || !this.currentVideo || !this.currentFolder) return;
        const position = Number(media.currentTime || 0);
        const duration = Number(media.duration || this.currentVideo.duration || 0);
        if (!position && !duration) return;
        try {
            await fetch(`${this.apiBase}/api/progress`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder_path: this.currentFolder, bvid: this.currentVideo.bvid, page: this.currentVideo.page, position, duration, completed: duration > 0 && position / duration >= 0.92 }) });
        } catch (_) {}
    }

    showDownloadProgress() {
        const container = document.getElementById('download-progress');
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        container.classList.remove('hidden');

        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }

        fill.style.width = '0%';
        text.textContent = '0%';
    }

    hideDownloadProgress() {
        if (this.progressInterval) { clearInterval(this.progressInterval); this.progressInterval = null; }
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        fill.style.width = '100%';
        text.textContent = '100%';
        setTimeout(() => {
            document.getElementById('download-progress').classList.add('hidden');
        }, 300);
    }


    showError(message) {
        const errorToast = document.getElementById('error-toast');
        const errorMessage = document.getElementById('error-message');
        
        errorMessage.textContent = message;
        errorToast.classList.remove('hidden');
        
        setTimeout(() => {
            errorToast.classList.add('hidden');
        }, 3000);
    }

    setupSubtitleButton(video) {
        const subtitleTrack = document.getElementById('subtitle-track');

        // 先重置字幕状态
        this.subtitleEnabled = false;
        subtitleTrack.src = '';
        subtitleTrack.style.display = 'none';

        if (video.has_subtitle && video.subtitle_url) {
            // 有字幕可用。加载字幕
            this.loadSubtitle(video.subtitle_url);
        } else {
            console.log('无字幕可用');
        }
    }

    loadSubtitle(subtitleUrl) {
        try {
            const subtitleTrack = document.getElementById('subtitle-track');
            const videoPlayer = document.getElementById('video-player');

            // 设置字幕源
            subtitleTrack.src = `${this.apiBase}${subtitleUrl}`;
            subtitleTrack.style.display = 'block';

            // 根据用户设置决定是否默认显示字幕
            this.subtitleEnabled = this.settings.subtitles;
            console.log('字幕已加载，将在Plyr初始化时自动启用');

            // 等待视频和字幕都加载完成后应用字幕状态
            const enableSubtitle = () => {
                if (videoPlayer.textTracks.length > 0) {
                    videoPlayer.textTracks[0].mode = this.settings.subtitles ? 'showing' : 'disabled';
                }
            };

            // 如果视频已经加载，立即应用字幕状态
            if (videoPlayer.readyState >= 1) {
                enableSubtitle();
            } else {
                // 否则等待视频加载
                videoPlayer.addEventListener('loadedmetadata', enableSubtitle, { once: true });
            }
        } catch (error) {
            console.error('加载字幕失败:', error);
        }
    }

    initPlyrPlayer() {
        const videoPlayer = document.getElementById('video-player');
        
        // Plyr配置选项
        const plyrOptions = {
            // 锁定标准 16:9 比例，防止尺寸怪异
            ratio: '16:9',
            // 控制按钮配置：只显示播放、进度条、当前时间、总时长、字幕和全屏
            controls: [
                'play', // 播放/暂停
                'progress', // 进度条
                'current-time', // 当前时间
                'duration', // 总时长
                'captions', // 字幕
                'fullscreen' // 全屏
            ],
            // 不显示设置菜单
            settings: [],
            // 字幕配置
            captions: {
                active: this.settings.subtitles, // 默认开启字幕（如果有的话）
                language: 'auto',
                update: true
            },
            // 其他配置
            autoplay: this.settings.autoplay, // 优先尝试自动播放
            clickToPlay: true,
            hideControls: true,
            resetOnEnd: false,
            keyboard: { focused: true, global: false },
            tooltips: { controls: false, seek: true },
            displayDuration: true,
            invertTime: false,
            toggleInvert: true
        };

        // 创建Plyr实例
        this.player = new Plyr(videoPlayer, plyrOptions);

        // 监听Plyr事件
        this.player.on('ready', () => {
            console.log('Plyr播放器已就绪');
            // 如果有字幕且默认开启，则启用字幕
            // 注意：player.captions 存在并不代表 captions.tracks 存在（Plyr 在部分时序下
            // 会返回 undefined），直接取 .length 会抛 TypeError，必须先判空
            const captionTracks = this.player.captions && this.player.captions.tracks;
            if (this.settings.subtitles && this.subtitleEnabled && captionTracks && captionTracks.length > 0) {
                this.player.captions.active = true;
            }
            if (this.settings.autoplay) {
                this.player.play().catch(e => {
                    console.log('自动播放被阻止，需要用户手动播放');
                });
            }
        });

        this.player.on('play', () => {
            console.log('开始播放');
        });

        this.player.on('pause', () => {
            console.log('暂停播放');
            this.saveCurrentProgress(true);
        });

        this.player.on('timeupdate', () => {
            if (!this._progressSaveAt || Date.now() - this._progressSaveAt > 5000) {
                this._progressSaveAt = Date.now();
                this.saveCurrentProgress();
            }
        });

        this.player.on('loadedmetadata', () => {
            const saved = this.currentVideo?.progress;
            if (saved && saved.position > 5 && saved.position < (this.player.duration || Infinity) - 3) this.player.currentTime = saved.position;
        });

        this.player.on('ended', () => {
            this.saveCurrentProgress(true);
            if (this.settings.autoplay) this.playRelative(1);
        });

        // 播放错误处理
        this.player.on('error', (event) => {
            console.error('播放器错误:', event);
            this.showError('视频播放失败，请检查网络连接或重试');
        });

        // 视频加载错误处理（避免重复绑定并在清空/销毁时不误报）
        if (this._mediaErrorHandler && this.player.media) {
            try { this.player.media.removeEventListener('error', this._mediaErrorHandler); } catch (_) {}
        }
        this._mediaErrorHandler = (e) => {
            const videoPlayer = document.getElementById('video-player');
            // 正在清空或无有效播放源时忽略
            if (!videoPlayer || (!videoPlayer.src && !videoPlayer.currentSrc)) return;
            console.error('视频加载错误:', e);
            this.showError('视频文件加载失败');
        };
        this.player.media.addEventListener('error', this._mediaErrorHandler);

        // 检测视频是否可以播放
        this.player.on('canplay', () => {
            console.log('视频可以播放');
            // 仅在用户开启自动播放时重试，避免覆盖手动暂停
            if (this.settings.autoplay && this.player && this.player.paused) {
                this.player.play().catch(() => {});
            }
        });

        // 字幕事件监听
        this.player.on('captionsenabled', () => {
            this.subtitleEnabled = true;
            console.log('字幕已启用');
        });

        this.player.on('captionsdisabled', () => {
            this.subtitleEnabled = false;
            console.log('字幕已禁用');
        });
    }

    toggleSubtitle() {
        // 使用Plyr API控制字幕
        if (this.player && this.player.captions) {
            this.player.captions.toggle();
        }
    }

}
