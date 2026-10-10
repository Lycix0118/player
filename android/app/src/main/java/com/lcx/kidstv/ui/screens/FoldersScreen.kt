package com.lcx.kidstv.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lcx.kidstv.core.model.Episode
import com.lcx.kidstv.core.model.FolderInfo
import com.lcx.kidstv.ui.AppViewModel
import com.lcx.kidstv.ui.components.AppHeader
import com.lcx.kidstv.ui.components.EmptyState
import com.lcx.kidstv.ui.components.SectionKicker
import com.lcx.kidstv.ui.theme.KidsColors
import kotlin.math.ceil

/**
 * 合集列表页，对应网页版 `#folders-screen`。
 * 结构：顶部导航条 → 「继续观看」→ 视频库工具条 → 合集网格。
 */
@Composable
fun FoldersScreen(vm: AppViewModel) {
    val title = if (vm.pathStack.isEmpty()) "📁 选择文件夹"
    else "📁 ${vm.pathStack.last()}"

    Column(Modifier.fillMaxSize()) {
        AppHeader(
            title = title,
            pill = vm.timePill(),
            onBack = if (vm.pathStack.isEmpty()) null else vm::navigateToParent,
            onLockClick = { vm.requestParentAccess { vm.openSettings() } },
        )

        LazyVerticalGrid(
            columns = GridCells.Adaptive(minSize = 250.dp),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 18.dp, bottom = 36.dp),
            horizontalArrangement = Arrangement.spacedBy(18.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            // ---- 继续观看 ----
            if (vm.continueWatching.isNotEmpty()) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    ContinueWatchingSection(vm)
                }
            }

            // ---- 视频库工具条 ----
            item(span = { GridItemSpan(maxLineSpan) }) {
                LibraryToolbar(vm)
            }

            // ---- 合集网格 ----
            if (vm.foldersLoading && vm.folders.isEmpty()) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .height(180.dp),
                        contentAlignment = Alignment.Center,
                    ) { CircularProgressIndicator(color = KidsColors.CoralRed) }
                }
            } else if (vm.folders.isEmpty()) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .padding(vertical = 32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        EmptyState(
                            title = "📁 暂无视频合集",
                            description = "未检测到视频合集，或尚未连接到局域网后端服务。\n若在平板上运行，请在家长区配置电脑后端的局域网 IP 地址。",
                        )
                        Spacer(Modifier.height(18.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Button(
                                onClick = { vm.requestParentAccess { vm.openSettings() } },
                                colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                            ) { Text("⚙️ 家长区配置服务") }
                            TextButton(onClick = vm::refreshCurrentFolders) { Text("重新加载") }
                        }
                    }
                }
            } else {
                itemsIndexed(vm.folders, key = { _, f -> f.path }) { index, folder ->
                    FolderCard(vm, folder, index)
                }
            }
        }
    }
}

@Composable
private fun ContinueWatchingSection(vm: AppViewModel) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
            Column(Modifier.weight(1f)) {
                SectionKicker("继续观看")
                Spacer(Modifier.height(2.dp))
                Text(
                    "接着上次播放",
                    style = MaterialTheme.typography.headlineSmall,
                    color = KidsColors.Gray900,
                )
            }
            Text(
                "${vm.continueWatching.size} 个未完成视频",
                style = MaterialTheme.typography.labelMedium,
                color = KidsColors.Gray600,
            )
        }
        Spacer(Modifier.height(12.dp))
        // 两列排布，最多 6 个（与网页版一致的取数上限）
        vm.continueWatching.chunked(2).forEach { rowItems ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                rowItems.forEach { episode ->
                    ContinueCard(vm, episode, Modifier.weight(1f))
                }
                if (rowItems.size == 1) Spacer(Modifier.weight(1f))
            }
        }
        Spacer(Modifier.height(6.dp))
    }
}

@Composable
private fun ContinueCard(vm: AppViewModel, episode: Episode, modifier: Modifier = Modifier) {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = KidsColors.White,
        border = androidx.compose.foundation.BorderStroke(1.dp, KidsColors.Gray200),
        modifier = modifier.clickable {
            if (vm.isFolderLocked(episode.folderPath)) {
                vm.showFolderBlocked(episode.folderPath)
            } else {
                vm.playEpisode(episode, episode.folderPath)
            }
        },
    ) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier
                    .size(34.dp)
                    .clip(CircleShape)
                    .background(KidsColors.CoralRed),
                contentAlignment = Alignment.Center,
            ) { Text("▶", color = KidsColors.White, fontSize = 13.sp) }

            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    episode.title.ifBlank { "第 ${episode.displayIndex} 集" },
                    style = MaterialTheme.typography.titleMedium,
                    color = KidsColors.Gray900,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(3.dp))
                Text(
                    "${episode.folderPath} · 已观看 ${episode.progress?.percent ?: 0}%",
                    style = MaterialTheme.typography.labelMedium,
                    color = KidsColors.Gray600,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun LibraryToolbar(vm: AppViewModel) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(top = 6.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            SectionKicker("我的视频库")
            Spacer(Modifier.height(2.dp))
            Text(
                when {
                    vm.foldersLoading -> "正在读取视频库…"
                    vm.folders.isEmpty() -> "还没有视频合集"
                    else -> "${vm.folders.size} 个合集，选择一个开始播放"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = KidsColors.Gray600,
            )
        }
        TextButton(onClick = vm::refreshCurrentFolders) { Text("刷新") }
    }
}

@Composable
private fun FolderCard(vm: AppViewModel, folder: FolderInfo, index: Int) {
    val locked = vm.isFolderLocked(folder.path)
    val remainingSec = vm.folderRemainingSeconds(folder.path)
    val remainingMin = remainingSec?.let { ceil(it / 60.0).toInt() }

    Surface(
        shape = RoundedCornerShape(12.dp),
        color = KidsColors.White,
        shadowElevation = 2.dp,
        modifier = Modifier
            .fillMaxWidth()
            .clickable { vm.openFolder(folder) },
    ) {
        Column {
            // 顶部渐变条（网页版是 hover 显示，触摸端没有 hover，这里常显作为视觉标识）
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(4.dp)
                    .background(
                        Brush.horizontalGradient(
                            listOf(KidsColors.CoralRed, KidsColors.MintGreen)
                        )
                    )
            )

            Box {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 20.dp, vertical = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("📁", fontSize = 42.sp)
                    Spacer(Modifier.height(14.dp))
                    Text(
                        folder.name,
                        style = MaterialTheme.typography.titleLarge,
                        color = KidsColors.Gray800,
                        textAlign = TextAlign.Center,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(6.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (folder.videoCount > 0) {
                            Text(
                                "${folder.videoCount} 部视频",
                                style = MaterialTheme.typography.bodyMedium,
                                color = KidsColors.Gray600,
                            )
                        }
                        if (!folder.hasListFile) {
                            Text(
                                "子目录",
                                style = MaterialTheme.typography.bodyMedium,
                                color = KidsColors.MintDark,
                            )
                        }
                    }
                }

                // 右上角限时徽章
                when {
                    locked -> FolderTimeBadge(
                        text = "🔒 今日已休息",
                        bg = KidsColors.CoralDark,
                        fg = KidsColors.White,
                        modifier = Modifier.align(Alignment.TopEnd).padding(10.dp),
                    )
                    remainingMin != null -> FolderTimeBadge(
                        text = "⏱ 剩 $remainingMin 分",
                        bg = if (remainingMin <= 10) KidsColors.YellowDark else KidsColors.Gray100,
                        fg = KidsColors.Gray800,
                        modifier = Modifier.align(Alignment.TopEnd).padding(10.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun FolderTimeBadge(
    text: String,
    bg: androidx.compose.ui.graphics.Color,
    fg: androidx.compose.ui.graphics.Color,
    modifier: Modifier = Modifier,
) {
    Surface(shape = RoundedCornerShape(50), color = bg, modifier = modifier) {
        Text(
            text,
            color = fg,
            fontSize = 11.5.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}
