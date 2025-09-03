import requests
import json
import re
import os
from zhconv import convert  # 用于简繁转换

# 设置常量
USER_AGENT = "AptvPlayer/2.7.4"

def fetch_url(url, description="数据"):
    """通用URL请求函数"""
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"获取{description}失败: {e}")
        return None

def normalize_channel_name(name):
    """标准化频道名称（转简体并小写）"""
    if not name:
        return ""
    return convert(name.lower(), 'zh-cn')

def process_single_source(output_filename, list_url, epg_map, logo_sources):
    """处理单个直播源"""
    # 获取频道列表数据
    list_data = fetch_url(list_url, f"频道列表({output_filename})")
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
        
        # 跳过无效的频道行
        if not channel_name or not channel_url:
            print(f"警告: 跳过无效的频道行(第{line_count}行): {line}")
            continue
            
        norm_channel_name = normalize_channel_name(channel_name)
        
        # 匹配EPG信息
        tvg_id = ""
        tvg_name = ""
        if norm_channel_name in epg_map:
            tvg_id = epg_map[norm_channel_name]["channel_id"]
            tvg_name = epg_map[norm_channel_name]["channel_name"]
        
        # 匹配Logo
        tvg_logo = ""
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
    epg_map = {}
    if epg_data:
        try:
            epg_channels = json.loads(epg_data)
            # 创建EPG映射表（标准化名称->channel_id和channel_name）
            for channel in epg_channels:
                norm_name = normalize_channel_name(channel["channel_name"])
                epg_map[norm_name] = {
                    "channel_id": channel["channel_id"],
                    "channel_name": channel["channel_name"]
                }
            print(f"成功加载EPG数据，包含 {len(epg_map)} 个频道")
        except Exception as e:
            print(f"解析EPG数据失败: {e}")
            epg_map = {}
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
    for output_filename, list_url in live_urls.items():
        print(f"\n开始处理: {output_filename} (源: {list_url})")
        try:
            success = process_single_source(output_filename, list_url, epg_map, logo_sources)
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
        
    success = main()
    if not success:
        print("处理过程中出现错误")
        exit(1)