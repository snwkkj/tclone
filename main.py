import argparse
import asyncio
import os
import shutil
import subprocess
import sys

SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
if os.path.isdir(SRC_DIR) and SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from tclone.config import DEFAULT_CONFIG_FILE, load_config_raw
from tclone.analyzer import run_analyzer
from tclone.clonner import run_clonner
from tclone.forward import run_forwarder


class _CleanHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action):
        if not action.option_strings:
            return super()._format_action_invocation(action)
        
        # Always show just the flags, no arguments
        return ', '.join(action.option_strings)
    
    def _format_action(self, action):
        # Temporarily remove nargs for formatting
        original_nargs = action.nargs
        if action.nargs in ('?', '*'):
            action.nargs = None
        
        result = super()._format_action(action)
        
        # Restore original nargs
        action.nargs = original_nargs
        return result


def build_parser():
    parser = argparse.ArgumentParser(
        description="Telegram message forwarder using Telethon",
        formatter_class=_CleanHelpFormatter,
        add_help=False,
    )

    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Run in silent mode (no terminal output, no spinner)",
    )

    parser.add_argument(
        "-l",
        "--logs",
        action="store_true",
        help="Write detailed execution logs to log.log",
    )

    parser.add_argument(
        "-d",
        "--delete",
        action="store_true",
        help="Delete session file and offsets.json, then exit",
    )

    parser.add_argument(
        "-c",
        "--config",
        action="store_true",
        help="Open config.yml in the default editor and exit",
    )

    parser.add_argument(
        "-f",
        "--forward",
        action="store_true",
        help="Forward mode (default)",
    )

    parser.add_argument(
        "-m",
        "--mirror",
        nargs="?",
        const=True,
        default=False,
        help="Mirror a group: create a [backup] group, copy photo, and create topics",
    )

    parser.add_argument(
        "-a",
        "--analyzer",
        nargs="?",
        const=True,
        default=False,
        help="Analyze a target chat and generate a storage report (txt + png)",
    )

    parser.add_argument(
        "-s",
        "--source",
        type=str,
        default=None,
        help="Override source chat/channel (ignores config.yml source)",
    )

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        default=None,
        help="Override target chat/channel (ignores config.yml target)",
    )

    return parser


def get_app_dir():
    if sys.platform.startswith("win"):
        return os.path.join(os.path.expanduser("~"), "tclone")

    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Application Support",
            "tclone",
        )

    return os.path.join(os.path.expanduser("~"), ".tclone")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

    if sys.platform.startswith("win"):
        try:
            subprocess.call(["attrib", "+h", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def ensure_default_config(path):
    if os.path.exists(path):
        return

    try:
        template_cfg = os.path.join(os.path.abspath(os.path.dirname(__file__)), DEFAULT_CONFIG_FILE)
        if os.path.exists(template_cfg):
            shutil.copy2(template_cfg, path)
            return
    except Exception:
        pass

    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "api_id: 0\n"
            "api_hash: \"\"\n"
            "source: -1000000000000\n"
            "target: -1000000000000\n\n"
            "batch_size: 100\n"
            "message_delay_s: 1.0\n\n"
            "pause_every_messages: 1000\n"
            "pause_duration_s: 300\n\n"
            "session_name: \"session\"\n"
            "log_file: \"log.log\"\n"
            "offset_file: \"offset.json\"\n"
            "drop_author: true\n"
            "banner:\n"
            "  enabled: true\n"
            "  text: \"BACKUP\"\n"
            "  font_file: \"BebasNeue-Regular.ttf\"\n"
            "  band_color: [155, 0, 0]\n"
            "  band_alpha: 255\n"
            "  band_height_ratio: 0.22\n"
            "  band_min_px: 90\n"
            "  font_size_ratio: 0.74\n"
            "  letter_spacing_ratio: 0.14\n"
            "  letter_spacing_min_px: 4\n"
            "  text_color: [255, 255, 255]\n"
            "  outline_color: [0, 0, 0]\n"
            "  outline_ratio: 0.06\n"
            "  outline_min_px: 2\n"
        )


def resolve_config_path(app_dir):
    local_cfg = os.path.join(os.getcwd(), DEFAULT_CONFIG_FILE)
    app_cfg = os.path.join(app_dir, DEFAULT_CONFIG_FILE)

    if os.path.exists(app_cfg):
        return app_cfg

    ensure_dir(app_dir)
    ensure_default_config(app_cfg)
    return app_cfg


def ensure_fonts(base_dir):
    fonts_dst = os.path.join(base_dir, "fonts")
    try:
        os.makedirs(fonts_dst, exist_ok=True)
    except Exception:
        return

    repo_root = os.path.abspath(os.path.dirname(__file__))
    src_dirs = [os.path.join(repo_root, "fonts"), os.path.join(repo_root, "fontes")]

    exts = (".ttf", ".otf", ".ttc")
    for src_dir in src_dirs:
        if not os.path.isdir(src_dir):
            continue
        try:
            for name in os.listdir(src_dir):
                if not name.lower().endswith(exts):
                    continue
                src_fp = os.path.join(src_dir, name)
                dst_fp = os.path.join(fonts_dst, name)
                if os.path.exists(dst_fp):
                    continue
                try:
                    shutil.copy2(src_fp, dst_fp)
                except Exception:
                    pass
        except Exception:
            pass


def open_settings_file(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
        return

    if shutil.which("termux-open"):
        subprocess.Popen(["termux-open", path])
        return

    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", path])
        return

    if shutil.which("nano"):
        subprocess.call(["nano", path])
        return

    raise RuntimeError("No default opener found (termux-open/xdg-open) and nano is not available")


def main():
    parser = build_parser()
    args = parser.parse_args()

    local_cfg = os.path.join(os.getcwd(), DEFAULT_CONFIG_FILE)
    if os.path.exists(local_cfg):
        base_dir = os.getcwd()
        config_path = local_cfg
    else:
        base_dir = get_app_dir()
        config_path = resolve_config_path(base_dir)

        ensure_fonts(base_dir)

    if args.config:
        open_settings_file(config_path)
        return 0

    cfg = load_config_raw(config_path)

    try:
        from dotenv import load_dotenv  # type: ignore

        local_env = os.path.join(os.getcwd(), ".env")
        local_env_example = os.path.join(os.getcwd(), ".env.example")
        if os.path.exists(local_env):
            load_dotenv(local_env, override=False)
        elif os.path.exists(local_env_example):
            load_dotenv(local_env_example, override=False)
        else:
            load_dotenv(override=False)
    except Exception:
        pass

    env_api_id = os.getenv("API_ID")
    env_api_hash = os.getenv("API_HASH")
    if env_api_id:
        cfg["api_id"] = env_api_id
    if env_api_hash:
        cfg["api_hash"] = env_api_hash

    if isinstance(args.mirror, str):
        cfg["source"] = args.mirror

    if isinstance(args.analyzer, str):
        cfg["target"] = args.analyzer

    if args.source is not None:
        cfg["source"] = args.source

    if args.target is not None:
        cfg["target"] = args.target

    if cfg.get("api_id") is None or cfg.get("api_hash") is None:
        raise ValueError(
            "Missing api_id/api_hash. Set them in config.yml or provide API_ID/API_HASH in .env"
        )

    if args.analyzer:
        if cfg.get("target") is None:
            raise ValueError("Missing target. Use --target or set 'target' in config.yml")
    elif args.mirror:
        if cfg.get("source") is None:
            raise ValueError("Missing source. Use --source or set 'source' in config.yml")
    else:
        if cfg.get("source") is None or cfg.get("target") is None:
            raise ValueError("Missing source/target. Use --source/--target or set them in config.yml")

    cfg["session_name"] = os.path.join(base_dir, "session")
    cfg["log_file"] = os.path.join(base_dir, "log.log")
    cfg["offset_file"] = os.path.join(base_dir, "offset.json")
    cfg["base_dir"] = base_dir

    try:
        if args.analyzer:
            return asyncio.run(run_analyzer(cfg, args))
        if args.mirror:
            return asyncio.run(run_clonner(cfg, args))
        return asyncio.run(run_forwarder(cfg, args))
    except KeyboardInterrupt:
        print("\nStopped by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
