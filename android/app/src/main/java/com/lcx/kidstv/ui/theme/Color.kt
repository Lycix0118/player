package com.lcx.kidstv.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * 取自网页版 `frontend/styles/tokens.css` 的 :root 变量，一一对应。
 * 改色请两边一起改，否则安卓端与网页端会走样。
 */
object KidsColors {
    val CoralRed = Color(0xFFFF6B6B)
    val MintGreen = Color(0xFF4ECDC4)
    val SunshineYellow = Color(0xFFFFE66D)

    val CoralLight = Color(0xFFFF8E8E)
    val CoralDark = Color(0xFFFF4757)
    val MintLight = Color(0xFF6BCCC4)
    val MintDark = Color(0xFF26D0CE)
    val YellowLight = Color(0xFFFFED8A)
    val YellowDark = Color(0xFFFFD93D)

    val White = Color(0xFFFFFFFF)
    val Gray50 = Color(0xFFF8F9FA)
    val Gray100 = Color(0xFFF1F3F4)
    val Gray200 = Color(0xFFE8EAED)
    val Gray300 = Color(0xFFDADCE0)
    val Gray600 = Color(0xFF5F6368)
    val Gray800 = Color(0xFF3C4043)
    val Gray900 = Color(0xFF202124)

    /** 半透明黑：播放页锁屏遮罩 */
    val Scrim = Color(0xE6000000)
}
