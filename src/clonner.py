import asyncio
import os
import tempfile
from datetime import datetime

import itertools
import random
import sys

from PIL import Image, ImageDraw, ImageFont
from telethon import errors
from telethon.tl import functions, types

from forward import load_offsets, make_offset_key, parse_telegram_target, save_offsets, _should_ignore_message, _normalize_ignore_list
from runtime import FONTS_DIR
from session import create_and_start_client


def _clear_status_line():
    sys.stdout.write("\r" + " " * 120 + "\r")
    sys.stdout.flush()


async def _countdown(seconds, quiet=False, prefix="Pausing..."):
    for remaining in range(seconds, 0, -1):
        if not quiet:
            msg = f"{prefix} {remaining}s remaining"
            sys.stdout.write("\r" + msg.ljust(120))
            sys.stdout.flush()
        await asyncio.sleep(1)

    if not quiet:
        _clear_status_line()


async def _call_with_floodwait(call_factory, log, label, max_retries=5):
    attempt = 0
    while True:
        try:
            return await call_factory()
        except errors.FloodWaitError as e:
            attempt += 1
            wait_s = int(getattr(e, "seconds", 0)) + 5
            log(f"FloodWait on {label}: sleeping {wait_s}s")

            if not getattr(log, "quiet", False):
                for remaining in range(wait_s, 0, -1):
                    sys.stdout.write(f"\rFloodWait on {label}: sleeping {remaining}s")
                    sys.stdout.flush()
                    await asyncio.sleep(1)
                _clear_status_line()
            else:
                await asyncio.sleep(wait_s)

            if attempt >= max_retries:
                raise


async def _forward_message_to_topic(
    client,
    source_entity,
    target_entity,
    msg_id,
    target_topic_id,
    drop_author,
    log,
):
    from_peer = await client.get_input_entity(source_entity)
    to_peer = await client.get_input_entity(target_entity)
    random_id = random.randint(-(2**63), 2**63 - 1)

    try:
        return await _call_with_floodwait(
            lambda: client(
                functions.messages.ForwardMessagesRequest(
                    from_peer=from_peer,
                    id=[msg_id],
                    to_peer=to_peer,
                    top_msg_id=target_topic_id,
                    drop_author=bool(drop_author),
                    silent=True,
                    random_id=[random_id],
                )
            ),
            log,
            "ForwardMessagesRequest(top_msg_id)",
        )
    except TypeError:
        pass

    try:
        return await _call_with_floodwait(
            lambda: client(
                functions.messages.ForwardMessagesRequest(
                    from_peer=from_peer,
                    id=[msg_id],
                    to_peer=to_peer,
                    reply_to_msg_id=target_topic_id,
                    drop_author=bool(drop_author),
                    silent=True,
                    random_id=[random_id],
                )
            ),
            log,
            "ForwardMessagesRequest(reply_to_msg_id)",
        )
    except TypeError:
        pass

    raise RuntimeError(
        "Your Telethon version does not support forwarding into forum topics via ForwardMessagesRequest."
    )


def _apply_backup_banner(image_path, banner_cfg=None, base_dir=None):
    img = Image.open(image_path).convert("RGBA")

    banner_cfg = banner_cfg or {}
    if banner_cfg.get("enabled", True) is False:
        return

    w, h = img.size

    band_height_ratio = float(banner_cfg.get("band_height_ratio", 0.22))
    band_min_px = int(banner_cfg.get("band_min_px", 90))
    band_h = max(int(h * band_height_ratio), band_min_px)
    band_y0 = (h - band_h) // 2

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def _parse_rgb(value, default):
        if isinstance(value, str):
            s = value.strip()
            if s.startswith("#"):
                s = s[1:]
            if len(s) == 6:
                try:
                    r = int(s[0:2], 16)
                    g = int(s[2:4], 16)
                    b = int(s[4:6], 16)
                    return (r, g, b)
                except Exception:
                    return default
            return default

        if isinstance(value, (list, tuple)) and len(value) >= 3:
            try:
                return (int(value[0]), int(value[1]), int(value[2]))
            except Exception:
                return default

        return default

    band_color = banner_cfg.get("band_color", [155, 0, 0])
    band_alpha_raw = banner_cfg.get("band_alpha", 255)
    try:
        band_alpha = float(band_alpha_raw)
    except Exception:
        band_alpha = 255.0

    if 0.0 <= band_alpha <= 100.0:
        band_alpha = (band_alpha / 100.0) * 255.0

    band_alpha = int(round(band_alpha))
    br, bg, bb = _parse_rgb(band_color, (155, 0, 0))
    band_alpha = max(0, min(255, band_alpha))
    draw.rectangle([(0, band_y0), (w, band_y0 + band_h)], fill=(br, bg, bb, band_alpha))

    text = str(banner_cfg.get("text", "BACKUP") or "BACKUP")
    font_size_ratio = float(banner_cfg.get("font_size_ratio", 0.74))
    font_size = max(int(band_h * font_size_ratio), 24)

    fonts_dirs = []
    if base_dir:
        fonts_dirs.append(os.path.join(str(base_dir), "fonts"))
    fonts_dirs.append(FONTS_DIR)

    font_paths = []

    def _name_candidates(name):
        if not name:
            return []
        s = str(name)
        lower = s.lower()
        if lower.endswith(".ttf") or lower.endswith(".otf") or lower.endswith(".ttc"):
            return [s]
        return [s, s + ".ttf", s + ".otf", s + ".ttc"]

    cfg_font_file = banner_cfg.get("font_file")
    if cfg_font_file:
        for fonts_dir in fonts_dirs:
            for cand in _name_candidates(cfg_font_file):
                font_paths.append(os.path.join(fonts_dir, cand))

    cfg_font_files = banner_cfg.get("font_files")
    if isinstance(cfg_font_files, (list, tuple)) and cfg_font_files:
        for fonts_dir in fonts_dirs:
            for name in cfg_font_files:
                if not name:
                    continue
                for cand in _name_candidates(name):
                    font_paths.append(os.path.join(fonts_dir, cand))

    for fonts_dir in fonts_dirs:
        font_paths.extend(
            [
                os.path.join(fonts_dir, "BebasNeue-Regular.ttf"),
                os.path.join(fonts_dir, "Oswald-Bold.ttf"),
                os.path.join(fonts_dir, "Anton-Regular.ttf"),
                os.path.join(fonts_dir, "Montserrat-SemiBold.ttf"),
                os.path.join(fonts_dir, "DejaVuSans-Bold.ttf"),
            ]
        )

    font = None
    for fp in font_paths:
        try:
            if os.path.exists(fp):
                font = ImageFont.truetype(fp, font_size)
                break
        except Exception:
            font = None

    if font is None:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    letter_spacing_ratio = float(banner_cfg.get("letter_spacing_ratio", 0.14))
    letter_spacing_min_px = int(banner_cfg.get("letter_spacing_min_px", 4))
    gap = max(letter_spacing_min_px, int(font_size * letter_spacing_ratio))

    def _glyph_w(ch):
        bbox = draw.textbbox((0, 0), ch, font=font)
        return int(bbox[2] - bbox[0])

    widths = [_glyph_w(ch) for ch in text]
    total_w = sum(widths) + gap * (len(text) - 1)
    x = int((w - total_w) / 2)
    y = band_y0 + (band_h // 2)

    outline_ratio = float(banner_cfg.get("outline_ratio", 0.06))
    outline_min_px = int(banner_cfg.get("outline_min_px", 2))
    outline = max(outline_min_px, int(font_size * outline_ratio))

    text_color = banner_cfg.get("text_color", [255, 255, 255])
    outline_color = banner_cfg.get("outline_color", [0, 0, 0])
    tr, tg, tb = _parse_rgb(text_color, (255, 255, 255))
    or_, og, ob = _parse_rgb(outline_color, (0, 0, 0))
    for ch, cw in zip(text, widths):
        cx = x + (cw // 2)
        for dx in range(-outline, outline + 1):
            for dy in range(-outline, outline + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text(
                    (cx + dx, y + dy),
                    ch,
                    font=font,
                    fill=(or_, og, ob, 255),
                    anchor="mm",
                )
        draw.text(
            (cx, y),
            ch,
            font=font,
            fill=(tr, tg, tb, 255),
            anchor="mm",
        )
        x += cw + gap

    out = Image.alpha_composite(img, overlay).convert("RGB")
    out.save(image_path, format="JPEG", quality=92)


async def _copy_group_photo(client, source_entity, target_entity, log, banner_cfg=None, base_dir=None):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp_path = tmp.name

        downloaded = await client.download_profile_photo(source_entity, file=tmp_path)
        if not downloaded or not os.path.exists(downloaded):
            return

        try:
            _apply_backup_banner(downloaded, banner_cfg=banner_cfg, base_dir=base_dir)
            log("Applied BACKUP banner to group photo")
        except Exception as e:
            log(f"Failed to apply BACKUP banner: {e}")

        uploaded = await client.upload_file(downloaded)
        photo = types.InputChatUploadedPhoto(file=uploaded)
        await _call_with_floodwait(
            lambda: client(functions.channels.EditPhotoRequest(channel=target_entity, photo=photo)),
            log,
            "EditPhotoRequest",
        )
        log("Copied group photo")

    except Exception as e:
        log(f"Failed to copy group photo: {e}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


async def _try_set_anonymous_admin(client, target_entity, log):
    try:
        me = await client.get_me()
        rights = types.ChatAdminRights(
            change_info=True,
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            add_admins=True,
            anonymous=True,
            manage_call=True,
            other=True,
            manage_topics=True,
        )
        await client(
            functions.channels.EditAdminRequest(
                channel=target_entity,
                user_id=me.id,
                admin_rights=rights,
                rank="admin",
            )
        )
        log("Enabled anonymous admin on backup group")
    except Exception as e:
        log(f"Could not enable anonymous admin: {e}")


async def _restrict_member_permissions(client, target_entity, log):
    try:
        rights = types.ChatBannedRights(
            until_date=0,
            send_messages=False,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
            embed_links=True,
            send_polls=True,
            change_info=True,
            invite_users=True,
            pin_messages=True,
            manage_topics=True,
        )

        await client(
            functions.messages.EditChatDefaultBannedRightsRequest(
                peer=target_entity,
                banned_rights=rights,
            )
        )
        log("Updated default member permissions (only send messages allowed)")
    except Exception as e:
        log(f"Failed to update default member permissions: {e}")


async def _set_about_and_invite_link(client, target_entity, source_title, source_id, log):
    invite_link = None
    try:
        exported = await _call_with_floodwait(
            lambda: client(
                functions.messages.ExportChatInviteRequest(
                    peer=target_entity,
                    expire_date=None,
                    usage_limit=None,
                    title="backup",
                    request_needed=True,
                )
            ),
            log,
            "ExportChatInviteRequest",
        )
        invite_link = getattr(exported, "link", None)
        if invite_link:
            log("Created invite link with approval required")
    except Exception as e:
        log(f"Failed to create invite link with approval required: {e}")

    about = f"Backup of {source_title} ({source_id})"
    if invite_link:
        about = about + "\n" + invite_link

    try:
        if hasattr(functions.channels, "EditAboutRequest"):
            await _call_with_floodwait(
                lambda: client(functions.channels.EditAboutRequest(channel=target_entity, about=about)),
                log,
                "EditAboutRequest",
            )
        else:
            await _call_with_floodwait(
                lambda: client(functions.messages.EditChatAboutRequest(peer=target_entity, about=about)),
                log,
                "EditChatAboutRequest",
            )
        log("Updated group bio/about")
    except Exception as e:
        log(f"Failed to update group bio/about: {e}")


async def _mirror_topics(client, source_entity, target_entity, topic_delay_s, log, ignore_list=None):
    try:
        await _call_with_floodwait(
            lambda: client(functions.channels.ToggleForumRequest(channel=target_entity, enabled=True)),
            log,
            "ToggleForumRequest",
        )
    except Exception as e:
        log(f"Failed to enable forum on backup group: {e}")
        return {}

    ignore_list = _normalize_ignore_list(ignore_list or [])
    topic_map = {}

    existing_by_title = {}
    try:
        offset_date_t = None
        offset_id_t = 0
        offset_topic_t = 0
        while True:
            res_t = await client(
                functions.channels.GetForumTopicsRequest(
                    channel=target_entity,
                    offset_date=offset_date_t,
                    offset_id=offset_id_t,
                    offset_topic=offset_topic_t,
                    limit=100,
                    q="",
                )
            )
            topics_t = getattr(res_t, "topics", None) or []
            if not topics_t:
                break
            for t in topics_t:
                title = getattr(t, "title", None)
                if title and title not in existing_by_title:
                    existing_by_title[title] = t.id

            last_t = topics_t[-1]
            offset_date_t = getattr(last_t, "date", None)
            offset_id_t = last_t.id
            offset_topic_t = last_t.id
    except Exception:
        existing_by_title = {}

    offset_date = None
    offset_id = 0
    offset_topic = 0

    while True:
        try:
            res = await client(
                functions.channels.GetForumTopicsRequest(
                    channel=source_entity,
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_topic=offset_topic,
                    limit=100,
                    q="",
                )
            )
        except Exception as e:
            log(f"Failed to fetch topics: {e}")
            return {}

        topics = getattr(res, "topics", None) or []
        if not topics:
            return topic_map

        for t in topics:
            topic_id = getattr(t, "id", None)
            title = getattr(t, "title", None)
            if not title:
                log(f"Skipping deleted topic marker (id={topic_id})")
                continue

            # Skip ignored topics
            if topic_id in ignore_list:
                log(f"Skipping ignored topic: {title} (id={topic_id})")
                continue
            existing_id = existing_by_title.get(title)
            if existing_id is not None:
                topic_map[topic_id] = existing_id
                continue
            try:
                updates = await _call_with_floodwait(
                    lambda: client(
                        functions.channels.CreateForumTopicRequest(
                            channel=target_entity,
                            title=title,
                            icon_color=getattr(t, "icon_color", None),
                            icon_emoji_id=getattr(t, "icon_emoji_id", None),
                        )
                    ),
                    log,
                    "CreateForumTopicRequest",
                )

                created_topic_id = None
                for u in getattr(updates, "updates", []) or []:
                    msg = getattr(u, "message", None)
                    if msg is not None and getattr(msg, "id", None) is not None:
                        created_topic_id = msg.id
                        break

                if created_topic_id is None:
                    created_topic_id = topic_id

                topic_map[topic_id] = created_topic_id
                log(f"Created topic: {title}")
            except errors.FloodWaitError as e:
                log(f"FloodWait while creating topic: sleeping {e.seconds}s")
                await asyncio.sleep(e.seconds + 5)
            except Exception as e:
                msg = str(e)
                if "premium" in msg.lower():
                    try:
                        updates = await _call_with_floodwait(
                            lambda: client(
                                functions.channels.CreateForumTopicRequest(
                                    channel=target_entity,
                                    title=title,
                                    icon_color=getattr(t, "icon_color", None),
                                    icon_emoji_id=None,
                                )
                            ),
                            log,
                            "CreateForumTopicRequest(no_emoji)",
                        )

                        created_topic_id = None
                        for u in getattr(updates, "updates", []) or []:
                            m = getattr(u, "message", None)
                            if m is not None and getattr(m, "id", None) is not None:
                                created_topic_id = m.id
                                break
                        if created_topic_id is None:
                            created_topic_id = topic_id

                        topic_map[topic_id] = created_topic_id
                        log(f"Created topic: {title}")
                    except Exception as e2:
                        msg2 = str(e2)
                        if "premium" in msg2.lower():
                            try:
                                updates = await _call_with_floodwait(
                                    lambda: client(
                                        functions.channels.CreateForumTopicRequest(
                                            channel=target_entity,
                                            title=title,
                                            icon_color=None,
                                            icon_emoji_id=None,
                                        )
                                    ),
                                    log,
                                    "CreateForumTopicRequest(no_emoji_no_color)",
                                )

                                created_topic_id = None
                                for u in getattr(updates, "updates", []) or []:
                                    m = getattr(u, "message", None)
                                    if m is not None and getattr(m, "id", None) is not None:
                                        created_topic_id = m.id
                                        break
                                if created_topic_id is None:
                                    created_topic_id = topic_id

                                topic_map[topic_id] = created_topic_id
                                log(f"Created topic: {title}")
                            except Exception as e3:
                                log(f"Failed to create topic '{title}' (no emoji/color): {e3}")
                        else:
                            log(f"Failed to create topic '{title}' (no emoji): {e2}")
                else:
                    log(f"Failed to create topic '{title}': {e}")

            await asyncio.sleep(topic_delay_s)

        last = topics[-1]
        offset_date = getattr(last, "date", None)
        offset_id = last.id
        offset_topic = last.id

    return topic_map


async def _mirror_topic_messages(
    client,
    cfg,
    args,
    source_entity,
    target_entity,
    topic_map,
    log,
):
    batch_size = int(cfg.get("batch_size", 100))
    message_delay_s = float(cfg.get("message_delay_s", 0.8))

    pause_every_messages = int(cfg.get("pause_every_messages", 1000))
    pause_duration_s = int(cfg.get("pause_duration_s", 300))

    drop_author = bool(cfg.get("drop_author", False))
    
    ignore_topics = cfg.get("ignore_topics", [])
    if not isinstance(ignore_topics, list):
        ignore_topics = []

    offset_file = str(cfg.get("offset_file", "offset.json"))
    if os.path.dirname(offset_file):
        os.makedirs(os.path.dirname(offset_file), exist_ok=True)

    offsets = load_offsets(offset_file)

    source_chat_key = getattr(source_entity, "id", None) or "source"
    target_chat_key = getattr(target_entity, "id", None) or "target"

    for source_topic_id, target_topic_id in topic_map.items():
        offset_key = make_offset_key(source_chat_key, source_topic_id, target_chat_key)
        last_id = offsets.get(offset_key, 0)
        sent_since_pause = 0
        spinner = itertools.cycle("|/-\\")

        log(f"Mirroring messages for topic {source_topic_id} -> {target_topic_id} (from {last_id})")

        while True:
            try:
                messages = await client.get_messages(
                    source_entity,
                    limit=batch_size,
                    min_id=last_id,
                    reverse=True,
                    reply_to=source_topic_id,
                )
            except Exception as e:
                log(f"Failed to fetch messages for topic {source_topic_id}: {e}")
                await asyncio.sleep(10)
                continue

            if not messages:
                break

            for msg in messages:
                try:
                    if _should_ignore_message(msg, source_chat_key, source_topic_id, ignore_topics):
                        last_id = msg.id
                        offsets[offset_key] = last_id
                        save_offsets(offset_file, offsets)
                        if not getattr(args, "quiet", False):
                            sys.stdout.write(f"\rSkipping ignored message {msg.id}...")
                            sys.stdout.flush()
                        continue
                    
                    if isinstance(msg, types.MessageService):
                        last_id = msg.id
                        offsets[offset_key] = last_id
                        save_offsets(offset_file, offsets)
                        continue

                    if drop_author and isinstance(getattr(msg, "media", None), types.MessageMediaWebPage):
                        log(
                            f"Sending MessageMediaWebPage {msg.id} as new message (drop_author fallback)"
                        )
                        await client.send_message(
                            entity=target_entity,
                            message=getattr(msg, "message", None) or "",
                            reply_to=target_topic_id,
                            link_preview=True,
                        )
                    else:
                        await _forward_message_to_topic(
                            client,
                            source_entity,
                            target_entity,
                            msg.id,
                            target_topic_id,
                            drop_author,
                            log,
                        )

                    last_id = msg.id
                    offsets[offset_key] = last_id
                    save_offsets(offset_file, offsets)
                    sent_since_pause += 1

                    if not getattr(args, "quiet", False):
                        sys.stdout.write(
                            f"\rSending messages... {next(spinner)} "
                            f"({sent_since_pause}/{pause_every_messages})"
                        )
                        sys.stdout.flush()

                    if sent_since_pause >= pause_every_messages:
                        if not getattr(args, "quiet", False):
                            _clear_status_line()
                        log(
                            f"Pausing for {pause_duration_s}s "
                            f"after {pause_every_messages} messages"
                        )
                        await _countdown(
                            pause_duration_s,
                            quiet=getattr(args, "quiet", False),
                            prefix="Pausing...",
                        )
                        sent_since_pause = 0

                    await asyncio.sleep(message_delay_s)

                except errors.FloodWaitError as e:
                    if not getattr(args, "quiet", False):
                        _clear_status_line()
                    log(f"FloodWait: sleeping {e.seconds}s")
                    await asyncio.sleep(e.seconds + 5)
                except Exception as e:
                    if not getattr(args, "quiet", False):
                        _clear_status_line()
                    log(f"Failed to send message {getattr(msg, 'id', None)}: {e}")

                    if getattr(msg, "id", None) is not None:
                        last_id = msg.id
                        offsets[offset_key] = last_id
                        save_offsets(offset_file, offsets)
                    await asyncio.sleep(2)

            if not getattr(args, "quiet", False):
                _clear_status_line()


async def run_clonner(cfg, args):
    api_id = int(cfg["api_id"])
    api_hash = str(cfg["api_hash"])

    source = cfg.get("source")
    if source is None:
        raise ValueError("Missing source")

    session_name = str(cfg.get("session_name", "session"))

    topic_delay_s = float(cfg.get("topic_delay_s", cfg.get("message_delay_s", 1.0)))

    log_fp = None
    if getattr(args, "logs", False):
        try:
            log_path = str(cfg.get("log_file", "log.log"))
            if os.path.dirname(log_path):
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
            log_fp = open(log_path, "a", encoding="utf-8")
        except Exception:
            log_fp = None

    def log(msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"
        if log_fp is not None:
            try:
                log_fp.write(line + "\n")
                log_fp.flush()
            except Exception:
                pass
        if not getattr(args, "quiet", False):
            print(line)

    log.quiet = bool(getattr(args, "quiet", False))

    offset_file = str(cfg.get("offset_file", "offset.json"))
    try:
        if os.path.dirname(offset_file):
            os.makedirs(os.path.dirname(offset_file), exist_ok=True)
        if not os.path.exists(offset_file):
            save_offsets(offset_file, {})
    except Exception:
        pass

    offsets = load_offsets(offset_file)
    client = await create_and_start_client(session_name, api_id, api_hash)

    try:
        source_chat, _ = parse_telegram_target(source)
    except Exception:
        if not getattr(args, "quiet", False):
            print("Invalid source. Check that your peer ID/username/link is valid.")
        await client.disconnect()
        return 2

    try:
        source_entity = await client.get_entity(source_chat)
    except (
        errors.ChatIdInvalidError,
        errors.PeerIdInvalidError,
        errors.UsernameInvalidError,
        errors.UsernameNotOccupiedError,
    ):
        if not getattr(args, "quiet", False):
            print("Invalid source. Check that your peer ID/username/link is valid.")
        await client.disconnect()
        return 2
    except Exception as e:
        log(f"Failed to resolve source entity: {e}")
        await client.disconnect()
        return 2

    source_title = getattr(source_entity, "title", None) or str(source)
    source_id = getattr(source_entity, "id", None)
    backup_title = f"[backup] {source_title}"

    created_new = False
    backup_key = f"mirror_backup:{source_id}"
    target_entity = None
    backup_channel_id = offsets.get(backup_key)
    if backup_channel_id:
        try:
            target_entity = await client.get_entity(types.PeerChannel(int(backup_channel_id)))
            log(f"Reusing existing backup group (channel_id={backup_channel_id})")
        except Exception as e:
            log(f"Could not reuse existing backup group (channel_id={backup_channel_id}): {e}")
            target_entity = None

    if target_entity is None:
        log(f"Creating backup group: {backup_title}")

        try:
            try:
                created = await client(
                    functions.channels.CreateChannelRequest(
                        title=backup_title,
                        about="",
                        megagroup=True,
                    )
                )
            except errors.FloodWaitError as e:
                wait_s = int(getattr(e, "seconds", 0)) + 5
                if wait_s > 3600:
                    raise RuntimeError(
                        f"FloodWait too large for CreateChannelRequest ({wait_s}s). "
                        "Telegram is rate-limiting group creation. Reuse the existing backup group "
                        "(don't delete it) or wait and try later."
                    )

                log(f"FloodWait on CreateChannelRequest: sleeping {wait_s}s")
                await _countdown(
                    wait_s,
                    quiet=getattr(args, "quiet", False),
                    prefix="FloodWait...",
                )
                created = await client(
                    functions.channels.CreateChannelRequest(
                        title=backup_title,
                        about="",
                        megagroup=True,
                    )
                )
        except Exception as e:
            await client.disconnect()
            raise RuntimeError(f"Failed to create backup group: {e}")

        target_entity = created.chats[0]
        created_new = True

        try:
            offsets[backup_key] = int(getattr(target_entity, "id", 0))
            save_offsets(offset_file, offsets)
        except Exception:
            pass

    if created_new:
        await _restrict_member_permissions(client, target_entity, log)
        await _set_about_and_invite_link(client, target_entity, source_title, source_id, log)
        await _copy_group_photo(
            client,
            source_entity,
            target_entity,
            log,
            banner_cfg=cfg.get("banner") if isinstance(cfg, dict) else None,
            base_dir=cfg.get("base_dir") if isinstance(cfg, dict) else None,
        )
        await _try_set_anonymous_admin(client, target_entity, log)

    is_forum = bool(getattr(source_entity, "forum", False))
    if is_forum:
        log("Source is a forum. Mirroring topics...")
        ignore_topics_cfg = cfg.get("ignore_topics", [])
        if not isinstance(ignore_topics_cfg, list):
            ignore_topics_cfg = []
        topic_map = await _mirror_topics(client, source_entity, target_entity, topic_delay_s, log, ignore_list=ignore_topics_cfg)
        if topic_map:
            log("Mirroring topic messages...")
            await _mirror_topic_messages(
                client,
                cfg,
                args,
                source_entity,
                target_entity,
                topic_map,
                log,
            )

    log("Mirror finished")
    await client.disconnect()
    if log_fp is not None:
        try:
            log_fp.close()
        except Exception:
            pass
    return 0
