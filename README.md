# 儿童视频播放器（Bilibili + 电影先生）

一个包含后端（FastAPI）与前端静态页面的本地视频播放器工具：
- 后端负责：目录扫描、分阶段加载分P信息、封面缓存、字幕获取与缓存、B 站按需下载并合并视频音频（ffmpeg）、外部来源（silidm / 电影先生）m3u8 播放列表与分片代理。
- 前端负责：文件夹浏览、视频列表展示、封面懒加载、播放器（Plyr）与字幕显示、外部来源 HLS 流式播放（hls.js）。

> 视频来源只有两个：**B 站**（官方接口）与 **silidm.com（电影先生）**（苹果 CMS 采集站）。
> 早期接入的爱奇艺第三方解析链路已**整体移除**（解析站不稳定，且对动画剧集覆盖率差）。

本项目已进行维护：
- 清理冗余代码与无用导入；
- 修复模型中的可变默认值与时间戳默认值；
- 合并调用使用更安全的 `subprocess.run([...], shell=False)`；
- 注释更清晰，函数职责更明确；
- requirements 增补 pydantic。

## 目录结构

- backend/
  - main.py: FastAPI 应用与业务逻辑
  - models.py: Pydantic 模型
  - start_server.py: 启动脚本（开发时热重载）
  - silidm.py: 外部来源（电影先生）的取流实现（解析播放页、展开整季、分片代理与 ffmpeg 拉流）
  - bilibili_downloader.py: 独立的异步下载器（如需单独使用）
  - requirements.txt: 依赖列表
- frontend/
  - index.html: 唯一入口页面
  - js/: 前端模块（main.js 为入口，按 api/ state/ views/ components/ utils/ 分目录）
  - styles/: 分模块样式
  - vendor/: 本地化的第三方库（plyr.js / plyr.css / hls.min.js），保证离线与 LAN 可用
  - icon-192x192.png: 图标
- videos/: 放置每个专辑（文件夹），每个文件夹包含一个 list.txt（一行一个视频，可混写 B 站与 silidm 链接）
- covers/: 封面缓存（运行时生成）
- subtitles/: 字幕缓存（运行时生成）

## 环境要求

- Python 3.9+
- ffmpeg 可执行文件（需在 PATH 中）
- Windows、macOS 或 Linux 均可

## 安装

1) 创建虚拟环境并安装依赖（Windows PowerShell）：

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

2) 准备目录：首次运行会自动创建 `videos/`、`covers/`、`subtitles/` 目录。

## 可选配置（字幕）

如需启用字幕获取能力（通过 B 站用户 Cookie 调用字幕接口），在 `backend` 目录下创建 `config.py`：

```
# backend/config.py
BILIBILI_COOKIE = "你的B站Cookie"
```

注意：
- Cookie 含敏感信息，请勿提交到版本库。
- 未配置 Cookie 时，字幕功能不可用，但其他功能正常。

## 播放方式：流式（边下边播）

外部来源条目（silidm）默认走 **HLS 流式播放**，与 B 站的「下载合并 mp4」是两条不同链路：

| | B 站条目 | 外部来源条目（silidm） |
|---|---|---|
| 播放方式 | 下载 + ffmpeg 合并成本地 mp4 | HLS 流式（hls.js 边下边播） |
| 起播等待 | 需等整集下载完（几十秒～几分钟） | 约 3～5 秒 |
| 拖动进度条 | 本地文件，即时响应 | 需缓冲目标分片，约 1～3 秒 |
| 本地缓存 | 生成 mp4，计入缓存配额 | **不落盘**，不占配额 |
| 字幕 | 支持（需 Cookie） | 无 |

数据流向：后端代理 m3u8 文本（`/api/hls/{id}/index.m3u8`）**以及每个视频分片**
（`/api/hls/{id}/seg/{序号}.ts`）；分片由后端用**多条 Range 请求并行拉取**后再返回。

为什么分片也要代理：上游 CDN 对**单条连接**限速（实测 0.7～1.2 Mbps），低于流的码率
（3.5～3.8 Mbps），浏览器直连必然反复卡顿；而同一 CDN 的总吞吐可达 8～15 Mbps。
把单个分片拆成若干段并行下载再拼接后，实测单分片耗时从 3.3 秒降到 0.9 秒。
并行连接数由 `backend/config.py` 的 `SILIDM_SEGMENT_PARALLELISM` 控制（默认 4）。

若某条外部来源视频此前已经下载成 mp4（`<专辑>/<id>_p<page>.mp4`），仍会**优先播放本地文件**
（省流量、可离线），不会重复走流式。

注意：
- 代理分片会把视频流量搬到后端。部署在同一台机器/局域网内时前后端带宽充裕，属净收益；
  若后端出口很窄，可调低 `SILIDM_SEGMENT_PARALLELISM`。
- 带 `#EXT-X-KEY` / `#EXT-X-MAP` 的流不做代理，保持浏览器直连（这类流的 URI 不是 ts 分片）。
- 该链路属于灰色方案，仅限个人/家庭自用；VIP 内容通常拿不到。
- 外部来源条目**无字幕**；播放进度为本地记录。

## 可选配置（silidm 源 / 电影先生）

[`silidm.com`](https://silidm.com)（站点名「电影先生」）是一个苹果 CMS 采集站，取流链路很简单：
播放页内联 `player_aaaa` JSON，`url` 字段就是 m3u8 明文直链（`encrypt: 0`，**无需解密**，
因此没有 `cryptography` 之类的依赖），也不校验 Referer，实测画质 1080p / 约 3.5～3.8 Mbps。

```
# backend/config.py
SILIDM_BASE = "https://silidm.com"        # 站点换域名时只改这一项
SILIDM_SEGMENT_PARALLELISM = 4            # 分片并行连接数（见下方说明）
```

`list.txt` 里支持三种写法：

```
https://silidm.com/video/42675.html      # 详情页 —— 一行自动展开整季（推荐）
https://silidm.com/play/42675-1-1.html   # 单集播放页
https://silidm.com/play/42675.html       # 上面那种的简写，等价于 -1-1
第7集 自定义标题 | https://silidm.com/play/42675-1-7.html
```

- 详情页会按「集数最多的播放源」展开整季；不同视频在该站的可用源不一样，
  有的只有单一源（如「奇妙萌可之闪耀流星」只有第 1 源/凌点，26 集齐全），源真失效时该视频才会打不开。
- 无法识别的 http 链接会在服务端日志打印一行 `[list.txt] 无法识别的视频来源`，
  方便排查。**不支持静默跳过** —— 早期版本会静默丢弃，写错格式时只表现为「合集莫名变空」。
- 直链域名会在 `fengbao13.com` / `bfeng11.com` 等之间轮换，代码**每次都从播放页现取**，
  不会把域名写死。
- 分片常是相对路径，且可能是嵌套 master playlist（`index.m3u8` → `2000k/hls/mixed.m3u8`），
  取流时会递归展开并补成绝对地址。
- **并行度不要调大**：该站上游对单连接限速（约 1 Mbps，低于 3.8 Mbps 码率），
  所以必须并行；但连接数一多（实测 8 路）上游会直接重置 TLS（`SSLEOFError`）。
  并且分片下载走**连接池复用**——不复用连接时实测失败率高达 1/3。
  当前默认 4 路 + 连接池，实测 40 秒播放缓冲稳定在 30 秒左右、仅首帧卡顿 1 次。

## 使用

1) 在 `videos/` 下创建一个文件夹，例如 `PeppaPig/`，并在其中建立 `list.txt`。
   **一行一个视频**，B 站与 silidm 可以任意混排：

```
https://www.bilibili.com/video/BV1xxxxxxx
BV1xxxxxxx
https://silidm.com/video/42675.html          # silidm 详情页：一行展开整季
https://silidm.com/play/42675-1-1.html       # silidm 单集
https://silidm.com/video/42675.html | albumid=6706607840549001  # 可选：爱奇艺专辑元数据
# 以 # 开头的是注释，空行忽略
# 需要自定义标题时用 | 分隔（放在链接任意一侧都行）：
第1集 露营好时光 | https://silidm.com/play/42675-1-1.html
```

- 每行解析成一个条目，按 list.txt 的先后顺序编号；重复条目自动去重。
- B 站条目支持 BV 号与视频链接；单个 BV 含多个分 P 时会自动展开成多集。
- silidm 条目支持**详情页**（`/video/<id>.html`，自动展开整季）、**单集播放页**
  （`/play/<id>-<源号>-<集号>.html`）以及简写（`/play/<id>.html`）；
  标题与封面默认取自详情页。链接后追加 `| albumid=<爱奇艺专辑ID>` 后，
  会按集数使用爱奇艺返回的真实集名和独立封面；元数据不可用时自动回退到 Silidm。

2) 启动后端服务（开发模式，热重载）：

```
python backend\start_server.py
```

或直接运行（无热重载）：

```
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

3) 打开前端：

浏览器访问 http://localhost:8000/ 即可。

- 顶部“文件夹”页展示 `videos/` 下的专辑文件夹。
- 点击进入某个专辑后，会分阶段加载分 P 基本信息与封面。
- 播放时：若本地已存在合并后的视频文件，直接播放；否则 B 站条目会临时下载音频/视频并用 ffmpeg 合并后播放，
  silidm 条目则直接走 HLS 流式播放（边下边播，约 3～5 秒起播）。

## 常见问题

- 403/429 或访问受限：已内置简易 QPS 与冷却策略，仍可能受 B 站策略影响，可降低并发或放慢请求速率（环境变量 OUTBOUND_MAX_QPS、OUTBOUND_MAX_CONCURRENCY）。
- 字幕无法获取：需要配置有效的 B 站 Cookie；且仅当视频存在用户字幕时可用。
- ffmpeg 未找到：请安装 ffmpeg 并确保其所在目录在系统 PATH 中。

## 接口速览

- GET /api/folders: 获取顶级文件夹
- GET /api/folders?path=子路径: 获取指定路径下的直接子文件夹
- GET /api/folders/{folder_path}: 获取分 P 基本信息
- GET /api/folders/{folder_path}/details: 获取包含封面与字幕可用性的详细信息
- GET /api/cover/{bvid}/{page}: 获取并缓存某分 P 的封面
- POST /api/covers/preload: 批量预加载封面
- GET /api/play/{folder_path}/{page}: 按需准备播放（B 站返回本地 mp4 URL，外部来源返回 m3u8 代理地址）
- GET /api/hls/{episode_id}/index.m3u8: 外部来源（silidm）流式播放的 m3u8 代理
  （转发播放列表，分片地址改写为后端代理；`episode_id` 前缀决定用哪个来源的解析器）
- GET /api/hls/{episode_id}/seg/{index}.ts: 外部来源 HLS 分片代理（多连接 Range 并行拉取后返回）
- GET /api/subtitle/{folder_path}/{page}: 下载并返回字幕 URL
- GET /api/progress/{folder_path}: 获取合集内所有观看进度
- POST /api/progress: 保存观看进度（folder_path、bvid、page、position、duration）
- POST /api/download/{folder_path}/{item_index}: 创建异步下载任务，返回 task_id
- GET /api/download/tasks/{task_id}: 查询下载阶段和真实进度
- GET /api/settings/cookie/status: 家长区 Cookie 状态
- POST /api/settings/cookie: 家长区保存 B 站 Cookie
- GET /api/cache/status: 家长区缓存状态
- POST /api/cache/clean: 家长区清理视频缓存
- 静态文件：/static/...、/covers/...、/subtitles/...

## 开发说明

- 代码风格：已避免 Pydantic 可变默认值陷阱，时间戳使用 Field(default_factory=...)。
- 合并命令：使用 `subprocess.run([...], shell=False)`，更安全。
- 异步与限流：对外呼做了并发/速率与冷却控制，尽量减少被限流风险。

## 许可证

仅用于学习与个人使用。请遵循 B 站及相关内容版权与使用条款。
