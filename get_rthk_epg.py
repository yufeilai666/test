#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立运行的RTHK EPG抓取脚本（异步）
获取未来7天节目，生成XMLTV文件（时间输出为北京时间，带 +0800 偏移）
同时输出 gzip 压缩文件。
"""

import asyncio
import aiohttp
import pytz
import gzip
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom

# ========== 配置 ==========
TZ_SH = pytz.timezone('Asia/Shanghai')

# 频道列表
# channelId: xmltv频道ID, channelName: 显示名称, id: URL拼接部分
CHANNELS = [
    {"channelId": "RTHK31", "channelName": "港臺電視31", "id": "tv31"},
    {"channelId": "RTHK32", "channelName": "港臺電視32", "id": "tv32"},
    {"channelId": "RTHK33", "channelName": "港臺電視33", "id": "tv33"},
    {"channelId": "RTHK34", "channelName": "港臺電視34", "id": "tv34"},
    {"channelId": "RTHK35", "channelName": "港臺電視35", "id": "tv35"},
]

BASE_URL = "https://www.rthk.hk/timetable"

# 分类标签
CATEGORIES = ["yufeilai666", "RTHK"]

# 日期范围：今天 ~ 今天+6天（共7天）
today = datetime.now(TZ_SH).date()
START_DATE = today
END_DATE = today + timedelta(days=6)

# ========== 工具函数 ==========
def log(msg: str) -> None:
    """简单日志输出（仅用于主流程和全局消息）"""
    print(msg)


async def fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """
    异步获取网页HTML
    :param url: 目标URL
    :param session: aiohttp会话
    :return: HTML字符串，失败返回空字符串
    """
    try:
        async with session.get(url, timeout=10) as resp:
            resp.encoding = 'utf-8'
            return await resp.text()
    except Exception:
        return ""


def parse_program_block(block, date_obj: datetime.date, channel_id: str) -> Optional[Dict[str, Any]]:
    """
    解析单个节目块，返回节目信息字典
    :param block: BeautifulSoup的节目块元素
    :param date_obj: 当前日期（date对象）
    :param channel_id: 频道ID
    :return: 包含 'title', 'start', 'stop', 'channel_id' 的字典；解析失败返回None
    """
    # 1. 获取时间
    time_block = block.find('div', class_='shTimeBlock')
    if not time_block:
        return None
    time_elems = time_block.find_all('p', class_='timeDis')
    if len(time_elems) < 3:
        return None

    start_str = time_elems[0].text.strip()
    end_str = time_elems[2].text.strip()

    # 解析开始时间（原网页时间即为北京时间）
    try:
        start_h, start_m = map(int, start_str.split(':'))
        start_dt = datetime(date_obj.year, date_obj.month, date_obj.day, start_h, start_m)
        start_dt = TZ_SH.localize(start_dt)
    except Exception:
        return None

    # 解析结束时间
    try:
        end_h, end_m = map(int, end_str.split(':'))
        end_dt = datetime(date_obj.year, date_obj.month, date_obj.day, end_h, end_m)
        if end_h < start_h or (end_h == start_h and end_m < start_m):
            end_dt += timedelta(days=1)
        end_dt = TZ_SH.localize(end_dt)
    except Exception:
        end_dt = start_dt + timedelta(minutes=30)

    # 2. 获取标题
    title_block = block.find('div', class_='shTitle')
    program_name = ""
    if title_block:
        a_tag = title_block.find('a')
        if a_tag:
            program_name = a_tag.text.strip()

    sub_block = block.find('div', class_='shSubTitle')
    sub_title = ""
    if sub_block:
        a_tag = sub_block.find('a')
        if a_tag:
            sub_title = a_tag.text.strip()

    if not program_name and not sub_title:
        return None

    # 合成最终标题
    if not program_name:
        final_title = sub_title
    elif not sub_title:
        final_title = program_name
    else:
        # 规则：
        # 1. 如果 sub_title 以 program_name 开头或结尾，说明 sub_title 包含完整节目名，用 sub_title
        # 2. 否则，如果 program_name 以 sub_title 开头或结尾，说明 program_name 包含完整节目名，用 program_name
        # 3. 否则，拼接两者
        if sub_title.startswith(program_name) or sub_title.endswith(program_name):
            final_title = sub_title
        elif program_name.startswith(sub_title) or program_name.endswith(sub_title):
            final_title = program_name
        else:
            final_title = f"{program_name} {sub_title}"

    return {
        'channel_id': channel_id,
        'title': final_title,
        'start': start_dt,
        'stop': end_dt,
    }


async def fetch_channel_programs(channel: Dict[str, str], session: aiohttp.ClientSession) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    异步获取单个频道的节目列表（仅未来7天）
    :param channel: 频道信息字典
    :param session: aiohttp会话
    :return: (节目字典列表, 日志行列表)
    """
    channel_id = channel['channelId']
    channel_name = channel['channelName']
    url_id = channel['id']
    url = f"{BASE_URL}/{url_id}"

    logs = []
    # 不再添加开头的分隔线，由主函数统一处理
    logs.append(f"📺 获取频道「{channel_name}」(id: {url_id}) 的EPG数据...")

    html = await fetch_html(url, session)
    if not html:
        logs.append(f"❌ 频道「{channel_name}」获取HTML失败")
        logs.append("*********************************")
        return [], logs

    soup = BeautifulSoup(html, 'html.parser')
    date_blocks = soup.find_all('div', class_='slideBlock')

    programs = []
    for block in date_blocks:
        date_attr = block.get('date')  # 格式 YYYYMMDD
        if not date_attr:
            continue
        try:
            dt = datetime.strptime(date_attr, "%Y%m%d").date()
        except ValueError:
            continue

        if not (START_DATE <= dt <= END_DATE):
            continue

        prog_blocks = block.find_all('div', class_='shdBlock')
        for pblock in prog_blocks:
            prog = parse_program_block(pblock, dt, channel_id)
            if prog:
                programs.append(prog)

    # 根据节目数量输出不同的日志
    if len(programs) == 0:
        logs.append(f"⚠️ 频道「{channel_name}」没有找到符合条件的节目")
    else:
        logs.append(f"✅ 频道「{channel_name}」添加了 {len(programs)} 个节目")
    logs.append("*********************************")
    return programs, logs


def build_xmltv(all_programs: List[Dict[str, Any]], channels: List[Dict[str, str]]) -> Tuple[str, int, int]:
    """
    生成XMLTV字符串，时间直接使用北京时间（+0800）
    只包含有节目的频道，并为每个节目添加空的<desc>标签
    :param all_programs: 所有节目字典列表
    :param channels: 频道信息列表
    :return: (XML字符串, 实际写入的频道数, 节目总数)
    """
    root = ET.Element("tv")
    root.set("generator-info-name", "yufeilai666")
    root.set("generator-info-url", "https://github.com/yufeilai666")

    # 统计哪些频道有节目
    channels_with_programs = set()
    for prog in all_programs:
        channels_with_programs.add(prog['channel_id'])

    # 频道（只添加有节目的）
    channel_count = 0
    for ch in channels:
        if ch['channelId'] not in channels_with_programs:
            continue
        ch_elem = ET.SubElement(root, "channel")
        ch_elem.set("id", ch['channelId'])
        display = ET.SubElement(ch_elem, "display-name")
        display.text = ch['channelName']
        channel_count += 1

    # 节目
    for prog in all_programs:
        prog_elem = ET.SubElement(root, "programme")
        prog_elem.set("channel", prog['channel_id'])

        start_beijing = prog['start'].astimezone(TZ_SH)
        stop_beijing = prog['stop'].astimezone(TZ_SH)
        start_str = start_beijing.strftime("%Y%m%d%H%M%S +0800")
        stop_str = stop_beijing.strftime("%Y%m%d%H%M%S +0800")
        prog_elem.set("start", start_str)
        prog_elem.set("stop", stop_str)

        title_elem = ET.SubElement(prog_elem, "title")
        title_elem.text = prog['title']

        # 添加空的描述标签
        desc_elem = ET.SubElement(prog_elem, "desc")
        desc_elem.text = ""

        for cat in CATEGORIES:
            cat_elem = ET.SubElement(prog_elem, "category")
            cat_elem.text = cat

    rough = ET.tostring(root, encoding='utf-8')
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8'), channel_count, len(all_programs)


async def main():
    """主异步函数"""
    log("🚀 开始抓取RTHK EPG数据...")
    all_programs = []
    all_logs = []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_channel_programs(ch, session) for ch in CHANNELS]
        results = await asyncio.gather(*tasks)

    # 按频道顺序处理结果
    for progs, logs in results:
        all_programs.extend(progs)
        all_logs.extend(logs)

    # 打印日志
    # 顶部全局分隔线
    log("==============================")
    # 打印所有频道的日志（每个频道已包含自己的结尾分隔线）
    for line in all_logs:
        log(line)
    # 底部全局分隔线（在总结之前）
    log("==============================")

    if not all_programs:
        log("⚠️ 没有获取到任何节目，退出")
        return

    # 生成XML（只包含有节目的频道）
    xml_content, channel_count, program_count = build_xmltv(all_programs, CHANNELS)

    # 写入普通 XML 文件
    xml_filename = "rthk_epg.xml"
    with open(xml_filename, 'w', encoding='utf-8') as f:
        f.write(xml_content)
    log(f"✅ XMLTV文件已生成: {xml_filename}")

    # 写入 gzip 压缩文件
    gz_filename = xml_filename + ".gz"
    with gzip.open(gz_filename, 'wt', encoding='utf-8') as f:
        f.write(xml_content)
    log(f"✅ GZIP压缩文件已生成: {gz_filename}")

    # 总结日志
    log(f"📊 总共添加了 {channel_count} 个频道和 {program_count} 个节目")
    # 底部最终分隔线
    log("==============================")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())