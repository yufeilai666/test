#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import asyncio
import json
import time
import hashlib
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from curl_cffi import AsyncSession
from curl_cffi.requests import Response
from xml.dom import minidom
import xml.etree.ElementTree as ET

# ========================= 配置常量 =========================

# 获取从昨天开始的节目天数
DAYS = 3

# XMLTV 文件名称
EPG_NAME = "fujianhaibotv_epg.xml"

# 首页URL（用于获取Cookie）
HOME_URL = "https://live.fjtv.net/"
# 频道列表接口模板（id从1到11）
CHANNEL_API_TEMPLATE = "https://live.fjtv.net/m2o/channel/channel_info.php?channel_id={id}"
# 节目单接口模板
EPG_API_TEMPLATE = (
    "https://mapi-plus.fjtv.net/cloudlive-manage-mapi/api/topic/program/list"
    "?topic_id={topic_id}&date={date}"
    "&app_secret=ea574ead10512926477d6728c1ad1db0"
    "&tenant_id=0&company_id=468&lang_type=zh"
)

# 基础请求头 —— 完全复制自浏览器直接访问的请求头
BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate, br",
}

# 频道ID映射表（匹配时使用 channel_id，即 name，不区分大小写），用于将原始频道名称映射为 XMLTV 中使用的频道标识
CHANNEL_ID_MAPPING = [
    {"original_channel_id": "少儿频道", "new_channel_id": "福建少儿频道"},
    {"original_channel_id": "体育频道", "new_channel_id": "福建体育频道"}
]

# 每个节目固定添加的分类标签
CATEGORIES = ["yufeilai666", "FJTV"]

# 北京时区（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))


# ========================= 工具函数 =========================
def beijing_now() -> datetime:
    """
    获取当前北京时间（带时区信息）。

    Returns:
        datetime: 当前北京时间，包含 UTC+8 时区信息。
    """
    return datetime.now(BEIJING_TZ)


def format_date(dt: datetime) -> str:
    """
    将 datetime 对象格式化为日期字符串 YYYY-MM-DD。

    Args:
        dt (datetime): 需要格式化的日期时间对象（应带时区）。

    Returns:
        str: 格式化后的日期字符串，例如 "2026-06-29"。
    """
    return dt.strftime("%Y-%m-%d")


def format_datetime(dt: datetime) -> str:
    """
    将 datetime 对象格式化为 XMLTV 标准时间格式。

    XMLTV 要求时间格式为 "YYYYMMDDHHMMSS +0800"（含时区偏移）。

    Args:
        dt (datetime): 带时区的 datetime 对象（通常为北京时间）。

    Returns:
        str: 格式化后的时间字符串，例如 "20260629120000 +0800"。
    """
    return dt.strftime("%Y%m%d%H%M%S") + " +0800"


def parse_datetime(date_str: str, time_str: str) -> datetime:
    """
    将日期字符串和时间字符串组合为北京时间 datetime 对象（带时区）。

    Args:
        date_str (str): 日期字符串，格式为 "YYYY-MM-DD"。
        time_str (str): 时间字符串，格式为 "HH:MM:SS"。

    Returns:
        datetime: 组合后的北京时间 datetime 对象（带 UTC+8 时区）。

    Raises:
        ValueError: 当日期或时间格式不正确时抛出。
    """
    dt_str = f"{date_str} {time_str}"
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=BEIJING_TZ)


def get_date_list() -> List[datetime]:
    """
    生成需要抓取 EPG 的日期列表。

    从“昨天”开始，连续 DAYS 天（由全局变量 DAYS 决定）。
    每个日期均表示为当天 00:00:00 的 datetime 对象（带时区）。

    Returns:
        List[datetime]: 日期列表，长度 = DAYS，每个元素为当天起始时刻（带时区）。
    """
    today = beijing_now().date()
    start = today - timedelta(days=1)  # 昨天
    return [
        datetime.combine(start + timedelta(days=i), datetime.min.time(), tzinfo=BEIJING_TZ)
        for i in range(DAYS)
    ]


# ======================== 数据获取函数 ========================
def print_flush(msg: str):
    """打印信息并立即刷新 stdout，确保在 GitHub Actions 中可见。"""
    print(msg)
    sys.stdout.flush()


async def fetch_homepage_cookie(session: AsyncSession) -> bool:
    """
    访问首页 https://live.fjtv.net/ 以获取并自动存储 Cookie。

    Args:
        session (AsyncSession): curl_cffi 异步会话（将自动存储 Cookie）。

    Returns:
        bool: 成功获取返回 True，否则返回 False。
    """
    try:
        resp = await session.get(HOME_URL, headers=BASE_HEADERS, impersonate="chrome110", timeout=30)
        resp.raise_for_status()
        print_flush("✅ 成功访问首页，获取到 Cookie")
        return True
    except Exception as e:
        print_flush(f"⚠️ 访问首页失败: {e}")
        return False


async def fetch_channel_list(session: AsyncSession) -> List[Dict]:
    """
    从海博TV获取所有频道列表（id 从 1 到 11）。

    每个频道返回一个字典，包含以下字段：
        - topic_id: 频道的数字ID（用于后续请求节目单）
        - channel_id: 频道标识（name 文本）
        - channel_name: 频道名称（name 文本）
        - logo_url: 频道图标URL

    Args:
        session (AsyncSession): curl_cffi 异步会话（已包含 Cookie）。

    Returns:
        List[Dict]: 频道字典列表，每个字典结构如上述描述。
    """
    channels = []
    for cid in range(1, 12):
        url = CHANNEL_API_TEMPLATE.format(id=cid)
        try:
            # 使用 curl_cffi 模拟 Chrome 110 指纹
            resp: Response = await session.get(
                url,
                headers=BASE_HEADERS,
                impersonate="chrome110",
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                ch = data[0]
                topic_id = ch.get("id")
                name = ch.get("name", "").strip()
                logo_url = ch.get("logo_url", "")
                if topic_id and name:
                    channels.append({
                        "topic_id": topic_id,
                        "channel_id": name,
                        "channel_name": name,
                        "logo_url": logo_url
                    })
                    print_flush(f"✅ 频道 id={cid}: {name}")
                else:
                    print_flush(f"⚠️ 频道 id={cid} 数据不完整，跳过")
            else:
                print_flush(f"⚠️ 频道 id={cid} 返回数据格式异常，跳过")
        except Exception as e:
            print_flush(f"⚠️ 频道 id={cid} 异常: {type(e).__name__}: {e}")
            continue
    return channels


async def fetch_channel_epg(
    session: AsyncSession,
    topic_id: str,
    channel_name: str,
    dates: List[datetime]
) -> Tuple[List[Dict], List[str]]:
    """
    获取单个频道在指定日期列表中的所有节目数据。

    对每个日期请求 EPG 接口，解析返回的 JSON 数据，提取节目信息（标题、开始/结束时间），
    并返回有效节目列表以及日志信息。

    Args:
        session (AsyncSession): curl_cffi 异步会话。
        topic_id (str): 频道的数字ID（用于构造请求URL）。
        channel_name (str): 频道显示名称（仅用于日志输出）。
        dates (List[datetime]): 要获取的日期列表（datetime 对象，带时区）。

    Returns:
        Tuple[List[Dict], List[str]]:
            - 节目列表，每个节目包含 "title", "start", "stop" 三个键，
              start 和 stop 为 datetime 对象（带时区）。
            - 日志列表（字符串），用于后续统一输出。
    """
    logs = []
    logs.append(f"📺 获取频道「{channel_name}」(topic_id: {topic_id}) 的EPG数据...")

    all_programs = []
    for dt in dates:
        date_str = format_date(dt)
        url = EPG_API_TEMPLATE.format(topic_id=topic_id, date=date_str)
        try:
            # 节目单接口同样使用浏览器头，并模拟指纹
            resp: Response = await session.get(
                url,
                headers=BASE_HEADERS,
                impersonate="chrome110",
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("error_code") != 200:
                logs.append(f"⚠️ 频道「{channel_name}」日期 {date_str} 返回错误: {data.get('error_message')}")
                continue
            result = data.get("result", [])
            if not result:
                logs.append(f"⚠️ 频道「{channel_name}」日期 {date_str} 没有节目数据")
                continue
            for item in result:
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                date_val = item.get("date")
                start_time = item.get("start_time")
                end_time = item.get("end_time")
                if not (date_val and start_time and end_time):
                    continue
                try:
                    start_dt = parse_datetime(date_val, start_time)
                    stop_dt = parse_datetime(date_val, end_time)
                except ValueError as ve:
                    logs.append(f"⚠️ 频道「{channel_name}」日期 {date_str} 时间解析失败: {ve}")
                    continue
                all_programs.append({
                    "title": title,
                    "start": start_dt,
                    "stop": stop_dt
                })
        except Exception as e:
            error_msg = str(e)
            logs.append(f"⚠️ 频道「{channel_name}」日期 {date_str} 请求失败: {error_msg}")

    if not all_programs:
        logs.append(f"⚠️ 频道「{channel_name}」没有找到任何节目")
        return [], logs

    # 按开始时间排序
    all_programs.sort(key=lambda x: x["start"])
    logs.append(f"✅ 频道「{channel_name}」添加了 {len(all_programs)} 个节目")
    return all_programs, logs


# ========================= 映射与构建 XMLTV =========================
def get_xmltv_channel_id(channel_id: str) -> str:
    """
    根据映射表，将原始的频道标识（channel_id，即 name）转换为 XMLTV 中使用的频道 id。

    若 channel_id（不区分大小写）存在于映射表的 original_channel_id 中，
    则返回对应的 new_channel_id；否则返回原 channel_id。

    Args:
        channel_id (str): 原始的频道标识（name 字段）。

    Returns:
        str: XMLTV 中 `<channel id="...">` 应使用的值。
    """
    for mapping in CHANNEL_ID_MAPPING:
        if mapping["original_channel_id"].lower() == channel_id.lower():
            return mapping["new_channel_id"]
    return channel_id


def build_xmltv(channels_data: List[Tuple[Dict, List[Dict]]]) -> ET.Element:
    """
    构建 XMLTV 的 ElementTree 根元素。

    先写入所有频道（包含图标），再写入所有节目。
    频道信息中会包含 logo_url，并生成 `<icon src="...">` 元素。

    Args:
        channels_data (List[Tuple[Dict, List[Dict]]]): 列表，每个元素为 (频道字典, 节目列表)。
            频道字典需包含 "channel_id", "channel_name", "logo_url" 等字段。
            节目列表中的每个节目需包含 "title", "start", "stop"。

    Returns:
        ET.Element: 根元素 `<tv>`，包含 generator-info-name 和 generator-info-url 属性。
    """
    tv = ET.Element("tv")
    tv.set("generator-info-name", "yufeilai666")
    tv.set("generator-info-url", "https://github.com/yufeilai666")

    channel_infos = []
    for ch_dict, programs in channels_data:
        channel_id = ch_dict["channel_id"]
        channel_name = ch_dict["channel_name"]
        logo_url = ch_dict.get("logo_url", "")
        xmltv_id = get_xmltv_channel_id(channel_id)
        channel_infos.append((xmltv_id, channel_name, programs, logo_url))

    # 写入所有频道
    for xmltv_id, channel_name, _, logo_url in channel_infos:
        channel_elem = ET.SubElement(tv, "channel", id=xmltv_id)
        display_name = ET.SubElement(channel_elem, "display-name")
        display_name.text = channel_name
        if logo_url:
            icon = ET.SubElement(channel_elem, "icon", src=logo_url)

    # 写入所有节目
    for xmltv_id, _, programs, _ in channel_infos:
        for prog in programs:
            start_str = format_datetime(prog["start"])
            stop_str = format_datetime(prog["stop"])
            prog_elem = ET.SubElement(
                tv,
                "programme",
                start=start_str,
                stop=stop_str,
                channel=xmltv_id
            )
            title_elem = ET.SubElement(prog_elem, "title")
            title_elem.text = prog["title"]
            for cat in CATEGORIES:
                cat_elem = ET.SubElement(prog_elem, "category")
                cat_elem.text = cat

    return tv


def prettify_xml(elem: ET.Element) -> str:
    """
    将 XML ElementTree 元素格式化为美观、可读的 XML 字符串，
    并自动包含 XML 声明（<?xml version="1.0" encoding="utf-8"?>）。

    Args:
        elem (ET.Element): XML 根元素。

    Returns:
        str: 包含 XML 声明的美化 XML 字符串（UTF-8 编码）。
    """
    rough_string = ET.tostring(elem, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


# ========================= 主流程 =========================
async def main():
    """
    主入口函数，执行完整的 EPG 抓取与 XMLTV 生成流程。

    步骤：
        0. 访问首页 https://live.fjtv.net/ 获取 Cookie。
        1. 从海博TV获取频道列表（id 1~11）。
        2. 确定日期范围（从昨天起 DAYS 天）。
        3. 并发抓取每个频道的 EPG 数据。
        4. 收集日志并按顺序输出。
        5. 构建 XMLTV 并保存为 fjhaibotv_epg.xml。

    Returns:
        None
    """
    try:
        # 创建 curl_cffi 异步会话，设置初始 Cookie（模拟浏览器中的 user_visit=2）
        # 注意：curl_cffi 的 AsyncSession 使用 async with 管理
        async with AsyncSession() as session:
            # 设置初始 cookie（与浏览器一致）
            session.cookies.set("user_visit", "2", domain=".fjtv.net", path="/")
            # 设置默认 impersonate 为 chrome110，所有请求将自动模拟该指纹
            session.impersonate = "chrome110"

            # 0. 访问首页获取 Cookie（可能会更新或添加其他 Cookie）
            print_flush("🍪 正在访问首页获取 Cookie...")
            cookie_success = await fetch_homepage_cookie(session)
            if not cookie_success:
                print_flush("⚠️ 获取 Cookie 失败，尝试继续...")
            else:
                print_flush("✅ Cookie 获取成功")

            # 1. 获取频道列表
            print_flush("📡 正在从「海博TV」获取频道列表")
            channels = await fetch_channel_list(session)

            if not channels:
                print_flush("❌ 没有获取到任何频道，程序退出")
                return

            print_flush(f"📺 从「海博TV」发现 {len(channels)} 个频道")
            print_flush("=================================")

            # 2. 准备日期列表
            dates = get_date_list()
            start_str = dates[0].strftime("%Y%m%d")
            end_str = dates[-1].strftime("%Y%m%d")
            print_flush(f"📡 正在抓取 {len(channels)} 个频道的节目数据")
            print_flush(f"ℹ️ 获取EPG数据日期范围: {start_str} 到 {end_str}")
            print_flush("=================================")

            # 3. 并发抓取 EPG（使用信号量限制并发数）
            sem = asyncio.Semaphore(3)

            async def fetch_with_semaphore(ch):
                async with sem:
                    # 复用同一个 session 实例，确保 Cookie 在所有请求中共享
                    programs, logs = await fetch_channel_epg(
                        session, ch["topic_id"], ch["channel_name"], dates
                    )
                    return ch, programs, logs

            tasks = [fetch_with_semaphore(ch) for ch in channels]
            results = await asyncio.gather(*tasks)

        # 4. 按频道顺序收集日志，并保留有节目的频道
        valid_channels = []
        for ch, programs, logs in results:
            for log in logs:
                print_flush(log)
            print_flush("*********************************")
            if programs:
                valid_channels.append((ch, programs))

        # 5. 生成 XMLTV
        print_flush("=================================")
        if valid_channels:
            tv_root = build_xmltv(valid_channels)
            xml_str = prettify_xml(tv_root)
            with open(EPG_NAME, "w", encoding="utf-8") as f:
                f.write(xml_str)
            print_flush(f"✅ XMLTV文件已生成: {EPG_NAME}")
            print_flush(
                f"📊 总共添加了 {len(valid_channels)} 个频道和 "
                f"{sum(len(p) for _, p in valid_channels)} 个节目"
            )
        else:
            print_flush("⚠️ 没有找到任何有效节目，未生成 XMLTV 文件")
        print_flush("=================================")

    except Exception as e:
        print_flush("❌ main() 内部发生异常:")
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        raise  # 重新抛出，让外层捕获


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_flush("\n⚠️ 用户中断程序")
        sys.exit(1)
    except Exception as e:
        print_flush("❌ 程序异常退出，完整堆栈如下:")
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        sys.exit(1)