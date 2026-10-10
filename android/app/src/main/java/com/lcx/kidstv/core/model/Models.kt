package com.lcx.kidstv.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient

/**
 * 与后端 JSON 严格对齐的数据模型。
 *
 * 后端来源：`backend/main.py` 的 31 个路由 + `backend/time_limits.py`。
 * 所有字段都给了默认值，配合 `ignoreUnknownKeys = true`，
 * 后端加字段时客户端不会崩（只会忽略）。
 */

/** `GET /api/folders?path=` 的元素 */
@Serializable
data class FolderInfo(
    val name: String = "",
    val path: String = "",
    @SerialName("parent_path") val parentPath: String? = null,
    @SerialName("has_list_file") val hasListFile: Boolean = false,
    @SerialName("video_count") val videoCount: Int = 0,
    @SerialName("downloaded_count") val downloadedCount: Int = 0,
    val depth: Int = 0,
)

/**
 * `GET /api/folders/{path}` 的元素（一集/一个视频）。
 *
 * 注意 B站 与 silidm 两种来源共用这个结构：
 * - B站：`bvid` 是真实 BV 号，`source = "bilibili"`
 * - silidm：`bvid` 实际是合成 ID（`silidm_<vod>-<sid>-<nid>`），`source = "silidm"`
 */
@Serializable
data class Episode(
    val index: Int = 0,
    val title: String = "",
    val page: Int = 1,
    val bvid: String = "",
    val cid: Long = 0,
    val duration: Int = 0,
    @SerialName("cover_url") val coverUrl: String = "",
    @SerialName("cover_source") val coverSource: String = "",
    /** 列表接口对 B站 条目返回 null（未探测），详情接口才给真正的布尔值 */
    @SerialName("has_subtitle") val hasSubtitle: Boolean? = null,
    val source: String = "bilibili",
    val url: String = "",
    @SerialName("episode_title") val episodeTitle: String = "",
    @SerialName("series_title") val seriesTitle: String = "",
) {
    /** 客户端本地附加：所属合集路径（服务端不返回，避免每条都塞一遍） */
    @Transient
    var folderPath: String = ""

    /** 客户端本地附加：观看进度 */
    @Transient
    var progress: WatchProgress? = null

    /** 展示用集号：优先用服务端 index，缺失时退回 page */
    val displayIndex: Int get() = if (index > 0) index else page

    val isStreamSource: Boolean get() = source != "bilibili"
}

/** `GET/POST /api/progress/{path}` 的值；key 为 `<folder>|<bvid>|<page>` */
@Serializable
data class WatchProgress(
    val position: Double = 0.0,
    val duration: Double = 0.0,
    val completed: Boolean = false,
    @SerialName("updated_at") val updatedAt: Double = 0.0,
) {
    /** 观看百分比（0~100），与网页版一致：分母至少为 1 防止除零 */
    val percent: Int
        get() = if (duration > 0) minOf(100, (position / duration * 100).toInt()) else 0
}

/** `POST /api/download/{folder}/{index}` 与 `GET /api/download/tasks/{id}` 的返回 */
@Serializable
data class DownloadTask(
    @SerialName("task_id") val taskId: String? = null,
    val status: String = "",
    val progress: Int = 0,
    val stage: String = "",
    @SerialName("video_url") val videoUrl: String = "",
    /** true = 走 HLS 流式（silidm），false 或缺省 = 走 /static 下的 mp4（B站） */
    val stream: Boolean = false,
    val error: String? = null,
)

/** `GET/POST /api/settings`（服务端默认值见 backend/settings.py） */
@Serializable
data class AppSettings(
    val autoplay: Boolean = false,
    val subtitles: Boolean = true,
    val theme: String = "candy",
    @SerialName("has_cookie") val hasCookie: Boolean = false,
)

/** `POST /api/time-limits/heartbeat` 的返回 */
@Serializable
data class HeartbeatResult(
    val status: String = "ok",
    @SerialName("should_lock") val shouldLock: Boolean = false,
    @SerialName("lock_reason") val lockReason: String? = null,
    @SerialName("folder_path") val folderPath: String = "",
    @SerialName("delta_seconds") val deltaSeconds: Double = 0.0,
    @SerialName("remaining_seconds") val remainingSeconds: Int? = null,
    @SerialName("global_remaining_seconds") val globalRemainingSeconds: Int? = null,
    val date: String = "",
)

/** 限时状态里的单个合集条目 */
@Serializable
data class TimeLimitFolder(
    val name: String = "",
    val path: String = "",
    @SerialName("limit_minutes") val limitMinutes: Int = 0,
    @SerialName("bonus_minutes") val bonusMinutes: Int = 0,
    @SerialName("effective_limit_minutes") val effectiveLimitMinutes: Int = 0,
    @SerialName("used_seconds") val usedSeconds: Int = 0,
    /** null = 不限制 */
    @SerialName("remaining_seconds") val remainingSeconds: Int? = null,
    @SerialName("self_locked") val selfLocked: Boolean = false,
    @SerialName("is_locked") val isLocked: Boolean = false,
)

/** `GET /api/time-limits/status`（返回结构见 backend/time_limits.py:get_time_limits_status） */
@Serializable
data class TimeLimitsStatus(
    val date: String = "",
    @SerialName("yesterday_date") val yesterdayDate: String = "",
    @SerialName("yesterday_used_seconds") val yesterdayUsedSeconds: Int = 0,
    val enabled: Boolean = false,
    @SerialName("has_parent_pin") val hasParentPin: Boolean = false,
    @SerialName("global_limit_minutes") val globalLimitMinutes: Int = 0,
    @SerialName("bonus_global_minutes") val bonusGlobalMinutes: Int = 0,
    @SerialName("effective_global_limit_minutes") val effectiveGlobalLimitMinutes: Int = 0,
    @SerialName("total_used_seconds") val totalUsedSeconds: Int = 0,
    @SerialName("global_remaining_seconds") val globalRemainingSeconds: Int? = null,
    @SerialName("global_is_locked") val globalIsLocked: Boolean = false,
    val folders: List<TimeLimitFolder> = emptyList(),
)

/** `POST /api/time-limits/extend` 的返回 */
@Serializable
data class ExtendResult(
    val result: ExtendResultBody? = null,
    val status: TimeLimitsStatus = TimeLimitsStatus(),
)

@Serializable
data class ExtendResultBody(
    val success: Boolean = false,
    val type: String = "",
    @SerialName("folder_path") val folderPath: String = "",
    @SerialName("added_minutes") val addedMinutes: Int = 0,
    val date: String = "",
)

/** `GET /api/batch/covers/{bvid}?pages=` */
@Serializable
data class CoverBatch(
    val covers: Map<String, String> = emptyMap(),
)

/** `GET /api/cache/status` */
@Serializable
data class CacheStatus(
    @SerialName("max_cache_size_mb") val maxCacheSizeMb: Double = 0.0,
    @SerialName("target_cache_size_mb") val targetCacheSizeMb: Double = 0.0,
    @SerialName("min_free_disk_mb") val minFreeDiskMb: Double = 0.0,
    @SerialName("current_cache_size_mb") val currentCacheSizeMb: Double = 0.0,
    @SerialName("free_disk_space_mb") val freeDiskSpaceMb: Double = 0.0,
    @SerialName("cached_videos_count") val cachedVideosCount: Int = 0,
)

/** `POST /api/time-limits/verify-pin` */
@Serializable
data class PinVerifyResult(val valid: Boolean = false)

/** `GET /api/settings/cookie/status` */
@Serializable
data class CookieStatus(@SerialName("has_cookie") val hasCookie: Boolean = false)

/** `GET /api/subtitle/{folder}/{index}` —— 只有 B站 条目才有字幕 */
@Serializable
data class SubtitleResponse(
    @SerialName("subtitle_url") val subtitleUrl: String = "",
)

/** `GET /api/app/version` */
@Serializable
data class AppUpdateInfo(
    @SerialName("version_code") val versionCode: Int = 1,
    @SerialName("version_name") val versionName: String = "1.0",
    @SerialName("min_version_code") val minVersionCode: Int = 1,
    @SerialName("download_url") val downloadUrl: String = "",
    @SerialName("file_name") val fileName: String = "app-release.apk",
    @SerialName("file_size") val fileSize: Long = 0L,
    @SerialName("release_date") val releaseDate: String = "",
    val changelog: String = "",
) {
    val fileSizeFormatted: String
        get() {
            if (fileSize <= 0) return ""
            val mb = fileSize / (1024.0 * 1024.0)
            return String.format(java.util.Locale.US, "%.1f MB", mb)
        }
}
