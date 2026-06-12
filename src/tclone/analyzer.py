import asyncio
import os
import re
import sys
from datetime import datetime
from math import log10

from PIL import Image, ImageDraw, ImageFont
from telethon import errors
from telethon.tl import types

from .forward import parse_telegram_target, _should_ignore_message
from .session import create_and_start_client


def _human_bytes(n):
    n = int(n or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(v)} {u}"
            return f"{v:.2f} {u}"
        v /= 1024.0


def _bytes_to_gb(n):
    return float(int(n or 0)) / (1024.0**3)


def _bytes_to_tb(n):
    return float(int(n or 0)) / (1024.0**4)


def _read_xdg_user_dir(var_name, fallback):
    try:
        cfg_fp = os.path.join(os.path.expanduser("~"), ".config", "user-dirs.dirs")
        if not os.path.exists(cfg_fp):
            return fallback
        with open(cfg_fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith(var_name + "="):
                    continue
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                value = value.replace("$HOME", os.path.expanduser("~"))
                value = os.path.expanduser(value)
                return value
    except Exception:
        return fallback
    return fallback


def _default_reports_dir():
    home = os.path.expanduser("~")
    termux_pictures = os.path.join(home, "storage", "pictures")
    if os.path.isdir(termux_pictures):
        return termux_pictures

    pictures = _read_xdg_user_dir("XDG_PICTURES_DIR", os.path.join(home, "Pictures"))
    return pictures


def _sanitize_filename(name):
    name = (name or "group").strip()
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        name = "group"
    return name


def _get_photo_size_bytes(photo):
    if not photo:
        return 0
    sizes = getattr(photo, "sizes", None) or []
    best = None
    best_area = -1
    for s in sizes:
        w = getattr(s, "w", None)
        h = getattr(s, "h", None)
        if w is None or h is None:
            continue
        area = int(w) * int(h)
        if area > best_area:
            best_area = area
            best = s
    if best is not None:
        return int(getattr(best, "size", 0) or 0)
    for s in sizes:
        if hasattr(s, "size"):
            return int(getattr(s, "size", 0) or 0)
    return 0


def _get_message_media_info(msg):
    media = getattr(msg, "media", None)
    if media is None:
        return None, 0

    if isinstance(media, types.MessageMediaPhoto):
        b = _get_photo_size_bytes(getattr(media, "photo", None))
        return "photos", b

    if isinstance(media, types.MessageMediaDocument):
        doc = getattr(media, "document", None)
        if doc is None:
            return "documents", 0
        size = int(getattr(doc, "size", 0) or 0)
        mime = str(getattr(doc, "mime_type", "") or "").lower()

        if mime.startswith("video/"):
            return "videos", size
        if mime.startswith("audio/"):
            return "audios", size
        if mime.startswith("image/"):
            return "images", size
        return "documents", size

    if isinstance(media, types.MessageMediaWebPage):
        return "webpages", 0

    return "other", 0


def _scaled_height(value, max_value, height):
    value = int(value or 0)
    max_value = int(max_value or 0)
    if max_value <= 0:
        return 0

    # Log scale so tiny categories still show up when one category dominates.
    # log10(1) = 0, log10(max+1) maps to 1.
    s = log10(value + 1) / log10(max_value + 1)
    return int(s * height)


def _draw_report_png(output_path, title, totals, counts, total_bytes, base_dir=None):
    w, h = 1600, 900
    bg = (17, 21, 28)
    panel = (23, 30, 41)
    accent = (124, 92, 255)
    text = (235, 241, 255)
    muted = (160, 170, 190)

    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    fonts_dirs = []
    if base_dir:
        fonts_dirs.append(os.path.join(str(base_dir), "fonts"))
    fonts_dirs.append(os.path.join(repo_root, "fonts"))

    def _first_existing(*names):
        for d in fonts_dirs:
            for n in names:
                fp = os.path.join(d, n)
                if os.path.exists(fp):
                    return fp
        return os.path.join(fonts_dirs[-1], names[0])

    bold_fp = _first_existing("DejaVuSans-Bold.ttf")
    regular_fp = _first_existing("DejaVuSans.ttf")

    try:
        font_title = ImageFont.truetype(bold_fp, 44)
        font_sub = ImageFont.truetype(regular_fp, 22)
        font_small = ImageFont.truetype(regular_fp, 18)
        font_tiny = ImageFont.truetype(regular_fp, 16)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_tiny = ImageFont.load_default()

    margin = 30
    draw.rounded_rectangle(
        (margin, margin, w - margin, h - margin),
        radius=18,
        fill=panel,
    )

    header_y = margin + 22
    draw.text((margin + 26, header_y), title, font=font_title, fill=text)
    draw.text(
        (margin + 26, header_y + 46),
        f"Estimated media total: {_human_bytes(total_bytes)}",
        font=font_sub,
        fill=muted,
    )

    chart_left = margin + 26
    chart_right = w - margin - 26
    chart_top = header_y + 125
    footer_h = 58
    labels_h = 115
    chart_bottom = h - margin - footer_h - labels_h

    keys = ["videos", "documents", "photos", "images", "audios", "webpages", "other"]
    labels = {
        "videos": "Videos",
        "documents": "Documents",
        "photos": "Photos",
        "images": "Images",
        "audios": "Audio",
        "webpages": "Links",
        "other": "Other",
    }

    data = [(k, int(totals.get(k, 0) or 0)) for k in keys]
    max_v = max([v for _, v in data] + [1])

    bar_area_w = chart_right - chart_left
    bar_area_h = chart_bottom - chart_top
    n = len(data)
    gap = 14
    bar_w = int((bar_area_w - gap * (n - 1)) / n)

    # Subtle grid lines
    grid_color = (40, 50, 70)
    for j in range(1, 5):
        yy = chart_top + int((chart_bottom - chart_top) * (j / 5))
        draw.line((chart_left, yy, chart_right, yy), fill=grid_color, width=1)

    bar_max_h = max(1, bar_area_h - 14)

    for i, (k, v) in enumerate(data):
        x0 = chart_left + i * (bar_w + gap)
        x1 = x0 + bar_w
        bh = _scaled_height(v, max_v, bar_max_h)
        if v > 0:
            bh = max(bh, 8)
        y1 = chart_bottom
        y0 = y1 - bh

        draw.rounded_rectangle((x0, y0, x1, y1), radius=12, fill=accent)

        label = labels.get(k, k)
        pct = (float(v) / float(total_bytes) * 100.0) if total_bytes else 0.0
        draw.text((x0, chart_bottom + 12), label, font=font_small, fill=muted)
        draw.text((x0, chart_bottom + 36), _human_bytes(v), font=font_small, fill=text)
        draw.text((x0, chart_bottom + 60), f"{pct:.2f}%", font=font_tiny, fill=muted)
        draw.text(
            (x0, y0 - 18),
            f"{int(counts.get(k, 0) or 0)}",
            font=font_tiny,
            fill=muted,
        )

    footer = f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    draw.text((margin + 26, h - margin - 36), footer, font=font_tiny, fill=muted)

    img.save(output_path, format="PNG")


async def run_analyzer(cfg, args):
    api_id = int(cfg["api_id"])
    api_hash = str(cfg["api_hash"])

    target = cfg.get("target")
    if getattr(args, "target", None) is not None:
        target = args.target
    if target is None:
        raise ValueError("Missing target. Use --target or set 'target' in config.yml")

    session_name = str(cfg.get("session_name", "session"))

    client = await create_and_start_client(session_name, api_id, api_hash)
    try:
        target_chat, _ = parse_telegram_target(target)
    except Exception:
        if not getattr(args, "quiet", False):
            print("Invalid target. Check that your peer ID/username/link is valid.")
        await client.disconnect()
        return 2

    try:
        target_entity = await client.get_entity(target_chat)
    except (
        errors.ChatIdInvalidError,
        errors.PeerIdInvalidError,
        errors.UsernameInvalidError,
        errors.UsernameNotOccupiedError,
    ):
        if not getattr(args, "quiet", False):
            print("Invalid target. Check that your peer ID/username/link is valid.")
        await client.disconnect()
        return 2
    except Exception as e:
        if not getattr(args, "quiet", False):
            print(f"Failed to resolve target: {e}")
        await client.disconnect()
        return 2

    title = getattr(target_entity, "title", None) or str(target)
    safe_name = _sanitize_filename(title)
    
    ignore_topics = cfg.get("ignore_topics", [])
    if not isinstance(ignore_topics, list):
        ignore_topics = []
    
    target_chat_id = getattr(target_entity, "id", None) or target_chat

    out_dir = str(cfg.get("reports_dir") or _default_reports_dir())
    os.makedirs(out_dir, exist_ok=True)

    report_path = os.path.join(out_dir, f"{safe_name}.txt")
    image_path = os.path.join(out_dir, f"{safe_name}.png")

    totals = {}
    counts = {}
    total_messages = 0
    media_messages = 0

    spinner = iter("|/-\\")

    try:
        async for msg in client.iter_messages(target_entity, reverse=True):
            if _should_ignore_message(msg, target_chat_id, None, ignore_topics):
                continue
            
            total_messages += 1
            kind, b = _get_message_media_info(msg)
            if kind is not None:
                media_messages += 1
                totals[kind] = int(totals.get(kind, 0)) + int(b)
                counts[kind] = int(counts.get(kind, 0)) + 1


            if not getattr(args, "quiet", False) and total_messages % 250 == 0:
                ch = next(spinner, "|")
                sys.stdout.write(
                    f"\rAnalyzing... {ch} messages={total_messages} media={media_messages}"
                )
                sys.stdout.flush()

        if not getattr(args, "quiet", False):
            sys.stdout.write("\r" + " " * 120 + "\r")
            sys.stdout.flush()

        total_bytes = sum(int(v or 0) for v in totals.values())

        is_group = isinstance(target_entity, types.Chat) or (
            isinstance(target_entity, types.Channel) and bool(getattr(target_entity, "megagroup", False))
        )
        storage_header = "GROUP STORAGE" if is_group else "CHANNEL STORAGE"
        name_label = "Group name" if is_group else "Channel name"

        lines = []
        lines.append(f"📊 {storage_header}")
        lines.append("------------------------------")

        total_gb = _bytes_to_gb(total_bytes)
        total_tb = _bytes_to_tb(total_bytes)

        lines.append(f"🧮 In GB: {total_gb:,.2f} GB")
        lines.append(f"🗄️ In TB: {total_tb:,.4f} TB")
        lines.append(f"📦 Total size: {_human_bytes(total_bytes)}")
        lines.append("------------------------------")
        lines.append(f"🏷️ {name_label}: {title}")
        lines.append(f"💬 Messages analyzed: {total_messages}")
        lines.append(f"📎 Messages with media: {media_messages}")
        lines.append("------------------------------")

        # Keep the report intentionally short (Telegram-message style)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        _draw_report_png(
            image_path,
            title,
            totals,
            counts,
            total_bytes,
            base_dir=cfg.get("base_dir"),
        )

        if not getattr(args, "quiet", False):
            print(f"Report saved: {report_path}")
            print(f"Chart saved: {image_path}")

    finally:
        await client.disconnect()

    return 0
