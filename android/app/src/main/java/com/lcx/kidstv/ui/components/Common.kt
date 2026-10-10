package com.lcx.kidstv.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lcx.kidstv.ui.AppViewModel
import com.lcx.kidstv.ui.theme.KidsColors

// =====================================================================
//  顶部「今日已看」时长胶囊
// =====================================================================

@Composable
fun TimePillBadge(pill: AppViewModel.TimePill, modifier: Modifier = Modifier) {
    val bg = when {
        pill.locked -> KidsColors.CoralDark
        pill.warn -> KidsColors.YellowDark
        else -> Color.White
    }
    val fg = when {
        pill.locked -> Color.White
        pill.warn -> KidsColors.Gray800
        else -> KidsColors.Gray600
    }
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = bg,
        shadowElevation = 1.dp,
    ) {
        Text(
            text = pill.text,
            color = fg,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp),
        )
    }
}

// =====================================================================
//  萌趣小电视（网页版 .tv-wrapper / .sleep-tv-wrapper）
// =====================================================================

/**
 * 用布局原语拼出来的小电视：天线 + 机身 + 屏幕 + 表情 + 旋钮 + 支脚 + 呼吸投影。
 *
 * @param eyeOpen 眼睛的开合比例（1 = 全开，0.12 = 眨眼）
 * @param sleeping 睡眠模式：闭眼 + 嘴变成小圆（用于「休息时间到啦」遮罩）
 */
@Composable
fun CuteTv(
    modifier: Modifier = Modifier,
    width: Dp = 190.dp,
    eyeOpen: Float = 1f,
    sleeping: Boolean = false,
    showLegs: Boolean = true,
) {
    val bodyWidth = width
    val bodyHeight = width * 0.66f
    val screenHeight = bodyHeight * 0.72f

    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // ---- 天线 ----
        Row(
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.Center,
            modifier = Modifier.height(bodyHeight * 0.22f),
        ) {
            Antenna(rotation = -28f, modifier = Modifier.offset(x = 4.dp))
            Spacer(Modifier.width(width * 0.16f))
            Antenna(rotation = 28f, modifier = Modifier.offset(x = (-4).dp))
        }

        // ---- 机身 ----
        Surface(
            shape = RoundedCornerShape(width * 0.11f),
            color = KidsColors.CoralRed,
            modifier = Modifier
                .width(bodyWidth)
                .height(bodyHeight),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(width * 0.055f),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // 屏幕
                Surface(
                    shape = RoundedCornerShape(width * 0.06f),
                    color = Color.White,
                    modifier = Modifier
                        .weight(1f)
                        .height(screenHeight),
                ) {
                    TvFace(sleeping = sleeping, eyeOpen = eyeOpen)
                }
                Spacer(Modifier.width(width * 0.055f))
                // 侧面板：旋钮 + 扬声器格栅
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                    modifier = Modifier.width(width * 0.1f),
                ) {
                    Knob(size = width * 0.085f, color = KidsColors.SunshineYellow)
                    Spacer(Modifier.height(bodyHeight * 0.1f))
                    Knob(size = width * 0.085f, color = KidsColors.SunshineYellow)
                    Spacer(Modifier.height(bodyHeight * 0.12f))
                    repeat(3) {
                        Box(
                            Modifier
                                .width(width * 0.075f)
                                .height(2.dp)
                                .background(KidsColors.CoralDark, RoundedCornerShape(1.dp))
                        )
                        Spacer(Modifier.height(3.dp))
                    }
                }
            }
        }

        if (showLegs) {
            // ---- 支脚 ----
            Row(
                horizontalArrangement = Arrangement.spacedBy(bodyWidth * 0.34f),
                modifier = Modifier.height(bodyHeight * 0.11f),
            ) {
                repeat(2) {
                    Box(
                        Modifier
                            .width(width * 0.075f)
                            .height(bodyHeight * 0.11f)
                            .background(KidsColors.CoralDark, RoundedCornerShape(bottomStart = 4.dp, bottomEnd = 4.dp))
                    )
                }
            }
        }
    }
}

@Composable
private fun Antenna(rotation: Float, modifier: Modifier = Modifier) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = modifier.rotate(rotation)) {
        Box(
            Modifier
                .size(9.dp)
                .background(KidsColors.CoralDark, CircleShape)
        )
        Box(
            Modifier
                .width(3.dp)
                .height(22.dp)
                .background(KidsColors.CoralDark)
        )
    }
}

@Composable
private fun Knob(size: Dp, color: Color) {
    Box(
        Modifier
            .size(size)
            .background(color, CircleShape)
    )
}

/** 屏幕里的表情：眼睛（可眨眼）+ 腮红 + 嘴巴 */
@Composable
private fun TvFace(sleeping: Boolean, eyeOpen: Float) {
    Row(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Eye(openRatio = if (sleeping) 0.14f else eyeOpen, blushOnLeft = true)
        Eye(openRatio = if (sleeping) 0.14f else eyeOpen, blushOnLeft = false)
    }
}

@Composable
private fun Eye(openRatio: Float, blushOnLeft: Boolean) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(contentAlignment = Alignment.TopEnd) {
            Box(
                Modifier
                    .width(15.dp)
                    .height((15.dp * openRatio).coerceAtLeast(2.dp))
                    .background(KidsColors.Gray800, CircleShape)
            )
            // 眼里的高光
            if (openRatio > 0.5f) {
                Box(
                    Modifier
                        .offset(x = (-2).dp, y = 2.dp)
                        .size(5.dp)
                        .background(Color.White, CircleShape)
                )
            }
        }
    }
}

// =====================================================================
//  三个弹跳小圆点（加载提示）
// =====================================================================

@Composable
fun LoadingDots(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "dots")
    val colors = listOf(KidsColors.CoralRed, KidsColors.MintGreen, KidsColors.SunshineYellow)
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        colors.forEachIndexed { index, color ->
            val offset by transition.animateFloat(
                initialValue = 0f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    animation = tween(durationMillis = 600, delayMillis = index * 140),
                    repeatMode = RepeatMode.Reverse,
                ),
                label = "dot$index",
            )
            Box(
                Modifier
                    .offset(y = (-6).dp * offset)
                    .size(11.dp)
                    .background(color, CircleShape)
            )
        }
    }
}

// =====================================================================
//  其他小件
// =====================================================================

/** 小节上方的浅色小标签，对应网页版 `.section-kicker` */
@Composable
fun SectionKicker(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        color = KidsColors.CoralRed,
        fontSize = 11.5.sp,
        fontWeight = FontWeight.Bold,
        letterSpacing = 1.2.sp,
        modifier = modifier,
    )
}

/** 底部居中吐司（对应网页版 #error-toast） */
@Composable
fun ToastHost(message: String?, onDismiss: () -> Unit) {
    if (message.isNullOrBlank()) return
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
        Surface(
            shape = RoundedCornerShape(50),
            color = KidsColors.Gray900,
            shadowElevation = 6.dp,
            modifier = Modifier
                .padding(bottom = 40.dp)
                .padding(horizontal = 24.dp),
        ) {
            Text(
                text = message,
                color = Color.White,
                fontSize = 14.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 22.dp, vertical = 12.dp),
            )
        }
    }
}

/** 空状态提示（对应网页版 .empty-state） */
@Composable
fun EmptyState(title: String, description: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(title, style = MaterialTheme.typography.titleLarge, color = KidsColors.Gray800)
        Spacer(Modifier.height(8.dp))
        Text(description, style = MaterialTheme.typography.bodyMedium, color = KidsColors.Gray600)
    }
}

/** 细进度条（视频卡片上的观看进度 / 限时用量条） */
@Composable
fun ProgressLine(
    fraction: Float,
    modifier: Modifier = Modifier,
    color: Color = KidsColors.CoralRed,
    track: Color = KidsColors.Gray200,
    height: Dp = 5.dp,
) {
    Box(
        modifier
            .height(height)
            .clip(RoundedCornerShape(50))
            .background(track)
    ) {
        Canvas(Modifier.fillMaxSize()) {
            drawRoundRect(
                color = color,
                size = Size(size.width * fraction.coerceIn(0f, 1f), size.height),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.height / 2f),
            )
        }
    }
}

/** 睡眠小电视的「z z Z」飘字 */
@Composable
fun SleepZzz(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "zzz")
    Row(modifier = modifier, verticalAlignment = Alignment.Bottom) {
        listOf("z", "z", "Z").forEachIndexed { index, ch ->
            val progress by transition.animateFloat(
                initialValue = 0f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    animation = tween(2200, delayMillis = index * 350),
                    repeatMode = RepeatMode.Restart,
                ),
                label = "z$index",
            )
            Text(
                text = ch,
                color = KidsColors.MintDark,
                fontSize = (14 + index * 5).sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.offset(y = (-18).dp * progress),
            )
            Spacer(Modifier.width(4.dp))
        }
    }
}

/** 一条竖直虚线（分隔用，避免依赖 divider 组件） */
@Composable
fun ThinDivider(color: Color = KidsColors.Gray200, modifier: Modifier = Modifier) {
    Canvas(modifier.fillMaxSize()) {
        drawLine(
            color = color,
            start = Offset(size.width / 2, 0f),
            end = Offset(size.width / 2, size.height),
            strokeWidth = size.width,
            cap = StrokeCap.Butt,
        )
    }
}

/** 描边圆（供内部绘图复用） */
internal fun androidx.compose.ui.graphics.drawscope.DrawScope.strokeCircle(
    color: Color,
    radius: Float,
    strokeWidth: Float,
) = drawCircle(color = color, radius = radius, style = Stroke(width = strokeWidth))
