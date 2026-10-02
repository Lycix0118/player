#!/usr/bin/env python3
"""
启动服务器脚本
"""
import uvicorn
from pathlib import Path

def main():
    BASE_DIR = Path(__file__).resolve().parent.parent
    videos_dir = BASE_DIR / "videos"
    videos_dir.mkdir(exist_ok=True)
    
    # 启动服务器
    print("🚀 启动儿童视频播放器后端服务...")
    print(f"📁 视频目录: {videos_dir.resolve()}")
    print("🌐 服务地址: http://localhost:8000")
    print("📖 API文档: http://localhost:8000/docs")
    print("🔄 按 Ctrl+C 停止服务")
    print("-" * 50)
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parent)],
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 服务已停止")

if __name__ == "__main__":
    main()