# 儿童视频播放器（Bilibili）

一个包含后端（FastAPI）与前端静态页面的本地视频播放器工具：
- 后端负责：目录扫描、分阶段加载分P信息、封面缓存、字幕获取与缓存、按需下载并合并视频音频（ffmpeg）。
- 前端负责：文件夹浏览、视频列表展示、封面懒加载、播放器（Plyr）与字幕显示。

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
  - bilibili_downloader.py: 独立的异步下载器（如需单独使用）
  - requirements.txt: 依赖列表
- frontend/
  - index.html, styles.css, app.js: 前端页面与逻辑
  - icon-192x192.png: 图标
- videos/: 放置每个专辑（文件夹），每个文件夹包含一个 list.txt（内含 B 站链接或 BV 号）
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

## 使用

1) 在 `videos/` 下创建一个文件夹，例如 `PeppaPig/`，并在其中建立 `list.txt`，内容示例：

```
https://www.bilibili.com/video/BV1xxxxxxx
# 也可以直接写 BV 号：
BV1xxxxxxx
```

只读取第一行作为该专辑的 BV 源（其余行可作为注释或备用）。

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
- 播放时：若本地已存在合并后的视频文件，直接播放；否则临时下载音频/视频并用 ffmpeg 合并，然后播放。

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
- GET /api/play/{folder_path}/{page}: 按需下载并播放（返回本地播放 URL）
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
