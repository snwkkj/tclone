import asyncio
import itertools
import json
import os
import random
import re
import sys
from datetime import datetime

from telethon import errors
from telethon.tl import functions, types

from .session import create_and_start_client


def parse_telegram_target(value):
    if isinstance(value, int):
        return value, None

    if isinstance(value, str):
        value = value.strip()

        if value.lstrip("-").isdigit():
            return int(value), None

        m = re.match(r"https?://t\.me/c/(\d+)/(\d+)", value)
        if m:
            return int("-100" + m.group(1)), int(m.group(2))

        m = re.match(r"https?://t\.me/([^/]+)/(\d+)", value)
        if m:
            return m.group(1), int(m.group(2))

        m = re.match(r"https?://t\.me/([^/]+)$", value)
        if m:
            return m.group(1), None

        return value, None

    raise ValueError(f"Invalid format: {value}")


def make_offset_key(source_chat, source_topic, target_chat):
    if source_topic:
        return f"{source_chat}:{source_topic}->{target_chat}"
    return f"{source_chat}->{target_chat}"


def load_offsets(offset_file):
    if not os.path.exists(offset_file):
        return {}
    try:
        with open(offset_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_offsets(offset_file, offsets):
    with open(offset_file, "w", encoding="utf-8") as f:
        json.dump(offsets, f, indent=2)


async def countdown(seconds, quiet=False):
    for remaining in range(seconds, 0, -1):
        if not quiet:
            sys.stdout.write(f"\rPausing... {remaining}s remaining")
            sys.stdout.flush()
        await asyncio.sleep(1)

    if not quiet:
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()


async def _forward_message_low_level(
    client,
    source_entity,
    target_entity,
    msg_id,
    target_topic_id,
    drop_author,
):
    from_peer = await client.get_input_entity(source_entity)
    to_peer = await client.get_input_entity(target_entity)
    random_id = random.randint(-(2**63), 2**63 - 1)

    try:
        return await client(
            functions.messages.ForwardMessagesRequest(
                from_peer=from_peer,
                id=[msg_id],
                to_peer=to_peer,
                top_msg_id=target_topic_id,
                drop_author=bool(drop_author),
                silent=True,
                random_id=[random_id],
            )
        )
    except TypeError:
        pass

    return await client(
        functions.messages.ForwardMessagesRequest(
            from_peer=from_peer,
            id=[msg_id],
            to_peer=to_peer,
            reply_to_msg_id=target_topic_id,
            drop_author=bool(drop_author),
            silent=True,
            random_id=[random_id],
        )
    )


async def run_forwarder(cfg, args):
    api_id = int(cfg["api_id"])
    api_hash = str(cfg["api_hash"])

    source = cfg["source"]
    target = cfg["target"]

    batch_size = int(cfg.get("batch_size", 100))
    message_delay_s = float(cfg.get("message_delay_s", 0.8))

    pause_every_messages = int(cfg.get("pause_every_messages", 1000))
    pause_duration_s = int(cfg.get("pause_duration_s", 300))

    drop_author = bool(cfg.get("drop_author", False))

    session_name = str(cfg.get("session_name", "session"))
    log_file = str(cfg.get("log_file", "log.log"))
    offset_file = str(cfg.get("offset_file", "offset.json"))

    if os.path.dirname(session_name):
        os.makedirs(os.path.dirname(session_name), exist_ok=True)
    if os.path.dirname(log_file):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    if os.path.dirname(offset_file):
        os.makedirs(os.path.dirname(offset_file), exist_ok=True)

    def log(msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"

        if args.logs:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        if not args.quiet:
            print(line)

    if args.delete:
        removed = False

        session_file = f"{session_name}.session"
        if os.path.exists(session_file):
            os.remove(session_file)
            print(f"Removed session file: {session_file}")
            removed = True

        if os.path.exists(offset_file):
            os.remove(offset_file)
            print(f"Removed offset file: {offset_file}")
            removed = True

        if not removed:
            print("Nothing to clean.")

        return 0

    client = await create_and_start_client(session_name, api_id, api_hash)

    os.system("cls" if os.name == "nt" else "clear")

    me = await client.get_me()
    username = f"@{me.username}" if me.username else f"id={me.id}"

    try:
        source_chat, source_topic = parse_telegram_target(source)
        target_chat, target_topic = parse_telegram_target(target)
    except Exception:
        if not args.quiet:
            print("Invalid source/target. Check that your peer IDs/usernames/links are valid.")
        await client.disconnect()
        return 2

    try:
        source_entity = await client.get_entity(source_chat)
        target_entity = await client.get_entity(target_chat)
    except (
        errors.ChatIdInvalidError,
        errors.PeerIdInvalidError,
        errors.UsernameInvalidError,
        errors.UsernameNotOccupiedError,
    ):
        if not args.quiet:
            print("Invalid source/target. Check that your peer IDs/usernames/links are valid.")
        await client.disconnect()
        return 2
    except Exception as e:
        log(f"Failed to resolve source/target entity: {e}")
        await client.disconnect()
        return 2

    offsets = load_offsets(offset_file)
    offset_key = make_offset_key(source_chat, source_topic, target_chat)
    last_id = offsets.get(offset_key, 0)

    sent_since_pause = 0
    spinner = itertools.cycle("|/-\\")

    log("Forwarder started")
    log(f"Logged in as {username}")
    log(f"Source: {source}")
    log(f"Target: {target}")
    log(f"Starting from message ID: {last_id}")

    while True:
        try:
            messages = await client.get_messages(
                source_entity,
                limit=batch_size,
                min_id=last_id,
                reverse=True,
                reply_to=source_topic,
            )
        except Exception as e:
            log(f"Failed to fetch messages: {e}")
            await asyncio.sleep(10)
            continue

        if not messages:
            if not args.quiet:
                sys.stdout.write("\r" + " " * 120 + "\r\n")
                sys.stdout.flush()

            log("All messages have been successfully forwarded.")
            log(f"Last processed message_id: {last_id}")
            log("Script finished.")

            await client.disconnect()
            return 0

        for msg in messages:
            try:
                if isinstance(msg, types.MessageService):
                    last_id = msg.id
                    offsets[offset_key] = last_id
                    save_offsets(offset_file, offsets)
                    continue

                if drop_author and isinstance(getattr(msg, "media", None), types.MessageMediaWebPage):
                    await client.send_message(
                        entity=target_entity,
                        message=getattr(msg, "message", None) or "",
                        reply_to=target_topic,
                        link_preview=True,
                    )
                elif drop_author:
                    await _forward_message_low_level(
                        client,
                        source_entity,
                        target_entity,
                        msg.id,
                        target_topic,
                        drop_author,
                    )
                else:
                    await client.send_message(
                        entity=target_entity,
                        message=msg,
                        reply_to=target_topic,
                    )

                last_id = msg.id
                offsets[offset_key] = last_id
                save_offsets(offset_file, offsets)
                sent_since_pause += 1

                if not args.quiet:
                    sys.stdout.write(
                        f"\rSending messages... {next(spinner)} "
                        f"({sent_since_pause}/{pause_every_messages})"
                    )
                    sys.stdout.flush()

                if sent_since_pause >= pause_every_messages:
                    log(
                        f"Pausing for {pause_duration_s}s "
                        f"after {pause_every_messages} messages"
                    )

                    await countdown(pause_duration_s, quiet=args.quiet)
                    sent_since_pause = 0

                await asyncio.sleep(message_delay_s)

            except errors.FloodWaitError as e:
                log(f"FloodWait: sleeping {e.seconds}s")
                await asyncio.sleep(e.seconds + 5)

            except Exception as e:
                log(f"Failed to send message {msg.id}: {e}")
                await asyncio.sleep(2)
