import re
import subprocess
import requests
import os

headers = {
    # 浏览器标识符
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/96.0.4664.45 Safari/537.36',
    # 防盗链
    'referer': 'https://www.bilibili.com/video/'
}


def get_response(url, params=None):
    """发送请求，并增加详细的错误捕获"""
    try:
        # 增加 timeout 参数，防止请求长时间卡死
        response = requests.get(url=url, params=params, headers=headers, timeout=10)
        response.raise_for_status()  # 如果请求返回的状态码不是2xx, 则引发HTTPError
        return response
    except requests.exceptions.RequestException as e:
        # 这是关键的修改：打印出具体的异常信息
        print(f"请求失败，具体错误: {e}")
        return None


def get_pname_and_save_to_file(bvid, cids, pages, names):
    """获取分P信息并保存到文件"""
    url = 'https://api.bilibili.com/x/player/pagelist?'
    param = {
        'bvid': bvid,
        'jsonp': 'jsonp'
    }
    # 注意这里调用 get_response 的方式也改变了
    response = get_response(url=url, params=param)
    if response:
        try:
            data = response.json()
            if data['code'] == 0:
                plist = data['data']
                with open('video_list.txt', 'w', encoding='utf-8') as f:
                    for p in plist:
                        cids.append(p['cid'])
                        pages.append(p['page'])
                        clean_name = re.sub(r'[\\/*?:"<>|]', "", p['part'])
                        names.append(clean_name)
                        f.write(f"BV: {bvid}, CID: {p['cid']}, Page: {p['page']}, Title: {clean_name}\n")
                print("分P列表已获取并保存到 video_list.txt")
                return True
            else:
                print(f"获取分P列表失败，B站返回信息: {data.get('message', '无')}")
                return False
        except (ValueError, KeyError) as e:
            print(f"解析分P列表JSON数据时出错: {e}")
            return False
    return False


def get_session(bvid, page):
    """request请求后 正则表达式session"""
    url = f'https://www.bilibili.com/video/{bvid}?p={page}'
    response = get_response(url=url)
    if response:
        session_match = re.search(r'"session":"(.*?)"', response.text)
        if session_match:
            return session_match.group(1)
    print("获取session失败")
    return None


def get_video_url(bvid, cid, session):
    """获取音视频链接"""
    url = 'https://api.bilibili.com/x/player/playurl'
    params = {
        'cid': cid,
        'bvid': bvid,
        'qn': '0',
        'type': '',
        'otype': 'json',
        'fourk': '1',
        'fnver': '0',
        'fnval': '976',
        'session': session
    }
    response = get_response(url=url, params=params)
    if response:
        try:
            data = response.json()
            if data['code'] == 0:
                audio_url = data['data']['dash']['audio'][0]['baseUrl']
                video_url = data['data']['dash']['video'][0]['baseUrl']
                print("音视频链接已得到")
                return [audio_url, video_url]
            else:
                print(f"获取音视频链接失败: {data.get('message', '无')}")
        except (ValueError, KeyError, IndexError) as e:
            print(f"解析音视频链接JSON数据时出错: {e}")
    return None


def save_video(name, audio_url, video_url):
    """保存数据 r.content获取二进制内容"""
    print(f"开始下载 {name} 的音频")
    audio_response = get_response(audio_url)
    if audio_response:
        with open(f"{name}.mp3", mode='wb') as af:
            af.write(audio_response.content)
        print(f"{name} 音频保存完成")

    print(f"开始下载 {name} 的视频")
    video_response = get_response(video_url)
    if video_response:
        with open(f"{name}.mp4", mode='wb') as vf:
            vf.write(video_response.content)
        print(f"{name} 视频保存完成")


def merge_audio_video(name):
    """音视频合并"""
    output_name = f"A_{name}.mp4"
    command = [
        'ffmpeg', '-i', f'{name}.mp4', '-i', f'{name}.mp3',
        '-c', 'copy', output_name
    ]
    print(f"正在为 {name} 执行合成命令...")
    try:
        # 使用 -loglevel error 来减少不必要的ffmpeg输出
        subprocess.run(command, shell=False, check=True, capture_output=True, text=True)
        print(f"{name} 视频合成完成，输出为 {output_name}")
        os.remove(f"{name}.mp3")
        os.remove(f"{name}.mp4")
        print(f"已删除临时的音视频文件 for {name}")
    except subprocess.CalledProcessError as e:
        print(f"合成视频时出错: {e}")
        print(f"FFmpeg的错误输出:\n{e.stderr}")
    except FileNotFoundError:
        print("错误: ffmpeg.exe 未找到。请确保它已安装并在系统路径中。")


if __name__ == '__main__':
    bvid = input("请输入Bilibili视频的BV号: ")
    cids = []
    pages = []
    names = []

    if get_pname_and_save_to_file(bvid, cids, pages, names):
        print(f"总共找到 {len(pages)} 个分P。")
        for p in range(len(pages)):
            print(f"\n--- 开始处理第 {p+1}/{len(pages)} P: {names[p]} ---")
            session = get_session(bvid, pages[p])
            if session:
                vc = get_video_url(bvid, cids[p], session)
                if vc:
                    save_video(names[p], vc[0], vc[1])
                    merge_audio_video(names[p])
