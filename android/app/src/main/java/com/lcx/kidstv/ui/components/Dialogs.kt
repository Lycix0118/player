package com.lcx.kidstv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import com.lcx.kidstv.core.model.AppUpdateInfo
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.lcx.kidstv.ui.GateMode
import com.lcx.kidstv.ui.theme.KidsColors

/** 统一的弹窗外壳（对应网页版 .app-modal-card） */
@Composable
private fun ModalCard(
    title: String,
    onClose: () -> Unit,
    content: @Composable () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = Color.White,
        shadowElevation = 12.dp,
        modifier = Modifier
            .fillMaxWidth(0.62f)
            .padding(vertical = 24.dp),
    ) {
        Column {
            // 头部
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(start = 22.dp, end = 14.dp, top = 18.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    title,
                    style = MaterialTheme.typography.titleLarge,
                    color = KidsColors.Gray900,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onClose) {
                    Text("×", fontSize = 24.sp, color = KidsColors.Gray600)
                }
            }
            Column(Modifier.padding(horizontal = 22.dp, vertical = 6.dp)) { content() }
            Spacer(Modifier.height(14.dp))
        }
    }
}

/**
 * 家长验证门禁。两种模式：
 * - 已配置 PIN → 输入 4 位数字，交后端校验
 * - 未配置   → 趣味算术题，纯本地校验
 */
@Composable
fun ParentGateDialog(
    mode: GateMode,
    question: String,
    error: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (String) -> Unit,
) {
    var input by remember(mode, question) { mutableStateOf("") }

    Dialog(onDismissRequest = onDismiss) {
        ModalCard(title = "🔒 家长验证", onClose = onDismiss) {
            Text(
                text = if (mode == GateMode.PIN) "请输入 4 位家长密码以继续："
                else "请回答算术题验证家长身份：",
                style = MaterialTheme.typography.bodyMedium,
                color = KidsColors.Gray600,
            )
            Spacer(Modifier.height(16.dp))

            if (mode == GateMode.MATH) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        question,
                        style = MaterialTheme.typography.headlineSmall,
                        color = KidsColors.CoralRed,
                        modifier = Modifier.padding(end = 16.dp),
                    )
                    OutlinedTextField(
                        value = input,
                        onValueChange = { input = it.filter { c -> c.isDigit() }.take(6) },
                        singleLine = true,
                        label = { Text("答案") },
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Number,
                            imeAction = ImeAction.Done,
                        ),
                        modifier = Modifier.width(150.dp),
                    )
                }
            } else {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it.filter { c -> c.isDigit() }.take(4) },
                    singleLine = true,
                    label = { Text("4 位 PIN") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.NumberPassword,
                        imeAction = ImeAction.Done,
                    ),
                    modifier = Modifier.width(200.dp),
                )
            }

            if (error) {
                Spacer(Modifier.height(10.dp))
                Text("验证失败，请重试", color = KidsColors.CoralDark, style = MaterialTheme.typography.bodyMedium)
            }

            Spacer(Modifier.height(22.dp))
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = onDismiss) { Text("取消") }
                Spacer(Modifier.width(10.dp))
                Button(
                    onClick = { onSubmit(input) },
                    colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                ) { Text("验证进入") }
            }
        }
    }
}

/** 家长临时加时 */
@Composable
fun ExtendDialog(
    onDismiss: () -> Unit,
    onExtend: (type: String, minutes: Int) -> Unit,
) {
    Dialog(onDismissRequest = onDismiss) {
        ModalCard(title = "⏱️ 家长临时加时", onClose = onDismiss) {
            Text(
                "请选择为当前合集或全局追加今日观看时长：",
                style = MaterialTheme.typography.bodyMedium,
                color = KidsColors.Gray600,
            )
            Spacer(Modifier.height(16.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                ExtendOption("本合集 +10 分钟", Modifier.weight(1f)) { onExtend("folder", 10) }
                ExtendOption("本合集 +15 分钟", Modifier.weight(1f)) { onExtend("folder", 15) }
            }
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                ExtendOption("全局总限时 +15 分钟", Modifier.weight(1f)) { onExtend("global", 15) }
                ExtendOption("今日不再限制", Modifier.weight(1f)) { onExtend("unlock_today", 1440) }
            }
        }
    }
}

@Composable
private fun ExtendOption(label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = KidsColors.Gray100,
        modifier = modifier,
    ) {
        TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
            Text(
                label,
                color = KidsColors.Gray800,
                fontSize = 13.5.sp,
                textAlign = TextAlign.Center,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

/** 合集已受限的温和拦截弹窗 */
@Composable
fun FolderBlockedDialog(
    title: String,
    description: String,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    Dialog(onDismissRequest = onDismiss) {
        ModalCard(title = "🌟 休息时间到啦", onClose = onDismiss) {
            Column(
                Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(
                    Modifier
                        .padding(vertical = 6.dp)
                        .background(KidsColors.YellowLight, RoundedCornerShape(50))
                        .padding(horizontal = 20.dp, vertical = 10.dp)
                ) {
                    Text("⏰", fontSize = 30.sp)
                }
                Spacer(Modifier.height(14.dp))
                Text(
                    title,
                    style = MaterialTheme.typography.titleLarge,
                    color = KidsColors.Gray900,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = KidsColors.Gray600,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(22.dp))
                Button(
                    onClick = onConfirm,
                    colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                    modifier = Modifier.width(160.dp),
                ) { Text("好的，去休息") }
            }
        }
    }
}

/** 检查更新与下载安装弹窗 */
@Composable
fun AppUpdateDialog(
    updateInfo: AppUpdateInfo,
    isDownloading: Boolean,
    downloadProgress: Int,
    onDismiss: () -> Unit,
    onConfirmUpdate: () -> Unit,
) {
    Dialog(onDismissRequest = { if (!isDownloading) onDismiss() }) {
        ModalCard(title = "🚀 发现新版本", onClose = { if (!isDownloading) onDismiss() }) {
            Column(Modifier.fillMaxWidth()) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column {
                        Text(
                            "新版本：v${updateInfo.versionName}",
                            style = MaterialTheme.typography.titleLarge,
                            color = KidsColors.CoralRed,
                            fontWeight = FontWeight.Bold,
                        )
                        if (updateInfo.releaseDate.isNotBlank()) {
                            Spacer(Modifier.height(2.dp))
                            Text(
                                "发布日期：${updateInfo.releaseDate}",
                                style = MaterialTheme.typography.bodySmall,
                                color = KidsColors.Gray600,
                            )
                        }
                    }
                    if (updateInfo.fileSizeFormatted.isNotBlank()) {
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = KidsColors.Gray100,
                        ) {
                            Text(
                                updateInfo.fileSizeFormatted,
                                style = MaterialTheme.typography.labelMedium,
                                color = KidsColors.Gray800,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                            )
                        }
                    }
                }

                Spacer(Modifier.height(14.dp))

                Text(
                    "更新内容：",
                    style = MaterialTheme.typography.titleSmall,
                    color = KidsColors.Gray900,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(6.dp))
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = KidsColors.Gray50,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        updateInfo.changelog.ifBlank { "性能优化与体验改进" },
                        style = MaterialTheme.typography.bodyMedium,
                        color = KidsColors.Gray800,
                        lineHeight = 22.sp,
                        modifier = Modifier.padding(12.dp),
                    )
                }

                Spacer(Modifier.height(20.dp))

                if (isDownloading) {
                    Column(Modifier.fillMaxWidth()) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                if (downloadProgress >= 100) "下载完成，正在唤起安装…" else "正在下载安装包…",
                                style = MaterialTheme.typography.bodyMedium,
                                color = KidsColors.CoralRed,
                            )
                            Text(
                                "$downloadProgress%",
                                style = MaterialTheme.typography.bodyMedium,
                                color = KidsColors.CoralRed,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        LinearProgressIndicator(
                            progress = { downloadProgress / 100f },
                            modifier = Modifier.fillMaxWidth().height(8.dp),
                            color = KidsColors.CoralRed,
                            trackColor = KidsColors.Gray200,
                        )
                    }
                } else {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        TextButton(onClick = onDismiss) {
                            Text("稍后再说", color = KidsColors.Gray600)
                        }
                        Spacer(Modifier.width(12.dp))
                        Button(
                            onClick = onConfirmUpdate,
                            colors = ButtonDefaults.buttonColors(containerColor = KidsColors.CoralRed),
                        ) {
                            Text("立即下载更新")
                        }
                    }
                }
            }
        }
    }
}
