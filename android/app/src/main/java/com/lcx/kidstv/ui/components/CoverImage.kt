package com.lcx.kidstv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.sp
import coil.compose.SubcomposeAsyncImage
import com.lcx.kidstv.ui.theme.KidsColors

/**
 * 视频封面：主地址失败自动退到兜底地址（对应网页版 `<img onerror>` 的两级回退），
 * 再失败就显示占位图标。
 */
@Composable
fun CoverImage(
    primary: String,
    fallback: String,
    modifier: Modifier = Modifier,
) {
    var useFallback by remember(primary, fallback) { mutableStateOf(false) }
    val model = if (useFallback) fallback else primary

    if (model.isBlank()) {
        CoverPlaceholder(modifier)
        return
    }

    SubcomposeAsyncImage(
        model = model,
        contentDescription = null,
        contentScale = ContentScale.Crop,
        modifier = modifier,
        loading = { Box(Modifier.fillMaxSize()) },
        error = {
            if (!useFallback && fallback.isNotBlank()) {
                LaunchedEffect(Unit) { useFallback = true }
                Box(Modifier.fillMaxSize())
            } else {
                CoverPlaceholder(Modifier.fillMaxSize())
            }
        },
    )
}

/** 封面占位：珊瑚红→薄荷绿渐变 + 胶片图标（与网页版 .video-thumbnail 背景一致） */
@Composable
fun CoverPlaceholder(modifier: Modifier = Modifier) {
    Box(
        modifier.background(
            Brush.linearGradient(listOf(KidsColors.CoralRed, KidsColors.MintGreen))
        ),
        contentAlignment = Alignment.Center,
    ) {
        Text("🎬", fontSize = 34.sp)
    }
}
