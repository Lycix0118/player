# B站 Cookie 配置文件示例
# 复制此文件为 backend/config.py 并填写您的 Cookie 即可
# 用于字幕解析、更高清晰度（如 1080P/大会员画质）等功能
# config.py 已被 .gitignore 忽略，不会被提交到版本库

# 获取方式：
# 1. 在电脑浏览器登录 bilibili.com
# 2. 按 F12 打开开发者工具
#    - 方法A（最稳妥）：点击顶部“应用程序”(Application) 或“存储”(Storage) -> 左侧展开“Cookie” -> 点击 https://www.bilibili.com
#      找到 SESSDATA 的值，格式为 SESSDATA=xxxxxx;
#    - 方法B：切换到“网络”(Network) 选项卡，刷新页面，点击任意请求（如 nav），在右侧标头的 Cookie 字段中全部复制
# 3. 核心：必须包含 SESSDATA=...; 否则B站API会当成未登录访客（锁480P画质）
# 4. 粘贴在下方引号内：

BILIBILI_COOKIE = """"""

# --- silidm.com（「电影先生」，苹果CMS 采集站）---
# list.txt 中允许写它的**详情页**（一行自动展开整季）或单集播放页：
#   https://silidm.com/video/42675.html        # 详情页 —— 推荐，一行搞定整季
#   https://silidm.com/play/42675-1-1.html     # 单集
# 该站播放页内联 player_aaaa JSON，url 字段就是 m3u8 明文直链：
# 无需解密、不校验 Referer；直链域名会轮换，代码每次从播放页现取。
# 站点换域名时只改这一项即可。
SILIDM_BASE = "https://silidm.com"
# 分片并行连接数。单连接被上游限速到 ~1Mbps（不够 3.8Mbps 码率），必须并行；
# 但连接太多会被重置 TLS（实测 8 路不稳），保守取 4。
SILIDM_SEGMENT_PARALLELISM = 4

# --- 磁盘与视频缓存管理策略 ---
# 视频缓存占用上限（单位: MB）。当视频总大小超过此阈值时，自动按 LRU（最近最少使用）淘汰旧视频
MAX_CACHE_SIZE_MB = 700

# 触发清理后回落的目标缓存大小（单位: MB）。保留最近播放的几集，避免频繁触发删除
TARGET_CACHE_SIZE_MB = 500

# 服务器剩余磁盘安全警戒线（单位: MB）。
# 即使视频缓存尚未达到上限，只要服务器剩余空间低于此值，也会自动触发紧急清理，防止磁盘被挤爆
MIN_FREE_DISK_MB = 800
