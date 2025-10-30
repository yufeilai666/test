import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dateutil import tz
import time
from bs4 import BeautifulSoup
import urllib.parse
from xml.dom import minidom

class TVScheduleConverter:
    def __init__(self):
        # 时区定义
        self.beijing_tz = tz.gettz('Asia/Shanghai')
        self.et_tz = tz.gettz('America/Toronto')  # 东部时间
        
        # API端点
        self.api_url = "https://lstimes.ca/wp-admin/admin-ajax.php"
        
    def get_request_dates(self):
        """获取需要请求的日期范围（北京时间的昨天到未来8天，共9天）"""
        beijing_now = datetime.now(self.beijing_tz)
        start_date = beijing_now - timedelta(days=1)  # 昨天
        end_date = beijing_now + timedelta(days=8)   # 未来8天
        
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
        
        return dates
    
    def get_output_dates(self):
        """获取需要输出的日期范围（北京时间的今天到未来6天，共7天）"""
        beijing_now = datetime.now(self.beijing_tz)
        start_date = beijing_now  # 今天
        end_date = beijing_now + timedelta(days=6)  # 未来6天
        
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
        
        return dates
    
    def convert_to_beijing_time(self, et_time_str, date_str):
        """将加拿大东部时间转换为北京时间"""
        try:
            # 解析加拿大东部时间（包含上午/下午）
            time_parts = et_time_str.replace('东', '').strip()
            
            # 处理上午/下午
            if '上午' in time_parts:
                time_parts = time_parts.replace('上午', 'AM')
            elif '下午' in time_parts:
                time_parts = time_parts.replace('下午', 'PM')
            
            # 提取时间部分
            time_value = time_parts.split(' ')[0]
            
            et_datetime_str = f"{date_str} {time_value}"
            
            # 创建加拿大东部时间对象
            et_time = datetime.strptime(et_datetime_str, '%Y-%m-%d %I:%M %p')
            et_time = et_time.replace(tzinfo=self.et_tz)
            
            # 转换为北京时间（ET+13小时=北京时间）
            beijing_time = et_time.astimezone(self.beijing_tz)
            
            return beijing_time
            
        except Exception as e:
            print(f"时间转换错误: {e}, 时间字符串: {et_time_str}")
            return None
    
    def parse_program_time(self, time_text, date_str):
        """解析节目时间文本"""
        times = time_text.strip().split('\n')
        et_time = None
        
        for t in times:
            if '东' in t:
                et_time = t.strip()
                break
                
        if not et_time:
            return None
            
        return self.convert_to_beijing_time(et_time, date_str)
    
    def get_tv_schedule_for_date(self, date_str, debug_file):
        """获取指定日期的电视节目表"""
        # 将日期转换为Unix时间戳
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        timestamp = int(time.mktime(date_obj.timetuple()))
        
        # 使用您提供的参数格式
        param_shortcode = '%7B%22style%22%3A%221%22%2C%22fullcontent_in%22%3A%22modal%22%2C%22show_image%22%3A%22show%22%2C%22channel%22%3A%22%22%2C%22slidesshow%22%3A%224%22%2C%22slidesscroll%22%3A%221%22%2C%22start_on%22%3A%221%22%2C%22before_today%22%3A%221%22%2C%22after_today%22%3A%227%22%2C%22order%22%3A%22DESC%22%2C%22orderby%22%3A%22date%22%2C%22meta_key%22%3A%22%22%2C%22meta_value%22%3A%22%22%2C%22ID%22%3A%22ex-1160%22%7D'
        
        params = {
            'action': 'extvs_get_schedule_simple',
            'param_shortcode': param_shortcode,
            'date': timestamp,
            'chanel': '%25e7%25af%2580%25e7%259b%25ae%25e8%25a1%25a8'  # 使用您提供的编码格式
        }
        
        print(f"请求日期: {date_str}")
        print(f"时间戳: {timestamp}")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Referer': 'https://lstimes.ca/'
            }
            
            response = requests.post(self.api_url, data=params, headers=headers, timeout=30)
            print(f"响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"请求失败，状态码: {response.status_code}")
                return []
                
            # 尝试解析JSON响应
            try:
                data = response.json()
                print(f"响应数据键: {data.keys() if data else '无数据'}")
            except:
                print(f"响应不是JSON格式: {response.text[:200]}")
                return []
                
            html_content = data.get('html', '')
            
            # 将HTML内容追加到调试文件中
            debug_file.write(f"\n\n{'='*50}\n")
            debug_file.write(f"日期: {date_str}\n")
            debug_file.write(f"时间戳: {timestamp}\n")
            debug_file.write(f"HTML内容长度: {len(html_content)}\n")
            debug_file.write(f"{'='*50}\n")
            debug_file.write(html_content)
            debug_file.flush()
            
            print(f"HTML内容长度: {len(html_content)}")
            
            return self.parse_html_schedule(html_content, date_str)
            
        except Exception as e:
            print(f"获取节目表错误 ({date_str}): {e}")
            return []
    
    def parse_html_schedule(self, html_content, date_str):
        """解析HTML节目表"""
        if not html_content or len(html_content) < 100:
            print(f"HTML内容为空或太短: {len(html_content)}")
            return []
            
        # 检查是否包含"No matching records found"
        if "No matching records found" in html_content:
            print(f"日期 {date_str} 没有找到节目记录")
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        programs = []
        
        # 查找所有节目行
        rows = soup.find_all('tr')
        print(f"找到 {len(rows)} 行")
        
        for i, row in enumerate(rows):
            try:
                # 跳过表头
                if row.find('thead'):
                    continue
                    
                # 提取时间信息
                time_td = row.find('td', class_='extvs-table1-time')
                if not time_td:
                    continue
                    
                time_text = time_td.get_text(strip=False)
                start_time = self.parse_program_time(time_text, date_str)
                
                if not start_time:
                    print(f"无法解析时间: {time_text}")
                    continue
                
                # 提取节目信息
                program_td = row.find('td', class_='extvs-table1-programme')
                if program_td:
                    title_elem = program_td.find('h3')
                    title = title_elem.get_text(strip=True) if title_elem else "未知节目"
                    
                    sub_tt_elem = program_td.find('span', class_='sub-tt')
                    cast_host = sub_tt_elem.get_text(strip=True) if sub_tt_elem else ""
                    
                    # 提取详细描述
                    description = ""
                    modal_content = program_td.find('div', class_='tvs-modal-content')
                    if modal_content:
                        desc_div = modal_content.find('div', class_='tvs_modal_des')
                        if desc_div:
                            # 获取描述文本
                            desc_text = desc_div.get_text(strip=False)
                            # 移除标题和演员信息
                            lines = desc_text.split('\n')
                            description_lines = []
                            for line in lines:
                                line = line.strip()
                                if (line and 
                                    title not in line and 
                                    cast_host not in line and 
                                    'md-date' not in line and
                                    not line.startswith('2025-')):
                                    description_lines.append(line)
                            description = ' '.join(description_lines)
                
                # 提取图片
                img_td = row.find('td', class_='extvs-table1-image')
                image_url = ""
                if img_td:
                    img = img_td.find('img')
                    if img and 'src' in img.attrs:
                        image_url = img['src']
                
                program = {
                    'title': title,
                    'cast_host': cast_host,
                    'description': description,
                    'start_time': start_time,
                    'image_url': image_url,
                    'original_time': time_text.strip(),
                    'date': date_str
                }
                
                programs.append(program)
                print(f"解析节目: {title} - {start_time}")
                
            except Exception as e:
                print(f"解析节目错误: {e}")
                continue
        
        return programs
    
    def calculate_end_times(self, all_programs):
        """计算所有节目的结束时间"""
        # 按开始时间排序所有节目
        sorted_programs = sorted(all_programs, key=lambda x: x['start_time'])
        
        # 为每个节目设置结束时间（使用下一个节目的开始时间）
        for i in range(len(sorted_programs)):
            if i < len(sorted_programs) - 1:
                # 使用下一个节目的开始时间作为当前节目的结束时间
                sorted_programs[i]['end_time'] = sorted_programs[i+1]['start_time']
            else:
                # 最后一个节目没有结束时间，标记为None
                sorted_programs[i]['end_time'] = None
        
        return sorted_programs
    
    def filter_programs_with_end_time(self, all_programs):
        """过滤节目，只保留有结束时间的节目"""
        return [program for program in all_programs if program['end_time'] is not None]
    
    def filter_programs_by_date(self, all_programs):
        """过滤节目，只保留输出日期范围内的节目"""
        output_dates = self.get_output_dates()
        filtered_programs = []
        
        for program in all_programs:
            program_date = program['start_time'].strftime('%Y-%m-%d')
            if program_date in output_dates:
                filtered_programs.append(program)
        
        return filtered_programs
    
    def generate_tvml_xml(self, all_programs):
        """生成标准的电视节目单XML格式（TVML）"""
        # 创建根元素
        tv = ET.Element('tv')
        tv.set('source-info-name', 'lstimes.ca')
        tv.set('generator-info-name', 'TV Schedule Converter')
        tv.set('generator-info-url', '')
        
        # 添加频道信息 - 修改为龙祥频道
        channel = ET.SubElement(tv, 'channel')
        channel.set('id', 'LS TIME 龙祥频道 (CA)')
        display_name = ET.SubElement(channel, 'display-name')
        display_name.set('lang', 'zh')
        display_name.text = '龙祥频道 (CA)'
        icon = ET.SubElement(channel, 'icon')
        icon.set('src', '')
        
        # 添加所有节目
        for program in all_programs:
            programme = ET.SubElement(tv, 'programme')
            
            # 设置开始和结束时间（TVML标准格式）
            start_str = program['start_time'].strftime('%Y%m%d%H%M%S %z')
            end_str = program['end_time'].strftime('%Y%m%d%H%M%S %z')
            programme.set('start', start_str)
            programme.set('stop', end_str)
            programme.set('channel', 'LS TIME 龙祥频道 (CA)')  # 修改为龙祥频道
            
            # 标题
            title = ET.SubElement(programme, 'title')
            title.set('lang', 'zh')
            title.text = program['title']
            
            # 副标题/演员信息
            if program['cast_host'] and program['cast_host'] != 'N/A':
                sub_title = ET.SubElement(programme, 'sub-title')
                sub_title.set('lang', 'zh')
                sub_title.text = program['cast_host']
            
            # 描述
            if program['description']:
                desc = ET.SubElement(programme, 'desc')
                desc.set('lang', 'zh')
                desc.text = program['description']
            
            # 分类（简单分类，可根据实际情况改进）
            category = ET.SubElement(programme, 'category')
            category.set('lang', 'zh')
            # 根据标题简单分类
            if '新闻' in program['title']:
                category.text = '新闻'
            elif '娱乐' in program['title'] or '头条' in program['title']:
                category.text = '娱乐'
            elif '旅行' in program['title'] or '旅行' in program['description']:
                category.text = '旅游'
            elif '侦探' in program['title'] or '侦探' in program['description']:
                category.text = '犯罪'
            elif '爱情' in program['title'] or '爱情' in program['description']:
                category.text = '爱情'
            elif '主持' in program['cast_host']:
                category.text = '综艺'
            else:
                category.text = '电影'
            
            # 图标
            if program['image_url']:
                icon = ET.SubElement(programme, 'icon')
                icon.set('src', program['image_url'])
        
        return tv
    
    def run(self):
        """主执行函数"""
        print("开始获取电视节目表...")
        
        # 获取请求日期范围（昨天到未来8天，共9天）
        request_dates = self.get_request_dates()
        print(f"请求日期范围: {request_dates[0]} 至 {request_dates[-1]}")
        
        # 获取输出日期范围（今天到未来6天，共7天）
        output_dates = self.get_output_dates()
        print(f"输出日期范围: {output_dates[0]} 至 {output_dates[-1]}")
        
        all_programs = []
        
        # 创建一个调试文件，用于保存所有日期的HTML内容
        with open("debug_all_dates.html", "w", encoding="utf-8") as debug_file:
            debug_file.write("LS TIME 龙祥频道调试信息\n")
            debug_file.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            debug_file.write(f"请求日期范围: {request_dates[0]} 至 {request_dates[-1]}\n")
            debug_file.write(f"输出日期范围: {output_dates[0]} 至 {output_dates[-1]}\n")
            
            # 先获取所有节目信息
            for date_str in request_dates:
                print(f"\n=== 获取 {date_str} 的节目表 ===")
                programs = self.get_tv_schedule_for_date(date_str, debug_file)
                all_programs.extend(programs)
                print(f"获取到 {len(programs)} 个节目")
                
                # 避免请求过于频繁
                time.sleep(1)
        
        print(f"\n总共获取 {len(all_programs)} 个节目")
        
        if not all_programs:
            print("没有获取到任何节目数据，请检查网络连接和参数设置")
            # 创建一个空的XML文件
            tv = ET.Element('tv')
            tv.set('source-info-name', 'lstimes.ca')
            tv.set('generator-info-name', 'TV Schedule Converter')
            tv.set('generator-info-url', '')
            
            # 添加频道信息 - 修改为龙祥频道
            channel = ET.SubElement(tv, 'channel')
            channel.set('id', 'LS TIME 龙祥频道 (CA)')
            display_name = ET.SubElement(channel, 'display-name')
            display_name.set('lang', 'zh')
            display_name.text = '龙祥频道 (CA)'
            icon = ET.SubElement(channel, 'icon')
            icon.set('src', '')
            
            rough_string = ET.tostring(tv, encoding='utf-8')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')
            
            with open("lstime_ca.xml", 'wb') as f:
                f.write(pretty_xml)
            print("已创建空的 lstime_ca.xml 文件")
            return
        
        # 计算结束时间（使用下一个节目的开始时间）
        all_programs = self.calculate_end_times(all_programs)
        
        # 过滤掉没有结束时间的节目（最后一个节目）
        programs_with_end_time = self.filter_programs_with_end_time(all_programs)
        print(f"有结束时间的节目: {len(programs_with_end_time)} 个")
        
        # 过滤节目，只保留输出日期范围内的节目
        filtered_programs = self.filter_programs_by_date(programs_with_end_time)
        print(f"过滤后保留 {len(filtered_programs)} 个节目")
        
        # 生成标准TVML格式的XML
        tvml_root = self.generate_tvml_xml(filtered_programs)
        
        # 美化XML输出
        rough_string = ET.tostring(tvml_root, encoding='utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')
        
        # 保存到文件 - 修改为lstime_ca.xml
        filename = "lstime_ca.xml"
        with open(filename, 'wb') as f:
            f.write(pretty_xml)
        
        print(f"TVML格式XML文件已保存: {filename}")
        
        # 打印统计信息
        print("\n各日期节目数量统计:")
        for date_str in output_dates:
            day_programs = [p for p in filtered_programs if p['start_time'].strftime('%Y-%m-%d') == date_str]
            print(f"{date_str}: {len(day_programs)} 个节目")
        
        return pretty_xml

# 运行脚本
if __name__ == "__main__":
    converter = TVScheduleConverter()
    converter.run()