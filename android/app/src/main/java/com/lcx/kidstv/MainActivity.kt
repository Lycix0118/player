package com.lcx.kidstv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import com.lcx.kidstv.ui.AppViewModel
import com.lcx.kidstv.ui.KidsTvApp

/**
 * 唯一 Activity。整个界面由 Compose 绘制，屏幕切换走 ViewModel 里的状态机，
 * 因此不需要 Fragment / Navigation。
 */
class MainActivity : ComponentActivity() {

    private val viewModel: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            KidsTvApp(viewModel)
        }
    }
}
