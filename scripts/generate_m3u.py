import requests
import json
import re
import os
import time
import random
import chardet  # 用于检测编码
from zhconv import convert  # 用于简繁转换

# 默认请求头
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# 常见的浏览器 User-Agent 列表
BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
]

def fetch_url(url, description="数据", encoding=None, referer=None, user_agent=None, max_retries=3):
    """通用URL请求函数"""
    headers = DEFAULT_HEADERS.copy()
    
    # 设置 User-Agent
    if user_agent:
        headers["User-Agent"] = user_agent
    else:
        headers["User-Agent"] = random.choice(BROWSER_USER_AGENTS)
    
    # 添加 Referer 头（如果提供）
    if referer is not None:  # 注意：空字符串也是有效值
        headers["Referer"] = referer
    else:
        # 如果没有提供 Referer，使用 URL 的域名作为默认 Referer
        try:
            domain = re.search(r'https?://([^/]+)', url).group(1)
            headers["Referer"] = f"https://{domain}/"
        except:
            pass
    
    # 添加其他可能的请求头
    headers["DNT"] = "1"
    headers["Sec-GPC"] = "1"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # 获取原始字节数据
            content_bytes = response.content
            
            # 如果指定了编码，使用指定编码
            if encoding:
                try:
                    return content_bytes.decode(encoding)
                except UnicodeDecodeError:
                    print(f"使用指定编码 {encoding} 解码失败，尝试自动检测")
            
            # 尝试自动检测编码
            detected = chardet.detect(content_bytes)
            if detected['confidence'] > 0.7:
                try:
                    return content_bytes.decode(detected['encoding'])
                except UnicodeDecodeError:
                    print(f"使用检测到的编码 {detected['encoding']} 解码失败，尝试其他编码")
            
            # 尝试常见的中文编码
            encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'latin-1']
            
            for enc in encodings_to_try:
                try:
                    return content_bytes.decode(enc)
                except UnicodeDecodeError:
                    continue
            
            # 如果所有尝试都失败，使用 UTF-8 并忽略错误
            return content_bytes.decode('utf-8', errors='ignore')
                
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + random.random()  # 指数退避策略
                print(f"获取{description}失败 (尝试 {attempt + 1}/{max_retries}): {e}. 等待 {wait_time:.2f} 秒后重试...")
                time.sleep(wait_time)
                
                # 每次重试时更换 User-Agent
                headers["User-Agent"] = random.choice(BROWSER_USER_AGENTS)
            else:
                print(f"获取{description}失败: {e}")
                return None
        except Exception as e:
            print(f"获取{description}失败: {e}")
            return None
    
    return None

def fix_unicode_escape(text):
    """修复Unicode转义序列"""
    if not text:
        return text
    
    # 检查是否包含Unicode转义序列
    if '\\u' in text:
        try:
            # 尝试将Unicode转义序列转换为实际字符
            return text.encode('utf-8').decode('unicode_escape')
        except:
            pass
    
    return text

def normalize_channel_name(name):
    """标准化频道名称（转简体并小写）"""
    if not name:
        return ""
    return convert(name.lower(), 'zh-cn')

def process_single_source(output_filename, source_config, epg_channels, logo_sources):
    """处理单个直播源"""
    list_url = source_config["url"]
    user_agent = source_config.get("user_agent")
    referer = source_config.get("referer")
    encoding = source_config.get("encoding")  # 从配置中获取编码
    
    # 对于特别难以访问的源，增加重试次数
    max_retries = 5 if "catvod.com" in list_url else 3
    
    list_data = fetch_url(list_url, f"频道列表({output_filename})", encoding, referer, user_agent, max_retries)
    
    if not list_data:
        return False
    
    # 解析列表数据并生成M3U
    current_group = "默认分组"
    m3u_lines = ["#EXTM3U"]
    line_count = 0
    valid_channel_count = 0
    
    for line in list_data.splitlines():
        line = line.strip()
        line_count += 1
        
        # 跳过空行
        if not line:
            continue
            
        # 检查是否是分组行 (支持多种格式)
        if line.endswith(",#genre#") or line.endswith(",genre") or re.search(r",#?\w*genre\w*#?$", line):
            current_group = re.sub(r",#?\w*genre\w*#?$", "", line)
            # 尝试修复Unicode转义序列
            current_group = fix_unicode_escape(current_group)
            print(f"检测到分组: {current_group} (第{line_count}行)")
            continue
            
        # 解析频道行 - 尝试多种分隔符
        parts = None
        separators = [",", " ", "\t"]
        
        for sep in separators:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) >= 2:
                    break
        
        if not parts or len(parts) < 2:
            print(f"警告: 无法解析第{line_count}行: {line}")
            continue
            
        channel_name, channel_url = parts
        channel_name = channel_name.strip()
        channel_url = channel_url.strip()
        
        # 尝试修复Unicode转义序列
        channel_name = fix_unicode_escape(channel_name)
        
        # 跳过无效的频道行
        if not channel_name or not channel_url:
            print(f"警告: 跳过无效的频道行(第{line_count}行): {line}")
            continue
            
        norm_channel_name = normalize_channel_name(channel_name)
        
        # 匹配EPG信息 - 按顺序查找，找到第一个匹配的
        tvg_id = ""
        tvg_name = ""
        tvg_logo = ""
        
        # 按顺序遍历EPG频道列表
        for epg_channel in epg_channels:
            epg_norm_name = normalize_channel_name(epg_channel["channel_name"])
            if epg_norm_name == norm_channel_name:
                tvg_id = epg_channel["channel_id"]
                tvg_name = epg_channel["channel_name"]
                break
        
        # 匹配Logo - 按顺序查找，找到第一个匹配的
        for logo_map in logo_sources:
            if norm_channel_name in logo_map:
                tvg_logo = logo_map[norm_channel_name]
                break
        
        # 构建M3U条目
        attr_parts = []
        if tvg_id:
            attr_parts.append(f'tvg-id="{tvg_id}"')
        if tvg_name:
            attr_parts.append(f'tvg-name="{tvg_name}"')
        if tvg_logo:
            attr_parts.append(f'tvg-logo="{tvg_logo}"')
        if current_group:
            attr_parts.append(f'group-title="{current_group}"')
        
        attrs = " ".join(attr_parts)
        m3u_lines.append(f'#EXTINF:-1 {attrs},{channel_name}')
        m3u_lines.append(channel_url)
        valid_channel_count += 1
    
    # 写入文件
    if valid_channel_count > 0:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(m3u_lines))
        
        print(f"M3U文件已生成: {output_filename} (包含{valid_channel_count}个频道)")
        return True
    else:
        print(f"警告: 源 {list_url} 没有有效的频道数据")
        return False

def main():
    """主处理函数"""
    # 1. 读取配置文件
    config_path = os.path.join(os.path.dirname(__file__), "..", "files.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"读取配置文件失败: {e}")
        return False
    
    snow_epg_json = config.get("snow_epg_json")
    live_urls = config.get("live_url", {})
    logo_jsons = config.get("logo_json", [])
    
    if not snow_epg_json or not live_urls:
        print("配置文件缺少必要字段")
        return False
    
    # 2. 获取EPG数据
    epg_data = fetch_url(snow_epg_json, "EPG信息")
    epg_channels = []
    if epg_data:
        try:
            epg_channels = json.loads(epg_data)
            # 统计原始EPG频道数量（不忽略大小写）
            original_count = len(epg_channels)
            
            # 创建标准化名称到原始频道的映射（用于统计）
            norm_name_count = {}
            for channel in epg_channels:
                norm_name = normalize_channel_name(channel["channel_name"])
                norm_name_count[norm_name] = norm_name_count.get(norm_name, 0) + 1
            
            # 统计去重后的EPG频道数量
            unique_count = len(norm_name_count)
            
            print(f"成功加载EPG数据，包含 {original_count} 个频道（{unique_count} 个唯一频道）")
        except Exception as e:
            print(f"解析EPG数据失败: {e}")
            epg_channels = []
    else:
        print("警告: 无法获取EPG数据，将跳过EPG匹配")
    
    # 3. 获取所有logo数据
    logo_sources = []
    for logo_url in logo_jsons:
        logo_data = fetch_url(logo_url, f"Logo数据({logo_url})")
        if logo_data:
            try:
                logos = json.loads(logo_data)
                logo_map = {}
                for logo in logos:
                    norm_name = normalize_channel_name(logo["logo_name"])
                    logo_map[norm_name] = logo["logo_url"]
                logo_sources.append(logo_map)
                print(f"成功加载Logo数据: {logo_url} (包含 {len(logo_map)} 个Logo)")
            except Exception as e:
                print(f"解析Logo数据失败: {logo_url}, 错误: {e}")
                logo_sources.append({})
        else:
            logo_sources.append({})
    
    # 4. 处理每个直播源
    success_count = 0
    for output_filename, source_config in live_urls.items():
        print(f"\n开始处理: {output_filename} (源: {source_config['url']})")
        try:
            success = process_single_source(output_filename, source_config, epg_channels, logo_sources)
            if success:
                success_count += 1
        except Exception as e:
            print(f"处理{output_filename}时发生错误: {e}")
    
    print(f"\n处理完成! 成功生成 {success_count}/{len(live_urls)} 个M3U文件")
    return success_count > 0

if __name__ == "__main__":
    # 安装依赖检查
    try:
        import zhconv
    except ImportError:
        print("请先安装zhconv库: pip install zhconv")
        exit(1)
        
    try:
        import requests
    except ImportError:
        print("请先安装requests库: pip install requests")
        exit(1)
        
    try:
        import chardet
    except ImportError:
        print("请先安装chardet库: pip install chardet")
        exit(1)
        
    success = main()
    if not success:
        print("处理过程中出现错误")
        exit(1)