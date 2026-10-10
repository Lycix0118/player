package com.lcx.kidstv.ui.screens

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.keyframes
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lcx.kidstv.ui.components.CuteTv
import com.lcx.kidstv.ui.components.LoadingDots
import com.lcx.kidstv.ui.theme.KidsColors

/**
 * 启动加载页：萌趣小电视（会眨眼、轻微上下浮动）+「正在准备精彩视频」+ 三色弹跳圆点。
 * 对应网页版 `#loading`。
 */
@Composable
fun LoadingScreen() {
    val transition = rememberInfiniteTransition(label = "loading")

    // 每 3.4 秒眨一次眼
    val eyeOpen by transition.animateFloat(
        initialValue = 1f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = keyframes {
                durationMillis = 3400
                1f at 0 using LinearEasing
                1f at 2950 using LinearEasing
                0.12f at 3080 using LinearEasing
                1f at 3210 using LinearEasing
                1f at 3400 using LinearEasing
            },
            repeatMode = RepeatMode.Restart,
        ),
        label = "blink",
    )

    // 轻微的上下浮动
    val bob by transition.animateFloat(
        initialValue = 0f,
        targetValue = -9f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1700),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "bob",
    )

    Box(
        Modifier
            .fillMaxSize()
            .background(KidsColors.Gray50),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CuteTv(
                width = 200.dp,
                eyeOpen = eyeOpen,
                modifier = Modifier
                    .offset(y = bob.dp)
                    .alpha(1f),
            )
            Spacer(Modifier.height(34.dp))
            Text(
                text = "正在准备精彩视频",
                color = KidsColors.Gray800,
                fontSize = 19.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(16.dp))
            LoadingDots()
        }
    }
}
