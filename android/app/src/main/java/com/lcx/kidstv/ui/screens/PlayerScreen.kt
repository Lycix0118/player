package com.lcx.kidstv.ui.screens

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import com.lcx.kidstv.ui.AppViewModel
import com.lcx.kidstv.ui.components.CuteTv
import com.lcx.kidstv.ui.components.ProgressLine
import com.lcx.kidstv.ui.components.SleepZzz
import com.lcx.kidstv.ui.components.TimePillBadge
import com.lcx.kidstv.ui.theme.KidsColors

/**
 * 播放页，对应网页版 `#player-screen`（`.player-screen-cinema`）。
 * 视频区锁 16:9、黑底、白色描边 + 柔和弥散阴影；上面叠加载遮罩 / 预警气泡 / 到期锁屏。
 */
@Composable
fun PlayerScreen(vm: AppViewModel) {
    val episode = vm.currentEpisode
    val exo = vm.player

    // 全屏时沉浸式隐藏系统状态栏与导航栏
    val context = LocalContext.current
    DisposableEffect(vm.isFullscreen) {
        val window = (context as? Activity)?.window
        if (window != null) {
            val insetsController = WindowCompat.getInsetsController(window, window.decorView)
            if (vm.isFullscreen) {
                insetsController.hide(WindowInsetsCompat.Type.systemBars())
                insetsController.systemBarsBehavior =
                    WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            } else {
                insetsController.show(WindowInsetsCompat.Type.systemBars())
            }
        }
        onDispose {
            val window = (context as? Activity)?.window
            if (window != null) {
                val insetsController = WindowCompat.getInsetsController(window, window.decorView)
                insetsController.show(WindowInsetsCompat.Type.systemBars())
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
    ) {
        // 非全屏时显示顶部导航栏
        if (!vm.isFullscreen) {
            PlayerHeader(vm, episode?.displayIndex ?: 0, episode?.title.orEmpty())
        }

        // 视频播放核心区域：自适应撑满剩余空间，完全黑底影院模式
        Box(
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .background(Color.Black),
            contentAlignment = Alignment.Center,
        ) {
            if (exo != null) {
                AndroidView(
                    factory = { ctx ->
                        PlayerView(ctx).apply {
                            useController = true
                            controllerAutoShow = true
                            keepScreenOn = true
                            setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING)
                            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                            setBackgroundColor(android.graphics.Color.BLACK)
                            player = exo
                            setFullscreenButtonClickListener {
                                vm.toggleFullscreen()
                            }
                        }
                    },
                    update = {
                        it.player = exo
                        it.setFullscreenButtonClickListener { vm.toggleFullscreen() }
                    },
                    onRelease = { it.player = null },
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                CenteredHint("正在准备播放…", Modifier.fillMaxSize())
            }

            // 全屏模式下浮动的半透明退出全屏按钮
            if (vm.isFullscreen) {
                Surface(
                    shape = RoundedCornerShape(50),
                    color = KidsColors.Gray900.copy(alpha = 0.65f),
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(start = 16.dp, top = 16.dp)
                        .clickable { vm.exitFullscreen() },
                ) {
                    Row(
                        Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("‹", fontSize = 20.sp, color = Color.White, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.padding(horizontal = 2.dp))
                        Text("退出全屏", fontSize = 13.sp, color = Color.White, fontWeight = FontWeight.SemiBold)
                    }
                }
            }

            // ---- 播放失败错误覆盖层 ----
            if (vm.playerError != null && !vm.preparing) {
                PlayerErrorOverlay(
                    message = vm.playerError ?: "播放出错",
                    onRetry = { vm.retryPlayback() },
                    onBack = { vm.backToVideos() },
                )
            }

            // ---- 准备中遮罩 ----
            if (vm.preparing) {
                PreparingOverlay(vm.preparePercent, vm.prepareStage)
            }

            // ---- 临界预警气泡（3 分钟 / 1 分钟）----
            vm.timeNotice?.let { notice ->
                Surface(
                    shape = RoundedCornerShape(50),
                    color = if (notice.startsWith("⏰")) KidsColors.CoralRed else KidsColors.Gray900,
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(top = 16.dp)
                        .clickable { vm.dismissTimeNotice() },
                ) {
                    Text(
                        notice,
                        color = Color.White,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
                    )
                }
            }

            // ---- 到期锁屏 ----
            vm.lockReason?.let { reason ->
                LockOverlay(
                    vm = vm,
                    isGlobal = reason == "global" || vm.limits?.globalIsLocked == true,
                )
            }
        }
    }
}

@Composable
private fun PlayerHeader(vm: AppViewModel, index: Int, title: String) {
    val hasPrev = vm.hasRelativeEpisode(-1)
    val hasNext = vm.hasRelativeEpisode(1)

    Row(
        Modifier
            .fillMaxWidth()
            .background(KidsColors.White)
            .padding(horizontal = 20.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // 返回
        Row(
            Modifier
                .clip(RoundedCornerShape(8.dp))
                .clickable { vm.backToVideos() }
                .padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("‹", fontSize = 24.sp, color = KidsColors.CoralRed, fontWeight = FontWeight.Bold)
            Spacer(Modifier.padding(horizontal = 3.dp))
            Text("返回", fontSize = 15.sp, color = KidsColors.CoralRed, fontWeight = FontWeight.SemiBold)
        }

        Spacer(Modifier.padding(horizontal = 6.dp))

        // 上一集 / 下一集
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            NavPill("上一集", enabled = hasPrev) { vm.playRelative(-1) }
            NavPill("下一集", enabled = hasNext) { vm.playRelative(1) }
        }

        Spacer(Modifier.padding(horizontal = 10.dp))

        // 集数徽章 + 标题
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
            Surface(
                shape = RoundedCornerShape(50),
                color = Color.Transparent,
                modifier = Modifier.background(
                    Brush.linearGradient(listOf(KidsColors.CoralRed, KidsColors.CoralLight)),
                    RoundedCornerShape(50),
                ),
            ) {
                Text(
                    "第 $index 集",
                    color = Color.White,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                )
            }
            Spacer(Modifier.padding(horizontal = 6.dp))
            Text(
                title.ifBlank { "正在准备播放…" },
                style = MaterialTheme.typography.titleLarge,
                color = KidsColors.Gray800,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }

        Spacer(Modifier.padding(horizontal = 4.dp))

        TimePillBadge(vm.timePill())
    }
}

@Composable
private fun NavPill(label: String, enabled: Boolean = true, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = if (enabled) KidsColors.Gray100 else KidsColors.Gray100.copy(alpha = 0.45f),
        modifier = if (enabled) Modifier.clickable(onClick = onClick) else Modifier,
    ) {
        Text(
            label,
            color = if (enabled) KidsColors.Gray800 else KidsColors.Gray600.copy(alpha = 0.4f),
            fontSize = 13.5.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
        )
    }
}

@Composable
private fun PlayerErrorOverlay(
    message: String,
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.88f)),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = Color.White,
            shadowElevation = 8.dp,
            modifier = Modifier
                .padding(24.dp)
                .widthIn(max = 440.dp),
        ) {
            Column(
                Modifier.padding(horizontal = 32.dp, vertical = 26.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("⚠️", fontSize = 36.sp)
                Spacer(Modifier.height(12.dp))
                Text(
                    "播放遇到问题",
                    style = MaterialTheme.typography.titleLarge,
                    color = KidsColors.Gray900,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = KidsColors.Gray600,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(20.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(
                        onClick = onRetry,
                        colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    ) {
                        Text("重试播放")
                    }
                    Button(
                        onClick = onBack,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = KidsColors.Gray100,
                            contentColor = KidsColors.Gray800,
                        ),
                    ) {
                        Text("返回列表")
                    }
                }
            }
        }
    }
}

/** 准备播放遮罩：白卡片 + 珊瑚描边 + 转圈 + 进度条（对应 .player-loader-overlay / .loader-card） */
@Composable
private fun PreparingOverlay(percent: Int, stage: String) {
    Box(
        Modifier
            .fillMaxSize()
            .background(KidsColors.Gray50.copy(alpha = 0.88f)),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = KidsColors.White,
            border = androidx.compose.foundation.BorderStroke(2.dp, KidsColors.CoralLight),
            shadowElevation = 10.dp,
            modifier = Modifier.widthIn(max = 440.dp),
        ) {
            Column(
                Modifier.padding(horizontal = 40.dp, vertical = 28.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                CircularProgressIndicator(color = KidsColors.CoralRed)
                Spacer(Modifier.height(18.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "正在连接高清视频流…",
                        style = MaterialTheme.typography.titleMedium,
                        color = KidsColors.Gray800,
                    )
                    Spacer(Modifier.padding(horizontal = 8.dp))
                    Text("$percent%", color = KidsColors.CoralRed, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.height(12.dp))
                ProgressLine(fraction = percent / 100f, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(10.dp))
                Text(stage, style = MaterialTheme.typography.bodyMedium, color = KidsColors.Gray600)
            }
        }
    }
}

/** 到期锁屏：打呼噜的小电视 + 文案 + 去休息 / 家长加时 */
@Composable
private fun LockOverlay(vm: AppViewModel, isGlobal: Boolean) {
    val title = if (isGlobal) "今日观看总时间到啦 🌙" else "今日休息时间到啦 🌙"
    val desc = if (isGlobal) {
        "今天所有视频的观看时间都用完啦。\n让眼睛好好睡一觉，明天再来探索新世界吧！✨"
    } else {
        "这个合集今天的观看时间已经用完啦。\n小电视要睡觉啦，明天我们再一起看！✨"
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(KidsColors.Gray50.copy(alpha = 0.97f)),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box {
                CuteTv(width = 150.dp, sleeping = true, showLegs = false)
                SleepZzz(
                    Modifier
                        .align(Alignment.TopEnd)
                        .padding(end = 4.dp)
                )
            }
            Spacer(Modifier.height(24.dp))
            Text(title, style = MaterialTheme.typography.headlineMedium, color = KidsColors.Gray900)
            Spacer(Modifier.height(10.dp))
            Text(
                desc,
                style = MaterialTheme.typography.bodyLarge,
                color = KidsColors.Gray600,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(24.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(
                    onClick = {
                        vm.dismissLock()
                        vm.backToFolders()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    modifier = Modifier.widthIn(min = 150.dp),
                ) { Text("好的，去休息") }
                Button(
                    onClick = { vm.requestParentAccess { vm.openExtendDialog() } },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = KidsColors.Gray100,
                        contentColor = KidsColors.Gray800,
                    ),
                    modifier = Modifier.widthIn(min = 130.dp),
                ) { Text("家长加时") }
            }
        }
    }
}
