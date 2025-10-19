import json
import requests
import os
import time
from pathlib import Path

# 读取配置文件
with open('files.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

epg_urls = config.get('epg_url', {})
epg_dir = Path('epg')

# 确保目录存在
epg_dir.mkdir(exist_ok=True)

print(f"⬇️ 开始下载 {len(epg_urls)} 个EPG文件...")

success_count = 0
fail_count = 0

for filename, url in epg_urls.items():
    max_retries = 3
    retry_delay = 2  # 重试延迟秒数
    
    for attempt in range(max_retries):
        try:
            print(f"🚀 正在下载: {filename} (尝试 {attempt + 1}/{max_retries})")
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; GitHub-Actions-EPG-Downloader/1.0)',
                'Accept-Encoding': 'gzip'
            }
            
            # 下载文件
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()  # 如果状态码不是200会抛出异常
            
            # 保存文件
            file_path = epg_dir / filename
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content)
            print(f"✅ 成功下载: {filename} ({file_size} 字节)")
            success_count += 1
            break  # 成功则跳出重试循环
            
        except Exception as e:
            print(f"⚠️ 下载失败 {filename} (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            
            # 如果是最后一次尝试仍然失败
            if attempt == max_retries - 1:
                print(f"❌ 放弃下载 {filename}，已达到最大重试次数")
                fail_count += 1
            else:
                # 不是最后一次失败，等待后重试
                print(f"⏳️ 等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # 指数退避策略

print(f"\n🎉 下载完成: 成功 {success_count} 个, 失败 {fail_count} 个")

# 如果有失败的文件，以代码0退出（不中断工作流）
exit(0)

