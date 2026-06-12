import os
import shutil
import subprocess
import sys

from config import DEFAULT_CONFIG_FILE, DEFAULT_CONFIG_TEXT


PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FONTS_DIR = os.path.join(PROJECT_DIR, "fonts")


def get_app_dir():
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        return os.path.join(home, "tclone")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "tclone")
    return os.path.join(home, ".tclone")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    if sys.platform.startswith("win"):
        try:
            subprocess.call(
                ["attrib", "+h", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def ensure_default_config(path):
    if os.path.exists(path):
        return

    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as config_file:
        config_file.write(DEFAULT_CONFIG_TEXT)


def resolve_runtime():
    local_config = os.path.join(os.getcwd(), DEFAULT_CONFIG_FILE)
    if os.path.exists(local_config):
        return os.getcwd(), local_config

    project_config = os.path.join(PROJECT_DIR, DEFAULT_CONFIG_FILE)
    project_manifest = os.path.join(PROJECT_DIR, "pyproject.toml")
    if os.path.exists(project_manifest) and os.path.exists(project_config):
        return PROJECT_DIR, project_config

    app_dir = get_app_dir()
    config_path = os.path.join(app_dir, DEFAULT_CONFIG_FILE)
    ensure_default_config(config_path)
    ensure_fonts(app_dir)
    return app_dir, config_path


def ensure_fonts(base_dir):
    fonts_dst = os.path.join(base_dir, "fonts")
    ensure_dir(fonts_dst)

    if not os.path.isdir(FONTS_DIR):
        return

    for name in os.listdir(FONTS_DIR):
        if not name.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        src = os.path.join(FONTS_DIR, name)
        dst = os.path.join(fonts_dst, name)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)


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
