package com.lcx.kidstv.ui

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.lcx.kidstv.core.data.ServerStore
import com.lcx.kidstv.core.model.AppSettings
import com.lcx.kidstv.core.model.AppUpdateInfo
import com.lcx.kidstv.core.model.CacheStatus
import com.lcx.kidstv.core.model.Episode
import com.lcx.kidstv.core.model.FolderInfo
import com.lcx.kidstv.core.model.TimeLimitFolder
import com.lcx.kidstv.core.model.TimeLimitsStatus
import com.lcx.kidstv.core.model.WatchProgress
import com.lcx.kidstv.core.net.ApiException
import com.lcx.kidstv.core.net.PlayerApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.random.Random

/** 五个屏幕，对应网页版的 5 个 `.screen` div */
enum class Screen { LOADING, FOLDERS, VIDEOS, PLAYER, SETTINGS }

/** 家长门禁的两种模式（与后端 `parent_pin` 是否配置联动） */
enum class GateMode { MATH, PIN }

/**
 * 应用唯一的状态容器。
 *
 * 这里集中了网页版 `frontend/js/app.js`（1111 行）+ `timelimits-controller.js`（800 行）的行为，
 * 但**不做任何业务解析**——解析、签名、分片代理全在后端，客户端只编排 UI 与播放。
 */
class AppViewModel(app: Application) : AndroidViewModel(app) {

    val serverStore = ServerStore(app)
    val api = PlayerApi(serverStore.baseUrl)

    // ---------------- 导航 ----------------

    var screen by mutableStateOf(Screen.LOADING)
        private set

    /** 当前浏览的路径栈（对应网页版 currentPath） */
    var pathStack by mutableStateOf<List<String>>(emptyList())
        private set

    // ---------------- 列表数据 ----------------

    var folders by mutableStateOf<List<FolderInfo>>(emptyList())
        private set
    var foldersLoading by mutableStateOf(true)
        private set
    var videos by mutableStateOf<List<Episode>>(emptyList())
        private set
    var currentFolderPath by mutableStateOf("")
        private set
    var continueWatching by mutableStateOf<List<Episode>>(emptyList())
        private set
    var libraryVideoCount by mutableStateOf(0)
        private set

    /** 异步补齐的封面缓存，key = `<bvid>|<page>`（服务端只对已缓存的封面直接返回地址） */
    var covers by mutableStateOf<Map<String, String>>(emptyMap())
        private set

    // ---------------- 服务端设置与限时 ----------------

    var settings by mutableStateOf(AppSettings())
        private set
    var limits by mutableStateOf<TimeLimitsStatus?>(null)
        private set
    var cacheStatus by mutableStateOf<CacheStatus?>(null)
        private set
    var cookieConfigured by mutableStateOf(false)
        private set

    // ---------------- 播放 ----------------

    var currentEpisode by mutableStateOf<Episode?>(null)
        private set

    /**
     * Media3 播放器。用 Compose 状态持有 —— 因为播放器是在「拿到播放地址之后」才惰性创建的，
     * 而播放页可能更早就已经组合（此时还是加载遮罩），必须能触发 PlayerView 重新挂载。
     */
    var player by mutableStateOf<ExoPlayer?>(null)
        private set

    /** 播放准备遮罩（对应网页版 #download-progress） */
    var preparing by mutableStateOf(false)
        private set
    var preparePercent by mutableStateOf(0)
        private set
    var prepareStage by mutableStateOf("正在准备播放，请稍候")
        private set

    /** 后台播放失败/无法播放时的提示（在播放器上方显示） */
    var playerError by mutableStateOf<String?>(null)
        private set

    /** 是否全屏播放（影院全屏模式） */
    var isFullscreen by mutableStateOf(false)
        private set

    // ---------------- 提示 ----------------

    var toast by mutableStateOf<String?>(null)
        private set

    // ---------------- 家长门禁 ----------------

    var gateVisible by mutableStateOf(false)
        private set
    var gateMode by mutableStateOf(GateMode.MATH)
        private set
    var gateQuestion by mutableStateOf("")
        private set
    var gateError by mutableStateOf(false)
        private set

    private var gateAnswer = 0
    private var gateOnSuccess: (() -> Unit)? = null

    /** 通过验证后的免密窗口（网页版是 10 分钟） */
    private var parentUnlockedUntil = 0L

    // ---------------- 弹窗 ----------------

    /** 合集受限拦截弹窗：title / desc */
    var blockedDialog by mutableStateOf<Pair<String, String>?>(null)
        private set

    /** 临时加时弹窗 */
    var extendVisible by mutableStateOf(false)
        private set

    /** 播放中到期锁屏遮罩：非 null 即为已锁定（值为 lockReason） */
    var lockReason by mutableStateOf<String?>(null)
        private set

    /** 播放中的临界提醒气泡（3 分钟 / 1 分钟） */
    var timeNotice by mutableStateOf<String?>(null)
        private set

    // ---------------- 版本与自动更新 ----------------

    var updateInfo by mutableStateOf<AppUpdateInfo?>(null)
        private set
    var updateDialogVisible by mutableStateOf(false)
        private set
    var isCheckingUpdate by mutableStateOf(false)
        private set
    var isDownloadingUpdate by mutableStateOf(false)
        private set
    var updateDownloadProgress by mutableStateOf(0)
        private set

    val appVersionName: String
        get() = try {
            val pInfo = appContext.packageManager.getPackageInfo(appContext.packageName, 0)
            pInfo.versionName ?: "1.0.1"
        } catch (_: Exception) {
            "1.0.1"
        }

    val appVersionCode: Long
        get() = try {
            val pInfo = appContext.packageManager.getPackageInfo(appContext.packageName, 0)
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
                pInfo.longVersionCode
            } else {
                @Suppress("DEPRECATION")
                pInfo.versionCode.toLong()
            }
        } catch (_: Exception) {
            2L
        }

    // ---------------- 应用前后台 ----------------

    var appResumed by mutableStateOf(true)

    // ---------------- 内部：播放任务与计时 ----------------

    private var playJob: Job? = null
    private var tickerJob: Job? = null
    private var activeFolder: String? = null
    private var unreportedSeconds = 0.0
    private var currentRemainingSeconds: Int? = null
    private var notified3Min = false
    private var notified1Min = false
    private var lockTriggered = false
    private var lastProgressSavedAt = 0L

    private val appContext get() = getApplication<Application>()

    // =====================================================================
    //  启动
    // =====================================================================

    fun bootstrap() {
        viewModelScope.launch {
            val startedAt = System.currentTimeMillis()
            // 与网页版一致：并发拉设置与限时状态，再加载文件夹
            launch { syncSettings() }
            launch { refreshLimits() }
            launch { loadFolders("") }
            // 启动时静默检查更新
            launch { checkAppUpdate(silent = true) }
            // 让加载动画至少展示 900ms，避免一闪而过（网页版是 450ms，平板过渡感觉更快）
            val elapsed = System.currentTimeMillis() - startedAt
            if (elapsed < 900) delay(900 - elapsed)
            enterApp()
        }
    }

    private fun enterApp() {
        if (screen != Screen.LOADING) return
        screen = Screen.FOLDERS
    }

    // =====================================================================
    //  合集
    // =====================================================================

    fun loadFolders(path: String) {
        viewModelScope.launch {
            foldersLoading = true
            try {
                val result = api.listFolders(path)
                folders = result
                pathStack = if (path.isBlank()) emptyList() else path.split("/").filter { it.isNotBlank() }
                refreshLimits()
                loadAllProgress(result)
            } catch (e: Exception) {
                folders = emptyList()
                showToast("加载文件夹失败")
            } finally {
                foldersLoading = false
            }
        }
    }

    fun refreshCurrentFolders() {
        loadFolders(pathStack.joinToString("/"))
    }

    fun navigateToParent() {
        if (pathStack.isEmpty()) return
        loadFolders(pathStack.dropLast(1).joinToString("/"))
    }

    fun openFolder(folder: FolderInfo) {
        if (isFolderLocked(folder.path)) {
            showFolderBlocked(folder.path)
            return
        }
        if (folder.hasListFile) loadVideos(folder.path) else loadFolders(folder.path)
    }

    /**
     * 首页「继续观看」需要所有合集各自的进度 —— 与网页版一样并发拉取。
     * 单合集失败不影响整体（用 runCatching 兜住）。
     */
    private suspend fun loadAllProgress(allFolders: List<FolderInfo>) {
        val playable = allFolders.filter { it.hasListFile }
        // 注意：这里必须显式开 coroutineScope —— `async` 是 CoroutineScope 的扩展，
        // 普通 suspend 函数里没有这个接收者。
        val collected = coroutineScope {
            playable.map { folder ->
                async {
                    runCatching {
                        val episodes = api.listEpisodes(folder.path)
                        val progress = runCatching { api.getProgress(folder.path) }
                            .getOrDefault(emptyMap<String, WatchProgress>())
                        episodes.map { ep ->
                            ep.folderPath = folder.path
                            ep.progress = progress["${folder.path}|${ep.bvid}|${ep.page}"]
                            ep
                        }
                    }.getOrDefault(emptyList<Episode>())
                }
            }.awaitAll().flatten()
        }

        libraryVideoCount = collected.size
        continueWatching = collected
            .filter { it.progress != null && it.progress?.completed == false && (it.progress?.position ?: 0.0) > 5 }
            .sortedByDescending { it.progress?.updatedAt ?: 0.0 }
            .take(6)
    }

    // =====================================================================
    //  分集列表
    // =====================================================================

    fun loadVideos(folderPath: String) {
        viewModelScope.launch {
            try {
                currentFolderPath = folderPath
                val episodes = api.listEpisodes(folderPath)
                val progress = runCatching { api.getProgress(folderPath) }.getOrDefault(emptyMap())
                episodes.forEach { ep ->
                    ep.folderPath = folderPath
                    ep.progress = progress["${folderPath}|${ep.bvid}|${ep.page}"]
                }
                videos = episodes
                screen = Screen.VIDEOS
                loadCovers(episodes)
            } catch (e: Exception) {
                showToast("加载视频列表失败")
            }
        }
    }

    // =====================================================================
    //  封面（异步补齐，与网页版 loadCoversAsync 等价）
    // =====================================================================

    fun loadCovers(episodes: List<Episode>) {
        viewModelScope.launch {
            val need = episodes.filter { it.coverUrl.isBlank() && it.bvid.isNotBlank() }
            if (need.isEmpty()) return@launch
            val merged = mutableMapOf<String, String>()
            need.groupBy { it.bvid }.forEach { (bvid, items) ->
                runCatching { api.batchCovers(bvid, items.map { it.page }) }
                    .onSuccess { batch ->
                        batch.covers.forEach { (page, url) ->
                            if (url.isNotBlank()) merged["$bvid|$page"] = api.coverUrl(url)
                        }
                    }
            }
            if (merged.isNotEmpty()) covers = covers + merged
        }
    }

    /** 视频卡片最终使用的封面地址；拿不到就返回空串（UI 会显示占位图标） */
    fun coverFor(episode: Episode): String {
        if (episode.coverUrl.isNotBlank()) return api.coverUrl(episode.coverUrl)
        return covers["${episode.bvid}|${episode.page}"].orEmpty()
    }

    /** 封面全失败时的兜底地址（对应网页版 img onerror 的 /api/cover/...） */
    fun fallbackCoverFor(episode: Episode): String =
        api.fallbackCoverUrl(episode.bvid, episode.page)

    // =====================================================================
    //  播放
    // =====================================================================

    fun playEpisode(episode: Episode, folderPath: String = currentFolderPath) {
        if (isFolderLocked(folderPath)) {
            showFolderBlocked(folderPath)
            return
        }
        playJob?.cancel()
        playJob = viewModelScope.launch {
            // 从「继续观看」进来时，当前分集列表可能还是别的合集 → 先同步过来，
            // 否则播放页的「上一集 / 下一集」会指向错误的合集。
            if (currentFolderPath != folderPath) {
                currentFolderPath = folderPath
                runCatching { api.listEpisodes(folderPath) }.onSuccess { list ->
                    val progress = runCatching { api.getProgress(folderPath) }.getOrDefault(emptyMap())
                    list.forEach { item ->
                        item.folderPath = folderPath
                        item.progress = progress["${folderPath}|${item.bvid}|${item.page}"]
                    }
                    videos = list
                    loadCovers(list)
                }
            }

            // 停止上一集播放与计时
            saveCurrentProgress(force = true)
            stopTracking()
            player?.let { exo ->
                runCatching {
                    exo.stop()
                    exo.clearMediaItems()
                }
            }
            subtitleUrl = null

            currentEpisode = episode
            episode.folderPath = folderPath
            screen = Screen.PLAYER
            startTracking(folderPath)
            preparing = true
            preparePercent = 0
            prepareStage = "正在连接高清视频流…"
            playerError = null

            try {
                val task = api.startDownload(folderPath, episode.displayIndex, episode.bvid, episode.page)
                if (task.status == "ready") {
                    loadSubtitleIfAny(episode)
                    openPlayer(task.videoUrl, task.stream)
                } else if (task.taskId != null) {
                    pollDownloadTask(task.taskId, episode)
                } else {
                    failPreparation("无法开始播放")
                }
            } catch (e: Exception) {
                failPreparation("播放视频失败")
            }
        }
    }

    private suspend fun pollDownloadTask(taskId: String, episode: Episode) {
        repeat(MAX_POLL_TIMES) {
            val task = runCatching { api.getDownloadTask(taskId) }.getOrNull()
                ?: run { failPreparation("下载任务不可用"); return }
            preparePercent = task.progress
            prepareStage = task.stage.ifBlank { "正在准备播放，请稍候" }
            when (task.status) {
                "ready" -> {
                    loadSubtitleIfAny(episode)
                    openPlayer(
                        task.videoUrl.ifBlank { "/static/${episode.folderPath}/${episode.bvid}_p${episode.page}.mp4" },
                        task.stream,
                    )
                    return
                }
                "failed" -> {
                    failPreparation(task.error ?: "下载失败")
                    return
                }
            }
            delay(800)
        }
        failPreparation("准备超时，请重试")
    }

    private fun failPreparation(message: String) {
        preparing = false
        playerError = message
        showToast(message)
    }

    private var subtitleUrl: String? = null

    /** 只有 B站 提供字幕；外部来源（silidm）直接跳过，避免无谓的 404 */
    private suspend fun loadSubtitleIfAny(episode: Episode) {
        subtitleUrl = if (episode.source == "bilibili") {
            runCatching {
                api.getSubtitleUrl(episode.folderPath, episode.displayIndex, episode.bvid, episode.page)
            }.getOrNull()
        } else {
            null
        }
    }

    private fun openPlayer(rawUrl: String, stream: Boolean) {
        val url = api.resolve(rawUrl)
        ensurePlayer()
        val exo = player ?: return

        // 恢复播放进度（与网页版 loadedmetadata 保持一致：已看 > 5秒且未完播，自动续播）
        val saved = currentEpisode?.progress
        val durationSec = currentEpisode?.duration ?: 0
        val startPositionMs = if (saved != null && !saved.completed && saved.position > 5.0 && (durationSec <= 0 || saved.position < durationSec - 5.0)) {
            (saved.position * 1000).toLong()
        } else {
            0L
        }

        val startPlayback = { withSubtitle: Boolean ->
            val builder = MediaItem.Builder().setUri(Uri.parse(url))
            val sub = subtitleUrl
            if (withSubtitle && sub != null) {
                // 侧载字幕：后端把 B站 字幕抓成 VTT 落盘，这里作为 SubtitleConfiguration 挂上去
                val config = MediaItem.SubtitleConfiguration.Builder(Uri.parse(api.resolve(sub)))
                    .setMimeType(MimeTypes.TEXT_VTT)
                    .setLanguage("zh")
                    .setLabel("中文字幕")
                    .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                    .build()
                builder.setSubtitleConfigurations(listOf(config))
            }
            exo.setMediaItem(builder.build(), startPositionMs)
            exo.prepare()
            exo.playWhenReady = settings.autoplay
        }

        runCatching { startPlayback(true) }
            .recoverCatching {
                // 侧载字幕在个别版本上不被支持 → 退化成纯视频，不影响播放
                subtitleUrl = null
                startPlayback(false)
            }
            .onFailure { failPreparation("播放器初始化失败") }

        preparing = false
        if (startPositionMs > 0) {
            val min = (startPositionMs / 1000) / 60
            val sec = (startPositionMs / 1000) % 60
            showToast("已恢复上次播放进度 (%d:%02d)".format(min, sec))
        }
    }

    private fun ensurePlayer() {
        if (player != null) return
        val newPlayer = ExoPlayer.Builder(appContext).build().apply {
            repeatMode = Player.REPEAT_MODE_OFF
            trackSelectionParameters = trackSelectionParameters.buildUpon()
                .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, !settings.subtitles)
                .build()
            addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(playbackState: Int) {
                    if (playbackState == Player.STATE_ENDED) {
                        handlePlaybackEnded()
                    }
                }

                override fun onPlayerError(error: PlaybackException) {
                    handlePlaybackError(error)
                }
            })
        }
        player = newPlayer
    }

    private fun handlePlaybackEnded() {
        saveCurrentProgress(force = true, markCompleted = true)
        flushHeartbeat()
        if (settings.autoplay && hasRelativeEpisode(1)) {
            showToast("本集播放完毕，即将播放下一集…")
            playRelative(1)
        }
    }

    private fun handlePlaybackError(error: PlaybackException) {
        val message = when (error.errorCode) {
            PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
            PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT -> "网络连接失败，请检查服务器连接"
            PlaybackException.ERROR_CODE_IO_FILE_NOT_FOUND,
            PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS -> "视频资源不存在或服务器异常"
            PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED,
            PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED -> "视频流解析失败，请重试"
            else -> "视频播放遇到问题（${error.errorCodeName}）"
        }
        preparing = false
        playerError = message
        showToast(message)
    }

    fun retryPlayback() {
        val ep = currentEpisode ?: return
        playEpisode(ep, currentFolderPath)
    }

    fun togglePlayPause() {
        val exo = player ?: return
        if (exo.isPlaying) exo.pause() else exo.play()
    }

    /** 检查是否存在前一集或后一集 */
    fun hasRelativeEpisode(offset: Int): Boolean {
        val current = currentEpisode ?: return false
        val list = videos
        val idx = list.indexOfFirst { it.bvid == current.bvid && it.page == current.page }
        if (idx < 0) return false
        return list.getOrNull(idx + offset) != null
    }

    /** 上一集 / 下一集（网页版 playRelative）。返回是否成功切换 */
    fun playRelative(offset: Int) {
        val current = currentEpisode ?: return
        val list = videos
        val idx = list.indexOfFirst { it.bvid == current.bvid && it.page == current.page }
        if (idx < 0) return
        val target = list.getOrNull(idx + offset)
        if (target == null) {
            showToast(if (offset > 0) "已经是最后一集" else "已经是第一集")
            return
        }
        playEpisode(target, currentFolderPath)
    }

    fun toggleFullscreen() {
        isFullscreen = !isFullscreen
    }

    fun exitFullscreen() {
        isFullscreen = false
    }

    /** 离开播放页时彻底停止并清理（对应网页版 clearVideoPlayer） */
    fun clearPlayer() {
        playJob?.cancel()
        playJob = null
        preparing = false
        saveCurrentProgress(force = true)
        stopTracking()
        player?.let { exo ->
            runCatching {
                exo.stop()
                exo.clearMediaItems()
            }
        }
        subtitleUrl = null
        currentEpisode = null
        isFullscreen = false
    }

    private fun releasePlayer() {
        playJob?.cancel()
        playJob = null
        tickerJob?.cancel()
        tickerJob = null
        player?.let { runCatching { it.release() } }
        player = null
        isFullscreen = false
    }

    fun onAppPause() {
        appResumed = false
        player?.pause()
        saveCurrentProgress(force = true)
        flushHeartbeat()
    }

    fun onAppResume() {
        appResumed = true
        refreshLimits()
    }

    override fun onCleared() {
        releasePlayer()
        super.onCleared()
    }

    // =====================================================================
    //  进度上报
    // =====================================================================

    private fun saveCurrentProgress(force: Boolean = false, markCompleted: Boolean = false) {
        val exo = player ?: return
        val episode = currentEpisode ?: return
        if (episode.folderPath.isBlank()) return
        val position = exo.currentPosition / 1000.0
        val duration = exo.duration.let { if (it > 0) it / 1000.0 else episode.duration.toDouble() }
        if (position <= 0.0 && duration <= 0.0) return
        if (!force && abs(System.currentTimeMillis() - lastProgressSavedAt) < PROGRESS_SAVE_INTERVAL_MS) return
        lastProgressSavedAt = System.currentTimeMillis()
        val isCompleted = markCompleted || (duration > 0 && position / duration >= 0.92)

        // 同步更新内存中的进度，返回列表时即刻反映
        val updatedProgress = WatchProgress(
            position = position,
            duration = duration,
            completed = isCompleted,
            updatedAt = System.currentTimeMillis() / 1000.0,
        )
        episode.progress = updatedProgress

        viewModelScope.launch {
            runCatching {
                api.saveProgress(
                    folderPath = episode.folderPath,
                    bvid = episode.bvid,
                    page = episode.page,
                    position = position,
                    duration = duration,
                    completed = isCompleted,
                )
            }
        }
    }

    // =====================================================================
    //  设置
    // =====================================================================

    fun syncSettings() {
        viewModelScope.launch {
            runCatching { api.getSettings() }.onSuccess { settings = it }
            runCatching { api.cookieStatus() }.onSuccess { cookieConfigured = it.hasCookie }
        }
    }

    fun setAutoplay(value: Boolean) {
        settings = settings.copy(autoplay = value)
        viewModelScope.launch { runCatching { api.saveSetting("autoplay", value) } }
    }

    fun setSubtitles(value: Boolean) {
        settings = settings.copy(subtitles = value)
        player?.let { exo ->
            exo.trackSelectionParameters = exo.trackSelectionParameters.buildUpon()
                .setTrackTypeDisabled(C.TRACK_TYPE_TEXT, !value)
                .build()
        }
        viewModelScope.launch { runCatching { api.saveSetting("subtitles", value) } }
    }

    fun saveCookie(cookie: String) {
        if (cookie.isBlank()) {
            showToast("请先粘贴 Cookie")
            return
        }
        viewModelScope.launch {
            runCatching { api.saveCookie(cookie.trim()) }
                .onSuccess {
                    cookieConfigured = true
                    showToast("Cookie 保存成功")
                }
                .onFailure { showToast("Cookie 保存失败，请检查服务是否正常") }
        }
    }

    fun refreshCacheStatus() {
        viewModelScope.launch {
            runCatching { api.cacheStatus() }.onSuccess { cacheStatus = it }
        }
    }

    fun cleanCache() {
        viewModelScope.launch {
            runCatching {
                api.cleanCache()
                refreshCacheStatus()
                showToast("缓存清理完成")
            }.onFailure { showToast("缓存清理失败") }
        }
    }

    fun updateServerUrl(url: String, onApplied: (Boolean) -> Unit) {
        val normalized = PlayerApi.normalize(url)
        if (normalized == api.baseUrl) {
            onApplied(true)
            return
        }
        serverStore.baseUrl = normalized
        api.setBaseUrl(normalized)
        viewModelScope.launch {
            val ok = runCatching { api.listFolders("") }.isSuccess
            if (ok) {
                showToast("已连接：$normalized")
                refreshLimits()
                loadFolders("")
            } else {
                showToast("连接失败，请检查地址与服务")
            }
            onApplied(ok)
        }
    }

    val serverUrl: String get() = api.baseUrl

    // =====================================================================
    //  观看限时：状态查询
    // =====================================================================

    fun refreshLimits() {
        viewModelScope.launch {
            runCatching { api.timeLimitsStatus() }.onSuccess { limits = it }
        }
    }

    /** 与网页版 isFolderLocked 完全等价 */
    fun isFolderLocked(folderPath: String): Boolean {
        val status = limits ?: return false
        if (!status.enabled) return false
        if (status.globalIsLocked) return true
        val clean = cleanPath(folderPath)
        val folder = status.folders.firstOrNull { it.path == clean } ?: return false
        return folder.isLocked
    }

    fun folderRemainingSeconds(folderPath: String): Int? {
        val status = limits ?: return null
        if (!status.enabled) return null
        val clean = cleanPath(folderPath)
        val folder = status.folders.firstOrNull { it.path == clean }
        return folder?.remainingSeconds ?: status.globalRemainingSeconds
    }

    /** 顶部「今日已看 N 分钟」胶囊文案与配色（对应网页版 updateTodayWatchTimeDisplay） */
    data class TimePill(val text: String, val warn: Boolean, val locked: Boolean)

    fun timePill(): TimePill {
        val status = limits ?: return TimePill("⏱️ 今日已看 0 分钟", false, false)
        val totalMin = (status.totalUsedSeconds + unreportedSeconds).toInt() / 60
        if (status.enabled && status.globalLimitMinutes > 0) {
            val effLimit =
                if (status.effectiveGlobalLimitMinutes > 0) status.effectiveGlobalLimitMinutes
                else status.globalLimitMinutes
            val locked = totalMin >= effLimit || status.globalIsLocked
            val warn = !locked && effLimit - totalMin <= 5
            return TimePill("⏱️ 今日已看 $totalMin / $effLimit 分钟", warn, locked)
        }
        return TimePill("⏱️ 今日已看 $totalMin 分钟", false, false)
    }

    // =====================================================================
    //  观看限时：心跳计时
    // =====================================================================

    private fun startTracking(folderPath: String) {
        stopTracking()
        activeFolder = cleanPath(folderPath)
        unreportedSeconds = 0.0
        notified3Min = false
        notified1Min = false
        lockTriggered = false
        timeNotice = null
        lockReason = null
        currentRemainingSeconds = folderRemainingSeconds(activeFolder ?: "")

        tickerJob = viewModelScope.launch {
            while (isActive) {
                delay(1000)
                handleTick()
            }
        }
    }

    private fun stopTracking() {
        tickerJob?.cancel()
        tickerJob = null
        timeNotice = null
        flushHeartbeat()
    }

    private fun handleTick() {
        val exo = player
        if (exo != null && exo.isPlaying && appResumed) {
            unreportedSeconds += 1.0
            currentRemainingSeconds?.let { remaining ->
                val next = (remaining - 1).coerceAtLeast(0)
                currentRemainingSeconds = next
                checkRemainingNotice(next)
                if (next <= 0 && !lockTriggered) triggerLockout("time_exhausted")
            }
            if (unreportedSeconds >= HEARTBEAT_INTERVAL_SECONDS) flushHeartbeat()
            saveCurrentProgress()
        }
    }

    private fun flushHeartbeat() {
        val folder = activeFolder
        val delta = unreportedSeconds
        if (folder.isNullOrBlank() || delta <= 0.0) return
        unreportedSeconds = 0.0
        viewModelScope.launch {
            runCatching { api.heartbeat(folder, delta) }
                .onSuccess { result ->
                    result.remainingSeconds?.let { currentRemainingSeconds = it }
                    limits = limits?.let {
                        it.copy(totalUsedSeconds = it.totalUsedSeconds + delta.toInt())
                    }
                    if (result.shouldLock && !lockTriggered) triggerLockout(result.lockReason ?: "folder")
                }
                .onFailure {
                    // 上报失败就把时间还回去，下次一起报，避免少计
                    unreportedSeconds += delta
                }
        }
    }

    private fun checkRemainingNotice(remainingSec: Int) {
        if (remainingSec <= 0) return
        when {
            remainingSec <= 180 && remainingSec > 60 && !notified3Min -> {
                notified3Min = true
                timeNotice = "⏱️ 还有 3 分钟要休息眼睛咯 🎈"
                viewModelScope.launch {
                    delay(6000)
                    if (timeNotice?.startsWith("⏱️") == true) timeNotice = null
                }
            }
            remainingSec <= 60 && !notified1Min -> {
                notified1Min = true
                timeNotice = "⏰ 还有 1 分钟倒计时，准备休息啦"
            }
        }
    }

    fun dismissTimeNotice() {
        timeNotice = null
    }

    private fun triggerLockout(reason: String) {
        lockTriggered = true
        timeNotice = null
        player?.let { runCatching { it.pause() } }
        lockReason = reason
    }

    fun dismissLock() {
        lockReason = null
    }

    // =====================================================================
    //  合集受限拦截
    // =====================================================================

    fun showFolderBlocked(folderPath: String) {
        val global = limits?.globalIsLocked == true
        blockedDialog = if (global) {
            "今日全局观看总时长已用完 🌙" to
                "今天看视频的时间很充实啦，眼睛需要好好休息一下！明天小电视再陪你玩~"
        } else {
            "这个合集今日时间已用完 🎈" to
                "今天这个合集看得够多啦，让眼睛休息一下，或者去看看其他内容吧！"
        }
    }

    fun dismissBlockedDialog() {
        blockedDialog = null
    }

    // =====================================================================
    //  家长门禁
    // =====================================================================

    /** 若在免密窗口内直接放行，否则弹验证（对应网页版 requestParentAccess） */
    fun requestParentAccess(onSuccess: () -> Unit) {
        if (System.currentTimeMillis() < parentUnlockedUntil) {
            onSuccess()
            return
        }
        gateOnSuccess = onSuccess
        gateError = false
        if (limits?.hasParentPin == true) {
            gateMode = GateMode.PIN
            gateQuestion = ""
        } else {
            gateMode = GateMode.MATH
            // 趣味算术题：70% 乘法（4~9 × 4~9），30% 两位数加法
            if (Random.nextDouble() > 0.3) {
                val a = Random.nextInt(4, 10)
                val b = Random.nextInt(4, 10)
                gateAnswer = a * b
                gateQuestion = "$a × $b = ?"
            } else {
                val a = Random.nextInt(15, 55)
                val b = Random.nextInt(15, 55)
                gateAnswer = a + b
                gateQuestion = "$a + $b = ?"
            }
        }
        gateVisible = true
    }

    fun dismissGate() {
        gateVisible = false
        gateOnSuccess = null
    }

    fun submitGate(input: String) {
        viewModelScope.launch {
            val pass = if (gateMode == GateMode.PIN) {
                runCatching { api.verifyPin(input.trim()) }.getOrDefault(false)
            } else {
                input.trim().toIntOrNull() == gateAnswer
            }
            if (pass) {
                parentUnlockedUntil = System.currentTimeMillis() + PARENT_UNLOCK_WINDOW_MS
                val callback = gateOnSuccess
                gateVisible = false
                gateOnSuccess = null
                callback?.invoke()
            } else {
                gateError = true
            }
        }
    }

    // =====================================================================
    //  家长区：限时配置
    // =====================================================================

    fun saveTimeLimitsConfig(
        enabled: Boolean,
        globalLimitMinutes: Int,
        folderLimits: Map<String, Int>,
        parentPin: String? = null,
    ) {
        viewModelScope.launch {
            runCatching {
                api.saveTimeLimitsConfig(enabled, globalLimitMinutes, folderLimits, parentPin)
            }.onSuccess {
                limits = it
                showToast("限时设置已保存")
            }.onFailure { showToast("保存限时设置失败") }
        }
    }

    fun resetTodayUsage() {
        viewModelScope.launch {
            runCatching { api.resetToday() }
                .onSuccess {
                    limits = it
                    showToast("今日计时已重置")
                }
                .onFailure { showToast("重置失败") }
        }
    }

    // =====================================================================
    //  临时加时
    // =====================================================================

    fun openExtendDialog() {
        extendVisible = true
    }

    fun dismissExtendDialog() {
        extendVisible = false
    }

    fun submitExtension(type: String, minutes: Int) {
        val folder = activeFolder ?: currentFolderPath
        viewModelScope.launch {
            runCatching { api.extendTime(type, folder, minutes) }
                .onSuccess { data ->
                    limits = data.status
                    extendVisible = false
                    lockReason = null
                    lockTriggered = false
                    notified3Min = false
                    notified1Min = false
                    currentRemainingSeconds = folderRemainingSeconds(folder)
                    showToast(if (minutes >= 1440) "今日已解除限制" else "已成功加时 $minutes 分钟")
                    if (screen == Screen.PLAYER) player?.play()
                    if (screen == Screen.FOLDERS) refreshCurrentFolders()
                }
                .onFailure { showToast("加时失败，请检查网络") }
        }
    }

    // =====================================================================
    //  屏幕切换与工具
    // =====================================================================

    fun backToFolders() {
        if (screen == Screen.PLAYER) clearPlayer()
        screen = Screen.FOLDERS
        refreshLimits()
    }

    fun backToVideos() {
        clearPlayer()
        // 若当前没有分集列表（例如是从「继续观看」直接进的播放页），退回合集页
        screen = if (videos.isEmpty()) Screen.FOLDERS else Screen.VIDEOS
    }

    fun openSettings() {
        syncSettings()
        refreshLimits()
        refreshCacheStatus()
        screen = Screen.SETTINGS
    }

    fun showToast(message: String) {
        toast = message
        viewModelScope.launch {
            delay(3000)
            if (toast == message) toast = null
        }
    }

    fun dismissToast() {
        toast = null
    }

    private fun cleanPath(path: String): String =
        path.replace('\\', '/').trim('/')

    /** 当前合集里，本集是第几集（用于播放页「第 N 集」徽章） */
    val currentEpisodeList: List<Episode> get() = videos

    // =====================================================================
    //  应用版本与更新
    // =====================================================================

    fun checkAppUpdate(silent: Boolean = false) {
        if (isCheckingUpdate || isDownloadingUpdate) return
        viewModelScope.launch {
            isCheckingUpdate = true
            try {
                val remote = api.getAppUpdateInfo()
                updateInfo = remote
                if (remote.versionCode > appVersionCode) {
                    updateDialogVisible = true
                } else if (!silent) {
                    showToast("当前已是最新版本 (v$appVersionName)")
                }
            } catch (e: Exception) {
                if (!silent) {
                    showToast("检查更新失败: ${e.message ?: "网络异常"}")
                }
            } finally {
                isCheckingUpdate = false
            }
        }
    }

    fun dismissUpdateDialog() {
        if (!isDownloadingUpdate) {
            updateDialogVisible = false
        }
    }

    fun startUpdateDownload() {
        val info = updateInfo ?: return
        if (isDownloadingUpdate) return

        viewModelScope.launch {
            isDownloadingUpdate = true
            updateDownloadProgress = 0
            try {
                val cacheDir = appContext.externalCacheDir ?: appContext.cacheDir
                val apkFile = java.io.File(cacheDir, "kids_tv_update.apk")
                if (apkFile.exists()) apkFile.delete()

                api.downloadApk(info.downloadUrl, apkFile) { downloaded, total ->
                    if (total > 0) {
                        updateDownloadProgress = ((downloaded.toDouble() / total.toDouble()) * 100).toInt().coerceIn(0, 100)
                    }
                }
                updateDownloadProgress = 100
                delay(300)
                installApk(apkFile)
            } catch (e: Exception) {
                showToast("下载更新失败: ${e.message ?: "网络错误"}")
            } finally {
                isDownloadingUpdate = false
            }
        }
    }

    private fun installApk(file: java.io.File) {
        try {
            val context = appContext
            val uri = androidx.core.content.FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file,
            )
            val intent = android.content.Intent(android.content.Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                    android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION
            }
            context.startActivity(intent)
        } catch (e: Exception) {
            showToast("唤起安装器失败: ${e.message}")
        }
    }

    companion object {
        private const val HEARTBEAT_INTERVAL_SECONDS = 5.0
        private const val PROGRESS_SAVE_INTERVAL_MS = 5000L
        private const val PARENT_UNLOCK_WINDOW_MS = 10 * 60 * 1000L
        private const val MAX_POLL_TIMES = 600
    }
}

/** 便于 UI 层判断：合集是否被限时锁住时拿到的展示信息 */
data class FolderLockInfo(val locked: Boolean, val remainingMinutes: Int?)
