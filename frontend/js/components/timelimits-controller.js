/**
 * Time Limits Controller (观看限时管理控制器)
 * 负责：
 * 1. 家长验证门禁（算术题 / 4位PIN口令）
 * 2. 物理播放时间精确心跳累计与服务端同步
 * 3. 临界预警（3分钟/1分钟温馨气泡提示）
 * 4. 到期小电视休息锁屏拦截与合集卡片防点拦截
 * 5. 家长区设置面板交互与临时加时授权
 */

export class TimeLimitsController {
    constructor(app) {
        this.app = app;
        this.apiBase = app.apiBase || window.location.origin;

        // 状态数据
        this.status = null;
        this.parentUnlockedUntil = 0; // 内存凭证，验证通过后短期免密（10分钟）
        this.mathAnswer = null;

        // 播放计时心跳相关
        this.activeFolder = null;
        this.tickInterval = null;
        this.unreportedSeconds = 0;
        this.currentRemainingSeconds = null;
        this.isLocked = false;
        this.notified3Min = false;
        this.notified1Min = false;

        this.initDOMElements();
        this.bindEvents();
    }

    initDOMElements() {
        // 家长门禁
        this.parentGateModal = document.getElementById('parent-gate-modal');
        this.parentGateClose = document.getElementById('parent-gate-close');
        this.parentGateCancel = document.getElementById('parent-gate-cancel');
        this.parentGateSubmit = document.getElementById('parent-gate-submit');
        this.parentGatePrompt = document.getElementById('parent-gate-prompt');
        this.parentGateMathBox = document.getElementById('parent-gate-math-box');
        this.parentGateQuestion = document.getElementById('parent-gate-question');
        this.parentGateMathAnswer = document.getElementById('parent-gate-math-answer');
        this.parentGatePinBox = document.getElementById('parent-gate-pin-box');
        this.parentGatePinInput = document.getElementById('parent-gate-pin-input');
        this.parentGateError = document.getElementById('parent-gate-error');

        // 家长区设置元素
        this.enabledSwitch = document.getElementById('setting-timelimit-enabled');
        this.optionsContainer = document.getElementById('timelimit-options-container');
        this.globalSelect = document.getElementById('setting-timelimit-global');
        this.globalCustom = document.getElementById('setting-timelimit-global-custom');
        this.globalStat = document.getElementById('timelimit-global-stat');
        this.folderLimitsList = document.getElementById('folder-limits-list');
        this.pinStatusBadge = document.getElementById('pin-status-badge');
        this.pinInput = document.getElementById('parent-pin-input');
        this.savePinBtn = document.getElementById('save-parent-pin-btn');
        this.clearPinBtn = document.getElementById('clear-parent-pin-btn');
        this.saveLimitsBtn = document.getElementById('save-timelimits-btn');
        this.resetTodayBtn = document.getElementById('reset-today-limits');

        // 播放中提示与锁屏
        this.playerTimeNotice = document.getElementById('player-time-notice');
        this.playerTimeNoticeText = document.getElementById('player-time-notice-text');
        this.playerTimeupOverlay = document.getElementById('player-timeup-overlay');
        this.timeupBackBtn = document.getElementById('timeup-back-btn');

        // 顶部右上角今日已看时长徽章
        this.headerTodayTime = document.getElementById('header-today-time');
        this.videosTodayTime = document.getElementById('videos-today-time');
        this.playerTodayTime = document.getElementById('player-today-time');

        // 家长加时弹窗
        this.extendModal = document.getElementById('extend-modal');
        this.extendModalClose = document.getElementById('extend-modal-close');

        // 目录受限拦截弹窗
        this.folderBlockedModal = document.getElementById('folder-blocked-modal');
        this.folderBlockedClose = document.getElementById('folder-blocked-close');
        this.folderBlockedConfirm = document.getElementById('folder-blocked-confirm');
    }

    bindEvents() {
        // 家长门禁弹窗关闭
        this.parentGateClose?.addEventListener('click', () => this.hideParentGate());
        this.parentGateCancel?.addEventListener('click', () => this.hideParentGate());
        this.parentGateSubmit?.addEventListener('click', () => this.verifyParentGate());
        this.parentGateMathAnswer?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.verifyParentGate();
        });
        this.parentGatePinInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.verifyParentGate();
        });

        // 加时弹窗关闭
        this.extendModalClose?.addEventListener('click', () => this.hideExtendModal());
        this.extendModal?.querySelectorAll('.extend-option-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const type = btn.dataset.type;
                const minutes = parseInt(btn.dataset.min, 10);
                this.submitExtension(type, minutes);
            });
        });

        // 合集拦截弹窗
        this.folderBlockedClose?.addEventListener('click', () => this.hideFolderBlockedModal());
        this.folderBlockedConfirm?.addEventListener('click', () => this.hideFolderBlockedModal());

        // 播放页锁屏按钮（休息完毕返回合集）
        this.timeupBackBtn?.addEventListener('click', () => {
            this.hideTimeupOverlay();
            this.app.showScreen('folders');
        });

        // 家长设置面板事件
        this.enabledSwitch?.addEventListener('change', (e) => {
            this.toggleOptionsVisibility(e.target.checked);
        });

        this.globalSelect?.addEventListener('change', (e) => {
            if (e.target.value === 'custom') {
                this.globalCustom?.classList.remove('hidden');
                this.globalCustom?.focus();
            } else {
                this.globalCustom?.classList.add('hidden');
            }
        });

        this.saveLimitsBtn?.addEventListener('click', () => this.saveSettingsFromForm());
        this.resetTodayBtn?.addEventListener('click', () => this.resetTodayUsagePrompt());

        this.savePinBtn?.addEventListener('click', () => this.savePinFromInput());
        this.clearPinBtn?.addEventListener('click', () => this.clearPin());

        // 监听浏览器切后台与恢复，精准暂停/补传计时
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
                this.flushHeartbeat();
            }
        });
        window.addEventListener('beforeunload', () => {
            this.flushHeartbeat();
        });
    }

    // --- 家长门禁逻辑 ---

    requestParentAccess(onSuccess) {
        // 若在10分钟凭证有效期内，直接放行
        if (Date.now() < this.parentUnlockedUntil) {
            onSuccess();
            return;
        }

        this.onGateSuccess = onSuccess;
        this.showParentGate();
    }

    showParentGate() {
        if (!this.parentGateModal) return;
        this.parentGateError?.classList.add('hidden');

        const hasPin = Boolean(this.status?.has_parent_pin);
        if (hasPin) {
            this.parentGatePrompt.textContent = '请输入4位家长密码以继续：';
            this.parentGateMathBox.classList.add('hidden');
            this.parentGatePinBox.classList.remove('hidden');
            if (this.parentGatePinInput) {
                this.parentGatePinInput.value = '';
                setTimeout(() => this.parentGatePinInput.focus(), 150);
            }
        } else {
            // 生成趣味算术题目（单数乘法或两位数加法）
            const isMultiply = Math.random() > 0.3;
            let question = '';
            let ans = 0;
            if (isMultiply) {
                const a = Math.floor(Math.random() * 6) + 4; // 4-9
                const b = Math.floor(Math.random() * 6) + 4; // 4-9
                ans = a * b;
                question = `${a} × ${b} = ?`;
            } else {
                const a = Math.floor(Math.random() * 40) + 15;
                const b = Math.floor(Math.random() * 40) + 15;
                ans = a + b;
                question = `${a} + ${b} = ?`;
            }
            this.mathAnswer = ans;
            this.parentGateQuestion.textContent = question;
            this.parentGatePrompt.textContent = '请回答算术题验证家长身份：';
            this.parentGateMathBox.classList.remove('hidden');
            this.parentGatePinBox.classList.add('hidden');
            if (this.parentGateMathAnswer) {
                this.parentGateMathAnswer.value = '';
                setTimeout(() => this.parentGateMathAnswer.focus(), 150);
            }
        }

        this.parentGateModal.classList.remove('hidden');
    }

    hideParentGate() {
        this.parentGateModal?.classList.add('hidden');
        this.onGateSuccess = null;
    }

    async verifyParentGate() {
        const hasPin = Boolean(this.status?.has_parent_pin);
        let pass = false;

        if (hasPin) {
            const pin = this.parentGatePinInput?.value.trim() || '';
            try {
                const res = await fetch(`${this.apiBase}/api/time-limits/verify-pin`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pin })
                });
                const data = await res.json();
                pass = Boolean(data.valid);
            } catch (_) {
                pass = false;
            }
        } else {
            const userAns = parseInt(this.parentGateMathAnswer?.value, 10);
            pass = userAns === this.mathAnswer;
        }

        if (pass) {
            this.parentUnlockedUntil = Date.now() + 10 * 60 * 1000; // 10分钟免验证
            const cb = this.onGateSuccess;
            this.hideParentGate();
            if (typeof cb === 'function') cb();
        } else {
            this.parentGateError?.classList.remove('hidden');
            if (hasPin) {
                this.parentGatePinInput?.select();
            } else {
                this.parentGateMathAnswer?.select();
            }
        }
    }

    // --- 数据加载与状态同步 ---

    async fetchStatus() {
        try {
            const res = await fetch(`${this.apiBase}/api/time-limits/status`);
            if (res.ok) {
                this.status = await res.json();
                this.updateTodayWatchTimeDisplay();
                return this.status;
            }
        } catch (error) {
            console.warn('获取限时状态失败:', error);
        }
        return null;
    }

    updateTodayWatchTimeDisplay() {
        const baseSeconds = this.status?.total_used_seconds || 0;
        const currentTotalSeconds = baseSeconds + (this.unreportedSeconds || 0);
        const totalMin = Math.floor(currentTotalSeconds / 60);

        let labelText = `⏱️ 今日已看 ${totalMin} 分钟`;
        let isWarn = false;
        let isLocked = false;

        if (this.status?.enabled && this.status.global_limit_minutes > 0) {
            const effLimit = this.status.effective_global_limit_minutes || this.status.global_limit_minutes;
            labelText = `⏱️ 今日已看 ${totalMin} / ${effLimit} 分钟`;
            if (totalMin >= effLimit || this.status.global_is_locked) {
                isLocked = true;
            } else if (effLimit - totalMin <= 5) {
                isWarn = true;
            }
        }

        const pillClass = isLocked ? 'header-time-pill time-locked' : (isWarn ? 'header-time-pill time-warn' : 'header-time-pill');

        if (this.headerTodayTime) {
            this.headerTodayTime.textContent = labelText;
            this.headerTodayTime.className = pillClass;
        }
        if (this.videosTodayTime) {
            this.videosTodayTime.textContent = labelText;
            this.videosTodayTime.className = pillClass;
        }
        if (this.playerTodayTime) {
            this.playerTodayTime.textContent = labelText;
        }
    }

    renderSettingsPanel(status = this.status) {
        if (!status) return;
        this.updateTodayWatchTimeDisplay();

        // 开关
        if (this.enabledSwitch) {
            this.enabledSwitch.checked = Boolean(status.enabled);
            this.toggleOptionsVisibility(status.enabled);
        }

        // 全局限时
        const globalMin = status.global_limit_minutes || 0;
        const globalOptions = ['0', '15', '30', '45', '60', '90', '120'];
        if (this.globalSelect) {
            if (globalOptions.includes(String(globalMin))) {
                this.globalSelect.value = String(globalMin);
                this.globalCustom?.classList.add('hidden');
            } else {
                this.globalSelect.value = 'custom';
                if (this.globalCustom) {
                    this.globalCustom.value = globalMin;
                    this.globalCustom.classList.remove('hidden');
                }
            }
        }

        // 全局统计
        if (this.globalStat) {
            const usedMin = Math.floor((status.total_used_seconds || 0) / 60);
            if (status.global_limit_minutes > 0) {
                const effMin = status.effective_global_limit_minutes || status.global_limit_minutes;
                const remMin = Math.max(0, Math.floor((status.global_remaining_seconds || 0) / 60));
                this.globalStat.textContent = `今日已看: ${usedMin} / ${effMin} 分钟 (剩 ${remMin} 分钟)`;
                this.globalStat.className = status.global_is_locked
                    ? 'timelimit-badge badge-locked'
                    : 'timelimit-badge badge-active';
            } else {
                this.globalStat.textContent = `今日已看: ${usedMin} 分钟 (不限时)`;
                this.globalStat.className = 'timelimit-badge';
            }
        }

        // 密码状态
        if (this.pinStatusBadge) {
            this.pinStatusBadge.textContent = status.has_parent_pin ? '已设置4位PIN' : '趣味算术题验证';
            this.pinStatusBadge.className = status.has_parent_pin ? 'timelimit-badge badge-active' : 'timelimit-badge';
        }
        if (this.clearPinBtn) {
            this.clearPinBtn.classList.toggle('hidden', !status.has_parent_pin);
        }

        // 合集列表渲染
        this.renderFolderLimitsList(status.folders || []);
    }

    toggleOptionsVisibility(enabled) {
        if (this.optionsContainer) {
            this.optionsContainer.style.opacity = enabled ? '1' : '0.5';
            this.optionsContainer.style.pointerEvents = enabled ? 'auto' : 'none';
        }
    }

    renderFolderLimitsList(folders) {
        if (!this.folderLimitsList) return;
        if (!folders || folders.length === 0) {
            this.folderLimitsList.innerHTML = '<p class="settings-status">暂无底层视频合集</p>';
            return;
        }

        this.folderLimitsList.innerHTML = folders.map(f => {
            const usedMin = Math.floor(f.used_seconds / 60);
            const effMin = f.effective_limit_minutes || f.limit_minutes;
            const pct = effMin > 0 ? Math.min(100, Math.round((f.used_seconds / (effMin * 60)) * 100)) : 0;
            const isLocked = Boolean(f.is_locked);
            const fillClass = isLocked ? 'fill-locked' : (pct >= 80 ? 'fill-warn' : '');

            const limitVal = f.limit_minutes || 0;
            const isStandard = ['0', '15', '20', '30', '45', '60'].includes(String(limitVal));

            return `
                <div class="folder-limit-row" data-path="${this.escapeHtml(f.path)}">
                    <div class="folder-limit-info">
                        <span class="folder-limit-name" title="${this.escapeHtml(f.name)}">
                            <span>📁</span> ${this.escapeHtml(f.name)}
                        </span>
                        <span class="folder-limit-used">
                            今日已看: <strong>${usedMin}</strong> 分钟 ${effMin > 0 ? `/ ${effMin} 分钟` : ''}
                        </span>
                    </div>
                    ${effMin > 0 ? `
                        <div class="folder-limit-progress-bar">
                            <div class="folder-limit-progress-fill ${fillClass}" style="width: ${pct}%"></div>
                        </div>
                    ` : ''}
                    <div class="folder-limit-inputs">
                        <select class="folder-limit-select" data-path="${this.escapeHtml(f.path)}">
                            <option value="0" ${limitVal === 0 ? 'selected' : ''}>不限制 (默认)</option>
                            <option value="15" ${limitVal === 15 ? 'selected' : ''}>15 分钟</option>
                            <option value="20" ${limitVal === 20 ? 'selected' : ''}>20 分钟</option>
                            <option value="30" ${limitVal === 30 ? 'selected' : ''}>30 分钟</option>
                            <option value="45" ${limitVal === 45 ? 'selected' : ''}>45 分钟</option>
                            <option value="60" ${limitVal === 60 ? 'selected' : ''}>60 分钟</option>
                            <option value="custom" ${!isStandard && limitVal > 0 ? 'selected' : ''}>自定义分钟...</option>
                        </select>
                        <input type="number" min="1" max="300" class="folder-limit-custom-input ${(!isStandard && limitVal > 0) ? '' : 'hidden'}"
                               value="${(!isStandard && limitVal > 0) ? limitVal : ''}" placeholder="分钟数">
                    </div>
                </div>
            `;
        }).join('');

        // 绑定各目录下拉变化
        this.folderLimitsList.querySelectorAll('.folder-limit-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const row = e.target.closest('.folder-limit-row');
                const customInput = row.querySelector('.folder-limit-custom-input');
                if (e.target.value === 'custom') {
                    customInput?.classList.remove('hidden');
                    customInput?.focus();
                } else {
                    customInput?.classList.add('hidden');
                }
            });
        });
    }

    async saveSettingsFromForm() {
        const enabled = Boolean(this.enabledSwitch?.checked);

        // 全局限时
        let globalLimit = 0;
        if (this.globalSelect?.value === 'custom') {
            globalLimit = parseInt(this.globalCustom?.value, 10) || 0;
        } else {
            globalLimit = parseInt(this.globalSelect?.value, 10) || 0;
        }

        // 各目录限时
        const folderLimits = {};
        if (this.folderLimitsList) {
            this.folderLimitsList.querySelectorAll('.folder-limit-row').forEach(row => {
                const path = row.dataset.path;
                const sel = row.querySelector('.folder-limit-select');
                const customInput = row.querySelector('.folder-limit-custom-input');
                let minutes = 0;
                if (sel?.value === 'custom') {
                    minutes = parseInt(customInput?.value, 10) || 0;
                } else {
                    minutes = parseInt(sel?.value, 10) || 0;
                }
                folderLimits[path] = minutes;
            });
        }

        try {
            const res = await fetch(`${this.apiBase}/api/time-limits/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled,
                    global_limit_minutes: globalLimit,
                    folder_limits: folderLimits
                })
            });
            if (res.ok) {
                this.status = await res.json();
                this.renderSettingsPanel(this.status);
                this.app.notify?.show('限时设置已保存', 'success');
            } else {
                this.app.notify?.show('保存限时设置失败', 'error');
            }
        } catch (error) {
            console.error('保存设置异常:', error);
            this.app.notify?.show('保存失败，请检查网络', 'error');
        }
    }

    async savePinFromInput() {
        const pin = this.pinInput?.value.trim() || '';
        if (pin && (!/^\d{4}$/.test(pin))) {
            this.app.notify?.show('PIN密码必须为4位数字', 'warning');
            return;
        }
        try {
            const res = await fetch(`${this.apiBase}/api/time-limits/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ parent_pin: pin })
            });
            if (res.ok) {
                this.status = await res.json();
                this.renderSettingsPanel(this.status);
                if (this.pinInput) this.pinInput.value = '';
                this.app.notify?.show(pin ? '4位密码设置成功' : '已恢复趣味算术题验证', 'success');
            }
        } catch (err) {
            this.app.notify?.show('设置密码失败', 'error');
        }
    }

    async clearPin() {
        try {
            const res = await fetch(`${this.apiBase}/api/time-limits/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ parent_pin: '' })
            });
            if (res.ok) {
                this.status = await res.json();
                this.renderSettingsPanel(this.status);
                this.app.notify?.show('已清除密码，恢复趣味算术验证', 'success');
            }
        } catch (err) {
            this.app.notify?.show('清除密码失败', 'error');
        }
    }

    async resetTodayUsagePrompt() {
        if (!confirm('确定要清零今日所有合集的观看时长记录吗？\n（今日已看时间将归零重新计算）')) {
            return;
        }
        try {
            const res = await fetch(`${this.apiBase}/api/time-limits/reset-today`, {
                method: 'POST'
            });
            if (res.ok) {
                this.status = await res.json();
                this.renderSettingsPanel(this.status);
                this.app.notify?.show('今日计时已重置', 'success');
            }
        } catch (err) {
            this.app.notify?.show('重置失败', 'error');
        }
    }

    // --- 目录受限判定与拦截 ---

    isFolderLocked(folderPath) {
        if (!this.status || !this.status.enabled) return false;
        if (this.status.global_is_locked) return true;
        const cleanPath = String(folderPath || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
        const folder = (this.status.folders || []).find(f => f.path === cleanPath);
        return Boolean(folder && folder.is_locked);
    }

    getFolderRemainingSeconds(folderPath) {
        if (!this.status || !this.status.enabled) return null;
        const cleanPath = String(folderPath || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
        const folder = (this.status.folders || []).find(f => f.path === cleanPath);
        if (folder) return folder.remaining_seconds;
        return this.status.global_remaining_seconds;
    }

    showFolderBlockedModal(folderPath) {
        this._blockedFolderTarget = folderPath;
        const isGlobal = Boolean(this.status?.global_is_locked);
        const titleEl = document.getElementById('folder-blocked-title');
        const descEl = document.getElementById('folder-blocked-desc');

        if (titleEl) {
            titleEl.textContent = isGlobal ? '今日全局观看总时长已用完 🌙' : '这个合集今日时间已用完 🎈';
        }
        if (descEl) {
            descEl.textContent = isGlobal
                ? '今天看视频的时间很充实啦，眼睛需要好好休息一下！明天小电视再陪你玩~'
                : '今天这个合集看得够多啦，让眼睛休息一下，或者去看看其他内容吧！';
        }

        this.folderBlockedModal?.classList.remove('hidden');
    }

    hideFolderBlockedModal() {
        this.folderBlockedModal?.classList.add('hidden');
        this._blockedFolderTarget = null;
    }

    // --- 播放器高精度秒表与心跳上报 ---

    startTrackingForFolder(folderPath) {
        this.stopTracking();
        this.activeFolder = String(folderPath || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
        this.unreportedSeconds = 0;
        this.notified3Min = false;
        this.notified1Min = false;
        this.isLocked = false;
        this.hideTimeNotice();
        this.hideTimeupOverlay();

        // 获取该合集初始剩余秒数
        this.currentRemainingSeconds = this.getFolderRemainingSeconds(this.activeFolder);

        // 每秒检查一次是否在有效播放并计时
        this.tickInterval = setInterval(() => {
            this.handlePlaybackTick();
        }, 1000);
    }

    stopTracking() {
        if (this.tickInterval) {
            clearInterval(this.tickInterval);
            this.tickInterval = null;
        }
        this.flushHeartbeat();
        this.hideTimeNotice();
    }

    handlePlaybackTick() {
        const media = this.app.player?.media || document.getElementById('video-player');
        if (!media) return;

        // 仅在实际物理播放且页面前台可见时计时
        const isPlaying = !media.paused && !media.ended && !media.seeking && media.readyState >= 2;
        const isVisible = document.visibilityState === 'visible';

        if (isPlaying && isVisible) {
            this.unreportedSeconds += 1;
            this.updateTodayWatchTimeDisplay();

            if (this.currentRemainingSeconds !== null) {
                this.currentRemainingSeconds = Math.max(0, this.currentRemainingSeconds - 1);
                this.checkRemainingNotice(this.currentRemainingSeconds);

                if (this.currentRemainingSeconds <= 0 && !this.isLocked) {
                    this.triggerLockout('time_exhausted');
                }
            }
        }

        // 每5秒上报一次心跳到服务端
        if (this.unreportedSeconds >= 5) {
            this.flushHeartbeat();
        }
    }

    async flushHeartbeat() {
        if (this.unreportedSeconds <= 0 || !this.activeFolder) return;
        const delta = this.unreportedSeconds;
        this.unreportedSeconds = 0;

        try {
            const res = await fetch(`${this.apiBase}/api/time-limits/heartbeat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    folder_path: this.activeFolder,
                    delta_seconds: delta
                })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.remaining_seconds !== null && data.remaining_seconds !== undefined) {
                    this.currentRemainingSeconds = data.remaining_seconds;
                }
                if (this.status) {
                    this.status.total_used_seconds = (this.status.total_used_seconds || 0) + delta;
                }
                this.updateTodayWatchTimeDisplay();
                if (data.should_lock && !this.isLocked) {
                    this.triggerLockout(data.lock_reason);
                }
            }
        } catch (err) {
            console.warn('心跳上报失败:', err);
        }
    }

    checkRemainingNotice(remainingSec) {
        if (remainingSec === null || remainingSec <= 0) return;

        // 3分钟预警 (<= 180s)
        if (remainingSec <= 180 && remainingSec > 60 && !this.notified3Min) {
            this.notified3Min = true;
            this.showTimeNotice('⏱️ 还有 3 分钟要休息眼睛咯 🎈', false);
            setTimeout(() => this.hideTimeNotice(), 6000);
        }
        // 1分钟紧急预警 (<= 60s)
        else if (remainingSec <= 60 && !this.notified1Min) {
            this.notified1Min = true;
            this.showTimeNotice('⏰ 还有 1 分钟倒计时，准备休息啦', true);
        }
    }

    showTimeNotice(text, isUrgent = false) {
        if (!this.playerTimeNotice || !this.playerTimeNoticeText) return;
        this.playerTimeNoticeText.textContent = text;
        this.playerTimeNotice.className = isUrgent
            ? 'player-time-notice notice-urgent'
            : 'player-time-notice';
        this.playerTimeNotice.classList.remove('hidden');
    }

    hideTimeNotice() {
        this.playerTimeNotice?.classList.add('hidden');
    }

    triggerLockout(reason) {
        this.isLocked = true;
        this.hideTimeNotice();

        // 暂停视频播放
        const media = this.app.player?.media || document.getElementById('video-player');
        if (media) {
            try { media.pause(); } catch (_) {}
        }
        if (this.app.player) {
            try { this.app.player.pause(); } catch (_) {}
        }

        // 显示萌趣打呼噜电视遮罩
        this.showTimeupOverlay(reason);
    }

    showTimeupOverlay(reason) {
        if (!this.playerTimeupOverlay) return;
        const title = document.getElementById('timeup-title');
        const desc = document.getElementById('timeup-desc');

        if (reason === 'global' || this.status?.global_is_locked) {
            if (title) title.textContent = '今日观看总时间到啦 🌙';
            if (desc) desc.innerHTML = '今天所有视频的观看时间都用完啦。<br>让眼睛好好睡一觉，明天再来探索新世界吧！✨';
        } else {
            if (title) title.textContent = '今日休息时间到啦 🌙';
            if (desc) desc.innerHTML = '这个合集今天的观看时间已经用完啦。<br>小电视要睡觉啦，明天我们再一起看！✨';
        }

        this.playerTimeupOverlay.classList.remove('hidden');
    }

    hideTimeupOverlay() {
        this.playerTimeupOverlay?.classList.add('hidden');
    }

    // --- 家长加时操作 ---

    showExtendModal(folderPath = this.activeFolder) {
        this._extendTargetFolder = folderPath;
        const desc = document.getElementById('extend-modal-desc');
        if (desc && folderPath) {
            desc.textContent = `为合集「${folderPath}」或全局总限时追加今日时间：`;
        }
        this.extendModal?.classList.remove('hidden');
    }

    hideExtendModal() {
        this.extendModal?.classList.add('hidden');
        this._extendTargetFolder = null;
    }

    async submitExtension(type, minutes) {
        const folder = this._extendTargetFolder || this.activeFolder || '';
        try {
            const res = await fetch(`${this.apiBase}/api/time-limits/extend`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: type,
                    folder_path: folder,
                    minutes: minutes
                })
            });

            if (res.ok) {
                const data = await res.json();
                this.status = data.status;
                this.updateTodayWatchTimeDisplay();
                this.hideExtendModal();
                this.hideTimeupOverlay();
                this.hideFolderBlockedModal();
                this.isLocked = false;
                this.notified3Min = false;
                this.notified1Min = false;

                // 重新读取剩余秒数
                this.currentRemainingSeconds = this.getFolderRemainingSeconds(this.activeFolder);

                this.app.notify?.show(
                    minutes >= 1440 ? '今日已解除限制' : `已成功加时 ${minutes} 分钟`,
                    'success'
                );

                // 若在播放页，尝试恢复播放
                if (this.app.currentScreen === 'player' && this.app.player) {
                    try { this.app.player.play().catch(() => {}); } catch (_) {}
                }
                // 若在合集页，刷新列表样式
                if (this.app.currentScreen === 'folders') {
                    this.app.loadFolders(this.app.currentPath.join('/'));
                }
            } else {
                this.app.notify?.show('加时失败', 'error');
            }
        } catch (err) {
            this.app.notify?.show('网络异常，加时失败', 'error');
        }
    }

    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
}
