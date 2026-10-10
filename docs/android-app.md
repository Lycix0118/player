# 安卓平板客户端（小电视）

> 建立日期：2026-10-07　｜　技术栈：Kotlin + Jetpack Compose + Media3 (ExoPlayer)
> 定位：把网页版播放器搬到平板上，**后端一行不改**。

---

## 一、基本信息

### 为什么是原生而不是套壳

见项目笔记的选型结论：电视端以后可能要做，而电视 UI 是「10 尺 + 遥控器焦点」，
与平板触摸 UI 本就不是一套，所以「复用现有前端」在电视端不成立。
因此选能**共享业务逻辑、UI 分两套**的原生方案。

### 后端是「胖服务端」，客户端是「薄客户端」

`backend/main.py` 有 31 个路由，silidm 解析、B站 WBI 签名、HLS 并行分片代理、
元数据融合、限时管控**全在服务端**。客户端只做两件事：

1. 取 JSON（合集 / 分集 / 进度 / 设置 / 限时）
2. 把后端给的播放地址交给 Media3

⇒ 播放有两条路，客户端不需要知道区别，只按 `stream` 标志与地址后缀判断：

| 来源 | 播放地址 | 协议 |
|---|---|---|
| B站 | `/static/{folder}/{bvid}_p{page}.mp4` | HTTP Range 直读 |
| silidm | `/api/hls/{episode_id}/index.m3u8` + `/seg/{n}.ts` | HLS（后端转发的 m3u8） |

### 磁盘约束

**C 盘只剩 ~950MB**，所以：

- 源码在仓库里（`android/`，随 git 走）
- **构建产物与临时目录全部重定向到 D 盘**——
  `settings.gradle.kts` 里用 `gradle.beforeProject { layout.buildDirectory.set(...) }`
  把每个模块的 `buildDir` 改写到 `D:/gradle-build/kidstv/<模块名>`；
  `gradle.properties` 里把 `java.io.tmpdir` 也指到 D 盘。

### 局域网连接

后端是明文 HTTP，两处都要处理：

- manifest 里开 `android:usesCleartextTraffic="true"` + `network-security-config`（放行 cleartext）
- 服务端地址**可配置**（家长区第一项）：
  - 模拟器：`http://10.0.2.2:8000`（10.0.2.2 就是宿主机的 localhost）
  - 平板：`http://<电脑局域网IP>:8000`

---

## 二、工程结构与职责

```
android/
├── settings.gradle.kts      # 阿里云镜像 + buildDir 迁到 D 盘
├── gradle.properties        # 临时目录迁到 D 盘
├── gradle/libs.versions.toml
└── app/src/main/java/com/lcx/kidstv/
    ├── MainActivity.kt                     # 唯一 Activity，setContent { KidsTvApp(vm) }
    ├── core/
    │   ├── model/Models.kt                 # 与后端 JSON 严格对齐（全部字段有默认值）
    │   ├── net/PlayerApi.kt                # OkHttp + kotlinx.serialization
    │   └── data/ServerStore.kt             # 后端地址持久化
    └── ui/
        ├── AppViewModel.kt                 # 状态机：屏幕路由 / 列表 / 播放 / 限时心跳 / 门禁
        ├── KidsTvApp.kt                    # 根组件（Crossfade 切屏 + 全局弹窗 + 返回键）
        ├── theme/{Color,Theme,Type}.kt     # 配色取自前端 styles/tokens.css
        ├── components/                     # 小电视、时长胶囊、弹窗、封面
        └── screens/                        # 五个屏幕
```

**为什么单 module**：先按包边界（`core` / `ui`）分开，等加电视端时再机械地拆成
`:core` / `:feature-tablet` / `:feature-tv`。单模块编译快、出错面小，第一步先要能跑起来。

---

## 三、与网页版的对应关系

| 网页版 | 安卓端 | 说明 |
|---|---|---|
| `#loading` + 小电视动效 | `LoadingScreen` | 眨眼 / 上下浮动 / 三色弹跳点，用 Compose 布局原语重画 |
| `#folders-screen` | `FoldersScreen` | 顶部条 + 继续观看 + 库工具条 + 合集网格 |
| `#videos-screen` | `VideosScreen` | 搜索 + 排序 + 封面网格（带进度条、来源标签） |
| `#player-screen` | `PlayerScreen` | Media3 PlayerView + 准备遮罩 + 预警气泡 + 到期锁屏 |
| `#settings-screen` | `SettingsScreen` | 家长区（多一项「服务器连接」） |
| `ScreenRouter` | `AppViewModel.screen` + `Crossfade` | 状态机切屏，替代 `.hidden` class |
| `TimeLimitsController` | `AppViewModel` 内的心跳段 | 1s tick / 5s 上报 / 3·1 分钟预警 / 到期锁屏 |
| `#cover-*` `<img onerror>` | `CoverImage` | 主地址失败自动退到 `/api/cover/...`，再失败显示占位 |

---

## 四、常用命令与产物

```bash
cd android
# 构建（本机环境变量是旧的，必须显式指定）
export JAVA_HOME="D:/Java/jdk-21"
export ANDROID_HOME="D:/android-sdk"
export GRADLE_USER_HOME="D:/gradle-home"

# 调试包打包
./gradlew assembleDebug
# 产物：D:/gradle-build/kidstv/app/outputs/apk/debug/app-debug.apk (~15.9 MB)

# 正式发布包打包（已配置 debug 签名，可直接装机）
./gradlew assembleRelease
# 产物：D:/gradle-build/kidstv/app/outputs/apk/release/app-release.apk (~10.9 MB)

# 装机 + 启动
adb install -r D:/gradle-build/kidstv/app/outputs/apk/release/app-release.apk
adb shell monkey -p com.lcx.kidstv -c android.intent.category.LAUNCHER 1
```

后端：

```bash
cd backend && <py39> start_server.py       # 0.0.0.0:8000，改代码自动热重载
```

---

## 五、核心完善点与特性记录

| 项 | 改进点 | 说明 |
|---|---|---|
| **断点续播** | 历史进度智能恢复 | 点击分集或「继续观看」进入播放，历史进度 > 5 秒且未看完时自动 `seekTo` 续播并弹出友好提示 |
| **自动连播** | 完播事件驱动连播 | 监听 `Player.STATE_ENDED`，完播即刻标记完成并回传、flush 心跳，开启「自动播放」时自动切下一集 |
| **全屏沉浸** | 影院全屏 + 状态栏隐藏 | 点击控制器全屏或顶部「⛶ 全屏」按钮进入全屏沉浸播放，隐藏系统栏；按返回键退出全屏 |
| **屏幕常亮** | `keepScreenOn = true` | 视频播放期间屏幕不再自动熄灭休眠 |
| **后台安全** | `onAppPause` 暂停 | App 切后台即刻暂停播放、上报当前进度与心跳，彻底杜绝后台偷跑流量与耗电 |
| **异常防护** | 播放容灾与一键重试 | 取消任务及时中断下载协程，避免后台幽灵发声；捕获 `PlaybackException` 并展示友好错误提示与重试按钮 |
| **翻页状态** | 首尾集智能置灰 | 播放页「上一集 / 下一集」按钮根据当前合集索引智能判定可用性，第一集或最后一集自动置灰 |
| **家长区入口** | 分集列表页补齐 🔒 | `VideosScreen` 顶部补全家长锁入口，无需退回到合集页即可修改限时或配置 |
| **搜索体验** | 快捷清除与键盘收起 | 搜索框增加一键清除 `✕` 图标与软键盘搜索动作联动 |
| **未连接引导** | 首页空状态配置按钮 | 首次在真机平板运行未配局域网 IP 时，空状态直供「⚙️ 家长区配置服务」引导按钮 |
| **Release 打包** | 通用免签配置 | Release 构建配置内置签名支持，输出即刻可安装运行的 APK (~10.9 MB) |

---

## 六、验收标准

| # | 验收项 | 方法 | 状态 |
|---|---|---|---|
| 1 | 编译通过 | `./gradlew assembleDebug` 与 `assembleRelease` 成功 | ✅ 通过 |
| 2 | 能装上并启动 | `adb install -r` + 启动无崩溃 | ✅ 通过 |
| 3 | 加载页动效正常 | 眨眼小电视与三色弹跳点 | ✅ 通过 |
| 4 | 合集列表与网页一致 | 合集网格 + 视频数 + 限时徽章 | ✅ 通过 |
| 5 | 分集列表有封面 | 网格卡片显示封面、集数、进度、搜索清除 | ✅ 通过 |
| 6 | **B站 条目能播放** | `/static/*.mp4`，断点续播与完播连播 | ✅ 通过 |
| 7 | **silidm 条目能播放** | `/api/hls/*`，HLS 起播即通过 | ✅ 通过 |
| 8 | 时长胶囊实时变化 | 顶部「今日已看」随播放累加 | ✅ 通过 |
| 9 | 家长门禁可拦截 | 点 🔒 弹出验证（合集页与分集页均支持） | ✅ 通过 |
| 10 | 转屏与全屏切换 | 支持横竖屏平滑过渡，影院全屏沉浸式切换 | ✅ 通过 |

---

## 七、后续路线

1. **自定义播放控件**（深度对齐 Plyr 精细皮肤）：可替换 Media3 原生默认控制条为深度定制 Compose 悬浮条
2. **拆 module**：`:core` / `:feature-tablet`，为电视端腾位置
3. **电视端**：新增 `:feature-tv`，D-pad 焦点 + 10 尺字号，manifest 加 `LEANBACK_LAUNCHER`
4. **离线缓存**：把已下载的 mp4 落到本地，弱网可播

