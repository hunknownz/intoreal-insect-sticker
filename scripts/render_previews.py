#!/usr/bin/env python3
import json
from collections import defaultdict
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIEWS = PROJECT_ROOT / "previews"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
PAPER = "#F2EEE4"
CARD = "#FAF8F2"
INK = "#202622"
MUTED = "#667069"
RULE = "#D5CEBE"
ACCENT = "#5E6E5A"


def font(size, chinese=False):
    return ImageFont.truetype(SONGTI if chinese else ARIAL, size)


def text(draw, xy, value, size, fill=INK, chinese=False, anchor=None):
    chinese = chinese or any("\u4e00" <= character <= "\u9fff" for character in value)
    draw.text(xy, value, font=font(size, chinese), fill=fill, anchor=anchor)


def fit_sticker(path, maximum):
    with Image.open(path) as source:
        source = source.convert("RGBA")
        source.thumbnail(maximum, Image.Resampling.LANCZOS)
        return source.copy()


def base_canvas(width, height):
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    for x in range(80, width, 160):
        draw.line((x, 0, x, height), fill="#E7E0D3", width=1)
    for y in range(80, height, 160):
        draw.line((0, y, width, y), fill="#E7E0D3", width=1)
    draw.rectangle((40, 40, width - 41, height - 41), outline=RULE, width=2)
    return image, draw


def render_grid(records, title, kicker, output, subtitle=None, columns=None):
    width = 2400
    count = len(records)
    columns = columns or (1 if count == 1 else 2 if count <= 4 else 3 if count <= 6 else 4)
    rows = (count + columns - 1) // columns
    gap_x, gap_y = 42, 38
    grid_width = 2180
    card_width = (grid_width - gap_x * (columns - 1)) // columns
    card_height = 850 if rows == 1 else 430
    grid_height = rows * card_height + (rows - 1) * gap_y
    start_y = 326
    height = max(1350, start_y + grid_height + 124)
    image, draw = base_canvas(width, height)
    text(draw, (110, 92), kicker, 26, MUTED)
    text(draw, (108, 132), title, 68, INK, chinese=True)
    count_label = f"{len(records):02d} SPECIES"
    text(draw, (2290, 108), count_label, 28, MUTED, anchor="ra")
    if subtitle:
        text(draw, (112, 224), subtitle, 24, MUTED)
    draw.line((110, 278, 2290, 278), fill=RULE, width=2)
    total_width = card_width * columns + gap_x * (columns - 1)
    start_x = (width - total_width) // 2
    for index, row in enumerate(records):
        column = index % columns
        line = index // columns
        x = start_x + column * (card_width + gap_x)
        y = start_y + line * (card_height + gap_y)
        draw.rounded_rectangle((x + 5, y + 8, x + card_width + 5, y + card_height + 8), radius=18, fill="#DED8CA")
        draw.rounded_rectangle((x, y, x + card_width, y + card_height), radius=18, fill=CARD, outline=RULE, width=2)
        draw.line((x + 24, y + 62, x + card_width - 24, y + 62), fill=RULE, width=1)
        text(draw, (x + 24, y + 24), f"{index + 1:02d}", 22, MUTED)
        text(draw, (x + card_width - 24, y + 24), row["taxonomy"]["order"].upper(), 18, MUTED, anchor="ra")
        maximum = (card_width - 70, card_height - 220)
        sticker = fit_sticker(PROJECT_ROOT / row["sticker"]["file"], maximum)
        sx = x + (card_width - sticker.width) // 2
        sy = y + 82 + (card_height - 220 - sticker.height) // 2
        image.paste(sticker, (sx, sy), sticker)
        label_y = y + card_height - 112
        draw.line((x + 24, label_y - 18, x + card_width - 24, label_y - 18), fill=RULE, width=1)
        text(draw, (x + 24, label_y), row["scientificName"], 28 if card_width > 500 else 22, INK)
        text(draw, (x + 24, label_y + 44), row["names"]["zh-Hans"], 25 if card_width > 500 else 20, ACCENT, chinese=True)
        text(draw, (x + card_width - 24, label_y + 50), f"{row['sticker']['reviewScore']}/100", 19, MUTED, anchor="ra")
    text(draw, (112, height - 78), "INTOREAL  ·  SPECIMEN DRAWER  ·  REVIEWED NATURAL-HISTORY ILLUSTRATIONS", 22, MUTED)
    text(draw, (2290, height - 78), "ALPHA WEBP  /  1000 PX", 22, MUTED, anchor="ra")
    output.parent.mkdir(parents=True, exist_ok=True)
    png = output.with_suffix(".png")
    image.save(png)
    image.save(output, "WEBP", quality=93, method=6)
    png.unlink()


def render_header(records):
    width, height = 2400, 900
    image, draw = base_canvas(width, height)
    text(draw, (112, 100), "INTOREAL  /  INSECT STICKERS", 28, MUTED)
    text(draw, (108, 156), "昆虫图鉴", 86, INK, chinese=True)
    text(draw, (112, 278), "形态有证据，识别有秩序。", 34, ACCENT, chinese=True)
    draw.line((112, 352, 920, 352), fill=RULE, width=2)
    text(draw, (112, 390), f"{len(records):02d} REVIEWED SPECIES", 25, MUTED)
    text(draw, (112, 438), "TRANSPARENT WEBP  ·  PRIMARY + BLIND REVIEW", 22, MUTED)
    positions = [(1060, 100, 560), (1570, 36, 660), (2020, 164, 430)]
    for row, (cx, y, size) in zip(records, positions):
        sticker = fit_sticker(PROJECT_ROOT / row["sticker"]["file"], (size, 680))
        image.paste(sticker, (cx - sticker.width // 2, y + (680 - sticker.height) // 2), sticker)
    text(draw, (112, 802), "A QUIET TAXONOMY OF LIVING FORM", 22, MUTED)
    output = PREVIEWS / "header.webp"
    output.parent.mkdir(parents=True, exist_ok=True)
    png = output.with_suffix(".png")
    image.save(png)
    image.save(output, "WEBP", quality=93, method=6)
    png.unlink()


def main():
    records = json.loads((PROJECT_ROOT / "data/species.json").read_text(encoding="utf-8"))["species"]
    if not records:
        raise ValueError("没有已发布物种，拒绝生成空预览")
    render_header(records)
    render_grid(records, "全球昆虫图鉴", "INTOREAL  /  NATURAL HISTORY COLLECTION", PREVIEWS / "hero.webp", "每一种形态，都经过独立核对。")
    render_grid(records, "目级标本", "TAXONOMIC DRAWERS  /  ORDERS", PREVIEWS / "orders.webp", "以统一视觉尺度观察不同目级形态。")
    families = defaultdict(list)
    for row in records:
        families[row["taxonomy"]["family"]].append(row)
    for family, items in sorted(families.items()):
        render_grid(items, family, "FAMILY DRAWER  /  科级图鉴", PREVIEWS / "families" / f"{family.lower()}.webp", f"{len(items)} 个已审核物种")
    print(json.dumps({"ok": True, "species": len(records), "families": sorted(families), "previews": ["header.webp", "hero.webp", "orders.webp"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
