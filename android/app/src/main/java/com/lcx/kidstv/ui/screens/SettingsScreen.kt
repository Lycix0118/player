package com.lcx.kidstv.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lcx.kidstv.ui.AppViewModel
import com.lcx.kidstv.ui.components.AppHeader
import com.lcx.kidstv.ui.components.ProgressLine
import com.lcx.kidstv.ui.components.SectionKicker
import com.lcx.kidstv.ui.theme.KidsColors
import kotlin.math.min

/**
 * 家长区，对应网页版 `#settings-screen`。
 *
 * 比网页版多一项「服务器地址」——安卓端不像网页由同一 origin 提供页面，
 * 必须显式告诉它后端在哪（模拟器 10.0.2.2，平板走局域网 IP）。
 */
@Composable
fun SettingsScreen(vm: AppViewModel) {
    var cookieInput by remember { mutableStateOf("") }
    var cookieVisible by remember { mutableStateOf(false) }
    var serverInput by remember { mutableStateOf(vm.serverUrl) }

    var tlEnabled by remember { mutableStateOf(false) }
    var globalLimit by remember { mutableStateOf(0) }
    var pinInput by remember { mutableStateOf("") }
    val folderLimits = remember { mutableStateMapOf<String, Int>() }
    var initialized by remember { mutableStateOf(false) }

    LaunchedEffect(vm.limits) {
        val limits = vm.limits ?: return@LaunchedEffect
        if (!initialized) {
            tlEnabled = limits.enabled
            globalLimit = limits.globalLimitMinutes
            initialized = true
        }
        limits.folders.forEach { folder ->
            if (!folderLimits.containsKey(folder.path)) folderLimits[folder.path] = folder.limitMinutes
        }
    }

    Column(Modifier.fillMaxSize()) {
        AppHeader(
            title = "🔒 家长区",
            onBack = vm::backToFolders,
        )

        // 注意：imePadding 必须放在 verticalScroll 之后（即滚动内容内部），只给内容补一段底部留白，
        // 这样键盘弹出时「保存限时设置 / 重置今日计时」能被滚上来。
        // 反过来放在外层 Column 上会去压缩 viewport，实测会把 AppHeader 压成 0 高。
        Column(
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(horizontal = 20.dp, vertical = 18.dp),
        ) {
            // ---- 顶部说明（对应 .parent-zone-intro）----
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = KidsColors.White,
                shadowElevation = 1.dp,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("🔒", fontSize = 34.sp)
                    Spacer(Modifier.width(16.dp))
                    Column {
                        SectionKicker("家长管理")
                        Text(
                            "为孩子准备一个安心的播放环境",
                            style = MaterialTheme.typography.titleLarge,
                            color = KidsColors.Gray900,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "账号连接、播放习惯和缓存管理都在这里调整。设置统一保存在服务端，" +
                                "所有设备自动保持一致并立即生效。",
                            style = MaterialTheme.typography.bodyMedium,
                            color = KidsColors.Gray600,
                        )
                    }
                }
            }

            Spacer(Modifier.height(22.dp))

            // ---- 服务器地址（安卓端特有）----
            SectionHeading("服务器连接", "播放器需要知道后端跑在哪")
            SettingsCard {
                OutlinedTextField(
                    value = serverInput,
                    onValueChange = { serverInput = it },
                    singleLine = true,
                    label = { Text("后端地址") },
                    supportingText = {
                        Text(
                            "模拟器用 http://10.0.2.2:8000；平板用 http://<电脑局域网IP>:8000",
                            fontSize = 11.5.sp,
                            color = KidsColors.Gray600,
                        )
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    Button(
                        onClick = { vm.updateServerUrl(serverInput) { } },
                        colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    ) { Text("连接并刷新") }
                }
            }

            Spacer(Modifier.height(22.dp))

            // ---- 账号与内容 ----
            SectionHeading("账号与内容", "用于解锁高清画质和字幕")
            SettingsCard {
                Text("B站 Cookie", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                Spacer(Modifier.height(4.dp))
                Text(
                    "粘贴浏览器中 bilibili.com 的完整 Cookie。Cookie 仅用于本播放器访问 B站接口。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KidsColors.Gray600,
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = cookieInput,
                    onValueChange = { cookieInput = it },
                    label = { Text("SESSDATA=...; bili_jct=...;") },
                    minLines = 3,
                    maxLines = 5,
                    visualTransformation = if (cookieVisible) VisualTransformation.None
                    else PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        if (vm.cookieConfigured) "已配置 Cookie" else "尚未配置",
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (vm.cookieConfigured) KidsColors.MintDark else KidsColors.Gray600,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = { cookieVisible = !cookieVisible }) {
                        Text(if (cookieVisible) "隐藏" else "显示")
                    }
                    Spacer(Modifier.width(6.dp))
                    Button(
                        onClick = { vm.saveCookie(cookieInput); cookieInput = "" },
                        colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    ) { Text("保存 Cookie") }
                }
            }

            Spacer(Modifier.height(22.dp))

            // ---- 播放习惯 ----
            SectionHeading("播放习惯", "保存后立即生效")
            SettingsCard {
                SwitchRow(
                    title = "自动播放",
                    subtitle = "进入视频页面后自动开始播放",
                    checked = vm.settings.autoplay,
                    onCheckedChange = vm::setAutoplay,
                )
                Spacer(Modifier.height(10.dp))
                SwitchRow(
                    title = "默认开启字幕",
                    subtitle = "视频有字幕时自动显示",
                    checked = vm.settings.subtitles,
                    onCheckedChange = vm::setSubtitles,
                )
            }

            Spacer(Modifier.height(22.dp))

            // ---- 观看限时 ----
            SectionHeading("⏱️ 观看限时管理", "保护视力，支持合集单项及全局总限时")
            SettingsCard {
                SwitchRow(
                    title = "开启观看限时",
                    subtitle = "启用后将严格按下方策略管控播放，到期自动休息",
                    checked = tlEnabled,
                    onCheckedChange = { tlEnabled = it },
                )

                Spacer(Modifier.height(16.dp))
                Text("🌍 全局每日总限时", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                Spacer(Modifier.height(2.dp))
                Text(
                    "所有视频共享的今日累计播放时长上限",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KidsColors.Gray600,
                )
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = if (globalLimit == 0) "" else globalLimit.toString(),
                        onValueChange = { globalLimit = it.filter { c -> c.isDigit() }.take(3).toIntOrNull() ?: 0 },
                        singleLine = true,
                        label = { Text("分钟（0 = 不限制）") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.width(200.dp),
                    )
                    Spacer(Modifier.width(14.dp))
                    vm.limits?.let { status ->
                        val usedMin = status.totalUsedSeconds / 60
                        Text(
                            if (status.globalLimitMinutes > 0)
                                "今日已看: $usedMin / ${status.effectiveGlobalLimitMinutes} 分钟"
                            else
                                "今日已看: $usedMin 分钟（不限时）",
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (status.globalIsLocked) KidsColors.CoralDark else KidsColors.Gray600,
                        )
                    }
                }

                Spacer(Modifier.height(20.dp))
                Text("📁 各底层合集每日独立限时", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                Spacer(Modifier.height(2.dp))
                Text(
                    "单独限制特定动画或合集的每日时长（不设则不限）",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KidsColors.Gray600,
                )
                Spacer(Modifier.height(10.dp))

                val folders = vm.limits?.folders.orEmpty()
                if (folders.isEmpty()) {
                    Text("暂无底层视频合集", style = MaterialTheme.typography.bodyMedium, color = KidsColors.Gray600)
                } else {
                    folders.forEach { folder ->
                        val usedMin = folder.usedSeconds / 60
                        val effMin = if (folder.effectiveLimitMinutes > 0) folder.effectiveLimitMinutes else folder.limitMinutes
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "📁 ${folder.name}",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = KidsColors.Gray800,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Text(
                                    if (effMin > 0) "今日已看 $usedMin / $effMin 分钟" else "今日已看 $usedMin 分钟",
                                    style = MaterialTheme.typography.labelMedium,
                                    color = KidsColors.Gray600,
                                )
                                if (effMin > 0) {
                                    Spacer(Modifier.height(6.dp))
                                    ProgressLine(
                                        fraction = min(1f, folder.usedSeconds.toFloat() / (effMin * 60f)),
                                        color = if (folder.isLocked) KidsColors.CoralDark else KidsColors.CoralRed,
                                        modifier = Modifier.width(180.dp),
                                    )
                                }
                            }
                            OutlinedTextField(
                                value = (folderLimits[folder.path] ?: 0).let { if (it == 0) "" else it.toString() },
                                onValueChange = { input ->
                                    folderLimits[folder.path] =
                                        input.filter { c -> c.isDigit() }.take(3).toIntOrNull() ?: 0
                                },
                                singleLine = true,
                                label = { Text("限时(分)") },
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                modifier = Modifier.width(140.dp),
                            )
                        }
                    }
                }

                Spacer(Modifier.height(20.dp))
                Text("🔐 家长验证方式", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                Spacer(Modifier.height(2.dp))
                Text(
                    if (vm.limits?.hasParentPin == true) "已设置 4 位 PIN" else "当前使用趣味算术题验证",
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (vm.limits?.hasParentPin == true) KidsColors.MintDark else KidsColors.Gray600,
                )
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = pinInput,
                        onValueChange = { pinInput = it.filter { c -> c.isDigit() }.take(4) },
                        singleLine = true,
                        label = { Text("设置 4 位数字密码") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        modifier = Modifier.width(220.dp),
                    )
                    Spacer(Modifier.width(12.dp))
                    Button(
                        onClick = {
                            // 必须把本地正在编辑的限时值一起带上：只传 PIN 会让服务端用旧值覆盖未保存的改动
                            if (!Regex("^\\d{4}$").matches(pinInput)) {
                                vm.showToast("PIN 密码必须为 4 位数字")
                            } else {
                                vm.saveTimeLimitsConfig(
                                    enabled = tlEnabled,
                                    globalLimitMinutes = globalLimit,
                                    folderLimits = folderLimits.toMap(),
                                    parentPin = pinInput,
                                )
                                pinInput = ""
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    ) { Text("设置密码") }
                    if (vm.limits?.hasParentPin == true) {
                        Spacer(Modifier.width(8.dp))
                        TextButton(
                            onClick = {
                                vm.saveTimeLimitsConfig(
                                    enabled = tlEnabled,
                                    globalLimitMinutes = globalLimit,
                                    folderLimits = folderLimits.toMap(),
                                    parentPin = "",
                                )
                            },
                        ) { Text("清除密码") }
                    }
                }

                Spacer(Modifier.height(20.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = vm::resetTodayUsage) {
                        Text("重置今日计时", color = KidsColors.CoralDark)
                    }
                    Spacer(Modifier.width(10.dp))
                    Button(
                        onClick = {
                            vm.saveTimeLimitsConfig(
                                enabled = tlEnabled,
                                globalLimitMinutes = globalLimit,
                                folderLimits = folderLimits.toMap(),
                            )
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    ) { Text("保存限时设置") }
                }
            }

            Spacer(Modifier.height(22.dp))

            // ---- 显示偏好 ----
            SectionHeading("显示偏好", "选择孩子更容易使用的界面")
            SettingsCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("配色主题", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                    Spacer(Modifier.weight(1f))
                    Text("糖果电视（当前）", style = MaterialTheme.typography.bodyMedium, color = KidsColors.Gray600)
                }
            }

            Spacer(Modifier.height(22.dp))

            // ---- 存储管理 ----
            SectionHeading(
                "存储管理",
                vm.cacheStatus?.let { "当前缓存 ${it.currentCacheSizeMb} MB · ${it.cachedVideosCount} 个文件" }
                    ?: "正在读取缓存状态…",
            )
            SettingsCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("清理视频缓存", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                        Text(
                            "不会删除 videos 文件夹中的原始视频",
                            style = MaterialTheme.typography.bodyMedium,
                            color = KidsColors.Gray600,
                        )
                    }
                    TextButton(onClick = vm::cleanCache) { Text("清理缓存") }
                }
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("关于播放器", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                        Text(
                            "儿童视频播放器 · 简单、安全、好用",
                            style = MaterialTheme.typography.bodyMedium,
                            color = KidsColors.Gray600,
                        )
                    }
                    Text(
                        "v${vm.appVersionName}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = KidsColors.Gray600,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("应用版本与更新", style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
                        Text(
                            if (vm.isCheckingUpdate) "正在从服务器检查最新版本…"
                            else if (vm.isDownloadingUpdate) "正在下载更新 (${vm.updateDownloadProgress}%)…"
                            else "版本号：v${vm.appVersionName}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = KidsColors.Gray600,
                        )
                    }
                    Button(
                        onClick = { vm.checkAppUpdate(silent = false) },
                        enabled = !vm.isCheckingUpdate && !vm.isDownloadingUpdate,
                        colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    ) {
                        Text(if (vm.isCheckingUpdate) "检查中…" else "检查更新")
                    }
                }
            }

            Spacer(Modifier.height(40.dp))
        }
    }
}

@Composable
private fun SectionHeading(title: String, hint: String? = null) {
    Row(Modifier.fillMaxWidth().padding(bottom = 8.dp), verticalAlignment = Alignment.Bottom) {
        Text(title, style = MaterialTheme.typography.titleLarge, color = KidsColors.Gray900)
        Spacer(Modifier.weight(1f))
        if (hint != null) {
            Text(hint, style = MaterialTheme.typography.labelMedium, color = KidsColors.Gray600)
        }
    }
}

@Composable
private fun SettingsCard(content: @Composable ColumnScope.() -> Unit) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = KidsColors.White,
        shadowElevation = 1.dp,
        modifier = Modifier
            .fillMaxWidth()
            .widthIn(max = 1180.dp),
    ) {
        Column(Modifier.padding(18.dp), content = content)
    }
}

@Composable
private fun SwitchRow(
    title: String,
    subtitle: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = KidsColors.Gray900)
            Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = KidsColors.Gray600)
        }
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = Color.White,
                checkedTrackColor = KidsColors.CoralRed,
            ),
        )
    }
}

/** 供设置页复用的空白占位（无内容时不至于突兀） */
@Composable
private fun Blank() {
    Box(Modifier.background(Color.Transparent))
}
