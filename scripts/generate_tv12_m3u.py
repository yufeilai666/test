import requests
import json
import re
from zhconv import convert  # 用于简繁转换

# 设置常量
USER_AGENT = "AptvPlayer/2.7.4"
CONFIG = {
    "snow_epg_json": "https://raw.githubusercontent.com/yufeilai666/tvepg/main/snow_epg.json",
    "base_url": {
      "tv12.m3u": "https://2099.tv12.xyz",
      "tv1288.m3u": "https://2099.tv1288.xyz"
      },
    "logo_json": [
        "https://raw.githubusercontent.com/yufeilai666/tvepg/logo_info/logo.json",
        "https://raw.githubusercontent.com/yufeilai666/tvepg/logo_info/logo_112114.json",
        "https://raw.githubusercontent.com/yufeilai666/tvepg/logo_info/logo_taksssss.json",
        "https://raw.githubusercontent.com/yufeilai666/tvepg/logo_info/logo_fanmingming.json"
    ]
}

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

def get_correct_pwd(base_url):
    """从base_url获取correctPwd值"""
    html = fetch_url(base_url, "主页")
    if html:
        match = re.search(r'const correctPwd\s*=\s*"([^"]+)"', html)
        if match:
            return match.group(1)
    return None

def normalize_channel_name(name):
    """标准化频道名称（转简体并小写）"""
    return convert(name.lower(), 'zh-cn')

def process_m3u_data():
    """主处理函数"""
    # 1. 获取EPG数据
    epg_data = fetch_url(CONFIG["snow_epg_json"], "EPG信息")
    epg_channels = []
    if epg_data:
        try:
            epg_channels = json.loads(epg_data)
        except:
            print("解析EPG数据失败")
    else:
        print("警告: 无法获取EPG数据，将跳过EPG匹配")
    
    # 2. 获取所有logo数据
    logo_sources = []
    for logo_url in CONFIG["logo_json"]:
        logo_data = fetch_url(logo_url, f"Logo数据({logo_url})")
        if logo_data:
            try:
                logos = json.loads(logo_data)
                logo_map = {}
                for logo in logos:
                    norm_name = normalize_channel_name(logo["logo_name"])
                    logo_map[norm_name] = logo["logo_url"]
                logo_sources.append(logo_map)
            except:
                print(f"解析Logo数据失败: {logo_url}")
        else:
            logo_sources.append({})
    
    # 3. 处理每个base_url
    for output_filename, base_url in CONFIG["base_url"].items():
        print(f"\n处理 {base_url} -> {output_filename}")
        
        # 获取correctPwd
        correct_pwd = get_correct_pwd(base_url)
        if not correct_pwd:
            print(f"无法获取 {base_url} 的correctPwd，跳过")
            continue
        
        # 获取频道列表数据
        list_url = f"{base_url}/list.txt?pwd={correct_pwd}"
        list_data = fetch_url(list_url, "频道列表")
        if not list_data:
            continue
        
        # 解析列表数据并生成M3U
        current_group = "默认分组"
        m3u_lines = ["#EXTM3U"]
        
        for line in list_data.splitlines():
            line = line.strip()
            if not line:
                continue
                
            # 检查是否是分组行
            if line.endswith(",#genre#"):
                current_group = line.replace(",#genre#", "")
                continue
                
            # 解析频道行
            parts = line.split(",", 1)
            if len(parts) < 2:
                continue
                
            channel_name, channel_url = parts
            norm_channel_name = normalize_channel_name(channel_name)
            
            # 按照EPG数据从上往下匹配
            tvg_id = ""
            tvg_name = ""
            for channel in epg_channels:
                if normalize_channel_name(channel["channel_name"]) == norm_channel_name:
                    tvg_id = channel["channel_id"]
                    tvg_name = channel["channel_name"]
                    break
            
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
        
        # 写入文件
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(m3u_lines))
        
        print(f"M3U文件已生成: {output_filename}")
    
    return True

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
        
    success = process_m3u_data()
    if not success:
        print("生成M3U文件失败")
        exit(1)