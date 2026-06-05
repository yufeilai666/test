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
import os
import random
from typing import Dict, List, Optional, Any, Tuple, Union

# TMDB配置
TMDB_API_KEY: Optional[str] = os.environ.get('TMDB_API_KEY')

# 清理后标题的缓存
_title_clean_cache: Dict[str, str] = {}

# TMDB描述信息缓存
_tmdb_description_cache: Dict[str, Optional[Dict[str, Any]]] = {}


def clean_movie_title(title: str) -> str:
    """
    清理电影标题，移除括号及其内容（带缓存功能）

    参数:
        title (str): 原始标题

    返回:
        str: 清理后的标题
    """
    if title in _title_clean_cache:
        return _title_clean_cache[title]

    # 移除中文括号及其内容
    cleaned_title = re.sub(r'（[^）]*）', '', title)
    # 移除英文括号及其内容
    cleaned_title = re.sub(r'\([^)]*\)', '', cleaned_title)
    # 移除方括号及其内容
    cleaned_title = re.sub(r'\[[^\]]*\]', '', cleaned_title)
    # 移除多余空格
    cleaned_title = cleaned_title.strip()

    print(f"🛠 清理标题: '{title}' -> '{cleaned_title}'")

    # 缓存结果
    _title_clean_cache[title] = cleaned_title
    return cleaned_title


def format_description(description: str) -> str:
    """
    格式化描述文本：处理各种换行符，按段落处理，去除空白行，每个段首添加两个全角空格

    参数:
        description (str): 原始描述文本

    返回:
        str: 格式化后的描述文本
    """
    if not description:
        return ""

    # 1. 统一换行符：将 \r\n、\r 和多个连续换行符统一为单个 \n
    description = re.sub(r'\r\n|\r|\n+', '\n', description)

    # 2. 按换行符分割成段落
    paragraphs = description.split('\n')

    # 3. 清理每个段落：移除首尾空白，过滤空段落
    cleaned_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para:  # 只保留非空段落
            # 4. 在每个段落开始添加两个全角空格
            para = '　　' + para
            cleaned_paragraphs.append(para)

    # 5. 用换行符连接所有段落
    formatted_description = '\n'.join(cleaned_paragraphs)

    return formatted_description


def search_tmdb_movie_direct(original_title: str) -> Optional[Dict[str, Any]]:
    """
    直接使用TMDB API搜索电影信息，避免第三方库的问题

    参数:
        original_title (str): 原始电影标题

    返回:
        Optional[Dict[str, Any]]: 包含电影信息的字典，如果未找到或出错则返回None
            字典键: 'title', 'overview', 'release_date', 'vote_average', 'id', 'poster_url'
    """
    if not TMDB_API_KEY:
        print("⚠️ TMDB_API_KEY 未设置，跳过TMDB搜索")
        return None

    # 清理标题
    clean_title = clean_movie_title(original_title)

    # 如果清理后标题为空，使用原始标题
    if not clean_title:
        clean_title = original_title

    # 检查缓存中是否已有该电影的描述信息
    cache_key = clean_title.lower().strip()
    if cache_key in _tmdb_description_cache:
        print(f"☑️ 使用缓存中的描述描述: {original_title}")
        return _tmdb_description_cache[cache_key]

    # 地区搜索顺序
    regions: List[str] = ['zh-HK', 'zh-TW']

    for region in regions:
        try:
            # 构建搜索URL
            search_url = "https://api.themoviedb.org/3/search/movie"
            params = {
                'api_key': TMDB_API_KEY,
                'language': region,
                'query': clean_title,
                'page': 1
            }

            print(f"🎬🔎 在 {region} 地区搜索电影: '{clean_title}' (原始标题: '{original_title}')")

            # 发送搜索请求
            response = requests.get(search_url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])

                if results:
                    # 取第一个结果
                    movie_id = results[0]['id']

                    # 获取电影详情
                    details_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
                    details_params = {
                        'api_key': TMDB_API_KEY,
                        'language': region
                    }

                    details_response = requests.get(details_url, params=details_params, timeout=10)

                    if details_response.status_code == 200:
                        movie_details = details_response.json()

                        # 检查是否有描述信息
                        overview = movie_details.get('overview', '')
                        if overview:
                            print(f"✅ 在 {region} 找到电影信息: {movie_details.get('title', '未知标题')}")

                            # 使用改进的格式化函数处理TMDB的描述信息
                            formatted_overview = format_description(overview)

                            movie_info = {
                                'title': original_title,  # 使用原始标题显示
                                'overview': formatted_overview,
                                'release_date': movie_details.get('release_date', ''),
                                'vote_average': movie_details.get('vote_average', 0),
                                'id': movie_id,
                                'poster_url': None  # TMDB暂时不返回海报URL
                            }

                            # 将成功获取的电影信息存入缓存
                            _tmdb_description_cache[cache_key] = movie_info
                            print(f"💾 已将描述信息存入临时缓存: {original_title}")

                            return movie_info
                        else:
                            print(f"⚠️ 在 {region} 找到电影但无描述信息，继续搜索其他地区")
                    else:
                        print(f"❌ 获取电影详情失败: {details_response.status_code}")
                else:
                    print(f"⚠️ 在 {region} 未找到电影: {clean_title}")
            else:
                print(f"❌ TMDB搜索请求失败: {response.status_code}")

            # 避免请求过快
            time.sleep(random.uniform(0.5, 1.1))

        except Exception as e:
            print(f"❌ TMDB搜索错误 ({region}): {e}")
            continue

    print(f"⚠️ 在所有地区均未找到电影描述信息: {clean_title}")

    # 将未找到的电影也存入缓存，避免重复搜索
    _tmdb_description_cache[cache_key] = None
    print(f"💾 已将未找到电影的空描述信息存入缓存: {original_title}")

    return None


class TVScheduleConverter:
    """电视节目表转换器，负责获取、解析、合并中英文节目单并生成XMLTV格式文件"""

    def __init__(self) -> None:
        """初始化时区、网站URL等配置"""
        # 时区定义
        self.beijing_tz = tz.gettz('Asia/Shanghai')
        self.et_tz = tz.gettz('America/Toronto')  # 东部时间
        self.pt_tz = tz.gettz('America/Los_Angeles')  # 太平洋时间

        # 网站URL
        self.base_url = "https://lstimes.ca"
        self.schedule_url = "https://lstimes.ca/schedule"
        self.en_schedule_url = "https://lstimes.ca/en/schedule"
        self.api_url = "https://lstimes.ca/wp-admin/admin-ajax.php"

    def clean_description(self, desc_text: str) -> str:
        """
        清理描述文本，移除换行符和制表符，并在开头添加两个全角空格

        参数:
            desc_text (str): 原始描述文本

        返回:
            str: 清理后的描述文本
        """
        if not desc_text:
            return ""

        # 移除所有换行符和制表符
        cleaned_text = desc_text.replace('\n', '').replace('\t', '')

        # 如果文本不为空，在开头添加两个全角空格
        if cleaned_text:
            cleaned_text = '　　' + cleaned_text

        return cleaned_text

    def get_tmdb_description(self, title: str) -> str:
        """
        从TMDB获取电影描述信息

        参数:
            title (str): 电影标题

        返回:
            str: 描述文本，如果未找到则返回空字符串
        """
        if not title or title == "未知节目":
            return ""

        # 检查缓存中是否已有该电影的描述信息
        cache_key = clean_movie_title(title).lower().strip()
        if cache_key in _tmdb_description_cache:
            print(f"☑️ 使用缓存中的描述: {title}")
            movie_info = _tmdb_description_cache[cache_key]
            return movie_info['overview'] if movie_info and movie_info.get('overview') else ""

        print(f"🌏 尝试从TMDB获取电影描述: '{title}'")
        movie_info = search_tmdb_movie_direct(title)

        if movie_info and movie_info.get('overview'):
            print(f"✅ 成功从TMDB获取到描述信息")
            return movie_info['overview']
        else:
            print(f"⚠️ 无法从TMDB获取描述信息")
            return ""

    def get_page_params(self, schedule_url: str) -> Optional[Dict[str, str]]:
        """
        获取页面中的参数（通用方法，可指定中文或英文页面）

        参数:
            schedule_url (str): 节目表页面URL（中文或英文）

        返回:
            Optional[Dict[str, str]]: 包含 param_shortcode 和 chanel_selected 的字典，失败则返回None
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(schedule_url, headers=headers, timeout=30)
            print(f"🌏 获取页面状态码: {response.status_code} (URL: {schedule_url})")

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

    def get_request_dates(self) -> List[str]:
        """
        获取需要请求的日期范围（北京时间的昨天到未来7天，共9天）

        返回:
            List[str]: 日期字符串列表，格式为 YYYY-MM-DD
        """
        beijing_now = datetime.now(self.beijing_tz)
        start_date = beijing_now - timedelta(days=1)  # 昨天
        end_date = beijing_now + timedelta(days=7)   # 未来7天

        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)

        return dates

    def get_output_dates(self) -> List[str]:
        """
        获取需要输出的日期范围（北京时间的今天到未来6天，共7天）

        返回:
            List[str]: 日期字符串列表，格式为 YYYY-MM-DD
        """
        beijing_now = datetime.now(self.beijing_tz)
        start_date = beijing_now  # 今天
        end_date = beijing_now + timedelta(days=6)  # 未来6天

        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)

        return dates

    def convert_to_beijing_time(self, time_str: str, date_str: str, timezone: str = 'et') -> Optional[datetime]:
        """
        将加拿大时间转换为北京时间

        参数:
            time_str (str): 时间字符串，如 "東12:10 上午" 或 "西3:35 上午"
            date_str (str): 日期字符串，格式 YYYY-MM-DD
            timezone (str): 时区标识，'et' 东部时间，'pt' 太平洋时间

        返回:
            Optional[datetime]: 转换后的北京时间 datetime 对象，失败返回None
        """
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
                tz_obj = self.pt_tz
            else:
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

    def parse_program_time_simple(self, time_text: str) -> Optional[datetime]:
        """
        简化版时间解析 - 直接从包含完整日期时间的文本中提取

        参数:
            time_text (str): 包含完整日期时间的文本，如 "2025-10-31 - 12:10 上午"

        返回:
            Optional[datetime]: 解析后的北京时间 datetime 对象，失败返回None
        """
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
                print(f"⚠️ 使用回退解析: {time_text}")
                return None

        except Exception as e:
            print(f"❌ 简化时间解析错误: {e}, 时间文本: {time_text}")
            return None

    def parse_program_time_original(self, time_text: str, date_str: str) -> Optional[datetime]:
        """
        原来的复杂解析方法（作为回退）

        参数:
            time_text (str): 原始时间文本，如 "東12:10 上午 西3:35 上午"
            date_str (str): 日期字符串，格式 YYYY-MM-DD

        返回:
            Optional[datetime]: 解析后的北京时间 datetime 对象，失败返回None
        """
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
                        return beijing_time_pt
                    else:
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

    def get_tv_schedule_for_date(self, date_str: str, debug_file, page_params: Dict[str, str],
                                 referer_url: str) -> List[Dict[str, Any]]:
        """
        获取指定日期的电视节目表（通用，可指定referer）

        参数:
            date_str (str): 日期字符串，格式 YYYY-MM-DD
            debug_file: 调试文件对象，用于写入HTML内容
            page_params (Dict[str, str]): 包含 param_shortcode 和 chanel_selected 的字典
            referer_url (str): Referer 头部使用的URL

        返回:
            List[Dict[str, Any]]: 节目信息字典列表，每个字典包含标题、演员、描述、开始时间等
        """
        # 将日期转换为Unix时间戳
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        timestamp = int(time.mktime(date_obj.timetuple()))

        param_shortcode = page_params['param_shortcode']
        chanel_selected = page_params['chanel_selected']

        # 对参数进行URL编码
        param_shortcode_encoded = urllib.parse.quote(param_shortcode)

        params = {
            'action': 'extvs_get_schedule_simple',
            'param_shortcode': param_shortcode_encoded,
            'date': timestamp,
            'chanel': chanel_selected
            "lang": "en"
        }

        print(f"📆 请求日期: {date_str}")
        print(f"📆 时间戳: {timestamp}")

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Referer': referer_url,
                'Accept-Language': 'en-US,en;q=0.9' if 'en/schedule' in referer_url else 'zh-CN,zh;q=0.9'
}

            response = requests.post(self.api_url, data=params, headers=headers, timeout=30)
            print(f"✅ 响应状态码: {response.status_code}")

            if response.status_code != 200:
                print(f"❌ 请求失败，状态码: {response.status_code}")
                return []

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
            debug_file.write(f"Referer: {referer_url}\n")
            debug_file.write(f"HTML内容长度: {len(html_content)}\n")
            debug_file.write(f"{'='*50}\n")
            debug_file.write(html_content)
            debug_file.flush()

            print(f"✅ HTML内容长度: {len(html_content)}")

            return self.parse_html_schedule(html_content, date_str)

        except Exception as e:
            print(f"❌ 获取节目表错误 ({date_str}): {e}")
            return []

    def parse_html_schedule(self, html_content: str, date_str: str) -> List[Dict[str, Any]]:
        """
        解析HTML节目表，提取节目信息

        参数:
            html_content (str): 节目表的HTML内容
            date_str (str): 当前请求的日期字符串，用于调试

        返回:
            List[Dict[str, Any]]: 节目信息字典列表
        """
        if not html_content or len(html_content) < 100:
            print(f"⚠️ HTML内容为空或太短: {len(html_content)}")
            return []

        if "No matching records found" in html_content:
            print(f"⚠️ 日期 {date_str} 没有找到节目记录")
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        programs = []

        rows = soup.find_all('tr')
        print(f"✅ 找到 {len(rows)} 行")
        print("*" * 34)

        for i, row in enumerate(rows):
            try:
                if row.find('thead'):
                    continue

                time_td = row.find('td', class_='extvs-table1-time')
                if not time_td:
                    continue

                md_date_elem = time_td.find('span', class_='md-date')
                if md_date_elem:
                    time_text_with_date = md_date_elem.get_text(strip=True)
                    start_time = self.parse_program_time_simple(time_text_with_date)
                else:
                    time_text = time_td.get_text(strip=False)
                    start_time = self.parse_program_time_original(time_text, date_str)

                if not start_time:
                    print(f"⚠️ 无法解析时间: {time_text}")
                    continue

                program_td = row.find('td', class_='extvs-table1-programme')
                if program_td:
                    title_elem = program_td.find('h3')
                    title = title_elem.get_text(strip=True) if title_elem else "未知节目"

                    sub_tt_elem = program_td.find('span', class_='sub-tt')
                    cast_host = sub_tt_elem.get_text(strip=True) if sub_tt_elem else ""

                    description = ""
                    figure_elem = program_td.find('figure', class_='extvs-simple-sch')
                    if figure_elem:
                        p_elem = figure_elem.find('p')
                        if p_elem:
                            description = self.clean_description(p_elem.get_text(strip=False))

                print(f"📺 解析节目: {title} - {start_time}")

                if not description:
                    modal_content = program_td.find('div', class_='tvs-modal-content')
                    if modal_content:
                        desc_div = modal_content.find('div', class_='tvs_modal_des')
                        if desc_div:
                            desc_text = desc_div.get_text(strip=False)
                            lines = desc_text.split('\n')
                            description_lines = []
                            for line in lines:
                                line = line.strip()
                                if (line and
                                    title not in line and
                                    cast_host not in line and
                                    'md-date' not in line and
                                    not re.match(r'^\d{4}-\d{2}-\d{2}', line)):
                                    description_lines.append(line)
                            description = self.clean_description(''.join(description_lines))

                if not description:
                    description = self.get_tmdb_description(title)

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
                print("*" * 34)

            except Exception as e:
                print(f"❌ 解析节目错误: {e}")
                continue

        return programs

    def calculate_end_times(self, all_programs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        计算所有节目的结束时间（使用下一个节目的开始时间）

        参数:
            all_programs (List[Dict[str, Any]]): 节目列表（需包含 start_time 字段）

        返回:
            List[Dict[str, Any]]: 添加了 end_time 字段的节目列表，按开始时间升序排列
        """
        sorted_programs = sorted(all_programs, key=lambda x: x['start_time'])

        for i in range(len(sorted_programs)):
            if i < len(sorted_programs) - 1:
                sorted_programs[i]['end_time'] = sorted_programs[i + 1]['start_time']
            else:
                sorted_programs[i]['end_time'] = None

        return sorted_programs

    def filter_programs_with_end_time(self, all_programs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤节目，只保留有结束时间的节目

        参数:
            all_programs (List[Dict[str, Any]]): 节目列表

        返回:
            List[Dict[str, Any]]: 过滤后的节目列表
        """
        return [program for program in all_programs if program['end_time'] is not None]

    def filter_programs_by_date(self, all_programs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤节目，只保留输出日期范围内的节目

        参数:
            all_programs (List[Dict[str, Any]]): 节目列表

        返回:
            List[Dict[str, Any]]: 过滤后的节目列表
        """
        output_dates = self.get_output_dates()
        filtered_programs = []

        for program in all_programs:
            program_date = program['start_time'].strftime('%Y-%m-%d')
            if program_date in output_dates:
                filtered_programs.append(program)

        return filtered_programs

    def merge_english_titles(self, chinese_programs: List[Dict[str, Any]],
                             english_programs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将英文标题合并到中文节目列表中，按开始时间匹配（精确到分钟）

        参数:
            chinese_programs (List[Dict[str, Any]]): 中文节目列表
            english_programs (List[Dict[str, Any]]): 英文节目列表

        返回:
            List[Dict[str, Any]]: 合并后的节目列表（中文节目，标题字段已拼接英文）
        """
        # 构建英文节目索引：以开始时间（分钟精度）为key
        en_index: Dict[datetime, str] = {}
        for ep in english_programs:
            time_key = ep['start_time'].replace(second=0, microsecond=0)
            if time_key not in en_index:
                en_index[time_key] = ep['title']

        for prog in chinese_programs:
            time_key = prog['start_time'].replace(second=0, microsecond=0)
            en_title = en_index.get(time_key)
            if en_title and en_title.strip():
                if en_title.strip().lower() != prog['title'].strip().lower():
                    prog['title'] = f"{prog['title']} / {en_title}"
                    print(f"🔗 合并标题: {prog['title']}")
                else:
                    print(f"⏭️ 英文标题与中文相同，跳过拼接: {prog['title']}")
            else:
                print(f"⚠️ 未找到匹配的英文节目: {prog['title']} 时间 {time_key}")

        return chinese_programs

    def generate_xmltv_xml(self, all_programs: List[Dict[str, Any]]) -> ET.Element:
        """
        生成标准的电视节目单XML格式（XMLTV）

        参数:
            all_programs (List[Dict[str, Any]]): 节目列表（需包含 title, cast_host, description,
                                                  start_time, end_time, image_url 等字段）

        返回:
            ET.Element: XMLTV 根元素
        """
        # 简繁体关键词映射
        traditional_keywords = {
            '新闻': ['新闻', '新聞'],
            '娱乐': ['娱乐', '娛樂', '头条', '頭條'],
            '旅游': ['旅行', '旅游', '旅遊'],
            '犯罪': ['侦探', '偵探', '犯罪', '槍擊', '枪击', '开枪', '開槍', '槍殺', '枪杀', '抢劫', '搶劫'],
            '爱情': ['爱情', '愛情', 'Love', 'love', '相愛', '相爱', '恋爱', '戀愛'],
            '综艺': ['主持']
        }

        def contains_any(text: str, keywords: List[str]) -> bool:
            """检查文本是否包含任意一个关键词（支持简繁体）"""
            if not text:
                return False
            return any(keyword in text for keyword in keywords)

        # 创建根元素
        tv = ET.Element('tv')
        tv.set('generator-info-name', 'yufeilai666')
        tv.set('generator-info-url', 'https://github.com/yufeilai666')
        tv.set('source-info-name', 'lstimes.ca')

        # 添加频道信息 - 龙祥频道
        channel = ET.SubElement(tv, 'channel')
        channel.set('id', 'LS TIMES TV')
        display_name = ET.SubElement(channel, 'display-name')
        display_name.set('lang', 'zh')
        display_name.text = '龙祥频道 (CA)'
        icon = ET.SubElement(channel, 'icon')
        icon.set('src', '')

        # 额外的分类列表
        additional_categories = ["yufeilai666", "lstimes.ca"]

        # 添加所有节目
        for program in all_programs:
            programme = ET.SubElement(tv, 'programme')

            start_str = program['start_time'].strftime('%Y%m%d%H%M%S %z')
            end_str = program['end_time'].strftime('%Y%m%d%H%M%S %z')
            programme.set('start', start_str)
            programme.set('stop', end_str)
            programme.set('channel', 'LS TIMES TV')

            # 标题（已合并英文）
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
            else:
                ET.SubElement(programme, 'desc', {'lang': 'zh'})

            # 确定主要分类
            main_category = None
            if contains_any(program['title'], traditional_keywords['新闻']):
                main_category = '新聞'
            elif contains_any(program['title'], traditional_keywords['娱乐']):
                main_category = '娛樂'
            elif contains_any(program['title'], traditional_keywords['旅游']) or contains_any(program.get('description', ''), traditional_keywords['旅游']):
                main_category = '旅遊'
            elif contains_any(program['title'], traditional_keywords['犯罪']) or contains_any(program.get('description', ''), traditional_keywords['犯罪']):
                main_category = '犯罪'
            elif contains_any(program['title'], traditional_keywords['爱情']) or contains_any(program.get('description', ''), traditional_keywords['爱情']):
                main_category = '愛情'
            elif contains_any(program.get('cast_host', ''), traditional_keywords['综艺']):
                main_category = '綜藝'
            else:
                main_category = '電影'

            if main_category:
                category = ET.SubElement(programme, 'category')
                category.set('lang', 'zh')
                category.text = main_category

            for cat in additional_categories:
                category = ET.SubElement(programme, 'category')
                category.set('lang', 'zh')
                category.text = cat

            if program['image_url']:
                icon_elem = ET.SubElement(programme, 'icon')
                icon_elem.set('src', program['image_url'])

        return tv

    def run(self) -> Optional[str]:
        """
        主执行函数：获取中英文节目表，合并标题，生成XMLTV文件

        返回:
            Optional[str]: 生成的XML字符串，失败则返回None
        """
        print("🌏 开始获取电视节目表...")

        # 获取中文页面参数
        print("=== 获取中文页面参数 ===")
        ch_page_params = self.get_page_params(self.schedule_url)
        if not ch_page_params:
            print("❌ 无法获取中文页面参数，无法继续")
            return None

        # 获取英文页面参数
        print("=== 获取英文页面参数 ===")
        en_page_params = self.get_page_params(self.en_schedule_url)
        if not en_page_params:
            print("⚠️ 无法获取英文页面参数，将跳过英文标题合并")

        request_dates = self.get_request_dates()
        print(f"📅 请求日期范围: {request_dates[0]} 至 {request_dates[-1]}")

        output_dates = self.get_output_dates()
        print(f"📅 输出日期范围: {output_dates[0]} 至 {output_dates[-1]}")

        all_ch_programs = []

        with open("debug_LS-TIMES-CA_all_dates.html", "w", encoding="utf-8") as debug_file:
            debug_file.write("LS TIMES TV 调试信息\n")
            debug_file.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            debug_file.write(f"请求日期范围: {request_dates[0]} 至 {request_dates[-1]}\n")
            debug_file.write(f"输出日期范围: {output_dates[0]} 至 {output_dates[-1]}\n")

            for date_str in request_dates:
                print("\n" + "=" * 34)
                print(f"=== 获取中文节目表 {date_str} ===")
                programs = self.get_tv_schedule_for_date(date_str, debug_file, ch_page_params, self.schedule_url)
                all_ch_programs.extend(programs)
                print(f"✅ 获取到 {len(programs)} 个中文节目")
                time.sleep(1)

        print("\n" + "=" * 34)
        print(f"📺 总共获取中文节目 {len(all_ch_programs)} 个")

        if not all_ch_programs:
            print("\n" + "=" * 34)
            print("⚠️ 没有获取到任何节目数据，请检查网络连接和参数设置")
            # 创建一个空的XML文件
            tv = ET.Element('tv')
            tv.set('generator-info-name', 'yufeilai666')
            tv.set('generator-info-url', 'https://github.com/yufeilai666')
            tv.set('source-info-name', 'lstimes.ca')
            channel = ET.SubElement(tv, 'channel')
            channel.set('id', 'LS TIMES TV')
            display_name = ET.SubElement(channel, 'display-name')
            display_name.set('lang', 'zh')
            display_name.text = '龙祥频道 (CA)'
            icon = ET.SubElement(channel, 'icon')
            icon.set('src', '')
            rough_string = ET.tostring(tv, encoding='utf-8')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')
            with open("lstimes_ca_null.xml", 'wb') as f:
                f.write(pretty_xml)
            print("⚠️ 已创建空的 lstimes_ca_null.xml 文件")
            return None

        # 获取英文节目表（仅输出日期范围）
        all_en_programs = []
        if en_page_params:
            print("\n=== 开始获取英文节目表（仅输出日期范围）===")
            with open("debug_LS-TIMES-CA_en_dates.html", "w", encoding="utf-8") as en_debug_file:
                en_debug_file.write("LS TIMES TV 英文调试信息\n")
                en_debug_file.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                en_debug_file.write(f"输出日期范围: {output_dates[0]} 至 {output_dates[-1]}\n")
                for date_str in output_dates:
                    print("\n" + "=" * 34)
                    print(f"=== 获取英文节目表 {date_str} ===")
                    programs = self.get_tv_schedule_for_date(date_str, en_debug_file, en_page_params, self.en_schedule_url)
                    all_en_programs.extend(programs)
                    print(f"✅ 获取到 {len(programs)} 个英文节目")
                    time.sleep(1)
            print(f"📺 总共获取英文节目 {len(all_en_programs)} 个")
        else:
            print("⚠️ 跳过英文节目单获取")

        all_ch_programs = self.calculate_end_times(all_ch_programs)
        ch_programs_with_end = self.filter_programs_with_end_time(all_ch_programs)
        print(f"📺 有结束时间的中文节目: {len(ch_programs_with_end)} 个")

        filtered_ch_programs = self.filter_programs_by_date(ch_programs_with_end)
        print(f"📺 过滤后保留中文节目: {len(filtered_ch_programs)} 个")

        if all_en_programs:
            print("\n=== 开始合并英文标题 ===")
            merged_programs = self.merge_english_titles(filtered_ch_programs, all_en_programs)
        else:
            merged_programs = filtered_ch_programs

        xmltv_root = self.generate_xmltv_xml(merged_programs)
        rough_string = ET.tostring(xmltv_root, encoding='utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')

        filename = "lstimes_ca_epg.xml"
        with open(filename, 'wb') as f:
            f.write(pretty_xml)

        print(f"🎉 XMLTV格式的XML文件已保存: {filename}")

        print("\n📺 各日期节目数量统计:")
        for date_str in output_dates:
            day_programs = [p for p in merged_programs if p['start_time'].strftime('%Y-%m-%d') == date_str]
            print(f"📅 {date_str}: {len(day_programs)} 个节目")

        return pretty_xml.decode('utf-8')


if __name__ == "__main__":
    converter = TVScheduleConverter()
    converter.run()