package com.lcx.kidstv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lcx.kidstv.ui.AppViewModel
import com.lcx.kidstv.ui.theme.KidsColors

/**
 * 顶部导航条，对应网页版 `.app-header`：
 * 白底 + 底部 2px 分隔线 + 极浅投影，标题居中，右侧放「今日已看」胶囊与家长区锁按钮。
 */
@Composable
fun AppHeader(
    title: String,
    pill: AppViewModel.TimePill? = null,
    onBack: (() -> Unit)? = null,
    onLockClick: (() -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .shadow(2.dp)
            .background(KidsColors.White)
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // 左：返回
        Box(Modifier.size(width = 88.dp, height = 40.dp), contentAlignment = Alignment.CenterStart) {
            if (onBack != null) {
                Text(
                    text = "← 返回",
                    color = KidsColors.CoralRed,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .clickable(onClick = onBack)
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                )
            }
        }

        // 中：标题
        Text(
            text = title,
            fontSize = 19.sp,
            fontWeight = FontWeight.Bold,
            color = KidsColors.Gray800,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center,
            modifier = Modifier.weight(1f),
        )

        // 右：胶囊 + 锁 + 自定义
        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.height(40.dp),
        ) {
            pill?.let { TimePillBadge(it) }
            trailing?.invoke()
            if (onLockClick != null) {
                Box(
                    Modifier
                        .size(38.dp)
                        .clip(RoundedCornerShape(50))
                        .background(KidsColors.Gray100)
                        .clickable(onClick = onLockClick),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("🔒", fontSize = 16.sp)
                }
            }
        }
    }
}

/** 白底内容区，宽度上限 1180dp（对齐网页版 .content 的 max-width） */
@Composable
fun ContentColumn(
    modifier: Modifier = Modifier,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp),
        content = content,
    )
}
