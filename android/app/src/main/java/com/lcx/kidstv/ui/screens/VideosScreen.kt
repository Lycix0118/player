package com.lcx.kidstv.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lcx.kidstv.core.model.Episode
import com.lcx.kidstv.ui.AppViewModel
import com.lcx.kidstv.ui.components.AppHeader
import com.lcx.kidstv.ui.components.CoverImage
import com.lcx.kidstv.ui.components.EmptyState
import com.lcx.kidstv.ui.components.ProgressLine
import com.lcx.kidstv.ui.theme.KidsColors
import java.util.Locale

private enum class SortMode(val label: String, val value: String) {
    INDEX("正序", "index"),
    PROGRESS("最近观看", "progress"),
    TITLE("标题", "title"),
}

/**
 * 分集列表页，对应网页版 `#videos-screen`。
 */
@Composable
fun VideosScreen(vm: AppViewModel) {
    var query by remember { mutableStateOf("") }
    var sort by remember { mutableStateOf(SortMode.INDEX) }
    val focusManager = LocalFocusManager.current

    val folderName = vm.currentFolderPath.split('/').lastOrNull().orEmpty()

    val visible = remember(vm.videos, query, sort) {
        vm.videos
            .filter { query.isBlank() || it.title.lowercase(Locale.getDefault()).contains(query.lowercase(Locale.getDefault())) }
            .sortedWith(
                when (sort) {
                    SortMode.TITLE -> compareBy { it.title }
                    SortMode.PROGRESS -> compareByDescending { it.progress?.updatedAt ?: 0.0 }
                    SortMode.INDEX -> compareBy { it.displayIndex }
                }
            )
    }

    Column(Modifier.fillMaxSize()) {
        AppHeader(
            title = "📺 $folderName",
            pill = vm.timePill(),
            onBack = vm::backToFolders,
            onLockClick = { vm.requestParentAccess { vm.openSettings() } },
        )

        LazyVerticalGrid(
            columns = GridCells.Adaptive(minSize = 280.dp),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 14.dp, bottom = 36.dp),
            horizontalArrangement = Arrangement.spacedBy(18.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(bottom = 2.dp),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedTextField(
                        value = query,
                        onValueChange = { query = it },
                        singleLine = true,
                        placeholder = { Text("⌕ 搜索本合集", color = KidsColors.Gray600) },
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                        keyboardActions = KeyboardActions(onSearch = { focusManager.clearFocus() }),
                        trailingIcon = if (query.isNotBlank()) {
                            {
                                Text(
                                    "✕",
                                    color = KidsColors.Gray600,
                                    fontSize = 13.sp,
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(50))
                                        .clickable { query = "" }
                                        .padding(horizontal = 10.dp, vertical = 6.dp),
                                )
                            }
                        } else null,
                        modifier = Modifier.width(260.dp),
                    )
                    Spacer(Modifier.width(10.dp))
                    SortSelector(sort) { sort = it }
                }
            }

            if (visible.isEmpty()) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    EmptyState(
                        title = "📺 暂无视频",
                        description = "请在 list.txt 中添加 B站 或 silidm（电影先生）视频链接",
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(220.dp),
                    )
                }
            } else {
                items(visible, key = { "${it.bvid}|${it.page}" }) { episode ->
                    VideoCard(vm, episode)
                }
            }
        }
    }
}

@Composable
private fun SortSelector(current: SortMode, onSelect: (SortMode) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = KidsColors.White,
            border = androidx.compose.foundation.BorderStroke(1.dp, KidsColors.Gray300),
            modifier = Modifier.clickable { expanded = true },
        ) {
            Row(
                Modifier.padding(horizontal = 14.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(current.label, color = KidsColors.Gray800, fontSize = 14.sp)
                Spacer(Modifier.width(6.dp))
                Text("▾", color = KidsColors.Gray600, fontSize = 12.sp)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            SortMode.entries.forEach { mode ->
                DropdownMenuItem(
                    text = { Text(mode.label) },
                    onClick = {
                        onSelect(mode)
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
private fun VideoCard(vm: AppViewModel, episode: Episode) {
    val progress = episode.progress
    val percent = progress?.percent ?: 0

    Surface(
        shape = RoundedCornerShape(12.dp),
        color = KidsColors.White,
        shadowElevation = 2.dp,
        modifier = Modifier
            .fillMaxWidth()
            .clickable { vm.playEpisode(episode, episode.folderPath) },
    ) {
        Column {
            CoverImage(
                primary = vm.coverFor(episode),
                fallback = vm.fallbackCoverFor(episode),
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(16f / 9f)
                    .clip(RoundedCornerShape(topStart = 12.dp, topEnd = 12.dp)),
            )

            Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                Text(
                    episode.title.ifBlank { "第 ${episode.displayIndex} 集" },
                    style = MaterialTheme.typography.titleMedium,
                    color = KidsColors.Gray800,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    lineHeight = 21.sp,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    "第 ${episode.displayIndex} 集" + if (episode.source == "silidm") " · 电影先生" else "",
                    color = KidsColors.CoralRed,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                if (episode.duration > 0) {
                    Spacer(Modifier.height(3.dp))
                    Text(
                        formatDuration(episode.duration),
                        style = MaterialTheme.typography.bodyMedium,
                        color = KidsColors.Gray600,
                    )
                }
                if (percent > 0) {
                    Spacer(Modifier.height(8.dp))
                    ProgressLine(fraction = percent / 100f, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(4.dp))
                    Text(
                        if (progress?.completed == true) "已看完" else "已观看 $percent%",
                        color = KidsColors.Gray600,
                        fontSize = 12.sp,
                    )
                }
            }
        }
    }
}

private fun formatDuration(seconds: Int): String {
    val minutes = seconds / 60
    val rest = seconds % 60
    return "%d:%02d".format(Locale.US, minutes, rest)
}

/** 供播放页复用的居中提示（加载中 / 无视频） */
@Composable
internal fun CenteredHint(text: String, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text, color = KidsColors.Gray600, textAlign = TextAlign.Center)
    }
}
