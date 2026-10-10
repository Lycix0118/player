package com.lcx.kidstv.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp

private val KidsColorScheme = lightColorScheme(
    primary = KidsColors.CoralRed,
    onPrimary = KidsColors.White,
    primaryContainer = KidsColors.CoralLight,
    onPrimaryContainer = KidsColors.White,
    secondary = KidsColors.MintGreen,
    onSecondary = KidsColors.White,
    tertiary = KidsColors.SunshineYellow,
    onTertiary = KidsColors.Gray800,
    background = KidsColors.Gray50,
    onBackground = KidsColors.Gray900,
    surface = KidsColors.White,
    onSurface = KidsColors.Gray900,
    surfaceVariant = KidsColors.Gray100,
    onSurfaceVariant = KidsColors.Gray600,
    outline = KidsColors.Gray300,
    error = KidsColors.CoralDark,
    onError = KidsColors.White,
)

/** 圆角档位对应 tokens.css 的 --radius-sm / md / lg */
private val KidsShapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(24.dp),
)

@Composable
fun KidsTvTheme(content: @Composable () -> Unit) {
    // 网页版只有一套「糖果电视」配色，没有暗色模式，故这里固定浅色
    MaterialTheme(
        colorScheme = KidsColorScheme,
        shapes = KidsShapes,
        typography = KidsTypography,
        content = content,
    )
}
