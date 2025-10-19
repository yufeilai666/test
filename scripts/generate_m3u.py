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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

def clean_channel_name(name):
    """清洗频道名称，应用所有指定的规则"""
    if not name:
        return name
    
    original_name = name
    
    # 第一步：处理括号及括号内的内容（新增规则）
    name = re.sub(r'\s*\([^)]*\)', '', name)  # 去掉括号及括号内的内容
    name = re.sub(r'\s*（[^）]*）', '', name)  # 处理全角括号
    
    # 第二步：处理HD、UHD、超高清、高清等
    # 去掉HD相关格式
    name = re.sub(r'\s*-\s*HD\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*HD\s*$', '', name, flags=re.IGNORECASE)
    
    # 清理掉UHD，超高清
    name = re.sub(r'\s*UHD\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*超高清\s*', '', name, flags=re.IGNORECASE)
    
    # 去掉高清（可能有空格也可能没有）
    name = re.sub(r'\s*高清\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'高清\s*$', '', name, flags=re.IGNORECASE)
    
    # 第三步：处理CCTV5+相关规则
    # CCTV5+的各种变体
    name = re.sub(r'CCTV-?5\s*[PPLUS\+⁺＋]', 'CCTV5+', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV5\s*[PPLUS\+⁺＋]', 'CCTV5+', name, flags=re.IGNORECASE)
    
    # 处理CCTV5+体育相关
    name = re.sub(r'CCTV-?5\+.*体育.*', 'CCTV5+', name, flags=re.IGNORECASE)
    
    # CCTV5＋清洗为CCTV5+
    name = re.sub(r'CCTV5＋', 'CCTV5+', name)
    
    # 第四步：处理CCTV16 4K相关规则
    # CCTV164K替换为CCTV16-4K
    name = re.sub(r'CCTV164K', 'CCTV16-4K', name, flags=re.IGNORECASE)
    
    # CCTV16奥林匹克4K相关清洗为CCTV16-4K
    name = re.sub(r'CCTV16奥林匹克.*4K.*', 'CCTV16-4K', name, flags=re.IGNORECASE)
    
    # CCTV16-4K不清洗（但确保格式正确）
    name = re.sub(r'CCTV16-4K', 'CCTV16-4K', name, flags=re.IGNORECASE)
    
    # 第五步：处理CCTV4国际频道相关规则
    # CCTV4欧洲、美洲、亚洲的各种英文和中文变体
    # 欧洲相关
    name = re.sub(r'CCTV-?4\s*(EUO|Europe|Europe|EUO|OZ)', 'CCTV4欧洲', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-?4.*欧洲.*', 'CCTV4欧洲', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-?4.*中文国际.*欧洲.*', 'CCTV4欧洲', name, flags=re.IGNORECASE)
    
    # 美洲相关
    name = re.sub(r'CCTV-?4\s*(AME|America|America|AME|MZ)', 'CCTV4美洲', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-?4.*美洲.*', 'CCTV4美洲', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-?4.*中文国际.*美洲.*', 'CCTV4美洲', name, flags=re.IGNORECASE)
    
    # 亚洲相关
    name = re.sub(r'CCTV-?4\s*(Asia|Asia|YZ)', 'CCTV4亚洲', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-?4.*亚洲.*', 'CCTV4亚洲', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-?4.*中文国际.*亚洲.*', 'CCTV4亚洲', name, flags=re.IGNORECASE)
    
    # CCTV4-美洲/欧洲/亚洲去掉横线
    name = re.sub(r'CCTV4-美洲', 'CCTV4美洲', name)
    name = re.sub(r'CCTV4-欧洲', 'CCTV4欧洲', name)
    name = re.sub(r'CCTV4-亚洲', 'CCTV4亚洲', name)
    
    # 第六步：处理CCTV4K相关规则
    # 去掉CCTV4K后面的括号数字
    name = re.sub(r'CCTV4K\(\d+\)', 'CCTV4K', name, flags=re.IGNORECASE)
    
    # CCTV-4K/8K/16K去掉横线
    name = re.sub(r'CCTV-4K', 'CCTV4K', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-8K', 'CCTV8K', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV-16K', 'CCTV16K', name, flags=re.IGNORECASE)
    
    # 第七步：处理其他CCTV频道的横线（但保留CCTV16-4K）
    # 注意：这个规则要在CCTV16-4K处理后执行
    name = re.sub(r'CCTV-(\d+[^K]?)', r'CCTV\1', name)
    
    # 第八步：处理CCTV一位数频道中的0（第一次需求中的规则4）
    # 去掉CCTV一位数频道中的0，但保留两位数频道
    # 匹配CCTV后面跟着0和1-9的数字，或者0和1-9的数字后面有+
    name = re.sub(r'CCTV0(\d)(?!\d)', r'CCTV\1', name, flags=re.IGNORECASE)
    name = re.sub(r'CCTV0(\d)\+', r'CCTV\1+', name, flags=re.IGNORECASE)
    
    # 第九步：处理地区前缀和竖线（第一次需求中的规则5）
    name = re.sub(r'^[^|]+\|', '', name)
    
    # 第十步：处理CCTV频道的主要部分（第一次需求中的规则8）
    # 只保留CCTV频道的主要部分
    # 匹配CCTV后面跟着数字和可能的+，然后可能有空格和其他字符
    cctv_match = re.search(r'(CCTV\d+\+?)\s*.*', name, re.IGNORECASE)
    if cctv_match and not any(keyword in name for keyword in ['欧洲', '美洲', '亚洲', '香港']):
        name = cctv_match.group(1)
    
    # 第十一步：特殊频道处理
    # Channel V国际娱乐台HD清洗为Channel V
    name = re.sub(r'Channel V国际娱乐台.*', 'Channel V', name, flags=re.IGNORECASE)
    
    # "黑龙江视"修正为"黑龙江卫视"（第一次需求中的规则9）
    name = re.sub(r'黑龙江视', '黑龙江卫视', name)
    
    # 去除首尾空格
    name = name.strip()
    
    if name != original_name:
        print(f"频道名称清洗: '{original_name}' -> '{name}'")
    
    return name

def fetch_url(url, description="数据", encoding=None, referer=None, user_agent=None, max_retries=3):
    """通用URL请求函数"""
    headers = DEFAULT_HEADERS.copy()
    
    # 设置 User-Agent
    if user_agent:
        headers["User-Agent"] = user_agent
    else:
        # 使用更现代的浏览器 User-Agent
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
            # 对于特定域名，使用更真实的浏览器头
            if "tv12.xyz" in url or "tv1288.xyz" in url:
                # 使用更完整的浏览器头
                browser_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                }
                headers.update(browser_headers)
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # 获取原始字节数据
            content_bytes = response.content
            
            # 首先尝试使用指定的编码
            if encoding:
                try:
                    return content_bytes.decode(encoding)
                except UnicodeDecodeError:
                    print(f"使用指定编码 {encoding} 解码失败，尝试自动检测")
            
            # 对于tv12和tv1288源，尝试多种编码
            if "tv12.xyz" in url or "tv1288.xyz" in url:
                encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'latin-1', 'iso-8859-1']
                for enc in encodings_to_try:
                    try:
                        decoded_content = content_bytes.decode(enc)
                        # 检查解码后的内容是否包含可读字符
                        if any(keyword in decoded_content for keyword in ['CCTV', '卫视', 'http', '#genre#']):
                            print(f"成功使用编码 {enc} 解码 {description}")
                            return decoded_content
                    except UnicodeDecodeError:
                        continue
            
            # 尝试自动检测编码
            detected = chardet.detect(content_bytes)
            if detected['confidence'] > 0.6:  # 降低置信度阈值
                try:
                    decoded_content = content_bytes.decode(detected['encoding'])
                    # 验证解码结果
                    if any(keyword in decoded_content for keyword in ['CCTV', '卫视', 'http', '#genre#']):
                        print(f"使用检测到的编码 {detected['encoding']} (置信度: {detected['confidence']:.2f})")
                        return decoded_content
                except UnicodeDecodeError:
                    print(f"使用检测到的编码 {detected['encoding']} 解码失败，尝试其他编码")
            
            # 尝试常见的中文编码
            encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'latin-1']
            
            for enc in encodings_to_try:
                try:
                    decoded_content = content_bytes.decode(enc)
                    # 验证解码结果是否包含预期的内容
                    if any(keyword in decoded_content for keyword in ['CCTV', '卫视', 'http', '#genre#']):
                        print(f"成功使用编码 {enc} 解码 {description}")
                        return decoded_content
                except UnicodeDecodeError:
                    continue
            
            # 如果所有尝试都失败，返回原始字节的字符串表示（用于调试）
            print(f"所有编码尝试失败，返回原始内容的前1000字符用于调试")
            return str(content_bytes[:1000])
                
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
    # 只做简繁转换和小写，不进行清洗
    return convert(name.lower(), 'zh-cn')

def is_valid_m3u_line(line):
    """检查是否为有效的M3U格式行"""
    line = line.strip()
    if not line:
        return False
    
    # 有效的行应该包含逗号分隔的频道名称和URL，或者是分组行
    if line.endswith(",#genre#") or line.endswith(",genre") or re.search(r",#?\w*genre\w*#?$", line):
        return True
    
    # 检查是否是频道行（名称,URL格式）
    if re.search(r'^[^,]+,[^,]+$', line):
        return True
    
    return False

def process_single_source(output_filename, source_config, epg_channels, logo_sources):
    """处理单个直播源"""
    list_url = source_config["url"]
    user_agent = source_config.get("user_agent")
    referer = source_config.get("referer")
    encoding = source_config.get("encoding")  # 从配置中获取编码
    
    # 对于特别难以访问的源，增加重试次数
    max_retries = 5 if "catvod.com" in list_url else 3
    
    print(f"正在获取: {list_url}")
    list_data = fetch_url(list_url, f"频道列表({output_filename})", encoding, referer, user_agent, max_retries)
    
    if not list_data:
        print(f"错误: 无法获取 {output_filename} 的数据")
        return False
    
    # 检查数据是否看起来像二进制数据
    if list_data.startswith("b'") or "\\x" in list_data[:100]:
        print(f"警告: {output_filename} 的数据可能仍然是二进制格式")
        # 尝试直接处理原始字节数据
        try:
            response = requests.get(list_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            raw_bytes = response.content
            
            # 尝试多种编码
            for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                try:
                    list_data = raw_bytes.decode(enc)
                    if any(keyword in list_data for keyword in ['CCTV', '卫视', 'http']):
                        print(f"通过直接请求并使用 {enc} 编码成功解码")
                        break
                except:
                    continue
        except Exception as e:
            print(f"直接请求也失败: {e}")
            return False
    
    # 检查数据质量 - 计算有效行的比例
    lines = list_data.splitlines()
    valid_lines = [line for line in lines if is_valid_m3u_line(line)]
    valid_ratio = len(valid_lines) / len(lines) if lines else 0
    
    print(f"数据统计: 总行数: {len(lines)}, 有效行: {len(valid_lines)}, 有效比例: {valid_ratio:.1%}")
    
    if valid_ratio < 0.1 and len(valid_lines) < 10:  # 如果有效行比例低于10%且有效行少于10个
        print(f"警告: {output_filename} 的数据质量太差，跳过处理")
        # 但仍然尝试处理，可能会有一些有效频道
        # return False
    
    # 解析列表数据并生成M3U
    current_group = "默认分组"
    m3u_lines = ["#EXTM3U"]
    line_count = 0
    valid_channel_count = 0
    skipped_lines = 0
    
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
            skipped_lines += 1
            if skipped_lines <= 3:  # 只显示前3个解析失败的例子
                # 显示行的前50个字符，避免输出过长
                display_line = line[:50] + "..." if len(line) > 50 else line
                print(f"警告: 无法解析第{line_count}行: {display_line}")
            continue
            
        channel_name, channel_url = parts
        channel_name = channel_name.strip()
        channel_url = channel_url.strip()
        
        # 尝试修复Unicode转义序列
        channel_name = fix_unicode_escape(channel_name)
        
        # 跳过无效的频道行
        if not channel_name or not channel_url:
            skipped_lines += 1
            continue
            
        # 检查URL是否以常见协议开头
        if not re.match(r'^(http|https|rtmp|rtsp|mms|p3p|p2p|P2p|tvbus|mitv)://', channel_url, re.IGNORECASE):
            skipped_lines += 1
            if skipped_lines <= 5:  # 只显示前5个被跳过的URL例子
                print(f"跳过不支持的协议: {channel_url[:50]}...")
            continue
            
        # 清洗频道名称（只对直播源数据进行清洗）
        cleaned_channel_name = clean_channel_name(channel_name)
        norm_channel_name = normalize_channel_name(cleaned_channel_name)
        
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
        m3u_lines.append(f'#EXTINF:-1 {attrs},{cleaned_channel_name}')
        m3u_lines.append(channel_url)
        valid_channel_count += 1
    
    if skipped_lines > 0:
        print(f"跳过了 {skipped_lines} 个无效行")
    
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