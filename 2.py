import requests
import re
import json
import os

def get_bilibili_video_covers(bvid):
    """
    根据Bilibili视频的BV号，获取并下载所有分P的封面图片。

    参数:
        bvid (str): Bilibili视频的BV号 (例如: "BV1LnuzzyEQp")。
    """
    # 1. 构建视频页面URL并发起请求
    url = f"https://www.bilibili.com/video/{bvid}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.bilibili.com/'
    }

    try:
        print(f"正在获取BV号为 {bvid} 的视频页面...")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # 如果请求失败则抛出异常
        html_content = response.text

        # 2. 使用正则表达式查找并提取包含视频信息的JSON数据
        match = re.search(r'<script>window\.__INITIAL_STATE__=(.*?);\(function\(\)', html_content)
        if not match:
            print("错误：在页面源代码中未找到视频数据。")
            return

        json_data_string = match.group(1)

        # 3. 解析JSON数据
        data = json.loads(json_data_string)

        # 4. 提取视频分P列表
        video_parts = data.get('videoData', {}).get('pages', [])
        if not video_parts:
            print(f"未找到BV号 {bvid} 的分P视频。")
            return
            
        video_title = data.get('videoData', {}).get('title', bvid)
        # 清理标题中的非法字符，以便作为文件夹名称
        safe_folder_name = re.sub(r'[\\/*?:"<>|]', "", video_title)

        # 创建一个以视频标题命名的文件夹来保存图片
        if not os.path.exists(safe_folder_name):
            os.makedirs(safe_folder_name)

        print(f"找到 {len(video_parts)} 个分P视频。开始下载封面...")

        # 5. 遍历所有分P，打印信息并下载封面
        for part in video_parts:
            part_number = part.get('page')
            part_title = part.get('part')
            # 清理分P标题中的非法字符，以便作为文件名
            safe_part_title = re.sub(r'[\\/*?:"<>|]', "", part_title)
            cover_url = part.get('first_frame')

            if cover_url:
                # 确保URL协议完整 (有些URL可能以 // 开头)
                if cover_url.startswith('//'):
                    cover_url = 'http:' + cover_url
                    
                print(f"\n分P {part_number}: {part_title}")
                print(f"  封面链接: {cover_url}")

                try:
                    # 下载图片
                    img_response = requests.get(cover_url, headers=headers, timeout=15)
                    img_response.raise_for_status()
                    
                    # 获取图片文件后缀名
                    file_extension = os.path.splitext(cover_url)[1].split('@')[0]
                    if not file_extension:
                         file_extension = '.jpg' # 默认后缀
                         
                    # 创建文件名并保存
                    file_name = f"{part_number:03d}_{safe_part_title}{file_extension}"
                    file_path = os.path.join(safe_folder_name, file_name)

                    with open(file_path, 'wb') as f:
                        f.write(img_response.content)
                    print(f"  封面已保存至: {file_path}")

                except requests.exceptions.RequestException as e:
                    print(f"  下载图片失败: {e}")
            else:
                print(f"\n分P {part_number}: {part_title}")
                print("  未找到封面链接。")

    except requests.exceptions.RequestException as e:
        print(f"获取页面时发生错误: {e}")
    except json.JSONDecodeError:
        print("错误：解析页面中的JSON数据失败。")
    except Exception as e:
        print(f"发生未知错误: {e}")


# --- 使用示例 ---
# 根据您提供的图片和代码中的信息，BV号为 BV1LnuzzyEQp
if __name__ == "__main__":
    bv_id = "BV1LnuzzyEQp"
    get_bilibili_video_covers(bv_id)
