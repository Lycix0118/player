import requests
import re
import json
import os
import time
from functools import reduce
from hashlib import md5

# --- 在这里粘贴您的完整Cookie ---
# 警告：Cookie包含您的个人登录信息，请勿分享给他人！
# Cookie会过期，如果脚本失效，请从浏览器开发者工具中获取最新的Cookie并替换。
YOUR_COOKIE = os.getenv("BILIBILI_COOKIE", "")



# --- WBI签名相关函数 (无需修改) ---
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def get_mixin_key(orig: str):
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]

def get_wbi_keys(session):
    try:
        resp = session.get('https://api.bilibili.com/x/web-interface/nav', timeout=15)
        resp.raise_for_status()
        json_content = resp.json()
        img_url: str = json_content['data']['wbi_img']['img_url']
        sub_url: str = json_content['data']['wbi_img']['sub_url']
        img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
        return get_mixin_key(img_key + sub_key)
    except Exception as e:
        print(f"获取WBI密钥失败: {e}")
        return None

def sign_wbi_params(params: dict, wbi_key: str):
    params['wts'] = str(int(time.time()))
    sorted_params = dict(sorted(params.items()))
    query_parts = []
    for k, v in sorted_params.items():
        v_str = str(v).replace("'", "").replace("!", "").replace("(", "").replace(")", "").replace("*", "")
        query_parts.append(f'{k}={v_str}')
    query_string = '&'.join(query_parts)
    w_rid = md5((query_string + wbi_key).encode()).hexdigest()
    params['w_rid'] = w_rid
    return params

def convert_seconds_to_lrc_time(seconds):
    millisec = int((seconds - int(seconds)) * 100)
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"[{minutes:02d}:{sec:02d}.{millisec:02d}]"

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def get_bilibili_subtitle(bvid, p_number, cookie):
    """
    根据B站BV号和分P号，下载用户上传的字幕并保存为LRC文件。
    (已集成WBI签名和Cookie)
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Referer': f'https://www.bilibili.com/video/{bvid}',
        'Cookie': cookie  # <--- 在这里加入了您的Cookie
    })

    try:
        # Step 1: 获取视频页面信息
        video_page_url = f"https://www.bilibili.com/video/{bvid}"
        print(f"正在访问视频页面: {video_page_url}")
        response = session.get(video_page_url, timeout=15)
        response.raise_for_status()
        
        match = re.search(r'<script>window\.__INITIAL_STATE__=(.*?);\(function\(\)', response.text)
        if not match:
            print("错误：无法在页面源码中找到视频信息。")
            return

        initial_state = json.loads(match.group(1))
        video_data = initial_state.get('videoData', {})
        video_title = video_data.get('title', bvid)
        video_parts = video_data.get('pages', [])

        if not video_parts or p_number > len(video_parts):
            print(f"错误：找不到BV号 {bvid} 的分P {p_number}。")
            return

        target_part = video_parts[p_number - 1]
        cid = target_part.get('cid')
        part_title = target_part.get('part', f'P{p_number}')
        print(f"成功获取信息：视频='{video_title}', P{p_number}='{part_title}', cid={cid}")

        # Step 2: WBI签名并请求API
        print("正在获取WBI签名密钥...")
        wbi_key = get_wbi_keys(session)
        if not wbi_key: return

        params = {'bvid': bvid, 'cid': cid}
        signed_params = sign_wbi_params(params, wbi_key)
        
        player_api_url = "https://api.bilibili.com/x/player/wbi/v2"
        print(f"正在获取 P{p_number} 的字幕列表 (已WBI签名并携带Cookie)...")
        response = session.get(player_api_url, params=signed_params, timeout=15)
        response.raise_for_status()
        subtitle_data = response.json()

        if subtitle_data.get('code') != 0:
            print(f"API返回错误：Code: {subtitle_data.get('code')}, Message: {subtitle_data.get('message')}")
            if subtitle_data.get('code') == -10403: print("提示：可能是Cookie失效或IP被限制。")
            return

        subtitles_list = subtitle_data.get('data', {}).get('subtitle', {}).get('subtitles', [])
        if not subtitles_list:
            print(f"API调用成功，但 P{p_number} 没有任何可用字幕。")
            return

        # Step 3: 筛选并下载用户字幕
        user_subtitle = next((s for s in subtitles_list if s.get('ai_type') == 0 and s.get('subtitle_url')), None)
        
        if not user_subtitle:
            print(f"未在 P{p_number} 中找到用户上传的字幕。")
            return

        print(f"成功找到用户上传的字幕: '{user_subtitle.get('lan_doc')}'")
        subtitle_url = user_subtitle.get('subtitle_url')
        if subtitle_url.startswith('//'):
            subtitle_url = 'https:' + subtitle_url

        # Step 4: 保存为LRC文件
        print("正在下载字幕文件...")
        response = session.get(subtitle_url, timeout=15)
        response.raise_for_status()
        subtitle_content = response.json()

        folder_name = sanitize_filename(video_title)
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        lrc_filename = f"{p_number:02d}_{sanitize_filename(part_title)}.lrc"
        file_path = os.path.join(folder_name, lrc_filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            for line in subtitle_content.get('body', []):
                f.write(f"{convert_seconds_to_lrc_time(line.get('from'))}{line.get('content')}\n")
        
        print(f"成功！字幕已保存至: {file_path}")

    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
    except json.JSONDecodeError as e:
        print(f"错误：解析JSON数据失败。 {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")


# --- 使用示例 ---
if __name__ == "__main__":
    bv_id = "BV1LnuzzyEQp"
    part_number = 2
    
    if not YOUR_COOKIE:
        print("错误：请在脚本顶部的 YOUR_COOKIE 变量中填入您的B站Cookie。")
    else:
        get_bilibili_subtitle(bv_id, part_number, YOUR_COOKIE)
