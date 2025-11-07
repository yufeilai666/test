import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from xml.dom import minidom
import re
import json

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
    tv.set('source-info-name', 'TVKing')
    tv.set('source-info-url', 'https://tvking.funorange.com.tw')
    
    for channel in channels:
        # 构建EPG URL
        epg_url = f"https://tvking.funorange.com.tw/channel/{channel['id']}"
        
        try:
            print(f"正在获取频道 {channel['name']} 的EPG数据...")
            
            # 发送请求获取网页HTML
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(epg_url, headers=headers)
            response.raise_for_status()
            
            # 从HTML中提取Vue数据
            schedule_data = extract_vue_data_from_html(response.text)
            
            if not schedule_data:
                print(f"警告: 无法从频道 {channel['name']} 的HTML中提取数据")
                continue
            
            # 添加频道信息到XML
            channel_element = ET.SubElement(tv, 'channel')
            channel_element.set('id', channel['name'])
            
            display_name = ET.SubElement(channel_element, 'display-name')
            display_name.set('lang', 'zh')
            display_name.text = channel['name']
            
            # 处理节目数据
            process_schedule_data(tv, channel['name'], schedule_data)
            
            print(f"频道 {channel['name']} 处理完成")
            
        except requests.RequestException as e:
            print(f"请求频道 {channel['name']} 的EPG数据失败: {e}")
        except Exception as e:
            print(f"处理频道 {channel['name']} 数据时发生错误: {e}")
    
    # 生成格式化的XML
    try:
        xml_str = minidom.parseString(ET.tostring(tv, encoding='utf-8')).toprettyxml(indent="  ", encoding='utf-8')
        
        # 写入文件
        with open('tvgo.xml', 'wb') as f:
            f.write(xml_str)
            
        print(f"EPG数据已成功写入 tvgo.xml")
        
    except Exception as e:
        print(f"写入XML文件时发生错误: {e}")

def extract_vue_data_from_html(html_content):
    """
    从HTML内容中提取Vue组件的数据 - 备用方法
    """
    try:
        # 查找Vue实例创建代码
        pattern = r"createApp\({[\s\S]*?data\(\) {[\s\S]*?return {[\s\S]*?scheduleList: (\[[\s\S]*?\])[\s\S]*?}}"
        match = re.search(pattern, html_content)
        
        if match:
            schedule_list_str = match.group(1)
            
            # 清理JavaScript对象格式，转换为JSON格式
            schedule_list_str = schedule_list_str.replace("'", '"')
            schedule_list_str = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', schedule_list_str)
            schedule_list_str = re.sub(r',\s*}', '}', schedule_list_str)
            schedule_list_str = re.sub(r',\s*]', ']', schedule_list_str)
            
            # 解析JSON数据
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
            
            # 处理跨天情况 (当结束时间小于开始时间)
            if time_end < time_start:
                # 将结束日期设为下一天
                next_day = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                end_datetime = f"{next_day} {time_end}"
            
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