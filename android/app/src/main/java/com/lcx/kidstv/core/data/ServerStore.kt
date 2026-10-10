package com.lcx.kidstv.core.data

import android.content.Context
import android.os.Build
import com.lcx.kidstv.core.net.PlayerApi

/**
 * 本地持久化：目前只有「后端服务器地址」。
 *
 * 为什么需要它：安卓端不像网页由同一个 origin 提供页面，
 * 必须知道后端跑在哪。模拟器用 `10.0.2.2`，真机平板走局域网 `192.168.x.x`。
 */
class ServerStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("kids_tv_prefs", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, null) ?: defaultUrl
        set(value) {
            prefs.edit().putString(KEY_BASE_URL, PlayerApi.normalize(value)).apply()
        }

    private val defaultUrl: String
        get() {
            val isEmulator = Build.FINGERPRINT.startsWith("generic") ||
                Build.MODEL.contains("google_sdk") ||
                Build.MODEL.contains("Emulator") ||
                Build.HARDWARE.contains("goldfish") ||
                Build.HARDWARE.contains("ranchu")
            return if (isEmulator) PlayerApi.DEFAULT_BASE_URL else "http://192.168.40.39:8000"
        }

    companion object {
        private const val KEY_BASE_URL = "base_url"
    }
}
