import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dateutil import tz
import time
from bs4 import BeautifulSoup
import urllib.parse
from xml.dom import minidom
import re

class TVScheduleConverter:
    def __init__(self):
        # 时区定义
        self.beijing_tz = tz.gettz('Asia/Shanghai')
        self.et_tz = tz.gettz('America/Toronto')  # 东部时间
        self.pt_tz = tz.gettz('America/Los_Angeles')  # 太平洋时间
        
        # 网站URL
        self.base_url = "https://lstimes.ca"
        self.schedule_url = "https://lstimes.ca/schedule"
        self.api_url = "https://lstimes.ca/wp-admin/admin-ajax.php"
        
    def clean_description(self, desc_text):
        """清理描述文本，直接过滤掉换行符"""
        if not desc_text:
            return ""
        
        # 直接移除所有换行符
        return desc_text.replace('\n', '')
    
    def get_page_params(self):
        """获取页面中的参数"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(self.schedule_url, headers=headers, timeout=30)
            print(f"🌏 获取页面状态码: {response.status_code}")
            
            if response.status_code != 200:
                print("❌ 无法获取页面")
                return None
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 查找包含参数的div
            tv_div = soup.find('div', class_='ex-tvs-simple')
            if not tv_div:
                print("⚠️ 未找到节目表div")
                return None
                
            # 获取param_shortcode
            param_input = tv_div.find('input', {'id': 'param_shortcode'})
            if not param_input:
                print("⚠️ 未找到param_shortcode")
                return None
                
            param_shortcode = param_input.get('value', '')
            print(f"✅ 获取到param_shortcode: {param_shortcode}")
            
            # 获取chanel_selected
            chanel_input = tv_div.find('input', {'name': 'chanel_selected'})
            if not chanel_input:
                print("⚠️ 未找到chanel_selected")
                return None
                
            chanel_selected = chanel_input.get('value', '')
            print(f"✅ 获取到chanel_selected: {chanel_selected}")
            
            return {
                'param_shortcode': param_shortcode,
                'chanel_selected': chanel_selected
            }
            
        except Exception as e:
            print(f"❌ 获取页面参数错误: {e}")
            return None
    
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
    
    def convert_to_beijing_time(self, time_str, date_str, timezone='et'):
        """将加拿大时间转换为北京时间"""
        try:
            # 解析时间字符串
            time_parts = time_str.replace('東', '').replace('西', '').strip()
            
            # 处理上午/下午
            if '上午' in time_parts:
                time_parts = time_parts.replace('上午', 'AM')
            elif '下午' in time_parts:
                time_parts = time_parts.replace('下午', 'PM')
            
            # 提取时间部分和AM/PM部分
            parts = time_parts.split(' ')
            time_value = parts[0]
            am_pm = parts[1] if len(parts) > 1 else 'AM'
            
            # 处理时间格式，确保小时部分没有前导零
            if ':' in time_value:
                hour, minute = time_value.split(':')
                # 移除前导零
                hour = str(int(hour))
                time_value = f"{hour}:{minute}"
            
            # 选择时区
            if timezone == 'pt':
                # 太平洋时间
                tz_obj = self.pt_tz
            else:
                # 东部时间
                tz_obj = self.et_tz
            
            datetime_str = f"{date_str} {time_value} {am_pm}"
            
            # 创建时间对象
            local_time = datetime.strptime(datetime_str, '%Y-%m-%d %I:%M %p')
            local_time = local_time.replace(tzinfo=tz_obj)
            
            # 转换为北京时间
            beijing_time = local_time.astimezone(self.beijing_tz)
            
            return beijing_time
            
        except Exception as e:
            print(f"❌ 时间转换错误: {e}, 时间字符串: {time_str}, 构建的字符串: {datetime_str}")
            return None
    
    def parse_program_time_simple(self, time_text):
        """简化版时间解析 - 直接从包含完整日期时间的文本中提取"""
        try:
            # 使用正则表达式提取完整的日期时间格式
            # 匹配格式: "2025-10-31 - 12:10 上午"
            date_time_match = re.search(r'(\d{4}-\d{2}-\d{2})\s*-\s*(\d+:\d+)\s*(上午|下午)', time_text)
            
            if date_time_match:
                date_str = date_time_match.group(1)  # 2025-10-31
                time_str = date_time_match.group(2)  # 12:10
                am_pm = date_time_match.group(3)     # 上午/下午
                
                # 转换为标准格式
                time_value = time_str
                if am_pm == '下午' and ':' in time_str:
                    hour, minute = time_str.split(':')
                    hour = str(int(hour) + 12) if int(hour) < 12 else hour
                    time_value = f"{hour}:{minute}"
                
                # 构建完整的日期时间字符串（太平洋时间）
                datetime_str = f"{date_str} {time_value}"
                local_time = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M')
                local_time = local_time.replace(tzinfo=self.pt_tz)  # 假设是太平洋时间
                
                # 转换为北京时间
                beijing_time = local_time.astimezone(self.beijing_tz)
                return beijing_time
                
            else:
                # 如果没有找到完整日期时间，回退到原来的复杂解析
                print(f"⚠️ 使用回退解析: {time_text}")
                return None
                
        except Exception as e:
            print(f"❌ 简化时间解析错误: {e}, 时间文本: {time_text}")
            return None

    def parse_program_time_original(self, time_text, date_str):
        """原来的复杂解析方法（作为回退）"""
        try:
            # 使用正则表达式提取东部时间和太平洋时间
            et_match = re.search(r'東(\d+:\d+)\s+(上午|下午)', time_text)
            pt_match = re.search(r'西(\d+:\d+)\s+(上午|下午)', time_text)
            
            if et_match and pt_match:
                et_time_str = f"東{et_match.group(1)} {et_match.group(2)}"
                pt_time_str = f"西{pt_match.group(1)} {pt_match.group(2)}"
                
                # 转换为北京时间
                beijing_time_et = self.convert_to_beijing_time(et_time_str, date_str, 'et')
                beijing_time_pt = self.convert_to_beijing_time(pt_time_str, date_str, 'pt')
                
                # 检查是否跨越午夜
                if beijing_time_et and beijing_time_pt:
                    # 如果两个时间相差超过12小时，说明跨越了午夜
                    time_diff = abs((beijing_time_et - beijing_time_pt).total_seconds())
                    if time_diff > 12 * 3600:
                        # 使用太平洋时间来确定日期，因为太平洋时间更早
                        return beijing_time_pt
                    else:
                        # 使用东部时间
                        return beijing_time_et
                elif beijing_time_et:
                    return beijing_time_et
                else:
                    return beijing_time_pt
            elif et_match:
                et_time_str = f"東{et_match.group(1)} {et_match.group(2)}"
                return self.convert_to_beijing_time(et_time_str, date_str, 'et')
            elif pt_match:
                pt_time_str = f"西{pt_match.group(1)} {pt_match.group(2)}"
                return self.convert_to_beijing_time(pt_time_str, date_str, 'pt')
            else:
                print(f"⚠️ 无法解析时间: {time_text}")
                return None
                
        except Exception as e:
            print(f"❌ 解析节目时间错误: {e}, 时间文本: {time_text}")
            return None
    
    def get_tv_schedule_for_date(self, date_str, debug_file, page_params):
        """获取指定日期的电视节目表"""
        # 将日期转换为Unix时间戳
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        timestamp = int(time.mktime(date_obj.timetuple()))
        
        # 使用从页面获取的参数
        param_shortcode = page_params['param_shortcode']
        chanel_selected = page_params['chanel_selected']
        
        # 对参数进行URL编码
        param_shortcode_encoded = urllib.parse.quote(param_shortcode)
        
        params = {
            'action': 'extvs_get_schedule_simple',
            'param_shortcode': param_shortcode_encoded,
            'date': timestamp,
            'chanel': chanel_selected
        }
        
        print(f"📆 请求日期: {date_str}")
        print(f"📆 时间戳: {timestamp}")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Referer': 'https://lstimes.ca/schedule'
            }
            
            response = requests.post(self.api_url, data=params, headers=headers, timeout=30)
            print(f"✅ 响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ 请求失败，状态码: {response.status_code}")
                return []
                
            # 尝试解析JSON响应
            try:
                data = response.json()
                print(f"✅ 响应数据键: {data.keys() if data else '无数据'}")
            except:
                print(f"⚠️ 响应不是JSON格式: {response.text[:200]}")
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
            
            print(f"✅ HTML内容长度: {len(html_content)}")
            
            return self.parse_html_schedule(html_content, date_str)
            
        except Exception as e:
            print(f"❌ 获取节目表错误 ({date_str}): {e}")
            return []
    
    def parse_html_schedule(self, html_content, date_str):
        """解析HTML节目表"""
        if not html_content or len(html_content) < 100:
            print(f"⚠️ HTML内容为空或太短: {len(html_content)}")
            return []
            
        # 检查是否包含"No matching records found"
        if "No matching records found" in html_content:
            print(f"⚠️ 日期 {date_str} 没有找到节目记录")
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        programs = []
        
        # 查找所有节目行
        rows = soup.find_all('tr')
        print(f"✅ 找到 {len(rows)} 行")
        
        for i, row in enumerate(rows):
            try:
                # 跳过表头
                if row.find('thead'):
                    continue
                    
                # 提取时间信息
                time_td = row.find('td', class_='extvs-table1-time')
                if not time_td:
                    continue
                
                # 首先尝试查找包含完整日期时间的元素
                md_date_elem = time_td.find('span', class_='md-date')
                if md_date_elem:
                    time_text_with_date = md_date_elem.get_text(strip=True)
                    start_time = self.parse_program_time_simple(time_text_with_date)
                else:
                    # 如果没有找到完整日期时间，使用原来的方法
                    time_text = time_td.get_text(strip=False)
                    start_time = self.parse_program_time_original(time_text, date_str)
                
                if not start_time:
                    print(f"⚠️ 无法解析时间: {time_text}")
                    continue
                
                # 提取节目信息
                program_td = row.find('td', class_='extvs-table1-programme')
                if program_td:
                    title_elem = program_td.find('h3')
                    title = title_elem.get_text(strip=True) if title_elem else "未知节目"
                    
                    sub_tt_elem = program_td.find('span', class_='sub-tt')
                    cast_host = sub_tt_elem.get_text(strip=True) if sub_tt_elem else ""
                    
                    # 提取描述 - 从figure中的p标签获取
                    description = ""
                    figure_elem = program_td.find('figure', class_='extvs-simple-sch')
                    if figure_elem:
                        p_elem = figure_elem.find('p')
                        if p_elem:
                            description = self.clean_description(p_elem.get_text(strip=False))
                    
                    # 如果没有从p标签获取到描述，尝试从modal中获取
                    if not description:
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
                                description = self.clean_description(''.join(description_lines))
                
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
                    'original_time': time_text_with_date if md_date_elem else time_text.strip(),
                    'date': date_str
                }
                
                programs.append(program)
                print(f"📺 解析节目: {title} - {start_time}")
                
            except Exception as e:
                print(f"❌ 解析节目错误: {e}")
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
        # 简繁体关键词映射
        traditional_keywords = {
            '新闻': ['新闻', '新聞'],
            '娱乐': ['娱乐', '娛樂', '头条', '頭條'],
            '旅游': ['旅行', '旅游', '旅遊'],
            '犯罪': ['侦探', '偵探', '犯罪', '槍擊', '枪击', '开枪', '開槍', '槍殺', '枪杀', '抢劫', '搶劫'],
            '爱情': ['爱情', '愛情', 'Love', 'love', '相愛', '相爱', '恋爱', '戀愛'],
            '综艺': ['主持']
        }

        def contains_any(text, keywords):
            """检查文本是否包含任意一个关键词（支持简繁体）"""
            if not text:
                return False
            return any(keyword in text for keyword in keywords)

        # 创建根元素
        tv = ET.Element('tv')
        tv.set('generator-info-name', 'yufeilai666')
        tv.set('generator-info-url', 'https://github.com/yufeilai666')
        tv.set('source-info-name', 'lstimes.ca')
        
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
            
            # 描述 - 如果没有描述，使用自闭合标签
            if program['description']:
                desc = ET.SubElement(programme, 'desc')
                desc.set('lang', 'zh')
                desc.text = program['description']
            else:
                # 使用自闭合的desc标签
                ET.SubElement(programme, 'desc', {'lang': 'zh'})
            
            # 添加credits元素，包含writer信息
            credits = ET.SubElement(programme, 'credits')
            writer = ET.SubElement(credits, 'writer')
            writer.text = 'yufeilai666'
            
            # 分类（使用简繁体关键词映射）
            category = ET.SubElement(programme, 'category')
            category.set('lang', 'zh')
            
            # 使用简繁体关键词映射进行分类
            if contains_any(program['title'], traditional_keywords['新闻']):
                category.text = '新聞'
            elif contains_any(program['title'], traditional_keywords['娱乐']):
                category.text = '娛樂'
            elif contains_any(program['title'], traditional_keywords['旅游']) or contains_any(program.get('description', ''), traditional_keywords['旅游']):
                category.text = '旅遊'
            elif contains_any(program['title'], traditional_keywords['犯罪']) or contains_any(program.get('description', ''), traditional_keywords['犯罪']):
                category.text = '犯罪'
            elif contains_any(program['title'], traditional_keywords['爱情']) or contains_any(program.get('description', ''), traditional_keywords['爱情']):
                category.text = '愛情'
            elif contains_any(program.get('cast_host', ''), traditional_keywords['综艺']):
                category.text = '綜藝'
            else:
                category.text = '電影'
            
            # 图标
            if program['image_url']:
                icon = ET.SubElement(programme, 'icon')
                icon.set('src', program['image_url'])
        
        return tv
    
    def run(self):
        """主执行函数"""
        print("🛠 开始获取电视节目表...")
        
        # 首先获取页面参数
        print("=== 获取页面参数 ===")
        page_params = self.get_page_params()
        if not page_params:
            print("❌ 无法获取页面参数，无法继续")
            return
        
        # 获取请求日期范围（昨天到未来8天，共9天）
        request_dates = self.get_request_dates()
        print(f"📅 请求日期范围: {request_dates[0]} 至 {request_dates[-1]}")
        
        # 获取输出日期范围（今天到未来6天，共7天）
        output_dates = self.get_output_dates()
        print(f"📅 输出日期范围: {output_dates[0]} 至 {output_dates[-1]}")
        
        all_programs = []
        
        # 创建一个调试文件，用于保存所有日期的HTML内容
        with open("debug_LSTIME-CA_all_dates.html", "w", encoding="utf-8") as debug_file:
            debug_file.write("LS TIME 龙祥频道调试信息\n")
            debug_file.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            debug_file.write(f"请求日期范围: {request_dates[0]} 至 {request_dates[-1]}\n")
            debug_file.write(f"输出日期范围: {output_dates[0]} 至 {output_dates[-1]}\n")
            
            # 先获取所有节目信息
            for date_str in request_dates:
                print("\n" + "="*36)
                print(f"=== 获取 {date_str} 的节目表 ===")
                programs = self.get_tv_schedule_for_date(date_str, debug_file, page_params)
                all_programs.extend(programs)
                print(f"✅ 获取到 {len(programs)} 个节目")
                
                # 避免请求过于频繁
                time.sleep(1)
        
        print("\n" + "="*36)
        print(f"📺 总共获取 {len(all_programs)} 个节目")
        
        if not all_programs:
            print("\n" + "="*36)
            print("⚠️ 没有获取到任何节目数据，请检查网络连接和参数设置")
            # 创建一个空的XML文件
            tv = ET.Element('tv')
            tv.set('generator-info-name', 'yufeilai666')
            tv.set('generator-info-url', 'https://github.com/yufeilai666')
            tv.set('source-info-name', 'lstimes.ca')
            
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
            print("⚠️ 已创建空的 lstime_ca.xml 文件")
            return
        
        # 计算结束时间（使用下一个节目的开始时间）
        all_programs = self.calculate_end_times(all_programs)
        
        # 过滤掉没有结束时间的节目（最后一个节目）
        programs_with_end_time = self.filter_programs_with_end_time(all_programs)
        print(f"📺 有结束时间的节目: {len(programs_with_end_time)} 个")
        
        # 过滤节目，只保留输出日期范围内的节目
        filtered_programs = self.filter_programs_by_date(programs_with_end_time)
        print(f"📺 过滤后保留 {len(filtered_programs)} 个节目")
        
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
        
        print(f"🎉 TVML格式XML文件已保存: {filename}")
        
        # 打印统计信息
        print("\n📺 各日期节目数量统计:")
        for date_str in output_dates:
            day_programs = [p for p in filtered_programs if p['start_time'].strftime('%Y-%m-%d') == date_str]
            print(f"📅 {date_str}: {len(day_programs)} 个节目")
        
        return pretty_xml

# 运行脚本
if __name__ == "__main__":
    converter = TVScheduleConverter()
    converter.run()