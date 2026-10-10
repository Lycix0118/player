package com.lcx.kidstv.core.net

import com.lcx.kidstv.core.model.AppSettings
import com.lcx.kidstv.core.model.AppUpdateInfo
import com.lcx.kidstv.core.model.CacheStatus
import com.lcx.kidstv.core.model.CookieStatus
import com.lcx.kidstv.core.model.CoverBatch
import com.lcx.kidstv.core.model.DownloadTask
import com.lcx.kidstv.core.model.Episode
import com.lcx.kidstv.core.model.ExtendResult
import com.lcx.kidstv.core.model.FolderInfo
import com.lcx.kidstv.core.model.HeartbeatResult
import com.lcx.kidstv.core.model.PinVerifyResult
import com.lcx.kidstv.core.model.SubtitleResponse
import com.lcx.kidstv.core.model.TimeLimitsStatus
import com.lcx.kidstv.core.model.WatchProgress
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/** 后端返回非 2xx 时抛出；[code] 用于区分 404（资源不存在）与 5xx（服务端问题） */
class ApiException(val code: Int, val bodyText: String) : Exception("HTTP $code: $bodyText")

/**
 * 后端（FastAPI）HTTP 客户端。
 *
 * 设计要点：
 * - **后端一行没改**：所有解析、WBI 签名、HLS 分片代理、元数据融合都在服务端，
 *   客户端只负责取 JSON 与拼播放地址。
 * - `baseUrl` 可运行时切换（家长设置里填服务器地址），因此不是 val。
 * - 用 OkHttp 的连接池复用：silidm 的 HLS 分片是逐片拉取的，
 *   后端本身也是靠连接复用才跑得动（见项目笔记），客户端这边同样受益。
 */
class PlayerApi(baseUrl: String) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .callTimeout(120, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private val json = Json {
        ignoreUnknownKeys = true      // 后端加字段不会导致客户端崩
        isLenient = true
        coerceInputValues = true      // 显式 null 落到默认值，而不是抛异常
        explicitNulls = false
    }

    @Volatile
    var baseUrl: String = normalize(baseUrl)
        private set

    fun setBaseUrl(url: String) {
        baseUrl = normalize(url)
    }

    /** 把后端返回的相对地址（`/static/...`、`/api/hls/...`、`/covers/...`）拼成绝对地址 */
    fun resolve(path: String): String =
        if (path.startsWith("http://") || path.startsWith("https://")) path else baseUrl + path

    // ---------- 底层 ----------

    private suspend fun rawExecute(request: Request): String = withContext(Dispatchers.IO) {
        http.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw ApiException(response.code, body)
            body
        }
    }

    private suspend fun rawGet(path: String): String =
        rawExecute(Request.Builder().url(resolve(path)).get().build())

    private suspend fun rawPost(path: String, body: RequestBody?): String =
        rawExecute(
            Request.Builder().url(resolve(path))
                .post(body ?: EMPTY_BODY)
                .build()
        )

    private suspend fun <T> get(path: String, de: DeserializationStrategy<T>): T =
        json.decodeFromString(de, rawGet(path))

    private suspend fun <T> post(
        path: String,
        body: RequestBody?,
        de: DeserializationStrategy<T>,
    ): T = json.decodeFromString(de, rawPost(path, body))

    // ---------- 合集与分集 ----------

    suspend fun listFolders(path: String? = null): List<FolderInfo> {
        val target = if (path.isNullOrBlank()) "/api/folders" else "/api/folders?path=" + enc(path)
        return get(target, ListSerializer(FolderInfo.serializer()))
    }

    suspend fun listEpisodes(folderPath: String): List<Episode> =
        get("/api/folders/" + enc(folderPath), ListSerializer(Episode.serializer()))

    // ---------- 观看进度 ----------

    /** 返回 key 为 `<folder>|<bvid>|<page>` 的映射（与网页版一致） */
    suspend fun getProgress(folderPath: String): Map<String, WatchProgress> =
        get(
            "/api/progress/" + enc(folderPath),
            MapSerializer(String.serializer(), WatchProgress.serializer()),
        )

    suspend fun saveProgress(
        folderPath: String,
        bvid: String,
        page: Int,
        position: Double,
        duration: Double,
        completed: Boolean,
    ): WatchProgress {
        val body = buildJsonObject {
            put("folder_path", folderPath)
            put("bvid", bvid)
            put("page", page)
            put("position", position)
            put("duration", duration)
            put("completed", completed)
        }.toString().toRequestBody(JSON_MEDIA)
        return post("/api/progress", body, WatchProgress.serializer())
    }

    // ---------- 播放 ----------

    suspend fun startDownload(folderPath: String, index: Int, bvid: String, page: Int): DownloadTask {
        val url = "/api/download/" + enc(folderPath) + "/" + index +
            "?bvid=" + enc(bvid) + "&page=" + page
        return post(url, null, DownloadTask.serializer())
    }

    suspend fun getDownloadTask(taskId: String): DownloadTask =
        get("/api/download/tasks/" + enc(taskId), DownloadTask.serializer())

    // ---------- 设置 ----------

    suspend fun getSettings(): AppSettings = get("/api/settings", AppSettings.serializer())

    suspend fun saveSetting(key: String, value: Boolean): AppSettings {
        val body = buildJsonObject { put(key, value) }.toString().toRequestBody(JSON_MEDIA)
        return post("/api/settings", body, AppSettings.serializer())
    }

    suspend fun saveCookie(cookie: String): Boolean {
        val body = buildJsonObject { put("cookie", cookie) }.toString().toRequestBody(JSON_MEDIA)
        // 返回 {"success":true,"has_cookie":true} —— 只关心调用是否成功，故读原始文本
        rawPost("/api/settings/cookie", body)
        return true
    }

    suspend fun cookieStatus(): CookieStatus =
        get("/api/settings/cookie/status", CookieStatus.serializer())

    // ---------- 观看限时 ----------

    suspend fun timeLimitsStatus(): TimeLimitsStatus =
        get("/api/time-limits/status", TimeLimitsStatus.serializer())

    suspend fun saveTimeLimitsConfig(
        enabled: Boolean,
        globalLimitMinutes: Int,
        folderLimits: Map<String, Int>,
        parentPin: String? = null,
    ): TimeLimitsStatus {
        val body = buildJsonObject {
            put("enabled", enabled)
            put("global_limit_minutes", globalLimitMinutes)
            put("folder_limits", buildJsonObject {
                folderLimits.forEach { (k, v) -> put(k, v) }
            })
            if (parentPin != null) put("parent_pin", parentPin)
        }.toString().toRequestBody(JSON_MEDIA)
        return post("/api/time-limits/config", body, TimeLimitsStatus.serializer())
    }

    suspend fun heartbeat(folderPath: String, deltaSeconds: Double): HeartbeatResult {
        val body = buildJsonObject {
            put("folder_path", folderPath)
            put("delta_seconds", deltaSeconds)
        }.toString().toRequestBody(JSON_MEDIA)
        return post("/api/time-limits/heartbeat", body, HeartbeatResult.serializer())
    }

    suspend fun extendTime(type: String, folderPath: String, minutes: Int): ExtendResult {
        val body = buildJsonObject {
            put("type", type)
            put("folder_path", folderPath)
            put("minutes", minutes)
        }.toString().toRequestBody(JSON_MEDIA)
        return post("/api/time-limits/extend", body, ExtendResult.serializer())
    }

    suspend fun resetToday(): TimeLimitsStatus =
        post("/api/time-limits/reset-today", null, TimeLimitsStatus.serializer())

    suspend fun verifyPin(pin: String): Boolean {
        val body = buildJsonObject { put("pin", pin) }.toString().toRequestBody(JSON_MEDIA)
        return post("/api/time-limits/verify-pin", body, PinVerifyResult.serializer()).valid
    }

    // ---------- 缓存 ----------

    suspend fun cacheStatus(): CacheStatus = get("/api/cache/status", CacheStatus.serializer())

    suspend fun cleanCache() {
        rawPost("/api/cache/clean", null)
    }

    // ---------- 字幕（仅 B站）----------

    /**
     * 取单集字幕地址。外部来源（silidm）没有字幕，调用会 404，这里吞掉返回 null。
     * 注意：`/api/download` 不返回字幕字段，必须单独打这个接口（网页版也是这么做的）。
     */
    suspend fun getSubtitleUrl(folderPath: String, index: Int, bvid: String, page: Int): String? {
        val path = "/api/subtitle/" + enc(folderPath) + "/" + index +
            "?bvid=" + enc(bvid) + "&page=" + page
        return runCatching {
            json.decodeFromString(SubtitleResponse.serializer(), rawGet(path)).subtitleUrl
        }.getOrNull()?.takeIf { it.isNotBlank() }
    }

    // ---------- 封面 ----------

    suspend fun batchCovers(bvid: String, pages: List<Int>): CoverBatch =
        get(
            "/api/batch/covers/" + enc(bvid) + "?pages=" + pages.joinToString(","),
            CoverBatch.serializer(),
        )

    /** 单张封面的兜底地址（网页版 img onerror 用的就是它） */
    fun fallbackCoverUrl(bvid: String, page: Int): String =
        baseUrl + "/api/cover/" + enc(bvid) + "/" + page

    /** 把可能是相对路径的封面地址补成绝对地址 */
    fun coverUrl(raw: String): String =
        if (raw.isBlank()) "" else resolve(raw)

    /** 获取服务端最新应用版本信息 */
    suspend fun getAppUpdateInfo(): AppUpdateInfo =
        get("/api/app/version", AppUpdateInfo.serializer())

    /** 下载新版本 APK 文件并报告下载进度 */
    suspend fun downloadApk(
        downloadUrl: String,
        targetFile: java.io.File,
        onProgress: (bytesDownloaded: Long, totalBytes: Long) -> Unit,
    ): Boolean = withContext(Dispatchers.IO) {
        val request = Request.Builder().url(resolve(downloadUrl)).get().build()
        http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw ApiException(response.code, "下载更新失败: HTTP ${response.code}")
            val body = response.body ?: throw ApiException(500, "下载内容为空")
            val totalBytes = body.contentLength()
            var downloadedBytes = 0L

            targetFile.parentFile?.mkdirs()
            val tempFile = java.io.File(targetFile.parentFile, "${targetFile.name}.downloading")
            tempFile.outputStream().use { output ->
                body.byteStream().use { input ->
                    val buffer = ByteArray(32 * 1024)
                    var read: Int
                    while (input.read(buffer).also { read = it } != -1) {
                        output.write(buffer, 0, read)
                        downloadedBytes += read
                        onProgress(downloadedBytes, totalBytes)
                    }
                    output.flush()
                }
            }
            if (tempFile.renameTo(targetFile)) {
                true
            } else {
                tempFile.copyTo(targetFile, overwrite = true)
                tempFile.delete()
                true
            }
        }
    }

    companion object {
        private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()
        private val EMPTY_BODY: RequestBody = ByteArray(0).toRequestBody(null, 0, 0)
        private const val HEX = "0123456789ABCDEF"

        fun normalize(url: String): String = url.trim().trimEnd('/').ifBlank { DEFAULT_BASE_URL }

        /** 模拟器里 10.0.2.2 就是宿主机的 localhost —— 后端跑在宿主机 8000 端口 */
        const val DEFAULT_BASE_URL = "http://10.0.2.2:8000"

        /**
         * 等价于 JS 的 `encodeURIComponent`。
         * 必须逐字节编码（含中文与 `/`），因为后端路由是 `{folder_path:path}`，
         * 网页版就是这么拼的（`encodeURIComponent(folder.path)`），保持一致最省事。
         */
        fun enc(value: String): String {
            val sb = StringBuilder(value.length + 8)
            for (byte in value.toByteArray(Charsets.UTF_8)) {
                val i = byte.toInt() and 0xFF
                val c = i.toChar()
                if (c in 'A'..'Z' || c in 'a'..'z' || c in '0'..'9' || c in "-_.!~*'()") {
                    sb.append(c)
                } else {
                    sb.append('%').append(HEX[i shr 4]).append(HEX[i and 0x0F])
                }
            }
            return sb.toString()
        }
    }
}
