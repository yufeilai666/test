import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from xml.dom import minidom
import re

def get_tvgo_epg():
    # 频道信息 - 可以扩展为多个频道
    channels = [
        {"id": "325", "name": "DAZN 1"}
        # 可以在这里添加更多频道
        # {"id": "326", "name": "DAZN 2"},
        # {"id": "327", "name": "其他频道"},
    ]
    
    # 创建XMLTV根元素
    tv = ET.Element('tv')
    tv.set('generator-info-name', 'yufeilai666')
    tv.set('generator-info-url', 'https://github.com/yufeilai666')
    
    for channel in channels:
        # 构建EPG URL
        epg_url = f"https://tvking.funorange.com.tw/channel/{channel['id']}"
        
        try:
            print(f"🌏 正在获取频道 {channel['name']} 的EPG数据...")
            
            # 发送请求获取网页HTML
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(epg_url, headers=headers)
            response.raise_for_status()
            
            # 从HTML中提取Vue数据
            schedule_data = extract_vue_data_from_html(response.text)
            
            if not schedule_data:
                print(f"⚠️ 警告: 无法从频道「{channel['name']}」的HTML中提取数据")
                continue
            
            # 添加频道信息到XML
            channel_element = ET.SubElement(tv, 'channel')
            channel_element.set('id', channel['name'])
            
            display_name = ET.SubElement(channel_element, 'display-name')
            display_name.set('lang', 'zh')
            display_name.text = channel['name']
            
            # 处理节目数据
            process_schedule_data(tv, channel['name'], schedule_data)
            
            print(f"✅ 频道「{channel['name']}」处理完成")
            
        except requests.RequestException as e:
            print(f"❌ 请求频道「{channel['name']}」的EPG数据失败: {e}")
        except Exception as e:
            print(f"❌ 处理频道「{channel['name']}」数据时发生错误: {e}")
    
    # 生成格式化的XML
    try:
        xml_str = minidom.parseString(ET.tostring(tv, encoding='utf-8')).toprettyxml(indent="  ", encoding='utf-8')
        
        # 写入文件
        with open('tvgo.xml', 'wb') as f:
            f.write(xml_str)
            
        print(f"🎉 EPG数据已成功写入 tvgo.xml")
        
    except Exception as e:
        print(f"❌ 写入XML文件时发生错误: {e}")

def extract_vue_data_from_html(html_content):
    """
    从HTML内容中提取Vue组件的数据
    """
    try:
        # 查找包含scheduleList的JavaScript代码段
        # 使用正则表达式匹配Vue数据对象
        pattern = r"scheduleList\s*:\s*(\[.*?\])\s*,?\s*\w+"
        match = re.search(pattern, html_content, re.DOTALL)
        
        if match:
            schedule_list_str = match.group(1)
            # 清理JavaScript对象格式，转换为JSON格式
            schedule_list_str = schedule_list_str.replace("'", '"')
            # 处理JavaScript对象键（无引号）
            schedule_list_str = re.sub(r'(\w+):', r'"\1":', schedule_list_str)
            # 处理可能的尾随逗号
            schedule_list_str = re.sub(r',\s*}', '}', schedule_list_str)
            schedule_list_str = re.sub(r',\s*]', ']', schedule_list_str)
            
            # 解析JSON数据
            schedule_data = json.loads(schedule_list_str)
            return schedule_data
        
        # 如果上面的模式不匹配，尝试另一种模式
        pattern2 = r"data\s*\(\)\s*\{\s*return\s*\{([^}]+scheduleList[^}]+)\}\s*\}"
        match2 = re.search(pattern2, html_content, re.DOTALL)
        
        if match2:
            data_content = match2.group(1)
            # 提取scheduleList部分
            schedule_match = re.search(r'scheduleList\s*:\s*(\[.*?\])', data_content, re.DOTALL)
            if schedule_match:
                schedule_list_str = schedule_match.group(1)
                schedule_list_str = schedule_list_str.replace("'", '"')
                schedule_list_str = re.sub(r'(\w+):', r'"\1":', schedule_list_str)
                schedule_list_str = re.sub(r',\s*}', '}', schedule_list_str)
                schedule_list_str = re.sub(r',\s*]', ']', schedule_list_str)
                
                schedule_data = json.loads(schedule_list_str)
                return schedule_data
        
        return None
        
    except Exception as e:
        print(f"提取Vue数据时发生错误: {e}")
        return None

def process_schedule_data(tv, channel_name, schedule_data):
    """
    处理节目数据并添加到XML
    """
    for day_schedule in schedule_data:
        date_str = day_schedule.get('date', '')
        program_list = day_schedule.get('programList', [])
        
        for program in program_list:
            # 跳过没有时间信息的广告节目
            if 'timeS' not in program or 'timeE' not in program or program.get('program') == 'ads':
                continue
                
            time_start = program.get('timeS', '')
            time_end = program.get('timeE', '')
            program_title = program.get('program', '')
            
            # 构建完整的开始和结束时间
            start_datetime = f"{date_str} {time_start}"
            end_datetime = f"{date_str} {time_end}"
            
            # 创建节目元素
            programme = ET.SubElement(tv, 'programme')
            programme.set('channel', channel_name)
            programme.set('start', format_datetime(start_datetime))
            programme.set('stop', format_datetime(end_datetime))
            
            # 添加节目标题
            title = ET.SubElement(programme, 'title')
            title.set('lang', 'zh')
            title.text = program_title

def format_datetime(datetime_str):
    """
    将日期时间字符串转换为XMLTV标准格式
    台北时间使用 UTC+8，所以格式为: YYYYMMDDHHMMSS +0800
    """
    try:
        # 解析原始格式: "2025-11-07 00:00:00"
        dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
        # 转换为XMLTV格式: "20251107000000 +0800" (台北时间 UTC+8)
        return dt.strftime('%Y%m%d%H%M%S +0800')
    except ValueError:
        # 如果格式不匹配，尝试其他可能的格式
        try:
            dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            return dt.strftime('%Y%m%d%H%M%S +0800')
        except:
            return datetime_str

if __name__ == "__main__":
    get_tvgo_epg()