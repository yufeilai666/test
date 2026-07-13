"""
节目单图片 OCR 识别并生成 XMLTV 格式文件。

【功能概述】
- 使用 EasyOCR 识别图片中的文字（黑底白字，自动反转并裁边）。
- 解析日期和时间，将节目按日分组。
- 生成符合 XMLTV 标准的节目单，每日节目结束后插入“收播”占位（除非是最后一天）。
- 为每个节目（包括收播占位）添加固定的分类标签 ['yufeilai666', 'gehua']。
- 包含 OCR 常见错字修正字典（已优化：修正手足→王贵，U→1时间转换等）。
- 新增打印前 400 行原始 OCR 识别结果，方便调试核对。

【输入说明】
- 来源目录：epg/cwjd_ocr/
- 输入格式：自动识别目录下的最新图片（支持 .jpg, .png, .webp 等常见格式）

【输出说明】
- 输出目录：epg/
- 输出文件：cwjd_epg_another.xml（XMLTV 格式标准节目单）
"""

import os
import re
import io
import xml.sax.saxutils as saxutils
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageOps
import numpy as np
import easyocr
from itertools import groupby

# ---------------------------- 配置 ----------------------------
EPG_NAME = "cwjd_epg_another1.xml"  # EPG文件名
CATEGORY_TAGS: List[str] = ["yufeilai666", "gehua"]          # 固定的分类标签

# 🔥 初始化 EasyOCR 阅读器 (中文+数字/英文)
# gpu=False 表示使用 CPU 运行，如果需要 GPU 加速可改为 True
READER = easyocr.Reader(['ch_sim', 'en'], gpu=False)  

CROP_PADDING: int = 8                                       # 裁剪边缘保留的像素，防止括号被切

# 针对“从原始识别数据解析节目，得到标题”之后
# 标题错字修正映射表（格式：错误 -> 正确）
TITLE_CORRECTIONS: Dict[str, str] = {
    '哪呈': '哪吒',
    '哪吴': '哪吒',
    '元籼': '元帅',
    '王趴与': '王贵与',
    '手足与': '王贵与',
    '河西走请': '河西走廊',
    '河西走确': '河西走廊',
    '乌贫记': '乌盆记',
    '打倒上坟': '打侄上坟',
    "军工记忆:": "军工记忆·",
    "军工记忆.": "军工记忆·",
    "有酬美33了": "醉美331 ",
    "酬美331": "醉美331",
    "醇美331": "醉美331",
    "钦娃": "猴娃",
    "独吼记.": "狮吼记·",
    "独吼记:": "狮吼记·"
}

# 针对“原始识别结果”数据
# 🔥 修正映射表（格式：模式字符串 -> (替换内容, 模式类型)）
# 模式类型支持 "text"（纯文本）和 "regex"（正则表达式）
# 使用纯文本时，会查找行内是否包含该字符串并替换；使用正则时可以匹配模糊变体
LINE_CORRECTIONS: Dict[str, Tuple[str, str]] = {
    # 纯文本替换模式示例
    "ES55央本38国(2": ("11:55 醉美331 吉林篇02", "text"),
    ":58几本关33几十1休起03": ("11:58 醉美331 吉林篇03", "text"),
}


def clean_title(title: str) -> str:
    """
    清洗标题：合并多余空格，修正常见的 OCR 错字，去除首尾干扰标点。
    """
    title = re.sub(r'\s+', ' ', title).strip()
    for wrong, right in TITLE_CORRECTIONS.items():
        title = title.replace(wrong, right)
    # 去除首尾无效标点（注意保留括号，不删括号）
    title = re.sub(r'^[，。、！？；：,.!?;:\'"“”‘’]+', '', title)
    title = re.sub(r'[，。、！？；：,.!?;:\'"“”‘’]+$', '', title)
    return title


def parse_schedule_from_image(image_bytes: bytes) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    对图片进行 EasyOCR 识别，提取节目单数据，并返回原始识别文本行。
    """
    # 1. 打开图片并转为灰度
    img = Image.open(io.BytesIO(image_bytes)).convert('L')
    # 2. 反色（黑底白字→白底黑字），利于 OCR 识别
    img = ImageOps.invert(img)
    # 3. 智能裁剪（保留边缘，防止括号被切）
    bbox = img.getbbox()
    if bbox:
        img = img.crop((
            max(0, bbox[0] - CROP_PADDING),
            max(0, bbox[1] - CROP_PADDING),
            min(img.width, bbox[2] + CROP_PADDING),
            min(img.height, bbox[3] + CROP_PADDING)
        ))
    # 4. 将图片转为 RGB（EasyOCR 需要 RGB 模式）
    img = img.convert('RGB')

    lines = []
    # 因为长图可能超过 EasyOCR 的最佳分辨率，我们依然保留你原来的切块逻辑
    CHUNK_HEIGHT = 3800
    OVERLAP = 200
    w, h = img.size
    print(f"🔍 图片高度 {h}px，固定切分为 {CHUNK_HEIGHT}px/块，重叠 {OVERLAP}px")

    chunks: List[Image.Image] = []
    if h <= CHUNK_HEIGHT:
        chunks.append(img)
    else:
        for y in range(0, h, CHUNK_HEIGHT - OVERLAP):
            end_y = min(y + CHUNK_HEIGHT, h)
            chunk = img.crop((0, y, w, end_y))
            chunks.append(chunk)

    print(f"✂️ 共切分成 {len(chunks)} 个子块，开始逐块识别...")
    for i, chunk in enumerate(chunks):
        # 将 PIL 图像转为 Numpy 数组，方便 EasyOCR 处理
        img_np = np.array(chunk)
        # 调用 EasyOCR，detail=0 表示只返回纯文本列表
        chunk_lines = READER.readtext(img_np, detail=0)
        print(f"  子块 {i + 1}/{len(chunks)} 识别到 {len(chunk_lines)} 行")
        lines.extend(chunk_lines)

    # 🔥 原始识别行修正：在解析之前，对 OCR 严重错误的行进行替换（兼容纯文本和正则）
    for i in range(len(lines)):
        for pattern, (replacement, mode) in LINE_CORRECTIONS.items():
            if mode == "text":
                # 纯文本匹配：只要行内包含该字符串，就替换（只替换这一部分）
                if pattern in lines[i]:
                    lines[i] = lines[i].replace(pattern, replacement)
                    break  # 替换后跳过当前行剩下的匹配，避免重复替换
            elif mode == "regex":
                # 正则匹配：如果模式匹配该行，就替换匹配的部分
                if re.search(pattern, lines[i]):
                    lines[i] = re.sub(pattern, replacement, lines[i])
                    break

    schedule: List[Dict[str, str]] = []
    current_date: Optional[str] = None

    date_pattern = re.compile(r'(\d{4})/(\d{2})/(\d{2})')
    # 注意：\s* 匹配 0 个或多个空白，用于兼容 OCR 漏掉空格的情况
    time_pattern = re.compile(r'^(\d{2}):(\d{2})\s*(.*)$')

    for line in lines:
        line = line.strip()
        # 清除行首隐藏的零宽空格和 BOM
        line = re.sub(r'^[\s\u200B\uFEFF]+', '', line)
        # 清除整行内所有零宽空格、零宽连字、不连字及 BOM（防止乱码干扰匹配）
        line = re.sub(r'[\u200B-\u200D\uFEFF]+', '', line)

        if not line:
            continue

        # 识别日期行（先尝试匹配完整的 YYYY/MM/DD）
        date_match = date_pattern.search(line)
        if date_match:
            current_date = f"{date_match.group(1)}{date_match.group(2)}{date_match.group(3)}"
            continue

        # ✅ 备选修复：如果日期被 OCR 识别错误（如 Ce 星期二），但保留了“星期X”信息
        if current_date and re.search(r'星期[一二三四五六日]', line):
            weekday_match = re.search(r'星期([一二三四五六日])', line)
            if weekday_match:
                weekday_map = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6}
                target_weekday = weekday_map[weekday_match.group(1)]
                current_dt = datetime.strptime(current_date, "%Y%m%d")
                current_weekday = current_dt.weekday()
                # 计算目标日期与当前日期的偏移（如果目标星期小于或等于当前，说明是下一周）
                offset = target_weekday - current_weekday
                if offset <= 0:
                    offset += 7
                new_dt = current_dt + timedelta(days=offset)
                current_date = new_dt.strftime("%Y%m%d")
                continue  # 这一行是日期行，解析为日期后直接跳过，不进入节目解析

        # 识别节目行
        if current_date:
            # ✅ 关键修复：直接按索引判断分钟的第二位是否为 O/U（如 15:0U），屏蔽前序匹配干扰
            if len(line) >= 5 and line[2] == ':' and line[4] in 'OoUu':
                fixed_minutes = line[3:5].replace('O', '0').replace('o', '0').replace('U', '1').replace('u', '1')
                line = line[:3] + fixed_minutes + line[5:]

            time_match = time_pattern.match(line)
            if time_match:
                hour, minute = time_match.group(1), time_match.group(2)
                title_raw = time_match.group(3).strip()
                title = clean_title(title_raw)
                if title:
                    schedule.append({
                        "date": current_date,
                        "time": f"{hour}{minute}",
                        "title": title
                    })
    return schedule, lines


def generate_xmltv(schedule: List[Dict[str, str]]) -> str:
    """
    将节目列表转换为 XMLTV 格式的字符串。
    """
    if not schedule:
        return ""

    schedule.sort(key=lambda x: (x['date'], x['time']))

    groups: List[tuple] = []
    for date_str, items in groupby(schedule, key=lambda x: x['date']):
        groups.append((date_str, list(items)))

    xml_lines: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<tv generator-info-name="yufeilai666" generator-info-url="https://github.com/yufeilai666">'
    ]
    xml_lines.append('  <channel id="重温经典">')
    xml_lines.append('    <display-name>重温经典频道</display-name>')
    xml_lines.append('  </channel>')

    for day_idx, (date_str, items) in enumerate(groups):
        for i, item in enumerate(items):
            start_dt = datetime.strptime(f"{item['date']}{item['time']}", "%Y%m%d%H%M")
            start_str = start_dt.strftime("%Y%m%d%H%M%S") + " +0800"

            if i + 1 < len(items):
                next_item = items[i + 1]
                next_dt = datetime.strptime(f"{next_item['date']}{next_item['time']}", "%Y%m%d%H%M")
                stop_str = next_dt.strftime("%Y%m%d%H%M%S") + " +0800"
            else:
                next_date_obj = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=1)
                next_dt = datetime.combine(next_date_obj, datetime.min.time())
                stop_str = next_dt.strftime("%Y%m%d%H%M%S") + " +0800"

            safe_title = saxutils.escape(item['title'])
            xml_lines.append(f'  <programme start="{start_str}" stop="{stop_str}" channel="重温经典">')
            xml_lines.append(f'    <title>{safe_title}</title>')
            for cat in CATEGORY_TAGS:
                xml_lines.append(f'    <category>{cat}</category>')
            xml_lines.append('  </programme>')

            if i == len(items) - 1 and day_idx + 1 < len(groups):
                placeholder_start_dt = next_dt
                next_day_items = groups[day_idx + 1][1]
                if next_day_items:
                    first_next_item = next_day_items[0]
                    placeholder_stop_dt = datetime.strptime(
                        f"{first_next_item['date']}{first_next_item['time']}", "%Y%m%d%H%M"
                    )
                else:
                    placeholder_stop_dt = placeholder_start_dt + timedelta(hours=1)

                placeholder_start_str = placeholder_start_dt.strftime("%Y%m%d%H%M%S") + " +0800"
                placeholder_stop_str = placeholder_stop_dt.strftime("%Y%m%d%H%M%S") + " +0800"

                xml_lines.append(f'  <programme start="{placeholder_start_str}" stop="{placeholder_stop_str}" channel="重温经典">')
                xml_lines.append(f'    <title>收播</title>')
                for cat in CATEGORY_TAGS:
                    xml_lines.append(f'    <category>{cat}</category>')
                xml_lines.append('  </programme>')

    xml_lines.append('</tv>')
    return "\n".join(xml_lines)


def main() -> None:
    IMG_DIR = Path("epg/cwjd_ocr")
    if not IMG_DIR.exists():
        raise FileNotFoundError(f"目录不存在: {IMG_DIR}")

    files = [f for f in IMG_DIR.iterdir() if f.is_file()]
    if not files:
        raise FileNotFoundError(f"目录 {IMG_DIR} 中没有找到任何文件")

    latest_img_file = max(files, key=lambda f: f.stat().st_mtime)
    print(f"找到最新图片：{latest_img_file}")

    image_bytes = latest_img_file.read_bytes()
    print("正在通过 EasyOCR 识别图片内容，请稍候...")
    schedule, raw_lines = parse_schedule_from_image(image_bytes)
    print(f"成功解析出 {len(schedule)} 个节目。\n")

    print("*" * 34)
    print("--- 前400行原始识别结果 ---")
    max_lines = min(400, len(raw_lines))
    for i in range(max_lines):
        print(f"  [{i+1}] {raw_lines[i]}")
    print("--- 原始识别结果结束 ---\n")
    
    print("*" * 34)
    print("--- 前300行识别结果（解析后）---")
    for i, item in enumerate(schedule[:300]):
        print(f"  [{i+1}] {item['date']} {item['time']} - {item['title']}")
    print("--- 预览结束 ---\n")

    xml_content = generate_xmltv(schedule)
   
    print("*" * 34)
    print("--- XMLTV 文件前 10 行预览 ---")
    for line in xml_content.splitlines()[:10]:
        print(line)
    print("--- 预览结束 ---\n")
    
    print("=" * 34)

    OUTPUT_DIR = Path("epg")
    OUTPUT_DIR.mkdir(exist_ok=True)
    file_path = OUTPUT_DIR / EPG_NAME
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(xml_content)
    print(f"XMLTV 文件保存成功：{file_path}")
    print("=" * 34)


if __name__ == "__main__":
    main()