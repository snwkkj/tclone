import argparse
import asyncio
import os

from analyzer import run_analyzer
from clonner import run_clonner
from config import load_config_raw
from forward import run_forwarder
from runtime import clean_runtime_files, open_settings_file, resolve_runtime


class _HelpFormatter(argparse.RawTextHelpFormatter):
    def _format_action_invocation(self, action):
        if not action.option_strings:
            return super()._format_action_invocation(action)

        if "--source" in action.option_strings or "--target" in action.option_strings:
            return ", ".join(action.option_strings)

        return super()._format_action_invocation(action)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tclone",
        description="Telegram message forwarder using Telethon",
        formatter_class=_HelpFormatter,
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
        "--clean",
        action="store_true",
        help="Delete session file and offset.json, then exit",
    )

    parser.add_argument(
        "-c",
        "--config",
        "--settings",
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
        metavar="SOURCE",
        help="Mirror a group: create a [backup] group, copy photo, and create topics",
    )

    parser.add_argument(
        "-a",
        "--analyzer",
        nargs="?",
        const=True,
        default=False,
        metavar="TARGET",
        help="Analyze a target chat and generate a storage report (txt + png)",
    )

    parser.add_argument(
        "-s",
        "--source",
        type=str,
        default=None,
        metavar="SOURCE",
        help="Override source chat/channel (ignores config.yml source)",
    )

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        default=None,
        metavar="TARGET",
        help="Override target chat/channel (ignores config.yml target)",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    base_dir, config_path = resolve_runtime()

    if args.config:
        open_settings_file(config_path)
        return 0

    if args.delete:
        removed = clean_runtime_files(base_dir)
        if removed:
            for path in removed:
                print(f"Removed: {path}")
        else:
            print("Nothing to clean.")
        return 0

    cfg = load_config_raw(config_path)

    try:
        from dotenv import load_dotenv  # type: ignore

        local_env = os.path.join(base_dir, ".env")
        local_env_example = os.path.join(base_dir, ".env.example")
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
        raise ValueError("Missing api_id/api_hash. Set them in config.yml or provide API_ID/API_HASH in .env")

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
