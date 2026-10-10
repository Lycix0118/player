package com.lcx.kidstv.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.lcx.kidstv.ui.components.AppUpdateDialog
import com.lcx.kidstv.ui.components.FolderBlockedDialog
import com.lcx.kidstv.ui.components.ExtendDialog
import com.lcx.kidstv.ui.components.ParentGateDialog
import com.lcx.kidstv.ui.components.ToastHost
import com.lcx.kidstv.ui.screens.FoldersScreen
import com.lcx.kidstv.ui.screens.LoadingScreen
import com.lcx.kidstv.ui.screens.PlayerScreen
import com.lcx.kidstv.ui.screens.SettingsScreen
import com.lcx.kidstv.ui.screens.VideosScreen
import com.lcx.kidstv.ui.theme.KidsColors
import com.lcx.kidstv.ui.theme.KidsTvTheme

/**
 * 应用根组件：屏幕路由（对应网页版 `ScreenRouter`）+ 全局弹窗 + 吐司。
 *
 * 屏切换用 Crossfade 做淡入淡出，替代网页版的 `.screen.hidden` 显示切换。
 */
@Composable
fun KidsTvApp(vm: AppViewModel) {

    // 前后台感知：切后台时暂停播放、保存进度并停止计时（网页版靠 visibilitychange 做同样的事）
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> vm.onAppResume()
                Lifecycle.Event.ON_PAUSE -> vm.onAppPause()
                Lifecycle.Event.ON_STOP -> vm.onAppPause()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(Unit) { vm.bootstrap() }

    // 系统返回键：全屏时先退出全屏；有上一级才拦截，根页面交回系统（退出 App）
    val canGoBack = when {
        vm.isFullscreen -> true
        vm.screen == Screen.SETTINGS || vm.screen == Screen.PLAYER || vm.screen == Screen.VIDEOS -> true
        vm.screen == Screen.FOLDERS -> vm.pathStack.isNotEmpty()
        else -> false
    }
    BackHandler(enabled = canGoBack) {
        when {
            vm.isFullscreen -> vm.exitFullscreen()
            vm.screen == Screen.SETTINGS -> vm.backToFolders()
            vm.screen == Screen.PLAYER -> vm.backToVideos()
            vm.screen == Screen.VIDEOS -> vm.backToFolders()
            vm.screen == Screen.FOLDERS -> vm.navigateToParent()
            else -> Unit
        }
    }

    KidsTvTheme {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = KidsColors.Gray50,
        ) {
            Box(Modifier.fillMaxSize()) {
                Crossfade(
                    targetState = vm.screen,
                    animationSpec = tween(durationMillis = 260),
                    label = "screen",
                ) { screen ->
                    Box(
                        Modifier
                            .fillMaxSize()
                            .background(KidsColors.Gray50)
                    ) {
                        when (screen) {
                            Screen.LOADING -> LoadingScreen()
                            Screen.FOLDERS -> FoldersScreen(vm)
                            Screen.VIDEOS -> VideosScreen(vm)
                            Screen.PLAYER -> PlayerScreen(vm)
                            Screen.SETTINGS -> SettingsScreen(vm)
                        }
                    }
                }

                ToastHost(vm.toast) { vm.dismissToast() }
            }
        }

        // ---- 全局弹窗 ----
        if (vm.gateVisible) {
            ParentGateDialog(
                mode = vm.gateMode,
                question = vm.gateQuestion,
                error = vm.gateError,
                onDismiss = vm::dismissGate,
                onSubmit = vm::submitGate,
            )
        }

        if (vm.extendVisible) {
            ExtendDialog(
                onDismiss = vm::dismissExtendDialog,
                onExtend = vm::submitExtension,
            )
        }

        vm.blockedDialog?.let { (title, description) ->
            FolderBlockedDialog(
                title = title,
                description = description,
                onDismiss = vm::dismissBlockedDialog,
                onConfirm = vm::dismissBlockedDialog,
            )
        }

        vm.updateInfo?.let { update ->
            if (vm.updateDialogVisible) {
                AppUpdateDialog(
                    updateInfo = update,
                    isDownloading = vm.isDownloadingUpdate,
                    downloadProgress = vm.updateDownloadProgress,
                    onDismiss = vm::dismissUpdateDialog,
                    onConfirmUpdate = vm::startUpdateDownload,
                )
            }
        }
    }
}
