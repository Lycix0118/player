// 应用状态管理
class VideoPlayerApp {
    constructor() {
        this.currentScreen = 'loading';
        this.currentFolder = null;
        this.currentVideo = null;
        this.apiBase = window.location.origin;
        this.subtitleEnabled = false;
        this.currentPath = [];  // 当前路径栈 ['folder1', 'subfolder1']
        this.folderHistory = []; // 导航历史
        this.player = null; // Plyr播放器实例
        // 启动与就绪状态
        this.foldersLoaded = false;
        this.loadStartTime = Date.now();
        this.appEntered = false;
        this.settings = this.loadSettings();
        
        this.init();
    }

    async init() {
        // 绑定事件监听器
        this.bindEvents();
        
        // 注册 Service Worker
        this.registerServiceWorker();
        
        // 加载文件夹数据
        this.loadFolders();
    }

    escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (character) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[character]));
    }

    bindEvents() {
        // 返回按钮
        document.getElementById('back-to-folders').addEventListener('click', () => {
            this.showScreen('folders');
        });
        
        document.getElementById('back-to-videos').addEventListener('click', () => {
            this.showScreen('videos');
        });

        // 返回上级文件夹按钮
        document.getElementById('back-to-parent').addEventListener('click', () => {
            this.navigateToParent();
        });

        document.getElementById('open-settings').addEventListener('click', () => this.openSettings());
        document.getElementById('install-app').addEventListener('click', () => this.installApp());
        document.getElementById('back-from-settings').addEventListener('click', () => this.showScreen('folders'));
        document.getElementById('save-cookie').addEventListener('click', () => this.saveCookie());
        document.getElementById('toggle-cookie-visibility').addEventListener('click', () => this.toggleCookieVisibility());
        document.getElementById('clear-cache').addEventListener('click', () => this.clearCache());
        document.getElementById('setting-autoplay').addEventListener('change', (event) => this.updateSetting('autoplay', event.target.checked));
        document.getElementById('setting-subtitles').addEventListener('change', (event) => this.updateSetting('subtitles', event.target.checked));
        document.getElementById('theme-select').addEventListener('change', (event) => this.updateSetting('theme', event.target.value));
        this.applySettings();
        this.updateInstallButton();
    }

    async installApp() {
        if (this.isAppInstalled()) {
            this.showError('应用已经添加到桌面');
            return;
        }

        if (!deferredPrompt) {
            this.showError('当前浏览器暂不支持自动添加，请打开浏览器菜单选择“安装应用”或“添加到主屏幕”');
            return;
        }

        const installPrompt = deferredPrompt;
        deferredPrompt = null;
        installPrompt.prompt();

        try {
            await installPrompt.userChoice;
        } catch (error) {
            console.log('PWA 安装结果读取失败:', error);
        }
        this.updateInstallButton();
    }

    isAppInstalled() {
        return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    }

    updateInstallButton() {
        const button = document.getElementById('install-app');
        if (!button) return;

        if (this.isAppInstalled()) {
            button.textContent = '✓ 已添加';
            button.disabled = true;
            button.title = '应用已添加到桌面';
            button.setAttribute('aria-label', '应用已添加到桌面');
        }
    }

    loadSettings() {
        try {
            return { autoplay: false, subtitles: true, theme: 'candy', ...JSON.parse(localStorage.getItem('player-settings') || '{}') };
        } catch (error) { return { autoplay: false, subtitles: true, theme: 'candy' }; }
    }

    updateSetting(key, value) {
        this.settings[key] = value;
        localStorage.setItem('player-settings', JSON.stringify(this.settings));
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
        if (this.currentScreen === 'player' && screenName !== 'player') {
            this.clearVideoPlayer();
        }
        
        // 隐藏应用主要内容屏幕
        ['folders', 'videos', 'player', 'settings'].forEach(name => {
            const screen = document.getElementById(`${name}-screen`);
            if (screen) {
                screen.classList.add('hidden');
            }
        });
        
        // 显示目标屏幕
        const targetScreen = document.getElementById(`${screenName}-screen`);
        if (targetScreen) {
            targetScreen.classList.remove('hidden');
            this.currentScreen = screenName;
        }
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

    renderFolders(folders) {
        const container = document.getElementById('folders-list');
        container.innerHTML = '';

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

        if (videos.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>📺 暂无视频</h3>
                    <p>请在 list.txt 中添加B站视频链接</p>
                </div>
            `;
            return;
        }

        videos.forEach((video, index) => {
            const videoElement = document.createElement('div');
            videoElement.className = 'video-item';
            const videoIndex = video.index || (index + 1);
            videoElement.dataset.videoIndex = videoIndex;
            videoElement.dataset.videoPage = video.page;
            videoElement.dataset.videoBvid = video.bvid || '';
            videoElement.setAttribute('tabindex', '0'); // 键盘可访问性

            // 如果已有本地缓存好的封面，直接展示，无需loading
            const hasCover = !!video.cover_url;
            const thumbnailHTML = hasCover
                ? `<img src="${this.escapeHtml(this.apiBase + video.cover_url)}" alt="视频封面" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="placeholder-icon" style="display: none;">🎬</div>`
                : '<div class="placeholder-icon">🎬</div>';

            videoElement.innerHTML = `
                <div class="video-thumbnail ${hasCover ? '' : 'loading'}">
                    ${thumbnailHTML}
                </div>
                <div class="video-info">
                    <div class="video-title">${this.escapeHtml(video.title)}</div>
                    <div class="video-page">第 ${this.escapeHtml(videoIndex)} 集</div>
                    ${video.duration ? `<div class="video-duration">${this.escapeHtml(this.formatDuration(video.duration))}</div>` : ''}
                </div>
            `;

            // 点击和键盘事件
            const handleActivation = () => {
                this.playVideo(video);
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
                thumbnail.innerHTML = `
                    <img src="${this.escapeHtml(this.apiBase + coverUrl)}" alt="视频封面"
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

    async playVideo(video) {
        try {
            this.currentVideo = video;
            const videoIndex = video.index || video.page;
            const titleEl = document.getElementById('video-title');
            const badgeEl = document.getElementById('player-badge');
            if (titleEl) titleEl.textContent = video.title;
            if (badgeEl) badgeEl.textContent = `第 ${videoIndex} 集`;

            // 先清空播放器
            this.clearVideoPlayer();

            this.showScreen('player');
            this.showDownloadProgress();
            
            // 请求播放视频，带上 bvid 与 page 参数以支持多 BV 列表
            const playUrl = `${this.apiBase}/api/play/${encodeURIComponent(this.currentFolder)}/${videoIndex}?bvid=${encodeURIComponent(video.bvid || '')}&page=${video.page || 1}`;
            const response = await fetch(playUrl);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const result = await response.json();
            
            if (result.status === 'ready') {
                this.loadVideoPlayer(result.video_url);
                // 设置字幕按钮状态，使用API返回的字幕信息
                this.setupSubtitleButton({
                    ...video,
                    has_subtitle: result.has_subtitle,
                    subtitle_url: result.subtitle_url
                });
            } else {
                this.showError('视频正在准备中，请稍后重试');
            }
            
        } catch (error) {
            this.hideDownloadProgress();
            this.showError('播放视频失败');
            console.error('Error playing video:', error);
        }
    }

    clearVideoPlayer() {
        // 销毁现有的Plyr实例
        if (this.player) {
            try { this.player.destroy(); } catch (_) {}
            this.player = null;
        }

        const videoPlayer = document.getElementById('video-player');
        const subtitleTrack = document.getElementById('subtitle-track');

        // 暂停并清空当前视频
        if (videoPlayer) {
            try { videoPlayer.pause(); } catch (_) {}
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

    loadVideoPlayer(videoUrl) {
        const videoPlayer = document.getElementById('video-player');
        if (!videoPlayer) return;

        // 直接规范设置 video.src，避免动态修改 source 标签的兼容性缺陷
        videoPlayer.src = `${this.apiBase}${videoUrl}`;
        videoPlayer.preload = 'auto';

        // 初始化Plyr播放器统一托管播放时序
        this.initPlyrPlayer();

        this.hideDownloadProgress();
    }

    showDownloadProgress() {
        const container = document.getElementById('download-progress');
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        container.classList.remove('hidden');

        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }

        let progress = 10;
        fill.style.width = `${progress}%`;
        text.textContent = '准备中...';

        // 渐进式平滑进度提示（最高停在 92%，等待后端完成返回）
        this.progressInterval = setInterval(() => {
            if (progress < 90) {
                progress += Math.max(1, (90 - progress) * 0.1);
                fill.style.width = `${Math.round(progress)}%`;
                text.textContent = `${Math.round(progress)}%`;
            }
        }, 300);
    }

    hideDownloadProgress() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
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
            if (this.settings.subtitles && this.subtitleEnabled && this.player.captions && this.player.captions.tracks.length > 0) {
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
        });

        // 播放错误处理
        this.player.on('error', (event) => {
            console.error('播放器错误:', event);
            this.showError('视频播放失败，请检查网络连接或重试');
        });

        // 视频加载错误处理
        this.player.media.addEventListener('error', (e) => {
            console.error('视频加载错误:', e);
            this.showError('视频文件加载失败');
        });

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

    async registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                await navigator.serviceWorker.register('./sw.js');
                console.log('Service Worker 注册成功');
            } catch (error) {
                console.log('Service Worker 注册失败:', error);
            }
        }
    }
}

// 启动应用
document.addEventListener('DOMContentLoaded', () => {
    window.videoPlayerApp = new VideoPlayerApp();
});

// PWA 安装提示
let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;

    window.videoPlayerApp?.updateInstallButton();
    console.log('PWA 可以安装');
});

window.addEventListener('appinstalled', () => {
    console.log('PWA 已安装');
    deferredPrompt = null;
    window.videoPlayerApp?.updateInstallButton();
});
