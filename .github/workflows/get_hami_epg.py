import asyncio
import os
import pytz
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from loguru import logger
from typing import List, Dict, Tuple, Optional

# ---------- 常量配置 ----------

UA = "HamiVideo/7.12.806(Android 11;GM1910) OKHTTP/3.12.2"
headers = {
    'X-ClientSupport-UserProfile': '1',
    'User-Agent': UA
}

# 网络请求超时（秒）
REQUEST_TIMEOUT = 30
# 最大重试次数
MAX_RETRIES = 3
# 重试间隔（秒）
RETRY_DELAY = 10
# 最大并发请求数（控制同时获取EPG的频道数量）
MAX_CONCURRENCY = 5

# EPG 分类标签，用于在 XML 中为每个节目添加 category 元素
CATEGORIES = ["yufeilai666", "hami"]

# EPG 文件名
EPG_NAME = "hami.xml"

# 频道ID映射表，用于在生成XML时将原始频道名替换为自定义ID，
# 同时可选地替换显示名称（display-name）。
# 格式：
#   original_channel_id: 原始频道名称（即 original_id，也就是 API 返回的 channelName）
#   new_channel_id: 映射后用于 <channel id="..."> 和 <programme channel="..."> 的新ID
#   new_channel_name: （可选）若存在且非空，则用作 <display-name> 的内容；若未提供或为空，则沿用原始名称并追加 " (hami)" 后缀。
CHANNEL_ID_MAPPING = [
    {"original_channel_id": "中天新聞台", "new_channel_id": "中天新聞"},
    {"original_channel_id": "龍華電影台", "new_channel_id": "龍華電影"},
    {"original_channel_id": "龍華經典台", "new_channel_id": "龍華經典"}
]


# ---------- 异步请求函数 ----------

async def request_channel_list(client: httpx.AsyncClient) -> List[Dict]:
    """
    从 HamiVideo API 获取所有电视频道列表。

    Args:
        client: httpx 异步客户端，用于发送请求。

    Returns:
        频道列表，每个频道包含 'channelId', 'channelName', 'contentPk' 三个键。
        若请求失败或未找到频道数据，返回空列表。
    """
    params = {
        "appVersion": "7.12.806",
        "deviceType": "1",
        "appOS": "android",
        "menuId": "162"
    }
    url = "https://apl-hamivideo.cdn.hinet.net/HamiVideo/getUILayoutById.php"
    channel_list = []

    try:
        response = await client.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            elements = []

            # 在 UIInfo 中查找标题为 "頻道一覽" 的区块，获取其 elements
            for info in data.get("UIInfo", []):
                if info.get("title") == "頻道一覽":
                    elements = info.get('elements', [])
                    break

            # 提取每个频道的 contentPk 作为频道标识，同时保存名称
            for element in elements:
                channel_list.append({
                    "channelId": element.get('contentPk', ''),
                    "channelName": element.get('title', ''),
                    "contentPk": element.get('contentPk', '')
                })
    except Exception as e:
        logger.error(f"🚨 获取频道列表时出错: {e}")

    return channel_list


async def request_epg(client: httpx.AsyncClient, channel_name: str, content_pk: str) -> Tuple[List[Dict], List[str]]:
    """
    获取单个频道未来7天的节目表（EPG）。

    Args:
        client: httpx 异步客户端。
        channel_name: 频道名称（仅用于日志记录）。
        content_pk: 频道的 contentPk 值，用于API请求。

    Returns:
        一个元组，包含：
            - programs: 节目列表，每个节目包含 channelId, channelName, programName, description, start, end。
            - daily_logs: 长度为7的日志列表，记录每天获取情况（用于调试和用户反馈）。
    """
    url = "https://apl-hamivideo.cdn.hinet.net/HamiVideo/getEpgByContentIdAndDate.php"
    epg_result = []
    daily_logs = []
    today = datetime.now(pytz.timezone('Asia/Taipei'))

    for i in range(7):  # 获取从今天开始的7天数据
        date = today + timedelta(days=i)
        formatted_date = date.strftime('%Y-%m-%d')
        params = {
            "deviceType": "1",
            "Date": formatted_date,
            "contentPk": content_pk,
        }

        daily_programs = 0

        try:
            response = await client.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                ui_info = data.get('UIInfo', [])
                if ui_info:
                    elements = ui_info[0].get('elements', [])
                    for element in elements:
                        program_info_list = element.get('programInfo', [])
                        if program_info_list:
                            program_info = program_info_list[0]
                            start_time, end_time = hami_time_to_datetime(program_info['hintSE'])

                            epg_result.append({
                                "channelId": content_pk,
                                "channelName": element.get('title', ''),
                                "programName": program_info.get('programName', ''),
                                "description": program_info.get('description', ''),
                                "start": start_time,
                                "end": end_time
                            })
                            daily_programs += 1

                # 记录当天获取情况
                if daily_programs > 0:
                    daily_logs.append(f"  📅 {formatted_date}: ✅ 成功获取 {daily_programs} 个节目")
                else:
                    daily_logs.append(f"  📅 {formatted_date}: ⚠️  无节目数据")
            else:
                daily_logs.append(f"  📅 {formatted_date}: ❌ HTTP {response.status_code}")

        except httpx.TimeoutException:
            daily_logs.append(f"  📅 {formatted_date}: ⏰ 请求超时")
        except httpx.RequestError as e:
            daily_logs.append(f"  📅 {formatted_date}: 🔌 网络错误: {str(e)[:50]}")
        except Exception as e:
            daily_logs.append(f"  📅 {formatted_date}: 🚨 其他错误: {str(e)[:50]}")

    return epg_result, daily_logs


async def get_programs_with_retry(
    client: httpx.AsyncClient,
    channel: Dict,
    semaphore: asyncio.Semaphore
) -> Tuple[List[Dict], List[str]]:
    """
    带重试机制和并发控制的单个频道节目获取函数。

    Args:
        client: httpx 异步客户端。
        channel: 频道信息字典，必须包含 'channelName' 和 'contentPk'。
        semaphore: 用于限制并发数的信号量。

    Returns:
        一个元组 (programs, logs)，其中：
            - programs: 该频道的所有节目（可能为空）。
            - logs: 该频道整个获取过程的日志列表（包括开始、每天结果、结束/错误信息）。
    """
    async with semaphore:  # 控制同时进行请求的频道数量
        retries = 0
        channel_name = channel['channelName']
        channel_logs = []

        while retries < MAX_RETRIES:
            try:
                # 开始获取日志（若为重试则注明次数）
                start_msg = f"🔍 开始获取频道: {channel_name}"
                if retries > 0:
                    start_msg += f" (第{retries+1}次重试)"
                channel_logs.append(start_msg)

                # 请求EPG数据
                programs, daily_logs = await request_epg(client, channel_name, channel['contentPk'])
                channel_logs.extend(daily_logs)

                # 统计总节目数
                total = len(programs)
                if total > 0:
                    channel_logs.append(f"✅ {channel_name} 完成，共获取 {total} 个节目")
                else:
                    channel_logs.append(f"⚠️  {channel_name} 完成，无节目数据")

                return programs, channel_logs

            except Exception as e:
                retries += 1
                if retries < MAX_RETRIES:
                    retry_msg = f"🔄 {channel_name} 出错，{RETRY_DELAY}秒后重试 ({retries}/{MAX_RETRIES}): {str(e)[:50]}"
                    channel_logs.append(retry_msg)
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    error_msg = f"❌ {channel_name} 达到最大重试次数，跳过..."
                    channel_logs.append(error_msg)

        return [], channel_logs


async def request_all_epg(client: httpx.AsyncClient) -> Tuple[List[Dict], List[Dict]]:
    """
    并发获取所有频道的节目表，并输出详细的获取日志。

    Args:
        client: httpx 异步客户端。

    Returns:
        一个元组 (channels, programs)：
            - channels: 原始频道列表（来自 request_channel_list）。
            - programs: 所有频道合并后的节目列表。
    """
    logger.info("📡 开始获取频道列表...")
    raw_channels = await request_channel_list(client)
    logger.info(f"📊 找到 {len(raw_channels)} 个频道")

    all_programs = []
    all_channel_logs = {}  # 用于后续打印日志

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    tasks = []
    for channel in raw_channels:
        task = get_programs_with_retry(client, channel, semaphore)
        tasks.append(task)

    # 并发执行所有任务，允许异常返回
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理结果并收集日志
    for idx, result in enumerate(results):
        channel = raw_channels[idx]
        channel_name = channel['channelName']

        if isinstance(result, Exception):
            # 任务自身抛出未捕获的异常（理论上 get_programs_with_retry 内部已捕获所有，但以防万一）
            error_logs = [
                f"🔍 开始获取频道: {channel_name}",
                f"❌ {channel_name} 获取出错: {str(result)[:100]}"
            ]
            all_channel_logs[channel_name] = error_logs
            logger.error(f"❌ {channel_name} 获取出错: {result}")
        elif isinstance(result, tuple) and len(result) == 2:
            programs, channel_logs = result
            all_channel_logs[channel_name] = channel_logs
            if programs:
                all_programs.extend(programs)

    # 按频道顺序打印详细的获取日志
    logger.info("\n" + "=" * 34)
    logger.info("📺 各频道获取详情:")
    logger.info("=" * 34)

    total_success = 0
    total_failed = 0

    for channel in raw_channels:
        channel_name = channel['channelName']
        logs = all_channel_logs.get(channel_name, [])
        if logs:
            # 判断是否成功：存在包含"✅"且"完成"的日志行
            success = any("✅" in log and "完成" in log for log in logs)
            if success:
                total_success += 1
            else:
                total_failed += 1

            for log in logs:
                logger.info(log)
            logger.info("")  # 频道间空一行

    logger.info("=" * 34)
    logger.info(f"📊 频道获取统计:")
    logger.info(f"  ✅ 成功: {total_success} 个频道")
    logger.info(f"  ❌ 失败: {total_failed} 个频道")
    logger.info(f"  📺 总数: {len(raw_channels)} 个频道")
    logger.info(f"🎬 共获取 {len(all_programs)} 个节目")
    logger.info("=" * 34)

    return raw_channels, all_programs


# ---------- 辅助函数 ----------

def hami_time_to_datetime(time_range: str) -> Tuple[datetime, datetime]:
    """
    将 Hami API 返回的时间字符串（格式 "YYYY-MM-DD HH:MM:SS~YYYY-MM-DD HH:MM:SS"）
    转换为带时区（Asia/Taipei）的 datetime 对象。

    Args:
        time_range: 如 "2026-07-26 12:00:00~2026-07-26 13:00:00"

    Returns:
        包含开始时间和结束时间的元组，均为带时区的 datetime。
    """
    start_str, end_str = time_range.split('~')
    start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
    tz = pytz.timezone('Asia/Taipei')
    return tz.localize(start), tz.localize(end)


def generate_xml_epg(channels: List[Dict], programs: List[Dict]) -> ET.ElementTree:
    """
    根据频道列表和节目列表生成符合 XMLTV 格式的 EPG XML 文档。

    该函数会使用 CHANNEL_ID_MAPPING 进行两项映射：
        1. 将原始频道名（original_channel_id）映射为自定义频道ID（new_channel_id），
           用于 <channel id="..."> 和 <programme channel="...">。
        2. 若映射项中提供了非空的 new_channel_name，则将其用作 <display-name> 的内容；
           否则，使用原始频道名称并追加 " (hami)" 作为显示名。

    Args:
        channels: 频道列表，每个频道需包含 'channelName' 和 'contentPk'。
        programs: 节目列表，每个节目需包含 'channelId', 'programName',
                  'description', 'start', 'end'。

    Returns:
        xml.etree.ElementTree.ElementTree 对象，可直接写入文件。
    """
    # 创建根元素 <tv>
    root = ET.Element("tv")
    root.set("generator-info-name", "yufeilai666")
    root.set("generator-info-url", "https://github.com/yufeilai666")

    # 构建映射字典：ID映射 + 显示名映射（可选）
    id_map = {item["original_channel_id"]: item["new_channel_id"] for item in CHANNEL_ID_MAPPING}
    # 构建 original_channel_id -> new_channel_name 的映射（如果存在且非空）
    name_map = {
        item["original_channel_id"]: item.get("new_channel_name")
        for item in CHANNEL_ID_MAPPING
        if item.get("new_channel_name")
    }
    # 构建 contentPk -> 频道原始名称 的映射（只构建一次）
    content_to_name = {ch["contentPk"]: ch["channelName"] for ch in channels}

    # 先添加所有 <channel> 定义
    for channel in channels:
        # 明确区分用于映射的原始标识符和用于显示的名称（当前值相同但语义分离）
        original_id = channel["channelName"]      # 用于映射和作为 channel id 的基础
        original_name = channel["channelName"]    # 用于显示名称（若未指定新名称）

        # 根据映射决定频道ID，若无映射则使用原始名称
        channel_id = id_map.get(original_id, original_id)

        # 决定 display-name 的内容
        custom_name = name_map.get(original_id)
        if custom_name:
            display_name = custom_name
        else:
            display_name = original_name + " (hami)"   # 默认加上后缀

        channel_elem = ET.SubElement(root, "channel")
        channel_elem.set("id", channel_id)

        display_name_elem = ET.SubElement(channel_elem, "display-name")
        display_name_elem.text = display_name

    # 然后添加所有 <programme> 条目
    for program in programs:
        # 通过 contentPk 反查原始频道名称（即原始ID）
        original_id = content_to_name.get(program["channelId"], program["channelId"])
        # 应用相同的映射，确保与对应 <channel> 的 id 一致
        channel_id = id_map.get(original_id, original_id)

        programme = ET.SubElement(root, "programme")
        programme.set("start", program["start"].strftime("%Y%m%d%H%M%S %z"))
        programme.set("stop", program["end"].strftime("%Y%m%d%H%M%S %z"))
        programme.set("channel", channel_id)

        title = ET.SubElement(programme, "title")
        title.set("lang", "zh")
        title.text = program["programName"]

        if program["description"]:
            desc = ET.SubElement(programme, "desc")
            desc.set("lang", "zh")
            desc.text = program["description"]

        # 添加预设的分类标签
        for category_text in CATEGORIES:
            category = ET.SubElement(programme, "category")
            category.set("lang", "zh")
            category.text = category_text

    return ET.ElementTree(root)


# ---------- 主入口 ----------

async def main() -> None:
    """
    主异步函数，负责执行完整的 EPG 获取与 XML 生成流程。
    包括：
        1. 创建输出目录
        2. 获取所有频道及节目
        3. 生成 XML 文件并保存
        4. 输出最终统计信息
    """
    logger.info("🚀 开始生成Hami电视节目表...")

    # 确定输出目录（项目根目录下的 output 文件夹）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    output_dir = os.path.join(project_root, "output")
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"📁 输出目录: {output_dir}")
    logger.info(f"🏷️  使用分类: {CATEGORIES}")

    # 创建 HTTP 客户端（包含连接池限制）
    async with httpx.AsyncClient(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
    ) as client:
        channels, programs = await request_all_epg(client)

        # 生成 XML
        xml_tree = generate_xml_epg(channels, programs)
        root = xml_tree.getroot()
        output_file = os.path.join(output_dir, EPG_NAME)

        # 美化 XML 并写入文件（兼容 Python 3.8 及更低版本）
        try:
            # Python 3.9+ 使用内置 indent
            ET.indent(root, space="  ")
            tree = ET.ElementTree(root)
            with open(output_file, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                tree.write(f, encoding="utf-8", xml_declaration=False)
        except AttributeError:
            # Python 3.8 及以下使用 minidom 美化
            from xml.dom import minidom
            rough_string = ET.tostring(root, encoding='unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")
            lines = pretty_xml.splitlines()
            if lines and lines[0].startswith('<?xml'):
                lines = lines[1:]
            pretty_xml = "\n".join(lines)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write(pretty_xml)

        logger.success(f"\n✅ 电视节目表已成功生成: {output_file}")
        logger.info(f"📊 文件大小: {os.path.getsize(output_file) / 1024:.2f} KB")
        logger.info(f"📺 频道数: {len(channels)}")
        logger.info(f"🎬 节目数: {len(programs)}")


if __name__ == '__main__':
    # 配置 loguru 日志（默认只输出到控制台，可取消注释以保存到文件）
    logger.remove()
    # logger.add("hami_epg.log", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
    asyncio.run(main())