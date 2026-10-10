# 安卓开发环境搭建记录

> 搭建日期：2026-10-07　｜　用途：为「儿童视频播放器」的原生 Android 客户端（Kotlin + Jetpack Compose + Media3）准备构建与调试环境
> 搭建方式：**纯命令行**（未依赖 Android Studio 安装向导）

---

## 一、基本信息

### 核心约束

**C 盘只剩约 1GB**（搭建时约 3GB，后续持续下降），因此 SDK、Gradle 缓存、AVD 数据**全部落在 D 盘**。

### 安装位置

| 用途 | 路径 | 占用 |
|---|---|---|
| JDK 21（运行 Gradle 自身） | `D:\Java\jdk-21` | — |
| JDK 17（Android 项目默认工具链） | `D:\Java\jdk-17` | — |
| Android SDK | `D:\android-sdk` | 3.9 G（清理后） |
| AVD / 模拟器数据 | `D:\android-home` | 5.3 G |
| Gradle 缓存与全局配置 | `D:\gradle-home` | 1.2 G |
| 验证用示例项目 | `D:\android-scratch\HelloTablet` | 51 M |

### 已安装 SDK 组件

| 组件 | 版本 |
|---|---|
| platform-tools（含 adb） | 37.0.1 |
| platforms/android-36 | 2.0.0 |
| build-tools/36.0.0 | 36.0.0 |
| emulator | 37.2.12 |
| system-images/android-35/google_apis_playstore_tablet/x86_64 | 9.0.0 ← **AVD 正在用** |
| cmdline-tools/latest | 23.0.0 |

> 原先还装过 `system-images/android-36/google_apis/x86_64`（4.3 GB），但它**从未被任何 AVD 使用**
> —— AVD 实际用的是 `medium_tablet` profile 自己拉的 android-35。已于 2026-10-07 删除。

### 模拟器

- 名称：**`medium_tablet`**（Pixel Tablet）
- 规格：2560×1600 @ 320dpi，Android 15 / API 35，RAM 1907MB
- 硬件加速：**WHPX 已启用**（`emulator-check accel` 通过），**冷启动约 10 秒**

### 环境变量（用户级、已持久化）

| 变量 | 值 | 作用 |
|---|---|---|
| `JAVA_HOME` | `D:\Java\jdk-21` | 运行 Gradle 自身 |
| `ANDROID_HOME` / `ANDROID_SDK_ROOT` | `D:\android-sdk` | SDK 位置 |
| `ANDROID_USER_HOME` | `D:\android-home` | 把 `.android`（含 avd）挪到 D 盘 |
| `ANDROID_AVD_HOME` | `D:\android-home\avd` | 让传统 `emulator.exe` 也能找到 AVD |
| `GRADLE_USER_HOME` | `D:\gradle-home` | Gradle 缓存挪到 D 盘 |
| `PATH` | 追加 JDK/bin、SDK 的 `platform-tools`、`emulator`、`cmdline-tools\latest\bin` | 命令行直接可用 |

> ⚠️ **环境变量对已打开的终端不生效**，需新开一个终端窗口。

---

## 二、常用命令

```bash
# 启动模拟器
emulator -avd medium_tablet

# 查看已连接设备
adb devices -l

# 命令行建项目（不依赖 IDE）
android create empty-activity -o D:/myapp --name MyApp --application-id com.example.myapp

# 构建 / 安装 / 启动
cd <项目目录>
./gradlew assembleDebug          # 产物：app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell monkey -p <包名> -c android.intent.category.LAUNCHER 1
```

---

## 三、踩过的坑（均在本机实测）

### 1. ⚠️ 最重要：Gradle 官方分发 CDN 在国内基本不可用

`services.gradle.org` 返回 307 后**下载停滞**——实测约 **60 KB/s**，10 分钟只下了 33 MB。

**必须换镜像。** 改 `gradle/wrapper/gradle-wrapper.properties`：

```properties
distributionUrl=https\://mirrors.cloud.tencent.com/gradle/gradle-9.1.0-bin.zip
networkTimeout=60000
```

腾讯镜像实测 **5.68 MB/s**。（阿里云的 `mirrors.aliyun.com/gradle/` 路径是 404，别用）

### 2. Maven 依赖建议加阿里云镜像

实测速度：`repo1.maven.org` **467 KB/s** ｜ 阿里云 public **6.98 MB/s** ｜ Google Maven 3.17 MB/s。

在 `settings.gradle.kts` 的**两处** repositories（`pluginManagement` 与 `dependencyResolutionManagement`）最前面加：

```kotlin
maven { url = uri("https://maven.aliyun.com/repository/public") }
maven { url = uri("https://maven.aliyun.com/repository/google") }
maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
```

### 3. JDK 工具链：项目要 17，而 Gradle 会去 GitHub 拉（被墙）

Android 模板默认 `kotlin { jvmToolchain(17) }`，本机原本只有 JDK 21 →
Gradle 尝试从 `github.com/adoptium/...` 自动下载 JDK 17，失败。

**已解决**：装 JDK 17 到 `D:\Java\jdk-17`（清华 TUNA 镜像，实测 **44 MB/s**），
并在 `D:\gradle-home\gradle.properties` 明确指定：

```properties
org.gradle.java.installations.paths=D:/Java/jdk-17,D:/Java/jdk-21
org.gradle.java.installations.auto-download=false
```

### 4. `sdkmanager` / `avdmanager` 的包名不能用 `;`

cmd 的 `for` 命令把 `;` 当分隔符，`platforms;android-36` 会被拆成两个包，
报 `Package platforms not found`。

**改用 `/`**：`platforms/android-36`、`build-tools/36.0.0`、`system-images/android-36/google_apis/x86_64`。

（例外：`avdmanager -k` 参数**只认 `;`**，而这正好过不了 cmd —— 所以建 AVD 改用 `android emulator create`）

### 5. 新版 `android` CLI 有「做完不退出」的毛病

`android sdk install <包>` 实际已完成下载与解压，但进程不返回（实测卡 10 分钟以上）。

**结论：涉及下载时优先用经典 `sdkmanager` + `/` 分隔 ID**，实测正常退出。
`android create` / `android emulator create` 无此问题。

### 6. git bash 的两个路径陷阱

- `adb shell screencap -p /sdcard/x.png` —— `/sdcard/...` 会被 MSYS 转成 Windows 路径
  → 加 `MSYS_NO_PATHCONV=1`
- 加了上面那个之后，**本地**路径又不再转换了 → 本地参数写成 `"D:\path\file.png"`

### 7. 局域网明文 HTTP（后续做 App 时会遇到）

Android 9+ 默认禁止 App 访问 `http://192.168.x.x`，需在清单中开
`android:usesCleartextTraffic="true"` 或配 `network-security-config`。

### 8. ❗ 本机「删除」= 进回收站，不清空就等于没删

在这台机器上，**`rm` 和 `Remove-Item` 都会把文件移进 `X:\$Recycle.Bin`，磁盘空间不会立即释放**。
实测：删完 Flutter SDK（2.9 GB）后 D 盘可用空间几乎没变，回收站却多了 2 万多条目。

真正回收空间：

```powershell
Clear-RecycleBin -DriveLetter D -Force
```

实测清空 D 盘回收站释放 **14 GB**（41.8G → 55.9G）。

两条配套经验：

- **判断空间别用 MSYS 的 `df`/`du`**——本机读数会滞后/缓存（同一命令前后都返回 42G）。
  用 `Get-Volume`（PowerShell）取准确值。
- **删大树别用 `rm -rf`**——2.9G / 5 万文件跑了 20 分钟没删完。
  改用 `Remove-Item -Recurse -Force`（5.5 分钟），或 robocopy 镜像法。

---

## 四、验收标准（本次已全部通过）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | JDK 21 与 JDK 17 均可用 | ✅ 21.0.2 / 17.0.20.1 |
| 2 | `adb` 可用 | ✅ 37.0.1 |
| 3 | 模拟器硬件加速 | ✅ WHPX 可用（`emulator-check accel`） |
| 4 | 模拟器能冷启动 | ✅ **10 秒**内 `sys.boot_completed=1` |
| 5 | AVD 落在 D 盘 | ✅ `D:\android-home\avd\medium_tablet.avd` |
| 6 | `./gradlew assembleDebug` 构建成功 | ✅ 3m38s，产出 **12MB** APK |
| 7 | APK 能装进模拟器并运行 | ✅ 前台 `MainActivity`，界面渲染出 "Hello Android!" |
| 8 | **C 盘空间未被侵占** | ✅ 搭建期间 3.1G → 2.7G（仅新增 `.android` 目录 237M）；⚠️ 但之后持续下降到 ~1G，与本次搭建无关 |

> 验证截图：`D:\android-scratch\verify\app-running.png`

---

## 五、已执行的清理（2026-10-07）

| 清理项 | 体积 | 说明 |
|---|---|---|
| `D:\flutter`（整个目录） | 4.6 G | Flutter 路线已弃用。含 SDK 本体 2.9 G + 冗余安装包 zip 1.7 G |
| `system-images/android-36/google_apis/x86_64` | 4.3 G | 从未被任何 AVD 引用（AVD 用的是 android-35） |
| PATH 中的 `D:\flutter\flutter\bin` | — | User 与 Machine 两处均已移除（该目录已不存在） |
| D 盘回收站 | ~20 G | 上述删除实际都落到了回收站，`Clear-RecycleBin` 后才真正释放 |

**最终效果：D 盘可用 41.8 G → 55.9 G。**

> ⚠️ PATH 的修改**对已打开的终端不生效**，需新开终端；旧终端里 `flutter` 仍可能残留。

### 保留项 / 后续可关注

- D 盘本来就有 `D:\Android Studio`；SDK 配好后可以直接打开 IDE 使用
- **C 盘只剩 ~1 GB，是当前最大的隐患**。扫描确认**不是缓存造成的**
  （`.android` 237M / `Local\Temp` 213M / `Local\Google` 1.4G / `ProgramData\Package Cache` 1.3G，
  都不足以解释 200 G 占满）→ 属结构性问题：装的软件太多。
  可行方向是**把软件迁到 D 盘**，或扩容/合并分区。
