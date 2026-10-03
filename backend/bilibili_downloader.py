import re
import asyncio
import aiohttp
import aiofiles
import subprocess
import os
from pathlib import Path
from typing import Optional, Callable, List, Dict
import json
try:
    from .models import VideoInfo
except ImportError:
    from models import VideoInfo

class BilibiliDownloader:
    """异步B站视频下载器"""
    
    def __init__(self):
        self.headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/96.0.4664.45 Safari/537.36',
            'referer': 'https://www.bilibili.com/video/'
        }
        self.session = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def get_session(self):
        """获取或创建session"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session
    
    async def get_video_info(self, bv_id: str) -> Optional[VideoInfo]:
        """获取视频基本信息"""
        try:
            session = await self.get_session()
            url = f'https://api.bilibili.com/x/web-interface/view?bvid={bv_id}'
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['code'] == 0:
                        video_data = data['data']
                        return VideoInfo(
                            bv_id=bv_id,
                            title=self._clean_filename(video_data['title']),
                            duration=self._format_duration(video_data['duration']),
                            thumbnail=video_data['pic'],
                            upload_date=video_data.get('pubdate', ''),
                            is_downloaded=False
                        )
        except Exception as e:
            print(f"获取视频信息失败: {e}")
        return None
    
    async def get_video_pages(self, bv_id: str) -> List[Dict]:
        """获取视频分P信息"""
        try:
            session = await self.get_session()
            url = 'https://api.bilibili.com/x/player/pagelist'
            params = {'bvid': bv_id, 'jsonp': 'jsonp'}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['code'] == 0:
                        return data['data']
        except Exception as e:
            print(f"获取分P信息失败: {e}")
        return []
    
    async def get_page_session(self, bv_id: str, page: int = 1) -> Optional[str]:
        """获取页面session"""
        try:
            session = await self.get_session()
            url = f'https://www.bilibili.com/video/{bv_id}?p={page}'
            
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    session_match = re.search(r'"session":"(.*?)"', text)
                    if session_match:
                        return session_match.group(1)
        except Exception as e:
            print(f"获取session失败: {e}")
        return None
    
    async def get_video_urls(self, bv_id: str, cid: str, session_id: str) -> Optional[List[str]]:
        """获取视频下载链接"""
        try:
            session = await self.get_session()
            url = 'https://api.bilibili.com/x/player/playurl'
            params = {
                'cid': cid,
                'bvid': bv_id,
                'qn': '0',
                'type': '',
                'otype': 'json',
                'fourk': '1',
                'fnver': '0',
                'fnval': '976',
                'session': session_id
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['code'] == 0:
                        dash_data = data['data']['dash']
                        audio_url = dash_data['audio'][0]['baseUrl']
                        video_url = dash_data['video'][0]['baseUrl']
                        return [audio_url, video_url]
        except Exception as e:
            print(f"获取视频链接失败: {e}")
        return None
    
    async def download_file(self, url: str, filepath: str, progress_callback: Optional[Callable] = None) -> bool:
        """下载文件"""
        try:
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    async with aiofiles.open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback and total_size > 0:
                                progress = int((downloaded / total_size) * 100)
                                progress_callback(progress)
                    
                    return True
        except Exception as e:
            print(f"下载文件失败: {e}")
        return False
    
    async def download_video(self, bv_id: str, output_dir: str, progress_callback: Optional[Callable] = None) -> bool:
        """下载视频（主函数）"""
        try:
            # 获取视频信息
            video_info = await self.get_video_info(bv_id)
            if not video_info:
                return False
            
            # 获取分P信息
            pages = await self.get_video_pages(bv_id)
            if not pages:
                return False
            
            # 处理第一个分P（简化处理）
            page = pages[0]
            cid = page['cid']
            page_num = page['page']
            title = self._clean_filename(page['part'] or video_info.title)
            
            # 获取session
            session_id = await self.get_page_session(bv_id, page_num)
            if not session_id:
                return False
            
            # 获取下载链接
            urls = await self.get_video_urls(bv_id, cid, session_id)
            if not urls:
                return False
            
            audio_url, video_url = urls
            
            # 创建输出目录
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)
            
            # 下载音频和视频
            audio_file = output_path / f"{title}.mp3"
            video_file = output_path / f"{title}.mp4"
            
            print(f"开始下载音频: {title}")
            if progress_callback:
                progress_callback(10)
            
            if not await self.download_file(audio_url, str(audio_file)):
                return False
            
            if progress_callback:
                progress_callback(50)
            
            print(f"开始下载视频: {title}")
            if not await self.download_file(video_url, str(video_file)):
                return False
            
            if progress_callback:
                progress_callback(80)
            
            # 合并音视频
            output_file = output_path / f"A_{title}.mp4"
            if await self.merge_audio_video(str(video_file), str(audio_file), str(output_file)):
                # 删除临时文件
                os.remove(str(audio_file))
                os.remove(str(video_file))
                
                if progress_callback:
                    progress_callback(100)
                
                print(f"视频下载完成: {output_file}")
                return True
            
        except Exception as e:
            print(f"下载视频失败: {e}")
        
        return False
    
    async def merge_audio_video(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """合并音视频"""
        try:
            command = [
                'ffmpeg', '-i', video_path, '-i', audio_path,
                '-c', 'copy', output_path, '-y'
            ]
            
            # 在线程池中运行ffmpeg
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(
                None, 
                lambda: subprocess.run(command, capture_output=True, text=True)
            )
            
            return process.returncode == 0
            
        except Exception as e:
            print(f"合并音视频失败: {e}")
            return False
    
    def _clean_filename(self, filename: str) -> str:
        """清理文件名"""
        return re.sub(r'[\\/*?:"<>|]', "", filename)
    
    def _format_duration(self, seconds: int) -> str:
        """格式化时长"""
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
